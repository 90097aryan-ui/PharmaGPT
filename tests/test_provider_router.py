"""
tests/test_provider_router.py — Unit + integration tests for
pharmagpt/providers/router.py (the additive AI orchestration layer).

These tests never call a real Gemini/NVIDIA endpoint: `isolated_router`
swaps in throwaway copies of the router's provider registry/cache so fake
providers can be registered per test without touching module state other
tests (or pharmagpt.state's real gemini_client) depend on.
"""

import time
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

import pharmagpt.providers.router as router
from pharmagpt.providers.factory import ProviderConfigError
from pharmagpt.providers.router import FailureCategory, ProviderCallError, TaskIntent


class _FakeClient:
    """Duck-typed .models.generate_content()/.generate_content_stream(),
    same contract as google.genai.Client / NemotronClient. `fail_exception`
    lets a test control exactly which exception type/shape is raised on the
    first `fail_times` calls, so failure-classification behavior can be
    exercised deterministically; it defaults to a generic RuntimeError,
    matching the original (pre-classification) test fixtures below."""

    def __init__(self, name, *, fail_times=0, text="ok", chunks=None, fail_exception=None):
        self.name = name
        self.calls = 0
        self.fail_times = fail_times
        self.text = text
        self.chunks = chunks if chunks is not None else ["a", "b", "c"]
        self.fail_exception = fail_exception
        self.models = self

    def _raise(self):
        raise self.fail_exception if self.fail_exception is not None else RuntimeError(f"{self.name} exploded")

    def generate_content(self, *, model=None, contents=None, config=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            self._raise()
        return SimpleNamespace(
            text=self.text,
            usage_metadata=SimpleNamespace(prompt_token_count=5, candidates_token_count=7),
        )

    def generate_content_stream(self, *, model=None, contents=None, config=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            self._raise()
        for c in self.chunks:
            yield SimpleNamespace(text=c)


@pytest.fixture()
def isolated_router(monkeypatch):
    monkeypatch.setattr(router, "_PROVIDER_BUILDERS", dict(router._PROVIDER_BUILDERS))
    monkeypatch.setattr(router, "_PROVIDER_MODELS", dict(router._PROVIDER_MODELS))
    monkeypatch.setattr(router, "_CLIENT_CACHE", {})
    monkeypatch.setattr(router, "_provider_cooldown_until", {})
    monkeypatch.setattr(router, "DEFAULT_CHAT_PROVIDER", "nemotron")
    monkeypatch.setattr(router, "DEFAULT_DOCUMENT_PROVIDER", "gemini")
    monkeypatch.setattr(router, "ENABLE_FALLBACK", True)
    return router


def _register(rt, name, client, model="test-model"):
    rt.register_provider(name, lambda: client, model=model)


# ── Routing rules ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "intent",
    [TaskIntent.CHAT, TaskIntent.GENERAL_QA, TaskIntent.SUMMARY, TaskIntent.SEARCH, TaskIntent.UNKNOWN],
)
def test_chat_intents_route_to_chat_provider(isolated_router, intent):
    assert isolated_router._provider_for_intent(intent) == "nemotron"


@pytest.mark.parametrize(
    "intent",
    [
        TaskIntent.URS, TaskIntent.DQ, TaskIntent.IQ, TaskIntent.OQ, TaskIntent.PQ,
        TaskIntent.SAT, TaskIntent.FAT, TaskIntent.VALIDATION_PLAN,
        TaskIntent.VALIDATION_SUMMARY, TaskIntent.RISK_ASSESSMENT, TaskIntent.FMEA,
        TaskIntent.CAPA, TaskIntent.CHANGE_CONTROL, TaskIntent.SOP, TaskIntent.FACILITY_URS,
    ],
)
def test_document_intents_route_to_document_provider(isolated_router, intent):
    assert isolated_router._provider_for_intent(intent) == "gemini"


def test_get_client_returns_registered_provider_client(isolated_router):
    fake = _FakeClient("gemini")
    _register(isolated_router, "gemini", fake)
    assert isolated_router.get_client(TaskIntent.URS) is fake


def test_get_client_never_builds_unrelated_unconfigured_provider(isolated_router):
    # Only "nemotron" is registered with a working builder; routing a
    # document intent must never touch the (broken) "gemini" builder.
    def _boom():
        raise AssertionError("gemini builder must not be invoked for a chat intent")

    isolated_router.register_provider("gemini", _boom, model="g")
    _register(isolated_router, "nemotron", _FakeClient("nemotron"))
    isolated_router.get_client(TaskIntent.CHAT)  # must not raise


# ── Future-provider extensibility ────────────────────────────────────────

def test_register_provider_supports_new_providers(isolated_router):
    fake = _FakeClient("claude")
    _register(isolated_router, "claude", fake, model="claude-x")
    # Point the chat bucket at the newly-registered provider via config, no
    # other code changes required.
    import pharmagpt.providers.router as rt
    rt.DEFAULT_CHAT_PROVIDER = "claude"
    try:
        assert rt.get_client(TaskIntent.CHAT) is fake
    finally:
        rt.DEFAULT_CHAT_PROVIDER = "nemotron"


# ── generate_content: success, retry, fallback ───────────────────────────

def test_generate_content_success_first_try(isolated_router):
    fake = _FakeClient("nemotron", text="hello")
    _register(isolated_router, "nemotron", fake)
    _register(isolated_router, "gemini", _FakeClient("gemini"))

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "hello"
    assert fake.calls == 1


def test_generate_content_retries_once_before_fallback(isolated_router):
    primary = _FakeClient("nemotron", fail_times=1, text="recovered")
    _register(isolated_router, "nemotron", primary)
    _register(isolated_router, "gemini", _FakeClient("gemini"))

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "recovered"
    assert primary.calls == 2  # one failure + one successful retry, no fallback needed


def test_generate_content_falls_back_after_primary_exhausted(isolated_router):
    primary = _FakeClient("nemotron", fail_times=99)  # always fails
    fallback = _FakeClient("gemini", text="fallback-worked")
    _register(isolated_router, "nemotron", primary)
    _register(isolated_router, "gemini", fallback)

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "fallback-worked"
    assert primary.calls == 2  # retried once
    assert fallback.calls == 1  # single fallback attempt, not retried


def test_generate_content_raises_provider_call_error_when_all_fail(isolated_router):
    _register(isolated_router, "nemotron", _FakeClient("nemotron", fail_times=99))
    _register(isolated_router, "gemini", _FakeClient("gemini", fail_times=99))

    with pytest.raises(ProviderCallError) as exc_info:
        isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert exc_info.value.__cause__ is not None
    assert "chat" in str(exc_info.value)


def test_generate_content_falls_back_on_builder_config_error(isolated_router):
    """A misconfigured primary provider (e.g. missing API key -> builder
    raises ProviderConfigError on first use) must trigger the same
    retry+fallback path as a runtime call failure, not leak past it."""

    def _broken_builder():
        raise router.ProviderConfigError("NVIDIA_API_KEY missing")

    isolated_router.register_provider("nemotron", _broken_builder, model="n")
    fallback = _FakeClient("gemini", text="fallback-worked")
    _register(isolated_router, "gemini", fallback)

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "fallback-worked"
    assert fallback.calls == 1


def test_fallback_disabled_fails_fast_without_trying_secondary(isolated_router):
    isolated_router.ENABLE_FALLBACK = False
    primary = _FakeClient("nemotron", fail_times=99)
    fallback = _FakeClient("gemini", text="should not be used")
    _register(isolated_router, "nemotron", primary)
    _register(isolated_router, "gemini", fallback)

    with pytest.raises(ProviderCallError):
        isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert primary.calls == 2  # still retries once
    assert fallback.calls == 0  # never touched


def test_generate_content_logs_required_fields(isolated_router, caplog):
    _register(isolated_router, "nemotron", _FakeClient("nemotron", text="hi"))
    _register(isolated_router, "gemini", _FakeClient("gemini"))

    # pharmagpt/logging_config.py sets propagate=False on the "pharmagpt"
    # logger namespace (by design, so gunicorn's root handler doesn't
    # double-log) — caplog's handler sits on the root logger, so it must be
    # attached directly to router's logger here to observe records.
    router_logger = router.logger
    router_logger.addHandler(caplog.handler)
    router_logger.setLevel("INFO")
    try:
        isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    finally:
        router_logger.removeHandler(caplog.handler)

    matches = [r for r in caplog.records if "ai_router_call" in r.getMessage()]
    assert matches, f"no ai_router_call log record captured; got: {[r.getMessage() for r in caplog.records]}"
    msg = matches[0].getMessage()
    for field in ("intent=chat", "provider=nemotron", "model=", "latency_ms=", "success=True", "fallback_used=False", "prompt_tokens=5", "completion_tokens=7"):
        assert field in msg


# ── generate_content_stream ──────────────────────────────────────────────

def test_generate_content_stream_success(isolated_router):
    _register(isolated_router, "nemotron", _FakeClient("nemotron", chunks=["x", "y"]))
    _register(isolated_router, "gemini", _FakeClient("gemini"))

    chunks = list(isolated_router.generate_content_stream(TaskIntent.CHAT, contents=[]))
    assert [c.text for c in chunks] == ["x", "y"]


def test_generate_content_stream_empty_stream_returns_empty_iterable_not_none(isolated_router):
    """Regression test (Stage 3): a provider whose stream is genuinely
    empty (zero chunks, immediate StopIteration on the first next()) is a
    successful call, not a failure -- generate_content_stream() must
    return an empty iterable, never None, since every caller does
    `for chunk in ai_router.generate_content_stream(...)`. A bare `return`
    inside this (non-generator) function silently returned None instead,
    crashing every such caller with "'NoneType' object is not iterable" --
    present since Stage 1, first caught by Document Control's (Stage 3)
    empty-output tests, which are what actually exercise a zero-chunk
    stream."""
    _register(isolated_router, "nemotron", _FakeClient("nemotron", chunks=[]))
    _register(isolated_router, "gemini", _FakeClient("gemini"))

    result = isolated_router.generate_content_stream(TaskIntent.CHAT, contents=[])
    assert result is not None
    assert list(result) == []


def test_generate_content_stream_falls_back_when_start_fails(isolated_router):
    primary = _FakeClient("nemotron", fail_times=99)
    fallback = _FakeClient("gemini", chunks=["fb1", "fb2"])
    _register(isolated_router, "nemotron", primary)
    _register(isolated_router, "gemini", fallback)

    chunks = list(isolated_router.generate_content_stream(TaskIntent.CHAT, contents=[]))
    assert [c.text for c in chunks] == ["fb1", "fb2"]
    assert primary.calls == 2
    assert fallback.calls == 1


def test_generate_content_stream_raises_when_all_fail(isolated_router):
    _register(isolated_router, "nemotron", _FakeClient("nemotron", fail_times=99))
    _register(isolated_router, "gemini", _FakeClient("gemini", fail_times=99))

    with pytest.raises(ProviderCallError):
        list(isolated_router.generate_content_stream(TaskIntent.CHAT, contents=[]))


# ── Failure classification ───────────────────────────────────────────────

def _quota_error():
    return genai_errors.ClientError(429, {"message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"})


def _auth_error():
    return genai_errors.ClientError(401, {"message": "invalid api key", "status": "UNAUTHENTICATED"})


def _model_error():
    return genai_errors.ClientError(400, {"message": "malformed request body", "status": "INVALID_ARGUMENT"})


def _safety_error():
    return genai_errors.ClientError(400, {"message": "response blocked", "status": "SAFETY"})


def _server_error():
    return genai_errors.ServerError(503, {"message": "backend unavailable", "status": "UNAVAILABLE"})


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_quota_error(), FailureCategory.QUOTA),
        (_auth_error(), FailureCategory.AUTHENTICATION),
        (_model_error(), FailureCategory.MODEL),
        (_safety_error(), FailureCategory.SAFETY),
        (_server_error(), FailureCategory.TRANSIENT),
        (ProviderConfigError("NVIDIA_API_KEY missing"), FailureCategory.AUTHENTICATION),
        (TypeError("bad kwargs"), FailureCategory.APPLICATION),
        (KeyError("missing field"), FailureCategory.APPLICATION),
        (RuntimeError("something unexpected"), FailureCategory.TRANSIENT),
    ],
)
def test_classify_failure(exc, expected):
    assert router._classify_failure(exc) is expected


def test_quota_failure_is_not_retried_on_same_provider(isolated_router):
    primary = _FakeClient("gemini", fail_times=1, fail_exception=_quota_error())
    fallback = _FakeClient("nemotron", text="fallback-worked")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", fallback)
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "fallback-worked"
    assert primary.calls == 1  # NOT retried — quota failures skip the same-provider retry
    assert fallback.calls == 1


def test_transient_failure_is_retried_before_fallback(isolated_router):
    primary = _FakeClient("gemini", fail_times=1, fail_exception=_server_error(), text="recovered")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", _FakeClient("nemotron"))
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "recovered"
    assert primary.calls == 2  # bounded retry: one failure + one successful retry


def test_model_failure_is_retried_before_fallback(isolated_router):
    primary = _FakeClient("gemini", fail_times=1, fail_exception=_model_error(), text="recovered")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", _FakeClient("nemotron"))
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "recovered"
    assert primary.calls == 2


def test_authentication_failure_is_not_retried_but_falls_back(isolated_router):
    primary = _FakeClient("gemini", fail_times=99, fail_exception=_auth_error())
    fallback = _FakeClient("nemotron", text="fallback-worked")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", fallback)
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "fallback-worked"
    assert primary.calls == 1  # not retried
    assert fallback.calls == 1


def test_safety_failure_does_not_retry_or_fall_back(isolated_router):
    primary = _FakeClient("gemini", fail_times=99, fail_exception=_safety_error())
    fallback = _FakeClient("nemotron", text="should not be used")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", fallback)
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    with pytest.raises(ProviderCallError) as exc_info:
        isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert "category=safety" in str(exc_info.value)
    assert primary.calls == 1
    assert fallback.calls == 0  # never touched — a safety rejection is not a provider problem


def test_application_failure_does_not_retry_or_fall_back(isolated_router):
    primary = _FakeClient("gemini", fail_times=99, fail_exception=TypeError("bad request shape"))
    fallback = _FakeClient("nemotron", text="should not be used")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", fallback)
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    with pytest.raises(ProviderCallError) as exc_info:
        isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert "category=application" in str(exc_info.value)
    assert primary.calls == 1
    assert fallback.calls == 0  # a bug in our own code would fail identically on any provider


def test_generate_content_stream_quota_failure_not_retried(isolated_router):
    primary = _FakeClient("gemini", fail_times=1, fail_exception=_quota_error())
    fallback = _FakeClient("nemotron", chunks=["fb"])
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", fallback)
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    chunks = list(isolated_router.generate_content_stream(TaskIntent.CHAT, contents=[]))
    assert [c.text for c in chunks] == ["fb"]
    assert primary.calls == 1
    assert fallback.calls == 1


# ── Circuit breaker / cooldown ───────────────────────────────────────────

def test_quota_failure_starts_cooldown_for_that_provider(isolated_router):
    primary = _FakeClient("gemini", fail_times=1, fail_exception=_quota_error())
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", _FakeClient("nemotron", text="fallback-worked"))
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    assert not isolated_router._in_cooldown("gemini")
    isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert isolated_router._in_cooldown("gemini")


def test_cooled_down_provider_is_skipped_entirely(isolated_router, monkeypatch):
    # A provider already in cooldown must not be called at all — not even
    # once — on a subsequent request; the router should go straight to the
    # fallback provider without wasting a call rediscovering the same 429.
    primary = _FakeClient("gemini", fail_times=0)  # would succeed if called
    fallback = _FakeClient("nemotron", text="fallback-worked")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", fallback)
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    isolated_router._provider_cooldown_until["gemini"] = time.monotonic() + 60

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "fallback-worked"
    assert primary.calls == 0  # never invoked while cooling down
    assert fallback.calls == 1


def test_cooldown_expires_and_provider_is_retried(isolated_router):
    primary = _FakeClient("gemini", fail_times=0, text="recovered")
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", _FakeClient("nemotron", text="should not be used"))
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    # Cooldown that already expired in the past.
    isolated_router._provider_cooldown_until["gemini"] = time.monotonic() - 1

    response = isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert response.text == "recovered"
    assert primary.calls == 1


def test_both_providers_cooling_down_raises_without_calling_either(isolated_router):
    primary = _FakeClient("gemini", fail_times=0)
    fallback = _FakeClient("nemotron", fail_times=0)
    _register(isolated_router, "gemini", primary)
    _register(isolated_router, "nemotron", fallback)
    isolated_router.DEFAULT_CHAT_PROVIDER = "gemini"

    isolated_router._provider_cooldown_until["gemini"] = time.monotonic() + 60
    isolated_router._provider_cooldown_until["nemotron"] = time.monotonic() + 60

    with pytest.raises(ProviderCallError):
        isolated_router.generate_content(TaskIntent.CHAT, contents=[])
    assert primary.calls == 0
    assert fallback.calls == 0


# ── Backward compatibility: existing gemini_client path is untouched ────────

def test_state_gemini_client_still_importable_and_unaffected():
    """Importing/using the router must never disturb pharmagpt.state's
    module-level gemini_client singleton every existing route/service uses."""
    from pharmagpt.state import gemini_client

    assert hasattr(gemini_client, "models")
    assert hasattr(gemini_client.models, "generate_content")

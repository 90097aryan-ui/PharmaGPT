"""
tests/test_provider_router.py — Unit + integration tests for
pharmagpt/providers/router.py (the additive AI orchestration layer).

These tests never call a real Gemini/NVIDIA endpoint: `isolated_router`
swaps in throwaway copies of the router's provider registry/cache so fake
providers can be registered per test without touching module state other
tests (or pharmagpt.state's real gemini_client) depend on.
"""

from types import SimpleNamespace

import pytest

import pharmagpt.providers.router as router
from pharmagpt.providers.router import ProviderCallError, TaskIntent


class _FakeClient:
    """Duck-typed .models.generate_content()/.generate_content_stream(),
    same contract as google.genai.Client / NemotronClient."""

    def __init__(self, name, *, fail_times=0, text="ok", chunks=None):
        self.name = name
        self.calls = 0
        self.fail_times = fail_times
        self.text = text
        self.chunks = chunks if chunks is not None else ["a", "b", "c"]
        self.models = self

    def generate_content(self, *, model=None, contents=None, config=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"{self.name} exploded")
        return SimpleNamespace(
            text=self.text,
            usage_metadata=SimpleNamespace(prompt_token_count=5, candidates_token_count=7),
        )

    def generate_content_stream(self, *, model=None, contents=None, config=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"{self.name} exploded")
        for c in self.chunks:
            yield SimpleNamespace(text=c)


@pytest.fixture()
def isolated_router(monkeypatch):
    monkeypatch.setattr(router, "_PROVIDER_BUILDERS", dict(router._PROVIDER_BUILDERS))
    monkeypatch.setattr(router, "_PROVIDER_MODELS", dict(router._PROVIDER_MODELS))
    monkeypatch.setattr(router, "_CLIENT_CACHE", {})
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


# ── Backward compatibility: existing gemini_client path is untouched ────────

def test_state_gemini_client_still_importable_and_unaffected():
    """Importing/using the router must never disturb pharmagpt.state's
    module-level gemini_client singleton every existing route/service uses."""
    from pharmagpt.state import gemini_client

    assert hasattr(gemini_client, "models")
    assert hasattr(gemini_client.models, "generate_content")

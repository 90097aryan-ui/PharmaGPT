"""
tests/test_nemotron_provider_logging.py — Security regression coverage for
the NVIDIA provider's logging.

Root cause (Stage 4B): NVIDIA_MODEL is normally a non-secret catalog slug
('vendor/model-name', e.g. 'nvidia/nemotron-3-ultra-550b-a55b') and was
logged in full at INFO level in several places
(providers/nemotron_client.py, providers/factory.py) on that assumption.
When a real deployment had a key-shaped value in NVIDIA_MODEL instead (the
two vars swapped/misentered), that value was logged in plaintext. The fix
(providers/nemotron_client.py::safe_model_label()) redacts any value that
doesn't match the documented catalog-slug shape before it reaches a log
call; NVIDIA_API_KEY itself was never logged anywhere and stays that way.

These tests never make a real network call (requests.post is monkeypatched)
and never assert on or print a real credential — REAL_LOOKING_KEY below is a
synthetic, obviously-fake string used only to prove the redaction logic,
not a real NVIDIA key.

pharmagpt/logging_config.py sets propagate=False on the "pharmagpt" logger
namespace (so gunicorn's root handler doesn't double-log), so caplog's
handler — which attaches to the root logger by default — would never see
these records via plain `caplog.at_level(...)`. Attaching caplog's handler
directly to the module's own logger (matching
tests/test_provider_router.py's established pattern) is required.
"""

import logging
from types import SimpleNamespace

import pytest

from pharmagpt.providers import factory
from pharmagpt.providers import nemotron_client as nc

# Obviously-synthetic test fixtures — not real credentials.
REAL_LOOKING_KEY = "nvapi-FAKEKEYSHAPEDVALUEFORTESTINGONLYNOTAREALCREDENTIAL9x"
FAKE_API_KEY = "nvapi-also-fake-test-only-not-a-real-credential"
VALID_MODEL_SLUG = "nvidia/nemotron-3-ultra-550b-a55b"


def _captured_log_text(logger_obj, caplog, fn):
    logger_obj.addHandler(caplog.handler)
    logger_obj.setLevel("INFO")
    try:
        fn()
    finally:
        logger_obj.removeHandler(caplog.handler)
    return "\n".join(r.getMessage() for r in caplog.records)


# ── safe_model_label(): unit coverage ───────────────────────────────────────

def test_safe_model_label_passes_through_valid_catalog_slug():
    assert nc.safe_model_label(VALID_MODEL_SLUG) == VALID_MODEL_SLUG


def test_safe_model_label_redacts_key_shaped_value():
    label = nc.safe_model_label(REAL_LOOKING_KEY)
    assert REAL_LOOKING_KEY not in label
    assert "redacted" in label.lower()


def test_safe_model_label_redacts_value_with_no_slash():
    label = nc.safe_model_label("some-bare-model-name-no-vendor-prefix")
    assert "redacted" in label.lower()


def test_safe_model_label_redacts_nvapi_prefixed_value_even_with_a_slash():
    # Belt-and-suspenders: the nvapi- prefix check must catch a key-shaped
    # value independently of slash presence, not rely on slash-absence alone.
    value = "nvapi-something/looks-like-a-slug"
    label = nc.safe_model_label(value)
    assert value not in label
    assert "redacted" in label.lower()


def test_safe_model_label_handles_unset():
    assert nc.safe_model_label(None) == "<unset>"
    assert nc.safe_model_label("") == "<unset>"


# ── Integration: real log call sites never emit a key-shaped model value ───

class _FakeResponse:
    status_code = 200

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    def iter_lines(self, decode_unicode=True):
        yield 'data: {"choices": [{"delta": {"content": "ok"}}]}'
        yield "data: [DONE]"


def _contents():
    return [SimpleNamespace(role="user", parts=[SimpleNamespace(text="hi")])]


def test_generate_content_never_logs_key_shaped_model_or_api_key(monkeypatch, caplog):
    monkeypatch.setattr(nc.requests, "post", lambda *a, **k: _FakeResponse())
    client = nc.NemotronClient(api_key=FAKE_API_KEY, model=REAL_LOOKING_KEY)

    log_text = _captured_log_text(
        nc.logger, caplog,
        lambda: client.models.generate_content(contents=_contents()),
    )

    assert REAL_LOOKING_KEY not in log_text
    assert FAKE_API_KEY not in log_text
    assert "redacted" in log_text.lower()


def test_generate_content_stream_never_logs_key_shaped_model_or_api_key(monkeypatch, caplog):
    monkeypatch.setattr(nc.requests, "post", lambda *a, **k: _FakeResponse())
    client = nc.NemotronClient(api_key=FAKE_API_KEY, model=REAL_LOOKING_KEY)

    log_text = _captured_log_text(
        nc.logger, caplog,
        lambda: list(client.models.generate_content_stream(contents=_contents())),
    )

    assert REAL_LOOKING_KEY not in log_text
    assert FAKE_API_KEY not in log_text
    assert "redacted" in log_text.lower()


def test_generate_content_still_logs_legitimate_model_value(monkeypatch, caplog):
    """The fix must not over-redact -- a real catalog slug stays fully
    visible in logs for observability/debugging, exactly as before."""
    monkeypatch.setattr(nc.requests, "post", lambda *a, **k: _FakeResponse())
    client = nc.NemotronClient(api_key=FAKE_API_KEY, model=VALID_MODEL_SLUG)

    log_text = _captured_log_text(
        nc.logger, caplog,
        lambda: client.models.generate_content(contents=_contents()),
    )

    assert VALID_MODEL_SLUG in log_text
    assert FAKE_API_KEY not in log_text


def test_factory_never_logs_key_shaped_model_or_api_key(caplog):
    log_text = _captured_log_text(
        factory.logger, caplog,
        lambda: factory.get_ai_client("nemotron", None, FAKE_API_KEY, REAL_LOOKING_KEY),
    )

    assert REAL_LOOKING_KEY not in log_text
    assert FAKE_API_KEY not in log_text
    assert "redacted" in log_text.lower()


def test_factory_still_logs_legitimate_model_value(caplog):
    log_text = _captured_log_text(
        factory.logger, caplog,
        lambda: factory.get_ai_client("nemotron", None, FAKE_API_KEY, VALID_MODEL_SLUG),
    )

    assert VALID_MODEL_SLUG in log_text
    assert FAKE_API_KEY not in log_text


# ── Source-level guard: the API key must never reach any log call site ─────

def _logger_call_arg_names(module):
    """AST-based (not line-window) scan: every argument name/attribute
    referenced inside a logger.<level>(...) call anywhere in `module`'s
    source, across every call site."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_logger_call = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "logger"
        )
        if not is_logger_call:
            continue
        for arg in ast.walk(node):
            if isinstance(arg, ast.Name):
                names.add(arg.id)
            elif isinstance(arg, ast.Attribute):
                names.add(arg.attr)
    return names


def test_api_key_never_referenced_in_any_logger_call():
    """Structural guard, not just a runtime check: no logger.<level>(...)
    call anywhere in nemotron_client.py or factory.py may reference
    api_key/nvidia_api_key/gemini_api_key/_headers as an argument — the
    only legitimate use of the key is building the Authorization header
    (nemotron_client.py) or constructing the genai.Client (factory.py),
    never logging it. Catches a future regression (e.g. someone adding a
    debug log of the request headers) structurally, independent of the
    runtime tests above."""
    forbidden = {"api_key", "nvidia_api_key", "gemini_api_key", "_headers"}
    for module in (nc, factory):
        found = _logger_call_arg_names(module) & forbidden
        assert not found, f"{module.__name__}: logger call references {found}"

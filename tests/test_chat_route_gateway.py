"""
tests/test_chat_route_gateway.py — routes/chat.py's migration onto the AI
Gateway (pharmagpt/providers/router.py), Stage 1 pilot call site.

These tests never call a real Gemini/NVIDIA endpoint: pharmagpt.routes.chat's
ai_router.generate_content_stream is monkeypatched directly, mirroring how
tests/test_provider_router.py isolates the router itself.
"""

import json

import pharmagpt.routes.chat as chat_route
from pharmagpt import database as db
from pharmagpt.providers.router import ProviderCallError
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID


def _make_project():
    return db.create_project(
        "Gateway Test Project", "Tablet Press", "Acme", "Production",
        "IQ/OQ/PQ", company_id=BOOTSTRAP_COMPANY_ID,
    )


def _sse_events(response):
    body = response.get_data(as_text=True)
    events = []
    for block in body.strip().split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: "):]))
    return events


def test_stream_success_uses_router(client, monkeypatch):
    from types import SimpleNamespace

    project = _make_project()

    def fake_stream(intent, *, contents, config=None, **kwargs):
        assert intent.value == "chat"
        yield SimpleNamespace(text="Hello ")
        yield SimpleNamespace(text="world")

    monkeypatch.setattr(chat_route.ai_router, "generate_content_stream", fake_stream)

    resp = client.post("/stream", json={
        "message": "hi", "project_id": project["id"], "use_documents": False,
    })
    events = _sse_events(resp)
    assert "".join(e.get("chunk", "") for e in events if "chunk" in e) == "Hello world"
    assert any(e.get("done") for e in events)


def test_stream_reports_error_when_every_provider_fails(client, monkeypatch):
    project = _make_project()

    def fake_stream(intent, *, contents, config=None, **kwargs):
        # Mirrors the real router: every provider exhausted (retry +
        # cooldown-aware fallback), raised before any chunk is produced.
        raise ProviderCallError("AI request failed for intent=chat after retry and fallback (category=quota).")

    monkeypatch.setattr(chat_route.ai_router, "generate_content_stream", fake_stream)

    resp = client.post("/stream", json={
        "message": "hi", "project_id": project["id"], "use_documents": False,
    })
    events = _sse_events(resp)
    error_events = [e for e in events if "error" in e]
    assert error_events, f"expected an error SSE event, got: {events}"
    # The sanitized gateway message reaches the client -- never the raw
    # upstream provider error text (ProviderCallError's own contract).
    assert error_events[0]["error"] == "AI service is temporarily unavailable. Please try again."

    # History rollback happened: the optimistic user message saved before
    # streaming started must have been cleared, same as the pre-existing
    # errors.ServerError rollback behavior.
    assert db.get_project_messages(project["id"]) == []

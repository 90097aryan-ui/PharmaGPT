"""
tests/test_risk_generate_endpoint.py — Regression coverage for the
POST /risk/assessments/<id>/generate request chain (AI Risk Assistant
"AI Generate Risk Items" button, pharmagpt/static/js/risk.js ->
pharmagpt/routes/risk.py::generate_items -> Gemini).

Confirms the frontend fetch() URL and the Flask route agree, and that
every outcome on this path — success, unmatched route, wrong method,
a Gemini failure, and a missing/invalid auth token — returns JSON, never
Flask's default HTML error page (a fetch() caller can't parse HTML and
fails with "Unexpected token '<'").
"""

from unittest.mock import patch

import pytest

from pharmagpt.auth.context import TenantContext

TENANT = TenantContext(
    user_id="user-1", email="jane@example.com", display_name="Jane Admin",
    role="company_admin", company_id="company-1",
)
AUTH_HEADERS = {"Authorization": "Bearer good-token"}
MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


@pytest.fixture()
def client(db_path):
    """Real auth gate (not bypassed) — this suite exercises 401 paths too."""
    import pharmagpt.app as appmod

    return appmod.app.test_client()


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


def _create_assessment(client):
    with _as(TENANT):
        resp = client.post(
            "/risk/assessments",
            json={"title": "Autoclave FMEA", "assessment_type": "process", "methodology": "FMEA"},
            headers=AUTH_HEADERS,
        )
    return resp.get_json()["id"]


class _FakeChunk:
    def __init__(self, text):
        self.text = text


# ── 1. AI Risk Generation (the reported flow) ────────────────────────────────

def test_frontend_url_matches_the_registered_flask_route(client):
    """pharmagpt/static/js/risk.js:934 calls POST /risk/assessments/{aid}/generate.
    Assert that exact path resolves to routes/risk.py::generate_items and not
    a 404 — the concrete claim under test in the bug report."""
    aid = _create_assessment(client)

    with _as(TENANT), patch(
        "pharmagpt.routes.risk.gemini_client.models.generate_content_stream",
        return_value=[_FakeChunk('[{"failure_mode": "Seal failure", "hazard": "Contamination"}]')],
    ):
        resp = client.post(f"/risk/assessments/{aid}/generate", json={}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")


def test_ai_risk_generation_saves_items_and_streams_done_event(client):
    aid = _create_assessment(client)

    with _as(TENANT), patch(
        "pharmagpt.routes.risk.gemini_client.models.generate_content_stream",
        return_value=[_FakeChunk('[{"failure_mode": "Seal failure", "hazard": "Contamination"}]')],
    ):
        resp = client.post(f"/risk/assessments/{aid}/generate", json={}, headers=AUTH_HEADERS)

    body = resp.get_data(as_text=True)
    assert '"done": true' in body
    assert '"count": 1' in body

    with _as(TENANT):
        items_resp = client.get(f"/risk/assessments/{aid}/items", headers=AUTH_HEADERS)
    assert len(items_resp.get_json()) == 1


# ── 2. Missing route ──────────────────────────────────────────────────────────

def test_typoed_or_renamed_route_returns_json_404_not_html(client):
    """If this URL is ever renamed/mistyped again, the caller must get a
    parseable JSON 404, not Flask's default HTML error page."""
    aid = _create_assessment(client)

    with _as(TENANT):
        resp = client.post(f"/risk/assessments/{aid}/genereate", json={}, headers=AUTH_HEADERS)

    assert resp.status_code == 404
    assert resp.content_type.startswith("application/json")
    assert resp.get_json() == {"error": "Not found"}


# ── 3. Invalid endpoint / wrong method ───────────────────────────────────────

def test_wrong_http_method_returns_json_405_not_html(client):
    aid = _create_assessment(client)

    with _as(TENANT):
        resp = client.get(f"/risk/assessments/{aid}/generate", headers=AUTH_HEADERS)

    assert resp.status_code == 405
    assert resp.content_type.startswith("application/json")
    assert resp.get_json() == {"error": "Method not allowed"}


def test_nonexistent_assessment_id_returns_json_404_not_html(client):
    with _as(TENANT):
        resp = client.post("/risk/assessments/999999/generate", json={}, headers=AUTH_HEADERS)

    assert resp.status_code == 404
    assert resp.content_type.startswith("application/json")


# ── 4. Gemini failure ─────────────────────────────────────────────────────────

def test_gemini_failure_streams_json_error_event_not_html_crash(client):
    """generate_items() starts the SSE response (200, text/event-stream)
    before ever calling Gemini, so a Gemini-side failure can't become an
    HTTP 500 — it must surface as a JSON error event inside the stream."""
    aid = _create_assessment(client)

    def _raise(*a, **k):
        raise RuntimeError("Gemini API unavailable")

    with _as(TENANT), patch(
        "pharmagpt.routes.risk.gemini_client.models.generate_content_stream",
        side_effect=_raise,
    ):
        resp = client.post(f"/risk/assessments/{aid}/generate", json={}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")
    body = resp.get_data(as_text=True)
    assert "Gemini API unavailable" in body
    assert not body.strip().startswith("<")


# ── 5. Authentication failure ────────────────────────────────────────────────

def test_missing_auth_header_returns_json_401_not_html(client):
    resp = client.post("/risk/assessments/1/generate", json={})

    assert resp.status_code == 401
    assert resp.content_type.startswith("application/json")
    assert not resp.get_data(as_text=True).strip().startswith("<")


def test_invalid_bearer_token_returns_json_401_not_html(client):
    with patch(MIDDLEWARE_PATH, side_effect=__import__(
        "pharmagpt.auth.context", fromlist=["AuthenticationError"]
    ).AuthenticationError("Invalid or expired session")):
        resp = client.post(
            "/risk/assessments/1/generate", json={},
            headers={"Authorization": "Bearer garbage-token"},
        )

    assert resp.status_code == 401
    assert resp.content_type.startswith("application/json")


# ── 6. assessmentId propagation contract (pharmagpt/static/js/risk.js) ──────
# window.useTemplate() previously read the POST /risk/assessments response
# without checking res.ok, so a failed create (e.g. the Super Admin 403
# below) was treated as a saved assessment: assessment.id was undefined,
# the header rendered "undefined"/"undefined" status+priority badges, and
# the AI Generate button was wired to aiGenerateItems(undefined) ->
# POST /risk/assessments/undefined/generate. The fix is in risk.js (res.ok
# + assessment.id checks before opening the editor, a disabled button when
# id is missing, and a guard inside aiGenerateItems itself). These tests
# lock in the backend contract that fix depends on.

def test_new_unsaved_assessment_create_failure_returns_no_id(client):
    """The condition that used to slip through useTemplate()'s missing
    res.ok check: a failed create must return an error body with no `id`
    field, never a partial/fake assessment object."""
    super_admin = TenantContext(
        user_id="super-1", email="super@example.com", display_name="Super Admin",
        role="super_admin", company_id=None,
    )
    with _as(super_admin):
        resp = client.post(
            "/risk/assessments",
            json={"title": "Should not save", "assessment_type": "process", "methodology": "FMEA"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 403
    body = resp.get_json()
    assert "id" not in body


def test_saved_assessment_response_always_has_real_id_status_priority(client):
    """A successful create must return a complete object — the fields the
    header badges render without a fallback (status, priority) must never
    be missing, and id must be a real int the frontend can propagate."""
    with _as(TENANT):
        resp = client.post(
            "/risk/assessments",
            json={"title": "Autoclave FMEA", "assessment_type": "process", "methodology": "FMEA"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    body = resp.get_json()
    assert isinstance(body["id"], int)
    assert body["status"]
    assert body["priority"]


def test_invalid_assessment_id_on_generate_returns_json_404(client):
    """A generate call against an id that doesn't exist (e.g. a stale
    client-side reference) must 404 cleanly, not 500 or hang."""
    with _as(TENANT):
        resp = client.post("/risk/assessments/424242/generate", json={}, headers=AUTH_HEADERS)

    assert resp.status_code == 404
    assert resp.content_type.startswith("application/json")


def test_missing_assessment_id_literal_undefined_in_url_returns_json_404(client):
    """The exact URL the browser was observed sending:
    POST /risk/assessments/undefined/generate. <int:aid> must not match
    the literal string "undefined", so Flask 404s (via the JSON handler
    added in app.py) instead of routing into generate_items with a bad id."""
    with _as(TENANT):
        resp = client.post("/risk/assessments/undefined/generate", json={}, headers=AUTH_HEADERS)

    assert resp.status_code == 404
    assert resp.content_type.startswith("application/json")
    assert not resp.get_data(as_text=True).strip().startswith("<")


def test_ai_generation_succeeds_immediately_after_save(client):
    """End-to-end: create -> real id comes back -> generate against that id
    works on the first call, with no extra save step required."""
    with _as(TENANT):
        create_resp = client.post(
            "/risk/assessments",
            json={"title": "Autoclave FMEA", "assessment_type": "process", "methodology": "FMEA"},
            headers=AUTH_HEADERS,
        )
    aid = create_resp.get_json()["id"]

    with _as(TENANT), patch(
        "pharmagpt.routes.risk.gemini_client.models.generate_content_stream",
        return_value=[_FakeChunk('[{"failure_mode": "Seal failure", "hazard": "Contamination"}]')],
    ):
        gen_resp = client.post(f"/risk/assessments/{aid}/generate", json={}, headers=AUTH_HEADERS)

    assert gen_resp.status_code == 200
    assert '"done": true' in gen_resp.get_data(as_text=True)

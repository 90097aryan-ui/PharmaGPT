"""
tests/test_urs_docx_download_auth.py — Regression coverage for the DOCX
export download-auth bug (Stabilization Iteration 2, priority 1).

Root cause (see docs/URS_STABILIZATION_REVIEW.md): the app is bearer-token
-only auth — the access token lives in localStorage and is attached only to
fetch() calls via static/js/auth.js's patched window.fetch(). The DOCX
export button in static/js/urs.js downloads via a plain
`<a download href="...">` click, a real browser navigation that cannot
attach a custom Authorization header. That request reached the global auth
gate with no header at all and always got a 401; Chrome's download manager
renders that failure as "Try to sign in to the site. Then download again."

Fix: auth/middleware.py falls back to an access token mirrored into a
signed, HttpOnly Flask session cookie at login (routes/auth.py) whenever a
request has no Authorization header. These tests exercise the *real*
before_request gate (like test_app_auth_integration.py) rather than
conftest.py's `client` fixture, which intentionally bypasses auth entirely
for business-logic tests.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pharmagpt.auth.context import TenantContext

SAMPLE_TENANT = TenantContext(
    user_id="user-1", email="jane@example.com", display_name="Jane Reviewer",
    role="reviewer_qa", company_id="company-1",
)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod
    return appmod.app.test_client()


def _login(client) -> str:
    """Log in through the real /auth/login route so the session-cookie
    fallback is set exactly as production does; return the issued token."""
    fake_session = SimpleNamespace(access_token="real-token", refresh_token="ref", expires_at=1234)
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.return_value = SimpleNamespace(session=fake_session)
    with patch("pharmagpt.routes.auth.get_anonymous_client", return_value=fake_supabase), \
         patch("pharmagpt.routes.auth.resolve_tenant_context", return_value=SAMPLE_TENANT):
        resp = client.post("/auth/login", json={"email": "jane@example.com", "password": "correct"})
    assert resp.status_code == 200
    return resp.get_json()["access_token"]


def test_docx_download_without_login_is_rejected(client):
    """A request with no Authorization header and no session cookie — a
    cold browser navigation — must be rejected with a clean 401."""
    resp = client.get("/urs/999999/export/docx")
    assert resp.status_code == 401


def test_docx_download_via_bare_navigation_succeeds_after_login(client):
    """Reproduces the reported bug end-to-end: log in (establishing the
    session cookie), then issue a GET with *no* Authorization header —
    exactly what the <a download> click in urs.js produces — and confirm
    the DOCX bytes come back instead of a 401."""
    with patch("pharmagpt.auth.middleware.resolve_tenant_context", return_value=SAMPLE_TENANT):
        token = _login(client)

        create_resp = client.post(
            "/urs/", json={"title": "Download Auth Test URS", "equipment_name": "Autoclave"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        urs_id = create_resp.get_json()["id"]

        # No Authorization header on this request at all — simulates the
        # plain <a href> navigation a browser download performs.
        resp = client.get(f"/urs/{urs_id}/export/docx")

    assert resp.status_code == 200
    assert resp.mimetype == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert len(resp.data) > 0


def test_present_bad_header_is_never_overridden_by_a_valid_session_cookie(client):
    """The session-cookie fallback only applies when a request has *no*
    Authorization header at all. A request that sends a bad one must still
    401 immediately, even with a valid session cookie from an earlier
    login in the same client."""
    with patch("pharmagpt.auth.middleware.resolve_tenant_context") as mock_resolve:
        mock_resolve.return_value = SAMPLE_TENANT
        _login(client)

        from pharmagpt.auth.context import AuthenticationError
        mock_resolve.side_effect = AuthenticationError("Invalid or expired session")
        resp = client.get(
            "/urs/999999/export/docx", headers={"Authorization": "Bearer garbage"}
        )

    assert resp.status_code == 401


def test_logout_clears_the_session_cookie_fallback(client):
    # /auth/logout is gated twice — once by the global before_request hook
    # (pharmagpt.auth.middleware's import binding) and again by its own
    # @require_auth decorator (pharmagpt.auth.decorators's separate import
    # binding of the same underlying function) — both must be patched.
    with patch("pharmagpt.auth.middleware.resolve_tenant_context", return_value=SAMPLE_TENANT), \
         patch("pharmagpt.auth.decorators.resolve_tenant_context", return_value=SAMPLE_TENANT), \
         patch("pharmagpt.routes.auth.get_anonymous_client", return_value=MagicMock()):
        token = _login(client)
        logout_resp = client.post(
            "/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )
        assert logout_resp.status_code == 200

        resp = client.get("/urs/999999/export/docx")

    assert resp.status_code == 401

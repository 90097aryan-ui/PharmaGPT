"""
tests/test_app_auth_integration.py — Phase 2 step 2.5 integration tests.

Exercises the *real* pharmagpt.app (actual app object, actual registered
blueprints, actual before_request middleware) rather than a standalone
test app, to prove the middleware protects real business routes without
any route file having been modified.

Defines its own `client` fixture (shadowing tests/conftest.py's) that
skips the is_exempt bypass conftest.py applies for the rest of the suite
— this file specifically needs the real, unpatched gate.
"""

from unittest.mock import patch

import pytest

from pharmagpt.auth.context import TenantContext


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()

SAMPLE_TENANT = TenantContext(
    user_id="user-1",
    email="jane@example.com",
    display_name="Jane Reviewer",
    role="reviewer_qa",
    company_id="company-1",
)


# ── Exempt paths stay public ────────────────────────────────────────────

def test_spa_shell_is_public(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_health_is_public(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_login_route_is_public(client):
    # Reaches the real routes/auth.py handler (rejected for missing
    # fields, HTTP 400) rather than being blocked by the middleware
    # (which would be HTTP 401) — proves it's exempt, not merely
    # tolerant of bad input.
    resp = client.post("/auth/login", json={})
    assert resp.status_code == 400


def test_static_assets_are_exempt_from_auth(client):
    # No such file exists, so Flask's static handler 404s. The important
    # assertion is that it's not 401 — a 401 would mean the middleware
    # gated the request before Flask ever got to look for the file.
    resp = client.get("/static/does-not-exist.js")
    assert resp.status_code == 404


def test_favicon_is_exempt_from_auth(client):
    resp = client.get("/favicon.ico")
    assert resp.status_code != 401


# ── Everything else requires a valid session ────────────────────────────

def test_protected_route_rejects_missing_token(client):
    resp = client.get("/dashboard/stats")
    assert resp.status_code == 401
    assert "Authorization" in resp.get_json()["error"]


def test_protected_route_rejects_malformed_header(client):
    resp = client.get("/dashboard/stats", headers={"Authorization": "Token abc"})
    assert resp.status_code == 401


def test_protected_route_rejects_invalid_token(client):
    from pharmagpt.auth.context import AuthenticationError

    with patch(
        "pharmagpt.auth.middleware.resolve_tenant_context",
        side_effect=AuthenticationError("Invalid or expired session"),
    ):
        resp = client.get(
            "/dashboard/stats", headers={"Authorization": "Bearer bad-token"}
        )
    assert resp.status_code == 401


def test_protected_route_allows_authenticated_request(client):
    with patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SAMPLE_TENANT
    ):
        resp = client.get(
            "/dashboard/stats", headers={"Authorization": "Bearer good-token"}
        )

    assert resp.status_code == 200


def test_multiple_blueprints_are_protected(client):
    # Spot-check a few different route files to confirm the middleware is
    # global, not accidentally scoped to one blueprint.
    for path in ("/dashboard/stats", "/dashboard/validation-score"):
        resp = client.get(path)
        assert resp.status_code == 401, path

"""
tests/test_routes_auth.py — routes/auth.py (login/logout/me), mocked against
the Supabase client (no live Supabase project required).

This blueprint is not registered on the main Flask app yet
(IMPLEMENTATION_ROADMAP.md Phase 2 step 2.5), so tests register it onto a
standalone Flask app rather than importing pharmagpt.app.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from supabase_auth.errors import AuthApiError

from pharmagpt.auth.context import TenantContext
from pharmagpt.routes.auth import bp as auth_bp


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


SAMPLE_TENANT = TenantContext(
    user_id="user-1",
    email="jane@example.com",
    display_name="Jane Reviewer",
    role="reviewer_qa",
    company_id="company-1",
)


# ── /auth/login ────────────────────────────────────────────────────────────

def test_login_missing_fields_returns_400(client):
    resp = client.post("/auth/login", json={"email": "jane@example.com"})
    assert resp.status_code == 400


def test_login_bad_credentials_returns_401(client):
    fake_client = MagicMock()
    fake_client.auth.sign_in_with_password.side_effect = AuthApiError(
        "Invalid login credentials", 400, None
    )

    with patch("pharmagpt.routes.auth.get_anonymous_client", return_value=fake_client):
        resp = client.post(
            "/auth/login", json={"email": "jane@example.com", "password": "wrong"}
        )

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Invalid email or password"


def test_login_valid_credentials_no_profile_returns_403(client):
    session = SimpleNamespace(access_token="tok", refresh_token="ref", expires_at=1234)
    fake_client = MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(session=session)

    from pharmagpt.auth.context import AuthenticationError

    with patch("pharmagpt.routes.auth.get_anonymous_client", return_value=fake_client), \
         patch(
             "pharmagpt.routes.auth.resolve_tenant_context",
             side_effect=AuthenticationError("No PharmaGPT profile exists for this identity"),
         ):
        resp = client.post(
            "/auth/login", json={"email": "jane@example.com", "password": "correct"}
        )

    assert resp.status_code == 403


def test_login_success_returns_session_and_user(client):
    session = SimpleNamespace(access_token="tok", refresh_token="ref", expires_at=1234)
    fake_client = MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(session=session)

    with patch("pharmagpt.routes.auth.get_anonymous_client", return_value=fake_client), \
         patch("pharmagpt.routes.auth.resolve_tenant_context", return_value=SAMPLE_TENANT):
        resp = client.post(
            "/auth/login", json={"email": "jane@example.com", "password": "correct"}
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["access_token"] == "tok"
    assert body["refresh_token"] == "ref"
    assert body["user"]["role"] == "reviewer_qa"
    assert body["user"]["company_id"] == "company-1"

    fake_client.auth.sign_in_with_password.assert_called_once_with(
        {"email": "jane@example.com", "password": "correct"}
    )


# ── /auth/logout ───────────────────────────────────────────────────────────

def test_logout_without_token_returns_401(client):
    resp = client.post("/auth/logout")
    assert resp.status_code == 401


def test_logout_revokes_session_via_admin_sign_out(client):
    fake_client = MagicMock()

    with patch(
        "pharmagpt.auth.decorators.resolve_tenant_context", return_value=SAMPLE_TENANT
    ), patch("pharmagpt.routes.auth.get_anonymous_client", return_value=fake_client):
        resp = client.post(
            "/auth/logout", headers={"Authorization": "Bearer good-token"}
        )

    assert resp.status_code == 200
    assert resp.get_json() == {"success": True}
    fake_client.auth.admin.sign_out.assert_called_once_with("good-token", "global")


# ── /auth/me ───────────────────────────────────────────────────────────────

def test_me_without_token_returns_401(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_returns_tenant_context(client):
    with patch(
        "pharmagpt.auth.decorators.resolve_tenant_context", return_value=SAMPLE_TENANT
    ):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer good-token"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user_id"] == "user-1"
    assert body["email"] == "jane@example.com"
    assert body["role"] == "reviewer_qa"
    assert body["company_id"] == "company-1"

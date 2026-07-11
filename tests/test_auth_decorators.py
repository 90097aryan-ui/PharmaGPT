"""
tests/test_auth_decorators.py — pharmagpt.auth.decorators.require_auth,
exercised against a throwaway Flask app so it doesn't depend on any real
route existing yet.
"""

from unittest.mock import patch

import pytest
from flask import Flask, g, jsonify

from pharmagpt.auth.context import AuthenticationError, TenantContext
from pharmagpt.auth.decorators import require_auth


@pytest.fixture()
def app():
    app = Flask(__name__)

    @app.route("/protected")
    @require_auth
    def protected():
        return jsonify({"user_id": g.tenant.user_id, "role": g.tenant.role})

    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_missing_authorization_header_returns_401(client):
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert "Authorization" in resp.get_json()["error"]


def test_malformed_authorization_header_returns_401(client):
    resp = client.get("/protected", headers={"Authorization": "Token abc123"})
    assert resp.status_code == 401


def test_invalid_token_returns_401(client):
    with patch(
        "pharmagpt.auth.decorators.resolve_tenant_context",
        side_effect=AuthenticationError("Invalid or expired session"),
    ):
        resp = client.get("/protected", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Invalid or expired session"


def test_valid_token_calls_view_with_tenant_context(client):
    ctx = TenantContext(
        user_id="user-1",
        email="a@example.com",
        display_name="Jane Reviewer",
        role="reviewer_qa",
        company_id="company-1",
    )
    with patch("pharmagpt.auth.decorators.resolve_tenant_context", return_value=ctx):
        resp = client.get("/protected", headers={"Authorization": "Bearer good-token"})

    assert resp.status_code == 200
    assert resp.get_json() == {"user_id": "user-1", "role": "reviewer_qa"}

"""
tests/test_auth_context.py — pharmagpt.auth.context, mocked against the
Supabase client (no live Supabase project required).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pharmagpt.auth.context import AuthenticationError, resolve_tenant_context


def _client_returning(user, profile_data):
    """Build a MagicMock standing in for get_authenticated_client()'s return
    value, wired so client.auth.get_user(...) and the users-table query chain
    return the given user/profile."""
    client = MagicMock()
    client.auth.get_user.return_value = SimpleNamespace(user=user)

    query = client.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query
    query.execute.return_value = SimpleNamespace(data=profile_data)

    return client


def test_missing_token_raises():
    with pytest.raises(AuthenticationError):
        resolve_tenant_context("")


def test_supabase_rejects_token_raises():
    client = MagicMock()
    client.auth.get_user.side_effect = Exception("invalid JWT")

    with patch("pharmagpt.auth.context.get_authenticated_client", return_value=client):
        with pytest.raises(AuthenticationError):
            resolve_tenant_context("bad-token")


def test_valid_token_no_profile_row_raises():
    supabase_user = SimpleNamespace(id="user-1", email="a@example.com")
    client = _client_returning(supabase_user, profile_data=None)

    with patch("pharmagpt.auth.context.get_authenticated_client", return_value=client):
        with pytest.raises(AuthenticationError, match="No PharmaGPT profile"):
            resolve_tenant_context("good-token")


def test_deactivated_account_raises():
    supabase_user = SimpleNamespace(id="user-1", email="a@example.com")
    profile = {
        "company_id": "company-1",
        "display_name": "Jane Reviewer",
        "status": "deactivated",
        "roles": {"name": "user"},
    }
    client = _client_returning(supabase_user, profile)

    with patch("pharmagpt.auth.context.get_authenticated_client", return_value=client):
        with pytest.raises(AuthenticationError, match="deactivated"):
            resolve_tenant_context("good-token")


def test_valid_user_resolves_tenant_context():
    supabase_user = SimpleNamespace(id="user-1", email="a@example.com")
    profile = {
        "company_id": "company-1",
        "display_name": "Jane Reviewer",
        "status": "active",
        "roles": {"name": "reviewer_qa"},
    }
    client = _client_returning(supabase_user, profile)

    with patch("pharmagpt.auth.context.get_authenticated_client", return_value=client):
        ctx = resolve_tenant_context("good-token")

    assert ctx.user_id == "user-1"
    assert ctx.email == "a@example.com"
    assert ctx.display_name == "Jane Reviewer"
    assert ctx.role == "reviewer_qa"
    assert ctx.company_id == "company-1"


def test_super_admin_has_no_company():
    supabase_user = SimpleNamespace(id="user-1", email="admin@example.com")
    profile = {
        "company_id": None,
        "display_name": "Root Admin",
        "status": "active",
        "roles": {"name": "super_admin"},
    }
    client = _client_returning(supabase_user, profile)

    with patch("pharmagpt.auth.context.get_authenticated_client", return_value=client):
        ctx = resolve_tenant_context("good-token")

    assert ctx.role == "super_admin"
    assert ctx.company_id is None

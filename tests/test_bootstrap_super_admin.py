"""
tests/test_bootstrap_super_admin.py — scripts/bootstrap_super_admin.py,
fully mocked against the Supabase client (no live Supabase project, no
real .env, and no real credentials needed to run these tests).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

from scripts.bootstrap_super_admin import (
    REQUIRED_ENV_VARS,
    BootstrapError,
    bootstrap_super_admin,
    create_super_admin_auth_identity,
    find_auth_user_by_email,
    find_existing_super_admin,
    get_super_admin_role_id,
    load_config,
    main,
)


# ── load_config ──────────────────────────────────────────────────────────

def test_load_config_missing_vars_raises():
    with pytest.raises(BootstrapError, match="SUPABASE_URL"):
        load_config({})


def test_load_config_all_present_uses_default_display_name():
    env = {name: "x" for name in REQUIRED_ENV_VARS}
    config = load_config(env)
    assert config["SUPER_ADMIN_DISPLAY_NAME"] == "Super Admin"


def test_load_config_respects_custom_display_name():
    env = {name: "x" for name in REQUIRED_ENV_VARS}
    env["SUPER_ADMIN_DISPLAY_NAME"] = "Root Admin"
    config = load_config(env)
    assert config["SUPER_ADMIN_DISPLAY_NAME"] == "Root Admin"


# ── get_super_admin_role_id ─────────────────────────────────────────────

def _query_mock(execute_return):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.single.return_value = q
    q.limit.return_value = q
    q.execute.return_value = execute_return
    return q


def test_get_super_admin_role_id_found():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={"id": 7}))

    assert get_super_admin_role_id(client) == 7


def test_get_super_admin_role_id_missing_raises():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=None))

    with pytest.raises(BootstrapError, match="roles table"):
        get_super_admin_role_id(client)


# ── find_existing_super_admin ───────────────────────────────────────────

def test_find_existing_super_admin_none():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[]))

    assert find_existing_super_admin(client, 7) is None


def test_find_existing_super_admin_found():
    row = {"id": "user-1", "display_name": "Root Admin"}
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[row]))

    assert find_existing_super_admin(client, 7) == row


# ── find_auth_user_by_email ─────────────────────────────────────────────

def test_find_auth_user_by_email_found_first_page():
    match = SimpleNamespace(id="auth-1", email="admin@example.com")
    other = SimpleNamespace(id="auth-2", email="someone@example.com")
    client = MagicMock()
    client.auth.admin.list_users.return_value = [other, match]

    result = find_auth_user_by_email(client, "admin@example.com")
    assert result is match


def test_find_auth_user_by_email_not_found():
    client = MagicMock()
    client.auth.admin.list_users.return_value = []

    assert find_auth_user_by_email(client, "nobody@example.com") is None


def test_find_auth_user_by_email_case_insensitive():
    match = SimpleNamespace(id="auth-1", email="Admin@Example.com")
    client = MagicMock()
    client.auth.admin.list_users.return_value = [match]

    assert find_auth_user_by_email(client, "admin@example.com") is match


# ── create_super_admin_auth_identity ────────────────────────────────────

def test_create_super_admin_auth_identity_success():
    created_user = SimpleNamespace(id="auth-1", email="admin@example.com")
    client = MagicMock()
    client.auth.admin.create_user.return_value = SimpleNamespace(user=created_user)

    result = create_super_admin_auth_identity(client, "admin@example.com", "pw", "Root Admin")
    assert result is created_user


def test_create_super_admin_auth_identity_resumes_existing():
    client = MagicMock()
    client.auth.admin.create_user.side_effect = AuthApiError(
        "A user with this email address has already been registered", 422, None
    )
    existing = SimpleNamespace(id="auth-1", email="admin@example.com")
    client.auth.admin.list_users.return_value = [existing]

    result = create_super_admin_auth_identity(client, "admin@example.com", "pw", "Root Admin")
    assert result is existing


def test_create_super_admin_auth_identity_other_error_raises():
    client = MagicMock()
    client.auth.admin.create_user.side_effect = AuthApiError("Password too weak", 422, None)

    with pytest.raises(BootstrapError, match="Failed to create"):
        create_super_admin_auth_identity(client, "admin@example.com", "pw", "Root Admin")


def test_create_super_admin_auth_identity_already_registered_but_not_found_raises():
    client = MagicMock()
    client.auth.admin.create_user.side_effect = AuthApiError(
        "already been registered", 422, None
    )
    client.auth.admin.list_users.return_value = []

    with pytest.raises(BootstrapError, match="Failed to create"):
        create_super_admin_auth_identity(client, "admin@example.com", "pw", "Root Admin")


# ── bootstrap_super_admin (full flow) ───────────────────────────────────

def _client_with(roles_data, users_execute_side_effect, created_auth_user=None, create_error=None):
    client = MagicMock()

    roles_q = _query_mock(SimpleNamespace(data=roles_data))
    users_q = MagicMock()
    users_q.select.return_value = users_q
    users_q.eq.return_value = users_q
    users_q.limit.return_value = users_q
    users_q.insert.return_value = users_q
    users_q.execute.side_effect = users_execute_side_effect

    client.table.side_effect = lambda name: {"roles": roles_q, "users": users_q}[name]

    if create_error is not None:
        client.auth.admin.create_user.side_effect = create_error
    else:
        client.auth.admin.create_user.return_value = SimpleNamespace(user=created_auth_user)

    return client


def test_bootstrap_no_op_when_super_admin_exists():
    existing_row = {"id": "user-1", "display_name": "Root Admin"}
    client = _client_with(
        roles_data={"id": 7},
        users_execute_side_effect=[SimpleNamespace(data=[existing_row])],
    )

    message = bootstrap_super_admin(client, "admin@example.com", "pw", "Root Admin")

    assert "already exists" in message
    client.auth.admin.create_user.assert_not_called()


def test_bootstrap_creates_super_admin_when_none_exists():
    created_user = SimpleNamespace(id="auth-1", email="admin@example.com")
    client = _client_with(
        roles_data={"id": 7},
        users_execute_side_effect=[
            SimpleNamespace(data=[]),          # find_existing_super_admin: none yet
            SimpleNamespace(data=[{"id": "auth-1"}]),  # insert result
        ],
        created_auth_user=created_user,
    )

    message = bootstrap_super_admin(client, "admin@example.com", "pw", "Root Admin")

    assert "Super Admin created" in message
    assert "auth-1" in message
    client.auth.admin.create_user.assert_called_once()


def test_bootstrap_race_on_insert_resolves_to_no_op():
    created_user = SimpleNamespace(id="auth-1", email="admin@example.com")
    existing_row = {"id": "auth-1", "display_name": "Root Admin"}
    client = _client_with(
        roles_data={"id": 7},
        users_execute_side_effect=[
            SimpleNamespace(data=[]),                      # first check: none yet
            APIError({"message": "duplicate key value"}),  # insert races with another run
            SimpleNamespace(data=[existing_row]),           # recheck: now it exists
        ],
        created_auth_user=created_user,
    )

    message = bootstrap_super_admin(client, "admin@example.com", "pw", "Root Admin")

    assert "already exists" in message


def test_bootstrap_insert_failure_with_no_recheck_match_raises():
    created_user = SimpleNamespace(id="auth-1", email="admin@example.com")
    client = _client_with(
        roles_data={"id": 7},
        users_execute_side_effect=[
            SimpleNamespace(data=[]),
            APIError({"message": "some other database error"}),
            SimpleNamespace(data=[]),
        ],
        created_auth_user=created_user,
    )

    with pytest.raises(BootstrapError, match="Failed to insert"):
        bootstrap_super_admin(client, "admin@example.com", "pw", "Root Admin")


# ── main() ───────────────────────────────────────────────────────────────

def test_main_returns_1_and_prints_error_when_env_incomplete(capsys):
    with patch("scripts.bootstrap_super_admin.load_dotenv"), \
         patch.dict("os.environ", {}, clear=True):
        exit_code = main()

    assert exit_code == 1
    assert "Bootstrap failed" in capsys.readouterr().err


def test_main_returns_0_and_prints_message_on_success(capsys):
    env = {name: "x" for name in REQUIRED_ENV_VARS}

    with patch("scripts.bootstrap_super_admin.load_dotenv"), \
         patch.dict("os.environ", env, clear=True), \
         patch("scripts.bootstrap_super_admin.build_service_role_client") as build_client, \
         patch(
             "scripts.bootstrap_super_admin.bootstrap_super_admin",
             return_value="Super Admin created (id=auth-1, email=x).",
         ):
        build_client.return_value = MagicMock()
        exit_code = main()

    assert exit_code == 0
    assert "Super Admin created" in capsys.readouterr().out

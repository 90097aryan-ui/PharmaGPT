"""
tests/test_users_directory.py — Regression coverage for GET /users/directory
(routes/users.py::list_users_directory), the minimal read-only user
directory added to close the actual root cause behind "Lifecycle shows an
assigned approver but the deviation never appears in Workflow Inbox": the
Workflow Builder's old free-text "Approver User ID" field let an admin type
a value that didn't correspond to any real account. This directory backs
the Workflow Builder's searchable approver picker so an approver is always
chosen from real, active company users — never typed.

Unlike GET /users (company_admin/super_admin only), this endpoint is open
to any authenticated tenant member — an ordinary "user" configuring their
own deviation's Workflow Builder must be able to load it too.

Same mocking technique as tests/test_user_invite_and_list.py:
FakeSupabaseClient/_FakeQuery from tests/test_assume_company_context.py,
real Flask app + real auth middleware with resolve_tenant_context patched
per-test — no real Supabase project is touched.
"""

from unittest.mock import patch

import pytest

from tests.test_assume_company_context import FakeSupabaseClient
from tests.test_security_tenant_rbac_esig import (
    ADMIN_A, COMPANY_A, COMPANY_B, REVIEWER_A, SUPER_ADMIN, USER_A, AUTH_HEADERS, MIDDLEWARE_PATH,
)

DIRECTORY_CLIENT_PATH = "pharmagpt.routes.users.get_service_role_client"


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


@pytest.fixture()
def store():
    return {
        "users": [
            {"id": "user-in-a", "company_id": COMPANY_A, "display_name": "In Company A", "status": "active",
             "workflow_role_id": 4},
            {"id": "user-in-a-inactive", "company_id": COMPANY_A, "display_name": "Deactivated A", "status": "deactivated",
             "workflow_role_id": 1},
            {"id": "user-in-b", "company_id": COMPANY_B, "display_name": "In Company B", "status": "active",
             "workflow_role_id": 4},
        ],
        "workflow_roles": [
            {"id": 1, "name": "Initiator"},
            {"id": 4, "name": "Approver"},
            {"id": 5, "name": "Plant Head"},
        ],
        "departments": [
            {"id": "dept-a-production", "company_id": COMPANY_A, "name": "Production"},
        ],
        "user_departments": [
            {"user_id": "user-in-a", "department_id": "dept-a-production", "company_id": COMPANY_A, "is_primary": True},
        ],
    }


def test_directory_open_to_plain_user_role_not_just_admins(client, store):
    """A plain "user" (deviations can be configured by anyone, not just
    admins) must be able to load the directory to pick an approver — unlike
    GET /users, this is not @require_role-gated."""
    fake = FakeSupabaseClient(store)
    with _as(USER_A), patch(DIRECTORY_CLIENT_PATH, return_value=fake):
        resp = client.get("/users/directory", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    ids = {row["user_id"] for row in resp.get_json()}
    assert "user-in-a" in ids


def test_directory_reviewer_role_can_also_load_it(client, store):
    fake = FakeSupabaseClient(store)
    with _as(REVIEWER_A), patch(DIRECTORY_CLIENT_PATH, return_value=fake):
        resp = client.get("/users/directory", headers=AUTH_HEADERS)
    assert resp.status_code == 200


def test_directory_scoped_to_own_company(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(DIRECTORY_CLIENT_PATH, return_value=fake):
        resp = client.get("/users/directory", headers=AUTH_HEADERS)

    ids = {row["user_id"] for row in resp.get_json()}
    assert "user-in-a" in ids
    assert "user-in-b" not in ids


def test_directory_excludes_inactive_users(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(DIRECTORY_CLIENT_PATH, return_value=fake):
        resp = client.get("/users/directory", headers=AUTH_HEADERS)

    ids = {row["user_id"] for row in resp.get_json()}
    assert "user-in-a-inactive" not in ids


def test_directory_resolves_department_and_designation(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(DIRECTORY_CLIENT_PATH, return_value=fake):
        resp = client.get("/users/directory", headers=AUTH_HEADERS)

    row = next(r for r in resp.get_json() if r["user_id"] == "user-in-a")
    assert row["display_name"] == "In Company A"
    assert row["department"] == "Production"
    assert row["designation"] == "Approver"


def test_directory_user_with_no_department_or_workflow_role_gets_empty_strings(client, store):
    store["users"].append({
        "id": "user-in-a-no-dept", "company_id": COMPANY_A, "display_name": "No Dept",
        "status": "active", "workflow_role_id": None,
    })
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(DIRECTORY_CLIENT_PATH, return_value=fake):
        resp = client.get("/users/directory", headers=AUTH_HEADERS)

    row = next(r for r in resp.get_json() if r["user_id"] == "user-in-a-no-dept")
    assert row["department"] == ""
    assert row["designation"] == ""


def test_directory_super_admin_without_assumed_context_forbidden(client, store):
    fake = FakeSupabaseClient(store)
    with _as(SUPER_ADMIN), patch(DIRECTORY_CLIENT_PATH, return_value=fake):
        resp = client.get("/users/directory", headers=AUTH_HEADERS)

    assert resp.status_code == 403

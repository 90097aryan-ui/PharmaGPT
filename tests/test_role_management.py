"""
tests/test_role_management.py — Regression coverage for Phase 3.5's Role
Management (folded into User Management, routes/users.py::update_user —
no new table, no permission builder; the 4 roles stay frozen).

Cross-company protection for a Company Admin's PATCH /users/<id> is
enforced entirely by Postgres RLS (migrations/0012_users_company_admin_rls_
up.sql) — deliberately, since RLS is "the layer that actually holds" per
this codebase's own stated security posture, and routes/users.py adds no
redundant app-level company_id filter for that path (see the module
docstring there). That specific guarantee is a Postgres-server-side
property a mocked-client unit test cannot exercise — it is verified live/
manually (PHASE_3_5_IMPLEMENTATION_REPORT.md), not faked here.

What IS unit-testable and covered below:
  - A Company Admin can reassign a role within their own company (happy path).
  - Setting role_id=1 (super_admin) is rejected before it ever reaches Postgres.
  - An assumed-context Super Admin's app-level company_id filter (the one
    piece of defense-in-depth this path DOES have, since the service-role
    client bypasses RLS entirely) actually rejects a user outside the
    assumed company.
"""

from unittest.mock import patch

import pytest

from tests.test_assume_company_context import FakeSupabaseClient
from tests.test_security_tenant_rbac_esig import ADMIN_A, COMPANY_A, COMPANY_B, SUPER_ADMIN, AUTH_HEADERS, MIDDLEWARE_PATH

USERS_CLIENT_PATH = "pharmagpt.routes.users.get_authenticated_client"
USERS_SERVICE_CLIENT_PATH = "pharmagpt.routes.users.get_service_role_client"
# Yuktav P0-4: PATCH /users/<id> now writes its audit entry fail-closed
# (routes/users.py::_audit_fail_closed) BEFORE the mutation — every test
# that expects the mutation to succeed must mock this client too, exactly
# like tests/test_companies.py's AUDIT_CLIENT_PATH already does, or the
# unmocked real Supabase call would make the fail-closed write raise and the
# route would correctly (but, for these tests, unintentionally) 500.
AUDIT_CLIENT_PATH = "pharmagpt.db.qms_repo.get_authenticated_client"


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
            {"id": "user-in-a", "company_id": COMPANY_A, "role_id": 4, "display_name": "In Company A", "status": "active"},
            {"id": "user-in-b", "company_id": COMPANY_B, "role_id": 4, "display_name": "In Company B", "status": "active"},
        ],
    }


def test_company_admin_reassigns_role_within_own_company(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake), \
         patch(AUDIT_CLIENT_PATH, return_value=fake):
        resp = client.patch("/users/user-in-a", json={"role_id": 3}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert store["users"][0]["role_id"] == 3
    # P0-4: role_id is a privilege change — fail-closed audit entry landed.
    assert any(e["action"] == "User updated" for e in store["audit_trail"])


def test_cannot_set_role_to_super_admin(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake), \
         patch(AUDIT_CLIENT_PATH, return_value=fake):
        resp = client.patch("/users/user-in-a", json={"role_id": 1}, headers=AUTH_HEADERS)

    assert resp.status_code == 400
    assert store["users"][0]["role_id"] == 4  # unchanged
    # Rejected before the fail-closed audit write is even attempted.
    assert store.get("audit_trail", []) == []


def test_assumed_context_super_admin_cannot_touch_another_companys_user(client, store):
    """The one app-level defense-in-depth check this path has: the
    assumed-context Super Admin's service-role query is explicitly filtered
    to g.tenant.company_id by routes/users.py itself, since the service
    role bypasses RLS entirely."""
    fake = FakeSupabaseClient(store)
    assumed_super_admin = SUPER_ADMIN.__class__(
        user_id=SUPER_ADMIN.user_id, email=SUPER_ADMIN.email,
        display_name=SUPER_ADMIN.display_name, role="super_admin", company_id=COMPANY_A,
    )
    with _as(assumed_super_admin), patch(USERS_SERVICE_CLIENT_PATH, return_value=fake), \
         patch(AUDIT_CLIENT_PATH, return_value=fake):
        resp = client.patch("/users/user-in-b", json={"role_id": 3}, headers=AUTH_HEADERS)

    assert resp.status_code == 404
    assert store["users"][1]["role_id"] == 4  # unchanged — company_id filter excluded this row
    # P0-4: the pre-mutation existence check excluded this out-of-scope user
    # before the fail-closed audit write was ever attempted.
    assert store.get("audit_trail", []) == []


def test_assumed_context_super_admin_can_touch_own_assumed_companys_user(client, store):
    fake = FakeSupabaseClient(store)
    assumed_super_admin = SUPER_ADMIN.__class__(
        user_id=SUPER_ADMIN.user_id, email=SUPER_ADMIN.email,
        display_name=SUPER_ADMIN.display_name, role="super_admin", company_id=COMPANY_A,
    )
    with _as(assumed_super_admin), patch(USERS_SERVICE_CLIENT_PATH, return_value=fake), \
         patch(AUDIT_CLIENT_PATH, return_value=fake):
        resp = client.patch("/users/user-in-a", json={"role_id": 3}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert store["users"][0]["role_id"] == 3


# ── P0-4: fail-closed audit policy for status/role_id changes ───────────────
# A user's status/role_id change grants or revokes access/privilege — see
# routes/users.py::_audit_fail_closed and FINAL REPORT §D. If the required
# audit entry cannot be written, the mutation must NOT happen.

def test_update_user_audit_failure_blocks_role_change(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake), \
         patch(AUDIT_CLIENT_PATH, side_effect=RuntimeError("audit db unreachable")):
        resp = client.patch("/users/user-in-a", json={"role_id": 3}, headers=AUTH_HEADERS)

    assert resp.status_code == 500
    assert store["users"][0]["role_id"] == 4  # unchanged — mutation was blocked


def test_update_user_audit_failure_blocks_deactivation(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake), \
         patch(AUDIT_CLIENT_PATH, side_effect=RuntimeError("audit db unreachable")):
        resp = client.patch("/users/user-in-a", json={"status": "deactivated"}, headers=AUTH_HEADERS)

    assert resp.status_code == 500
    assert store["users"][0]["status"] == "active"  # unchanged — mutation was blocked

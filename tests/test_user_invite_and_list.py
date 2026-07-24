"""
tests/test_user_invite_and_list.py — Regression coverage for GET /users and
POST /users (routes/users.py), which had zero direct test coverage before
Phase F.2 (tests/test_role_management.py covers only PATCH /users/<id>).

Same mocking technique as tests/test_companies.py and
tests/test_role_management.py: FakeSupabaseClient/_FakeQuery from
tests/test_assume_company_context.py, real Flask app + real auth
middleware with resolve_tenant_context patched per-test.
"""

from unittest.mock import patch

import pytest

from pharmagpt.services.identity_admin import IdentityProvisioningError
from tests.test_assume_company_context import FakeSupabaseClient
from tests.test_security_tenant_rbac_esig import ADMIN_A, COMPANY_A, COMPANY_B, SUPER_ADMIN, AUTH_HEADERS, MIDDLEWARE_PATH

USERS_CLIENT_PATH = "pharmagpt.routes.users.get_authenticated_client"
USERS_SERVICE_CLIENT_PATH = "pharmagpt.routes.users.get_service_role_client"
PROVISION_USER_PATH = "pharmagpt.routes.users.provision_user"
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
            {"id": "user-in-a-2", "company_id": COMPANY_A, "role_id": 3, "display_name": "Also In Company A", "status": "active"},
            {"id": "user-in-b", "company_id": COMPANY_B, "role_id": 4, "display_name": "In Company B", "status": "active"},
        ],
        "audit_trail": [],
    }


def _assumed_super_admin(company_id):
    return SUPER_ADMIN.__class__(
        user_id=SUPER_ADMIN.user_id, email=SUPER_ADMIN.email,
        display_name=SUPER_ADMIN.display_name, role="super_admin", company_id=company_id,
    )


def test_list_users_company_admin_scoped(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake):
        resp = client.get("/users", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    ids = {row["id"] for row in resp.get_json()}
    # Company Admin's RLS-scoped client is expected to return only its own
    # company's rows in production; the fake client here returns everything
    # it's given, so this asserts the route doesn't filter OUT anyone in its
    # own company, not that RLS itself is being exercised (that's a live-DB
    # concern, see docs/FINAL_RELEASE_EVIDENCE/MANUAL_VERIFICATION_CHECKLIST.md).
    assert {"user-in-a", "user-in-a-2"} <= ids


def test_list_users_super_admin_without_assumed_context_forbidden(client, store):
    fake = FakeSupabaseClient(store)
    with _as(SUPER_ADMIN), patch(USERS_SERVICE_CLIENT_PATH, return_value=fake):
        resp = client.get("/users", headers=AUTH_HEADERS)

    assert resp.status_code == 403
    assert "assume a company context" in resp.get_json()["error"]


def test_list_users_assumed_super_admin_scoped_to_assumed_company(client, store):
    fake = FakeSupabaseClient(store)
    with _as(_assumed_super_admin(COMPANY_A)), patch(USERS_SERVICE_CLIENT_PATH, return_value=fake):
        resp = client.get("/users", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    ids = {row["id"] for row in resp.get_json()}
    assert ids == {"user-in-a", "user-in-a-2"}
    assert "user-in-b" not in ids


def test_invite_user_success_creates_and_audits(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake), patch(
        AUDIT_CLIENT_PATH, return_value=fake,
    ), patch(
        PROVISION_USER_PATH,
        return_value={"auth_user_id": "new-user-id", "temporary_password": "temp-pw-456"},
    ) as mock_provision:
        resp = client.post(
            "/users",
            json={"email": "new@companya.example", "display_name": "New Hire", "role_id": 4},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["temporary_password"] == "temp-pw-456"
    mock_provision.assert_called_once()
    _, kwargs = mock_provision.call_args
    assert kwargs["company_id"] == COMPANY_A
    assert kwargs["role_id"] == 4
    # Audit entry uses the real provisioned auth_user_id (Phase F.2 fix —
    # previously read a nonexistent "user_id" key and always fell back to
    # the invitee's email instead).
    assert len(store["audit_trail"]) == 1
    assert store["audit_trail"][0]["record_id"] == "new-user-id"
    assert store["audit_trail"][0]["action"] == "User invited"


def test_invite_user_rejects_invalid_role_id(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake):
        resp = client.post(
            "/users",
            json={"email": "x@example.com", "display_name": "X", "role_id": 1},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 400
    assert "role_id must be one of" in resp.get_json()["error"]


def test_invite_user_requires_email_and_display_name(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake):
        resp = client.post("/users", json={"role_id": 4}, headers=AUTH_HEADERS)

    assert resp.status_code == 400


def test_invite_user_super_admin_without_assumed_context_forbidden(client, store):
    fake = FakeSupabaseClient(store)
    with _as(SUPER_ADMIN), patch(USERS_CLIENT_PATH, return_value=fake):
        resp = client.post(
            "/users",
            json={"email": "x@example.com", "display_name": "X", "role_id": 4},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 403


def test_invite_user_provisioning_failure_returns_clean_500(client, store):
    fake = FakeSupabaseClient(store)
    with _as(ADMIN_A), patch(USERS_CLIENT_PATH, return_value=fake), patch(
        PROVISION_USER_PATH, side_effect=IdentityProvisioningError("email already registered"),
    ):
        resp = client.post(
            "/users",
            json={"email": "taken@example.com", "display_name": "X", "role_id": 4},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 500
    assert "already registered" in resp.get_json()["error"]

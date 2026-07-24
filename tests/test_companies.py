"""
tests/test_companies.py — Regression coverage for Phase 3.5's Company
Administration (routes/companies.py), which had zero direct test coverage
before Phase F.2 (only reachable indirectly through
tests/test_assume_company_context.py's company-picker fixture data).

Mocks pharmagpt.services.supabase_client.get_authenticated_client the same
way tests/test_assume_company_context.py and tests/test_role_management.py
already do (FakeSupabaseClient/_FakeQuery, imported from
test_assume_company_context) — no real Supabase project is touched.
provision_user() (which itself would need a service-role client) is patched
directly at its routes/companies.py import site, since identity provisioning
is services/identity_admin.py's concern, already exercised independently.
"""

from unittest.mock import patch

import pytest

from pharmagpt.services.identity_admin import IdentityProvisioningError
from tests.test_assume_company_context import FakeSupabaseClient
from tests.test_security_tenant_rbac_esig import ADMIN_A, COMPANY_A, SUPER_ADMIN, USER_A, AUTH_HEADERS, MIDDLEWARE_PATH

COMPANIES_CLIENT_PATH = "pharmagpt.routes.companies.get_authenticated_client"
PROVISION_USER_PATH = "pharmagpt.routes.companies.provision_user"
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
        "companies": [
            {"id": COMPANY_A, "legal_name": "Company A", "industry_segment": "pharma", "status": "active"},
        ],
        "roles": [
            {"id": 1, "name": "super_admin"},
            {"id": 2, "name": "company_admin"},
            {"id": 3, "name": "reviewer_qa"},
            {"id": 4, "name": "user"},
        ],
        "audit_trail": [],
    }


def _patched(store):
    fake = FakeSupabaseClient(store)
    return fake, patch(COMPANIES_CLIENT_PATH, return_value=fake), patch(AUDIT_CLIENT_PATH, return_value=fake)


def test_list_companies_super_admin_ok(client, store):
    fake, p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2:
        resp = client.get("/companies", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert resp.get_json()[0]["id"] == COMPANY_A


def test_list_companies_company_admin_forbidden(client, store):
    fake, p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.get("/companies", headers=AUTH_HEADERS)

    assert resp.status_code == 403


def test_list_companies_regular_user_forbidden(client, store):
    fake, p1, p2 = _patched(store)
    with _as(USER_A), p1, p2:
        resp = client.get("/companies", headers=AUTH_HEADERS)

    assert resp.status_code == 403


def test_create_company_success_provisions_admin_and_audits(client, store):
    fake, p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2, patch(
        PROVISION_USER_PATH,
        return_value={"auth_user_id": "new-admin-id", "temporary_password": "temp-pw-123"},
    ) as mock_provision:
        resp = client.post(
            "/companies",
            json={
                "legal_name": "New Biotech Co",
                "industry_segment": "biotech",
                "admin_email": "admin@newbiotech.example",
                "admin_display_name": "New Admin",
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["company"]["legal_name"] == "New Biotech Co"
    assert body["admin"]["temporary_password"] == "temp-pw-123"
    mock_provision.assert_called_once()
    _, kwargs = mock_provision.call_args
    assert kwargs["role_id"] == 2  # company_admin
    assert kwargs["company_id"] == body["company"]["id"]
    # Best-effort audit entry landed in the Postgres-side audit_trail table.
    assert len(store["audit_trail"]) == 1
    assert store["audit_trail"][0]["record_type"] == "company"
    assert store["audit_trail"][0]["action"] == "Company created"


def test_create_company_missing_legal_name_rejected(client, store):
    fake, p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2:
        resp = client.post(
            "/companies",
            json={"industry_segment": "biotech", "admin_email": "a@b.com", "admin_display_name": "A"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 400


def test_create_company_invalid_industry_segment_rejected(client, store):
    fake, p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2:
        resp = client.post(
            "/companies",
            json={
                "legal_name": "X", "industry_segment": "not-a-real-segment",
                "admin_email": "a@b.com", "admin_display_name": "A",
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 400


def test_create_company_non_super_admin_forbidden(client, store):
    fake, p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.post(
            "/companies",
            json={
                "legal_name": "X", "industry_segment": "biotech",
                "admin_email": "a@b.com", "admin_display_name": "A",
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 403


def test_create_company_provisioning_failure_reports_company_created(client, store):
    """Company row is not rolled back on a provisioning failure (Supabase
    has no cross-call transaction here) — the response must say so
    explicitly rather than silently losing the company."""
    fake, p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2, patch(
        PROVISION_USER_PATH,
        side_effect=IdentityProvisioningError("email already registered"),
    ):
        resp = client.post(
            "/companies",
            json={
                "legal_name": "Orphan Co", "industry_segment": "cro",
                "admin_email": "taken@example.com", "admin_display_name": "A",
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 500
    body = resp.get_json()
    assert body["company"]["legal_name"] == "Orphan Co"
    assert "admin provisioning failed" in body["error"]
    # The company row itself was still created in the store.
    assert any(c["legal_name"] == "Orphan Co" for c in store["companies"])


def test_suspend_then_reactivate_company(client, store):
    fake, p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2:
        suspend_resp = client.post(f"/companies/{COMPANY_A}/suspend", headers=AUTH_HEADERS)
        assert suspend_resp.status_code == 200
        assert suspend_resp.get_json()["status"] == "suspended"
        assert store["companies"][0]["status"] == "suspended"

        reactivate_resp = client.post(f"/companies/{COMPANY_A}/reactivate", headers=AUTH_HEADERS)
        assert reactivate_resp.status_code == 200
        assert store["companies"][0]["status"] == "active"

    # Both actions produced a best-effort audit entry.
    actions = [row["action"] for row in store["audit_trail"]]
    assert "Company suspended" in actions
    assert "Company reactivated" in actions


def test_suspend_nonexistent_company_404(client, store):
    fake, p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2:
        resp = client.post("/companies/does-not-exist/suspend", headers=AUTH_HEADERS)

    assert resp.status_code == 404


def test_suspend_company_non_super_admin_forbidden(client, store):
    fake, p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.post(f"/companies/{COMPANY_A}/suspend", headers=AUTH_HEADERS)

    assert resp.status_code == 403

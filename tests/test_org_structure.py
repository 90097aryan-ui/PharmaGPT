"""
tests/test_org_structure.py — Regression coverage for Department/Designation
Management (migrations/0015_rbac_org_framework_up.sql,
pharmagpt/routes/org_structure.py, pharmagpt/db/org_structure_repo.py) and
provision_org_defaults_for_company(), the shared routine
routes/companies.py::create_company calls for every new company.

Reuses the fake Supabase client from tests/test_rbac.py (same superset of
tests/test_assume_company_context.py's FakeSupabaseClient this module's
routes need).
"""

from unittest.mock import patch

import pytest

from pharmagpt.db import org_structure_repo
from tests.test_rbac import FakeRbacClient
from tests.test_security_tenant_rbac_esig import (
    ADMIN_A, COMPANY_A, COMPANY_B, REVIEWER_A, SUPER_ADMIN, AUTH_HEADERS, MIDDLEWARE_PATH,
)

ORG_CLIENT_PATH = "pharmagpt.routes.org_structure.get_authenticated_client"
ORG_SERVICE_CLIENT_PATH = "pharmagpt.routes.org_structure.get_service_role_client"
ORG_AUTH_SERVICE_CLIENT_PATH = "pharmagpt.auth.rbac.get_service_role_client"


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod
    return appmod.app.test_client()


@pytest.fixture()
def store():
    return {
        "departments": [
            {"id": "dept-a-qa", "company_id": COMPANY_A, "name": "Quality Assurance (QA)",
             "department_code": "QA", "status": "active"},
            {"id": "dept-b-qa", "company_id": COMPANY_B, "name": "Quality Assurance (QA)",
             "department_code": "QA", "status": "active"},
        ],
        "designations": [],
        "approval_levels": [],
        "rbac_audit_log": [],
    }


def _patched(store):
    fake = FakeRbacClient(store)
    return patch(ORG_CLIENT_PATH, return_value=fake), patch(ORG_SERVICE_CLIENT_PATH, return_value=fake)


def test_create_department_requires_reason(client, store):
    p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.post(
            "/org/departments", json={"name": "Packaging", "department_code": "PACKAGING"}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 400


def test_create_department_writes_audit_entry(client, store):
    p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.post(
            "/org/departments",
            json={"name": "Packaging", "department_code": "PACKAGING", "reason": "New line opening"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201
    assert resp.get_json()["company_id"] == COMPANY_A
    entry = store["rbac_audit_log"][-1]
    assert entry["department_id"] == resp.get_json()["id"]
    assert "New line opening" in entry["reason"]


def test_disable_department(client, store):
    p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.patch(
            "/org/departments/dept-a-qa", json={"status": "disabled", "reason": "Merged into QC"}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    assert store["departments"][0]["status"] == "disabled"


def test_company_admin_cannot_see_other_companys_departments(client, store):
    p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.get("/org/departments", headers=AUTH_HEADERS)
    ids = {d["id"] for d in resp.get_json()}
    assert ids == {"dept-a-qa"}


def test_super_admin_without_assumed_context_is_forbidden(client, store):
    p1, p2 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2:
        resp = client.get("/org/departments", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_create_designation_requires_reason(client, store):
    p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.post("/org/designations", json={"name": "Production Executive"}, headers=AUTH_HEADERS)
    assert resp.status_code == 400


def test_create_and_disable_designation(client, store):
    p1, p2 = _patched(store)
    with _as(ADMIN_A), p1, p2:
        create_resp = client.post(
            "/org/designations", json={"name": "Production Executive", "reason": "New role"}, headers=AUTH_HEADERS,
        )
        assert create_resp.status_code == 201
        designation_id = create_resp.get_json()["id"]

        disable_resp = client.patch(
            f"/org/designations/{designation_id}", json={"status": "disabled", "reason": "No longer used"},
            headers=AUTH_HEADERS,
        )
    assert disable_resp.status_code == 200
    assert store["designations"][0]["status"] == "disabled"


def test_rbac_company_admin_can_administer_departments_despite_legacy_reviewer_qa(client, store):
    """RBAC administration surfaces under /org also honor an active RBAC
    "Company Admin" assignment for a legacy reviewer_qa Coordinator — same
    centralized require_rbac_admin_access gate as /rbac/*."""
    store["rbac_roles"] = [
        {"id": "role-a-company-admin", "company_id": COMPANY_A, "name": "Company Admin", "status": "active"},
    ]
    store["rbac_user_roles"] = [
        {"id": "ur-coord", "user_id": REVIEWER_A.user_id, "role_id": "role-a-company-admin", "company_id": COMPANY_A},
    ]
    p1, p2 = _patched(store)
    p3 = patch(ORG_AUTH_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store))
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/org/departments", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    ids = {d["id"] for d in resp.get_json()}
    assert ids == {"dept-a-qa"}


def test_legacy_reviewer_qa_without_rbac_company_admin_role_denied_org_admin(client, store):
    store["rbac_roles"] = []
    store["rbac_user_roles"] = []
    p1, p2 = _patched(store)
    p3 = patch(ORG_AUTH_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store))
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/org/departments", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_update_department_cannot_cross_company_boundary(client, store):
    """org_structure_repo.update_department() must scope by company_id, not
    just department id — the service-role client used for super_admin (and
    now for an RBAC-only Company Admin whose legacy role isn't company_admin)
    bypasses RLS entirely, so this app-layer filter is the only thing
    stopping a cross-company PATCH by guessed/known department id."""
    row = org_structure_repo.update_department(
        FakeRbacClient(store), "dept-b-qa", COMPANY_A, {"status": "disabled"},
    )
    assert row is None
    assert store["departments"][1]["status"] == "active"  # unchanged


def test_provision_org_defaults_for_company_is_idempotent():
    """provision_org_defaults_for_company is the routine
    routes/companies.py::create_company calls for every new company —
    verifies it seeds departments/approval-levels/roles once, and a second
    call for the same company doesn't duplicate rows."""
    store_ = {"departments": [], "approval_levels": [], "rbac_roles": [
        {"id": "tpl-1", "company_id": None, "name": "Company Admin", "description": "",
         "department_code": None, "is_template": True},
        {"id": "tpl-2", "company_id": None, "name": "QA Manager", "description": "",
         "department_code": "QA", "is_template": True},
    ], "rbac_role_permissions": [], "rbac_permissions": [
        {"id": "perm-1", "module": "QMS", "action": "Approve"},
    ]}
    fake = FakeRbacClient(store_)

    summary_1 = org_structure_repo.provision_org_defaults_for_company(fake, COMPANY_A)
    assert summary_1["roles_created"] == 2
    assert len(store_["departments"]) == 12
    assert len(store_["approval_levels"]) == 3

    summary_2 = org_structure_repo.provision_org_defaults_for_company(fake, COMPANY_A)
    assert summary_2["roles_created"] == 0  # already cloned — idempotent
    assert len(store_["departments"]) == 12  # find_or_create_department didn't duplicate
    assert len(store_["approval_levels"]) == 3

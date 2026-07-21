"""
tests/test_security_tenant_rbac_esig.py — Regression coverage for the three
critical security fixes (SECURITY_REVIEW.md / ARCHITECTURE_REVIEW.md):

  1. Cross-tenant access: no request may read/write another company's data,
     even by guessing a valid record id (pharmagpt/tenancy.py).
  2. Unauthorized role access: server-side RBAC on destructive/approval
     routes (pharmagpt/auth/decorators.py::require_role).
  3. E-signature spoofing: performed_by/role/electronic_sig on an approval
     entry are always derived from the authenticated session, never from
     client-supplied JSON (pharmagpt/tenancy.py::signing_identity).

Exercises the real pharmagpt.app + real auth middleware (pattern borrowed
from tests/test_projects_dual_write.py), with the auth middleware's
resolve_tenant_context patched per-test so no real Supabase call is made.
"""

from unittest.mock import patch

import pytest

from pharmagpt import database as db
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.context import TenantContext

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"
COMPANY_B = "company-b-22222222-2222-2222-2222-222222222222"

ADMIN_A = TenantContext(
    user_id="admin-a", email="admin-a@example.com", display_name="Alice Admin",
    role="company_admin", company_id=COMPANY_A,
)
ADMIN_B = TenantContext(
    user_id="admin-b", email="admin-b@example.com", display_name="Bob Admin",
    role="company_admin", company_id=COMPANY_B,
)
REVIEWER_A = TenantContext(
    user_id="reviewer-a", email="reviewer-a@example.com", display_name="Rita Reviewer",
    role="reviewer_qa", company_id=COMPANY_A,
)
USER_A = TenantContext(
    user_id="user-a", email="user-a@example.com", display_name="Uma User",
    role="user", company_id=COMPANY_A,
)

AUTH_HEADERS = {"Authorization": "Bearer good-token"}
MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


def _create_project(client, tenant, name="Project"):
    with _as(tenant):
        return client.post(
            "/projects",
            json={"name": name, "equipment_name": "HPLC", "manufacturer": "Agilent",
                  "department": "QC", "validation_type": "IQ/OQ/PQ"},
            headers=AUTH_HEADERS,
        ).get_json()


def _create_deviation(client, tenant, title="Deviation"):
    with _as(tenant):
        return client.post(
            "/qms/deviations", json={"title": title}, headers=AUTH_HEADERS,
        ).get_json()


# ── 1. Cross-tenant access ───────────────────────────────────────────────────

def test_cross_tenant_cannot_read_another_companys_project(client):
    project = _create_project(client, ADMIN_A)

    with _as(ADMIN_B):
        resp = client.get(f"/projects/{project['id']}", headers=AUTH_HEADERS)

    assert resp.status_code == 404


def test_cross_tenant_cannot_update_another_companys_project(client):
    project = _create_project(client, ADMIN_A)

    with _as(ADMIN_B):
        resp = client.put(
            f"/projects/{project['id']}", json={"name": "Hijacked"}, headers=AUTH_HEADERS,
        )

    assert resp.status_code == 404
    assert db.get_project(project["id"])["name"] == "Project"


def test_cross_tenant_cannot_delete_another_companys_project(client):
    project = _create_project(client, ADMIN_A)

    with _as(ADMIN_B):
        resp = client.delete(f"/projects/{project['id']}", headers=AUTH_HEADERS)

    assert resp.status_code == 404
    assert db.get_project(project["id"]) is not None


def test_project_list_never_includes_other_companys_projects(client):
    _create_project(client, ADMIN_A, name="Company A Project")
    _create_project(client, ADMIN_B, name="Company B Project")

    with _as(ADMIN_A):
        resp = client.get("/projects", headers=AUTH_HEADERS)

    names = {p["name"] for p in resp.get_json()}
    assert names == {"Company A Project"}


def test_cross_tenant_cannot_read_another_companys_kb_document(client):
    with _as(ADMIN_A):
        upload_resp = client.post(
            "/kb/documents",
            data={"title": "Company A SOP", "file": (__import__("io").BytesIO(b"content"), "sop.txt")},
            content_type="multipart/form-data",
            headers=AUTH_HEADERS,
        )
    kb_id = upload_resp.get_json()["id"]

    with _as(ADMIN_B):
        resp = client.get(f"/kb/documents/{kb_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 404


def test_cross_tenant_cannot_read_another_companys_deviation(client):
    deviation = _create_deviation(client, ADMIN_A)

    with _as(ADMIN_B):
        resp = client.get(f"/qms/deviations/{deviation['id']}", headers=AUTH_HEADERS)

    assert resp.status_code == 404


def test_cross_tenant_cannot_read_another_companys_qms_attachments_or_audit_trail(client):
    """The shared polymorphic qms_attachments/comments/audit_trail/approvals
    tables have no company_id of their own — this exercises the
    record-ownership check in routes/qms_common.py::_record_exists that
    stands in for it."""
    deviation = _create_deviation(client, ADMIN_A)

    with _as(ADMIN_B):
        attachments = client.get(f"/qms/deviation/{deviation['id']}/attachments", headers=AUTH_HEADERS)
        audit_trail = client.get(f"/qms/deviation/{deviation['id']}/audit-trail", headers=AUTH_HEADERS)

    assert attachments.status_code == 404
    assert audit_trail.status_code == 404


def test_cross_tenant_cannot_link_another_companys_capa_to_own_deviation(client):
    """A deviation and a capa in different companies must not be linkable,
    even though both ids independently exist."""
    deviation = _create_deviation(client, ADMIN_A)
    with _as(ADMIN_B):
        capa = client.post("/qms/capa", json={"title": "Company B CAPA"}, headers=AUTH_HEADERS).get_json()

    with _as(ADMIN_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/link-capa",
            json={"capa_id": capa["id"]}, headers=AUTH_HEADERS,
        )

    assert resp.status_code == 400


# ── 2. Unauthorized role access (RBAC) ───────────────────────────────────────

def test_user_role_cannot_delete_project(client):
    project = _create_project(client, ADMIN_A)

    with _as(USER_A):
        resp = client.delete(f"/projects/{project['id']}", headers=AUTH_HEADERS)

    assert resp.status_code == 403
    assert db.get_project(project["id"]) is not None


def test_company_admin_can_delete_project(client):
    project = _create_project(client, ADMIN_A)

    with _as(ADMIN_A):
        resp = client.delete(f"/projects/{project['id']}", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert db.get_project(project["id"]) is None


def test_user_role_cannot_submit_deviation_approval(client):
    deviation = _create_deviation(client, ADMIN_A)

    with _as(USER_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/approval",
            json={"action": "Investigation Started"}, headers=AUTH_HEADERS,
        )

    assert resp.status_code == 403


def test_reviewer_qa_can_submit_deviation_approval(client):
    deviation = _create_deviation(client, ADMIN_A)

    with _as(REVIEWER_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/approval",
            json={"action": "Investigation Started"}, headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201


def test_user_role_cannot_delete_kb_document(client):
    with _as(ADMIN_A):
        upload_resp = client.post(
            "/kb/documents",
            data={"title": "SOP", "file": (__import__("io").BytesIO(b"content"), "sop.txt")},
            content_type="multipart/form-data",
            headers=AUTH_HEADERS,
        )
    kb_id = upload_resp.get_json()["id"]

    with _as(USER_A):
        resp = client.delete(f"/kb/documents/{kb_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 403
    assert db.get_kb_document(kb_id) is not None


# ── 3. E-signature spoofing ───────────────────────────────────────────────────

def test_approval_performed_by_cannot_be_spoofed_by_client(client):
    """A caller claiming to be someone else in the request body must be
    ignored — the audit trail must record the authenticated identity."""
    deviation = _create_deviation(client, ADMIN_A)

    with _as(REVIEWER_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/approval",
            json={
                "action": "Investigation Started",
                "performed_by": "Fake CEO",
                "role": "super_admin",
                "electronic_sig": "not-a-real-signature",
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    entry = resp.get_json()
    assert entry["performed_by"] == "Rita Reviewer"
    assert entry["role"] == "reviewer_qa"
    assert entry["electronic_sig"] == "Rita Reviewer"

    trail = qmsdb.get_approval_trail("deviation", deviation["id"])
    assert all(e["performed_by"] == "Rita Reviewer" for e in trail)
    assert not any(e["performed_by"] == "Fake CEO" for e in trail)


def test_approval_audit_entry_also_uses_authenticated_identity(client):
    deviation = _create_deviation(client, ADMIN_A)

    with _as(REVIEWER_A):
        client.post(
            f"/qms/deviations/{deviation['id']}/approval",
            json={"action": "Investigation Started", "performed_by": "Fake CEO"},
            headers=AUTH_HEADERS,
        )

    audit = qmsdb.get_audit_trail("deviation", deviation["id"])
    approval_entries = [a for a in audit if a["action"] == "Investigation Started"]
    assert approval_entries
    assert all(a["performed_by"] == "Rita Reviewer" for a in approval_entries)


def test_risk_assessment_approval_performed_by_cannot_be_spoofed(client):
    with _as(ADMIN_A):
        assessment = client.post(
            "/risk/assessments", json={"title": "Risk 1"}, headers=AUTH_HEADERS,
        ).get_json()

    with _as(REVIEWER_A):
        resp = client.post(
            f"/risk/assessments/{assessment['id']}/approval",
            json={"action": "Submitted for Review", "performed_by": "Fake CEO", "role": "super_admin"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    entry = resp.get_json()
    assert entry["performed_by"] == "Rita Reviewer"
    assert entry["role"] == "reviewer_qa"

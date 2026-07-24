"""
tests/test_phase_f_compliance.py — Regression coverage for the Phase F
compliance-hardening fixes (PHARMAGPT_v1.0_PHASE_F_RELEASE_CERTIFICATION.md):

  1. RBAC (C7): three previously-unguarded QA-significant endpoints now
     require company_admin/reviewer_qa.
  2. Workflow (C2): OQ/PQ test-case execution is blocked until the prior
     protocol stage is complete.
  3. Workflow (C3): a Validation Report cannot be approved while its linked
     qualification's PQ is incomplete, and CAN be approved once it is.
  4. Workflow (WP3 terminal-state immutability): a Closed CAPA cannot be
     edited via PUT.
  5. Audit trail (C4/C5): create/update/delete write a qms_audit_trail entry
     carrying company_id and an old/new value diff.
  6. Identity non-spoofability (C6): a QMS comment's author is always the
     authenticated caller, never a client-supplied value.

Same pattern as tests/test_security_tenant_rbac_esig.py: real app + real
auth middleware, with resolve_tenant_context patched per-test so no real
Supabase call is made.
"""

from unittest.mock import patch

import pytest

from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.context import TenantContext

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"

ADMIN_A = TenantContext(
    user_id="admin-a", email="admin-a@example.com", display_name="Alice Admin",
    role="company_admin", company_id=COMPANY_A,
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


# ── 1. RBAC (C7): previously-unguarded endpoints now require a QA/admin role ──

def test_user_role_cannot_publish_risk_assessment_to_library(client):
    with _as(ADMIN_A):
        assessment = client.post("/risk/assessments", json={"title": "Risk A"}, headers=AUTH_HEADERS).get_json()
    with _as(USER_A):
        resp = client.post(f"/risk/assessments/{assessment['id']}/publish", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_user_role_cannot_complete_qualification_protocol(client):
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "Qual A", "equipment_name": "HPLC"}, headers=AUTH_HEADERS).get_json()
        protocol = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "IQ"}, headers=AUTH_HEADERS).get_json()
    with _as(USER_A):
        resp = client.post(f"/qual/{qual['id']}/protocols/{protocol['id']}/complete", json={}, headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_user_role_cannot_escalate_capa_action(client):
    with _as(ADMIN_A):
        capa = client.post("/qms/capa", json={"title": "CAPA A"}, headers=AUTH_HEADERS).get_json()
        action = client.post(f"/qms/capa/{capa['id']}/actions",
                              json={"description": "Fix it", "owner": "Bob"}, headers=AUTH_HEADERS).get_json()
    with _as(USER_A):
        resp = client.post(f"/qms/capa/actions/{action['id']}/escalate",
                            json={"escalated_to": "Manager"}, headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_reviewer_qa_can_complete_qualification_protocol(client):
    """Control case: proves the block above is role-specific, not a general failure."""
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "Qual B", "equipment_name": "HPLC"}, headers=AUTH_HEADERS).get_json()
        protocol = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "IQ"}, headers=AUTH_HEADERS).get_json()
    with _as(REVIEWER_A):
        resp = client.post(f"/qual/{qual['id']}/protocols/{protocol['id']}/complete", json={}, headers=AUTH_HEADERS)
    assert resp.status_code == 200


# ── 2. Workflow (C2): OQ execution blocked until IQ is complete ──────────────

def test_oq_test_execution_blocked_before_iq_complete(client):
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "Seq Qual", "equipment_name": "Autoclave"}, headers=AUTH_HEADERS).get_json()
        client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "IQ"}, headers=AUTH_HEADERS)
        oq = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "OQ"}, headers=AUTH_HEADERS).get_json()
        tc = client.post(f"/qual/{qual['id']}/protocols/{oq['id']}/test-cases/add",
                          json={"test_name": "OQ-1"}, headers=AUTH_HEADERS).get_json()

        resp = client.post(f"/qual/{qual['id']}/protocols/{oq['id']}/execute/{tc['id']}",
                            json={"result": "pass"}, headers=AUTH_HEADERS)
    assert resp.status_code == 409
    assert "IQ" in resp.get_json()["error"]


def test_oq_test_execution_allowed_once_iq_complete(client):
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "Seq Qual 2", "equipment_name": "Autoclave"}, headers=AUTH_HEADERS).get_json()
        iq = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "IQ"}, headers=AUTH_HEADERS).get_json()
        oq = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "OQ"}, headers=AUTH_HEADERS).get_json()
        tc = client.post(f"/qual/{qual['id']}/protocols/{oq['id']}/test-cases/add",
                          json={"test_name": "OQ-1"}, headers=AUTH_HEADERS).get_json()

        # Complete IQ first (no test cases -> nothing pending, force not needed)
        complete_resp = client.post(f"/qual/{qual['id']}/protocols/{iq['id']}/complete", json={}, headers=AUTH_HEADERS)
        assert complete_resp.status_code == 200

        resp = client.post(f"/qual/{qual['id']}/protocols/{oq['id']}/execute/{tc['id']}",
                            json={"result": "pass"}, headers=AUTH_HEADERS)
    assert resp.status_code == 200


# ── 3. Workflow (C3): report approval gated on linked qualification's PQ ─────

def test_report_approval_blocked_when_linked_pq_incomplete(client):
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "PQ Qual", "equipment_name": "Freezer"}, headers=AUTH_HEADERS).get_json()
        client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "PQ"}, headers=AUTH_HEADERS)
        report = client.post("/report/", json={"title": "Freezer Report", "linked_qual_id": qual["id"]},
                              headers=AUTH_HEADERS).get_json()
        client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review"}, headers=AUTH_HEADERS)
        resp = client.post(f"/report/{report['id']}/approval", json={"action": "QA Approved"}, headers=AUTH_HEADERS)
    assert resp.status_code == 409
    assert "PQ" in resp.get_json()["error"]


def test_report_approval_allowed_once_linked_pq_complete(client):
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "PQ Qual 2", "equipment_name": "Freezer"}, headers=AUTH_HEADERS).get_json()
        pq = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "PQ"}, headers=AUTH_HEADERS).get_json()
        complete_resp = client.post(f"/qual/{qual['id']}/protocols/{pq['id']}/complete", json={}, headers=AUTH_HEADERS)
        assert complete_resp.status_code == 200

        report = client.post("/report/", json={"title": "Freezer Report 2", "linked_qual_id": qual["id"]},
                              headers=AUTH_HEADERS).get_json()
        client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review"}, headers=AUTH_HEADERS)
        resp = client.post(f"/report/{report['id']}/approval", json={"action": "QA Approved"}, headers=AUTH_HEADERS)
    assert resp.status_code == 201


def test_report_approval_unaffected_when_no_qualification_linked(client):
    """Linkage stays optional — this is the pre-existing, legitimate
    standalone-report workflow (see docs/WORKFLOW_VALIDATION_REPORT.md §2)."""
    with _as(ADMIN_A):
        report = client.post("/report/", json={"title": "Standalone Report"}, headers=AUTH_HEADERS).get_json()
        client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review"}, headers=AUTH_HEADERS)
        resp = client.post(f"/report/{report['id']}/approval", json={"action": "QA Approved"}, headers=AUTH_HEADERS)
    assert resp.status_code == 201


# ── 4. Workflow: terminal-state immutability ──────────────────────────────────

def test_closed_capa_cannot_be_edited(client):
    with _as(ADMIN_A):
        capa = client.post("/qms/capa", json={"title": "Closing CAPA"}, headers=AUTH_HEADERS).get_json()
        close_resp = client.post(f"/qms/capa/{capa['id']}/approval", json={"action": "Closed"}, headers=AUTH_HEADERS)
        assert close_resp.status_code == 201

        resp = client.put(f"/qms/capa/{capa['id']}", json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
    assert resp.status_code == 409


# ── 5. Audit trail (C4/C5): create/update/delete are logged with company_id + diff ──

def test_equipment_create_writes_audit_entry_with_company_and_diff(client, db_path):
    with _as(ADMIN_A):
        project = client.post("/projects", json={"name": "Audit Project", "equipment_name": "HPLC",
                                                   "manufacturer": "Agilent", "department": "QC",
                                                   "validation_type": "IQ/OQ/PQ"}, headers=AUTH_HEADERS).get_json()
        equipment = client.post(f"/projects/{project['id']}/equipment",
                                 json={"name": "HPLC-01"}, headers=AUTH_HEADERS).get_json()

    trail = qmsdb.get_audit_trail("equipment", equipment["id"])
    assert len(trail) == 1
    entry = trail[0]
    assert entry["action"] == "Created"
    assert entry["company_id"] == COMPANY_A
    assert entry["performed_by"] == "Alice Admin"
    assert entry["result"] == "success"
    assert '"name"' in entry["new_values"]


def test_equipment_update_writes_audit_entry_with_old_and_new_values(client):
    with _as(ADMIN_A):
        project = client.post("/projects", json={"name": "Audit Project 2", "equipment_name": "HPLC",
                                                   "manufacturer": "Agilent", "department": "QC",
                                                   "validation_type": "IQ/OQ/PQ"}, headers=AUTH_HEADERS).get_json()
        equipment = client.post(f"/projects/{project['id']}/equipment",
                                 json={"name": "HPLC-02"}, headers=AUTH_HEADERS).get_json()
        client.put(f"/equipment/{equipment['id']}", json={"name": "HPLC-02-Renamed"}, headers=AUTH_HEADERS)

    trail = qmsdb.get_audit_trail("equipment", equipment["id"])
    update_entries = [e for e in trail if e["action"] == "Updated"]
    assert len(update_entries) == 1
    assert "HPLC-02" in update_entries[0]["old_values"]
    assert "HPLC-02-Renamed" in update_entries[0]["new_values"]


def test_equipment_delete_writes_audit_entry(client):
    with _as(ADMIN_A):
        project = client.post("/projects", json={"name": "Audit Project 3", "equipment_name": "HPLC",
                                                   "manufacturer": "Agilent", "department": "QC",
                                                   "validation_type": "IQ/OQ/PQ"}, headers=AUTH_HEADERS).get_json()
        equipment = client.post(f"/projects/{project['id']}/equipment",
                                 json={"name": "HPLC-03"}, headers=AUTH_HEADERS).get_json()
        client.delete(f"/equipment/{equipment['id']}", headers=AUTH_HEADERS)

    trail = qmsdb.get_audit_trail("equipment", equipment["id"])
    assert any(e["action"] == "Deleted" for e in trail)


# ── 6. Identity non-spoofability (C6): comment author is server-derived ──────

def test_qms_comment_author_cannot_be_spoofed(client):
    with _as(ADMIN_A):
        deviation = client.post("/qms/deviations", json={"title": "Spoofing Test Deviation"},
                                 headers=AUTH_HEADERS).get_json()
        resp = client.post(
            f"/qms/deviation/{deviation['id']}/comments",
            json={"comment": "Looks fine", "author": "Fake CEO", "role": "super_admin"},
            headers=AUTH_HEADERS,
        )
    # record_type in the URL is "deviation" (see qms_common.py VALID_RECORD_TYPES)
    assert resp.status_code == 201
    comment = resp.get_json()
    assert comment["author"] == "Alice Admin"
    assert comment["role"] == "company_admin"

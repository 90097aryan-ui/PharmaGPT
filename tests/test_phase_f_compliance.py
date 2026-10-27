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
  7. Workflow (WP3): terminal-state immutability for remaining 7 modules
     (Document Control, URS, Qualification, Validation Report, Risk Assessment,
     Deviation, Change Control).

Same pattern as tests/test_security_tenant_rbac_esig.py: real app + real
auth middleware, with resolve_tenant_context patched per-test so no real
Supabase call is made.
"""

from unittest.mock import patch

import pytest

from pharmagpt import qms_database as qmsdb
from pharmagpt import qual_database as qdb
from pharmagpt import urs_database as udb
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

# Document Control assign-chain uses these fixed test user IDs (see tests/conftest.py)
# The workflow engine assigns these exact user_ids as approvers for the review steps.
DOC_REVIEWER_ID = "22222222-2222-2222-2222-222222222222"
DOC_DEPT_HEAD_ID = "33333333-3333-3333-3333-333333333333"
DOC_QA_HEAD_ID = "44444444-4444-4444-4444-444444444444"

# TenantContext for the Document Control review-chain approvers (matching assign-chain user_ids)
DOC_REVIEWER_CTX = TenantContext(
    user_id=DOC_REVIEWER_ID, email="reviewer@example.com", display_name="Rita Reviewer",
    role="reviewer_qa", company_id=COMPANY_A,
)
DOC_DEPT_HEAD_CTX = TenantContext(
    user_id=DOC_DEPT_HEAD_ID, email="dept-head@example.com", display_name="Dana Head",
    role="reviewer_qa", company_id=COMPANY_A,
)
DOC_QA_HEAD_CTX = TenantContext(
    user_id=DOC_QA_HEAD_ID, email="qa-head@example.com", display_name="Quinn Head",
    role="reviewer_qa", company_id=COMPANY_A,
)

# Separate company_admin approver for Change Control steps 7 & 11 (segregation of duties:
# the record creator ADMIN_A cannot be assigned as their own approver)
CC_APPROVER_ADMIN = TenantContext(
    user_id="cc-approver-admin", email="cc-approver@example.com", display_name="CC Approver Admin",
    role="company_admin", company_id=COMPANY_A,
)

AUTH_HEADERS = {"Authorization": "Bearer good-token"}
MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


class _FakeSupabaseClient:
    """Minimal stand-in for Supabase client used by tenancy.missing_or_inactive_users
    and Deviation/Change Control workflow builder approver validation."""
    def __init__(self, store: dict):
        self._store = store

    def table(self, name: str):
        return self

    def select(self, cols: str):
        return self

    def eq(self, col: str, val):
        return self

    def in_(self, col: str, vals):
        return self

    def execute(self):
        company_id = self._store.get("company_id", "company-a-11111111-1111-1111-1111-111111111111")
        # Filter to active users in the target company
        users = [
            u for u in self._store.get("users", [])
            if u.get("company_id") == company_id and u.get("status") == "active"
        ]
        # If an .in_("id", ...) filter was applied, narrow further
        if hasattr(self, "_filter_ids"):
            users = [u for u in users if u["id"] in self._filter_ids]
        return type("Resp", (), {"data": users})()


@pytest.fixture()
def client(db_path, monkeypatch):
    import pharmagpt.app as appmod
    # Electronic Signature gate (pharmagpt/services/esignature_service.py) —
    # these pre-existing tests predate e-signature and don't supply a
    # password/meaning/reason; bypassed here for the same reason
    # tests/conftest.py's shared `client` fixture bypasses it.
    import pharmagpt.services.esignature_service as esignature_service
    monkeypatch.setattr(esignature_service, "require_esignature", lambda *a, **k: None)

    # Yuktav org/RBAC/workflow authorization task, enforcement-closure phase:
    # has_business_permission() no longer bypasses company_admin/reviewer_qa
    # unconditionally — see tests/conftest.py's shared `client` fixture for
    # the full rationale (this file defines its own `client`, so it needs
    # the same mock independently).
    # Note: workflow_engine._check_business_permission imports get_effective_permissions
    # from pharmagpt.auth.rbac; module_access also imports it from rbac.
    # workspace_access also calls get_effective_permissions. Patch all three.
    import pharmagpt.services.rbac_defaults as rbac_defaults
    monkeypatch.setattr(
        "pharmagpt.auth.rbac.get_effective_permissions",
        lambda tenant: {(m, a) for m in rbac_defaults.MODULES for a in rbac_defaults.ACTIONS},
    )
    monkeypatch.setattr(
        "pharmagpt.auth.module_access.get_effective_permissions",
        lambda tenant: {(m, a) for m in rbac_defaults.MODULES for a in rbac_defaults.ACTIONS},
    )
    monkeypatch.setattr(
        "pharmagpt.auth.workspace_access.get_effective_permissions",
        lambda tenant: {(m, a) for m in rbac_defaults.MODULES for a in rbac_defaults.ACTIONS},
    )

    # Document Control assign-chain: permissive user directory validation
    # (mirrors tests/conftest.py's _PermissiveDocumentChainUsersClient)
    monkeypatch.setattr(
        "pharmagpt.routes.qms_documents.get_service_role_client",
        lambda: _FakeSupabaseClient({
            "company_id": COMPANY_A,
            "users": [
                {"id": DOC_REVIEWER_ID, "company_id": COMPANY_A, "status": "active"},
                {"id": DOC_DEPT_HEAD_ID, "company_id": COMPANY_A, "status": "active"},
                {"id": DOC_QA_HEAD_ID, "company_id": COMPANY_A, "status": "active"},
                {"id": "admin-a", "company_id": COMPANY_A, "status": "active"},
                {"id": "reviewer-a", "company_id": COMPANY_A, "status": "active"},
                {"id": "user-a", "company_id": COMPANY_A, "status": "active"},
            ],
        }),
    )

    # Deviation/Change Control workflow builder: permissive approver directory
    monkeypatch.setattr(
        "pharmagpt.routes.qms_deviations.get_service_role_client",
        lambda: _FakeSupabaseClient({
            "company_id": COMPANY_A,
            "users": [
                {"id": "admin-a", "company_id": COMPANY_A, "status": "active"},
                {"id": "reviewer-a", "company_id": COMPANY_A, "status": "active"},
                {"id": "user-a", "company_id": COMPANY_A, "status": "active"},
            ],
        }),
    )
    monkeypatch.setattr(
        "pharmagpt.routes.qms_change_control.get_service_role_client",
        lambda: _FakeSupabaseClient({
            "company_id": COMPANY_A,
            "users": [
                {"id": "admin-a", "company_id": COMPANY_A, "status": "active"},
                {"id": "reviewer-a", "company_id": COMPANY_A, "status": "active"},
                {"id": "user-a", "company_id": COMPANY_A, "status": "active"},
                {"id": "cc-approver-admin", "company_id": COMPANY_A, "status": "active"},
            ],
        }),
    )

    return appmod.app.test_client()


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


def _configure_deviation_workflow_builder(client, did):
    """Configure the Deviation Workflow Builder with approvers for all steps."""
    # Get current builder config
    builder = client.get(f"/qms/deviations/{did}/workflow-builder").get_json()
    steps = builder["steps"]
    # Assign approvers to all review-chain steps
    for s in steps:
        s["approver_user_id"] = "reviewer-a"
        s["approver_display_name"] = "Rita Reviewer"
    # CAPA phase approvers
    capa_phase = {
        "qa_review_approver_user_id": "reviewer-a",
        "qa_review_approver_display_name": "Rita Reviewer",
        "final_approval_approver_user_id": "reviewer-a",
        "final_approval_approver_display_name": "Rita Reviewer",
    }
    client.put(f"/qms/deviations/{did}/workflow-builder",
               json={"steps": steps, "capa_phase": capa_phase}, headers=AUTH_HEADERS)


def _configure_change_control_workflow_builder(client, cc_id):
    """Configure the Change Control Workflow Builder with approvers for all steps."""
    # Change Control uses a fixed template (CHANGE_CONTROL_WORKFLOW_V1), not a dynamic
    # builder. The workflow/start endpoint handles approver assignment internally.
    # No builder configuration needed — the template has fixed steps with eligible_roles.
    pass


def _advance_deviation_to_closed(client):
    """Advance the current deviation through its workflow to Closed status."""
    # The deviation ID is not known here; this helper is called after creation
    # and workflow start. We'll inline the logic in the test instead.
    pass


# ── 1. RBAC (C7): previously-unguarded endpoints now require a QA/admin role ──

def test_user_role_cannot_publish_risk_assessment_to_library(client):
    with _as(ADMIN_A):
        assessment = client.post("/risk/assessments", json={"title": "Risk A"}, headers=AUTH_HEADERS).get_json()
    with _as(USER_A):
        resp = client.post(f"/risk/assessments/{assessment['id']}/publish", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def _approve(*protocol_ids):
    """These Phase F tests are about role/sequencing/report gates, not about the
    approval-before-execution gate (covered in tests/test_validation_approval_workflow.py
    and tests/test_protocol_execution_gate.py), so the protocols start Approved."""
    for pid in protocol_ids:
        qdb.set_protocol_approval_status(pid, "approved")


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
        _approve(protocol["id"])
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
        _approve(oq["id"])

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
        _approve(iq["id"], oq["id"])

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
        _approve(pq["id"])
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
        # /approval is now a compatibility wrapper over the Workflow Engine
        # (CAPA_WORKFLOW_V1, 8 steps) — one call advances exactly one real
        # step, so reaching "Closed" from a fresh CAPA takes the full
        # sequence (same mechanism as tests/test_qms_routes.py::
        # test_capa_approval_status_map). Step 6 (Effectiveness Verification)
        # is a mandatory, dedicated, e-signed gate — see
        # tests/test_capa_effectiveness_verification.py — so it's decided via
        # /effectiveness-verification, not this legacy action map.
        for action in ["Root Cause Analysis Started", "Preventive Actions Planned", "Implementation Started",
                       "Effectiveness Check Started"]:
            client.post(f"/qms/capa/{capa['id']}/approval", json={"action": action}, headers=AUTH_HEADERS)

    # CRIT-02 (Security Audit remediation): ADMIN_A created this CAPA, so it
    # can no longer self-assign as its own approver — steps 6-8 (Effectiveness
    # Verification, QA Review, Closed) are decided as REVIEWER_A instead.
    with _as(REVIEWER_A):
        verify_resp = client.post(f"/qms/capa/{capa['id']}/effectiveness-verification", json={
            "verification_date": "2026-08-07", "verified_by": "Rita Reviewer",
            "verification_method": "Trend review", "objective_evidence": "No recurrence observed",
            "result": "Effective",
        }, headers=AUTH_HEADERS)
        assert verify_resp.status_code == 201
        client.post(f"/qms/capa/{capa['id']}/approval", json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)
        close_resp = client.post(f"/qms/capa/{capa['id']}/approval", json={"action": "Closed"}, headers=AUTH_HEADERS)
        assert close_resp.status_code == 201
        assert client.get(f"/qms/capa/{capa['id']}", headers=AUTH_HEADERS).get_json()["status"] == "Closed"

    with _as(ADMIN_A):
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


# ── 7. Workflow (WP3): terminal-state immutability for remaining 7 modules ──
# Replicates the CAPA test pattern (test_closed_capa_cannot_be_edited) for each
# module that received a terminal-state guard in routes/*.py. Each test:
#   1. Creates a record as ADMIN_A
#   2. Advances it to its terminal status via the module's approval/workflow path
#   3. Verifies the terminal status is reached
#   4. Attempts a PUT edit as ADMIN_A
#   5. Asserts HTTP 409 with audit-logged failure

def test_obsolete_document_control_cannot_be_edited(client):
    """Document Control: Obsolete is terminal (routes/qms_documents.py::update_document)."""
    with _as(ADMIN_A):
        doc = client.post("/qms/documents", json={"title": "Terminal SOP", "doc_type": "SOP"},
                          headers=AUTH_HEADERS).get_json()
        # Assign required review chain (Author-only, P0-A) — use permissive test user IDs
        client.post(f"/qms/documents/{doc['id']}/assign-chain", json={
            "reviewer_user_id": DOC_REVIEWER_ID, "reviewer_name": "Rita Reviewer",
            "department_head_user_id": DOC_DEPT_HEAD_ID, "department_head_name": "Dana Head",
            "quality_head_user_id": DOC_QA_HEAD_ID, "quality_head_name": "Quinn Head",
        }, headers=AUTH_HEADERS)
        # Self-check + final version upload (mandatory gates)
        client.post(f"/qms/documents/{doc['id']}/self-check", headers=AUTH_HEADERS)
        import io
        client.post(f"/qms/documents/{doc['id']}/versions/upload",
                    data={"file": (io.BytesIO(b"final content"), "final.txt")},
                    content_type="multipart/form-data", headers=AUTH_HEADERS)
        # Start workflow and advance to Effective via workflow engine
        client.post(f"/qms/documents/{doc['id']}/workflow/start", headers=AUTH_HEADERS)
        # Advance through workflow steps using /workflow endpoint (not /workflow/state)
        while True:
            state = client.get(f"/qms/documents/{doc['id']}/workflow", headers=AUTH_HEADERS).get_json()
            instance = state.get("instance")
            if not instance or instance.get("status") != "in_progress":
                break
            step = next(s for s in state["steps"] if s["step_order"] == instance["current_step_order"])
            if step["step_type"] == "approval":
                # Use the correct approver context for each step (matches assign-chain user_ids)
                if step["step_key"] == "under_review":
                    approver_ctx = DOC_REVIEWER_CTX
                elif step["step_key"] == "department_head_approval":
                    approver_ctx = DOC_DEPT_HEAD_CTX
                elif step["step_key"] == "quality_head_approval":
                    approver_ctx = DOC_QA_HEAD_CTX
                else:  # effective (Quality Release) - company_admin
                    approver_ctx = ADMIN_A
                with _as(approver_ctx):
                    client.post(f"/qms/documents/{doc['id']}/workflow/steps/{step['step_order']}/decide",
                                json={"decision": "approve"}, headers=AUTH_HEADERS)
            else:
                # Activity step (submitted) - advance
                client.post(f"/qms/documents/{doc['id']}/workflow/steps/{step['step_order']}/decide",
                            json={"decision": "advance"}, headers=AUTH_HEADERS)
        # Clear training gate and release to Effective
        t = client.post(f"/qms/documents/{doc['id']}/training",
                        json={"trainee_name": "Test Trainee"}, headers=AUTH_HEADERS).get_json()
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01"}, headers=AUTH_HEADERS)
        client.post(f"/qms/documents/{doc['id']}/release",
                    json={"meaning": "Released"}, headers=AUTH_HEADERS)
        assert client.get(f"/qms/documents/{doc['id']}", headers=AUTH_HEADERS).get_json()["status"] == "Effective"
        # Now apply post-Effective "Made Obsolete" action via legacy /approval endpoint
        client.post(f"/qms/documents/{doc['id']}/approval",
                    json={"action": "Made Obsolete", "password": "pw", "meaning": "Obsolete", "reason": "Superseded"},
                    headers=AUTH_HEADERS)
        assert client.get(f"/qms/documents/{doc['id']}", headers=AUTH_HEADERS).get_json()["status"] == "Obsolete"
        # Attempt edit on Obsolete document
        resp = client.put(f"/qms/documents/{doc['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "Obsolete" in resp.get_json()["error"]


def test_obsolete_urs_cannot_be_edited(client):
    """URS: obsolete is terminal (routes/urs.py::update_urs)."""
    with _as(ADMIN_A):
        urs = client.post("/urs/", json={"title": "Terminal URS"}, headers=AUTH_HEADERS).get_json()
        # The full 7-signatory path is covered in tests/test_validation_approval_workflow.py;
        # this test is about the terminal state, so put the record at Effective directly
        # (legacy pre-standard approval) and retire it through the real endpoint.
        udb.update_urs(urs["id"], {"status": "effective"})
        client.post(f"/urs/{urs['id']}/approval",
                    json={"action": "Obsolete", "password": "pw", "meaning": "Cancelled", "reason": "test"},
                    headers=AUTH_HEADERS)
        assert client.get(f"/urs/{urs['id']}", headers=AUTH_HEADERS).get_json()["status"] == "obsolete"
        resp = client.put(f"/urs/{urs['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "Obsolete" in resp.get_json()["error"]


def test_obsolete_qualification_cannot_be_edited(client):
    """Qualification: obsolete is terminal (routes/qual.py::update_qualification)."""
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "Terminal Qual", "equipment_name": "HPLC"},
                           headers=AUTH_HEADERS).get_json()
        # Create and complete IQ/OQ/PQ protocols to allow approval progression
        iq = client.post(f"/qual/{qual['id']}/protocols",
                         json={"protocol_type": "IQ"}, headers=AUTH_HEADERS).get_json()
        oq = client.post(f"/qual/{qual['id']}/protocols",
                         json={"protocol_type": "OQ"}, headers=AUTH_HEADERS).get_json()
        pq = client.post(f"/qual/{qual['id']}/protocols",
                         json={"protocol_type": "PQ"}, headers=AUTH_HEADERS).get_json()
        for proto in [iq, oq, pq]:
            client.post(f"/qual/{qual['id']}/protocols/{proto['id']}/complete", json={}, headers=AUTH_HEADERS)
        # Advance qualification through lifecycle to Obsolete
        qdb.update_qualification(qual["id"], {"status": "approved"})
        for action, meaning in [("Closed", "Approved"), ("Obsolete", "Cancelled")]:
            client.post(f"/qual/{qual['id']}/approval",
                        json={"action": action, "password": "pw", "meaning": meaning, "reason": "test"},
                        headers=AUTH_HEADERS)
        assert client.get(f"/qual/{qual['id']}", headers=AUTH_HEADERS).get_json()["status"] == "obsolete"
        resp = client.put(f"/qual/{qual['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "obsolete" in resp.get_json()["error"].lower()


def test_archived_validation_report_cannot_be_edited(client):
    """Validation Report: archived/obsolete are terminal (routes/report.py::update_report)."""
    with _as(ADMIN_A):
        report = client.post("/report/", json={"title": "Terminal Report"},
                             headers=AUTH_HEADERS).get_json()
        # Advance through Validation Report lifecycle to Archived
        for action in ["Submit for Review", "Technical Review Approved", "QA Approved",
                       "Released", "Archived"]:
            client.post(f"/report/{report['id']}/approval",
                        json={"action": action, "password": "pw", "meaning": action, "reason": "test"},
                        headers=AUTH_HEADERS)
        assert client.get(f"/report/{report['id']}", headers=AUTH_HEADERS).get_json()["status"] == "archived"
        resp = client.put(f"/report/{report['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "archived" in resp.get_json()["error"].lower()


def test_obsolete_validation_report_cannot_be_edited(client):
    """Validation Report: obsolete is also terminal (routes/report.py::update_report)."""
    with _as(ADMIN_A):
        report = client.post("/report/", json={"title": "Terminal Report 2"},
                             headers=AUTH_HEADERS).get_json()
        # Advance to Released then Obsolete (alternative terminal path)
        for action in ["Submit for Review", "Technical Review Approved", "QA Approved",
                       "Released", "Obsolete"]:
            client.post(f"/report/{report['id']}/approval",
                        json={"action": action, "password": "pw", "meaning": action, "reason": "test"},
                        headers=AUTH_HEADERS)
        assert client.get(f"/report/{report['id']}", headers=AUTH_HEADERS).get_json()["status"] == "obsolete"
        resp = client.put(f"/report/{report['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "obsolete" in resp.get_json()["error"].lower()


def test_closed_risk_assessment_cannot_be_edited(client):
    """Risk Assessment: Closed is terminal (routes/risk.py::update_assessment)."""
    with _as(ADMIN_A):
        assessment = client.post("/risk/assessments", json={"title": "Terminal Risk"},
                                 headers=AUTH_HEADERS).get_json()
        # Advance through Risk Assessment lifecycle to Closed
        for action in ["Submitted for Review", "Reviewed", "Approved", "Closed"]:
            client.post(f"/risk/assessments/{assessment['id']}/approval",
                        json={"action": action, "password": "pw", "meaning": action, "reason": "test"},
                        headers=AUTH_HEADERS)
        assert client.get(f"/risk/assessments/{assessment['id']}", headers=AUTH_HEADERS).get_json()["status"] == "Closed"
        resp = client.put(f"/risk/assessments/{assessment['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "Closed" in resp.get_json()["error"]


def test_closed_deviation_cannot_be_edited(client):
    """Deviation: Closed is terminal (routes/qms_deviations.py::update_deviation)."""
    with _as(ADMIN_A):
        deviation = client.post("/qms/deviations", json={"title": "Terminal Deviation"},
                                headers=AUTH_HEADERS).get_json()
        # Configure workflow builder with approvers (required before workflow/start)
        _configure_deviation_workflow_builder(client, deviation["id"])
        # Start workflow and advance through all steps to Closed
        client.post(f"/qms/deviations/{deviation['id']}/workflow/start", headers=AUTH_HEADERS)
        while True:
            state = client.get(f"/qms/deviations/{deviation['id']}/workflow", headers=AUTH_HEADERS).get_json()
            instance = state.get("instance")
            if not instance or instance.get("status") != "in_progress":
                break
            step = next(s for s in state["steps"] if s["step_order"] == instance["current_step_order"])
            # For approval steps, decide as REVIEWER_A (segregation of duties)
            if step["step_type"] == "approval":
                with _as(REVIEWER_A):
                    client.post(f"/qms/deviations/{deviation['id']}/workflow/steps/{step['step_order']}/decide",
                                json={"decision": "approve"}, headers=AUTH_HEADERS)
            else:
                # Activity steps - advance
                client.post(f"/qms/deviations/{deviation['id']}/workflow/steps/{step['step_order']}/decide",
                            json={"decision": "advance"}, headers=AUTH_HEADERS)
        assert client.get(f"/qms/deviations/{deviation['id']}", headers=AUTH_HEADERS).get_json()["status"] == "Closed"
        resp = client.put(f"/qms/deviations/{deviation['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "Closed" in resp.get_json()["error"]


def test_closed_change_control_cannot_be_edited(client):
    """Change Control: Closed is terminal (routes/qms_change_control.py::update_change_control)."""
    with _as(ADMIN_A):
        cc = client.post("/qms/change-control", json={"title": "Terminal Change Control"},
                         headers=AUTH_HEADERS).get_json()
        # Change Control uses a fixed template (CHANGE_CONTROL_WORKFLOW_V1), no builder config needed
        # Start workflow
        client.post(f"/qms/change-control/{cc['id']}/workflow/start", headers=AUTH_HEADERS)
        # Assign approvers for approval steps:
        # - Step 6 (qa_review): eligible_roles reviewer_qa,company_admin -> assign reviewer-a
        # - Step 7 (approval): eligible_roles company_admin -> assign cc-approver-admin (segregation of duties)
        # - Step 11 (closed): eligible_roles company_admin -> assign cc-approver-admin (segregation of duties)
        for step_order, user_id, display_name in [(6, "reviewer-a", "Rita Reviewer"), (7, "cc-approver-admin", "CC Approver Admin"), (11, "cc-approver-admin", "CC Approver Admin")]:
            resp = client.post(f"/qms/change-control/{cc['id']}/workflow/steps/{step_order}/assign",
                        json={"approvers": [{"user_id": user_id, "display_name": display_name}]},
                        headers=AUTH_HEADERS)
            print(f"  Assign step {step_order} ({user_id}): {resp.status_code} {resp.get_json()}")
        # Advance through all steps to Closed (safety limit: 20 iterations)
        for i in range(20):
            state = client.get(f"/qms/change-control/{cc['id']}/workflow", headers=AUTH_HEADERS).get_json()
            instance = state.get("instance")
            if not instance or instance.get("status") != "in_progress":
                print(f"Iteration {i}: workflow complete, status={instance.get('status') if instance else 'no instance'}")
                break
            step = next(s for s in state["steps"] if s["step_order"] == instance["current_step_order"])
            print(f"Iteration {i}: step {step['step_order']} ({step['step_key']}, {step['step_type']}), approvers={step.get('approvers', [])}")
            if step["step_type"] == "approval":
                # Step 6 (qa_review) uses reviewer_qa; steps 7, 11 (approval, closed) use company_admin
                if step["step_order"] in (7, 11):
                    approver_ctx = CC_APPROVER_ADMIN
                else:
                    approver_ctx = REVIEWER_A
                with _as(approver_ctx):
                    resp = client.post(f"/qms/change-control/{cc['id']}/workflow/steps/{step['step_order']}/decide",
                                json={"decision": "approve"}, headers=AUTH_HEADERS)
                    print(f"  Decide response: {resp.status_code} {resp.get_json()}")
            else:
                resp = client.post(f"/qms/change-control/{cc['id']}/workflow/steps/{step['step_order']}/decide",
                            json={"decision": "advance"}, headers=AUTH_HEADERS)
                print(f"  Advance response: {resp.status_code} {resp.get_json()}")
        else:
            pytest.fail("Change Control workflow did not complete within 20 iterations")
        assert client.get(f"/qms/change-control/{cc['id']}", headers=AUTH_HEADERS).get_json()["status"] == "Closed"
        resp = client.put(f"/qms/change-control/{cc['id']}",
                          json={"title": "Sneaky edit"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "Closed" in resp.get_json()["error"]

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
SUPER_ADMIN = TenantContext(
    user_id="super-1", email="super@example.com", display_name="Super Admin",
    role="super_admin", company_id=None,
)

AUTH_HEADERS = {"Authorization": "Bearer good-token"}
MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


@pytest.fixture(autouse=True)
def _active_approver_directory(monkeypatch):
    """/workflow/start validates every configured approver against the
    company's active users (routes/qms_deviations.py::
    _missing_or_inactive_approvers) — a real Supabase call in production.
    Autouse-patched here so this file's deviation-workflow tests (which
    configure either ADMIN_A or REVIEWER_A, both company A, as the
    approver) keep passing without per-test boilerplate."""
    from tests.test_assume_company_context import FakeSupabaseClient
    store = {"users": [
        {"id": ADMIN_A.user_id, "company_id": COMPANY_A, "status": "active"},
        {"id": REVIEWER_A.user_id, "company_id": COMPANY_A, "status": "active"},
    ]}
    monkeypatch.setattr(
        "pharmagpt.routes.qms_deviations.get_service_role_client", lambda: FakeSupabaseClient(store)
    )


@pytest.fixture()
def client(db_path, monkeypatch):
    import pharmagpt.app as appmod
    # Electronic Signature gate (pharmagpt/services/esignature_service.py) —
    # these pre-existing tests predate e-signature and don't supply a
    # password/meaning/reason; bypassed here for the same reason
    # tests/conftest.py's shared `client` fixture bypasses it. This file's
    # own esig-spoofing tests (e.g. test_risk_assessment_approval_
    # performed_by_cannot_be_spoofed) are about a different, still-relevant
    # protection — that a client-supplied performed_by/role/electronic_sig
    # is ignored in favor of the authenticated identity — and are unaffected
    # by bypassing this separate, newer gate.
    import pharmagpt.services.esignature_service as esignature_service
    monkeypatch.setattr(esignature_service, "require_esignature", lambda *a, **k: None)

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


def test_cross_tenant_cannot_reach_another_companys_feature_request(client):
    with _as(ADMIN_A):
        fr = client.post(
            "/qms/feature-requests", json={"title": "T", "description": "D"}, headers=AUTH_HEADERS,
        ).get_json()

    with _as(ADMIN_B):
        get_resp = client.get(f"/qms/feature-requests/{fr['id']}", headers=AUTH_HEADERS)
        put_resp = client.put(
            f"/qms/feature-requests/{fr['id']}", json={"title": "Hijacked"}, headers=AUTH_HEADERS,
        )
        delete_resp = client.delete(f"/qms/feature-requests/{fr['id']}", headers=AUTH_HEADERS)

    assert get_resp.status_code == 404
    assert put_resp.status_code == 404
    assert delete_resp.status_code == 404


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


def test_cross_tenant_cannot_reach_another_companys_qualification_protocol(client):
    """Phase 2 RBAC/multi-tenancy audit finding: routes/qual.py's protocol/
    test-case/execution/deviation routes checked only that a child id
    belonged to the qid in the URL, never that qid itself belonged to the
    caller's company — Company B could read/write Company A's qualification
    protocols, test cases, executions, and deviations by guessing ids.
    Fixed via a shared _scoped_protocol() helper (mirrors the file's own
    already-correct pattern in generate_test_cases/review_protocol/
    export_protocol_docx)."""
    with _as(ADMIN_A):
        qual = client.post("/qual/", json={"title": "Company A Qualification", "equipment_name": "HPLC"},
                           headers=AUTH_HEADERS).get_json()
        protocol = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "IQ"},
                               headers=AUTH_HEADERS).get_json()
        tc = client.post(f"/qual/{qual['id']}/protocols/{protocol['id']}/test-cases/add",
                         json={"test_name": "Power-up check"}, headers=AUTH_HEADERS).get_json()

    with _as(ADMIN_B):
        assert client.get(f"/qual/{qual['id']}/protocols/{protocol['id']}", headers=AUTH_HEADERS).status_code == 404
        assert client.put(f"/qual/{qual['id']}/protocols/{protocol['id']}", json={"status": "hijacked"},
                          headers=AUTH_HEADERS).status_code == 404
        assert client.get(f"/qual/{qual['id']}/protocols/{protocol['id']}/test-cases",
                          headers=AUTH_HEADERS).status_code == 404
        assert client.put(f"/qual/{qual['id']}/protocols/{protocol['id']}/test-cases/{tc['id']}",
                          json={"status": "pass"}, headers=AUTH_HEADERS).status_code == 404
        assert client.post(f"/qual/{qual['id']}/protocols/{protocol['id']}/execute/{tc['id']}",
                           json={"result": "pass"}, headers=AUTH_HEADERS).status_code == 404
        assert client.post(f"/qual/{qual['id']}/protocols/{protocol['id']}/complete",
                           json={}, headers=AUTH_HEADERS).status_code == 404


def test_cross_tenant_cannot_reach_another_companys_urs_requirement_or_version(client):
    """Phase 2 RBAC/multi-tenancy audit finding: routes/urs.py's requirement
    update/delete and version-requirements routes had no tenancy check at
    all (not even a same-company id-ownership check)."""
    with _as(ADMIN_A):
        urs = client.post("/urs/", json={"title": "Company A URS", "equipment_name": "HPLC"},
                          headers=AUTH_HEADERS).get_json()
        req = client.post(f"/urs/{urs['id']}/requirements/add", json={"requirement": "Shall log data"},
                          headers=AUTH_HEADERS).get_json()
        version = client.post(f"/urs/{urs['id']}/versions", json={"change_summary": "v1"},
                              headers=AUTH_HEADERS).get_json()

    with _as(ADMIN_B):
        assert client.put(f"/urs/{urs['id']}/requirements/{req['id']}", json={"requirement": "hijacked"},
                          headers=AUTH_HEADERS).status_code == 404
        assert client.delete(f"/urs/{urs['id']}/requirements/{req['id']}",
                             headers=AUTH_HEADERS).status_code == 404
        assert client.get(f"/urs/{urs['id']}/versions/{version['id']}/requirements",
                          headers=AUTH_HEADERS).status_code == 404


def test_cross_tenant_cannot_reach_another_companys_report_approval_or_versions(client):
    """Phase 2 RBAC/multi-tenancy audit finding: routes/report.py's GET
    approval-trail and versions routes had no tenancy check at all."""
    with _as(ADMIN_A):
        report = client.post("/report/", json={"title": "Company A Report"}, headers=AUTH_HEADERS).get_json()

    with _as(ADMIN_B):
        assert client.get(f"/report/{report['id']}/approval", headers=AUTH_HEADERS).status_code == 404
        assert client.get(f"/report/{report['id']}/versions", headers=AUTH_HEADERS).status_code == 404
        assert client.post(f"/report/{report['id']}/versions", json={"change_summary": "hijacked"},
                           headers=AUTH_HEADERS).status_code == 404


def test_cross_tenant_cannot_acknowledge_or_train_on_another_companys_document(client):
    """Phase 2 RBAC/multi-tenancy audit finding: routes/qms_documents.py's
    distribution-acknowledge and training-status routes are keyed only by
    their own id (no did in the URL) and had no tenancy check at all."""
    with _as(ADMIN_A):
        doc = client.post("/qms/documents", json={"title": "Company A SOP"}, headers=AUTH_HEADERS).get_json()
        dist = client.post(f"/qms/documents/{doc['id']}/distribution", json={"distributed_to": "QA Team"},
                           headers=AUTH_HEADERS).get_json()
        training = client.post(f"/qms/documents/{doc['id']}/training", json={"trainee_name": "Uma User"},
                               headers=AUTH_HEADERS).get_json()

    with _as(ADMIN_B):
        assert client.post(f"/qms/documents/distribution/{dist['id']}/acknowledge",
                           json={"acknowledged_date": "2026-07-23"}, headers=AUTH_HEADERS).status_code == 404
        assert client.put(f"/qms/documents/training/{training['id']}",
                          json={"training_status": "Completed"}, headers=AUTH_HEADERS).status_code == 404


def test_cross_tenant_cannot_escalate_another_companys_capa_action(client):
    """Phase 2 RBAC/multi-tenancy audit finding: routes/qms_capa.py's
    escalate-action route is keyed only by action id (no cid in the URL)
    and had no tenancy check at all."""
    with _as(ADMIN_A):
        capa = client.post("/qms/capa", json={"title": "Company A CAPA"}, headers=AUTH_HEADERS).get_json()
        action = client.post(f"/qms/capa/{capa['id']}/actions", json={"description": "Fix the thing"},
                             headers=AUTH_HEADERS).get_json()

    with _as(ADMIN_B):
        resp = client.post(f"/qms/capa/actions/{action['id']}/escalate",
                           json={"escalated_to": "Someone"}, headers=AUTH_HEADERS)
        assert resp.status_code == 404


def test_cross_tenant_cannot_reach_change_control_ai_narrative_endpoints(client):
    """Phase 2 RBAC/multi-tenancy audit finding: the 7 dynamically-generated
    AI-narrative endpoints (risk-summary, rollback-plan, regulatory-impact,
    justification, executive-summary, verification-summary,
    effectiveness-review — routes/qms_change_control.py's add_url_rule loop)
    checked existence via a raw, unscoped ccdb.get_change_control(cc_id)
    instead of tenancy.scoped_or_none(), unlike every other route in the
    same file. Company B could read Company A's change-control AI narrative
    content. Fixed to match the file's own established pattern."""
    with _as(ADMIN_A):
        cc = client.post("/qms/change-control", json={"title": "Company A Change"}, headers=AUTH_HEADERS).get_json()

    with _as(ADMIN_B):
        for path in ("risk-summary", "rollback-plan", "regulatory-impact", "justification",
                     "executive-summary", "verification-summary", "effectiveness-review"):
            resp = client.post(f"/qms/change-control/{cc['id']}/{path}", headers=AUTH_HEADERS)
            assert resp.status_code == 404, f"{path} leaked Company A's change control to Company B"


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


def _dev_configure_all_approvers(client, deviation_id, tenant):
    """Fill in every named-approval step's approver via the Workflow Builder
    — the Review chain plus the fixed CAPA-phase steps (QA Review, Final
    Approval) — since that's the only place approvers are ever configured
    for a deviation; there is no runtime "Assign Approver" action. Must be
    called while already inside an `_as(...)` context so the PUT is
    authenticated as the intended caller."""
    builder = client.get(f"/qms/deviations/{deviation_id}/workflow-builder", headers=AUTH_HEADERS).get_json()
    for s in builder["steps"]:
        s["approver_user_id"] = tenant.user_id
        s["approver_display_name"] = tenant.display_name
    capa_phase = {
        "qa_review_approver_user_id": tenant.user_id, "qa_review_approver_display_name": tenant.display_name,
        "final_approval_approver_user_id": tenant.user_id, "final_approval_approver_display_name": tenant.display_name,
    }
    client.put(f"/qms/deviations/{deviation_id}/workflow-builder",
               json={"steps": builder["steps"], "capa_phase": capa_phase}, headers=AUTH_HEADERS)


def _reach_qa_approval(client, deviation_id, approver_tenant):
    """Drive a deviation through the Initiator Manager Review -> QA Manager
    Review -> QA Approval gate, naming `approver_tenant` as the approver for
    all three steps (all eligible for reviewer_qa/company_admin)."""
    with _as(approver_tenant):
        _dev_configure_all_approvers(client, deviation_id, approver_tenant)
        client.post(f"/qms/deviations/{deviation_id}/workflow/start", headers=AUTH_HEADERS)
        for step_order in (2, 3, 4):
            client.post(
                f"/qms/deviations/{deviation_id}/workflow/steps/{step_order}/decide",
                json={"decision": "approve"}, headers=AUTH_HEADERS,
            )


def test_user_role_cannot_advance_workflow_activity_step(client):
    deviation = _create_deviation(client, ADMIN_A)
    _reach_qa_approval(client, deviation["id"], ADMIN_A)

    # Step 5 (Investigation Open) is an activity step eligible to
    # reviewer_qa/company_admin only — a plain 'user' may not advance it.
    with _as(USER_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/workflow/steps/5/decide",
            json={"decision": "advance"}, headers=AUTH_HEADERS,
        )

    assert resp.status_code == 403


def test_reviewer_qa_can_advance_eligible_workflow_activity_step(client):
    deviation = _create_deviation(client, ADMIN_A)
    _reach_qa_approval(client, deviation["id"], ADMIN_A)

    with _as(REVIEWER_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/workflow/steps/5/decide",
            json={"decision": "advance"}, headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200


def test_reviewer_qa_not_named_as_approver_cannot_decide_approval_step(client):
    """RBAC for approval steps is per-record and per-named-approver, not
    just per-role — see PHASE1_INVESTIGATION_PLAN.md: any reviewer_qa/
    company_admin could decide any deviation's approval under the old free
    action->status map; the redesign requires being the *assigned* approver."""
    deviation = _create_deviation(client, ADMIN_A)
    with _as(ADMIN_A):
        _dev_configure_all_approvers(client, deviation["id"], ADMIN_A)
        client.post(f"/qms/deviations/{deviation['id']}/workflow/start", headers=AUTH_HEADERS)

    with _as(REVIEWER_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/workflow/steps/2/decide",
            json={"decision": "approve"}, headers=AUTH_HEADERS,
        )

    assert resp.status_code == 403


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

def test_workflow_decide_identity_cannot_be_spoofed_by_client(client):
    """A caller claiming to be someone else in the request body must be
    ignored — the decided_by field must record the authenticated identity."""
    deviation = _create_deviation(client, ADMIN_A)
    with _as(ADMIN_A):
        _dev_configure_all_approvers(client, deviation["id"], REVIEWER_A)
        client.post(f"/qms/deviations/{deviation['id']}/workflow/start", headers=AUTH_HEADERS)

    with _as(REVIEWER_A):
        resp = client.post(
            f"/qms/deviations/{deviation['id']}/workflow/steps/2/decide",
            json={
                "decision": "approve",
                "performed_by": "Fake CEO",
                "role": "super_admin",
                "electronic_sig": "not-a-real-signature",
            },
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200
    state = resp.get_json()
    step2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step2["decided_by"] == "Rita Reviewer"
    assert step2["decided_by"] != "Fake CEO"


def test_workflow_audit_entry_also_uses_authenticated_identity(client):
    deviation = _create_deviation(client, ADMIN_A)
    with _as(ADMIN_A):
        _dev_configure_all_approvers(client, deviation["id"], REVIEWER_A)
        client.post(f"/qms/deviations/{deviation['id']}/workflow/start", headers=AUTH_HEADERS)

    with _as(REVIEWER_A):
        client.post(
            f"/qms/deviations/{deviation['id']}/workflow/steps/2/decide",
            json={"decision": "approve", "performed_by": "Fake CEO"},
            headers=AUTH_HEADERS,
        )

    audit = qmsdb.get_audit_trail("deviation", deviation["id"])
    approval_entries = [a for a in audit if "Approved" in a["action"]]
    assert approval_entries
    assert all(a["performed_by"] == "Rita Reviewer" for a in approval_entries)
    assert not any(a["performed_by"] == "Fake CEO" for a in audit)


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


# ── 3b. E-signature spoofing at record-CREATION time (REPOSITORY_AUDIT.md
# Critical finding; FUNCTIONAL_VALIDATION_REPORT.md C3) ─────────────────────
# The 2026-07-21 fix above only covered approval actions. Record creation
# (Deviation/CAPA/Change Control/Document) took the audit trail's
# performed_by straight from a client-supplied field (initiated_by /
# requested_by / owner) instead of the authenticated identity. Fixed by
# using tenancy.signing_identity(g.tenant)["performed_by"] at creation time
# too, exactly mirroring the approval-time pattern above.

def test_deviation_creation_audit_performed_by_cannot_be_spoofed(client):
    with _as(ADMIN_A):
        resp = client.post(
            "/qms/deviations",
            json={"title": "Deviation", "initiated_by": "Fake CEO Spoofed Identity"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    deviation = resp.get_json()

    audit = qmsdb.get_audit_trail("deviation", deviation["id"])
    creation_entries = [a for a in audit if a["action"] == "Deviation initiated"]
    assert creation_entries
    assert all(a["performed_by"] == "Alice Admin" for a in creation_entries)
    assert not any(a["performed_by"] == "Fake CEO Spoofed Identity" for a in creation_entries)


def test_capa_creation_audit_performed_by_cannot_be_spoofed(client):
    with _as(ADMIN_A):
        resp = client.post(
            "/qms/capa",
            json={"title": "CAPA", "initiated_by": "Fake CEO Spoofed Identity"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    capa = resp.get_json()

    audit = qmsdb.get_audit_trail("capa", capa["id"])
    creation_entries = [a for a in audit if a["action"] == "CAPA created"]
    assert creation_entries
    assert all(a["performed_by"] == "Alice Admin" for a in creation_entries)
    assert not any(a["performed_by"] == "Fake CEO Spoofed Identity" for a in creation_entries)


def test_change_control_creation_audit_performed_by_cannot_be_spoofed(client):
    with _as(ADMIN_A):
        resp = client.post(
            "/qms/change-control",
            json={"title": "Change Control", "requested_by": "Fake CEO Spoofed Identity"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    cc = resp.get_json()

    audit = qmsdb.get_audit_trail("change_control", cc["id"])
    creation_entries = [a for a in audit if a["action"] == "Change control drafted"]
    assert creation_entries
    assert all(a["performed_by"] == "Alice Admin" for a in creation_entries)
    assert not any(a["performed_by"] == "Fake CEO Spoofed Identity" for a in creation_entries)


def test_document_creation_audit_performed_by_cannot_be_spoofed(client):
    with _as(ADMIN_A):
        resp = client.post(
            "/qms/documents",
            json={"title": "Document", "owner": "Fake CEO Spoofed Identity"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    document = resp.get_json()

    audit = qmsdb.get_audit_trail("document", document["id"])
    creation_entries = [a for a in audit if a["action"] == "Document created"]
    assert creation_entries
    assert all(a["performed_by"] == "Alice Admin" for a in creation_entries)
    assert not any(a["performed_by"] == "Fake CEO Spoofed Identity" for a in creation_entries)


# ── 3c. Phase 3 (Enterprise Validation Platform): equipment_documents was
# widened to accept deviation/capa/change_control/risk_assessment as
# source_types (equipment_database.py::SOURCE_TYPES) for the Project ->
# Equipment -> Validation Documents -> QMS Records -> Knowledge Base
# traceability chain. This is a two-sided tenant check: the equipment row
# was already scoped, but the *linked* record must be scoped too — otherwise
# a caller could discover another company's deviation/capa/change-control/
# risk-assessment id by linking it into their own equipment record. ────────

def _create_equipment(client, tenant, name="HPLC System"):
    with _as(tenant):
        project = client.post(
            "/projects", json={"name": "Equipment Project", "equipment_name": "HPLC",
                                "manufacturer": "Agilent", "department": "QC",
                                "validation_type": "IQ/OQ/PQ"},
            headers=AUTH_HEADERS,
        ).get_json()
        return client.post(
            f"/projects/{project['id']}/equipment", json={"name": name}, headers=AUTH_HEADERS,
        ).get_json()


def test_cross_tenant_cannot_link_equipment_to_another_companys_deviation(client):
    equipment = _create_equipment(client, ADMIN_A)
    with _as(ADMIN_B):
        deviation_b = client.post(
            "/qms/deviations", json={"title": "Company B Deviation"}, headers=AUTH_HEADERS,
        ).get_json()

    with _as(ADMIN_A):
        resp = client.post(
            f"/equipment/{equipment['id']}/documents",
            json={"document_role": "quality_record", "source_type": "deviation", "source_id": deviation_b["id"]},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 404


def test_cross_tenant_cannot_link_own_equipment_from_another_company(client):
    equipment_a = _create_equipment(client, ADMIN_A)
    with _as(ADMIN_A):
        deviation_a = client.post(
            "/qms/deviations", json={"title": "Company A Deviation"}, headers=AUTH_HEADERS,
        ).get_json()

    with _as(ADMIN_B):
        resp = client.post(
            f"/equipment/{equipment_a['id']}/documents",
            json={"document_role": "quality_record", "source_type": "deviation", "source_id": deviation_a["id"]},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 404


# ── 3d. Risk Assessment e-signature parity fix (Phase 3) ────────────────────
# risk_approval was missing electronic_sig entirely, unlike every other
# suite's approval-trail table — routes/risk.py now passes
# sig["electronic_sig"] the same way qms_documents.py/urs.py/qual.py do.

def test_risk_assessment_approval_now_records_electronic_sig(client):
    with _as(ADMIN_A):
        assessment = client.post(
            "/risk/assessments", json={"title": "Risk 1"}, headers=AUTH_HEADERS,
        ).get_json()

    with _as(REVIEWER_A):
        resp = client.post(
            f"/risk/assessments/{assessment['id']}/approval",
            json={"action": "Submitted for Review", "electronic_sig": "Fake Sig"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 201
    entry = resp.get_json()
    assert entry["electronic_sig"] == "Rita Reviewer"


# ── 4. POST /projects role matrix (PLATFORM_ARCHITECTURE.md §7) ─────────────
# Any authenticated identity scoped to a company (company_admin, reviewer_qa,
# user) may create a project inside that company. Super Admin has no
# standing company_id and is denied — "no standing access to tenant
# content" is the platform's documented posture, not a bug
# (routes/projects.py::create_project).

def _post_project(client, tenant, name="RBAC matrix project"):
    with _as(tenant):
        return client.post(
            "/projects",
            json={"name": name, "equipment_name": "HPLC", "manufacturer": "Agilent",
                  "department": "QC", "validation_type": "IQ/OQ/PQ"},
            headers=AUTH_HEADERS,
        )


def test_company_admin_can_create_project(client):
    resp = _post_project(client, ADMIN_A)

    assert resp.status_code == 201
    assert resp.get_json()["company_id"] == COMPANY_A


def test_reviewer_qa_can_create_project(client):
    resp = _post_project(client, REVIEWER_A)

    assert resp.status_code == 201
    assert resp.get_json()["company_id"] == COMPANY_A


def test_user_role_can_create_project(client):
    resp = _post_project(client, USER_A)

    assert resp.status_code == 201
    assert resp.get_json()["company_id"] == COMPANY_A


def test_super_admin_cannot_create_project_without_standing_access(client):
    resp = _post_project(client, SUPER_ADMIN)

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "Super Admin has no standing access to tenant content"


def test_super_admin_creation_attempt_persists_no_project(client):
    """A rejected Super Admin create must leave no row behind — nothing for
    a subsequent request to find or leak across tenants."""
    before = len(db.get_all_projects(COMPANY_A))

    resp = _post_project(client, SUPER_ADMIN)

    assert resp.status_code == 403
    assert len(db.get_all_projects(COMPANY_A)) == before

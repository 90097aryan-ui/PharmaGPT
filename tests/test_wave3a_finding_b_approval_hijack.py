"""
tests/test_wave3a_finding_b_approval_hijack.py — Regression coverage for
Wave 3A-B (Security Audit remediation, Finding B): the legacy
POST /qms/capa/<id>/approval and POST /qms/change-control/<id>/approval
wrappers used to silently REPLACE an already-assigned approval step's named
approver(s) with whoever called the endpoint next, then immediately decide
the step as that caller — completely bypassing the intended guarantee that
only the deliberately named approver may perform the governed approval
(routes/qms_capa.py::submit_approval, routes/qms_change_control.py::
submit_approval).

Fix: the self-assign fallback in both wrappers is now gated identically to
routes/qms_documents.py::submit_approval's own fallback — it only fires when
the step has NO approver assigned yet at all (`not approver_ids`), never to
displace an existing assignment. Once a real assignment exists, an
unauthorized caller now falls through to wfe.decide_step()'s own
WorkflowPermissionError, which both routes now map to 403 (previously
lumped in with WorkflowError as a blanket 409).

Pattern mirrors tests/test_security_tenant_rbac_esig.py exactly (real
pharmagpt.app + real auth middleware, resolve_tenant_context patched per
call).
"""

from unittest.mock import patch

import pytest

from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.context import TenantContext

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"

CREATOR = TenantContext(
    user_id="creator-a", email="creator-a@example.com", display_name="Cara Creator",
    role="company_admin", company_id=COMPANY_A,
)
LEGITIMATE_APPROVER = TenantContext(
    user_id="reviewer-a", email="reviewer-a@example.com", display_name="Rita Reviewer",
    role="reviewer_qa", company_id=COMPANY_A,
)
HIJACKING_USER = TenantContext(
    user_id="approver-a", email="approver-a@example.com", display_name="Amy Approver",
    role="reviewer_qa", company_id=COMPANY_A,
)

AUTH_HEADERS = {"Authorization": "Bearer good-token"}
MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


@pytest.fixture()
def client(db_path, monkeypatch):
    import pharmagpt.app as appmod
    import pharmagpt.services.esignature_service as esignature_service
    monkeypatch.setattr(esignature_service, "require_esignature", lambda *a, **k: None)

    from tests.test_assume_company_context import FakeSupabaseClient
    store = {"users": [
        {"id": CREATOR.user_id, "company_id": COMPANY_A, "status": "active"},
        {"id": LEGITIMATE_APPROVER.user_id, "company_id": COMPANY_A, "status": "active"},
        {"id": HIJACKING_USER.user_id, "company_id": COMPANY_A, "status": "active"},
    ]}
    monkeypatch.setattr(
        "pharmagpt.routes.qms_capa.get_service_role_client", lambda: FakeSupabaseClient(store)
    )
    monkeypatch.setattr(
        "pharmagpt.routes.qms_change_control.get_service_role_client", lambda: FakeSupabaseClient(store)
    )

    # Yuktav org/RBAC/workflow authorization task, enforcement-closure phase:
    # has_business_permission() no longer bypasses company_admin/reviewer_qa
    # unconditionally — see tests/conftest.py's shared `client` fixture for
    # the full rationale (this file defines its own `client`, so it needs
    # the same mock independently).
    import pharmagpt.services.rbac_defaults as rbac_defaults
    monkeypatch.setattr(
        "pharmagpt.auth.module_access.get_effective_permissions",
        lambda tenant: {(m, a) for m in rbac_defaults.MODULES for a in rbac_defaults.ACTIONS},
    )

    return appmod.app.test_client()


# ── CAPA setup: drive a fresh CAPA to its first 'approval'-type step ────────

def _capa_to_qa_review(client):
    """Create a CAPA as CREATOR and advance it through the five leading
    'activity' steps to 'qa_review' (an 'approval' step) — mirrors
    tests/test_qms_routes.py::test_capa_approval_status_map's own sequence,
    minus Effectiveness Verification's dedicated gate (reached beforehand
    here since qa_review is CAPA_WORKFLOW_V1 step 7, effectiveness_check is
    step 6 — so this helper submits effectiveness-verification too)."""
    with _as(CREATOR):
        capa = client.post("/qms/capa", json={"title": "CAPA-Hijack-Test"}, headers=AUTH_HEADERS).get_json()
        cid = capa["id"]
        for action in ["Root Cause Analysis Started", "Preventive Actions Planned",
                       "Implementation Started", "Effectiveness Check Started"]:
            r = client.post(f"/qms/capa/{cid}/approval", json={"action": action}, headers=AUTH_HEADERS)
            assert r.status_code == 201, r.get_json()
        assert client.get(f"/qms/capa/{cid}", headers=AUTH_HEADERS).get_json()["status"] == "Effectiveness Check"

    # Effectiveness Verification (step 6) requires a non-creator identity
    # (CRIT-02) and its own dedicated, e-signed endpoint.
    with _as(LEGITIMATE_APPROVER):
        r = client.post(f"/qms/capa/{cid}/effectiveness-verification", json={
            "verification_date": "2026-08-07", "verified_by": "Rita Reviewer",
            "verification_method": "Trend review", "objective_evidence": "No recurrence observed",
            "result": "Effective",
        }, headers=AUTH_HEADERS)
        assert r.status_code == 201, r.get_json()
    with _as(CREATOR):
        assert client.get(f"/qms/capa/{cid}", headers=AUTH_HEADERS).get_json()["status"] == "QA Review"
    return cid


def _cc_to_qa_review(client):
    """Create a Change Control as CREATOR and advance it through the five
    leading 'activity' steps to 'qa_review' (an 'approval' step)."""
    with _as(CREATOR):
        cc = client.post("/qms/change-control", json={"title": "CC-Hijack-Test"}, headers=AUTH_HEADERS).get_json()
        cc_id = cc["id"]
        for action in ["Initial Review Started", "Impact Assessment Started",
                       "Risk Assessment Started", "Sent for Department Review"]:
            r = client.post(f"/qms/change-control/{cc_id}/approval", json={"action": action}, headers=AUTH_HEADERS)
            assert r.status_code == 201, r.get_json()
        assert client.get(f"/qms/change-control/{cc_id}", headers=AUTH_HEADERS).get_json()["status"] == "QA Review"
    return cc_id


def _assign(client, record_type, record_id, step_order, approver):
    url = f"/qms/{'capa' if record_type == 'capa' else 'change-control'}/{record_id}/workflow/steps/{step_order}/assign"
    with _as(CREATOR):
        r = client.post(url, json={"approvers": [{"user_id": approver.user_id, "display_name": approver.display_name}]},
                         headers=AUTH_HEADERS)
    assert r.status_code == 200, r.get_json()


def _current_step(client, record_type, record_id):
    url = f"/qms/{'capa' if record_type == 'capa' else 'change-control'}/{record_id}/workflow"
    with _as(CREATOR):
        wf = client.get(url, headers=AUTH_HEADERS).get_json()
    order = wf["instance"]["current_step_order"]
    return order, next(s for s in wf["steps"] if s["step_order"] == order)


# ── Finding B: hijack attempt must be rejected (403) for both modules ──────

def test_capa_legacy_approval_cannot_hijack_assigned_approver(client):
    cid = _capa_to_qa_review(client)
    order, step = _current_step(client, "capa", cid)
    assert step["step_key"] == "qa_review"

    _assign(client, "capa", cid, order, LEGITIMATE_APPROVER)
    _, step_before = _current_step(client, "capa", cid)
    assert {a["user_id"] for a in step_before["approvers"]} == {LEGITIMATE_APPROVER.user_id}

    with _as(CREATOR):
        capa_before = client.get(f"/qms/capa/{cid}", headers=AUTH_HEADERS).get_json()
    trail_before = qmsdb.get_approval_trail("capa", cid)
    sigs_before = qmsdb.get_esignatures("capa", cid)

    with _as(HIJACKING_USER):
        hijack_resp = client.post(f"/qms/capa/{cid}/approval",
                                   json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)

    assert hijack_resp.status_code == 403, hijack_resp.get_json()

    _, step_after = _current_step(client, "capa", cid)
    assert {a["user_id"] for a in step_after["approvers"]} == {LEGITIMATE_APPROVER.user_id}, (
        "Assignment must be byte-for-byte unchanged after a blocked hijack attempt"
    )
    assert step_after["status"] == step_before["status"] == "pending"
    assert step_after.get("decided_by") in ("", None)

    with _as(CREATOR):
        capa_after = client.get(f"/qms/capa/{cid}", headers=AUTH_HEADERS).get_json()
    assert capa_after["status"] == capa_before["status"] == "QA Review"
    assert qmsdb.get_approval_trail("capa", cid) == trail_before, "No approval entry may be created"
    assert qmsdb.get_esignatures("capa", cid) == sigs_before, "No e-signature record may be created"


def test_change_control_legacy_approval_cannot_hijack_assigned_approver(client):
    cc_id = _cc_to_qa_review(client)
    order, step = _current_step(client, "change_control", cc_id)
    assert step["step_key"] == "qa_review"

    _assign(client, "change_control", cc_id, order, LEGITIMATE_APPROVER)
    _, step_before = _current_step(client, "change_control", cc_id)
    assert {a["user_id"] for a in step_before["approvers"]} == {LEGITIMATE_APPROVER.user_id}

    with _as(CREATOR):
        cc_before = client.get(f"/qms/change-control/{cc_id}", headers=AUTH_HEADERS).get_json()
    trail_before = qmsdb.get_approval_trail("change_control", cc_id)
    sigs_before = qmsdb.get_esignatures("change_control", cc_id)

    with _as(HIJACKING_USER):
        hijack_resp = client.post(f"/qms/change-control/{cc_id}/approval",
                                   json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)

    assert hijack_resp.status_code == 403, hijack_resp.get_json()

    _, step_after = _current_step(client, "change_control", cc_id)
    assert {a["user_id"] for a in step_after["approvers"]} == {LEGITIMATE_APPROVER.user_id}, (
        "Assignment must be byte-for-byte unchanged after a blocked hijack attempt"
    )
    assert step_after["status"] == step_before["status"] == "pending"
    assert step_after.get("decided_by") in ("", None)

    with _as(CREATOR):
        cc_after = client.get(f"/qms/change-control/{cc_id}", headers=AUTH_HEADERS).get_json()
    assert cc_after["status"] == cc_before["status"] == "QA Review"
    assert qmsdb.get_approval_trail("change_control", cc_id) == trail_before, "No approval entry may be created"
    assert qmsdb.get_esignatures("change_control", cc_id) == sigs_before, "No e-signature record may be created"


# ── Legitimate approval must keep working through the legacy wrapper ───────

def test_capa_legacy_approval_still_works_for_the_assigned_approver(client):
    cid = _capa_to_qa_review(client)
    order, _ = _current_step(client, "capa", cid)
    _assign(client, "capa", cid, order, LEGITIMATE_APPROVER)

    with _as(LEGITIMATE_APPROVER):
        r = client.post(f"/qms/capa/{cid}/approval",
                         json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)
    assert r.status_code == 201, r.get_json()

    _, step_after = _current_step(client, "capa", cid)
    assert step_after["step_key"] == "closed"  # advanced past qa_review


def test_change_control_legacy_approval_still_works_for_the_assigned_approver(client):
    cc_id = _cc_to_qa_review(client)
    order, _ = _current_step(client, "change_control", cc_id)
    _assign(client, "change_control", cc_id, order, LEGITIMATE_APPROVER)

    with _as(LEGITIMATE_APPROVER):
        r = client.post(f"/qms/change-control/{cc_id}/approval",
                         json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)
    assert r.status_code == 201, r.get_json()

    with _as(CREATOR):
        cc = client.get(f"/qms/change-control/{cc_id}", headers=AUTH_HEADERS).get_json()
    assert cc["status"] == "Approval"  # advanced past qa_review


# ── No-approver fallback must still work (legacy compatibility) ────────────

def test_capa_legacy_approval_fallback_still_self_assigns_when_unassigned(client):
    """No prior /workflow/steps/<n>/assign call at all — the first
    non-creator caller may still self-assign-and-decide, exactly as before
    this fix. Only a caller arriving AFTER a real assignment already exists
    is now blocked."""
    cid = _capa_to_qa_review(client)
    order, step = _current_step(client, "capa", cid)
    assert not step["approvers"], "precondition: nobody assigned yet"

    with _as(HIJACKING_USER):  # any non-creator, role-eligible identity
        r = client.post(f"/qms/capa/{cid}/approval",
                         json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)
    assert r.status_code == 201, r.get_json()

    _, step_after = _current_step(client, "capa", cid)
    assert step_after["step_key"] == "closed"


def test_change_control_legacy_approval_fallback_still_self_assigns_when_unassigned(client):
    cc_id = _cc_to_qa_review(client)
    order, step = _current_step(client, "change_control", cc_id)
    assert not step["approvers"], "precondition: nobody assigned yet"

    with _as(HIJACKING_USER):
        r = client.post(f"/qms/change-control/{cc_id}/approval",
                         json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)
    assert r.status_code == 201, r.get_json()


# ── CRIT-02 creator-exclusion must still hold through the (now-gated) fallback ──

def test_capa_creator_still_cannot_self_assign_via_legacy_fallback(client):
    cid = _capa_to_qa_review(client)
    order, step = _current_step(client, "capa", cid)
    assert not step["approvers"]

    with _as(CREATOR):
        r = client.post(f"/qms/capa/{cid}/approval",
                         json={"action": "Submitted for QA Review"}, headers=AUTH_HEADERS)
    # reject_creator_as_approver raises a plain WorkflowError (not
    # WorkflowPermissionError) — 409, same as before this fix.
    assert r.status_code == 409, r.get_json()

    _, step_after = _current_step(client, "capa", cid)
    assert not step_after["approvers"], "creator's self-assign attempt must not have been persisted"

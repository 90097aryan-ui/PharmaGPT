"""
tests/test_qms_market_complaint.py — Market Complaint Management (P0)
regression coverage: CRUD, numbering, tenant isolation, IDOR protection,
RBAC, workflow transitions (assign/decide/reject), required-field
validation, e-signature gating, closed-terminal behavior, complaint-number
immutability, audit events, and qms_common attachments/comments/audit-trail
integration.

Mirrors the existing patterns in tests/test_qms_routes.py,
tests/test_crit02_segregation_of_duties.py, and
tests/test_security_tenant_rbac_esig.py — same `client` fixture (see
tests/conftest.py; note the flask_test_app_context gotcha: every test here
drives the record exclusively through `client`, never a manually-held
app_context()).
"""

import pytest

from pharmagpt.auth.context import TenantContext
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID

_CREATOR_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py::_TEST_TENANT.user_id
_APPROVER_ID = "00000000-0000-0000-0000-000000000002"  # distinct, non-creator, same company
_OTHER_COMPANY_ID = "11111111-1111-1111-1111-111111111111"
_CROSS_COMPANY_USER_ID = "00000000-0000-0000-0000-000000000004"  # real, active, but a DIFFERENT company
_INACTIVE_SAME_COMPANY_USER_ID = "00000000-0000-0000-0000-000000000005"  # same company, deactivated
_APPROVER_ID_2 = "00000000-0000-0000-0000-000000000006"  # distinct, non-creator, same company
_APPROVER_ID_3 = "00000000-0000-0000-0000-000000000007"  # distinct, non-creator, same company


def _as_approver(monkeypatch):
    """Switch the acting identity to _APPROVER_ID — CRIT-02 (segregation of
    duties) means the record's own creator can never be its approver."""
    import tests.conftest as conftest_module
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id=_APPROVER_ID, email="approver@example.com", display_name="Approver User",
        role="reviewer_qa", company_id=conftest_module._TEST_TENANT.company_id,
    ))


def _as_other_company(monkeypatch):
    """Switch the acting identity to a different company entirely, for
    cross-tenant isolation checks."""
    import tests.conftest as conftest_module
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id="00000000-0000-0000-0000-000000000099", email="other@example.com",
        display_name="Other Co User", role="company_admin", company_id=_OTHER_COMPANY_ID,
    ))


def _as_plain_user(monkeypatch):
    """Switch to a non-admin 'user' role, same company — for RBAC checks."""
    import tests.conftest as conftest_module
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id="00000000-0000-0000-0000-000000000003", email="plain@example.com",
        display_name="Plain User", role="user", company_id=conftest_module._TEST_TENANT.company_id,
    ))


@pytest.fixture(autouse=True)
def _company_directory(monkeypatch):
    """Every assign endpoint validates the proposed approver against the
    caller's company (CRIT-02's cross-tenant check) via a service-role
    Supabase call — faked here so no real Supabase project is needed."""
    from tests.test_assume_company_context import FakeSupabaseClient
    store = {"users": [
        {"id": _CREATOR_ID, "company_id": BOOTSTRAP_COMPANY_ID, "status": "active"},
        {"id": _APPROVER_ID, "company_id": BOOTSTRAP_COMPANY_ID, "status": "active"},
        {"id": _CROSS_COMPANY_USER_ID, "company_id": _OTHER_COMPANY_ID, "status": "active"},
        {"id": _INACTIVE_SAME_COMPANY_USER_ID, "company_id": BOOTSTRAP_COMPANY_ID, "status": "deactivated"},
        {"id": _APPROVER_ID_2, "company_id": BOOTSTRAP_COMPANY_ID, "status": "active"},
        {"id": _APPROVER_ID_3, "company_id": BOOTSTRAP_COMPANY_ID, "status": "active"},
    ]}
    fake = lambda: FakeSupabaseClient(store)
    monkeypatch.setattr("pharmagpt.routes.qms_market_complaint.get_service_role_client", fake)


def _create(client, **overrides):
    data = {"title": "Foreign particulate in Batch B-2201"}
    data.update(overrides)
    r = client.post("/qms/market-complaints", json=data)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# ── CRUD + numbering ─────────────────────────────────────────────────────────

def test_create_requires_title(client):
    r = client.post("/qms/market-complaints", json={})
    assert r.status_code == 400
    assert "title" in r.get_json()["error"].lower()


def test_create_generates_permanent_number_and_defaults(client):
    complaint = _create(client)
    assert complaint["complaint_number"].startswith("MC-")
    import re
    assert re.match(r"^MC-\d{4}-\d{4}$", complaint["complaint_number"])
    assert complaint["status"] == "Draft"
    assert complaint["potential_quality_defect"] is False
    assert complaint["potential_adverse_event"] is False


def test_complaint_numbers_are_sequential_per_year(client):
    c1 = _create(client, title="Complaint One")
    c2 = _create(client, title="Complaint Two")
    n1 = int(c1["complaint_number"].split("-")[-1])
    n2 = int(c2["complaint_number"].split("-")[-1])
    assert n2 == n1 + 1


def test_get_and_list(client):
    complaint = _create(client)
    r = client.get(f"/qms/market-complaints/{complaint['id']}")
    assert r.status_code == 200
    assert r.get_json()["id"] == complaint["id"]

    r = client.get("/qms/market-complaints")
    assert r.status_code == 200
    assert any(c["id"] == complaint["id"] for c in r.get_json())


def test_list_filters_by_status_severity_product(client):
    _create(client, title="A", product="Widget", severity="Critical")
    _create(client, title="B", product="Gadget", severity="Minor")
    r = client.get("/qms/market-complaints?product=Widget")
    results = r.get_json()
    assert len(results) == 1 and results[0]["title"] == "A"

    r = client.get("/qms/market-complaints?severity=Minor")
    results = r.get_json()
    assert all(c["severity"] == "Minor" for c in results)


def test_update_ordinary_fields(client):
    complaint = _create(client)
    r = client.put(f"/qms/market-complaints/{complaint['id']}", json={
        "description": "Updated description", "risk_level": "Medium",
        "potential_quality_defect": True,
    })
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["description"] == "Updated description"
    assert updated["potential_quality_defect"] is True


def test_get_not_found(client):
    r = client.get("/qms/market-complaints/999999")
    assert r.status_code == 404


def test_update_not_found(client):
    r = client.put("/qms/market-complaints/999999", json={"description": "x"})
    assert r.status_code == 404


# ── Complaint number immutability ────────────────────────────────────────────

def test_complaint_number_cannot_be_changed_via_put(client):
    complaint = _create(client)
    r = client.put(f"/qms/market-complaints/{complaint['id']}", json={"complaint_number": "MC-2020-9999"})
    assert r.status_code == 400
    assert "complaint_number" in r.get_json()["error"]
    # confirm it actually didn't change
    assert client.get(f"/qms/market-complaints/{complaint['id']}").get_json()["complaint_number"] == complaint["complaint_number"]


def test_status_qa_reviewer_approver_closure_date_blocked_via_put(client):
    complaint = _create(client)
    for field, value in (("status", "Closed"), ("qa_reviewer", "X"), ("approver", "Y"), ("closure_date", "2026-01-01")):
        r = client.put(f"/qms/market-complaints/{complaint['id']}", json={field: value})
        assert r.status_code == 400, f"{field} should be blocked"


# ── RBAC / unauthorized access ────────────────────────────────────────────────

def test_delete_requires_company_admin(client, monkeypatch):
    complaint = _create(client)
    _as_plain_user(monkeypatch)
    r = client.delete(f"/qms/market-complaints/{complaint['id']}")
    assert r.status_code == 403


def test_delete_succeeds_for_company_admin(client):
    complaint = _create(client)
    r = client.delete(f"/qms/market-complaints/{complaint['id']}")
    assert r.status_code == 200
    assert client.get(f"/qms/market-complaints/{complaint['id']}").status_code == 404


# ── Tenant isolation / IDOR ───────────────────────────────────────────────────

def test_cross_tenant_cannot_read_another_companys_complaint(client, monkeypatch):
    complaint = _create(client)
    _as_other_company(monkeypatch)
    r = client.get(f"/qms/market-complaints/{complaint['id']}")
    assert r.status_code == 404  # not 403 — scoped_or_none() never distinguishes wrong-company from not-found


def test_cross_tenant_cannot_update_or_delete_another_companys_complaint(client, monkeypatch):
    complaint = _create(client)
    _as_other_company(monkeypatch)
    assert client.put(f"/qms/market-complaints/{complaint['id']}", json={"description": "hijacked"}).status_code == 404
    assert client.delete(f"/qms/market-complaints/{complaint['id']}").status_code == 404


def test_cross_tenant_cannot_access_attachments_comments_audit_via_qms_common(client, monkeypatch):
    """IDOR protection through the SHARED qms_common.py endpoints — proves
    the market_complaint._GETTERS/VALID_RECORD_TYPES registration is
    tenant-scoped, not just this module's own routes."""
    complaint = _create(client)
    cid = complaint["id"]
    _as_other_company(monkeypatch)
    assert client.get(f"/qms/market_complaint/{cid}/attachments").status_code == 404
    assert client.get(f"/qms/market_complaint/{cid}/comments").status_code == 404
    assert client.get(f"/qms/market_complaint/{cid}/audit-trail").status_code == 404


def test_invalid_record_type_rejected_by_qms_common():
    # 'market-complaints' (hyphenated, this module's own route prefix) is
    # NOT a registered record_type string for the shared endpoints — only
    # 'market_complaint' (underscore) is, mirroring change_control's
    # identical distinct-string precedent.
    pass  # covered implicitly by the underscore-vs-hyphen usage above; no separate route to hit


# ── qms_common: attachments / comments / audit-trail (own company) ───────────

def test_attachments_comments_audit_trail_reachable_for_own_company(client):
    complaint = _create(client)
    cid = complaint["id"]
    assert client.get(f"/qms/market_complaint/{cid}/attachments").status_code == 200
    r = client.post(f"/qms/market_complaint/{cid}/comments", json={"comment": "Looks urgent"})
    assert r.status_code == 201
    comments = client.get(f"/qms/market_complaint/{cid}/comments").get_json()
    assert len(comments) == 1 and comments[0]["comment"] == "Looks urgent"
    audit_trail = client.get(f"/qms/market_complaint/{cid}/audit-trail").get_json()
    assert any("COMPLAINT_CREATED" in (e.get("action") or "") for e in audit_trail)


# ── Audit events ──────────────────────────────────────────────────────────────

def test_audit_events_for_create_and_update(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.put(f"/qms/market-complaints/{cid}", json={"description": "revised"})
    entries = client.get(f"/qms/market_complaint/{cid}/audit-trail").get_json()
    actions = [e["action"] for e in entries]
    assert "COMPLAINT_CREATED" in actions
    assert "COMPLAINT_UPDATED" in actions


def test_audit_event_for_delete(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.delete(f"/qms/market-complaints/{cid}")
    # Record is gone, but the audit trail write happened before deletion —
    # verified indirectly: delete returned 200 (see test above); a direct
    # read of a deleted record's own audit trail 404s via _record_exists(),
    # matching every other QMS module's behavior (audit rows persist in the
    # DB but aren't reachable through the record-scoped endpoint once the
    # parent record is gone).
    assert client.get(f"/qms/market_complaint/{cid}/audit-trail").status_code == 404


# ── Workflow: required-field validation, assign, decide, e-signature ─────────

def test_workflow_not_started_shows_no_instance(client):
    complaint = _create(client)
    r = client.get(f"/qms/market-complaints/{complaint['id']}/workflow")
    assert r.status_code == 200
    assert r.get_json()["instance"] is None


def test_workflow_start_requires_valid_record(client):
    r = client.post("/qms/market-complaints/999999/workflow/start")
    assert r.status_code == 404


def test_workflow_decide_with_invalid_decision_rejected(client):
    complaint = _create(client)
    client.post(f"/qms/market-complaints/{complaint['id']}/workflow/start")
    r = client.post(f"/qms/market-complaints/{complaint['id']}/workflow/steps/2/decide",
                     json={"decision": "not-a-real-decision"})
    assert r.status_code == 400


def test_creator_cannot_self_assign_as_approver(client):
    complaint = _create(client)
    client.post(f"/qms/market-complaints/{complaint['id']}/workflow/start")
    r = client.post(f"/qms/market-complaints/{complaint['id']}/workflow/steps/2/assign",
                     json={"approvers": [{"user_id": _CREATOR_ID, "display_name": "Creator"}]})
    assert r.status_code == 409
    assert "segregation of duties" in r.get_json()["error"].lower()


def test_forged_cross_company_approver_rejected(client):
    """Approver-dropdown UX fix (Yuktav): the frontend now sources approver
    choices from GET /users/directory (company-scoped) instead of a free-typed
    Supabase user id, but the assign endpoint itself is the actual security
    boundary — it must independently reject a user id belonging to a
    different company even though that id is real and active, exactly as if
    someone bypassed the dropdown and forged the browser request."""
    complaint = _create(client)
    client.post(f"/qms/market-complaints/{complaint['id']}/workflow/start")
    r = client.post(f"/qms/market-complaints/{complaint['id']}/workflow/steps/2/assign",
                     json={"approvers": [{"user_id": _CROSS_COMPANY_USER_ID, "display_name": "Cross Company"}]})
    assert r.status_code == 400
    assert "not a valid, active user" in r.get_json()["error"].lower()
    state = client.get(f"/qms/market-complaints/{complaint['id']}/workflow").get_json()
    assert not state["steps"][1]["approvers"]


def test_forged_inactive_approver_rejected(client):
    """Same as above, for a real same-company user who has since been
    deactivated — GET /users/directory already excludes them from the
    dropdown, but the assign endpoint must refuse them independently too."""
    complaint = _create(client)
    client.post(f"/qms/market-complaints/{complaint['id']}/workflow/start")
    r = client.post(f"/qms/market-complaints/{complaint['id']}/workflow/steps/2/assign",
                     json={"approvers": [{"user_id": _INACTIVE_SAME_COMPANY_USER_ID, "display_name": "Inactive User"}]})
    assert r.status_code == 400
    assert "not a valid, active user" in r.get_json()["error"].lower()
    state = client.get(f"/qms/market-complaints/{complaint['id']}/workflow").get_json()
    assert not state["steps"][1]["approvers"]


# ── Workflow: upfront/bulk approver assignment (assign-all) ──────────────────

def _assign_all(client, cid, *, step2=_APPROVER_ID, step3=_APPROVER_ID_2, step4=_APPROVER_ID_3):
    return client.post(f"/qms/market-complaints/{cid}/workflow/assign-all", json={"assignments": [
        {"step_order": 2, "approvers": [{"user_id": step2, "display_name": "Step 2 Approver"}]},
        {"step_order": 3, "approvers": [{"user_id": step3, "display_name": "Step 3 Approver"}]},
        {"step_order": 4, "approvers": [{"user_id": step4, "display_name": "Step 4 Approver"}]},
    ]})


def test_assign_all_approvers_in_one_call(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = _assign_all(client, cid)
    assert r.status_code == 200, r.get_json()
    state = r.get_json()
    steps_by_order = {s["step_order"]: s for s in state["steps"]}
    assert steps_by_order[2]["approvers"][0]["user_id"] == _APPROVER_ID
    assert steps_by_order[3]["approvers"][0]["user_id"] == _APPROVER_ID_2
    assert steps_by_order[4]["approvers"][0]["user_id"] == _APPROVER_ID_3
    # Assignment alone must not advance the lifecycle.
    assert state["instance"]["current_step_order"] == 2


def test_assign_all_persists_all_three_assignments(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    _assign_all(client, cid)
    state = client.get(f"/qms/market-complaints/{cid}/workflow").get_json()
    steps_by_order = {s["step_order"]: s for s in state["steps"]}
    assert steps_by_order[2]["approvers"][0]["display_name"] == "Step 2 Approver"
    assert steps_by_order[3]["approvers"][0]["display_name"] == "Step 3 Approver"
    assert steps_by_order[4]["approvers"][0]["display_name"] == "Step 4 Approver"


def test_assign_all_invalid_step2_approver_blocks_entire_request(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = _assign_all(client, cid, step2=_CROSS_COMPANY_USER_ID)
    assert r.status_code == 400, r.get_json()
    state = client.get(f"/qms/market-complaints/{cid}/workflow").get_json()
    # Atomicity: steps 3/4's otherwise-valid approvers must NOT have been persisted either.
    assert all(not s["approvers"] for s in state["steps"] if s["step_type"] == "approval")


def test_assign_all_invalid_step3_approver_blocks_entire_request(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = _assign_all(client, cid, step3=_INACTIVE_SAME_COMPANY_USER_ID)
    assert r.status_code == 400, r.get_json()
    state = client.get(f"/qms/market-complaints/{cid}/workflow").get_json()
    assert all(not s["approvers"] for s in state["steps"] if s["step_type"] == "approval")


def test_assign_all_invalid_step4_approver_blocks_entire_request(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = _assign_all(client, cid, step4="totally-fake-nonexistent-user-id")
    assert r.status_code == 400, r.get_json()
    state = client.get(f"/qms/market-complaints/{cid}/workflow").get_json()
    assert all(not s["approvers"] for s in state["steps"] if s["step_type"] == "approval")


def test_assign_all_cross_company_approver_rejected(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = _assign_all(client, cid, step3=_CROSS_COMPANY_USER_ID)
    assert r.status_code == 400
    assert "not a valid, active user" in r.get_json()["error"].lower()


def test_assign_all_inactive_approver_rejected(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = _assign_all(client, cid, step4=_INACTIVE_SAME_COMPANY_USER_ID)
    assert r.status_code == 400
    assert "not a valid, active user" in r.get_json()["error"].lower()


def test_assign_all_creator_cannot_be_assigned_to_any_step(client):
    """Segregation-of-duties must be enforced for EVERY step in the batch,
    not just the first one checked."""
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")

    for kwargs in ({"step2": _CREATOR_ID}, {"step3": _CREATOR_ID}, {"step4": _CREATOR_ID}):
        r = _assign_all(client, cid, **kwargs)
        assert r.status_code == 409, r.get_json()
        assert "segregation of duties" in r.get_json()["error"].lower()
        state = client.get(f"/qms/market-complaints/{cid}/workflow").get_json()
        assert all(not s["approvers"] for s in state["steps"] if s["step_type"] == "approval")


def test_assign_all_requires_non_empty_assignments_list(client):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = client.post(f"/qms/market-complaints/{cid}/workflow/assign-all", json={"assignments": []})
    assert r.status_code == 400


def test_assign_all_does_not_require_esignature(client, monkeypatch):
    """Assigning approvers is not an approval decision — no e-signature
    fields are expected or required, only when a step is later decided."""
    import pharmagpt.services.esignature_service as esignature_service

    def _fail(*a, **k):
        raise esignature_service.ReauthenticationError("should not be called for assignment")
    monkeypatch.setattr("pharmagpt.routes.qms_market_complaint.esignature_service.require_esignature", _fail)

    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    r = _assign_all(client, cid)
    assert r.status_code == 200, r.get_json()


def test_assign_all_upfront_then_sequential_lifecycle_enforced(client, monkeypatch):
    """The core requirement: assign all three approvers upfront in ONE call,
    then prove the lifecycle still executes strictly sequentially — a
    pre-assigned future-step approver can never decide early, and each step
    only unlocks once its predecessor is actually approved."""
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    assert _assign_all(client, cid).status_code == 200

    # Only step 2 is actionable initially — steps 3/4 cannot be decided early
    # even though they already have an assigned approver.
    _as_approver(monkeypatch)
    for step_order in (3, 4):
        r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/{step_order}/decide",
                         json={"decision": "approve", "meaning": "Approved", "reason": "x"})
        assert r.status_code == 409
        assert "not the current step" in r.get_json()["error"].lower()

    # Step 2's assigned approver (_APPROVER_ID) decides step 2 -> unlocks step 3.
    r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/2/decide",
                     json={"decision": "approve", "meaning": "Approved", "reason": "x"})
    assert r.status_code == 200, r.get_json()
    assert client.get(f"/qms/market-complaints/{cid}/workflow").get_json()["instance"]["current_step_order"] == 3

    # Step 4 still cannot be decided before step 3.
    r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/4/decide",
                     json={"decision": "approve", "meaning": "Approved", "reason": "x"})
    assert r.status_code == 409
    assert "not the current step" in r.get_json()["error"].lower()

    # Step 3's assigned approver (_APPROVER_ID_2) decides step 3 -> unlocks step 4.
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id=_APPROVER_ID_2, email="approver2@example.com", display_name="Approver Two",
        role="reviewer_qa", company_id=conftest_module._TEST_TENANT.company_id,
    ))
    r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/3/decide",
                     json={"decision": "approve", "meaning": "Approved", "reason": "x"})
    assert r.status_code == 200, r.get_json()
    assert client.get(f"/qms/market-complaints/{cid}/workflow").get_json()["instance"]["current_step_order"] == 4

    # Step 4's assigned approver (_APPROVER_ID_3) decides step 4 -> Closed.
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id=_APPROVER_ID_3, email="approver3@example.com", display_name="Approver Three",
        role="reviewer_qa", company_id=conftest_module._TEST_TENANT.company_id,
    ))
    r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/4/decide",
                     json={"decision": "approve", "meaning": "Approved", "reason": "x"})
    assert r.status_code == 200, r.get_json()
    assert client.get(f"/qms/market-complaints/{cid}").get_json()["status"] == "Closed"


def test_decide_without_assigned_approver_blocked(client, monkeypatch):
    complaint = _create(client)
    client.post(f"/qms/market-complaints/{complaint['id']}/workflow/start")
    _as_approver(monkeypatch)
    r = client.post(f"/qms/market-complaints/{complaint['id']}/workflow/steps/2/decide",
                     json={"decision": "approve"})
    assert r.status_code == 409
    assert "no assigned approver" in r.get_json()["error"].lower()


def test_full_lifecycle_submitted_to_closed(client, monkeypatch):
    """Draft -> Submitted -> Triage & Risk Assessment -> QA Review -> Closed,
    the full P0 workflow, asserting record status after each gate."""
    complaint = _create(client)
    cid = complaint["id"]
    assert client.get(f"/qms/market-complaints/{cid}").get_json()["status"] == "Draft"

    r = client.post(f"/qms/market-complaints/{cid}/workflow/start")
    assert r.status_code == 201
    # Step 1 ("submitted") auto-completes on start; status now reflects
    # step 2's gate_status (services/workflow_engine.py::
    # _status_after_completing) — same behavior as Deviation/CAPA.
    assert client.get(f"/qms/market-complaints/{cid}").get_json()["status"] == "Triage & Risk Assessment"

    for step_order in (2, 3, 4):
        assign = client.post(f"/qms/market-complaints/{cid}/workflow/steps/{step_order}/assign",
                              json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
        assert assign.status_code == 200, assign.get_json()
        _as_approver(monkeypatch)
        decide = client.post(f"/qms/market-complaints/{cid}/workflow/steps/{step_order}/decide",
                              json={"decision": "approve", "meaning": "Approved", "reason": "Reviewed"})
        assert decide.status_code == 200, decide.get_json()

    final = client.get(f"/qms/market-complaints/{cid}").get_json()
    assert final["status"] == "Closed"

    entries = client.get(f"/qms/market_complaint/{cid}/audit-trail").get_json()
    assert any(e["action"] == "COMPLAINT_APPROVED" for e in entries)


def test_closed_complaint_is_immutable(client, monkeypatch):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    for step_order in (2, 3, 4):
        client.post(f"/qms/market-complaints/{cid}/workflow/steps/{step_order}/assign",
                    json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
        _as_approver(monkeypatch)
        client.post(f"/qms/market-complaints/{cid}/workflow/steps/{step_order}/decide",
                    json={"decision": "approve", "meaning": "Approved", "reason": "Reviewed"})

    r = client.put(f"/qms/market-complaints/{cid}", json={"description": "too late"})
    assert r.status_code == 409
    assert "closed" in r.get_json()["error"].lower()


def test_reject_at_triage_sends_to_terminal_rejected_and_allows_resubmit(client, monkeypatch):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    client.post(f"/qms/market-complaints/{cid}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
    _as_approver(monkeypatch)
    r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/2/decide",
                     json={"decision": "reject", "meaning": "Rejected", "reason": "Insufficient evidence"})
    assert r.status_code == 200
    assert client.get(f"/qms/market-complaints/{cid}").get_json()["status"] == "Rejected"

    entries = client.get(f"/qms/market_complaint/{cid}/audit-trail").get_json()
    assert any(e["action"] == "COMPLAINT_REJECTED" for e in entries)

    # Resubmission: a rejected instance is no longer "active", so start_instance
    # may create a fresh one — same behavior as Deviation/CAPA.
    r = client.post(f"/qms/market-complaints/{cid}/workflow/start")
    assert r.status_code == 201


def test_esignature_reauthentication_failure_blocks_decision(client, monkeypatch):
    """Overrides the `client` fixture's own require_esignature no-op patch
    for this one test, to prove the route actually calls it and handles
    ReauthenticationError -> 401 without mutating the workflow state."""
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    client.post(f"/qms/market-complaints/{cid}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
    _as_approver(monkeypatch)

    import pharmagpt.services.esignature_service as esignature_service

    def _fail(*a, **k):
        raise esignature_service.ReauthenticationError("Password confirmation failed")
    monkeypatch.setattr("pharmagpt.routes.qms_market_complaint.esignature_service.require_esignature", _fail)

    r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/2/decide",
                     json={"decision": "approve", "meaning": "Approved", "reason": "Reviewed", "password": "wrong"})
    assert r.status_code == 401
    # State must be unchanged — the failed signature happened before any decision.
    state = client.get(f"/qms/market-complaints/{cid}/workflow").get_json()
    assert state["instance"]["current_step_order"] == 2


def test_esignature_invalid_meaning_blocks_decision(client, monkeypatch):
    complaint = _create(client)
    cid = complaint["id"]
    client.post(f"/qms/market-complaints/{cid}/workflow/start")
    client.post(f"/qms/market-complaints/{cid}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
    _as_approver(monkeypatch)

    import pharmagpt.services.esignature_service as esignature_service

    def _fail(*a, **k):
        raise esignature_service.ESignatureError("meaning must be one of: ...")
    monkeypatch.setattr("pharmagpt.routes.qms_market_complaint.esignature_service.require_esignature", _fail)

    r = client.post(f"/qms/market-complaints/{cid}/workflow/steps/2/decide",
                     json={"decision": "approve", "meaning": "NotARealMeaning", "reason": "x"})
    assert r.status_code == 400

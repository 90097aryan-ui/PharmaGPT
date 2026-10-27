"""
tests/test_crit02_segregation_of_duties.py — Regression coverage for
CRIT-02 (PharmaGPT Security Audit, Stage 2 remediation, Wave 1):
segregation of duties / self-approval on CAPA, Change Control, and
Deviations.

Before this fix, a record's own creator could assign themselves as the
named approver for their own CAPA/Change Control workflow step (Deviations'
equivalent: the Workflow Builder), then approve it — no server-side check
compared the proposed approver against the record's creator. Documents
already had a correct, separately-implemented fix for this (routes/
qms_documents.py::set_review_chain_route) and is intentionally NOT touched
or re-tested here (Stage 2: NOT CONFIRMED vulnerable for Documents).

Enforcement is layered:
  1. services/workflow_engine.py::assign_approvers() — the shared boundary
     CAPA and Change Control's assign endpoints route through — refuses the
     record's own creator via reject_creator_as_approver() (layer B).
  2. routes/qms_deviations.py::update_workflow_builder — Deviations doesn't
     route through assign_approvers(), so it calls reject_creator_as_approver()
     directly (layer A, the only layer for this module).
  3. All three routes additionally reject a proposed approver who isn't a
     real, active user of the caller's own company (cross-tenant check,
     tenancy.missing_or_inactive_users).

Default `client` fixture identity is the fixed test tenant (role=
company_admin) — every record below is created by it, so it is the
CREATOR throughout.
"""

import pytest

from pharmagpt.auth.context import TenantContext
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID

_CREATOR_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py::_TEST_TENANT.user_id
_APPROVER_ID = "00000000-0000-0000-0000-000000000002"  # distinct, non-creator, same company
_OTHER_COMPANY_USER_ID = "00000000-0000-0000-0000-000000000099"  # valid user, but a different company


@pytest.fixture(autouse=True)
def _company_directory(monkeypatch):
    """Every assign endpoint under test validates the proposed approver
    against the caller's company (CRIT-02's cross-tenant check) via a
    service-role Supabase call — faked here so no real Supabase project is
    needed. _OTHER_COMPANY_USER_ID is deliberately a DIFFERENT company_id."""
    from tests.test_assume_company_context import FakeSupabaseClient
    store = {"users": [
        {"id": _CREATOR_ID, "company_id": BOOTSTRAP_COMPANY_ID, "status": "active"},
        {"id": _APPROVER_ID, "company_id": BOOTSTRAP_COMPANY_ID, "status": "active"},
        {"id": _OTHER_COMPANY_USER_ID, "company_id": "some-other-company-id", "status": "active"},
    ]}
    fake = lambda: FakeSupabaseClient(store)
    monkeypatch.setattr("pharmagpt.routes.qms_capa.get_service_role_client", fake)
    monkeypatch.setattr("pharmagpt.routes.qms_change_control.get_service_role_client", fake)
    monkeypatch.setattr("pharmagpt.routes.qms_deviations.get_service_role_client", fake)


def _as_approver(monkeypatch):
    import tests.conftest as conftest_module
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id=_APPROVER_ID, email="approver@example.com", display_name="Approver User",
        role="reviewer_qa", company_id=conftest_module._TEST_TENANT.company_id,
    ))


# ── CAPA ──────────────────────────────────────────────────────────────────────

# CAPA_WORKFLOW_V1 (qms_database.py): steps 1-5 are role-eligible 'activity'
# steps (no named-approver concept — assign_approvers() itself refuses
# them, "does not take named approvers"); step 6 ("Effectiveness Check") is
# the first 'approval' step, so that's what these assign-focused tests
# target. assign_approvers() doesn't require the step to be the workflow's
# *current* step (only decide_step does), so no need to decide steps 1-5
# first just to exercise assignment.

def test_capa_creator_cannot_self_assign_as_approver(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]
    client.post(f"/qms/capa/{cid}/workflow/start")

    r = client.post(f"/qms/capa/{cid}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _CREATOR_ID, "display_name": "Creator"}]})
    assert r.status_code == 409
    assert "segregation of duties" in r.get_json()["error"].lower()


def test_capa_cross_tenant_user_cannot_be_assigned_as_approver(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]
    client.post(f"/qms/capa/{cid}/workflow/start")

    r = client.post(f"/qms/capa/{cid}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _OTHER_COMPANY_USER_ID, "display_name": "Foreign User"}]})
    assert r.status_code == 400
    assert _OTHER_COMPANY_USER_ID in r.get_json()["error"]


def test_capa_authorized_non_creator_approver_can_be_assigned(client):
    """Full assign-then-decide-to-Closed coverage for a non-creator
    approver already exists end-to-end in tests/test_qms_routes.py::
    test_capa_approval_status_map (steps through the mandatory
    Effectiveness Verification gate too) — this test isolates just the
    assignment call CRIT-02 actually changed."""
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]
    client.post(f"/qms/capa/{cid}/workflow/start")

    r = client.post(f"/qms/capa/{cid}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["steps"][5]["approvers"][0]["user_id"] == _APPROVER_ID


def test_capa_creator_cannot_self_assign_even_after_another_approver_is_named(client):
    """Defense-in-depth: the creator is refused as an approver regardless of
    whether the step already has a different, valid approver assigned."""
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]
    client.post(f"/qms/capa/{cid}/workflow/start")
    client.post(f"/qms/capa/{cid}/workflow/steps/6/assign",
                json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})

    r = client.post(f"/qms/capa/{cid}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _CREATOR_ID, "display_name": "Creator"}]})
    assert r.status_code == 409
    assert "segregation of duties" in r.get_json()["error"].lower()


# ── Change Control ────────────────────────────────────────────────────────────

# CHANGE_CONTROL_WORKFLOW_V1: steps 1-5 are role-eligible 'activity' steps
# (no named-approver concept); step 6 ("QA Review") is the first 'approval'
# step and — unlike CAPA's step 6 — has no dedicated-endpoint special case,
# so it can be decided through the plain generic decide endpoint once it's
# the current step.

def test_change_control_creator_cannot_self_assign_as_approver(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    cc_id = cc["id"]
    client.post(f"/qms/change-control/{cc_id}/workflow/start")

    r = client.post(f"/qms/change-control/{cc_id}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _CREATOR_ID, "display_name": "Creator"}]})
    assert r.status_code == 409
    assert "segregation of duties" in r.get_json()["error"].lower()


def test_change_control_cross_tenant_user_cannot_be_assigned_as_approver(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    cc_id = cc["id"]
    client.post(f"/qms/change-control/{cc_id}/workflow/start")

    r = client.post(f"/qms/change-control/{cc_id}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _OTHER_COMPANY_USER_ID, "display_name": "Foreign User"}]})
    assert r.status_code == 400
    assert _OTHER_COMPANY_USER_ID in r.get_json()["error"]


def test_change_control_authorized_non_creator_approver_can_be_assigned_and_can_approve(client, monkeypatch):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    cc_id = cc["id"]
    client.post(f"/qms/change-control/{cc_id}/workflow/start")  # auto-completes step 1 ("Submitted")

    # Advance steps 2-5 (plain role-eligible activity, creator is fine) to
    # reach step 6 ("QA Review", approval) as the current step.
    for step_order in range(2, 6):
        r = client.post(f"/qms/change-control/{cc_id}/workflow/steps/{step_order}/decide",
                         json={"decision": "advance"})
        assert r.status_code == 200, r.get_json()

    r = client.post(f"/qms/change-control/{cc_id}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
    assert r.status_code == 200, r.get_json()

    _as_approver(monkeypatch)
    r = client.post(f"/qms/change-control/{cc_id}/workflow/steps/6/decide", json={"decision": "approve"})
    assert r.status_code == 200, r.get_json()


def test_change_control_creator_remains_unable_to_decide_a_step_assigned_to_someone_else(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    cc_id = cc["id"]
    client.post(f"/qms/change-control/{cc_id}/workflow/start")  # auto-completes step 1 ("Submitted")
    client.post(f"/qms/change-control/{cc_id}/workflow/steps/6/assign",
                json={"approvers": [{"user_id": _APPROVER_ID, "display_name": "Approver User"}]})
    for step_order in range(2, 6):
        client.post(f"/qms/change-control/{cc_id}/workflow/steps/{step_order}/decide",
                    json={"decision": "advance"})

    # Step 6 already has a named approver (_APPROVER_ID, assigned above,
    # before it became current) — the creator, not being that named
    # approver, is rejected for the ordinary identity reason.
    r = client.post(f"/qms/change-control/{cc_id}/workflow/steps/6/decide", json={"decision": "approve"})
    assert r.status_code == 403


# ── Deviations (Workflow Builder — no runtime assign endpoint) ───────────────

def _deviation_builder_payload(user_id, display_name):
    return {
        "steps": [
            {"step_name": "Production Head", "department": "Production",
             "approver_user_id": user_id, "approver_display_name": display_name},
        ],
        "capa_phase": {
            "qa_review_approver_user_id": user_id, "qa_review_approver_display_name": display_name,
            "final_approval_approver_user_id": user_id, "final_approval_approver_display_name": display_name,
        },
    }


def test_deviation_creator_cannot_self_assign_via_workflow_builder(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]

    r = client.put(f"/qms/deviations/{did}/workflow-builder",
                    json=_deviation_builder_payload(_CREATOR_ID, "Creator"))
    assert r.status_code == 409
    assert "segregation of duties" in r.get_json()["error"].lower()


def test_deviation_cross_tenant_user_cannot_be_assigned_via_workflow_builder(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]

    r = client.put(f"/qms/deviations/{did}/workflow-builder",
                    json=_deviation_builder_payload(_OTHER_COMPANY_USER_ID, "Foreign User"))
    assert r.status_code == 400
    assert _OTHER_COMPANY_USER_ID in r.get_json()["error"]


def test_deviation_authorized_non_creator_approver_can_be_assigned_and_can_approve(client, monkeypatch):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]

    r = client.put(f"/qms/deviations/{did}/workflow-builder",
                    json=_deviation_builder_payload(_APPROVER_ID, "Approver User"))
    assert r.status_code == 200, r.get_json()

    r = client.post(f"/qms/deviations/{did}/workflow/start")
    assert r.status_code == 201, r.get_json()

    _as_approver(monkeypatch)
    r = client.post(f"/qms/deviations/{did}/workflow/steps/2/decide", json={"decision": "approve"})
    assert r.status_code == 200, r.get_json()


def test_deviation_creator_remains_unable_to_decide_step_assigned_to_another(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]
    client.put(f"/qms/deviations/{did}/workflow-builder",
               json=_deviation_builder_payload(_APPROVER_ID, "Approver User"))
    client.post(f"/qms/deviations/{did}/workflow/start")

    r = client.post(f"/qms/deviations/{did}/workflow/steps/2/decide", json={"decision": "approve"})
    assert r.status_code == 403


# ── Legacy / no-captured-creator records — the check is a documented no-op ──

def test_legacy_capa_with_no_captured_creator_allows_any_assignment(db_path, client):
    """A CAPA row created directly at the repository layer (bypassing the
    route, e.g. simulating a pre-CRIT-02 record) has no created_by_user_id
    — reject_creator_as_approver() must not retroactively block it."""
    from pharmagpt import qms_capa_database as cdb
    legacy = cdb.create_capa({"title": "Legacy CAPA"}, company_id=BOOTSTRAP_COMPANY_ID)
    assert legacy.get("created_by_user_id", "") == ""

    r = client.post(f"/qms/capa/{legacy['id']}/workflow/start")
    assert r.status_code == 201, r.get_json()
    r = client.post(f"/qms/capa/{legacy['id']}/workflow/steps/6/assign",
                     json={"approvers": [{"user_id": _CREATOR_ID, "display_name": "Anyone"}]})
    assert r.status_code == 200, r.get_json()


# ── Repository/engine-layer direct proof — independent of any route ─────────

def test_reject_creator_as_approver_blocks_matching_creator(db_path):
    from pharmagpt import qms_capa_database as cdb
    from pharmagpt.services import workflow_engine as wfe

    capa = cdb.create_capa({"title": "CAPA"}, company_id=BOOTSTRAP_COMPANY_ID,
                           created_by_user_id=_CREATOR_ID, created_by_display_name="Creator")
    with pytest.raises(wfe.WorkflowError, match="segregation of duties"):
        wfe.reject_creator_as_approver("capa", capa["id"], [{"user_id": _CREATOR_ID}])


def test_reject_creator_as_approver_allows_a_different_user(db_path):
    from pharmagpt import qms_capa_database as cdb
    from pharmagpt.services import workflow_engine as wfe

    capa = cdb.create_capa({"title": "CAPA"}, company_id=BOOTSTRAP_COMPANY_ID,
                           created_by_user_id=_CREATOR_ID, created_by_display_name="Creator")
    wfe.reject_creator_as_approver("capa", capa["id"], [{"user_id": _APPROVER_ID}])  # must not raise


def test_reject_creator_as_approver_is_noop_for_record_with_no_captured_creator(db_path):
    from pharmagpt import qms_capa_database as cdb
    from pharmagpt.services import workflow_engine as wfe

    capa = cdb.create_capa({"title": "CAPA"}, company_id=BOOTSTRAP_COMPANY_ID)  # no created_by_user_id
    wfe.reject_creator_as_approver("capa", capa["id"], [{"user_id": _CREATOR_ID}])  # must not raise

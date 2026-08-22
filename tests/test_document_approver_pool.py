"""
tests/test_document_approver_pool.py — Phase 3 coverage: the configurable
approver pool (Department Head + Quality Head/Designee mandatory, Plant
Head optional, fixed required quorum = 2), and quorum scoped to the final
Approval stage only (Review stays single-reviewer).

Engine/DB-level tests exercise qms_document_database.py directly, same
style as tests/test_quorum_approval.py. Route-level tests use the `client`
fixture (tests/conftest.py — company_admin role, BOOTSTRAP_COMPANY_ID tenant).
"""

import io

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_workflow_database as wfdb
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


# ── Pool CRUD ──────────────────────────────────────────────────────────────

def test_set_and_get_pool_member(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana Head")
    pool = qdb.get_approver_pool(COMPANY_ID, "")
    assert {p["pool_role"]: p["user_id"] for p in pool} == {"department_head": "dh-1"}


def test_set_pool_member_upserts(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn Head")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-2", "Quinn Head II")
    pool = qdb.get_approver_pool(COMPANY_ID, "")
    assert next(p for p in pool if p["pool_role"] == "quality_head")["user_id"] == "qh-2"


def test_department_specific_overrides_company_default(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "default-dh", "Default DH")
    qdb.set_approver_pool_member(COMPANY_ID, "QA", "department_head", "qa-dh", "QA-specific DH")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "default-qh", "Default QH")

    qa_pool = qdb.get_approver_pool(COMPANY_ID, "QA")
    by_role = {p["pool_role"]: p["user_id"] for p in qa_pool}
    assert by_role["department_head"] == "qa-dh"      # department-specific wins
    assert by_role["quality_head"] == "default-qh"    # falls back to company default


def test_deactivated_member_excluded(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "plant_head", "ph-1", "Pat Head")
    qdb.deactivate_approver_pool_member(COMPANY_ID, "", "plant_head")
    pool = qdb.get_approver_pool(COMPANY_ID, "")
    assert "plant_head" not in {p["pool_role"] for p in pool}


# ── resolve_pool_approvers: mandatory vs optional ─────────────────────────────

def test_resolve_raises_when_department_head_missing(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn")
    with pytest.raises(ValueError, match="department_head"):
        qdb.resolve_pool_approvers({"company_id": COMPANY_ID, "department": ""})


def test_resolve_raises_when_quality_head_missing(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana")
    with pytest.raises(ValueError, match="quality_head"):
        qdb.resolve_pool_approvers({"company_id": COMPANY_ID, "department": ""})


def test_resolve_succeeds_2_of_2_without_plant_head(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn")
    approvers = qdb.resolve_pool_approvers({"company_id": COMPANY_ID, "department": ""})
    assert {a["pool_role"] for a in approvers} == {"department_head", "quality_head"}
    assert len(approvers) == 2


def test_resolve_includes_plant_head_when_configured(db_path):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn")
    qdb.set_approver_pool_member(COMPANY_ID, "", "plant_head", "ph-1", "Pat")
    approvers = qdb.resolve_pool_approvers({"company_id": COMPANY_ID, "department": ""})
    assert {a["pool_role"] for a in approvers} == {"department_head", "quality_head", "plant_head"}
    assert len(approvers) == 3
    assert qdb.APPROVAL_QUORUM_REQUIRED == 2  # fixed regardless of 2-of-2 vs 2-of-3


# ── quorum_eligible: Review stays single-reviewer, only Approval is quorum-gated ──

def _make_document():
    return qdb.create_document({"title": "Cleaning SOP"}, company_id=COMPANY_ID)


def test_review_step_never_becomes_quorum_mode(db_path):
    doc = _make_document()
    state = wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID,
                                "Ada Author", default_quorum=3)
    step2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step2["approval_mode"] == "any"
    assert step2["required_quorum"] is None


def test_approval_step_becomes_quorum_mode(db_path):
    doc = _make_document()
    state = wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID,
                                "Ada Author", default_quorum=2)
    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["approval_mode"] == "quorum"
    assert step3["required_quorum"] == 2


def test_review_single_reviewer_approve_advances_even_with_quorum_override(db_path):
    """With quorum_eligible=0 on step 2, a document-level quorum override no
    longer blocks a single reviewer from advancing Review — this is the
    concrete behavioural difference from Phase 2 (where the same setup
    required two reviewers on step 2 too)."""
    doc = _make_document()
    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID,
                        "Ada Author", default_quorum=2)
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": "rev-1", "display_name": "Rita"}])
    state = wfe.decide_step("document", doc["id"], 2, "approve", user_id="rev-1", role="reviewer_qa",
                             performed_by="Rita")
    assert state["instance"]["current_step_order"] == 3


# ── Route-level: pool auto-assignment on workflow start ──────────────────────

def test_start_workflow_auto_assigns_pool_approvers_with_quorum_2(client):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana Head")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn Head")

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")  # Phase 5 hard gate
    client.post(
        f"/qms/documents/{doc['id']}/versions/upload",
        data={"file": (io.BytesIO(b"final content"), "final.txt")},
        content_type="multipart/form-data",
    )
    state = client.post(f"/qms/documents/{doc['id']}/workflow/start").get_json()

    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["approval_mode"] == "quorum"
    assert step3["required_quorum"] == 2
    approver_ids = {a["user_id"] for a in step3["approvers"]}
    assert approver_ids == {"dh-1", "qh-1"}


def test_start_workflow_includes_plant_head_but_quorum_stays_2(client):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana Head")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn Head")
    qdb.set_approver_pool_member(COMPANY_ID, "", "plant_head", "ph-1", "Pat Head")

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")  # Phase 5 hard gate
    client.post(
        f"/qms/documents/{doc['id']}/versions/upload",
        data={"file": (io.BytesIO(b"final content"), "final.txt")},
        content_type="multipart/form-data",
    )
    state = client.post(f"/qms/documents/{doc['id']}/workflow/start").get_json()

    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["required_quorum"] == 2
    approver_ids = {a["user_id"] for a in step3["approvers"]}
    assert approver_ids == {"dh-1", "qh-1", "ph-1"}


def test_start_workflow_falls_back_to_manual_quorum_when_pool_unconfigured(client):
    """No pool configured at all — falls back to the pre-Phase-3 behaviour
    (approval_quorum field, or 'any' mode if that's also unset). Confirms
    backward compatibility for a company that hasn't set up a pool yet."""
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")  # Phase 5 hard gate
    client.post(
        f"/qms/documents/{doc['id']}/versions/upload",
        data={"file": (io.BytesIO(b"final content"), "final.txt")},
        content_type="multipart/form-data",
    )
    state = client.post(f"/qms/documents/{doc['id']}/workflow/start").get_json()

    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["approval_mode"] == "any"
    assert step3["approvers"] == []


def test_legacy_approval_endpoint_does_not_overwrite_pool_approvers(client):
    """Regression guard for a bug caught during implementation: the legacy
    /approval wrapper used to unconditionally self-assign the calling user
    as the sole approver whenever they weren't already one — which would
    have silently wiped out the pool-derived mandatory approvers. Now it
    only self-assigns when NO approver is set yet at all."""
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana Head")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn Head")

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")  # Phase 5 hard gate
    client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(b"final content"), "final.txt")},
        content_type="multipart/form-data",
    )
    client.post(f"/qms/documents/{did}/workflow/start")
    # advance past Review with a manually assigned reviewer so we reach the
    # quorum-gated Approval step
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": "rev-1", "display_name": "Rita"}]})
    client.post(f"/qms/documents/{did}/workflow/steps/2/decide",
                json={"decision": "approve", "meaning": "Reviewed"})

    # a bystander who is NOT in the pool calls the legacy endpoint
    r = client.post(f"/qms/documents/{did}/approval", json={"action": "Approved", "meaning": "Approved"})
    assert r.status_code == 409  # WorkflowPermissionError -> 409 in this route's except clause

    state = wfe.get_instance_state("document", did)
    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    approver_ids = {a["user_id"] for a in step3["approvers"]}
    assert approver_ids == {"dh-1", "qh-1"}  # unchanged — never overwritten


# ── pool CRUD route ────────────────────────────────────────────────────────

def test_approver_pool_route_set_and_get(client):
    r = client.post("/qms/documents/approver-pool",
                     json={"pool_role": "department_head", "user_id": "dh-1", "display_name": "Dana"})
    assert r.status_code == 201
    r = client.get("/qms/documents/approver-pool")
    assert r.status_code == 200
    assert {p["pool_role"]: p["user_id"] for p in r.get_json()} == {"department_head": "dh-1"}


def test_approver_pool_route_rejects_unknown_role(client):
    r = client.post("/qms/documents/approver-pool",
                     json={"pool_role": "site_head", "user_id": "x"})
    assert r.status_code == 400

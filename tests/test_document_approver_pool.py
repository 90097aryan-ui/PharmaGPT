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


def test_approval_step_never_becomes_quorum_mode_now(db_path):
    """SOP workflow correction: Department Head/Quality Head/Plant Head are
    now strictly sequential single-decider steps — start_instance() must
    never snapshot ANY Document Control approval step as quorum mode any
    more, even with a quorum override, superseding the old
    test_approval_step_becomes_quorum_mode (which asserted the opposite,
    Phase-3 behaviour)."""
    doc = _make_document()
    state = wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID,
                                "Ada Author", default_quorum=2)
    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["approval_mode"] == "any"
    assert step3["required_quorum"] is None


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


# ── Route-level: the pool is no longer consulted at workflow start ──────────
# SOP workflow correction: assignment authority belongs to the Author alone
# (POST .../assign-chain — see tests/test_document_author_assigned_chain.py
# for that full suite). The Approver Pool's CRUD/routes/resolve functions
# above are untouched and still work for any other future use; these tests
# confirm specifically that having a pool configured no longer auto-assigns
# ANYTHING at Submit for Review — Submit for Review is blocked instead,
# exactly as it would be for any document with no chain assigned.

def test_configured_pool_no_longer_auto_assigns_at_workflow_start(client):
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana Head")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn Head")

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")
    client.post(
        f"/qms/documents/{doc['id']}/versions/upload",
        data={"file": (io.BytesIO(b"final content"), "final.txt")},
        content_type="multipart/form-data",
    )
    r = client.post(f"/qms/documents/{doc['id']}/workflow/start")
    # blocked — no review/approval chain assigned, regardless of pool config
    assert r.status_code == 409
    assert "chain" in r.get_json()["error"].lower()


def test_legacy_approval_endpoint_also_requires_an_assigned_chain(client):
    """The legacy /approval wrapper's auto-start branch goes through the
    exact same _submission_gate_error()/_assign_review_chain_to_steps() path
    as /workflow/start now — an unconfigured chain blocks it the same way,
    regardless of whether an Approver Pool happens to be configured."""
    qdb.set_approver_pool_member(COMPANY_ID, "", "department_head", "dh-1", "Dana Head")
    qdb.set_approver_pool_member(COMPANY_ID, "", "quality_head", "qh-1", "Quinn Head")

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(b"final content"), "final.txt")},
        content_type="multipart/form-data",
    )
    r = client.post(f"/qms/documents/{did}/approval", json={"action": "Approved", "meaning": "Approved"})
    assert r.status_code == 409
    assert "chain" in r.get_json()["error"].lower()


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

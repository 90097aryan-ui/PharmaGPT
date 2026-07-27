"""
tests/test_workflow_engine.py — Regression coverage for the generic workflow
engine (pharmagpt/services/workflow_engine.py + qms_workflow_database.py,
Phase 1: Deviation Investigation Redesign) via the DEVIATION_INVESTIGATION_V1
template it ships seeded (qms_database.QMS_SCHEMA).

Exercises the engine directly (no Flask routes) against the db_path
fixture's throwaway SQLite database — same style as
tests/test_lifecycle_engine.py, but this engine persists real rows so each
test also creates a deviation record to attach the workflow to.
"""

import pytest

from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_workflow_database as wfdb
from pharmagpt.services import workflow_engine as wfe

COMPANY_ID = "test-company"
INITIATOR = "Ida Initiator"


@pytest.fixture(autouse=True)
def _app_context():
    """workflow_engine calls audit.log(), which reads flask.g — needs an
    application context even though these tests never make an HTTP request."""
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def _make_deviation(db_path):
    return ddb.create_deviation({"title": "Temp excursion"}, company_id=COMPANY_ID)


def _start(dev):
    return wfe.start_instance("DEVIATION_INVESTIGATION_V1", "deviation", dev["id"], COMPANY_ID, INITIATOR)


def _assign(dev, step_order, user_id="mgr-1", name="Manny Manager"):
    return wfe.assign_approvers("deviation", dev["id"], step_order, [{"user_id": user_id, "display_name": name}])


def _approve(dev, step_order, user_id="mgr-1", role="reviewer_qa"):
    return wfe.decide_step("deviation", dev["id"], step_order, "approve",
                            user_id=user_id, role=role, performed_by="Manny Manager")


def _advance(dev, step_order, role="reviewer_qa"):
    return wfe.decide_step("deviation", dev["id"], step_order, "advance",
                            user_id="n/a", role=role, performed_by="Some Investigator")


# ── start_instance ────────────────────────────────────────────────────────────

def test_start_instance_completes_step_one_and_advances(db_path):
    dev = _make_deviation(db_path)
    state = _start(dev)

    assert state["instance"]["current_step_order"] == 2
    assert state["instance"]["status"] == "in_progress"
    assert state["steps"][0]["step_key"] == "submitted"
    assert state["steps"][0]["status"] == "approved"
    assert ddb.get_deviation(dev["id"])["status"] == "Initiator Manager Review"


def test_start_instance_twice_is_rejected(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    with pytest.raises(wfe.WorkflowError):
        _start(dev)


def test_unknown_template_key_raises(db_path):
    dev = _make_deviation(db_path)
    with pytest.raises(wfe.WorkflowError):
        wfe.start_instance("NOT_A_REAL_TEMPLATE", "deviation", dev["id"], COMPANY_ID, INITIATOR)


# ── Named-approver enforcement on approval steps ─────────────────────────────

def test_approval_step_without_assigned_approver_blocks_decision(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    with pytest.raises(wfe.WorkflowError):
        _approve(dev, 2, user_id="mgr-1")


def test_only_the_assigned_approver_may_decide(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    _assign(dev, 2, user_id="mgr-1", name="Manny Manager")

    with pytest.raises(wfe.WorkflowPermissionError):
        _approve(dev, 2, user_id="someone-else")

    state = _approve(dev, 2, user_id="mgr-1")
    assert state["instance"]["current_step_order"] == 3
    assert ddb.get_deviation(dev["id"])["status"] == "QA Manager Review"


def test_decide_wrong_step_order_is_rejected(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    _assign(dev, 2, user_id="mgr-1")
    with pytest.raises(wfe.WorkflowError):
        wfe.decide_step("deviation", dev["id"], 3, "approve",
                         user_id="mgr-1", role="reviewer_qa", performed_by="Manny Manager")


def test_assigning_approver_to_non_approval_step_is_rejected(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    with pytest.raises(wfe.WorkflowError):
        # step 1 ("submitted") is an activity step, already completed anyway
        wfe.assign_approvers("deviation", dev["id"], 1, [{"user_id": "x"}])


# ── Activity-step role gating ─────────────────────────────────────────────────

def _walk_to_qa_approval(dev):
    """Helper: submitted -> initiator_mgr_review -> qa_mgr_review -> qa_approval, all approved."""
    _start(dev)
    for step_order, uid in ((2, "init-mgr"), (3, "qa-mgr"), (4, "qa-head")):
        _assign(dev, step_order, user_id=uid, name=uid)
        _approve(dev, step_order, user_id=uid, role="company_admin")


def test_activity_step_requires_eligible_role(db_path):
    dev = _make_deviation(db_path)
    _walk_to_qa_approval(dev)
    # step 5 = investigation_open, eligible_roles reviewer_qa,company_admin
    with pytest.raises(wfe.WorkflowPermissionError):
        _advance(dev, 5, role="user")

    state = _advance(dev, 5, role="reviewer_qa")
    assert state["instance"]["current_step_order"] == 6
    assert ddb.get_deviation(dev["id"])["status"] == "Evidence Collection"


# ── Investigation lock ────────────────────────────────────────────────────────

def test_is_unlocked_false_before_qa_approval_true_after(db_path):
    dev = _make_deviation(db_path)
    unlocked, reason = wfe.is_unlocked("deviation", dev["id"], "qa_approval")
    assert unlocked is False and "Submission" in reason

    _start(dev)
    unlocked, reason = wfe.is_unlocked("deviation", dev["id"], "qa_approval")
    assert unlocked is False
    assert "Initiator Manager Review" in reason

    for step_order, uid in ((2, "init-mgr"), (3, "qa-mgr"), (4, "qa-head")):
        _assign(dev, step_order, user_id=uid, name=uid)
        _approve(dev, step_order, user_id=uid, role="company_admin")

    unlocked, reason = wfe.is_unlocked("deviation", dev["id"], "qa_approval")
    assert unlocked is True
    assert reason == ""


# ── Reject / return ───────────────────────────────────────────────────────────

def test_reject_terminates_the_instance(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    _assign(dev, 2, user_id="mgr-1")
    state = wfe.decide_step("deviation", dev["id"], 2, "reject",
                             user_id="mgr-1", role="reviewer_qa", performed_by="Manny Manager",
                             comments="Insufficient detail")
    assert state["instance"]["status"] == "rejected"
    assert ddb.get_deviation(dev["id"])["status"] == "Rejected"

    with pytest.raises(wfe.WorkflowError):
        _advance(dev, 5)


def test_return_from_qa_review(db_path):
    dev = _make_deviation(db_path)
    _walk_to_qa_approval(dev)
    for step_order in (5, 6, 7, 8, 9, 10, 11):
        _advance(dev, step_order, role="reviewer_qa")
    _assign(dev, 12, user_id="qa-reviewer", name="Quinn QA")
    state = wfe.decide_step("deviation", dev["id"], 12, "return",
                             user_id="qa-reviewer", role="reviewer_qa", performed_by="Quinn QA",
                             comments="Need more evidence")

    assert state["instance"]["current_step_order"] == 6
    assert ddb.get_deviation(dev["id"])["status"] == "Returned for Investigation"
    steps_by_order = {s["step_order"]: s for s in state["steps"]}
    assert steps_by_order[6]["status"] == "pending"
    assert steps_by_order[11]["status"] == "pending"
    assert steps_by_order[12]["status"] == "returned"


def test_return_only_legal_from_qa_review(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    _assign(dev, 2, user_id="mgr-1")
    with pytest.raises(wfe.WorkflowError):
        wfe.decide_step("deviation", dev["id"], 2, "return",
                         user_id="mgr-1", role="reviewer_qa", performed_by="Manny Manager")


# ── Full happy path ───────────────────────────────────────────────────────────

def test_full_happy_path_reaches_closed(db_path):
    dev = _make_deviation(db_path)
    _walk_to_qa_approval(dev)
    for step_order in (5, 6, 7, 8, 9, 10, 11):
        _advance(dev, step_order, role="reviewer_qa")
    for step_order in (12, 13):
        _assign(dev, step_order, user_id="qa-head", name="Quinn QA")
        _approve(dev, step_order, user_id="qa-head", role="company_admin")
    state = _advance(dev, 14, role="reviewer_qa")  # effectiveness_check
    assert ddb.get_deviation(dev["id"])["status"] == "Effectiveness Check"

    state = wfe.decide_step("deviation", dev["id"], 15, "advance",
                             user_id="n/a", role="company_admin", performed_by="Quinn QA")
    assert state["instance"]["status"] == "completed"
    assert ddb.get_deviation(dev["id"])["status"] == "Closed"

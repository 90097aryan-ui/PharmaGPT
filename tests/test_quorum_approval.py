"""
tests/test_quorum_approval.py — Regression coverage for configurable quorum
approval on Document Control (services/workflow_engine.py's
approval_mode='quorum' branch of decide_step(), gated by
DOCUMENT_WORKFLOW_V1's step 2 "under_review" and step 3 "effective" approval
steps via qms_documents.approval_quorum -> start_instance(default_quorum=...)).

Exercises the engine directly against the db_path fixture's throwaway SQLite
database, same style as tests/test_workflow_engine.py — this is the same
engine and template, just with a per-document quorum override instead of the
default single-decider 'any' mode.
"""

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_workflow_database as wfdb
from pharmagpt.services import workflow_engine as wfe

COMPANY_ID = "test-company"


@pytest.fixture(autouse=True)
def _app_context():
    """workflow_engine calls audit.log(), which reads flask.g — needs an
    application context even though these tests never make an HTTP request."""
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def _make_document(created_by_user_id="author-1"):
    return qdb.create_document(
        {"title": "Cleaning SOP"}, company_id=COMPANY_ID,
        created_by_user_id=created_by_user_id, created_by_display_name="Ada Author",
    )


def _start(doc, quorum=None):
    return wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID,
                               "Ada Author", default_quorum=quorum)


def _assign(doc, step_order, approvers):
    return wfe.assign_approvers("document", doc["id"], step_order, approvers)


def _vote(doc, step_order, user_id, decision, name=None):
    return wfe.decide_step("document", doc["id"], step_order, decision,
                            user_id=user_id, role="reviewer_qa", performed_by=name or user_id)


APPROVER_A = {"user_id": "appr-a", "display_name": "Al Approver"}
APPROVER_B = {"user_id": "appr-b", "display_name": "Bea Approver"}


# ── Quorum not yet met ────────────────────────────────────────────────────────

def test_quorum_not_met_keeps_step_pending(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    _assign(doc, 2, [APPROVER_A, APPROVER_B])

    state = _vote(doc, 2, "appr-a", "approve", "Al Approver")

    step2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step2["status"] == "pending"
    assert step2["votes_cast"] == 1
    assert step2["required_quorum"] == 2
    assert state["instance"]["current_step_order"] == 2
    assert qdb.get_document(doc["id"])["status"] == "Under Review"


# ── Quorum met ────────────────────────────────────────────────────────────────

def test_quorum_met_advances_step(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    _assign(doc, 2, [APPROVER_A, APPROVER_B])

    _vote(doc, 2, "appr-a", "approve", "Al Approver")
    state = _vote(doc, 2, "appr-b", "approve", "Bea Approver")

    step2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step2["status"] == "approved"
    assert step2["votes_cast"] == 2
    assert state["instance"]["current_step_order"] == 3


# ── Self-vote and duplicate-vote guards ───────────────────────────────────────

def test_document_creator_cannot_be_assigned_as_quorum_approver(db_path):
    doc = _make_document(created_by_user_id="author-1")
    _start(doc, quorum=2)
    with pytest.raises(wfe.WorkflowError):
        _assign(doc, 2, [{"user_id": "author-1", "display_name": "Ada Author"}, APPROVER_B])


def test_duplicate_vote_is_rejected(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    _assign(doc, 2, [APPROVER_A, APPROVER_B])
    _vote(doc, 2, "appr-a", "approve", "Al Approver")

    with pytest.raises(wfe.WorkflowError):
        _vote(doc, 2, "appr-a", "approve", "Al Approver")


def test_only_an_assigned_approver_may_vote(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    _assign(doc, 2, [APPROVER_A, APPROVER_B])

    with pytest.raises(wfe.WorkflowPermissionError):
        _vote(doc, 2, "someone-else", "approve", "Stranger")


def test_quorum_step_without_assigned_approvers_blocks_voting(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    with pytest.raises(wfe.WorkflowError):
        _vote(doc, 2, "appr-a", "approve", "Al Approver")


# ── Single rejection resets to Draft and clears votes ────────────────────────

def test_single_rejection_resets_step_and_clears_votes(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    _assign(doc, 2, [APPROVER_A, APPROVER_B])

    _vote(doc, 2, "appr-a", "approve", "Al Approver")
    state = _vote(doc, 2, "appr-b", "reject", "Bea Approver")

    step2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step2["status"] == "rejected"
    assert state["instance"]["status"] == "rejected"
    assert qdb.get_document(doc["id"])["status"] == "Draft"
    assert wfdb.get_votes(step2["id"]) == []


# ── Default ('any') behaviour is unchanged when no quorum override is set ────

def test_no_quorum_override_preserves_any_mode(db_path):
    doc = _make_document()
    _start(doc, quorum=None)
    _assign(doc, 2, [APPROVER_A])

    state = _vote(doc, 2, "appr-a", "approve", "Al Approver")

    step2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step2["approval_mode"] == "any"
    assert "votes_cast" not in step2
    assert step2["status"] == "approved"
    assert state["instance"]["current_step_order"] == 3

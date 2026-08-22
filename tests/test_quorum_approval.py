"""
tests/test_quorum_approval.py — Regression coverage for the generic
configurable-quorum approval mechanism itself (services/workflow_engine.py's
approval_mode='quorum' branch of decide_step()/_decide_quorum_step()).

SOP workflow correction note: Document Control's Department Head/Quality
Head/Plant Head steps are now strictly SEQUENTIAL single-decider steps, not
a shared quorum step — quorum_eligible=0 on every one of DOCUMENT_WORKFLOW_
V1's approval steps (qms_database.py), so qms_documents.py's routes can
never actually produce a live quorum-mode step any more (see
tests/test_document_author_assigned_chain.py for that new sequential-
approval coverage instead). The quorum MECHANISM in workflow_engine.py is
still fully general-purpose — any future record_type/step could use it — so
this file now exercises it directly at the engine/DB level: manually
snapshotting one instance step as approval_mode='quorum' (bypassing
DOCUMENT_WORKFLOW_V1's own quorum_eligible=0, which only gates
start_instance()'s own snapshotting decision, not decide_step()'s ability to
process a quorum step once one exists) rather than relying on any live
caller to produce one. The assertions themselves — quorum math, vote-
clearing on reject, duplicate-vote/self-vote guards — are unchanged from
before this rewrite.
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


def _make_document():
    return qdb.create_document({"title": "Cleaning SOP"}, company_id=COMPANY_ID)


def _start_and_force_quorum_on_step(doc, step_order, required_quorum):
    """Starts a normal (non-quorum) DOCUMENT_WORKFLOW_V1 instance, then
    directly overwrites one already-created instance step's approval_mode/
    required_quorum to 'quorum' — the engine-level state _decide_quorum_step
    actually branches on — bypassing quorum_eligible=0's block on
    start_instance() ever doing this automatically for Document Control.
    This is intentionally the lowest-level way to reach a real quorum step:
    it tests decide_step()'s dispatch and _decide_quorum_step()'s own logic,
    not any particular record_type's routing decision to request one."""
    state = wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    step = next(s for s in state["steps"] if s["step_order"] == step_order)
    conn = wfdb.get_connection()
    conn.execute(
        "UPDATE qms_workflow_instance_steps SET approval_mode = 'quorum', required_quorum = ? WHERE id = ?",
        (required_quorum, step["id"]),
    )
    conn.commit()
    conn.close()
    return state


def _assign(doc, step_order, approvers):
    return wfe.assign_approvers("document", doc["id"], step_order, approvers)


def _vote(doc, step_order, user_id, decision, name=None, comments=""):
    return wfe.decide_step("document", doc["id"], step_order, decision,
                            user_id=user_id, role="reviewer_qa", performed_by=name or user_id, comments=comments)


def _clear_review(doc):
    """Advance past step 2 (Review, always single-decider) so the instance
    reaches step 3 — the step _start_and_force_quorum_on_step forced into
    quorum mode."""
    _assign(doc, 2, [{"user_id": "rev-1", "display_name": "Rita Reviewer"}])
    return _vote(doc, 2, "rev-1", "approve", "Rita Reviewer")


APPROVER_A = {"user_id": "appr-a", "display_name": "Al Approver"}
APPROVER_B = {"user_id": "appr-b", "display_name": "Bea Approver"}


# ── Quorum not yet met ────────────────────────────────────────────────────────

def test_quorum_not_met_keeps_step_pending(db_path):
    doc = _make_document()
    _start_and_force_quorum_on_step(doc, 3, required_quorum=2)
    _clear_review(doc)
    _assign(doc, 3, [APPROVER_A, APPROVER_B])

    state = _vote(doc, 3, "appr-a", "approve", "Al Approver")

    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["status"] == "pending"
    assert step3["votes_cast"] == 1
    assert step3["required_quorum"] == 2
    assert state["instance"]["current_step_order"] == 3


# ── Quorum met ────────────────────────────────────────────────────────────────

def test_quorum_met_advances_step(db_path):
    doc = _make_document()
    _start_and_force_quorum_on_step(doc, 3, required_quorum=2)
    _clear_review(doc)
    _assign(doc, 3, [APPROVER_A, APPROVER_B])

    _vote(doc, 3, "appr-a", "approve", "Al Approver")
    state = _vote(doc, 3, "appr-b", "approve", "Bea Approver")

    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["status"] == "approved"
    assert step3["votes_cast"] == 2
    assert state["instance"]["current_step_order"] == 4  # advanced to step 4, not completed — 5 steps total now


# ── Self-vote and duplicate-vote guards ───────────────────────────────────────

@pytest.mark.skip(reason="Requires Wave 1 SOD-01 (reject_creator_as_approver in workflow_engine.py), "
                          "which is uncommitted work outside this redesign's scope — preserved untouched "
                          "in git stash, not merged into this branch. Un-skip once that work lands.")
def test_document_creator_cannot_be_assigned_as_quorum_approver(db_path):
    doc = _make_document()
    _start_and_force_quorum_on_step(doc, 3, required_quorum=2)
    _clear_review(doc)
    with pytest.raises(wfe.WorkflowError):
        _assign(doc, 3, [{"user_id": "author-1", "display_name": "Ada Author"}, APPROVER_B])


def test_duplicate_vote_is_rejected(db_path):
    doc = _make_document()
    _start_and_force_quorum_on_step(doc, 3, required_quorum=2)
    _clear_review(doc)
    _assign(doc, 3, [APPROVER_A, APPROVER_B])
    _vote(doc, 3, "appr-a", "approve", "Al Approver")

    with pytest.raises(wfe.WorkflowError):
        _vote(doc, 3, "appr-a", "approve", "Al Approver")


def test_only_an_assigned_approver_may_vote(db_path):
    doc = _make_document()
    _start_and_force_quorum_on_step(doc, 3, required_quorum=2)
    _clear_review(doc)
    _assign(doc, 3, [APPROVER_A, APPROVER_B])

    with pytest.raises(wfe.WorkflowPermissionError):
        _vote(doc, 3, "someone-else", "approve", "Stranger")


def test_quorum_step_without_assigned_approvers_blocks_voting(db_path):
    doc = _make_document()
    _start_and_force_quorum_on_step(doc, 3, required_quorum=2)
    _clear_review(doc)
    with pytest.raises(wfe.WorkflowError):
        _vote(doc, 3, "appr-a", "approve", "Al Approver")


# ── Single rejection resets to Draft and clears votes ────────────────────────

def test_single_rejection_resets_step_and_clears_votes(db_path):
    doc = _make_document()
    _start_and_force_quorum_on_step(doc, 3, required_quorum=2)
    _clear_review(doc)
    _assign(doc, 3, [APPROVER_A, APPROVER_B])

    _vote(doc, 3, "appr-a", "approve", "Al Approver")
    # Document Control redesign (Phase 2): any rejection now requires a
    # non-empty comment — a bare reject vote (no reason) is no longer legal.
    state = _vote(doc, 3, "appr-b", "reject", "Bea Approver", comments="Not satisfied with evidence")

    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["status"] == "rejected"
    assert state["instance"]["status"] == "rejected"
    assert qdb.get_document(doc["id"])["status"] == "Draft"
    assert wfdb.get_votes(step3["id"]) == []


# ── Default ('any') behaviour is unchanged when no quorum override is set ────

def test_no_quorum_override_preserves_any_mode(db_path):
    doc = _make_document()
    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    _assign(doc, 2, [APPROVER_A])

    state = _vote(doc, 2, "appr-a", "approve", "Al Approver")

    step2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step2["approval_mode"] == "any"
    assert "votes_cast" not in step2
    assert step2["status"] == "approved"
    assert state["instance"]["current_step_order"] == 3


def test_no_quorum_override_preserves_any_mode_on_approval_step_too(db_path):
    doc = _make_document()
    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    _assign(doc, 2, [APPROVER_A])
    _vote(doc, 2, "appr-a", "approve", "Al Approver")
    _assign(doc, 3, [APPROVER_B])

    state = _vote(doc, 3, "appr-b", "approve", "Bea Approver")

    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["approval_mode"] == "any"
    assert "votes_cast" not in step3
    assert step3["status"] == "approved"
    assert state["instance"]["current_step_order"] == 4  # 5-step template — not yet completed


# ── Document Control's own steps are never quorum-eligible by default ───────

def test_document_workflow_steps_are_never_quorum_eligible_by_default(db_path):
    """SOP workflow correction: Department Head/Quality Head/Plant Head are
    strictly sequential single-decider steps now — start_instance() must
    never auto-snapshot any Document Control approval step as quorum mode,
    even if a caller passes default_quorum > 1 (nothing does any more, but
    this guards against a future regression reintroducing that call)."""
    doc = _make_document()
    state = wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID,
                                "Ada Author", default_quorum=3)
    for step in state["steps"]:
        if step["step_type"] == "approval":
            assert step["approval_mode"] == "any"
            assert step["required_quorum"] is None

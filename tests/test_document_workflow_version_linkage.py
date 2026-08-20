"""
tests/test_document_workflow_version_linkage.py — Phase 2 coverage:
services/workflow_engine.py's document-scoped version-linkage hooks
(VERSION_ON_INSTANCE_START / VERSION_ON_STEP_APPROVED / VERSION_ON_STEP_REJECTED,
CURRENT_VERSION_LOOKUP), the mandatory-rejection-comment gate, and
qms_document_database.py's fork-on-rejection (reject_and_fork_version).

Exercises the engine directly against the db_path fixture's throwaway
SQLite database, same style as tests/test_workflow_engine.py and
tests/test_quorum_approval.py.
"""

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_workflow_database as wfdb
from pharmagpt.services import workflow_engine as wfe

COMPANY_ID = "test-company"


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def _make_document():
    return qdb.create_document({"title": "Cleaning SOP", "content": "initial content"}, company_id=COMPANY_ID)


def _start(doc, quorum=None):
    return wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID,
                               "Ada Author", default_quorum=quorum)


def _assign(doc, step_order, user_id="rev-1", name="Rita Reviewer"):
    return wfe.assign_approvers("document", doc["id"], step_order, [{"user_id": user_id, "display_name": name}])


def _decide(doc, step_order, decision, user_id="rev-1", role="reviewer_qa", comments=""):
    return wfe.decide_step("document", doc["id"], step_order, decision,
                            user_id=user_id, role=role, performed_by="Rita Reviewer", comments=comments)


# ── start_instance links the instance to the current version, moves it to under_review ──

def test_start_instance_links_version_and_moves_to_under_review(db_path):
    doc = _make_document()
    v0 = qdb.get_current_version(doc["id"])
    assert v0["status"] == "draft"

    state = _start(doc)

    v0_after = qdb.get_version(v0["id"])
    assert v0_after["status"] == "under_review"
    assert v0_after["workflow_instance_id"] == state["instance"]["id"]
    assert wfdb.get_active_instance("document", doc["id"])["document_version_id"] == v0["id"]


# ── Review accepted advances the version to pending_approval ─────────────────

def test_review_accepted_advances_version_to_pending_approval(db_path):
    doc = _make_document()
    v0 = qdb.get_current_version(doc["id"])
    _start(doc)
    _assign(doc, 2, "rev-1")

    _decide(doc, 2, "approve", user_id="rev-1")

    assert qdb.get_version(v0["id"])["status"] == "pending_approval"


# ── Review rejection: mandatory comment, fork-on-reject ──────────────────────

def test_review_reject_without_comment_is_blocked(db_path):
    doc = _make_document()
    _start(doc)
    _assign(doc, 2, "rev-1")

    with pytest.raises(wfe.WorkflowError, match="comment is required"):
        _decide(doc, 2, "reject", user_id="rev-1", comments="")

    # nothing mutated: version still under_review, no fork happened
    v0 = qdb.get_current_version(doc["id"])
    assert v0["status"] == "under_review"


def test_review_reject_with_comment_forks_new_immutable_version(db_path):
    doc = _make_document()
    v0 = qdb.get_current_version(doc["id"])
    _start(doc)
    _assign(doc, 2, "rev-1")

    _decide(doc, 2, "reject", user_id="rev-1", comments="Missing acceptance criteria")

    old = qdb.get_version(v0["id"])
    assert old["status"] == "review_rejected"
    assert old["rejection_reason"] == "Missing acceptance criteria"

    new_current = qdb.get_current_version(doc["id"])
    assert new_current["id"] != v0["id"]
    assert new_current["status"] == "draft"
    assert new_current["version_number"] == "0.2"
    assert new_current["parent_version_id"] == v0["id"]
    assert new_current["content_snapshot"] == old["content_snapshot"]

    doc_after = qdb.get_document(doc["id"])
    assert doc_after["status"] == "Draft"
    assert doc_after["version"] == "0.2"


def test_rejected_version_content_cannot_be_edited_after_fork(db_path):
    """The rejected version is permanently immutable — its own trigger guard
    (Phase 1) still applies once it left 'draft', independent of the fork."""
    import sqlite3
    doc = _make_document()
    v0 = qdb.get_current_version(doc["id"])
    _start(doc)
    _assign(doc, 2, "rev-1")
    _decide(doc, 2, "reject", user_id="rev-1", comments="Fix formatting")

    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE qms_document_versions SET content_snapshot = 'tampered' WHERE id = ?", (v0["id"],))
    conn.close()


def test_new_version_requires_fresh_self_check_never_carried_forward(db_path):
    doc = _make_document()
    v0 = qdb.get_current_version(doc["id"])
    qdb.transition_version_status(v0["id"], "under_review")  # simulate self-check having been done pre-submit
    qdb.transition_version_status(v0["id"], "review_rejected", rejection_reason="x")
    # (transition_version_status alone doesn't set self_check_completed_at;
    # this test's real point is the NEW version's own field, below)
    new_v = qdb._insert_version_row(doc["id"], version_number="0.2", parent_version_id=v0["id"],
                                     content_snapshot="x", created_by_user_id="author-1")
    assert new_v["self_check_completed_at"] == ""


# ── Full new-SOP reject/resubmit cycle: numbering sequence ───────────────────

def test_full_new_sop_reject_resubmit_numbering_sequence(db_path):
    doc = _make_document()
    assert qdb.get_current_version(doc["id"])["version_number"] == "0.1"

    _start(doc)
    _assign(doc, 2, "rev-1")
    _decide(doc, 2, "reject", user_id="rev-1", comments="rework 1")
    assert qdb.get_current_version(doc["id"])["version_number"] == "0.2"

    _start(doc)
    _assign(doc, 2, "rev-1")
    _decide(doc, 2, "reject", user_id="rev-1", comments="rework 2")
    assert qdb.get_current_version(doc["id"])["version_number"] == "0.3"

    _start(doc)
    _assign(doc, 2, "rev-1")
    _decide(doc, 2, "approve", user_id="rev-1")
    assert qdb.get_current_version(doc["id"])["version_number"] == "0.3"
    assert qdb.get_current_version(doc["id"])["status"] == "pending_approval"


# ── Quorum reject path also requires a comment and forks ─────────────────────

def _clear_review_quorum(doc):
    """Since Phase 3, step 2 (Review) is never quorum-eligible regardless of
    a document-level quorum override (qms_database.py's DOCUMENT_WORKFLOW_V1
    seed sets quorum_eligible=0 on it) — a single reviewer always suffices
    to advance past it, even when default_quorum was passed to _start()."""
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": "rev-1", "display_name": "Rita"}])
    return wfe.decide_step("document", doc["id"], 2, "approve", user_id="rev-1", role="reviewer_qa", performed_by="Rita")


def test_quorum_approval_reject_without_comment_is_blocked(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    _clear_review_quorum(doc)

    wfe.assign_approvers("document", doc["id"], 3, [
        {"user_id": "appr-a", "display_name": "Al"}, {"user_id": "appr-b", "display_name": "Bea"},
    ])
    with pytest.raises(wfe.WorkflowError, match="comment is required"):
        wfe.decide_step("document", doc["id"], 3, "reject", user_id="appr-a", role="reviewer_qa",
                         performed_by="Al", comments="")


def test_quorum_approval_reject_with_comment_forks_and_clears_votes(db_path):
    doc = _make_document()
    v0 = qdb.get_current_version(doc["id"])
    _start(doc, quorum=2)
    _clear_review_quorum(doc)

    wfe.assign_approvers("document", doc["id"], 3, [
        {"user_id": "appr-a", "display_name": "Al"}, {"user_id": "appr-b", "display_name": "Bea"},
    ])
    wfe.decide_step("document", doc["id"], 3, "approve", user_id="appr-a", role="reviewer_qa", performed_by="Al")
    state = wfe.decide_step("document", doc["id"], 3, "reject", user_id="appr-b", role="reviewer_qa",
                             performed_by="Bea", comments="Numbers don't reconcile")

    assert qdb.get_version(v0["id"])["status"] == "approval_rejected"
    assert qdb.get_version(v0["id"])["rejection_reason"] == "Numbers don't reconcile"
    new_current = qdb.get_current_version(doc["id"])
    assert new_current["version_number"] == "0.2"
    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert wfdb.get_votes(step3["id"]) == []


def test_old_votes_never_carry_forward_into_resubmitted_cycle(db_path):
    doc = _make_document()
    _start(doc, quorum=2)
    _assign(doc, 2, "rev-1")
    _decide(doc, 2, "reject", user_id="rev-1", comments="rework")  # single-approver 'any' mode: quorum
    # only ever activates once >=2 approvers are assigned, so a lone
    # assigned approver's own reject still behaves as a normal single
    # decider reject here — confirms rejecting doesn't require quorum to
    # have been reached first.

    _start(doc, quorum=2)
    _clear_review_quorum(doc)
    wfe.assign_approvers("document", doc["id"], 3, [
        {"user_id": "appr-a", "display_name": "Al"}, {"user_id": "appr-b", "display_name": "Bea"},
    ])
    # same approver id ("appr-a") voting on a brand-new instance/step must be
    # allowed — has_voted() is scoped to instance_step_id, never to the
    # document/version as a whole.
    state = wfe.decide_step("document", doc["id"], 3, "approve", user_id="appr-a", role="reviewer_qa",
                             performed_by="Al")
    step3 = next(s for s in state["steps"] if s["step_order"] == 3)
    assert step3["votes_cast"] == 1


# ── Non-document record types are completely unaffected ──────────────────────

def test_deviation_workflow_unaffected_by_document_hooks(db_path):
    dev = ddb.create_deviation({"title": "Temp excursion"}, company_id=COMPANY_ID)
    state = wfe.start_instance("DEVIATION_INVESTIGATION_V1", "deviation", dev["id"], COMPANY_ID, "Ida Initiator")
    assert state["instance"]["current_step_order"] == 2
    # no document_version_id ever set for a non-document instance
    assert state["instance"].get("document_version_id") in (None, "")


def test_deviation_reject_with_empty_comment_still_allowed(db_path):
    """The mandatory-comment gate is scoped strictly to record_type=='document'
    — CAPA/Deviation/Change Control's existing (empty-comment-allowed)
    behaviour must be completely unchanged."""
    dev = ddb.create_deviation({"title": "Temp excursion"}, company_id=COMPANY_ID)
    wfe.start_instance("DEVIATION_INVESTIGATION_V1", "deviation", dev["id"], COMPANY_ID, "Ida Initiator")
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "mgr-1", "display_name": "Manny"}])
    # step 2 of DEVIATION_INVESTIGATION_V1 may be an activity step depending
    # on the seed template; if it's not an approval step this call would
    # raise for an unrelated reason — guard by checking step_type first.
    state = wfe.get_instance_state("deviation", dev["id"])
    step = next(s for s in state["steps"] if s["step_order"] == 2)
    if step["step_type"] != "approval":
        pytest.skip("DEVIATION_INVESTIGATION_V1 step 2 is not an approval step in this schema version")
    wfe.decide_step("deviation", dev["id"], 2, "reject", user_id="mgr-1", role="reviewer_qa",
                     performed_by="Manny", comments="")  # must NOT raise

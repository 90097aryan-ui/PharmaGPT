"""
tests/test_approval_engine.py — Regression coverage for the shared,
configurable approval-workflow definitions (pharmagpt/services/
approval_engine.py, Phase 3: Enterprise Validation Platform).

This is a workflow-definition/lookup layer, not a data-storage change — each
suite still writes to its own existing approval-trail table. These tests
cover the lookup contract itself (stage_for_action) and that the two example
workflows given in the Phase 3 task spec (SOP; Validation) are present with
the expected stage ordering.
"""

from pharmagpt.services import approval_engine


def test_sop_workflow_present_and_ordered():
    stages = approval_engine.WORKFLOWS["SOP"]
    assert [s["stage"] for s in stages] == ["Initiator", "Reviewer", "QA Head"]
    assert stages[-1]["status"] == "Effective"


def test_validation_workflow_present_and_ordered():
    stages = approval_engine.WORKFLOWS["VALIDATION"]
    assert [s["stage"] for s in stages] == [
        "Author", "Reviewer", "QA Coordinator", "QA Head",
        "Execution", "Post Execution Review", "Effective",
    ]
    assert stages[3]["status"] == "Effective"  # QA Head reaches Effective


def test_stage_for_action_finds_matching_stage():
    stage = approval_engine.stage_for_action("SOP", "Approved")
    assert stage is not None
    assert stage["stage"] == "QA Head"
    assert stage["role"] == "company_admin"


def test_stage_for_action_returns_none_for_unknown_action():
    assert approval_engine.stage_for_action("SOP", "Not A Real Action") is None


def test_stage_for_action_returns_none_for_unknown_workflow():
    assert approval_engine.stage_for_action("NOT_A_WORKFLOW", "Approved") is None


def test_workflows_extensible_without_code_change():
    """New document types (including a future MFR/BMR/BPR onboarding, per
    PHASE_3_IMPLEMENTATION_REPORT.md's deferral note) plug in as one new dict
    entry — verified here by adding one at runtime and confirming lookup
    works identically to a built-in entry, with no other code touched."""
    approval_engine.WORKFLOWS["_TEST_ONLY"] = [
        {"stage": "Author", "role": "user", "action": "Drafted", "status": "Draft"},
    ]
    try:
        assert approval_engine.stage_for_action("_TEST_ONLY", "Drafted")["role"] == "user"
    finally:
        del approval_engine.WORKFLOWS["_TEST_ONLY"]

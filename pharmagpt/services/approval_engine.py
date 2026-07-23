"""
services/approval_engine.py — shared, configurable approval-workflow
definitions for the platform's governed document types.

This is a workflow-definition/lookup layer, not a data-storage change: each
suite keeps writing to its own existing approval-trail table (qms_approvals
for Document Control/Deviation/CAPA/Change Control, urs_approvals, qual_approvals,
val_report_approvals, risk_approval) exactly as it does today — moving that
storage onto one physical table is unnecessary churn the actual requirement
("configurable workflows") does not call for. What was missing platform-wide
was a single, explicit place naming each workflow's stages, the role
authorized to act at each stage, and the status each stage's action produces
— today that mapping existed only as an implicit, undocumented action->status
dict duplicated per route file. WORKFLOWS below is that single place; routes
are not required to switch to consuming it to keep working (existing
per-route action->status maps are untouched), but new callers (and this
phase's PHASE_3_IMPLEMENTATION_REPORT.md) can point at one definition instead
of five.

WORKFLOWS is intentionally extensible: adding a new document type — including
a future MFR/BMR/BPR once approved for a later phase — is one new dict entry,
no code change.
"""

from __future__ import annotations

# Each workflow is an ordered list of stages: {stage, role, action, status}.
# `role` is one of the four frozen platform roles (super_admin / company_admin
# / reviewer_qa / user) that is authorized to perform that stage's action.
# `action` matches the existing action-name vocabulary each route's own
# action->status map already uses (qms_documents.py::_STATUS_MAP, etc.), so
# this is documentation-and-lookup, not a second source of truth that could
# drift from the routes' own maps.
WORKFLOWS: dict[str, list[dict[str, str]]] = {
    # SOP / general Document Control: Initiator -> Reviewer(s) -> QA Head -> Effective.
    "SOP": [
        {"stage": "Initiator", "role": "user", "action": "Submitted for Review", "status": "Under Review"},
        {"stage": "Reviewer", "role": "reviewer_qa", "action": "Reviewed", "status": "Under Review"},
        {"stage": "QA Head", "role": "company_admin", "action": "Approved", "status": "Effective"},
    ],
    # Validation (URS/DQ/FAT/SAT/IQ/OQ/PQ/Validation Report, once routed through
    # Document Control per this phase's DQ/FAT/SAT consolidation): Author ->
    # Reviewer -> QA Coordinator -> QA Head -> Approved -> Execution ->
    # Post Execution Review -> Effective.
    "VALIDATION": [
        {"stage": "Author", "role": "user", "action": "Submitted for Review", "status": "Under Review"},
        {"stage": "Reviewer", "role": "reviewer_qa", "action": "Reviewed", "status": "Under Review"},
        {"stage": "QA Coordinator", "role": "reviewer_qa", "action": "Submitted for Approval", "status": "Pending Approval"},
        {"stage": "QA Head", "role": "company_admin", "action": "Approved", "status": "Effective"},
        {"stage": "Execution", "role": "user", "action": "Execution Complete", "status": "Effective"},
        {"stage": "Post Execution Review", "role": "reviewer_qa", "action": "Post Execution Reviewed", "status": "Effective"},
        {"stage": "Effective", "role": "company_admin", "action": "Made Effective", "status": "Effective"},
    ],
}


def stage_for_action(workflow_key: str, action: str) -> dict[str, str] | None:
    """Return the stage definition matching `action` in the named workflow,
    or None if the workflow or action isn't recognized. Callers use this to
    look up which role is expected to perform a given approval action —
    informational/documentation lookup, not an enforcement gate (role
    enforcement itself is @require_role on each route, and status-transition
    enforcement is lifecycle_engine.validate_transition())."""
    for stage in WORKFLOWS.get(workflow_key, []):
        if stage["action"] == action:
            return stage
    return None

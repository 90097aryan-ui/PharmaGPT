"""
services/workflow_engine.py — generic, reusable multi-step approval workflow
engine (Phase 1: Deviation Investigation Redesign, PHASE1_INVESTIGATION_PLAN).

Built on top of qms_workflow_database.py's CRUD, this module owns the actual
decision logic: instantiating a template against a record, enforcing that
only a named assigned user may decide an 'approval' step (vs. any
role-eligible user for an 'activity' step), advancing the instance,
writing the resulting status back onto the owning record, and logging every
transition to the existing qms_audit_trail via audit.log() — no new audit
table.

Deliberately record_type-agnostic: dispatch for "how does this record_type's
status get written back" lives in the STATUS_APPLIERS registry below, not in
hardcoded if/elif branching. A future adopting module needs (a) a new
qms_workflow_templates row + step rows and (b) one new entry in
STATUS_APPLIERS — no change to the functions in this file.

Approver semantics (Assumption, see PHASE1_INVESTIGATION_PLAN): a step's
named approvers are "any one of" — the first assigned approver to act
decides the step. Multiple approvers on one step exist to support backup/
delegate coverage, not unanimous consent. Easy to add an all-of mode later
(an `approval_mode` column) without breaking this schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from pharmagpt import audit
from pharmagpt import qms_workflow_database as wfdb


class WorkflowError(Exception):
    """Raised for an illegal workflow operation caused by record/step state
    (unknown step, step already decided, missing approver assignment, ...).
    Routes catch this and return 409."""


class WorkflowPermissionError(WorkflowError):
    """Raised specifically when the caller is not entitled to make the
    decision they attempted (not a named approver, role not eligible).
    Routes catch this and return 403."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _eligible_roles(step: dict) -> list[str]:
    return [r for r in (step.get("eligible_roles") or "").split(",") if r]


def _status_after_completing(template_steps: list[dict], completed_step_order: int, last_order: int) -> str:
    """The record's status once `completed_step_order` is approved: the
    *next* step's gate_status (that step is now the one being awaited), so
    `qms_deviations.status` names whichever step is currently in progress —
    e.g. completing 'qa_approval' shows 'Investigation Open', matching the
    spec's "... -> QA Approval -> Investigation Open -> ..." diagram (each
    name is what's happening now, not what just finished).

    Exception: the transition *into* the workflow's last step never jumps
    ahead to that step's own gate_status (here, 'Closed') — a deviation
    only becomes Closed once the last step is itself decided, not merely
    reached, since `routes/qms_deviations.py::update_deviation` treats
    status=='Closed' as immutable. Until then, status holds at the last
    step actually completed (e.g. 'Effectiveness Check')."""
    this_step = next(s for s in template_steps if s["step_order"] == completed_step_order)
    if completed_step_order >= last_order:
        return this_step["gate_status"]
    next_order = completed_step_order + 1
    if next_order >= last_order:
        return this_step["gate_status"]
    next_step = next(s for s in template_steps if s["step_order"] == next_order)
    return next_step["gate_status"]


def _apply_deviation_status(record_id: int, status: str) -> None:
    from pharmagpt import qms_deviation_database as ddb
    ddb.update_deviation(record_id, {"status": status})


def _apply_capa_status(record_id: int, status: str) -> None:
    # The engine's reject/return decisions write generic gate-status labels
    # ("Rejected", "Returned for Investigation") that aren't part of CAPA's
    # own status vocabulary (qms_database.QMS_META["capa_statuses"]) — map
    # the generic label back onto CAPA's actual "Rejected -> Open" rule here,
    # confined to this one applier, not the engine's core decision logic.
    from pharmagpt import qms_capa_database as capadb
    mapped = "Open" if status == "Rejected" else status
    capadb.update_capa(record_id, {"status": mapped})


def _apply_change_control_status(record_id: int, status: str) -> None:
    from pharmagpt import qms_change_control_database as ccdb
    mapped = "Draft" if status == "Rejected" else status
    ccdb.update_change_control(record_id, {"status": mapped})


def _apply_document_status(record_id: int, status: str) -> None:
    from pharmagpt import qms_document_database as qdb
    from pharmagpt.routes.qms_documents import _publish_effective_document_to_kb
    mapped = "Draft" if status == "Rejected" else status
    document = qdb.update_document(record_id, {"status": mapped})
    if mapped == "Effective" and (document.get("content") or "").strip():
        _publish_effective_document_to_kb(document)


# Registry dispatch for "how does this record_type's status get written back"
# — adding a future module is one function + one entry here, never a growing
# if/elif chain and never a change to decide_step/start_instance/etc.
STATUS_APPLIERS: dict[str, Callable[[int, str], None]] = {
    "deviation": _apply_deviation_status,
    "capa": _apply_capa_status,
    "change_control": _apply_change_control_status,
    "document": _apply_document_status,
}


def _apply_gate_status(record_type: str, record_id: int, status: str) -> None:
    """Write the workflow's resulting status onto the owning record via
    STATUS_APPLIERS. The one place a future adopting module needs an entry."""
    applier = STATUS_APPLIERS.get(record_type)
    if applier is None:
        raise WorkflowError(f"Unsupported record_type '{record_type}' for workflow_engine")
    applier(record_id, status)


def get_instance_state(record_type: str, record_id: int) -> dict:
    """Full workflow state for a record: the latest instance (if any) plus
    every step and its assigned approvers. Used by GET .../workflow and by
    is_unlocked()."""
    instance = wfdb.get_latest_instance(record_type, record_id)
    if not instance:
        return {"instance": None, "steps": []}
    steps = wfdb.get_instance_steps(instance["id"])
    for s in steps:
        s["approvers"] = wfdb.get_step_approvers(s["id"])
    return {"instance": instance, "steps": steps}


def is_unlocked(record_type: str, record_id: int, unlock_step_key: str) -> tuple[bool, str]:
    """Whether `unlock_step_key` has been approved for this record's current
    (or most recent) workflow instance, and if not, a human-readable reason
    naming the step actually being waited on."""
    instance = wfdb.get_latest_instance(record_type, record_id)
    if not instance:
        return False, "Waiting for Submission"

    steps = wfdb.get_instance_steps(instance["id"])
    target = next((s for s in steps if s["step_key"] == unlock_step_key), None)
    if not target:
        return False, "Workflow misconfigured"
    if target["status"] == "approved":
        return True, ""
    if instance["status"] == "rejected":
        return False, "Deviation was rejected — resubmit to reopen the workflow"

    current = next((s for s in steps if s["step_order"] == instance["current_step_order"]), None)
    pending_name = current["step_name"] if current else target["step_name"]
    return False, f"Waiting for {pending_name}"


def start_instance(workflow_key: str, record_type: str, record_id: int,
                    company_id: str | None, performed_by: str) -> dict:
    """Instantiate a fresh workflow run for a record (e.g. on 'Submit for
    Review'). Step 1 is an 'activity' step representing the submission
    itself and is completed immediately by the caller; current_step_order
    advances to step 2."""
    template = wfdb.get_template_by_key(workflow_key)
    if not template:
        raise WorkflowError(f"Unknown workflow template '{workflow_key}'")
    template_steps = wfdb.get_template_steps(template["id"])
    if not template_steps:
        raise WorkflowError(f"Workflow template '{workflow_key}' has no steps")

    existing = wfdb.get_active_instance(record_type, record_id)
    if existing:
        raise WorkflowError("A workflow is already in progress for this record")

    instance = wfdb.create_instance(template["id"], record_type, record_id, company_id)
    for t_step in template_steps:
        wfdb.create_instance_step(instance["id"], t_step)

    first_step = wfdb.get_instance_step(instance["id"], 1)
    now = _now()
    wfdb.update_instance_step(first_step["id"], {
        "status": "approved", "decided_by": performed_by, "decided_at": now,
    })
    last_order = max(s["step_order"] for s in template_steps)
    if len(template_steps) > 1:
        wfdb.update_instance(instance["id"], {"current_step_order": 2})
    else:
        wfdb.update_instance(instance["id"], {"status": "completed", "completed_at": now})
    _apply_gate_status(record_type, record_id, _status_after_completing(template_steps, 1, last_order))
    audit.log(record_type, record_id, f"Workflow started: {first_step['step_name']}")
    return get_instance_state(record_type, record_id)


def assign_approvers(record_type: str, record_id: int, step_order: int,
                      approvers: list[dict]) -> dict:
    """Set the named approver(s) for one of this record's approval steps.
    `approvers` is [{"user_id": ..., "display_name": ...}, ...].

    Known Phase 1 limitation: a step's `eligible_roles` is not cross-checked
    against each candidate's actual role here (the user directory is a
    Postgres/Supabase table — routes/users.py — not reachable from this
    SQLite-side engine without a network round trip per assignment). The
    security-critical guarantee this module *does* enforce is decide_step()'s
    "only a named assignee may decide" check; restricting who is *offered*
    as an assignee in the picker UI is left to the frontend for Phase 1."""
    instance = wfdb.get_active_instance(record_type, record_id)
    if not instance:
        raise WorkflowError("No active workflow instance for this record")
    step = wfdb.get_instance_step(instance["id"], step_order)
    if not step:
        raise WorkflowError(f"Unknown workflow step {step_order}")
    if step["step_type"] != "approval":
        raise WorkflowError(f"'{step['step_name']}' does not take named approvers")
    if step["status"] not in ("pending", "in_progress"):
        raise WorkflowError(f"'{step['step_name']}' is already {step['status']}")
    if not approvers:
        raise WorkflowError("At least one approver is required")

    wfdb.set_step_approvers(step["id"], approvers)
    names = ", ".join(a.get("display_name") or a["user_id"] for a in approvers)
    audit.log(record_type, record_id, f"Approver(s) assigned for {step['step_name']}", detail=names)
    return get_instance_state(record_type, record_id)


def decide_step(record_type: str, record_id: int, step_order: int, decision: str, *,
                 user_id: str, role: str, performed_by: str, comments: str = "") -> dict:
    """Decide the record's *current* workflow step.

    decision:
      'advance'          — step_type='activity'; caller's `role` must be in
                            the step's eligible_roles (no named assignment).
      'approve'/'reject' — step_type='approval'; caller's `user_id` must be
                            one of the step's assigned approvers.
      'return'           — step_type='approval', only legal from the
                            'qa_review' step; sends the record back to
                            'evidence_collection' for further investigation
                            (re-opens the intervening activity steps).
    """
    instance = wfdb.get_active_instance(record_type, record_id)
    if not instance:
        raise WorkflowError("No active workflow instance for this record")
    if instance["current_step_order"] != step_order:
        raise WorkflowError(
            f"Step {step_order} is not the current step (current is {instance['current_step_order']})"
        )
    step = wfdb.get_instance_step(instance["id"], step_order)
    if not step:
        raise WorkflowError(f"Unknown workflow step {step_order}")
    if step["status"] not in ("pending", "in_progress"):
        raise WorkflowError(f"'{step['step_name']}' is already {step['status']}")

    if step["step_type"] == "approval":
        if decision not in ("approve", "reject", "return"):
            raise WorkflowError(f"Illegal decision '{decision}' for an approval step")
        if decision == "return" and step["step_key"] != "qa_review":
            raise WorkflowError("'Return for Investigation' is only valid from QA Review")
        approvers = wfdb.get_step_approvers(step["id"])
        if not approvers:
            raise WorkflowError(f"'{step['step_name']}' has no assigned approver yet")
        if user_id not in {a["user_id"] for a in approvers}:
            raise WorkflowPermissionError("You are not an assigned approver for this step")
    else:
        if decision != "advance":
            raise WorkflowError(f"Illegal decision '{decision}' for an activity step")
        if role not in _eligible_roles(step):
            raise WorkflowPermissionError(f"Role '{role}' is not eligible to advance '{step['step_name']}'")

    now = _now()
    template_steps = wfdb.get_template_steps(instance["template_id"])
    last_order = max(s["step_order"] for s in template_steps)

    if decision in ("approve", "advance"):
        wfdb.update_instance_step(step["id"], {
            "status": "approved", "decided_by": performed_by, "decided_at": now, "comments": comments,
        })
        if step_order >= last_order:
            wfdb.update_instance(instance["id"], {"status": "completed", "completed_at": now})
        else:
            wfdb.update_instance(instance["id"], {"current_step_order": step_order + 1})
        _apply_gate_status(record_type, record_id, _status_after_completing(template_steps, step_order, last_order))
        audit.log(record_type, record_id, f"{step['step_name']}: Approved",
                   reason=comments, detail=f"decided by {performed_by}")

    elif decision == "reject":
        wfdb.update_instance_step(step["id"], {
            "status": "rejected", "decided_by": performed_by, "decided_at": now, "comments": comments,
        })
        wfdb.update_instance(instance["id"], {"status": "rejected", "completed_at": now})
        _apply_gate_status(record_type, record_id, "Rejected")
        audit.log(record_type, record_id, f"{step['step_name']}: Rejected", reason=comments)

    else:  # return
        wfdb.update_instance_step(step["id"], {
            "status": "returned", "decided_by": performed_by, "decided_at": now, "comments": comments,
        })
        target = next((s for s in template_steps if s["step_key"] == "evidence_collection"), None)
        if not target:
            raise WorkflowError("Workflow misconfigured: no 'evidence_collection' step to return to")
        wfdb.update_instance(instance["id"], {"current_step_order": target["step_order"]})
        for inst_step in wfdb.get_instance_steps(instance["id"]):
            if target["step_order"] <= inst_step["step_order"] < step_order and inst_step["status"] == "approved":
                wfdb.update_instance_step(inst_step["id"], {"status": "pending", "decided_by": "", "decided_at": ""})
        _apply_gate_status(record_type, record_id, "Returned for Investigation")
        audit.log(record_type, record_id, f"{step['step_name']}: Returned for further investigation",
                   reason=comments)

    return get_instance_state(record_type, record_id)

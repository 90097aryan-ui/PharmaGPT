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
    mapped = "Draft" if status == "Rejected" else status
    if mapped == "Effective":
        # Document Control redesign (spec §16/§17/§20, corrected): quorum
        # achieved on the final Approval step means the version is
        # 'approved', not Effective — it holds there until BOTH the training
        # gate (>=90% completion, >=1 trainee) has cleared AND the Quality
        # Coordinator / authorized Quality role explicitly releases it (see
        # routes/qms_documents.py::release_document). This module
        # deliberately does not auto-transition to Effective on its own —
        # that would let quorum completion (an Approval decision) or a
        # training record update (any user with training-update access)
        # silently perform what must be a distinct, explicitly authorized
        # release action.
        qdb.update_document(record_id, {"status": "Approved"})
    else:
        qdb.update_document(record_id, {"status": mapped})


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


# ── Document Control redesign — version-linkage hooks ────────────────────────
# Same registry-dispatch shape as STATUS_APPLIERS/CREATOR_LOOKUP above: one
# entry per record_type, absent (no-op) for every module that has no version
# concept (CAPA, Deviation, Change Control are all unaffected — decide_step/
# start_instance call these unconditionally, but the .get() lookup returns
# None for them and nothing fires). Only "document" has an entry. The engine
# itself never references a document-specific step_key or status string —
# that knowledge lives entirely inside these three handler functions.

def _document_version_lookup(record_id: int) -> int | None:
    """Also responsible for forking a fresh revision draft if the
    document's current version is already 'effective' — starting a new
    review cycle against an Effective document (e.g. re-submitting for the
    spec's '1.0 Effective -> 1.1 Revision Draft' case) must fork BEFORE the
    new workflow instance is linked to a version, so the instance points at
    the version that will actually be reviewed, not the outgoing Effective
    one. See qms_document_database.start_new_revision()."""
    from pharmagpt import qms_document_database as qdb
    version = qdb.get_current_version(record_id)
    if not version:
        return None
    if version["status"] == "effective":
        version = qdb.start_new_revision(record_id)
    return version["id"]


CURRENT_VERSION_LOOKUP: dict[str, Callable[[int], int | None]] = {
    "document": _document_version_lookup,
}


def _document_version_on_instance_start(record_id: int, instance: dict) -> None:
    """Submit for Review: the document's current (draft) version moves to
    under_review and records which workflow instance owns this review
    cycle."""
    from pharmagpt import qms_document_database as qdb
    qdb.start_review_cycle_for_version(record_id, instance["id"])


def _document_version_on_step_approved(record_id: int, step: dict) -> None:
    """Review accepted ('under_review') advances the version to
    pending_approval. Quorum/approval achieved on the final Approval step
    ('effective') advances it to 'approved' — NOT 'effective' yet; this
    fires BEFORE _apply_gate_status() (see decide_step/_decide_quorum_step
    call order) specifically so qms_document_database.try_clear_training_gate(),
    called from _apply_document_status(), already sees the version as
    'approved' and can check the training gate immediately rather than
    requiring a second, separate action."""
    from datetime import date
    from pharmagpt import qms_document_database as qdb
    if step.get("step_key") == "under_review":
        qdb.advance_version_to_pending_approval(record_id)
        # Document Control redesign (spec §8): Review Date is captured by
        # the system at the moment the review activity completes, never
        # author-entered. Overwritten on every review cycle (including
        # re-review after a rejection/rework), so it always reflects the
        # MOST RECENT review acceptance, not the first one.
        qdb.update_document(record_id, {"review_date": date.today().isoformat()})
    elif step.get("step_key") == "effective":
        qdb.advance_version_to_approved(record_id)


def _document_version_on_step_rejected(record_id: int, reason: str) -> None:
    """Any Review or Approval rejection: the current version becomes
    permanently immutable (review_rejected/approval_rejected, chosen by its
    own current status — see qms_document_database.reject_and_fork_version),
    the rejection reason is recorded against it, and a brand-new Draft
    version is forked and becomes current. Old votes/approvers never carry
    forward because the next Submit for Review creates an entirely new
    workflow instance (start_instance's own "already in progress" guard
    prevents reusing the rejected one)."""
    from pharmagpt import qms_document_database as qdb
    qdb.reject_and_fork_version(record_id, reason)


VERSION_ON_INSTANCE_START: dict[str, Callable[[int, dict], None]] = {
    "document": _document_version_on_instance_start,
}
VERSION_ON_STEP_APPROVED: dict[str, Callable[[int, dict], None]] = {
    "document": _document_version_on_step_approved,
}
VERSION_ON_STEP_REJECTED: dict[str, Callable[[int, str], None]] = {
    "document": _document_version_on_step_rejected,
}


def _require_comment_on_document_reject(record_type: str, comments: str) -> None:
    """Any Review or Approval rejection on a Document Control record must
    carry a non-empty comment (locked spec requirement) — scoped strictly to
    record_type=='document' so CAPA/Deviation/Change Control's existing
    reject behaviour (empty comment always allowed today) is unchanged."""
    if record_type == "document" and not (comments or "").strip():
        raise WorkflowError("A comment is required to reject this document")


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
        # Configurable quorum approval (Document Control): additive fields,
        # only populated for approval_mode='quorum' steps — every 'any'-mode
        # step (every other module, and Document Control by default) keeps
        # exactly its pre-quorum response shape.
        if s.get("approval_mode") == "quorum":
            votes = wfdb.get_votes(s["id"])
            s["votes"] = votes
            s["votes_cast"] = sum(1 for v in votes if v["decision"] == "approve")
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
                    company_id: str | None, performed_by: str, *,
                    default_quorum: int | None = None) -> dict:
    """Instantiate a fresh workflow run for a record (e.g. on 'Submit for
    Review'). Step 1 is an 'activity' step representing the submission
    itself and is completed immediately by the caller; current_step_order
    advances to step 2.

    `default_quorum` (Document Control only — every other caller omits it):
    when given and > 1, every 'approval' step in this instance is snapshotted
    as approval_mode='quorum' requiring that many distinct approve votes
    (services/workflow_engine.py's decide_step()); omitted or <= 1 reproduces
    today's single-decider 'any' mode exactly."""
    template = wfdb.get_template_by_key(workflow_key)
    if not template:
        raise WorkflowError(f"Unknown workflow template '{workflow_key}'")
    template_steps = wfdb.get_template_steps(template["id"])
    if not template_steps:
        raise WorkflowError(f"Workflow template '{workflow_key}' has no steps")

    existing = wfdb.get_active_instance(record_type, record_id)
    if existing:
        raise WorkflowError("A workflow is already in progress for this record")

    document_version_id = CURRENT_VERSION_LOOKUP.get(record_type, lambda _r: None)(record_id)
    instance = wfdb.create_instance(template["id"], record_type, record_id, company_id,
                                     document_version_id=document_version_id)
    for t_step in template_steps:
        # Document Control redesign (Phase 3): quorum_eligible (default 1)
        # restricts which approval steps may ever be snapshotted as quorum
        # mode. Document Control's own seed sets this 0 on its Review step
        # (services/qms_database.py) so Review stays single-reviewer even
        # when a document's approval_quorum override is set — only the
        # final Approval step is ever quorum-gated. Every other module's
        # steps default to 1 (unchanged) and none of them ever pass
        # default_quorum > 1 in the first place, so this is a no-op for
        # CAPA/Deviation/Change Control regardless.
        use_quorum = (t_step["step_type"] == "approval" and t_step.get("quorum_eligible", 1)
                      and default_quorum and default_quorum > 1)
        wfdb.create_instance_step(
            instance["id"], t_step,
            approval_mode="quorum" if use_quorum else "any",
            required_quorum=default_quorum if use_quorum else None,
        )

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
    version_start_hook = VERSION_ON_INSTANCE_START.get(record_type)
    if version_start_hook:
        version_start_hook(record_id, instance)
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


def _decide_quorum_step(record_type: str, record_id: int, instance: dict, step: dict, decision: str, *,
                         user_id: str, performed_by: str, comments: str) -> dict:
    """Configurable-quorum approval (Document Control): a step in
    approval_mode='quorum' requires `required_quorum` distinct approve votes
    before it advances. A single reject vote immediately rejects the step
    (same record-status effect as the 'any'-mode reject path below, via
    _apply_gate_status's existing "Rejected" -> "Draft" mapping) and clears
    every vote cast so far, so a resubmission starts its quorum count fresh —
    mirrors the 'any'-mode single-decider reject, just for N voters instead
    of one."""
    approvers = wfdb.get_step_approvers(step["id"])
    if not approvers:
        raise WorkflowError(f"'{step['step_name']}' has no assigned approver yet")
    if user_id not in {a["user_id"] for a in approvers}:
        raise WorkflowPermissionError("You are not an assigned approver for this step")
    if wfdb.has_voted(step["id"], user_id):
        raise WorkflowError("You have already voted on this step")
    if decision == "reject":
        _require_comment_on_document_reject(record_type, comments)

    wfdb.record_vote(step["id"], user_id, decision, comments, instance.get("company_id"))
    now = _now()

    if decision == "reject":
        wfdb.clear_votes(step["id"])
        wfdb.update_instance_step(step["id"], {
            "status": "rejected", "decided_by": performed_by, "decided_at": now, "comments": comments,
        })
        wfdb.update_instance(instance["id"], {"status": "rejected", "completed_at": now})
        _apply_gate_status(record_type, record_id, "Rejected")
        version_reject_hook = VERSION_ON_STEP_REJECTED.get(record_type)
        if version_reject_hook:
            version_reject_hook(record_id, comments)
        audit.log(record_type, record_id, f"{step['step_name']}: Rejected (quorum vote)",
                   reason=comments, detail=f"decided by {performed_by}")
        return get_instance_state(record_type, record_id)

    votes_cast = sum(1 for v in wfdb.get_votes(step["id"]) if v["decision"] == "approve")
    required = step.get("required_quorum") or 1
    audit.log(record_type, record_id, f"{step['step_name']}: Vote recorded ({votes_cast}/{required})",
              detail=f"voted by {performed_by}")
    if votes_cast < required:
        return get_instance_state(record_type, record_id)

    template_steps = wfdb.get_template_steps(instance["template_id"])
    last_order = max(s["step_order"] for s in template_steps)
    step_order = step["step_order"]
    wfdb.update_instance_step(step["id"], {
        "status": "approved", "decided_by": performed_by, "decided_at": now, "comments": comments,
    })
    if step_order >= last_order:
        wfdb.update_instance(instance["id"], {"status": "completed", "completed_at": now})
    else:
        wfdb.update_instance(instance["id"], {"current_step_order": step_order + 1})
    # Version hook runs BEFORE _apply_gate_status (Document Control redesign,
    # Phase 4): the training-gate check inside _apply_document_status needs
    # the version already moved to 'approved' to see it.
    version_approved_hook = VERSION_ON_STEP_APPROVED.get(record_type)
    if version_approved_hook:
        version_approved_hook(record_id, step)
    _apply_gate_status(record_type, record_id, _status_after_completing(template_steps, step_order, last_order))
    audit.log(record_type, record_id, f"{step['step_name']}: Approved (quorum met {votes_cast}/{required})",
              reason=comments, detail=f"decided by {performed_by}")
    return get_instance_state(record_type, record_id)


def decide_step(record_type: str, record_id: int, step_order: int, decision: str, *,
                 user_id: str, role: str, performed_by: str, comments: str = "",
                 return_to: str = "") -> dict:
    """Decide the record's *current* workflow step.

    decision:
      'advance'          — step_type='activity'; caller's `role` must be in
                            the step's eligible_roles (no named assignment).
      'approve'/'reject' — step_type='approval'; caller's `user_id` must be
                            one of the step's assigned approvers.
      'return'           — step_type='approval'. With no `return_to`, only
                            legal from the 'qa_review' step and always sends
                            the record back to 'evidence_collection' (Phase 1
                            deviation behaviour, unchanged). A caller may pass
                            an explicit `return_to` step_key to return from
                            any other approval step to a different target —
                            e.g. CAPA's Effectiveness Verification step
                            routing back to Root Cause Analysis or CAPA
                            Planning depending on the verification result
                            (routes/qms_capa.py). The record's status then
                            becomes the target step's own gate_status rather
                            than the generic "Returned for Investigation"
                            label, since that label isn't part of every
                            module's status vocabulary.
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

    if step["step_type"] == "approval" and step.get("approval_mode") == "quorum":
        if decision not in ("approve", "reject"):
            raise WorkflowError(f"Illegal decision '{decision}' for a quorum approval step")
        return _decide_quorum_step(record_type, record_id, instance, step, decision,
                                    user_id=user_id, performed_by=performed_by, comments=comments)

    if step["step_type"] == "approval":
        if decision not in ("approve", "reject", "return"):
            raise WorkflowError(f"Illegal decision '{decision}' for an approval step")
        if decision == "return" and not return_to and step["step_key"] != "qa_review":
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

    if decision == "reject":
        _require_comment_on_document_reject(record_type, comments)

    if decision in ("approve", "advance"):
        wfdb.update_instance_step(step["id"], {
            "status": "approved", "decided_by": performed_by, "decided_at": now, "comments": comments,
        })
        if step_order >= last_order:
            wfdb.update_instance(instance["id"], {"status": "completed", "completed_at": now})
        else:
            wfdb.update_instance(instance["id"], {"current_step_order": step_order + 1})
        # Version hook runs BEFORE _apply_gate_status — see the identical
        # comment in _decide_quorum_step above.
        version_approved_hook = VERSION_ON_STEP_APPROVED.get(record_type)
        if version_approved_hook:
            version_approved_hook(record_id, step)
        _apply_gate_status(record_type, record_id, _status_after_completing(template_steps, step_order, last_order))
        audit.log(record_type, record_id, f"{step['step_name']}: Approved",
                   reason=comments, detail=f"decided by {performed_by}")

    elif decision == "reject":
        wfdb.update_instance_step(step["id"], {
            "status": "rejected", "decided_by": performed_by, "decided_at": now, "comments": comments,
        })
        wfdb.update_instance(instance["id"], {"status": "rejected", "completed_at": now})
        _apply_gate_status(record_type, record_id, "Rejected")
        version_reject_hook = VERSION_ON_STEP_REJECTED.get(record_type)
        if version_reject_hook:
            version_reject_hook(record_id, comments)
        audit.log(record_type, record_id, f"{step['step_name']}: Rejected", reason=comments)

    else:  # return
        wfdb.update_instance_step(step["id"], {
            "status": "returned", "decided_by": performed_by, "decided_at": now, "comments": comments,
        })
        target_key = return_to or "evidence_collection"
        target = next((s for s in template_steps if s["step_key"] == target_key), None)
        if not target:
            raise WorkflowError(f"Workflow misconfigured: no '{target_key}' step to return to")
        wfdb.update_instance(instance["id"], {"current_step_order": target["step_order"]})
        for inst_step in wfdb.get_instance_steps(instance["id"]):
            if target["step_order"] <= inst_step["step_order"] < step_order and inst_step["status"] == "approved":
                wfdb.update_instance_step(inst_step["id"], {"status": "pending", "decided_by": "", "decided_at": ""})
        new_status = target["gate_status"] if return_to else "Returned for Investigation"
        _apply_gate_status(record_type, record_id, new_status)
        audit.log(record_type, record_id, f"{step['step_name']}: Returned for further investigation",
                   reason=comments, detail=f"Returned to '{target['step_name']}'" if return_to else "")

    return get_instance_state(record_type, record_id)

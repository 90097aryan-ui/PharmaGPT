"""
services/workflow_context.py — a single object describing "where a record
stands in its Workflow Engine instance right now," for the shared frontend
review panel to consume instead of juggling separate instance/step/user
parameters.

Read-only and additive: builds on top of services/workflow_engine.py's
existing get_instance_state(), no engine change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class WorkflowContext:
    record_type: str
    record_id: int
    workflow_instance: dict | None
    current_step: dict | None
    current_user: dict  # {"user_id": ..., "role": ..., "display_name": ...}

    def to_dict(self) -> dict:
        return asdict(self)


def build_workflow_context(record_type: str, record_id: int, tenant) -> WorkflowContext:
    from pharmagpt.services import workflow_engine as wfe

    state = wfe.get_instance_state(record_type, record_id)
    instance = state["instance"]
    steps = state["steps"]
    current_step = None
    if instance:
        current_step = next(
            (s for s in steps if s["step_order"] == instance["current_step_order"]), None
        )
    return WorkflowContext(
        record_type=record_type,
        record_id=record_id,
        workflow_instance=instance,
        current_step=current_step,
        current_user={
            "user_id": tenant.user_id,
            "role": tenant.role,
            "display_name": tenant.display_name or tenant.email,
        },
    )

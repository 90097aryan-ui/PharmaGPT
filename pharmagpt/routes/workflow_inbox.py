"""
routes/workflow_inbox.py — Universal Workflow Inbox: every pending Workflow
Engine step assigned to the logged-in user, across every module wired to
services/workflow_engine.py (Deviations, CAPA, Change Control, SOP today;
any future module automatically once it has a template + a
services/workflow_registry.py entry).

Reads only qms_workflow_database.py's generic tables (via
list_my_pending_steps/list_recent_decisions) plus workflow_registry.py's
small module-lookup table for display fields (title, record number, route,
icon) — no module-specific business logic lives here. Never decides a step;
"Review" always routes into each module's own /workflow/steps/<order>/decide
route (see routes/qms_deviations.py, qms_capa.py, qms_change_control.py,
qms_documents.py) so the engine is never bypassed.

Routes
------
GET /workflow/inbox        pending steps assigned to the logged-in user
GET /workflow/inbox/stats  dashboard/notification counts + recent decisions
"""

from flask import Blueprint, g, jsonify

from pharmagpt import qms_workflow_database as wfdb
from pharmagpt import tenancy
from pharmagpt.services import workflow_registry

bp = Blueprint("workflow_inbox", __name__, url_prefix="/workflow")

# No due_date/priority column exists anywhere in the schema (a schema change
# is out of scope) — "Overdue" is a labeled heuristic on pending-step age,
# not a real configured SLA.
_OVERDUE_DAYS = 5


def _days_pending(pending_since: str) -> float | None:
    if not pending_since:
        return None
    from datetime import datetime, timezone
    try:
        started = datetime.fromisoformat(pending_since.replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - started).total_seconds() / 86400
    except ValueError:
        return None


def _assigned_to(step: dict) -> list[str]:
    if step["step_type"] == "approval":
        approvers = wfdb.get_step_approvers(step["step_id"])
        return [a.get("display_name") or a["user_id"] for a in approvers]
    return [f"Any {r}" for r in (step.get("eligible_roles") or "").split(",") if r]


def _enrich(step: dict) -> dict | None:
    descriptor = workflow_registry.describe(step["record_type"])
    if not descriptor:
        return None
    record = descriptor.get_record(step["record_id"])
    if not record:
        return None
    days_pending = _days_pending(step["pending_since"])
    return {
        "module": descriptor.record_type,
        "module_icon": descriptor.icon,
        "record_id": step["record_id"],
        "record_number": record.get(descriptor.number_field, ""),
        "title": record.get(descriptor.title_field, ""),
        "route": f"{descriptor.route_prefix}/{step['record_id']}",
        "current_step_order": step["step_order"],
        "current_step_name": step["step_name"],
        "step_type": step["step_type"],
        "assigned_to": _assigned_to(step),
        "status": "In Progress",
        "due_date": None,  # not tracked anywhere in the schema
        "priority": "Normal",  # not tracked anywhere in the schema
        "submitted_by": record.get("created_by") or record.get("initiator") or "",
        "submitted_date": record.get("created_at", ""),
        "pending_since": step["pending_since"],
        "days_pending": round(days_pending, 1) if days_pending is not None else None,
        "overdue": bool(days_pending is not None and days_pending >= _OVERDUE_DAYS),
    }


@bp.route("/inbox", methods=["GET"])
def get_inbox():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    rows = wfdb.list_my_pending_steps(g.tenant.company_id, g.tenant.user_id, g.tenant.role)
    items = [item for item in (_enrich(r) for r in rows) if item]
    return jsonify(items)


@bp.route("/inbox/stats", methods=["GET"])
def get_inbox_stats():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    rows = wfdb.list_my_pending_steps(g.tenant.company_id, g.tenant.user_id, g.tenant.role)
    items = [item for item in (_enrich(r) for r in rows) if item]

    sig = tenancy.signing_identity(g.tenant)
    recent = wfdb.list_recent_decisions(g.tenant.company_id, sig["performed_by"], limit=10)

    return jsonify({
        "my_pending_count": len(items),
        "awaiting_my_decision_count": sum(1 for i in items if i["step_type"] == "approval"),
        "overdue_count": sum(1 for i in items if i["overdue"]),
        "recent_decisions": recent,
    })

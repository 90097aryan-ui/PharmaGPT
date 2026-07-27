"""
scripts/backfill_deviation_status_v2.py — One-time local remap of existing
`qms_deviations.status` values from the old flat 9-status vocabulary to the
Phase 1 workflow-gated vocabulary (services/workflow_engine.py,
DEVIATION_INVESTIGATION_V1 template), and synthesis of a completed
`qms_workflow_instance` (+ instance_steps) for each remapped row so its
Investigation-tab lock state and workflow history stay consistent going
forward — see PHASE1_INVESTIGATION_PLAN.md.

Local SQLite only (pharmagpt/database.py's DB_PATH) — no Postgres/service-role
call, unlike scripts/backfill_qms.py's Phase 3.5 dual-write backfill, which
this script is independent of.

Each remapped row is treated as though it had already cleared every workflow
step up to and including the one implied by its old status (decided_by=
'system-migration-v2', decided_at=now) — conservatively, never granting a
step beyond what the old status already implied the record had reached.

Idempotent: a deviation that already has a workflow instance (i.e. was
created after this migration, or already migrated) is skipped.

Usage:
    python scripts/backfill_deviation_status_v2.py [--dry-run]
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402
from pharmagpt import qms_deviation_database as ddb  # noqa: E402
from pharmagpt import qms_workflow_database as wfdb  # noqa: E402

WORKFLOW_KEY = "DEVIATION_INVESTIGATION_V1"

# old_status -> (completed_step_order, new_status)
# new_status is the gate_status of completed_step_order + 1 (the step the
# record is now waiting on), matching workflow_engine._status_after_completing,
# except where noted.
_OLD_STATUS_MAP = {
    "Initiated":             (0, "Draft"),                # no instance synthesized
    "Under Investigation":   (5, "Evidence Collection"),
    "Impact Assessed":       (5, "Evidence Collection"),
    "Risk Assessed":         (5, "Evidence Collection"),
    "Root Cause Identified": (10, "CAPA Recommendation"),
    "CAPA Assigned":         (11, "QA Review"),
    "QA Review":             (11, "QA Review"),
    "Approved":              (13, "Effectiveness Check"),
    "Closed":                (15, "Closed"),               # terminal — instance 'completed'
    "Rejected":              (0, "Rejected"),               # instance 'rejected', no steps synthesized
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate_deviation(row: dict, template_id: int, template_steps: list[dict], dry_run: bool) -> str:
    old_status = row.get("status", "")
    mapping = _OLD_STATUS_MAP.get(old_status)
    if mapping is None:
        return f"skip (unrecognized status {old_status!r})"

    completed_step_order, new_status = mapping

    if wfdb.get_latest_instance("deviation", row["id"]):
        return "skip (already has a workflow instance)"

    if dry_run:
        return f"would remap {old_status!r} -> {new_status!r} (completed through step {completed_step_order})"

    if old_status == "Initiated":
        ddb.update_deviation(row["id"], {"status": new_status})
        return f"remapped {old_status!r} -> {new_status!r} (no instance — still Draft)"

    instance = wfdb.create_instance(template_id, "deviation", row["id"], row.get("company_id"))
    now = _now()
    last_order = max(s["step_order"] for s in template_steps)

    for t_step in template_steps:
        inst_step = wfdb.create_instance_step(instance["id"], t_step)
        if old_status == "Rejected":
            continue  # leave every step 'pending'; only the instance itself is marked rejected below
        if t_step["step_order"] <= completed_step_order:
            wfdb.update_instance_step(inst_step["id"], {
                "status": "approved", "decided_by": "system-migration-v2", "decided_at": now,
                "comments": "Backfilled from pre-Phase-1 status history",
            })

    if old_status == "Rejected":
        wfdb.update_instance(instance["id"], {"status": "rejected", "completed_at": now})
    elif completed_step_order >= last_order:
        wfdb.update_instance(instance["id"], {"status": "completed", "completed_at": now})
    else:
        wfdb.update_instance(instance["id"], {"current_step_order": completed_step_order + 1})

    ddb.update_deviation(row["id"], {"status": new_status})
    return f"remapped {old_status!r} -> {new_status!r} (completed through step {completed_step_order})"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    db.init_db()  # ensures the new workflow tables + seeded template exist
    template = wfdb.get_template_by_key(WORKFLOW_KEY)
    if not template:
        print(f"ERROR: workflow template {WORKFLOW_KEY!r} not found — did init_db() seed it?")
        sys.exit(1)
    template_steps = wfdb.get_template_steps(template["id"])

    rows = ddb.get_all_deviations(company_id=None)
    print(f"Found {len(rows)} deviation(s).")
    for row in rows:
        result = migrate_deviation(row, template["id"], template_steps, args.dry_run)
        print(f"  #{row['id']} {row.get('deviation_number', '')}: {result}")


if __name__ == "__main__":
    main()

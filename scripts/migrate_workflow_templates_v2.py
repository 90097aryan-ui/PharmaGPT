"""
scripts/migrate_workflow_templates_v2.py — reconcile the CAPA/Change
Control/Document Workflow Engine templates against their current code-level
definitions (qms_database.py's QMS_SCHEMA).

Context: qms_workflow_templates/qms_workflow_template_steps are seeded via
`INSERT OR IGNORE` in QMS_SCHEMA (executed by database.py::init_db() on
every app start) — idempotent for a brand-new database, but a no-op on a
database that already has a workflow_key's rows from an earlier version of
this file (e.g. DOCUMENT_WORKFLOW_V1 was redesigned from 4 steps to 3 during
development). This script deletes and re-inserts the *template step* rows
for the three named workflow_keys so an already-initialized database picks
up the current step definitions.

Safe to run any time, including on a database with in-progress instances:
qms_workflow_instance_steps snapshots each step's fields at
start_instance()/create_instance_step() time (see qms_workflow_database.py)
rather than referencing the template live, so already-running instances are
completely unaffected — only future start_instance() calls see the updated
step list. The template *row* itself (workflow_key) is left untouched, only
its step rows are refreshed.

Usage:
    python scripts/migrate_workflow_templates_v2.py [--dry-run]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402
from pharmagpt.database import get_connection  # noqa: E402

WORKFLOW_KEYS = ("CAPA_WORKFLOW_V1", "CHANGE_CONTROL_WORKFLOW_V1", "DOCUMENT_WORKFLOW_V1")


def reconcile(workflow_key: str, dry_run: bool) -> str:
    conn = get_connection()
    template = conn.execute(
        "SELECT * FROM qms_workflow_templates WHERE workflow_key = ?", (workflow_key,)
    ).fetchone()
    if not template:
        conn.close()
        return "skip (template not seeded yet — init_db() will create it fresh)"

    existing_steps = conn.execute(
        "SELECT * FROM qms_workflow_template_steps WHERE template_id = ? ORDER BY step_order", (template["id"],)
    ).fetchall()

    if dry_run:
        conn.close()
        return f"would delete {len(existing_steps)} existing step row(s) and re-seed from QMS_SCHEMA"

    conn.execute("DELETE FROM qms_workflow_template_steps WHERE template_id = ?", (template["id"],))
    conn.commit()
    conn.close()
    return f"deleted {len(existing_steps)} stale step row(s), pending re-seed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    db.init_db()
    for key in WORKFLOW_KEYS:
        print(f"{key}: {reconcile(key, args.dry_run)}")

    if not args.dry_run:
        # Re-run the (idempotent) schema script once at the end — with the
        # stale step rows gone, its INSERT OR IGNORE for each workflow_key's
        # steps now actually inserts the current definitions.
        db.init_db()
        print("Re-seeded current step definitions from QMS_SCHEMA.")


if __name__ == "__main__":
    main()

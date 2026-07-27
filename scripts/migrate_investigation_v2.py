"""
scripts/migrate_investigation_v2.py — One-time local backfill for the
architecture refactor (Workflow vs. Investigation separation,
PHASE1_REFACTOR_PLAN.md §6).

Any deviation already running against the old DEVIATION_INVESTIGATION_V1
workflow template is left exactly as-is — its workflow instance is not
touched, and new deviations already point at DEVIATION_LIFECYCLE_V2 (see
routes/qms_deviations.py::WORKFLOW_KEY). This script only copies the old
qms_deviation_investigation row's content (fishbone/5-Why/timeline/root
cause, produced by the pre-refactor '/investigate' AI Investigation
Assistant) into the new Investigation Case tables, so a deviation that
already has investigation data doesn't show an empty Investigation Case:

  - timeline_data           -> qms_investigation_timeline_events rows
  - root_cause_statement    -> qms_investigation_root_cause.probable_cause
  - fishbone/5-Why summary  -> qms_investigation_root_cause.probable_cause_rationale

qms_deviation_investigation itself is left untouched (read-only source, not
dropped — a later cleanup phase can retire it once the new tables are
proven).

Idempotent: a deviation that already has any qms_investigation_timeline_events
or qms_investigation_root_cause row is skipped.

Usage:
    python scripts/migrate_investigation_v2.py [--dry-run]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402
from pharmagpt import qms_deviation_database as ddb  # noqa: E402
from pharmagpt import qms_investigation_database as idb  # noqa: E402

RECORD_TYPE = "deviation"


def _fishbone_five_why_summary(investigation: dict) -> str:
    parts = []
    fb = investigation.get("fishbone_data") or {}
    for category in ("man", "machine", "method", "material", "measurement", "environment"):
        items = fb.get(category) or []
        if items:
            parts.append(f"{category.title()}: " + "; ".join(items))
    fw = investigation.get("five_why_data") or []
    for i, entry in enumerate(fw, 1):
        if entry.get("question") or entry.get("answer"):
            parts.append(f"Why {i}: {entry.get('question', '')} -> {entry.get('answer', '')}")
    return "\n".join(parts)


def migrate_deviation(deviation_id: int, dry_run: bool) -> str:
    investigation = ddb.get_investigation(deviation_id)
    if not investigation:
        return "skip (no pre-refactor investigation data)"

    already_migrated = (
        idb.get_timeline_events(RECORD_TYPE, deviation_id)
        or idb.get_root_cause(RECORD_TYPE, deviation_id)
    )
    if already_migrated:
        return "skip (already migrated)"

    timeline = investigation.get("timeline_data") or []
    root_cause_statement = investigation.get("root_cause_statement") or ""
    rationale = _fishbone_five_why_summary(investigation)

    if dry_run:
        return f"would migrate {len(timeline)} timeline event(s)" + (
            " + root cause" if root_cause_statement else ""
        )

    for entry in timeline:
        idb.add_timeline_event(RECORD_TYPE, deviation_id, {
            "event_type": "Deviation",
            "event_datetime": entry.get("datetime", ""),
            "description": entry.get("event", ""),
            "source": "manual",
        })

    if root_cause_statement or rationale:
        idb.upsert_root_cause(RECORD_TYPE, deviation_id, {
            "probable_cause": root_cause_statement,
            "probable_cause_rationale": rationale,
        })

    return f"migrated {len(timeline)} timeline event(s)" + (" + root cause" if root_cause_statement else "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    db.init_db()
    rows = ddb.get_all_deviations(company_id=None)
    print(f"Found {len(rows)} deviation(s).")
    for row in rows:
        result = migrate_deviation(row["id"], args.dry_run)
        print(f"  #{row['id']} {row.get('deviation_number', '')}: {result}")


if __name__ == "__main__":
    main()

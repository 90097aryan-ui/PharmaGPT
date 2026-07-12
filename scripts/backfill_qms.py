"""
scripts/backfill_qms.py — One-time Phase 3.5 backfill: SQLite
deviations/capas/change_controls/risk_assessments -> Postgres
deviations/capas/change_controls/risk_assessments, under the same
bootstrap company Phase 3.2-3.4 use, docs/PHASE3_EXECUTION_PLAN.md.

CLI-only, service-role key — same administrative-script convention as the
other Phase 3 backfill scripts. Request-handling code (pharmagpt/db/
qms_repo.py) always acts as the authenticated caller instead.

Only migrates the flat fields with a column in the target schema (title,
status, project_id) — the current build's richer sub-structures
(investigation, impact, CAPA actions/effectiveness, change-control impact/
actions, risk items/library/actions) have no table in the frozen target
schema and are intentionally NOT migrated; see pharmagpt/db/qms_repo.py's
module docstring.

Idempotent: rows with a postgres_id already set are skipped. Safe to
re-run after a partial failure.

Usage:
    python scripts/backfill_qms.py
"""

import os
import sys

from dotenv import load_dotenv
from supabase import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402
from pharmagpt import qms_capa_database as cdb  # noqa: E402
from pharmagpt import qms_change_control_database as ccdb  # noqa: E402
from pharmagpt import qms_deviation_database as ddb  # noqa: E402
from pharmagpt import risk_database as rdb  # noqa: E402
from scripts.backfill_projects import (  # noqa: E402
    BackfillError,
    build_service_role_client,
    find_or_create_bootstrap_company,
    load_config,
)

_TABLE_BY_RECORD_TYPE = {
    "deviation": "deviations",
    "capa": "capas",
    "change_control": "change_controls",
    "risk_assessment": "risk_assessments",
}


def _resolve_project_postgres_id(project_id) -> str | None:
    if not project_id:
        return None
    project = db.get_project(project_id)
    return (project or {}).get("postgres_id")


def backfill_record_type(client: Client, company_id: str, record_type: str,
                          sqlite_rows: list[dict], set_postgres_id_fn) -> dict:
    """Generic backfill for one of the four Phase 3.5 record types. Returns
    {"migrated": int, "skipped_already_migrated": int}."""
    table = _TABLE_BY_RECORD_TYPE[record_type]
    migrated = 0
    skipped = 0

    for row in sqlite_rows:
        if row.get("postgres_id"):
            skipped += 1
            continue

        payload = {
            "company_id": company_id,
            "title": row.get("title") or "Untitled",
            "status": row.get("status") or "open",
            "project_id": _resolve_project_postgres_id(row.get("project_id")),
        }
        inserted = client.table(table).insert(payload).execute()
        set_postgres_id_fn(row["id"], inserted.data[0]["id"])
        migrated += 1

    return {"migrated": migrated, "skipped_already_migrated": skipped}


def main() -> int:
    load_dotenv()

    try:
        config = load_config(os.environ)
    except BackfillError as exc:
        print(f"Backfill failed: {exc}", file=sys.stderr)
        return 1

    client = build_service_role_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
    company_id = find_or_create_bootstrap_company(client, config["BOOTSTRAP_COMPANY_NAME"])
    print(f"Bootstrap company: {config['BOOTSTRAP_COMPANY_NAME']!r} ({company_id})")

    jobs = (
        ("deviation", ddb.get_all_deviations(), ddb.set_deviation_postgres_id),
        ("capa", cdb.get_all_capas(), cdb.set_capa_postgres_id),
        ("change_control", ccdb.get_all_change_controls(), ccdb.set_change_control_postgres_id),
        ("risk_assessment", rdb.get_all_assessments(), rdb.set_assessment_postgres_id),
    )

    for record_type, rows, setter in jobs:
        summary = backfill_record_type(client, company_id, record_type, rows, setter)
        print(
            f"{record_type}: migrated {summary['migrated']}; "
            f"{summary['skipped_already_migrated']} already migrated, skipped."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
scripts/check_qms_parity.py — Phase 3.5 parity check
(docs/PHASE3_EXECUTION_PLAN.md).

Compares every SQLite deviation/capa/change_control/risk_assessment row
that has been dual-written or backfilled (postgres_id is set) against its
Postgres counterpart on the fields dual-write actually keeps in sync
(title, status, project_id -> resolved via projects.postgres_id). Read-only.

CLI-only, service-role key — same convention as the other Phase 3 scripts.

Usage:
    python scripts/check_qms_parity.py

Exit code 0 if zero drift found, 1 otherwise.
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
from scripts.check_projects_parity import (  # noqa: E402
    REQUIRED_ENV_VARS,
    ParityCheckError,
    build_service_role_client,
    load_config,
)

_TABLE_BY_RECORD_TYPE = {
    "deviation": "deviations",
    "capa": "capas",
    "change_control": "change_controls",
    "risk_assessment": "risk_assessments",
}


def _normalize(value):
    return value if value else None


def _resolve_project_postgres_id(project_id) -> str | None:
    if not project_id:
        return None
    project = db.get_project(project_id)
    return (project or {}).get("postgres_id")


def check_record_type_parity(client: Client, record_type: str, sqlite_rows: list[dict]) -> list[dict]:
    table = _TABLE_BY_RECORD_TYPE[record_type]
    drifted = []

    for row in sqlite_rows:
        postgres_id = row.get("postgres_id")
        if not postgres_id:
            continue

        result = client.table(table).select("*").eq("id", postgres_id).maybe_single().execute()
        pg_row = result.data if result else None

        if pg_row is None:
            drifted.append({
                "record_type": record_type, "sqlite_id": row["id"], "postgres_id": postgres_id,
                "issue": "missing_in_postgres",
            })
            continue

        diffs = {}
        if _normalize(row.get("title")) != _normalize(pg_row.get("title")):
            diffs["title"] = {"sqlite": row.get("title"), "postgres": pg_row.get("title")}
        if _normalize(row.get("status")) != _normalize(pg_row.get("status")):
            diffs["status"] = {"sqlite": row.get("status"), "postgres": pg_row.get("status")}

        expected_project_postgres_id = _resolve_project_postgres_id(row.get("project_id"))
        if _normalize(expected_project_postgres_id) != _normalize(pg_row.get("project_id")):
            diffs["project_id"] = {
                "sqlite_resolved": expected_project_postgres_id, "postgres": pg_row.get("project_id"),
            }

        if diffs:
            drifted.append({
                "record_type": record_type, "sqlite_id": row["id"], "postgres_id": postgres_id, "diffs": diffs,
            })

    return drifted


def check_qms_parity(client: Client) -> list[dict]:
    drifted = []
    drifted += check_record_type_parity(client, "deviation", ddb.get_all_deviations())
    drifted += check_record_type_parity(client, "capa", cdb.get_all_capas())
    drifted += check_record_type_parity(client, "change_control", ccdb.get_all_change_controls())
    drifted += check_record_type_parity(client, "risk_assessment", rdb.get_all_assessments())
    return drifted


def main() -> int:
    load_dotenv()

    try:
        config = load_config(os.environ)
    except ParityCheckError as exc:
        print(f"Parity check failed: {exc}", file=sys.stderr)
        return 1

    client = build_service_role_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
    drifted = check_qms_parity(client)

    if drifted:
        print(f"PARITY CHECK FAILED: {len(drifted)} record(s) drifted:")
        for entry in drifted:
            print(f"  {entry}")
        return 1

    print("Parity check passed: 0 drift across all dual-written/backfilled QMS records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

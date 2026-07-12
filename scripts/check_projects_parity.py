"""
scripts/check_projects_parity.py — Phase 3.2 parity check
(docs/PHASE3_EXECUTION_PLAN.md).

Compares every SQLite `projects` row that has been dual-written or
backfilled (postgres_id is set) against its Postgres counterpart on the
fields that have a home in the target schema. Read-only — makes no writes
to either database. Meant to be run periodically during the dual-write
Staging soak the plan's deployment checkpoints require before a flag can
be flipped to a read-cutover state.

CLI-only, service-role key — same administrative-script convention as
scripts/bootstrap_super_admin.py and scripts/backfill_projects.py.

Usage:
    python scripts/check_projects_parity.py

Exit code 0 if zero drift found, 1 otherwise (CI/cron-friendly).
"""

import os
import sys

from dotenv import load_dotenv
from supabase import Client, create_client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402

REQUIRED_ENV_VARS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
FIELDS_TO_COMPARE = ("name", "status", "target_date", "risk_category",
                     "protocol_number", "report_number")


class ParityCheckError(Exception):
    """Raised for any condition that should stop the parity check script."""


def load_config(env: dict) -> dict:
    config = {name: env.get(name) for name in REQUIRED_ENV_VARS}
    missing = [name for name in REQUIRED_ENV_VARS if not config[name]]
    if missing:
        raise ParityCheckError("Missing required .env values: " + ", ".join(missing))
    return config


def build_service_role_client(supabase_url: str, service_role_key: str) -> Client:
    """Administrative, CLI-only. Never call this pattern from
    request-handling code."""
    return create_client(supabase_url, service_role_key)


def _normalize(value):
    """None and "" are the same absence of a value across SQLite/Postgres —
    compare on that basis rather than flagging a false-positive drift."""
    return value if value else None


def check_projects_parity(client: Client) -> list[dict]:
    """Return one entry per project that has drifted or gone missing.
    Projects never dual-written/backfilled (no postgres_id yet) are not a
    parity concern and are skipped, not flagged."""
    drifted = []
    for project in db.get_all_projects():
        postgres_id = project.get("postgres_id")
        if not postgres_id:
            continue

        result = (
            client.table("projects").select("*").eq("id", postgres_id).maybe_single().execute()
        )
        pg_row = result.data if result else None

        if pg_row is None:
            drifted.append({
                "sqlite_id": project["id"],
                "postgres_id": postgres_id,
                "issue": "missing_in_postgres",
            })
            continue

        diffs = {}
        for field in FIELDS_TO_COMPARE:
            sqlite_val = _normalize(project.get(field))
            pg_val = _normalize(pg_row.get(field))
            if str(sqlite_val) != str(pg_val):
                diffs[field] = {"sqlite": sqlite_val, "postgres": pg_val}

        if diffs:
            drifted.append({
                "sqlite_id": project["id"],
                "postgres_id": postgres_id,
                "diffs": diffs,
            })

    return drifted


def main() -> int:
    load_dotenv()

    try:
        config = load_config(os.environ)
    except ParityCheckError as exc:
        print(f"Parity check failed: {exc}", file=sys.stderr)
        return 1

    client = build_service_role_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
    drifted = check_projects_parity(client)

    if drifted:
        print(f"PARITY CHECK FAILED: {len(drifted)} project(s) drifted:")
        for entry in drifted:
            print(f"  {entry}")
        return 1

    print("Parity check passed: 0 drift across all dual-written/backfilled projects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

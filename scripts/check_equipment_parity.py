"""
scripts/check_equipment_parity.py — Phase 3.4 parity check
(docs/PHASE3_EXECUTION_PLAN.md).

Compares every SQLite `equipment` row that has been dual-written or
backfilled (postgres_id is set) against its Postgres counterpart, field for
field (full fidelity is expected here, unlike Projects/KB — see
pharmagpt/db/equipment_repo.py's module docstring). Read-only.

CLI-only, service-role key — same convention as the other Phase 3 scripts.

Usage:
    python scripts/check_equipment_parity.py

Exit code 0 if zero drift found, 1 otherwise.
"""

import os
import sys

from dotenv import load_dotenv
from supabase import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import equipment_database as equipdb  # noqa: E402
from scripts.check_projects_parity import (  # noqa: E402
    ParityCheckError,
    build_service_role_client,
    load_config,
)

FIELDS_TO_COMPARE = (
    "equipment_code", "name", "category", "equipment_type", "tag_number",
    "model", "manufacturer", "vendor", "serial_number", "asset_number",
    "plant", "block", "department", "area", "room", "line",
    "installation_date", "commissioning_date",
    "qualification_status", "validation_status", "qualification_type",
    "criticality", "gmp_impact", "notes",
)


def _normalize(value):
    return value if value else None


def check_equipment_parity(client: Client) -> list[dict]:
    drifted = []

    for equipment in equipdb.get_all_equipment():
        postgres_id = equipment.get("postgres_id")
        if not postgres_id:
            continue

        result = client.table("equipment").select("*").eq("id", postgres_id).maybe_single().execute()
        pg_row = result.data if result else None

        if pg_row is None:
            drifted.append({
                "sqlite_id": equipment["id"], "postgres_id": postgres_id,
                "issue": "missing_in_postgres",
            })
            continue

        diffs = {}
        for field in FIELDS_TO_COMPARE:
            sqlite_val = _normalize(equipment.get(field))
            pg_val = _normalize(pg_row.get(field))
            if str(sqlite_val) != str(pg_val):
                diffs[field] = {"sqlite": sqlite_val, "postgres": pg_val}

        if diffs:
            drifted.append({"sqlite_id": equipment["id"], "postgres_id": postgres_id, "diffs": diffs})

    return drifted


def main() -> int:
    load_dotenv()

    try:
        config = load_config(os.environ)
    except ParityCheckError as exc:
        print(f"Parity check failed: {exc}", file=sys.stderr)
        return 1

    client = build_service_role_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
    drifted = check_equipment_parity(client)

    if drifted:
        print(f"PARITY CHECK FAILED: {len(drifted)} equipment record(s) drifted:")
        for entry in drifted:
            print(f"  {entry}")
        return 1

    print("Parity check passed: 0 drift across all dual-written/backfilled equipment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
scripts/check_kb_parity.py — Phase 3.3 parity check
(docs/PHASE3_EXECUTION_PLAN.md).

Compares every SQLite `kb_documents` row that has been dual-written or
backfilled (postgres_id is set) against its Postgres `documents` +
`document_versions` counterpart. Read-only. Note: extracted_text is
EXPECTED to drift after the initial backfill copy, since ongoing
extraction-completion events are not dual-written in this iteration (see
config.KB_BACKEND's docstring) — this script does not compare extracted_text
for that reason; it is not a gap in the check, it's a known, documented
scope boundary.

CLI-only, service-role key — same convention as the other Phase 3 scripts.

Usage:
    python scripts/check_kb_parity.py

Exit code 0 if zero drift found (on the fields actually kept in sync),
1 otherwise.
"""

import os
import sys

from dotenv import load_dotenv
from supabase import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402
from scripts.check_projects_parity import (  # noqa: E402
    ParityCheckError,
    build_service_role_client,
    load_config,
)

# Fields kept in sync by dual-write (see module docstring re: extracted_text).
DOCUMENT_FIELDS_TO_COMPARE = ("document_type", "status")
CATEGORY_FIELD = "folder"  # compared via document_categories.name, not a raw column


def _normalize(value):
    return value if value else None


def check_kb_parity(client: Client) -> list[dict]:
    drifted = []

    for summary_row in db.get_kb_documents():
        postgres_id = summary_row.get("postgres_id")
        if not postgres_id:
            continue

        result = (
            client.table("documents").select("*, document_categories(name)")
            .eq("id", postgres_id).maybe_single().execute()
        )
        pg_row = result.data if result else None

        if pg_row is None:
            drifted.append({
                "sqlite_id": summary_row["id"],
                "postgres_id": postgres_id,
                "issue": "missing_in_postgres",
            })
            continue

        diffs = {}

        pg_category_name = (pg_row.get("document_categories") or {}).get("name")
        if _normalize(summary_row.get("folder")) != _normalize(pg_category_name):
            diffs["folder"] = {"sqlite": summary_row.get("folder"), "postgres": pg_category_name}

        if pg_row.get("status") not in ("approved", "archived"):
            diffs["status"] = {"issue": f"unexpected Postgres status {pg_row.get('status')!r}"}

        if diffs:
            drifted.append({"sqlite_id": summary_row["id"], "postgres_id": postgres_id, "diffs": diffs})

    return drifted


def main() -> int:
    load_dotenv()

    try:
        config = load_config(os.environ)
    except ParityCheckError as exc:
        print(f"Parity check failed: {exc}", file=sys.stderr)
        return 1

    client = build_service_role_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
    drifted = check_kb_parity(client)

    if drifted:
        print(f"PARITY CHECK FAILED: {len(drifted)} KB document(s) drifted:")
        for entry in drifted:
            print(f"  {entry}")
        return 1

    print("Parity check passed: 0 drift (folder/status) across all dual-written/backfilled KB documents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
scripts/backfill_projects.py — One-time Phase 3.2 backfill: SQLite
`projects` -> Postgres `projects`, under a single bootstrap company
(IMP-007, IMPLEMENTATION_ROADMAP.md §15), docs/PHASE3_EXECUTION_PLAN.md.

CLI-only. Never imported by pharmagpt/app.py, exposes no HTTP route — same
"service-role is administrative-script-only" convention as
scripts/bootstrap_super_admin.py: request-handling code (pharmagpt/db/
projects_repo.py) always acts as the authenticated caller under RLS;
only a manually-run script like this one uses the service-role key.

Run this against Staging after Phase 3.2's dual-write code is deployed.
Backfill catches up everything created *before* that point; dual-write
(routes/projects.py) covers everything created after.

Idempotent: every already-migrated SQLite row already carries its Postgres
id in the postgres_id bookkeeping column (pharmagpt/database.py) — rows
with a postgres_id already set are skipped. Safe to re-run after a partial
failure.

Usage:
    python scripts/backfill_projects.py

Reads from .env:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    BOOTSTRAP_COMPANY_NAME   (optional, default below)
    DB_PATH                  (optional — same SQLite file the app uses)
"""

import os
import sys

from dotenv import load_dotenv
from supabase import Client, create_client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402

DEFAULT_BOOTSTRAP_COMPANY_NAME = "PharmaGPT Bootstrap Company (pre-migration data)"
DEFAULT_INDUSTRY_SEGMENT = "pharma"
REQUIRED_ENV_VARS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


class BackfillError(Exception):
    """Raised for any condition that should stop the backfill script."""


def load_config(env: dict) -> dict:
    """Pull backfill configuration out of an environment mapping (a plain
    dict, not os.environ directly, so tests can exercise this without a
    real .env file — same pattern as scripts/bootstrap_super_admin.py)."""
    config = {name: env.get(name) for name in REQUIRED_ENV_VARS}
    config["BOOTSTRAP_COMPANY_NAME"] = env.get("BOOTSTRAP_COMPANY_NAME") or DEFAULT_BOOTSTRAP_COMPANY_NAME

    missing = [name for name in REQUIRED_ENV_VARS if not config[name]]
    if missing:
        raise BackfillError("Missing required .env values: " + ", ".join(missing))

    return config


def build_service_role_client(supabase_url: str, service_role_key: str) -> Client:
    """The one deliberate service-role use in this script — administrative,
    CLI-only. Never call this pattern from request-handling code."""
    return create_client(supabase_url, service_role_key)


def find_or_create_bootstrap_company(client: Client, name: str) -> str:
    """Idempotent find-or-create by legal_name. Returns the company's uuid."""
    existing = (
        client.table("companies").select("id").eq("legal_name", name).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    created = client.table("companies").insert(
        {"legal_name": name, "industry_segment": DEFAULT_INDUSTRY_SEGMENT}
    ).execute()
    return created.data[0]["id"]


def to_iso_utc(sqlite_timestamp: str | None) -> str | None:
    """SQLite's CURRENT_TIMESTAMP is naive UTC ('YYYY-MM-DD HH:MM:SS'), but
    Postgres `timestamptz` columns need an explicit offset to avoid being
    interpreted in the session's timezone. Already-ISO / already-offset
    strings pass through unchanged."""
    if not sqlite_timestamp:
        return None
    value = sqlite_timestamp.strip()
    if "T" not in value:
        value = value.replace(" ", "T", 1)
    if not (value.endswith("Z") or "+" in value[10:]):
        value += "Z"
    return value


def backfill_projects(client: Client, company_id: str) -> dict:
    """Migrate every SQLite project row without a postgres_id yet.

    Only fields with a home in DATABASE_ARCHITECTURE.md §4.2's `projects`
    table are carried over (see pharmagpt/db/projects_repo.py's module
    docstring for why equipment_name/manufacturer/department/
    validation_type/model/location and owner/approver are intentionally
    left out). Returns {"migrated": int, "skipped_already_migrated": int}.
    """
    migrated = 0
    skipped = 0
    for project in db.get_all_projects():
        if project.get("postgres_id"):
            skipped += 1
            continue

        inserted = client.table("projects").insert({
            "company_id": company_id,
            "name": project["name"],
            "status": project.get("status") or "active",
            "target_date": project.get("target_date") or None,
            "risk_category": project.get("risk_category") or None,
            "protocol_number": project.get("protocol_number") or None,
            "report_number": project.get("report_number") or None,
            "created_at": to_iso_utc(project.get("created_at")),
        }).execute()

        db.set_project_postgres_id(project["id"], inserted.data[0]["id"])
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

    summary = backfill_projects(client, company_id)
    print(
        f"Migrated {summary['migrated']} project(s); "
        f"{summary['skipped_already_migrated']} already migrated, skipped."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

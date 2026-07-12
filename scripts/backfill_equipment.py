"""
scripts/backfill_equipment.py — One-time Phase 3.4 backfill: SQLite
`equipment` -> Postgres `equipment` (company-owned, PA-013), plus
`equipment_documents` (source_type='kb' only) -> `equipment_links`, under
the same bootstrap company Phase 3.2/3.3 use, docs/PHASE3_EXECUTION_PLAN.md.

CLI-only, service-role key — same administrative-script convention as the
other Phase 3 backfill scripts. Request-handling code (pharmagpt/db/
equipment_repo.py) always acts as the authenticated caller instead.

Equipment is re-parented from project-owned to company-owned as part of
this backfill (PLATFORM_ARCHITECTURE.md §10, PA-013) — every SQLite
equipment row, regardless of which project it belongs to, is migrated
under the single bootstrap company, exactly like Projects and KB documents
were. Links to project-sourced documents (source_type='project') are
skipped, not migrated — those documents have no Postgres home yet
(roadmap Phase 9, out of this plan's 3.1-3.6 scope).

Idempotent: rows with a postgres_id already set are skipped. Safe to
re-run after a partial failure.

Usage:
    python scripts/backfill_equipment.py
"""

import os
import sys

from dotenv import load_dotenv
from supabase import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402
from pharmagpt import equipment_database as equipdb  # noqa: E402
from scripts.backfill_projects import (  # noqa: E402
    BackfillError,
    build_service_role_client,
    find_or_create_bootstrap_company,
    load_config,
)

_EQUIPMENT_FIELDS = (
    "equipment_code", "name", "category", "equipment_type", "tag_number",
    "model", "manufacturer", "vendor", "serial_number", "asset_number",
    "plant", "block", "department", "area", "room", "line",
    "installation_date", "commissioning_date",
    "qualification_status", "validation_status", "qualification_type",
    "criticality", "gmp_impact", "notes",
)


def backfill_equipment(client: Client, company_id: str) -> dict:
    """Migrate every SQLite equipment row without a postgres_id yet.
    Returns {"migrated": int, "skipped_already_migrated": int}."""
    migrated = 0
    skipped = 0

    for equipment in equipdb.get_all_equipment():
        if equipment.get("postgres_id"):
            skipped += 1
            continue

        payload = {field: (equipment.get(field) or None) for field in _EQUIPMENT_FIELDS}
        payload["company_id"] = company_id
        inserted = client.table("equipment").insert(payload).execute()

        equipdb.set_equipment_postgres_id(equipment["id"], inserted.data[0]["id"])
        migrated += 1

    return {"migrated": migrated, "skipped_already_migrated": skipped}


def backfill_equipment_links(client: Client, company_id: str) -> dict:
    """Migrate equipment_documents rows (source_type='kb' only, and only
    once the linked KB document already has a Postgres mirror) into
    equipment_links. Returns {"migrated": int, "skipped_already_migrated":
    int, "skipped_no_target": int} — the last counts links this pass
    genuinely cannot migrate yet (project-sourced, or the KB document
    hasn't been backfilled), which is expected, not an error."""
    migrated = 0
    skipped_already_migrated = 0
    skipped_no_target = 0

    for equipment in equipdb.get_all_equipment():
        equipment_postgres_id = equipment.get("postgres_id")
        if not equipment_postgres_id:
            continue  # equipment itself not migrated yet — nothing to link from

        for link in equipdb.list_equipment_documents(equipment["id"]):
            if link.get("postgres_id"):
                skipped_already_migrated += 1
                continue

            if link["source_type"] != "kb":
                skipped_no_target += 1
                continue

            kb_doc = db.get_kb_document(link["source_id"])
            kb_postgres_id = (kb_doc or {}).get("postgres_id")
            if not kb_postgres_id:
                skipped_no_target += 1
                continue

            inserted = client.table("equipment_links").insert({
                "company_id": company_id,
                "equipment_id": equipment_postgres_id,
                "record_type": "document",
                "record_id": kb_postgres_id,
            }).execute()

            equipdb.set_equipment_document_postgres_id(link["id"], inserted.data[0]["id"])
            migrated += 1

    return {
        "migrated": migrated,
        "skipped_already_migrated": skipped_already_migrated,
        "skipped_no_target": skipped_no_target,
    }


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

    equipment_summary = backfill_equipment(client, company_id)
    print(
        f"Migrated {equipment_summary['migrated']} equipment record(s); "
        f"{equipment_summary['skipped_already_migrated']} already migrated, skipped."
    )

    links_summary = backfill_equipment_links(client, company_id)
    print(
        f"Migrated {links_summary['migrated']} equipment_links(s); "
        f"{links_summary['skipped_already_migrated']} already migrated; "
        f"{links_summary['skipped_no_target']} skipped (project-sourced or KB doc not yet migrated)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

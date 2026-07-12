"""
scripts/backfill_kb_documents.py — One-time Phase 3.3 backfill: SQLite
`kb_documents` -> Postgres documents/document_versions/document_categories/
tags/document_tags, under the same bootstrap company Phase 3.2 uses
(IMP-007), docs/PHASE3_EXECUTION_PLAN.md.

CLI-only, service-role key — same administrative-script convention as
scripts/backfill_projects.py. Request-handling code (pharmagpt/db/kb_repo.py)
always acts as the authenticated caller instead.

Run this against Staging after Phase 3.3's dual-write code is deployed.
Backfill catches up everything uploaded *before* that point (including a
one-time copy of whatever extracted text already exists at backfill time —
extracted-text sync is not otherwise dual-written, see config.KB_BACKEND's
docstring); dual-write (routes/knowledge_base.py) covers new
uploads/deletes created after.

Idempotent: rows with a postgres_id already set are skipped. Safe to
re-run after a partial failure.

Usage:
    python scripts/backfill_kb_documents.py

Reads from .env:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    BOOTSTRAP_COMPANY_NAME   (optional — same default as backfill_projects.py)
    DB_PATH                  (optional — same SQLite file the app uses)
"""

import os
import sys

from dotenv import load_dotenv
from supabase import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt import database as db  # noqa: E402
from pharmagpt.db.kb_repo import KB_DOCUMENT_TYPE  # noqa: E402
from scripts.backfill_projects import (  # noqa: E402
    BackfillError,
    build_service_role_client,
    find_or_create_bootstrap_company,
    load_config,
)


def find_or_create_category(client: Client, company_id: str, name: str) -> str:
    """Same find-or-create semantics as pharmagpt/db/kb_repo.py, but against
    the service-role client (this is an admin script, no user token exists)."""
    existing = (
        client.table("document_categories")
        .select("id").eq("company_id", company_id).eq("name", name).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    created = client.table("document_categories").insert(
        {"company_id": company_id, "name": name}
    ).execute()
    return created.data[0]["id"]


def find_or_create_tag(client: Client, company_id: str, name: str) -> str:
    existing = (
        client.table("tags")
        .select("id").eq("company_id", company_id).eq("name", name).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    created = client.table("tags").insert({"company_id": company_id, "name": name}).execute()
    return created.data[0]["id"]


def _parse_tags(tags_csv: str) -> list[str]:
    return [t.strip() for t in (tags_csv or "").split(",") if t.strip()]


def backfill_kb_documents(client: Client, company_id: str) -> dict:
    """Migrate every SQLite kb_documents row without a postgres_id yet.
    Returns {"migrated": int, "skipped_already_migrated": int}."""
    migrated = 0
    skipped = 0

    for summary_row in db.get_kb_documents():
        if summary_row.get("postgres_id"):
            skipped += 1
            continue

        kb_doc = db.get_kb_document(summary_row["id"])  # full row, incl. text_content

        category_id = find_or_create_category(client, company_id, kb_doc["folder"])

        doc_row = client.table("documents").insert({
            "company_id": company_id,
            "project_id": None,
            "source_context": "knowledge_base",
            "document_type": KB_DOCUMENT_TYPE,
            "status": "approved",
            "category_id": category_id,
            "effective_date": kb_doc.get("effective_date") or None,
        }).execute().data[0]
        document_id = doc_row["id"]

        version_row = client.table("document_versions").insert({
            "company_id": company_id,
            "document_id": document_id,
            "major_version": 1,
            "minor_version": 0,
            "storage_path": f"uploads/kb/{kb_doc['stored_filename']}",
            "content_type": kb_doc["file_type"],
            "size_bytes": kb_doc["file_size"],
            "extracted_text": kb_doc.get("text_content") or None,
            "lifecycle_state_at_snapshot": "approved",
        }).execute().data[0]

        client.table("documents").update(
            {"current_version_id": version_row["id"]}
        ).eq("id", document_id).eq("company_id", company_id).execute()

        for tag_name in _parse_tags(kb_doc.get("tags")):
            tag_id = find_or_create_tag(client, company_id, tag_name)
            client.table("document_tags").insert({
                "company_id": company_id, "document_id": document_id, "tag_id": tag_id,
            }).execute()

        db.set_kb_document_postgres_id(kb_doc["id"], document_id)
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

    summary = backfill_kb_documents(client, company_id)
    print(
        f"Migrated {summary['migrated']} KB document(s); "
        f"{summary['skipped_already_migrated']} already migrated, skipped."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

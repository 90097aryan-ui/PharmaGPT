"""
pharmagpt/db/kb_repo.py — Postgres CRUD for Knowledge Base documents.

Phase 3.3 (docs/PHASE3_EXECUTION_PLAN.md). Not the source of truth yet —
see config.KB_BACKEND. Every function acts as the caller's own authenticated
Supabase client (get_authenticated_client), never the service-role key,
matching pharmagpt/db/projects_repo.py's established convention.

Mapping notes (DATABASE_ARCHITECTURE.md §4.4, §7, §9), each a deliberate,
documented decision rather than an assumption:

- KB documents consolidate into `documents` with
  source_context='knowledge_base', project_id=NULL, per DB-002.
- `document_type` has no equivalent in SQLite's kb_documents (which only
  captures folder + free-text tags, not a document-type taxonomy) — set to
  the fixed sentinel 'kb_document' until a real type field exists upstream.
- SQLite's `folder` maps to `document_categories.name` (find-or-create,
  company-scoped) via `documents.category_id` — this *is* the taxonomy
  DATABASE_ARCHITECTURE.md §9 describes.
- SQLite's comma-separated `tags` maps to `tags`/`document_tags` rows
  (find-or-create per tag, company-scoped).
- No lifecycle/approval workflow exists for KB uploads in the current app
  (extraction_status tracks *text extraction*, not document approval) — KB
  documents are usable immediately on upload today, so migrated/dual-written
  rows are created directly in 'approved' state (PLATFORM_ARCHITECTURE.md
  §12: "the state Knowledge Base ... references resolve to by default"),
  not 'draft'. This reflects current behavior; it does not invent a review
  gate that doesn't exist.
- `document_versions.storage_path` records today's local-disk-relative path
  (`uploads/kb/{stored_filename}`) as a placeholder — actual byte storage
  cutover to Supabase Storage is roadmap Phase 4, out of scope here. This
  column will be rewritten, not re-derived, when that phase lands.
- extracted_text is set at creation time if already available, and can be
  updated later via update_extracted_text() — but nothing calls that
  function yet in this iteration (see config.KB_BACKEND's docstring).
- Deleting a KB document in SQLite is (and remains) a real hard delete —
  no UI/API change. The Postgres mirror cannot literally hard-delete a
  `documents` row that still has `document_versions` (RESTRICT, §5.3) and,
  independent of that constraint, hard deletion is not how the target
  architecture models "gone" for a controlled document (§12: Obsolete/
  Archived, never hard-deleted by user action). archive_document() sets
  status='archived' instead — correct for where this is eventually headed,
  invisible to today's user (who only ever sees the SQLite-backed response).
"""

from pharmagpt.services.supabase_client import get_authenticated_client

DOCUMENTS_TABLE = "documents"
VERSIONS_TABLE = "document_versions"
CATEGORIES_TABLE = "document_categories"
TAGS_TABLE = "tags"
DOCUMENT_TAGS_TABLE = "document_tags"

KB_DOCUMENT_TYPE = "kb_document"


def find_or_create_category(access_token: str, company_id: str, name: str) -> str:
    """Idempotent find-or-create by (company_id, name). Returns the
    category's uuid."""
    client = get_authenticated_client(access_token)
    existing = (
        client.table(CATEGORIES_TABLE)
        .select("id").eq("company_id", company_id).eq("name", name).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    created = (
        client.table(CATEGORIES_TABLE)
        .insert({"company_id": company_id, "name": name}).execute()
    )
    return created.data[0]["id"]


def find_or_create_tag(access_token: str, company_id: str, name: str) -> str:
    """Idempotent find-or-create by (company_id, name). Returns the tag's uuid."""
    client = get_authenticated_client(access_token)
    existing = (
        client.table(TAGS_TABLE)
        .select("id").eq("company_id", company_id).eq("name", name).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    created = client.table(TAGS_TABLE).insert({"company_id": company_id, "name": name}).execute()
    return created.data[0]["id"]


def _parse_tags(tags_csv: str) -> list[str]:
    return [t.strip() for t in (tags_csv or "").split(",") if t.strip()]


def create_kb_document(access_token: str, company_id: str, *, title: str, folder: str,
                        tags_csv: str = "", stored_filename: str, file_type: str,
                        file_size: int, effective_date: str | None = None,
                        extracted_text: str | None = None) -> dict:
    """Create the documents/document_versions/tags rows for one KB upload.
    Returns {"document_id": uuid, "version_id": uuid}.

    Not atomic across the underlying inserts (PostgREST has no
    multi-statement transaction) — a partial failure leaves a partial mirror,
    which scripts/check_kb_parity.py is the intended safety net for, same
    accepted trade-off as Phase 3.2's dual-write."""
    client = get_authenticated_client(access_token)

    category_id = find_or_create_category(access_token, company_id, folder)

    doc_row = client.table(DOCUMENTS_TABLE).insert({
        "company_id": company_id,
        "project_id": None,
        "source_context": "knowledge_base",
        "document_type": KB_DOCUMENT_TYPE,
        "status": "approved",
        "category_id": category_id,
        "effective_date": effective_date or None,
    }).execute().data[0]
    document_id = doc_row["id"]

    version_row = client.table(VERSIONS_TABLE).insert({
        "company_id": company_id,
        "document_id": document_id,
        "major_version": 1,
        "minor_version": 0,
        "storage_path": f"uploads/kb/{stored_filename}",
        "content_type": file_type,
        "size_bytes": file_size,
        "extracted_text": extracted_text or None,
        "lifecycle_state_at_snapshot": "approved",
    }).execute().data[0]
    version_id = version_row["id"]

    client.table(DOCUMENTS_TABLE).update(
        {"current_version_id": version_id}
    ).eq("id", document_id).eq("company_id", company_id).execute()

    for tag_name in _parse_tags(tags_csv):
        tag_id = find_or_create_tag(access_token, company_id, tag_name)
        client.table(DOCUMENT_TAGS_TABLE).insert({
            "company_id": company_id, "document_id": document_id, "tag_id": tag_id,
        }).execute()

    return {"document_id": document_id, "version_id": version_id}


def update_extracted_text(access_token: str, company_id: str, document_id: str,
                           extracted_text: str) -> None:
    """Update the extracted_text of a KB document's (only) version row. Not
    called from any request path yet in this iteration — see
    config.KB_BACKEND's docstring — but used by the backfill script."""
    client = get_authenticated_client(access_token)
    client.table(VERSIONS_TABLE).update(
        {"extracted_text": extracted_text}
    ).eq("document_id", document_id).eq("company_id", company_id).execute()


def archive_document(access_token: str, company_id: str, document_id: str) -> None:
    """Mark a Postgres-mirrored KB document 'archived' — the dual-write
    counterpart to SQLite's real hard delete (see module docstring)."""
    client = get_authenticated_client(access_token)
    client.table(DOCUMENTS_TABLE).update(
        {"status": "archived"}
    ).eq("id", document_id).eq("company_id", company_id).execute()

"""
pharmagpt/db/equipment_repo.py — Postgres CRUD for the `equipment` and
`equipment_links` tables.

Phase 3.4 (docs/PHASE3_EXECUTION_PLAN.md). Not the source of truth yet —
see config.EQUIPMENT_BACKEND. Every function acts as the caller's own
authenticated Supabase client (get_authenticated_client), never the
service-role key, matching the established convention.

Mapping notes:
- `equipment` is company-owned in the target schema (PLATFORM_ARCHITECTURE.md
  §10, PA-013) — no project_id column at all, unlike SQLite's current
  project-owned shape. company_id is supplied by the caller (from
  g.tenant.company_id), not derived from the SQLite row's project.
- Every Basic/Installation/Qualification field SQLite tracks has a direct
  column in the target schema (migrations/0004 + the 0007 correction for
  gmp_impact's type and the added notes column) — full fidelity, nothing
  silently dropped, unlike Phase 3.2's Projects migration.
- Equipment has no lifecycle/soft-delete field in the target schema (unlike
  `documents`, which has status). delete_equipment() therefore attempts a
  real delete, not an archive-style status flip — DATABASE_ARCHITECTURE.md
  §5.3 itself treats equipment hard-deletion as "a rare, Super-Admin/
  data-retention operation," consistent with a real (if infrequent) delete
  path rather than requiring a lifecycle field this table doesn't have.
  If equipment_links rows still reference it, Postgres RESTRICTs the
  delete — the caller (routes/equipment.py) catches and logs that, same
  non-blocking policy as every other Phase 3 dual-write.
- equipment_links dual-write is intentionally narrow: only source_type='kb'
  links, and only once the linked KB document has already been dual-written
  (kb_documents.postgres_id is set). 'project'-sourced links have no
  Postgres-side `documents` row to reference yet (project-generated
  document migration is roadmap Phase 9, outside this plan's 3.1-3.6 scope)
  — callers skip and log those, they are not silently dropped.
"""

from pharmagpt.services.supabase_client import get_authenticated_client

EQUIPMENT_TABLE = "equipment"
LINKS_TABLE = "equipment_links"

_EQUIPMENT_FIELDS = (
    "equipment_code", "name", "category", "equipment_type", "tag_number",
    "model", "manufacturer", "vendor", "serial_number", "asset_number",
    "plant", "block", "department", "area", "room", "line",
    "installation_date", "commissioning_date",
    "qualification_status", "validation_status", "qualification_type",
    "criticality", "gmp_impact", "notes",
)


def _payload(data: dict) -> dict:
    return {field: (data.get(field) or None) for field in _EQUIPMENT_FIELDS}


def create_equipment(access_token: str, company_id: str, data: dict) -> dict:
    """Insert one row into Postgres `equipment`. Returns the inserted row."""
    client = get_authenticated_client(access_token)
    payload = _payload(data)
    payload["company_id"] = company_id
    result = client.table(EQUIPMENT_TABLE).insert(payload).execute()
    return result.data[0]


def update_equipment(access_token: str, company_id: str, postgres_id: str, data: dict) -> dict | None:
    """Update the mutable fields of one Postgres `equipment` row."""
    client = get_authenticated_client(access_token)
    result = (
        client.table(EQUIPMENT_TABLE)
        .update(_payload(data))
        .eq("id", postgres_id).eq("company_id", company_id)
        .execute()
    )
    return result.data[0] if result.data else None


def delete_equipment(access_token: str, company_id: str, postgres_id: str) -> None:
    """Delete one Postgres `equipment` row. Raises if Postgres RESTRICTs the
    delete (equipment_links still reference it) — callers must catch, same
    non-blocking policy as every other Phase 3 dual-write."""
    client = get_authenticated_client(access_token)
    client.table(EQUIPMENT_TABLE).delete().eq("id", postgres_id).eq("company_id", company_id).execute()


def link_kb_document(access_token: str, company_id: str, equipment_postgres_id: str,
                      kb_document_postgres_id: str) -> dict:
    """Create one equipment_links row (record_type='document') connecting
    equipment to a Postgres-mirrored KB document. Returns the inserted row."""
    client = get_authenticated_client(access_token)
    result = client.table(LINKS_TABLE).insert({
        "company_id": company_id,
        "equipment_id": equipment_postgres_id,
        "record_type": "document",
        "record_id": kb_document_postgres_id,
    }).execute()
    return result.data[0]


def unlink(access_token: str, company_id: str, link_postgres_id: str) -> None:
    client = get_authenticated_client(access_token)
    client.table(LINKS_TABLE).delete().eq("id", link_postgres_id).eq("company_id", company_id).execute()

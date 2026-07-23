"""
equipment_database.py — SQLite CRUD for the Equipment entity (PharmaGPT v1.0 Module 2).

Tables managed here
-------------------
equipment           : One row per physical equipment record, owned by a Project.
                      Carries Basic/Installation/Qualification information per
                      PharmaGPT v1.0 Module 2. Designed to be the stable parent
                      row future modules (Calibration, Preventive Maintenance,
                      Breakdown History, Spare Parts, Vendor Qualification,
                      Environmental Monitoring, Utilities, Asset Management)
                      will FK against via `equipment_id` — none of those tables
                      are created by this module.
equipment_documents : Polymorphic link table connecting an Equipment record to
                      an existing Knowledge Base document (`kb_documents`) or
                      an existing Project document (`documents`). Never copies
                      file content — the same manual can be linked from many
                      Equipment records / Projects (see PROJECT_MEMORY/
                      ARCHITECTURE.md §10 Knowledge Base). Mirrors the
                      polymorphic-reference pattern already established by the
                      QMS shared tables (DEC-010/DEC-011), applied here to a
                      link table rather than an owned attachment.

Relationship to pharmagpt/equipment/ (Equipment Intelligence Engine)
----------------------------------------------------------------------
`pharmagpt/equipment/` is a *static reference catalog* (EquipmentProfile per
equipment type — HPLC, GC, Autoclave, ...) used to enrich AI prompts. It is
not an instance store and is intentionally left untouched by this module. An
`equipment` row's `equipment_type` field is free text that *may* match a
catalog entry (see services/equipment_service.py::get_equipment_type_catalog
for autocomplete); no FK or enum constraint ties them together.
"""

from pharmagpt.database import get_connection

DOCUMENT_ROLES = (
    "user_manual", "vendor_manual", "sop", "drawing", "pnid",
    "electrical_drawing", "pneumatic_drawing", "fat", "sat", "urs", "other",
    # Phase 3 (Enterprise Validation Platform): generic role for the four new
    # QMS record source_types below — a deviation/CAPA/change control/risk
    # assessment isn't a "document" in the same sense as the roles above, so
    # it doesn't need one of the document-shaped role values.
    "quality_record",
)
# Phase 3 (Enterprise Validation Platform): widened from ("kb", "project") to
# also cover the traceability chain's Equipment -> QMS Records link
# (docs/DATABASE_ARCHITECTURE.md §6's equipment_links mechanism) — same
# polymorphic table, same pattern, no rename, no schema change (source_type
# is already free text).
SOURCE_TYPES = ("kb", "project", "deviation", "capa", "change_control", "risk_assessment")


# ── Equipment CRUD ────────────────────────────────────────────────────────────

_EQUIPMENT_FIELDS = (
    "equipment_code", "name", "category", "equipment_type", "tag_number",
    "model", "manufacturer", "vendor", "serial_number", "asset_number",
    "plant", "block", "department", "area", "room", "line",
    "installation_date", "commissioning_date",
    "qualification_status", "validation_status", "qualification_type",
    "criticality", "gmp_impact", "notes",
)


def create_equipment(project_id: int, data: dict) -> dict:
    """Insert a new Equipment row scoped to a Project and return the full dict."""
    conn = get_connection()
    columns = ", ".join(_EQUIPMENT_FIELDS)
    placeholders = ", ".join("?" for _ in _EQUIPMENT_FIELDS)
    values = [(data.get(f) or "").strip() if isinstance(data.get(f), str) else data.get(f) or ""
              for f in _EQUIPMENT_FIELDS]
    # installation_date / commissioning_date are nullable dates, not '' defaults
    for date_field in ("installation_date", "commissioning_date"):
        idx = _EQUIPMENT_FIELDS.index(date_field)
        values[idx] = data.get(date_field) or None

    cur = conn.execute(
        f"INSERT INTO equipment (project_id, {columns}) VALUES (?, {placeholders})",
        [project_id, *values],
    )
    conn.commit()
    row = conn.execute("SELECT * FROM equipment WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_equipment(equipment_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_equipment_scoped(equipment_id: int, company_id: str) -> dict | None:
    """Return the equipment row only if it exists AND its owning Project
    belongs to `company_id`. `equipment` has no company_id column of its own
    (it inherits tenancy from its Project, project_id is NOT NULL) — this
    joins rather than trusting a caller-supplied company match.

    `company_id` must come from the authenticated TenantContext, never from
    client input (pharmagpt/tenancy.py) — every flat /equipment/<id> route
    must use this instead of get_equipment() alone.
    """
    conn = get_connection()
    row = conn.execute(
        """SELECT e.* FROM equipment e
           JOIN projects p ON p.id = e.project_id
           WHERE e.id = ? AND p.company_id = ?""",
        (equipment_id, company_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_project_equipment(project_id: int) -> list[dict]:
    """All Equipment records belonging to a Project, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM equipment WHERE project_id = ? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_equipment(company_id: str | None = None) -> list[dict]:
    """Every Equipment record across every Project (Phase 3.4,
    docs/PHASE3_EXECUTION_PLAN.md — the backfill/parity scripts need a
    company-wide view, not a per-project one, since Postgres equipment is
    company-owned).

    `company_id=None` is reserved for the offline backfill/parity scripts,
    which intentionally run company-by-company using the service-role key,
    not a live request — see scripts/backfill_equipment.py. Any live route
    must always pass the authenticated tenant's company_id.
    """
    conn = get_connection()
    if company_id is None:
        rows = conn.execute(
            """SELECT e.*, p.name AS project_name FROM equipment e
               JOIN projects p ON p.id = e.project_id
               ORDER BY e.created_at DESC"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT e.*, p.name AS project_name FROM equipment e
               JOIN projects p ON p.id = e.project_id
               WHERE p.company_id = ? ORDER BY e.created_at DESC""",
            (company_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_equipment(equipment_id: int, data: dict) -> dict | None:
    conn = get_connection()
    existing = conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if not existing:
        conn.close()
        return None
    existing = dict(existing)

    def _field(key: str) -> object:
        val = data.get(key, existing.get(key) or "")
        return val.strip() if isinstance(val, str) else val

    def _date(key: str) -> object:
        return data.get(key, existing.get(key)) or None

    assignments = ", ".join(f"{f} = ?" for f in _EQUIPMENT_FIELDS)
    values = [
        _date(f) if f in ("installation_date", "commissioning_date") else _field(f)
        for f in _EQUIPMENT_FIELDS
    ]
    conn.execute(
        f"UPDATE equipment SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        [*values, equipment_id],
    )
    conn.commit()
    row = conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_equipment(equipment_id: int) -> None:
    """Delete an Equipment record. ON DELETE CASCADE removes its document links."""
    conn = get_connection()
    conn.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))
    conn.commit()
    conn.close()


def set_equipment_postgres_id(equipment_id: int, postgres_id: str) -> None:
    """Record the Postgres `equipment.id` (uuid) this SQLite equipment row
    was dual-written to (Phase 3.4, docs/PHASE3_EXECUTION_PLAN.md). Pure
    migration bookkeeping, same pattern as set_project_postgres_id (3.2)
    and set_kb_document_postgres_id (3.3)."""
    conn = get_connection()
    conn.execute("UPDATE equipment SET postgres_id = ? WHERE id = ?", (postgres_id, equipment_id))
    conn.commit()
    conn.close()


def search_equipment(query: str, company_id: str, project_id: int | None = None) -> list[dict]:
    """Keyword search across name/equipment_code/tag_number/serial_number/manufacturer,
    scoped to `company_id` (must come from the authenticated TenantContext,
    never client input — pharmagpt/tenancy.py) and optionally further to a
    single project."""
    conn = get_connection()
    like = f"%{query}%"
    sql = """SELECT e.* FROM equipment e
             JOIN projects p ON p.id = e.project_id
             WHERE p.company_id = ?
               AND (e.name LIKE ? OR e.equipment_code LIKE ? OR e.tag_number LIKE ?
                    OR e.serial_number LIKE ? OR e.manufacturer LIKE ? OR e.asset_number LIKE ?)"""
    params: list = [company_id, like, like, like, like, like, like]
    if project_id is not None:
        sql += " AND e.project_id = ?"
        params.append(project_id)
    sql += " ORDER BY e.created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def import_legacy_equipment(project_id: int) -> dict | None:
    """
    One-click consolidation: create an Equipment record pre-filled from a
    Project's legacy free-text fields (equipment_name/manufacturer/model/
    equipment_id), so existing projects can adopt the new entity without the
    user re-typing data that already exists. Returns None if the project has
    no legacy equipment info to import.
    """
    conn = get_connection()
    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    if not project:
        return None
    project = dict(project)
    if not (project.get("equipment_name") or "").strip():
        return None

    return create_equipment(project_id, {
        "name": project.get("equipment_name", ""),
        "manufacturer": project.get("manufacturer", ""),
        "model": project.get("model", ""),
        "equipment_code": project.get("equipment_id", ""),
        "department": project.get("department", ""),
    })


# ── Equipment ↔ Document links ────────────────────────────────────────────────

def link_equipment_document(equipment_id: int, document_role: str, source_type: str,
                             source_id: int, title_snapshot: str = "") -> dict:
    if document_role not in DOCUMENT_ROLES:
        raise ValueError(f"Invalid document_role: {document_role}")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type}")

    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO equipment_documents
           (equipment_id, document_role, source_type, source_id, title_snapshot)
           VALUES (?, ?, ?, ?, ?)""",
        (equipment_id, document_role, source_type, source_id, title_snapshot),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM equipment_documents WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def list_equipment_documents(equipment_id: int) -> list[dict]:
    """
    All document links for an Equipment record, resolved against their live
    source table where possible (falls back to the stored title_snapshot if
    the source document was deleted, so a broken link is visible, not silent).
    """
    conn = get_connection()
    links = [dict(r) for r in conn.execute(
        "SELECT * FROM equipment_documents WHERE equipment_id = ? ORDER BY linked_at DESC",
        (equipment_id,),
    ).fetchall()]

    # Phase 3 (Enterprise Validation Platform): resolution for the QMS record
    # source_types added to SOURCE_TYPES above — each queries its own table's
    # title-bearing column(s) via qms_database, not a document table.
    _qms_resolvers = {
        "deviation": ("qms_deviations", "title"),
        "capa": ("qms_capas", "title"),
        "change_control": ("qms_change_controls", "title"),
        "risk_assessment": ("risk_assessments", "title"),
    }

    for link in links:
        link["resolved"] = False
        if link["source_type"] == "kb":
            doc = conn.execute(
                "SELECT title, file_type, folder FROM kb_documents WHERE id = ?", (link["source_id"],)
            ).fetchone()
            if doc:
                link["resolved"] = True
                link["display_title"] = doc["title"]
                link["file_type"] = doc["file_type"]
        elif link["source_type"] == "project":
            doc = conn.execute(
                "SELECT original_name, file_type FROM documents WHERE id = ?", (link["source_id"],)
            ).fetchone()
            if doc:
                link["resolved"] = True
                link["display_title"] = doc["original_name"]
                link["file_type"] = doc["file_type"]
        elif link["source_type"] in _qms_resolvers:
            table, title_col = _qms_resolvers[link["source_type"]]
            record = conn.execute(
                f"SELECT {title_col} FROM {table} WHERE id = ?", (link["source_id"],)
            ).fetchone()
            if record:
                link["resolved"] = True
                link["display_title"] = record[title_col]
        if not link["resolved"]:
            link["display_title"] = link["title_snapshot"] or "(document removed)"

    conn.close()
    return links


def unlink_equipment_document(link_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM equipment_documents WHERE id = ?", (link_id,))
    conn.commit()
    conn.close()


def get_equipment_document_link(link_id: int) -> dict | None:
    """Single equipment_documents row by id — used by dual-write to look up
    postgres_id before an unlink (Phase 3.4)."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM equipment_documents WHERE id = ?", (link_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_equipment_document_postgres_id(link_id: int, postgres_id: str) -> None:
    """Record the Postgres `equipment_links.id` (uuid) this SQLite
    equipment_documents row was dual-written to (Phase 3.4)."""
    conn = get_connection()
    conn.execute(
        "UPDATE equipment_documents SET postgres_id = ? WHERE id = ?", (postgres_id, link_id)
    )
    conn.commit()
    conn.close()


# ── Init (called by database.py's init_db) ────────────────────────────────────

EQUIPMENT_SCHEMA = """
    -- ── equipment ─────────────────────────────────────────────────────────────
    -- One row per physical equipment record, owned by exactly one Project.
    -- Future modules (Calibration, Preventive Maintenance, Breakdown History,
    -- Spare Parts, Vendor Qualification, Environmental Monitoring, Utilities,
    -- Asset Management) are expected to FK against equipment.id — none of
    -- those tables are created here (architecture only, per Module 2 scope).
    CREATE TABLE IF NOT EXISTS equipment (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id            INTEGER NOT NULL,

        -- Basic Information
        equipment_code        TEXT    DEFAULT '',   -- user-assigned "Equipment ID" / asset tag
        name                  TEXT    NOT NULL DEFAULT '',
        category              TEXT    DEFAULT '',   -- e.g. Analytical, Manufacturing, Packaging, Utility
        equipment_type        TEXT    DEFAULT '',   -- e.g. HPLC, Autoclave — may match pharmagpt/equipment/ catalog
        tag_number            TEXT    DEFAULT '',
        model                 TEXT    DEFAULT '',
        manufacturer          TEXT    DEFAULT '',
        vendor                TEXT    DEFAULT '',
        serial_number         TEXT    DEFAULT '',
        asset_number          TEXT    DEFAULT '',

        -- Installation Information
        plant                 TEXT    DEFAULT '',
        block                 TEXT    DEFAULT '',
        department            TEXT    DEFAULT '',
        area                  TEXT    DEFAULT '',
        room                  TEXT    DEFAULT '',
        line                  TEXT    DEFAULT '',
        installation_date     TEXT    DEFAULT NULL,  -- ISO date YYYY-MM-DD
        commissioning_date    TEXT    DEFAULT NULL,

        -- Qualification Information
        qualification_status  TEXT    DEFAULT '',   -- Not Started | In Progress | Qualified | Requalification Due
        validation_status      TEXT    DEFAULT '',   -- Not Started | In Progress | Validated
        qualification_type    TEXT    DEFAULT '',   -- e.g. DQ/IQ/OQ/PQ, CSV, FAT/SAT
        criticality           TEXT    DEFAULT '',   -- Critical | Major | Minor
        gmp_impact            TEXT    DEFAULT '',   -- Direct | Indirect | No Impact

        notes                 TEXT    DEFAULT '',
        created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- ── equipment_documents ───────────────────────────────────────────────────
    -- Links an Equipment record to an existing kb_documents or documents row.
    -- Polymorphic on (source_type, source_id) — no single FK is possible since
    -- the two source tables are distinct; this mirrors the QMS shared-table
    -- polymorphic-reference precedent (DEC-010/DEC-011). Never stores a copy
    -- of the file itself, only the reference.
    CREATE TABLE IF NOT EXISTS equipment_documents (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_id    INTEGER NOT NULL,
        document_role   TEXT    NOT NULL,   -- user_manual | vendor_manual | sop | drawing | pnid |
                                             -- electrical_drawing | pneumatic_drawing | fat | sat | urs | other
        source_type     TEXT    NOT NULL,   -- 'kb' (kb_documents) | 'project' (documents)
        source_id       INTEGER NOT NULL,
        title_snapshot  TEXT    DEFAULT '',  -- denormalized title at link time, used if the source is later deleted
        linked_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_equipment_project_id ON equipment(project_id);
    CREATE INDEX IF NOT EXISTS idx_equipment_documents_equipment_id ON equipment_documents(equipment_id);
"""

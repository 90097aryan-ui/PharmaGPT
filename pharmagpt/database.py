"""
database.py — SQLite interface for PharmaGPT.

Tables
──────
projects            : One row per validation project with equipment/dept metadata.
messages            : Every chat turn (user + AI) linked to a project. Used to
                      rebuild Gemini conversation history on server restart.
documents           : Metadata for every uploaded project file. The file itself
                      lives on disk at uploads/{project_id}/{stored_filename}.
document_text       : Extracted plain text for each uploaded document. Used by
                      document_search.py for keyword RAG and will feed vector
                      embeddings in v0.8.
generated_documents : AI-generated validation documents saved to a project.
                      Stored as markdown; exported to DOCX/PDF on demand.
val_projects        : SUPERSEDED (Phase 2 Module 1) — Validation Workspace projects
                      (v0.8). Its owner/approver/target_date/risk_category/status/
                      model/location/protocol_number/report_number fields now live
                      directly on `projects` (see `_migrate_val_projects()`). This
                      table is kept, read-only, for historical data — nothing
                      writes to it anymore. There is now only one Project entity.
val_audit_trail     : SUPERSEDED (Phase 2 Module 1) — superseded by `qms_audit_trail`
                      with record_type='project'. Kept, read-only, for history.
kb_documents        : Global Knowledge Base — permanent document library not
                      tied to any project. Supports folder, tag, and full-text search.
equipment           : PharmaGPT v1.0 Module 2 — Equipment as a first-class entity,
                      owned by a Project. See equipment_database.py.
equipment_documents : Module 2 — polymorphic links from an Equipment record to
                      existing kb_documents/documents rows (no file duplication).
                      See equipment_database.py.

All tables are created automatically on first startup via init_db().
Database file: pharmagpt/pharmagpt.db
"""

import sqlite3
import os

# Absolute path to the SQLite file.
#
# IMPORTANT — deployment note: the default below sits inside the pharmagpt/
# package folder, which lives on the *application* filesystem. On platforms
# with an ephemeral/read-only filesystem (e.g. Render web services without a
# persistent disk), that folder is reset on every restart, redeploy, or
# idle-spindown — every INSERT commits successfully in the moment, but the
# data silently disappears the next time the dyno/container restarts,
# because init_db() just creates a brand-new empty file again. This is why
# "project creation appears successful but the table is later empty" can
# happen with correctly-committing code.
#
# Set DB_PATH to a file on a mounted persistent volume in production (see
# render.yaml) to fix this at the infrastructure level; it defaults to the
# previous in-package path for local development.
DB_PATH = os.getenv("DB_PATH") or os.path.join(os.path.dirname(__file__), "pharmagpt.db")


def get_connection() -> sqlite3.Connection:
    """Open (or create) the database and return a connection.
    row_factory=sqlite3.Row makes every row behave like a dict."""
    # timeout: wait for locks instead of raising "database is locked"
    # immediately — matters once multiple gunicorn workers/threads share
    # this one SQLite file (see Procfile: --workers=2 --threads=4).
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # Enforce foreign-key constraints (SQLite disables them by default)
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets readers and writers work concurrently instead of the default
    # rollback-journal mode, which takes an exclusive lock for the whole
    # duration of every write — the more likely source of lock contention
    # under concurrent gunicorn workers/threads.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """
    Add a column to an existing table if it isn't already there.

    SQLite has no `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, so this checks
    PRAGMA table_info() first. Safe to call on every startup — purely
    additive, never touches existing data.
    """
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    """Create tables if they do not already exist. Safe to call on every startup."""
    from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID  # noqa: F401 (used by several tenant-isolation blocks below)

    conn = get_connection()
    conn.executescript("""
        -- ── projects ──────────────────────────────────────────────────────────
        -- Each project represents one validation activity (e.g., IQ for HPLC).
        CREATE TABLE IF NOT EXISTS projects (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,           -- user-chosen project title
            equipment_name  TEXT    DEFAULT '',         -- e.g. "Agilent HPLC 1260"
            manufacturer    TEXT    DEFAULT '',         -- e.g. "Agilent Technologies"
            department      TEXT    DEFAULT '',         -- e.g. "Quality Control"
            validation_type TEXT    DEFAULT '',         -- e.g. "IQ/OQ/PQ", "CSV", "FAT"
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ── messages ──────────────────────────────────────────────────────────
        -- Every chat turn (user question + AI reply) is stored here.
        -- Linked to a project so history can be reconstructed per-project.
        -- ON DELETE CASCADE means deleting a project also deletes its messages.
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL,
            role        TEXT    NOT NULL CHECK(role IN ('user', 'model')),
            content     TEXT    NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        -- ── documents ─────────────────────────────────────────────────────────
        -- Metadata for every file uploaded to a project.
        -- The file itself lives at  uploads/{project_id}/{stored_filename}.
        -- original_name  = what the user's browser sent (may have spaces, caps)
        -- stored_filename = sanitised name actually written to disk (secure_filename)
        -- file_size is in bytes; the UI converts it to KB/MB for display.
        -- ON DELETE CASCADE removes document rows when the project is deleted,
        -- but the caller must also delete the physical file (see documents.py).
        CREATE TABLE IF NOT EXISTS documents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      INTEGER NOT NULL,
            original_name   TEXT    NOT NULL,
            stored_filename TEXT    NOT NULL,
            file_type       TEXT    NOT NULL,   -- extension: pdf, docx, xlsx, txt
            file_size       INTEGER NOT NULL,   -- bytes
            upload_date     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        -- ── document_text ──────────────────────────────────────────────────────
        -- Plain text extracted from each uploaded document on upload.
        -- One row per document (UNIQUE on document_id enforces this).
        -- Used for keyword search (document_search.py) and will feed
        -- vector embeddings in v0.8 when the RAG upgrade is implemented.
        -- extraction_status: 'ok' | 'empty' | 'error'
        CREATE TABLE IF NOT EXISTS document_text (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id      INTEGER NOT NULL UNIQUE,
            project_id       INTEGER NOT NULL,
            text_content     TEXT    NOT NULL DEFAULT '',
            page_count       INTEGER NOT NULL DEFAULT 0,
            word_count       INTEGER NOT NULL DEFAULT 0,
            extraction_status TEXT   NOT NULL DEFAULT 'ok',
            extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id)  REFERENCES projects(id)  ON DELETE CASCADE
        );

        -- ── generated_documents ────────────────────────────────────────────────
        -- AI-generated validation documents (OQ, IQ, PQ, URS, etc.).
        -- form_data is stored as JSON so the wizard can be pre-filled on re-open.
        -- content is the raw markdown returned by Gemini; exported to DOCX/PDF on demand.
        CREATE TABLE IF NOT EXISTS generated_documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL,
            doc_type    TEXT    NOT NULL,   -- 'OQ' | 'IQ' | 'PQ' | 'URS' | ...
            title       TEXT    NOT NULL,
            form_data   TEXT    NOT NULL DEFAULT '{}',   -- JSON
            content     TEXT    NOT NULL DEFAULT '',     -- markdown
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        -- ── val_projects ──────────────────────────────────────────────────────
        -- Validation Workspace projects (v0.8). Each row is a full validation
        -- engagement with equipment details, personnel, schedule, and risk tier.
        CREATE TABLE IF NOT EXISTS val_projects (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            equipment_name  TEXT    DEFAULT '',
            equipment_id    TEXT    DEFAULT '',
            department      TEXT    DEFAULT '',
            manufacturer    TEXT    DEFAULT '',
            model           TEXT    DEFAULT '',
            location        TEXT    DEFAULT '',
            validation_type TEXT    DEFAULT '',
            protocol_number TEXT    DEFAULT '',
            report_number   TEXT    DEFAULT '',
            owner           TEXT    DEFAULT '',
            approver        TEXT    DEFAULT '',
            target_date     TEXT    DEFAULT NULL,
            risk_category   TEXT    DEFAULT '',
            status          TEXT    DEFAULT 'In Progress',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ── val_audit_trail ────────────────────────────────────────────────────
        -- Immutable log of every action taken within a validation project.
        CREATE TABLE IF NOT EXISTS val_audit_trail (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            val_proj_id INTEGER NOT NULL,
            action      TEXT    NOT NULL,
            user_note   TEXT    DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (val_proj_id) REFERENCES val_projects(id) ON DELETE CASCADE
        );

        -- ── kb_documents ─────────────────────────────────────────────────────
        -- Global Knowledge Base: permanent document library not tied to any project.
        -- Supports folder organisation, tags, versioning, effective/review dates,
        -- and full-text keyword search through extracted text_content.
        -- Files stored at: uploads/kb/{stored_filename}
        CREATE TABLE IF NOT EXISTS kb_documents (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            title            TEXT    NOT NULL,
            folder           TEXT    NOT NULL DEFAULT 'Others',
            tags             TEXT    NOT NULL DEFAULT '',        -- comma-separated
            doc_version      TEXT    NOT NULL DEFAULT '1.0',
            effective_date   TEXT    DEFAULT NULL,              -- ISO date YYYY-MM-DD
            review_date      TEXT    DEFAULT NULL,              -- ISO date YYYY-MM-DD
            original_name    TEXT    NOT NULL,
            stored_filename  TEXT    NOT NULL,
            file_type        TEXT    NOT NULL,
            file_size        INTEGER NOT NULL DEFAULT 0,
            text_content     TEXT    NOT NULL DEFAULT '',
            word_count       INTEGER NOT NULL DEFAULT 0,
            page_count       INTEGER NOT NULL DEFAULT 0,
            extraction_status TEXT   NOT NULL DEFAULT 'ok',
            upload_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ── kb_document_versions ───────────────────────────────────────────
        -- Phase 3 (Enterprise Validation Platform): Knowledge Base had no
        -- version history at all — re-upload/re-publish silently overwrote
        -- the stored file in place. Mirrors qms_document_versions's shape
        -- (see qms_document_database.py::create_version/get_versions);
        -- stored_filename replaces content_snapshot because KB documents are
        -- files (DOCX/PDF), not markdown snapshots.
        CREATE TABLE IF NOT EXISTS kb_document_versions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            kb_document_id    INTEGER NOT NULL,
            version           TEXT    NOT NULL DEFAULT '',
            change_summary    TEXT    DEFAULT '',
            stored_filename   TEXT    DEFAULT '',
            changed_by        TEXT    DEFAULT '',
            created_at        TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (kb_document_id) REFERENCES kb_documents(id) ON DELETE CASCADE
        );
    """)
    conn.commit()

    # ── Document Processing Engine — additive columns ─────────────────────────
    # See services/document_processor.py and services/extraction/. Existing
    # extraction_status values ('ok' | 'empty' | 'error') keep working
    # unmodified; the new async multi-engine pipeline additionally uses
    # 'pending' | 'processing' | 'partial' | 'failed'.
    for _table in ("document_text", "kb_documents"):
        _add_column_if_missing(conn, _table, "extraction_progress_current", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, _table, "extraction_progress_total",   "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, _table, "extraction_engine",           "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, _table, "quality_score",               "REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, _table, "extraction_seconds",          "REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, _table, "pages_failed",                "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, _table, "error_message",               "TEXT NOT NULL DEFAULT ''")
    conn.commit()

    # ── Phase 3.3 dual-write bookkeeping (docs/PHASE3_EXECUTION_PLAN.md) ──────
    # Migration bookkeeping only, not part of the target Postgres schema —
    # same pattern as projects.postgres_id (Phase 3.2).
    _add_column_if_missing(conn, "kb_documents", "postgres_id", "TEXT DEFAULT NULL")
    conn.commit()

    # ── Phase 2 (PharmaGPT Architecture Program): auto-publish-to-KB ─────────
    # Identifies the governed record (Document Control / URS / Qualification
    # protocol / Validation Report) a KB entry was auto-published from, so
    # services/kb_sync.py can upsert in place on every re-approval instead of
    # accumulating a new row per version — the KB always shows exactly one
    # row per governed record, always the current effective version. NULL for
    # every manually-uploaded document (unchanged behaviour).
    _add_column_if_missing(conn, "kb_documents", "source_type", "TEXT DEFAULT NULL")
    _add_column_if_missing(conn, "kb_documents", "source_id",   "INTEGER DEFAULT NULL")
    conn.commit()

    # ── Risk Management Suite tables ──────────────────────────────────────────
    from pharmagpt.risk_database import RISK_SCHEMA
    conn.executescript(RISK_SCHEMA)
    conn.commit()

    # ── Phase 3 (Enterprise Validation Platform) e-signature parity fix ──────
    # risk_approval was missing electronic_sig entirely (unlike qms_approvals/
    # urs_approvals/qual_approvals/val_report_approvals), so routes/risk.py's
    # approval endpoint could not record a non-spoofable e-signature the same
    # way every other suite's approval endpoint already does.
    _add_column_if_missing(conn, "risk_approval", "electronic_sig", "TEXT DEFAULT ''")
    conn.commit()

    # ── Phase 3.5 dual-write bookkeeping (docs/PHASE3_EXECUTION_PLAN.md) ──────
    # Migration bookkeeping only, not part of the target Postgres schema —
    # same pattern as projects.postgres_id (3.2), kb_documents.postgres_id
    # (3.3), equipment.postgres_id (3.4).
    _add_column_if_missing(conn, "risk_assessments", "postgres_id", "TEXT DEFAULT NULL")
    conn.commit()

    # ── Tenant isolation (security fix, docs/SECURITY_REVIEW.md) ──────────────
    from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as _BOOTSTRAP_COMPANY_ID
    _add_column_if_missing(conn, "risk_assessments", "company_id", "TEXT DEFAULT NULL")
    _add_column_if_missing(conn, "risk_library", "company_id", "TEXT DEFAULT NULL")
    conn.commit()
    conn.execute("UPDATE risk_assessments SET company_id = ? WHERE company_id IS NULL", (_BOOTSTRAP_COMPANY_ID,))
    conn.execute("UPDATE risk_library SET company_id = ? WHERE company_id IS NULL", (_BOOTSTRAP_COMPANY_ID,))
    conn.commit()

    # ── URS Management Suite tables ───────────────────────────────────────────
    from pharmagpt.urs_database import URS_SCHEMA
    conn.executescript(URS_SCHEMA)
    conn.commit()

    # ── URS AI generation — background job tracking (additive columns) ───────
    # See services/urs_generation_job.py. generate_requirements() used to
    # stream the Gemini response over the request itself, which held a
    # gunicorn worker for the full generation time and got SIGKILLed by
    # `--timeout=60` on long prompts. Generation now runs on job_runner's
    # thread pool and the frontend polls this state instead.
    # generation_status: 'idle' | 'running' | 'completed' | 'failed'
    _add_column_if_missing(conn, "urs_projects", "generation_status",           "TEXT NOT NULL DEFAULT 'idle'")
    _add_column_if_missing(conn, "urs_projects", "generation_progress_current", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "urs_projects", "generation_progress_total",   "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "urs_projects", "generation_result_count",     "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "urs_projects", "generation_error",            "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "urs_projects", "generation_message",          "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "urs_projects", "generation_started_at",       "TIMESTAMP DEFAULT NULL")
    _add_column_if_missing(conn, "urs_projects", "generation_finished_at",      "TIMESTAMP DEFAULT NULL")
    conn.commit()

    # ── URS document control automation (Stabilization Iteration 2) ──────────
    # See urs_database.py create_urs()/create_version_snapshot(). `version`
    # is the document-control header's version label ("1.0", "2.0", ...),
    # auto-set at creation and kept in sync with the latest urs_versions
    # snapshot — distinct from `revision` (the "A"/"B"/... rework-cycle
    # letter) which already existed as a column.
    _add_column_if_missing(conn, "urs_projects", "version", "TEXT NOT NULL DEFAULT '1.0'")
    conn.commit()

    # ── Tenant isolation (security fix, docs/SECURITY_REVIEW.md) ──────────────
    _add_column_if_missing(conn, "urs_projects", "company_id", "TEXT DEFAULT NULL")
    conn.commit()
    conn.execute("UPDATE urs_projects SET company_id = ? WHERE company_id IS NULL", (BOOTSTRAP_COMPANY_ID,))
    conn.commit()

    # ── Qualification Management Suite tables ─────────────────────────────────
    from pharmagpt.qual_database import QUAL_SCHEMA
    conn.executescript(QUAL_SCHEMA)
    conn.commit()

    # ── Tenant isolation (security fix, docs/SECURITY_REVIEW.md) ──────────────
    _add_column_if_missing(conn, "qual_qualifications", "company_id", "TEXT DEFAULT NULL")
    conn.commit()
    conn.execute("UPDATE qual_qualifications SET company_id = ? WHERE company_id IS NULL", (BOOTSTRAP_COMPANY_ID,))
    conn.commit()

    # ── Validation Report Management Suite tables ──────────────────────────────
    from pharmagpt.report_database import REPORT_SCHEMA
    conn.executescript(REPORT_SCHEMA)
    conn.commit()

    # ── Tenant isolation (security fix, docs/SECURITY_REVIEW.md) ──────────────
    _add_column_if_missing(conn, "val_reports", "company_id", "TEXT DEFAULT NULL")
    conn.commit()
    conn.execute("UPDATE val_reports SET company_id = ? WHERE company_id IS NULL", (BOOTSTRAP_COMPANY_ID,))
    conn.commit()

    # ── Quality Management Suite tables (Document Control, Deviation, CAPA) ────
    from pharmagpt.qms_database import QMS_SCHEMA
    conn.executescript(QMS_SCHEMA)
    conn.commit()

    # ── Phase 3.5 dual-write bookkeeping (docs/PHASE3_EXECUTION_PLAN.md) ──────
    _add_column_if_missing(conn, "qms_deviations", "postgres_id", "TEXT DEFAULT NULL")
    _add_column_if_missing(conn, "qms_capas", "postgres_id", "TEXT DEFAULT NULL")
    _add_column_if_missing(conn, "qms_change_controls", "postgres_id", "TEXT DEFAULT NULL")
    conn.commit()

    # ── Tenant isolation (security fix, docs/SECURITY_REVIEW.md) ──────────────
    for _qms_table in ("qms_deviations", "qms_capas", "qms_change_controls", "qms_documents"):
        _add_column_if_missing(conn, _qms_table, "company_id", "TEXT DEFAULT NULL")
    conn.commit()
    for _qms_table in ("qms_deviations", "qms_capas", "qms_change_controls", "qms_documents"):
        conn.execute(f"UPDATE {_qms_table} SET company_id = ? WHERE company_id IS NULL", (BOOTSTRAP_COMPANY_ID,))
    conn.commit()

    # ── Phase 3 (Enterprise Validation Platform) versioning-triad gap fix ─────
    # qms_documents already had effective_date/review_date/superseded_by, but
    # no superseded_date to say *when* a document was superseded — the last
    # field needed for the full Document Number/Version/Revision/Status/
    # Effective Date/Review Date/Superseded Date/Audit Trail/E-signature set.
    # Stamped by routes/qms_documents.py::submit_approval() when a document
    # transitions to Obsolete, the same way effective_date is already stamped
    # on the transition to Effective.
    _add_column_if_missing(conn, "qms_documents", "superseded_date", "TEXT DEFAULT ''")
    conn.commit()

    # ── Equipment entity (PharmaGPT v1.0 Module 2) ─────────────────────────────
    from pharmagpt.equipment_database import EQUIPMENT_SCHEMA
    conn.executescript(EQUIPMENT_SCHEMA)
    conn.commit()

    # ── Phase 3.4 dual-write bookkeeping (docs/PHASE3_EXECUTION_PLAN.md) ──────
    # Migration bookkeeping only, not part of the target Postgres schema —
    # same pattern as projects.postgres_id (3.2) and kb_documents.postgres_id (3.3).
    _add_column_if_missing(conn, "equipment", "postgres_id", "TEXT DEFAULT NULL")
    _add_column_if_missing(conn, "equipment_documents", "postgres_id", "TEXT DEFAULT NULL")
    conn.commit()

    # ── Phase 2 Module 1 — merge Validation Workspace fields into projects ────
    # Additive columns only; val_projects/val_audit_trail are never dropped or
    # written to going forward, only read once by _migrate_val_projects().
    for _col, _ddl in (
        ("owner",                        "TEXT DEFAULT ''"),
        ("approver",                      "TEXT DEFAULT ''"),
        ("target_date",                   "TEXT DEFAULT NULL"),
        ("risk_category",                 "TEXT DEFAULT ''"),
        ("status",                        "TEXT DEFAULT 'In Progress'"),
        ("model",                         "TEXT DEFAULT ''"),
        ("location",                      "TEXT DEFAULT ''"),
        ("protocol_number",               "TEXT DEFAULT ''"),
        ("report_number",                 "TEXT DEFAULT ''"),
        ("equipment_id",                  "TEXT DEFAULT ''"),
        ("migrated_from_val_project_id",  "INTEGER DEFAULT NULL"),
        ("postgres_id",                   "TEXT DEFAULT NULL"),
    ):
        _add_column_if_missing(conn, "projects", _col, _ddl)
    conn.commit()

    # ── Tenant isolation (security fix, docs/SECURITY_REVIEW.md) ──────────────
    # SQLite predates company_id entirely — see pharmagpt/tenancy.py's module
    # docstring. These columns are additive/backfilled, never destructive:
    # any row created before this column existed lands on the same bootstrap
    # company Postgres already uses for its own pre-migration backfill, so a
    # legacy row is never left orphaned (invisible to everyone) or globally
    # visible (visible to everyone).
    #
    # projects.company_id must exist BEFORE _migrate_val_projects() runs
    # (below) — that function inserts into projects with an explicit
    # company_id value, so the column has to already be there.
    _add_column_if_missing(conn, "projects", "company_id", "TEXT DEFAULT NULL")
    _add_column_if_missing(conn, "kb_documents", "company_id", "TEXT DEFAULT NULL")
    conn.commit()
    conn.execute("UPDATE projects SET company_id = ? WHERE company_id IS NULL", (BOOTSTRAP_COMPANY_ID,))
    conn.execute("UPDATE kb_documents SET company_id = ? WHERE company_id IS NULL", (BOOTSTRAP_COMPANY_ID,))
    conn.commit()

    # ── Phase F: audit-trail completeness (PHARMAGPT_v1.0_PHASE_F...) ─────────
    # qms_audit_trail originally captured only action/detail/performed_by —
    # insufficient for a 21 CFR Part 11 audit trail (Timestamp/User/Company/
    # Object Type/Object ID/Action/Old Value/New Value/Reason/Session-IP/
    # Result). Purely additive; see pharmagpt/audit.py for the writer.
    for _col, _ddl in (
        ("company_id",  "TEXT DEFAULT NULL"),
        ("old_values",  "TEXT DEFAULT ''"),
        ("new_values",  "TEXT DEFAULT ''"),
        ("reason",      "TEXT DEFAULT ''"),
        ("ip_address",  "TEXT DEFAULT ''"),
        ("session_id",  "TEXT DEFAULT ''"),
        ("result",      "TEXT DEFAULT 'success'"),
    ):
        _add_column_if_missing(conn, "qms_audit_trail", _col, _ddl)
    conn.commit()

    _migrate_val_projects(conn)

    conn.close()


def _migrate_val_projects(conn: sqlite3.Connection) -> None:
    """
    One-time, idempotent copy of legacy Validation Workspace rows into the
    unified `projects` table (Phase 2 Module 1: there is now only one Project
    entity — see PROJECT_MEMORY/DECISIONS.md). Guarded by
    `projects.migrated_from_val_project_id` so a val_project already copied is
    never re-copied. `val_projects`/`val_audit_trail` are left physically
    unchanged — no destructive migration, no data loss if this needs to be
    re-run or audited later.
    """
    from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID

    already_migrated = {
        row["migrated_from_val_project_id"]
        for row in conn.execute(
            "SELECT migrated_from_val_project_id FROM projects "
            "WHERE migrated_from_val_project_id IS NOT NULL"
        ).fetchall()
    }
    for vp in conn.execute("SELECT * FROM val_projects").fetchall():
        if vp["id"] in already_migrated:
            continue
        cur = conn.execute(
            """INSERT INTO projects
               (name, equipment_name, manufacturer, department, validation_type,
                owner, approver, target_date, risk_category, status, model,
                location, protocol_number, report_number, equipment_id,
                migrated_from_val_project_id, company_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                vp["name"], vp["equipment_name"], vp["manufacturer"], vp["department"],
                vp["validation_type"], vp["owner"], vp["approver"], vp["target_date"],
                vp["risk_category"], vp["status"], vp["model"], vp["location"],
                vp["protocol_number"], vp["report_number"], vp["equipment_id"], vp["id"],
                BOOTSTRAP_COMPANY_ID,
            ),
        )
        new_project_id = cur.lastrowid
        for entry in conn.execute(
            "SELECT * FROM val_audit_trail WHERE val_proj_id = ? ORDER BY created_at ASC",
            (vp["id"],),
        ).fetchall():
            conn.execute(
                """INSERT INTO qms_audit_trail
                   (record_type, record_id, action, detail, performed_by, created_at)
                   VALUES ('project', ?, ?, ?, '', ?)""",
                (new_project_id, entry["action"], entry["user_note"], entry["created_at"]),
            )
    conn.commit()


# ── Project CRUD ──────────────────────────────────────────────────────────────

def create_project(name: str, equipment_name: str, manufacturer: str,
                   department: str, validation_type: str, *, company_id: str,
                   owner: str = "", approver: str = "", target_date: str | None = None,
                   risk_category: str = "", status: str = "In Progress",
                   model: str = "", location: str = "",
                   protocol_number: str = "", report_number: str = "") -> dict:
    """
    Insert a new project row and return the full project dict.

    `company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`) — never a client-supplied value — see
    pharmagpt/tenancy.py. It is keyword-only and required (no default) so a
    call site cannot silently create an unscoped row by omission.

    The other keyword-only fields (owner, approver, target_date,
    risk_category, status, model, location, protocol_number, report_number)
    were formerly exclusive to the separate Validation Workspace project
    entity (val_projects) — Phase 2 Module 1 merged that entity into this
    one, so every project can now carry them. All are optional so existing
    callers that only pass the original five positional fields keep working.
    """
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO projects
           (name, equipment_name, manufacturer, department, validation_type,
            company_id, owner, approver, target_date, risk_category, status, model,
            location, protocol_number, report_number)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (name, equipment_name, manufacturer, department, validation_type,
         company_id, owner, approver, target_date, risk_category, status, model,
         location, protocol_number, report_number),
    )
    conn.commit()
    project = dict(conn.execute(
        "SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return project


def get_all_projects(company_id: str | None = None) -> list[dict]:
    """Return all projects belonging to `company_id`, ordered newest-first.

    `company_id` must come from the authenticated TenantContext, never from
    client input (pharmagpt/tenancy.py) — this is the primary list endpoint
    a cross-tenant enumeration attack would target. `company_id=None` is
    reserved for offline backfill/parity scripts (service-role key, not a
    live request — see scripts/backfill_projects.py) which need a
    cross-company view; every live route must always pass a company_id.
    """
    conn = get_connection()
    if company_id is None:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM projects WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> dict | None:
    """Return a single project dict, or None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_project(project_id: int, data: dict) -> dict | None:
    """
    Update a project's mutable fields, including the Validation-Workspace
    fields merged in by Phase 2 Module 1 (owner/approver/target_date/
    risk_category/status/model/location/protocol_number/report_number).
    Replaces the old, now-retired PUT /val-projects/<id> (workspace.py).
    """
    conn = get_connection()
    existing = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not existing:
        conn.close()
        return None
    existing = dict(existing)

    def _field(key: str, strip: bool = True) -> object:
        val = data.get(key, existing.get(key) or "")
        return val.strip() if strip and isinstance(val, str) else val

    conn.execute(
        """UPDATE projects SET
           name=?, equipment_name=?, manufacturer=?, department=?, validation_type=?,
           owner=?, approver=?, target_date=?, risk_category=?, status=?, model=?,
           location=?, protocol_number=?, report_number=?
           WHERE id=?""",
        (
            _field("name"), _field("equipment_name"), _field("manufacturer"),
            _field("department"), _field("validation_type"), _field("owner"),
            _field("approver"), data.get("target_date", existing.get("target_date")) or None,
            _field("risk_category"), _field("status") or "In Progress",
            _field("model"), _field("location"), _field("protocol_number"),
            _field("report_number"), project_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_project(project_id: int) -> None:
    """Delete a project and all its messages (cascade handles messages)."""
    conn = get_connection()
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()


def set_project_postgres_id(project_id: int, postgres_id: str) -> None:
    """Record the Postgres `projects.id` (uuid) this SQLite project row was
    dual-written to (Phase 3.2, docs/PHASE3_EXECUTION_PLAN.md). Pure
    migration bookkeeping — postgres_id is not part of the target Postgres
    schema and has no meaning once SQLite is retired (Phase 3.6)."""
    conn = get_connection()
    conn.execute("UPDATE projects SET postgres_id = ? WHERE id = ?", (postgres_id, project_id))
    conn.commit()
    conn.close()


# ── Message CRUD ──────────────────────────────────────────────────────────────

def save_message(project_id: int, role: str, content: str) -> None:
    """Persist one chat turn to the messages table."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (project_id, role, content) VALUES (?, ?, ?)",
        (project_id, role, content),
    )
    conn.commit()
    conn.close()


def get_project_messages(project_id: int) -> list[dict]:
    """Return all messages for a project in chronological order.
    Each dict has keys: role ('user'|'model'), content (str)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE project_id = ? ORDER BY created_at ASC",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_project_messages(project_id: int) -> None:
    """Delete all messages for a project without deleting the project itself."""
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE project_id = ?", (project_id,))
    conn.commit()
    conn.close()


# ── Document CRUD ─────────────────────────────────────────────────────────────

def save_document(project_id: int, original_name: str, stored_filename: str,
                  file_type: str, file_size: int) -> dict:
    """Insert a document metadata row and return the full document dict."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO documents (project_id, original_name, stored_filename, file_type, file_size)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, original_name, stored_filename, file_type, file_size),
    )
    conn.commit()
    doc = dict(conn.execute(
        "SELECT * FROM documents WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return doc


def get_project_documents(project_id: int) -> list[dict]:
    """
    Return all documents for a project, newest first, left-joined with their
    document_text row so the list view can show extraction status/progress
    without a second round-trip per document. `extraction_status` defaults to
    'pending' for a document whose background job hasn't created its
    document_text row yet (should be momentary in practice).
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT d.*,
                  COALESCE(dt.extraction_status, 'pending') AS extraction_status,
                  COALESCE(dt.extraction_progress_current, 0) AS extraction_progress_current,
                  COALESCE(dt.extraction_progress_total, 0)   AS extraction_progress_total,
                  COALESCE(dt.extraction_engine, '')  AS extraction_engine,
                  COALESCE(dt.quality_score, 0)       AS quality_score,
                  COALESCE(dt.pages_failed, 0)         AS pages_failed,
                  dt.page_count, dt.word_count
           FROM documents d
           LEFT JOIN document_text dt ON dt.document_id = d.id
           WHERE d.project_id = ?
           ORDER BY d.upload_date DESC""",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id: int) -> dict | None:
    """Return a single document metadata row, or None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_document(doc_id: int) -> None:
    """Remove a document metadata row from the database.
    The caller is responsible for deleting the file from disk."""
    conn = get_connection()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


# ── Document text CRUD ────────────────────────────────────────────────────────

def create_pending_document_text(document_id: int, project_id: int) -> None:
    """
    Create a placeholder document_text row immediately after a project
    document is uploaded — before the background extraction job has even
    started — so GET /documents/<id>/status always has a row to return
    instead of a transient 404.
    """
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO document_text
           (document_id, project_id, text_content, page_count, word_count, extraction_status)
           VALUES (?, ?, '', 0, 0, 'pending')""",
        (document_id, project_id),
    )
    conn.commit()
    conn.close()


def update_document_text_progress(document_id: int, current: int, total: int,
                                   engine: str = "") -> None:
    """Persist in-flight extraction progress. Called (throttled) from the
    extraction pipeline's progress_cb so any process can poll status."""
    conn = get_connection()
    conn.execute(
        """UPDATE document_text
           SET extraction_status = 'processing',
               extraction_progress_current = ?,
               extraction_progress_total = ?,
               extraction_engine = ?
           WHERE document_id = ?""",
        (current, total, engine, document_id),
    )
    conn.commit()
    conn.close()


def get_document_text_status(document_id: int) -> dict | None:
    """Lightweight status/progress projection for GET /documents/<id>/status."""
    conn = get_connection()
    row = conn.execute(
        """SELECT document_id, extraction_status, extraction_progress_current,
                  extraction_progress_total, extraction_engine, quality_score,
                  pages_failed, page_count, word_count, error_message
           FROM document_text WHERE document_id = ?""",
        (document_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_document_text(document_id: int, project_id: int, text_content: str,
                       page_count: int, word_count: int,
                       extraction_status: str = "ok", *,
                       pages_failed: int = 0, engine_used: str = "",
                       quality_score: float = 0.0, extraction_seconds: float = 0.0,
                       error_message: str = "") -> None:
    """Insert (or replace) extracted text for a document — the final commit
    at the end of extraction (sync or async). Extra keyword-only stats
    parameters are additive; existing positional-only callers keep working."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO document_text
           (document_id, project_id, text_content, page_count, word_count, extraction_status,
            pages_failed, extraction_engine, quality_score, extraction_seconds, error_message,
            extraction_progress_current, extraction_progress_total)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (document_id, project_id, text_content, page_count, word_count, extraction_status,
         pages_failed, engine_used, quality_score, extraction_seconds, error_message,
         page_count, page_count),
    )
    conn.commit()
    conn.close()


def get_document_text(document_id: int) -> dict | None:
    """Return the document_text row for a document, or None if not extracted."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM document_text WHERE document_id = ?", (document_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_document_texts(project_id: int) -> list[dict]:
    """
    Return all extracted texts for a project, joined with original_name
    from the documents table so the caller can cite source file names.

    Each dict has: document_id, original_name, text_content, page_count, word_count
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT dt.document_id, d.original_name, dt.text_content,
                  dt.page_count, dt.word_count, dt.extraction_status
           FROM document_text dt
           JOIN documents d ON d.id = dt.document_id
           WHERE dt.project_id = ?
             AND dt.extraction_status = 'ok'
             AND dt.text_content != ''
           ORDER BY d.upload_date ASC""",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project_insights(project_id: int) -> dict:
    """
    Return aggregated document statistics for the Document Insights page.

    Returns dict with keys:
        document_count  : int
        total_pages     : int
        total_words     : int
        file_types      : dict {ext: count}
        last_upload     : str | None  (ISO timestamp)
        extracted_count : int  (documents with text extraction successful)
    """
    conn = get_connection()

    agg = conn.execute(
        """SELECT
               COUNT(d.id)                   AS document_count,
               MAX(d.upload_date)            AS last_upload,
               COALESCE(SUM(dt.page_count), 0) AS total_pages,
               COALESCE(SUM(dt.word_count), 0) AS total_words,
               COUNT(dt.id)                  AS extracted_count
           FROM documents d
           LEFT JOIN document_text dt
               ON dt.document_id = d.id AND dt.extraction_status = 'ok'
           WHERE d.project_id = ?""",
        (project_id,),
    ).fetchone()

    type_rows = conn.execute(
        "SELECT file_type, COUNT(*) AS cnt FROM documents WHERE project_id = ? GROUP BY file_type",
        (project_id,),
    ).fetchall()

    conn.close()

    file_types = {r["file_type"]: r["cnt"] for r in type_rows}

    return {
        "document_count":  agg["document_count"] or 0,
        "last_upload":     agg["last_upload"],
        "total_pages":     agg["total_pages"] or 0,
        "total_words":     agg["total_words"] or 0,
        "extracted_count": agg["extracted_count"] or 0,
        "file_types":      file_types,
    }


# ── Generated Documents CRUD ──────────────────────────────────────────────────

def save_generated_document(project_id: int, doc_type: str, title: str,
                            form_data_json: str, content: str) -> dict:
    """Persist an AI-generated validation document and return the full row."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO generated_documents
           (project_id, doc_type, title, form_data, content)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, doc_type, title, form_data_json, content),
    )
    conn.commit()
    row = dict(conn.execute(
        "SELECT * FROM generated_documents WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return row


def get_project_generated_documents(project_id: int) -> list[dict]:
    """Return all generated documents for a project, newest first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, project_id, doc_type, title, created_at
           FROM generated_documents WHERE project_id = ? ORDER BY created_at DESC""",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_generated_document(doc_id: int) -> dict | None:
    """Return a single generated document row (including full content)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM generated_documents WHERE id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_generated_document(doc_id: int) -> None:
    """Delete a generated document by id."""
    conn = get_connection()
    conn.execute("DELETE FROM generated_documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


# ── Validation Workspace CRUD (v0.8) — RETIRED (PharmaGPT v1.0 Module 3) ─────
# create_val_project/get_all_val_projects/get_val_project/update_val_project/
# delete_val_project/add_val_audit_entry/get_val_audit_trail were removed —
# their only caller (routes/workspace.py) was deleted when the legacy
# Validation Workspace was retired in favor of the unified Project Workspace.
# val_projects/val_audit_trail remain as read-only historical tables (see
# _migrate_val_projects() above); nothing writes to them anymore. See
# PROJECT_MEMORY/DECISIONS.md DEC-024.


# ── Knowledge Base CRUD ───────────────────────────────────────────────────────

KB_FOLDERS = [
    "SOP", "Validation", "Qualification", "Protocols",
    "Reports", "Regulations", "Vendor Documents", "Others",
]


def create_kb_document(title: str, folder: str, tags: str, doc_version: str,
                       effective_date: str | None, review_date: str | None,
                       original_name: str, stored_filename: str,
                       file_type: str, file_size: int, *, company_id: str) -> dict:
    """Insert a new KB document row and return the full row dict.

    `company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py.
    """
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO kb_documents
           (title, folder, tags, doc_version, effective_date, review_date,
            original_name, stored_filename, file_type, file_size, company_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, folder, tags, doc_version, effective_date or None,
         review_date or None, original_name, stored_filename, file_type, file_size, company_id),
    )
    conn.commit()
    row = dict(conn.execute(
        "SELECT * FROM kb_documents WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return row


def set_kb_document_source(kb_id: int, source_type: str, source_id: int) -> None:
    """Tag a KB document as auto-published from a governed record (Phase 2
    services/kb_sync.py), so the next approval of that same record updates
    this row in place instead of creating a duplicate."""
    conn = get_connection()
    conn.execute(
        "UPDATE kb_documents SET source_type = ?, source_id = ? WHERE id = ?",
        (source_type, source_id, kb_id),
    )
    conn.commit()
    conn.close()


def get_kb_document_by_source(source_type: str, source_id: int, company_id: str) -> dict | None:
    """Return the KB document auto-published from this governed record, if
    any — used by services/kb_sync.py to upsert rather than duplicate on
    every re-approval. Tenant-scoped: company_id must come from the
    authenticated TenantContext, never client input."""
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM kb_documents
           WHERE source_type = ? AND source_id = ? AND company_id = ?""",
        (source_type, source_id, company_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_kb_document_file(kb_id: int, *, title: str, doc_version: str,
                            effective_date: str | None, original_name: str,
                            stored_filename: str, file_type: str, file_size: int) -> dict:
    """Point an existing KB document at a newly re-published file (a new
    effective version of the same governed record) — services/kb_sync.py's
    upsert path. Does not touch folder/tags/company_id/source_type/
    source_id, which stay as originally set."""
    conn = get_connection()
    conn.execute(
        """UPDATE kb_documents
           SET title = ?, doc_version = ?, effective_date = ?, original_name = ?,
               stored_filename = ?, file_type = ?, file_size = ?
           WHERE id = ?""",
        (title, doc_version, effective_date or None, original_name,
         stored_filename, file_type, file_size, kb_id),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM kb_documents WHERE id = ?", (kb_id,)).fetchone())
    conn.close()
    return row


def create_kb_version(kb_document_id: int, version: str, change_summary: str,
                      stored_filename: str, changed_by: str = "") -> dict:
    """Snapshot a KB document's outgoing version before it's overwritten by a
    re-publish/re-upload — see services/kb_sync.py::publish_to_kb(). Mirrors
    qms_document_database.py::create_version()'s shape."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO kb_document_versions (kb_document_id, version, change_summary, stored_filename, changed_by)
           VALUES (?,?,?,?,?)""",
        (kb_document_id, version, change_summary, stored_filename, changed_by),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM kb_document_versions WHERE id = ?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


def get_kb_versions(kb_document_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM kb_document_versions WHERE kb_document_id = ? ORDER BY created_at DESC",
        (kb_document_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_kb_documents(company_id: str | None = None, folder: str | None = None, tag: str | None = None,
                     file_type: str | None = None,
                     keyword: str | None = None,
                     title: str | None = None) -> list[dict]:
    """Return KB documents belonging to `company_id`, with optional filters.
    Excludes text_content for performance.

    `company_id` must come from the authenticated TenantContext, never from
    client input (pharmagpt/tenancy.py). `company_id=None` is reserved for
    offline backfill/parity scripts (service-role key, not a live request —
    see scripts/backfill_kb_documents.py) which need a cross-company view;
    every live route must always pass a company_id.
    """
    conditions: list[str] = []
    params: list = []
    if company_id is not None:
        conditions.append("company_id = ?")
        params.append(company_id)

    if folder:
        conditions.append("folder = ?")
        params.append(folder)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag}%")
    if file_type:
        conditions.append("file_type = ?")
        params.append(file_type)
    if title:
        conditions.append("title LIKE ?")
        params.append(f"%{title}%")
    if keyword:
        conditions.append("(title LIKE ? OR text_content LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT id, title, folder, tags, doc_version, effective_date, review_date,
                   original_name, file_type, file_size, word_count, page_count,
                   extraction_status, upload_date, extraction_progress_current,
                   extraction_progress_total, extraction_engine, quality_score,
                   pages_failed, error_message, postgres_id, company_id
            FROM kb_documents {where} ORDER BY upload_date DESC""",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_kb_document(kb_id: int) -> dict | None:
    """Return a single KB document row including text_content."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM kb_documents WHERE id = ?", (kb_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_kb_document_text(kb_id: int, text_content: str, word_count: int,
                             page_count: int, extraction_status: str, *,
                             pages_failed: int = 0, engine_used: str = "",
                             quality_score: float = 0.0, extraction_seconds: float = 0.0,
                             error_message: str = "") -> None:
    """Store extracted text for a KB document — the final commit at the end
    of extraction (sync or async). Extra keyword-only stats parameters are
    additive; existing positional-only callers keep working."""
    conn = get_connection()
    conn.execute(
        """UPDATE kb_documents
           SET text_content = ?, word_count = ?, page_count = ?, extraction_status = ?,
               pages_failed = ?, extraction_engine = ?, quality_score = ?,
               extraction_seconds = ?, error_message = ?,
               extraction_progress_current = ?, extraction_progress_total = ?
           WHERE id = ?""",
        (text_content, word_count, page_count, extraction_status, pages_failed, engine_used,
         quality_score, extraction_seconds, error_message, page_count, page_count, kb_id),
    )
    conn.commit()
    conn.close()


def mark_kb_pending(kb_id: int) -> None:
    """Reset a KB document to 'pending' — called right after upload (before
    the background job starts) and by the retry endpoint."""
    conn = get_connection()
    conn.execute(
        """UPDATE kb_documents
           SET extraction_status = 'pending', extraction_progress_current = 0,
               extraction_progress_total = 0, extraction_engine = '',
               quality_score = 0, extraction_seconds = 0, pages_failed = 0,
               error_message = ''
           WHERE id = ?""",
        (kb_id,),
    )
    conn.commit()
    conn.close()


def update_kb_progress(kb_id: int, current: int, total: int, engine: str = "") -> None:
    """Persist in-flight extraction progress for a KB document."""
    conn = get_connection()
    conn.execute(
        """UPDATE kb_documents
           SET extraction_status = 'processing', extraction_progress_current = ?,
               extraction_progress_total = ?, extraction_engine = ?
           WHERE id = ?""",
        (current, total, engine, kb_id),
    )
    conn.commit()
    conn.close()


def get_kb_document_status(kb_id: int) -> dict | None:
    """Lightweight status/progress projection for GET /kb/documents/<id>/status."""
    conn = get_connection()
    row = conn.execute(
        """SELECT id, extraction_status, extraction_progress_current, extraction_progress_total,
                  extraction_engine, quality_score, pages_failed, page_count, word_count,
                  error_message
           FROM kb_documents WHERE id = ?""",
        (kb_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_kb_document(kb_id: int) -> None:
    """Delete a KB document row by id."""
    conn = get_connection()
    conn.execute("DELETE FROM kb_documents WHERE id = ?", (kb_id,))
    conn.commit()
    conn.close()


def set_kb_document_postgres_id(kb_id: int, postgres_id: str) -> None:
    """Record the Postgres `documents.id` (uuid) this SQLite kb_documents
    row was dual-written to (Phase 3.3, docs/PHASE3_EXECUTION_PLAN.md).
    Pure migration bookkeeping, same pattern as
    set_project_postgres_id (Phase 3.2)."""
    conn = get_connection()
    conn.execute("UPDATE kb_documents SET postgres_id = ? WHERE id = ?", (postgres_id, kb_id))
    conn.commit()
    conn.close()


def get_kb_folder_counts(company_id: str) -> dict:
    """Return {folder: count} for all KB folders belonging to `company_id`.

    `company_id` must come from the authenticated TenantContext, never from
    client input (pharmagpt/tenancy.py).
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT folder, COUNT(*) AS cnt FROM kb_documents WHERE company_id = ? GROUP BY folder",
        (company_id,),
    ).fetchall()
    conn.close()
    return {r["folder"]: r["cnt"] for r in rows}


# ── Dashboard stats ───────────────────────────────────────────────────────────

def get_dashboard_stats(company_id: str) -> dict:
    """Return all data needed by the Home Dashboard in one query round-trip,
    scoped to `company_id`.

    `company_id` must come from the authenticated TenantContext, never from
    client input (pharmagpt/tenancy.py) — this aggregates project names,
    chat message snippets, and document titles across the whole system, so
    an unscoped query here would be one of the more serious cross-tenant
    content leaks in the app, not just a count leak.
    """
    conn = get_connection()

    counts = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM projects WHERE company_id = :cid)                AS projects,
            (SELECT COUNT(*) FROM projects
               WHERE company_id = :cid
                 AND (target_date IS NOT NULL
                      OR migrated_from_val_project_id IS NOT NULL))                AS val_projects,
            (SELECT COUNT(*) FROM kb_documents WHERE company_id = :cid)            AS kb_documents,
            (SELECT COUNT(*) FROM generated_documents gd
               JOIN projects p ON p.id = gd.project_id
               WHERE p.company_id = :cid)                                          AS protocols_generated,
            (SELECT COUNT(*) FROM qms_capas
               WHERE status NOT IN ('Closed','Rejected') AND company_id = :cid)     AS pending_capas,
            (SELECT COUNT(*) FROM qms_deviations
               WHERE status NOT IN ('Closed','Rejected') AND company_id = :cid)     AS pending_deviations
    """, {"cid": company_id}).fetchone()

    recent_projects = conn.execute(
        """SELECT id, name, equipment_name, validation_type, created_at
           FROM projects WHERE company_id = ? ORDER BY created_at DESC LIMIT 5""",
        (company_id,),
    ).fetchall()

    recent_convs = conn.execute(
        """SELECT m.project_id, p.name AS project_name,
                  SUBSTR(m.content, 1, 160) AS snippet, m.created_at
           FROM messages m
           JOIN projects p ON p.id = m.project_id
           WHERE m.role = 'model' AND p.company_id = ?
           ORDER BY m.created_at DESC LIMIT 5""",
        (company_id,),
    ).fetchall()

    recent_activity = conn.execute(
        """SELECT 'audit'    AS type, qat.action  AS title, p.name   AS context, qat.created_at
           FROM qms_audit_trail qat JOIN projects p ON p.id = qat.record_id
           WHERE qat.record_type = 'project' AND p.company_id = ?
           UNION ALL
           SELECT 'document' AS type, d.original_name AS title, p.name AS context, d.upload_date AS created_at
           FROM documents d JOIN projects p ON p.id = d.project_id
           WHERE p.company_id = ?
           UNION ALL
           SELECT 'kb'       AS type, kb.title AS title, kb.folder AS context, kb.upload_date AS created_at
           FROM kb_documents kb
           WHERE kb.company_id = ?
           UNION ALL
           SELECT 'protocol' AS type, gd.title AS title, p.name AS context, gd.created_at
           FROM generated_documents gd JOIN projects p ON p.id = gd.project_id
           WHERE p.company_id = ?
           ORDER BY created_at DESC LIMIT 10""",
        (company_id, company_id, company_id, company_id),
    ).fetchall()

    upcoming_reviews = conn.execute(
        """SELECT title, folder, review_date, doc_version
           FROM kb_documents
           WHERE review_date IS NOT NULL AND review_date >= date('now') AND company_id = ?
           ORDER BY review_date ASC LIMIT 5""",
        (company_id,),
    ).fetchall()

    upcoming_val = conn.execute(
        """SELECT name, equipment_name, target_date, status, validation_type
           FROM projects
           WHERE target_date IS NOT NULL AND target_date >= date('now') AND status != 'Completed'
             AND company_id = ?
           ORDER BY target_date ASC LIMIT 5""",
        (company_id,),
    ).fetchall()

    health = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM documents d JOIN projects p ON p.id = d.project_id
               WHERE p.company_id = :cid)                                          AS total_docs,
            (SELECT COUNT(*) FROM document_text dt JOIN projects p ON p.id = dt.project_id
               WHERE dt.extraction_status = 'ok' AND p.company_id = :cid)          AS extracted_ok,
            (SELECT COUNT(*) FROM document_text dt JOIN projects p ON p.id = dt.project_id
               WHERE dt.extraction_status = 'error' AND p.company_id = :cid)       AS extracted_error,
            (SELECT COUNT(*) FROM messages m JOIN projects p ON p.id = m.project_id
               WHERE p.company_id = :cid)                                          AS total_messages,
            (SELECT COUNT(*) FROM qms_audit_trail qat JOIN projects p ON p.id = qat.record_id
               WHERE qat.record_type = 'project' AND p.company_id = :cid)          AS audit_entries,
            (SELECT COUNT(*) FROM kb_documents WHERE extraction_status = 'ok' AND company_id = :cid) AS kb_extracted_ok
    """, {"cid": company_id}).fetchone()

    conn.close()

    return {
        "counts":               dict(counts),
        "recent_projects":      [dict(r) for r in recent_projects],
        "recent_conversations": [dict(r) for r in recent_convs],
        "recent_activity":      [dict(r) for r in recent_activity],
        "upcoming_reviews":     [dict(r) for r in upcoming_reviews],
        "upcoming_validations": [dict(r) for r in upcoming_val],
        "system_health":        dict(health),
    }

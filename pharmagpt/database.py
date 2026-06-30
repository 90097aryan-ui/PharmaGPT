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
val_projects        : Validation Workspace projects (v0.8) with full equipment,
                      personnel, schedule, and risk-tier metadata.
val_audit_trail     : Immutable log of every action within a validation project.
kb_documents        : Global Knowledge Base — permanent document library not
                      tied to any project. Supports folder, tag, and full-text search.

All tables are created automatically on first startup via init_db().
Database file: pharmagpt/pharmagpt.db
"""

import sqlite3
import os

# Absolute path to the SQLite file — sits inside the pharmagpt/ package folder.
DB_PATH = os.path.join(os.path.dirname(__file__), "pharmagpt.db")


def get_connection() -> sqlite3.Connection:
    """Open (or create) the database and return a connection.
    row_factory=sqlite3.Row makes every row behave like a dict."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce foreign-key constraints (SQLite disables them by default)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they do not already exist. Safe to call on every startup."""
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
    """)
    conn.commit()

    # ── Risk Management Suite tables ──────────────────────────────────────────
    from pharmagpt.risk_database import RISK_SCHEMA
    conn.executescript(RISK_SCHEMA)
    conn.commit()

    # ── URS Management Suite tables ───────────────────────────────────────────
    from pharmagpt.urs_database import URS_SCHEMA
    conn.executescript(URS_SCHEMA)
    conn.commit()

    # ── Qualification Management Suite tables ─────────────────────────────────
    from pharmagpt.qual_database import QUAL_SCHEMA
    conn.executescript(QUAL_SCHEMA)
    conn.commit()

    # ── Validation Report Management Suite tables ──────────────────────────────
    from pharmagpt.report_database import REPORT_SCHEMA
    conn.executescript(REPORT_SCHEMA)
    conn.commit()

    conn.close()


# ── Project CRUD ──────────────────────────────────────────────────────────────

def create_project(name: str, equipment_name: str, manufacturer: str,
                   department: str, validation_type: str) -> dict:
    """Insert a new project row and return the full project dict."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO projects (name, equipment_name, manufacturer, department, validation_type)
           VALUES (?, ?, ?, ?, ?)""",
        (name, equipment_name, manufacturer, department, validation_type),
    )
    conn.commit()
    project = dict(conn.execute(
        "SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return project


def get_all_projects() -> list[dict]:
    """Return all projects ordered newest-first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY created_at DESC"
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


def delete_project(project_id: int) -> None:
    """Delete a project and all its messages (cascade handles messages)."""
    conn = get_connection()
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
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
    """Return all documents for a project, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM documents WHERE project_id = ? ORDER BY upload_date DESC",
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

def save_document_text(document_id: int, project_id: int, text_content: str,
                       page_count: int, word_count: int,
                       extraction_status: str = "ok") -> None:
    """Insert (or replace) extracted text for a document."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO document_text
           (document_id, project_id, text_content, page_count, word_count, extraction_status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (document_id, project_id, text_content, page_count, word_count, extraction_status),
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


# ── Validation Workspace CRUD (v0.8) ─────────────────────────────────────────

def create_val_project(data: dict) -> dict:
    """Insert a new validation project and return the full row."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO val_projects
           (name, equipment_name, equipment_id, department, manufacturer,
            model, location, validation_type, protocol_number, report_number,
            owner, approver, target_date, risk_category)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("name", "").strip(),
            data.get("equipment_name", "").strip(),
            data.get("equipment_id", "").strip(),
            data.get("department", "").strip(),
            data.get("manufacturer", "").strip(),
            data.get("model", "").strip(),
            data.get("location", "").strip(),
            data.get("validation_type", "").strip(),
            data.get("protocol_number", "").strip(),
            data.get("report_number", "").strip(),
            data.get("owner", "").strip(),
            data.get("approver", "").strip(),
            data.get("target_date") or None,
            data.get("risk_category", "").strip(),
        ),
    )
    conn.commit()
    row = dict(conn.execute(
        "SELECT * FROM val_projects WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return row


def get_all_val_projects() -> list[dict]:
    """Return all validation projects, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM val_projects ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_val_project(val_proj_id: int) -> dict | None:
    """Return a single validation project, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM val_projects WHERE id = ?", (val_proj_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_val_project(val_proj_id: int, data: dict) -> dict | None:
    """Update mutable fields on a validation project."""
    conn = get_connection()
    conn.execute(
        """UPDATE val_projects SET
           name=?, equipment_name=?, equipment_id=?, department=?,
           manufacturer=?, model=?, location=?, validation_type=?,
           protocol_number=?, report_number=?, owner=?, approver=?,
           target_date=?, risk_category=?, status=?
           WHERE id=?""",
        (
            data.get("name", "").strip(),
            data.get("equipment_name", "").strip(),
            data.get("equipment_id", "").strip(),
            data.get("department", "").strip(),
            data.get("manufacturer", "").strip(),
            data.get("model", "").strip(),
            data.get("location", "").strip(),
            data.get("validation_type", "").strip(),
            data.get("protocol_number", "").strip(),
            data.get("report_number", "").strip(),
            data.get("owner", "").strip(),
            data.get("approver", "").strip(),
            data.get("target_date") or None,
            data.get("risk_category", "").strip(),
            data.get("status", "In Progress").strip(),
            val_proj_id,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM val_projects WHERE id = ?", (val_proj_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_val_project(val_proj_id: int) -> None:
    """Delete a validation project (audit trail cascades)."""
    conn = get_connection()
    conn.execute("DELETE FROM val_projects WHERE id = ?", (val_proj_id,))
    conn.commit()
    conn.close()


def add_val_audit_entry(val_proj_id: int, action: str, user_note: str = "") -> dict:
    """Append an audit trail entry and return the inserted row."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO val_audit_trail (val_proj_id, action, user_note) VALUES (?,?,?)",
        (val_proj_id, action, user_note),
    )
    conn.commit()
    row = dict(conn.execute(
        "SELECT * FROM val_audit_trail WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return row


def get_val_audit_trail(val_proj_id: int) -> list[dict]:
    """Return all audit entries for a validation project, oldest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM val_audit_trail WHERE val_proj_id = ? ORDER BY created_at ASC",
        (val_proj_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Knowledge Base CRUD ───────────────────────────────────────────────────────

KB_FOLDERS = [
    "SOP", "Validation", "Qualification", "Protocols",
    "Reports", "Regulations", "Vendor Documents", "Others",
]


def create_kb_document(title: str, folder: str, tags: str, doc_version: str,
                       effective_date: str | None, review_date: str | None,
                       original_name: str, stored_filename: str,
                       file_type: str, file_size: int) -> dict:
    """Insert a new KB document row and return the full row dict."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO kb_documents
           (title, folder, tags, doc_version, effective_date, review_date,
            original_name, stored_filename, file_type, file_size)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, folder, tags, doc_version, effective_date or None,
         review_date or None, original_name, stored_filename, file_type, file_size),
    )
    conn.commit()
    row = dict(conn.execute(
        "SELECT * FROM kb_documents WHERE id = ?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return row


def get_kb_documents(folder: str | None = None, tag: str | None = None,
                     file_type: str | None = None,
                     keyword: str | None = None,
                     title: str | None = None) -> list[dict]:
    """Return KB documents with optional filters. Excludes text_content for performance."""
    conditions: list[str] = []
    params: list = []

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
                   extraction_status, upload_date
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
                             page_count: int, extraction_status: str) -> None:
    """Store extracted text for a KB document after upload."""
    conn = get_connection()
    conn.execute(
        """UPDATE kb_documents
           SET text_content = ?, word_count = ?, page_count = ?, extraction_status = ?
           WHERE id = ?""",
        (text_content, word_count, page_count, extraction_status, kb_id),
    )
    conn.commit()
    conn.close()


def delete_kb_document(kb_id: int) -> None:
    """Delete a KB document row by id."""
    conn = get_connection()
    conn.execute("DELETE FROM kb_documents WHERE id = ?", (kb_id,))
    conn.commit()
    conn.close()


def get_kb_folder_counts() -> dict:
    """Return {folder: count} for all KB folders."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT folder, COUNT(*) AS cnt FROM kb_documents GROUP BY folder"
    ).fetchall()
    conn.close()
    return {r["folder"]: r["cnt"] for r in rows}


# ── Dashboard stats ───────────────────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    """Return all data needed by the Home Dashboard in one query round-trip."""
    conn = get_connection()

    counts = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM projects)                                   AS projects,
            (SELECT COUNT(*) FROM val_projects)                               AS val_projects,
            (SELECT COUNT(*) FROM kb_documents)                               AS kb_documents,
            (SELECT COUNT(*) FROM generated_documents)                        AS protocols_generated,
            (SELECT COUNT(*) FROM generated_documents WHERE doc_type='CAPA')  AS pending_capas,
            (SELECT COUNT(*) FROM generated_documents WHERE doc_type='Deviation') AS pending_deviations
    """).fetchone()

    recent_projects = conn.execute(
        """SELECT id, name, equipment_name, validation_type, created_at
           FROM projects ORDER BY created_at DESC LIMIT 5"""
    ).fetchall()

    recent_convs = conn.execute(
        """SELECT m.project_id, p.name AS project_name,
                  SUBSTR(m.content, 1, 160) AS snippet, m.created_at
           FROM messages m
           JOIN projects p ON p.id = m.project_id
           WHERE m.role = 'model'
           ORDER BY m.created_at DESC LIMIT 5"""
    ).fetchall()

    recent_activity = conn.execute(
        """SELECT 'audit'    AS type, vat.action  AS title, vp.name  AS context, vat.created_at
           FROM val_audit_trail vat JOIN val_projects vp ON vp.id = vat.val_proj_id
           UNION ALL
           SELECT 'document' AS type, d.original_name AS title, p.name AS context, d.upload_date AS created_at
           FROM documents d JOIN projects p ON p.id = d.project_id
           UNION ALL
           SELECT 'kb'       AS type, kb.title AS title, kb.folder AS context, kb.upload_date AS created_at
           FROM kb_documents kb
           UNION ALL
           SELECT 'protocol' AS type, gd.title AS title, p.name AS context, gd.created_at
           FROM generated_documents gd JOIN projects p ON p.id = gd.project_id
           ORDER BY created_at DESC LIMIT 10"""
    ).fetchall()

    upcoming_reviews = conn.execute(
        """SELECT title, folder, review_date, doc_version
           FROM kb_documents
           WHERE review_date IS NOT NULL AND review_date >= date('now')
           ORDER BY review_date ASC LIMIT 5"""
    ).fetchall()

    upcoming_val = conn.execute(
        """SELECT name, equipment_name, target_date, status, validation_type
           FROM val_projects
           WHERE target_date IS NOT NULL AND target_date >= date('now') AND status != 'Completed'
           ORDER BY target_date ASC LIMIT 5"""
    ).fetchall()

    health = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM documents)                                        AS total_docs,
            (SELECT COUNT(*) FROM document_text WHERE extraction_status = 'ok')     AS extracted_ok,
            (SELECT COUNT(*) FROM document_text WHERE extraction_status = 'error')  AS extracted_error,
            (SELECT COUNT(*) FROM messages)                                         AS total_messages,
            (SELECT COUNT(*) FROM val_audit_trail)                                  AS audit_entries,
            (SELECT COUNT(*) FROM kb_documents WHERE extraction_status = 'ok')      AS kb_extracted_ok
    """).fetchone()

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

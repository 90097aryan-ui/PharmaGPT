"""
urs_database.py — SQLite CRUD for the URS Management Suite.

Tables
──────
urs_projects      : Master URS record (one per URS document)
urs_requirements  : Individual requirement rows per URS
urs_approvals     : Immutable approval / review audit trail
urs_versions      : Snapshot of requirements at each version point
"""

import json
from datetime import datetime
from pharmagpt.database import get_connection


# ── Schema (imported by database.init_db) ────────────────────────────────────

URS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS urs_projects (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        urs_number          TEXT    NOT NULL DEFAULT '',
        doc_number          TEXT    DEFAULT '',
        title               TEXT    NOT NULL,
        revision            TEXT    DEFAULT 'A',
        status              TEXT    DEFAULT 'draft',
        department          TEXT    DEFAULT '',
        site                TEXT    DEFAULT '',
        location            TEXT    DEFAULT '',
        equipment_name      TEXT    DEFAULT '',
        equipment_id        TEXT    DEFAULT '',
        manufacturer        TEXT    DEFAULT '',
        model               TEXT    DEFAULT '',
        capacity            TEXT    DEFAULT '',
        category            TEXT    DEFAULT '',
        equipment_type      TEXT    DEFAULT '',
        validation_type     TEXT    DEFAULT '',
        purpose             TEXT    DEFAULT '',
        intended_use        TEXT    DEFAULT '',
        process_description TEXT    DEFAULT '',
        prepared_by         TEXT    DEFAULT '',
        reviewed_by         TEXT    DEFAULT '',
        approved_by         TEXT    DEFAULT '',
        effective_date      TEXT    DEFAULT '',
        linked_project_id   INTEGER DEFAULT NULL,
        ai_review_data      TEXT    DEFAULT '{}',
        compliance_score    INTEGER DEFAULT 0,
        completeness_score  INTEGER DEFAULT 0,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS urs_requirements (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        urs_id              INTEGER NOT NULL,
        req_id              TEXT    NOT NULL DEFAULT '',
        section             TEXT    NOT NULL DEFAULT 'General',
        requirement         TEXT    NOT NULL DEFAULT '',
        rationale           TEXT    DEFAULT '',
        priority            TEXT    DEFAULT 'Medium',
        gmp_criticality     TEXT    DEFAULT 'GMP',
        regulatory_ref      TEXT    DEFAULT '',
        verification_method TEXT    DEFAULT '',
        acceptance_criteria TEXT    DEFAULT '',
        risk_link           TEXT    DEFAULT '',
        traceability_link   TEXT    DEFAULT '',
        comments            TEXT    DEFAULT '',
        status              TEXT    DEFAULT 'draft',
        source              TEXT    DEFAULT 'ai',
        sort_order          INTEGER DEFAULT 0,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (urs_id) REFERENCES urs_projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS urs_approvals (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        urs_id       INTEGER NOT NULL,
        action       TEXT    NOT NULL,
        performed_by TEXT    DEFAULT '',
        role         TEXT    DEFAULT '',
        comments     TEXT    DEFAULT '',
        version      TEXT    DEFAULT '',
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (urs_id) REFERENCES urs_projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS urs_versions (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        urs_id                INTEGER NOT NULL,
        version               TEXT    NOT NULL,
        revision              TEXT    DEFAULT 'A',
        status                TEXT    DEFAULT 'draft',
        change_summary        TEXT    DEFAULT '',
        requirements_snapshot TEXT    DEFAULT '[]',
        req_count             INTEGER DEFAULT 0,
        created_by            TEXT    DEFAULT '',
        created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (urs_id) REFERENCES urs_projects(id) ON DELETE CASCADE
    );

    -- urs_numbering: atomic per-year sequence counters backing
    -- _next_document_number(). One row per (series, year) — 'series'
    -- distinguishes the URS Number sequence from the Document Number
    -- sequence so they can grow independently. Sequence state lives here,
    -- not derived from urs_projects rows, so a deleted URS never frees its
    -- number for reuse (document control requires numbers stay unique
    -- forever, not just among currently-existing rows).
    CREATE TABLE IF NOT EXISTS urs_numbering (
        series   TEXT    NOT NULL,
        year     INTEGER NOT NULL,
        last_seq INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (series, year)
    );
"""


# ── Document Control Automation ───────────────────────────────────────────────
# Server-issued, never client-supplied. See routes/urs.py create_urs()/
# add_approval() for how these are wired into the create and approval flows.

def _next_document_number(series: str, prefix: str) -> str:
    """Atomically allocate the next sequential number in `series` for the
    current calendar year and return it formatted as PREFIX-YYYY-NNN.

    Uses urs_numbering as a dedicated counter table (rather than COUNT(*) or
    MAX() over urs_projects) so a deleted URS never frees its number for
    reuse, and concurrent creates under SQLite's serialized writers never
    race to the same number."""
    year = datetime.now().year
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO urs_numbering (series, year, last_seq) VALUES (?, ?, 0) "
            "ON CONFLICT(series, year) DO NOTHING",
            (series, year),
        )
        conn.execute(
            "UPDATE urs_numbering SET last_seq = last_seq + 1 WHERE series = ? AND year = ?",
            (series, year),
        )
        seq = conn.execute(
            "SELECT last_seq FROM urs_numbering WHERE series = ? AND year = ?",
            (series, year),
        ).fetchone()[0]
    conn.close()
    return f"{prefix}-{year}-{seq:03d}"


# ── URS Projects ──────────────────────────────────────────────────────────────

def create_urs(data: dict, *, company_id: str) -> dict:
    """Create a new URS. Document-control fields are entirely system-issued:
    urs_number/doc_number are auto-numbered, revision/version always start
    at 'A'/'1.0', status always starts at 'draft', and reviewed_by/
    approved_by/effective_date start blank — none of these are read from
    `data` even if a caller supplies them (closes the previous bypass where
    a client could POST {"status": "approved"} directly at creation time).
    prepared_by is still read from `data`; routes/urs.py's create_urs() is
    responsible for populating it from the authenticated user before calling
    this function.

    `company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py.
    """
    urs_number = _next_document_number("urs_number", "URS")
    doc_number = _next_document_number("doc_number", "QA-URS")
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO urs_projects
               (urs_number, doc_number, title, revision, version, status, department, site, location,
                equipment_name, equipment_id, manufacturer, model, capacity, category,
                equipment_type, validation_type, purpose, intended_use, process_description,
                prepared_by, reviewed_by, approved_by, effective_date, linked_project_id, company_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                urs_number,
                doc_number,
                data.get("title", "Untitled URS"),
                "A",
                "1.0",
                "draft",
                data.get("department", ""),
                data.get("site", ""),
                data.get("location", ""),
                data.get("equipment_name", ""),
                data.get("equipment_id", ""),
                data.get("manufacturer", ""),
                data.get("model", ""),
                data.get("capacity", ""),
                data.get("category", ""),
                data.get("equipment_type", ""),
                data.get("validation_type", ""),
                data.get("purpose", ""),
                data.get("intended_use", ""),
                data.get("process_description", ""),
                data.get("prepared_by", ""),
                "",
                "",
                "",
                data.get("linked_project_id"),
                company_id,
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    add_approval_entry(new_id, "URS Created", data.get("prepared_by", "System"), "Author",
                       "Initial draft created", "A")
    return get_urs(new_id)


def get_urs(urs_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM urs_projects WHERE id = ?", (urs_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
    return d


def get_all_urs(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts (service-role key, not a live
    request); every live route must always pass a company_id."""
    conn = get_connection()
    where_clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("status", "category", "department", "equipment_type"):
            if filters.get(field):
                where_clauses.append(f"{field} = ?")
                params.append(filters[field])
        if filters.get("keyword"):
            where_clauses.append("(title LIKE ? OR equipment_name LIKE ? OR urs_number LIKE ?)")
            kw = f"%{filters['keyword']}%"
            params += [kw, kw, kw]
    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    rows = conn.execute(
        f"SELECT * FROM urs_projects {where} ORDER BY created_at DESC", params
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
        result.append(d)
    return result


def update_urs(urs_id: int, data: dict) -> dict | None:
    allowed = [
        "urs_number", "doc_number", "title", "revision", "status", "department", "site",
        "location", "equipment_name", "equipment_id", "manufacturer", "model", "capacity",
        "category", "equipment_type", "validation_type", "purpose", "intended_use",
        "process_description", "prepared_by", "reviewed_by", "approved_by", "effective_date",
        "compliance_score", "completeness_score", "ai_review_data",
    ]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return get_urs(urs_id)
    if "ai_review_data" in updates and isinstance(updates["ai_review_data"], dict):
        updates["ai_review_data"] = json.dumps(updates["ai_review_data"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [urs_id]
    conn = get_connection()
    with conn:
        conn.execute(
            f"UPDATE urs_projects SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
    conn.close()
    return get_urs(urs_id)


# ── AI Generation Job Tracking ────────────────────────────────────────────────
# See services/urs_generation_job.py. Generation runs on a background thread
# (services/job_runner.py); these functions are how that thread reports
# progress and how routes/urs.py's polling endpoint reads it back. Status
# lives in SQLite (not memory) so it is visible regardless of which gunicorn
# worker/thread handles a given poll request.

def start_generation(urs_id: int, total_batches: int) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """UPDATE urs_projects
               SET generation_status = 'running',
                   generation_progress_current = 0,
                   generation_progress_total = ?,
                   generation_result_count = 0,
                   generation_error = '',
                   generation_started_at = CURRENT_TIMESTAMP,
                   generation_finished_at = NULL
               WHERE id = ?""",
            (total_batches, urs_id),
        )
    conn.close()


def update_generation_progress(urs_id: int, current_batch: int, result_count: int) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """UPDATE urs_projects
               SET generation_progress_current = ?, generation_result_count = ?
               WHERE id = ?""",
            (current_batch, result_count, urs_id),
        )
    conn.close()


def finish_generation(
    urs_id: int, status: str, total_batches: int, result_count: int,
    error: str = "", message: str = "",
) -> None:
    """Atomically write the terminal generation state — status, final
    progress (current == total), result_count, and message/error — in a
    single UPDATE statement.

    This is the only place generation_status ever becomes 'completed' or
    'failed', and it is always written together with the result_count that
    goes with it. Previously the last per-batch update_generation_progress()
    call published the final result_count on its own, with status still
    'running' until a separate, later finish_generation() call (after the
    full save_requirements() pass) flipped it — a poll landing in that gap
    could observe "N requirements generated" next to generation_status:
    'running', which the frontend had no consistent way to reconcile (the
    root cause of the old "59 requirements" / "taking longer than expected"
    contradiction). Folding the final progress+count+status into one
    statement — and persisting requirements incrementally per batch instead
    of in one bulk save at the end (see append_requirements) — closes that
    window entirely rather than just narrowing it.
    """
    conn = get_connection()
    with conn:
        conn.execute(
            """UPDATE urs_projects
               SET generation_status = ?, generation_progress_current = ?,
                   generation_progress_total = ?, generation_result_count = ?,
                   generation_error = ?, generation_message = ?,
                   generation_finished_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, total_batches, total_batches, result_count, error, message, urs_id),
        )
    conn.close()


def get_generation_status(urs_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT generation_status, generation_progress_current, generation_progress_total,
                  generation_result_count, generation_error, generation_message,
                  generation_started_at, generation_finished_at
           FROM urs_projects WHERE id = ?""",
        (urs_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_urs(urs_id: int) -> bool:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM urs_projects WHERE id = ?", (urs_id,))
    conn.close()
    return True


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    total       = conn.execute("SELECT COUNT(*) FROM urs_projects WHERE company_id = ?", (company_id,)).fetchone()[0]
    draft       = conn.execute("SELECT COUNT(*) FROM urs_projects WHERE status='draft' AND company_id = ?", (company_id,)).fetchone()[0]
    under_review= conn.execute("SELECT COUNT(*) FROM urs_projects WHERE status='under_review' AND company_id = ?", (company_id,)).fetchone()[0]
    approved    = conn.execute("SELECT COUNT(*) FROM urs_projects WHERE status='approved' AND company_id = ?", (company_id,)).fetchone()[0]
    obsolete    = conn.execute("SELECT COUNT(*) FROM urs_projects WHERE status='obsolete' AND company_id = ?", (company_id,)).fetchone()[0]
    total_reqs  = conn.execute(
        "SELECT COUNT(*) FROM urs_requirements r JOIN urs_projects p ON p.id = r.urs_id WHERE p.company_id = ?",
        (company_id,),
    ).fetchone()[0]
    by_category = {}
    for row in conn.execute(
        "SELECT category, COUNT(*) FROM urs_projects WHERE company_id = ? GROUP BY category", (company_id,)
    ).fetchall():
        by_category[row[0] or "Other"] = row[1]
    recent = conn.execute(
        "SELECT id, title, status, equipment_name, category, created_at FROM urs_projects "
        "WHERE company_id = ? ORDER BY created_at DESC LIMIT 8",
        (company_id,),
    ).fetchall()
    pending_approval = conn.execute(
        "SELECT COUNT(*) FROM urs_projects WHERE status IN ('under_review','pending_approval') AND company_id = ?",
        (company_id,),
    ).fetchone()[0]
    conn.close()
    return {
        "total": total, "draft": draft, "under_review": under_review,
        "approved": approved, "obsolete": obsolete,
        "pending_approval": pending_approval,
        "total_requirements": total_reqs,
        "by_category": by_category,
        "recent": [dict(r) for r in recent],
    }


# ── Requirements ──────────────────────────────────────────────────────────────

def get_requirements(urs_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM urs_requirements WHERE urs_id = ? ORDER BY sort_order, section, req_id",
        (urs_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_requirements(urs_id: int, requirements: list[dict]) -> list[dict]:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM urs_requirements WHERE urs_id = ?", (urs_id,))
        for i, req in enumerate(requirements):
            conn.execute(
                """INSERT INTO urs_requirements
                   (urs_id, req_id, section, requirement, rationale, priority,
                    gmp_criticality, regulatory_ref, verification_method,
                    acceptance_criteria, risk_link, traceability_link,
                    comments, status, source, sort_order)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    urs_id,
                    req.get("req_id", f"REQ-{i+1:03d}"),
                    req.get("section", "General"),
                    req.get("requirement", ""),
                    req.get("rationale", ""),
                    req.get("priority", "Medium"),
                    req.get("gmp_criticality", "GMP"),
                    req.get("regulatory_ref", ""),
                    req.get("verification_method", "Functional Test"),
                    req.get("acceptance_criteria", ""),
                    req.get("risk_link", ""),
                    req.get("traceability_link", ""),
                    req.get("comments", ""),
                    req.get("status", "draft"),
                    req.get("source", "ai"),
                    i,
                ),
            )
        conn.execute(
            "UPDATE urs_projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (urs_id,)
        )
    conn.close()
    return get_requirements(urs_id)


def append_requirements(urs_id: int, requirements: list[dict]) -> list[dict]:
    """Insert new requirement rows without touching any existing ones.

    Used by services/urs_generation_job.py to persist each AI generation
    batch as soon as it completes, rather than accumulating every batch in
    memory and writing them all in one save_requirements() call at the very
    end. This closes the window where a background-job crash between "Gemini
    finished" and "the bulk save ran" would silently lose already-generated
    requirements, and it means generation_result_count always reflects rows
    that are actually in the table, not just an in-memory tally."""
    if not requirements:
        return get_requirements(urs_id)
    conn = get_connection()
    with conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM urs_requirements WHERE urs_id = ?",
            (urs_id,),
        ).fetchone()[0]
        for offset, req in enumerate(requirements, start=1):
            conn.execute(
                """INSERT INTO urs_requirements
                   (urs_id, req_id, section, requirement, rationale, priority,
                    gmp_criticality, regulatory_ref, verification_method,
                    acceptance_criteria, risk_link, traceability_link,
                    comments, status, source, sort_order)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    urs_id,
                    req.get("req_id", ""),
                    req.get("section", "General"),
                    req.get("requirement", ""),
                    req.get("rationale", ""),
                    req.get("priority", "Medium"),
                    req.get("gmp_criticality", "GMP"),
                    req.get("regulatory_ref", ""),
                    req.get("verification_method", "Functional Test"),
                    req.get("acceptance_criteria", ""),
                    req.get("risk_link", ""),
                    req.get("traceability_link", ""),
                    req.get("comments", ""),
                    req.get("status", "draft"),
                    req.get("source", "ai"),
                    max_order + offset,
                ),
            )
        conn.execute(
            "UPDATE urs_projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (urs_id,)
        )
    conn.close()
    return get_requirements(urs_id)


def add_requirement(urs_id: int, req: dict) -> dict:
    conn = get_connection()
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM urs_requirements WHERE urs_id = ?", (urs_id,)
    ).fetchone()[0]
    with conn:
        cur = conn.execute(
            """INSERT INTO urs_requirements
               (urs_id, req_id, section, requirement, rationale, priority,
                gmp_criticality, regulatory_ref, verification_method,
                acceptance_criteria, risk_link, traceability_link,
                comments, status, source, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                urs_id,
                req.get("req_id", ""),
                req.get("section", "General"),
                req.get("requirement", ""),
                req.get("rationale", ""),
                req.get("priority", "Medium"),
                req.get("gmp_criticality", "GMP"),
                req.get("regulatory_ref", ""),
                req.get("verification_method", "Functional Test"),
                req.get("acceptance_criteria", ""),
                req.get("risk_link", ""),
                req.get("traceability_link", ""),
                req.get("comments", ""),
                req.get("status", "draft"),
                req.get("source", "manual"),
                max_order + 1,
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM urs_requirements WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    return dict(row) if row else {}


def update_requirement(req_id: int, data: dict) -> dict | None:
    allowed = [
        "req_id", "section", "requirement", "rationale", "priority", "gmp_criticality",
        "regulatory_ref", "verification_method", "acceptance_criteria",
        "risk_link", "traceability_link", "comments", "status",
    ]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [req_id]
    conn = get_connection()
    with conn:
        conn.execute(f"UPDATE urs_requirements SET {set_clause} WHERE id = ?", values)
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM urs_requirements WHERE id = ?", (req_id,)).fetchone()
    conn2.close()
    return dict(row) if row else None


def delete_requirement(req_id: int) -> bool:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM urs_requirements WHERE id = ?", (req_id,))
    conn.close()
    return True


# ── Approval Workflow ─────────────────────────────────────────────────────────

def add_approval_entry(
    urs_id: int, action: str, performed_by: str,
    role: str = "", comments: str = "", version: str = ""
) -> dict:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            "INSERT INTO urs_approvals (urs_id, action, performed_by, role, comments, version) VALUES (?,?,?,?,?,?)",
            (urs_id, action, performed_by, role, comments, version),
        )
        new_id = cur.lastrowid
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM urs_approvals WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    return dict(row) if row else {}


def get_approval_trail(urs_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM urs_approvals WHERE urs_id = ? ORDER BY created_at ASC", (urs_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Version History ───────────────────────────────────────────────────────────

def create_version_snapshot(urs_id: int, change_summary: str, created_by: str) -> dict:
    urs = get_urs(urs_id)
    if not urs:
        return {}
    reqs = get_requirements(urs_id)
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM urs_versions WHERE urs_id = ?", (urs_id,)
    ).fetchone()[0]
    conn.close()
    version_num = f"v{count + 1}.0"
    conn2 = get_connection()
    with conn2:
        cur = conn2.execute(
            """INSERT INTO urs_versions
               (urs_id, version, revision, status, change_summary, requirements_snapshot, req_count, created_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                urs_id, version_num, urs.get("revision", "A"), urs.get("status", "draft"),
                change_summary, json.dumps(reqs), len(reqs), created_by,
            ),
        )
        new_id = cur.lastrowid
        # Keep the document-control header's `version` field (auto-generated,
        # see create_urs) in sync with the latest snapshot so it never drifts
        # from the version history it's summarizing.
        conn2.execute(
            "UPDATE urs_projects SET version = ? WHERE id = ?",
            (f"{count + 1}.0", urs_id),
        )
    conn2.close()
    conn3 = get_connection()
    row = conn3.execute("SELECT * FROM urs_versions WHERE id = ?", (new_id,)).fetchone()
    conn3.close()
    return dict(row) if row else {}


def get_versions(urs_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, urs_id, version, revision, status, change_summary,
                  req_count, created_by, created_at
           FROM urs_versions WHERE urs_id = ? ORDER BY created_at DESC""",
        (urs_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_version_requirements(version_id: int) -> list[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT requirements_snapshot FROM urs_versions WHERE id = ?", (version_id,)
    ).fetchone()
    conn.close()
    if not row:
        return []
    return json.loads(row[0] or "[]")

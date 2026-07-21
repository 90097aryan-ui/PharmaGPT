"""
qual_database.py — SQLite CRUD for the Qualification Management Suite (IQ/OQ/PQ).

Tables
──────
qual_qualifications  : Master qualification record per equipment/project
qual_protocols       : IQ / OQ / PQ protocol documents (one per type per qual)
qual_test_cases      : Individual test cases with URS + Risk traceability links
qual_executions      : Test execution results (pass/fail/actual results)
qual_deviations      : Deviations raised during execution
qual_attachments     : Evidence files linked to executions or protocols
qual_approvals       : Immutable approval / review audit trail
qual_versions        : Protocol version history snapshots
qual_ai_reviews      : AI review results per protocol
"""

import json
import sqlite3
from pharmagpt.database import get_connection


# ── Schema ────────────────────────────────────────────────────────────────────

QUAL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS qual_qualifications (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        qual_number         TEXT    DEFAULT '',
        title               TEXT    NOT NULL,
        revision            TEXT    DEFAULT 'A',
        status              TEXT    DEFAULT 'draft',
        equipment_name      TEXT    DEFAULT '',
        equipment_id        TEXT    DEFAULT '',
        equipment_type      TEXT    DEFAULT '',
        manufacturer        TEXT    DEFAULT '',
        model               TEXT    DEFAULT '',
        serial_number       TEXT    DEFAULT '',
        capacity            TEXT    DEFAULT '',
        department          TEXT    DEFAULT '',
        site                TEXT    DEFAULT '',
        location            TEXT    DEFAULT '',
        category            TEXT    DEFAULT '',
        validation_type     TEXT    DEFAULT 'IQ/OQ/PQ',
        scope               TEXT    DEFAULT '',
        purpose             TEXT    DEFAULT '',
        process_description TEXT    DEFAULT '',
        system_description  TEXT    DEFAULT '',
        drawing_refs        TEXT    DEFAULT '',
        document_refs       TEXT    DEFAULT '',
        manufacturer_details TEXT   DEFAULT '',
        linked_project_id   INTEGER DEFAULT NULL,
        linked_urs_id       INTEGER DEFAULT NULL,
        linked_risk_id      INTEGER DEFAULT NULL,
        prepared_by         TEXT    DEFAULT '',
        reviewed_by         TEXT    DEFAULT '',
        approved_by         TEXT    DEFAULT '',
        effective_date      TEXT    DEFAULT '',
        planned_start       TEXT    DEFAULT '',
        planned_end         TEXT    DEFAULT '',
        actual_start        TEXT    DEFAULT '',
        actual_end          TEXT    DEFAULT '',
        iq_status           TEXT    DEFAULT 'not_started',
        oq_status           TEXT    DEFAULT 'not_started',
        pq_status           TEXT    DEFAULT 'not_started',
        overall_status      TEXT    DEFAULT 'not_started',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS qual_protocols (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        qual_id             INTEGER NOT NULL,
        protocol_type       TEXT    NOT NULL CHECK(protocol_type IN ('IQ','OQ','PQ')),
        protocol_number     TEXT    DEFAULT '',
        title               TEXT    DEFAULT '',
        revision            TEXT    DEFAULT 'A',
        status              TEXT    DEFAULT 'draft',
        scope               TEXT    DEFAULT '',
        purpose             TEXT    DEFAULT '',
        references_text     TEXT    DEFAULT '',
        definitions         TEXT    DEFAULT '',
        responsibilities    TEXT    DEFAULT '',
        system_description  TEXT    DEFAULT '',
        summary             TEXT    DEFAULT '',
        conclusion          TEXT    DEFAULT '',
        ai_generated        INTEGER DEFAULT 0,
        ai_review_data      TEXT    DEFAULT '{}',
        compliance_score    INTEGER DEFAULT 0,
        completeness_score  INTEGER DEFAULT 0,
        pass_count          INTEGER DEFAULT 0,
        fail_count          INTEGER DEFAULT 0,
        pending_count       INTEGER DEFAULT 0,
        deviation_count     INTEGER DEFAULT 0,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (qual_id) REFERENCES qual_qualifications(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qual_test_cases (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        protocol_id         INTEGER NOT NULL,
        qual_id             INTEGER NOT NULL,
        test_id             TEXT    DEFAULT '',
        section             TEXT    DEFAULT 'General',
        test_name           TEXT    NOT NULL DEFAULT '',
        objective           TEXT    DEFAULT '',
        prerequisites       TEXT    DEFAULT '',
        test_procedure      TEXT    DEFAULT '',
        expected_result     TEXT    DEFAULT '',
        acceptance_criteria TEXT    DEFAULT '',
        equipment_required  TEXT    DEFAULT '',
        materials_required  TEXT    DEFAULT '',
        gmp_criticality     TEXT    DEFAULT 'GMP',
        risk_level          TEXT    DEFAULT 'Medium',
        regulatory_ref      TEXT    DEFAULT '',
        urs_req_ids         TEXT    DEFAULT '[]',
        risk_item_ids       TEXT    DEFAULT '[]',
        status              TEXT    DEFAULT 'pending',
        sort_order          INTEGER DEFAULT 0,
        source              TEXT    DEFAULT 'ai',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (protocol_id) REFERENCES qual_protocols(id) ON DELETE CASCADE,
        FOREIGN KEY (qual_id)     REFERENCES qual_qualifications(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qual_executions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        test_case_id        INTEGER NOT NULL,
        protocol_id         INTEGER NOT NULL,
        qual_id             INTEGER NOT NULL,
        actual_result       TEXT    DEFAULT '',
        result              TEXT    DEFAULT 'pending' CHECK(result IN ('pending','pass','fail','na')),
        comments            TEXT    DEFAULT '',
        deviation_ref       TEXT    DEFAULT '',
        executed_by         TEXT    DEFAULT '',
        executed_date       TEXT    DEFAULT '',
        reviewed_by         TEXT    DEFAULT '',
        reviewed_date       TEXT    DEFAULT '',
        electronic_sig      TEXT    DEFAULT '',
        sig_date            TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (test_case_id) REFERENCES qual_test_cases(id) ON DELETE CASCADE,
        FOREIGN KEY (protocol_id)  REFERENCES qual_protocols(id)  ON DELETE CASCADE,
        FOREIGN KEY (qual_id)      REFERENCES qual_qualifications(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qual_deviations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        qual_id             INTEGER NOT NULL,
        protocol_id         INTEGER DEFAULT NULL,
        test_case_id        INTEGER DEFAULT NULL,
        deviation_number    TEXT    DEFAULT '',
        title               TEXT    DEFAULT '',
        description         TEXT    DEFAULT '',
        impact              TEXT    DEFAULT 'Minor',
        root_cause          TEXT    DEFAULT '',
        corrective_action   TEXT    DEFAULT '',
        status              TEXT    DEFAULT 'open',
        raised_by           TEXT    DEFAULT '',
        raised_date         TEXT    DEFAULT '',
        closed_by           TEXT    DEFAULT '',
        closed_date         TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (qual_id) REFERENCES qual_qualifications(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qual_attachments (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        qual_id             INTEGER NOT NULL,
        protocol_id         INTEGER DEFAULT NULL,
        execution_id        INTEGER DEFAULT NULL,
        filename            TEXT    NOT NULL,
        original_name       TEXT    DEFAULT '',
        file_type           TEXT    DEFAULT '',
        file_size           INTEGER DEFAULT 0,
        description         TEXT    DEFAULT '',
        uploaded_by         TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (qual_id) REFERENCES qual_qualifications(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qual_approvals (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        qual_id             INTEGER NOT NULL,
        protocol_id         INTEGER DEFAULT NULL,
        action              TEXT    NOT NULL,
        performed_by        TEXT    DEFAULT '',
        role                TEXT    DEFAULT '',
        comments            TEXT    DEFAULT '',
        version             TEXT    DEFAULT '',
        electronic_sig      TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (qual_id) REFERENCES qual_qualifications(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qual_versions (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        qual_id                 INTEGER NOT NULL,
        protocol_id             INTEGER NOT NULL,
        protocol_type           TEXT    NOT NULL,
        version                 TEXT    NOT NULL,
        revision                TEXT    DEFAULT 'A',
        status                  TEXT    DEFAULT 'draft',
        change_summary          TEXT    DEFAULT '',
        test_cases_snapshot     TEXT    DEFAULT '[]',
        test_count              INTEGER DEFAULT 0,
        pass_count              INTEGER DEFAULT 0,
        fail_count              INTEGER DEFAULT 0,
        created_by              TEXT    DEFAULT '',
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (qual_id)     REFERENCES qual_qualifications(id) ON DELETE CASCADE,
        FOREIGN KEY (protocol_id) REFERENCES qual_protocols(id)      ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qual_ai_reviews (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        protocol_id         INTEGER NOT NULL,
        qual_id             INTEGER NOT NULL,
        review_type         TEXT    DEFAULT 'ai',
        compliance_score    INTEGER DEFAULT 0,
        completeness_score  INTEGER DEFAULT 0,
        risk_coverage_score INTEGER DEFAULT 0,
        overall_score       INTEGER DEFAULT 0,
        recommendation      TEXT    DEFAULT '',
        strengths           TEXT    DEFAULT '[]',
        missing_tests       TEXT    DEFAULT '[]',
        duplicate_tests     TEXT    DEFAULT '[]',
        improvements        TEXT    DEFAULT '[]',
        regulatory_gaps     TEXT    DEFAULT '[]',
        executive_summary   TEXT    DEFAULT '',
        full_review_data    TEXT    DEFAULT '{}',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (protocol_id) REFERENCES qual_protocols(id)      ON DELETE CASCADE,
        FOREIGN KEY (qual_id)     REFERENCES qual_qualifications(id) ON DELETE CASCADE
    );
"""


# ── Qualifications ────────────────────────────────────────────────────────────

def create_qualification(data: dict, *, company_id: str) -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO qual_qualifications
               (qual_number, title, revision, status, equipment_name, equipment_id,
                equipment_type, manufacturer, model, serial_number, capacity,
                department, site, location, category, validation_type, scope, purpose,
                process_description, system_description, drawing_refs, document_refs,
                manufacturer_details, linked_project_id, linked_urs_id, linked_risk_id,
                prepared_by, reviewed_by, approved_by, effective_date,
                planned_start, planned_end, company_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("qual_number", ""),
                data.get("title", "Untitled Qualification"),
                data.get("revision", "A"),
                data.get("status", "draft"),
                data.get("equipment_name", ""),
                data.get("equipment_id", ""),
                data.get("equipment_type", ""),
                data.get("manufacturer", ""),
                data.get("model", ""),
                data.get("serial_number", ""),
                data.get("capacity", ""),
                data.get("department", ""),
                data.get("site", ""),
                data.get("location", ""),
                data.get("category", ""),
                data.get("validation_type", "IQ/OQ/PQ"),
                data.get("scope", ""),
                data.get("purpose", ""),
                data.get("process_description", ""),
                data.get("system_description", ""),
                data.get("drawing_refs", ""),
                data.get("document_refs", ""),
                data.get("manufacturer_details", ""),
                data.get("linked_project_id"),
                data.get("linked_urs_id"),
                data.get("linked_risk_id"),
                data.get("prepared_by", ""),
                data.get("reviewed_by", ""),
                data.get("approved_by", ""),
                data.get("effective_date", ""),
                data.get("planned_start", ""),
                data.get("planned_end", ""),
                company_id,
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    add_approval_entry(new_id, None, "Qualification Created",
                       data.get("prepared_by", "System"), "Author", "Initial draft created")
    return get_qualification(new_id)


def get_qualification(qual_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qual_qualifications WHERE id = ?", (qual_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_qualifications(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts; every live route must always pass
    a company_id."""
    conn = get_connection()
    where_clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("status", "category", "department", "equipment_type", "iq_status", "oq_status", "pq_status"):
            if filters.get(field):
                where_clauses.append(f"{field} = ?")
                params.append(filters[field])
        if filters.get("keyword"):
            where_clauses.append("(title LIKE ? OR equipment_name LIKE ? OR qual_number LIKE ?)")
            kw = f"%{filters['keyword']}%"
            params += [kw, kw, kw]
    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    rows = conn.execute(
        f"SELECT * FROM qual_qualifications {where} ORDER BY created_at DESC", params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_qualification(qual_id: int, data: dict) -> dict | None:
    allowed = [
        "qual_number", "title", "revision", "status", "equipment_name", "equipment_id",
        "equipment_type", "manufacturer", "model", "serial_number", "capacity",
        "department", "site", "location", "category", "validation_type", "scope", "purpose",
        "process_description", "system_description", "drawing_refs", "document_refs",
        "manufacturer_details", "linked_project_id", "linked_urs_id", "linked_risk_id",
        "prepared_by", "reviewed_by", "approved_by", "effective_date",
        "planned_start", "planned_end", "actual_start", "actual_end",
        "iq_status", "oq_status", "pq_status", "overall_status",
    ]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return get_qualification(qual_id)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [qual_id]
    conn = get_connection()
    with conn:
        conn.execute(
            f"UPDATE qual_qualifications SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
    conn.close()
    return get_qualification(qual_id)


def delete_qualification(qual_id: int) -> bool:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM qual_qualifications WHERE id = ?", (qual_id,))
    conn.close()
    return True


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    total       = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE company_id = ?", (company_id,)).fetchone()[0]
    draft       = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE status='draft' AND company_id = ?", (company_id,)).fetchone()[0]
    in_progress = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE status='in_progress' AND company_id = ?", (company_id,)).fetchone()[0]
    completed   = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE status='completed' AND company_id = ?", (company_id,)).fetchone()[0]
    approved    = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE status='approved' AND company_id = ?", (company_id,)).fetchone()[0]

    iq_complete = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE iq_status='completed' AND company_id = ?", (company_id,)).fetchone()[0]
    oq_complete = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE oq_status='completed' AND company_id = ?", (company_id,)).fetchone()[0]
    pq_complete = conn.execute("SELECT COUNT(*) FROM qual_qualifications WHERE pq_status='completed' AND company_id = ?", (company_id,)).fetchone()[0]

    total_tests  = conn.execute(
        "SELECT COUNT(*) FROM qual_test_cases t JOIN qual_qualifications q ON q.id = t.qual_id WHERE q.company_id = ?",
        (company_id,),
    ).fetchone()[0]
    pass_count   = conn.execute(
        """SELECT COUNT(*) FROM qual_executions e
           JOIN qual_test_cases t ON t.id = e.test_case_id
           JOIN qual_qualifications q ON q.id = t.qual_id
           WHERE e.result='pass' AND q.company_id = ?""",
        (company_id,),
    ).fetchone()[0]
    fail_count   = conn.execute(
        """SELECT COUNT(*) FROM qual_executions e
           JOIN qual_test_cases t ON t.id = e.test_case_id
           JOIN qual_qualifications q ON q.id = t.qual_id
           WHERE e.result='fail' AND q.company_id = ?""",
        (company_id,),
    ).fetchone()[0]
    open_devs    = conn.execute(
        """SELECT COUNT(*) FROM qual_deviations d
           JOIN qual_qualifications q ON q.id = d.qual_id
           WHERE d.status='open' AND q.company_id = ?""",
        (company_id,),
    ).fetchone()[0]
    pending_approvals = conn.execute(
        "SELECT COUNT(*) FROM qual_qualifications WHERE status IN ('under_review','pending_approval') AND company_id = ?",
        (company_id,),
    ).fetchone()[0]

    recent = conn.execute(
        """SELECT id, qual_number, title, equipment_name, status, iq_status, oq_status, pq_status, created_at
           FROM qual_qualifications WHERE company_id = ? ORDER BY created_at DESC LIMIT 8""",
        (company_id,),
    ).fetchall()
    conn.close()

    return {
        "total": total, "draft": draft, "in_progress": in_progress,
        "completed": completed, "approved": approved,
        "iq_complete": iq_complete, "oq_complete": oq_complete, "pq_complete": pq_complete,
        "total_tests": total_tests, "pass_count": pass_count, "fail_count": fail_count,
        "open_deviations": open_devs, "pending_approvals": pending_approvals,
        "recent": [dict(r) for r in recent],
    }


# ── Protocols ─────────────────────────────────────────────────────────────────

def create_protocol(qual_id: int, protocol_type: str, data: dict) -> dict:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO qual_protocols
               (qual_id, protocol_type, protocol_number, title, revision, status,
                scope, purpose, references_text, definitions, responsibilities,
                system_description, summary, conclusion)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                qual_id,
                protocol_type,
                data.get("protocol_number", ""),
                data.get("title", f"{protocol_type} Protocol"),
                data.get("revision", "A"),
                data.get("status", "draft"),
                data.get("scope", ""),
                data.get("purpose", ""),
                data.get("references_text", ""),
                data.get("definitions", ""),
                data.get("responsibilities", ""),
                data.get("system_description", ""),
                data.get("summary", ""),
                data.get("conclusion", ""),
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    return get_protocol(new_id)


def get_protocol(protocol_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qual_protocols WHERE id = ?", (protocol_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
    return d


def get_protocols_for_qual(qual_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qual_protocols WHERE qual_id = ? ORDER BY protocol_type",
        (qual_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
        result.append(d)
    return result


def update_protocol(protocol_id: int, data: dict) -> dict | None:
    allowed = [
        "protocol_number", "title", "revision", "status", "scope", "purpose",
        "references_text", "definitions", "responsibilities", "system_description",
        "summary", "conclusion", "ai_generated", "ai_review_data",
        "compliance_score", "completeness_score", "pass_count", "fail_count",
        "pending_count", "deviation_count",
    ]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return get_protocol(protocol_id)
    if "ai_review_data" in updates and isinstance(updates["ai_review_data"], dict):
        updates["ai_review_data"] = json.dumps(updates["ai_review_data"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [protocol_id]
    conn = get_connection()
    with conn:
        conn.execute(
            f"UPDATE qual_protocols SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
    conn.close()
    return get_protocol(protocol_id)


def delete_protocol(protocol_id: int) -> bool:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM qual_protocols WHERE id = ?", (protocol_id,))
    conn.close()
    return True


# ── Test Cases ────────────────────────────────────────────────────────────────

def get_test_cases(protocol_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qual_test_cases WHERE protocol_id = ? ORDER BY sort_order, section, test_id",
        (protocol_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["urs_req_ids"]   = json.loads(d.get("urs_req_ids")   or "[]")
        d["risk_item_ids"] = json.loads(d.get("risk_item_ids") or "[]")
        result.append(d)
    return result


def save_test_cases(protocol_id: int, qual_id: int, test_cases: list[dict]) -> list[dict]:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM qual_test_cases WHERE protocol_id = ?", (protocol_id,))
        for i, tc in enumerate(test_cases):
            urs_ids  = json.dumps(tc.get("urs_req_ids", []))
            risk_ids = json.dumps(tc.get("risk_item_ids", []))
            conn.execute(
                """INSERT INTO qual_test_cases
                   (protocol_id, qual_id, test_id, section, test_name, objective,
                    prerequisites, test_procedure, expected_result, acceptance_criteria,
                    equipment_required, materials_required, gmp_criticality, risk_level,
                    regulatory_ref, urs_req_ids, risk_item_ids, status, sort_order, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    protocol_id, qual_id,
                    tc.get("test_id", f"TC-{i+1:03d}"),
                    tc.get("section", "General"),
                    tc.get("test_name", ""),
                    tc.get("objective", ""),
                    tc.get("prerequisites", ""),
                    tc.get("test_procedure", ""),
                    tc.get("expected_result", ""),
                    tc.get("acceptance_criteria", ""),
                    tc.get("equipment_required", ""),
                    tc.get("materials_required", ""),
                    tc.get("gmp_criticality", "GMP"),
                    tc.get("risk_level", "Medium"),
                    tc.get("regulatory_ref", ""),
                    urs_ids, risk_ids,
                    tc.get("status", "pending"),
                    i,
                    tc.get("source", "ai"),
                ),
            )
        conn.execute(
            "UPDATE qual_protocols SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (protocol_id,)
        )
    conn.close()
    _refresh_protocol_counts(protocol_id)
    return get_test_cases(protocol_id)


def add_test_case(protocol_id: int, qual_id: int, tc: dict) -> dict:
    conn = get_connection()
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM qual_test_cases WHERE protocol_id = ?", (protocol_id,)
    ).fetchone()[0]
    urs_ids  = json.dumps(tc.get("urs_req_ids", []))
    risk_ids = json.dumps(tc.get("risk_item_ids", []))
    with conn:
        cur = conn.execute(
            """INSERT INTO qual_test_cases
               (protocol_id, qual_id, test_id, section, test_name, objective,
                prerequisites, test_procedure, expected_result, acceptance_criteria,
                equipment_required, materials_required, gmp_criticality, risk_level,
                regulatory_ref, urs_req_ids, risk_item_ids, status, sort_order, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                protocol_id, qual_id,
                tc.get("test_id", ""),
                tc.get("section", "General"),
                tc.get("test_name", ""),
                tc.get("objective", ""),
                tc.get("prerequisites", ""),
                tc.get("test_procedure", ""),
                tc.get("expected_result", ""),
                tc.get("acceptance_criteria", ""),
                tc.get("equipment_required", ""),
                tc.get("materials_required", ""),
                tc.get("gmp_criticality", "GMP"),
                tc.get("risk_level", "Medium"),
                tc.get("regulatory_ref", ""),
                urs_ids, risk_ids,
                tc.get("status", "pending"),
                max_order + 1,
                tc.get("source", "manual"),
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM qual_test_cases WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    if not row:
        return {}
    d = dict(row)
    d["urs_req_ids"]   = json.loads(d.get("urs_req_ids")   or "[]")
    d["risk_item_ids"] = json.loads(d.get("risk_item_ids") or "[]")
    return d


def update_test_case(tc_id: int, data: dict) -> dict | None:
    allowed = [
        "test_id", "section", "test_name", "objective", "prerequisites",
        "test_procedure", "expected_result", "acceptance_criteria",
        "equipment_required", "materials_required", "gmp_criticality",
        "risk_level", "regulatory_ref", "urs_req_ids", "risk_item_ids", "status",
    ]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return None
    for json_field in ("urs_req_ids", "risk_item_ids"):
        if json_field in updates and isinstance(updates[json_field], list):
            updates[json_field] = json.dumps(updates[json_field])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [tc_id]
    conn = get_connection()
    with conn:
        conn.execute(f"UPDATE qual_test_cases SET {set_clause} WHERE id = ?", values)
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM qual_test_cases WHERE id = ?", (tc_id,)).fetchone()
    conn2.close()
    if not row:
        return None
    d = dict(row)
    d["urs_req_ids"]   = json.loads(d.get("urs_req_ids")   or "[]")
    d["risk_item_ids"] = json.loads(d.get("risk_item_ids") or "[]")
    return d


def delete_test_case(tc_id: int) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT protocol_id FROM qual_test_cases WHERE id = ?", (tc_id,)).fetchone()
    protocol_id = row[0] if row else None
    with conn:
        conn.execute("DELETE FROM qual_test_cases WHERE id = ?", (tc_id,))
    conn.close()
    if protocol_id:
        _refresh_protocol_counts(protocol_id)
    return True


# ── Executions ────────────────────────────────────────────────────────────────

def get_executions(protocol_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qual_executions WHERE protocol_id = ? ORDER BY created_at", (protocol_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_execution_for_test(test_case_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM qual_executions WHERE test_case_id = ? ORDER BY created_at DESC LIMIT 1",
        (test_case_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_execution(test_case_id: int, protocol_id: int, qual_id: int, data: dict) -> dict:
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM qual_executions WHERE test_case_id = ?", (test_case_id,)
    ).fetchone()
    with conn:
        if existing:
            conn.execute(
                """UPDATE qual_executions
                   SET actual_result=?, result=?, comments=?, deviation_ref=?,
                       executed_by=?, executed_date=?, reviewed_by=?, reviewed_date=?,
                       electronic_sig=?, sig_date=?, updated_at=CURRENT_TIMESTAMP
                   WHERE test_case_id=?""",
                (
                    data.get("actual_result", ""),
                    data.get("result", "pending"),
                    data.get("comments", ""),
                    data.get("deviation_ref", ""),
                    data.get("executed_by", ""),
                    data.get("executed_date", ""),
                    data.get("reviewed_by", ""),
                    data.get("reviewed_date", ""),
                    data.get("electronic_sig", ""),
                    data.get("sig_date", ""),
                    test_case_id,
                ),
            )
            exec_id = existing[0]
        else:
            cur = conn.execute(
                """INSERT INTO qual_executions
                   (test_case_id, protocol_id, qual_id, actual_result, result, comments,
                    deviation_ref, executed_by, executed_date, reviewed_by, reviewed_date,
                    electronic_sig, sig_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    test_case_id, protocol_id, qual_id,
                    data.get("actual_result", ""),
                    data.get("result", "pending"),
                    data.get("comments", ""),
                    data.get("deviation_ref", ""),
                    data.get("executed_by", ""),
                    data.get("executed_date", ""),
                    data.get("reviewed_by", ""),
                    data.get("reviewed_date", ""),
                    data.get("electronic_sig", ""),
                    data.get("sig_date", ""),
                ),
            )
            exec_id = cur.lastrowid
        # Update test case status
        result = data.get("result", "pending")
        tc_status = {"pass": "pass", "fail": "fail", "na": "na"}.get(result, "pending")
        conn.execute("UPDATE qual_test_cases SET status=? WHERE id=?", (tc_status, test_case_id))
    conn.close()
    _refresh_protocol_counts(protocol_id)
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM qual_executions WHERE id = ?", (exec_id,)).fetchone()
    conn2.close()
    return dict(row) if row else {}


def _refresh_protocol_counts(protocol_id: int) -> None:
    conn = get_connection()
    tc_pass    = conn.execute("SELECT COUNT(*) FROM qual_test_cases WHERE protocol_id=? AND status='pass'", (protocol_id,)).fetchone()[0]
    tc_fail    = conn.execute("SELECT COUNT(*) FROM qual_test_cases WHERE protocol_id=? AND status='fail'", (protocol_id,)).fetchone()[0]
    tc_pending = conn.execute("SELECT COUNT(*) FROM qual_test_cases WHERE protocol_id=? AND status='pending'", (protocol_id,)).fetchone()[0]
    dev_count  = conn.execute(
        "SELECT COUNT(*) FROM qual_deviations WHERE protocol_id=? AND status='open'", (protocol_id,)
    ).fetchone()[0]
    with conn:
        conn.execute(
            "UPDATE qual_protocols SET pass_count=?, fail_count=?, pending_count=?, deviation_count=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (tc_pass, tc_fail, tc_pending, dev_count, protocol_id),
        )
    conn.close()


# ── Deviations ────────────────────────────────────────────────────────────────

def create_deviation(qual_id: int, data: dict) -> dict:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM qual_deviations WHERE qual_id=?", (qual_id,)).fetchone()[0]
    dev_number = f"DEV-{qual_id:03d}-{count+1:03d}"
    with conn:
        cur = conn.execute(
            """INSERT INTO qual_deviations
               (qual_id, protocol_id, test_case_id, deviation_number, title,
                description, impact, root_cause, corrective_action, status,
                raised_by, raised_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                qual_id,
                data.get("protocol_id"),
                data.get("test_case_id"),
                data.get("deviation_number", dev_number),
                data.get("title", ""),
                data.get("description", ""),
                data.get("impact", "Minor"),
                data.get("root_cause", ""),
                data.get("corrective_action", ""),
                data.get("status", "open"),
                data.get("raised_by", ""),
                data.get("raised_date", ""),
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM qual_deviations WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    return dict(row) if row else {}


def get_deviations(qual_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qual_deviations WHERE qual_id = ? ORDER BY created_at DESC", (qual_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_deviation(dev_id: int, data: dict) -> dict | None:
    allowed = ["title", "description", "impact", "root_cause", "corrective_action",
               "status", "raised_by", "raised_date", "closed_by", "closed_date"]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [dev_id]
    conn = get_connection()
    with conn:
        conn.execute(f"UPDATE qual_deviations SET {set_clause} WHERE id = ?", values)
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM qual_deviations WHERE id = ?", (dev_id,)).fetchone()
    conn2.close()
    return dict(row) if row else None


# ── Approvals ─────────────────────────────────────────────────────────────────

def add_approval_entry(qual_id: int, protocol_id, action: str, performed_by: str,
                       role: str = "", comments: str = "", version: str = "",
                       electronic_sig: str = "") -> dict:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO qual_approvals
               (qual_id, protocol_id, action, performed_by, role, comments, version, electronic_sig)
               VALUES (?,?,?,?,?,?,?,?)""",
            (qual_id, protocol_id, action, performed_by, role, comments, version, electronic_sig),
        )
        new_id = cur.lastrowid
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM qual_approvals WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    return dict(row) if row else {}


def get_approval_trail(qual_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qual_approvals WHERE qual_id = ? ORDER BY created_at ASC", (qual_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Version History ───────────────────────────────────────────────────────────

def create_version_snapshot(qual_id: int, protocol_id: int, change_summary: str, created_by: str) -> dict:
    protocol = get_protocol(protocol_id)
    if not protocol:
        return {}
    test_cases = get_test_cases(protocol_id)
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM qual_versions WHERE protocol_id = ?", (protocol_id,)
    ).fetchone()[0]
    conn.close()
    version_num = f"v{count + 1}.0"
    pass_c   = sum(1 for tc in test_cases if tc.get("status") == "pass")
    fail_c   = sum(1 for tc in test_cases if tc.get("status") == "fail")
    conn2 = get_connection()
    with conn2:
        cur = conn2.execute(
            """INSERT INTO qual_versions
               (qual_id, protocol_id, protocol_type, version, revision, status,
                change_summary, test_cases_snapshot, test_count, pass_count, fail_count, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                qual_id, protocol_id, protocol.get("protocol_type", ""),
                version_num, protocol.get("revision", "A"), protocol.get("status", "draft"),
                change_summary, json.dumps(test_cases), len(test_cases), pass_c, fail_c, created_by,
            ),
        )
        new_id = cur.lastrowid
    conn2.close()
    conn3 = get_connection()
    row = conn3.execute("SELECT * FROM qual_versions WHERE id = ?", (new_id,)).fetchone()
    conn3.close()
    return dict(row) if row else {}


def get_versions(qual_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, qual_id, protocol_id, protocol_type, version, revision, status,
                  change_summary, test_count, pass_count, fail_count, created_by, created_at
           FROM qual_versions WHERE qual_id = ? ORDER BY created_at DESC""",
        (qual_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── AI Reviews ────────────────────────────────────────────────────────────────

def save_ai_review(protocol_id: int, qual_id: int, review_data: dict) -> dict:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO qual_ai_reviews
               (protocol_id, qual_id, compliance_score, completeness_score,
                risk_coverage_score, overall_score, recommendation,
                strengths, missing_tests, duplicate_tests, improvements,
                regulatory_gaps, executive_summary, full_review_data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                protocol_id, qual_id,
                review_data.get("compliance_score", 0),
                review_data.get("completeness_score", 0),
                review_data.get("risk_coverage_score", 0),
                review_data.get("overall_score", 0),
                review_data.get("recommendation", ""),
                json.dumps(review_data.get("strengths", [])),
                json.dumps(review_data.get("missing_tests", [])),
                json.dumps(review_data.get("duplicate_tests", [])),
                json.dumps(review_data.get("improvements", [])),
                json.dumps(review_data.get("regulatory_gaps", [])),
                review_data.get("executive_summary", ""),
                json.dumps(review_data),
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    update_protocol(protocol_id, {
        "compliance_score": review_data.get("compliance_score", 0),
        "completeness_score": review_data.get("completeness_score", 0),
        "ai_review_data": review_data,
    })
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM qual_ai_reviews WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    if not row:
        return {}
    d = dict(row)
    for f in ("strengths", "missing_tests", "duplicate_tests", "improvements", "regulatory_gaps", "full_review_data"):
        try:
            d[f] = json.loads(d.get(f) or "[]" if f != "full_review_data" else d.get(f) or "{}")
        except Exception:
            pass
    return d


def get_latest_ai_review(protocol_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM qual_ai_reviews WHERE protocol_id = ? ORDER BY created_at DESC LIMIT 1",
        (protocol_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for f in ("strengths", "missing_tests", "duplicate_tests", "improvements", "regulatory_gaps"):
        try:
            d[f] = json.loads(d.get(f) or "[]")
        except Exception:
            d[f] = []
    try:
        d["full_review_data"] = json.loads(d.get("full_review_data") or "{}")
    except Exception:
        d["full_review_data"] = {}
    return d


# ── Traceability Matrix ───────────────────────────────────────────────────────

def build_traceability_matrix(qual_id: int) -> dict:
    """Auto-generate traceability matrix from linked URS req IDs and risk item IDs."""
    conn = get_connection()
    qual = get_qualification(qual_id)
    test_cases = conn.execute(
        "SELECT * FROM qual_test_cases WHERE qual_id = ? ORDER BY sort_order",
        (qual_id,),
    ).fetchall()
    conn.close()

    urs_map: dict[str, list] = {}
    risk_map: dict[str, list] = {}
    matrix_rows = []

    for tc in test_cases:
        d = dict(tc)
        urs_ids  = json.loads(d.get("urs_req_ids")   or "[]")
        risk_ids = json.loads(d.get("risk_item_ids") or "[]")
        tc_entry = {
            "test_id": d.get("test_id", ""),
            "test_name": d.get("test_name", ""),
            "section": d.get("section", ""),
            "status": d.get("status", "pending"),
            "gmp_criticality": d.get("gmp_criticality", ""),
            "urs_req_ids": urs_ids,
            "risk_item_ids": risk_ids,
        }
        matrix_rows.append(tc_entry)
        for uid in urs_ids:
            if uid not in urs_map:
                urs_map[uid] = []
            urs_map[uid].append(d.get("test_id", ""))
        for rid in risk_ids:
            if rid not in risk_map:
                risk_map[rid] = []
            risk_map[rid].append(d.get("test_id", ""))

    return {
        "qual_id": qual_id,
        "qual_number": qual.get("qual_number", "") if qual else "",
        "equipment_name": qual.get("equipment_name", "") if qual else "",
        "matrix_rows": matrix_rows,
        "urs_coverage": urs_map,
        "risk_coverage": risk_map,
        "total_tests": len(matrix_rows),
        "urs_ids_covered": len(urs_map),
        "risk_ids_covered": len(risk_map),
    }

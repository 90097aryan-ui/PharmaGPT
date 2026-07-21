"""
report_database.py — SQLite CRUD for the Validation Report Management Suite (VRMS).

Tables
──────
val_reports          : Master validation report record (one per qualification lifecycle)
val_report_sections  : Individual report sections with generated/edited content
val_report_approvals : Immutable approval / review audit trail
val_report_versions  : Snapshot of report at each version point
val_report_ai_reviews: AI review results and scores
"""

import json
from pharmagpt.database import get_connection


# ── Schema ────────────────────────────────────────────────────────────────────

REPORT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS val_reports (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        report_number       TEXT    DEFAULT '',
        doc_number          TEXT    DEFAULT '',
        title               TEXT    NOT NULL,
        revision            TEXT    DEFAULT 'A',
        status              TEXT    DEFAULT 'draft',
        report_type         TEXT    DEFAULT 'Validation Report',
        equipment_name      TEXT    DEFAULT '',
        equipment_id        TEXT    DEFAULT '',
        equipment_type      TEXT    DEFAULT '',
        manufacturer        TEXT    DEFAULT '',
        model               TEXT    DEFAULT '',
        serial_number       TEXT    DEFAULT '',
        department          TEXT    DEFAULT '',
        site                TEXT    DEFAULT '',
        location            TEXT    DEFAULT '',
        validation_type     TEXT    DEFAULT 'IQ/OQ/PQ',
        scope               TEXT    DEFAULT '',
        purpose             TEXT    DEFAULT '',
        linked_qual_id      INTEGER DEFAULT NULL,
        linked_urs_id       INTEGER DEFAULT NULL,
        linked_risk_id      INTEGER DEFAULT NULL,
        linked_project_id   INTEGER DEFAULT NULL,
        prepared_by         TEXT    DEFAULT '',
        reviewed_by         TEXT    DEFAULT '',
        approved_by         TEXT    DEFAULT '',
        effective_date      TEXT    DEFAULT '',
        report_date         TEXT    DEFAULT '',
        planned_start       TEXT    DEFAULT '',
        planned_end         TEXT    DEFAULT '',
        actual_start        TEXT    DEFAULT '',
        actual_end          TEXT    DEFAULT '',
        iq_outcome          TEXT    DEFAULT '',
        oq_outcome          TEXT    DEFAULT '',
        pq_outcome          TEXT    DEFAULT '',
        overall_outcome     TEXT    DEFAULT '',
        total_tests         INTEGER DEFAULT 0,
        pass_count          INTEGER DEFAULT 0,
        fail_count          INTEGER DEFAULT 0,
        na_count            INTEGER DEFAULT 0,
        deviation_count     INTEGER DEFAULT 0,
        open_actions        INTEGER DEFAULT 0,
        compliance_score    INTEGER DEFAULT 0,
        completeness_score  INTEGER DEFAULT 0,
        ai_readiness_score  INTEGER DEFAULT 0,
        ai_review_data      TEXT    DEFAULT '{}',
        ai_generated        INTEGER DEFAULT 0,
        version             TEXT    DEFAULT 'v1.0',
        change_summary      TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS val_report_sections (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id           INTEGER NOT NULL,
        section_key         TEXT    NOT NULL,
        section_title       TEXT    NOT NULL,
        section_order       INTEGER DEFAULT 0,
        content             TEXT    DEFAULT '',
        content_type        TEXT    DEFAULT 'markdown',
        is_generated        INTEGER DEFAULT 0,
        is_edited           INTEGER DEFAULT 0,
        is_required         INTEGER DEFAULT 1,
        word_count          INTEGER DEFAULT 0,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (report_id) REFERENCES val_reports(id) ON DELETE CASCADE,
        UNIQUE(report_id, section_key)
    );

    CREATE TABLE IF NOT EXISTS val_report_approvals (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id           INTEGER NOT NULL,
        action              TEXT    NOT NULL,
        performed_by        TEXT    DEFAULT '',
        role                TEXT    DEFAULT '',
        comments            TEXT    DEFAULT '',
        version             TEXT    DEFAULT '',
        electronic_sig      TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (report_id) REFERENCES val_reports(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS val_report_versions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id           INTEGER NOT NULL,
        version             TEXT    NOT NULL,
        revision            TEXT    DEFAULT 'A',
        status              TEXT    DEFAULT 'draft',
        change_summary      TEXT    DEFAULT '',
        sections_snapshot   TEXT    DEFAULT '{}',
        compliance_score    INTEGER DEFAULT 0,
        completeness_score  INTEGER DEFAULT 0,
        created_by          TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (report_id) REFERENCES val_reports(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS val_report_ai_reviews (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id           INTEGER NOT NULL,
        compliance_score    INTEGER DEFAULT 0,
        completeness_score  INTEGER DEFAULT 0,
        readiness_score     INTEGER DEFAULT 0,
        overall_score       INTEGER DEFAULT 0,
        recommendation      TEXT    DEFAULT '',
        missing_sections    TEXT    DEFAULT '[]',
        missing_evidence    TEXT    DEFAULT '[]',
        regulatory_gaps     TEXT    DEFAULT '[]',
        data_integrity_issues TEXT  DEFAULT '[]',
        improvements        TEXT    DEFAULT '[]',
        strengths           TEXT    DEFAULT '[]',
        reviewer_comments   TEXT    DEFAULT '[]',
        executive_summary   TEXT    DEFAULT '',
        full_review_data    TEXT    DEFAULT '{}',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (report_id) REFERENCES val_reports(id) ON DELETE CASCADE
    );
"""


# ── Standard report section definitions ──────────────────────────────────────

STANDARD_SECTIONS = [
    ("cover_page",           "Cover Page",                    1,  True),
    ("approval_page",        "Approval Page",                 2,  True),
    ("revision_history",     "Revision History",              3,  True),
    ("table_of_contents",    "Table of Contents",             4,  True),
    ("executive_summary",    "Executive Summary",             5,  True),
    ("purpose",              "Purpose",                       6,  True),
    ("scope",                "Scope",                         7,  True),
    ("responsibilities",     "Responsibilities",              8,  True),
    ("applicable_standards", "Applicable Standards",          9,  True),
    ("equipment_details",    "Equipment Details",             10, True),
    ("system_description",   "System Description",            11, True),
    ("validation_strategy",  "Validation Strategy",           12, True),
    ("urs_summary",          "URS Summary",                   13, True),
    ("risk_assessment_summary", "Risk Assessment Summary",    14, True),
    ("iq_summary",           "Installation Qualification (IQ) Summary", 15, True),
    ("oq_summary",           "Operational Qualification (OQ) Summary",  16, True),
    ("pq_summary",           "Performance Qualification (PQ) Summary",  17, True),
    ("execution_summary",    "Execution Summary",             18, True),
    ("deviation_summary",    "Deviation Summary",             19, True),
    ("traceability_summary", "Traceability Summary",          20, True),
    ("critical_findings",    "Critical Findings",             21, True),
    ("risk_evaluation",      "Risk Evaluation",               22, True),
    ("compliance_assessment","Overall Compliance Assessment", 23, True),
    ("conclusion",           "Conclusion",                    24, True),
    ("recommendations",      "Recommendations",               25, True),
    ("final_statement",      "Final Validation Statement",    26, True),
    ("annexures",            "Annexures",                     27, False),
    ("supporting_evidence",  "Supporting Evidence",           28, False),
]


# ── Reports ───────────────────────────────────────────────────────────────────

def create_report(data: dict, *, company_id: str) -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO val_reports
               (report_number, doc_number, title, revision, status, report_type,
                equipment_name, equipment_id, equipment_type, manufacturer, model,
                serial_number, department, site, location, validation_type, scope, purpose,
                linked_qual_id, linked_urs_id, linked_risk_id, linked_project_id,
                prepared_by, reviewed_by, approved_by, effective_date, report_date,
                planned_start, planned_end, company_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("report_number", ""),
                data.get("doc_number", ""),
                data.get("title", "Validation Report"),
                data.get("revision", "A"),
                data.get("status", "draft"),
                data.get("report_type", "Validation Report"),
                data.get("equipment_name", ""),
                data.get("equipment_id", ""),
                data.get("equipment_type", ""),
                data.get("manufacturer", ""),
                data.get("model", ""),
                data.get("serial_number", ""),
                data.get("department", ""),
                data.get("site", ""),
                data.get("location", ""),
                data.get("validation_type", "IQ/OQ/PQ"),
                data.get("scope", ""),
                data.get("purpose", ""),
                data.get("linked_qual_id"),
                data.get("linked_urs_id"),
                data.get("linked_risk_id"),
                data.get("linked_project_id"),
                data.get("prepared_by", ""),
                data.get("reviewed_by", ""),
                data.get("approved_by", ""),
                data.get("effective_date", ""),
                data.get("report_date", ""),
                data.get("planned_start", ""),
                data.get("planned_end", ""),
                company_id,
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    _init_sections(new_id)
    add_approval_entry(new_id, "Report Created", data.get("prepared_by", "System"), "Author", "Initial draft created")
    return get_report(new_id)


def _init_sections(report_id: int) -> None:
    conn = get_connection()
    with conn:
        for key, title, order, required in STANDARD_SECTIONS:
            conn.execute(
                """INSERT OR IGNORE INTO val_report_sections
                   (report_id, section_key, section_title, section_order, is_required)
                   VALUES (?,?,?,?,?)""",
                (report_id, key, title, order, 1 if required else 0),
            )
    conn.close()


def get_report(report_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM val_reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
    except Exception:
        d["ai_review_data"] = {}
    return d


def get_all_reports(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts; every live route must always pass
    a company_id."""
    conn = get_connection()
    where_clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("status", "report_type", "department", "equipment_type", "validation_type"):
            if filters.get(field):
                where_clauses.append(f"{field} = ?")
                params.append(filters[field])
        if filters.get("keyword"):
            where_clauses.append(
                "(title LIKE ? OR equipment_name LIKE ? OR report_number LIKE ? OR department LIKE ?)"
            )
            kw = f"%{filters['keyword']}%"
            params += [kw, kw, kw, kw]
        if filters.get("linked_qual_id"):
            where_clauses.append("linked_qual_id = ?")
            params.append(filters["linked_qual_id"])
    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    rows = conn.execute(
        f"SELECT * FROM val_reports {where} ORDER BY created_at DESC", params
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
        except Exception:
            d["ai_review_data"] = {}
        result.append(d)
    return result


def update_report(report_id: int, data: dict) -> dict | None:
    allowed = [
        "report_number", "doc_number", "title", "revision", "status", "report_type",
        "equipment_name", "equipment_id", "equipment_type", "manufacturer", "model",
        "serial_number", "department", "site", "location", "validation_type", "scope", "purpose",
        "linked_qual_id", "linked_urs_id", "linked_risk_id", "linked_project_id",
        "prepared_by", "reviewed_by", "approved_by", "effective_date", "report_date",
        "planned_start", "planned_end", "actual_start", "actual_end",
        "iq_outcome", "oq_outcome", "pq_outcome", "overall_outcome",
        "total_tests", "pass_count", "fail_count", "na_count", "deviation_count", "open_actions",
        "compliance_score", "completeness_score", "ai_readiness_score",
        "ai_review_data", "ai_generated", "version", "change_summary",
    ]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return get_report(report_id)
    if "ai_review_data" in updates and isinstance(updates["ai_review_data"], dict):
        updates["ai_review_data"] = json.dumps(updates["ai_review_data"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [report_id]
    conn = get_connection()
    with conn:
        conn.execute(
            f"UPDATE val_reports SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
    conn.close()
    return get_report(report_id)


def delete_report(report_id: int) -> bool:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM val_reports WHERE id = ?", (report_id,))
    conn.close()
    return True


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    total       = conn.execute("SELECT COUNT(*) FROM val_reports WHERE company_id = ?", (company_id,)).fetchone()[0]
    draft       = conn.execute("SELECT COUNT(*) FROM val_reports WHERE status='draft' AND company_id = ?", (company_id,)).fetchone()[0]
    under_review= conn.execute("SELECT COUNT(*) FROM val_reports WHERE status='under_review' AND company_id = ?", (company_id,)).fetchone()[0]
    approved    = conn.execute("SELECT COUNT(*) FROM val_reports WHERE status='approved' AND company_id = ?", (company_id,)).fetchone()[0]
    released    = conn.execute("SELECT COUNT(*) FROM val_reports WHERE status='released' AND company_id = ?", (company_id,)).fetchone()[0]
    archived    = conn.execute("SELECT COUNT(*) FROM val_reports WHERE status='archived' AND company_id = ?", (company_id,)).fetchone()[0]
    ai_gen      = conn.execute("SELECT COUNT(*) FROM val_reports WHERE ai_generated=1 AND company_id = ?", (company_id,)).fetchone()[0]

    avg_compliance   = conn.execute("SELECT AVG(compliance_score) FROM val_reports WHERE compliance_score > 0 AND company_id = ?", (company_id,)).fetchone()[0] or 0
    avg_completeness = conn.execute("SELECT AVG(completeness_score) FROM val_reports WHERE completeness_score > 0 AND company_id = ?", (company_id,)).fetchone()[0] or 0
    avg_readiness    = conn.execute("SELECT AVG(ai_readiness_score) FROM val_reports WHERE ai_readiness_score > 0 AND company_id = ?", (company_id,)).fetchone()[0] or 0

    by_dept = conn.execute(
        "SELECT department, COUNT(*) as cnt FROM val_reports WHERE department != '' AND company_id = ? "
        "GROUP BY department ORDER BY cnt DESC LIMIT 8",
        (company_id,),
    ).fetchall()
    by_type = conn.execute(
        "SELECT validation_type, COUNT(*) as cnt FROM val_reports WHERE validation_type != '' AND company_id = ? "
        "GROUP BY validation_type ORDER BY cnt DESC",
        (company_id,),
    ).fetchall()
    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM val_reports WHERE company_id = ? GROUP BY status",
        (company_id,),
    ).fetchall()

    recent = conn.execute(
        """SELECT id, report_number, title, equipment_name, department, status,
                  compliance_score, ai_readiness_score, created_at
           FROM val_reports WHERE company_id = ? ORDER BY created_at DESC LIMIT 8""",
        (company_id,),
    ).fetchall()
    conn.close()

    return {
        "total": total,
        "draft": draft,
        "under_review": under_review,
        "approved": approved,
        "released": released,
        "archived": archived,
        "ai_generated": ai_gen,
        "avg_compliance": round(avg_compliance, 1),
        "avg_completeness": round(avg_completeness, 1),
        "avg_readiness": round(avg_readiness, 1),
        "by_department": [dict(r) for r in by_dept],
        "by_type": [dict(r) for r in by_type],
        "by_status": [dict(r) for r in by_status],
        "recent": [dict(r) for r in recent],
    }


# ── Sections ──────────────────────────────────────────────────────────────────

def get_sections(report_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM val_report_sections WHERE report_id = ? ORDER BY section_order",
        (report_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_section(report_id: int, section_key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM val_report_sections WHERE report_id = ? AND section_key = ?",
        (report_id, section_key),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_section(report_id: int, section_key: str, content: str) -> dict | None:
    word_count = len(content.split()) if content else 0
    conn = get_connection()
    with conn:
        conn.execute(
            """UPDATE val_report_sections
               SET content = ?, is_edited = 1, word_count = ?, updated_at = CURRENT_TIMESTAMP
               WHERE report_id = ? AND section_key = ?""",
            (content, word_count, report_id, section_key),
        )
    conn.close()
    _update_report_completeness(report_id)
    return get_section(report_id, section_key)


def mark_section_generated(report_id: int, section_key: str, content: str) -> None:
    word_count = len(content.split()) if content else 0
    conn = get_connection()
    with conn:
        conn.execute(
            """UPDATE val_report_sections
               SET content = ?, is_generated = 1, word_count = ?, updated_at = CURRENT_TIMESTAMP
               WHERE report_id = ? AND section_key = ?""",
            (content, word_count, report_id, section_key),
        )
    conn.close()


def _update_report_completeness(report_id: int) -> None:
    conn = get_connection()
    total_req = conn.execute(
        "SELECT COUNT(*) FROM val_report_sections WHERE report_id = ? AND is_required = 1",
        (report_id,),
    ).fetchone()[0]
    filled_req = conn.execute(
        "SELECT COUNT(*) FROM val_report_sections WHERE report_id = ? AND is_required = 1 AND LENGTH(TRIM(content)) > 50",
        (report_id,),
    ).fetchone()[0]
    conn.close()
    score = round((filled_req / total_req * 100) if total_req else 0)
    update_report(report_id, {"completeness_score": score})


# ── Approvals ─────────────────────────────────────────────────────────────────

def add_approval_entry(report_id: int, action: str, performed_by: str,
                       role: str = "", comments: str = "", version: str = "",
                       electronic_sig: str = "") -> dict:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO val_report_approvals
               (report_id, action, performed_by, role, comments, version, electronic_sig)
               VALUES (?,?,?,?,?,?,?)""",
            (report_id, action, performed_by, role, comments, version, electronic_sig),
        )
        new_id = cur.lastrowid
    conn.close()
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM val_report_approvals WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    return dict(row) if row else {}


def get_approval_trail(report_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM val_report_approvals WHERE report_id = ? ORDER BY created_at ASC",
        (report_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Version History ───────────────────────────────────────────────────────────

def create_version_snapshot(report_id: int, change_summary: str, created_by: str) -> dict:
    report = get_report(report_id)
    if not report:
        return {}
    sections = get_sections(report_id)
    sections_snapshot = {s["section_key"]: s["content"] for s in sections}
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM val_report_versions WHERE report_id = ?", (report_id,)
    ).fetchone()[0]
    conn.close()
    version_num = f"v{count + 1}.0"
    conn2 = get_connection()
    with conn2:
        cur = conn2.execute(
            """INSERT INTO val_report_versions
               (report_id, version, revision, status, change_summary,
                sections_snapshot, compliance_score, completeness_score, created_by)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                report_id, version_num,
                report.get("revision", "A"),
                report.get("status", "draft"),
                change_summary,
                json.dumps(sections_snapshot),
                report.get("compliance_score", 0),
                report.get("completeness_score", 0),
                created_by,
            ),
        )
        new_id = cur.lastrowid
    conn2.close()
    conn3 = get_connection()
    row = conn3.execute("SELECT * FROM val_report_versions WHERE id = ?", (new_id,)).fetchone()
    conn3.close()
    return dict(row) if row else {}


def get_versions(report_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, report_id, version, revision, status, change_summary,
                  compliance_score, completeness_score, created_by, created_at
           FROM val_report_versions WHERE report_id = ? ORDER BY created_at DESC""",
        (report_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── AI Reviews ────────────────────────────────────────────────────────────────

def save_ai_review(report_id: int, review_data: dict) -> dict:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO val_report_ai_reviews
               (report_id, compliance_score, completeness_score, readiness_score,
                overall_score, recommendation, missing_sections, missing_evidence,
                regulatory_gaps, data_integrity_issues, improvements, strengths,
                reviewer_comments, executive_summary, full_review_data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                report_id,
                review_data.get("compliance_score", 0),
                review_data.get("completeness_score", 0),
                review_data.get("readiness_score", 0),
                review_data.get("overall_score", 0),
                review_data.get("recommendation", ""),
                json.dumps(review_data.get("missing_sections", [])),
                json.dumps(review_data.get("missing_evidence", [])),
                json.dumps(review_data.get("regulatory_gaps", [])),
                json.dumps(review_data.get("data_integrity_issues", [])),
                json.dumps(review_data.get("improvements", [])),
                json.dumps(review_data.get("strengths", [])),
                json.dumps(review_data.get("reviewer_comments", [])),
                review_data.get("executive_summary", ""),
                json.dumps(review_data),
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    update_report(report_id, {
        "compliance_score": review_data.get("compliance_score", 0),
        "completeness_score": review_data.get("completeness_score", 0),
        "ai_readiness_score": review_data.get("readiness_score", 0),
        "ai_review_data": review_data,
    })
    conn2 = get_connection()
    row = conn2.execute("SELECT * FROM val_report_ai_reviews WHERE id = ?", (new_id,)).fetchone()
    conn2.close()
    if not row:
        return {}
    d = dict(row)
    for f in ("missing_sections", "missing_evidence", "regulatory_gaps",
              "data_integrity_issues", "improvements", "strengths", "reviewer_comments"):
        try:
            d[f] = json.loads(d.get(f) or "[]")
        except Exception:
            d[f] = []
    try:
        d["full_review_data"] = json.loads(d.get("full_review_data") or "{}")
    except Exception:
        d["full_review_data"] = {}
    return d


def get_latest_ai_review(report_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM val_report_ai_reviews WHERE report_id = ? ORDER BY created_at DESC LIMIT 1",
        (report_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for f in ("missing_sections", "missing_evidence", "regulatory_gaps",
              "data_integrity_issues", "improvements", "strengths", "reviewer_comments"):
        try:
            d[f] = json.loads(d.get(f) or "[]")
        except Exception:
            d[f] = []
    try:
        d["full_review_data"] = json.loads(d.get("full_review_data") or "{}")
    except Exception:
        d["full_review_data"] = {}
    return d

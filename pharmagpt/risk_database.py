"""
risk_database.py — SQLite CRUD functions for the Risk Management Suite.

Tables managed here:
  risk_assessments  : Master assessment records
  risk_items        : Individual risk rows per assessment (FMEA / HACCP / Matrix)
  risk_library      : Reusable risk catalogue enriched from approved assessments
  risk_actions      : Mitigation action tracking
  risk_approval     : Review & approval audit trail
"""

import json
import sqlite3
from pharmagpt.database import get_connection


# ── Assessments ───────────────────────────────────────────────────────────────

def create_assessment(data: dict, *, company_id: str) -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO risk_assessments
               (title, assessment_type, assessment_subtype, methodology,
                department, area, equipment, product, process,
                protocol_reference, change_control_reference,
                assessment_owner, reviewer, approver, assessment_date,
                revision, status, priority, reason_for_assessment, form_data, company_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("title", "Untitled Assessment"),
                data.get("assessment_type", ""),
                data.get("assessment_subtype", ""),
                data.get("methodology", "FMEA"),
                data.get("department", ""),
                data.get("area", ""),
                data.get("equipment", ""),
                data.get("product", ""),
                data.get("process", ""),
                data.get("protocol_reference", ""),
                data.get("change_control_reference", ""),
                data.get("assessment_owner", ""),
                data.get("reviewer", ""),
                data.get("approver", ""),
                data.get("assessment_date", ""),
                data.get("revision", "Rev 00"),
                data.get("status", "Draft"),
                data.get("priority", "Medium"),
                data.get("reason_for_assessment", ""),
                json.dumps(data.get("form_data", {})),
                company_id,
            ),
        )
        new_id = cur.lastrowid
    # Fetch after commit so the new connection sees the row
    return get_assessment(new_id)


def get_assessment(assessment_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM risk_assessments WHERE id = ?", (assessment_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["form_data"] = json.loads(d.get("form_data") or "{}")
    d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
    return d


def get_all_assessments(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts (service-role key, not a live
    request); every live route must always pass a company_id."""
    conn = get_connection()
    where_clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("assessment_type", "methodology", "status", "priority", "department"):
            val = filters.get(field)
            if val:
                where_clauses.append(f"{field} = ?")
                params.append(val)
        keyword = filters.get("keyword")
        if keyword:
            where_clauses.append("(title LIKE ? OR equipment LIKE ? OR process LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    sql = "SELECT * FROM risk_assessments"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["form_data"] = json.loads(d.get("form_data") or "{}")
        d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
        result.append(d)
    return result


def update_assessment(assessment_id: int, data: dict) -> dict | None:
    conn = get_connection()
    fields = [
        "title", "assessment_type", "assessment_subtype", "methodology",
        "department", "area", "equipment", "product", "process",
        "protocol_reference", "change_control_reference",
        "assessment_owner", "reviewer", "approver", "assessment_date",
        "revision", "status", "priority", "reason_for_assessment",
    ]
    updates = []
    params = []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if "form_data" in data:
        updates.append("form_data = ?")
        params.append(json.dumps(data["form_data"]))
    if "ai_review_data" in data:
        updates.append("ai_review_data = ?")
        params.append(json.dumps(data["ai_review_data"]))
    updates.append("updated_at = datetime('now')")
    params.append(assessment_id)
    with conn:
        conn.execute(
            f"UPDATE risk_assessments SET {', '.join(updates)} WHERE id = ?",
            params,
        )
    return get_assessment(assessment_id)


def delete_assessment(assessment_id: int) -> bool:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM risk_assessments WHERE id = ?", (assessment_id,))
    return True


def set_assessment_postgres_id(assessment_id: int, postgres_id: str) -> None:
    """Record the Postgres `risk_assessments.id` (uuid) this SQLite
    assessment row was dual-written to (Phase 3.5, docs/PHASE3_EXECUTION_PLAN.md)."""
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE risk_assessments SET postgres_id = ? WHERE id = ?", (postgres_id, assessment_id)
        )


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, priority, COUNT(*) as cnt FROM risk_assessments WHERE company_id = ? GROUP BY status, priority",
        (company_id,),
    ).fetchall()

    stats = {
        "total": 0, "draft": 0, "in_review": 0, "approved": 0, "closed": 0,
        "critical": 0, "high": 0, "medium": 0, "low": 0,
        "by_type": {}, "by_department": {},
    }

    all_rows = conn.execute("SELECT * FROM risk_assessments WHERE company_id = ?", (company_id,)).fetchall()
    stats["total"] = len(all_rows)

    for row in all_rows:
        d = dict(row)
        s = d.get("status", "Draft").lower().replace(" ", "_")
        if s in stats:
            stats[s] += 1
        p = d.get("priority", "Medium").lower()
        if p in stats:
            stats[p] += 1
        atype = d.get("assessment_type", "other")
        stats["by_type"][atype] = stats["by_type"].get(atype, 0) + 1
        dept = d.get("department", "Unknown")
        stats["by_department"][dept] = stats["by_department"].get(dept, 0) + 1

    # High RPN items
    high_rpn = conn.execute(
        """SELECT COUNT(*) as cnt FROM risk_items i
           JOIN risk_assessments a ON a.id = i.assessment_id
           WHERE i.rpn >= 100 AND i.status != 'Closed' AND a.company_id = ?""",
        (company_id,),
    ).fetchone()
    stats["high_rpn"] = high_rpn["cnt"] if high_rpn else 0

    # Pending actions
    pending = conn.execute(
        """SELECT COUNT(*) as cnt FROM risk_actions r
           JOIN risk_assessments a ON a.id = r.assessment_id
           WHERE r.status IN ('Pending','In Progress') AND a.company_id = ?""",
        (company_id,),
    ).fetchone()
    stats["pending_actions"] = pending["cnt"] if pending else 0

    # Recent assessments
    recent = conn.execute(
        "SELECT id, title, assessment_type, status, priority, created_at FROM risk_assessments "
        "WHERE company_id = ? ORDER BY created_at DESC LIMIT 5",
        (company_id,),
    ).fetchall()
    stats["recent"] = [dict(r) for r in recent]

    return stats


# ── Risk Items ────────────────────────────────────────────────────────────────

def get_items(assessment_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_items WHERE assessment_id = ? ORDER BY item_order, id",
        (assessment_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_items(assessment_id: int, items: list[dict]) -> list[dict]:
    """Replace all items for an assessment (bulk upsert pattern)."""
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM risk_items WHERE assessment_id = ?", (assessment_id,))
        for i, item in enumerate(items):
            rpn = None
            s = item.get("severity")
            o = item.get("occurrence")
            d = item.get("detection")
            if s and o and d:
                try:
                    rpn = int(s) * int(o) * int(d)
                except (ValueError, TypeError):
                    rpn = None

            res_rpn = None
            rs = item.get("residual_severity")
            ro = item.get("residual_occurrence")
            rd = item.get("residual_detection")
            if rs and ro and rd:
                try:
                    res_rpn = int(rs) * int(ro) * int(rd)
                except (ValueError, TypeError):
                    res_rpn = None

            conn.execute(
                """INSERT INTO risk_items
                   (assessment_id, item_order, process_step, failure_mode, failure_effect,
                    severity, potential_cause, occurrence, current_controls,
                    detection, detection_rating, rpn, hazard, hazard_category,
                    preventive_measure, is_ccp, critical_limit, monitoring,
                    corrective_action, verification, records,
                    probability, impact, risk_rating, risk_acceptance,
                    recommended_action, action_owner, due_date, residual_risk,
                    residual_severity, residual_occurrence, residual_detection,
                    residual_rpn, status, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    assessment_id, i,
                    item.get("process_step", ""),
                    item.get("failure_mode", ""),
                    item.get("failure_effect", ""),
                    item.get("severity"),
                    item.get("potential_cause", ""),
                    item.get("occurrence"),
                    item.get("current_controls", ""),
                    item.get("detection"),
                    item.get("detection_rating"),
                    rpn,
                    item.get("hazard", ""),
                    item.get("hazard_category", ""),
                    item.get("preventive_measure", ""),
                    1 if item.get("is_ccp") else 0,
                    item.get("critical_limit", ""),
                    item.get("monitoring", ""),
                    item.get("corrective_action", ""),
                    item.get("verification", ""),
                    item.get("records", ""),
                    item.get("probability", ""),
                    item.get("impact", ""),
                    item.get("risk_rating", ""),
                    item.get("risk_acceptance", ""),
                    item.get("recommended_action", ""),
                    item.get("action_owner", ""),
                    item.get("due_date", ""),
                    item.get("residual_risk", ""),
                    item.get("residual_severity"),
                    item.get("residual_occurrence"),
                    item.get("residual_detection"),
                    res_rpn,
                    item.get("status", "Open"),
                    item.get("notes", ""),
                ),
            )
    return get_items(assessment_id)


# ── Risk Library ──────────────────────────────────────────────────────────────

def get_library(company_id: str, category: str = None, keyword: str = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py) — risk_library entries are
    populated from a company's own approved assessments (see
    publish_assessment_to_library) and can contain that company's specific
    equipment/process names, so this catalog must not be shared across
    companies despite being a "library"."""
    conn = get_connection()
    sql = "SELECT * FROM risk_library"
    params = [company_id]
    clauses = ["company_id = ?"]
    if category:
        clauses.append("category = ?")
        params.append(category)
    if keyword:
        clauses.append("(failure_mode LIKE ? OR hazard LIKE ? OR process_step LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY usage_count DESC, id DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def add_library_entry(data: dict, *, company_id: str) -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO risk_library
               (category, subcategory, assessment_type, methodology, process_step,
                failure_mode, failure_effect, potential_cause, current_controls,
                recommended_action, typical_severity, typical_occurrence,
                typical_detection, typical_rpn, regulatory_reference, source_assessment_id,
                company_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("category", "General"),
                data.get("subcategory", ""),
                data.get("assessment_type", ""),
                data.get("methodology", "FMEA"),
                data.get("process_step", ""),
                data.get("failure_mode", ""),
                data.get("failure_effect", ""),
                data.get("potential_cause", ""),
                data.get("current_controls", ""),
                data.get("recommended_action", ""),
                data.get("typical_severity"),
                data.get("typical_occurrence"),
                data.get("typical_detection"),
                data.get("typical_rpn"),
                data.get("regulatory_reference", ""),
                data.get("source_assessment_id"),
                company_id,
            ),
        )
        new_id = cur.lastrowid
    row = get_connection().execute("SELECT * FROM risk_library WHERE id = ?", (new_id,)).fetchone()
    return dict(row)


def publish_assessment_to_library(assessment_id: int) -> int:
    """Push approved assessment items into the risk library. Returns count added."""
    items = get_items(assessment_id)
    assessment = get_assessment(assessment_id)
    if not assessment:
        return 0
    count = 0
    for item in items:
        if item.get("failure_mode") or item.get("hazard"):
            add_library_entry({
                "category": _type_to_category(assessment.get("assessment_type", "")),
                "subcategory": assessment.get("assessment_subtype", ""),
                "assessment_type": assessment.get("assessment_type", ""),
                "methodology": assessment.get("methodology", "FMEA"),
                "process_step": item.get("process_step", ""),
                "failure_mode": item.get("failure_mode") or item.get("hazard", ""),
                "failure_effect": item.get("failure_effect", ""),
                "potential_cause": item.get("potential_cause", ""),
                "current_controls": item.get("current_controls") or item.get("preventive_measure", ""),
                "recommended_action": item.get("recommended_action", ""),
                "typical_severity": item.get("severity"),
                "typical_occurrence": item.get("occurrence"),
                "typical_detection": item.get("detection"),
                "typical_rpn": item.get("rpn"),
                "source_assessment_id": assessment_id,
            }, company_id=assessment["company_id"])
            count += 1
    return count


def _type_to_category(atype: str) -> str:
    mapping = {
        "validation": "Validation", "manufacturing": "Manufacturing",
        "engineering": "Engineering", "quality": "Quality",
        "warehouse": "Warehouse", "misc": "General",
    }
    return mapping.get(atype.lower(), "General")


# ── Risk Actions ──────────────────────────────────────────────────────────────

def get_actions(assessment_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_actions WHERE assessment_id = ? ORDER BY created_at",
        (assessment_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_action(assessment_id: int, data: dict) -> dict:
    conn = get_connection()
    with conn:
        if data.get("id"):
            conn.execute(
                """UPDATE risk_actions SET action_description=?, action_owner=?,
                   due_date=?, completion_date=?, status=?, effectiveness_check=?, notes=?
                   WHERE id=? AND assessment_id=?""",
                (
                    data.get("action_description", ""),
                    data.get("action_owner", ""),
                    data.get("due_date", ""),
                    data.get("completion_date", ""),
                    data.get("status", "Pending"),
                    data.get("effectiveness_check", ""),
                    data.get("notes", ""),
                    data["id"], assessment_id,
                ),
            )
            row = conn.execute("SELECT * FROM risk_actions WHERE id = ?", (data["id"],)).fetchone()
        else:
            cur = conn.execute(
                """INSERT INTO risk_actions
                   (assessment_id, item_id, action_description, action_owner,
                    due_date, status, effectiveness_check, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    assessment_id,
                    data.get("item_id"),
                    data.get("action_description", ""),
                    data.get("action_owner", ""),
                    data.get("due_date", ""),
                    data.get("status", "Pending"),
                    data.get("effectiveness_check", ""),
                    data.get("notes", ""),
                ),
            )
            row = conn.execute("SELECT * FROM risk_actions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


# ── Risk Approval ─────────────────────────────────────────────────────────────

def get_approval_trail(assessment_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_approval WHERE assessment_id = ? ORDER BY timestamp",
        (assessment_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_approval_entry(assessment_id: int, action: str, performed_by: str = "",
                       role: str = "", comments: str = "") -> dict:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO risk_approval (assessment_id, action, performed_by, role, comments)
               VALUES (?,?,?,?,?)""",
            (assessment_id, action, performed_by, role, comments),
        )
        new_id = cur.lastrowid
    row = get_connection().execute("SELECT * FROM risk_approval WHERE id = ?", (new_id,)).fetchone()
    return dict(row)


# ── Init (called by database.py's init_db) ────────────────────────────────────

RISK_SCHEMA = """
    CREATE TABLE IF NOT EXISTS risk_assessments (
        id                        INTEGER PRIMARY KEY AUTOINCREMENT,
        title                     TEXT    NOT NULL DEFAULT 'Untitled Assessment',
        assessment_type           TEXT    NOT NULL DEFAULT '',
        assessment_subtype        TEXT    NOT NULL DEFAULT '',
        methodology               TEXT    NOT NULL DEFAULT 'FMEA',
        department                TEXT    DEFAULT '',
        area                      TEXT    DEFAULT '',
        equipment                 TEXT    DEFAULT '',
        product                   TEXT    DEFAULT '',
        process                   TEXT    DEFAULT '',
        protocol_reference        TEXT    DEFAULT '',
        change_control_reference  TEXT    DEFAULT '',
        assessment_owner          TEXT    DEFAULT '',
        reviewer                  TEXT    DEFAULT '',
        approver                  TEXT    DEFAULT '',
        assessment_date           TEXT    DEFAULT '',
        revision                  TEXT    DEFAULT 'Rev 00',
        status                    TEXT    DEFAULT 'Draft',
        priority                  TEXT    DEFAULT 'Medium',
        reason_for_assessment     TEXT    DEFAULT '',
        ai_review_data            TEXT    DEFAULT '{}',
        form_data                 TEXT    DEFAULT '{}',
        created_at                TEXT    DEFAULT (datetime('now')),
        updated_at                TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS risk_items (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id       INTEGER NOT NULL,
        item_order          INTEGER DEFAULT 0,
        process_step        TEXT    DEFAULT '',
        failure_mode        TEXT    DEFAULT '',
        failure_effect      TEXT    DEFAULT '',
        severity            INTEGER,
        potential_cause     TEXT    DEFAULT '',
        occurrence          INTEGER,
        current_controls    TEXT    DEFAULT '',
        detection           INTEGER,
        detection_rating    INTEGER,
        rpn                 INTEGER,
        hazard              TEXT    DEFAULT '',
        hazard_category     TEXT    DEFAULT '',
        preventive_measure  TEXT    DEFAULT '',
        is_ccp              INTEGER DEFAULT 0,
        critical_limit      TEXT    DEFAULT '',
        monitoring          TEXT    DEFAULT '',
        corrective_action   TEXT    DEFAULT '',
        verification        TEXT    DEFAULT '',
        records             TEXT    DEFAULT '',
        probability         TEXT    DEFAULT '',
        impact              TEXT    DEFAULT '',
        risk_rating         TEXT    DEFAULT '',
        risk_acceptance     TEXT    DEFAULT '',
        recommended_action  TEXT    DEFAULT '',
        action_owner        TEXT    DEFAULT '',
        due_date            TEXT    DEFAULT '',
        residual_risk       TEXT    DEFAULT '',
        residual_severity   INTEGER,
        residual_occurrence INTEGER,
        residual_detection  INTEGER,
        residual_rpn        INTEGER,
        status              TEXT    DEFAULT 'Open',
        notes               TEXT    DEFAULT '',
        created_at          TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS risk_library (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        category              TEXT    NOT NULL DEFAULT 'General',
        subcategory           TEXT    DEFAULT '',
        assessment_type       TEXT    DEFAULT '',
        methodology           TEXT    DEFAULT 'FMEA',
        process_step          TEXT    DEFAULT '',
        failure_mode          TEXT    DEFAULT '',
        failure_effect        TEXT    DEFAULT '',
        potential_cause       TEXT    DEFAULT '',
        current_controls      TEXT    DEFAULT '',
        recommended_action    TEXT    DEFAULT '',
        typical_severity      INTEGER,
        typical_occurrence    INTEGER,
        typical_detection     INTEGER,
        typical_rpn           INTEGER,
        regulatory_reference  TEXT    DEFAULT '',
        source_assessment_id  INTEGER,
        usage_count           INTEGER DEFAULT 0,
        created_at            TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (source_assessment_id) REFERENCES risk_assessments(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS risk_actions (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id        INTEGER NOT NULL,
        item_id              INTEGER,
        action_description   TEXT    NOT NULL DEFAULT '',
        action_owner         TEXT    DEFAULT '',
        due_date             TEXT    DEFAULT '',
        completion_date      TEXT    DEFAULT '',
        status               TEXT    DEFAULT 'Pending',
        effectiveness_check  TEXT    DEFAULT '',
        notes                TEXT    DEFAULT '',
        created_at           TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id) ON DELETE CASCADE,
        FOREIGN KEY (item_id) REFERENCES risk_items(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS risk_approval (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id  INTEGER NOT NULL,
        action         TEXT    NOT NULL,
        performed_by   TEXT    DEFAULT '',
        role           TEXT    DEFAULT '',
        comments       TEXT    DEFAULT '',
        timestamp      TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id) ON DELETE CASCADE
    );
"""

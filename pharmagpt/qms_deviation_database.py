"""
qms_deviation_database.py — SQLite CRUD for the Deviation Management module.

Tables managed here (schema lives in qms_database.QMS_SCHEMA):
  qms_deviations               : Master deviation record.
  qms_deviation_investigation  : Root cause investigation (fishbone, 5-Why, timeline).
  qms_deviation_impact         : Impact assessment entries.
  qms_deviation_capa_link      : Links a deviation to the CAPA(s) raised from it.

Shared cross-module tables (attachments, comments, audit trail, approvals)
live in qms_database.py and are accessed with record_type='deviation'.
"""

import json
from pharmagpt.database import get_connection
from pharmagpt.qms_database import generate_deviation_number


# ── Deviations ─────────────────────────────────────────────────────────────────

def create_deviation(data: dict, *, company_id: str) -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    deviation_number = data.get("deviation_number") or generate_deviation_number()
    cur = conn.execute(
        """INSERT INTO qms_deviations
           (deviation_number, title, deviation_type, deviation_category, department, area,
            product, batch_lot, equipment, project_id, date_of_occurrence, date_reported,
            initiated_by, description, immediate_action, status, risk_level, form_data, company_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            deviation_number,
            data.get("title", "Untitled Deviation").strip() or "Untitled Deviation",
            data.get("deviation_type", "Minor"),
            data.get("deviation_category", "Manufacturing"),
            data.get("department", ""),
            data.get("area", ""),
            data.get("product", ""),
            data.get("batch_lot", ""),
            data.get("equipment", ""),
            data.get("project_id") or None,
            data.get("date_of_occurrence", ""),
            data.get("date_reported", ""),
            data.get("initiated_by", ""),
            data.get("description", ""),
            data.get("immediate_action", ""),
            data.get("status", "Initiated"),
            data.get("risk_level", ""),
            json.dumps(data.get("form_data", {})),
            company_id,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_deviation(new_id)


def get_deviation(deviation_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_deviations WHERE id = ?", (deviation_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["form_data"] = json.loads(d.get("form_data") or "{}")
    d["ai_investigation_data"] = json.loads(d.get("ai_investigation_data") or "{}")
    return d


def get_all_deviations(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts (service-role key, not a live
    request); every live route must always pass a company_id."""
    conn = get_connection()
    clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("deviation_type", "deviation_category", "status", "department"):
            val = filters.get(field)
            if val:
                clauses.append(f"{field} = ?")
                params.append(val)
        keyword = filters.get("keyword")
        if keyword:
            clauses.append("(title LIKE ? OR deviation_number LIKE ? OR description LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    sql = "SELECT * FROM qms_deviations"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["form_data"] = json.loads(d.get("form_data") or "{}")
        d["ai_investigation_data"] = json.loads(d.get("ai_investigation_data") or "{}")
        result.append(d)
    return result


def update_deviation(deviation_id: int, data: dict) -> dict | None:
    conn = get_connection()
    fields = [
        "title", "deviation_type", "deviation_category", "department", "area", "product",
        "batch_lot", "equipment", "project_id", "date_of_occurrence", "date_reported",
        "initiated_by", "description", "immediate_action", "status", "risk_level",
        "qa_reviewer", "approver", "closure_date",
    ]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if "form_data" in data:
        updates.append("form_data = ?")
        params.append(json.dumps(data["form_data"]))
    if "ai_investigation_data" in data:
        updates.append("ai_investigation_data = ?")
        params.append(json.dumps(data["ai_investigation_data"]))
    if not updates:
        conn.close()
        return get_deviation(deviation_id)
    updates.append("updated_at = datetime('now')")
    params.append(deviation_id)
    conn.execute(f"UPDATE qms_deviations SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_deviation(deviation_id)


def delete_deviation(deviation_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM qms_deviations WHERE id = ?", (deviation_id,))
    conn.commit()
    conn.close()


def set_deviation_postgres_id(deviation_id: int, postgres_id: str) -> None:
    """Record the Postgres `deviations.id` (uuid) this SQLite deviation row
    was dual-written to (Phase 3.5, docs/PHASE3_EXECUTION_PLAN.md)."""
    conn = get_connection()
    conn.execute("UPDATE qms_deviations SET postgres_id = ? WHERE id = ?", (postgres_id, deviation_id))
    conn.commit()
    conn.close()


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, deviation_type, deviation_category, created_at FROM qms_deviations WHERE company_id = ?",
        (company_id,),
    ).fetchall()
    stats = {"total": len(rows), "open": 0, "closed": 0, "by_type": {}, "by_category": {}, "by_status": {}}
    for r in rows:
        d = dict(r)
        status = d.get("status", "Initiated")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        if status in ("Closed", "Rejected"):
            stats["closed"] += 1
        else:
            stats["open"] += 1
        stats["by_type"][d.get("deviation_type", "Minor")] = stats["by_type"].get(d.get("deviation_type", "Minor"), 0) + 1
        stats["by_category"][d.get("deviation_category", "Manufacturing")] = \
            stats["by_category"].get(d.get("deviation_category", "Manufacturing"), 0) + 1

    # Monthly trend for the last 6 months
    trend = conn.execute(
        """SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS cnt
           FROM qms_deviations
           WHERE created_at >= date('now', '-6 months') AND company_id = ?
           GROUP BY month ORDER BY month ASC""",
        (company_id,),
    ).fetchall()
    stats["monthly_trend"] = [dict(r) for r in trend]

    recent = conn.execute(
        "SELECT id, deviation_number, title, deviation_type, status, created_at FROM qms_deviations "
        "WHERE company_id = ? ORDER BY created_at DESC LIMIT 5",
        (company_id,),
    ).fetchall()
    stats["recent"] = [dict(r) for r in recent]
    conn.close()
    return stats


# ── Investigation (fishbone / 5-Why / timeline) ────────────────────────────────

def upsert_investigation(deviation_id: int, data: dict) -> dict:
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM qms_deviation_investigation WHERE deviation_id = ?", (deviation_id,)
    ).fetchone()
    fishbone = json.dumps(data.get("fishbone_data", {})) if "fishbone_data" in data else None
    five_why = json.dumps(data.get("five_why_data", [])) if "five_why_data" in data else None
    timeline = json.dumps(data.get("timeline_data", [])) if "timeline_data" in data else None

    if existing:
        updates, params = [], []
        for field, value in (
            ("root_cause_category", data.get("root_cause_category")),
            ("root_cause_statement", data.get("root_cause_statement")),
            ("investigator", data.get("investigator")),
            ("investigation_date", data.get("investigation_date")),
        ):
            if value is not None:
                updates.append(f"{field} = ?")
                params.append(value)
        if fishbone is not None:
            updates.append("fishbone_data = ?")
            params.append(fishbone)
        if five_why is not None:
            updates.append("five_why_data = ?")
            params.append(five_why)
        if timeline is not None:
            updates.append("timeline_data = ?")
            params.append(timeline)
        updates.append("updated_at = datetime('now')")
        params.append(deviation_id)
        if updates:
            conn.execute(
                f"UPDATE qms_deviation_investigation SET {', '.join(updates)} WHERE deviation_id = ?", params
            )
            conn.commit()
    else:
        conn.execute(
            """INSERT INTO qms_deviation_investigation
               (deviation_id, root_cause_category, root_cause_statement, fishbone_data,
                five_why_data, timeline_data, investigator, investigation_date)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                deviation_id,
                data.get("root_cause_category", ""),
                data.get("root_cause_statement", ""),
                fishbone or "{}",
                five_why or "[]",
                timeline or "[]",
                data.get("investigator", ""),
                data.get("investigation_date", ""),
            ),
        )
        conn.commit()

    conn.close()
    return get_investigation(deviation_id)


def get_investigation(deviation_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM qms_deviation_investigation WHERE deviation_id = ?", (deviation_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["fishbone_data"] = json.loads(d.get("fishbone_data") or "{}")
    d["five_why_data"] = json.loads(d.get("five_why_data") or "[]")
    d["timeline_data"] = json.loads(d.get("timeline_data") or "[]")
    return d


# ── Impact assessment ────────────────────────────────────────────────────────────

def add_impact(deviation_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_deviation_impact (deviation_id, impact_area, assessment_text, risk_level, batches_affected)
           VALUES (?,?,?,?,?)""",
        (
            deviation_id, data.get("impact_area", ""), data.get("assessment_text", ""),
            data.get("risk_level", ""), data.get("batches_affected", ""),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_deviation_impact WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_impacts(deviation_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_deviation_impact WHERE deviation_id = ? ORDER BY created_at ASC",
        (deviation_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Deviation <-> CAPA linkage ────────────────────────────────────────────────────

def link_capa(deviation_id: int, capa_id: int) -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO qms_deviation_capa_link (deviation_id, capa_id) VALUES (?,?)",
        (deviation_id, capa_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_deviation_capa_link WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_linked_capas(deviation_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.* FROM qms_capas c
           JOIN qms_deviation_capa_link l ON l.capa_id = c.id
           WHERE l.deviation_id = ? ORDER BY l.created_at DESC""",
        (deviation_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["form_data"] = json.loads(d.get("form_data") or "{}")
        result.append(d)
    return result


def get_linked_deviations(capa_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT d.* FROM qms_deviations d
           JOIN qms_deviation_capa_link l ON l.deviation_id = d.id
           WHERE l.capa_id = ? ORDER BY l.created_at DESC""",
        (capa_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["form_data"] = json.loads(d.get("form_data") or "{}")
        result.append(d)
    return result

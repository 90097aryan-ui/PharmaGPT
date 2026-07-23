"""
qms_capa_database.py — SQLite CRUD for the CAPA (Corrective and Preventive
Action) module.

Tables managed here (schema lives in qms_database.QMS_SCHEMA):
  qms_capas               : Master CAPA record.
  qms_capa_actions        : Individual corrective/preventive action tasks
                             (owner, due date, status, escalation).
  qms_capa_effectiveness  : Effectiveness check records.

Shared cross-module tables (attachments, comments, audit trail, approvals)
live in qms_database.py and are accessed with record_type='capa'.
"""

import json
from pharmagpt.database import get_connection
from pharmagpt.qms_database import generate_capa_number


# ── CAPAs ──────────────────────────────────────────────────────────────────────

def create_capa(data: dict, *, company_id: str) -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    capa_number = data.get("capa_number") or generate_capa_number()
    cur = conn.execute(
        """INSERT INTO qms_capas
           (capa_number, title, capa_source, source_reference, department, project_id,
            problem_statement, root_cause, initiated_by, date_initiated, target_closure_date,
            status, qa_reviewer, approver, form_data, company_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            capa_number,
            data.get("title", "Untitled CAPA").strip() or "Untitled CAPA",
            data.get("capa_source", "Deviation"),
            data.get("source_reference", ""),
            data.get("department", ""),
            data.get("project_id") or None,
            data.get("problem_statement", ""),
            data.get("root_cause", ""),
            data.get("initiated_by", ""),
            data.get("date_initiated", ""),
            data.get("target_closure_date", ""),
            data.get("status", "Open"),
            data.get("qa_reviewer", ""),
            data.get("approver", ""),
            json.dumps(data.get("form_data", {})),
            company_id,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_capa(new_id)


def get_capa(capa_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_capas WHERE id = ?", (capa_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["form_data"] = json.loads(d.get("form_data") or "{}")
    return d


def get_all_capas(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts (service-role key, not a live
    request); every live route must always pass a company_id."""
    conn = get_connection()
    clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("capa_source", "status", "department"):
            val = filters.get(field)
            if val:
                clauses.append(f"{field} = ?")
                params.append(val)
        keyword = filters.get("keyword")
        if keyword:
            clauses.append("(title LIKE ? OR capa_number LIKE ? OR problem_statement LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    sql = "SELECT * FROM qms_capas"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["form_data"] = json.loads(d.get("form_data") or "{}")
        result.append(d)
    return result


def update_capa(capa_id: int, data: dict) -> dict | None:
    conn = get_connection()
    fields = [
        "title", "capa_source", "source_reference", "department", "project_id",
        "problem_statement", "root_cause", "initiated_by", "date_initiated",
        "target_closure_date", "status", "qa_reviewer", "approver", "closure_date",
    ]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if "form_data" in data:
        updates.append("form_data = ?")
        params.append(json.dumps(data["form_data"]))
    if not updates:
        conn.close()
        return get_capa(capa_id)
    updates.append("updated_at = datetime('now')")
    params.append(capa_id)
    conn.execute(f"UPDATE qms_capas SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_capa(capa_id)


def delete_capa(capa_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM qms_capas WHERE id = ?", (capa_id,))
    conn.commit()
    conn.close()


def set_capa_postgres_id(capa_id: int, postgres_id: str) -> None:
    """Record the Postgres `capas.id` (uuid) this SQLite CAPA row was
    dual-written to (Phase 3.5, docs/PHASE3_EXECUTION_PLAN.md)."""
    conn = get_connection()
    conn.execute("UPDATE qms_capas SET postgres_id = ? WHERE id = ?", (postgres_id, capa_id))
    conn.commit()
    conn.close()


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, status, date_initiated, target_closure_date FROM qms_capas WHERE company_id = ?",
        (company_id,),
    ).fetchall()
    stats = {"total": len(rows), "open": 0, "closed": 0, "overdue": 0, "by_status": {}}
    for r in rows:
        d = dict(r)
        status = d.get("status", "Open")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        if status == "Closed":
            stats["closed"] += 1
        else:
            stats["open"] += 1

    # CAPA aging — open CAPAs past their target closure date
    overdue = conn.execute(
        """SELECT id, capa_number, title, status, target_closure_date
           FROM qms_capas
           WHERE status != 'Closed' AND status != 'Rejected'
             AND target_closure_date IS NOT NULL AND target_closure_date != ''
             AND target_closure_date < date('now')
             AND company_id = ?
           ORDER BY target_closure_date ASC""",
        (company_id,),
    ).fetchall()
    stats["overdue"] = len(overdue)
    stats["overdue_capas"] = [dict(r) for r in overdue[:10]]

    pending_actions = conn.execute(
        """SELECT COUNT(*) AS cnt FROM qms_capa_actions a
           JOIN qms_capas c ON c.id = a.capa_id
           WHERE a.status IN ('Pending','In Progress') AND c.company_id = ?""",
        (company_id,),
    ).fetchone()
    stats["pending_actions"] = pending_actions["cnt"] if pending_actions else 0

    escalated_actions = conn.execute(
        """SELECT COUNT(*) AS cnt FROM qms_capa_actions a
           JOIN qms_capas c ON c.id = a.capa_id
           WHERE a.escalated = 1 AND c.company_id = ?""",
        (company_id,),
    ).fetchone()
    stats["escalated_actions"] = escalated_actions["cnt"] if escalated_actions else 0

    recent = conn.execute(
        "SELECT id, capa_number, title, capa_source, status, created_at FROM qms_capas "
        "WHERE company_id = ? ORDER BY created_at DESC LIMIT 5",
        (company_id,),
    ).fetchall()
    stats["recent"] = [dict(r) for r in recent]
    conn.close()
    return stats


# ── Actions (corrective / preventive tasks) ────────────────────────────────────

def upsert_action(capa_id: int, data: dict) -> dict:
    conn = get_connection()
    if data.get("id"):
        conn.execute(
            """UPDATE qms_capa_actions SET action_type=?, description=?, owner=?, due_date=?,
               completion_date=?, status=?, escalated=?, escalated_to=?, escalated_date=?, evidence_ref=?
               WHERE id=? AND capa_id=?""",
            (
                data.get("action_type", "Corrective"), data.get("description", ""),
                data.get("owner", ""), data.get("due_date", ""), data.get("completion_date", ""),
                data.get("status", "Pending"), 1 if data.get("escalated") else 0,
                data.get("escalated_to", ""), data.get("escalated_date", ""),
                data.get("evidence_ref", ""), data["id"], capa_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM qms_capa_actions WHERE id = ?", (data["id"],)).fetchone()
    else:
        cur = conn.execute(
            """INSERT INTO qms_capa_actions
               (capa_id, action_type, description, owner, due_date, status, evidence_ref)
               VALUES (?,?,?,?,?,?,?)""",
            (
                capa_id, data.get("action_type", "Corrective"), data.get("description", ""),
                data.get("owner", ""), data.get("due_date", ""), data.get("status", "Pending"),
                data.get("evidence_ref", ""),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM qms_capa_actions WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_actions(capa_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_capa_actions WHERE capa_id = ? ORDER BY created_at ASC",
        (capa_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_action(action_id: int) -> dict | None:
    """Single CAPA action, including its owning capa_id — used by
    routes/qms_capa.py to verify tenancy before escalating (Phase 2 RBAC/
    multi-tenancy audit: this route has no cid in its URL to check
    directly)."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_capa_actions WHERE id = ?", (action_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def escalate_action(action_id: int, escalated_to: str, escalated_date: str) -> dict | None:
    conn = get_connection()
    conn.execute(
        """UPDATE qms_capa_actions SET escalated = 1, escalated_to = ?, escalated_date = ?, status = 'Escalated'
           WHERE id = ?""",
        (escalated_to, escalated_date, action_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_capa_actions WHERE id = ?", (action_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Effectiveness checks ────────────────────────────────────────────────────────

def upsert_effectiveness(capa_id: int, data: dict) -> dict:
    conn = get_connection()
    if data.get("id"):
        conn.execute(
            """UPDATE qms_capa_effectiveness SET check_criterion=?, method=?, timeframe=?,
               acceptable_result=?, actual_result=?, status=?, checked_by=?, check_date=?
               WHERE id=? AND capa_id=?""",
            (
                data.get("check_criterion", ""), data.get("method", ""), data.get("timeframe", ""),
                data.get("acceptable_result", ""), data.get("actual_result", ""),
                data.get("status", "Pending"), data.get("checked_by", ""), data.get("check_date", ""),
                data["id"], capa_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM qms_capa_effectiveness WHERE id = ?", (data["id"],)).fetchone()
    else:
        cur = conn.execute(
            """INSERT INTO qms_capa_effectiveness
               (capa_id, check_criterion, method, timeframe, acceptable_result, status)
               VALUES (?,?,?,?,?,?)""",
            (
                capa_id, data.get("check_criterion", ""), data.get("method", ""),
                data.get("timeframe", ""), data.get("acceptable_result", ""), data.get("status", "Pending"),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM qms_capa_effectiveness WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_effectiveness(capa_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_capa_effectiveness WHERE capa_id = ? ORDER BY created_at ASC",
        (capa_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

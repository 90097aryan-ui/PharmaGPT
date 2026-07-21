"""
qms_change_control_database.py — SQLite CRUD for the Change Control module
(Quality Management Suite, Phase 2).

Tables managed here (schema lives in qms_database.QMS_SCHEMA):
  qms_change_controls          : Master change control record.
  qms_change_control_impact    : Impact assessment entries (Validation, Risk,
                                  SOP, Training, Equipment, ... per QMS_META
                                  change_control_impact_areas).
  qms_change_control_actions   : Implementation plan steps (activity, owner,
                                  dates, status) — same shape as CAPA actions.
  qms_change_control_links     : Links a change control to an existing
                                  Deviation or CAPA record (linked_type ∈
                                  {deviation, capa}).

Shared cross-module tables (attachments, comments, audit trail, approvals)
live in qms_database.py and are accessed with record_type='change_control'.
"""

import json
from pharmagpt.database import get_connection
from pharmagpt.qms_database import generate_change_control_number


# ── Change Controls ───────────────────────────────────────────────────────────

def create_change_control(data: dict, *, company_id: str) -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    cc_number = data.get("cc_number") or generate_change_control_number()
    cur = conn.execute(
        """INSERT INTO qms_change_controls
           (cc_number, title, change_type, change_category, department, area,
            equipment_system, project_id, requested_by, date_requested,
            target_implementation_date, change_description, reason_for_change,
            current_state, proposed_state, status, risk_level, form_data, company_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            cc_number,
            data.get("title", "Untitled Change").strip() or "Untitled Change",
            data.get("change_type", "Minor"),
            data.get("change_category", "Equipment"),
            data.get("department", ""),
            data.get("area", ""),
            data.get("equipment_system", ""),
            data.get("project_id") or None,
            data.get("requested_by", ""),
            data.get("date_requested", ""),
            data.get("target_implementation_date", ""),
            data.get("change_description", ""),
            data.get("reason_for_change", ""),
            data.get("current_state", ""),
            data.get("proposed_state", ""),
            data.get("status", "Draft"),
            data.get("risk_level", ""),
            json.dumps(data.get("form_data", {})),
            company_id,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_change_control(new_id)


def get_change_control(cc_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_change_controls WHERE id = ?", (cc_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["form_data"] = json.loads(d.get("form_data") or "{}")
    d["ai_narratives"] = json.loads(d.get("ai_narratives") or "{}")
    return d


def get_all_change_controls(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts (service-role key, not a live
    request); every live route must always pass a company_id."""
    conn = get_connection()
    clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("change_type", "change_category", "status", "department"):
            val = filters.get(field)
            if val:
                clauses.append(f"{field} = ?")
                params.append(val)
        keyword = filters.get("keyword")
        if keyword:
            clauses.append("(title LIKE ? OR cc_number LIKE ? OR change_description LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    sql = "SELECT * FROM qms_change_controls"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["form_data"] = json.loads(d.get("form_data") or "{}")
        d["ai_narratives"] = json.loads(d.get("ai_narratives") or "{}")
        result.append(d)
    return result


def update_change_control(cc_id: int, data: dict) -> dict | None:
    conn = get_connection()
    fields = [
        "title", "change_type", "change_category", "department", "area", "equipment_system",
        "project_id", "requested_by", "date_requested", "target_implementation_date",
        "change_description", "reason_for_change", "current_state", "proposed_state",
        "status", "risk_level", "qa_reviewer", "approver", "implementation_date",
        "verification_date", "closure_date",
    ]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if "form_data" in data:
        updates.append("form_data = ?")
        params.append(json.dumps(data["form_data"]))
    if "ai_narratives" in data:
        updates.append("ai_narratives = ?")
        params.append(json.dumps(data["ai_narratives"]))
    if not updates:
        conn.close()
        return get_change_control(cc_id)
    updates.append("updated_at = datetime('now')")
    params.append(cc_id)
    conn.execute(f"UPDATE qms_change_controls SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_change_control(cc_id)


def delete_change_control(cc_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM qms_change_controls WHERE id = ?", (cc_id,))
    conn.commit()
    conn.close()


def set_change_control_postgres_id(cc_id: int, postgres_id: str) -> None:
    """Record the Postgres `change_controls.id` (uuid) this SQLite change
    control row was dual-written to (Phase 3.5, docs/PHASE3_EXECUTION_PLAN.md)."""
    conn = get_connection()
    conn.execute("UPDATE qms_change_controls SET postgres_id = ? WHERE id = ?", (postgres_id, cc_id))
    conn.commit()
    conn.close()


def set_narrative(cc_id: int, key: str, text: str) -> dict:
    """Merge one AI-generated narrative (risk_summary, rollback_plan, regulatory_impact,
    justification, executive_summary, verification_summary, effectiveness_review) into
    the change control's ai_narratives JSON blob without disturbing the others."""
    cc = get_change_control(cc_id)
    narratives = dict(cc.get("ai_narratives") or {}) if cc else {}
    narratives[key] = text
    return update_change_control(cc_id, {"ai_narratives": narratives})


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, change_type, change_category, created_at FROM qms_change_controls WHERE company_id = ?",
        (company_id,),
    ).fetchall()
    stats = {"total": len(rows), "open": 0, "closed": 0, "by_type": {}, "by_category": {}, "by_status": {}}
    for r in rows:
        d = dict(r)
        status = d.get("status", "Draft")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        if status in ("Closed", "Rejected"):
            stats["closed"] += 1
        else:
            stats["open"] += 1
        stats["by_type"][d.get("change_type", "Minor")] = stats["by_type"].get(d.get("change_type", "Minor"), 0) + 1
        stats["by_category"][d.get("change_category", "Equipment")] = \
            stats["by_category"].get(d.get("change_category", "Equipment"), 0) + 1

    stats["emergency_open"] = conn.execute(
        "SELECT COUNT(*) AS cnt FROM qms_change_controls WHERE change_type = 'Emergency' "
        "AND status NOT IN ('Closed','Rejected') AND company_id = ?",
        (company_id,),
    ).fetchone()["cnt"]

    overdue = conn.execute(
        """SELECT id, cc_number, title, status, target_implementation_date
           FROM qms_change_controls
           WHERE status NOT IN ('Closed','Rejected')
             AND target_implementation_date IS NOT NULL AND target_implementation_date != ''
             AND target_implementation_date < date('now')
             AND company_id = ?
           ORDER BY target_implementation_date ASC""",
        (company_id,),
    ).fetchall()
    stats["overdue"] = len(overdue)
    stats["overdue_changes"] = [dict(r) for r in overdue[:10]]

    pending_approvals = conn.execute(
        "SELECT COUNT(*) AS cnt FROM qms_change_controls WHERE status IN ('QA Review','Approval') AND company_id = ?",
        (company_id,),
    ).fetchone()
    stats["pending_approvals"] = pending_approvals["cnt"] if pending_approvals else 0

    recent = conn.execute(
        "SELECT id, cc_number, title, change_type, status, created_at FROM qms_change_controls "
        "WHERE company_id = ? ORDER BY created_at DESC LIMIT 5",
        (company_id,),
    ).fetchall()
    stats["recent"] = [dict(r) for r in recent]
    conn.close()
    return stats


# ── Impact assessment ──────────────────────────────────────────────────────────

def add_impact(cc_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_change_control_impact (cc_id, impact_area, impacted, extent, action_required)
           VALUES (?,?,?,?,?)""",
        (
            cc_id, data.get("impact_area", ""), data.get("impacted", "Potential"),
            data.get("extent", ""), data.get("action_required", ""),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_change_control_impact WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_impacts(cc_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_change_control_impact WHERE cc_id = ? ORDER BY created_at ASC",
        (cc_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Implementation plan actions ────────────────────────────────────────────────

def upsert_action(cc_id: int, data: dict) -> dict:
    conn = get_connection()
    if data.get("id"):
        conn.execute(
            """UPDATE qms_change_control_actions SET step_no=?, activity=?, responsible=?,
               start_date=?, target_date=?, completion_date=?, status=?
               WHERE id=? AND cc_id=?""",
            (
                data.get("step_no", 0), data.get("activity", ""), data.get("responsible", ""),
                data.get("start_date", ""), data.get("target_date", ""), data.get("completion_date", ""),
                data.get("status", "Pending"), data["id"], cc_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM qms_change_control_actions WHERE id = ?", (data["id"],)).fetchone()
    else:
        cur = conn.execute(
            """INSERT INTO qms_change_control_actions
               (cc_id, step_no, activity, responsible, start_date, target_date, status)
               VALUES (?,?,?,?,?,?,?)""",
            (
                cc_id, data.get("step_no", 0), data.get("activity", ""), data.get("responsible", ""),
                data.get("start_date", ""), data.get("target_date", ""), data.get("status", "Pending"),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM qms_change_control_actions WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_actions(cc_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_change_control_actions WHERE cc_id = ? ORDER BY step_no ASC, created_at ASC",
        (cc_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Deviation / CAPA linkage ───────────────────────────────────────────────────

def link_record(cc_id: int, linked_type: str, linked_id: int) -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO qms_change_control_links (cc_id, linked_type, linked_id) VALUES (?,?,?)",
        (cc_id, linked_type, linked_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_change_control_links WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_linked_records(cc_id: int, linked_type: str | None = None) -> list[dict]:
    conn = get_connection()
    if linked_type:
        rows = conn.execute(
            "SELECT * FROM qms_change_control_links WHERE cc_id = ? AND linked_type = ? ORDER BY created_at DESC",
            (cc_id, linked_type),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM qms_change_control_links WHERE cc_id = ? ORDER BY created_at DESC",
            (cc_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_change_controls_for_record(linked_type: str, linked_id: int) -> list[dict]:
    """Reverse lookup — change controls linked to a given Deviation/CAPA. Lets
    those modules surface 'Related Change Controls' without a schema change or
    any edit to their own database/route/JS files."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT cc.* FROM qms_change_controls cc
           JOIN qms_change_control_links l ON l.cc_id = cc.id
           WHERE l.linked_type = ? AND l.linked_id = ? ORDER BY l.created_at DESC""",
        (linked_type, linked_id),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["form_data"] = json.loads(d.get("form_data") or "{}")
        d["ai_narratives"] = json.loads(d.get("ai_narratives") or "{}")
        result.append(d)
    return result

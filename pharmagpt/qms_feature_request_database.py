"""
qms_feature_request_database.py — SQLite CRUD for the Feature Requests module.

Table managed here (schema lives in qms_database.QMS_SCHEMA):
  feature_requests : Master feature request record — title, description,
                      module, priority, status, assigned_to, created_by.

v1 is CRUD only — no workflow engine, no dual-write to Postgres, no
approvals. Attachments/comments/audit-trail reuse the shared polymorphic
tables in qms_database.py with record_type='feature_request' (see
routes/qms_common.py).
"""

from pharmagpt.database import get_connection
from pharmagpt.qms_database import generate_feature_request_number


def create_feature_request(data: dict, *, company_id: str, created_by: str) -> dict:
    """`company_id`/`created_by` must come from the caller's authenticated
    tenant (`g.tenant`), never client-supplied — see pharmagpt/tenancy.py."""
    conn = get_connection()
    fr_number = generate_feature_request_number()
    cur = conn.execute(
        """INSERT INTO feature_requests
           (fr_number, title, description, module, priority, status, assigned_to, created_by, company_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            fr_number,
            data.get("title", "Untitled Feature Request").strip() or "Untitled Feature Request",
            data.get("description", ""),
            data.get("module", ""),
            data.get("priority", "Medium"),
            data.get("status", "New"),
            data.get("assigned_to", ""),
            created_by,
            company_id,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_feature_request(new_id)


def get_feature_request(fr_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM feature_requests WHERE id = ?", (fr_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_feature_requests(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("status", "priority", "module"):
            val = filters.get(field)
            if val:
                clauses.append(f"{field} = ?")
                params.append(val)
        keyword = filters.get("keyword")
        if keyword:
            clauses.append("(title LIKE ? OR fr_number LIKE ? OR description LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    sql = "SELECT * FROM feature_requests"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_feature_request(fr_id: int, data: dict) -> dict | None:
    conn = get_connection()
    fields = ["title", "description", "module", "priority", "status", "assigned_to"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if not updates:
        conn.close()
        return get_feature_request(fr_id)
    updates.append("updated_at = datetime('now')")
    params.append(fr_id)
    conn.execute(f"UPDATE feature_requests SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_feature_request(fr_id)


def delete_feature_request(fr_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM feature_requests WHERE id = ?", (fr_id,))
    conn.commit()
    conn.close()

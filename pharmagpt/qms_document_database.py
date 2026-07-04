"""
qms_document_database.py — SQLite CRUD for the Document Control module.

Tables managed here (schema lives in qms_database.QMS_SCHEMA):
  qms_documents             : Master controlled-document record.
  qms_document_versions     : Revision history snapshots.
  qms_document_distribution : Who a document was distributed to / acknowledgement.
  qms_document_training     : Training requirement tracking per document.

Shared cross-module tables (attachments, comments, audit trail, approvals)
live in qms_database.py and are accessed with record_type='document'.
"""

import json
from pharmagpt.database import get_connection
from pharmagpt.qms_database import generate_document_number


# ── Documents ──────────────────────────────────────────────────────────────────

def create_document(data: dict) -> dict:
    conn = get_connection()
    doc_number = data.get("doc_number") or generate_document_number(
        data.get("doc_type", "SOP"), data.get("department", "")
    )
    cur = conn.execute(
        """INSERT INTO qms_documents
           (doc_number, doc_type, title, department, category, version, status,
            effective_date, review_date, expiry_date, owner, reviewer, approver,
            content, form_data, project_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_number,
            data.get("doc_type", "SOP"),
            data.get("title", "Untitled Document").strip() or "Untitled Document",
            data.get("department", ""),
            data.get("category", ""),
            data.get("version", "1.0"),
            data.get("status", "Draft"),
            data.get("effective_date", ""),
            data.get("review_date", ""),
            data.get("expiry_date", ""),
            data.get("owner", ""),
            data.get("reviewer", ""),
            data.get("approver", ""),
            data.get("content", ""),
            json.dumps(data.get("form_data", {})),
            data.get("project_id") or None,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_document(new_id)


def get_document(document_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_documents WHERE id = ?", (document_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["form_data"] = json.loads(d.get("form_data") or "{}")
    d["ai_review_data"] = json.loads(d.get("ai_review_data") or "{}")
    return d


def get_all_documents(filters: dict | None = None) -> list[dict]:
    conn = get_connection()
    clauses, params = [], []
    if filters:
        for field in ("doc_type", "status", "department", "category"):
            val = filters.get(field)
            if val:
                clauses.append(f"{field} = ?")
                params.append(val)
        keyword = filters.get("keyword")
        if keyword:
            clauses.append("(title LIKE ? OR doc_number LIKE ? OR content LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    sql = "SELECT id, doc_number, doc_type, title, department, category, version, status, " \
          "effective_date, review_date, expiry_date, owner, reviewer, approver, project_id, " \
          "created_at, updated_at FROM qms_documents"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_document(document_id: int, data: dict) -> dict | None:
    conn = get_connection()
    fields = [
        "doc_type", "title", "department", "category", "version", "status",
        "effective_date", "review_date", "expiry_date", "owner", "reviewer", "approver",
        "content", "project_id",
    ]
    updates, params = [], []
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
    if not updates:
        conn.close()
        return get_document(document_id)
    updates.append("updated_at = datetime('now')")
    params.append(document_id)
    conn.execute(f"UPDATE qms_documents SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_document(document_id)


def delete_document(document_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM qms_documents WHERE id = ?", (document_id,))
    conn.commit()
    conn.close()


def get_dashboard_stats() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT status, doc_type FROM qms_documents").fetchall()
    stats = {
        "total": len(rows), "draft": 0, "under_review": 0, "pending_approval": 0,
        "effective": 0, "under_revision": 0, "obsolete": 0, "by_type": {},
    }
    status_key_map = {
        "Draft": "draft", "Under Review": "under_review", "Pending Approval": "pending_approval",
        "Effective": "effective", "Under Revision": "under_revision", "Obsolete": "obsolete",
    }
    for r in rows:
        d = dict(r)
        key = status_key_map.get(d.get("status", "Draft"))
        if key:
            stats[key] += 1
        stats["by_type"][d.get("doc_type", "Other")] = stats["by_type"].get(d.get("doc_type", "Other"), 0) + 1

    due_soon = conn.execute(
        """SELECT id, doc_number, title, review_date, expiry_date, status
           FROM qms_documents
           WHERE status = 'Effective'
             AND ((review_date IS NOT NULL AND review_date != '' AND review_date <= date('now', '+30 days'))
                  OR (expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= date('now', '+30 days')))
           ORDER BY review_date ASC LIMIT 10"""
    ).fetchall()
    stats["due_for_review"] = [dict(r) for r in due_soon]

    recent = conn.execute(
        "SELECT id, doc_number, title, doc_type, status, created_at FROM qms_documents ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    stats["recent"] = [dict(r) for r in recent]
    conn.close()
    return stats


def search_documents(keyword: str) -> list[dict]:
    return get_all_documents({"keyword": keyword})


# ── Versions ───────────────────────────────────────────────────────────────────

def create_version(document_id: int, version: str, change_summary: str,
                   content_snapshot: str, changed_by: str = "") -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_document_versions (document_id, version, change_summary, content_snapshot, changed_by)
           VALUES (?,?,?,?,?)""",
        (document_id, version, change_summary, content_snapshot, changed_by),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_document_versions WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_versions(document_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_document_versions WHERE document_id = ? ORDER BY created_at DESC",
        (document_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Distribution ───────────────────────────────────────────────────────────────

def add_distribution(document_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_document_distribution (document_id, distributed_to, department, distributed_date)
           VALUES (?,?,?,?)""",
        (document_id, data.get("distributed_to", ""), data.get("department", ""), data.get("distributed_date", "")),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_document_distribution WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_distribution(document_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_document_distribution WHERE document_id = ? ORDER BY distributed_date DESC",
        (document_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def acknowledge_distribution(dist_id: int, acknowledged_date: str) -> dict | None:
    conn = get_connection()
    conn.execute(
        "UPDATE qms_document_distribution SET acknowledged = 1, acknowledged_date = ? WHERE id = ?",
        (acknowledged_date, dist_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_document_distribution WHERE id = ?", (dist_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Training ───────────────────────────────────────────────────────────────────

def add_training(document_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_document_training (document_id, trainee_name, role, training_status, training_date, trainer, evidence_ref)
           VALUES (?,?,?,?,?,?,?)""",
        (
            document_id, data.get("trainee_name", ""), data.get("role", ""),
            data.get("training_status", "Pending"), data.get("training_date", ""),
            data.get("trainer", ""), data.get("evidence_ref", ""),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_document_training WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_training(document_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_document_training WHERE document_id = ? ORDER BY id DESC",
        (document_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_training_status(training_id: int, training_status: str, training_date: str = "") -> dict | None:
    conn = get_connection()
    conn.execute(
        "UPDATE qms_document_training SET training_status = ?, training_date = ? WHERE id = ?",
        (training_status, training_date, training_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_document_training WHERE id = ?", (training_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

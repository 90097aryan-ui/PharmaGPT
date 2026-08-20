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
from pharmagpt.services import document_versioning as dv
from pharmagpt.services import lifecycle_engine


# ── Documents ──────────────────────────────────────────────────────────────────

def create_document(data: dict, *, company_id: str, created_by_user_id: str = "") -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py.
    `created_by_user_id` (Document Control redesign) is used only to
    populate the document's initial version row's own `created_by_user_id`
    (see create_initial_version() below) — it is deliberately NOT stored on
    qms_documents itself here, since a document-level creator column is
    outside this redesign's scope."""
    conn = get_connection()
    doc_number = data.get("doc_number") or generate_document_number(
        data.get("doc_type", "SOP"), data.get("department", "")
    )
    cur = conn.execute(
        """INSERT INTO qms_documents
           (doc_number, doc_type, title, department, category, version, status,
            effective_date, review_date, expiry_date, owner, reviewer, approver,
            content, form_data, project_id, company_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            company_id,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    create_initial_version(new_id, data.get("content", ""), created_by_user_id)
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


def get_all_documents(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline backfill/parity scripts (service-role key, not a live
    request); every live route must always pass a company_id."""
    conn = get_connection()
    clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
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
          "created_at, updated_at, company_id FROM qms_documents"
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
        "effective_date", "review_date", "expiry_date", "superseded_date", "owner", "reviewer", "approver",
        "content", "project_id", "approval_quorum",
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


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py)."""
    conn = get_connection()
    rows = conn.execute("SELECT status, doc_type FROM qms_documents WHERE company_id = ?", (company_id,)).fetchall()
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
             AND company_id = ?
           ORDER BY review_date ASC LIMIT 10""",
        (company_id,),
    ).fetchall()
    stats["due_for_review"] = [dict(r) for r in due_soon]

    recent = conn.execute(
        "SELECT id, doc_number, title, doc_type, status, created_at FROM qms_documents "
        "WHERE company_id = ? ORDER BY created_at DESC LIMIT 5",
        (company_id,),
    ).fetchall()
    stats["recent"] = [dict(r) for r in recent]
    conn.close()
    return stats


def search_documents(keyword: str, company_id: str) -> list[dict]:
    return get_all_documents(company_id, {"keyword": keyword})


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


def get_version(version_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_document_versions WHERE id = ?", (version_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_current_version(document_id: int) -> dict | None:
    """The document's authoritative current version row, via
    qms_documents.current_version_id. None for a document created before
    this redesign that has never had a version created for it."""
    conn = get_connection()
    row = conn.execute(
        """SELECT v.* FROM qms_document_versions v
           JOIN qms_documents d ON d.current_version_id = v.id
           WHERE d.id = ?""",
        (document_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _insert_version_row(document_id: int, *, version_number: str, parent_version_id: int | None,
                         content_snapshot: str, created_by_user_id: str, change_summary: str = "") -> dict:
    """Low-level insert only — always creates a 'draft' row. Never call this
    directly to fork a rejected/effective version; use
    services/document_versioning.py's orchestration functions, which also
    update qms_documents.current_version_id and the parent version's own
    status. `version`/`changed_by` are populated identically to
    `version_number`/`created_by_user_id` for backward-compatible reads by
    existing callers (services/qms_document_service.py's report generator,
    the legacy 'versions' UI tab)."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_document_versions
           (document_id, version, change_summary, content_snapshot, changed_by,
            version_number, parent_version_id, status, created_by_user_id)
           VALUES (?,?,?,?,?,?,?,'draft',?)""",
        (document_id, version_number, change_summary, content_snapshot, created_by_user_id,
         version_number, parent_version_id, created_by_user_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_document_versions WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def create_initial_version(document_id: int, content: str, created_by_user_id: str) -> dict:
    """A brand-new document's first version (0.1). Also points
    qms_documents.current_version_id at it and mirrors content/version onto
    the parent row so every existing list/dashboard/search query (which
    reads qms_documents.content/.version directly) keeps working unchanged."""
    version = _insert_version_row(
        document_id, version_number=dv.first_version_number(), parent_version_id=None,
        content_snapshot=content, created_by_user_id=created_by_user_id,
    )
    set_document_current_version(document_id, version["id"])
    return version


def set_document_current_version(document_id: int, version_id: int) -> None:
    """The only function that updates qms_documents.current_version_id, and
    keeps the legacy denormalized content/version columns mirroring the new
    current version row — existing readers of qms_documents.content/.version
    (DOCX export, KB publish, dashboards) never need to know this redesign
    exists."""
    version = get_version(version_id)
    if not version:
        raise ValueError(f"No such document version {version_id}")
    conn = get_connection()
    conn.execute(
        "UPDATE qms_documents SET current_version_id = ?, version = ?, content = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (version_id, version["version_number"], version["content_snapshot"], document_id),
    )
    conn.commit()
    conn.close()


def transition_version_status(version_id: int, new_status: str, **extra_fields) -> dict:
    """The only function permitted to change a qms_document_versions row's
    status (or the handful of fields below the trigger boundary that are
    legitimately still writable outside 'draft' — see qms_database.py's
    trg_document_versions_immutable_* triggers for the DB-layer half of this
    guarantee). Validates the transition against
    lifecycle_engine.QMS_DOCUMENT_VERSION before writing anything —
    service-layer guard, independent of and in addition to the DB trigger.

    `extra_fields` may include: rejection_reason, effective_date,
    workflow_instance_id, self_check_completed_at, source_attachment_id —
    the columns the trigger does NOT freeze at the content/'draft' boundary,
    because each is legitimately written exactly once, at the specific
    transition that produces it (see each column's schema comment)."""
    version = get_version(version_id)
    if not version:
        raise ValueError(f"No such document version {version_id}")
    lifecycle_engine.validate_transition("QMS_DOCUMENT_VERSION", version["status"], new_status)

    allowed_extra = {"rejection_reason", "effective_date", "workflow_instance_id",
                      "self_check_completed_at", "source_attachment_id"}
    updates, params = ["status = ?"], [new_status]
    for k, v in extra_fields.items():
        if k not in allowed_extra:
            raise ValueError(f"'{k}' is not a field transition_version_status() may set")
        updates.append(f"{k} = ?")
        params.append(v)
    params.append(version_id)

    conn = get_connection()
    conn.execute(f"UPDATE qms_document_versions SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_version(version_id)


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


def get_distribution_entry(dist_id: int) -> dict | None:
    """Single distribution entry, including its owning document_id — used by
    routes/qms_documents.py to verify tenancy before acknowledging (Phase 2
    RBAC/multi-tenancy audit: this route has no did in its URL to check
    directly)."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_document_distribution WHERE id = ?", (dist_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


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


def get_training_entry(training_id: int) -> dict | None:
    """Single training entry, including its owning document_id — used by
    routes/qms_documents.py to verify tenancy before updating status
    (Phase 2 RBAC/multi-tenancy audit: this route has no did in its URL to
    check directly)."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_document_training WHERE id = ?", (training_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


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

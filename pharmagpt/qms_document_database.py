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


# ── Templates (Document Control redesign, Phase 5) ───────────────────────────

def create_template(doc_type: str, name: str, structure: list, *,
                     company_id: str = "", created_by: str = "") -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO qms_document_templates (doc_type, name, structure_json, company_id, created_by) "
        "VALUES (?,?,?,?,?)",
        (doc_type, name, json.dumps(structure), company_id, created_by),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_document_templates WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    d = dict(row)
    d["structure"] = json.loads(d["structure_json"])
    return d


def get_template(template_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_document_templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["structure"] = json.loads(d["structure_json"])
    return d


def list_templates(doc_type: str = "", company_id: str = "") -> list[dict]:
    """Active templates for `doc_type`, company-specific ones first, falling
    back to platform-wide defaults (company_id='')."""
    conn = get_connection()
    clauses, params = ["is_active = 1"], []
    if doc_type:
        clauses.append("doc_type = ?")
        params.append(doc_type)
    if company_id:
        clauses.append("(company_id = ? OR company_id = '')")
        params.append(company_id)
    else:
        clauses.append("company_id = ''")
    rows = conn.execute(
        f"SELECT * FROM qms_document_templates WHERE {' AND '.join(clauses)} ORDER BY company_id DESC, name ASC",
        params,
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["structure"] = json.loads(d["structure_json"])
        out.append(d)
    return out


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
            prepared_by, content, form_data, project_id, company_id, template_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            # Document Control Information (spec §2): "Prepared By" is the
            # authenticated creator, mirroring urs_database.create_urs()'s
            # identical prepared_by pattern — routes/qms_documents.py stamps
            # this from g.tenant, never accepts a client-supplied value.
            data.get("prepared_by", ""),
            data.get("content", ""),
            json.dumps(data.get("form_data", {})),
            data.get("project_id") or None,
            company_id,
            data.get("template_id") or None,
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
        "prepared_by", "reviewed_by", "approved_by",
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

    # Document Control redesign: keep the authoritative CURRENT version's
    # content_snapshot in sync with every content edit, not just the
    # denormalized qms_documents.content mirror — otherwise the version
    # that gets frozen at Submit for Review would be whatever content
    # existed at creation/fork time, not the author's actual final edits.
    # Every existing caller of update_document() with "content" (the PUT
    # route, AI draft generation) gets this fix automatically, with no
    # change needed at those call sites. Silently no-ops if the current
    # version isn't 'draft' (routes/qms_documents.py's PUT already blocks
    # content edits outside Draft/Under Revision before reaching here).
    if "content" in data:
        version = get_current_version(document_id)
        if version and version["status"] == "draft":
            vconn = get_connection()
            vconn.execute(
                "UPDATE qms_document_versions SET content_snapshot = ? WHERE id = ?",
                (data["content"], version["id"]),
            )
            vconn.commit()
            vconn.close()

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


def record_self_check(document_id: int, performed_by: str) -> dict:
    """Author Self-Check (Document Control redesign, Phase 5) — a HARD gate:
    Submit for Review is blocked until this has been recorded against the
    CURRENT version specifically (see is_self_check_cleared() below). Only
    legal while the version is still 'draft' — self-check is a pre-
    submission author action, not something that can be backfilled onto a
    version already under review. Never carries forward to a new version:
    every version row is created fresh with self_check_completed_at=''
    (see _insert_version_row) — a version forked by rejection or by a new
    revision cycle always requires its own fresh self-check."""
    version = get_current_version(document_id)
    if not version:
        raise ValueError(f"Document {document_id} has no current version")
    if version["status"] != "draft":
        raise ValueError(f"Self-Check can only be recorded while the version is Draft (current status: "
                          f"'{version['status']}')")
    from datetime import datetime, timezone
    completed_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "UPDATE qms_document_versions SET self_check_completed_at = ? WHERE id = ?",
        (completed_at, version["id"]),
    )
    conn.commit()
    conn.close()
    return get_version(version["id"])


def is_self_check_cleared(document_id: int) -> bool:
    """Whether the document's CURRENT version has a recorded self-check —
    the hard-gate check routes/qms_documents.py calls before allowing
    Submit for Review."""
    version = get_current_version(document_id)
    return bool(version and version.get("self_check_completed_at"))


_TRANSITION_EXTRA_FIELDS = {"rejection_reason", "effective_date", "workflow_instance_id",
                            "self_check_completed_at", "source_attachment_id",
                            "version", "version_number"}


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
    transition that produces it (see each column's schema comment).
    `version`/`version_number` are additionally restricted to the
    approved -> effective transition specifically (the one point a
    version's number is legitimately finalized, e.g. 0.3 -> 1.0 — see
    services/document_versioning.py's numbering rule and
    try_clear_training_gate() below) — this mirrors the DB trigger's own
    WHEN-clause exception exactly, service-layer side."""
    version = get_version(version_id)
    if not version:
        raise ValueError(f"No such document version {version_id}")
    lifecycle_engine.validate_transition("QMS_DOCUMENT_VERSION", version["status"], new_status)
    if ("version" in extra_fields or "version_number" in extra_fields) and (
            version["status"] != "approved" or new_status != "effective"):
        raise ValueError("version/version_number may only be set on the approved -> effective transition")

    updates, params = ["status = ?"], [new_status]
    for k, v in extra_fields.items():
        if k not in _TRANSITION_EXTRA_FIELDS:
            raise ValueError(f"'{k}' is not a field transition_version_status() may set")
        updates.append(f"{k} = ?")
        params.append(v)
    params.append(version_id)

    conn = get_connection()
    conn.execute(f"UPDATE qms_document_versions SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_version(version_id)


# ── Workflow <-> version linkage (Document Control redesign, Phase 2) ───────
# Called only from services/workflow_engine.py's document-scoped hook
# registry (VERSION_ON_INSTANCE_START / VERSION_ON_STEP_APPROVED /
# VERSION_ON_STEP_REJECTED) — never directly from routes.

def start_review_cycle_for_version(document_id: int, instance_id: int) -> dict:
    """Submit for Review: the document's current (draft) version moves to
    under_review and records which workflow instance owns this cycle."""
    version = get_current_version(document_id)
    if not version:
        raise ValueError(f"Document {document_id} has no current version to submit")
    return transition_version_status(version["id"], "under_review", workflow_instance_id=instance_id)


def advance_version_to_pending_approval(document_id: int) -> dict:
    """Review accepted: the version moves from under_review to
    pending_approval, awaiting the final quorum approval stage."""
    version = get_current_version(document_id)
    if not version:
        raise ValueError(f"Document {document_id} has no current version")
    return transition_version_status(version["id"], "pending_approval")


def start_new_revision(document_id: int) -> dict:
    """Starting a fresh revision cycle against an already-Effective document
    (the spec's 'Existing SOP: 1.0 Effective -> 1.1 Revision Draft' case —
    distinct from reject_and_fork_version(), which forks mid-review/
    mid-approval, not from an Effective version). The outgoing Effective
    version is marked 'superseded' (still fully retained, still read-only —
    never 'effective' again, since a document has at most one Effective
    version at a time) and a new Draft version is forked from it via
    services/document_versioning.py's next_revision_number() (X.0 -> X.1).
    Returns the new draft version."""
    current = get_current_version(document_id)
    if not current:
        raise ValueError(f"Document {document_id} has no current version")
    if current["status"] != "effective":
        raise ValueError(f"Version {current['id']} is '{current['status']}', not 'effective' — "
                          f"only an Effective version can start a new revision cycle")
    transition_version_status(current["id"], "superseded")

    next_number = dv.next_revision_number(current["version_number"])
    new_version = _insert_version_row(
        document_id, version_number=next_number, parent_version_id=current["id"],
        content_snapshot=current["content_snapshot"], created_by_user_id=current["created_by_user_id"],
        change_summary=f"New revision cycle started from Effective version {current['version_number']}",
    )
    set_document_current_version(document_id, new_version["id"])
    return new_version


def reject_and_fork_version(document_id: int, rejection_reason: str) -> dict:
    """Any Review or Approval rejection: the current version is marked
    permanently immutable (review_rejected if it was under_review,
    approval_rejected if it was pending_approval — chosen by its own
    current status, never passed in) with `rejection_reason` recorded
    against it forever, and a brand-new Draft version is forked from its
    content and becomes the document's current version. The forked
    version's self_check_completed_at starts empty (a new Self-Check is
    always required — see qms_database.py's column default) and its
    created_by_user_id carries forward from the rejected version (nothing
    has been authored yet; the human author edits this draft next).

    Returns the NEW draft version."""
    current = get_current_version(document_id)
    if not current:
        raise ValueError(f"Document {document_id} has no current version to reject")
    reject_status = {"under_review": "review_rejected", "pending_approval": "approval_rejected"}.get(current["status"])
    if not reject_status:
        raise ValueError(f"Version {current['id']} cannot be rejected from status '{current['status']}'")
    transition_version_status(current["id"], reject_status, rejection_reason=rejection_reason)

    next_number = dv.next_version_number(current["version_number"], "rework")
    new_version = _insert_version_row(
        document_id, version_number=next_number, parent_version_id=current["id"],
        content_snapshot=current["content_snapshot"], created_by_user_id=current["created_by_user_id"],
        change_summary=f"Forked after rejection of version {current['version_number']}",
    )
    set_document_current_version(document_id, new_version["id"])
    return new_version


# ── Approver pool (Document Control redesign, Phase 3) ───────────────────────
# Department Head and Quality Head/Designee are mandatory seats; Plant Head
# is optional. Required quorum for the final Approval stage is always 2
# regardless of pool size (2-of-2 without Plant Head, 2-of-3 with) — a fixed
# business rule, not a per-document setting; see resolve_pool_approvers().
#
# "reviewer" (final correction pass): the single named decider for the
# 'under_review' step — mandatory, but single-decider, not quorum, so it is
# resolved separately by resolve_pool_reviewer() below rather than folded
# into MANDATORY_POOL_ROLES/resolve_pool_approvers() (which stay scoped to
# the 'effective' step's quorum exactly as before this change).

MANDATORY_POOL_ROLES = ("department_head", "quality_head")
ALL_POOL_ROLES = ("reviewer", "department_head", "quality_head", "plant_head")
APPROVAL_QUORUM_REQUIRED = 2


def get_approver_pool(company_id: str, department: str = "") -> list[dict]:
    """Active pool rows for `department`, falling back to the company-wide
    default pool (department='') for any role not specifically configured
    for this department. At most one row per pool_role in the result."""
    conn = get_connection()
    dept_rows = conn.execute(
        "SELECT * FROM qms_document_approver_pool WHERE company_id = ? AND department = ? AND active = 1",
        (company_id, department),
    ).fetchall()
    by_role = {r["pool_role"]: dict(r) for r in dept_rows}
    if department:
        default_rows = conn.execute(
            "SELECT * FROM qms_document_approver_pool WHERE company_id = ? AND department = '' AND active = 1",
            (company_id,),
        ).fetchall()
        for r in default_rows:
            by_role.setdefault(r["pool_role"], dict(r))
    conn.close()
    return list(by_role.values())


def set_approver_pool_member(company_id: str, department: str, pool_role: str,
                              user_id: str, display_name: str = "") -> dict:
    if pool_role not in ALL_POOL_ROLES:
        raise ValueError(f"Unknown pool_role '{pool_role}'")
    conn = get_connection()
    conn.execute(
        """INSERT INTO qms_document_approver_pool (company_id, department, pool_role, user_id, display_name, active)
           VALUES (?,?,?,?,?,1)
           ON CONFLICT (company_id, department, pool_role)
           DO UPDATE SET user_id = excluded.user_id, display_name = excluded.display_name,
                         active = 1, updated_at = datetime('now')""",
        (company_id, department, pool_role, user_id, display_name),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM qms_document_approver_pool WHERE company_id = ? AND department = ? AND pool_role = ?",
        (company_id, department, pool_role),
    ).fetchone()
    conn.close()
    return dict(row)


def deactivate_approver_pool_member(company_id: str, department: str, pool_role: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE qms_document_approver_pool SET active = 0, updated_at = datetime('now') "
        "WHERE company_id = ? AND department = ? AND pool_role = ?",
        (company_id, department, pool_role),
    )
    conn.commit()
    conn.close()


def resolve_pool_approvers(document: dict) -> list[dict]:
    """[{'user_id', 'display_name', 'pool_role'}, ...] for a document's
    department (falling back to the company-wide pool for any unconfigured
    role) — Department Head and Quality Head only (Plant Head appended
    only when configured). Raises ValueError naming whichever mandatory
    role(s) are missing; callers (routes) catch this and fall back to
    manual approver assignment rather than blocking the workflow."""
    pool = get_approver_pool(document.get("company_id", ""), document.get("department", ""))
    by_role = {p["pool_role"]: p for p in pool if p.get("user_id")}
    missing = [r for r in MANDATORY_POOL_ROLES if r not in by_role]
    if missing:
        raise ValueError(f"Approver pool is missing mandatory role(s): {', '.join(missing)}")
    approvers = [
        {"user_id": by_role[r]["user_id"], "display_name": by_role[r].get("display_name", ""), "pool_role": r}
        for r in MANDATORY_POOL_ROLES
    ]
    if "plant_head" in by_role:
        approvers.append({"user_id": by_role["plant_head"]["user_id"],
                           "display_name": by_role["plant_head"].get("display_name", ""), "pool_role": "plant_head"})
    return approvers


def resolve_pool_reviewer(document: dict) -> dict | None:
    """{'user_id', 'display_name', 'pool_role'} for the document's
    department (falling back to the company-wide pool) 'reviewer' seat, for
    the 'under_review' step — single named decider, not quorum, so unlike
    resolve_pool_approvers() this never raises: returns None when not
    configured, and the caller (routes/qms_documents.py) leaves the step
    without a pre-assigned approver in that case, exactly as it already does
    today. Once assigned, workflow_engine.decide_step()'s existing "no
    assigned approver yet" check is what actually prevents the step from
    being decided by anyone else."""
    pool = get_approver_pool(document.get("company_id", ""), document.get("department", ""))
    by_role = {p["pool_role"]: p for p in pool if p.get("user_id")}
    entry = by_role.get("reviewer")
    if not entry:
        return None
    return {"user_id": entry["user_id"], "display_name": entry.get("display_name", ""), "pool_role": "reviewer"}


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
    """`document_version_id` (Document Control redesign) is always
    stamped with whatever the document's CURRENT version is at the moment
    the training row is created — never editable afterward. This is what
    makes "rejected-version training cannot clear a newer version" true
    with no special-case logic: if a rejection later forks a new version,
    document_version_id already points at the (now superseded) version
    these trainees were assigned against, and a fresh training round tied
    to the new version has to be created before its own gate can clear."""
    current_version = get_current_version(document_id)
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_document_training
           (document_id, trainee_name, role, training_status, training_date, trainer, evidence_ref, document_version_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            document_id, data.get("trainee_name", ""), data.get("role", ""),
            data.get("training_status", "Pending"), data.get("training_date", ""),
            data.get("trainer", ""), data.get("evidence_ref", ""),
            current_version["id"] if current_version else None,
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


# ── Training gate (Document Control redesign, Phase 4) ──────────────────────
# The SOP must not become Effective unless >=1 trainee is assigned AND
# training_completion >= 90% for that specific version. Zero trainees is
# NEVER treated as 100% — training_completion_pct() returns None (not 0.0
# or 100.0) when no trainee rows exist for the version, and
# training_gate_status()/try_clear_training_gate() both treat None as "not
# cleared", never as vacuously passing.

TRAINING_GATE_THRESHOLD_PCT = 90.0


def training_completion_pct(document_version_id: int) -> float | None:
    """None (not 0.0) when zero trainees are assigned to this version —
    callers must never treat that as a passing percentage."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT training_status FROM qms_document_training WHERE document_version_id = ?",
        (document_version_id,),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    completed = sum(1 for r in rows if r["training_status"] == "Completed")
    return (completed / len(rows)) * 100.0


def training_gate_status(document_version_id: int) -> dict:
    """{'completion_pct', 'trainee_count', 'cleared', 'threshold_pct'} — the
    single source of truth the UI and the gate-check function both read, so
    they can never disagree about whether the gate has cleared."""
    conn = get_connection()
    trainee_count = conn.execute(
        "SELECT COUNT(*) AS n FROM qms_document_training WHERE document_version_id = ?",
        (document_version_id,),
    ).fetchone()["n"]
    conn.close()
    pct = training_completion_pct(document_version_id)
    cleared = trainee_count > 0 and pct is not None and pct >= TRAINING_GATE_THRESHOLD_PCT
    return {"completion_pct": pct, "trainee_count": trainee_count, "cleared": cleared,
            "threshold_pct": TRAINING_GATE_THRESHOLD_PCT}


def advance_version_to_approved(document_id: int) -> dict:
    """Quorum/approval achieved on the final Approval step: the version
    moves pending_approval -> approved (NOT effective — see
    try_clear_training_gate() below for the training-gated final step)."""
    version = get_current_version(document_id)
    if not version:
        raise ValueError(f"Document {document_id} has no current version")
    return transition_version_status(version["id"], "approved")


def try_clear_training_gate(document_id: int, effective_date: str | None = None) -> dict | None:
    """If the document's current version is 'approved' and its training
    gate has cleared, transitions the version to 'effective' (stamping
    effective_date), updates qms_documents.status to 'Effective', and
    returns the updated document — the caller (services/workflow_engine.py's
    _apply_document_status, or routes/qms_documents.py's update_training)
    is responsible for any KB-publish side effect. Returns None (no-op) if
    the version isn't 'approved' yet or the gate hasn't cleared — safe to
    call speculatively any time a training record's status changes.

    `effective_date` (spec §4 gap closure: "Effective date is supplied/
    confirmed at release"): the Quality Coordinator's confirmed release
    date, from routes/qms_documents.py::release_document — defaults to
    today when not supplied (every pre-existing caller, incl. tests)."""
    version = get_current_version(document_id)
    if not version or version["status"] != "approved":
        return None
    gate = training_gate_status(version["id"])
    if not gate["cleared"]:
        return None
    from datetime import date
    effective_date = effective_date or date.today().isoformat()
    # The version's number is finalized here — e.g. 0.3 -> 1.0, or 1.3 -> 2.0
    # — this is the one point in the whole lifecycle a version's number is
    # legitimately rewritten (see transition_version_status()'s guard and
    # qms_database.py's matching DB-trigger exception).
    final_number = dv.next_version_number(version["version_number"], "effective")
    transition_version_status(version["id"], "effective", effective_date=effective_date,
                               version=final_number, version_number=final_number)
    return update_document(document_id, {"status": "Effective", "effective_date": effective_date,
                                          "version": final_number})

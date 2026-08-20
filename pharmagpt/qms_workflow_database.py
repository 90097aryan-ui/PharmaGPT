"""
qms_workflow_database.py — SQLite CRUD for the generic, cross-module
workflow engine (Phase 1: Deviation Investigation Redesign).

Schema lives in qms_database.QMS_SCHEMA:
  qms_workflow_templates       : named, ordered workflow definitions.
  qms_workflow_template_steps  : one row per ordered step in a template.
  qms_workflow_instances       : one workflow run (per record, per attempt).
  qms_workflow_instance_steps  : per-instance copy of each step + its outcome.
  qms_workflow_step_approvers  : named user(s) assigned to an approval step.

This module is pure CRUD (mirrors qms_deviation_database.py's style, one
connection per call) — decision logic, eligibility checks, and audit logging
live in services/workflow_engine.py. Reusable by any record_type; Phase 1
only calls it for record_type='deviation'.
"""

from pharmagpt.database import get_connection


# ── Templates ────────────────────────────────────────────────────────────────

def get_template_by_key(workflow_key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM qms_workflow_templates WHERE workflow_key = ?", (workflow_key,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_template_steps(template_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_workflow_template_steps WHERE template_id = ? ORDER BY step_order ASC",
        (template_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Additive only (Deviation UI & Workflow Refactor): lets a caller build a
# fresh template at runtime (e.g. one dynamic Review chain per deviation),
# on top of the same tables the seeded templates above already live in — no
# change to get_template_by_key/get_template_steps or to any function below.

def create_template(workflow_key: str, name: str, module: str) -> dict:
    conn = get_connection()
    conn.execute(
        "INSERT INTO qms_workflow_templates (workflow_key, name, module) VALUES (?,?,?)",
        (workflow_key, name, module),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM qms_workflow_templates WHERE workflow_key = ?", (workflow_key,)
    ).fetchone()
    conn.close()
    return dict(row)


def create_template_step(template_id: int, step_order: int, step_key: str, step_name: str,
                          step_type: str, eligible_roles: str, gate_status: str) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_workflow_template_steps
           (template_id, step_order, step_key, step_name, step_type, eligible_roles, gate_status)
           VALUES (?,?,?,?,?,?,?)""",
        (template_id, step_order, step_key, step_name, step_type, eligible_roles, gate_status),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM qms_workflow_template_steps WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    conn.close()
    return dict(row)


# ── Instances ────────────────────────────────────────────────────────────────

def create_instance(template_id: int, record_type: str, record_id: int, company_id: str | None) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_workflow_instances
           (template_id, record_type, record_id, company_id, status, current_step_order)
           VALUES (?,?,?,?, 'in_progress', 1)""",
        (template_id, record_type, record_id, company_id or ""),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM qms_workflow_instances WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    conn.close()
    return dict(row)


def get_active_instance(record_type: str, record_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM qms_workflow_instances
           WHERE record_type = ? AND record_id = ? AND status = 'in_progress'
           ORDER BY id DESC LIMIT 1""",
        (record_type, record_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_latest_instance(record_type: str, record_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM qms_workflow_instances WHERE record_type = ? AND record_id = ?
           ORDER BY id DESC LIMIT 1""",
        (record_type, record_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_instance(instance_id: int, data: dict) -> None:
    fields = ["status", "current_step_order", "completed_at"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if not updates:
        return
    params.append(instance_id)
    conn = get_connection()
    conn.execute(f"UPDATE qms_workflow_instances SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()


# ── Instance steps ───────────────────────────────────────────────────────────

def create_instance_step(instance_id: int, template_step: dict, *,
                          approval_mode: str = "any", required_quorum: int | None = None) -> dict:
    """`approval_mode`/`required_quorum` are snapshotted onto the instance step
    at creation time (mirrors required_quorum's role in start_instance()) so a
    later change to a document's approval_quorum never retroactively alters a
    review already in progress. Defaults reproduce the pre-quorum 'any one of'
    behaviour exactly — every caller that doesn't pass them is unaffected."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_workflow_instance_steps
           (instance_id, template_step_id, step_order, step_key, step_name, step_type,
            eligible_roles, gate_status, status, approval_mode, required_quorum)
           VALUES (?,?,?,?,?,?,?,?, 'pending', ?, ?)""",
        (
            instance_id, template_step["id"], template_step["step_order"],
            template_step["step_key"], template_step["step_name"], template_step["step_type"],
            template_step["eligible_roles"], template_step["gate_status"],
            approval_mode, required_quorum,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM qms_workflow_instance_steps WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    conn.close()
    return dict(row)


def get_instance_steps(instance_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_workflow_instance_steps WHERE instance_id = ? ORDER BY step_order ASC",
        (instance_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_instance_step(instance_id: int, step_order: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM qms_workflow_instance_steps WHERE instance_id = ? AND step_order = ?",
        (instance_id, step_order),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_instance_step(step_id: int, data: dict) -> None:
    fields = ["status", "decided_by", "decided_at", "comments"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if not updates:
        return
    params.append(step_id)
    conn = get_connection()
    conn.execute(f"UPDATE qms_workflow_instance_steps SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()


# ── Named approvers ──────────────────────────────────────────────────────────

def set_step_approvers(instance_step_id: int, approvers: list[dict]) -> None:
    """Replace the approver list for a step. `approvers` is
    [{"user_id": ..., "display_name": ...}, ...]."""
    conn = get_connection()
    conn.execute("DELETE FROM qms_workflow_step_approvers WHERE instance_step_id = ?", (instance_step_id,))
    for a in approvers:
        conn.execute(
            "INSERT INTO qms_workflow_step_approvers (instance_step_id, user_id, display_name) VALUES (?,?,?)",
            (instance_step_id, a["user_id"], a.get("display_name", "")),
        )
    conn.commit()
    conn.close()


def get_step_approvers(instance_step_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_workflow_step_approvers WHERE instance_step_id = ? ORDER BY id ASC",
        (instance_step_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Quorum votes (Document Control configurable approval quorum) ────────────
# Only written/read for instance steps with approval_mode='quorum' — every
# other step ('any' mode, all of CAPA/Deviation/Change Control today) never
# touches this table. See services/workflow_engine.py's quorum branch of
# decide_step().

def record_vote(instance_step_id: int, user_id: str, decision: str, reason: str, company_id: str | None) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_workflow_step_votes (instance_step_id, user_id, decision, reason, company_id)
           VALUES (?,?,?,?,?)""",
        (instance_step_id, user_id, decision, reason, company_id or ""),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_workflow_step_votes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_votes(instance_step_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_workflow_step_votes WHERE instance_step_id = ? ORDER BY voted_at ASC",
        (instance_step_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_voted(instance_step_id: int, user_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM qms_workflow_step_votes WHERE instance_step_id = ? AND user_id = ?",
        (instance_step_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def clear_votes(instance_step_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM qms_workflow_step_votes WHERE instance_step_id = ?", (instance_step_id,))
    conn.commit()
    conn.close()


# ── Universal Workflow Inbox (Problem 1/7) ───────────────────────────────────
# Purely additive, record_type-agnostic reads for the Inbox: only
# record_type/record_id + step/instance metadata, no module-specific fields.
# Module-aware display data (title, record number, route) is resolved
# separately by services/workflow_registry.py.

def list_my_pending_steps(company_id: str, user_id: str, role: str) -> list[dict]:
    """Every in-progress workflow instance's *current* step, across all
    record_types, where the caller may act on it right now: a named
    approver (approval steps) or holding an eligible role (activity steps).
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT i.record_type, i.record_id, i.id AS instance_id,
               s.id AS step_id, s.step_order, s.step_key, s.step_name,
               s.step_type, s.status,
               COALESCE(
                   (SELECT MAX(decided_at) FROM qms_workflow_instance_steps
                    WHERE instance_id = i.id AND step_order < i.current_step_order
                      AND decided_at != ''),
                   i.started_at
               ) AS pending_since
        FROM qms_workflow_instances i
        JOIN qms_workflow_instance_steps s
          ON s.instance_id = i.id AND s.step_order = i.current_step_order
        WHERE i.status = 'in_progress'
          AND i.company_id = ?
          AND (
              (s.step_type = 'approval' AND EXISTS (
                  SELECT 1 FROM qms_workflow_step_approvers a
                  WHERE a.instance_step_id = s.id AND a.user_id = ?
              ))
              OR
              (s.step_type = 'activity' AND (',' || s.eligible_roles || ',') LIKE ('%,' || ? || ',%'))
          )
        ORDER BY pending_since ASC
        """,
        (company_id, user_id, role),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_recent_decisions(company_id: str, performed_by: str, limit: int = 10) -> list[dict]:
    """Steps this user has decided (any instance status), most recent
    first. Matched by `decided_by` (the signing identity's display name) —
    the only identity recorded on a step; there is no decided_by_user_id
    column (see qms_workflow_instance_steps schema)."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT i.record_type, i.record_id, s.step_order, s.step_key, s.step_name,
               s.status, s.decided_at, s.decided_by, s.comments
        FROM qms_workflow_instance_steps s
        JOIN qms_workflow_instances i ON i.id = s.instance_id
        WHERE i.company_id = ? AND s.decided_by = ? AND s.decided_at != ''
        ORDER BY s.decided_at DESC
        LIMIT ?
        """,
        (company_id, performed_by, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

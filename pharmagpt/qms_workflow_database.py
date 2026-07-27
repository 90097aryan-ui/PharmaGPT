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

def create_instance_step(instance_id: int, template_step: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_workflow_instance_steps
           (instance_id, template_step_id, step_order, step_key, step_name, step_type,
            eligible_roles, gate_status, status)
           VALUES (?,?,?,?,?,?,?,?, 'pending')""",
        (
            instance_id, template_step["id"], template_step["step_order"],
            template_step["step_key"], template_step["step_name"], template_step["step_type"],
            template_step["eligible_roles"], template_step["gate_status"],
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

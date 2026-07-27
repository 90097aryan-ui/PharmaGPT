"""
qms_investigation_database.py — SQLite CRUD for the Investigation Engine
(architecture refactor: Workflow vs. Investigation separation).

Tables (schema in qms_database.QMS_SCHEMA), all polymorphic on
(record_type, record_id) exactly like qms_attachments/qms_comments:
  qms_investigation_evidence          : evidence/documents, review status
  qms_investigation_sop_review        : applicable SOP/spec review checklist
  qms_investigation_interviews        : personnel interviews
  qms_investigation_timeline_events   : timeline builder entries
  qms_investigation_ai_runs           : append-only AI Assistant/Report log
  qms_investigation_root_cause        : Possible/Probable/Confirmed root cause
  qms_investigation_summary           : finalized handoff record into CAPA
  qms_investigation_tasks             : investigative task tracking (Phase 2 Part 1)

Pure CRUD, one connection per call (same style as qms_deviation_database.py).
Business rules (evidence score, lock enforcement, AI orchestration) live in
services/investigation_engine.py — this module never rejects a write itself.
"""

import json
from pharmagpt.database import get_connection


# ── Evidence ─────────────────────────────────────────────────────────────────

def add_evidence(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_investigation_evidence
           (record_type, record_id, category, attachment_id, description, review_status, notes, source, version)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            record_type, record_id, data.get("category", ""), data.get("attachment_id"),
            data.get("description", ""), data.get("review_status", "Pending"), data.get("notes", ""),
            data.get("source", ""), data.get("version", ""),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_evidence WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_evidence(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_investigation_evidence WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_evidence(evidence_id: int, data: dict) -> dict | None:
    fields = ["category", "description", "review_status", "reviewed_by", "reviewed_at", "notes",
              "source", "version", "attachment_id"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    conn = get_connection()
    if updates:
        params.append(evidence_id)
        conn.execute(f"UPDATE qms_investigation_evidence SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_evidence WHERE id = ?", (evidence_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── SOP review ───────────────────────────────────────────────────────────────

def add_sop_review(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_investigation_sop_review
           (record_type, record_id, doc_reference, version, effective_date, relevant_section, review_status, notes)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            record_type, record_id, data.get("doc_reference", ""), data.get("version", ""),
            data.get("effective_date", ""), data.get("relevant_section", ""),
            data.get("review_status", "Pending"), data.get("notes", ""),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_sop_review WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_sop_reviews(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_investigation_sop_review WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_sop_review(sop_review_id: int, data: dict) -> dict | None:
    fields = ["review_status", "reviewed_by", "reviewed_at", "notes"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    conn = get_connection()
    if updates:
        params.append(sop_review_id)
        conn.execute(f"UPDATE qms_investigation_sop_review SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_sop_review WHERE id = ?", (sop_review_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Interviews ───────────────────────────────────────────────────────────────

def add_interview(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_investigation_interviews
           (record_type, record_id, interviewee_name, interviewee_role, interview_date,
            questions_json, answers_json, observation, status, signature, notes, attachment_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record_type, record_id, data.get("interviewee_name", ""), data.get("interviewee_role", ""),
            data.get("interview_date", ""), json.dumps(data.get("questions", [])),
            json.dumps(data.get("answers", [])), data.get("observation", ""),
            data.get("status", "Scheduled"), data.get("signature", ""),
            data.get("notes", ""), data.get("attachment_id"),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_interviews WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _parse_interview(dict(row))


def get_interviews(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_investigation_interviews WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [_parse_interview(dict(r)) for r in rows]


def update_interview(interview_id: int, data: dict) -> dict | None:
    fields = ["interviewee_name", "interviewee_role", "interview_date", "observation", "status", "signature",
              "notes", "attachment_id"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if "questions" in data:
        updates.append("questions_json = ?")
        params.append(json.dumps(data["questions"]))
    if "answers" in data:
        updates.append("answers_json = ?")
        params.append(json.dumps(data["answers"]))
    conn = get_connection()
    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(interview_id)
        conn.execute(f"UPDATE qms_investigation_interviews SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_interviews WHERE id = ?", (interview_id,)).fetchone()
    conn.close()
    return _parse_interview(dict(row)) if row else None


def _parse_interview(d: dict) -> dict:
    d["questions"] = json.loads(d.pop("questions_json", "[]") or "[]")
    d["answers"] = json.loads(d.pop("answers_json", "[]") or "[]")
    return d


# ── Timeline ─────────────────────────────────────────────────────────────────

def add_timeline_event(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_investigation_timeline_events
           (record_type, record_id, event_type, event_datetime, description, source)
           VALUES (?,?,?,?,?,?)""",
        (
            record_type, record_id, data.get("event_type", ""), data.get("event_datetime", ""),
            data.get("description", ""), data.get("source", "manual"),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_timeline_events WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_timeline_events(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM qms_investigation_timeline_events WHERE record_type = ? AND record_id = ?
           ORDER BY event_datetime ASC, created_at ASC""",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── AI runs (append-only) ─────────────────────────────────────────────────────

def add_ai_run(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_investigation_ai_runs
           (record_type, record_id, mode, run_type, prompt_version, model, input_snapshot_json,
            output_json, evidence_references_json, confidence, processing_duration_ms,
            token_usage_json, generated_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record_type, record_id, data.get("mode", "assistant"), data.get("run_type", ""),
            data.get("prompt_version", ""), data.get("model", ""),
            json.dumps(data.get("input_snapshot", {})), json.dumps(data.get("output", {})),
            json.dumps(data.get("evidence_references", [])), data.get("confidence"),
            data.get("processing_duration_ms"),
            json.dumps(data["token_usage"]) if data.get("token_usage") is not None else None,
            data.get("generated_by", ""),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_ai_runs WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _parse_ai_run(dict(row))


def get_ai_runs(record_type: str, record_id: int, mode: str | None = None) -> list[dict]:
    conn = get_connection()
    if mode:
        rows = conn.execute(
            """SELECT * FROM qms_investigation_ai_runs WHERE record_type = ? AND record_id = ? AND mode = ?
               ORDER BY created_at DESC""",
            (record_type, record_id, mode),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM qms_investigation_ai_runs WHERE record_type = ? AND record_id = ? ORDER BY created_at DESC",
            (record_type, record_id),
        ).fetchall()
    conn.close()
    return [_parse_ai_run(dict(r)) for r in rows]


def _parse_ai_run(d: dict) -> dict:
    d["input_snapshot"] = json.loads(d.pop("input_snapshot_json", "{}") or "{}")
    d["output"] = json.loads(d.pop("output_json", "{}") or "{}")
    d["evidence_references"] = json.loads(d.pop("evidence_references_json", "[]") or "[]")
    raw_tokens = d.pop("token_usage_json", None)
    d["token_usage"] = json.loads(raw_tokens) if raw_tokens else None
    return d


# ── Root cause (Possible -> Probable -> Confirmed) ───────────────────────────

def upsert_root_cause(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM qms_investigation_root_cause WHERE record_type = ? AND record_id = ?",
        (record_type, record_id),
    ).fetchone()

    fields = [
        "possible_cause", "possible_cause_source", "probable_cause", "probable_cause_rationale",
        "confidence_level", "confirmed_root_cause", "confirmed_by", "confirmed_at",
    ]
    json_fields = {
        "supporting_evidence_refs": "supporting_evidence_refs_json",
        "alternative_causes": "alternative_causes_json",
    }

    if existing:
        updates, params = [], []
        for f in fields:
            if f in data:
                updates.append(f"{f} = ?")
                params.append(data[f])
        for key, col in json_fields.items():
            if key in data:
                updates.append(f"{col} = ?")
                params.append(json.dumps(data[key]))
        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(existing["id"])
            conn.execute(f"UPDATE qms_investigation_root_cause SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
    else:
        conn.execute(
            """INSERT INTO qms_investigation_root_cause
               (record_type, record_id, possible_cause, possible_cause_source, probable_cause,
                probable_cause_rationale, supporting_evidence_refs_json, confidence_level,
                alternative_causes_json, confirmed_root_cause, confirmed_by, confirmed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record_type, record_id, data.get("possible_cause", ""), data.get("possible_cause_source", ""),
                data.get("probable_cause", ""), data.get("probable_cause_rationale", ""),
                json.dumps(data.get("supporting_evidence_refs", [])), data.get("confidence_level", ""),
                json.dumps(data.get("alternative_causes", [])), data.get("confirmed_root_cause", ""),
                data.get("confirmed_by", ""), data.get("confirmed_at", ""),
            ),
        )
        conn.commit()

    conn.close()
    return get_root_cause(record_type, record_id)


def get_root_cause(record_type: str, record_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM qms_investigation_root_cause WHERE record_type = ? AND record_id = ?",
        (record_type, record_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["supporting_evidence_refs"] = json.loads(d.pop("supporting_evidence_refs_json", "[]") or "[]")
    d["alternative_causes"] = json.loads(d.pop("alternative_causes_json", "[]") or "[]")
    return d


# ── Investigation summary (finalized CAPA handoff) ───────────────────────────

def upsert_summary(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM qms_investigation_summary WHERE record_type = ? AND record_id = ?",
        (record_type, record_id),
    ).fetchone()

    fields = ["summary_text", "root_cause_ref", "finalized_by", "finalized_at"]
    json_fields = {"key_findings": "key_findings_json", "recommended_capa_actions": "recommended_capa_actions_json",
                   "open_questions": "open_questions_json"}

    if existing:
        updates, params = [], []
        for f in fields:
            if f in data:
                updates.append(f"{f} = ?")
                params.append(data[f])
        for key, col in json_fields.items():
            if key in data:
                updates.append(f"{col} = ?")
                params.append(json.dumps(data[key]))
        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(existing["id"])
            conn.execute(f"UPDATE qms_investigation_summary SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
    else:
        conn.execute(
            """INSERT INTO qms_investigation_summary
               (record_type, record_id, summary_text, key_findings_json, root_cause_ref,
                recommended_capa_actions_json, finalized_by, finalized_at, open_questions_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                record_type, record_id, data.get("summary_text", ""),
                json.dumps(data.get("key_findings", [])), data.get("root_cause_ref", ""),
                json.dumps(data.get("recommended_capa_actions", [])),
                data.get("finalized_by", ""), data.get("finalized_at", ""),
                json.dumps(data.get("open_questions", [])),
            ),
        )
        conn.commit()

    conn.close()
    return get_summary(record_type, record_id)


def get_summary(record_type: str, record_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM qms_investigation_summary WHERE record_type = ? AND record_id = ?",
        (record_type, record_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["key_findings"] = json.loads(d.pop("key_findings_json", "[]") or "[]")
    d["recommended_capa_actions"] = json.loads(d.pop("recommended_capa_actions_json", "[]") or "[]")
    d["open_questions"] = json.loads(d.pop("open_questions_json", "[]") or "[]")
    return d


# ── Investigation Tasks ────────────────────────────────────────────────────

def add_task(record_type: str, record_id: int, data: dict) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_investigation_tasks
           (record_type, record_id, title, description, assigned_user, department, priority,
            due_date, status, evidence_attachment_id, comments, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record_type, record_id, data.get("title", ""), data.get("description", ""),
            data.get("assigned_user", ""), data.get("department", ""), data.get("priority", "Medium"),
            data.get("due_date", ""), data.get("status", "Pending"), data.get("evidence_attachment_id"),
            data.get("comments", ""), data.get("created_by", ""),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_tasks(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_investigation_tasks WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task(task_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_investigation_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_task(task_id: int, data: dict) -> dict | None:
    fields = ["title", "description", "assigned_user", "department", "priority", "due_date",
              "status", "completion_date", "evidence_attachment_id", "comments"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    conn = get_connection()
    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(task_id)
        conn.execute(f"UPDATE qms_investigation_tasks SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    row = conn.execute("SELECT * FROM qms_investigation_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

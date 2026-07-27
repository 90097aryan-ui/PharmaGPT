"""
services/investigation_engine.py — Investigation Engine (architecture
refactor: Workflow vs. Investigation separation, PHASE1_REFACTOR_PLAN).

Answers "what work has been done to find the root cause" — evidence, SOP
review, interviews, timeline, AI assistance, root cause, and the final
CAPA-handoff summary. Record-type-agnostic (deviation today; CAPA/Complaint/
OOS/OOT/Audit Finding/Supplier/Validation investigations later reuse this
same module with a different `record_type` string — no engine change).

This is a *service*, not its own exposed API surface (refinement #1): every
business module owns its own `/investigation/*` routes and calls straight
into these functions; there is no standalone Investigation blueprint.

Every state-mutating function takes an explicit `unlocked: bool` that the
caller must have already computed (e.g. via
`workflow_engine.is_unlocked(record_type, record_id, "qa_approval")`) and
raises InvestigationLockedError if False — so a future module's route file
cannot accidentally expose a write by forgetting the check; the engine
itself refuses.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from pharmagpt import qms_investigation_database as idb
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import investigation_prompt as ip
from pharmagpt.services.qms_shared import call_gemini, parse_json_response


class InvestigationLockedError(Exception):
    """Raised when a write is attempted while the Investigation Case is
    locked. Routes catch this and return 423, same as Phase 1's lock."""


def _require_unlocked(unlocked: bool) -> None:
    if not unlocked:
        raise InvestigationLockedError("Investigation Case is locked — complete the pending approval step first")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Evidence ─────────────────────────────────────────────────────────────────

def add_evidence(record_type: str, record_id: int, data: dict, *, unlocked: bool) -> dict:
    _require_unlocked(unlocked)
    return idb.add_evidence(record_type, record_id, data)


def get_evidence(record_type: str, record_id: int) -> list[dict]:
    return idb.get_evidence(record_type, record_id)


def update_evidence(evidence_id: int, data: dict, *, unlocked: bool) -> dict | None:
    _require_unlocked(unlocked)
    return idb.update_evidence(evidence_id, data)


# ── SOP review ───────────────────────────────────────────────────────────────

def add_sop_review(record_type: str, record_id: int, data: dict, *, unlocked: bool) -> dict:
    _require_unlocked(unlocked)
    return idb.add_sop_review(record_type, record_id, data)


def get_sop_reviews(record_type: str, record_id: int) -> list[dict]:
    return idb.get_sop_reviews(record_type, record_id)


def update_sop_review(sop_review_id: int, data: dict, *, unlocked: bool) -> dict | None:
    _require_unlocked(unlocked)
    return idb.update_sop_review(sop_review_id, data)


# ── Interviews ───────────────────────────────────────────────────────────────

def add_interview(record_type: str, record_id: int, data: dict, *, unlocked: bool) -> dict:
    _require_unlocked(unlocked)
    return idb.add_interview(record_type, record_id, data)


def get_interviews(record_type: str, record_id: int) -> list[dict]:
    return idb.get_interviews(record_type, record_id)


def update_interview(interview_id: int, data: dict, *, unlocked: bool) -> dict | None:
    _require_unlocked(unlocked)
    return idb.update_interview(interview_id, data)


# ── Timeline ─────────────────────────────────────────────────────────────────

def add_timeline_event(record_type: str, record_id: int, data: dict, *, unlocked: bool) -> dict:
    _require_unlocked(unlocked)
    return idb.add_timeline_event(record_type, record_id, data)


def get_timeline_events(record_type: str, record_id: int) -> list[dict]:
    return idb.get_timeline_events(record_type, record_id)


# ── Investigation Tasks (Phase 2 Part 1) ─────────────────────────────────────
# Investigative activities, NOT Workflow steps and NOT CAPA actions — a task's
# status is never read by workflow_engine and completing one never advances a
# workflow step. Same lock semantics as every other investigative write.

def add_task(record_type: str, record_id: int, data: dict, *, unlocked: bool) -> dict:
    _require_unlocked(unlocked)
    return idb.add_task(record_type, record_id, data)


def get_tasks(record_type: str, record_id: int) -> list[dict]:
    return idb.get_tasks(record_type, record_id)


def get_task_scoped(task_id: int, record_type: str, record_id: int) -> dict | None:
    """Returns the task only if it actually belongs to (record_type, record_id) —
    routes use this before update_task so a caller can't mutate another
    record's task by guessing its id (same defense-in-depth as tenancy checks
    elsewhere, applied at the investigation-record boundary)."""
    task = idb.get_task(task_id)
    if not task or task["record_type"] != record_type or task["record_id"] != record_id:
        return None
    return task


def update_task(task_id: int, data: dict, *, unlocked: bool) -> dict | None:
    _require_unlocked(unlocked)
    data = dict(data)
    if data.get("status") == "Completed" and not data.get("completion_date"):
        data["completion_date"] = _now()
    return idb.update_task(task_id, data)


# ── AI Assistant / AI Report Generation (refinement #3, #5) ─────────────────

# Required evidence categories / expected timeline event types — shared by
# _evidence_summary() (what the AI is told is missing) and get_dashboard()
# (what the deterministic score counts as missing). One list, two consumers,
# so the AI and the dashboard can never disagree about what "complete" means.
REQUIRED_EVIDENCE_CATEGORIES = (
    "BMR", "BPR", "SOP", "Calibration Certificate", "PM Record", "Cleaning Record",
    "Environmental Monitoring", "Equipment Log", "Validation Report", "Training Record",
)
EXPECTED_TIMELINE_EVENT_TYPES = (
    "Batch", "Machine", "QA", "Maintenance", "Sampling", "Testing",
)


def _evidence_summary(record_type: str, record_id: int) -> dict:
    """Concrete, itemized snapshot of everything gathered so far — not just
    counts — so the AI Assistant/Report can reason about *specific* gaps
    (missing calibration cert, missing training record, which interview is
    still Scheduled, etc.) per Part 6, and so ai_runs.evidence_references_json
    can record exactly which rows backed a given AI run (Part 7 "Traceable")."""
    evidence = idb.get_evidence(record_type, record_id)
    sop_reviews = idb.get_sop_reviews(record_type, record_id)
    interviews = idb.get_interviews(record_type, record_id)
    timeline_events = idb.get_timeline_events(record_type, record_id)

    categories_present = {e["category"] for e in evidence if e["review_status"] == "Reviewed"}
    missing_categories = [c for c in REQUIRED_EVIDENCE_CATEGORIES if c not in categories_present]
    event_types_present = {t["event_type"] for t in timeline_events}

    return {
        "evidence_count": len(evidence),
        "evidence_items": [
            {"category": e["category"], "review_status": e["review_status"], "description": e["description"]}
            for e in evidence
        ],
        "missing_evidence_categories": missing_categories,
        "sop_review_count": len(sop_reviews),
        "sop_reviews": [
            {"doc_reference": s["doc_reference"], "review_status": s["review_status"]} for s in sop_reviews
        ],
        "interview_count": len(interviews),
        "interviews": [
            {"interviewee_name": i["interviewee_name"], "interviewee_role": i["interviewee_role"],
             "status": i["status"]} for i in interviews
        ],
        "timeline_event_count": len(timeline_events),
        "missing_timeline_event_types": [t for t in EXPECTED_TIMELINE_EVENT_TYPES if t not in event_types_present],
        # References every row shown to the model, for evidence_references_json (traceability).
        "_evidence_ids": [e["id"] for e in evidence],
        "_sop_review_ids": [s["id"] for s in sop_reviews],
        "_interview_ids": [i["id"] for i in interviews],
        "_timeline_ids": [t["id"] for t in timeline_events],
    }


def _evidence_references(evidence_summary: dict) -> list[dict]:
    refs = []
    for key, ref_type in (
        ("_evidence_ids", "evidence"), ("_sop_review_ids", "sop_review"),
        ("_interview_ids", "interview"), ("_timeline_ids", "timeline_event"),
    ):
        refs.extend({"type": ref_type, "id": i} for i in evidence_summary.get(key, []))
    return refs


def run_ai_assistant(record_type: str, record_id: int, context: dict, *, question: str = "",
                      generated_by: str, unlocked: bool) -> dict:
    """Interactive, ad-hoc AI analysis — callable any number of times, never
    gates a workflow step (Part 3 of the original redesign spec)."""
    _require_unlocked(unlocked)
    evidence_summary = _evidence_summary(record_type, record_id)
    prompt = ip.build_assistant_prompt(context, evidence_summary, question)

    start = time.monotonic()
    response_text = call_gemini(prompt, temperature=0.3)
    duration_ms = int((time.monotonic() - start) * 1000)

    output = parse_json_response(response_text, default={
        "analysis": ip.INSUFFICIENT_EVIDENCE_STATEMENT, "possible_causes": [],
        "missing_evidence": [], "missing_sop_review": [], "missing_interviews": [],
        "missing_calibration": [], "missing_pm": [], "missing_training": [],
        "contradictions": [], "recommended_next_steps": [],
    })
    possible_causes = output.get("possible_causes") or []
    confidence = possible_causes[0].get("confidence") if possible_causes else None

    return idb.add_ai_run(record_type, record_id, {
        "mode": "assistant", "run_type": "evidence_analysis", "prompt_version": ip.PROMPT_VERSION,
        "model": GEMINI_MODEL, "input_snapshot": {"context": context, "evidence_summary": evidence_summary,
                                                   "question": question},
        "output": output, "evidence_references": _evidence_references(evidence_summary), "confidence": confidence,
        "processing_duration_ms": duration_ms, "token_usage": None, "generated_by": generated_by,
    })


def run_ai_report(record_type: str, record_id: int, context: dict, investigation_data: dict, *,
                   generated_by: str, unlocked: bool) -> dict:
    """Formal investigation report generation — a distinct mode from the
    interactive assistant (refinement #5), also re-runnable any number of
    times and logged the same way (each call is a new, timestamped,
    queryable row in the append-only qms_investigation_ai_runs table — this
    IS the report's version history, per Part 7 "Versioned")."""
    _require_unlocked(unlocked)
    evidence_summary = _evidence_summary(record_type, record_id)
    prompt = ip.build_report_prompt(context, evidence_summary, investigation_data)

    start = time.monotonic()
    response_text = call_gemini(prompt, temperature=0.2)
    duration_ms = int((time.monotonic() - start) * 1000)

    output = parse_json_response(response_text, default={
        "executive_summary": "", "investigation_narrative": "", "evidence_review": "",
        "conclusion": ip.INSUFFICIENT_EVIDENCE_STATEMENT, "confidence": None,
    })

    return idb.add_ai_run(record_type, record_id, {
        "mode": "report_generation", "run_type": "full_report", "prompt_version": ip.PROMPT_VERSION,
        "model": GEMINI_MODEL, "input_snapshot": {"context": context, "evidence_summary": evidence_summary},
        "output": output, "evidence_references": _evidence_references(evidence_summary),
        "confidence": output.get("confidence"),
        "processing_duration_ms": duration_ms, "token_usage": None, "generated_by": generated_by,
    })


def get_ai_history(record_type: str, record_id: int, mode: str | None = None) -> list[dict]:
    return idb.get_ai_runs(record_type, record_id, mode)


# ── Root cause (Possible -> Probable -> Confirmed, refinement #6) ───────────

def save_root_cause(record_type: str, record_id: int, data: dict, *, unlocked: bool) -> dict:
    """AI output (possible_cause) is written by run_ai_assistant/callers
    separately from the investigator's own probable_cause/confirmed_root_cause
    fields — this function never overwrites one with the other; the caller
    decides which fields to set."""
    _require_unlocked(unlocked)
    return idb.upsert_root_cause(record_type, record_id, data)


def get_root_cause(record_type: str, record_id: int) -> dict | None:
    return idb.get_root_cause(record_type, record_id)


# ── Investigation Summary (finalized CAPA handoff, refinement #7) ───────────

def finalize_summary(record_type: str, record_id: int, data: dict, *, finalized_by: str, unlocked: bool) -> dict:
    _require_unlocked(unlocked)
    data = dict(data)
    data["finalized_by"] = finalized_by
    data["finalized_at"] = _now()
    return idb.upsert_summary(record_type, record_id, data)


def get_summary(record_type: str, record_id: int) -> dict | None:
    return idb.get_summary(record_type, record_id)


# ── Evidence Dashboard (refinement #4 — deterministic, never AI-generated) ──
# REQUIRED_EVIDENCE_CATEGORIES / EXPECTED_TIMELINE_EVENT_TYPES are defined once,
# above, and shared with _evidence_summary() so the AI Assistant and this
# rules-based dashboard can never disagree about what "complete" means.

def get_dashboard(record_type: str, record_id: int) -> dict:
    """Rules-based Evidence Dashboard. Every number here is computed from
    stored rows by a fixed formula — no AI call is part of this calculation
    (refinement #4, Part 8/12: AI may advise, AI must never calculate a
    business KPI). Always returns which specific items are missing, never
    just a bare percentage, so the score can't be mistaken for an AI judgment.
    `latest_ai_recommendations` is the one exception — it's a read-only,
    clearly-labelled pass-through of the most recent AI Assistant run's own
    output, never folded into any of the deterministic percentages below."""
    evidence = idb.get_evidence(record_type, record_id)
    sop_reviews = idb.get_sop_reviews(record_type, record_id)
    interviews = idb.get_interviews(record_type, record_id)
    timeline_events = idb.get_timeline_events(record_type, record_id)
    tasks = idb.get_tasks(record_type, record_id)

    categories_present = {e["category"] for e in evidence if e["review_status"] == "Reviewed"}
    missing_categories = [c for c in REQUIRED_EVIDENCE_CATEGORIES if c not in categories_present]
    document_completeness = (
        (len(REQUIRED_EVIDENCE_CATEGORIES) - len(missing_categories)) / len(REQUIRED_EVIDENCE_CATEGORIES)
    )

    sop_clarifications_open = sum(1 for s in sop_reviews if s["review_status"] == "Requires Clarification")
    sop_completeness = (
        sum(1 for s in sop_reviews if s["review_status"] in ("Reviewed", "Not Applicable")) / len(sop_reviews)
        if sop_reviews else 0.0
    )

    interviews_completed = sum(1 for i in interviews if i["status"] == "Completed")
    interview_completeness = interviews_completed / len(interviews) if interviews else 0.0

    event_types_present = {t["event_type"] for t in timeline_events}
    missing_event_types = [t for t in EXPECTED_TIMELINE_EVENT_TYPES if t not in event_types_present]
    timeline_completeness = (
        (len(EXPECTED_TIMELINE_EVENT_TYPES) - len(missing_event_types)) / len(EXPECTED_TIMELINE_EVENT_TYPES)
    )

    tasks_by_status = {"Pending": 0, "In Progress": 0, "Completed": 0, "Cancelled": 0}
    for t in tasks:
        tasks_by_status[t["status"]] = tasks_by_status.get(t["status"], 0) + 1
    outstanding_tasks = tasks_by_status["Pending"] + tasks_by_status["In Progress"]
    # No tasks recorded is 0% task completeness, not 100% — consistent with
    # interview/SOP completeness also being 0.0 when nothing has been recorded
    # yet, so an untouched investigation reads as 0% progress, not inflated.
    task_completeness = (
        (tasks_by_status["Completed"] + tasks_by_status["Cancelled"]) / len(tasks) if tasks else 0.0
    )

    # Equal-weighted average of the four original completeness dimensions —
    # unchanged formula, kept for backward compatibility with existing callers.
    evidence_score = round(
        100 * (document_completeness + sop_completeness + interview_completeness + timeline_completeness) / 4
    )
    # Investigation Progress folds task completion in as a 5th dimension —
    # the new headline number; evidence_score is retained as-is above it.
    investigation_progress_pct = round(
        100 * (document_completeness + sop_completeness + interview_completeness
               + timeline_completeness + task_completeness) / 5
    )

    latest_assistant_run = next(iter(idb.get_ai_runs(record_type, record_id, mode="assistant")), None)
    latest_ai_recommendations = None
    if latest_assistant_run:
        out = latest_assistant_run.get("output") or {}
        latest_ai_recommendations = {
            "source": "AI Assistant (advisory only — not a deterministic calculation)",
            "generated_at": latest_assistant_run.get("created_at"),
            "missing_evidence": out.get("missing_evidence", []),
            "missing_sop_review": out.get("missing_sop_review", []),
            "missing_interviews": out.get("missing_interviews", []),
            "missing_calibration": out.get("missing_calibration", []),
            "missing_pm": out.get("missing_pm", []),
            "missing_training": out.get("missing_training", []),
            "contradictions": out.get("contradictions", []),
            "recommended_next_steps": out.get("recommended_next_steps", []),
        }

    return {
        "evidence_score": evidence_score,
        "evidence_score_basis": "rules-based (document/SOP/interview/timeline completeness, equally weighted)",
        "investigation_progress_pct": investigation_progress_pct,
        "document_completeness_pct": round(document_completeness * 100),
        "missing_evidence_categories": missing_categories,
        "sop_review_completeness_pct": round(sop_completeness * 100),
        "sop_reviews_requiring_clarification": sop_clarifications_open,
        "interview_completeness_pct": round(interview_completeness * 100),
        "interviews_completed": interviews_completed,
        "interviews_total": len(interviews),
        "timeline_completeness_pct": round(timeline_completeness * 100),
        "missing_timeline_event_types": missing_event_types,
        "outstanding_tasks": outstanding_tasks,
        "tasks_by_status": tasks_by_status,
        "tasks_total": len(tasks),
        "latest_ai_recommendations": latest_ai_recommendations,
    }

"""
tests/test_investigation_engine.py — Regression coverage for the
Investigation Engine (services/investigation_engine.py +
qms_investigation_database.py, architecture refactor: Workflow vs.
Investigation separation).

Exercises the engine directly (no Flask routes) against the db_path
fixture's throwaway SQLite database, same style as test_workflow_engine.py.
"""

import pytest

from pharmagpt.services import investigation_engine as inv

RECORD_TYPE = "deviation"
RECORD_ID = 1


@pytest.fixture(autouse=True)
def _app_context():
    """investigation_engine doesn't call audit.log itself, but keep parity
    with test_workflow_engine.py in case a future change adds it."""
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


# ── Lock enforcement ─────────────────────────────────────────────────────────

def test_mutations_refuse_when_locked(db_path):
    with pytest.raises(inv.InvestigationLockedError):
        inv.add_evidence(RECORD_TYPE, RECORD_ID, {"category": "BMR"}, unlocked=False)
    with pytest.raises(inv.InvestigationLockedError):
        inv.add_sop_review(RECORD_TYPE, RECORD_ID, {"doc_reference": "SOP-1"}, unlocked=False)
    with pytest.raises(inv.InvestigationLockedError):
        inv.add_interview(RECORD_TYPE, RECORD_ID, {"interviewee_name": "A"}, unlocked=False)
    with pytest.raises(inv.InvestigationLockedError):
        inv.add_timeline_event(RECORD_TYPE, RECORD_ID, {"event_type": "Batch"}, unlocked=False)
    with pytest.raises(inv.InvestigationLockedError):
        inv.save_root_cause(RECORD_TYPE, RECORD_ID, {"probable_cause": "x"}, unlocked=False)
    with pytest.raises(inv.InvestigationLockedError):
        inv.finalize_summary(RECORD_TYPE, RECORD_ID, {}, finalized_by="QA", unlocked=False)
    with pytest.raises(inv.InvestigationLockedError):
        inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {}, generated_by="QA", unlocked=False)
    with pytest.raises(inv.InvestigationLockedError):
        inv.run_ai_report(RECORD_TYPE, RECORD_ID, {}, {}, generated_by="QA", unlocked=False)


def test_reads_never_require_unlocked(db_path):
    assert inv.get_evidence(RECORD_TYPE, RECORD_ID) == []
    assert inv.get_sop_reviews(RECORD_TYPE, RECORD_ID) == []
    assert inv.get_interviews(RECORD_TYPE, RECORD_ID) == []
    assert inv.get_timeline_events(RECORD_TYPE, RECORD_ID) == []
    assert inv.get_root_cause(RECORD_TYPE, RECORD_ID) is None
    assert inv.get_summary(RECORD_TYPE, RECORD_ID) is None
    assert inv.get_ai_history(RECORD_TYPE, RECORD_ID) == []


# ── Evidence / SOP / interviews / timeline CRUD ──────────────────────────────

def test_evidence_add_and_update(db_path):
    entry = inv.add_evidence(RECORD_TYPE, RECORD_ID, {"category": "BMR", "description": "Batch record"}, unlocked=True)
    assert entry["review_status"] == "Pending"
    updated = inv.update_evidence(entry["id"], {"review_status": "Reviewed", "reviewed_by": "QA"}, unlocked=True)
    assert updated["review_status"] == "Reviewed"
    assert len(inv.get_evidence(RECORD_TYPE, RECORD_ID)) == 1


def test_sop_review_add(db_path):
    entry = inv.add_sop_review(RECORD_TYPE, RECORD_ID, {"doc_reference": "SOP-QA-014", "review_status": "Reviewed"}, unlocked=True)
    assert entry["doc_reference"] == "SOP-QA-014"
    assert len(inv.get_sop_reviews(RECORD_TYPE, RECORD_ID)) == 1


def test_interview_add_with_questions_answers(db_path):
    entry = inv.add_interview(RECORD_TYPE, RECORD_ID, {
        "interviewee_name": "John Operator", "interviewee_role": "Operator",
        "questions": ["What happened?"], "answers": ["The alarm sounded"], "status": "Completed",
    }, unlocked=True)
    assert entry["questions"] == ["What happened?"]
    assert entry["answers"] == ["The alarm sounded"]
    fetched = inv.get_interviews(RECORD_TYPE, RECORD_ID)
    assert fetched[0]["interviewee_name"] == "John Operator"


def test_timeline_events_ordered_by_datetime(db_path):
    inv.add_timeline_event(RECORD_TYPE, RECORD_ID, {"event_type": "Alarm", "event_datetime": "2026-01-02T10:00"}, unlocked=True)
    inv.add_timeline_event(RECORD_TYPE, RECORD_ID, {"event_type": "Batch", "event_datetime": "2026-01-01T08:00"}, unlocked=True)
    events = inv.get_timeline_events(RECORD_TYPE, RECORD_ID)
    assert [e["event_type"] for e in events] == ["Batch", "Alarm"]


# ── Root cause (Possible -> Probable -> Confirmed) ───────────────────────────

def test_root_cause_three_tier_upsert(db_path):
    inv.save_root_cause(RECORD_TYPE, RECORD_ID, {
        "possible_cause": "Loose connection", "possible_cause_source": "ai", "confidence_level": "Medium",
    }, unlocked=True)
    rc = inv.get_root_cause(RECORD_TYPE, RECORD_ID)
    assert rc["possible_cause"] == "Loose connection"
    assert rc["possible_cause_source"] == "ai"
    assert rc["probable_cause"] == ""

    inv.save_root_cause(RECORD_TYPE, RECORD_ID, {
        "probable_cause": "Feeder motor electrical fault", "probable_cause_rationale": "PM-2026-014",
    }, unlocked=True)
    rc = inv.get_root_cause(RECORD_TYPE, RECORD_ID)
    # AI's possible_cause is untouched by setting the investigator's probable_cause.
    assert rc["possible_cause"] == "Loose connection"
    assert rc["probable_cause"] == "Feeder motor electrical fault"

    inv.save_root_cause(RECORD_TYPE, RECORD_ID, {
        "confirmed_root_cause": "Feeder motor electrical fault", "confirmed_by": "QA Head", "confirmed_at": "2026-01-05",
    }, unlocked=True)
    rc = inv.get_root_cause(RECORD_TYPE, RECORD_ID)
    assert rc["confirmed_root_cause"] == "Feeder motor electrical fault"
    assert rc["confirmed_by"] == "QA Head"


# ── AI runs (assistant / report_generation, refinement #3/#5) ───────────────

def test_ai_assistant_run_logs_full_metadata(db_path, monkeypatch):
    monkeypatch.setattr(inv, "call_gemini", lambda prompt, temperature=0.3: '{"analysis": "test", "possible_causes": [{"cause": "x", "confidence": 0.5}]}')
    run = inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {"Title": "Dev"}, question="Why?", generated_by="Investigator", unlocked=True)
    assert run["mode"] == "assistant"
    assert run["run_type"] == "evidence_analysis"
    assert run["prompt_version"]
    assert run["model"]
    assert run["generated_by"] == "Investigator"
    assert run["confidence"] == 0.5
    assert run["processing_duration_ms"] >= 0
    assert run["output"]["analysis"] == "test"
    assert run["token_usage"] is None


def test_ai_report_run_is_a_distinct_mode(db_path, monkeypatch):
    monkeypatch.setattr(inv, "call_gemini", lambda prompt, temperature=0.3: '{"executive_summary": "s", "conclusion": "c", "confidence": 0.8}')
    run = inv.run_ai_report(RECORD_TYPE, RECORD_ID, {}, {}, generated_by="QA", unlocked=True)
    assert run["mode"] == "report_generation"
    assert run["run_type"] == "full_report"

    history_all = inv.get_ai_history(RECORD_TYPE, RECORD_ID)
    history_assistant = inv.get_ai_history(RECORD_TYPE, RECORD_ID, mode="assistant")
    assert len(history_all) == 1
    assert len(history_assistant) == 0


def test_ai_runs_are_append_only_never_overwritten(db_path, monkeypatch):
    monkeypatch.setattr(inv, "call_gemini", lambda prompt, temperature=0.3: '{"analysis": "run"}')
    inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {}, generated_by="A", unlocked=True)
    inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {}, generated_by="B", unlocked=True)
    history = inv.get_ai_history(RECORD_TYPE, RECORD_ID)
    assert len(history) == 2
    assert {h["generated_by"] for h in history} == {"A", "B"}


# ── Investigation Summary (finalized CAPA handoff, refinement #7) ───────────

def test_finalize_summary_records_who_and_when(db_path):
    summary = inv.finalize_summary(RECORD_TYPE, RECORD_ID, {
        "summary_text": "Root cause confirmed", "key_findings": ["Finding 1"],
        "recommended_capa_actions": ["Retrain operator"],
    }, finalized_by="QA Head", unlocked=True)
    assert summary["finalized_by"] == "QA Head"
    assert summary["finalized_at"]
    assert summary["key_findings"] == ["Finding 1"]
    assert inv.get_summary(RECORD_TYPE, RECORD_ID)["summary_text"] == "Root cause confirmed"


# ── Evidence Dashboard (deterministic, refinement #4) ────────────────────────

def test_dashboard_is_zero_with_no_data(db_path):
    dash = inv.get_dashboard(RECORD_TYPE, RECORD_ID)
    assert dash["evidence_score"] == 0
    assert dash["investigation_progress_pct"] == 0
    assert "rules-based" in dash["evidence_score_basis"]
    assert dash["interviews_total"] == 0
    assert dash["outstanding_tasks"] == 0
    assert dash["latest_ai_recommendations"] is None
    assert len(dash["missing_evidence_categories"]) == len(inv.REQUIRED_EVIDENCE_CATEGORIES)


def test_dashboard_score_increases_with_reviewed_evidence(db_path):
    categories = list(inv.REQUIRED_EVIDENCE_CATEGORIES)
    half = categories[:5]
    for category in half:
        inv.add_evidence(RECORD_TYPE, RECORD_ID, {"category": category, "review_status": "Reviewed"}, unlocked=True)
    dash = inv.get_dashboard(RECORD_TYPE, RECORD_ID)
    assert dash["document_completeness_pct"] == 50  # 5 of 10 required categories
    assert dash["missing_evidence_categories"] == categories[5:]
    assert dash["evidence_score"] > 0


# ── Investigation Tasks (Phase 2 Part 1) ─────────────────────────────────────

def test_task_add_and_lock_gating(db_path):
    with pytest.raises(inv.InvestigationLockedError):
        inv.add_task(RECORD_TYPE, RECORD_ID, {"title": "Pull batch record"}, unlocked=False)
    task = inv.add_task(RECORD_TYPE, RECORD_ID, {
        "title": "Pull batch record", "assigned_user": "J. Doe", "department": "QA", "priority": "High",
    }, unlocked=True)
    assert task["status"] == "Pending"
    assert task["priority"] == "High"
    assert len(inv.get_tasks(RECORD_TYPE, RECORD_ID)) == 1


def test_task_completion_stamps_completion_date(db_path):
    task = inv.add_task(RECORD_TYPE, RECORD_ID, {"title": "Interview operator"}, unlocked=True)
    assert task["completion_date"] == ""
    updated = inv.update_task(task["id"], {"status": "Completed"}, unlocked=True)
    assert updated["status"] == "Completed"
    assert updated["completion_date"]

    with pytest.raises(inv.InvestigationLockedError):
        inv.update_task(task["id"], {"status": "Cancelled"}, unlocked=False)


def test_task_scoped_lookup_rejects_wrong_record(db_path):
    task = inv.add_task(RECORD_TYPE, RECORD_ID, {"title": "x"}, unlocked=True)
    assert inv.get_task_scoped(task["id"], RECORD_TYPE, RECORD_ID) is not None
    assert inv.get_task_scoped(task["id"], RECORD_TYPE, RECORD_ID + 1) is None
    assert inv.get_task_scoped(task["id"], "capa", RECORD_ID) is None


def test_task_never_advances_workflow(db_path):
    """Completing a task must not touch workflow_engine/qms_deviations.status at all —
    Part 1: 'Tasks do not automatically advance workflow'. Since add_task/update_task
    never import or call workflow_engine, this is enforced structurally; this test
    just confirms updating a task to Completed doesn't raise or require any workflow
    state to exist for RECORD_ID (no deviation row exists in this test DB at all)."""
    task = inv.add_task(RECORD_TYPE, RECORD_ID, {"title": "x"}, unlocked=True)
    inv.update_task(task["id"], {"status": "Completed"}, unlocked=True)  # no workflow row needed


# ── Widened Evidence / Interview fields (Phase 2 Parts 2/4) ─────────────────

def test_evidence_source_and_version_fields(db_path):
    entry = inv.add_evidence(RECORD_TYPE, RECORD_ID, {
        "category": "Calibration Certificate", "source": "LIMS export", "version": "Rev 2",
    }, unlocked=True)
    assert entry["source"] == "LIMS export"
    assert entry["version"] == "Rev 2"
    updated = inv.update_evidence(entry["id"], {"version": "Rev 3"}, unlocked=True)
    assert updated["version"] == "Rev 3"


def test_interview_notes_and_attachment_fields(db_path):
    entry = inv.add_interview(RECORD_TYPE, RECORD_ID, {
        "interviewee_name": "J. Doe", "observation": "Saw the alarm", "notes": "Seemed uncertain about timing",
    }, unlocked=True)
    assert entry["observation"] == "Saw the alarm"
    assert entry["notes"] == "Seemed uncertain about timing"
    assert entry["attachment_id"] is None


# ── Investigation Summary open_questions (Phase 2 Part 9) ───────────────────

def test_summary_open_questions_round_trip(db_path):
    summary = inv.finalize_summary(RECORD_TYPE, RECORD_ID, {
        "summary_text": "x", "open_questions": ["Was the calibration cert current?"],
    }, finalized_by="QA Head", unlocked=True)
    assert summary["open_questions"] == ["Was the calibration cert current?"]
    assert inv.get_summary(RECORD_TYPE, RECORD_ID)["open_questions"] == ["Was the calibration cert current?"]


# ── AI Quality Rules (Phase 2 Parts 6/7/12) ──────────────────────────────────

def test_ai_assistant_evidence_summary_is_itemized_not_just_counts(db_path):
    inv.add_evidence(RECORD_TYPE, RECORD_ID, {"category": "BMR", "review_status": "Reviewed"}, unlocked=True)
    summary = inv._evidence_summary(RECORD_TYPE, RECORD_ID)
    assert summary["evidence_items"] == [{"category": "BMR", "review_status": "Reviewed", "description": ""}]
    assert "PM Record" in summary["missing_evidence_categories"]
    assert summary["_evidence_ids"]


def test_ai_assistant_run_populates_evidence_references_for_traceability(db_path, monkeypatch):
    inv.add_evidence(RECORD_TYPE, RECORD_ID, {"category": "BMR"}, unlocked=True)
    inv.add_sop_review(RECORD_TYPE, RECORD_ID, {"doc_reference": "SOP-1"}, unlocked=True)
    monkeypatch.setattr(inv, "call_gemini", lambda prompt, temperature=0.3: '{"analysis": "test"}')
    run = inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {}, generated_by="Investigator", unlocked=True)
    ref_types = {r["type"] for r in run["evidence_references"]}
    assert "evidence" in ref_types
    assert "sop_review" in ref_types


def test_ai_refusal_statement_flows_through_when_model_says_insufficient(db_path, monkeypatch):
    from pharmagpt.prompts import investigation_prompt as ip
    monkeypatch.setattr(
        inv, "call_gemini",
        lambda prompt, temperature=0.3: f'{{"analysis": "{ip.INSUFFICIENT_EVIDENCE_STATEMENT}", "possible_causes": []}}',
    )
    run = inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {}, generated_by="Investigator", unlocked=True)
    assert run["output"]["analysis"] == "Unable to determine root cause. Additional evidence is required."


def test_ai_assistant_unparseable_response_defaults_to_refusal_statement(db_path, monkeypatch):
    from pharmagpt.prompts import investigation_prompt as ip
    monkeypatch.setattr(inv, "call_gemini", lambda prompt, temperature=0.3: "not json")
    run = inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {}, generated_by="Investigator", unlocked=True)
    assert run["output"]["analysis"] == ip.INSUFFICIENT_EVIDENCE_STATEMENT


def test_ai_report_unparseable_response_defaults_to_refusal_statement(db_path, monkeypatch):
    from pharmagpt.prompts import investigation_prompt as ip
    monkeypatch.setattr(inv, "call_gemini", lambda prompt, temperature=0.2: "not json")
    run = inv.run_ai_report(RECORD_TYPE, RECORD_ID, {}, {}, generated_by="QA", unlocked=True)
    assert run["output"]["conclusion"] == ip.INSUFFICIENT_EVIDENCE_STATEMENT


def test_never_invent_rules_and_refusal_statement_are_in_both_prompts(db_path):
    from pharmagpt.prompts import investigation_prompt as ip
    assistant_prompt = ip.build_assistant_prompt({"Title": "Dev"}, inv._evidence_summary("deviation", 999))
    report_prompt = ip.build_report_prompt({"Title": "Dev"}, inv._evidence_summary("deviation", 999), {})
    for prompt in (assistant_prompt, report_prompt):
        assert "never invent" in prompt.lower()
        assert ip.INSUFFICIENT_EVIDENCE_STATEMENT in prompt


# ── Dashboard: tasks + AI recommendations (Phase 2 Part 10) ─────────────────

def test_dashboard_reflects_outstanding_tasks(db_path):
    t1 = inv.add_task(RECORD_TYPE, RECORD_ID, {"title": "a"}, unlocked=True)
    inv.add_task(RECORD_TYPE, RECORD_ID, {"title": "b"}, unlocked=True)
    dash = inv.get_dashboard(RECORD_TYPE, RECORD_ID)
    assert dash["outstanding_tasks"] == 2
    assert dash["tasks_total"] == 2
    inv.update_task(t1["id"], {"status": "Completed"}, unlocked=True)
    dash = inv.get_dashboard(RECORD_TYPE, RECORD_ID)
    assert dash["outstanding_tasks"] == 1
    assert dash["tasks_by_status"]["Completed"] == 1


def test_dashboard_surfaces_latest_ai_assistant_recommendations_as_advisory_only(db_path, monkeypatch):
    monkeypatch.setattr(
        inv, "call_gemini",
        lambda prompt, temperature=0.3: '{"analysis": "x", "missing_calibration": ["Pump P-101 cert"], "missing_training": []}',
    )
    inv.run_ai_assistant(RECORD_TYPE, RECORD_ID, {}, generated_by="Investigator", unlocked=True)
    dash = inv.get_dashboard(RECORD_TYPE, RECORD_ID)
    rec = dash["latest_ai_recommendations"]
    assert rec is not None
    assert rec["missing_calibration"] == ["Pump P-101 cert"]
    assert "advisory" in rec["source"].lower()


def test_dashboard_never_calls_ai_even_with_tasks_and_ai_history(db_path, monkeypatch):
    """Extends the existing determinism guarantee to the new dashboard fields —
    get_dashboard() must still never call the AI itself (Part 8/12: AI may
    advise, AI must never calculate a business KPI); it may only *read* a
    previously-stored AI run via idb.get_ai_runs (no model call)."""
    def _fail(*a, **kw):
        raise AssertionError("get_dashboard must never call the AI")
    monkeypatch.setattr(inv, "call_gemini", _fail)
    inv.add_task(RECORD_TYPE, RECORD_ID, {"title": "x"}, unlocked=True)
    inv.get_dashboard(RECORD_TYPE, RECORD_ID)  # must not raise


def test_dashboard_never_calls_ai(db_path, monkeypatch):
    """Evidence Score must be deterministic — never touches call_gemini."""
    def _fail(*a, **kw):
        raise AssertionError("get_dashboard must never call the AI")
    monkeypatch.setattr(inv, "call_gemini", _fail)
    inv.add_evidence(RECORD_TYPE, RECORD_ID, {"category": "BMR", "review_status": "Reviewed"}, unlocked=True)
    inv.get_dashboard(RECORD_TYPE, RECORD_ID)  # must not raise

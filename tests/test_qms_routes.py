"""
tests/test_qms_routes.py — Flask test-client integration tests for the QMS
Phase 1 API surface: Document Control, Deviation Management, CAPA, and the
shared endpoints (attachments/comments/audit-trail/approval/dashboard/meta).

AI-backed endpoints are exercised with pharmagpt.services.qms_shared.call_gemini
and stream_gemini monkeypatched to canned responses — the real Gemini pipeline
(SSE streaming, prompt construction, JSON parsing, DB persistence) is already
verified manually end-to-end against the live API; these tests only need to
prove the Flask routes and DB writes work, deterministically and without a
network dependency.
"""

import json
import io

import pytest


@pytest.fixture()
def mock_gemini(monkeypatch):
    """Monkeypatch call_gemini/stream_gemini across all three QMS services to
    return deterministic canned output instead of calling the real API.

    Each service does `from qms_shared import call_gemini`, which binds its
    own local name — patching qms_shared.call_gemini alone would not affect
    those already-bound references, so every consuming module is patched too.
    """
    import pharmagpt.services.qms_shared as shared
    import pharmagpt.services.qms_document_service as doc_svc
    import pharmagpt.services.qms_deviation_service as dev_svc
    import pharmagpt.services.qms_capa_service as capa_svc
    import pharmagpt.services.qms_change_control_service as cc_svc
    import pharmagpt.services.investigation_engine as inv_engine
    import pharmagpt.routes.qms_documents as doc_routes

    def _fake_call_gemini(prompt, temperature=0.3):
        return "canned response"

    def _fake_stream_gemini(prompt, temperature=0.4):
        yield "# Generated Title\n"
        yield "Some generated markdown content."

    for mod in (shared, doc_svc, dev_svc, capa_svc, cc_svc, inv_engine):
        monkeypatch.setattr(mod, "call_gemini", _fake_call_gemini)
    monkeypatch.setattr(shared, "stream_gemini", _fake_stream_gemini)
    monkeypatch.setattr(doc_routes, "stream_gemini", _fake_stream_gemini)
    return shared


# ── Shared: dashboard / meta ────────────────────────────────────────────────

def test_meta_endpoint(client):
    r = client.get("/qms/meta")
    assert r.status_code == 200
    data = r.get_json()
    assert "SOP" in data["document_types"]
    assert "Open" in data["capa_statuses"]
    assert "Emergency" in data["change_types"]
    assert "Closed" in data["change_control_statuses"]


def test_dashboard_endpoint_empty(client):
    r = client.get("/qms/dashboard")
    assert r.status_code == 200
    summary = r.get_json()["summary"]
    assert summary["total_documents"] == 0
    assert summary["open_deviations"] == 0
    assert summary["open_capas"] == 0
    assert summary["total_changes"] == 0
    assert summary["open_changes"] == 0
    assert summary["pending_change_approvals"] == 0
    assert summary["emergency_changes"] == 0


# ── Document Control ─────────────────────────────────────────────────────────

def test_document_crud_lifecycle(client):
    r = client.post("/qms/documents", json={"doc_type": "SOP", "title": "Cleaning SOP", "department": "QA"})
    assert r.status_code == 201
    doc = r.get_json()
    assert doc["doc_number"] == "SOP-QA-0001"
    did = doc["id"]

    r = client.get("/qms/documents")
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    r = client.get(f"/qms/documents/{did}")
    assert r.status_code == 200

    r = client.put(f"/qms/documents/{did}", json={"content": "# Content"})
    assert r.status_code == 200
    assert r.get_json()["content"] == "# Content"

    r = client.delete(f"/qms/documents/{did}")
    assert r.status_code == 200
    assert client.get(f"/qms/documents/{did}").status_code == 404


def test_document_create_requires_title(client):
    r = client.post("/qms/documents", json={"doc_type": "SOP"})
    assert r.status_code == 400


def test_document_approval_transitions_status(client):
    # The /approval endpoint is now a compatibility wrapper over
    # services/workflow_engine.py (DOCUMENT_WORKFLOW_V1, 3 steps): one call
    # decides exactly one real workflow step — see
    # routes/qms_documents.py::submit_approval docstring. The first call
    # both starts the instance (auto-completing "Submitted for Review") and
    # decides the now-current "Under Review" step in the same request; since
    # "Under Review" is the second-to-last step, the display stays "Under
    # Review" until the final "Made Effective" step is itself decided.
    doc = client.post("/qms/documents", json={"title": "Doc"}).get_json()
    did = doc["id"]

    r = client.post(f"/qms/documents/{did}/approval", json={"action": "Submitted for Review", "performed_by": "J Doe"})
    assert r.status_code == 201
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Under Review"

    client.post(f"/qms/documents/{did}/approval", json={"action": "Approved", "performed_by": "M Shah"})
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Effective"


def test_document_versions_training_distribution_routes(client):
    doc = client.post("/qms/documents", json={"title": "Doc"}).get_json()
    did = doc["id"]

    r = client.post(f"/qms/documents/{did}/versions", json={"version": "1.1", "change_summary": "Update"})
    assert r.status_code == 201
    assert client.get(f"/qms/documents/{did}/versions").get_json()[0]["version"] == "1.0"

    r = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "A Kumar"})
    assert r.status_code == 201
    training_id = r.get_json()["id"]
    r = client.put(f"/qms/documents/training/{training_id}", json={"training_status": "Completed", "training_date": "2026-07-01"})
    assert r.get_json()["training_status"] == "Completed"

    r = client.post(f"/qms/documents/{did}/distribution", json={"distributed_to": "Production"})
    assert r.status_code == 201
    dist_id = r.get_json()["id"]
    r = client.post(f"/qms/documents/distribution/{dist_id}/acknowledge", json={"acknowledged_date": "2026-07-02"})
    assert r.get_json()["acknowledged"] == 1


def test_document_ai_review_uses_mocked_gemini(client, mock_gemini, monkeypatch):
    import pharmagpt.services.qms_document_service as doc_svc
    monkey_json = json.dumps({
        "completeness_score": 80, "regulatory_compliance_score": 75, "clarity_score": 85,
        "overall_score": 80, "critical_findings": [], "missing_elements": [],
        "suggested_improvements": [], "reviewer_comments": "Good", "recommendation": "Approve",
    })
    monkeypatch.setattr(doc_svc, "call_gemini", lambda prompt, temperature=0.3: monkey_json)

    doc = client.post("/qms/documents", json={"title": "Doc", "content": "# Some content"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/review")
    assert r.status_code == 200
    review = r.get_json()
    assert review["overall_score"] == 80
    assert client.get(f"/qms/documents/{doc['id']}").get_json()["ai_review_data"]["recommendation"] == "Approve"


def test_document_generate_draft_streams_and_persists(client, mock_gemini):
    doc = client.post("/qms/documents", json={"title": "Doc"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    assert r.status_code == 200
    assert r.mimetype == "text/event-stream"
    body = r.get_data(as_text=True)
    assert "Generated Title" in body

    saved = client.get(f"/qms/documents/{doc['id']}").get_json()
    assert "Generated Title" in saved["content"]


def test_document_docx_export(client):
    doc = client.post("/qms/documents", json={"title": "Doc", "content": "# Content"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/export/docx")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(r.data) > 1000


# ── Deviation Management ─────────────────────────────────────────────────────

_FIXED_USER_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py::_TEST_TENANT.user_id


def _dev_configure_all_approvers(client, did, user_id=_FIXED_USER_ID, display_name="Test User"):
    """Fill in every named-approval step's approver via the Workflow Builder
    (the only place they can be set for deviations — there is no runtime
    "Assign Approver" action): the Review chain plus the fixed CAPA-phase
    steps (QA Review, Final Approval)."""
    steps = client.get(f"/qms/deviations/{did}/workflow-builder").get_json()["steps"]
    for s in steps:
        s["approver_user_id"] = user_id
        s["approver_display_name"] = display_name
    capa_phase = {
        "qa_review_approver_user_id": user_id, "qa_review_approver_display_name": display_name,
        "final_approval_approver_user_id": user_id, "final_approval_approver_display_name": display_name,
    }
    client.put(f"/qms/deviations/{did}/workflow-builder", json={"steps": steps, "capa_phase": capa_phase})


def _dev_reach_qa_approval(client, did):
    """Drive a deviation from Draft through the Initiator Manager Review ->
    QA Manager Review -> QA Approval gate, using the fixture's single fixed
    tenant (role=company_admin) as the named approver for every step —
    that role is eligible for all three per DEVIATION_LIFECYCLE_V2 (steps
    2/3/4, displayed as the "Review" phase). Approvers (including the
    CAPA-phase steps not reached yet) are configured via the Workflow
    Builder before submission and are auto-assigned at /workflow/start."""
    _dev_configure_all_approvers(client, did)

    r = client.post(f"/qms/deviations/{did}/workflow/start")
    assert r.status_code == 201, r.get_json()
    for step_order in (2, 3, 4):
        r = client.post(f"/qms/deviations/{did}/workflow/steps/{step_order}/decide", json={"decision": "approve"})
        assert r.status_code == 200, r.get_json()


def test_deviation_crud_lifecycle(client):
    r = client.post("/qms/deviations", json={"title": "Temp excursion", "deviation_type": "Major"})
    assert r.status_code == 201
    dev = r.get_json()
    assert dev["status"] == "Draft"
    did = dev["id"]

    assert client.get("/qms/deviations").status_code == 200
    r = client.put(f"/qms/deviations/{did}", json={"risk_level": "High"})
    assert r.get_json()["risk_level"] == "High"

    r = client.delete(f"/qms/deviations/{did}")
    assert r.status_code == 200


def test_deviation_investigation_case_locked_until_qa_approval(client, mock_gemini):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    r = client.post(f"/qms/deviations/{dev['id']}/investigation/ai/assistant", json={})
    assert r.status_code == 423
    r = client.post(f"/qms/deviations/{dev['id']}/investigation/evidence", json={"category": "BMR"})
    assert r.status_code == 423
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()["investigation_unlocked"] is False


def test_deviation_investigation_ai_assistant_and_report(client, mock_gemini, monkeypatch):
    import pharmagpt.services.investigation_engine as inv_engine
    canned = json.dumps({
        "analysis": "Evidence points to a maintenance gap", "possible_causes": [{"cause": "Loose connection", "confidence": 0.7}],
        "missing_evidence": [], "recommended_next_steps": ["Review PM records"],
    })
    monkeypatch.setattr(inv_engine, "call_gemini", lambda prompt, temperature=0.3: canned)

    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    _dev_reach_qa_approval(client, dev["id"])
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()["investigation_unlocked"] is True
    # QA Approval just cleared -> the record now sits at the next step, Investigation.
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()["status"] == "Investigation"

    r = client.post(f"/qms/deviations/{dev['id']}/investigation/ai/assistant", json={"question": "What happened?"})
    assert r.status_code == 201
    run = r.get_json()
    assert run["mode"] == "assistant"
    assert run["output"]["analysis"] == "Evidence points to a maintenance gap"
    assert run["model"]
    assert run["prompt_version"]

    r = client.post(f"/qms/deviations/{dev['id']}/investigation/ai/report", json={})
    assert r.status_code == 201
    assert r.get_json()["mode"] == "report_generation"

    history = client.get(f"/qms/deviations/{dev['id']}/investigation/ai/history").get_json()
    assert len(history) == 2
    assistant_only = client.get(f"/qms/deviations/{dev['id']}/investigation/ai/history?mode=assistant").get_json()
    assert len(assistant_only) == 1


def test_deviation_investigation_tasks_lock_and_crud(client, mock_gemini):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]

    # Locked before qa_approval — same 423 pattern as evidence/interviews.
    r = client.post(f"/qms/deviations/{did}/investigation/tasks", json={"title": "Pull batch record"})
    assert r.status_code == 423

    _dev_reach_qa_approval(client, did)

    r = client.post(f"/qms/deviations/{did}/investigation/tasks", json={
        "title": "Pull batch record", "assigned_user": "J. Doe", "department": "QA", "priority": "High",
    })
    assert r.status_code == 201
    task = r.get_json()
    assert task["status"] == "Pending"

    listed = client.get(f"/qms/deviations/{did}/investigation/tasks").get_json()
    assert len(listed) == 1

    r = client.put(f"/qms/deviations/{did}/investigation/tasks/{task['id']}", json={"status": "Completed"})
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["status"] == "Completed"
    assert updated["completion_date"]

    # Audit trail rolls up to the deviation, same as evidence/interviews.
    audit = client.get(f"/qms/deviation/{did}/audit-trail").get_json()
    actions = [a["action"] for a in audit]
    assert "Investigation task added" in actions
    assert "Investigation task updated" in actions


def test_deviation_investigation_tasks_tenant_and_record_scoping(client, mock_gemini):
    dev1 = client.post("/qms/deviations", json={"title": "Dev1"}).get_json()
    dev2 = client.post("/qms/deviations", json={"title": "Dev2"}).get_json()
    _dev_reach_qa_approval(client, dev1["id"])
    _dev_reach_qa_approval(client, dev2["id"])

    task = client.post(f"/qms/deviations/{dev1['id']}/investigation/tasks", json={"title": "x"}).get_json()

    # A task belonging to dev1 cannot be updated through dev2's URL.
    r = client.put(f"/qms/deviations/{dev2['id']}/investigation/tasks/{task['id']}", json={"status": "Completed"})
    assert r.status_code == 404

    # Nonexistent deviation entirely.
    r = client.get("/qms/deviations/999999/investigation/tasks")
    assert r.status_code == 404


def test_deviation_investigation_knowledge_base(client, mock_gemini, monkeypatch):
    import pharmagpt.routes.qms_deviations as dev_routes
    from pharmagpt.services.retrieval_engine import RetrievalResult

    def _fake_retrieve_context(**kwargs):
        return RetrievalResult(
            context_text="...", chunks=[], found=True, query_terms=["deviation"],
            sources=[{"id": 1, "name": "SOP-QA-014 Cleaning Validation", "doc_type": "KB - SOP"}],
        )
    monkeypatch.setattr(dev_routes.retrieval_engine, "retrieve_context", _fake_retrieve_context)

    dev = client.post("/qms/deviations", json={"title": "Dev", "product": "Amoxicillin"}).get_json()
    did = dev["id"]
    _dev_reach_qa_approval(client, did)

    r = client.get(f"/qms/deviations/{did}/investigation/knowledge-base")
    assert r.status_code == 200
    kb = r.get_json()
    assert kb["kb_suggestions"] == [{"doc_reference": "SOP-QA-014 Cleaning Validation", "source_type": "KB - SOP"}]
    assert kb["previous_deviations"] == []  # only dev itself exists, excluded from its own suggestions
    assert kb["previous_capas"] == []
    assert kb["equipment_history"] == []

    r = client.post(f"/qms/deviations/{did}/investigation/knowledge-base/accept-sop",
                     json={"doc_reference": "SOP-QA-014 Cleaning Validation"})
    assert r.status_code == 201
    entry = r.get_json()
    assert entry["doc_reference"] == "SOP-QA-014 Cleaning Validation"
    assert entry["notes"] == "Auto-retrieved from Knowledge Base"
    assert len(client.get(f"/qms/deviations/{did}/investigation/sop-review").get_json()) == 1


def test_deviation_investigation_knowledge_base_finds_related_deviations(client, mock_gemini, monkeypatch):
    import pharmagpt.routes.qms_deviations as dev_routes
    from pharmagpt.services.retrieval_engine import RetrievalResult

    monkeypatch.setattr(dev_routes.retrieval_engine, "retrieve_context",
                         lambda **kwargs: RetrievalResult(context_text="", chunks=[], sources=[], found=False, query_terms=[]))

    dev1 = client.post("/qms/deviations", json={"title": "Dev1", "product": "Amoxicillin"}).get_json()
    dev2 = client.post("/qms/deviations", json={"title": "Dev2", "product": "Amoxicillin"}).get_json()
    _dev_reach_qa_approval(client, dev2["id"])

    kb = client.get(f"/qms/deviations/{dev2['id']}/investigation/knowledge-base").get_json()
    assert [d["id"] for d in kb["previous_deviations"]] == [dev1["id"]]


def test_deviation_impact_and_capa_link(client, mock_gemini):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    r = client.post(f"/qms/deviations/{dev['id']}/impact", json={"impact_area": "Product Quality", "risk_level": "Low"})
    assert r.status_code == 201
    assert len(client.get(f"/qms/deviations/{dev['id']}/impact").get_json()) == 1

    capa = client.post("/qms/capa", json={"title": "CAPA", "capa_source": "Deviation"}).get_json()
    r = client.post(f"/qms/deviations/{dev['id']}/link-capa", json={"capa_id": capa["id"]})
    assert r.status_code == 201

    linked = client.get(f"/qms/deviations/{dev['id']}/capas").get_json()
    assert linked[0]["id"] == capa["id"]

    reverse = client.get(f"/qms/capa/{capa['id']}/deviations").get_json()
    assert reverse[0]["id"] == dev["id"]


def test_deviation_workflow_named_approver_gate_end_to_end(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]

    # Draft has no workflow instance yet.
    wf = client.get(f"/qms/deviations/{did}/workflow").get_json()
    assert wf["instance"] is None
    assert wf["current_phase"] == "Draft"

    _dev_reach_qa_approval(client, did)
    assert client.get(f"/qms/deviations/{did}").get_json()["status"] == "Investigation"
    wf = client.get(f"/qms/deviations/{did}/workflow").get_json()
    assert wf["current_phase"] == "Investigation"
    assert wf["progress_pct"] == round(100 * 4 / 9)

    # Step 5 ("Investigation") is a single activity step under DEVIATION_LIFECYCLE_V2 —
    # the investigator declares the investigation complete and moves to CAPA.
    r = client.post(f"/qms/deviations/{did}/workflow/steps/5/decide", json={"decision": "advance"})
    assert r.status_code == 200, r.get_json()
    assert client.get(f"/qms/deviations/{did}").get_json()["status"] == "CAPA"

    # QA Review (6) and Final Approval (7) are named-approval gates grouped
    # under "CAPA" — already assigned at /workflow/start via the Workflow
    # Builder's capa_phase configuration (_dev_reach_qa_approval above), no
    # runtime assignment needed here.
    for step_order in (6, 7):
        r = client.post(f"/qms/deviations/{did}/workflow/steps/{step_order}/decide", json={"decision": "approve"})
        assert r.status_code == 200, r.get_json()

    r = client.post(f"/qms/deviations/{did}/workflow/steps/8/decide", json={"decision": "advance"})
    assert r.status_code == 200
    assert client.get(f"/qms/deviations/{did}").get_json()["status"] == "Effectiveness Check"

    r = client.post(f"/qms/deviations/{did}/workflow/steps/9/decide", json={"decision": "advance"})
    assert r.status_code == 200
    final = client.get(f"/qms/deviations/{did}").get_json()
    assert final["status"] == "Closed"

    # Closed deviations are immutable, same guarantee as before this refactor.
    r = client.put(f"/qms/deviations/{did}", json={"risk_level": "High"})
    assert r.status_code == 409


def test_deviation_docx_export(client):
    dev = client.post("/qms/deviations", json={"title": "Dev", "description": "Something happened"}).get_json()
    r = client.post(f"/qms/deviations/{dev['id']}/export/docx")
    assert r.status_code == 200
    assert len(r.data) > 1000


# ── CAPA ───────────────────────────────────────────────────────────────────────

def test_capa_crud_lifecycle(client):
    r = client.post("/qms/capa", json={"title": "CAPA A"})
    assert r.status_code == 201
    capa = r.get_json()
    assert capa["status"] == "Open"
    cid = capa["id"]

    assert client.get("/qms/capa").status_code == 200
    r = client.put(f"/qms/capa/{cid}", json={"root_cause": "Root cause text"})
    assert r.get_json()["root_cause"] == "Root cause text"

    assert client.delete(f"/qms/capa/{cid}").status_code == 200


def test_capa_actions_and_escalation(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]

    r = client.post(f"/qms/capa/{cid}/actions", json={"action_type": "Corrective", "description": "Fix", "owner": "QA"})
    assert r.status_code == 201
    action = r.get_json()

    r = client.post(f"/qms/capa/actions/{action['id']}/escalate", json={"escalated_to": "QA Head", "escalated_date": "2026-07-20"})
    assert r.get_json()["escalated"] == 1

    actions = client.get(f"/qms/capa/{cid}/actions").get_json()
    assert len(actions) == 1


def test_capa_effectiveness_route(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    r = client.post(f"/qms/capa/{capa['id']}/effectiveness", json={"check_criterion": "No recurrence", "method": "Trend"})
    assert r.status_code == 201
    assert len(client.get(f"/qms/capa/{capa['id']}/effectiveness").get_json()) == 1


def test_capa_approval_status_map(client):
    # The /approval endpoint is now a compatibility wrapper over
    # services/workflow_engine.py (CAPA_WORKFLOW_V1): one call decides
    # exactly one real workflow step — see
    # routes/qms_capa.py::submit_approval docstring. The first call both
    # starts the instance (auto-completing "CAPA Opened") and decides the
    # now-current "Root Cause Analysis" step, landing on "CA Planned".
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]

    client.post(f"/qms/capa/{cid}/approval", json={"action": "Root Cause Analysis Started", "performed_by": "A"})
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "CA Planned"

    for action in ["Preventive Actions Planned", "Implementation Started",
                   "Effectiveness Check Started", "Submitted for QA Review", "Closed"]:
        client.post(f"/qms/capa/{cid}/approval", json={"action": action, "performed_by": "B"})
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "QA Review"

    client.post(f"/qms/capa/{cid}/approval", json={"action": "Closed", "performed_by": "B"})
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Closed"


def test_capa_trend_summary_uses_mocked_gemini(client, mock_gemini):
    r = client.get("/qms/capa/trend-summary")
    assert r.status_code == 200
    assert "summary" in r.get_json()


def test_capa_docx_export(client):
    capa = client.post("/qms/capa", json={"title": "CAPA", "problem_statement": "Issue"}).get_json()
    r = client.post(f"/qms/capa/{capa['id']}/export/docx")
    assert r.status_code == 200
    assert len(r.data) > 1000


# ── Change Control ───────────────────────────────────────────────────────────

def test_change_control_crud_lifecycle(client):
    r = client.post("/qms/change-control", json={"title": "Upgrade HVAC firmware", "change_type": "Major"})
    assert r.status_code == 201
    cc = r.get_json()
    assert cc["cc_number"].startswith("CC-")
    assert cc["status"] == "Draft"
    cc_id = cc["id"]

    assert client.get("/qms/change-control").status_code == 200
    r = client.put(f"/qms/change-control/{cc_id}", json={"risk_level": "Medium"})
    assert r.get_json()["risk_level"] == "Medium"

    r = client.delete(f"/qms/change-control/{cc_id}")
    assert r.status_code == 200
    assert client.get(f"/qms/change-control/{cc_id}").status_code == 404


def test_change_control_create_requires_title(client):
    r = client.post("/qms/change-control", json={"change_type": "Minor"})
    assert r.status_code == 400


def test_change_control_impact_ai_route(client, mock_gemini, monkeypatch):
    import pharmagpt.services.qms_change_control_service as cc_svc
    import json as _json
    canned = _json.dumps([
        {"impact_area": "Validation", "impacted": "Yes", "extent": "Re-qualification required", "action_required": "Re-IQ/OQ"},
    ])
    monkeypatch.setattr(cc_svc, "call_gemini", lambda prompt, temperature=0.3: canned)

    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    r = client.post(f"/qms/change-control/{cc['id']}/suggest-impact")
    assert r.status_code == 200
    suggestions = r.get_json()
    assert suggestions[0]["impact_area"] == "Validation"

    r = client.post(f"/qms/change-control/{cc['id']}/impact", json=suggestions[0])
    assert r.status_code == 201
    assert len(client.get(f"/qms/change-control/{cc['id']}/impact").get_json()) == 1


def test_change_control_implementation_plan_ai_route(client, mock_gemini, monkeypatch):
    import pharmagpt.services.qms_change_control_service as cc_svc
    import json as _json
    canned = _json.dumps([{"step_no": 1, "activity": "Procure parts", "responsible": "Engineering"}])
    monkeypatch.setattr(cc_svc, "call_gemini", lambda prompt, temperature=0.3: canned)

    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    r = client.post(f"/qms/change-control/{cc['id']}/suggest-implementation-plan")
    assert r.status_code == 200
    steps = r.get_json()
    assert steps[0]["activity"] == "Procure parts"

    r = client.post(f"/qms/change-control/{cc['id']}/actions", json=steps[0])
    assert r.status_code == 201
    assert len(client.get(f"/qms/change-control/{cc['id']}/actions").get_json()) == 1


def test_change_control_ai_narratives(client, mock_gemini):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    for path, key in [
        ("risk-summary", "risk_summary"), ("rollback-plan", "rollback_plan"),
        ("regulatory-impact", "regulatory_impact"), ("justification", "justification"),
        ("executive-summary", "executive_summary"), ("verification-summary", "verification_summary"),
        ("effectiveness-review", "effectiveness_review"),
    ]:
        r = client.post(f"/qms/change-control/{cc['id']}/{path}")
        assert r.status_code == 200
        assert r.get_json()["text"] == "canned response"

    saved = client.get(f"/qms/change-control/{cc['id']}").get_json()
    assert saved["ai_narratives"]["risk_summary"] == "canned response"
    assert saved["ai_narratives"]["effectiveness_review"] == "canned response"


def test_change_control_deviation_capa_linking(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()

    r = client.post(f"/qms/change-control/{cc['id']}/link-deviation", json={"deviation_id": dev["id"]})
    assert r.status_code == 201
    r = client.post(f"/qms/change-control/{cc['id']}/link-capa", json={"capa_id": capa["id"]})
    assert r.status_code == 201

    assert client.get(f"/qms/change-control/{cc['id']}/deviations").get_json()[0]["id"] == dev["id"]
    assert client.get(f"/qms/change-control/{cc['id']}/capas").get_json()[0]["id"] == capa["id"]


def test_change_control_approval_status_map(client):
    # The /approval endpoint is now a compatibility wrapper over
    # services/workflow_engine.py (CHANGE_CONTROL_WORKFLOW_V1): one call
    # decides exactly one real workflow step — see
    # routes/qms_change_control.py::submit_approval docstring. The first
    # call both starts the instance (auto-completing "Submitted") and
    # decides the now-current "Initial Review" step, landing on
    # "Impact Assessment".
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    cc_id = cc["id"]

    client.post(f"/qms/change-control/{cc_id}/approval", json={"action": "Submitted", "performed_by": "A"})
    assert client.get(f"/qms/change-control/{cc_id}").get_json()["status"] == "Impact Assessment"

    for action in ["Risk Assessment Started", "Sent for Department Review", "Submitted for QA Review",
                   "Sent for Approval", "Approved"]:
        client.post(f"/qms/change-control/{cc_id}/approval", json={"action": action, "performed_by": "B"})
    assert client.get(f"/qms/change-control/{cc_id}").get_json()["status"] == "Implementation"

    for action in ["Implementation Complete", "Verified", "Verified"]:
        client.post(f"/qms/change-control/{cc_id}/approval", json={"action": action, "performed_by": "C"})
    assert client.get(f"/qms/change-control/{cc_id}").get_json()["status"] == "Effectiveness Review"

    client.post(f"/qms/change-control/{cc_id}/approval", json={"action": "Closed", "performed_by": "C"})
    assert client.get(f"/qms/change-control/{cc_id}").get_json()["status"] == "Closed"


def test_change_control_rejection_returns_to_draft(client):
    # Reject is only legal from an approval-type step (the same
    # decide_step() rule Deviations already follow), so this drives the
    # change control forward to its "QA Review" approval gate first, then
    # rejects from there.
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    cc_id = cc["id"]
    client.post(f"/qms/change-control/{cc_id}/approval", json={"action": "Submitted", "performed_by": "A"})
    for action in ["Risk Assessment Started", "Sent for Department Review", "Submitted for QA Review"]:
        client.post(f"/qms/change-control/{cc_id}/approval", json={"action": action, "performed_by": "B"})
    assert client.get(f"/qms/change-control/{cc_id}").get_json()["status"] == "QA Review"

    client.post(f"/qms/change-control/{cc_id}/approval", json={"action": "Rejected", "performed_by": "B"})
    assert client.get(f"/qms/change-control/{cc_id}").get_json()["status"] == "Draft"


def test_change_control_docx_export(client):
    cc = client.post("/qms/change-control", json={"title": "Change", "change_description": "Upgrade firmware"}).get_json()
    r = client.post(f"/qms/change-control/{cc['id']}/export/docx")
    assert r.status_code == 200
    assert len(r.data) > 1000


# ── Shared: attachments / comments / audit-trail ──────────────────────────────

def test_attachments_upload_download_delete(client):
    doc = client.post("/qms/documents", json={"title": "Doc"}).get_json()
    did = doc["id"]

    r = client.post(
        f"/qms/document/{did}/attachments",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "test.pdf"), "description": "Test file"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201
    attachment = r.get_json()

    r = client.get(f"/qms/document/{did}/attachments")
    assert len(r.get_json()) == 1

    r = client.get(f"/qms/attachments/{attachment['id']}/download")
    assert r.status_code == 200
    r.get_data()  # fully consume + close the streamed file response before deleting (Windows file lock)
    r.close()

    r = client.delete(f"/qms/attachments/{attachment['id']}")
    assert r.status_code == 200
    assert client.get(f"/qms/document/{did}/attachments").get_json() == []


def test_comments_and_audit_trail_generic_endpoints(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]

    r = client.post(f"/qms/deviation/{did}/comments", json={"author": "J Doe", "comment": "Looks fine"})
    assert r.status_code == 201
    assert len(client.get(f"/qms/deviation/{did}/comments").get_json()) == 1

    # Deviation creation itself writes an audit entry
    audit = client.get(f"/qms/deviation/{did}/audit-trail").get_json()
    assert any(a["action"] == "Deviation initiated" for a in audit)


def test_invalid_record_type_rejected(client):
    r = client.get("/qms/not-a-real-type/1/attachments")
    assert r.status_code == 400


def test_change_control_shares_generic_comment_and_audit_endpoints(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    cc_id = cc["id"]

    r = client.post(f"/qms/change_control/{cc_id}/comments", json={"author": "J Doe", "comment": "Looks reasonable"})
    assert r.status_code == 201
    assert len(client.get(f"/qms/change_control/{cc_id}/comments").get_json()) == 1

    audit = client.get(f"/qms/change_control/{cc_id}/audit-trail").get_json()
    assert any(a["action"] == "Change control drafted" for a in audit)

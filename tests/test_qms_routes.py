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
    import pharmagpt.routes.qms_documents as doc_routes

    def _fake_call_gemini(prompt, temperature=0.3):
        return "canned response"

    def _fake_stream_gemini(prompt, temperature=0.4):
        yield "# Generated Title\n"
        yield "Some generated markdown content."

    for mod in (shared, doc_svc, dev_svc, capa_svc):
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


def test_dashboard_endpoint_empty(client):
    r = client.get("/qms/dashboard")
    assert r.status_code == 200
    summary = r.get_json()["summary"]
    assert summary["total_documents"] == 0
    assert summary["open_deviations"] == 0
    assert summary["open_capas"] == 0


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

def test_deviation_crud_lifecycle(client):
    r = client.post("/qms/deviations", json={"title": "Temp excursion", "deviation_type": "Major"})
    assert r.status_code == 201
    dev = r.get_json()
    assert dev["status"] == "Initiated"
    did = dev["id"]

    assert client.get("/qms/deviations").status_code == 200
    r = client.put(f"/qms/deviations/{did}", json={"risk_level": "High"})
    assert r.get_json()["risk_level"] == "High"

    r = client.delete(f"/qms/deviations/{did}")
    assert r.status_code == 200


def test_deviation_investigation_ai_route(client, mock_gemini, monkeypatch):
    import pharmagpt.services.qms_deviation_service as dev_svc
    canned = json.dumps({
        "fishbone_data": {"man": ["fatigue"], "machine": [], "method": [], "material": [], "measurement": [], "environment": []},
        "five_why_data": [{"question": "Why?", "answer": "Because"}],
        "timeline_data": [{"datetime": "T0", "event": "Discovered"}],
        "root_cause_category": "Human Error",
        "root_cause_statement": "Operator fatigue led to missed step",
    })
    monkeypatch.setattr(dev_svc, "call_gemini", lambda prompt, temperature=0.3: canned)

    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    r = client.post(f"/qms/deviations/{dev['id']}/investigate")
    assert r.status_code == 200
    inv = r.get_json()
    assert inv["root_cause_statement"] == "Operator fatigue led to missed step"

    # Status should auto-transition from Initiated to Under Investigation
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()["status"] == "Under Investigation"


def test_deviation_impact_and_capa_link(client, mock_gemini):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    r = client.post(f"/qms/deviations/{dev['id']}/impact", json={"impact_area": "Product Quality", "risk_level": "Low"})
    assert r.status_code == 201
    assert len(client.get(f"/qms/deviations/{dev['id']}/impact").get_json()) == 1

    capa = client.post("/qms/capa", json={"title": "CAPA", "capa_source": "Deviation"}).get_json()
    r = client.post(f"/qms/deviations/{dev['id']}/link-capa", json={"capa_id": capa["id"]})
    assert r.status_code == 201
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()["status"] == "CAPA Assigned"

    linked = client.get(f"/qms/deviations/{dev['id']}/capas").get_json()
    assert linked[0]["id"] == capa["id"]

    reverse = client.get(f"/qms/capa/{capa['id']}/deviations").get_json()
    assert reverse[0]["id"] == dev["id"]


def test_deviation_approval_status_map(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    did = dev["id"]

    client.post(f"/qms/deviations/{did}/approval", json={"action": "Investigation Started", "performed_by": "A"})
    assert client.get(f"/qms/deviations/{did}").get_json()["status"] == "Under Investigation"

    client.post(f"/qms/deviations/{did}/approval", json={"action": "Closed", "performed_by": "B"})
    assert client.get(f"/qms/deviations/{did}").get_json()["status"] == "Closed"


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
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]

    client.post(f"/qms/capa/{cid}/approval", json={"action": "Root Cause Analysis Started", "performed_by": "A"})
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Root Cause Analysis"

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

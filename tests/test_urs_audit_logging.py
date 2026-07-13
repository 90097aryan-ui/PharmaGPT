"""
tests/test_urs_audit_logging.py — Regression coverage for Stabilization
Iteration 2 priority 6: expanded audit logging for Generation Started/
Completed and DOCX Generated/Downloaded/Download Failed, on top of the
existing "URS Created" / approval-action entries.
"""

import json

from pharmagpt import urs_database as udb
from pharmagpt.services import urs_generation_job as gen_job
from google.genai import types


class _FakeModels:
    def __init__(self, fn):
        self._fn = fn

    def generate_content(self, model, contents, config):
        return self._fn(model, contents, config)


class _FakeClient:
    def __init__(self, fn):
        self.models = _FakeModels(fn)


class _FakeUsage:
    def __init__(self):
        self.prompt_token_count = 100
        self.candidates_token_count = 200


class _FakeCandidate:
    def __init__(self, finish_reason=types.FinishReason.STOP):
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = _FakeUsage()
        self.candidates = [_FakeCandidate()]


def _req_json(section):
    return json.dumps([{
        "section": section, "requirement": "The system shall do X.",
        "rationale": "GMP", "priority": "High", "gmp_criticality": "GMP-Critical",
        "regulatory_ref": "21 CFR Part 11", "verification_method": "Functional Test",
        "acceptance_criteria": "Pass/fail",
    }])


def test_docx_export_logs_generated_and_downloaded(client):
    urs = client.post("/urs/", json={"title": "Audit DOCX Test", "equipment_name": "Autoclave"}).get_json()
    uid = urs["id"]
    client.post(f"/urs/{uid}/requirements", json=[
        {"req_id": "REQ-001", "section": "General Requirements", "requirement": "Shall log cycles.",
         "priority": "High", "gmp_criticality": "GMP", "verification_method": "Functional Test",
         "acceptance_criteria": "Logs visible"},
    ])

    resp = client.get(f"/urs/{uid}/export/docx")
    assert resp.status_code == 200

    trail = [entry["action"] for entry in udb.get_approval_trail(uid)]
    assert "DOCX Generated" in trail
    assert "DOCX Downloaded" in trail
    assert "DOCX Download Failed" not in trail


def test_docx_export_logs_download_failed_on_generation_error(client, monkeypatch):
    urs = client.post("/urs/", json={"title": "Audit DOCX Failure Test", "equipment_name": "X"}).get_json()
    uid = urs["id"]

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated markdown_to_docx failure")

    monkeypatch.setattr("pharmagpt.routes.urs.markdown_to_docx", _boom)

    resp = client.get(f"/urs/{uid}/export/docx")
    assert resp.status_code == 500

    trail = [entry["action"] for entry in udb.get_approval_trail(uid)]
    assert "DOCX Download Failed" in trail
    assert "DOCX Generated" not in trail
    assert "DOCX Downloaded" not in trail


def test_generation_logs_started_and_completed(db_path, monkeypatch):
    urs = udb.create_urs({"title": "Audit Generation Test", "equipment_name": "Autoclave"})

    def fake_generate_content(model, contents, config):
        return _FakeResponse(_req_json("Functional Requirements"))

    monkeypatch.setattr(gen_job, "gemini_client", _FakeClient(fake_generate_content))

    gen_job.submit_generation_job(
        urs["id"], urs, ["Functional Requirements"], performed_by="QA Engineer",
    )

    import time
    deadline = time.monotonic() + 10.0
    status = None
    while time.monotonic() < deadline:
        status = udb.get_generation_status(urs["id"])
        if status["generation_status"] in ("completed", "failed"):
            break
        time.sleep(0.05)

    assert status["generation_status"] == "completed"
    trail = udb.get_approval_trail(urs["id"])
    actions = [e["action"] for e in trail]
    assert "Generation Started" in actions
    assert "Generation Completed" in actions
    started = next(e for e in trail if e["action"] == "Generation Started")
    completed = next(e for e in trail if e["action"] == "Generation Completed")
    assert started["performed_by"] == "QA Engineer"
    assert completed["performed_by"] == "QA Engineer"


def test_generation_logs_failed_when_every_batch_errors(db_path, monkeypatch):
    urs = udb.create_urs({"title": "Audit Generation Failure Test", "equipment_name": "X"})

    def fake_generate_content(model, contents, config):
        raise RuntimeError("Gemini is down")

    monkeypatch.setattr(gen_job, "gemini_client", _FakeClient(fake_generate_content))

    gen_job._run_generation_job(urs["id"], urs, [["Functional Requirements"]], "System")

    actions = [e["action"] for e in udb.get_approval_trail(urs["id"])]
    assert "Generation Failed" in actions
    assert "Generation Completed" not in actions

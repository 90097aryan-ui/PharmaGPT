"""
tests/test_urs_routes.py — Integration tests for URS AI generation through
Flask's test client.

Mirrors tests/test_routes_upload_async.py's shape: POST must return almost
immediately (this is the entire fix for the Render WORKER TIMEOUT — see
services/urs_generation_job.py) and GET .../generate/status must reach a
terminal state without the HTTP connection ever being held open for the
duration of generation.
"""

import json
import time

import pytest

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
        self.prompt_token_count = 123
        self.candidates_token_count = 456


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


def _wait_for_terminal_status(client, urs_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = client.get(f"/urs/{urs_id}/generate/status").get_json()
        if status.get("generation_status") in ("completed", "failed"):
            return status
        time.sleep(0.1)
    pytest.fail(f"generation never reached a terminal status: {status}")


def test_generate_endpoint_returns_immediately_then_completes(client, monkeypatch):
    def fake_generate_content(model, contents, config):
        time.sleep(0.05)  # simulated Gemini latency
        return _FakeResponse(_req_json("Functional Requirements"))

    monkeypatch.setattr(gen_job, "gemini_client", _FakeClient(fake_generate_content))

    urs = client.post("/urs/", json={
        "title": "URS - Autoclave", "equipment_name": "Autoclave-01",
    }).get_json()

    start = time.monotonic()
    resp = client.post(f"/urs/{urs['id']}/generate", json={"sections": ["Functional Requirements"]})
    elapsed = time.monotonic() - start

    assert resp.status_code == 202
    assert resp.get_json()["status"] == "started"
    # The whole point of this redesign: the HTTP response must not wait on Gemini.
    assert elapsed < 1.0

    status = _wait_for_terminal_status(client, urs["id"])
    assert status["generation_status"] == "completed"
    assert status["generation_result_count"] == 1

    reqs = client.get(f"/urs/{urs['id']}/requirements").get_json()
    assert len(reqs) == 1
    assert reqs[0]["section"] == "Functional Requirements"


def test_generate_status_404_for_unknown_urs(client):
    resp = client.get("/urs/999999/generate/status")
    assert resp.status_code == 404


def test_generate_404_for_unknown_urs(client):
    resp = client.post("/urs/999999/generate", json={"sections": ["Functional Requirements"]})
    assert resp.status_code == 404

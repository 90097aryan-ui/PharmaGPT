"""
tests/test_capa_effectiveness_verification.py — Regression coverage for the
CAPA Effectiveness Verification gate (routes/qms_capa.py
EFFECTIVENESS_STEP_KEY / submit_effectiveness_verification), the compliance
fix for "CAPA can be closed without documented Effectiveness Verification".

Uses the same Flask test-client fixtures as tests/test_qms_routes.py
(tests/conftest.py) — the `client` fixture bypasses auth and no-ops
esignature_service.require_esignature by default; tests that need the real
e-signature gate re-patch it directly, same pattern as
tests/test_esignature_service.py.
"""

import pharmagpt.services.esignature_service as esig


def _capa_at_effectiveness_gate(client):
    """Create a CAPA and walk it, via the legacy /approval wrapper, up to
    the point where CAPA_WORKFLOW_V1 step 6 (Effectiveness Verification) is
    the current step and CAPA status == 'Effectiveness Check'."""
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]
    client.post(f"/qms/capa/{cid}/approval", json={"action": "Root Cause Analysis Started"})
    for action in ["Preventive Actions Planned", "Implementation Started", "Effectiveness Check Started"]:
        client.post(f"/qms/capa/{cid}/approval", json={"action": action})
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Effectiveness Check"
    return cid


VALID_VERIFICATION = {
    "verification_date": "2026-08-07",
    "verified_by": "QA Lead",
    "verification_method": "Trend review of recurrence data",
    "objective_evidence": "No recurrence in 90-day monitoring window",
}


# ── Cannot close without verification / cannot bypass ────────────────────────

def test_generic_workflow_decide_endpoint_rejects_effectiveness_step(client):
    cid = _capa_at_effectiveness_gate(client)
    r = client.post(f"/qms/capa/{cid}/workflow/steps/6/decide", json={"decision": "approve"})
    assert r.status_code == 409
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Effectiveness Check"


def test_legacy_approval_endpoint_rejects_effectiveness_step(client):
    cid = _capa_at_effectiveness_gate(client)
    r = client.post(f"/qms/capa/{cid}/approval", json={"action": "Submitted for QA Review"})
    assert r.status_code == 409
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Effectiveness Check"


def test_cannot_close_without_verification(client):
    cid = _capa_at_effectiveness_gate(client)
    # Both decision paths into "Closed" are blocked while the verification
    # gate hasn't been passed — the sequential workflow engine also refuses
    # to decide step 7/8 out of order.
    assert client.post(f"/qms/capa/{cid}/workflow/steps/7/decide", json={"decision": "approve"}).status_code == 409
    assert client.post(f"/qms/capa/{cid}/workflow/steps/8/decide", json={"decision": "approve"}).status_code == 409
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Effectiveness Check"


def test_missing_required_fields_rejected(client):
    cid = _capa_at_effectiveness_gate(client)
    r = client.post(f"/qms/capa/{cid}/effectiveness-verification", json={"result": "Effective"})
    assert r.status_code == 400


def test_invalid_result_rejected(client):
    cid = _capa_at_effectiveness_gate(client)
    r = client.post(f"/qms/capa/{cid}/effectiveness-verification",
                     json={**VALID_VERIFICATION, "result": "Maybe"})
    assert r.status_code == 400


def test_verification_rejected_when_not_at_gate(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    r = client.post(f"/qms/capa/{capa['id']}/effectiveness-verification",
                     json={**VALID_VERIFICATION, "result": "Effective"})
    assert r.status_code == 409


# ── Result branching ──────────────────────────────────────────────────────────

def test_effective_result_advances_to_qa_review_and_records_history(client):
    cid = _capa_at_effectiveness_gate(client)
    r = client.post(f"/qms/capa/{cid}/effectiveness-verification",
                     json={**VALID_VERIFICATION, "result": "Effective"})
    assert r.status_code == 201
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "QA Review"

    history = client.get(f"/qms/capa/{cid}/effectiveness-verification").get_json()
    assert len(history) == 1
    assert history[0]["result"] == "Effective"
    assert history[0]["verified_by"] == "QA Lead"

    wf = client.get(f"/qms/capa/{cid}/workflow").get_json()
    assert wf["instance"]["current_step_order"] == 7
    steps_by_order = {s["step_order"]: s for s in wf["steps"]}
    assert steps_by_order[6]["status"] == "approved"

    # CAPA may now be closed via the normal QA Review -> Closed path.
    client.post(f"/qms/capa/{cid}/approval", json={"action": "Submitted for QA Review"})
    client.post(f"/qms/capa/{cid}/approval", json={"action": "Closed"})
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Closed"


def test_partially_effective_returns_to_capa_plan(client):
    cid = _capa_at_effectiveness_gate(client)
    r = client.post(f"/qms/capa/{cid}/effectiveness-verification",
                     json={**VALID_VERIFICATION, "result": "Partially Effective"})
    assert r.status_code == 201
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "CA Planned"

    wf = client.get(f"/qms/capa/{cid}/workflow").get_json()
    assert wf["instance"]["current_step_order"] == 3
    steps_by_order = {s["step_order"]: s for s in wf["steps"]}
    assert steps_by_order[3]["status"] == "pending"   # ca_planned reopened
    assert steps_by_order[5]["status"] == "pending"   # implementation reopened
    assert steps_by_order[6]["status"] == "returned"  # the verification step itself

    # The bypass guard still holds against the reopened prior steps.
    assert client.post(f"/qms/capa/{cid}/workflow/steps/6/decide", json={"decision": "approve"}).status_code == 409


def test_not_effective_reopens_investigation(client):
    cid = _capa_at_effectiveness_gate(client)
    r = client.post(f"/qms/capa/{cid}/effectiveness-verification",
                     json={**VALID_VERIFICATION, "result": "Not Effective"})
    assert r.status_code == 201
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Root Cause Analysis"

    wf = client.get(f"/qms/capa/{cid}/workflow").get_json()
    assert wf["instance"]["current_step_order"] == 2
    steps_by_order = {s["step_order"]: s for s in wf["steps"]}
    assert steps_by_order[2]["status"] == "pending"


# ── Electronic Signature required ─────────────────────────────────────────────

def test_effectiveness_verification_requires_esignature(client, monkeypatch):
    cid = _capa_at_effectiveness_gate(client)

    def _fail(*a, **k):
        raise esig.ReauthenticationError("Password confirmation failed")
    monkeypatch.setattr(esig, "require_esignature", _fail)

    r = client.post(f"/qms/capa/{cid}/effectiveness-verification",
                     json={**VALID_VERIFICATION, "result": "Effective"})
    assert r.status_code == 401
    # No partial mutation: still at the gate, no verification row persisted.
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] == "Effectiveness Check"
    assert client.get(f"/qms/capa/{cid}/effectiveness-verification").get_json() == []


# ── Audit trail ────────────────────────────────────────────────────────────────

def test_effectiveness_verification_writes_audit_entries(client):
    cid = _capa_at_effectiveness_gate(client)
    esignatures_before = len(client.get(f"/qms/capa/{cid}/esignatures").get_json())

    client.post(f"/qms/capa/{cid}/effectiveness-verification",
                json={**VALID_VERIFICATION, "result": "Effective"})

    trail = client.get(f"/qms/capa/{cid}/audit-trail").get_json()
    actions = [e["action"] for e in trail]
    assert any("Effectiveness Verification recorded: Effective" in a for a in actions)
    assert any(a.startswith("E-Signature:") for a in actions)

    esignatures = client.get(f"/qms/capa/{cid}/esignatures").get_json()
    assert len(esignatures) == esignatures_before + 1
    assert esignatures[-1]["record_type"] == "capa"

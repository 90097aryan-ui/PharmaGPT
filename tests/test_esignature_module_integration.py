"""
tests/test_esignature_module_integration.py — Regression coverage for wiring
the existing, unmodified pharmagpt/services/esignature_service.py into the
remaining GMP modules: Deviation Management, Qualification (IQ/OQ/PQ),
Validation Reports (Process/Cleaning/CSV Validation, DQ/FAT/SAT reports),
Risk Assessment (covers FMEA/HACCP as risk_type variants), Training Records,
and the Document Control/CAPA/Change Control Workflow Panel decide-step path
(closes a bypass — that path was not gated in the prior phase, only the
legacy submit_approval path was).

Exercises the REAL gate (not tests/conftest.py's `client` fixture bypass,
which exists for the 300+ pre-existing business-logic tests that predate
e-signature) via a local `client` fixture that skips only the auth-exempt
patch, mocking esignature_service.reauthenticate — the actual Supabase Auth
boundary — exactly as tests/test_esignature_service.py already does.
"""

from unittest.mock import patch

import pytest

from pharmagpt import qms_database as qmsdb

REAUTH_PATH = "pharmagpt.services.esignature_service.reauthenticate"


@pytest.fixture()
def client(db_path, monkeypatch):
    import pharmagpt.app as appmod
    import pharmagpt.auth.middleware as auth_middleware
    monkeypatch.setattr(auth_middleware, "is_exempt", lambda path: True)
    return appmod.app.test_client()


def _reauth(ok=True):
    return patch(REAUTH_PATH, return_value=ok)


SIGN = {"password": "correct-password", "meaning": "Approved", "reason": "Looks correct"}


# ── Qualification (IQ/OQ/PQ) ────────────────────────────────────────────────

def test_qualification_approval_requires_reason(client):
    qual = client.post("/qual/", json={"title": "Q1", "equipment_name": "HPLC"}).get_json()
    with _reauth(True):
        resp = client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review", "password": "x", "meaning": "Reviewed"})
    assert resp.status_code == 400


def test_qualification_approval_wrong_password_blocked(client):
    qual = client.post("/qual/", json={"title": "Q1", "equipment_name": "HPLC"}).get_json()
    with _reauth(False):
        resp = client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review", **SIGN})
    assert resp.status_code == 401
    assert client.get(f"/qual/{qual['id']}").get_json()["status"] == "draft"  # unchanged


def test_qualification_approval_records_signature_and_audit_and_continues(client):
    qual = client.post("/qual/", json={"title": "Q1", "equipment_name": "HPLC"}).get_json()
    with _reauth(True):
        resp = client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review", **SIGN})
    assert resp.status_code == 201
    assert client.get(f"/qual/{qual['id']}").get_json()["status"] == "under_review"  # workflow continued

    trail = qmsdb.get_esignatures("qualification", qual["id"])
    assert len(trail) == 1
    assert trail[0]["meaning"] == "Approved"

    audit_trail = qmsdb.get_audit_trail("qualification", qual["id"])
    assert any("E-Signature" in a["action"] for a in audit_trail)


# ── Risk Assessment (covers FMEA / HACCP as risk_type variants) ────────────

def test_risk_assessment_approval_wrong_password_blocked(client):
    assessment = client.post("/risk/assessments", json={"title": "Risk 1"}).get_json()
    with _reauth(False):
        resp = client.post(f"/risk/assessments/{assessment['id']}/approval", json={"action": "Submitted for Review", **SIGN})
    assert resp.status_code == 401


def test_risk_assessment_approval_records_signature_and_continues(client):
    assessment = client.post("/risk/assessments", json={"title": "Risk 1"}).get_json()
    with _reauth(True):
        resp = client.post(f"/risk/assessments/{assessment['id']}/approval", json={"action": "Submitted for Review", **SIGN})
    assert resp.status_code == 201
    assert client.get(f"/risk/assessments/{assessment['id']}").get_json()["status"] == "In Review"
    assert len(qmsdb.get_esignatures("risk_assessment", assessment["id"])) == 1


# ── Validation Reports (Process/Cleaning/CSV Validation, DQ/FAT/SAT) ───────

def test_validation_report_approval_wrong_password_blocked(client):
    report = client.post("/report/", json={"title": "R1"}).get_json()
    with _reauth(False):
        resp = client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review", **SIGN})
    assert resp.status_code == 401


def test_validation_report_approval_records_signature_and_continues(client):
    report = client.post("/report/", json={"title": "R1"}).get_json()
    with _reauth(True):
        resp = client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review", **SIGN})
    assert resp.status_code == 201
    assert client.get(f"/report/{report['id']}").get_json()["status"] == "under_review"
    assert len(qmsdb.get_esignatures("val_report", report["id"])) == 1


# ── Training Records ─────────────────────────────────────────────────────────

def test_training_completion_requires_signature(client):
    doc = client.post("/qms/documents", json={"title": "SOP"}).get_json()
    training = client.post(f"/qms/documents/{doc['id']}/training", json={"trainee_name": "A Kumar"}).get_json()
    with _reauth(False):
        resp = client.put(f"/qms/documents/training/{training['id']}", json={"training_status": "Completed", **SIGN, "password": "wrong"})
    assert resp.status_code == 401
    assert client.get(f"/qms/documents/{doc['id']}/training").get_json()[0]["training_status"] == "Pending"


def test_training_pending_update_does_not_require_signature(client):
    """Only the Completed transition is a GMP decision — leaving it Pending
    (administrative record-keeping) must not require a signature."""
    doc = client.post("/qms/documents", json={"title": "SOP"}).get_json()
    training = client.post(f"/qms/documents/{doc['id']}/training", json={"trainee_name": "A Kumar"}).get_json()
    resp = client.put(f"/qms/documents/training/{training['id']}", json={"training_status": "Pending"})
    assert resp.status_code == 200


def test_training_completion_records_signature(client):
    doc = client.post("/qms/documents", json={"title": "SOP"}).get_json()
    training = client.post(f"/qms/documents/{doc['id']}/training", json={"trainee_name": "A Kumar"}).get_json()
    with _reauth(True):
        resp = client.put(f"/qms/documents/training/{training['id']}", json={"training_status": "Completed", **SIGN})
    assert resp.status_code == 200
    assert len(qmsdb.get_esignatures("document", doc["id"])) == 1


# ── Document Control / CAPA / Change Control Workflow Panel decide-step ────
# (closes the bypass: this path was previously unguarded)

def test_document_workflow_panel_decide_requires_signature(client):
    doc = client.post("/qms/documents", json={"title": "Doc"}).get_json()
    resp = client.post(f"/qms/documents/{doc['id']}/workflow/steps/1/decide", json={"decision": "advance"})
    assert resp.status_code == 400  # missing meaning/reason — blocked before reaching the workflow engine


def test_document_workflow_panel_decide_wrong_password_blocked(client):
    doc = client.post("/qms/documents", json={"title": "Doc"}).get_json()
    with _reauth(False):
        resp = client.post(
            f"/qms/documents/{doc['id']}/workflow/steps/1/decide",
            json={"decision": "advance", "meaning": "Reviewed", "reason": "x", "password": "wrong"},
        )
    assert resp.status_code == 401


def test_capa_workflow_panel_decide_requires_signature(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    resp = client.post(f"/qms/capa/{capa['id']}/workflow/steps/1/decide", json={"decision": "advance"})
    assert resp.status_code == 400


def test_change_control_workflow_panel_decide_requires_signature(client):
    cc = client.post("/qms/change-control", json={"title": "CC"}).get_json()
    resp = client.post(f"/qms/change-control/{cc['id']}/workflow/steps/1/decide", json={"decision": "advance"})
    assert resp.status_code == 400


# ── Deviation Management ─────────────────────────────────────────────────────

def test_deviation_decide_requires_signature(client):
    dev = client.post("/qms/deviations", json={"title": "Dev 1"}).get_json()
    resp = client.post(f"/qms/deviations/{dev['id']}/workflow/steps/1/decide", json={"decision": "advance"})
    assert resp.status_code == 400  # missing meaning/reason — blocked before the workflow engine's own RBAC check


def test_deviation_decide_wrong_password_blocked(client):
    dev = client.post("/qms/deviations", json={"title": "Dev 1"}).get_json()
    with _reauth(False):
        resp = client.post(
            f"/qms/deviations/{dev['id']}/workflow/steps/1/decide",
            json={"decision": "advance", "meaning": "Reviewed", "reason": "x", "password": "wrong"},
        )
    assert resp.status_code == 401


# ── Unauthorized user (RBAC enforced before e-signature is ever reached) ───

def test_unauthorized_role_cannot_reach_qualification_approval(client, monkeypatch):
    """conftest.py's before_request shim (registered once, at import time —
    Flask forbids registering new before_request handlers after the app has
    served its first request) falls back to a fixed company_admin tenant
    whenever g.tenant isn't already set. Monkeypatching that fallback's
    *role* to a plain "user" for this test exercises the exact same
    require_role gate a real non-admin session would hit — without needing
    a second before_request registration this late."""
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module

    qual = client.post("/qual/", json={"title": "Q1", "equipment_name": "HPLC"}).get_json()

    plain_user = TenantContext(
        user_id="plain-user", email="plain@example.com", display_name="Plain User",
        role="user", company_id=conftest_module._TEST_TENANT.company_id,
    )
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", plain_user)

    with _reauth(True):
        resp = client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review", **SIGN})
    assert resp.status_code == 403  # blocked by @require_role before esignature_service is ever called

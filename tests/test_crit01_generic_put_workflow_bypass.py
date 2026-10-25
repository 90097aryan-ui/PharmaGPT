"""
tests/test_crit01_generic_put_workflow_bypass.py — Regression coverage for
CRIT-01 (PharmaGPT Security Audit, Stage 2 remediation, Wave 1).

Before this fix, PUT /qms/<module>/<id> (and PUT /risk/assessments/<id>)
accepted workflow-controlled fields (status, approver, qa_reviewer,
reviewer, closure_date, implementation_date, verification_date, version,
superseded_date) with no relationship to the workflow engine, named-approver
check, or e-signature gate those record types' dedicated endpoints enforce —
letting any authenticated user move a Document/CAPA/Deviation/Change
Control/Risk Assessment straight to a terminal GMP status with a single
unguarded PUT.

Enforcement is layered:
  1. Repository layer (primary boundary) — qms_capa_database.
     CAPA_CONTROLLED_FIELDS and its siblings; update_*() raises ValueError
     unless the caller explicitly passes allow_controlled_fields=True.
  2. Route layer (defense-in-depth) — the generic PUT handler returns a
     clean 400 before ever reaching the repository call.

These tests exercise the real Flask routes (tests/conftest.py's `client`
fixture, default tenant role="company_admin" — the fix is not role-gated,
so the highest-privilege role is exploitable identically to the lowest,
confirmed in the Stage 2 verification) plus direct repository-layer calls.
"""

import pytest


# ── A/B: generic PUT rejects every workflow-controlled field, per module ────

def test_document_put_rejects_status(client):
    doc = client.post("/qms/documents", json={"doc_type": "SOP", "title": "Cleaning SOP", "department": "QA"}).get_json()
    assert doc["status"] == "Draft"

    r = client.put(f"/qms/documents/{doc['id']}", json={"status": "Effective"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/documents/{doc['id']}").get_json()["status"] == "Draft"


@pytest.mark.parametrize("field,value", [
    ("approver", "Fake Approver"),
    ("reviewer", "Fake Reviewer"),
    ("version", "9.9"),
    ("superseded_date", "2020-01-01"),
])
def test_document_put_rejects_controlled_field(client, field, value):
    doc = client.post("/qms/documents", json={"doc_type": "SOP", "title": "Doc", "department": "QA"}).get_json()
    r = client.put(f"/qms/documents/{doc['id']}", json={field: value})
    assert r.status_code == 400
    assert field in r.get_json()["error"]
    assert client.get(f"/qms/documents/{doc['id']}").get_json()[field] != value


def test_capa_put_rejects_status(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    assert capa["status"] == "Open"

    r = client.put(f"/qms/capa/{capa['id']}", json={"status": "Closed"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/capa/{capa['id']}").get_json()["status"] == "Open"


@pytest.mark.parametrize("field,value", [
    ("qa_reviewer", "Fake QA"),
    ("approver", "Fake Approver"),
    ("closure_date", "2020-01-01"),
])
def test_capa_put_rejects_controlled_field(client, field, value):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    r = client.put(f"/qms/capa/{capa['id']}", json={field: value})
    assert r.status_code == 400
    assert field in r.get_json()["error"]
    assert client.get(f"/qms/capa/{capa['id']}").get_json()[field] != value


def test_capa_put_cannot_bypass_effectiveness_verification_gate(client):
    """Flagship regression case: PUT {"status": "Closed"} previously fully
    defeated the mandatory, e-signed Effectiveness Verification step that
    tests/test_capa_effectiveness_verification.py proves is otherwise
    unreachable through the generic decide-step and legacy-approval
    endpoints."""
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]

    r = client.put(f"/qms/capa/{cid}", json={"status": "Closed"})
    assert r.status_code == 400
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] != "Closed"


def test_deviation_put_rejects_status(client):
    dev = client.post("/qms/deviations", json={"title": "Temp excursion"}).get_json()
    assert dev["status"] == "Draft"

    r = client.put(f"/qms/deviations/{dev['id']}", json={"status": "Closed"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()["status"] == "Draft"


@pytest.mark.parametrize("field,value", [
    # NOTE: qa_reviewer is deliberately NOT included — see
    # qms_deviation_database.DEVIATION_CONTROLLED_FIELDS's comment; it is a
    # pre-existing, intentional backward-compatibility exception, covered by
    # tests/test_deviation_workflow_builder.py::
    # test_overview_update_still_accepts_qa_reviewer_field_for_backward_compat.
    ("approver", "Fake Approver"),
    ("closure_date", "2020-01-01"),
])
def test_deviation_put_rejects_controlled_field(client, field, value):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    r = client.put(f"/qms/deviations/{dev['id']}", json={field: value})
    assert r.status_code == 400
    assert field in r.get_json()["error"]
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()[field] != value


def test_change_control_put_rejects_status(client):
    cc = client.post("/qms/change-control", json={"title": "Upgrade HVAC firmware"}).get_json()
    assert cc["status"] == "Draft"

    r = client.put(f"/qms/change-control/{cc['id']}", json={"status": "Closed"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/change-control/{cc['id']}").get_json()["status"] == "Draft"


@pytest.mark.parametrize("field,value", [
    ("qa_reviewer", "Fake QA"),
    ("approver", "Fake Approver"),
    ("implementation_date", "2020-01-01"),
    ("verification_date", "2020-01-01"),
    ("closure_date", "2020-01-01"),
])
def test_change_control_put_rejects_controlled_field(client, field, value):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    r = client.put(f"/qms/change-control/{cc['id']}", json={field: value})
    assert r.status_code == 400
    assert field in r.get_json()["error"]
    assert client.get(f"/qms/change-control/{cc['id']}").get_json()[field] != value


def test_risk_assessment_put_rejects_status(client):
    a = client.post("/risk/assessments", json={"title": "Risk", "assessment_type": "FMEA"}).get_json()
    assert a["status"] == "Draft"

    r = client.put(f"/risk/assessments/{a['id']}", json={"status": "Approved"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/risk/assessments/{a['id']}").get_json()["status"] == "Draft"


@pytest.mark.parametrize("field,value", [
    ("reviewer", "Fake Reviewer"),
    ("approver", "Fake Approver"),
])
def test_risk_assessment_put_rejects_controlled_field(client, field, value):
    a = client.post("/risk/assessments", json={"title": "Risk", "assessment_type": "FMEA"}).get_json()
    r = client.put(f"/risk/assessments/{a['id']}", json={field: value})
    assert r.status_code == 400
    assert field in r.get_json()["error"]
    assert client.get(f"/risk/assessments/{a['id']}").get_json()[field] != value


# ── C: legitimate, non-controlled field edits still work (no over-blocking) ─

def test_document_put_still_accepts_legitimate_fields(client):
    doc = client.post("/qms/documents", json={"doc_type": "SOP", "title": "Doc", "department": "QA"}).get_json()
    r = client.put(f"/qms/documents/{doc['id']}", json={"title": "Renamed SOP", "content": "# Draft body"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["title"] == "Renamed SOP"
    assert body["content"] == "# Draft body"


def test_capa_put_still_accepts_legitimate_fields(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    r = client.put(f"/qms/capa/{capa['id']}", json={"root_cause": "Root cause text"})
    assert r.status_code == 200
    assert r.get_json()["root_cause"] == "Root cause text"


def test_deviation_put_still_accepts_legitimate_fields(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    r = client.put(f"/qms/deviations/{dev['id']}", json={"risk_level": "High"})
    assert r.status_code == 200
    assert r.get_json()["risk_level"] == "High"


def test_change_control_put_still_accepts_legitimate_fields(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    r = client.put(f"/qms/change-control/{cc['id']}", json={"risk_level": "Medium"})
    assert r.status_code == 200
    assert r.get_json()["risk_level"] == "Medium"


def test_risk_assessment_put_still_accepts_legitimate_fields(client):
    a = client.post("/risk/assessments", json={"title": "Risk", "assessment_type": "FMEA"}).get_json()
    r = client.put(f"/risk/assessments/{a['id']}", json={"methodology": "FMEA-v2"})
    assert r.status_code == 200
    assert r.get_json()["methodology"] == "FMEA-v2"


# ── D: legitimate workflow transitions still reach the DB after the fix ─────
# (Broader multi-step approval-chain regression is covered by the existing
# suites — test_capa_effectiveness_verification.py, test_workflow_engine.py,
# test_deviation_workflow_builder.py, test_qms_routes.py — run alongside
# this file; these are lightweight, single-step smoke checks that the
# allow_controlled_fields=True wiring added at each internal call site
# actually works end-to-end through the real HTTP route.)

def test_capa_legitimate_approval_action_still_transitions_status(client):
    """Asserts only that the status actually changed, not the exact label —
    workflow_engine.py's _status_after_completing() shows the *next* step's
    gate_status once a step completes (by design, see its docstring), not
    the just-completed step's own name, so "Root Cause Analysis Started"
    legitimately lands on "CA Planned", not "Root Cause Analysis"."""
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    r = client.post(f"/qms/capa/{capa['id']}/approval", json={"action": "Root Cause Analysis Started"})
    assert r.status_code == 201
    assert client.get(f"/qms/capa/{capa['id']}").get_json()["status"] != "Open"


def test_change_control_legitimate_approval_action_still_transitions_status(client):
    """See test_capa_...'s docstring above re: next-step gate_status labeling."""
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    r = client.post(f"/qms/change-control/{cc['id']}/approval", json={"action": "Submitted"})
    assert r.status_code == 201
    assert client.get(f"/qms/change-control/{cc['id']}").get_json()["status"] != "Draft"


# Document Control's /approval endpoint additionally requires Author
# Self-Check + Final Author Version upload + a complete review chain before
# "Submitted for Review" is accepted (_submission_gate_error(), an existing,
# unrelated business rule) — reproducing that full precondition sequence
# here would risk a fragile test of something this wave doesn't touch.
# tests/test_qms_routes.py already exercises the full, correct Document
# Control submission flow end-to-end; running it (see Stage 2 report)
# confirms the allow_controlled_fields=True wiring added to
# routes/qms_documents.py::submit_approval works. The direct repository-
# layer check above (test_document_database_update_refuses_controlled_
# field_by_default) already proves qdb.update_document(..., allow_
# controlled_fields=True) itself still succeeds.


def test_risk_legitimate_approval_action_still_transitions_status(client):
    a = client.post("/risk/assessments", json={"title": "Risk", "assessment_type": "FMEA"}).get_json()
    r = client.post(f"/risk/assessments/{a['id']}/approval", json={"action": "Submitted for Review"})
    assert r.status_code == 201
    assert client.get(f"/risk/assessments/{a['id']}").get_json()["status"] == "In Review"


# ── E: repository layer itself refuses controlled fields, independent of ────
# any route — proves a future route cannot reintroduce CRIT-01 by calling
# these functions directly.

def test_capa_database_update_refuses_controlled_field_by_default(db_path):
    from pharmagpt import qms_capa_database as cdb

    capa = cdb.create_capa({"title": "CAPA"}, company_id="test-company-1")
    with pytest.raises(ValueError, match="status"):
        cdb.update_capa(capa["id"], {"status": "Closed"})
    assert cdb.get_capa(capa["id"])["status"] != "Closed"

    # The explicit opt-in still works, for trusted internal callers.
    updated = cdb.update_capa(capa["id"], {"status": "Closed"}, allow_controlled_fields=True)
    assert updated["status"] == "Closed"


def test_document_database_update_refuses_controlled_field_by_default(db_path):
    from pharmagpt import qms_document_database as qdb

    doc = qdb.create_document({"title": "Doc"}, company_id="test-company-1")
    with pytest.raises(ValueError, match="approver"):
        qdb.update_document(doc["id"], {"approver": "Fake Approver"})
    assert qdb.get_document(doc["id"])["approver"] != "Fake Approver"

    # The explicit opt-in still works, for trusted internal callers (e.g.
    # workflow_engine.py's STATUS_APPLIERS, submit_approval()).
    updated = qdb.update_document(doc["id"], {"status": "Approved"}, allow_controlled_fields=True)
    assert updated["status"] == "Approved"


def test_deviation_database_update_refuses_controlled_field_by_default(db_path):
    from pharmagpt import qms_deviation_database as ddb

    dev = ddb.create_deviation({"title": "Dev"}, company_id="test-company-1")
    with pytest.raises(ValueError, match="status"):
        ddb.update_deviation(dev["id"], {"status": "Closed"})


def test_change_control_database_update_refuses_controlled_field_by_default(db_path):
    from pharmagpt import qms_change_control_database as ccdb

    cc = ccdb.create_change_control({"title": "Change"}, company_id="test-company-1")
    with pytest.raises(ValueError, match="status"):
        ccdb.update_change_control(cc["id"], {"status": "Closed"})


def test_risk_assessment_database_update_refuses_controlled_field_by_default(db_path):
    from pharmagpt import risk_database as rdb

    a = rdb.create_assessment({"title": "Risk", "assessment_type": "FMEA"}, company_id="test-company-1")
    with pytest.raises(ValueError, match="status"):
        rdb.update_assessment(a["id"], {"status": "Approved"})

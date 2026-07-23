"""
tests/test_lifecycle_engine.py — Regression coverage for the shared lifecycle
engine (pharmagpt/services/lifecycle_engine.py, Phase 3: Enterprise
Validation Platform), which generalizes urs_lifecycle.py's proven
ALLOWED_TRANSITIONS/validate_transition()/InvalidTransitionError pattern to
QMS Document Control, Qualification, Validation Report, and Risk Assessment
— suites that previously accepted any mapped approval action regardless of
the record's current status.
"""

import pytest

from pharmagpt.services import lifecycle_engine
from pharmagpt.services import urs_lifecycle


# ── Unit-level: registry delegation and validation ───────────────────────────

def test_urs_delegates_to_urs_lifecycle_not_a_duplicate():
    """The registry must be the *same* dict object urs_lifecycle.py owns, not
    a copy — so urs_lifecycle.py stays the single source of truth for URS."""
    assert lifecycle_engine._REGISTRY["URS"] is urs_lifecycle.ALLOWED_TRANSITIONS


def test_noop_transition_always_allowed():
    lifecycle_engine.validate_transition("QMS_DOCUMENT", "Draft", "Draft")
    lifecycle_engine.validate_transition("UNKNOWN_KEY", "anything", "anything")


def test_unknown_lifecycle_key_permits_only_noop():
    with pytest.raises(lifecycle_engine.InvalidTransitionError):
        lifecycle_engine.validate_transition("UNKNOWN_KEY", "Draft", "Effective")


@pytest.mark.parametrize("current,requested", [
    ("Draft", "Under Review"),
    ("Under Review", "Effective"),
    ("Under Review", "Pending Approval"),
    ("Pending Approval", "Effective"),
    ("Effective", "Draft"),
    ("Effective", "Under Revision"),
    ("Effective", "Obsolete"),
])
def test_qms_document_legal_transitions(current, requested):
    lifecycle_engine.validate_transition("QMS_DOCUMENT", current, requested)


@pytest.mark.parametrize("current,requested", [
    ("Draft", "Effective"),
    ("Draft", "Obsolete"),
    ("Obsolete", "Effective"),
    ("Obsolete", "Draft"),
])
def test_qms_document_illegal_transitions_rejected(current, requested):
    with pytest.raises(lifecycle_engine.InvalidTransitionError):
        lifecycle_engine.validate_transition("QMS_DOCUMENT", current, requested)


def test_qualification_illegal_skip_rejected():
    with pytest.raises(lifecycle_engine.InvalidTransitionError):
        lifecycle_engine.validate_transition("QUALIFICATION", "obsolete", "approved")


def test_validation_report_illegal_skip_rejected():
    with pytest.raises(lifecycle_engine.InvalidTransitionError):
        lifecycle_engine.validate_transition("VALIDATION_REPORT", "obsolete", "released")


def test_risk_assessment_illegal_skip_rejected():
    with pytest.raises(lifecycle_engine.InvalidTransitionError):
        lifecycle_engine.validate_transition("RISK_ASSESSMENT", "Closed", "In Review")


# ── Route-level: 409 on an illegal transition ────────────────────────────────

def test_qualification_route_rejects_invalid_transition(client):
    qual = client.post("/qual/", json={"title": "Q1", "equipment_name": "HPLC"}).get_json()
    client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qual/{qual['id']}/approval", json={"action": "Approved"})
    client.post(f"/qual/{qual['id']}/approval", json={"action": "Closed"})

    # obsolete is only reachable from closed via a mapped action, but there is
    # none in qual.py's status_map back to under_review from obsolete/closed.
    resp = client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review"})
    assert resp.status_code == 409


def test_validation_report_route_rejects_invalid_transition(client):
    report = client.post("/report/", json={"title": "R1"}).get_json()
    client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review"})
    client.post(f"/report/{report['id']}/approval", json={"action": "QA Approved"})
    client.post(f"/report/{report['id']}/approval", json={"action": "Released"})
    client.post(f"/report/{report['id']}/approval", json={"action": "Archived"})

    resp = client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review"})
    assert resp.status_code == 409


def test_risk_assessment_route_rejects_invalid_transition(client):
    assessment = client.post("/risk/assessments", json={"title": "Risk 1"}).get_json()
    client.post(f"/risk/assessments/{assessment['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/risk/assessments/{assessment['id']}/approval", json={"action": "Approved"})
    client.post(f"/risk/assessments/{assessment['id']}/approval", json={"action": "Closed"})

    resp = client.post(
        f"/risk/assessments/{assessment['id']}/approval",
        json={"action": "Submitted for Review"},
    )
    assert resp.status_code == 409


def test_qms_document_route_rejects_invalid_transition(client):
    doc = client.post("/qms/documents", json={"title": "SOP 1", "doc_type": "SOP"}).get_json()
    # Approved always maps to Effective; a Draft document has no legal path
    # straight to Under Revision (only reachable from Effective/Under Review).
    resp = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Send for Revision"})
    assert resp.status_code == 409

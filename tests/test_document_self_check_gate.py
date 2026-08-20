"""
tests/test_document_self_check_gate.py — Phase 5 coverage: Author Self-Check
as a mandatory hard gate on Submit for Review, scoped to the CURRENT
version, never carried forward to a new version.
"""

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def _make_document():
    return qdb.create_document({"title": "Cleaning SOP", "content": "x"}, company_id=COMPANY_ID)


# ── Service layer ─────────────────────────────────────────────────────────────

def test_self_check_not_cleared_by_default(db_path):
    doc = _make_document()
    assert qdb.is_self_check_cleared(doc["id"]) is False


def test_record_self_check_clears_gate(db_path):
    doc = _make_document()
    qdb.record_self_check(doc["id"], "Ada Author")
    assert qdb.is_self_check_cleared(doc["id"]) is True
    version = qdb.get_current_version(doc["id"])
    assert version["self_check_completed_at"]


def test_self_check_only_legal_while_draft(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    qdb.transition_version_status(version["id"], "under_review")
    with pytest.raises(ValueError, match="Draft"):
        qdb.record_self_check(doc["id"], "Ada Author")


def test_new_version_after_rejection_requires_fresh_self_check(db_path):
    from pharmagpt.services import workflow_engine as wfe
    doc = _make_document()
    qdb.record_self_check(doc["id"], "Ada Author")
    v0 = qdb.get_current_version(doc["id"])
    assert v0["self_check_completed_at"]

    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": "rev-1", "display_name": "Rita"}])
    wfe.decide_step("document", doc["id"], 2, "reject", user_id="rev-1", role="reviewer_qa",
                     performed_by="Rita", comments="Needs rework")

    v1 = qdb.get_current_version(doc["id"])
    assert v1["id"] != v0["id"]
    assert v1["self_check_completed_at"] == ""  # never carried forward
    assert qdb.is_self_check_cleared(doc["id"]) is False


# ── Route layer: hard gate on Submit for Review ───────────────────────────────

def test_workflow_start_blocked_without_self_check(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/workflow/start")
    assert r.status_code == 409
    assert "Self-Check" in r.get_json()["error"]


def test_workflow_start_allowed_after_self_check(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/self-check")
    assert r.status_code == 200
    r = client.post(f"/qms/documents/{doc['id']}/workflow/start")
    assert r.status_code == 201


def test_legacy_approval_submit_for_review_blocked_without_self_check(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    assert r.status_code == 409
    assert "Self-Check" in r.get_json()["error"]


def test_legacy_approval_submit_for_review_allowed_after_self_check(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")
    r = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    assert r.status_code == 201


def test_self_check_route_blocked_once_under_review(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    r = client.post(f"/qms/documents/{doc['id']}/self-check")
    assert r.status_code == 409

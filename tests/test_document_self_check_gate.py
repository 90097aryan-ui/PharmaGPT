"""
tests/test_document_self_check_gate.py — Phase 5 coverage: Author Self-Check
as a mandatory hard gate on Submit for Review, scoped to the CURRENT
version, never carried forward to a new version.
"""

import io

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID


def _upload_final_version(client, did, text=b"final content"):
    r = client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(text), "final.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_json()


_CALLER_USER_ID = "00000000-0000-0000-0000-000000000001"  # the `client` fixture's fixed tenant user_id (Author)

# P0 stabilization: segregation of duties forbids the Author from also being
# an approver, so Reviewer/Department Head/Quality Head are distinct
# identities here.
_REVIEWER_USER_ID = "00000000-0000-0000-0000-000000000002"
_DEPT_HEAD_USER_ID = "00000000-0000-0000-0000-000000000003"
_QUALITY_HEAD_USER_ID = "00000000-0000-0000-0000-000000000004"


def _assign_chain(client, did):
    """SOP workflow correction: Submit for Review is now additionally gated
    on the Author having assigned a complete Reviewer/Department Head/
    Quality Head chain (Plant Head optional) — see
    tests/test_document_author_assigned_chain.py for the dedicated suite."""
    r = client.post(f"/qms/documents/{did}/assign-chain", json={
        "reviewer_user_id": _REVIEWER_USER_ID, "reviewer_name": "Rita",
        "department_head_user_id": _DEPT_HEAD_USER_ID, "department_head_name": "Al",
        "quality_head_user_id": _QUALITY_HEAD_USER_ID, "quality_head_name": "Quinn",
    })
    assert r.status_code == 200, r.get_json()


def _as(monkeypatch, user_id, display_name, role="user"):
    """Switch the client fixture's active identity mid-test. This file's
    autouse _app_context fixture holds one Flask app context open for the
    whole test (needed by the bare wfe.*/qdb.* calls in the "Service layer"
    tests below), which means the SAME `g` is reused across every
    client.post() call in a test (Flask does not push a second app context
    for the same app) — so the before_request shim's `if not hasattr(g,
    "tenant")` guard would otherwise never re-fire after the first request.
    Clearing g.tenant here forces it to re-populate from the (now updated)
    _TEST_TENANT on the next request."""
    from flask import g as flask_g
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module
    ctx = TenantContext(user_id=user_id, email=f"{user_id}@example.com", display_name=display_name,
                         role=role, company_id=conftest_module._TEST_TENANT.company_id)
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", ctx)
    flask_g.pop("tenant", None)


def _as_author(monkeypatch):
    _as(monkeypatch, _CALLER_USER_ID, "Test User", role="company_admin")


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
    _upload_final_version(client, doc["id"])
    _assign_chain(client, doc["id"])
    r = client.post(f"/qms/documents/{doc['id']}/workflow/start")
    assert r.status_code == 201


def test_legacy_approval_submit_for_review_blocked_without_self_check(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    assert r.status_code == 409
    assert "Self-Check" in r.get_json()["error"]


def test_legacy_approval_submit_for_review_allowed_after_self_check(client, monkeypatch):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")
    _upload_final_version(client, doc["id"])
    _assign_chain(client, doc["id"])
    # The legacy /approval wrapper requires company_admin/reviewer_qa (see
    # its @require_role) AND immediately decides the now-current step 2 as
    # whoever calls it — so the caller must be the assigned Reviewer's
    # user_id AND hold the reviewer_qa role, now that segregation of duties
    # forbids the Author from holding the Reviewer seat.
    _as(monkeypatch, _REVIEWER_USER_ID, "Rita", role="reviewer_qa")
    r = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    assert r.status_code == 201


def test_self_check_route_blocked_once_under_review(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")
    _upload_final_version(client, doc["id"])
    _assign_chain(client, doc["id"])
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    r = client.post(f"/qms/documents/{doc['id']}/self-check")
    assert r.status_code == 409


# ── Fix: revision forked from an Effective document must never inherit ──────
# Self-Check from the outgoing version — see routes/qms_documents.py's
# _submission_gate_error() and the new POST .../versions/start-revision.


def _drive_document_to_effective(client, monkeypatch):
    """SOP workflow correction: Department Head/Quality Head are now
    strictly sequential single-decider steps (3 and 4), not one shared
    quorum step — decides both in order, then Plant Head (step 5) is
    auto-skipped since _assign_chain never assigns one. Restores the active
    identity to the Author/company_admin before training/release, since
    every caller of this helper continues as the Author afterward."""
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "v1"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did)
    _assign_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    _as(monkeypatch, _REVIEWER_USER_ID, "Rita")
    client.post(f"/qms/documents/{did}/workflow/steps/2/decide",
                json={"decision": "approve", "meaning": "Reviewed"})
    _as(monkeypatch, _DEPT_HEAD_USER_ID, "Al")
    client.post(f"/qms/documents/{did}/workflow/steps/3/decide",
                json={"decision": "approve", "meaning": "Approved"})
    _as(monkeypatch, _QUALITY_HEAD_USER_ID, "Quinn")
    client.post(f"/qms/documents/{did}/workflow/steps/4/decide",
                json={"decision": "approve", "meaning": "Approved"})
    _as_author(monkeypatch)
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "T1"}).get_json()
    client.put(f"/qms/documents/training/{t['id']}", json={"training_status": "Completed", "training_date": "2026-01-01"})
    # Document Control redesign (spec §17/§20): training completion alone no
    # longer auto-flips the document to Effective — an explicit Quality
    # Coordinator release is required (routes/qms_documents.py::release_document,
    # see tests/test_document_quality_release.py for its dedicated coverage).
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Approved"
    client.post(f"/qms/documents/{did}/release", json={"meaning": "Released"})
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Effective"
    return did


def test_legacy_rejected_action_on_effective_document_is_blocked_not_silently_forked(client, monkeypatch):
    """This is the exact bug reported: the old code let "Rejected" on an
    Effective document fork a new version AND submit it in one call,
    checking the OUTGOING (Effective) version's stale Self-Check flag
    rather than requiring a fresh one on the version actually being
    submitted. Now blocked outright."""
    did = _drive_document_to_effective(client, monkeypatch)
    r = client.post(f"/qms/documents/{did}/approval",
                     json={"action": "Rejected", "comments": "Starting revision"})
    assert r.status_code == 409
    assert "start-revision" in r.get_json()["error"]
    # nothing was forked or mutated
    assert qdb.get_current_version(did)["status"] == "effective"


def test_workflow_start_on_effective_document_is_blocked(client, monkeypatch):
    did = _drive_document_to_effective(client, monkeypatch)
    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 409
    assert "start-revision" in r.get_json()["error"]


def test_start_revision_forks_new_draft_with_no_self_check(client, monkeypatch):
    did = _drive_document_to_effective(client, monkeypatch)
    effective_version = qdb.get_current_version(did)

    r = client.post(f"/qms/documents/{did}/versions/start-revision")
    assert r.status_code == 201, r.get_json()
    new_version = r.get_json()
    assert new_version["id"] != effective_version["id"]
    assert new_version["status"] == "draft"
    assert new_version["self_check_completed_at"] == ""  # never inherited
    assert qdb.is_self_check_cleared(did) is False


def test_submit_blocked_after_start_revision_until_fresh_self_check(client, monkeypatch):
    did = _drive_document_to_effective(client, monkeypatch)
    client.post(f"/qms/documents/{did}/versions/start-revision")

    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 409
    assert "Self-Check" in r.get_json()["error"]

    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did)
    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 201


def test_full_two_step_revision_flow_via_legacy_endpoint(client, monkeypatch):
    """start-revision -> self-check -> legacy 'Submitted for Review' all
    succeed in sequence, proving the corrected flow works end to end
    through the legacy /approval endpoint too, not just /workflow/start."""
    did = _drive_document_to_effective(client, monkeypatch)
    r = client.post(f"/qms/documents/{did}/versions/start-revision")
    assert r.status_code == 201
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did)
    _as(monkeypatch, _REVIEWER_USER_ID, "Rita", role="reviewer_qa")
    r = client.post(f"/qms/documents/{did}/approval", json={"action": "Submitted for Review"})
    assert r.status_code == 201
    # Pre-existing legacy-endpoint behavior (unrelated to this fix): when
    # "Submitted for Review" has to auto-start the instance, it also
    # auto-self-assigns the caller and immediately decides the now-current
    # step 2 in the same call — so status lands on 'pending_approval'
    # (step 2 approved), not 'under_review'.
    assert qdb.get_current_version(did)["status"] == "pending_approval"

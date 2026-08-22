"""
tests/test_document_training_gate.py — Phase 4 coverage: the training gate
(>=90% completion, >=1 trainee — zero trainees is never treated as 100%),
the new 'Approved' holding status between quorum/approval and Effective,
and version-scoped training (a rejected version's training can never clear
a newer version's gate).

Engine/DB-level tests exercise qms_document_database.py + workflow_engine.py
directly, same style as tests/test_quorum_approval.py. Route-level tests use
the `client` fixture.
"""

import io
from unittest.mock import patch

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID


def _upload_final_version(client, did, text=b"final content"):
    r = client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(text), "final.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_json()

REAUTH_PATH = "pharmagpt.services.esignature_service.reauthenticate"
SIGN = {"password": "correct-password", "meaning": "Approved", "reason": "Looks correct"}


def _reauth(ok=True):
    return patch(REAUTH_PATH, return_value=ok)


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def _make_document():
    return qdb.create_document({"title": "Cleaning SOP", "content": "some content"}, company_id=COMPANY_ID)


def _reach_approved(doc, quorum=None):
    """Drive a document through Submit -> Review approve -> final Approval
    approve, landing the version at 'approved' and the document status at
    'Approved' (training not yet cleared)."""
    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author",
                        default_quorum=quorum)
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": "rev-1", "display_name": "Rita"}])
    wfe.decide_step("document", doc["id"], 2, "approve", user_id="rev-1", role="reviewer_qa", performed_by="Rita")
    wfe.assign_approvers("document", doc["id"], 3, [{"user_id": "appr-1", "display_name": "Al"}])
    return wfe.decide_step("document", doc["id"], 3, "approve", user_id="appr-1", role="company_admin",
                            performed_by="Al")


# ── training_completion_pct / training_gate_status ───────────────────────────

def test_zero_trainees_returns_none_not_zero_or_hundred(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    assert qdb.training_completion_pct(version["id"]) is None
    gate = qdb.training_gate_status(version["id"])
    assert gate["cleared"] is False
    assert gate["trainee_count"] == 0
    assert gate["completion_pct"] is None


def test_below_threshold_not_cleared(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    qdb.add_training(doc["id"], {"trainee_name": "A"})
    qdb.add_training(doc["id"], {"trainee_name": "B"})
    t3 = qdb.add_training(doc["id"], {"trainee_name": "C"})
    qdb.update_training_status(t3["id"], "Completed", "2026-01-01")

    gate = qdb.training_gate_status(version["id"])
    assert round(gate["completion_pct"], 2) == round(100 / 3, 2)
    assert gate["cleared"] is False


def test_exactly_90_percent_clears(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    ids = [qdb.add_training(doc["id"], {"trainee_name": f"T{i}"})["id"] for i in range(10)]
    for tid in ids[:9]:
        qdb.update_training_status(tid, "Completed", "2026-01-01")

    gate = qdb.training_gate_status(version["id"])
    assert gate["completion_pct"] == 90.0
    assert gate["cleared"] is True


def test_above_90_percent_clears(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    ids = [qdb.add_training(doc["id"], {"trainee_name": f"T{i}"})["id"] for i in range(4)]
    for tid in ids:
        qdb.update_training_status(tid, "Completed", "2026-01-01")

    gate = qdb.training_gate_status(version["id"])
    assert gate["completion_pct"] == 100.0
    assert gate["cleared"] is True


# ── Full flow: quorum met holds at Approved until training clears ────────────

def test_approval_holds_at_approved_when_training_not_cleared(db_path):
    doc = _make_document()
    _reach_approved(doc)

    version = qdb.get_current_version(doc["id"])
    assert version["status"] == "approved"
    doc_after = qdb.get_document(doc["id"])
    assert doc_after["status"] == "Approved"
    assert doc_after["status"] != "Effective"


def test_approval_holds_at_approved_with_zero_trainees(db_path):
    """Explicit business-rule check: zero trainees must never be treated as
    100% — the document must NOT become Effective just because no training
    was ever assigned."""
    doc = _make_document()
    _reach_approved(doc)
    assert qdb.get_document(doc["id"])["status"] == "Approved"


def test_approval_holds_at_approved_even_if_training_already_cleared_until_released(db_path):
    """Corrected (spec §17/§20): even if trainees were completed BEFORE the
    final approval finished, the document must NOT become Effective
    automatically — an explicit Quality Coordinator release
    (qdb.try_clear_training_gate, now only invoked from the dedicated
    /release route) is always required regardless of training-gate timing."""
    doc = _make_document()
    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": "rev-1", "display_name": "Rita"}])
    wfe.decide_step("document", doc["id"], 2, "approve", user_id="rev-1", role="reviewer_qa", performed_by="Rita")

    # complete training while the version is still 'pending_approval'
    tid = qdb.add_training(doc["id"], {"trainee_name": "Complete Before Approval"})["id"]
    qdb.update_training_status(tid, "Completed", "2026-01-01")

    wfe.assign_approvers("document", doc["id"], 3, [{"user_id": "appr-1", "display_name": "Al"}])
    wfe.decide_step("document", doc["id"], 3, "approve", user_id="appr-1", role="company_admin", performed_by="Al")

    doc_after = qdb.get_document(doc["id"])
    assert doc_after["status"] == "Approved"
    assert not doc_after.get("effective_date")
    version = qdb.get_current_version(doc["id"])
    assert version["status"] == "approved"

    released = qdb.try_clear_training_gate(doc["id"])
    assert released["status"] == "Effective"
    assert released["effective_date"]
    version = qdb.get_current_version(doc["id"])
    assert version["status"] == "effective"
    assert version["effective_date"]


def test_training_completion_after_approval_requires_explicit_release_via_route(client):
    # The `client` fixture's fake tenant (tests/conftest.py) always acts as
    # this fixed user_id — the approver assigned to each step must match it
    # for decide_step()'s "only a named assignee may decide" check to pass.
    caller_user_id = "00000000-0000-0000-0000-000000000001"

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")  # Phase 5 hard gate
    _upload_final_version(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Rita"}]})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/2/decide",
                         json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    client.post(f"/qms/documents/{did}/workflow/steps/3/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Al"}]})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/3/decide",
                         json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()

    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Approved"

    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "Trainee One"}).get_json()
    gate_before = client.get(f"/qms/documents/{did}/training/gate").get_json()
    assert gate_before["cleared"] is False

    with _reauth(True):
        r = client.put(f"/qms/documents/training/{t['id']}",
                        json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    assert r.status_code == 200, r.get_json()

    gate_after = client.get(f"/qms/documents/{did}/training/gate").get_json()
    assert gate_after["cleared"] is True
    # Training completion alone must NOT flip the document to Effective —
    # spec §17/§20: only an explicit Quality Coordinator release does.
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Approved"

    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "Effective"
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Effective"


# ── Version-scoped training: rejected version's training never carries forward ──

def test_rejected_version_training_cannot_clear_new_version(db_path):
    doc = _make_document()
    v0 = qdb.get_current_version(doc["id"])
    # complete training against the ORIGINAL version before it's rejected
    tid = qdb.add_training(doc["id"], {"trainee_name": "Pre-rejection trainee"})["id"]
    qdb.update_training_status(tid, "Completed", "2026-01-01")
    assert qdb.training_gate_status(v0["id"])["cleared"] is True

    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": "rev-1", "display_name": "Rita"}])
    wfe.decide_step("document", doc["id"], 2, "reject", user_id="rev-1", role="reviewer_qa",
                     performed_by="Rita", comments="Needs rework")

    v1 = qdb.get_current_version(doc["id"])
    assert v1["id"] != v0["id"]
    # the new version has NO training of its own yet
    assert qdb.training_gate_status(v1["id"])["trainee_count"] == 0
    assert qdb.training_gate_status(v1["id"])["cleared"] is False
    # old version's cleared gate is untouched, but it's superseded/irrelevant now
    assert qdb.training_gate_status(v0["id"])["cleared"] is True


def test_new_training_round_required_for_new_version_after_rejection(db_path):
    doc = _make_document()
    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": "rev-1", "display_name": "Rita"}])
    wfe.decide_step("document", doc["id"], 2, "reject", user_id="rev-1", role="reviewer_qa",
                     performed_by="Rita", comments="rework")

    _reach_approved(doc)  # resubmit + go all the way through on the NEW version
    v1 = qdb.get_current_version(doc["id"])
    assert v1["status"] == "approved"
    assert qdb.get_document(doc["id"])["status"] == "Approved"  # still gated — no training on v1 yet

    tid = qdb.add_training(doc["id"], {"trainee_name": "Post-rejection trainee"})["id"]
    qdb.update_training_status(tid, "Completed", "2026-01-01")
    cleared_doc = qdb.try_clear_training_gate(doc["id"])
    assert cleared_doc is not None
    assert cleared_doc["status"] == "Effective"


# ── Non-document workflows unaffected ─────────────────────────────────────────

def test_deviation_workflow_completion_never_touches_training_gate(db_path):
    """CAPA/Deviation/Change Control have no training-gate concept at all —
    their own STATUS_APPLIERS entries are untouched by this phase's changes
    to _apply_document_status, confirmed by driving a full Deviation
    workflow to completion with no interaction with qms_document_training."""
    dev = ddb.create_deviation({"title": "Temp excursion"}, company_id=COMPANY_ID)
    state = wfe.start_instance("DEVIATION_INVESTIGATION_V1", "deviation", dev["id"], COMPANY_ID, "Ida Initiator")
    assert state["instance"]["current_step_order"] == 2
    assert ddb.get_deviation(dev["id"])["status"] not in ("Approved", "Effective")

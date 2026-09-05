"""
tests/test_document_chain_confirmation_gate.py — Phase 7A hard gate, ported
into this release alongside its existing Self-Check and Final Author
Version gates (neither replaces the other): the approval chain must be
explicitly re-confirmed for the CURRENT version before Submit for Review.
A chain last confirmed for a rejected or superseded version can never
silently satisfy its successor.

Design: qms_document_versions.chain_confirmed_at (TEXT DEFAULT ''),
identical in shape to self_check_completed_at — stamped by
qms_document_database.set_review_chain() on the current version every time
the Author assigns/re-confirms, and never carried forward since
_insert_version_row() always creates fresh rows with the column default.
The chain IDENTITY (reviewer/department_head/quality_head/plant_head)
still lives on qms_documents, unchanged, one row per document — this adds
a per-version confirmation flag on top, not a duplicate copy of who was
assigned.
"""

import io

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID

_CALLER_USER_ID = "00000000-0000-0000-0000-000000000001"  # the `client` fixture's fixed tenant user_id (Author)
_REVIEWER_USER_ID = "00000000-0000-0000-0000-000000000002"
_DEPT_HEAD_USER_ID = "00000000-0000-0000-0000-000000000003"
_QUALITY_HEAD_USER_ID = "00000000-0000-0000-0000-000000000004"

_FULL_CHAIN = {
    "reviewer_user_id": _REVIEWER_USER_ID, "reviewer_name": "Rita",
    "department_head_user_id": _DEPT_HEAD_USER_ID, "department_head_name": "Al",
    "quality_head_user_id": _QUALITY_HEAD_USER_ID, "quality_head_name": "Quinn",
}


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def _make_document():
    return qdb.create_document({"title": "Cleaning SOP", "content": "x"}, company_id=COMPANY_ID)


def _upload_final_version(client, did, text=b"final content"):
    r = client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(text), "final.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_json()


def _assign_chain(client, did, chain=None):
    r = client.post(f"/qms/documents/{did}/assign-chain", json=chain or _FULL_CHAIN)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ── A. Column exists for the current version, empty by default ────────────

def test_chain_confirmed_at_exists_on_current_version(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    assert "chain_confirmed_at" in version.keys()
    assert version["chain_confirmed_at"] == ""
    assert qdb.is_chain_confirmed(doc["id"]) is False


# ── B. Assigning/reassigning the chain confirms the current version ───────

def test_assigning_chain_confirms_current_version(db_path):
    doc = _make_document()
    qdb.set_review_chain(doc["id"], _FULL_CHAIN, assigned_by="Ada Author")
    assert qdb.is_chain_confirmed(doc["id"]) is True
    version = qdb.get_current_version(doc["id"])
    assert version["chain_confirmed_at"]


# ── C/D. A new version does not inherit confirmation, and an old version's
#         confirmation can never satisfy the new one ──────────────────────

def test_new_version_after_rejection_requires_fresh_chain_confirmation(db_path):
    from pharmagpt.services import workflow_engine as wfe

    doc = _make_document()
    qdb.record_self_check(doc["id"], "Ada Author")
    qdb.set_review_chain(doc["id"], _FULL_CHAIN, assigned_by="Ada Author")
    v0 = qdb.get_current_version(doc["id"])
    assert v0["chain_confirmed_at"]
    assert qdb.is_chain_confirmed(doc["id"]) is True

    wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", doc["id"], COMPANY_ID, "Ada Author")
    wfe.assign_approvers("document", doc["id"], 2, [{"user_id": _REVIEWER_USER_ID, "display_name": "Rita"}])
    wfe.decide_step("document", doc["id"], 2, "reject", user_id=_REVIEWER_USER_ID, role="reviewer_qa",
                     performed_by="Rita", comments="Needs rework")

    v1 = qdb.get_current_version(doc["id"])
    assert v1["id"] != v0["id"]
    assert v1["chain_confirmed_at"] == ""              # (C) never carried forward
    assert qdb.is_chain_confirmed(doc["id"]) is False  # (D) the old version's confirmation cannot satisfy this one

    # The chain IDENTITY itself is untouched — reused across revisions,
    # only its per-version *confirmation* was reset.
    chain = qdb.get_review_chain(qdb.get_document(doc["id"]))
    assert chain["reviewer"] and chain["department_head"] and chain["quality_head"]


# ── E. Submit for Review fails when the chain is complete but the current
#      version is not yet (re-)confirmed ──────────────────────────────────

def test_workflow_start_blocked_when_chain_complete_but_not_confirmed(client, monkeypatch):
    from pharmagpt.services import workflow_engine as wfe

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did)
    _assign_chain(client, did)

    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 201, r.get_json()

    wfe.assign_approvers("document", did, 2, [{"user_id": _REVIEWER_USER_ID, "display_name": "Rita"}])
    wfe.decide_step("document", did, 2, "reject", user_id=_REVIEWER_USER_ID, role="reviewer_qa",
                     performed_by="Rita", comments="Needs rework")

    # New Draft: chain identity is still complete on qms_documents (reused
    # across revisions), self-check and Final Author Version are satisfied
    # again below, but the chain has NOT been re-confirmed for this version.
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did, text=b"revised content")
    chain = qdb.get_review_chain(qdb.get_document(did))
    assert chain["reviewer"] and chain["department_head"] and chain["quality_head"]  # chain_complete is True
    assert qdb.is_chain_confirmed(did) is False

    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 409, r.get_json()
    assert "chain" in r.get_json()["error"].lower()


# ── F. Submit for Review succeeds once the current version IS confirmed and
#      every other TARGET gate is satisfied ────────────────────────────────

def test_workflow_start_succeeds_after_fresh_chain_confirmation(client, monkeypatch):
    from pharmagpt.services import workflow_engine as wfe

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did)
    _assign_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")

    wfe.assign_approvers("document", did, 2, [{"user_id": _REVIEWER_USER_ID, "display_name": "Rita"}])
    wfe.decide_step("document", did, 2, "reject", user_id=_REVIEWER_USER_ID, role="reviewer_qa",
                     performed_by="Rita", comments="Needs rework")

    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did, text=b"revised content")
    _assign_chain(client, did)  # re-confirms the chain for the new current version
    assert qdb.is_chain_confirmed(did) is True

    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 201, r.get_json()


# ── G. TARGET's own Final Author Version gate remains enforced (this port
#      is additive, not a replacement for it) ──────────────────────────────

def test_final_author_version_gate_still_enforced(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    _assign_chain(client, did)
    assert qdb.is_chain_confirmed(did) is True  # chain gate satisfied...

    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 409, r.get_json()   # ...but Final Author Version was never uploaded
    assert "final author version" in r.get_json()["error"].lower()

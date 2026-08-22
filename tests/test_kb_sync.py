"""
tests/test_kb_sync.py — Regression coverage for Phase 2's "approved documents
automatically become available in the Knowledge Base, no manual upload"
requirement (PHASE_2_IMPLEMENTATION_REPORT.md; services/kb_sync.py).

Covers all four integration points:
  - Document Control  -> Effective  (routes/qms_documents.py)
  - URS               -> Effective  (routes/urs.py)
  - Qualification      -> approved   (routes/qual.py, one KB entry per protocol)
  - Validation Report  -> released   (routes/report.py)

And the idempotent-upsert behaviour: re-approving the same record updates
the existing kb_documents row rather than creating a duplicate.
"""

import io

import pytest

from pharmagpt import database as db
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID


def _kb_rows_for(source_type: str, source_id: int):
    row = db.get_kb_document_by_source(source_type, source_id, BOOTSTRAP_COMPANY_ID)
    return [row] if row else []


def _self_check(client, did):
    """Document Control redesign (Phase 5, and gap-closure): Author
    Self-Check AND Final Author Version upload are both mandatory hard gates
    before Submit for Review can start — see routes/qms_documents.py's
    _SELF_CHECK_REQUIRED_ERROR / _FINAL_VERSION_REQUIRED_ERROR (spec §10:
    "The workflow must require Final Author Version before Review
    submission"). Applies to Document Control only (URS/Qualification/
    Validation Report below are unaffected). Kept under the original
    `_self_check` name so every existing call site here (13+) picks up the
    fix with no per-test change."""
    client.post(f"/qms/documents/{did}/self-check")
    r = client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(b"Final author-uploaded content."), "final.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_json()


def _clear_training_gate(client, did):
    """Document Control redesign (Phase 4, corrected per spec §17/§20):
    quorum/approval achieved holds a document at 'Approved' until the
    training gate clears (>=90% completion, >=1 trainee) AND an explicit
    Quality Coordinator release (POST .../release) is issued — training
    completion alone no longer auto-flips the document to Effective (see
    routes/qms_documents.py::release_document and
    tests/test_document_quality_release.py). This helper clears the gate
    and performs that release, so every existing caller here still reaches
    'Effective' exactly as before, just via the explicit call."""
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "KB Sync Test Trainee"}).get_json()
    client.put(f"/qms/documents/training/{t['id']}", json={"training_status": "Completed", "training_date": "2026-01-01"})
    client.post(f"/qms/documents/{did}/release", json={"meaning": "Released"})


_CALLER_USER_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py's fixed client-fixture tenant user_id


def _assign_chain(client, did):
    """SOP workflow correction: Submit for Review now additionally requires
    the Author to have assigned a complete Reviewer/Department Head/Quality
    Head chain first (Plant Head optional — never assigned here, so its
    step auto-skips). Kept as its own helper, called right before the
    existing "Submitted for Review"/"Approved" pair below, so every
    pre-existing call site here only needs one extra line.

    Every decision in this file is made by the SAME `client` fixture user
    (tests/conftest.py's fixed tenant) — assigning that one user_id to
    every required role (rather than distinct placeholder ids) is what lets
    each subsequent "Approved" call in _submit_and_fully_approve actually
    succeed: workflow_engine.decide_step()'s "only a named assignee may
    decide" check would otherwise 403/409 once the chain (not the legacy
    endpoint's now-inapplicable self-assign-if-empty fallback) has already
    named someone else."""
    r = client.post(f"/qms/documents/{did}/assign-chain", json={
        "reviewer_user_id": _CALLER_USER_ID, "reviewer_name": "Rita",
        "department_head_user_id": _CALLER_USER_ID, "department_head_name": "Dana",
        "quality_head_user_id": _CALLER_USER_ID, "quality_head_name": "Quinn",
    })
    assert r.status_code == 200, r.get_json()


def _submit_and_fully_approve(client, did):
    """Replaces the old single "Approved" call: Department Head/Quality
    Head are now sequential single-decider steps (3 and 4), not one shared
    quorum step, so reaching 'Approved' takes two decisions instead of one.
    Plant Head (step 5) auto-skips since _assign_chain never assigns one."""
    client.post(f"/qms/documents/{did}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qms/documents/{did}/approval", json={"action": "Approved"})
    return client.post(f"/qms/documents/{did}/approval", json={"action": "Approved"})


# ── Document Control ─────────────────────────────────────────────────────────

def test_effective_document_control_record_is_published_to_kb(client):
    doc = client.post("/qms/documents", json={"title": "Autoclave Operation SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP\n\nOperate the autoclave safely."})

    _self_check(client, doc["id"])
    _assign_chain(client, doc["id"])
    resp = _submit_and_fully_approve(client, doc["id"])
    assert resp.status_code == 201
    assert client.get(f"/qms/documents/{doc['id']}").get_json()["status"] == "Approved"
    _clear_training_gate(client, doc["id"])
    assert client.get(f"/qms/documents/{doc['id']}").get_json()["status"] == "Effective"

    rows = _kb_rows_for("document", doc["id"])
    assert len(rows) == 1
    assert rows[0]["title"] == "Autoclave Operation SOP"
    assert rows[0]["folder"] == "SOP"


def test_document_control_republish_updates_the_same_kb_row(client):
    doc = client.post("/qms/documents", json={"title": "Recalibration SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v1"})
    _self_check(client, doc["id"])
    _assign_chain(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])
    first_rows = _kb_rows_for("document", doc["id"])
    assert len(first_rows) == 1
    kb_id = first_rows[0]["id"]

    # Send the Effective document into a new revision cycle, revise, and
    # re-approve — Effective a second time. Document Control redesign
    # (fixed): starting a new revision cycle against an Effective document
    # is now its own explicit step (POST .../versions/start-revision) —
    # the old single-call "Rejected on Effective" shortcut is blocked
    # because a version it would fork can never already have a fresh
    # Self-Check recorded on it (see routes/qms_documents.py's
    # _submission_gate_error()). The chain assigned on the first cycle is
    # stored on the document itself and persists across revisions — no
    # need to reassign it here.
    r = client.post(f"/qms/documents/{doc['id']}/versions/start-revision")
    assert r.status_code == 201, r.get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v2 — revised"})
    _self_check(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])

    rows = _kb_rows_for("document", doc["id"])
    assert len(rows) == 1, "re-approval must update the existing KB row, not create a second one"
    assert rows[0]["id"] == kb_id


def test_document_without_content_cannot_reach_review_at_all(client):
    """Gap-closure (spec §10/§11): Final Author Version is now itself a hard
    gate before Submit for Review, and the upload endpoint rejects a file
    with no extractable text (routes/qms_documents.py::upload_final_author_version).
    A document can therefore no longer reach Effective — and so can no
    longer publish an empty KB entry — via the normal workflow at all, a
    stronger guarantee than the original Phase 2 "don't publish empty
    content" check this test used to exercise post-hoc."""
    doc = client.post("/qms/documents", json={"title": "Empty Draft SOP", "doc_type": "SOP"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/self-check")
    r = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    assert r.status_code == 409
    assert "Final Author Version" in r.get_json()["error"]
    assert _kb_rows_for("document", doc["id"]) == []


# ── URS ───────────────────────────────────────────────────────────────────────

def test_effective_urs_is_published_to_kb(client):
    urs = client.post("/urs/", json={"title": "HPLC URS", "equipment_name": "HPLC System"}).get_json()

    client.post(f"/urs/{urs['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/urs/{urs['id']}/approval", json={"action": "Approved"})
    resp = client.post(f"/urs/{urs['id']}/approval", json={"action": "Make Effective"})
    assert resp.status_code == 201

    rows = _kb_rows_for("urs", urs["id"])
    assert len(rows) == 1
    assert rows[0]["title"] == "HPLC URS"
    assert rows[0]["folder"] == "Validation"


def test_urs_not_yet_effective_is_not_published_to_kb(client):
    urs = client.post("/urs/", json={"title": "Draft-only URS", "equipment_name": "GC System"}).get_json()
    client.post(f"/urs/{urs['id']}/approval", json={"action": "Submitted for Review"})

    assert _kb_rows_for("urs", urs["id"]) == []


# ── Qualification (one KB entry per protocol) ────────────────────────────────

def test_approved_qualification_publishes_each_protocol_to_kb(client):
    qual = client.post("/qual/", json={"title": "HPLC Qualification", "equipment_name": "HPLC System"}).get_json()
    iq = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "IQ"}).get_json()
    oq = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "OQ"}).get_json()

    client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review"})
    resp = client.post(f"/qual/{qual['id']}/approval", json={"action": "Approved"})
    assert resp.status_code == 201

    iq_rows = _kb_rows_for("qualification_protocol", iq["id"])
    oq_rows = _kb_rows_for("qualification_protocol", oq["id"])
    assert len(iq_rows) == 1 and iq_rows[0]["folder"] == "Qualification"
    assert len(oq_rows) == 1 and oq_rows[0]["folder"] == "Qualification"


def test_qualification_republish_updates_the_same_protocol_kb_rows(client):
    qual = client.post("/qual/", json={"title": "GC Qualification", "equipment_name": "GC System"}).get_json()
    iq = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": "IQ"}).get_json()

    client.post(f"/qual/{qual['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qual/{qual['id']}/approval", json={"action": "Approved"})
    kb_id = _kb_rows_for("qualification_protocol", iq["id"])[0]["id"]

    client.post(f"/qual/{qual['id']}/approval", json={"action": "Approved"})
    rows = _kb_rows_for("qualification_protocol", iq["id"])
    assert len(rows) == 1
    assert rows[0]["id"] == kb_id


# ── Validation Report ─────────────────────────────────────────────────────────

def test_released_validation_report_is_published_to_kb(client):
    report = client.post("/report/", json={"title": "HPLC Validation Summary Report"}).get_json()

    client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review"})
    client.post(f"/report/{report['id']}/approval", json={"action": "QA Approved"})
    resp = client.post(f"/report/{report['id']}/approval", json={"action": "Released"})
    assert resp.status_code == 201

    rows = _kb_rows_for("report", report["id"])
    assert len(rows) == 1
    assert rows[0]["title"] == "HPLC Validation Summary Report"


def test_approved_but_not_released_report_is_not_published_to_kb(client):
    report = client.post("/report/", json={"title": "Pending Release Report"}).get_json()
    client.post(f"/report/{report['id']}/approval", json={"action": "Submit for Review"})
    client.post(f"/report/{report['id']}/approval", json={"action": "QA Approved"})

    assert _kb_rows_for("report", report["id"]) == []


# ── Phase 3: DQ/FAT/SAT consolidated into Document Control ──────────────────
# (routes/validation.py::_RETIRED_DOC_TYPES, qms_database.py::_DOC_TYPE_CODES)
# — they now get KB auto-sync "for free" via the same Document Control
# Effective-transition call every other doc_type already uses; no code in
# kb_sync.py itself needed changing.

@pytest.mark.parametrize("doc_type,expected_folder", [
    ("DQ", "Qualification"), ("FAT", "Protocols"), ("SAT", "Protocols"),
])
def test_consolidated_dq_fat_sat_are_published_to_kb(client, doc_type, expected_folder):
    doc = client.post("/qms/documents", json={"title": f"{doc_type} Protocol", "doc_type": doc_type}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": f"# {doc_type} Protocol\n\nTest content."})
    _self_check(client, doc["id"])
    _assign_chain(client, doc["id"])
    resp = _submit_and_fully_approve(client, doc["id"])
    assert resp.status_code == 201
    _clear_training_gate(client, doc["id"])

    rows = _kb_rows_for("document", doc["id"])
    assert len(rows) == 1
    assert rows[0]["folder"] == expected_folder


# ── Phase 3: version snapshot on re-publish (kb_document_versions) ──────────

def test_republish_snapshots_the_outgoing_version_instead_of_discarding_it(client):
    doc = client.post("/qms/documents", json={"title": "Versioned SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v1"})
    _self_check(client, doc["id"])
    _assign_chain(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])
    kb_row = _kb_rows_for("document", doc["id"])[0]

    client.post(f"/qms/documents/{doc['id']}/versions/start-revision")
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v2 — revised"})
    _self_check(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])

    versions = db.get_kb_versions(kb_row["id"])
    assert len(versions) == 1
    assert versions[0]["stored_filename"]


# ── RBF-001 Fix 2: creator attribution + audit trail for auto-published KB ──

def test_auto_published_kb_document_has_creator_attribution(client):
    doc = client.post("/qms/documents", json={"title": "Attributed SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP"})
    _self_check(client, doc["id"])
    _assign_chain(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])

    kb_row = _kb_rows_for("document", doc["id"])[0]
    assert kb_row["created_by"] == "Test User"  # conftest's fake authenticated tenant
    assert kb_row["updated_by"] == "Test User"


def test_auto_publish_logs_uploaded_audit_entry(client):
    doc = client.post("/qms/documents", json={"title": "Audited SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP"})
    _self_check(client, doc["id"])
    _assign_chain(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])

    kb_row = _kb_rows_for("document", doc["id"])[0]
    entries = client.get(f"/qms/kb_document/{kb_row['id']}/audit-trail").get_json()
    assert [e["action"] for e in entries] == ["Uploaded"]
    assert entries[0]["performed_by"] == "Test User"


def test_republish_logs_version_created_and_updated_audit_entries(client):
    doc = client.post("/qms/documents", json={"title": "Republished SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v1"})
    _self_check(client, doc["id"])
    _assign_chain(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])
    kb_row = _kb_rows_for("document", doc["id"])[0]

    client.post(f"/qms/documents/{doc['id']}/versions/start-revision")
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v2 — revised"})
    _self_check(client, doc["id"])
    _submit_and_fully_approve(client, doc["id"])
    _clear_training_gate(client, doc["id"])

    entries = client.get(f"/qms/kb_document/{kb_row['id']}/audit-trail").get_json()
    assert [e["action"] for e in entries] == ["Uploaded", "Version created", "Updated"]

    updated_row = db.get_kb_document(kb_row["id"])
    assert updated_row["updated_by"] == "Test User"

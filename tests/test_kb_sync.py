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

import pytest

from pharmagpt import database as db
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID


def _kb_rows_for(source_type: str, source_id: int):
    row = db.get_kb_document_by_source(source_type, source_id, BOOTSTRAP_COMPANY_ID)
    return [row] if row else []


# ── Document Control ─────────────────────────────────────────────────────────

def test_effective_document_control_record_is_published_to_kb(client):
    doc = client.post("/qms/documents", json={"title": "Autoclave Operation SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP\n\nOperate the autoclave safely."})

    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    resp = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Approved"})
    assert resp.status_code == 201

    rows = _kb_rows_for("document", doc["id"])
    assert len(rows) == 1
    assert rows[0]["title"] == "Autoclave Operation SOP"
    assert rows[0]["folder"] == "SOP"


def test_document_control_republish_updates_the_same_kb_row(client):
    doc = client.post("/qms/documents", json={"title": "Recalibration SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v1"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Approved"})
    first_rows = _kb_rows_for("document", doc["id"])
    assert len(first_rows) == 1
    kb_id = first_rows[0]["id"]

    # Send it back to Draft, revise, and re-approve — Effective a second time.
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Rejected"})
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v2 — revised"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Approved"})

    rows = _kb_rows_for("document", doc["id"])
    assert len(rows) == 1, "re-approval must update the existing KB row, not create a second one"
    assert rows[0]["id"] == kb_id


def test_document_without_content_is_not_published_to_kb(client):
    """An Effective document with no drafted content yet has nothing
    meaningful to publish — must not create an empty KB entry."""
    doc = client.post("/qms/documents", json={"title": "Empty Draft SOP", "doc_type": "SOP"}).get_json()
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Approved"})

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
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    resp = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Approved"})
    assert resp.status_code == 201

    rows = _kb_rows_for("document", doc["id"])
    assert len(rows) == 1
    assert rows[0]["folder"] == expected_folder


# ── Phase 3: version snapshot on re-publish (kb_document_versions) ──────────

def test_republish_snapshots_the_outgoing_version_instead_of_discarding_it(client):
    doc = client.post("/qms/documents", json={"title": "Versioned SOP", "doc_type": "SOP"}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v1"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Approved"})
    kb_row = _kb_rows_for("document", doc["id"])[0]

    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Rejected"})
    client.put(f"/qms/documents/{doc['id']}", json={"content": "# SOP v2 — revised"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Approved"})

    versions = db.get_kb_versions(kb_row["id"])
    assert len(versions) == 1
    assert versions[0]["stored_filename"]

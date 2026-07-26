"""
tests/test_creator_attribution.py — RBF-001 Fix 2 (P0 release blocker):
Projects and Knowledge Base documents must carry created_by/created_at/
updated_by/updated_at, and existing rows must be safely backfilled (no data
loss, no fabricated actors).
"""

import sqlite3

from pharmagpt import database as db


def test_create_project_sets_creator_and_updated_fields(db_path):
    project = db.create_project(
        name="HPLC IQ", equipment_name="Agilent HPLC 1260", manufacturer="Agilent",
        department="QC", validation_type="IQ/OQ/PQ",
        company_id="test-company-1", created_by="Jane Reviewer",
    )
    assert project["created_by"] == "Jane Reviewer"
    assert project["updated_by"] == "Jane Reviewer"
    assert project["updated_at"] == project["created_at"]


def test_update_project_refreshes_updated_by_and_updated_at(db_path):
    project = db.create_project(
        name="HPLC IQ", equipment_name="Agilent HPLC 1260", manufacturer="Agilent",
        department="QC", validation_type="IQ/OQ/PQ",
        company_id="test-company-1", created_by="Jane Reviewer",
    )
    updated = db.update_project(
        project["id"], {"name": "HPLC IQ — renamed"}, updated_by="John Approver",
    )
    assert updated["created_by"] == "Jane Reviewer"  # creator is immutable
    assert updated["updated_by"] == "John Approver"
    assert updated["updated_at"] >= project["updated_at"]


def test_create_kb_document_sets_creator_and_updated_fields(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-001", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop.pdf",
        stored_filename="sop_stored.pdf", file_type="pdf", file_size=100,
        company_id="test-company-1", created_by="Jane Reviewer",
    )
    assert kb_doc["created_by"] == "Jane Reviewer"
    assert kb_doc["updated_by"] == "Jane Reviewer"
    assert kb_doc["updated_at"] == kb_doc["upload_date"]


def test_update_kb_document_file_refreshes_updated_by(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-001", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop.pdf",
        stored_filename="sop_stored.pdf", file_type="pdf", file_size=100,
        company_id="test-company-1", created_by="Jane Reviewer",
    )
    updated = db.update_kb_document_file(
        kb_doc["id"], title="SOP-001 v2", doc_version="2.0", effective_date=None,
        original_name="sop_v2.pdf", stored_filename="sop_v2_stored.pdf",
        file_type="pdf", file_size=200, updated_by="John Approver",
    )
    assert updated["created_by"] == "Jane Reviewer"
    assert updated["updated_by"] == "John Approver"
    assert updated["doc_version"] == "2.0"


def test_kb_document_list_endpoint_includes_creator_fields(db_path):
    """get_kb_documents() (the list projection, used by GET /kb/documents)
    curates its own column list separately from get_kb_document() (single
    record) — a fix landing on one must not silently miss the other."""
    db.create_kb_document(
        title="SOP-001", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop.pdf",
        stored_filename="sop_stored.pdf", file_type="pdf", file_size=100,
        company_id="test-company-1", created_by="Jane Reviewer",
    )
    rows = db.get_kb_documents(company_id="test-company-1")
    assert rows[0]["created_by"] == "Jane Reviewer"
    assert rows[0]["updated_by"] == "Jane Reviewer"
    assert rows[0]["updated_at"]


def test_legacy_project_backfilled_created_by_from_audit_trail(db_path):
    """Simulates a pre-Fix-2 row (created before created_by/updated_by/
    updated_at existed) that already has a 'Project created' audit-trail
    entry — re-running init_db() must recover created_by from that entry
    rather than leaving it blank, and must never lose or alter the row."""
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        "INSERT INTO projects (name, company_id, created_by, updated_by) "
        "VALUES ('Legacy Project', 'test-company-1', '', '')"
    )
    legacy_id = conn.execute("SELECT id FROM projects WHERE name = 'Legacy Project'").fetchone()[0]
    conn.execute(
        "INSERT INTO qms_audit_trail (record_type, record_id, action, performed_by) "
        "VALUES ('project', ?, 'Project created', 'Historical Actor')",
        (legacy_id,),
    )
    conn.commit()
    conn.close()

    db.init_db()  # re-run the migration/backfill against the same DB_PATH

    project = db.get_project(legacy_id)
    assert project["name"] == "Legacy Project"  # no data loss
    assert project["created_by"] == "Historical Actor"


def test_legacy_project_without_audit_entry_stays_blank_not_fabricated(db_path):
    """No matching audit-trail entry exists — created_by must stay '' rather
    than being guessed/fabricated."""
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        "INSERT INTO projects (name, company_id, created_by, updated_by) "
        "VALUES ('Orphan Legacy Project', 'test-company-1', '', '')"
    )
    legacy_id = conn.execute(
        "SELECT id FROM projects WHERE name = 'Orphan Legacy Project'"
    ).fetchone()[0]
    conn.commit()
    conn.close()

    db.init_db()

    project = db.get_project(legacy_id)
    assert project["name"] == "Orphan Legacy Project"
    assert project["created_by"] == ""

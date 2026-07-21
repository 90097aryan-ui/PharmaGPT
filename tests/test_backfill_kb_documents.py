"""
tests/test_backfill_kb_documents.py — scripts/backfill_kb_documents.py,
fully mocked against the Supabase client and a throwaway SQLite database.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pharmagpt import database as db
from scripts.backfill_kb_documents import backfill_kb_documents


def test_backfill_kb_documents_migrates_and_records_postgres_id(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="quality,sop", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    company_id="test-company-1")
    db.update_kb_document_text(kb_doc["id"], "extracted text here", 3, 1, "ok")

    responses = iter([
        SimpleNamespace(data=[]),                         # find category -> none
        SimpleNamespace(data=[{"id": "cat-sop"}]),         # create category
        SimpleNamespace(data=[{"id": "pg-doc-1"}]),        # insert documents
        SimpleNamespace(data=[{"id": "pg-ver-1"}]),        # insert document_versions
        SimpleNamespace(data=None),                        # update current_version_id
        SimpleNamespace(data=[]),                          # find tag "quality" -> none
        SimpleNamespace(data=[{"id": "tag-quality"}]),      # create tag "quality"
        SimpleNamespace(data=None),                         # insert document_tags
        SimpleNamespace(data=[]),                           # find tag "sop" -> none
        SimpleNamespace(data=[{"id": "tag-sop"}]),          # create tag "sop"
        SimpleNamespace(data=None),                         # insert document_tags
    ])
    q = MagicMock()
    q.select.return_value = q
    q.insert.return_value = q
    q.update.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.execute.side_effect = lambda: next(responses)
    client = MagicMock()
    client.table.return_value = q

    summary = backfill_kb_documents(client, "company-1")

    assert summary == {"migrated": 1, "skipped_already_migrated": 0}
    assert db.get_kb_document(kb_doc["id"])["postgres_id"] == "pg-doc-1"

    version_payload = None
    for call in q.insert.call_args_list:
        (payload,) = call.args
        if "extracted_text" in payload:
            version_payload = payload
    assert version_payload["extracted_text"] == "extracted text here"
    assert version_payload["storage_path"] == "uploads/kb/stored1.pdf"


def test_backfill_kb_documents_skips_already_migrated(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    company_id="test-company-1")
    db.set_kb_document_postgres_id(kb_doc["id"], "already-there")

    client = MagicMock()

    summary = backfill_kb_documents(client, "company-1")

    assert summary == {"migrated": 0, "skipped_already_migrated": 1}
    client.table.assert_not_called()

"""
tests/test_check_kb_parity.py — scripts/check_kb_parity.py, fully mocked
against the Supabase client and a throwaway SQLite database.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pharmagpt import database as db
from scripts.check_kb_parity import check_kb_parity


def _query_mock(execute_return):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.maybe_single.return_value = q
    q.execute.return_value = execute_return
    return q


def test_check_parity_skips_documents_never_migrated(db_path):
    db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    )
    client = MagicMock()

    drifted = check_kb_parity(client)

    assert drifted == []
    client.table.assert_not_called()


def test_check_parity_flags_missing_in_postgres(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    )
    db.set_kb_document_postgres_id(kb_doc["id"], "pg-doc-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=None))

    drifted = check_kb_parity(client)

    assert len(drifted) == 1
    assert drifted[0]["issue"] == "missing_in_postgres"


def test_check_parity_passes_when_folder_and_status_match(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    )
    db.set_kb_document_postgres_id(kb_doc["id"], "pg-doc-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "status": "approved", "document_categories": {"name": "SOP"},
    }))

    drifted = check_kb_parity(client)

    assert drifted == []


def test_check_parity_flags_folder_drift(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    )
    db.set_kb_document_postgres_id(kb_doc["id"], "pg-doc-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "status": "approved", "document_categories": {"name": "Regulations"},
    }))

    drifted = check_kb_parity(client)

    assert len(drifted) == 1
    assert "folder" in drifted[0]["diffs"]


def test_check_parity_flags_unexpected_status(db_path):
    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    )
    db.set_kb_document_postgres_id(kb_doc["id"], "pg-doc-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "status": "draft", "document_categories": {"name": "SOP"},
    }))

    drifted = check_kb_parity(client)

    assert len(drifted) == 1
    assert "status" in drifted[0]["diffs"]

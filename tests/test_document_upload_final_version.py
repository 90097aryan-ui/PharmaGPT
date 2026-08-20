"""
tests/test_document_upload_final_version.py — Phase 5 coverage: Upload
Final Author Version becomes the authoritative content for the current
Draft version, reusing the existing attachment-storage and text-extraction
pipelines rather than creating a competing source of truth.
"""

import io

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def test_upload_becomes_authoritative_content(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    did = doc["id"]

    r = client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(b"# Cleaning SOP\n\nFinal author-edited procedure text."), "final.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_json()
    version = r.get_json()
    assert "Final author-edited procedure text" in version["content_snapshot"]
    assert version["source_attachment_id"]

    # qms_documents.content mirrors it (single source of truth, no duplicate)
    assert "Final author-edited procedure text" in client.get(f"/qms/documents/{did}").get_json()["content"]


def test_upload_blocked_once_not_draft(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    client.post(f"/qms/documents/{did}/workflow/start")

    r = client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(b"too late"), "late.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 409


def test_upload_rejects_disallowed_extension(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    r = client.post(
        f"/qms/documents/{doc['id']}/versions/upload",
        data={"file": (io.BytesIO(b"MZ\x90\x00"), "malware.exe")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_upload_creates_attachment_record(client):
    from pharmagpt import qms_database as qmsdb
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    did = doc["id"]

    client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(b"Real procedure content for the SOP."), "procedure.txt")},
        content_type="multipart/form-data",
    )

    attachments = qmsdb.get_attachments("document", did)
    assert len(attachments) == 1
    assert attachments[0]["description"] == "Final Author Version"


def test_no_file_returns_400(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/versions/upload", data={}, content_type="multipart/form-data")
    assert r.status_code == 400

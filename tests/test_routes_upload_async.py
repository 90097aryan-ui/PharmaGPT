"""
tests/test_routes_upload_async.py — Integration tests through Flask's test
client: upload returns immediately with status "pending", polling reaches a
terminal state, and the retry endpoint works after a forced failure.

Each test depends on the `db_path` fixture (tests/conftest.py) which points
pharmagpt.database at a fresh temp SQLite file *before* pharmagpt.app is ever
imported, so these tests never touch the real development database.
"""

import io
import time

import pytest


def _wait_for_terminal_status(client, url, timeout=10.0):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = client.get(url).get_json()
        if status.get("extraction_status") not in ("pending", "processing"):
            return status
        time.sleep(0.1)
    pytest.fail(f"extraction never reached a terminal status: {status}")


def test_project_document_upload_is_fast_then_completes(client, fixtures_dir):
    proj = client.post("/projects", json={
        "name": "Test Project", "equipment_name": "HPLC", "manufacturer": "Agilent",
        "department": "QC", "validation_type": "IQ",
    }).get_json()

    with open(fixtures_dir["small.pdf"], "rb") as fh:
        pdf_bytes = fh.read()

    start = time.monotonic()
    resp = client.post(
        f"/projects/{proj['id']}/documents",
        data={"file": (io.BytesIO(pdf_bytes), "manual.pdf")},
        content_type="multipart/form-data",
    )
    upload_elapsed = time.monotonic() - start

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["extraction_status"] == "pending"
    # The whole point of this redesign: the HTTP response must not wait on
    # extraction, no matter the document size.
    assert upload_elapsed < 1.0

    status = _wait_for_terminal_status(client, f"/documents/{body['id']}/status")
    assert status["extraction_status"] == "ok"
    assert status["page_count"] == 5


def test_kb_document_upload_and_retry_flow(client, fixtures_dir):
    with open(fixtures_dir["corrupted.pdf"], "rb") as fh:
        corrupt_bytes = fh.read()

    resp = client.post(
        "/kb/documents",
        data={
            "file": (io.BytesIO(corrupt_bytes), "broken.pdf"),
            "title": "Broken Manual", "folder": "SOP",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    kb_id = resp.get_json()["id"]

    status = _wait_for_terminal_status(client, f"/kb/documents/{kb_id}/status")
    assert status["extraction_status"] == "failed"

    # File is preserved, and retry re-runs extraction rather than losing it.
    retry_resp = client.post(f"/kb/documents/{kb_id}/retry")
    assert retry_resp.status_code == 202
    assert retry_resp.get_json()["status"] == "pending"

    status_after_retry = _wait_for_terminal_status(client, f"/kb/documents/{kb_id}/status")
    assert status_after_retry["extraction_status"] == "failed"  # still corrupt — expected


def test_document_status_endpoint_404_for_unknown_document(client):
    resp = client.get("/documents/999999/status")
    assert resp.status_code == 404


def test_project_document_retry_requires_file_present_on_disk(client, fixtures_dir):
    proj = client.post("/projects", json={
        "name": "P2", "equipment_name": "X", "manufacturer": "Y",
        "department": "Z", "validation_type": "IQ",
    }).get_json()

    with open(fixtures_dir["small.pdf"], "rb") as fh:
        pdf_bytes = fh.read()

    doc = client.post(
        f"/projects/{proj['id']}/documents",
        data={"file": (io.BytesIO(pdf_bytes), "manual.pdf")},
        content_type="multipart/form-data",
    ).get_json()

    _wait_for_terminal_status(client, f"/documents/{doc['id']}/status")

    # Delete the file from disk directly, then retry should fail gracefully.
    import os

    from pharmagpt import documents as doc_utils
    os.remove(doc_utils.get_file_path(proj["id"], doc["stored_filename"]))

    retry_resp = client.post(f"/documents/{doc['id']}/retry")
    assert retry_resp.status_code == 404

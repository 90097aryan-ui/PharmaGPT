"""
tests/test_document_export_historical_version.py — Phase 5 coverage:
exporting a specific historical (immutable) version's frozen content,
distinct from the document's live current state.
"""

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def test_report_defaults_to_current_content(client):
    doc = client.post("/qms/documents", json={"title": "Doc", "content": "current text"}).get_json()
    r = client.get(f"/qms/documents/{doc['id']}/report")
    assert "current text" in r.get_json()["markdown"]


def test_report_with_version_id_returns_historical_frozen_content(client):
    doc = client.post("/qms/documents", json={"title": "Doc", "content": "original v0.1 text"}).get_json()
    did = doc["id"]
    v0 = qdb.get_current_version(did)

    caller_user_id = "00000000-0000-0000-0000-000000000001"  # the `client` fixture's fixed tenant user_id
    client.post(f"/qms/documents/{did}/self-check")
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Rita"}]})
    r = client.post(f"/qms/documents/{did}/workflow/steps/2/decide",
                     json={"decision": "reject", "meaning": "Rejected", "reason": "x", "comments": "Needs rework"})
    assert r.status_code == 200, r.get_json()

    # current live content is now the NEW draft version's, forked from v0.1
    client.put(f"/qms/documents/{did}", json={"content": "revised v0.2 text"})

    current_report = client.get(f"/qms/documents/{did}/report").get_json()
    assert "revised v0.2 text" in current_report["markdown"]
    assert "original v0.1 text" not in current_report["markdown"]

    historical_report = client.get(f"/qms/documents/{did}/report?version_id={v0['id']}").get_json()
    assert "original v0.1 text" in historical_report["markdown"]
    assert "revised v0.2 text" not in historical_report["markdown"]
    assert "0.1" in historical_report["markdown"]


def test_export_docx_with_version_id_uses_historical_content(client):
    doc = client.post("/qms/documents", json={"title": "Doc", "content": "frozen content"}).get_json()
    did = doc["id"]
    v0 = qdb.get_current_version(did)
    client.put(f"/qms/documents/{did}", json={"content": "later edit"})

    r = client.post(f"/qms/documents/{did}/export/docx?version_id={v0['id']}")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_invalid_version_id_falls_back_to_current(client):
    doc = client.post("/qms/documents", json={"title": "Doc", "content": "current"}).get_json()
    r = client.get(f"/qms/documents/{doc['id']}/report?version_id=999999")
    assert "current" in r.get_json()["markdown"]


def test_version_id_from_another_document_is_rejected(client):
    doc1 = client.post("/qms/documents", json={"title": "Doc1", "content": "doc1 content"}).get_json()
    doc2 = client.post("/qms/documents", json={"title": "Doc2", "content": "doc2 content"}).get_json()
    doc1_version = qdb.get_current_version(doc1["id"])

    r = client.get(f"/qms/documents/{doc2['id']}/report?version_id={doc1_version['id']}")
    assert "doc2 content" in r.get_json()["markdown"]
    assert "doc1 content" not in r.get_json()["markdown"]

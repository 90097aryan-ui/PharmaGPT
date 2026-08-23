"""
tests/test_document_export_historical_version.py — Phase 5 coverage:
exporting a specific historical (immutable) version's frozen content,
distinct from the document's live current state.

Deliberately no autouse app_context fixture (see test_document_quality_
release.py's identical note / feedback_flask_test_app_context_gotcha) —
holding one open across every client.post() call in a test makes Flask
reuse that single `g` for every request instead of pushing a fresh one per
call, so a mid-test TenantContext monkeypatch would never actually be
re-read by conftest.py's before_request shim. The bare qdb.get_current_
version() calls below don't need an app context at all — database.py's
DB_PATH is a plain module attribute, not Flask-app-bound.
"""

import io

from pharmagpt import qms_document_database as qdb
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID


def test_report_defaults_to_current_content(client):
    doc = client.post("/qms/documents", json={"title": "Doc", "content": "current text"}).get_json()
    r = client.get(f"/qms/documents/{doc['id']}/report")
    assert "current text" in r.get_json()["markdown"]


def test_report_with_version_id_returns_historical_frozen_content(client, monkeypatch):
    doc = client.post("/qms/documents", json={"title": "Doc", "content": "original v0.1 text"}).get_json()
    did = doc["id"]
    v0 = qdb.get_current_version(did)

    # P0 stabilization: segregation of duties forbids the Author (the
    # `client` fixture's fixed tenant user_id) from also being an approver,
    # so Reviewer/Department Head/Quality Head are distinct identities here.
    reviewer_user_id = "00000000-0000-0000-0000-000000000002"
    client.post(f"/qms/documents/{did}/self-check")
    client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(b"original v0.1 text (final)"), "final.txt")},
        content_type="multipart/form-data",
    )
    # SOP workflow correction: Submit for Review requires the Author to have
    # assigned a complete Reviewer/Department Head/Quality Head chain first.
    client.post(f"/qms/documents/{did}/assign-chain", json={
        "reviewer_user_id": reviewer_user_id, "reviewer_name": "Rita",
        "department_head_user_id": "00000000-0000-0000-0000-000000000003", "department_head_name": "Al",
        "quality_head_user_id": "00000000-0000-0000-0000-000000000004", "quality_head_name": "Quinn",
    })
    client.post(f"/qms/documents/{did}/workflow/start")
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id=reviewer_user_id, email="reviewer@example.com", display_name="Rita",
        role="user", company_id=conftest_module._TEST_TENANT.company_id))
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

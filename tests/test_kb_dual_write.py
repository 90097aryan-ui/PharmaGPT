"""
tests/test_kb_dual_write.py — Phase 3.3 dual-write coverage
(docs/PHASE3_EXECUTION_PLAN.md).

Same pattern as tests/test_projects_dual_write.py: real pharmagpt.app +
real middleware, pharmagpt.routes.knowledge_base.kb_repo mocked so no real
Supabase/Postgres call is made. Uploads a plain .txt file to avoid pulling
in the PDF extraction pipeline's timing/async behavior — irrelevant to
what's under test here (the dual-write orchestration).
"""

import io
from unittest.mock import patch

import pytest

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt.auth.context import TenantContext

SAMPLE_TENANT = TenantContext(
    user_id="user-1", email="jane@example.com", display_name="Jane Admin",
    role="company_admin", company_id="company-1",
)

SUPER_ADMIN_TENANT = TenantContext(
    user_id="super-1", email="super@example.com", display_name="Super Admin",
    role="super_admin", company_id=None,
)

AUTH_HEADERS = {"Authorization": "Bearer good-token"}


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


@pytest.fixture()
def authed():
    return patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SAMPLE_TENANT
    )


def _upload(client, **form_overrides):
    form = {
        "file": (io.BytesIO(b"hello world"), "note.txt"),
        "title": "Test Note",
        "folder": "SOP",
        "tags": "quality,sop",
    }
    form.update(form_overrides)
    return client.post("/kb/documents", data=form, content_type="multipart/form-data", headers=AUTH_HEADERS)


def test_dual_write_disabled_by_default(client, authed, monkeypatch):
    monkeypatch.setattr(config, "KB_BACKEND", "sqlite")
    with authed, patch("pharmagpt.routes.knowledge_base.kb_repo.create_kb_document") as mock_create:
        resp = _upload(client)

    assert resp.status_code == 201
    mock_create.assert_not_called()
    assert db.get_kb_document(resp.get_json()["id"])["postgres_id"] is None


def test_dual_write_create_calls_repo_and_stores_postgres_id(client, authed, monkeypatch):
    monkeypatch.setattr(config, "KB_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.knowledge_base.kb_repo.create_kb_document",
        return_value={"document_id": "pg-doc-1", "version_id": "pg-ver-1"},
    ) as mock_create:
        resp = _upload(client)

    assert resp.status_code == 201
    kb_id = resp.get_json()["id"]
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args[0] == "good-token"
    assert args[1] == "company-1"
    assert kwargs["title"] == "Test Note"
    assert kwargs["folder"] == "SOP"
    assert kwargs["tags_csv"] == "quality,sop"
    assert db.get_kb_document(kb_id)["postgres_id"] == "pg-doc-1"


def test_dual_write_create_failure_does_not_break_response(client, authed, monkeypatch):
    monkeypatch.setattr(config, "KB_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.knowledge_base.kb_repo.create_kb_document",
        side_effect=RuntimeError("Postgres unreachable"),
    ):
        resp = _upload(client)

    assert resp.status_code == 201
    kb_id = resp.get_json()["id"]
    assert db.get_kb_document(kb_id) is not None
    assert db.get_kb_document(kb_id)["postgres_id"] is None


def test_dual_write_skips_super_admin_with_no_company(client, monkeypatch):
    monkeypatch.setattr(config, "KB_BACKEND", "dual")
    with patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SUPER_ADMIN_TENANT
    ), patch("pharmagpt.routes.knowledge_base.kb_repo.create_kb_document") as mock_create:
        resp = _upload(client)

    assert resp.status_code == 201
    mock_create.assert_not_called()


def test_dual_write_delete_archives_instead_of_hard_delete(client, authed, monkeypatch):
    monkeypatch.setattr(config, "KB_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.knowledge_base.kb_repo.create_kb_document",
        return_value={"document_id": "pg-doc-2", "version_id": "pg-ver-2"},
    ):
        create_resp = _upload(client)
    kb_id = create_resp.get_json()["id"]

    with authed, patch(
        "pharmagpt.routes.knowledge_base.kb_repo.archive_document"
    ) as mock_archive:
        resp = client.delete(f"/kb/documents/{kb_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    mock_archive.assert_called_once_with("good-token", "company-1", "pg-doc-2")


def test_dual_write_delete_skipped_without_prior_postgres_id(client, authed, monkeypatch):
    monkeypatch.setattr(config, "KB_BACKEND", "sqlite")
    with authed:
        create_resp = _upload(client)
    kb_id = create_resp.get_json()["id"]

    monkeypatch.setattr(config, "KB_BACKEND", "dual")
    with authed, patch("pharmagpt.routes.knowledge_base.kb_repo.archive_document") as mock_archive:
        resp = client.delete(f"/kb/documents/{kb_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    mock_archive.assert_not_called()

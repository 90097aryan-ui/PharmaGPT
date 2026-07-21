"""
tests/test_equipment_dual_write.py — Phase 3.4 dual-write coverage
(docs/PHASE3_EXECUTION_PLAN.md).

Same pattern as tests/test_projects_dual_write.py and
tests/test_kb_dual_write.py: real pharmagpt.app + real middleware,
pharmagpt.routes.equipment.equipment_repo mocked so no real Supabase/
Postgres call is made.
"""

from unittest.mock import patch

import pytest

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb
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


def _create_project(client):
    return client.post("/projects", json={
        "name": "HPLC IQ", "equipment_name": "Agilent HPLC 1260", "manufacturer": "Agilent",
        "department": "QC", "validation_type": "IQ/OQ/PQ",
    }, headers=AUTH_HEADERS).get_json()


def _create_equipment(client, project_id, **overrides):
    payload = {"name": "HPLC System 1", "manufacturer": "Agilent"}
    payload.update(overrides)
    return client.post(f"/projects/{project_id}/equipment", json=payload, headers=AUTH_HEADERS)


def test_dual_write_disabled_by_default(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "sqlite")
    with authed:
        project = _create_project(client)
        with patch("pharmagpt.routes.equipment.equipment_repo.create_equipment") as mock_create:
            resp = _create_equipment(client, project["id"])

    assert resp.status_code == 201
    mock_create.assert_not_called()
    assert equipdb.get_equipment(resp.get_json()["id"])["postgres_id"] is None


def test_dual_write_create_calls_repo_and_stores_postgres_id(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-1"},
        ) as mock_create:
            resp = _create_equipment(client, project["id"])

    assert resp.status_code == 201
    equipment_id = resp.get_json()["id"]
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[0] == "good-token"
    assert args[1] == "company-1"
    assert equipdb.get_equipment(equipment_id)["postgres_id"] == "pg-equip-1"


def test_dual_write_create_failure_does_not_break_response(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            side_effect=RuntimeError("Postgres unreachable"),
        ):
            resp = _create_equipment(client, project["id"])

    assert resp.status_code == 201
    assert equipdb.get_equipment(resp.get_json()["id"]) is not None


def test_super_admin_cannot_create_equipment(client, authed, monkeypatch):
    """Equipment is nested under a Project route, and Super Admin (no
    company_id) has no standing access to any company's Projects
    (PLATFORM_ARCHITECTURE.md §7) — so the project lookup itself resolves to
    "not found" for them, same as any caller outside that project's company,
    before either the SQLite write or the Postgres dual-write ever runs.
    The project itself is created by a real company_admin tenant first."""
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)

    with patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SUPER_ADMIN_TENANT
    ), patch("pharmagpt.routes.equipment.equipment_repo.create_equipment") as mock_create:
        resp = _create_equipment(client, project["id"])

    assert resp.status_code == 404
    mock_create.assert_not_called()


def test_dual_write_update_calls_repo_when_postgres_id_present(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-2"},
        ):
            equipment_id = _create_equipment(client, project["id"]).get_json()["id"]

        with patch(
            "pharmagpt.routes.equipment.equipment_repo.update_equipment", return_value={"id": "pg-equip-2"}
        ) as mock_update:
            resp = client.put(
                f"/equipment/{equipment_id}", json={"name": "Renamed"}, headers=AUTH_HEADERS
            )

    assert resp.status_code == 200
    mock_update.assert_called_once()
    args, _ = mock_update.call_args
    assert args[2] == "pg-equip-2"


def test_dual_write_delete_calls_repo_with_postgres_id(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-3"},
        ):
            equipment_id = _create_equipment(client, project["id"]).get_json()["id"]

        with patch("pharmagpt.routes.equipment.equipment_repo.delete_equipment") as mock_delete:
            resp = client.delete(f"/equipment/{equipment_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    mock_delete.assert_called_once_with("good-token", "company-1", "pg-equip-3")


def test_dual_write_delete_swallows_restrict_failure(client, authed, monkeypatch):
    """Postgres RESTRICTs deleting equipment that still has equipment_links —
    this must never surface to the caller (SQLite delete already succeeded)."""
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-4"},
        ):
            equipment_id = _create_equipment(client, project["id"]).get_json()["id"]

        with patch(
            "pharmagpt.routes.equipment.equipment_repo.delete_equipment",
            side_effect=RuntimeError("FK restrict"),
        ):
            resp = client.delete(f"/equipment/{equipment_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200


def test_dual_write_link_skips_project_sourced_documents(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-5"},
        ):
            equipment_id = _create_equipment(client, project["id"]).get_json()["id"]

        doc = db.save_document(project["id"], "manual.pdf", "stored.pdf", "pdf", 100)

        with patch("pharmagpt.routes.equipment.equipment_repo.link_kb_document") as mock_link:
            resp = client.post(
                f"/equipment/{equipment_id}/documents",
                json={"document_role": "user_manual", "source_type": "project", "source_id": doc["id"]},
                headers=AUTH_HEADERS,
            )

    assert resp.status_code == 201
    mock_link.assert_not_called()


def test_dual_write_link_kb_document_calls_repo_when_both_sides_migrated(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-6"},
        ):
            equipment_id = _create_equipment(client, project["id"]).get_json()["id"]

        kb_doc = db.create_kb_document(
            title="SOP-1", folder="SOP", tags="", doc_version="1.0",
            effective_date=None, review_date=None, original_name="sop1.pdf",
            stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
        company_id="company-1")
        db.set_kb_document_postgres_id(kb_doc["id"], "pg-kb-doc-1")

        with patch(
            "pharmagpt.routes.equipment.equipment_repo.link_kb_document",
            return_value={"id": "pg-link-1"},
        ) as mock_link:
            resp = client.post(
                f"/equipment/{equipment_id}/documents",
                json={"document_role": "sop", "source_type": "kb", "source_id": kb_doc["id"]},
                headers=AUTH_HEADERS,
            )
        link_id = resp.get_json()["id"]

    assert resp.status_code == 201
    mock_link.assert_called_once_with("good-token", "company-1", "pg-equip-6", "pg-kb-doc-1")
    assert equipdb.get_equipment_document_link(link_id)["postgres_id"] == "pg-link-1"


def test_dual_write_link_skipped_when_kb_document_not_migrated_yet(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-7"},
        ):
            equipment_id = _create_equipment(client, project["id"]).get_json()["id"]

        kb_doc = db.create_kb_document(
            title="SOP-2", folder="SOP", tags="", doc_version="1.0",
            effective_date=None, review_date=None, original_name="sop2.pdf",
            stored_filename="stored2.pdf", file_type="pdf", file_size=1024,
        company_id="company-1")
        # no postgres_id set on kb_doc -> not migrated yet

        with patch("pharmagpt.routes.equipment.equipment_repo.link_kb_document") as mock_link:
            resp = client.post(
                f"/equipment/{equipment_id}/documents",
                json={"document_role": "sop", "source_type": "kb", "source_id": kb_doc["id"]},
                headers=AUTH_HEADERS,
            )

    assert resp.status_code == 201
    mock_link.assert_not_called()


def test_dual_write_unlink_calls_repo_with_postgres_id(client, authed, monkeypatch):
    monkeypatch.setattr(config, "EQUIPMENT_BACKEND", "dual")
    with authed:
        project = _create_project(client)
        with patch(
            "pharmagpt.routes.equipment.equipment_repo.create_equipment",
            return_value={"id": "pg-equip-8"},
        ):
            equipment_id = _create_equipment(client, project["id"]).get_json()["id"]

        kb_doc = db.create_kb_document(
            title="SOP-3", folder="SOP", tags="", doc_version="1.0",
            effective_date=None, review_date=None, original_name="sop3.pdf",
            stored_filename="stored3.pdf", file_type="pdf", file_size=1024,
        company_id="company-1")
        db.set_kb_document_postgres_id(kb_doc["id"], "pg-kb-doc-2")

        with patch(
            "pharmagpt.routes.equipment.equipment_repo.link_kb_document",
            return_value={"id": "pg-link-2"},
        ):
            link_resp = client.post(
                f"/equipment/{equipment_id}/documents",
                json={"document_role": "sop", "source_type": "kb", "source_id": kb_doc["id"]},
                headers=AUTH_HEADERS,
            )
        link_id = link_resp.get_json()["id"]

        with patch("pharmagpt.routes.equipment.equipment_repo.unlink") as mock_unlink:
            resp = client.delete(
                f"/equipment/{equipment_id}/documents/{link_id}", headers=AUTH_HEADERS
            )

    assert resp.status_code == 200
    mock_unlink.assert_called_once_with("good-token", "company-1", "pg-link-2")

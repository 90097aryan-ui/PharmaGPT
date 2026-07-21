"""
tests/test_projects_dual_write.py — Phase 3.2 dual-write coverage
(docs/PHASE3_EXECUTION_PLAN.md).

Exercises the real pharmagpt.app + real middleware (pattern borrowed from
test_app_auth_integration.py), with pharmagpt.routes.projects.projects_repo
mocked so no real Supabase/Postgres call is made — these tests assert the
*orchestration* (when Postgres is called, with what, and that a Postgres
failure never breaks the SQLite-backed response), not Postgres itself.
"""

from unittest.mock import patch

import pytest

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt.auth.context import TenantContext

SAMPLE_TENANT = TenantContext(
    user_id="user-1",
    email="jane@example.com",
    display_name="Jane Admin",
    role="company_admin",
    company_id="company-1",
)

SUPER_ADMIN_TENANT = TenantContext(
    user_id="super-1",
    email="super@example.com",
    display_name="Super Admin",
    role="super_admin",
    company_id=None,
)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


@pytest.fixture()
def authed(client):
    """Context manager: patches the middleware to authenticate every
    request in `client` as SAMPLE_TENANT."""
    return patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SAMPLE_TENANT
    )


AUTH_HEADERS = {"Authorization": "Bearer good-token"}


def _create_payload(name="Dual-write test project"):
    return {"name": name, "equipment_name": "HPLC", "manufacturer": "Agilent",
            "department": "QC", "validation_type": "IQ/OQ/PQ"}


def test_dual_write_disabled_by_default(client, authed, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_BACKEND", "sqlite")
    with authed, patch("pharmagpt.routes.projects.projects_repo.create_project") as mock_create:
        resp = client.post("/projects", json=_create_payload(), headers=AUTH_HEADERS)

    assert resp.status_code == 201
    mock_create.assert_not_called()
    assert db.get_project(resp.get_json()["id"])["postgres_id"] is None


def test_dual_write_create_calls_repo_and_stores_postgres_id(client, authed, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.projects.projects_repo.create_project",
        return_value={"id": "pg-uuid-1"},
    ) as mock_create:
        resp = client.post("/projects", json=_create_payload(), headers=AUTH_HEADERS)

    assert resp.status_code == 201
    project_id = resp.get_json()["id"]
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args[0] == "good-token"
    assert args[1] == "company-1"
    assert kwargs["name"] == "Dual-write test project"
    assert db.get_project(project_id)["postgres_id"] == "pg-uuid-1"


def test_dual_write_create_failure_does_not_break_response(client, authed, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.projects.projects_repo.create_project",
        side_effect=RuntimeError("Postgres unreachable"),
    ):
        resp = client.post("/projects", json=_create_payload(), headers=AUTH_HEADERS)

    assert resp.status_code == 201
    project_id = resp.get_json()["id"]
    assert db.get_project(project_id) is not None
    assert db.get_project(project_id)["postgres_id"] is None


def test_super_admin_cannot_create_project(client, monkeypatch):
    """Super Admin has no standing access to tenant content (PLATFORM_ARCHITECTURE.md
    §7) — this is enforced before the SQLite write, let alone the Postgres
    dual-write, so there is nothing left for Postgres to skip."""
    monkeypatch.setattr(config, "PROJECTS_BACKEND", "dual")
    with patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SUPER_ADMIN_TENANT
    ), patch("pharmagpt.routes.projects.projects_repo.create_project") as mock_create:
        resp = client.post("/projects", json=_create_payload(), headers=AUTH_HEADERS)

    assert resp.status_code == 403
    mock_create.assert_not_called()


def test_dual_write_update_skipped_without_prior_postgres_id(client, authed, monkeypatch):
    # Created while the flag was "sqlite" -> no postgres_id was ever stored.
    monkeypatch.setattr(config, "PROJECTS_BACKEND", "sqlite")
    with authed:
        create_resp = client.post("/projects", json=_create_payload(), headers=AUTH_HEADERS)
    project_id = create_resp.get_json()["id"]

    monkeypatch.setattr(config, "PROJECTS_BACKEND", "dual")
    with authed, patch("pharmagpt.routes.projects.projects_repo.update_project") as mock_update:
        resp = client.put(
            f"/projects/{project_id}", json={"name": "Renamed"}, headers=AUTH_HEADERS
        )

    assert resp.status_code == 200
    mock_update.assert_not_called()


def test_dual_write_update_calls_repo_when_postgres_id_present(client, authed, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.projects.projects_repo.create_project",
        return_value={"id": "pg-uuid-2"},
    ):
        create_resp = client.post("/projects", json=_create_payload(), headers=AUTH_HEADERS)
    project_id = create_resp.get_json()["id"]

    with authed, patch(
        "pharmagpt.routes.projects.projects_repo.update_project", return_value={"id": "pg-uuid-2"}
    ) as mock_update:
        resp = client.put(
            f"/projects/{project_id}", json={"name": "Renamed"}, headers=AUTH_HEADERS
        )

    assert resp.status_code == 200
    mock_update.assert_called_once()
    args, kwargs = mock_update.call_args
    assert args[2] == "pg-uuid-2"
    assert kwargs["name"] == "Renamed"


def test_dual_write_delete_calls_repo_with_postgres_id(client, authed, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.projects.projects_repo.create_project",
        return_value={"id": "pg-uuid-3"},
    ):
        create_resp = client.post("/projects", json=_create_payload(), headers=AUTH_HEADERS)
    project_id = create_resp.get_json()["id"]

    with authed, patch(
        "pharmagpt.routes.projects.projects_repo.delete_project"
    ) as mock_delete:
        resp = client.delete(f"/projects/{project_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    mock_delete.assert_called_once_with("good-token", "company-1", "pg-uuid-3")

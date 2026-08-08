"""
tests/test_backup_admin_routes.py — RBAC gating for the new
/admin/backup/* routes (pharmagpt/routes/backup_admin.py).

Reuses the real Flask app + real auth middleware pattern from
tests/test_security_tenant_rbac_esig.py (resolve_tenant_context patched
per-test, no real Supabase call). Proves the dashboard is reachable only by
super_admin and that ordinary company roles get 403 — using the EXISTING
require_role decorator, unmodified.
"""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from pharmagpt import config
from pharmagpt.services import backup_service
from tests.test_security_tenant_rbac_esig import ADMIN_A, REVIEWER_A, SUPER_ADMIN, AUTH_HEADERS, MIDDLEWARE_PATH


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod
    return appmod.app.test_client()


@pytest.fixture(autouse=True)
def _isolated_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    (tmp_path / "uploads").mkdir()


@pytest.mark.parametrize("tenant", [ADMIN_A, REVIEWER_A])
def test_non_super_admin_cannot_reach_dashboard_page(client, tenant):
    with _as(tenant):
        resp = client.get("/admin/backup", headers=AUTH_HEADERS)
    assert resp.status_code == 403


@pytest.mark.parametrize("tenant", [ADMIN_A, REVIEWER_A])
def test_non_super_admin_cannot_reach_status_api(client, tenant):
    with _as(tenant):
        resp = client.get("/admin/backup/api/status", headers=AUTH_HEADERS)
    assert resp.status_code == 403


@pytest.mark.parametrize("tenant", [ADMIN_A, REVIEWER_A])
def test_non_super_admin_cannot_trigger_backup_or_verify(client, tenant):
    with _as(tenant):
        run_resp = client.post("/admin/backup/api/run", headers=AUTH_HEADERS)
        verify_resp = client.post("/admin/backup/api/verify", headers=AUTH_HEADERS)
    assert run_resp.status_code == 403
    assert verify_resp.status_code == 403


def test_super_admin_can_reach_dashboard_page(client):
    with _as(SUPER_ADMIN):
        resp = client.get("/admin/backup", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert b"Backup" in resp.data


def test_super_admin_can_read_status_and_history(client):
    with _as(SUPER_ADMIN):
        status_resp = client.get("/admin/backup/api/status", headers=AUTH_HEADERS)
        history_resp = client.get("/admin/backup/api/history", headers=AUTH_HEADERS)
    assert status_resp.status_code == 200
    assert "freshness" in status_resp.get_json()
    assert history_resp.status_code == 200
    assert "runs" in history_resp.get_json()


def test_super_admin_verify_endpoint_runs_a_real_drill(client):
    # Seed one real backup synchronously so /api/verify has something to check.
    backup_service.run_full_backup()
    with _as(SUPER_ADMIN):
        resp = client.post("/admin/backup/api/verify", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["overall"] == "pass"

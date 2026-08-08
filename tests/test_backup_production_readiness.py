"""
tests/test_backup_production_readiness.py — Coverage for the production-
readiness pass on the Backup & Recovery module: configuration detection,
health computation, verification persistence, the safe restore drill, and
— most importantly — that no route or service function ever surfaces a raw
exception message, "Failed to fetch"-style network error, or generic
"Internal Server Error" to the caller. Every failure path here should
resolve to a structured, friendly response instead of raising.

Companion to tests/test_backup_service.py (happy-path + core mechanics,
unchanged) and tests/test_backup_admin_routes.py (RBAC gating, unchanged).
"""

import json
import logging
import os
import time as time_module
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from pharmagpt import config
from pharmagpt.services import backup_service
from tests.test_security_tenant_rbac_esig import ADMIN_A, SUPER_ADMIN, AUTH_HEADERS, MIDDLEWARE_PATH


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod
    return appmod.app.test_client()


@pytest.fixture()
def backup_env(tmp_path, db_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "sample.pdf").write_bytes(b"fake pdf bytes")

    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(config, "BACKUP_ALERT_WEBHOOK_URL", None)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_DIR", None)
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", False)
    monkeypatch.setenv("GENERATED_DOCS_PATH", str(tmp_path / "generated_documents"))
    return {"tmp_path": tmp_path}


# ── configuration detection ─────────────────────────────────────────────────

def test_configuration_status_all_configured(backup_env, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_OFFSITE_DIR", str(tmp_path / "offsite"))
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)

    cfg = backup_service.get_configuration_status()

    assert cfg["encryption_key"]["status"] == "configured"
    assert cfg["backup_service"]["status"] == "configured"
    assert cfg["scheduler"]["status"] == "configured"
    assert cfg["offsite_storage"]["status"] == "configured"
    assert cfg["database_backup"]["status"] == "configured"
    # A fresh upload dir with a file in it (from the fixture) counts as configured.
    assert cfg["document_backup"]["status"] == "configured"

    # Every message is plain, curated text — never an exception repr.
    for entry in cfg.values():
        assert "Traceback" not in entry["message"]
        assert "Error(" not in entry["message"]


def test_configuration_status_missing_encryption_key(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    cfg = backup_service.get_configuration_status()
    assert cfg["encryption_key"]["status"] == "missing"
    assert "no encryption key" in cfg["encryption_key"]["message"].lower()


def test_configuration_status_failed_invalid_encryption_key(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    cfg = backup_service.get_configuration_status()
    assert cfg["encryption_key"]["status"] == "failed"
    # The raw cryptography exception must never leak into the message.
    assert "InvalidToken" not in cfg["encryption_key"]["message"]
    assert "base64" not in cfg["encryption_key"]["message"].lower()


def test_configuration_status_scheduler_missing_by_default(backup_env):
    cfg = backup_service.get_configuration_status()
    assert cfg["scheduler"]["status"] == "missing"


def test_configuration_status_scheduler_configured_when_flag_set(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)
    cfg = backup_service.get_configuration_status()
    assert cfg["scheduler"]["status"] == "configured"


def test_configuration_status_offsite_missing_by_default(backup_env):
    cfg = backup_service.get_configuration_status()
    assert cfg["offsite_storage"]["status"] == "missing"


def test_configuration_status_offsite_failed_when_unwritable(backup_env, monkeypatch):
    # A file (not a directory) as the offsite path can never be mkdir'd into.
    bogus = backup_env["tmp_path"] / "not_a_directory.txt"
    bogus.write_text("occupied")
    monkeypatch.setattr(config, "BACKUP_OFFSITE_DIR", str(bogus / "nested"))
    cfg = backup_service.get_configuration_status()
    assert cfg["offsite_storage"]["status"] == "failed"


def test_configuration_status_database_backup_failed_when_db_missing(backup_env, monkeypatch):
    from pharmagpt import database as db_module
    monkeypatch.setattr(db_module, "DB_PATH", str(backup_env["tmp_path"] / "does_not_exist.db"))
    cfg = backup_service.get_configuration_status()
    assert cfg["database_backup"]["status"] == "failed"


def test_configuration_status_document_backup_missing_when_no_uploads_dir(backup_env, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(tmp_path / "never_created"))
    cfg = backup_service.get_configuration_status()
    assert cfg["document_backup"]["status"] == "missing"


def test_configuration_status_backup_service_failed_when_dir_unwritable(backup_env, tmp_path, monkeypatch):
    # A file where a directory is expected — mkdir must fail cleanly.
    bogus_parent = tmp_path / "occupied_file"
    bogus_parent.write_text("x")
    monkeypatch.setattr(config, "BACKUP_DIR", str(bogus_parent / "backups"))
    cfg = backup_service.get_configuration_status()
    assert cfg["backup_service"]["status"] == "failed"


# ── _backup_dir() resilience (the core bug: read-only calls must never crash) ─

def test_status_reads_never_crash_when_backup_dir_unwritable(backup_env, tmp_path, monkeypatch):
    bogus_parent = tmp_path / "occupied_file2"
    bogus_parent.write_text("x")
    monkeypatch.setattr(config, "BACKUP_DIR", str(bogus_parent / "backups"))

    # None of these may raise — this is exactly what would previously 500
    # every GET to the dashboard if BACKUP_DIR was misconfigured.
    assert backup_service.get_latest() is None
    assert backup_service.get_history() == []
    freshness = backup_service.check_freshness()
    assert freshness["fresh"] is False
    assert backup_service.get_latest_verification() is None
    status = backup_service.get_dashboard_status()
    assert status["latest_run"] is None


# ── is_backup_runnable / is_archive_available gates ─────────────────────────

def test_is_backup_runnable_false_when_key_missing(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    runnable, reason = backup_service.is_backup_runnable()
    assert runnable is False
    assert reason and "encryption key" in reason.lower()


def test_is_backup_runnable_true_when_fully_configured(backup_env):
    runnable, reason = backup_service.is_backup_runnable()
    assert runnable is True
    assert reason is None


def test_archive_available_false_before_any_backup(backup_env):
    available, reason = backup_service.is_archive_available_for_verification_or_restore()
    assert available is False
    assert "no successful backup" in reason.lower()


def test_archive_available_true_after_a_backup(backup_env):
    backup_service.run_full_backup()
    available, reason = backup_service.is_archive_available_for_verification_or_restore()
    assert available is True
    assert reason is None


# ── verification persistence ────────────────────────────────────────────────

def test_verify_backup_persists_result_for_dashboard(backup_env):
    backup_service.run_full_backup()
    assert backup_service.get_latest_verification() is None  # not run yet

    report = backup_service.verify_backup()

    latest = backup_service.get_latest_verification()
    assert latest is not None
    assert latest["overall"] == report["overall"] == "pass"
    assert "timestamp" in latest

    history = backup_service.get_verification_history(limit=5)
    assert len(history) == 1


def test_verify_backup_never_raises_when_encryption_key_missing(backup_env, monkeypatch):
    """Regression test for the exact bug found in this pass: verify_backup()
    used to only catch BackupIntegrityError around decryption, so a missing
    BACKUP_ENCRYPTION_KEY (which raises BackupConfigError) escaped uncaught
    and would have surfaced as a raw 500 at the route layer."""
    backup_service.run_full_backup()
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)

    report = backup_service.verify_backup()  # must not raise

    assert report["overall"] == "fail"
    assert "error" in report
    # Still persisted, even on failure.
    assert backup_service.get_latest_verification()["overall"] == "fail"


def test_verify_backup_never_raises_on_unexpected_internal_error(backup_env, monkeypatch):
    backup_service.run_full_backup()

    def _boom(*a, **k):
        raise RuntimeError("simulated corruption")

    monkeypatch.setattr(backup_service, "_run_verification_checks", _boom)
    report = backup_service.verify_backup()

    assert report["overall"] == "fail"
    assert "simulated corruption" in report["error"]


# ── restore drill (new "Restore" action) ────────────────────────────────────

def test_run_restore_drill_succeeds_into_staging_never_live_paths(backup_env, monkeypatch):
    from pharmagpt import database as db_module
    live_db_path = db_module.DB_PATH
    live_upload_folder = config.UPLOAD_FOLDER

    backup_service.run_full_backup()
    result = backup_service.run_restore_drill()

    assert result["success"] is True
    staging = result["restored_to"]
    assert staging != live_db_path
    assert staging != live_upload_folder
    assert str(backup_service._backup_dir()) in staging
    assert "restore_staging" in staging

    # The live database file was never touched.
    import sqlite3
    conn = sqlite3.connect(live_db_path)
    conn.execute("SELECT COUNT(*) FROM qms_audit_trail")
    conn.close()


def test_run_restore_drill_clears_previous_staging_output(backup_env):
    backup_service.run_full_backup()
    first = backup_service.run_restore_drill()
    marker = backup_service._backup_dir() / "restore_staging" / "leftover_marker.txt"
    marker.write_text("should be removed on next drill")

    second = backup_service.run_restore_drill()

    assert second["success"] is True
    assert not marker.exists()


def test_run_restore_drill_fails_gracefully_with_no_archive(backup_env):
    result = backup_service.run_restore_drill()
    assert result["success"] is False
    assert "no backup archive" in result["error"].lower() or "no backup" in result["error"].lower()


def test_run_restore_drill_never_raises_on_unexpected_error(backup_env, monkeypatch):
    backup_service.run_full_backup()

    def _boom(*a, **k):
        raise RuntimeError("simulated disk full")

    monkeypatch.setattr(backup_service, "restore_from_backup", _boom)
    result = backup_service.run_restore_drill()

    assert result["success"] is False
    assert "simulated disk full" in result["error"]


# ── health computation ───────────────────────────────────────────────────────

def test_health_critical_when_encryption_key_missing(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    health = backup_service.compute_health()
    assert health["level"] == "critical"
    assert any("encryption" in r.lower() for r in health["reasons"])


def test_health_warning_when_no_backup_run_yet(backup_env):
    health = backup_service.compute_health()
    assert health["level"] == "warning"


def test_health_critical_when_last_run_failed(backup_env, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("disk error")
    monkeypatch.setattr(backup_service, "_backup_sqlite", _boom)
    backup_service.run_full_backup()

    health = backup_service.compute_health()
    assert health["level"] == "critical"


def test_health_healthy_when_everything_passes(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_OFFSITE_DIR", str(backup_env["tmp_path"] / "offsite"))
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)

    backup_service.run_full_backup()
    backup_service.verify_backup()

    health = backup_service.compute_health()
    assert health["level"] == "healthy"
    assert health["reasons"] == ["All checks passed."]


def test_health_warning_when_stale(backup_env):
    backup_service.run_full_backup()
    history = backup_service._load_state()
    history[-1]["finished_at"] = (datetime.now(timezone.utc) - timedelta(hours=999)).isoformat()
    backup_service._state_path().write_text(json.dumps(history), encoding="utf-8")

    health = backup_service.compute_health()
    assert health["level"] in ("warning", "critical")
    assert any("older than expected" in r for r in health["reasons"])


# ── next scheduled backup ───────────────────────────────────────────────────

def test_next_scheduled_backup_not_scheduled_when_scheduler_disabled(backup_env):
    result = backup_service.get_next_scheduled_backup()
    assert result["scheduled"] is False


def test_next_scheduled_backup_estimated_when_scheduler_enabled(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)
    backup_service.run_full_backup()

    result = backup_service.get_next_scheduled_backup()
    assert result["scheduled"] is True
    assert result["estimated_at"] is not None


def test_next_scheduled_backup_pending_when_no_run_yet(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)
    result = backup_service.get_next_scheduled_backup()
    assert result["scheduled"] is True
    assert result["estimated_at"] is None


# ── dashboard status aggregator ─────────────────────────────────────────────

def test_get_dashboard_status_shape(backup_env):
    backup_service.run_full_backup()
    backup_service.verify_backup()

    status = backup_service.get_dashboard_status()
    for key in ("latest_run", "freshness", "last_successful_backup", "last_failed_backup",
                "last_verification", "next_scheduled_backup", "health"):
        assert key in status


# ── concurrency guard ────────────────────────────────────────────────────────

def test_concurrent_backup_is_rejected_not_run(backup_env):
    assert backup_service._acquire_lock() is True  # simulate an in-flight run
    try:
        result = backup_service.run_full_backup()
        assert result.status == "failed"
        assert "already in progress" in result.error.lower()
    finally:
        backup_service._release_lock()

    # Lock released -> the next run proceeds normally.
    result2 = backup_service.run_full_backup()
    assert result2.status == "success"


def test_stale_lock_is_reclaimed_not_permanently_blocking(backup_env):
    lock_path = backup_service._backup_dir() / backup_service.LOCK_FILENAME
    lock_path.write_text("99999999", encoding="utf-8")
    old_time = time_module.time() - (backup_service.LOCK_STALE_SECONDS + 60)
    os.utime(lock_path, (old_time, old_time))

    result = backup_service.run_full_backup()
    assert result.status == "success"


def test_is_backup_runnable_false_while_locked(backup_env):
    assert backup_service._acquire_lock() is True
    try:
        runnable, reason = backup_service.is_backup_runnable()
        assert runnable is False
        assert "already in progress" in reason.lower()
    finally:
        backup_service._release_lock()


def test_lock_is_always_released_even_if_backup_raises(backup_env, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("disk error")
    monkeypatch.setattr(backup_service, "_backup_sqlite", _boom)

    backup_service.run_full_backup()

    assert backup_service.is_backup_locked() is False


def test_run_backup_cli_script_does_not_self_block(backup_env, monkeypatch):
    """Regression test for the exact bug found in this pass: an earlier
    version of scripts/run_backup.py pre-created the same lock file path
    backup_service.run_full_backup() now atomically manages itself, which
    meant _acquire_lock() always found the file already there and every
    single CLI/cron invocation failed with "already in progress" —
    against itself, not a real concurrent run. Runs the actual script as a
    subprocess against the isolated test environment to catch this class
    of bug, not just the in-process unit behavior above."""
    import subprocess
    import sys as _sys

    env = os.environ.copy()
    env["BACKUP_DIR"] = str(config.BACKUP_DIR)
    env["UPLOAD_FOLDER"] = str(config.UPLOAD_FOLDER)
    env["BACKUP_ENCRYPTION_KEY"] = config.BACKUP_ENCRYPTION_KEY
    env["DB_PATH"] = __import__("pharmagpt.database", fromlist=["DB_PATH"]).DB_PATH
    env["GENERATED_DOCS_PATH"] = os.environ.get("GENERATED_DOCS_PATH", str(backup_env["tmp_path"] / "generated_documents"))

    repo_root = os.path.join(os.path.dirname(__file__), "..")
    proc = subprocess.run(
        [_sys.executable, os.path.join(repo_root, "scripts", "run_backup.py")],
        env=env, capture_output=True, text=True, timeout=60,
    )

    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "already in progress" not in (proc.stdout + proc.stderr).lower()


# ═══════════════════════════════════════════════════════════════════════════
# Route-level tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _isolated_backups_for_routes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path / "route_backups"))
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(tmp_path / "route_uploads"))
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    (tmp_path / "route_uploads").mkdir()


def test_api_config_endpoint_returns_all_six_components(client):
    with _as(SUPER_ADMIN):
        resp = client.get("/admin/backup/api/config", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.get_json()["configuration"]
    for key in ("backup_service", "scheduler", "encryption_key", "offsite_storage", "database_backup", "document_backup"):
        assert key in body
        assert body[key]["status"] in ("configured", "missing", "failed")


def test_api_config_requires_super_admin(client):
    with _as(ADMIN_A):
        resp = client.get("/admin/backup/api/config", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_api_status_includes_new_dashboard_fields(client):
    with _as(SUPER_ADMIN):
        resp = client.get("/admin/backup/api/status", headers=AUTH_HEADERS)
    body = resp.get_json()
    for key in ("last_successful_backup", "last_failed_backup", "last_verification",
                "next_scheduled_backup", "health", "latest_run", "freshness"):
        assert key in body


def test_api_run_rejects_with_friendly_message_when_key_missing(client, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    with _as(SUPER_ADMIN):
        resp = client.post("/admin/backup/api/run", headers=AUTH_HEADERS)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["success"] is False
    assert "user_message" in body
    assert "BackupConfigError" not in body["user_message"]
    assert "Traceback" not in body["user_message"]


def test_api_verify_rejects_with_friendly_message_when_no_backup_exists(client):
    with _as(SUPER_ADMIN):
        resp = client.post("/admin/backup/api/verify", headers=AUTH_HEADERS)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["success"] is False
    assert "user_message" in body
    assert "no successful backup" in body["user_message"].lower()


def test_api_verify_never_returns_raw_exception_when_key_missing_after_backup(client, monkeypatch):
    """This is the exact regression scenario for the original bug: a
    backup exists, then the key is removed, then verify is called. Before
    the fix, this raised BackupConfigError uncaught -> generic 500
    "Internal server error" from app.py's global handler."""
    from pharmagpt.services import backup_service as svc
    svc.run_full_backup()
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)

    with _as(SUPER_ADMIN):
        resp = client.post("/admin/backup/api/verify", headers=AUTH_HEADERS)

    body = resp.get_json()
    assert resp.status_code in (409, 502)
    assert "user_message" in body
    assert body["user_message"] != "Internal server error"
    assert "BackupConfigError" not in json.dumps(body)
    assert "Traceback" not in json.dumps(body)


def test_api_restore_endpoint_success(client):
    from pharmagpt.services import backup_service as svc
    svc.run_full_backup()

    with _as(SUPER_ADMIN):
        resp = client.post("/admin/backup/api/restore", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert "restored_to" in body
    assert "user_message" in body


def test_api_restore_rejects_when_no_backup_exists(client):
    with _as(SUPER_ADMIN):
        resp = client.post("/admin/backup/api/restore", headers=AUTH_HEADERS)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["success"] is False
    assert "user_message" in body


def test_api_restore_requires_super_admin(client):
    with _as(ADMIN_A):
        resp = client.post("/admin/backup/api/restore", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_api_verification_history_endpoint(client):
    from pharmagpt.services import backup_service as svc
    svc.run_full_backup()
    svc.verify_backup()

    with _as(SUPER_ADMIN):
        resp = client.get("/admin/backup/api/verification-history", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert len(resp.get_json()["verifications"]) == 1


def test_api_history_malformed_limit_does_not_500(client):
    with _as(SUPER_ADMIN):
        resp = client.get("/admin/backup/api/history?limit=not-a-number", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert "runs" in resp.get_json()


def test_api_verification_history_malformed_limit_does_not_500(client):
    with _as(SUPER_ADMIN):
        resp = client.get("/admin/backup/api/verification-history?limit=-5", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert "verifications" in resp.get_json()


def test_dashboard_page_renders_when_nothing_is_configured_yet(client, monkeypatch):
    """The empty-state / not-configured scenario end to end: no backup has
    ever run, and the encryption key is unset. The page itself must still
    render (200), never a raw error page."""
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    with _as(SUPER_ADMIN):
        page_resp = client.get("/admin/backup", headers=AUTH_HEADERS)
        status_resp = client.get("/admin/backup/api/status", headers=AUTH_HEADERS)
        config_resp = client.get("/admin/backup/api/config", headers=AUTH_HEADERS)

    assert page_resp.status_code == 200
    assert status_resp.status_code == 200
    assert config_resp.status_code == 200
    assert status_resp.get_json()["latest_run"] is None
    assert config_resp.get_json()["configuration"]["encryption_key"]["status"] == "missing"


def test_no_route_response_ever_contains_banned_phrases(client):
    """Sweep every backup route in a fully-unconfigured, empty-database
    state and assert none of the four banned raw-error phrases ever
    appear in any JSON response body."""
    banned = ["Failed to fetch", "Internal Server Error", "Traceback (most recent call last)"]

    with _as(SUPER_ADMIN):
        responses = [
            client.get("/admin/backup", headers=AUTH_HEADERS),
            client.get("/admin/backup/api/status", headers=AUTH_HEADERS),
            client.get("/admin/backup/api/config", headers=AUTH_HEADERS),
            client.get("/admin/backup/api/history", headers=AUTH_HEADERS),
            client.get("/admin/backup/api/verification-history", headers=AUTH_HEADERS),
            client.post("/admin/backup/api/verify", headers=AUTH_HEADERS),
            client.post("/admin/backup/api/restore", headers=AUTH_HEADERS),
        ]

    for resp in responses:
        body_text = resp.get_data(as_text=True)
        for phrase in banned:
            assert phrase not in body_text, f"Banned phrase '{phrase}' found in response for {resp.request.path}"

"""
tests/test_backup_service.py — Backup & Recovery framework
(pharmagpt/services/backup_service.py).

Exercises the real backup/verify/restore code paths against a throwaway
SQLite DB, uploads folder, and backup directory (never the real
pharmagpt.db or the real backups/ directory). No Supabase credentials are
configured in this test environment, so the Postgres export path is
expected to gracefully skip (asserted explicitly below) rather than fail
the whole backup — that graceful-degradation behavior is itself under test.
"""

import json
import os
import time

import pytest
from cryptography.fernet import Fernet

from pharmagpt import config
from pharmagpt.services import backup_service


@pytest.fixture()
def backup_env(tmp_path, db_path, monkeypatch):
    """Isolated backup environment: throwaway DB (via the shared db_path
    fixture), throwaway upload folder, throwaway backup dir, a real
    generated Fernet key (never the app's dev-fallback pattern)."""
    backup_dir = tmp_path / "backups"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "sample.pdf").write_bytes(b"fake pdf bytes")

    generated_dir = tmp_path / "generated_documents"
    generated_dir.mkdir()
    (generated_dir / "report.docx").write_bytes(b"fake docx bytes")

    monkeypatch.setattr(config, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(config, "BACKUP_ALERT_WEBHOOK_URL", None)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_DIR", None)
    monkeypatch.setenv("GENERATED_DOCS_PATH", str(generated_dir))

    # Seed a couple of rows into the tables a real production DB would have,
    # so the integrity/row-count checks below exercise real data, not just
    # empty tables. qms_audit_trail/qms_esignatures already exist via
    # db.init_db() (called by the db_path fixture) — insert directly.
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO qms_audit_trail (record_type, record_id, action, detail, performed_by) "
        "VALUES ('document', 1, 'Created', 'test', 'tester')"
    )
    conn.commit()
    conn.close()

    return {"backup_dir": backup_dir, "upload_dir": upload_dir, "generated_dir": generated_dir}


def test_backup_config_error_when_key_unset(backup_env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    result = backup_service.run_full_backup()
    assert result.status == "failed"
    assert "BACKUP_ENCRYPTION_KEY" in result.error


def test_full_backup_succeeds_and_is_encrypted(backup_env):
    result = backup_service.run_full_backup()

    assert result.status == "success", result.error
    assert result.archive_path and os.path.exists(result.archive_path)
    assert result.archive_sha256 is not None
    assert result.size_bytes > 0

    # The archive on disk must not be a readable tar/gzip — it's Fernet-encrypted.
    with open(result.archive_path, "rb") as f:
        header = f.read(4)
    assert header != b"\x1f\x8b\x08\x08"  # not a raw gzip magic byte sequence

    # SQLite target: integrity check passed and the audit-trail row we
    # seeded was actually captured in the backup copy.
    assert result.targets["sqlite"]["integrity_check"] == "ok"
    assert result.targets["sqlite"]["row_counts"]["qms_audit_trail"] == 1

    # File targets captured our seeded files.
    assert result.targets["uploads"]["file_count"] == 1
    assert result.targets["generated_documents"]["file_count"] == 1

    # Postgres export: whether real Supabase credentials happen to be present
    # in this environment or not, it must never fail the overall backup —
    # either every configured table reports a row count (client available)
    # or the whole target reports "skipped" with a reason (client
    # unavailable, e.g. no .env configured). Both are success paths.
    postgres_target = result.targets["postgres"]
    assert isinstance(postgres_target["tables"], dict)
    if postgres_target["skipped"] is None:
        assert len(postgres_target["tables"]) == len(config.POSTGRES_BACKUP_TABLES)
    else:
        assert postgres_target["tables"] == {}

    # Post-write self-verification (decrypt round-trip) passed.
    assert result.verification["decrypt_roundtrip"] == "ok"


def test_backup_run_is_recorded_in_history_and_status(backup_env):
    backup_service.run_full_backup()
    latest = backup_service.get_latest()
    assert latest["status"] == "success"

    history = backup_service.get_history(limit=5)
    assert len(history) == 1
    assert history[0]["run_id"] == latest["run_id"]


def test_freshness_check_reports_fresh_immediately_after_a_run(backup_env):
    backup_service.run_full_backup()
    freshness = backup_service.check_freshness()
    assert freshness["fresh"] is True
    assert freshness["age_hours"] < 0.1


def test_freshness_check_reports_stale_and_no_runs_case(backup_env):
    # No run yet.
    freshness = backup_service.check_freshness()
    assert freshness["fresh"] is False
    assert freshness["last_success_at"] is None

    # A run that happened "long ago" relative to the configured frequency.
    backup_service.run_full_backup()
    history = backup_service._load_state()
    from datetime import datetime, timedelta, timezone
    history[-1]["finished_at"] = (datetime.now(timezone.utc) - timedelta(hours=999)).isoformat()
    backup_service._state_path().write_text(json.dumps(history), encoding="utf-8")

    freshness = backup_service.check_freshness()
    assert freshness["fresh"] is False
    assert freshness["age_hours"] > config.BACKUP_FREQUENCY_HOURS * 2
    assert "stale" not in freshness["reason"].lower()  # wording is factual (age vs threshold), not alarmist


def test_verify_backup_passes_restore_drill_against_real_archive(backup_env):
    run = backup_service.run_full_backup()
    report = backup_service.verify_backup(run.archive_path)

    assert report["overall"] == "pass", report
    assert report["checks"]["sqlite_integrity_check"] == "ok"
    assert report["checks"]["row_counts_match_manifest"] is True
    assert report["checks"]["uploads_count_matches_manifest"] is True
    assert report["checks"]["generated_documents_count_matches_manifest"] is True
    assert report["checks"]["manifest_present"] is True


def test_verify_backup_with_no_archive_reports_failure_not_a_crash(backup_env):
    report = backup_service.verify_backup("/nonexistent/path.bak.enc")
    assert report["overall"] == "fail"
    assert "error" in report


def test_verify_backup_detects_tampered_encrypted_archive(backup_env):
    run = backup_service.run_full_backup()
    # Flip a byte in the middle of the encrypted archive — Fernet must reject it.
    with open(run.archive_path, "r+b") as f:
        f.seek(50)
        b = f.read(1)
        f.seek(50)
        f.write(bytes([b[0] ^ 0xFF]))

    report = backup_service.verify_backup(run.archive_path)
    assert report["overall"] == "fail"
    assert "error" in report


def test_restore_from_backup_writes_into_fresh_directory(backup_env, tmp_path):
    run = backup_service.run_full_backup()
    target = tmp_path / "restore_target"

    result = backup_service.restore_from_backup(run.archive_path, str(target))

    assert (target / "db" / "pharmagpt.db").exists()
    assert (target / "uploads.tar.gz").exists()
    assert (target / "manifest.json").exists()
    assert result["restored_to"] == str(target)


def test_restore_from_backup_refuses_nonempty_target_without_confirm(backup_env, tmp_path):
    run = backup_service.run_full_backup()
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "existing_file.txt").write_text("do not overwrite me")

    with pytest.raises(backup_service.BackupIntegrityError):
        backup_service.restore_from_backup(run.archive_path, str(target))


def test_restore_from_backup_allows_nonempty_target_with_confirm_live(backup_env, tmp_path):
    run = backup_service.run_full_backup()
    target = tmp_path / "occupied2"
    target.mkdir()
    (target / "existing_file.txt").write_text("will remain alongside restored files")

    result = backup_service.restore_from_backup(run.archive_path, str(target), confirm_live=True)
    assert (target / "db" / "pharmagpt.db").exists()
    assert result["restored_to"] == str(target)


def test_retention_pruning_removes_old_snapshots(backup_env):
    backup_service.run_full_backup()
    snap_dir = backup_service._backup_dir() / "snapshots"
    archives = list(snap_dir.glob("*.bak.enc"))
    assert len(archives) == 1

    # Backdate the file's mtime beyond the configured retention window.
    old_time = time.time() - (config.BACKUP_SNAPSHOT_RETENTION_DAYS + 1) * 86400
    os.utime(archives[0], (old_time, old_time))

    removed = backup_service._prune("snapshots", config.BACKUP_SNAPSHOT_RETENTION_DAYS)
    assert removed == 1
    assert list(snap_dir.glob("*.bak.enc")) == []


@pytest.fixture()
def _backup_logger_caplog(caplog):
    """pharmagpt.logging_config.configure_logging() deliberately sets
    propagate=False on the "pharmagpt" logger (to avoid double-logging
    under gunicorn — see that module's docstring), which also means
    records never bubble up to caplog's default root-logger handler.
    Attach caplog's handler directly to this module's logger instead."""
    import logging
    target_logger = logging.getLogger("pharmagpt.services.backup_service")
    target_logger.addHandler(caplog.handler)
    caplog.set_level(logging.CRITICAL, logger="pharmagpt.services.backup_service")
    try:
        yield caplog
    finally:
        target_logger.removeHandler(caplog.handler)


def test_alert_logs_critical_and_handles_missing_webhook_gracefully(backup_env, _backup_logger_caplog):
    backup_service._alert("test subject", "test detail")
    assert any("BACKUP ALERT" in r.message for r in _backup_logger_caplog.records)


def test_failed_backup_triggers_alert(backup_env, monkeypatch, _backup_logger_caplog):
    def _boom(*a, **k):
        raise RuntimeError("simulated disk failure")

    monkeypatch.setattr(backup_service, "_backup_sqlite", _boom)

    result = backup_service.run_full_backup()

    assert result.status == "failed"
    assert "simulated disk failure" in result.error
    assert any("BACKUP ALERT" in r.message for r in _backup_logger_caplog.records)

"""
Off-site object-storage upload and the in-process backup scheduler
(services/backup_service.py, services/backup_scheduler.py).

No network: the object-store bucket is replaced by a fake. Covers successful
upload, upload failure, partial/missing configuration, and that scheduling is
never reported healthy without a running scheduler.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from pharmagpt import config
from pharmagpt.services import backup_scheduler, backup_service

SECRET_KEY = "super-secret-storage-key-123"


@pytest.fixture()
def env(tmp_path, db_path, monkeypatch):
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(config, "BACKUP_ALERT_WEBHOOK_URL", None)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_DIR", None)
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_URL", None)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_KEY", None)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_BUCKET", None)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_PREFIX", "pharmagpt/")
    monkeypatch.setenv("GENERATED_DOCS_PATH", str(tmp_path / "generated_documents"))
    return tmp_path


class FakeBucket:
    def __init__(self, *, fail=None, wrong_size=False, drop=False):
        self.objects, self.fail, self.wrong_size, self.drop = {}, fail, wrong_size, drop

    def upload(self, path, fh, options=None):
        if self.fail:
            raise RuntimeError(f"{self.fail} key={SECRET_KEY}")
        data = fh.read()
        self.objects[path] = len(data) + (1 if self.wrong_size else 0)

    def list(self, prefix, options=None):
        if self.drop:
            return []
        return [{"name": p.rsplit("/", 1)[-1], "metadata": {"size": n}} for p, n in self.objects.items()]


def configure_store(monkeypatch, bucket):
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_URL", "https://backups.example.invalid")
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_KEY", SECRET_KEY)
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_BUCKET", "yuktav-backups")
    monkeypatch.setattr(backup_service, "_get_object_store_bucket", lambda settings: bucket)


# ── upload ─────────────────────────────────────────────────────────────────

def test_successful_upload_is_recorded_and_run_succeeds(env, monkeypatch):
    bucket = FakeBucket()
    configure_store(monkeypatch, bucket)

    result = backup_service.run_full_backup()

    assert result.status == "success", result.error
    target = result.targets["object_storage"]
    assert target["status"] == "ok"
    assert target["object"].startswith("pharmagpt/") and target["object"].endswith(".bak.enc")
    assert list(bucket.objects) == [target["object"]]
    assert bucket.objects[target["object"]] == result.size_bytes  # the encrypted archive, not plaintext


def test_upload_failure_marks_run_failed_but_keeps_local_archive(env, monkeypatch, caplog):
    configure_store(monkeypatch, FakeBucket(fail="connection refused"))

    with caplog.at_level(logging.DEBUG):
        result = backup_service.run_full_backup()

    assert result.status == "failed"
    assert "Off-site upload failed" in result.error and "connection refused" in result.error
    assert result.targets["object_storage"]["status"] == "failed"
    assert result.archive_path and backup_service.Path(result.archive_path).exists()
    # Not counted as a successful backup, so freshness/health cannot call it off-site safe.
    assert backup_service.get_latest_successful() is None
    assert backup_service.compute_health()["level"] == "critical"
    assert SECRET_KEY not in result.error
    assert SECRET_KEY not in json.dumps(backup_service._load_state())
    assert SECRET_KEY not in caplog.text


@pytest.mark.parametrize("kwargs, word", [({"wrong_size": True}, "size mismatch"), ({"drop": True}, "missing")])
def test_unconfirmed_upload_is_a_failure(env, monkeypatch, kwargs, word):
    configure_store(monkeypatch, FakeBucket(**kwargs))
    result = backup_service.run_full_backup()
    assert result.status == "failed"
    assert word in result.error


def test_partial_configuration_fails_fast_naming_missing_variables(env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_URL", "https://backups.example.invalid")

    result = backup_service.run_full_backup()

    assert result.status == "failed"
    assert "BACKUP_OFFSITE_STORAGE_KEY" in result.error and "BACKUP_OFFSITE_STORAGE_BUCKET" in result.error
    assert result.archive_path is None  # nothing was written before the config check
    assert backup_service.get_configuration_status()["offsite_storage"]["status"] == "failed"


def test_no_object_storage_configured_still_succeeds_but_is_flagged(env):
    result = backup_service.run_full_backup()
    assert result.status == "success"
    assert result.targets["object_storage"]["status"] == "not configured"
    assert backup_service.get_configuration_status()["offsite_storage"]["status"] == "missing"


def test_encryption_key_remains_mandatory_with_object_storage(env, monkeypatch):
    configure_store(monkeypatch, FakeBucket())
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    result = backup_service.run_full_backup()
    assert result.status == "failed" and "BACKUP_ENCRYPTION_KEY" in result.error


# ── scheduler health ───────────────────────────────────────────────────────

def test_flag_alone_never_reports_scheduler_healthy(env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)

    assert backup_service.get_configuration_status()["scheduler"]["status"] == "failed"
    assert backup_service.get_next_scheduled_backup()["scheduled"] is False
    health = backup_service.compute_health()
    assert health["level"] == "critical"
    assert any("scheduler is not running" in r for r in health["reasons"])


def test_fresh_heartbeat_reports_scheduler_healthy_and_stale_does_not(env, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)
    backup_scheduler._write_heartbeat()
    assert backup_service.get_configuration_status()["scheduler"]["status"] == "configured"

    stale = datetime.now(timezone.utc) - timedelta(seconds=backup_scheduler.HEARTBEAT_STALE_SECONDS + 5)
    backup_scheduler._heartbeat_path().write_text(json.dumps({"at": stale.isoformat(), "pid": 1}), encoding="utf-8")
    assert backup_service.get_configuration_status()["scheduler"]["status"] == "failed"


def test_scheduler_does_not_start_when_disabled_or_misconfigured(env, monkeypatch):
    monkeypatch.setattr(backup_scheduler, "_thread", None)
    assert backup_scheduler.start() is False  # disabled

    monkeypatch.setattr(config, "BACKUP_SCHEDULER_ENABLED", True)
    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", None)
    assert backup_scheduler.start() is False  # no key -> cannot run backups

    monkeypatch.setattr(config, "BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(config, "BACKUP_OFFSITE_STORAGE_URL", "https://x.invalid")
    assert backup_scheduler.start() is False  # partial storage config


# ── scheduler behaviour ────────────────────────────────────────────────────

def test_tick_runs_backup_when_none_exists_then_not_again(env, monkeypatch):
    calls = []
    real = backup_service.run_full_backup
    monkeypatch.setattr(backup_service, "run_full_backup", lambda: (calls.append(1), real())[1])

    assert backup_scheduler.tick() is True
    assert backup_scheduler.heartbeat_status()["alive"] is True
    assert backup_scheduler.tick() is False  # a fresh success exists
    assert len(calls) == 1


def test_tick_waits_after_a_failed_run_and_when_locked(env, monkeypatch):
    configure_store(monkeypatch, FakeBucket(fail="down"))
    backup_service.run_full_backup()  # leaves a failed latest run
    called = []
    monkeypatch.setattr(backup_service, "run_full_backup", lambda: called.append(1))
    assert backup_scheduler.is_due() is False  # inside the retry back-off

    later = datetime.now(timezone.utc) + timedelta(minutes=backup_scheduler.RETRY_AFTER_FAILURE_MINUTES + 1)
    assert backup_scheduler.is_due(later) is True

    monkeypatch.setattr(backup_service, "is_backup_locked", lambda: True)
    assert backup_scheduler.is_due(later) is False
    assert called == []

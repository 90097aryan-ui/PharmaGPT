"""
services/backup_scheduler.py — in-process backup scheduler.

Runs inside the web service because only that service can read the
persistent disk holding the SQLite database and uploads (a Render cron job
cannot mount another service's disk). A daemon thread wakes every TICK_SECONDS,
writes a heartbeat file next to the backups, and starts backup_service.
run_full_backup() when no successful backup is newer than
BACKUP_FREQUENCY_HOURS. Several gunicorn workers each start a thread; the
backup lock file in run_full_backup() keeps them from overlapping.

Health is judged from the heartbeat file, never from the
BACKUP_SCHEDULER_ENABLED flag alone (see backup_service._check_scheduler).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from pharmagpt import config
from pharmagpt.services import backup_service

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
HEARTBEAT_FILENAME = "scheduler_heartbeat.json"
HEARTBEAT_STALE_SECONDS = 5 * TICK_SECONDS
RETRY_AFTER_FAILURE_MINUTES = 30  # don't hammer storage/Supabase after a failed run

_thread: threading.Thread | None = None
_thread_lock = threading.Lock()


def _heartbeat_path():
    return backup_service._backup_dir() / HEARTBEAT_FILENAME


def _write_heartbeat() -> None:
    payload = {"at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}
    path = _heartbeat_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def heartbeat_status() -> dict:
    """{"alive": bool, "last_beat_at": iso|None}. Alive = a heartbeat written
    by any worker within HEARTBEAT_STALE_SECONDS."""
    try:
        data = json.loads(_heartbeat_path().read_text(encoding="utf-8"))
        beat = datetime.fromisoformat(data["at"])
    except (OSError, ValueError, KeyError):
        return {"alive": False, "last_beat_at": None}
    age = (datetime.now(timezone.utc) - beat).total_seconds()
    return {"alive": age <= HEARTBEAT_STALE_SECONDS, "last_beat_at": data["at"]}


def is_due(now: datetime | None = None) -> bool:
    """True when a backup should start now: nothing running, no successful
    run within BACKUP_FREQUENCY_HOURS, and not inside the retry back-off that
    follows a failed run."""
    now = now or datetime.now(timezone.utc)
    if backup_service.is_backup_locked():
        return False
    latest = backup_service.get_latest()
    if latest and latest.get("status") == "failed" and latest.get("finished_at"):
        failed_at = datetime.fromisoformat(latest["finished_at"])
        if now - failed_at < timedelta(minutes=RETRY_AFTER_FAILURE_MINUTES):
            return False
    last_ok = backup_service.get_latest_successful()
    if not last_ok:
        return True
    return now - datetime.fromisoformat(last_ok["finished_at"]) >= timedelta(hours=config.BACKUP_FREQUENCY_HOURS)


def tick() -> bool:
    """One scheduler iteration. Returns True if it started a backup."""
    _write_heartbeat()
    if not is_due():
        return False
    logger.info("Scheduled backup starting")
    backup_service.run_full_backup()  # records its own result and alerts on failure
    return True


def _loop() -> None:
    while True:
        try:
            tick()
        except Exception:  # noqa: BLE001 - the loop must survive any single failure
            logger.exception("Backup scheduler tick failed")
        time.sleep(TICK_SECONDS)


def start() -> bool:
    """Start the scheduler thread in this process if scheduling is enabled and
    backups can actually run. Idempotent. Returns True if a thread is running."""
    global _thread
    if not config.BACKUP_SCHEDULER_ENABLED:
        return False
    try:
        backup_service._fernet()
        backup_service._object_store_settings()
    except backup_service.BackupConfigError as exc:
        logger.error("Backup scheduler NOT started: %s", exc)
        return False
    with _thread_lock:
        if _thread and _thread.is_alive():
            return True
        _thread = threading.Thread(target=_loop, name="backup-scheduler", daemon=True)
        _thread.start()
    logger.info("Backup scheduler started (every %sh)", config.BACKUP_FREQUENCY_HOURS)
    return True

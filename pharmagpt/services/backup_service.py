"""
pharmagpt/services/backup_service.py — Backup & Recovery framework.

Remediates the Compliance Matrix's Critical "Backup & Recovery" finding: the
production SQLite database (all QMS data, including the audit trail —
qms_audit_trail — and electronic signatures — qms_esignatures) had no
automated backup mechanism at all. See docs/BACKUP_ARCHITECTURE.md for the
full design rationale and docs/BACKUP_SOP.md / docs/DISASTER_RECOVERY_SOP.md
for the operating procedures this module implements.

Scope discipline (explicit, per the task that created this module): this file
NEVER reads, writes, or modifies RBAC, e-signature, or audit-trail logic. It
treats pharmagpt.db as an opaque file to copy, using SQLite's own online
backup API — the audit trail and e-signature tables are protected simply by
being inside that file, not by any code here understanding their schema.

Backup targets, one archive member each, bundled into one encrypted file per
run:
  db/pharmagpt.db          — SQLite online backup (sqlite3.Connection.backup)
  uploads/                 — UPLOAD_FOLDER, tar'd
  generated_documents/     — GENERATED_DOCS_PATH, tar'd
  config_snapshot.json     — sanitized (non-secret) effective configuration
  postgres/<table>.json    — one JSON array per table in POSTGRES_BACKUP_TABLES,
                              via the existing service-role Supabase client
                              (pharmagpt/services/supabase_client.py, unmodified)
  manifest.json            — checksums, row/file counts, run metadata

The bundle is tar+gzip'd, SHA-256'd, then encrypted at rest with Fernet
(symmetric AES via the `cryptography` package — already a pinned dependency,
no new requirement added).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from pharmagpt import config
from pharmagpt import database as db_module

logger = logging.getLogger(__name__)

STATE_FILENAME = "backup_state.json"
VERIFICATION_STATE_FILENAME = "verification_state.json"
MANIFEST_FILENAME = "manifest.json"
LOCK_FILENAME = ".backup.lock"
MAX_HISTORY_RUNS = 500  # rotation cap for backup_state.json — bounded, not unbounded growth
MAX_VERIFICATION_HISTORY = 200
LOCK_STALE_SECONDS = 2 * 3600  # a lock this old means the process that held it crashed, not that it's still running

# Config keys considered safe to include in the non-secret configuration
# snapshot. Deliberately an allowlist (not a denylist of secret names) so a
# future secret-looking config addition is excluded by default, not leaked
# by default. Never extend this with *_KEY, *_SECRET, *_TOKEN, *_PASSWORD.
_SAFE_CONFIG_KEYS = [
    "GEMINI_MODEL", "FLASK_DEBUG", "FLASK_PORT", "DATABASE_BACKEND",
    "PROJECTS_BACKEND", "KB_BACKEND", "EQUIPMENT_BACKEND", "QMS_BACKEND",
    "MAX_FILE_SIZE", "ALLOWED_EXTENSIONS", "PAGE_TIMEOUT_SECONDS",
    "EXTRACTION_WORKERS", "GC_INTERVAL_PAGES", "PROGRESS_WRITE_EVERY_N_PAGES",
    "URS_GENERATION_BATCH_SIZE", "URS_GENERATION_SLOW_WARNING_SECONDS",
    "URS_GENERATION_MAX_RETRIES", "BACKUP_FREQUENCY_HOURS",
    "BACKUP_SNAPSHOT_RETENTION_DAYS", "BACKUP_DAILY_RETENTION_DAYS",
    "POSTGRES_BACKUP_TABLES",
]


class BackupConfigError(RuntimeError):
    """Raised when a backup/restore/verify operation cannot run because
    required configuration (encryption key, etc.) is missing. Never silently
    substitutes a default for anything security-relevant — see
    BACKUP_ENCRYPTION_KEY's docstring in config.py."""


class BackupIntegrityError(RuntimeError):
    """Raised when a backup fails its own post-write verification, or a
    restore-drill / restore finds the archive unreadable or inconsistent."""


# ── data shapes ────────────────────────────────────────────────────────────

@dataclass
class BackupRunResult:
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: str = "running"  # running | success | failed
    archive_path: str | None = None
    archive_sha256: str | None = None
    size_bytes: int | None = None
    duration_seconds: float | None = None
    targets: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── encryption ─────────────────────────────────────────────────────────────

def _fernet() -> Fernet:
    key = config.BACKUP_ENCRYPTION_KEY
    if not key:
        raise BackupConfigError(
            "BACKUP_ENCRYPTION_KEY is not set. Generate one with "
            "scripts/generate_backup_key.py and store it in your secrets "
            "vault — backups are never written unencrypted."
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as exc:  # invalid key format
        raise BackupConfigError(f"BACKUP_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc


def encrypt_file(src_path: Path, dst_path: Path) -> None:
    fernet = _fernet()
    data = src_path.read_bytes()
    dst_path.write_bytes(fernet.encrypt(data))


def decrypt_file(src_path: Path, dst_path: Path) -> None:
    fernet = _fernet()
    data = src_path.read_bytes()
    try:
        plaintext = fernet.decrypt(data)
    except InvalidToken as exc:
        raise BackupIntegrityError(
            f"Backup archive {src_path} could not be decrypted — wrong "
            "BACKUP_ENCRYPTION_KEY or corrupted file."
        ) from exc
    dst_path.write_bytes(plaintext)


# ── paths ──────────────────────────────────────────────────────────────────

def _backup_dir() -> Path:
    """Resolve BACKUP_DIR and try to ensure its subfolders exist.

    Deliberately swallows OSError (permission denied, missing mount, etc.)
    instead of raising: this function is called by read-only status
    functions (get_latest, get_history, check_freshness, ...) on every
    dashboard page load, and a misconfigured/unwritable BACKUP_DIR must
    degrade to "no backups on record" (handled gracefully everywhere else
    in this module) rather than crash the status API with an unhandled
    OSError — see get_configuration_status() for how this is surfaced to
    the operator as an explicit ❌ Failed state instead of a raw exception."""
    p = Path(config.BACKUP_DIR).resolve()
    try:
        (p / "snapshots").mkdir(parents=True, exist_ok=True)
        (p / "daily").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create backup directories under %s: %s", p, exc)
    return p


def _state_path() -> Path:
    return _backup_dir() / STATE_FILENAME


def _verification_state_path() -> Path:
    return _backup_dir() / VERIFICATION_STATE_FILENAME


# ── concurrency guard ────────────────────────────────────────────────────────
# scripts/run_backup.py originally had its own lock-file check, but it was
# TOCTOU-racy (a plain path.exists() check followed by a separate write,
# with a window in between two near-simultaneous invocations could both
# pass) and only protected the CLI/cron entrypoint — a web request via
# POST /admin/backup/api/run went through job_runner with no lock at all,
# so two clicks of "Run Backup Now" (or a click racing a cron run) could
# start two concurrent run_full_backup() calls stepping on the same state
# file. The lock now lives here, in the one place both entrypoints call
# through, and uses an atomic O_CREAT|O_EXCL file create (atomic on both
# POSIX and Windows) instead of a check-then-write pair.

def _acquire_lock() -> bool:
    lock_path = _backup_dir() / LOCK_FILENAME
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        try:
            age = time.time() - lock_path.stat().st_mtime
        except OSError:
            age = 0
        if age > LOCK_STALE_SECONDS:
            # The process that held this lock is gone (a run cannot
            # plausibly still be in progress after 2 hours) — reclaim it
            # rather than block backups indefinitely because of one crash.
            logger.warning("Reclaiming a stale backup lock (%.0fs old): %s", age, lock_path)
            try:
                lock_path.unlink()
            except OSError:
                return False
            return _acquire_lock()
        return False
    except OSError:
        # Cannot even attempt the lock (e.g. BACKUP_DIR unwritable) — let
        # the caller's own encryption-key/backup-service checks surface
        # the real reason; don't block on a lock we can't create anyway.
        return True


def _release_lock() -> None:
    try:
        (_backup_dir() / LOCK_FILENAME).unlink(missing_ok=True)
    except OSError:
        pass


def is_backup_locked() -> bool:
    """Read-only check used by the /api/run pre-flight — never acquires."""
    lock_path = _backup_dir() / LOCK_FILENAME
    if not lock_path.exists():
        return False
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    return age <= LOCK_STALE_SECONDS


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ── state store (dedicated file — no table added to pharmagpt.db) ─────────
# Deliberately NOT a table inside pharmagpt.db: this module must never touch
# the schema of the database it is backing up, so run history lives in its
# own small JSON file instead. Read/write is append-then-rotate, not a
# database, so no concurrent-writer corruption handling is needed beyond
# what a single cron-triggered process already guarantees (one run at a
# time — see scripts/run_backup.py's lock file).

def _load_state() -> list[dict[str, Any]]:
    p = _state_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("backup_state.json unreadable (%s) — starting a fresh history", exc)
        return []


def _save_run(result: BackupRunResult) -> None:
    history = _load_state()
    history.append(result.to_dict())
    history = history[-MAX_HISTORY_RUNS:]
    p = _state_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(history, indent=2), encoding="utf-8")
    tmp.replace(p)  # atomic on POSIX and Windows (NTFS) — no torn-write state file


def get_history(limit: int = 20) -> list[dict[str, Any]]:
    return list(reversed(_load_state()))[:limit]


def get_latest() -> dict[str, Any] | None:
    history = _load_state()
    return history[-1] if history else None


def get_latest_successful() -> dict[str, Any] | None:
    successes = [r for r in _load_state() if r.get("status") == "success"]
    return successes[-1] if successes else None


def get_latest_failed() -> dict[str, Any] | None:
    failures = [r for r in _load_state() if r.get("status") == "failed"]
    return failures[-1] if failures else None


def _load_verification_state() -> list[dict[str, Any]]:
    p = _verification_state_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("verification_state.json unreadable (%s) — starting a fresh history", exc)
        return []


def _save_verification(report: dict[str, Any]) -> None:
    history = _load_verification_state()
    history.append(report)
    history = history[-MAX_VERIFICATION_HISTORY:]
    p = _verification_state_path()
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(history, default=str, indent=2), encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        # Recording the verification result is best-effort by design: a
        # storage problem here must never turn a completed verification
        # drill into a reported failure — the drill itself already
        # succeeded or failed independently of whether we could log it.
        logger.error("Could not persist verification result: %s", exc)


def get_latest_verification() -> dict[str, Any] | None:
    history = _load_verification_state()
    return history[-1] if history else None


def get_verification_history(limit: int = 20) -> list[dict[str, Any]]:
    return list(reversed(_load_verification_state()))[:limit]


def check_freshness() -> dict[str, Any]:
    """Used by both the dashboard and monitoring: is the last *successful*
    run recent enough given the configured frequency?"""
    history = _load_state()
    successes = [r for r in history if r.get("status") == "success"]
    if not successes:
        return {"fresh": False, "reason": "No successful backup has ever completed.", "last_success_at": None}
    last = successes[-1]
    last_dt = datetime.fromisoformat(last["finished_at"])
    age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
    stale_after = config.BACKUP_FREQUENCY_HOURS * 2
    fresh = age_hours <= stale_after
    return {
        "fresh": fresh,
        "last_success_at": last["finished_at"],
        "age_hours": round(age_hours, 2),
        "stale_after_hours": stale_after,
        "reason": None if fresh else f"Last successful backup is {age_hours:.1f}h old (threshold {stale_after}h).",
    }


# ── alerting ────────────────────────────────────────────────────────────────

def _alert(subject: str, detail: str) -> None:
    logger.critical("BACKUP ALERT: %s — %s", subject, detail)
    url = config.BACKUP_ALERT_WEBHOOK_URL
    if not url:
        logger.warning(
            "BACKUP_ALERT_WEBHOOK_URL is not configured — the alert above "
            "was only logged, not sent anywhere. Configure a webhook (Slack/"
            "Teams/PagerDuty/generic) per docs/BACKUP_SOP.md."
        )
        return
    payload = json.dumps({"text": f"[PharmaGPT Backup] {subject}: {detail}"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:  # noqa: BLE001 — alerting must never raise into the caller
        logger.error("Failed to POST backup alert webhook: %s", exc)


# ── target collectors ───────────────────────────────────────────────────────

def _backup_sqlite(dest_dir: Path) -> dict[str, Any]:
    """Online, non-locking copy via SQLite's own backup API — never a raw
    file copy, which risks capturing a torn write against the live WAL."""
    dest_file = dest_dir / "pharmagpt.db"
    src = sqlite3.connect(f"file:{db_module.DB_PATH}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(str(dest_file))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    # Post-copy integrity check on the *copy*, never the live file.
    check_conn = sqlite3.connect(str(dest_file))
    try:
        result = check_conn.execute("PRAGMA integrity_check").fetchone()[0]
        row_counts = {}
        for table in ("qms_audit_trail", "qms_esignatures"):
            try:
                row_counts[table] = check_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                row_counts[table] = None  # table doesn't exist in this DB — not fatal
    finally:
        check_conn.close()

    if result != "ok":
        raise BackupIntegrityError(f"SQLite backup copy failed PRAGMA integrity_check: {result}")

    return {
        "source": str(db_module.DB_PATH),
        "size_bytes": dest_file.stat().st_size,
        "integrity_check": result,
        "row_counts": row_counts,
    }


def _tar_directory(src_dir: str | os.PathLike, dest_tar: Path) -> dict[str, Any]:
    src = Path(src_dir)
    if not src.exists():
        return {"source": str(src), "present": False, "file_count": 0}
    file_count, total_bytes = 0, 0
    with tarfile.open(dest_tar, "w:gz") as tar:
        for root, _dirs, files in os.walk(src):
            for name in files:
                fp = Path(root) / name
                tar.add(fp, arcname=str(fp.relative_to(src)))
                file_count += 1
                total_bytes += fp.stat().st_size
    return {"source": str(src), "present": True, "file_count": file_count, "total_bytes": total_bytes}


def _config_snapshot() -> dict[str, Any]:
    snapshot = {}
    for key in _SAFE_CONFIG_KEYS:
        if hasattr(config, key):
            snapshot[key] = getattr(config, key)
    return snapshot


def _backup_postgres_tables(dest_dir: Path) -> dict[str, Any]:
    """Row-level JSON export via PostgREST (service-role client) — no extra
    binary dependency, works on Render's plain Python runtime today. See
    config.SUPABASE_DB_URL for the optional pg_dump-based supplementary path.
    """
    summary: dict[str, Any] = {"tables": {}, "skipped": None}
    try:
        from pharmagpt.services.supabase_client import get_service_role_client
        client = get_service_role_client()
    except Exception as exc:  # ValueError (missing env) or import-time issue
        summary["skipped"] = f"Supabase service-role client unavailable: {exc}"
        logger.warning("Postgres backup skipped: %s", summary["skipped"])
        return summary

    for table in config.POSTGRES_BACKUP_TABLES:
        try:
            resp = client.table(table).select("*").execute()
            rows = resp.data or []
            (dest_dir / f"{table}.json").write_text(json.dumps(rows, default=str, indent=2), encoding="utf-8")
            summary["tables"][table] = len(rows)
        except Exception as exc:  # noqa: BLE001 — one bad table must not abort the whole backup
            summary["tables"][table] = f"error: {exc}"
            logger.error("Postgres backup: table %s failed: %s", table, exc)

    if config.SUPABASE_DB_URL and shutil.which("pg_dump"):
        dump_path = dest_dir / "pg_dump.sql"
        rc = os.system(  # noqa: S605 — operator-supplied connection string, not user input
            f'pg_dump "{config.SUPABASE_DB_URL}" --no-owner --no-privileges -f "{dump_path}"'
        )
        summary["pg_dump"] = "ok" if rc == 0 and dump_path.exists() else f"pg_dump exited {rc}"
    else:
        summary["pg_dump"] = "skipped (SUPABASE_DB_URL unset or pg_dump not on PATH)"

    return summary


# ── retention ────────────────────────────────────────────────────────────────

def _prune(subdir: str, retention_days: int) -> int:
    cutoff = time.time() - retention_days * 86400
    removed = 0
    d = _backup_dir() / subdir
    for f in d.glob("*.bak.enc"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed


def _promote_to_daily_if_first_of_day(snapshot_path: Path) -> None:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    daily_dir = _backup_dir() / "daily"
    already_have_today = any(f.name.startswith(today) for f in daily_dir.glob("*.bak.enc"))
    if not already_have_today:
        shutil.copy2(snapshot_path, daily_dir / snapshot_path.name)


def _offsite_copy(snapshot_path: Path) -> str:
    if not config.BACKUP_OFFSITE_DIR:
        return "not configured — same-disk backup only (see docs/BACKUP_SOP.md 'Remaining risk')"
    try:
        dest = Path(config.BACKUP_OFFSITE_DIR)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_path, dest / snapshot_path.name)
        return "ok"
    except OSError as exc:
        logger.error("Offsite backup copy failed: %s", exc)
        return f"failed: {exc}"


# ── orchestration ───────────────────────────────────────────────────────────

def run_full_backup() -> BackupRunResult:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = datetime.now(timezone.utc)
    result = BackupRunResult(run_id=run_id, started_at=started.isoformat())

    # Fail fast on missing encryption key, before doing any work.
    try:
        _fernet()
    except BackupConfigError as exc:
        result.status, result.error = "failed", str(exc)
        result.finished_at = datetime.now(timezone.utc).isoformat()
        _save_run(result)
        _alert("Backup configuration error", str(exc))
        return result

    if not _acquire_lock():
        result.status = "failed"
        result.error = "A backup is already in progress."
        result.finished_at = datetime.now(timezone.utc).isoformat()
        _save_run(result)
        # Deliberately not alerted — a second concurrent trigger racing an
        # already-running backup is expected/benign, not an operational
        # failure worth paging anyone over.
        return result

    try:
        _run_full_backup_locked(result, started, run_id)
    finally:
        _release_lock()

    return result


def _run_full_backup_locked(result: BackupRunResult, started: datetime, run_id: str) -> None:
    with tempfile.TemporaryDirectory(prefix="pharmagpt_backup_") as tmp:
        tmp_path = Path(tmp)
        bundle_dir = tmp_path / "bundle"
        (bundle_dir / "db").mkdir(parents=True)
        (bundle_dir / "postgres").mkdir(parents=True)

        try:
            result.targets["sqlite"] = _backup_sqlite(bundle_dir / "db")

            result.targets["uploads"] = _tar_directory(config.UPLOAD_FOLDER, bundle_dir / "uploads.tar.gz")

            generated_docs = os.getenv("GENERATED_DOCS_PATH") or str(
                Path(__file__).resolve().parents[2] / "generated_documents"
            )
            result.targets["generated_documents"] = _tar_directory(generated_docs, bundle_dir / "generated_documents.tar.gz")

            (bundle_dir / "config_snapshot.json").write_text(
                json.dumps(_config_snapshot(), default=str, indent=2), encoding="utf-8"
            )
            result.targets["config"] = {"keys_captured": len(_config_snapshot())}

            result.targets["postgres"] = _backup_postgres_tables(bundle_dir / "postgres")

            manifest = {
                "run_id": run_id, "started_at": result.started_at,
                "targets": result.targets, "app": "PharmaGPT",
            }
            (bundle_dir / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            # Bundle -> tar.gz -> encrypt
            bundle_tar = tmp_path / "bundle.tar.gz"
            with tarfile.open(bundle_tar, "w:gz") as tar:
                tar.add(bundle_dir, arcname=".")

            snapshot_name = f"{run_id}.bak.enc"
            snapshot_path = _backup_dir() / "snapshots" / snapshot_name
            encrypt_file(bundle_tar, snapshot_path)

            result.archive_path = str(snapshot_path)
            result.archive_sha256 = _sha256(snapshot_path)
            result.size_bytes = snapshot_path.stat().st_size

            # Verify immediately: decrypt round-trip must reproduce the same bytes.
            verify_tmp = tmp_path / "verify_roundtrip.tar.gz"
            decrypt_file(snapshot_path, verify_tmp)
            if _sha256(verify_tmp) != _sha256(bundle_tar):
                raise BackupIntegrityError("Post-encryption decrypt round-trip did not match the original archive.")
            result.verification = {"decrypt_roundtrip": "ok"}

            _promote_to_daily_if_first_of_day(snapshot_path)
            result.targets["offsite"] = _offsite_copy(snapshot_path)

            removed_snapshots = _prune("snapshots", config.BACKUP_SNAPSHOT_RETENTION_DAYS)
            removed_daily = _prune("daily", config.BACKUP_DAILY_RETENTION_DAYS)
            result.targets["retention"] = {"snapshots_pruned": removed_snapshots, "daily_pruned": removed_daily}

            result.status = "success"

        except Exception as exc:  # noqa: BLE001 — must always reach _save_run + alert
            logger.exception("Backup run %s failed", run_id)
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"

    result.finished_at = datetime.now(timezone.utc).isoformat()
    result.duration_seconds = round(
        (datetime.fromisoformat(result.finished_at) - started).total_seconds(), 2
    )
    _save_run(result)

    if result.status != "success":
        _alert(f"Backup run {run_id} failed", result.error or "unknown error")
    if config.BACKUP_OFFSITE_DIR is None:
        logger.warning("BACKUP_OFFSITE_DIR is not configured — this backup exists only on the primary disk.")


# ── restore / verification drill ────────────────────────────────────────────

def _extract_backup(archive_path: Path, dest_dir: Path) -> Path:
    """Decrypt + untar a .bak.enc archive into dest_dir. Returns the bundle root."""
    decrypted = dest_dir / "bundle.tar.gz"
    decrypt_file(archive_path, decrypted)
    with tarfile.open(decrypted, "r:gz") as tar:
        tar.extractall(dest_dir)  # noqa: S202 — archive is our own encrypted output, not third-party input
    return dest_dir


def verify_backup(archive_path: str | None = None) -> dict[str, Any]:
    """Restore-drill: decrypt + extract the given (or latest) backup into a
    throwaway temp directory — NEVER the live DB_PATH/UPLOAD_FOLDER — and
    check it is actually usable. This is what docs/BACKUP_VALIDATION_PROTOCOL.md
    requires be run periodically, and what scripts/verify_backup.py drives to
    produce a Backup Test Report.

    Public contract: this function NEVER raises — every failure mode
    (missing archive, missing/invalid encryption key, corrupted archive,
    unexpected error) is caught and returned as {"overall": "fail", ...}
    instead. Callers (the CLI and the /admin/backup/api/verify route) can
    render the result directly without a try/except of their own, and the
    route never needs to translate a raised exception into a user-facing
    message. Every call, pass or fail, is recorded via _save_verification()
    so the dashboard's "Last Verification" stat survives a page reload."""
    try:
        report = _run_verification_checks(archive_path)
    except Exception as exc:  # noqa: BLE001 — this function must never raise, see docstring
        logger.exception("Verification drill for %s raised unexpectedly", archive_path)
        report = {
            "archive": archive_path,
            "checks": {},
            "overall": "fail",
            "error": f"{type(exc).__name__}: {exc}",
        }
    report.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    _save_verification(report)
    return report


def _run_verification_checks(archive_path: str | None) -> dict[str, Any]:
    """Implementation detail of verify_backup() — may raise; the caller
    always catches. Kept separate so verify_backup()'s try/except doesn't
    have to be threaded through every branch below by hand."""
    report: dict[str, Any] = {"archive": archive_path, "checks": {}, "overall": "fail"}

    path = Path(archive_path) if archive_path else _latest_archive_path()
    if path is None or not path.exists():
        report["error"] = "No backup archive found."
        return report
    report["archive"] = str(path)

    started = time.time()
    with tempfile.TemporaryDirectory(prefix="pharmagpt_restore_drill_") as tmp:
        tmp_path = Path(tmp)
        try:
            _extract_backup(path, tmp_path)
        except (BackupIntegrityError, BackupConfigError) as exc:
            report["error"] = str(exc)
            return report

        manifest_path = tmp_path / MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        report["checks"]["manifest_present"] = manifest_path.exists()

        db_path = tmp_path / "db" / "pharmagpt.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                report["checks"]["sqlite_integrity_check"] = integrity
                row_counts = {}
                for table in ("qms_audit_trail", "qms_esignatures"):
                    try:
                        row_counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    except sqlite3.OperationalError:
                        row_counts[table] = None
                report["checks"]["row_counts"] = row_counts
                expected = (manifest.get("targets", {}).get("sqlite", {}) or {}).get("row_counts", {})
                report["checks"]["row_counts_match_manifest"] = row_counts == expected if expected else "no manifest baseline"
            finally:
                conn.close()
        else:
            report["checks"]["sqlite_integrity_check"] = "MISSING — no db/pharmagpt.db in archive"

        for name, tarname in (("uploads", "uploads.tar.gz"), ("generated_documents", "generated_documents.tar.gz")):
            tar_path = tmp_path / tarname
            if tar_path.exists():
                with tarfile.open(tar_path) as tar:
                    members = tar.getmembers()
                report["checks"][f"{name}_file_count"] = len(members)
                expected_count = (manifest.get("targets", {}).get(name, {}) or {}).get("file_count")
                report["checks"][f"{name}_count_matches_manifest"] = (
                    len(members) == expected_count if expected_count is not None else "n/a"
                )
            else:
                report["checks"][f"{name}_file_count"] = 0

        pg_dir = tmp_path / "postgres"
        pg_tables = list(pg_dir.glob("*.json")) if pg_dir.exists() else []
        report["checks"]["postgres_tables_present"] = len(pg_tables)
        for f in pg_tables:
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report["checks"][f"postgres_{f.stem}_valid_json"] = False
                break
        else:
            report["checks"]["postgres_json_all_valid"] = True

    report["duration_seconds"] = round(time.time() - started, 2)
    critical_checks = [
        report["checks"].get("sqlite_integrity_check") == "ok",
        report["checks"].get("manifest_present", False),
    ]
    report["overall"] = "pass" if all(critical_checks) else "fail"
    return report


def _latest_archive_path() -> Path | None:
    snap_dir = _backup_dir() / "snapshots"
    archives = sorted(snap_dir.glob("*.bak.enc"), key=lambda p: p.stat().st_mtime)
    return archives[-1] if archives else None


def restore_from_backup(archive_path: str, target_dir: str, confirm_live: bool = False) -> dict[str, Any]:
    """Real restore, for actual DR use. Always writes to `target_dir` — a
    fresh directory the operator chooses. Will only ever write into the
    live DB_PATH/UPLOAD_FOLDER locations if the caller passes
    confirm_live=True (scripts/restore_from_backup.py gates this behind an
    interactive typed confirmation — never set programmatically)."""
    target = Path(target_dir)
    if target.exists() and any(target.iterdir()) and not confirm_live:
        raise BackupIntegrityError(
            f"{target} already exists and is not empty. Restore to an empty "
            "directory, or pass confirm_live=True if you have independently "
            "confirmed this is the intended live-overwrite target."
        )
    target.mkdir(parents=True, exist_ok=True)
    _extract_backup(Path(archive_path), target)
    return {"restored_to": str(target), "archive": archive_path}


def run_restore_drill(archive_path: str | None = None) -> dict[str, Any]:
    """Dashboard-safe "Restore" action: restores the given (or latest)
    archive into BACKUP_DIR/restore_staging/ — never DB_PATH, never
    UPLOAD_FOLDER, never any live path — so an operator can prove an
    archive actually restores and inspect the result, without the web
    dashboard ever being able to trigger a live-data overwrite. A true
    live-data restore stays CLI-only (restore_from_backup(), gated behind
    scripts/restore_from_backup.py's interactive typed confirmation) —
    intentionally not exposed over HTTP.

    The staging directory is cleared before each run (it only ever holds
    the previous drill's output, so this is always safe) rather than
    accumulated across runs.

    Public contract: like verify_backup(), this function never raises —
    every failure is returned as {"success": False, ...}."""
    try:
        path = Path(archive_path) if archive_path else _latest_archive_path()
        if path is None or not path.exists():
            return {"success": False, "error": "No backup archive is available to restore."}

        staging = _backup_dir() / "restore_staging"
        if staging.exists():
            shutil.rmtree(staging)

        result = restore_from_backup(str(path), str(staging))
        return {
            "success": True,
            "archive": str(path),
            "restored_to": result["restored_to"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001 — see docstring: this function must never raise
        logger.exception("Restore drill for %s raised unexpectedly", archive_path)
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


# ── configuration detection ─────────────────────────────────────────────────
# Each check below returns {"status": "configured"|"missing"|"failed",
# "message": "<one plain-English sentence, safe to show a non-technical
# operator as-is>"}. "missing" means "not yet configured, and that's
# expected/recoverable" (e.g. an optional feature nobody has turned on
# yet). "failed" means "configured, but broken" (e.g. a path that's set
# but not writable) — the UI must be able to tell these apart, per this
# module's UX requirements: a missing optional feature is a mild ⚠, a
# broken required one is a ❌.

def _check_encryption_key() -> dict[str, str]:
    if not config.BACKUP_ENCRYPTION_KEY:
        return {"status": "missing", "message": "No encryption key has been configured yet."}
    try:
        Fernet(config.BACKUP_ENCRYPTION_KEY.encode("utf-8"))
    except Exception:  # noqa: BLE001 — any malformed-key error collapses to one message
        return {"status": "failed", "message": "The configured encryption key is invalid."}
    return {"status": "configured", "message": "Encryption key is configured."}


def _check_backup_service() -> dict[str, str]:
    """Can the backup directory actually be written to? This is the one
    check that exercises a real filesystem write, not just a path check."""
    try:
        d = _backup_dir()
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return {"status": "failed", "message": "The backup storage location is not writable."}
    return {"status": "configured", "message": "Backup storage is reachable and writable."}


def _check_scheduler() -> dict[str, str]:
    if not config.BACKUP_SCHEDULER_ENABLED:
        return {
            "status": "missing",
            "message": "Automatic scheduling is not enabled — backups must be started manually.",
        }
    return {
        "status": "configured",
        "message": "Automatic scheduling is enabled. (PharmaGPT records that this was configured, but "
                    "cannot independently confirm an external scheduler is calling in — the Backup "
                    "Freshness check below is the real signal that runs are actually happening.)",
    }


def _check_offsite_storage() -> dict[str, str]:
    if not config.BACKUP_OFFSITE_DIR:
        return {
            "status": "missing",
            "message": "Offsite storage is not configured — backups exist on the primary disk only.",
        }
    try:
        d = Path(config.BACKUP_OFFSITE_DIR)
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return {"status": "failed", "message": "The configured offsite storage location is not writable."}
    return {"status": "configured", "message": "Offsite storage is reachable and writable."}


def _check_database_backup() -> dict[str, str]:
    db_path = getattr(db_module, "DB_PATH", None)
    if not db_path:
        return {"status": "missing", "message": "No production database path is configured."}
    if not Path(db_path).exists():
        return {"status": "failed", "message": "The production database file could not be found."}
    return {"status": "configured", "message": "The production database is present and reachable."}


def _check_document_backup() -> dict[str, str]:
    upload_folder = getattr(config, "UPLOAD_FOLDER", None)
    if not upload_folder:
        return {"status": "missing", "message": "No document storage location is configured."}
    # Not existing yet is normal on a brand-new deployment (it is created on
    # first upload) — that's a "missing"/not-yet-used state, not a failure.
    if not Path(upload_folder).exists():
        return {
            "status": "missing",
            "message": "No documents have been uploaded yet — storage will be created automatically on first upload.",
        }
    return {"status": "configured", "message": "Document storage is present and reachable."}


def get_configuration_status() -> dict[str, dict[str, str]]:
    """One check per component this module's dashboard needs to explain to
    an operator. Keys match the six components named in the Backup &
    Recovery production-readiness requirements."""
    return {
        "backup_service": _check_backup_service(),
        "scheduler": _check_scheduler(),
        "encryption_key": _check_encryption_key(),
        "offsite_storage": _check_offsite_storage(),
        "database_backup": _check_database_backup(),
        "document_backup": _check_document_backup(),
    }


def is_backup_runnable() -> tuple[bool, str | None]:
    """Server-side gate mirroring the dashboard's button-disable logic —
    used by the /api/run route so a request that is guaranteed to fail
    (per this task's explicit "never allow an action guaranteed to fail"
    requirement) is rejected immediately with a friendly reason instead of
    being submitted to the background job runner and failing a few seconds
    later. Returns (True, None) if a backup can proceed, else (False, reason)."""
    cfg = get_configuration_status()
    if cfg["encryption_key"]["status"] != "configured":
        return False, "Backups cannot run yet — an encryption key has not been configured."
    if cfg["backup_service"]["status"] != "configured":
        return False, "Backups cannot run yet — the backup storage location is not writable."
    if cfg["database_backup"]["status"] == "failed":
        return False, "Backups cannot run yet — the production database could not be found."
    if is_backup_locked():
        return False, "A backup is already in progress. Please wait for it to finish."
    return True, None


def is_archive_available_for_verification_or_restore() -> tuple[bool, str | None]:
    """Same idea as is_backup_runnable(), for the Verification Drill and
    Restore actions: both need a decryptable archive to exist first."""
    cfg = get_configuration_status()
    if cfg["encryption_key"]["status"] != "configured":
        return False, "Not available — an encryption key has not been configured, so no backup can be decrypted."
    if _latest_archive_path() is None:
        return False, "Not available — no successful backup exists yet."
    return True, None


# ── dashboard aggregation ────────────────────────────────────────────────────

def get_next_scheduled_backup() -> dict[str, Any]:
    if not config.BACKUP_SCHEDULER_ENABLED:
        return {"scheduled": False, "message": "Scheduling is not configured — backups must be run manually."}
    last_success = get_latest_successful()
    if not last_success:
        return {"scheduled": True, "estimated_at": None, "message": "Waiting for the first successful backup."}
    last_dt = datetime.fromisoformat(last_success["finished_at"])
    from datetime import timedelta
    next_dt = last_dt + timedelta(hours=config.BACKUP_FREQUENCY_HOURS)
    return {"scheduled": True, "estimated_at": next_dt.isoformat(), "message": None}


_HEALTH_ORDER = {"healthy": 0, "warning": 1, "critical": 2}


def compute_health() -> dict[str, Any]:
    """Deterministic traffic-light rollup for the dashboard. Combines
    configuration status, the last run's outcome, freshness, and the last
    verification result into one level (worst-of) plus the plain-English
    reasons behind it — the dashboard renders `reasons` directly instead of
    inventing its own explanation from the raw fields."""
    cfg = get_configuration_status()
    freshness = check_freshness()
    latest = get_latest()
    latest_verification = get_latest_verification()

    level = "healthy"
    reasons: list[str] = []

    def _bump(new_level: str, reason: str) -> None:
        nonlocal level
        reasons.append(reason)
        if _HEALTH_ORDER[new_level] > _HEALTH_ORDER[level]:
            level = new_level

    if cfg["encryption_key"]["status"] != "configured":
        _bump("critical", "Backups cannot run — encryption key is not configured.")
    if cfg["backup_service"]["status"] == "failed":
        _bump("critical", "Backup storage is not writable.")
    if cfg["database_backup"]["status"] == "failed":
        _bump("critical", "The production database could not be found.")

    if latest is None:
        _bump("warning", "No backup has been run yet.")
    elif latest.get("status") == "failed":
        _bump("critical", "The most recent backup run failed.")

    if latest is not None and latest.get("status") == "success" and not freshness.get("fresh", False):
        _bump("warning", "The most recent successful backup is older than expected.")

    if cfg["offsite_storage"]["status"] == "missing":
        _bump("warning", "Offsite storage is not configured — backups exist on one disk only.")
    elif cfg["offsite_storage"]["status"] == "failed":
        _bump("critical", "Offsite storage is configured but not writable.")

    if cfg["scheduler"]["status"] == "missing":
        _bump("warning", "Automatic scheduling is not enabled.")

    if latest_verification is None:
        _bump("warning", "No verification drill has been run yet.")
    elif latest_verification.get("overall") != "pass":
        _bump("warning", "The most recent verification drill did not pass.")

    if not reasons:
        reasons.append("All checks passed.")

    return {"level": level, "reasons": reasons}


def get_dashboard_status() -> dict[str, Any]:
    """Single aggregator backing GET /admin/backup/api/status — kept in the
    service layer (not the route) so it has direct test coverage independent
    of Flask/RBAC plumbing."""
    return {
        "latest_run": get_latest(),
        "freshness": check_freshness(),
        "last_successful_backup": get_latest_successful(),
        "last_failed_backup": get_latest_failed(),
        "last_verification": get_latest_verification(),
        "next_scheduled_backup": get_next_scheduled_backup(),
        "health": compute_health(),
    }

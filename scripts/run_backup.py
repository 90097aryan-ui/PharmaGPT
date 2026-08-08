"""
scripts/run_backup.py — Backup entrypoint for cron/Render Cron Job.

Usage:
    python scripts/run_backup.py

Exit code 0 on success, 1 on failure (so a cron/scheduler wrapper can alert
on a non-zero exit independently of the in-app webhook alert — belt and
braces monitoring, see docs/BACKUP_SOP.md).

Overlapping runs (a slow run plus the next scheduled trigger firing before
it finished, or this script racing a dashboard-triggered "Run Backup Now")
are guarded centrally in backup_service.run_full_backup() itself via an
atomic lock file — not here. An earlier version of this script kept its own
separate, non-atomic lock check, which (a) had a check-then-write race
window and (b) only protected this CLI entrypoint, not the web dashboard's
POST /admin/backup/api/run path. Keeping the lock in one place means both
entrypoints share the same protection and can never fight over two
different lock implementations touching the same file.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt.logging_config import configure_logging  # noqa: E402

configure_logging()

import logging  # noqa: E402

from pharmagpt.services import backup_service  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> int:
    result = backup_service.run_full_backup()

    if result.status == "success":
        logger.info(
            "Backup %s succeeded: %s bytes, %.1fs, sha256=%s",
            result.run_id, result.size_bytes, result.duration_seconds, result.archive_sha256,
        )
        return 0

    logger.error("Backup %s FAILED: %s", result.run_id, result.error)
    return 1


if __name__ == "__main__":
    sys.exit(main())

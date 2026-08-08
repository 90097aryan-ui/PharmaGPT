"""
scripts/restore_from_backup.py — Disaster-recovery restore.

By default restores into a NEW, empty directory you choose — it never
touches the live database or uploads folder unless you pass --confirm-live
AND type the exact confirmation phrase when prompted. Follow
docs/DISASTER_RECOVERY_SOP.md, not just this script, for a real incident.

Usage:
    # Safe default — restore into a fresh directory for inspection:
    python scripts/restore_from_backup.py --archive path/to/run.bak.enc --target ./restore_test

    # Real DR — overwrite the live persistent-disk paths (interactive confirm required):
    python scripts/restore_from_backup.py --archive path/to/run.bak.enc --target /var/data --confirm-live
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt.logging_config import configure_logging  # noqa: E402

configure_logging()

from pharmagpt.services import backup_service  # noqa: E402

CONFIRM_PHRASE = "RESTORE OVER LIVE DATA"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="Path to the .bak.enc archive to restore.")
    parser.add_argument("--target", required=True, help="Directory to restore into.")
    parser.add_argument(
        "--confirm-live", action="store_true",
        help="Allow restoring into a non-empty directory (e.g. the live persistent disk path). "
             "Still requires typing a confirmation phrase interactively.",
    )
    args = parser.parse_args()

    if args.confirm_live:
        print(
            "\n*** You are about to restore over a non-empty directory. ***\n"
            f"Target: {args.target}\n"
            "If this is the live persistent disk, this will overwrite the running "
            "database, uploads, and generated documents with the backup's contents.\n"
            f"Type exactly: {CONFIRM_PHRASE}\n"
        )
        typed = input("> ").strip()
        if typed != CONFIRM_PHRASE:
            print("Confirmation phrase did not match. Aborting — nothing was restored.")
            return 1

    try:
        result = backup_service.restore_from_backup(args.archive, args.target, confirm_live=args.confirm_live)
    except Exception as exc:  # noqa: BLE001
        print(f"Restore failed: {exc}")
        return 1

    print(f"Restored '{result['archive']}' into '{result['restored_to']}'.")
    print(
        "Reminder: the restored SQLite file, uploads/, and generated_documents/ are "
        "now on disk at the target path, but the running application process must be "
        "pointed at them (DB_PATH / UPLOAD_FOLDER / GENERATED_DOCS_PATH) and restarted "
        "— this script does not restart or reconfigure the running service. "
        "See docs/DISASTER_RECOVERY_SOP.md step 5 onward."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
scripts/verify_backup.py — Restore-drill verification + Backup Test Report.

Decrypts and extracts a backup archive into a throwaway temp directory
(never the live DB_PATH/UPLOAD_FOLDER), checks it, and writes a filled-in
Backup Test Report (docs/BACKUP_TEST_REPORT_TEMPLATE.md) so every drill run
leaves an auditable artifact — this is what
docs/BACKUP_VALIDATION_PROTOCOL.md requires be run periodically.

Usage:
    python scripts/verify_backup.py                     # verifies the latest backup
    python scripts/verify_backup.py --archive PATH       # verifies a specific archive
    python scripts/verify_backup.py --out-dir DIR        # where to write the report (default: docs/VALIDATION_EVIDENCE/backup_test_reports/)
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pharmagpt.logging_config import configure_logging  # noqa: E402

configure_logging()

from pharmagpt.services import backup_service  # noqa: E402

REPORT_TEMPLATE = """# Backup Test Report

**Report ID:** BTR-{run_id}
**Generated:** {generated_at}
**Archive tested:** {archive}
**Drill duration:** {duration}s
**Overall result:** {overall}

## Checks

| Check | Result |
|---|---|
{checks_table}

## Notes

- This report was generated automatically by `scripts/verify_backup.py`,
  which decrypts and extracts the archive into an isolated temporary
  directory and never touches the live database, uploads folder, or
  Postgres project.
- A PASS here confirms the archive is decryptable, internally consistent
  with its own manifest, and that the SQLite copy inside it passes
  `PRAGMA integrity_check` — it does not by itself prove a full production
  cutover would succeed; see docs/BACKUP_VALIDATION_PROTOCOL.md for the
  periodic full-restore-to-staging drill this report should be paired with.

## Raw check output

```json
{raw_json}
```
"""


def render_report(report: dict) -> str:
    import json
    rows = []
    for key, value in report.get("checks", {}).items():
        rows.append(f"| {key} | {value} |")
    return REPORT_TEMPLATE.format(
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        generated_at=datetime.now(timezone.utc).isoformat(),
        archive=report.get("archive"),
        duration=report.get("duration_seconds", "n/a"),
        overall=report.get("overall", "unknown").upper(),
        checks_table="\n".join(rows) or "| (no checks recorded) | — |",
        raw_json=json.dumps(report, indent=2, default=str),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default=None, help="Path to a specific .bak.enc archive; defaults to the latest.")
    parser.add_argument(
        "--out-dir", default=None,
        help="Directory to write the Backup Test Report into (default: docs/VALIDATION_EVIDENCE/backup_test_reports/).",
    )
    args = parser.parse_args()

    report = backup_service.verify_backup(args.archive)

    out_dir = Path(args.out_dir) if args.out_dir else (
        Path(__file__).resolve().parents[1] / "docs" / "VALIDATION_EVIDENCE" / "backup_test_reports"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"BTR-{stamp}.md"
    out_path.write_text(render_report(report), encoding="utf-8")

    print(f"Backup verification: {report.get('overall', 'unknown').upper()}")
    print(f"Report written to: {out_path}")

    return 0 if report.get("overall") == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

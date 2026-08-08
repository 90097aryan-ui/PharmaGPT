# Backup Validation Protocol (BVP-001)

**Document type:** Validation Protocol
**System:** PharmaGPT Backup & Recovery Framework
**Purpose:** Define the periodic testing required to demonstrate that backups are actually restorable, not merely created — "a backup that has never been restored is not a verified backup" (the same principle already stated, for the target Postgres architecture, in `docs/PLATFORM_ARCHITECTURE.md` §29; this protocol makes it concrete and executable for the framework actually built).
**Related documents:** `docs/BACKUP_ARCHITECTURE.md`, `docs/BACKUP_SOP.md`, `docs/DISASTER_RECOVERY_SOP.md`, `docs/BACKUP_TEST_REPORT_TEMPLATE.md`

---

## 1. Scope

This protocol defines two tiers of validation:

- **Tier 1 — Automated restore-drill** (`scripts/verify_backup.py`): decrypts and extracts a backup into an isolated temp directory and checks internal consistency. Fast, safe to run frequently, does not require staging infrastructure.
- **Tier 2 — Full staging restore**: actually stands up a copy of the application against restored data in a non-production environment and exercises it. Slower, requires a staging environment, proves more.

## 2. Acceptance criteria — Tier 1 (automated)

A restore-drill (`backup_service.verify_backup()`) is a **PASS** only if all of the following hold:

| # | Check | Pass condition |
|---|---|---|
| 1 | Archive decrypts | No `BackupIntegrityError` on decrypt |
| 2 | Manifest present | `manifest.json` exists in the extracted bundle |
| 3 | SQLite integrity | `PRAGMA integrity_check` returns exactly `ok` |
| 4 | Regulated-table row counts | `qms_audit_trail` / `qms_esignatures` row counts in the restored copy match the manifest's counts captured at backup time |
| 5 | File counts | Uploaded/generated document counts match the manifest |
| 6 | Postgres export | Every `postgres/<table>.json` file (if present) parses as valid JSON |

Any single failure → **FAIL**. A FAIL must be investigated before relying on that backup; it does not necessarily mean older backups are also bad, but the most recent successful run's mechanism should be checked for a systemic cause.

## 3. Acceptance criteria — Tier 2 (full staging restore)

A Tier 2 drill is a **PASS** only if all of the following hold, in addition to Tier 1 passing on the same archive:

| # | Check | Pass condition |
|---|---|---|
| 1 | Application boots | `gunicorn pharmagpt.app:app` starts cleanly against the restored `DB_PATH`/`UPLOAD_FOLDER`/`GENERATED_DOCS_PATH` |
| 2 | Health check | `GET /health` → `200` |
| 3 | Login | A known test user can authenticate |
| 4 | Representative record read | A QMS record created before the backup (e.g. a deviation or document) is visible and its content matches expectation |
| 5 | Audit trail intact | `GET /qms/<record_type>/<id>/audit-trail` for that record returns entries, not an empty/error response |
| 6 | E-signature intact | `GET /qms/<record_type>/<id>/esignatures` for a previously-signed record returns the expected signature(s) with a valid `signature_hash` |
| 7 | No RBAC/tenant regression | A cross-tenant read attempt against restored data is still denied (re-run the relevant subset of `tests/test_security_tenant_rbac_esig.py` against the staging environment, or the equivalent manual check) |

## 4. Frequency

| Tier | Frequency | Trigger |
|---|---|---|
| Tier 1 | Every backup run's own automatic self-verification (built into `run_full_backup()`) is always-on. In addition, an **independent** Tier 1 drill against the latest archive should run at least weekly, and always after any change to `backup_service.py` or its dependencies. | Scheduled (recommended: weekly cron alongside the backup schedule) or on-demand via the `/admin/backup` dashboard. |
| Tier 2 | At least quarterly, and after any material change to the database schema, migration process, or deployment platform. | Manual, scheduled by Platform/Infrastructure Engineering with QA sign-off. |

## 5. Procedure — Tier 1

1. Run `python scripts/verify_backup.py` (defaults to the latest archive) or use the "Run Verification Drill" button on `/admin/backup`.
2. The script writes a Backup Test Report to `docs/VALIDATION_EVIDENCE/backup_test_reports/BTR-<timestamp>.md` (see `docs/BACKUP_TEST_REPORT_TEMPLATE.md` for the format it fills in).
3. Review the report's `Overall result`. If `FAIL`, escalate per `docs/BACKUP_SOP.md` §7 (alerting) even if no automated alert fired (a manual drill failure is not itself wired to the webhook — only automatic in-run failures are).
4. File the report; do not delete it (it is validation evidence).

## 6. Procedure — Tier 2

1. Provision or reuse a staging environment matching production's runtime (same `render.yaml` service definition, pointed at a staging Supabase project if the Postgres tables are in scope for this drill).
2. Select the archive to restore (typically the most recent Tier-1-passed one).
3. `python scripts/restore_from_backup.py --archive <path> --target <staging persistent-disk path> --confirm-live` (confirm-live is appropriate here because the staging environment's data is expected to be overwritten — **never point this at the production path**).
4. Point the staging service's env vars at the restored paths; restart it.
5. Execute the checks in §3 table, recording pass/fail for each.
6. Fill in a Backup Test Report (§ manual section — Tier 2 checks are not automated by `scripts/verify_backup.py`; record them by hand using the same template for a single, consistent artifact type).
7. QA reviews and signs off. A Tier 2 FAIL blocks reliance on the backup mechanism as a whole (not just one archive) until root-caused — unlike a Tier 1 FAIL, which may be archive-specific.

## 7. Records

All Backup Test Reports live under `docs/VALIDATION_EVIDENCE/backup_test_reports/` and are retained for the same period as `BACKUP_DAILY_RETENTION_DAYS` (see `docs/BACKUP_SOP.md` §8) at minimum — they are themselves audit evidence that the backup control is operating effectively, and should survive at least as long as the backups they validate.

# Backup & Recovery Architecture

**Status:** Implemented (code + tests), NOT deployed. Remediates the Compliance Matrix's Critical "Backup & Recovery" finding (`PharmaGPT_Compliance_Matrix_and_Validation_Readiness.docx`, Section 3, Backup & Recovery — "no automated backup mechanism protects the live production SQLite database"). This document describes what was built; it does not claim anything here has been run against production. See `docs/BACKUP_SOP.md` for the operating procedure and `docs/DISASTER_RECOVERY_SOP.md` for the incident procedure.

**Scope discipline:** this framework does not modify RBAC, Electronic Signatures, Audit Trail, business logic, or the application's architecture. It adds one new service module, one new admin-only route blueprint (gated by the existing `require_role` decorator, unmodified), CLI scripts, and configuration. The audit trail (`qms_audit_trail`) and electronic signatures (`qms_esignatures`) tables are protected simply by being inside the SQLite file this framework backs up — no code here reads or understands their schema.

---

## 1. What is backed up

PharmaGPT's actual deployed system of record is SQLite (`pharmagpt.db`, `DB_PATH`) — Postgres/Supabase is the target architecture for a subset of domains (identity, RBAC, break-glass) and is not yet the source of truth for QMS data (`docs/MIGRATION.md`). The backup framework reflects that reality rather than only backing up the aspirational architecture:

| # | Target | Mechanism | Why |
|---|---|---|---|
| 1 | SQLite production DB (`DB_PATH`) | `sqlite3.Connection.backup()` — SQLite's own online backup API, not a raw file copy | **Primary target.** Contains all QMS data, the audit trail (`qms_audit_trail`), and electronic signatures (`qms_esignatures`). A raw file copy risks capturing a torn write against the live WAL file; the backup API does not. |
| 2 | Uploaded documents (`UPLOAD_FOLDER`) | tar+gzip of the directory tree | Explicitly requested; irreplaceable user-uploaded files on the same persistent disk as the DB. |
| 3 | Generated documents (`GENERATED_DOCS_PATH`) | tar+gzip of the directory tree | Same risk profile as (2) — AI-generated protocols, reports, DOCX exports — included for the same reason, at zero extra design cost. |
| 4 | Configuration | Sanitized (non-secret) JSON snapshot of an explicit allowlist in `config.py` | For DR reference only. **Secrets are never written to a backup archive** — see §4. |
| 5 | PostgreSQL/Supabase | Row-level JSON export via the existing service-role Supabase client (`services/supabase_client.py`, unmodified), one file per table in `config.POSTGRES_BACKUP_TABLES` | No new infrastructure dependency (no `pg_dump`/Postgres client tools on Render's plain Python runtime — see §5). Supplementary to Supabase's own managed backup. |
| 6 | Audit trail & Electronic signatures | Implicit — inside target (1) (SQLite) and, for the Postgres-side `audit_trail` mirror table, inside target (5) | No separate mechanism; this module never touches either table's schema or logic. |

All targets from one run are bundled into a single tar.gz, then encrypted at rest (§3) as one `<run_id>.bak.enc` file.

## 2. Frequency, retention, RPO, RTO

These are **newly established policy values** (this framework did not exist before), not previously measured figures — labelled accordingly.

| Parameter | Value | Basis |
|---|---|---|
| Backup frequency | Every 6 hours (`BACKUP_FREQUENCY_HOURS`) | Assumption — a pragmatic default balancing RPO against backup-window load on a single-disk deployment. Override via env var. |
| Short-term retention | 7 days, every run (`snapshots/`) | Assumption — covers "restore to an hour before an operator mistake" scenarios. |
| Long-term retention | 365 days, first success of each day (`daily/`) | Assumption — aligned to a 1-year GMP working-retention window. **The customer's actual regulatory record-retention requirement (often much longer than 1 year) must override this** — see `docs/BACKUP_SOP.md`. |
| RPO (SQLite/files) | ≤ 6 hours | Directly derived from backup frequency — the maximum data loss window if the primary disk is lost the instant before the next scheduled backup. |
| RPO (Postgres) | Assumption, contingent — Supabase's own managed PITR, documented elsewhere (`docs/PLATFORM_ARCHITECTURE.md` §29) as <5 min, **requires confirming PITR is actually enabled on the Supabase project's billing plan** — not verifiable from this codebase. This framework's own JSON export runs on the same 6-hour cadence as a supplementary, defense-in-depth copy regardless of that setting. |
| RTO (target) | ≤ 4 hours, full platform | Consistent with the existing target-state figure in `docs/PLATFORM_ARCHITECTURE.md` rather than inventing a new number. **Measured, not just targeted** — see the Test Results section of the implementation report for this session's actual restore-drill timings. |

## 3. Encryption

Backup archives are encrypted at rest with **Fernet** (symmetric AES-128-CBC + HMAC, via the `cryptography` package — already a pinned dependency; no new requirement was added). The key (`BACKUP_ENCRYPTION_KEY`) has **no default value** — `backup_service.py` raises `BackupConfigError` immediately if it is unset, rather than silently defaulting.

This is a deliberate contrast with `FLASK_SECRET_KEY`'s dev-mode fallback (`config.py`), which the Compliance Matrix flagged as a Critical gap precisely because a security-critical secret silently defaulting is itself a vulnerability class. The backup framework does not repeat that pattern. Generate a key with `python scripts/generate_backup_key.py` and store it in a secrets vault — never in the backup directory, never committed.

## 4. Configuration snapshot — what is and isn't captured

`_config_snapshot()` uses an **allowlist** (`_SAFE_CONFIG_KEYS` in `backup_service.py`), not a denylist of secret-looking names — a future config addition is excluded by default, not leaked by default. No `*_KEY`, `*_SECRET`, `*_TOKEN`, or `*_PASSWORD`-named value is ever captured. Actual secrets (`SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `FLASK_SECRET_KEY`, `BACKUP_ENCRYPTION_KEY` itself, etc.) must be independently re-supplied from your secrets vault / Render dashboard during a restore — see `docs/DISASTER_RECOVERY_SOP.md`.

## 5. PostgreSQL/Supabase backup mechanism — why JSON export, not `pg_dump`

Render's Python runtime (`buildCommand: pip install -r requirements.txt`, no Docker/apt-get access) does not ship PostgreSQL client tools, so a `pg_dump`-based backup cannot run in production without a custom build step this repo does not have. The framework instead uses row-level JSON export via the same PostgREST service-role client the app already uses (`services/supabase_client.py::get_service_role_client`) — zero new infrastructure.

**If** `SUPABASE_DB_URL` (a direct Postgres connection string from the Supabase dashboard — not previously part of this app's configuration) is set **and** `pg_dump` happens to be on `PATH`, a supplementary logical dump is also attempted; if either condition isn't met, this is skipped with a logged reason, never a failure of the overall backup run.

**Table list (`config.POSTGRES_BACKUP_TABLES`) was verified empirically against this app's own dev Supabase project**, not just read from migration files — see the comment in `config.py`. Running a real backup against that project during implementation showed the `migrations/0015_rbac_org_framework_up.sql` tables (`rbac_roles`, `rbac_permissions`, `designations`, etc.) do not yet exist there (`PGRST205` errors), confirming empirically what the Compliance Matrix could only describe as "unverifiable from code alone" — migration 0015 has not been applied to that project. The default table list excludes those 7 tables until that migration is applied; per-table failures are caught and logged rather than aborting the run either way, so this is a completeness setting, not a safety one.

## 6. Verification (built-in, automatic)

Every backup run verifies itself before being considered successful:
1. `PRAGMA integrity_check` on the SQLite **copy** (never the live file) — must return `ok`.
2. Post-encryption decrypt round-trip — the archive is decrypted immediately after writing and its checksum compared against the pre-encryption bundle, catching any encryption-layer corruption before the run is marked successful.

A separate, on-demand **restore-drill** (`scripts/verify_backup.py`, or the dashboard's "Run Verification Drill" button) decrypts and extracts a backup into an isolated temp directory — never the live paths — and checks: manifest present, SQLite integrity check, `qms_audit_trail`/`qms_esignatures` row counts match what the manifest recorded at backup time, uploaded/generated file counts match, Postgres JSON files all parse. See `docs/BACKUP_VALIDATION_PROTOCOL.md` for how often this should run and `docs/BACKUP_TEST_REPORT_TEMPLATE.md` for the artifact it produces.

## 7. Monitoring & alerting

Every run (success or failure) is recorded in `BACKUP_DIR/backup_state.json` (a dedicated file — **not** a new table in `pharmagpt.db**, so this module never touches the schema of the database it protects). On failure:
- Always logged at `CRITICAL` (visible in Render's log aggregation regardless of any other configuration).
- Optionally POSTed to `BACKUP_ALERT_WEBHOOK_URL` (generic JSON webhook — compatible with Slack/Teams/PagerDuty/Opsgenie incoming webhooks, or a custom endpoint) if configured.
- Surfaced on the `/admin/backup` dashboard (super_admin only).

`check_freshness()` independently flags a **stale** backup (no success within 2x the configured frequency) even if the scheduler silently stopped firing — not only an explicit failure.

## 8. Dashboard

`GET /admin/backup` — server-rendered status page, gated by the existing `@require_role("super_admin")` decorator (platform-wide concern, not tenant-scoped, consistent with how break-glass/RBAC admin surfaces are already gated). Backed by `/api/status` (dashboard summary + health), `/api/config` (the six-component configuration-detection panel), `/api/history` and `/api/verification-history`, and three action endpoints — `/api/run`, `/api/verify`, `/api/restore` (a safe, staging-only restore drill; see §6). Every action endpoint re-checks its own prerequisites server-side before doing any work (`is_backup_runnable()` / `is_archive_available_for_verification_or_restore()`) so a request that is guaranteed to fail is rejected immediately with a plain-English reason instead of being attempted — the UI disables the corresponding button for the same reason, but the API never relies on the UI alone to enforce it. See `pharmagpt/routes/backup_admin.py`.

Every route response is JSON with a `user_message` field safe to render as-is; no route ever lets a raw exception, stack trace, or generic "Internal Server Error" reach the browser (`verify_backup()` and `run_restore_drill()` are themselves hardened to never raise — see their docstrings — and every route additionally wraps its body in a last-resort try/except).

## 9. Files added / modified

**Added:**
- `pharmagpt/services/backup_service.py` — core logic
- `pharmagpt/routes/backup_admin.py` — dashboard + API routes
- `pharmagpt/templates/backup_dashboard.html` — dashboard page
- `scripts/run_backup.py`, `scripts/verify_backup.py`, `scripts/restore_from_backup.py`, `scripts/generate_backup_key.py`
- `tests/test_backup_service.py`, `tests/test_backup_admin_routes.py`, `tests/test_backup_production_readiness.py`
- `docs/BACKUP_ARCHITECTURE.md` (this file), `docs/BACKUP_SOP.md`, `docs/DISASTER_RECOVERY_SOP.md`, `docs/BACKUP_VALIDATION_PROTOCOL.md`, `docs/BACKUP_TEST_REPORT_TEMPLATE.md`

**Modified (minimal, additive only):**
- `pharmagpt/config.py` — new `BACKUP_*`/`SUPABASE_DB_URL`/`POSTGRES_BACKUP_TABLES` settings appended at end of file
- `pharmagpt/app.py` — two lines: import + `register_blueprint` for the new admin blueprint, in the same style as every other blueprint
- `render.yaml` — documented (not deployed) Cron Job service definition + new env var entries
- `.env.example` — new env var documentation

**Not modified:** `pharmagpt/auth/`, `pharmagpt/services/esignature_service.py`, `pharmagpt/audit.py`, any `qms_*` module, any existing route file, any migration.

### Production-readiness pass (this revision)

A follow-up pass hardened the module for real-world operation without changing its architecture:
- **Configuration detection** — `get_configuration_status()` checks Backup Service, Scheduler, Encryption Key, Offsite Storage, Database Backup, and Document Backup, each reporting `configured` / `missing` / `failed` with a plain-English message.
- **Health rollup** — `compute_health()` — 🟢/🟡/🔴 with stated reasons, combining configuration, last-run outcome, freshness, and last-verification result.
- **Verification persistence** — `verify_backup()` now records every drill (`verification_state.json`) so "Last Verification" survives a page reload, and is hardened to never raise (a missing/invalid encryption key previously escaped uncaught as `BackupConfigError` and would have surfaced as a raw 500).
- **Restore drill** — `run_restore_drill()` / `POST /api/restore` — restores the latest archive into `BACKUP_DIR/restore_staging/` (cleared before each run) so an operator can prove restorability from the dashboard without any web-exposed path to a live-data overwrite; a true live restore remains CLI-only (`scripts/restore_from_backup.py`, interactive confirmation required).
- **Concurrency guard** — an atomic, cross-process lock (`_acquire_lock()`/`_release_lock()`, stale-lock reclaim after 2h) now lives in `run_full_backup()` itself, covering both the CLI/cron path and the dashboard's "Run Backup Now" button. It replaces `scripts/run_backup.py`'s original lock-file check, which was non-atomic (a check-then-write race) and only protected the CLI path — the web dashboard's `POST /api/run` had no protection against a concurrent run at all before this pass.
- **Read-path resilience** — `_backup_dir()` no longer raises if `BACKUP_DIR` can't be created (e.g. a permissions problem); status reads degrade to "no backups on record" instead of 500ing the whole dashboard.
- **UI error handling** — the dashboard's `fetch` wrapper never surfaces a raw network-error message or an un-parsed response body; every failure path resolves to a curated, friendly string.

## 10. Remaining risks (not closed by this implementation)

1. **Same-disk backup by default.** `BACKUP_DIR` defaults to the same persistent disk as the live database. A disk-level failure (not a software bug — the actual failure mode this framework exists to protect against) would take out both the primary data and the on-disk backup together. `BACKUP_OFFSITE_DIR` (a second mounted disk/network share) or an external object-storage sync (documented in `docs/BACKUP_SOP.md`, not built as in-app code to avoid an unjustified new SDK dependency — see that SOP for why) closes this gap but requires operator setup; it is not configured by default.
2. **Nothing is scheduled yet.** `render.yaml` now documents a Cron Job service, but per this task's explicit "do not deploy" instruction, it has not been pushed or activated. Until it is, `scripts/run_backup.py` must be run manually or via some other scheduler.
3. **`BACKUP_ENCRYPTION_KEY` is not yet set anywhere.** No backup can run until an operator generates one and configures it — by design (see §3), but it means this framework is inert in its current, undeployed state.
4. **Supabase's own managed PITR status is unconfirmed.** Whether Point-in-Time-Recovery is actually enabled on the production Supabase project's plan is a dashboard/billing setting outside this codebase's visibility.
5. **Restore-to-a-genuinely-separate-environment has not been drilled.** The verification drill (§6) proves the archive is internally consistent and decryptable; it does not prove a full cutover of a live gunicorn process to restored data would succeed without incident. See `docs/BACKUP_VALIDATION_PROTOCOL.md` for the periodic full-drill this should be paired with.

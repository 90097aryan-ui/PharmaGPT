# SOP — Backup Operations (PharmaGPT)

**Document type:** Standard Operating Procedure
**System:** PharmaGPT Backup & Recovery Framework (`pharmagpt/services/backup_service.py`)
**Related documents:** `docs/BACKUP_ARCHITECTURE.md` (design), `docs/DISASTER_RECOVERY_SOP.md` (incident procedure), `docs/BACKUP_VALIDATION_PROTOCOL.md` (periodic verification), `docs/BACKUP_TEST_REPORT_TEMPLATE.md`
**Status:** Procedure describes how to operate the framework once deployed. As of this document's authorship, the framework is implemented and tested but **not deployed** — no step below has been executed against production. Do not check off any box below until it has actually been done.

---

## 1. Purpose

Define the procedure for automated, verified, encrypted backup of PharmaGPT's production database, uploaded/generated documents, configuration, and the tables currently live in the Supabase project, and for monitoring backup health.

## 2. Scope

Applies to the production Render deployment of PharmaGPT. Covers backup creation, encryption, retention, offsite copy, and failure alerting. Restore is covered by `docs/DISASTER_RECOVERY_SOP.md`.

## 3. Responsibilities

| Role | Responsibility |
|---|---|
| Platform/Infrastructure Engineer | Owns scheduling (cron/Render Cron Job), key management, offsite storage, alert routing. |
| Super Admin (application role) | Monitors `/admin/backup` dashboard; triggers on-demand backups/drills when needed. |
| QA | Owns `docs/BACKUP_VALIDATION_PROTOCOL.md` execution cadence and sign-off on Backup Test Reports. |

## 4. One-time setup (must be completed before the first scheduled run)

- [ ] **Generate the encryption key:** `python scripts/generate_backup_key.py`. Store the output in your secrets vault. Set it as `BACKUP_ENCRYPTION_KEY` in Render (Environment tab, `sync: false` — see `render.yaml`). Never commit it, never store it inside `BACKUP_DIR`.
- [ ] **Decide on an offsite location.** Options, in order of preference:
  - A second Render persistent disk (or any mounted network path) — set `BACKUP_OFFSITE_DIR` to its mount path. Zero new dependencies; `backup_service.py` copies the encrypted archive there automatically after every successful run.
  - A cloud object store (S3-compatible, Backblaze B2, etc.) — **not built into the application** (would require adding a cloud SDK dependency, which this task's scope explicitly avoided as an unjustified redesign for a first cut). Instead, wire an `rclone`/`aws s3 sync` command as a post-step in your cron/CI after `scripts/run_backup.py` exits 0, pointed at `BACKUP_DIR/snapshots/` and `BACKUP_DIR/daily/`.
  - **Until one of the above is configured, backups exist only on the primary disk** — `run_full_backup()` logs a `CRITICAL` warning on every single run to keep this visible, not just documented here.
- [ ] **Decide on an alert destination.** Set `BACKUP_ALERT_WEBHOOK_URL` to a Slack/Teams/PagerDuty/Opsgenie incoming-webhook URL (or any endpoint that accepts a JSON POST with a `text` field). Without this, failures still log at `CRITICAL` and appear on the dashboard, but no one is proactively paged.
- [ ] **Confirm Supabase managed backups.** Log into the Supabase dashboard → Settings → Database → Backups. Confirm Point-in-Time-Recovery is enabled if your plan supports it. This framework's Postgres export (§6 below) is a supplementary safeguard, not a replacement for Supabase's own backup.
- [ ] **Schedule `scripts/run_backup.py`.** See §5.

## 5. Scheduling

`render.yaml` documents (but, per this implementation's explicit scope, does not activate) a Render Cron Job service running `python scripts/run_backup.py` on the schedule matching `BACKUP_FREQUENCY_HOURS` (default: every 6 hours). To activate:
- [ ] Review the commented Cron Job block in `render.yaml`.
- [ ] Uncomment it (or create the equivalent service directly in the Render dashboard).
- [ ] Push/deploy — **outside the scope of this implementation task; a human operator with deploy authority must do this.**
- [ ] Set `BACKUP_SCHEDULER_ENABLED=true` on the web service once the scheduler is confirmed actually running — this is what flips the dashboard's Scheduler check from ⚠ to ✅ and enables the "Next Scheduled Backup" estimate. Do not set it before the scheduler is real; PharmaGPT cannot independently verify an external cron process is calling in, so this flag is only as honest as the operator setting it.

If not using Render's Cron Jobs, any scheduler capable of running a shell command on an interval (OS cron, a separate always-on worker, etc.) works — the script is a plain CLI entrypoint with no Render-specific dependency.

## 6. What each run does (reference — see `docs/BACKUP_ARCHITECTURE.md` for full design)

1. Acquires a lock file (prevents overlapping runs).
2. Online-copies the SQLite database via `sqlite3.Connection.backup()`.
3. Runs `PRAGMA integrity_check` on the copy.
4. Archives `UPLOAD_FOLDER` and `GENERATED_DOCS_PATH`.
5. Snapshots a non-secret configuration allowlist.
6. Exports the live Postgres tables (`config.POSTGRES_BACKUP_TABLES`) as JSON via the existing service-role Supabase client.
7. Bundles everything, encrypts with Fernet, computes a SHA-256 checksum.
8. Self-verifies via a decrypt round-trip.
9. Copies to `BACKUP_OFFSITE_DIR` if configured.
10. Prunes backups older than `BACKUP_SNAPSHOT_RETENTION_DAYS` (7 days default) from `snapshots/`, and older than `BACKUP_DAILY_RETENTION_DAYS` (365 days default) from `daily/`.
11. Records the run (success or failure) to `BACKUP_DIR/backup_state.json`.
12. Alerts (log + optional webhook) on failure.

## 7. Monitoring

- **Dashboard:** `/admin/backup` (Super Admin only). Shows:
  - **Backup Health** — one traffic-light rollup (🟢 Healthy / 🟡 Warning / 🔴 Critical) with the specific reasons behind it, computed from configuration status, the last run's outcome, freshness, and the last verification result (`backup_service.compute_health()`).
  - **Overview** — Last Successful Backup, Last Failed Backup, Last Verification, Backup Freshness, Next Scheduled Backup, and the most recent run's size/duration.
  - **Configuration** — a live ✅/⚠️/❌ check of all six components this SOP covers (Backup Service, Scheduler, Encryption Key, Offsite Storage, Database Backup, Document Backup) — see `backup_service.get_configuration_status()`.
  - **Actions** — "Run Backup Now", "Run Verification Drill", and "Restore (Test Location Only)" — the Restore button runs a real restore into an isolated `BACKUP_DIR/restore_staging/` directory to prove an archive is actually restorable; it never touches live paths. Every action button is disabled with a stated reason whenever its prerequisite configuration is missing, and the same check runs server-side (not just in the UI) so no request can be made that is guaranteed to fail.
  - **Run History** and **Last Verification Result** — every run and every verification drill is persisted (`backup_state.json` / `verification_state.json`) and survives a page reload.
- **Freshness check:** a backup older than 2x `BACKUP_FREQUENCY_HOURS` is flagged stale on the dashboard even if no explicit failure occurred (e.g. the scheduler itself stopped firing).
- **Failure alert:** `CRITICAL` log line always; webhook POST if `BACKUP_ALERT_WEBHOOK_URL` is set.
- **Error handling:** every dashboard state — including "nothing configured yet," "no backups exist," a failed backup, or an unreachable backend — renders a plain-English message. No route ever returns a raw exception message, stack trace, or a generic "Internal Server Error" to the browser.

## 8. Retention & disposal

| Class | Location | Retention | Disposal |
|---|---|---|---|
| Short-term (every run) | `BACKUP_DIR/snapshots/` | 7 days (default) | Auto-pruned by the backup service on each run. |
| Long-term (first success/day) | `BACKUP_DIR/daily/` | 365 days (default) | Auto-pruned by the backup service on each run. |

**Override `BACKUP_DAILY_RETENTION_DAYS` to match your customer's actual regulatory record-retention requirement** — the 365-day default is a working-retention assumption, not a validated regulatory figure, and is very likely shorter than what many GMP customers require. Confirm before relying on it.

## 9. Key management

- `BACKUP_ENCRYPTION_KEY` lives only in the secrets vault / Render environment (`sync: false`) — never in `BACKUP_DIR`, never committed, never logged.
- If the key is lost, **all existing encrypted backups become permanently unreadable.** Store it with the same rigor as `SUPABASE_SERVICE_ROLE_KEY`.
- Rotating the key: generate a new one, but decrypt-and-re-encrypt any backups you want to keep readable under the new key **before** discarding the old one (no automated rotation tool is provided in this implementation — a manual, infrequent operation).

## 10. Remaining risk this SOP does not close

Same-disk-only backup until `BACKUP_OFFSITE_DIR` (or an external sync step) is actually configured — see step 2 of §4. This is called out here, in `docs/BACKUP_ARCHITECTURE.md` §10, and in the implementation's final report; it is the one open item that most directly limits how much this framework currently reduces the original Critical finding's risk.

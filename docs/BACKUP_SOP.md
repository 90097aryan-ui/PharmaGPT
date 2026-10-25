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

## 4. One-time setup (must be completed before enabling scheduled backups)

**Why the scheduler runs inside the web service:** only the web service can read the persistent disk holding the SQLite database and uploads. A Render cron job cannot mount another service's disk, so the former cron job was removed. Do not re-add one.

- [ ] **Generate the encryption key** locally: `python scripts/generate_backup_key.py`. Store it in your secrets vault and set it as `BACKUP_ENCRYPTION_KEY` in the Render **web service** environment (`sync: false`). Never commit it or store it inside `BACKUP_DIR`.
- [ ] **Create the independent off-site bucket.** Use a *separate* Supabase project from production (so losing production does not lose the backups). Create a **private** bucket (e.g. `yuktav-backups`) and a key limited to it. Check the plan's maximum object size against your archive size (Supabase Storage enforces a per-file limit; raise it or choose a plan that fits).
- [ ] **Set on the Render web service** (all three together; a partial set makes every run fail):
  - `BACKUP_OFFSITE_STORAGE_URL` — project URL
  - `BACKUP_OFFSITE_STORAGE_KEY` — the bucket-scoped key (not the production service-role key)
  - `BACKUP_OFFSITE_STORAGE_BUCKET` — bucket name
  - optional `BACKUP_OFFSITE_STORAGE_PREFIX` (default `pharmagpt/`)
  `BACKUP_OFFSITE_DIR` is only an extra *local* directory and is not independent storage.
- [ ] **Set an alert destination:** `BACKUP_ALERT_WEBHOOK_URL`. Without it, failures only log and show on the dashboard.
- [ ] **Confirm Supabase managed backups** for the production identity database (Settings -> Database -> Backups; PITR if available). This framework's Postgres JSON export is supplementary.
- [ ] **Run one manual backup** from `/admin/backup` ("Run Backup Now"). Pass criteria: run status `success` and `object_storage.status` = `ok` in the run details.
- [ ] **Run a verification drill and the restore test** from the same page, and keep the report off the web disk (see section 11).
- [ ] **Only then** set `BACKUP_SCHEDULER_ENABLED=true` and redeploy (section 5).

## 5. Scheduling

`pharmagpt/services/backup_scheduler.py` starts a daemon thread in each web worker when `BACKUP_SCHEDULER_ENABLED=true` **and** a valid `BACKUP_ENCRYPTION_KEY` and complete (or no) off-site storage configuration exist. Every minute it writes a heartbeat file (`BACKUP_DIR/scheduler_heartbeat.json`) and starts a backup when no successful backup is newer than `BACKUP_FREQUENCY_HOURS` (default 6). After a failed run it waits 30 minutes before retrying. The shared lock prevents two workers from running at once.

- The dashboard reports the scheduler healthy **only while the heartbeat is fresh** (written within the last 5 minutes). Setting the flag without a running scheduler shows as failed/critical, never healthy.
- A run whose off-site upload fails is recorded as **failed** (the local archive is kept and verified, but the run never counts as a successful off-site backup, and failure alerts fire).
- `scripts/run_backup.py` remains for manual use from a shell *inside the web service* (it needs the same disk); it cannot be run from a Render cron job or one-off job.
- A backup runs inside the web process: watch memory and CPU on the first runs, particularly with large `uploads/`.

## 6. What each run does (reference — see `docs/BACKUP_ARCHITECTURE.md` for full design)

1. Acquires a lock file (prevents overlapping runs).
2. Online-copies the SQLite database via `sqlite3.Connection.backup()`.
3. Runs `PRAGMA integrity_check` on the copy.
4. Archives `UPLOAD_FOLDER` and `GENERATED_DOCS_PATH`.
5. Snapshots a non-secret configuration allowlist.
6. Exports the live Postgres tables (`config.POSTGRES_BACKUP_TABLES`) as JSON via the existing service-role Supabase client.
7. Bundles everything, encrypts with Fernet, computes a SHA-256 checksum.
8. Self-verifies via a decrypt round-trip.
9. Copies to `BACKUP_OFFSITE_DIR` if configured, then uploads the encrypted archive to the independent object store (if configured) and confirms it by listing the object and comparing its size. A failed or unconfirmed upload fails the run.
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
| Off-site object store | Bucket `BACKUP_OFFSITE_STORAGE_BUCKET`, prefix `BACKUP_OFFSITE_STORAGE_PREFIX` | **Never deleted by the application** | Set a lifecycle/retention rule or delete manually in the storage provider, matching your retention policy. |

**Override `BACKUP_DAILY_RETENTION_DAYS` to match your customer's actual regulatory record-retention requirement** — the 365-day default is a working-retention assumption, not a validated regulatory figure, and is very likely shorter than what many GMP customers require. Confirm before relying on it.

## 9. Key management

- `BACKUP_ENCRYPTION_KEY` lives only in the secrets vault / Render environment (`sync: false`) — never in `BACKUP_DIR`, never committed, never logged.
- If the key is lost, **all existing encrypted backups become permanently unreadable.** Store it with the same rigor as `SUPABASE_SERVICE_ROLE_KEY`.
- Rotating the key: generate a new one, but decrypt-and-re-encrypt any backups you want to keep readable under the new key **before** discarding the old one (no automated rotation tool is provided in this implementation — a manual, infrequent operation).

## 10. Remaining risk this SOP does not close

- Until the off-site object store is configured, backups exist only on the primary disk (the dashboard shows Offsite as missing, and every run logs a warning).
- The object store holds encrypted archives; losing `BACKUP_ENCRYPTION_KEY` makes all of them unreadable (section 9).
- The upload path has been tested with a fake bucket, not against a live Supabase Storage project: the first real run (section 4) is the acceptance test.
- The scheduler lives in the web process. If the service is down, no backup runs; the staleness alert (2x `BACKUP_FREQUENCY_HOURS`) is the signal.

## 11. Recovery steps and safe verification

Follow `docs/DISASTER_RECOVERY_SOP.md` for a real incident. For a safe drill that cannot overwrite live data:

1. **Dashboard:** "Run Verification Drill" and "Restore (Test Location Only)" decrypt/extract into temp or `BACKUP_DIR/restore_staging/` only.
2. **Off-site retrieval:** download an archive from the bucket (private, with your storage credentials), then restore it **into a new empty directory**:
   `python scripts/restore_from_backup.py --archive <file>.bak.enc --target ./restore_test`
   The key must be in `BACKUP_ENCRYPTION_KEY` in the shell used. Never pass `--confirm-live` for a drill.
3. **Check the result:** open `restore_test/db/pharmagpt.db` and run `PRAGMA integrity_check` (expect `ok`); confirm `manifest.json` row counts.
4. **Verification reports:** `python scripts/verify_backup.py --out-dir <durable-path>`. Its default output folder is inside the repo checkout, which is not durable on Render.
5. **Real recovery** (service stopped, after a fresh backup of the damaged state if possible): `restore_from_backup.py --target /var/data --confirm-live`, then type the confirmation phrase.

## 12. Required Render configuration (web service)

| Variable | Required | Notes |
|---|---|---|
| `BACKUP_ENCRYPTION_KEY` | Yes | Fernet key; `sync: false`. |
| `BACKUP_DIR` | Yes | `/var/data/backups` (on the persistent disk). |
| `BACKUP_OFFSITE_STORAGE_URL` / `_KEY` / `_BUCKET` | Yes for off-site | All three or none. Separate Supabase project recommended. |
| `BACKUP_OFFSITE_STORAGE_PREFIX` | No | Default `pharmagpt/`. |
| `BACKUP_SCHEDULER_ENABLED` | After section 4 | `true` starts the in-process scheduler. |
| `BACKUP_FREQUENCY_HOURS` | No | Default 6. |
| `BACKUP_ALERT_WEBHOOK_URL` | Recommended | Failure/staleness alerts. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Already required | Used for the Postgres table export. |

No separate Render service is required. `main` at `367d20f` already has the backup framework and the same web-service variables except the three `BACKUP_OFFSITE_STORAGE_*` ones; it never set `BACKUP_SCHEDULER_ENABLED`, so deploying this change is backward compatible.

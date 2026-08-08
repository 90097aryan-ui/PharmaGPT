# SOP — Disaster Recovery (PharmaGPT)

**Document type:** Standard Operating Procedure
**System:** PharmaGPT
**Related documents:** `docs/BACKUP_SOP.md`, `docs/BACKUP_ARCHITECTURE.md`, `docs/BACKUP_VALIDATION_PROTOCOL.md`
**Trigger conditions:** production data loss or corruption (disk failure, accidental destructive operation, ransomware, failed migration, etc.) requiring restoration from backup.
**Status:** Procedure only. No step below has been executed against production as part of this implementation — this describes what to do in a real incident, once the framework in `docs/BACKUP_ARCHITECTURE.md` is actually deployed and has at least one verified backup available.

---

## 1. Roles during an incident

| Role | Responsibility |
|---|---|
| Incident Commander | Declares the incident, owns the go/no-go decision to restore, communicates status. |
| Platform/Infrastructure Engineer | Executes the technical restore steps below. |
| QA / Compliance | Confirms post-restore data integrity before declaring the incident closed; owns the incident record. |

## 2. Declare the incident

- [ ] Confirm the failure mode (disk failure, accidental deletion, corruption, failed deploy, etc.) — do not restore reflexively; some incidents (e.g. a bad code deploy with intact data) do not need a data restore, only a code rollback (see `docs/DEPLOYMENT_RUNBOOK.md`).
- [ ] Check `/admin/backup` (if reachable) or `BACKUP_DIR/backup_state.json` directly on the disk for the most recent successful run and its checksum.
- [ ] If the primary disk itself is lost/unreachable, retrieve the archive from `BACKUP_OFFSITE_DIR` (or your external sync destination — see `docs/BACKUP_SOP.md` §4) instead.
- [ ] Notify stakeholders that a restore is starting, with the target RPO (≤6h for SQLite/files, see `docs/BACKUP_ARCHITECTURE.md` §2) so they know the expected data-loss window.

## 3. Choose the archive to restore

- [ ] Identify the archive filename (`<run_id>.bak.enc`) — prefer the most recent **verified** backup (one that has a matching `docs/VALIDATION_EVIDENCE/backup_test_reports/BTR-*.md` with `overall: PASS`, if a recent drill exists) over the most recent unverified one, unless the recency is more time-critical than the extra confidence.
- [ ] Note its SHA-256 (`backup_state.json` or the dashboard) for later verification.

## 4. Restore into a staging location first (always, even under time pressure)

```bash
python scripts/restore_from_backup.py --archive /var/data/backups/snapshots/<run_id>.bak.enc --target ./restore_staging
```

This decrypts and extracts into a **fresh** directory — it never touches the live paths. Confirm:
- [ ] `restore_staging/db/pharmagpt.db` exists.
- [ ] Run a manual sanity check: `sqlite3 restore_staging/db/pharmagpt.db "PRAGMA integrity_check;"` → expect `ok`.
- [ ] Spot-check `restore_staging/postgres/*.json` for the tables you expect (companies, users, break_glass_access, audit_trail, etc.).
- [ ] Confirm `restore_staging/uploads.tar.gz` and `restore_staging/generated_documents.tar.gz` extract cleanly.

If any of the above fails, **stop** — try the next-most-recent archive rather than proceeding with a bad restore.

## 5. Cut over (the actual outage-ending step)

This step depends on the nature of the incident:

### 5a. Disk lost / corrupted — restore onto a fresh disk
- [ ] Provision a new persistent disk (Render dashboard, or infra-as-code equivalent).
- [ ] Run the restore directly onto it, confirming live overwrite explicitly:
  ```bash
  python scripts/restore_from_backup.py --archive <path> --target /var/data --confirm-live
  ```
  You will be prompted to type an exact confirmation phrase — this is intentional friction for a live-data-overwrite operation.
- [ ] Point `DB_PATH`, `UPLOAD_FOLDER`, `GENERATED_DOCS_PATH` at the restored paths (they already match the standard production values if you restored directly to `/var/data` — confirm against `render.yaml`).
- [ ] Restart the application (Render redeploy, or a manual process restart) so it picks up the restored files.

### 5b. Postgres/Supabase data lost or corrupted
- [ ] First check whether Supabase's own managed PITR (§ "Confirm Supabase managed backups" in `docs/BACKUP_SOP.md`) can restore directly via the Supabase dashboard — that is the primary, more capable recovery path (point-in-time, not just the last 6-hour snapshot).
- [ ] If not available or insufficient, the JSON files under `restore_staging/postgres/<table>.json` contain the row-level data from this framework's own export. Re-inserting these requires a one-off script (not provided — write one using `get_service_role_client()` for the specific tables affected, since a generic "replay any table's JSON back into Postgres" tool was judged out of scope for this task's "do not overthink" instruction). Coordinate with whoever is running the incident before writing any data back — a partial/incorrect replay against RLS-protected tables can itself cause damage.

### 5c. Accidental destructive operation on live SQLite (no disk failure)
- [ ] Stop the application (or put it in maintenance mode) before restoring — restoring `pharmagpt.db` under a live gunicorn process risks a torn read.
- [ ] Restore per 5a, but you likely only need `restore_staging/db/pharmagpt.db` — copy just that file to `DB_PATH`, not the whole persistent disk.
- [ ] Restart the application.

## 6. Post-restore verification

- [ ] Health check: `curl https://<host>/health` → `200`.
- [ ] Log in as a test user; confirm the dashboard loads and shows data consistent with the restored backup's timestamp.
- [ ] Spot-check the audit trail and e-signature record counts against the manifest inside the restored archive (`restore_staging/manifest.json` → `targets.sqlite.row_counts`) — this is the same check `scripts/verify_backup.py` runs automatically; re-running it against the now-live DB is a good final confirmation:
  ```bash
  python scripts/verify_backup.py --archive <the archive you restored>
  ```
- [ ] QA/Compliance signs off that restored data integrity is acceptable before the incident is declared closed.

## 7. Post-incident

- [ ] Record the incident: cause, RPO actually experienced (time between the restored backup's timestamp and the incident), RTO actually experienced (time from declaration to health check passing), and file it alongside `docs/VALIDATION_EVIDENCE/`.
- [ ] If the incident revealed a gap in this procedure or the framework itself, update this document and `docs/BACKUP_ARCHITECTURE.md` — do not let the next incident rediscover the same gap.
- [ ] Confirm the next scheduled backup (§5, `docs/BACKUP_SOP.md`) still runs cleanly against the restored/new environment.

## 8. What this SOP does not cover

- A full DR rehearsal / game-day exercise (recommended periodically — see `docs/BACKUP_VALIDATION_PROTOCOL.md` for the closest built-in equivalent, the restore-drill verification, which is necessary but not sufficient for a full rehearsal).
- Cross-region failover — this framework backs up to a second disk/location you configure, not a hot-standby second environment.

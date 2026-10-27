# Release runbook — PharmaGPT 691affa -> candidate (Nutra signer provisioning release)

Status: **PREPARED, NOT EXECUTED.** Do not run any step until every gate in section 1 is satisfied and a
separate deployment authorization is recorded. Facts below were verified read-only on 2026-10-27.

## 0. Verified facts
- Production: `pharmagpt.service` -> `/home/ubuntu/PharmaGPT-release-691affa` (gunicorn 127.0.0.1:5000, 2 workers x 4 threads),
  nginx -> :5000, `https://yuktav.com/health` = `{"status":"ok"}`. Deployed source == commit `691affa` (283/283 files
  hash-identical after CR normalisation).
- Persistent data lives OUTSIDE the release dirs: DB `/home/ubuntu/PharmaGPT/pharmagpt/pharmagpt.db`, uploads
  `/home/ubuntu/PharmaGPT/pharmagpt/uploads` (via `.env` `DB_PATH` / `UPLOAD_FOLDER`). A release switch does not move data.
- Host: 2 cores, ~954 MB RAM (~380 MB free), 30 GB disk free. **Do not run test suites or pip installs on this host.**
- Startup migration (verified by running `init_db()` twice on a throwaway copy of the verified backup): additive only —
  new table `validation_signoffs`; new columns `created_by_user_id/created_by_display_name` on `urs_projects`,
  `qual_qualifications`, `qual_protocols`, `qms_documents`; `qual_protocols.approval_status` (+ one-time back-fill);
  indexes `idx_validation_signoffs_record`, `uq_validation_signoffs_signatory`, `uq_validation_signoffs_signer`;
  (added after that check, re-verify on the final candidate) tables `validation_transition_claims` and
  `qms_esignature_attempts` (+ index). `/health` now returns `{"status":"degraded","degraded":[...]}` (HTTP 200) if the
  sign-off unique indexes are missing; post-deploy check must expect exactly `{"status":"ok"}`.
  Integrity ok before/after; no row-count change in any existing table; second run is a no-op.
- Supabase migration `0017_company_branding`: **not required** for this release (only the company-branding PUT API
  uses the new `company_settings` columns; DOCX branding reads `companies.legal_name`). It is NOT applied in production
  (5 columns absent; `company_settings` has 0 rows so its CHECKs cannot fail). Apply only under separate authorization.

## 1. Gates (all must be true)
1. Written approvals recorded (Nutra administrator + QA head; extra approvals for the new Plant Head membership; QA's
   Engineering-vs-Production Reviewer choice). See `docs/NUTRA_SIGNER_PROVISIONING_PLAN.md`.
2. Provisioning executed with `scripts/provision_validation_signers.py` and verified; live preflight (repaired) = **GO**
   (every designation has a distinct authorized signer). Department enforcement stays ON.
3. Candidate commit pushed (separate instruction) and **CI green on that exact SHA** (real PyMuPDF, Linux).
4. Candidate release directory re-staged from that exact SHA (the currently staged `PharmaGPT-release-de2f9dc` predates
   `533dde5` and every later commit, and must NOT be switched to).
5. Separate written deployment authorization.

## 2. Pre-deployment (on the Oracle host, ubuntu@92.4.64.238)
```bash
SHA7=<candidate 7-char sha>; N=/home/ubuntu/PharmaGPT-release-$SHA7; TS=$(date -u +%Y%m%dT%H%M%SZ)
B=/home/ubuntu/db_backups/pre_${SHA7}_$TS; mkdir -p $B
# consistent DB backup + integrity check
python3 - <<EOF
import sqlite3
s=sqlite3.connect("file:/home/ubuntu/PharmaGPT/pharmagpt/pharmagpt.db?mode=ro",uri=True); d=sqlite3.connect("$B/pharmagpt.db"); s.backup(d); d.close()
print(sqlite3.connect("file:$B/pharmagpt.db?mode=ro",uri=True).execute("pragma integrity_check").fetchone())
EOF
sudo -n cp -p /etc/systemd/system/pharmagpt.service $B/pharmagpt.service.pre-$SHA7
tar -czf $B/uploads.tar.gz -C /home/ubuntu/PharmaGPT/pharmagpt uploads && tar -tzf $B/uploads.tar.gz >/dev/null
(cd $B && sha256sum * > SHA256SUMS)
df -h / | tail -1; curl -s localhost:5000/health
```
Stage (from the workstation): `git archive <SHA> | ssh ... 'cat > release.tar.gz'`, verify sha256, extract to `$N`,
`cp -p` the live `.env`, `ln -s /home/ubuntu/PharmaGPT-release-691affa/venv $N/venv` (requirements.txt unchanged since
691affa: verify with `git diff 691affa <SHA> -- requirements.txt` = empty), `python -m compileall -q pharmagpt`.
Re-run the read-only preflight from `$N` (`scripts/validation_approval_preflight.py --sqlite <DB> --supabase`) — must be GO.

## 3. Switch (only after sections 1-2)
```bash
sudo -n sed -i "s#PharmaGPT-release-691affa#PharmaGPT-release-$SHA7#g" /etc/systemd/system/pharmagpt.service
sudo -n systemctl daemon-reload && sudo -n systemctl restart pharmagpt
sleep 5; systemctl is-active pharmagpt nginx; curl -s localhost:5000/health
```

## 4. Post-deployment verification
- `curl -s https://yuktav.com/health` -> `{"status":"ok"}`; `curl -sI https://yuktav.com/` -> 200.
- `systemctl show pharmagpt -p WorkingDirectory -p MainPID`; `journalctl -u pharmagpt --since "-10 min" -p err` empty.
- Static assets 200: `/static/css/neumorphic.css`, `/static/img/yuktav-logo.png`, `/static/js/validation_approval_ui.js`.
- DB: `pragma integrity_check` ok; `validation_signoffs` + both `uq_validation_signoffs_*` indexes exist; no log line
  "duplicate completed sign-off group(s)" (would mean the unique indexes were not created).
- Unauthenticated API returns 401 (not 500). Login works; `GET /urs/<id>/approval/signatories` for a Nutra URS shows 7 designations.
- Acceptance: with Nutra's QA, use a **dedicated test URS** (not customer records) to confirm Submit by its author,
  refusal for a non-author, one sign-off, and that a second attempt gets 409. Anything not exercised is reported unverified.

## 5. Rollback
Triggers: health != ok after 2 min; any 5xx burst or startup/DB error in `journalctl`; unique-index or integrity failure;
approval page unusable for Nutra signers; QA requests rollback.
```bash
sudo -n cp -p $B/pharmagpt.service.pre-$SHA7 /etc/systemd/system/pharmagpt.service
sudo -n systemctl daemon-reload && sudo -n systemctl restart pharmagpt
sleep 5; curl -s localhost:5000/health; systemctl show pharmagpt -p WorkingDirectory   # must show ...691affa
```
Code rollback does not need a DB restore: the new table/columns/indexes are additive and ignored by 691affa. Restore
`$B/pharmagpt.db` only for data corruption (stop service, copy over, start). Directory (Supabase) changes are reverted
from the rollback JSON the provisioning tool wrote (set `workflow_role_id` back to NULL; delete the new Plant Head row).
Rollback is **claimed only after** health, WorkingDirectory and logs are re-verified.

## 6. Prepared state (2026-10-27, nothing switched)
- Candidate: `a926d99bb609620f2f3ec3641779c958f520bbab`; CI run 40462473301 green (2006 passed, 2 skipped, 1 deselected).
- Staged release dir: `/home/ubuntu/PharmaGPT-release-a926d99` (from `git archive`, tarball sha256
  `cf515d8c618e70c4991b2fc0b50d5bbf460dcb9c56fa3ea8c27238405f4adfb4`, 299/299 files hash-identical to the commit, `.env` copied
  mode 600, venv symlinked to the 691affa venv, compileall ok, `RELEASE_SHA.txt` added). `PharmaGPT-release-de2f9dc` is STALE: do not use.
- Backup for rollback readiness: `/home/ubuntu/db_backups/pre_a926d99_20261027T065621Z` (DB integrity ok, unit file, uploads tar, SHA256SUMS ok).
  Take a fresh backup immediately before the switch (section 2).
- Startup on a throwaway copy of that backup with the new code: adds 3 tables (`validation_signoffs`, `validation_transition_claims`,
  `qms_esignature_attempts`), creator/approval columns, 5 indexes; 0 row changes; idempotent; no missing controls.
- Live preflight from the staged dir: NO-GO (7 blocking, Nutra signer directory) until the approved provisioning is done.

## 7. Release decision: FAIL-CLOSED path (owner-selected 2026-10-27) — read before announcing the release
**Nutra validation approvals remain UNAVAILABLE after this release until authorized provisioning is completed.** Production data and signer
permissions are intentionally left unchanged; department enforcement stays ON (not disabled).
- What stops working for Nutra (the only tenant): **Submit for Review** and **Sign Off** on URS, DQ and IQ/OQ/PQ. Users get HTTP 403 with
  "Signing as <designation> requires a <role> role in: <department>". Nothing is changed by a refused attempt (no status change, no
  sign-off row, no e-signature; verified for all five document types in `tests/test_nutra_fail_closed.py`).
- Cannot be bypassed: Make Effective / Obsolete need an Approved / Effective record, which needs the seven signatures, so they cannot skip it.
- Still works: creating, listing, reading and editing records, the approval page (shows the true status), exports, QMS (deviation, CAPA,
  change control), Document Control authoring, Knowledge Base, chat/AI, login. (Full regression suite; Nutra has 2 URS in draft and no
  approvals in flight, so no existing approval is disrupted.)
- Behaviour change vs 691affa: the old one-step, no-e-signature approval is gone for everyone. That is the intended control improvement.
- To restore approvals: complete the authorized provisioning in `docs/NUTRA_SIGNER_PROVISIONING_PLAN.md` (needs an identity-verified
  approver, a break-glass grant or company_admin, and an independent QA approver), then re-run the preflight to GO. No redeploy is needed
  for that - it is a directory change.
- Tell users before the switch: "URS/qualification/DQ approvals are temporarily unavailable for Nutra."

# Backup Test Report — Template

**Related documents:** `docs/BACKUP_VALIDATION_PROTOCOL.md` (defines when/why this is filled in), `docs/BACKUP_ARCHITECTURE.md`

This is the canonical template. **Tier 1** reports are generated automatically by `scripts/verify_backup.py` (which fills in the same fields programmatically — do not hand-edit an auto-generated report; re-run the script instead) into `docs/VALIDATION_EVIDENCE/backup_test_reports/`. **Tier 2** (full staging restore) reports are filled in by hand using this same template, since Tier 2's application-level checks are not automated.

---

```markdown
# Backup Test Report

**Report ID:** BTR-<YYYYMMDDTHHMMSSZ>
**Tier:** 1 (automated restore-drill) | 2 (full staging restore)
**Generated:** <ISO8601 timestamp>
**Performed by:** <name/role — required for Tier 2; Tier 1 auto-fills "scripts/verify_backup.py">
**Archive tested:** <path or run_id>
**Drill duration:** <seconds>
**Overall result:** PASS | FAIL

## Checks

| Check | Result |
|---|---|
| Archive decrypts | ok / error |
| Manifest present | true / false |
| SQLite integrity_check | ok / <error text> |
| qms_audit_trail row count matches manifest | true / false / n/a |
| qms_esignatures row count matches manifest | true / false / n/a |
| Uploaded documents count matches manifest | true / false / n/a |
| Generated documents count matches manifest | true / false / n/a |
| Postgres JSON exports all valid | true / false / n/a |
| (Tier 2 only) Application boots against restored data | pass / fail |
| (Tier 2 only) GET /health returns 200 | pass / fail |
| (Tier 2 only) Test-user login succeeds | pass / fail |
| (Tier 2 only) Representative pre-backup record visible with correct content | pass / fail |
| (Tier 2 only) Audit trail intact for that record | pass / fail |
| (Tier 2 only) Electronic signature intact (hash verifies) for that record | pass / fail |
| (Tier 2 only) Cross-tenant access still denied post-restore | pass / fail |

## Notes / deviations

<Free text — anything that doesn't fit the table: a check that had to be skipped and why, an anomaly investigated and explained, etc. A report with unexplained skipped checks should not be treated as a clean PASS.>

## Raw check output

```json
<full machine-readable output from backup_service.verify_backup(), for Tier 1>
```

## Sign-off (Tier 2 only)

| Role | Name | Date |
|---|---|---|
| Performed by | | |
| QA reviewer | | |
```

---

## Field guidance

- **Report ID** — always timestamp-based, always unique. Never reuse an ID.
- **Overall result** — PASS requires every applicable check in `docs/BACKUP_VALIDATION_PROTOCOL.md` §2 (Tier 1) or §3 (Tier 2) to pass; a single failure is an overall FAIL, not a partial pass. Do not average or round up.
- **Notes / deviations** — this field exists specifically so a FAIL (or an unusual PASS, e.g. one where a check had to be skipped for a documented reason) is never silently dropped. An empty Notes section on a report with any non-"true"/"pass"/"ok" cell should be treated as an incomplete report, not a valid one.
- **Retention** — see `docs/BACKUP_VALIDATION_PROTOCOL.md` §7. Do not delete old reports; they are the evidence trail proving the backup control has been operating, not just installed.

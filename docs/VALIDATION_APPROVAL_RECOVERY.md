# Validation Approval Workflow — Deployment & Recovery Runbook

Applies to URS, DQ and IQ/OQ/PQ protocols. Nothing here is run automatically. Every data change below is a
**manual, change-controlled action** performed by an authorized administrator after a verified backup; the
application never rewrites production records on startup except the additive schema steps listed in §2.

## 1. Before deploying (read-only)

1. Take and verify a backup (`scripts/run_backup.py`; see `docs/BACKUP_SOP.md`).
2. Run the preflight — it opens SQLite read-only and issues only `SELECT`s to Supabase:

   ```
   python scripts/validation_approval_preflight.py --sqlite <path-to-db> --supabase --json preflight.json
   ```
   Exit `0` = GO, `2` = blocking findings, `1` = could not run. Re-run until there are no `BLOCKING` rows.
3. Resolve every `BLOCKING` finding (§3). `ACTION_REQUIRED` rows are per-record recoveries that may be done after
   deployment but before that record is needed. `WARNING`/`OK` rows are informational.

## 2. What startup changes (additive, idempotent)

| Change | Effect on existing data |
|---|---|
| `CREATE TABLE IF NOT EXISTS validation_signoffs` | none (new, empty) |
| `qual_protocols.approval_status` | new nullable column; **one-time back-fill** of rows still `NULL` from the parent Qualification (approved/closed → approved, under_review, pending_approval, obsolete, else draft) |
| `created_by_user_id` / `created_by_display_name` on `urs_projects`, `qual_qualifications`, `qual_protocols`, `qms_documents` | new columns, blank for existing rows (see §3 `DRAFT_AUTHOR_*`) |

Re-running startup never overwrites a later change (back-fill only touches `NULL`). Rollback = redeploy the previous build;
the extra table/columns are ignored by it, but records already moved into the new intermediate statuses
(`technical_review`, `qa_review`, `validation_review`, `final_approval`) cannot be actioned by the old build — finish or
reject them first.

## 3. Findings and how to recover each state

| Code | State | Meaning | Recovery |
|---|---|---|---|
| `READY_DRAFT` / (no finding) | Draft, creator known | none | none |
| `DRAFT_AUTHOR_NAME_FALLBACK` | Draft, blank creator id, name known | authorship matched on the stored display name | Author submits normally. Optionally stamp the true id (below) to remove the weak name match. |
| `DRAFT_AUTHOR_UNKNOWN` | Draft, no identity at all | nobody can submit it | **Stamp the creator** (below), or recreate the record. |
| `RESTART_REQUIRED` | Under Review / Pending Approval under the old workflow, no sign-offs | cannot reach Effective (needs 7 sign-offs) | A reviewer/approver with Validation:Review (department-authorized) **rejects it with a reason** ("restart under standard workflow"). History is kept. The author resubmits. **DQ:** rejection forks a new immutable draft version, so the author repeats Self-Check + Final Author Version. |
| `IN_FLIGHT_STANDARD_WORKFLOW` | already on the new workflow | none | continue signing |
| `LEGACY_APPROVED` | Approved, no ledger | grandfathered | Final approver runs **Make Effective** (e-signature). DQ also needs the training gate. Publication to the KB happens at that moment. |
| `APPROVED_WITH_INCOMPLETE_LEDGER` | Approved, fewer than 7 sign-offs | should not exist; ledger altered or partially restored | **Do not edit the ledger.** URS/protocol: reject from Approved (bumps revision) and re-run the chain. DQ cannot be rejected from Approved: raise a deviation, QA decides (new revision via *start-revision* after release, or controlled correction). Investigate how it happened. |
| `EFFECTIVE_OK` | Effective | none | none |
| `EFFECTIVE_NOT_IN_KB` | Effective but never published | KB gap | Re-publish through the normal gate (legacy records have no ledger so publication is allowed), e.g. from a shell with an app context: `kb_sync.publish_to_kb(source_type=…, source_id=…, company_id=…, …)`; or revise and re-release. Record it in the change record. |
| `EFFECTIVE_WITH_INCOMPLETE_LEDGER` | Effective with a partial ledger | altered ledger | Treat as an integrity event: QA investigation; do not rewrite rows. |
| `REJECTED_RESUBMITTABLE` | Draft after rejection | none | Author resubmits; superseded rows stay as history; a new cycle needs all seven signatures again. |
| `LEGACY_EXECUTION_GRANDFATHERED` | Protocol with executions recorded, no ledger | may continue executing | Finish execution. **Approving it retrospectively is a QA decision** (executed-before-approval is a deviation); once raised, follow the standard chain. |
| `LEGACY_DQ_WORKFLOW_GRANDFATHERED` | DQ with an active legacy workflow instance | finishes on the legacy engine | Complete or reject it there; the next submission uses the shared engine. |
| `TENANTLESS_RECORD` | row has no `company_id` | unreachable by any tenant | Assign the correct `company_id` (below) after confirming ownership. |
| `LEDGER_COMPANY_MISMATCH` | sign-off rows filed under another company | integrity/tenant defect | Stop and escalate; do not deploy until understood. |
| `NO_ELIGIBLE_SIGNER` | a company has nobody for a designation | that company cannot complete a cycle | Provision memberships (§4) — nobody can be a signer without department + functional role + `Validation` permission (+ `company_admin`/`reviewer_qa` platform role for review lines). |
| `INSUFFICIENT_DISTINCT_SIGNERS` | fewer than seven different people can fill the seven lines | segregation of duties cannot be met | Add people. There is deliberately no switch to relax this; an exception needs a documented, QA-authorized policy implemented as reviewed code. |
| `ENV_*` | a Supabase key is not set | e-signature re-authentication / department lookup cannot work | Set it in the deployment environment (never in the repo). |

### Stamping a creator or tenant (manual, after backup, with a change record)

```sql
-- run once per record, inside a transaction, by an authorized DBA; keep the output in the change record
UPDATE urs_projects SET created_by_user_id = '<auth user uuid>', created_by_display_name = '<name>'
 WHERE id = <id> AND (created_by_user_id IS NULL OR created_by_user_id = '');
-- same shape for qual_qualifications, qual_protocols, qms_documents
UPDATE urs_projects SET company_id = '<company uuid>' WHERE id = <id> AND (company_id IS NULL OR company_id = '');
```
Add an audit-trail entry describing who authorized the change and why. The creator columns are never writable through the API.

## 4. Provisioning a company that is not ready

Use the existing Organization admin (`/org`, `/rbac`): add each person to the department with the functional role the
designation needs (Initiator / Reviewer / Approver / Plant Head, or Coordinator), assign the matching RBAC role so they
hold `Validation:Submit`/`Review`/`Approve`, and give review-line signers the `reviewer_qa` platform role. Re-run the
preflight; the company must show `ready` with `distinct_assignable 7/7`.

## 5. After deploying (verification)

1. Re-run the preflight against the production database (still read-only): no new `BLOCKING` rows; counts of
   `RESTART_REQUIRED` fall as you work through them.
2. Smoke test with a throwaway URS in a test company: author submits, a non-author is refused, a wrong e-signature
   password is refused, the chain completes, Make Effective publishes to the KB.
3. Confirm `validation_signoffs` rows carry `esignature_id` and `signature_hash` and that those match `qms_esignatures`.

## 6. Rollback and its limits

Redeploy the previous build; do not drop the new table or columns. Records sitting in the new review statuses need to be
rejected back to Draft (with the new build) *before* rolling back, otherwise the old build cannot action them. Sign-off
rows are append-only and are retained.

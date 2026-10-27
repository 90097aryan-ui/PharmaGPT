# Nutra — Validation Signer Provisioning Plan (authorization-ready, NOT executed)

Status: **PROPOSED. No change has been made.** Production directory, SQLite and service are untouched.
Release under review: `de2f9dc` (+ local preflight repair `d3b84f0`, unpushed). Production: `691affa`.
Evidence date: 2026-10-27. Evidence method: select-only reads; in-memory simulation (no writes).
Users appear only as 6-hex pseudonyms (first 6 chars of SHA-256 of the user id). No names/emails.

## 1. Why (root cause)

`validation_approval._signer_department` requires ONE `user_departments` row whose department code AND
functional role (`workflow_roles`) both match the designation. In Nutra:
- all 22 memberships have `workflow_role_id = NULL` → no row can satisfy any designation;
- no `PLANT_HEAD` membership exists (the Plant Head user has no membership row).
Departments, platform roles, RBAC grants and RBAC role assignments are already correct.

## 2. Proposed changes (minimum set: 6 updates + 1 new row)

Mapping rule: the functional role is the one already named by the user's existing company RBAC role
(e.g. RBAC role "Validation Approver" → department VALIDATION, functional role Approver). No new RBAC
role, grant, user or department is created. `is_primary` is not changed.

| # | User | Designation | Dept | Functional role | RBAC evidence (existing assignment) | Change type |
|---|---|---|---|---|---|---|
| 1 | `9f4353` | Validation Engineer (Prepared By) | VALIDATION | Initiator | RBAC "Validation Initiator"; platform role `user` (no platform role needed for Prepared By) | UPDATE `workflow_role_id` on existing row |
| 2 | `bef06d` | Process Engineer (Reviewed By) | ENGINEERING | Reviewer | RBAC "Engineering Reviewer"; platform `reviewer_qa` | UPDATE |
| 3 | `e87edc` | Engineering Manager | ENGINEERING | Approver | RBAC "Engineering Approver"; `reviewer_qa` | UPDATE |
| 4 | `f38cda` | Production Manager | PRODUCTION | Approver | RBAC "Production Approver"; `reviewer_qa` | UPDATE |
| 5 | `b0369b` | QA Manager | QA | Approver | RBAC "QA Approver"; `reviewer_qa` | UPDATE |
| 6 | `cf46ca` | Validation Manager | VALIDATION | Approver | RBAC "Validation Approver"; `reviewer_qa` | UPDATE |
| 7 | `31405c` | Site Director / VP Quality (Final Approval) | PLANT_HEAD | Plant Head | RBAC "Plant Head / Approver"; `reviewer_qa`; currently NO membership row | INSERT new membership |

Choice flagged for the approver: Reviewed By accepts ENGINEERING **or** PRODUCTION Reviewer. Row 2 uses
Engineering Reviewer; Production Reviewer `75459e` is an equally valid alternative (pick one; do not do both
unless wanted — both would make two eligible reviewers).

Simulation (in-memory, same code as the preflight, using live directory data): after #1–#7 →
`ready=True`, eligible signers per designation 1/2/1/1/1/1/2, **7 of 7 distinct signers assignable**.
Without #7 only 6/7 (the only other Final Approval candidate is the QA Approver, already needed as QA Manager).
Separation of duties is unchanged: still seven different people, no switch.

## 3. Expected impact

- **Validation (URS, DQ, IQ/OQ/PQ):** these 7 users become eligible for exactly their designation (plus the
  existing RBAC grants/platform role, which still apply). Nobody else becomes eligible. Author-only submission
  and one-person-one-designation are unchanged and enforced server-side + by the DB unique indexes in `de2f9dc`.
- **Other workflows (side effect):** `workflow_engine` auto-resolves approvers by (department, functional role)
  only for template steps that opt in via `department_code` + `functional_role_name`. In production SQLite 0 of
  61 template steps opt in (read-only count), so **no current QMS/Document Control workflow routing changes**.
  If steps are later configured to opt in, these users would be resolved. Setting roles on the other 15 rows
  (PPIC, QC, Warehouse, Production/Engineering/QA Initiator etc.) is NOT proposed.
- **Other modules' RBAC:** no RBAC role/grant changes; no effect on access outside the Validation designations.
- **Rollback:** each change is reversible (#1–#6 set `workflow_role_id` back to NULL; #7 delete the new row).
  Capture pre-change values first (membership row id, `workflow_role_id`, `is_primary`).

## 4. Required approvals (record each in writing before execution)

| Item | Approver | Needed because |
|---|---|---|
| #1–#6 | Nutra company administrator | directory change inside their tenant |
| #1–#7 | Nutra QA head | designation eligibility for GMP signatories (Part 11 / Annex 11 accountability) |
| #7 (new membership) | Nutra administrator **and** QA | adds a membership, i.e. new authority for Final Approval |
| Reviewer choice (Eng vs Prod) | Nutra QA | selects who is the Reviewed By signatory |

Approval record must name the exact rows above (pseudonym + designation + dept + role). No approval is
inferred from any earlier task statement.

## 5. Execution method — BLOCKER FOUND in the mandated function

The instruction is to apply changes via `org_assignment.assign_user_to_department`. Reading it
(`pharmagpt/services/org_assignment.py:54-96`, `db/rbac_repo.py:136`, `migrations/0015…:272`):
1. it upserts the membership (the intended change);
2. then **INSERTs** the matching company RBAC role into `rbac_user_roles`;
3. only then writes the `rbac_audit_log` entry.
`rbac_user_roles` has `UNIQUE (user_id, role_id)` and every one of these 7 users **already holds** that RBAC
role. Step 2 would raise a unique-violation after step 1 committed → **membership changed but no audit row
written** (an unaudited change, the opposite of the requirement). Status: Confirmed from code and schema;
not executed (would write production).

Options (approver/engineering decision; none executed):
- **A (recommended):** small code fix + test: in `assign_user_to_department`, skip the RBAC insert when the user
  already holds the role (membership + audit still written, one audit row per change). Separate commit; then use it.
- **B:** a reviewed one-off script calling `org_directory.add_department_membership` and
  `rbac_repo.add_rbac_audit_entry` directly (same effect, no RBAC insert), with `reason` citing the approval ref.
**Decision recorded: option A selected. Implemented locally as commit `533dde5` (unpushed, not deployed). The
provisioning call is a one-off, so it must be run from a checkout that contains `533dde5` (not from the staged
`de2f9dc` release, which lacks the fix and would hit the unaudited-change defect).** Evidence: new regression test fails without the fix and passes
with it; `tests/test_org_assignment.py`, `test_rbac.py`, `test_org_directory.py` = 50 passed.
Either way: read the current `is_primary` per row and pass it back unchanged (membership upsert only touches
`is_primary` when True, and then only via `set_primary_department`).

## 6. QA Coordinator — separate decision (NOT part of this plan)

User `6facc0` holds RBAC "QA Coordinator/Admin" (dept QA, no functional role now). Mapping to `Coordinator` is
**not proposed and left unchanged**. If QA later decided to do it, consequences:
- `Coordinator` is accepted on every designation line → this user would be eligible for any ONE designation per
  cycle (SoD still forbids two). Simulation C: QA Manager eligible 1→2, Final Approval 2→3.
- It broadens who can sign GMP approvals; it is an elevation, so it needs its own explicit QA decision recorded
  separately, with a stated reason (e.g. backup signatory). It is not needed for 7/7.

## 7. After approval (not started)
Apply approved rows (method A or B) → rbac audit entries → re-run repaired preflight read-only (expect GO only if
all seven designations show a distinct eligible signer) → URS 1 & 2 blank-creator investigation → review the six
startup changes → request separate deployment authorization.

## 8. Execution tooling (committed locally, nothing executed)
`scripts/provision_validation_signers.py` (+ `pharmagpt/services/signer_provisioning.py`, tests in
`tests/test_signer_provisioning.py`). Dry run by default; `--execute` requires `--rollback-out` and a complete
approval file (administrator + QA head; additional administrator + QA approvals for the Plant Head membership;
QA `reviewer_choice` = ENGINEERING|PRODUCTION; `actor_pseudonym`). It accepts only the approved minimum set
(no Coordinator, no extra rows, distinct users), resolves users by pseudonym, requires each user to hold the
justifying RBAC role, captures original rows before writing, preserves `is_primary` (new Plant Head row: False —
confirm with the administrator), calls `assign_user_to_department` (which now compensates on failure and records
`old_value`), and re-reads membership + audit row after each change. Approval files hold references only and must not be committed.

## 9. URS 1 and 2 — blank creator ids (read-only findings, no change made)
Both are `draft`, created 2026-09-28 and 2026-10-10, no sign-offs (the ledger does not exist yet). `prepared_by` is set on both.
- URS 2: exactly one active directory user has the same display name → author-by-name works; optional stamp of the true id.
- URS 1: **no** directory user has that display name → nobody can submit it as its author (author-only rule).
Not a deployment blocker (no in-flight approvals). Recommended controlled remediation (needs Nutra QA to name the true
author of each, a backup, and a change record): follow `docs/VALIDATION_APPROVAL_RECOVERY.md` "Stamping a creator" for URS 2
(confirm user) and URS 1 (QA-attested author), or recreate URS 1 under the right author. Do not stamp by guess.

## 10. Correction
The earlier "2.50:1" for `--text-disabled` came from a faulty ad-hoc script. Correct value on `--bg` is 2.97:1 (still < 4.5:1 AA);
`--text-muted` is 6.01:1 (passes). Fixed in `7909301` (`#6F5F52`, 5.58:1) with `tests/test_neumorphic_contrast.py`.

## 11. Architecture reassessment (read-only evidence, 2026-10-27)
- **What "Nutra" is:** one `companies` row (`legal_name` Nutra, `industry_segment` = `nutraceutical`, created 2026-07-30) — the
  **demo tenant** created by `scripts/seed_nutra_demo.py` (docs `NUTRA_DEMO_DATA.md`). It is the only tenant in production
  (23 users, all with the seed's `@nutra.com` addresses, plus one platform super-admin without a company). "Category" is a
  different thing: the `industry_segment` column. Tenant = `companies.id` (all data is filtered by it). QA approval is a workflow
  inside a tenant (designations + RBAC + department membership); it is not a category.
- **Root cause of the 7 blockers:** a data/seed generation gap, not a code-design defect. The seed (2026-07-28) stores each
  user's functional role in the legacy global column `users.workflow_role_id` (migration 0014). Migration 0016 (2026-09-07) made the
  functional role a property of the department membership (`user_departments.workflow_role_id`) so that "QA Reviewer" != "Production
  Reviewer"; the validation engine reads only that. The seed was never updated and no backfill exists, so all 22 memberships are NULL.
  Evidence: all 23 users have a legacy role (7 Initiator, 7 Reviewer, 7 Approver, 1 Coordinator, 1 Plant Head) and it agrees with the
  role implied by their RBAC role for 23/23; 22 users have exactly one membership (so a mapping is unambiguous); the Plant Head user has none.
- **Why "QA Approver" RBAC alone does not qualify:** RBAC answers "may this person do Validation:Approve?"; the signatory line
  answers "may they sign AS the QA Manager?", which needs the department. The engine requires department AND functional role from
  the same membership row (`validation_approval._signer_department`), deliberately fail-closed. It is an implementation of the
  approved designation model (docs/VALIDATION_APPROVAL_WORKFLOW.md), not a Supabase/RBAC rule, and the default can be flipped only by
  a QA-authorized policy change. Making eligibility follow the RBAC role *name* would hang a signature authority on a free-text,
  per-company-editable string and re-open the cross-department ambiguity 0016 removed; accepting the legacy global role would let a
  user with Approver in QA and Production sign both lines. Neither is recommended.
- **Recommendation:** keep the engine; treat this as tenant data. The 7 minimum rows in §2 stay valid and are now backed by two
  independent records (RBAC role and the legacy functional role). Also fix `scripts/seed_nutra_demo.py` to write
  `user_departments.workflow_role_id` so a re-seed cannot recreate the gap (code change, no production effect).
- **Security note (unverified):** the seed script hard-codes one shared demo password and the production Supabase has 23 matching
  accounts with elevated platform roles. Whether it was ever changed is unknown (not tested). Owner should rotate/disable demo
  accounts before any real use of yuktav.com.


## 12. Hardened tool (local, unpushed; supersedes the description in section 8; provisioning remains BLOCKED)
`scripts/provision_validation_signers.py` + `pharmagpt/services/signer_provisioning.py` now fail closed:
- **Identity:** actor, administrator approver and QA approver each present a live Supabase access token, verified with the app's own
  `resolve_tenant_context`. No actor id is read from a file.
- **Authorization:** the actor must be this company's `company_admin`, or a `super_admin` with an ACTIVE `break_glass_access` grant for the
  company (the platform's Assume Company Context rule); the grant id is written into every audit entry. Lookup errors refuse.
- **Approvals:** bound to the exact change set by SHA-256, dated within 30 days, with references; approver pseudonyms must equal the
  authenticated approvers. **Independent QA is mandatory in this tool** (policy is not defined in the repo, so the strictest reading is
  enforced; relaxing it is a reviewed code change): QA approver != actor != administrator approver, holds QA Approver / QA Coordinator/Admin,
  and is not one of the people changed; nobody acting or approving may be one of the 7 changed users.
- **Attribution/atomicity:** audit entries carry the verified actor and approval references and are re-read after each change; any failure
  rolls back everything applied (each undo audited); `--rollback FILE` is an audited undo. Dry run is the default and still verifies everything.
- **Practical consequence for Nutra:** it has no `company_admin`. A super_admin needs an active break-glass grant, AND a different tenant user
  with a QA authority role must co-approve (the directory has a QA Coordinator/Admin user who is not among the 7). Whether a demo tenant may
  use a different process is the owner's quality-system decision, not something the tool can waive.

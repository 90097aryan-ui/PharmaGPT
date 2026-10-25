# Validation Approval Workflow (URS, DQ, IQ, OQ, PQ)

One engine — `pharmagpt/services/validation_approval.py` — runs the approval of all five Validation
document types. Each suite supplies only an adapter (how to read/write its own record); lifecycle,
signatories, RBAC, department enforcement, distinct signers, e-signature, the Effective gate and the
Knowledge Base gate exist once.

| Type | Record | Route | Ledger `doc_type` / `record_id` | Adapter |
|---|---|---|---|---|
| URS | `urs_projects` | `/urs/<id>/approval` | `URS` / urs id | `routes/urs.py` |
| DQ | `qms_documents` (doc_type `DQ`) | `/qms/documents/<id>/approval` (and `/release`) | `DQ` / document id | `routes/qms_documents.py` (`_shared_document_approval`) |
| IQ / OQ / PQ | `qual_protocols.approval_status` | `/qual/<qid>/protocols/<pid>/approval` | `IQ`/`OQ`/`PQ` / **protocol** id | `routes/qual.py` (`add_protocol_approval`) |

## Lifecycle

`draft → under_review → technical_review → qa_review → validation_review → final_approval → approved → effective`
(then `obsolete`). `urs_lifecycle.ALLOWED_TRANSITIONS` is the single source of truth. No stage can be skipped.
`pending_approval` is the pre-standard status: kept so existing rows load, but reject-only.

## Signatories (exact approved set) and who may sign

| Line | Designation | Stage | Needs `Validation:` | Department (`user_departments`) | Functional role |
|---|---|---|---|---|---|
| Prepared By | Validation Engineer | submit | Submit | VALIDATION | Initiator |
| Reviewed By | Process Engineer | under_review | Review | ENGINEERING or PRODUCTION | Reviewer |
| Engineering | Engineering Manager | technical_review | Approve | ENGINEERING | Approver |
| Production | Production Manager | technical_review | Approve | PRODUCTION | Approver |
| Quality Assurance | QA Manager | qa_review | Approve | QA | Approver |
| Validation | Validation Manager | validation_review | Approve | VALIDATION | Approver |
| Final Approval | Site Director / VP Quality | final_approval | Approve | PLANT_HEAD or QA | Plant Head / Approver |

`Coordinator` is accepted for every line (it holds all actions). Department **and** functional role must come
from the **same** membership row. Everything except submission also needs platform role `company_admin` or
`reviewer_qa`, so an Initiator (`user`) can submit but never sign, reject, release or obsolete.

- **Department enforcement is ON** (`VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT`, default true). Directory
  errors deny. A `company_admin` with no membership cannot sign. Turning it off is a QA-authorized policy change.
- **Seven distinct signers, no switch.** One person cannot hold two lines in a cycle. An exception would have to
  be a reviewed code change implementing a documented, authorized policy — there is deliberately no setting.
- **E-signature** on every action, with a fixed meaning set per action; the sign-off row links to the immutable
  `qms_esignatures` row (id + hash). Identity (user id, name, role) comes only from the authenticated tenant.
- **Append-only history.** `validation_signoffs` rows are never deleted or rewritten; rejection marks the
  cycle `superseded`; resubmission starts a new cycle.
- **Tenant isolation.** Every ledger query is filtered by `company_id`; routes 404 on foreign records.
- **Authorization precedes state** (403 before 409).

## Protocols (decision 2)

Each IQ/OQ/PQ protocol has its own `approval_status`, `revision` and ledger. The parent Qualification only groups
them: its status is a roll-up (draft / under_review / approved when all protocols are approved / effective when all
are effective) and standard approval actions at the parent are refused (400). A protocol's definition (fields and
test-case structure) is locked once it leaves Draft; recording execution results is not. `approval_status` and
`revision` have a single writer (`qual_database.set_protocol_approval_status`) and are not settable through PUT.
Making a protocol Effective takes a version snapshot.

## DQ (decision 1) — Document Control safeguards preserved

DQ uses the shared engine but keeps: Author Self-Check and Final Author Version as pre-submission vetoes; version
rows moving draft → under_review → pending_approval → approved → effective (immutability triggers untouched);
a new immutable draft version forked on rejection; the training gate (>= 90 %, >= 1 trainee) and content check as
pre-signature vetoes on Make Effective (so a blocked release never consumes a signature); content lock outside
Draft; `/release` delegates to the same path; and `qms_document_database.try_clear_training_gate` refuses
Effective for a DQ whose ledger is incomplete. A named per-document review chain is **not** required for DQ —
authority comes from department + functional role. A DQ cannot be rejected from `approved` (its version cannot
be un-approved); revise an Effective DQ with the existing start-revision flow.

## Knowledge Base (decision 6)

Publication happens at the `effective` transition only: URS (already so), DQ (already so), and each protocol at
**its own** Effective (previously: at container approval, all protocols). `kb_sync.publish_to_kb` itself refuses
(`ApprovalError` 409) any governed record whose mandatory approvals are not complete.

## Migration and in-flight records

- `CREATE TABLE IF NOT EXISTS validation_signoffs` and `ALTER TABLE qual_protocols ADD approval_status` are additive
  and idempotent. The one-time back-fill touches only rows where `approval_status IS NULL`: it carries a legacy
  container approval down to its protocols (approved/closed → approved, under_review → under_review, …).
- **Already approved under the old workflow** (zero ledger rows ever): can still be made Effective and published.
  A record approved by the new flow always has rows, so this exemption cannot be used to skip approvals.
- **In flight under the old workflow** (`under_review`/`pending_approval`, no ledger): cannot be completed; reject to
  Draft and resubmit (the approval page says so).
- **DQ with an active legacy workflow instance** finishes on the legacy engine; new submissions use the shared one;
  starting a legacy workflow for a DQ is refused.
- Rollback: redeploy the previous build. The new table/column are ignored by it, but records sitting in the new
  intermediate statuses are not actionable there.

## Authorship (only the author may submit)

`Validation:Submit` plus Validation/Initiator membership is **not** enough: the engine also requires the caller to be
the record's creator. The creator (`created_by_user_id` / `created_by_display_name`) is stamped once from the
authenticated session by `creator_identity.stamp()` on `urs_projects`, `qual_qualifications`, `qual_protocols` and
`qms_documents`; it is absent from every update allow-list and ignored if sent in a request body. Fallbacks for rows
that pre-date the columns: a protocol uses its parent Qualification's creator; a DQ uses its first version row's
`created_by_user_id`; as a last resort the authenticated display name stamped into `prepared_by` (weak — names are not
unique, and the preflight lists every such record). A record with no identity at all cannot be submitted until its
creator is stamped (runbook). Company admins get no override: they would still need to be the author.

## Approval before execution (IQ/OQ/PQ)

Executing a test case or completing a protocol requires that protocol's own `approval_status` to be `approved` or
`effective` (a sibling's approval does not count). It does **not** wait for Effective: `services/approval_engine.py`
orders the lifecycle Approved -> Execution -> Post Execution Review -> Effective, so Effective is the state *after*
execution evidence exists. Grandfathered: a protocol with executions recorded and no ledger row ever (started before
approval tracking) may continue; a protocol that has been through the new workflow always has ledger rows, so it
cannot use that exemption (rejecting an executed protocol blocks further execution until it is re-approved). The
existing IQ -> OQ -> PQ sequencing gate is independent and unchanged.

## Preflight and recovery

`scripts/validation_approval_preflight.py` (library: `services/validation_preflight.py`) is a read-only check for
companies that could not complete a seven-signer cycle and for records that would be blocked, restarted or
grandfathered. See `docs/VALIDATION_APPROVAL_RECOVERY.md` for the finding codes and the recovery of each legacy state.

## Relationship to SOD-01 Wave 1 (`stash@{0}`)

The stash holds an earlier version of what the tree already contains as CRIT-02 (`workflow_engine.reject_creator_as_approver`,
`CREATOR_LOOKUP`, `created_by_user_id/display_name` on deviations/CAPA/change control — covered by the passing
`tests/test_crit02_segregation_of_duties.py`). The stash was **not applied**. The one compatible gap was Document
Control: `create_document` had no `created_by_display_name` and `qms_documents` no creator columns, so the document
entry of `CREATOR_LOOKUP` could never fire. That is now integrated (additive columns, stamped at creation). Three of
the eight staged `test_segregation_of_duties_wave1.py` tests pass as a result. The other five assert behaviour that
later hardening intentionally replaced (CRIT-02's company-directory check returns 400 before the SoD check; Document
Control's per-step assign endpoint is disabled with 403; the Self-Check gate fires before the legacy `/approval`
wrapper) and cannot pass without weakening those controls; they should be rewritten, not made to pass.

## Known limits

- Which production companies have `user_departments` populated cannot be verified from a checkout — run the preflight
  with `--supabase`. With enforcement on, a company without memberships cannot sign until they are provisioned.
- The browser test drives the shared approval component and the real API in a real browser against an isolated server;
  it does not drive the full single-page-app shell (login via Supabase, navigation).

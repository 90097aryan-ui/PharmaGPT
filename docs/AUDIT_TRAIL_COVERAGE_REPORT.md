# Audit Trail Coverage Report — Phase F, Work Package 2

**Scope:** Verify and complete audit-trail logging for every create/update/delete/approval-transition endpoint across Projects, URS, Qualification/Protocols/IQ/OQ/PQ, Validation Reports, Approvals, Users, Roles, Companies, Knowledge Base, Equipment, CAPA, Deviation, Change Control, and Documents. Required fields per the Phase F brief: Timestamp, User, Company, Object Type, Object ID, Action, Old Values, New Values, Reason, Session/IP, Result.

## 1. Schema change

`qms_audit_trail` (the shared, polymorphic audit table already used by every SQLite-backed module) previously captured only `record_type, record_id, action, detail, performed_by, created_at`. Extended additively (`pharmagpt/database.py`, `_add_column_if_missing` — safe to run on every startup, never destructive) with:

`company_id, old_values, new_values, reason, ip_address, session_id, result`

`pharmagpt/qms_database.py::add_audit_entry()` was extended to accept and persist all seven new fields. **Verified directly**: schema migration and the low-level write path were smoke-tested against the live dev database (`pharmagpt.db`) before any route was touched — see the test row inserted and confirmed, then removed, at the start of this work package.

## 2. New shared writer: `pharmagpt/audit.py`

A single `audit.log(record_type, record_id, action, old=, new=, reason=, result=)` helper now backs every call site touched in this work package. It:

- Derives `performed_by` and `company_id` from the authenticated `g.tenant` — **never from client-supplied JSON/form fields** (closes the same class of spoofing bug `tenancy.signing_identity()` already closed for e-signatures, extended here to every audit entry, not just approvals — see §4/C6 below).
- Computes `old_values`/`new_values` as a **diff** of the two record dicts passed in (only changed fields are stored), redacting sensitive keys (`password`, `electronic_sig`, `access_token`, etc.) if they ever appear.
- Reads `ip_address` (`X-Forwarded-For` / `remote_addr`) and `session_id` (the existing anonymous-visitor session id set in `app.py::index()`) from the current Flask request/session.
- `result` defaults to `"success"`; `audit.log_failure()` is a convenience wrapper for logging a blocked/rejected attempt (illegal transition, workflow-sequencing violation) with `result="failure"`.

This is a **verifiable, code-level fact**, not a claim: `pharmagpt/audit.py` exists, is imported by every route file listed in §3, and was exercised by the full `pytest` run at the end of this work package (see `docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md`).

## 3. Coverage added, by domain

| Domain | File | Create | Update | Delete | Approval/transition | Notes |
|---|---|---|---|---|---|---|
| Project | `routes/projects.py` | ✅ (upgraded to `audit.log`, now with old/new/company) | ✅ (upgraded, now captures old/new) | ✅ (upgraded) | n/a | Already had create/update/delete audit pre-Phase F; now uses the richer helper. |
| Equipment | `routes/equipment.py` | ✅ **new** | ✅ **new** | ✅ **new** | n/a | Previously **zero** audit calls anywhere in this file — confirmed gap from Phase E (C4), now closed. Document link/unlink also audited. |
| URS | `routes/urs.py` | ✅ **new** | ✅ **new** (+ terminal-state immutability guard, see WP3) | ✅ **new** | AI review and version-snapshot events **new**; approval already existed | Also registered as a viewable record type on the shared `/qms/urs/<id>/audit-trail` endpoint (previously URS's audit trail existed but wasn't reachable through it — `qms_common.py`). |
| Qualification / Protocols / IQ / OQ / PQ | `routes/qual.py` | ✅ **new** (qualification, each protocol, each deviation) | ✅ **new** | ✅ **new** | Test execution and AI test-case generation events **new**; protocol-completion and top-level approval upgraded | Protocol-level create/execute now also carries the WP3 sequencing gate (see `docs/WORKFLOW_VALIDATION_REPORT.md`). |
| Validation Report | `routes/report.py` | ✅ **new** | ✅ **new** (+ terminal-state guard) | ✅ **new** | Version snapshot **new**; approval upgraded (now includes the WP3 PQ-completeness gate) | |
| QMS Document Control | `routes/qms_documents.py` | ✅ (upgraded) | ✅ **new** (+ terminal-state guard) | ✅ **new** | AI draft generation (success + failure) **new**; version creation **new**; approval upgraded | Confirms Phase E's finding: PUT/DELETE and the generation event were previously unaudited. |
| Deviation | `routes/qms_deviations.py` | ✅ (upgraded) | ✅ **new** (+ terminal-state guard) | ✅ **new** | AI investigation run **new**; approval upgraded (+ terminal-state guard) | |
| CAPA | `routes/qms_capa.py` | ✅ (upgraded) | ✅ **new** (+ terminal-state guard) | ✅ **new** | Action escalation **new** (was also missing a role guard — see `docs/RBAC_VERIFICATION_REPORT.md` C7); approval upgraded (+ terminal-state guard) | |
| Change Control | `routes/qms_change_control.py` | ✅ (upgraded) | ✅ **new** (+ terminal-state guard) | ✅ **new** | Approval upgraded (+ terminal-state guard) | |
| Risk Assessment | `routes/risk.py` | ✅ **new** | ✅ **new** (+ terminal-state guard) | ✅ **new** | Publish-to-library **new** (was also missing a role guard AND a status check — see C7); approval upgraded | |
| Knowledge Base | `routes/knowledge_base.py` | ✅ **new** | n/a (no PUT route exists) | ✅ **new** | n/a | Registered as a viewable record type (`kb_document`) on the shared audit-trail endpoint. |
| Attachments / Comments (shared, all QMS modules) | `routes/qms_common.py` | ✅ **new** (comments were entirely unaudited; attachments already logged an entry but with a spoofable identity — see §4) | — | ✅ **new** (attachment delete) | — | |
| Project Documents | `routes/docs.py` | n/a (upload not audited — see residual gaps below) | n/a (no update route) | ✅ **new** | n/a | Lower-priority working documents, not a GxP-controlled record type; delete now audited for completeness. |
| Users | `routes/users.py` | ✅ **new** (invite) | ✅ **new** (PATCH) | n/a (soft-deactivate only, covered by update) | — | **Postgres-backed, best-effort** — see §5. |
| Companies | `routes/companies.py` | ✅ **new** | ✅ **new** (suspend/reactivate) | n/a (no delete route exists) | — | **Postgres-backed, best-effort** — see §5. |

**Not extended in this work package** (documented, not silently dropped): individual URS-requirement / qualification-test-case / QMS-document-distribution-and-training sub-record CRUD remain unaudited at the field level. These are line items inside an already-audited parent record (the parent's create/update/delete IS audited), not independent GxP records — flagged as a residual, lower-priority gap rather than expanded into scope, consistent with the Phase F brief's "only fix verified release blockers" instruction.

## 4. Identity-spoofing fixes (closes C6)

Every one of the following previously accepted a client-supplied identity string for what is effectively an attribution/e-signature-adjacent field. All now derive identity from `g.tenant` / `tenancy.signing_identity()`:

| Location | Field | Fix |
|---|---|---|
| `routes/qms_common.py` attachment upload | `uploaded_by` | now `g.tenant.display_name or g.tenant.email` |
| `routes/qms_common.py` comment add | `author`, `role` | now derived from `g.tenant` |
| `routes/urs.py` version snapshot | `created_by` | now `_current_display_name()` |
| `routes/qual.py` protocol version snapshot | `created_by` | now `tenancy.signing_identity()` |
| `routes/qual.py` `complete_protocol` | `performed_by` | now `tenancy.signing_identity()` |
| `routes/qual.py` `execute_test_case` auto-deviation | `raised_by` | now the authenticated executor's identity |
| `routes/qms_documents.py` version snapshot | `changed_by` | now `tenancy.signing_identity()` |
| `routes/report.py` version snapshot | `created_by` | now `tenancy.signing_identity()` |

## 5. Known limitation — Postgres/Users/Companies audit is best-effort and currently unverifiable live

`routes/users.py` and `routes/companies.py` now call a best-effort audit helper (`pharmagpt/db/qms_repo.py::add_audit_entry`, the pre-existing Postgres-side `audit_trail` table) wrapped in try/except, mirroring this codebase's established dual-write failure pattern — a logging failure never blocks the primary action. **This cannot be verified as actually landing rows in the live database from this session**: per `docs/PHASE_F_FINDING_TRACEABILITY.md` A1/C1, the Postgres GRANTs for the identity/admin migrations (0010-0012) are not confirmed active in the live Supabase project, and this session has no live database session to check against. The code is correct and ready; whether it actually writes successfully **today** is marked **NOT VERIFIED**, not fixed, pending that separate operational item.

## 6. Verification performed

- Schema migration smoke-tested directly against the dev SQLite database (insert + read-back + cleanup) before any route change.
- `from pharmagpt.app import app` re-verified after every file's edits (12 checkpoints) — no import/syntax regressions introduced.
- **3 new automated tests** in `tests/test_phase_f_compliance.py` assert, against the real app and the real `qms_audit_trail` table (not a mock), that: creating an Equipment record writes an audit entry with the correct `company_id`, `performed_by`, and `result`; updating one writes an entry whose `old_values`/`new_values` actually contain the changed field; deleting one writes a "Deleted" entry. A fourth test asserts a QMS comment's stored `author`/`role` match the authenticated caller, not a spoofed request-body value (closes C6 for that specific endpoint). All four pass.
- Full `pytest` suite re-run at the end of this work package (514 tests total) — see `docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md` for the pass/fail count; this is the authoritative regression check for this work package, not a claim made here in isolation.

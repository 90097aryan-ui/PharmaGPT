# Electronic Signature Framework — Implementation Report

**Branch:** `feature/e-signature` (off `feature/rbac-framework`; not merged into `main`, not deployed).

## 1. Scope and approach

Additive compliance layer on top of the frozen authentication and RBAC frameworks — neither was modified. Closes the gap `docs/PLATFORM_ARCHITECTURE.md` §18 explicitly flagged as a defined future capability: *"v1.0 captures the manifestation of approval (actor, role, timestamp, reason) but not a cryptographically binding electronic signature... The schema and workflow are shaped so that adding true e-signature is additive — a new signature-event table linked to the existing approval action — not a redesign."* This implementation is exactly that.

Also closes the gap `pharmagpt/tenancy.py::signing_identity()` already documented in its own docstring: *"This app has no separate password-reentry or cryptographic signing step."* That function is untouched; the new e-signature layer sits alongside it as the step it described as missing.

## 2. Database schema

New table `qms_esignatures` (SQLite, `QMS_SCHEMA` in `pharmagpt/qms_database.py` — the same schema-definition location as every other QMS table, hooked into `pharmagpt/database.py::init_db()` exactly as it already was):

| Column | Captures |
|---|---|
| `user_id`, `full_name`, `role`, `department` | User ID, Full Name, Role, Department |
| `meaning` | Signature Meaning (fixed vocabulary — see §3) |
| `reason` | Reason for Signature |
| `signed_at_utc` | Date & Time (UTC) |
| `ip_address`, `user_agent` | IP Address, Device/Browser |
| `record_type`, `record_id`, `version_number` | Record Type, Record ID, Version Number |
| `old_status`, `new_status` | For audit-trail linkage |
| `approval_level` | Optional reference to the RBAC framework's `approval_levels` (see §6) |
| `reauth_method` | `password` today; `password+mfa` once MFA is wired in (see §8) |
| `signature_hash` | SHA-256 digest cryptographically linking the row to every field above (§4) |

**Immutable by omission**: no `update_esignature`/`delete_esignature` function exists anywhere in this codebase, and none should be added — covered by `tests/test_esignature_service.py::test_no_update_or_delete_function_exists_for_esignatures`. SQLite has no per-table grant system to enforce this at the database level (unlike the RBAC framework's Postgres `rbac_audit_log`, which has a grant-level guarantee) — immutability here is an application-level guarantee: no code path exists to mutate this table. Disclosed here, not silently assumed.

## 3. Signature meanings (fixed vocabulary)

`Created, Reviewed, Verified, Approved, Authorized, Released, Rejected, Cancelled` — not configurable per company, since these are the regulatory signature manifestations this framework is built around (21 CFR Part 11 §11.50).

## 4. Electronic Signature service — `pharmagpt/services/esignature_service.py`

The one common service every module calls. Two-phase, matching the reference integration:

1. **`require_esignature(tenant, password, meaning, reason)`** — call *before* performing the GMP decision. Validates the meaning/reason, then re-authenticates the password against Supabase Auth (`reauthenticate()`, a throwaway anonymous client — the resulting session is never stored or reused). Raises before anything is mutated if either check fails, so a bad password never lets a decision through and never leaves partial state.
2. **`record_signature(...)`** — call *after* the decision has succeeded, once old/new status are both known. Computes `signature_hash` (SHA-256 over every captured field, canonically ordered) and writes the immutable row, plus one audit-trail entry via the existing `pharmagpt/audit.py::log()` (unmodified).
3. **`verify_signature_integrity(row)`** — recomputes the hash from a stored row and compares; detects any post-write alteration of the signature row itself. Does not separately hash-chain each module's own business-record content (that would require touching every module's schema — out of scope for an additive layer, disclosed as a limitation, not silently assumed complete).

A logged-in session alone never satisfies step 1 — `require_esignature()` always re-verifies the password, independent of the bearer token already authenticating the request.

## 5. Reference integration (proof the common service works without redesigning workflow routing)

Wired into the three QMS modules whose `submit_approval` routes share the (already near-identical) status-transition pattern: `pharmagpt/routes/qms_documents.py`, `qms_capa.py`, `qms_change_control.py`. Each gets the same two-line addition — `require_esignature(...)` before the existing decision logic, `record_signature(...)` after it — with **zero changes to the workflow engine, status maps, or decision logic itself**.

Frontend: the shared `qmsRenderApproval`/`qmsSubmitApproval` helper (`pharmagpt/static/js/qms_common.js`) — used by every one of those modules' approval UI — now opens the new reusable `pharmagpt/static/js/esignature_dialog.js` dialog instead of the old plain typed-name/role fields. One shared JS change upgrades all three modules' UI at once.

**Not yet wired**: Deviation Management (which has migrated to its own dedicated workflow-builder UI, not the shared `qmsRenderApproval` path), Validation, IQ/OQ/PQ, Risk Assessment, Equipment Qualification, Training. The service and dialog are fully reusable for all of them — each needs the identical two-call pattern added to its own decision route, which is mechanical, low-risk, and deliberately deferred here to keep this phase's diff reviewable (see §8).

## 6. Multi-level approval / Approval Level field

Per instruction, workflow routing itself was **not** redesigned — the existing Workflow Engine (`pharmagpt/services/workflow_engine.py`) still owns sequencing, and single vs. multi-step approval chains are exactly as configured today. `qms_esignatures.approval_level` is an optional, purely informational field a caller may populate from the RBAC framework's `rbac_roles.approval_level_id` → `approval_levels` (migration `0015`) when the signer's role has one assigned, for traceability/reporting on which level signed. No new routing logic reads or enforces it.

## 7. Compliance mapping

| Requirement | 21 CFR Part 11 | EU GMP Annex 11 | ALCOA+ | How this framework addresses it |
|---|---|---|---|---|
| Signature identifies signer, meaning, date/time | §11.50 (signature manifestation) | Clause 14 (electronic signature) | Attributable, Contemporaneous | `user_id`/`full_name`/`role`/`meaning`/`signed_at_utc` captured server-side from the authenticated session — never client-supplied free text |
| Signature linked to its record, cannot be excised/copied | §11.70 (signature/record linking) | Clause 14 | Original, Accurate | `signature_hash` binds the row to `record_type`/`record_id`/`version_number`/`meaning`/`reason`/`old_status`/`new_status`/`signed_at_utc`; `verify_signature_integrity()` detects tampering |
| General controls (uniqueness, verification before use) | §11.100 | Clause 14 | Attributable | Non-spoofable identity from `TenantContext` (server-derived, matching the existing platform-wide discipline); one signature per decision |
| Two distinct identification components (ID + password) for each signing | §11.200(a)(1) | Clause 14 | — | Bearer-token session (already-established identity) **plus** a fresh password re-entry (`require_esignature`) — "a logged-in session alone must never approve GMP records" |
| Loss-management / non-repudiation controls | §11.300 | Clause 12 (security) | Attributable | Password re-verified against Supabase Auth on every signature; MFA is a defined extension point (`reauth_method`, `mfa_code` parameter), not yet enforced (see §8) |
| Audit trail of record changes, including who/what/when | §11.10(e) | Clause 9 (audit trails) | Attributable, Contemporaneous, Legible, Complete | Every signature writes one `pharmagpt/audit.py::log()` entry (old status → new status, reason, timestamp, non-spoofable actor) alongside the immutable signature row |
| Records retained, protected, retrievable | §11.10(c) | Clause 7 (data storage) | Enduring, Available | `qms_esignatures` is insert-only, indexed by `(record_type, record_id)`, retrievable via `GET /qms/<record_type>/<id>/esignatures` |

**WHO GMP / PIC/S**: both reference the same electronic-record/electronic-signature principles as Part 11/Annex 11 (attributable, contemporaneous, original, accurate records with a verifiable audit trail) rather than prescribing a distinct additional technical control — the mapping above satisfies the equivalent WHO Annex 5/PIC/S PI 011 expectations for computerized systems without a separate implementation.

**Assumption, not Confirmed**: this mapping reflects the well-established, commonly-cited structure of these regulations. The customer's Regulatory Affairs/QA function should verify against the current authoritative text of each regulation before relying on this mapping for an actual audit or inspection — this is engineering-level compliance-by-design, not a substitute for regulatory sign-off.

## 8. Authentication — re-authentication design

- **Password confirmation**: implemented (`reauthenticate()` re-verifies against Supabase Auth).
- **Session validation**: the existing bearer-token session must already be valid (via the untouched `require_auth`/`resolve_tenant_context`) before an e-signature attempt is even reachable — this is the "two distinct identification components" requirement (§11.200), not a redesign of session handling.
- **Future MFA compatibility**: `record_signature(..., mfa_code=None)` accepts and records an MFA code (`reauth_method` becomes `"password+mfa"`) but does not yet enforce one — reserved extension point, not a functioning MFA implementation. Flagged as a remaining recommendation, not silently claimed complete.

## 9. Files created / modified

**New:** `pharmagpt/services/esignature_service.py`, `pharmagpt/static/js/esignature_dialog.js`, `tests/test_esignature_service.py`, `docs/ESIGNATURE_FRAMEWORK.md` (this file).

**Edited (additive only):**
- `pharmagpt/qms_database.py` — new `qms_esignatures` table in `QMS_SCHEMA`, `add_esignature()`/`get_esignatures()` functions.
- `pharmagpt/routes/qms_common.py` — new `GET /qms/<record_type>/<id>/esignatures` read endpoint (mirrors the existing `.../approval` endpoint exactly).
- `pharmagpt/routes/qms_documents.py`, `qms_capa.py`, `qms_change_control.py` — each `submit_approval` gains the two-call e-signature gate.
- `pharmagpt/static/js/qms_common.js` — `qmsRenderApproval`/`qmsSubmitApproval` now open the reusable signature dialog instead of the old plain fields.
- `pharmagpt/templates/index.html` — one additive `<script>` include.

**Untouched:** `pharmagpt/auth/*` (authentication, RBAC), `pharmagpt/services/workflow_engine.py` (routing/status-transition logic), `pharmagpt/tenancy.py`, every other route, every migration from the RBAC framework, all frozen-role behavior.

## 10. Tests

`tests/test_esignature_service.py` — meaning/reason validation, re-authentication success/failure (mocked Supabase boundary), hash determinism and tamper detection, immutable row + audit entry written, and an explicit check that no update/delete function exists for the table. Existing `submit_approval` tests in `tests/test_qms_routes.py` (and any other file exercising those three endpoints) were updated to supply the new required `password`/`meaning`/`reason` fields — see the commit for the exact diff; this was a necessary, not incidental, API change per the explicit requirement that every such approval require a signature.

## 11. Remaining recommendations

- Wire the identical `require_esignature`/`record_signature` pair into Deviation Management's workflow-builder decision route, Validation/IQ-OQ-PQ, Risk Assessment, Equipment Qualification, and Training as each is ready — the service is already generic; this is mechanical, per-module follow-up.
- Populate `approval_level` from the signer's `rbac_roles.approval_level_id` once a module resolves that association for the acting user.
- Implement actual MFA verification behind the existing `mfa_code` parameter when the platform adds an MFA provider.
- The default seeded compliance mapping (§7) should be reviewed by the customer's QA/RA function before relying on it for an inspection.

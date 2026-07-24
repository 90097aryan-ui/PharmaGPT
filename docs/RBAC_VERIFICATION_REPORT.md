# RBAC Verification Report — Phase F, Work Package 4

**Scope:** Review every route for authentication, authorization, company isolation, and role-permission enforcement; attempt privilege-escalation analysis; verify against Viewer/Operator/QA/QA Manager/Admin/Super Admin.

## 1. Role model correction (carried forward from Phase E, re-verified here)

The roles named in the Phase F brief ("Viewer, Operator, QA, QA Manager, Admin, Super Admin") **do not exist in this codebase**. Verified directly again in this session against `pharmagpt/auth/decorators.py`, `migrations/0001_identity_tenancy_up.sql`, and every `@require_role(...)` call site. The actual, frozen role set is:

`super_admin` (role_id 1) | `company_admin` (role_id 2) | `reviewer_qa` (role_id 3) | `user` (role_id 4)

All findings below use these real names. Rough correspondence to the brief's terminology, for readability only (not an actual code mapping): `user` ≈ Viewer/Operator, `reviewer_qa` ≈ QA, `company_admin` ≈ QA Manager/Admin, `super_admin` ≈ Super Admin.

## 2. Authentication — verified

`pharmagpt/auth/middleware.py`'s `register_auth_middleware()` gates every route except an explicit exempt list (`/`, `/auth/login`, `/health`, `/favicon.ico`, `/static/*`). Re-confirmed live in Phase E (unauthenticated requests to `/equipment`, `/qms/dashboard`, `/dashboard/*`, `/qual/dashboard`, `/urs/dashboard` all returned 401 before login) and re-confirmed by direct code read in this session — no bypass found in either session.

## 3. Authorization gaps found and fixed in this work package (closes C7)

| # | Endpoint | Before | After |
|---|---|---|---|
| 1 | `POST /risk/assessments/<id>/publish` (`routes/risk.py`) | No role guard, no status check — any `user` could publish an assessment straight to the shared Risk Library, completely bypassing the role-gated "Approved" approval action that's supposed to be the only path there. | `@require_role("company_admin", "reviewer_qa")` added, plus a status check requiring the assessment to already be `Approved`. Blocked attempts are audit-logged. |
| 2 | `POST /qual/<id>/protocols/<pid>/complete` (`routes/qual.py`) | No role guard — any `user` could mark an IQ/OQ/PQ protocol (and, cascading, the parent qualification) complete. | `@require_role("company_admin", "reviewer_qa")` added. |
| 3 | `POST /qms/capa/actions/<aid>/escalate` (`routes/qms_capa.py`) | No role guard — any `user` could escalate a CAPA action. | `@require_role("company_admin", "reviewer_qa")` added. |

Every one of these three now carries the **same role tier as the canonical `/approval` endpoint of its own module** — the intended pattern already used consistently everywhere else in the codebase (create/generate is open to any authenticated user; delete and status-transition/approval actions require `company_admin` or `reviewer_qa`; only `super_admin`-exclusive routes like `/auth/companies` and `/companies/*` are further restricted). These three were the exceptions to that otherwise-consistent pattern.

## 4. Reviewed and deliberately NOT changed (documented, not overlooked)

| Endpoint(s) | Reasoning |
|---|---|
| `qms_documents.py` distribution/training add + acknowledge/update routes | These record routine, non-approval facts (a document was distributed to someone; a training was completed) rather than a QA sign-off or status transition. Locking these to `company_admin`/`reviewer_qa` without evidence of the intended business rule risks breaking a legitimate workflow (e.g. a `user` acknowledging their own training) that this session cannot verify against a live, credentialed session (see the disclosed methodology limit in `PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md` §0). Left open; flagged for a product-owner decision rather than guessed at. |
| `qms_documents.py /generate`, `qual.py /generate` (test cases), `report.py /generate` and `/generate/<section>`, `risk.py /generate`, `urs.py /generate` | AI **content generation** is open to any authenticated user across every module in this codebase, consistently — this is the established, deliberate pattern (generation ≠ approval), not a gap specific to one module. Audit logging was added to these events in Work Package 2 (`docs/AUDIT_TRAIL_COVERAGE_REPORT.md`) so generation is now at least attributable, even though it isn't role-gated. |

## 5. Company isolation — cross-reference

Every route reviewed in this work package resolves its scoping company_id from `g.tenant.company_id` (server-derived from the authenticated session), never from client input. Full findings are in `docs/MULTI_TENANT_SECURITY_REPORT.md` (Work Package 5) rather than duplicated here.

## 6. Privilege-escalation analysis

**Method used:** static analysis of every `@require_role(...)` decorator against every mutating route, cross-checked against what each route actually does (does the action's real-world consequence match its guard's strictness) — the same method that surfaced the three fixes in §3. This is the same approach the Phase E audit used and that this session independently re-derived rather than trusted.

**Live escalation attempts (e.g. logging in as `user` and calling a `reviewer_qa`-gated endpoint directly) were NOT performed in this session.** This requires an authenticated session, and per the disclosed hard constraint (`PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md` §0), this environment does not enter credentials — including this application's own test credentials — into any login field, live or automated-browser.

**Automated `pytest`-level privilege-escalation tests were added instead**, using the repo's existing mocked-`TenantContext` pattern (patches `resolve_tenant_context`, never touches a real credential — the same pattern `tests/test_security_tenant_rbac_esig.py` already established and this session reused, not invented). `tests/test_phase_f_compliance.py` directly exercises all three fixes in §3: a `user`-role tenant attempting each of the three previously-unguarded endpoints now gets a real, asserted 403 from the real route code; a `reviewer_qa`-role control case confirms the block is role-specific, not a general failure (`test_reviewer_qa_can_complete_qualification_protocol`, asserting 200). All four tests pass. This is real verification against actual route/decorator behavior, not source-reading alone — the strongest form of proof available without live credentials.

**Explicitly re-checked and confirmed safe (no change needed):**
- No route accepts `company_id` or `role` from the request body/query/header and uses it for an authorization decision — confirmed by grep across every route file, consistent with Phase E's finding.
- `routes/companies.py::suspend_company`/`reactivate_company` take `company_id` from the URL path under a `super_admin`-only guard — a legitimate target-resource id, not an identity/role field being trusted for authorization.
- `routes/users.py`'s `role_id` update path rejects `role_id=1` (super_admin) before it reaches Postgres, in addition to the database-level trigger — a company_admin or assumed-context super_admin cannot self-escalate or escalate another user to super_admin through this route.

## 7. Verification performed

- Every fix in §3 is a direct, cited code change.
- `from pharmagpt.app import app` re-verified after each edit.
- **4 new automated tests** in `tests/test_phase_f_compliance.py` directly assert the RBAC fixes in §3 (3 blocking, 1 control case) against the real app — all passing.
- Full `pytest` suite re-run (514 tests total) — see `docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md`.
- Live credentialed privilege-escalation testing: **NOT PERFORMED**, disclosed limitation, not silently skipped.

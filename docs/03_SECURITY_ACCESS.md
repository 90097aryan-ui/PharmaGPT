# 03 — Security & Access

**Document:** Yuktav / PharmaGPT — Security & Access
**Purpose:** Define who can access what and how it is enforced. Every control below is explicitly classified as one of: **UI restriction**, **backend authorization**, or **database/RLS enforcement**. A frontend restriction is never described as a security control on its own.
**Status:** Active
**Last reviewed:** 2026-08-23
**Source of truth / authority:** Code (`pharmagpt/auth/`, `pharmagpt/routes/`) is authoritative for what is enforced today. `docs/RBAC_FRAMEWORK.md`, `docs/ESIGNATURE_FRAMEWORK.md` describe additional capability that exists in code but whose merge/deploy status relative to `main` is unconfirmed (§14).
**Known limitations:** No live access to the deployed Supabase project — RLS policy *existence in migration files* is confirmed; RLS policy *active enforcement in production* is not.

---

## 1. Authentication

**CONFIRMED — backend enforcement.** Supabase Auth bearer tokens, verified server-side on every request via `client.auth.get_user()` (`pharmagpt/auth/context.py:49`). The app never validates a JWT locally against a secret — Supabase Auth is the sole authority on validity/expiry/revocation. A global `before_request` gate (`pharmagpt/auth/middleware.py:181-223`) applies to every route except `/`, `/auth/login`, `/health`, `/favicon.ico`, `/static/*`.

A signed, HttpOnly session cookie mirrors the token for header-less navigations (e.g. `<a download>` links); a present Authorization header always takes precedence when both exist.

**"Assume Company Context" (break-glass):** a `super_admin` may temporarily assume one company's context via a logged, time-boxed `break_glass_access` grant, re-verified on every request. It never elevates the acting role — a super_admin assuming a company still acts as super_admin, scoped to that company's data.

## 2. Authorization Model — Two Independent Layers

Both are real backend checks; neither is UI-only.

**Layer 1 — Frozen 4-role model (CONFIRMED, in active use):** `require_auth` (sets `g.tenant`) and `require_role(*roles)` (`pharmagpt/auth/decorators.py:61-85`) — returns 403 if `g.tenant.role` is not in the allowed set. Roles: `super_admin | company_admin | reviewer_qa | user`. Used across 42+ route call sites.

**Layer 2 — Fine-grained RBAC (CONFIRMED in code, LIMITED in current use):** `has_permission(tenant, module, action)` / `require_permission(module, action)` (`pharmagpt/auth/rbac.py:81-119`) — 15 modules × 8 actions, per-company-configurable roles resolved through `rbac_user_roles → rbac_roles → rbac_role_permissions`. **Currently used only by `/rbac/*` and `/org/*` administration routes.** No business route (Document Control, Deviations, CAPA, etc.) checks fine-grained RBAC permissions today.

**CONFLICT / REQUIRES DECISION:** `docs/RBAC_FRAMEWORK.md` and `docs/ESIGNATURE_FRAMEWORK.md` both state, as authored, that their branches were "not merged into `main`, not deployed." Current work is on `feature/document-control-redesign`. Whether these have since merged to `main` / reached production was **not independently re-verified** — confirm before treating the 21-role RBAC layer or e-signature as live in production.

## 3. Tenant Isolation

**CONFIRMED — backend (application-layer) enforcement, not database-layer, for SQLite-resident data.** `g.tenant.company_id` is resolved server-side only (never from client input) and threaded through every route via `pharmagpt/tenancy.py::scoped_or_none()` (single-record lookups return 404, not 403, closing an enumeration side-channel) or an explicit `company_id` filter. Confirmed present on: `projects, kb_documents, risk_assessments, risk_library, urs_projects, qual_qualifications, val_reports, qms_documents, qms_deviations, qms_capas, qms_change_controls`. `equipment` is scoped via its owning Project's `company_id` (join, no own column).

**Gap, disclosed not fixed:** shared polymorphic tables `qms_attachments`/`qms_comments`/`qms_audit_trail`/`qms_approvals` carry no `company_id` of their own — isolation depends entirely on `qms_common.py::_record_exists()` re-validating the parent record's company on every access.

**Gap, disclosed not fixed, low severity:** `review_engine.py::_score_cache` is a process-global, non-tenant-keyed in-memory dictionary backing one dashboard tile — a cross-company statistical bleed, not a record-level leak.

**NOT VERIFIED LIVE:** a two-company RLS isolation spot-check against the deployed Supabase project has never been performed; whether the `CREATE POLICY`/GRANT statements in migrations 0010–0012 are active in the live project is unconfirmed.

## 4. Roles (exact code strings)

| Role | Scope | Notes |
|---|---|---|
| `super_admin` | Platform-wide | No standing access to any company's data; may Assume Company Context (logged, time-boxed) |
| `company_admin` | Own company, full authority | |
| `reviewer_qa` | Own company | Gated for approval / status-transition / Document Control release endpoints alongside `company_admin` |
| `user` | Own company, default | Blocked from delete, approval, and status-transition actions |

**PROPOSED, not wired to business routes:** 21 additional role templates (Platform Admin, Plant Head, QA/QC/Validation/Production/Engineering/Warehouse/EHS Managers+Officers, Regulatory Manager, Auditor, Viewer) exist in the fine-grained RBAC layer (§2, Layer 2) but govern only `/rbac` and `/org` administration surfaces today.

## 5. Document Control Permissions

Enforcement here is **named-user-id-based**, not role-based, for the core review/approval decisions — and it is real backend enforcement, with one disclosed gap.

| Action | Who (UI) | Backend enforcement | Classification |
|---|---|---|---|
| Assign review/approval chain | Author (by convention) | `set_review_chain` rejects (409) unless current version status is `draft`. **No server-side check restricts *who* may call this endpoint** — only *when*. | **Gap: state enforced server-side; identity (Author-only) is UI convention only.** |
| Submit for Review | Author | Hard-blocked (409) unless: Author Self-Check done, Final Author Version uploaded, chain complete (Reviewer + Department Head + Quality Head) | Backend enforcement |
| Reviewer / Dept Head / Quality Head / Plant Head decision | Assigned individual | `workflow_engine.py::decide_step` checks the deciding `user_id` against `get_step_approvers(step)` — 403 if not an assigned approver for that step | Backend enforcement (named-user match, not role match) |
| Mid-workflow reassignment | — | Hard-disabled for Document Control regardless of role (always 403) | Backend enforcement |
| Release to Effective ("Quality Release") | company_admin / reviewer_qa | `@require_role("company_admin", "reviewer_qa")` | Backend enforcement (route-level role gate) |
| Create template / delete document / configure Approver Pool defaults | company_admin | `@require_role("company_admin")` | Backend enforcement |

**Flag for closure or explicit acceptance:** the `assign-chain` endpoint's lack of a server-side identity check on *who* may set the chain is a real, previously undocumented gap surfaced by this review — recommend a decision (add a check, or explicitly accept the risk given Draft-only + same-company constraints).

**Note:** the "decide workflow step" route itself carries no `@require_role` — the coarse gate is "any authenticated session in the company"; the fine-grained named-approver check lives inside `workflow_engine.py`. This is a disclosed, deliberate design (`docs/ESIGNATURE_MODULE_INTEGRATION.md`), not an oversight.

## 6. Admin / Super-Admin Permissions

`super_admin` reaches the Administration module only via `has_permission()`, and only when acting with `company_id = None` — no standing access to tenant business data. Role elevation to `super_admin` via a role-ID update is blocked at the database layer. `security_admin.py` (configuration/hardening dashboard) is `@require_role("super_admin")`-only, read-only, and never returns secret values — only status (present / weak / default).

## 7. API Security Coverage

**CONFIRMED.** The global middleware gates every non-exempt route regardless of per-route decorators — authentication is always applied first. A prior audit found and fixed three previously-unguarded mutating endpoints (risk publish, protocol-complete, CAPA-escalate); all three are now role-gated and test-covered.

**Deliberately left unguarded (disclosed, not an oversight):** Document Control's distribution/training routes, and every `/generate` (AI content draft) endpoint platform-wide — the consistent rule is "generation is not a business decision, approval is," so generation endpoints intentionally do not carry approval-level role gates.

## 8. RLS — Current Coverage Map

**Do not treat "RLS exists in this repository" as a blanket security control.** RLS policies exist in migration files for:

| Table group | RLS status (per migration) |
|---|---|
| Identity: `users`, `companies`, `break_glass_access` | Policy defined (migrations 0010–0012) |
| Knowledge Base "Document Engine" (`documents`, `document_versions`, `document_categories`, `tags`, `document_tags`) | Policy defined (migration 0006) — **this is a separate Postgres schema from the SQLite `kb_documents` table actually driving the Knowledge Base feature today** |
| Equipment (Postgres side) | Policy defined (migration 0007) |
| Deviations / CAPA / Change Control / Risk Assessments (Postgres dual-write side) | Policy defined (migration 0008) |
| RBAC tables (`rbac_roles`, `rbac_role_permissions`, `rbac_user_roles`, `rbac_audit_log`) | Policy defined (migration 0015); `rbac_audit_log` is select-only, no client write grant at all |

**Gap, CONFIRMED:** the actual Document Control module (`qms_documents` and related tables) — the Author/Reviewer/Department Head/Quality Head/Plant Head workflow described throughout this doc set — is **SQLite-backed with no RLS whatsoever**. Isolation there is 100% application-layer (§3). Most other day-to-day QMS behavior is in the same position, since the corresponding `QMS_BACKEND` dual-write flag is unset (see [02 §5](02_TECHNICAL_ARCHITECTURE.md)).

**NOT VERIFIED LIVE:** whether any of the migration-file RLS policies above are actually active against the deployed Supabase project has never been confirmed by a live session.

## 9. Audit Trail

**CONFIRMED.** Shared writer `pharmagpt/audit.py::log()` derives `performed_by` and `company_id` from `g.tenant` only — never from client-supplied fields — and stores diff-based `old_values`/`new_values` (with `password`/`electronic_sig`/`access_token` redacted), `ip_address`, `session_id`, and `result`. Covers create/update/delete/approval across all major SQLite QMS domains. Identity-spoofing was previously possible at 8 call sites and has been fixed (actor identity is now always server-derived).

**Tamper-evidence:** audit rows carry no cryptographic seal of their own (unlike e-signature records, §10) — integrity relies on no code path existing to update them, except for the Postgres `rbac_audit_log`, which has a real database-level select-only grant.

**Known limitation:** Postgres-side audit writes for Users/Companies are best-effort (wrapped in try/except) and have not been confirmed to land rows in the live database.

## 10. E-Signature

**CONFIRMED, implementation exists and is wired in.** `pharmagpt/services/esignature_service.py::require_esignature()` re-authenticates the acting user's password against Supabase Auth, independent of the existing bearer session. `record_signature()` computes a SHA-256 hash over signer/record/decision fields and is immutable by omission — no update/delete function exists for signature records, and this is test-covered.

Wired into every GMP decision endpoint found in the codebase: Document Control, CAPA, Change Control, Deviation, Qualification (IQ/OQ/PQ), Risk Assessment, Validation Reports, and Training completion — including a prior gap where the newer Workflow Panel decision path had not been gated, since closed.

**Explicitly not covered (no such endpoint/module exists to integrate):** Equipment Release, Batch Record Review/Approval.

**Reserved, not enforced:** a multi-factor re-authentication field (`reauth_method`) exists in the schema but MFA itself is not enforced — an acknowledged remaining item, not claimed as complete.

**See §2 conflict** regarding whether this framework's branch has merged to `main`/production.

## 11. File / Document Access Control

**CONFIRMED.** Every export/download endpoint (URS, Qualification, Validation Report, QMS Document DOCX/PDF) fetches its source document through a company-scoped getter before generating the output file — no bypass found. Attachment/comment access is gated by the same `_record_exists()` parent-record company check described in §3.

## 12. Environment Secrets Handling

**CONFIRMED (mechanism only — no values inspected or reproduced here).** `.env` is loaded via `python-dotenv`. `_require_env()` in `pharmagpt/services/supabase_client.py` raises only when a Supabase-backed code path actually executes, not at import — allowing the app to boot SQLite-only with no Supabase configuration present. Three Supabase client tiers exist: anon-key user-scoped (RLS-evaluated), anon-key anonymous (login/re-auth only), and service-role (RLS-bypassing, restricted to the identity-admin user-creation path). `security_config.py` exposes only startup-secret **status** (present / weak / default) to `super_admin`, never actual values.

## 13. Known Security Limitations (explicitly admitted, not inferred)

1. Live two-company RLS isolation has never been spot-checked against the deployed Supabase project.
2. Company Administration / User Management / Assume Company Context: RLS grants from migrations 0010–0012 are unconfirmed active in production.
3. `_score_cache` dashboard tile is process-global, not tenant-scoped (disclosed, low severity, not fixed).
4. CAPA / Change Control have no full arbitrary-transition lifecycle guard beyond terminal-state immutability.
5. Postgres Users/Companies audit writes are best-effort and unverified live.
6. Raw exception text can leak on some error paths (open, out of scope for this review).
7. No audit-log viewer exists for break-glass grants.
8. Document Control's `assign-chain` endpoint has no server-side role/identity restriction on *who* may set the chain — only *when* (Draft-only). New finding from this review; not previously documented.

## 14. Open Questions / Conflicts

1. **Branch/deploy status of RBAC and e-signature frameworks** — both source documents state "not merged, not deployed" as authored; current branch and later commits suggest more may have landed since. **Requires confirmation** before either is described as live in production anywhere in this doc set or externally.
2. **RLS terminology conflict** — "RLS exists in this repo" (true, for specific Postgres tables) must never be generalized to "the application is RLS-protected" (false — the SQLite-backed data driving most day-to-day behavior, including all of Document Control, has zero RLS and relies entirely on application-layer tenant filtering).
3. **`assign-chain` identity gap (§5, §13.8)** — needs an explicit decision: close the gap or formally accept the risk.

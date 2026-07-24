# PharmaGPT v1.0 — Release Readiness Report

**Phase:** E — End-to-End Validation & Release Readiness
**Audit date:** 2026-07-24
**Audit type:** Independent inspection, verification, and testing. No code, configuration, or architecture was changed as part of this audit (per Phase E rules).
**Audited against:** ALD-001-R1 (locked navigation/architecture), the 15-step validation workflow, and GAMP5 / USFDA 21 CFR Part 11 / EU GMP Annex 11 / Annex 15 / MHRA expectations for a computerized validation/QMS platform.

---

## 0. Methodology & Constraints

This audit combined four independent verification streams:

1. **Synthesis of prior self-authored assessments** — every existing report in the repo (`ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`, `FUNCTIONAL_VALIDATION_REPORT.md`, `SECURITY_REVIEW.md`, `PERFORMANCE_REPORT.md`, `ARCHITECTURE_REVIEW.md`, `DEPLOYMENT_REVIEW.md`, `SQLITE_AUDIT_REPORT.md`, the five `PHASE_N_IMPLEMENTATION_REPORT.md` documents, and the `docs/` folder) was read in full, dated, and cross-checked for contradictions. These are prior sessions' claims, not independently verified fact — treated accordingly.
2. **Independent source-code verification** — RBAC/permission enforcement, audit-trail completeness, and the document lifecycle state machine were re-derived directly from the current working tree (not from what prior reports claimed), with file:line citations.
3. **Independent workflow trace** — the full Login → Project → Equipment → URS → DQ/FAT/SAT → IQ/OQ/PQ → Validation Report → Approval → Effective → Audit Trail chain was traced through actual route code, separately from the RBAC/audit-trail pass.
4. **Live verification** — the Flask dev server was started and the running application inspected directly (DOM structure, error pages, unauthenticated behavior, network responses, error-handler source), plus a fresh full run of the `pytest` suite.

**Hard constraint disclosed up front:** per this environment's safety rules, credentials are never entered into any login field — including this application's own test/dev credentials. This means **authenticated live UI testing of the workflow was not possible in this audit**; authenticated-path behavior was verified through direct source-code inspection instead (stream 2/3 above), which is generally a stronger form of verification for logic correctness but cannot substitute for a live click-through. This is a genuine methodology gap the release owner should close with a manual, credentialed walkthrough before sign-off, particularly for the items in §4 below.

A fresh full `pytest` run was executed independently as part of this audit and completed: **500 passed, 1 deselected, 21 warnings in 248.12s** — this exactly matches the count in the most recent prior report (`ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`, 2026-07-23), independently confirming the suite is still green and that count is current, not stale. The acceptance test's own caveat still applies, however: every test mocks the Supabase client, so this suite would not have caught (and did not catch) the live-database GRANT failure behind C1 below, nor would it catch most of the gaps this audit found by direct source reading (C2-C7) since those are missing checks, not regressions a mocked-client test would exercise.

---

## 1. Overall Readiness Score

# **52%**

**Rationale:** The core validation-record engineering (URS, Qualification, Risk, Validation Report, QMS Document Control) is genuinely substantial and mostly sound — real lifecycle state machines, real e-signature capture on primary approval paths, real tenant scoping, a 500-test suite passing. But a v1.0 release of a pharmaceutical validation/QMS platform is judged against GxP control expectations, not just "does the feature work," and this audit found:

- The platform's own most recent formal acceptance test (`ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`, same day) already concluded **NO-GO** for Company Administration and Assume Company Context, and that verdict was never re-tested to a clean GO before later UI work proceeded.
- Independently, this audit found the audit trail — a foundational 21 CFR Part 11 control — is structurally incomplete (no old/new-value capture, no company_id on audit rows, and most PUT/DELETE actions across QMS/URS/Qualification/Report/Risk are never audited at all).
- Independently, this audit found the qualification sequencing (IQ before OQ before PQ) and the Validation Report's dependency on completed qualification evidence are **not enforced anywhere server-side** — a validation package could legally (in software terms) be released without its underlying evidence existing.

Any one of these three would be a serious finding for a GxP system; together they are release-blocking. The score reflects "a strong beta with real architecture" rather than "compliant v1.0."

---

## 2. Workflow Verification (15-step chain)

Traced directly through route source code (`pharmagpt/routes/*.py`) and cross-checked against the live running app's DOM/nav.

| # | Step | Navigation | Required fields | Status transitions | Error handling | Audit trail | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Company Login | ✅ live login screen confirmed | ✅ email+password server-required (`auth.py:74`) | N/A (session) | ✅ 401 invalid creds, 403 no profile (`auth.py:83-96`) | N/A | **Full** |
| 2 | Create Validation Project | ✅ Validation Suite → Projects | ✅ `name` required (`projects.py:121-123`); other fields unvalidated (e.g. target_date not date-checked) | ⚠ no governed lifecycle — status freely settable via PUT (`projects.py:175`) | ✅ 400 missing name | ✅ create/update/delete all audited (`projects.py:143,182,194`) — the **one** fully-audited domain | **Full, minor gap** |
| 3 | Assign Equipment | ✅ Project Workspace → Equipment | ✅ `name` required (`equipment.py:178-179`) | N/A (data record) | ✅ 404 project not found, tenant-checked unlink | ❌ **no audit calls anywhere in equipment.py** | **Partial** (works, unaudited) |
| 4 | Create URS | ✅ | ✅ title/equipment_name required; `prepared_by` server-derived, not spoofable (`urs.py:136`) | ✅ starts Draft | ✅ 400 on missing fields | ❌ create not audited; only approval transitions are | **Full mechanically, audit gap** |
| 5 | Review URS | ✅ | ✅ requires existing requirements (400 if none) | ✅ → Under Review, validated via `urs_lifecycle.validate_transition`, 409 on illegal jump | ✅ AI failure → 502, prior review preserved on failure | ✅ (review action logged) | **Full** |
| 6 | Approve URS | ✅ | ✅ `action` required, `performed_by` server-derived | ✅ full state machine, revision auto-bump on rework | ✅ 409 illegal transition | ✅ | **Full** |
| 7-9 | Generate DQ / FAT / SAT | ✅ (via QMS Document Control, not a dedicated screen) | ✅ `title` only; **no equipment/qualification linkage field exists in schema** | ✅ generic QMS_DOCUMENT lifecycle | ✅ 400/409 | ❌ generation event itself not audited | **Partial** — see Critical/High findings |
| 10-12 | Perform IQ / OQ / PQ | ✅ Qualification module | ✅ `protocol_type` enum-checked; pending test cases block completion unless forced | ⚠ parent Qualification status is guarded; **individual protocol status is not, and no check that IQ exists/completed before OQ/PQ** | ✅ failed test case can auto-open deviation | ❌ test-case generation not audited | **Partial — sequencing not enforced (Critical)** |
| 13 | Validation Report | ✅ | ⚠ only a resolvable title required; **linkage to Qualification is optional, no completeness check** | ✅ 6-state lifecycle guarded | ✅ 404/409 | ✅ approval actions audited (only audited action in file) | **Partial — no dependency gate (Critical)** |
| 14 | Approval (cross-module) | ✅ | ✅ role-gated, e-signature captured | ✅ | ✅ | ✅ | **Full** |
| 15 | Effective | ✅ | — | ✅ reached via module-specific terminal states; naming inconsistent (Effective / Approved+Closed / Released) but functionally equivalent, each auto-publishes to Knowledge Base | — | ✅ | **Full, cosmetic naming inconsistency** |
| — | Audit Trail (cross-cutting) | ✅ viewer exists per record | — | — | — | ⚠ infrastructure real, **inconsistently invoked** (see Critical #4/#5) | **Partial** |

**No step in the chain is a missing/non-functional stub** — every step has a real route, real persistence, and a real frontend entry point. The material risk is not "it doesn't work," it's "it doesn't stop you from doing it in the wrong order or without a full record" — exactly the class of finding a GAMP5/FDA/MHRA/EU GMP Annex 15 auditor is trained to look for.

---

## 3. Module Verification

| Module | State |
|---|---|
| Validation Suite (Dashboard/Projects/Workspace) | Functional. Live-nav-verified structure matches the locked hierarchy. |
| URS | Fully built: auto-numbering, AI generation as background job, review scoring, full lifecycle + e-signature, DOCX export, manual versioning. |
| DQ / FAT / SAT | Reachable via generic QMS Document Control, **not** their own dedicated flow; **dead code** — purpose-built `dq_prompt.py`/`fat_prompt.py`/`sat_prompt.py` exist but are never called (generic SOP template used instead); no schema link to Equipment/Qualification. |
| Qualification (IQ/OQ/PQ) | Functional generation/execution/completion; protocol-type-specific AI prompts genuinely used (unlike DQ/FAT/SAT); **no cross-protocol sequencing gate**. |
| Validation Report | Functional SSE section generation, full lifecycle; **no gate against incomplete underlying qualification**. |
| Quality Management (Deviations, CAPA, Change Control, Document Control) | Functional; CAPA and Change Control **do not use the lifecycle engine at all** — status is unguarded free-form in these two modules specifically. |
| Knowledge Base | Functional; versioned; auto-publish from 4 approval routes confirmed. |
| Equipment Library | Functional as a company-wide list view, but underlying data model is still project-owned (`project_id NOT NULL`), not the target company-owned many-to-many model — architecturally incomplete relative to roadmap, not broken. |
| Risk Management | Functional; e-signature gap on approval was previously found and fixed; **`/publish` endpoint bypasses the role-gated approval action with no guard** (see Critical #7); underlying `risk_database.py` leaks a SQLite connection in all 15 functions. |
| Document Generator | Old generic wizard's duplicate doc types retired; remaining scope narrowing (`docs/ARCHITECTURE_LOCK.md`) is a locked *draft*, explicitly "pending sign-off... does not authorize implementation" — not built, and should not be assumed built. |
| Administration (Companies/Users/Roles) | **Built but non-functional in the live database** — see Critical #1. This is the single highest-severity finding in this report. |
| Training / Complaints / Audit Management / Supplier Quality / Management Review | Confirmed via live DOM read: explicitly labeled **"(Coming Soon)"** — correctly represented as not-yet-built, not a hidden gap. |
| PharmaPilot / AI Assistant | Live workspace-chooser tile explicitly labeled **"Enterprise AI Assistant (placeholder only)."** The separate AI Assistant chat (Gemini-backed) is functional; "PharmaPilot" as its own branded capability is not. |

---

## 4. Multi-Tenant Verification

**Not independently re-verified live** in this audit (would require two distinct authenticated company sessions, blocked by the credential-entry constraint in §0). Findings are from direct source review:

- Application-layer scoping (`g.tenant.company_id`, never a client-supplied value, funneled through `tenancy.scoped_or_none()`) is used consistently across all routes checked — no route was found trusting a client-supplied `company_id` or role. `scoped_or_none()` deliberately returns 404 rather than 403 on a cross-tenant record reference, preventing existence-enumeration — good design.
- This is application-code-level enforcement only on the currently-live SQLite path — the SQLite schema itself has no `company_id` columns (confirmed by multiple prior reports and not contradicted by this audit's source review), so there is no database-level backstop equivalent to the Postgres side's RLS. A regression in the application-layer check would have nothing to catch it.
- The Postgres/Supabase schema (for the eventual cutover) does have RLS + matching policies on all Phase 3.2–3.5 tables per `docs/` migrations — but the **live 2-company RLS isolation spot-check and extended Staging soak required before cutover have still not been performed**, per `docs/PHASE3_FLAGS.md`/`docs/MIGRATION.md`, and this audit found no later document overriding that.
- **Recommendation:** before any claim of "multi-tenant verified," perform a live spot-check with two real company accounts (owner-provided credentials, entered by the owner — not by this audit) exercising cross-company access attempts against both the SQLite and (if enabled) Postgres paths.

---

## 5. Role-Based Access Control (RBAC) Testing

**Correction to the requested role set:** the roles named in the Phase E brief ("Administrator, QA Manager, Validation Engineer, Reviewer, Approver, Read Only") do not exist in the code. The actual, implemented role set is:

`super_admin` | `company_admin` | `reviewer_qa` | `user`

Testing against the roles that actually exist:

- `super_admin` — correctly restricted to `/auth/companies`, `/auth/assume-company`, platform administration; has **no standing tenant data access** by design (a real, verified security control) — but the only sanctioned path for legitimate tenant support (Assume Company Context) is itself broken (Critical #1), leaving no working support path at all currently.
- `company_admin` / `reviewer_qa` — correctly gated on `DELETE` and the canonical `/approval` transition endpoint across every QMS/URS/Qualification/Report module checked.
- `user` — correctly blocked from delete/approval as designed, **but** can reach several state-changing endpoints that should plausibly require `reviewer_qa`/`company_admin`: risk assessment publish, qualification protocol completion, CAPA action escalation, QMS document distribution/training records (Critical #7). This was not caught by the existing test suite's RBAC tests, which focus on the canonical delete/approval endpoints.
- Live-verified: unauthenticated requests to protected endpoints correctly return 401 (confirmed via dev-server request log: `/equipment`, `/qms/dashboard`, `/dashboard/*`, `/qual/dashboard`, `/urs/dashboard` all 401 before login).

---

## 6. Document Lifecycle Verification

Target spec: **Draft → Under Review → Approved → Effective → Obsolete → Archived**

| Record type | Actual states | Gap vs. spec |
|---|---|---|
| QMS Document | Draft, Under Review, Pending Approval, Effective, Under Revision, Obsolete | No distinct "Approved" (collapsed into the Effective transition); **no Archived state at all** (Obsolete is terminal) |
| URS | draft, under_review, pending_approval, approved, effective, obsolete | Closest match (5/6); **no Archived state** |
| Validation Report | draft, under_review, approved, released, archived, obsolete | All 6 conceptually present ("released" = Effective), **but a Released→Obsolete shortcut is legal, bypassing Archived** |
| CAPA / Change Control | free-form, module-specific | **No lifecycle-engine guard at all** — any status can follow any status |

Transitions that *are* guarded (Document, URS, Qualification, Report, Risk) correctly reject illegal jumps with HTTP 409 and correctly capture an e-signature-style `performed_by`/`role`/`electronic_sig` at each transition — this part of the engineering is solid. The gaps are in vocabulary completeness (missing Archived) and in the two modules with no guard at all.

---

## 7. Audit Trail Verification

Target spec: every critical action produces **Timestamp, User, Company, Old Value, New Value, Action**.

**What exists:** a real, shared `add_audit_entry()` helper (`qms_database.py:481-491`) writing `record_type, record_id, action, detail, performed_by, created_at` to `qms_audit_trail`, plus per-module approval tables. This infrastructure is genuinely used for creation and approval-transition events in most modules.

**What's missing against the spec, confirmed by direct code inspection:**

1. **No Old Value / New Value columns anywhere** — only a free-text `detail` string, populated inconsistently (e.g. version bumps get `"1.0 -> 2.0"`, ordinary field edits get nothing).
2. **No Company column on any audit-trail or approval table** — tenant-scoping of audit rows is indirect (via the parent record) rather than a first-class field.
3. **PUT (update) and DELETE are unaudited in every domain except `projects.py`** — confirmed via direct grep of every route file: `qms_documents.py`, `qms_deviations.py`, `qms_capa.py`, `qms_change_control.py`, `urs.py`, `qual.py`, `report.py`, `risk.py`, `equipment.py` all create-audit but never update/delete-audit.
4. **AI-generated content changes are never audited** anywhere (`qms_documents.py` draft generation, `report.py` section generation, `qual.py` test-case generation, `risk.py` item generation, `urs.py`'s background job is the one exception that does log generation start/finish).
5. **Identity spoofing survives in specific, non-canonical endpoints** even though the codebase has an established server-side-derivation fix (`tenancy.signing_identity()`) applied correctly to every module's main `/approval` endpoint: attachment upload and comment authorship (`qms_common.py`), qualification protocol completion's e-signature field (`qual.py:477`), and version-snapshot `created_by` (`qual.py`, `urs.py`, `report.py`) all still accept a client-supplied identity string.

This is, in aggregate, the most significant structural gap found by this audit independent of the pre-existing NO-GO — unaudited deletion of a GxP record (a Deviation, CAPA, Change Control, Document, Qualification, or Validation Report) is a fundamental 21 CFR Part 11 / Annex 11 control failure, not a cosmetic one.

---

## 8. Performance

No later report claims any of `PERFORMANCE_REPORT.md`'s (2026-07-21) findings were fixed; treated as still current, not independently re-benchmarked live in this audit (would require authenticated load generation).

- Postgres schema well-indexed (`company_id` + composite indexes throughout); legacy SQLite path has almost no secondary indexes outside equipment/QMS — most filtered lookups are full table scans (Medium, not yet visible at pilot scale).
- `risk_database.py` leaks a SQLite connection in all 15 functions (High).
- Auth/tenant resolution costs 2 uncached network round trips per request (High, highest-leverage fix available per the source report).
- 6 of 7 AI-generation endpoints stream synchronously in-request against `--workers=2 --threads=4` — the same pattern that already caused production WORKER TIMEOUT crashes for URS before it alone was fixed (High).
- One confirmed N+1 pattern in `equipment_database.py::list_equipment_documents()` (Low-Medium).
- No connection pooling for Supabase/Postgres (fresh client per call) — deliberate to avoid cross-request session bleed, but zero reuse (Medium).
- Most recent real timing data available (`docs/URS_STABILIZATION_ITERATION4_VALIDATION_REPORT.md`, 2026-07-13): login ~3.1s, dashboard loads 545-851ms, DOCX generation 2.64s/13-requirement doc, approvals 725ms-1.08s. No fresher numbers exist in the repo.

---

## 9. Security

- **Cross-tenant IDOR (previously Critical):** fixed by commit `aa15c66` (2026-07-21); confirmed by this audit's own independent source read that `g.tenant.company_id`-derived scoping is now pervasive. `SECURITY_REVIEW.md`'s Critical finding on this topic is **stale and should not be cited as current state** without this caveat.
- **QMS creation-time and approval-time e-signature spoofing (previously Critical):** fixed and regression-tested per `PHASE_1_IMPLEMENTATION_REPORT.md`. This audit found the fix was **not propagated everywhere** — see §7 item 5 above (attachments, comments, protocol completion, version snapshots).
- **Session/auth mechanism:** credentials are never stored or compared by this application — delegated entirely to Supabase Auth (`sign_in_with_password`); confirmed by direct read of `routes/auth.py`. A signed, HttpOnly Flask session cookie mirrors the access token solely to support non-fetch browser navigations (e.g. DOCX download links) — a deliberate, narrow, and reasonable design.
- **Postgres GRANTs for the 0010-0012 identity/admin migrations not active in the live database** — root cause of Critical #1; this is a security-relevant availability/access-control failure (Super Admin's only sanctioned support path is broken), not just a feature bug.
- **`FLASK_SECRET_KEY` hardcoded insecure fallback** still present at `pharmagpt/config.py:15` (Medium) — mitigated only because Render's dashboard auto-generates the real value in production; the code-level footgun was never removed.
- **No content/magic-byte file-upload validation** (extension-only) — Low, still open.
- **Raw Postgres/Gemini exception text leaking to client responses** in some error paths — Low/Medium, information disclosure.
- **Invalid URL handling — verified live and via source:** `pharmagpt/app.py:120-124` registers a real `@app.errorhandler(404)` returning `{"error": "Not found"}` with a proper 404 status for any unmatched route (except explicitly exempt static/health paths). This is correct API behavior; the only cosmetic gap is that this raw JSON response, not the styled in-app 404 component, is what a user sees for a truly invalid browser URL.
- **No CSRF token framework** — assessed as adequately mitigated by `SameSite=Lax` + bearer-token model in the prior security review; not independently re-litigated here.
- **SQL injection:** none found in any report reviewed, consistent finding across two independent prior security passes; not contradicted by this audit.
- **Session timeout / permission-bypass attempts:** not independently live-tested in this audit (requires an authenticated session — blocked per §0). Recommend a manual, credentialed pass by the release owner before sign-off.

---

## 10. Critical Issues

| # | Finding | Root Cause | Impact | Recommendation | Files Likely Affected |
|---|---|---|---|---|---|
| C1 | Company Administration, User Management (list/update), Role Management, and Assume Company Context are **non-functional in the live database** — the platform's own Enterprise Acceptance Test (2026-07-23) reached a formal **NO-GO** for exactly these areas, and no later document shows it re-tested to a clean GO. | Migrations 0010/0011/0012's trailing `GRANT`/`CREATE POLICY` statements are not active in the live Supabase project (likely halted partway through a prior manual SQL-editor run, e.g. on a "policy already exists" error). | Company Admins cannot manage their own users; Super Admin's only sanctioned tenant-support mechanism is unusable; this is the security model's designated break-glass path, currently broken. | Re-run each `_up.sql` migration in full against the live database, confirm grants are active, then re-run the full Enterprise Acceptance Test (all 7 areas) to a clean GO before proceeding. | `migrations/0010_break_glass_rls_up.sql`, `0011_companies_admin_rls_up.sql`, `0012_users_company_admin_rls_up.sql`, `pharmagpt/routes/companies.py`, `pharmagpt/routes/users.py`, `pharmagpt/routes/auth.py` |
| C2 | No server-side control prevents executing/completing an OQ or PQ protocol before an IQ protocol exists or is completed. | `create_protocol`/`execute_test_case` check only the target protocol's own preconditions, never sibling-protocol state. | GAMP5/FDA/EU Annex 15 non-conformance — undermines the evidentiary validity of any qualification package produced. | Add a server-side precondition: block OQ protocol creation/execution unless a completed IQ protocol exists for the same qualification (and PQ unless OQ is complete). | `pharmagpt/qual_database.py:425-453`, `pharmagpt/routes/qual.py:412-440` |
| C3 | A Validation Report can be created, AI-generated, approved, and released with no check that its linked Qualification (or underlying IQ/OQ/PQ) is complete/approved; linkage itself is optional. | `report.py`'s create/generate/approval paths never query qualification completeness; no schema-level required linkage. | Most consequential compliance gap in the chain — the final GAMP5 deliverable could be released without its underlying evidence, which would fail a regulatory audit immediately. | Require `linked_qual_id`; add a precondition check (qualification status = approved/complete, all IQ/OQ/PQ protocols completed) before allowing report approval/release. | `pharmagpt/routes/report.py:85-114,397-438`, `pharmagpt/report_database.py` |
| C4 | PUT (update) and DELETE are unaudited in every domain except `projects.py` — deleting a Deviation/CAPA/Change Control/Document/Qualification/Report/Risk Assessment leaves zero audit trail. | `add_audit_entry()` is wired into create + approval-transition handlers only, never into update/delete handlers. | Fails 21 CFR Part 11/Annex 11's basic audit-trail requirement for GxP records; would be flagged immediately by an FDA/MHRA inspector. | Wire `add_audit_entry`/`add_approval_entry` into every PUT and DELETE handler across all modules. | `qms_documents.py`, `qms_deviations.py`, `qms_capa.py`, `qms_change_control.py`, `urs.py`, `qual.py`, `report.py`, `risk.py`, `equipment.py` |
| C5 | Audit-trail schema captures no Old Value/New Value or Company — only a free-text `detail` string, inconsistently populated. | Schema designed around a generic detail field from the outset rather than structured before/after capture. | Cannot reconstruct "what changed" from the audit trail; fails the explicit spec (Timestamp/User/Company/Old Value/New Value/Action) and would not pass a GAMP5/21 CFR Part 11 audit-trail review. | Add `old_value`/`new_value` (structured or JSON) and `company_id` columns to the audit-trail and approval tables; populate at every call site. | `pharmagpt/qms_database.py:68-76,481-491`, `urs_database.py:75-85`, `risk_database.py`, `report_database.py:92-103`, `qual_database.py:181-193` |
| C6 | Identity is client-spoofable in several non-canonical endpoints despite an established server-derivation fix (`tenancy.signing_identity()`) used correctly elsewhere: attachment upload/comment authorship, qualification protocol completion's e-signature field, and version-snapshot `created_by`. | The fix was applied to each module's main `/approval` endpoint but not propagated to attachments, comments, protocol completion, or version snapshots. | Undermines e-signature integrity (21 CFR Part 11 §11.50/11.70) for these specific actions — a user could act under a spoofed name/role. | Replace all client-supplied identity fields at these call sites with `tenancy.signing_identity()`/`g.tenant`. | `pharmagpt/routes/qms_common.py` (attachments/comments), `pharmagpt/routes/qual.py:477,620`, `pharmagpt/routes/urs.py:504-506`, `pharmagpt/routes/report.py:480` |
| C7 | Several QA-significant, state-changing endpoints have no role guard at all: Risk `/publish` (bypasses the gated approval action entirely), Qualification protocol `/complete`, CAPA action escalation, QMS document distribution/training records. | `@require_role` was applied to `DELETE` and the canonical `/approval` endpoint per module, but not to every alternate mutation path with the same real-world effect. | A base `user` role can bypass the intended QA gate for risk-library publication and qualification-protocol completion — undermines segregation-of-duties, a core GxP/Part 11 control. | Add `@require_role("company_admin","reviewer_qa")` to each listed endpoint; audit the codebase systematically for other alternate-path mutations missing the guard their canonical counterpart has. | `pharmagpt/routes/risk.py:361-366`, `pharmagpt/routes/qual.py:443-482`, `pharmagpt/routes/qms_capa.py:220-229`, `pharmagpt/routes/qms_documents.py:117-143,192-240` |

---

## 11. High Issues

| # | Finding | Impact | Recommendation | Files |
|---|---|---|---|---|
| H1 | DQ/FAT/SAT have no schema linkage to Equipment or Qualification records. | GAMP5 traceability gap — cannot tell which DQ/FAT/SAT gates which equipment/qualification. | Add `equipment_id`/`linked_qual_id` foreign keys to the QMS document schema for these doc types. | `pharmagpt/qms_document_database.py:21-57` |
| H2 | DQ/FAT/SAT AI generation uses a generic SOP template; the dedicated `dq_prompt.py`/`fat_prompt.py`/`sat_prompt.py` are registered but never invoked. | Generated documents lack the correct structure for these specific GAMP5 document types. | Wire the generation route to select the doc_type-specific prompt builder. | `pharmagpt/routes/qms_documents.py:117-143` vs `pharmagpt/prompts/__init__.py:19-21,35-37` |
| H3 | `risk_database.py` leaks a SQLite connection in all 15 functions. | Resource-exhaustion risk under sustained load. | Use context-managed connections, consistent with other `*_database.py` modules. | `pharmagpt/risk_database.py` |
| H4 | 6 of 7 AI-generation endpoints stream synchronously in-request against a 2-worker/4-thread gunicorn config — the same pattern that already caused production timeouts for URS before it alone was fixed. | Worker-timeout crash risk under concurrent load for QMS documents, risk, qualification, report, validation, chat generation. | Move remaining generation endpoints to the same background-job + polling pattern already used for URS. | `pharmagpt/routes/qms_documents.py`, `risk.py`, `qual.py`, `report.py`, `validation.py`, `chat.py` |
| H5 | No caching of per-request Supabase auth/tenant resolution — 2 blocking network round trips on every request. | Elevated latency on every authenticated request, compounding under load. | Cache the resolved `TenantContext` per request/short TTL. | `pharmagpt/auth/context.py::resolve_tenant_context` |
| H6 | SQLite→Postgres cutover gate (extended Staging soak + 2-company RLS isolation spot-check) has not been performed for any of the 4 domain flags; the live SQLite path has no database-level tenant backstop (app-layer scoping only). | If the application-layer scoping check ever regresses, there is no schema-level control to catch it on the currently-live path. | Complete the Phase 3.6 cutover gate before scaling multi-tenant production load, or add an interim SQLite-level backstop. | `docs/PHASE3_FLAGS.md`, `docs/MIGRATION.md` |
| H7 | CAPA and Change Control do not use `lifecycle_engine` at all — status can be set to any value with no sequence guard. | Same defect class as C2, in an adjacent module: a Closed CAPA could be reopened arbitrarily, or a Change Control could skip required review stages. | Wire both modules into `lifecycle_engine.validate_transition`, matching the pattern in Document/URS/Qualification/Report/Risk. | `pharmagpt/routes/qms_capa.py`, `pharmagpt/routes/qms_change_control.py` |

---

## 12. Medium Issues

| # | Finding | Recommendation | Files |
|---|---|---|---|
| M1 | Document versioning is manual (a separate endpoint), not auto-snapshotted on regeneration, across URS/Qualification/Report/QMS Document. | Auto-invoke the version snapshot inside the generate/regenerate handler before overwriting content. | `urs.py`, `qual.py`, `report.py`, `qms_documents.py` version endpoints |
| M2 | Lifecycle vocabularies diverge from the 6-stage spec and from each other: QMS Document has no distinct "Approved" and no "Archived"; URS has no "Archived"; Validation Report allows a Released→Obsolete shortcut skipping Archived. | Standardize all record types on the same 6-stage vocabulary and transition map. | `pharmagpt/services/lifecycle_engine.py`, `pharmagpt/services/urs_lifecycle.py` |
| M3 | No audit-log viewer for Assume Company Context / break-glass grants — grants are stored but not surfaced anywhere reviewable. | Build a read-only history view (likely under Administration). Flagged by the prior acceptance test as a product decision, not fixed since. | Administration module (new view) |
| M4 | Raw Postgres/Gemini exception text leaks to client responses on some error paths. | Catch and translate backend exceptions into the existing generic error-page/JSON format. | Various route error handlers |
| M5 | `FLASK_SECRET_KEY` hardcoded insecure fallback still present in code. | Fail startup if the env var is unset in production, rather than silently falling back. | `pharmagpt/config.py:15` |
| M6 | No content/magic-byte file-upload validation (extension-only). | Add MIME/magic-byte verification on all upload endpoints. | Document/KB/Equipment upload handlers |
| M7 | Sidebar nav items are non-semantic `<div>`s, not keyboard-focusable (reconfirmed still-open by the most recent UX report). | Convert to semantic, focusable elements with proper ARIA roles. | `pharmagpt/templates/index.html`, `static/js/*` |

---

## 13. Low Issues

| # | Finding | Recommendation |
|---|---|---|
| L1 | Project status has no governed lifecycle, unlike every other module in the chain — freely settable via `PUT /projects/<id>`. | Optionally align with the shared lifecycle-engine pattern for consistency; lower urgency since Project itself isn't a GxP-controlled record. |
| L2 | A genuinely invalid browser URL gets a raw JSON `{"error":"Not found"}` (correct, but unstyled) rather than the polished in-app 404 component, which only renders for in-app record-not-found cases. | Consider serving the SPA shell for unmatched non-API GET routes so the branded 404 component renders consistently. |
| L3 | `README.md`'s stated test count (390) is stale — this audit independently re-ran the full suite and confirmed **500 passed, 1 deselected** is the current, live-verified count as of 2026-07-24. | Update the README after each significant suite change, or replace the hardcoded number with a CI badge. |
| L4 | No CSRF token framework (assessed as adequately mitigated by SameSite=Lax + bearer-token model). | Informational; revisit only if the auth model changes. |

---

## 14. Missing Features

Confirmed either via live DOM inspection of the running app or direct source review — these are correctly represented as not-yet-built, not hidden gaps, with one exception noted:

- **Training, Complaints, Audit Management, Supplier Quality, Management Review** — explicitly labeled "(Coming Soon)" in the live sidebar.
- **PharmaPilot** — explicitly labeled "Enterprise AI Assistant (placeholder only)" in the live workspace chooser. (The separate, working AI Assistant chat is not the same feature and should not be conflated with it in release communications.)
- **Equipment as company-owned master data** — still project-owned (`project_id NOT NULL`) rather than the target many-to-many model; a company-wide list view exists as a navigation-level accommodation, but the schema change is deferred.
- **DQ/FAT/SAT as first-class, equipment/qualification-linked records** — currently exist only as generically-typed QMS documents with no structural traceability link (see H1).
- **Assume Company Context audit-log viewer** — grants are recorded but not visible in any UI (see M3).
- **`docs/ARCHITECTURE_LOCK.md`'s further-narrowed Document Generator / Equipment Library sub-tab / Knowledge Base retaxonomy proposal** — explicitly marked "FINAL — pending sign-off... does not authorize implementation." **Note for the release owner:** the live application's currently deployed navigation already matches most of the structure described as "ALD-001-R1 LOCKED" in this audit's brief, which is *not* identical to what's written in `docs/ARCHITECTURE_LOCK.md`. It is worth confirming which document is the actual, current source of truth for "ALD-001-R1" — this audit found the file and the live app agreeing on some points (Validation Suite containing Projects, Equipment Library as a top-level module) but could not fully reconcile every sub-section within the audit's time budget.
- **Company Administration / User Management / Assume Company Context** — technically built (routes, UI, and migrations all exist) but non-functional against the live database (C1) — functionally equivalent to missing until that is fixed.

---

## 15. Recommended Improvements

In priority order, independent of strict severity:

1. Fix the Postgres GRANTs for migrations 0010-0012 and re-run the Enterprise Acceptance Test to a clean GO — this single fix unblocks the largest confirmed functional gap (C1).
2. Add the qualification-sequencing gate (C2) and the Validation Report completeness gate (C3) — these are the two findings most likely to fail a real regulatory inspection.
3. Close the audit-trail structural gaps (C4/C5) and the remaining identity-spoofing surface (C6) as one coordinated pass, since they're the same underlying pattern (the `tenancy.signing_identity()`/`add_audit_entry()` fixes exist and work — they just weren't applied everywhere).
4. Extend `@require_role` coverage to the alternate-path mutation endpoints found unguarded (C7), and run a systematic sweep for any others of the same shape.
5. Wire CAPA/Change Control into `lifecycle_engine` (H7) and standardize the lifecycle vocabularies (M2) in the same pass, since both are "make it consistent with the rest of the codebase" fixes.
6. Complete the DQ/FAT/SAT schema linkage and re-wire their dedicated prompts (H1/H2) — comparatively contained, high-value fixes.
7. Perform the live 2-company multi-tenant spot-check and the Postgres cutover soak (H6) before any further reliance on multi-tenant claims.
8. Schedule the manual, credentialed walkthrough this audit could not perform (session timeout, live login error-message behavior, live Company Admin/Assume Context re-test after C1 is fixed) before final sign-off.

---

## 16. Go / No-Go Recommendation

# **NO-GO**

PharmaGPT v1.0 should **not** be released in its current state. This is not a close call in either direction:

- The platform's own most recent, most authoritative functional test already reached NO-GO for a real, in-scope feature area (Company Administration / Assume Company Context), and that verdict has not been overturned by any later evidence.
- Independently of that, this audit found the audit trail — a load-bearing 21 CFR Part 11 control for any GxP system — to be structurally incomplete, and found that qualification sequencing and validation-report release are not gated against the evidence they depend on. Either of these findings alone would warrant a NO-GO for a pharmaceutical validation platform; both together make this an unambiguous recommendation.

The path back to GO is concrete and largely mechanical (§15 above) — this is a system with real architecture and a passing 500-test suite, not a system that needs to be re-designed. Recommend: fix C1–C7, re-run this full Phase E audit (not just the prior narrower acceptance test) end-to-end including the manual credentialed walkthrough this session could not perform, and only then reconsider release.

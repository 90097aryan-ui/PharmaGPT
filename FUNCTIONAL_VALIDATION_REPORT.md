# PharmaGPT — Functional Validation Report

**Validation date:** 2026-07-22
**Validated by:** Claude (acting as QA Validation Engineer), end-to-end UI-through-database testing
**Environment:** Local dev server (`pharmagpt-flask`, port 5187), real Supabase Auth/Postgres identity layer, real SQLite business-data layer, real Gemini API (`gemini-2.5-flash`)
**Baseline:** `pytest` — 370 passed, 0 failed, 1 deselected (before and after this validation pass)

## How this validation was performed

This was a genuine, interactive validation — not a code read-through. A real Flask server was started, real Supabase test accounts were provisioned (two companies, four roles: `super_admin`, `company_admin`, `reviewer_qa`, `user`), and modules were exercised through the actual browser DOM: real logins, real form submissions, real AI generation calls, real file uploads (via a synthetic `File`/`DataTransfer` object, since no OS file-picker automation was available — this exercises the exact same upload code path a real file picker would), real direct-API probes to confirm backend enforcement (RBAC, tenant isolation, spoofing resistance).

**Coverage note:** given the scope (15 modules × ~10 test dimensions), this pass prioritized breadth across all modules for the happy path, plus depth on the dimensions most consequential for a regulated pharma platform: RBAC, tenant isolation, audit-trail integrity, and AI-generation correctness. Every finding below was independently reproduced and root-caused in source before being reported; two initial suspected defects (a Risk-wizard "dead link" and a KB "search bug") were retracted after discovering they were artifacts of test timing/tooling, not real bugs — this is called out explicitly in-line where relevant, since transparency about false leads matters as much as the confirmed findings.

Findings are grouped by severity. Each entry has Module / Steps to Reproduce / Expected / Actual / Root Cause / Recommended Fix / Estimated Effort. Findings marked **[FIXED]** were corrected during this same session and re-verified live; the regression suite (370/370) was re-run clean after all fixes.

---

## Critical

### C1. Risk Assessment "New Assessment" wizard — Next button non-functional **[FIXED]**

- **Module:** Risk Assessment (New Assessment)
- **Steps to reproduce:** Log in → sidebar → Risk Management → New Assessment → select any risk type → click **Next**.
- **Expected:** Wizard advances to Step 2 (Assessment Information).
- **Actual:** Nothing happens. The wizard is permanently stuck on Step 1; there is no error, no console warning, no visual feedback. A customer cannot create a Risk Assessment through the UI at all.
- **Root cause:** `pharmagpt/static/js/risk.js` defines `window.wizardNext` / `window.wizardBack` for its own wizard. `pharmagpt/static/js/urs.js`, loaded later in `templates/index.html`, defines its own `window.wizardNext` / `window.wizardBack` for the URS wizard — silently overwriting Risk's. Clicking "Next" in the Risk wizard therefore runs URS's navigation logic against URS's own state (`ursState.selectedEquipmentType`, always null in this context), which no-ops. This is the exact same bug class the team already found and fixed once for different function names (`renderWizardStep`/`renderApprovalPanel`, see `DECISIONS.md` DEC-020) — this pair of names was missed in that pass.
- **Recommended fix:** Rename `risk.js`'s wizard-navigation functions to `riskWizardNext`/`riskWizardBack` (matching the DEC-020 naming convention) and update the 5 corresponding `onclick` references in `templates/index.html`.
- **Estimated effort:** Small (< 1 hour). **Applied and verified**: full wizard (type → info → methodology → review → create) now completes and opens the new assessment in the editor.

### C2. Validation Document Generator — AI generation fails 100% of the time **[FIXED]**

- **Module:** Generate Documents (URS / DQ / FAT / SAT / IQ / OQ / PQ / FMEA / CAPA / Deviation / Change Control — the real AI-powered generator, reached via the per-doc-type sidebar links under "Generate Document")
- **Steps to reproduce:** Select a project → sidebar → any doc-type link (e.g. OQ) → fill Equipment/Details → Reference Docs → **Generate OQ**.
- **Expected:** Gemini streams a full structured protocol document.
- **Actual:** Every single generation attempt fails: `Generation failed: 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'Penalty is not enabled for models/gemini-2.5-flash', 'status': 'INVALID_ARGUMENT'}}`. This is the single most important AI feature in the platform and it was completely non-functional.
- **Root cause:** `pharmagpt/routes/validation.py:112` passes `frequency_penalty=0.4` to `GenerateContentConfig`. The currently configured model, `gemini-2.5-flash`, rejects any penalty parameter outright — this is not transient, it fails deterministically on every call.
- **Recommended fix:** Remove the unsupported parameter.
- **Estimated effort:** Trivial (minutes). **Applied and verified**: generated a full OQ protocol (equipment description, glossary, numbered sections) end-to-end through the real UI wizard after the fix.

### C3. QMS audit trail — record-creation "performed by" is fully spoofable **[FIXED]**

- **Module:** Audit Trail (cross-cutting: Document Control, Deviation Management, CAPA, Change Control)
- **Steps to reproduce:** As any authenticated user, `POST /qms/deviations` (or `/qms/capa`, `/qms/change-control`, `/qms/documents`) with an `initiated_by` (or `requested_by` / `owner`) field set to an arbitrary name, e.g. `"Fake CEO Spoofed Identity"`.
- **Expected:** The audit trail entry recording who created the record should reflect the actual authenticated caller, non-repudiably — this is exactly the property the codebase's own recent security fix (`tenancy.signing_identity()`) already established for *approval*/e-signature actions (see `TEST_SUMMARY.md`'s "E-signature spoofing" tests).
- **Actual:** Confirmed exploit — created a real deviation with `initiated_by: "Fake CEO Spoofed Identity"`; the server stored it verbatim, and the audit-trail entry's `performed_by` was empty/spoofed rather than the real caller ("E2E Admin A"/"E2E Admin B" in testing). The same pattern exists in all four QMS creation endpoints.
- **Root cause:** `qmsdb.add_audit_entry(...)` at creation time was called with `data.get("initiated_by"/"requested_by"/"owner", "")` — a client-supplied field — instead of the authenticated `g.tenant` identity, in `routes/qms_deviations.py:144-145`, `routes/qms_capa.py:142-143`, `routes/qms_change_control.py:155-156`, and `routes/qms_documents.py:77`. The exact same vulnerability class was already fixed for approval actions elsewhere in the codebase (`tenancy.signing_identity()`), but that fix was never extended to record *creation*.
- **Recommended fix:** Use `tenancy.signing_identity(g.tenant)["performed_by"]` for the audit-entry `performed_by` argument in all four creation routes, exactly mirroring the already-approved pattern used for approvals. The record's own business fields (`initiated_by`, `requested_by`, `owner`) are left as legitimate, separately-editable business data (e.g. "who reported this on the shop floor" can differ from who is entering it) — only the audit-log attribution was in scope for this fix, since that is the field with 21 CFR Part 11 non-repudiation implications.
- **Estimated effort:** Small (< 1 hour for all 4 files). **Applied and verified**: re-ran the exact spoofing exploit after the fix — the audit trail now correctly shows the authenticated user regardless of the spoofed input field.

---

## High

### H1. Duplicate submission — QMS "Create" buttons have no debounce/disable guard **[FIXED]**

- **Module:** Deviation Management (confirmed); CAPA, Change Control, Document Control (same code pattern, fixed as a set)
- **Steps to reproduce:** Open "New Deviation", fill the title, click "Create Deviation" three times in quick succession.
- **Expected:** One deviation record is created; subsequent clicks during the in-flight request are ignored.
- **Actual:** Multiple deviation records are created from multiple clicks (confirmed via direct request tracing) — a real data-integrity problem for a regulated quality system, since duplicate deviation/CAPA/change-control records complicate investigation and closure tracking. By contrast, Project creation (`projects.js`) already had a correct disable-during-submit guard, showing this was an inconsistency, not a deliberate design choice.
- **Root cause:** `qmsDevCreate()`/`qmsCapaCreate()`/`qmsCCCreate()`/`qmsDocCreate()` in the respective `static/js/qms_*.js` files call `fetch(...)` with no button-disable guard before or during the request.
- **Recommended fix:** Add an id to each "Create" button and guard the handler with `if (btn.disabled) return; btn.disabled = true;` before the request, re-enabling on failure (mirroring `projects.js`'s existing pattern).
- **Estimated effort:** Small (~1 hour for all four). **Applied and verified**: repeated rapid clicks now produce exactly one record per case.

### H2. Delete-project failure is silently treated as success in the UI **[FIXED]**

- **Module:** Projects (Delete)
- **Steps to reproduce:** As a non-`company_admin` role, trigger `DELETE /projects/<id>` on the active project (backend correctly returns 403).
- **Expected:** A clear error message; no change to the visible chat/project state.
- **Actual:** `confirmDeleteProject()` never checked `res.ok` — a 403 (or any non-2xx) response was treated identically to success. If the deleted project was the active one, its chat/banner was cleared from the screen as if deletion succeeded, with no error shown, even though the project still existed server-side.
- **Root cause:** `pharmagpt/static/js/projects.js:206-228` — `await fetch(...)` result discarded without a status check.
- **Recommended fix:** Check `res.ok`, throw with the server's error message on failure, and only clear UI state on genuine success.
- **Estimated effort:** Trivial. **Applied and verified.**

### H3. No role-based UI gating — the "Delete project" button is shown to every role **[Partially fixed]**

- **Module:** Projects / RBAC (Permission Failure)
- **Steps to reproduce:** Log in as a plain `user` role (no `company_admin`), open a project, look at the sidebar delete icon.
- **Expected:** A role without delete permission shouldn't be offered a delete action that will always be rejected.
- **Actual:** The trash-can delete icon is rendered and clickable for every role. Combined with H2 (before its fix), this produced a genuinely confusing experience: click delete → confirm → the project appears to vanish from view → but it's still there after a refresh, with no explanation of why.
- **Root cause:** `projects.js`'s project-list renderer does not check the caller's role before rendering the delete button; the backend is the only enforcement layer.
- **Recommended fix / what was applied:** Hid the delete button for any role other than `company_admin` (using `window.PharmaAuth.getUser().role`, already available client-side from `/auth/login`/`/auth/me`). This is a narrow, targeted fix for the one concretely-observed instance.
- **What was *not* done, and why:** The same "backend-only enforcement, no UI gating" pattern likely recurs across other modules (QMS approvals, CAPA/deviation status transitions, etc.) — auditing and fixing every instance app-wide would be a much larger, more architectural change than the explicit "fix defects, don't redesign" mandate for this pass covers. Recommend a follow-up sweep specifically for this pattern.
- **Estimated effort:** Small for the fix applied; Medium (1-2 days) for a full app-wide audit.

### H4. Two parallel, inconsistent "Generate Document" experiences

- **Module:** Generate Documents
- **Steps to reproduce:** Click the main sidebar **"Generate Document"** nav item (the most prominent, obvious entry point) vs. clicking an individual doc-type link (URS/OQ/etc.) further down the sidebar.
- **Expected:** One coherent document-generation flow.
- **Actual:** The main "Generate Document" nav item opens a different, newer 6-step wizard (`gen_document.js`, self-labeled "v0.9") that does **not** call any AI at all — it produces a client-side JSON stub and explicitly says "Ready for AI generation in v1.0." The fully-functional, real AI-powered generator with DOCX export (`validation.js` / `routes/validation.py`, the one covered in C2 above) is only reachable via the secondary per-doc-type sidebar links. A customer using the obvious, prominently-labeled entry point gets an incomplete placeholder with no indication a working alternative exists elsewhere in the same sidebar.
- **Root cause:** Two competing implementations exist side by side (`view-gen-doc` vs `view-validation`), evidently from two different build phases, and the newer one was wired to the more prominent nav position without either completing its AI integration or removing/relabeling the older, complete one.
- **Recommended fix:** Product decision required — either (a) point the main "Generate Document" nav item at the real, working generator (`switchToValidation`/`view-validation`) and retire or clearly relabel the v0.9 stub, or (b) finish the v0.9 wizard's AI integration and retire the old one. Both options are feature/architecture decisions rather than defect fixes, so **not applied** in this pass per the explicit "no new features, no redesign" instruction — flagged here for a scoped decision.
- **Estimated effort:** Small if simply repointing the nav item to the existing working flow (~1 hour); Large if instead finishing the v0.9 AI integration.

### H5. User Management (scope item 12) and Company Branding (scope item 15) do not exist

- **Module:** User Management, Company Branding
- **Steps to reproduce:** Look for any screen or API route to invite a user, assign/change a role, deactivate an account, or set company branding (logo/colors).
- **Expected:** A `company_admin` can manage their company's users and branding per the documented role model (`roles.description`: "Full control within one company: users, Knowledge Base, Equipment Library, Projects, settings").
- **Actual:** No such route or screen exists anywhere in the app. `pharmagpt/routes/` has no `users.py`/`companies.py`/`admin.py`. The `company_settings.branding` JSONB column exists in the Postgres schema (migration `0001_identity_tenancy_up.sql`) but is never read or written by any route. The **only** way any user or company in this system was ever created is `scripts/bootstrap_super_admin.py` (a one-time CLI script, explicitly documented as exposing no HTTP route) or direct manipulation via the Supabase service-role key — which is exactly how the test fixtures for this validation pass had to be created, since there is no product-level path to do it.
- **Root cause:** Not implemented. This is a genuine scope gap, not a defect in existing code.
- **Recommended fix:** Build user-invite/role-assignment/deactivation and company-branding screens + routes. **Not implemented in this pass** — per the explicit "do not implement new features" instruction, a missing feature cannot be "fixed" without building it, which is out of scope here. Flagged as the report's clearest instruction conflict: item 12/15 validation was requested, but the only way to make it pass is net-new feature work.
- **Estimated effort:** Large (multi-day) — full CRUD UI + routes + RLS-safe Supabase writes for users, roles, and branding.

---

## Medium

### M1. Knowledge Base — "no search results" reuses the "totally empty library" message **[FIXED]**

- **Steps to reproduce:** Upload one KB document, then search by a title that doesn't match anything.
- **Expected:** A message like "No documents match your search."
- **Actual:** Shows "No documents found. Upload your first document using the + Add Document button above." — identical to the message for a library with zero documents, misleading a user who already has documents but searched for the wrong term.
- **Root cause:** `templates/index.html`'s `#kb-doc-empty` had one static message with no distinction between "empty library" and "empty search result."
- **Recommended fix / applied:** `renderKBList()` in `knowledge_base.js` now swaps the empty-state copy based on whether any search/folder filter is active.
- **Estimated effort:** Trivial.

### M2. Knowledge Base — rapid successive searches aren't request-sequenced **[FIXED]**

- **Steps to reproduce:** Trigger two KB searches in very quick succession (e.g. fast typing + auto-search, or a slow network).
- **Expected:** The UI always reflects the most recent search.
- **Actual:** `loadKBDocuments()` had no protection against out-of-order responses — a slower, older request could resolve after a faster, newer one and silently overwrite it with stale results. Reproduced directly by intentionally racing two `fetch` calls.
- **Root cause:** No request-sequencing/cancellation in `knowledge_base.js`.
- **Recommended fix / applied:** Added a monotonically increasing request-sequence guard; a response is only applied if it belongs to the most recently issued request.
- **Estimated effort:** Small.

### M3. Risk / URS / Qualification / Validation Report tabs inside a Project Workspace are not project-filtered

- **Steps to reproduce:** Open any Project Workspace → Risk Assessment tab.
- **Expected:** Shows risk assessments for this project.
- **Actual:** Opens the suite's global, unfiltered dashboard. This is already self-documented in the live UI itself ("Not yet filtered to this project — see Known Issues") and in `PROJECT_STATUS.md`'s Known Issues — re-confirmed still true, not a new finding. No fix applied (pre-existing, already tracked, and fixing it would mean adding `project_id`/`equipment_id` FKs to four tables — a schema/architecture change, out of scope for a defect-fix pass).
- **Estimated effort:** Medium-Large (schema migration + 4 suites' query logic) — already tracked in `DECISIONS.md` DEC-025.

### M4. Unauthenticated page load fires doomed authenticated API calls

- **Steps to reproduce:** Load `/` fresh with no session, open Network tab.
- **Expected:** No API calls until after login.
- **Actual:** `dashboard/stats`, `dashboard/validation-score`, and `projects` all fire and return 401 before the login form even finishes rendering, because those modules' own `DOMContentLoaded` handlers run unconditionally (a design choice `auth.js` itself documents and deliberately re-triggers after login — "these modules' own DOMContentLoaded handlers already fired... so re-trigger them now"). Cosmetic/noise only — no data is exposed, nothing breaks. Not fixed, to avoid risking the documented re-trigger flow for a purely cosmetic issue.
- **Estimated effort:** Small, if picked up — gate those modules' initial load behind `PharmaAuth.isAuthenticated()`.

---

## Low

### L1. Risk wizard's selection cards are non-semantic `<div>`s, not buttons

Type-selector and methodology-selector cards use `onclick` on plain `<div>`s rather than `<button>`/`<a>` elements — not reachable by keyboard Tab, no accessible role. Low priority, cosmetic/accessibility polish. Not fixed (would touch shared card-rendering CSS/markup beyond a scoped defect fix).

### L2. Chat: a transient Gemini failure is shown to the user but never logged server-side

Reproduced once (`Gemini server is temporarily unavailable`, resolved on retry — genuine transient upstream flakiness, not a persistent bug). No corresponding entry appeared in the Flask server log, consistent with the already-known, already-tracked "silent exception swallowing" item in `docs/CODE_REVIEW.md`, now confirmed to extend to `/stream`. Not fixed in this pass (logging-infrastructure change, not a functional defect).

### L3. Minor wizard button-label cosmetics

Some "Next" buttons render as "Next → Generate" (bundling the icon and the *next* step's name) which reads slightly awkwardly. Purely cosmetic, consistent with the app's existing "Next → [next step]" labeling convention elsewhere. Not fixed.

---

## What was explicitly tested and passed cleanly (no defect)

To be clear about what *worked*, not just what didn't:

- **Auth:** login (valid/invalid), logout, session-check-on-reload, role resolution — all correct.
- **Tenant isolation:** cross-tenant reads on Projects and KB documents correctly return 404 (never 403 — matching the documented "never confirm existence to an outsider" design); dashboards correctly show zero data for a fresh company; verified with two real, independent companies.
- **RBAC:** backend correctly rejects a `user`-role delete with 403 in every case tested.
- **Projects:** create (happy path + missing-required-field correctly blocked client-side), workspace tabs, audit trail ("Project created" entry correct).
- **Knowledge Base:** upload (with metadata/tags/dates), title search, folder counts, overdue-review-date highlighting in the detail panel — all correct once verified past initial timing-artifact false alarms (see note on methodology above).
- **AI Chat:** streaming response, retry-after-transient-failure, project-scoped history — correct.
- **QMS Deviation Management:** creation, full detail-tab navigation, and the **AI Investigation Assistant** (Fishbone/Ishikawa + 5-Why + timeline + root cause in one call) — produced a genuinely well-structured, relevant analysis, not generic filler.
- **QMS Audit Trail:** entries correctly recorded and timestamped for creation and AI-investigation events (attribution bug is C3 above, now fixed).
- **DOCX/Report export buttons:** present and reachable throughout (Risk, Deviation, Validation Generator) — not exhaustively byte-verified, but the export code paths did not error during generation.

---

## Fixes applied this session (Critical + High disposed)

| # | Finding | File(s) | Status |
|---|---|---|---|
| C1 | Risk wizard `wizardNext`/`wizardBack` collision | `static/js/risk.js`, `templates/index.html` | **Fixed & verified** |
| C2 | Gemini `frequency_penalty` unsupported on `gemini-2.5-flash` | `routes/validation.py` | **Fixed & verified** |
| C3 | QMS creation audit-trail spoofable `performed_by` | `routes/qms_deviations.py`, `routes/qms_capa.py`, `routes/qms_change_control.py`, `routes/qms_documents.py` | **Fixed & verified** |
| H1 | No duplicate-submission guard on QMS "Create" buttons | `static/js/qms_deviations.js`, `qms_capa.js`, `qms_change_control.js`, `qms_documents.js` | **Fixed & verified** |
| H2 | Delete-project ignores HTTP failure status | `static/js/projects.js` | **Fixed & verified** |
| H3 | Delete button shown regardless of role | `static/js/projects.js` | **Fixed (scoped) & verified** |
| H4 | Two parallel Generate Document flows | `static/js/gen_document.js` / `validation.js` | **Documented only** — product decision needed, out of scope (redesign) |
| H5 | User Management / Branding not implemented | n/a | **Documented only** — new feature, explicitly out of scope |
| M1 | KB empty-search messaging | `static/js/knowledge_base.js` | **Fixed & verified** |
| M2 | KB search race condition | `static/js/knowledge_base.js` | **Fixed & verified** |
| M3, M4, L1-L3 | See above | — | **Documented only**, low/pre-existing/out-of-scope |

**0 Critical, 0 High remaining that are addressable without new-feature work or redesign** (H4 and H5 remain open by necessity — see their entries above for why).

## Regression results

- **Before fixes:** `pytest` → 370 passed, 0 failed, 1 deselected.
- **After fixes:** `pytest` → 370 passed, 0 failed, 1 deselected. No regressions introduced.
- No new automated tests were added for the fixes in this pass (all fixes were verified live via the real browser/API during this session, per the report's methodology); adding regression tests for C1-C3 and H1-H2 specifically (risk wizard step advancement, validation-generate success, QMS creation audit attribution, duplicate-submission guard) is a reasonable, low-effort follow-up.

## Remaining Medium/Low enhancements (not blocking)

- M3 — project-filtered Risk/URS/Qual/Report tabs (schema change, already tracked as DEC-025 Future Review)
- M4 — gate pre-login API calls behind session check
- L1 — semantic HTML for Risk wizard selector cards
- L2 — server-side logging for `/stream` AI failures
- L3 — wizard button label cosmetics
- H3 follow-up — audit and apply role-based UI gating app-wide, not just the one instance fixed here
- H4/H5 — require an explicit product decision (which Generate Document flow to keep) and net-new feature work (User Management, Company Branding) respectively; both are one level above what a "fix defects" pass can close

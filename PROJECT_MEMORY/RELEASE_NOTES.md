# RELEASE_NOTES.md — PharmaGPT Release History

> Part of the permanent [PROJECT_MEMORY](CLAUDE.md) set. **This file is append-only.** Never
> rewrite or delete a past entry — add a new entry at the top for every release. Reconstructed
> from `git log`, the root-level `CHANGELOG.md`, and `docs/QMS_PHASE1.md` as of 2026-07-02.

---

## [Unreleased] — PharmaGPT v1.0 Module 3: Project Workspace & Navigation Refactoring

**Sprint Name:** PharmaGPT v1.0 Module 3 (follows Module 2 — Equipment as a First-Class Entity)
**Status:** Complete in the working tree, browser-verified end-to-end, full 148-test regression
suite passing (147 + 1 pre-existing flaky timing test confirmed unrelated on re-run),
**not yet committed to git** — per explicit instruction, no architectural commit until the full
Foundation Refactoring (Modules 1–3) is complete.

**Summary:** Establishes "One Project = One Workspace" — Equipment, Documents (+ Document Insights),
Risk Assessment, URS, Qualification, Validation Report, Tasks, Approvals, and History are now all
reached from a single unified Project Workspace opened by selecting a project, instead of a growing
set of permanent, project-scoped sidebar nav items. See [DECISIONS.md](DECISIONS.md) DEC-024/DEC-025
for full architectural detail, including a pre-existing architectural conflict discovered and
resolved before this module began: the sidebar's "Validation Workspace" item was still a fully live,
writable flow on a separate `val_projects` entity, contradicting the unified `projects` table Module
1 was supposed to have consolidated everything onto.

**What changed**
- **Retired the legacy Validation Workspace** (DEC-024): deleted `routes/workspace.py`,
  `static/js/val_workspace.js`, all `vw-*` CSS, and the `view-val-workspace`/`view-val-project`/
  `vw-create-modal` markup. Removed the now-dead `create_val_project`/`get_all_val_projects`/
  `get_val_project`/`update_val_project`/`delete_val_project`/`add_val_audit_entry`/
  `get_val_audit_trail` functions from `database.py`. `val_projects`/`val_audit_trail` **tables** are
  untouched — historical data and `_migrate_val_projects()` remain intact; nothing writes to them
  anymore, for real this time.
- **New Project Workspace** (DEC-025): `static/js/project_workspace.js` + `view-project-workspace`,
  built on the existing Enterprise Workspace shell (DEC-017) with a new generic `.ws-tabs`/`.ws-tab`
  tab-strip component added to `workspace.css`. Ten tabs: Overview, Equipment, Documents (+ Insights
  strip), Risk Assessment, URS, Qualification, Validation Report, Tasks (placeholder), Approvals
  (placeholder), History.
- **Equipment/Documents embedded, not rewritten**: the standalone Equipment list and Documents views'
  markup was moved verbatim into the new workspace's tab panels (same element IDs) — zero changes to
  `equipment.js`/`documents.js`/`insights.js`'s rendering logic. Only `equipment.js`'s two navigation
  functions changed (`eqBackToList()` now calls `window.pwShowTab('equipment')`).
- **Risk/URS/Qualification/Validation Report entry points**: four new tabs give these
  backend-complete-but-previously-unwired suites a live entry point via the existing generic
  `window.showView()` helper + each suite's `initX()` bootstrap. Explicitly **not** project-filtered
  (those tables have no `project_id` column) — disclosed as a Known Issue, not silently implied.
- **Live project History**: `routes/projects.py` create/update/delete now log to the shared
  `qms_audit_trail` table (`record_type='project'`, reusing the DEC-010 polymorphic pattern) —
  previously nothing logged audit entries for the unified `projects` table at all.
- **Two pre-existing, unrelated bugs fixed as a side effect**: `window.selectProject` was never
  actually exposed on `window` by `projects.js`, silently breaking the Dashboard's "Recent Projects"
  card navigation; fixed alongside `dashboard.js::switchToProject` (now fetches the project record and
  reuses the same navigation path a sidebar click takes).
- Sidebar simplified: removed the "Documents & Insights" section (`nav-equipment`/`nav-documents`/
  `nav-insights`) entirely, alongside the Validation Workspace item.
- `tests/test_project_workspace.py` — 6 new tests (project audit-trail logging, the new `project`
  QMS record type, confirming `/val-projects` routes are gone), all passing alongside the existing
  142 (148 total).

---

## [Unreleased] — PharmaGPT v1.0 Module 2: Equipment as a First-Class Entity

**Sprint Name:** PharmaGPT v1.0 Module 2 (follows Module 1 — the "Phase 2 Module 1" Validation
Workspace/`projects` merge, `pharmagpt/routes/projects.py`/`test_projects_merge.py`)
**Status:** Complete in the working tree, browser-verified end-to-end (create/edit/delete equipment,
legacy import, document linking/unlinking, Equipment Profile tabs, AI-context bundle), full 142-test
regression suite passing, **not yet committed to git**.

**Summary:** Equipment is now a real database entity owned by a Project (architecture and core
functionality only, per the module's stated scope — Calibration/Preventive Maintenance/etc. are
explicitly not built, only prepared for). Replaces nothing — `projects.equipment_name/manufacturer/
model/equipment_id` (free text) and `pharmagpt/equipment/` (the static per-type Intelligence Engine
profile catalog) are both left untouched for backward compatibility. See
[DECISIONS.md](DECISIONS.md) DEC-023 for full architectural detail.

**Modules Added**
- `pharmagpt/equipment_database.py` — `equipment` (Basic/Installation/Qualification Information per
  the module spec, `project_id NOT NULL ON DELETE CASCADE`) + `equipment_documents` (polymorphic
  link to `kb_documents`/`documents`, never duplicates file content) schema + CRUD, plus
  `import_legacy_equipment()` (one-click consolidation from a project's legacy free-text fields) and
  `search_equipment()`.
- `pharmagpt/routes/equipment.py` — project-scoped list/create, single-record CRUD, search, type
  catalog (autocomplete against `pharmagpt/equipment/`), document link/unlink/list, legacy import,
  and an AI-context-bundle endpoint (architecture only — not wired into generation).
- `pharmagpt/services/equipment_service.py` — `get_equipment_context_bundle()` (data-assembly seam
  for a future AI document-generation integration, same "stub now, wire later" pattern as the
  vector-RAG stubs, DEC-008) and `get_equipment_type_catalog()`.
- `pharmagpt/static/js/equipment.js` + `static/css/equipment.css` — project-scoped Equipment list
  view (Add/Edit modal, legacy-import banner) and an Equipment Profile page built on the existing
  Enterprise Workspace shell (DEC-017) with Overview/Specifications/Documentation/Qualification/
  Validation History/Related Documents/Related Risk Assessments/Future Modules (placeholder) tabs.
  All top-level functions are `eq`-prefixed to avoid the cross-suite global-scope collisions this
  codebase is known to have (DEC-020).
- Additive-only changes to shared files: `database.py` (new `EQUIPMENT_SCHEMA` executescript call),
  `app.py` (blueprint registration), `templates/index.html` (sidebar nav item, two new views, two
  new modals, CSS/JS script tags, generalized `__ws_setActiveView` to a `Set` of workspace view IDs
  instead of a single hardcoded `"view-gen-doc"` string so the Equipment Profile can reuse the same
  Enterprise Workspace enter/exit contract).
- `tests/test_equipment_database.py`, `tests/test_equipment_routes.py` — 33 new tests, all passing
  alongside the existing 109 (142 total, zero regressions).

---

## [Unreleased] — Quality Management Suite (Phase 2: Change Control)

**Sprint Name:** QMS Phase 2 — Change Control
**Status:** Complete in the working tree, browser-verified against the live Gemini API, **not yet
committed to git**.

**Summary:** Adds the Change Control module, following the exact Phase 1 pattern (DEC-010/DEC-011/
DEC-012) — polymorphic shared tables via `record_type='change_control'`, no new shared
attachment/comment/audit/approval mechanism. Covers the full GMP change-control lifecycle: Equipment,
Facility, HVAC, Water System, Compressed Air, Steam, Electrical, Software, PLC, SCADA, MES, ERP,
Barcode System, Vision System, BMS, LIMS, Validation, SOP, Specification, Packaging, Warehouse,
Quality, Engineering, Production, Utilities, and IT changes; Major/Minor/Critical/Temporary/
Permanent/Emergency change types; a 13-stage workflow (Draft → Submitted → Initial Review → Impact
Assessment → Risk Assessment → Department Review → QA Review → Approval → Implementation →
Verification → Effectiveness Review → Closed) with rejection supported at every stage. See
[DECISIONS.md](DECISIONS.md) DEC-021 for full architectural detail.

**Modules Added**
- `pharmagpt/qms_change_control_database.py` — CRUD for change controls, impact assessment entries,
  implementation plan actions, and Deviation/CAPA links; reuses `qms_database.py`'s shared
  attachments/comments/audit-trail/approvals via `record_type='change_control'`.
- `pharmagpt/routes/qms_change_control.py` — `/qms/change-control` blueprint (CRUD, AI-assist
  endpoints, impact/action sub-resources, linking, approval/status-transition, report/DOCX export).
- `pharmagpt/services/qms_change_control_service.py` — AI orchestration via the existing
  `services/qms_shared.py::call_gemini()`/`parse_json_response()` (no new AI-calling convention);
  markdown report builder for print/DOCX export.
- `pharmagpt/prompts/qms_change_control_prompt.py` — 9 prompt builders (impact assessment,
  implementation plan/checklist, risk summary, rollback plan, regulatory impact, change
  justification, executive summary, verification summary, effectiveness review).
- `pharmagpt/static/js/qms_change_control.js` — list/dashboard/detail/tabs/wizard frontend, reusing
  every `qms_common.js` shared helper (fetch wrapper, badges, meta cache, shared attachments/
  comments/audit/approval panels).

**Enhancements**
- New "Change Control" nested sidebar section and `view-qms-change-control` view, wired the same way
  as Document Control/Deviation/CAPA.
- Unified QMS dashboard (`qms_common.js::initQMSDashboard()`) gained a fourth stat-card pair (Open
  Change Controls, Emergency Changes) and a fourth module section card.
- `routes/qms_common.py`'s shared `/qms/dashboard`, `/qms/meta`, and generic attachments/comments/
  audit-trail/approval endpoints now serve `record_type='change_control'` with zero new routes.

**Bug Fixes**
- None — this is new functionality, not a fix.

**Database Changes**
- New tables (appended to the existing `QMS_SCHEMA` in `qms_database.py`, same `init_db()` hook):
  `qms_change_controls`, `qms_change_control_impact`, `qms_change_control_actions`,
  `qms_change_control_links`.
- New `QMS_META` enums: `change_types`, `change_categories`, `change_control_statuses`,
  `change_control_impact_areas`.
- No changes to any existing table.

**API Changes**
- New blueprint: `qms_change_control` (`/qms/change-control`). Full endpoint list documented in the
  route module's own docstring; root-level `API.md` updated to match.
- `routes/qms_common.py`: `VALID_RECORD_TYPES`/`_GETTERS` extended with `change_control`; `/qms/
  dashboard` response gained a `change_control` block and four new `summary` keys (`total_changes`,
  `open_changes`, `pending_change_approvals`, `emergency_changes`).

**UI Changes**
- New "Quality Management → Change Control" sidebar entry; new `view-qms-change-control` view.
- `qms.css` gained badge-color variants for statuses Phase 1 didn't need (Critical, Emergency,
  Temporary, Permanent, Submitted, Rejected, Draft, Yes, No, Potential) — no new component classes,
  everything else reuses the existing `.qms-*` primitives.
- `qms_common.js`'s QMS dashboard subtitle and stat grid updated to mention/include Change Control.

**AI Improvements**
- 9 new AI-assisted flows (impact assessment, implementation plan/checklist, risk summary, rollback
  plan, regulatory impact, change justification, executive summary, verification summary,
  effectiveness review), all optional and routed through the shared `qms_shared.py::call_gemini()`.

**Performance Improvements**
- None specific to this release.

**Security Improvements**
- None specific to this release; e-signature approach matches the existing typed-name convention.

**Documentation Updates**
- This document set (`PROJECT_STATUS.md`, `ARCHITECTURE.md`, `DECISIONS.md` DEC-021,
  `RELEASE_NOTES.md`) plus root-level `API.md`, `DATABASE.md`, `CHANGELOG.md`.

**Regression Results**
- Full pytest suite: 101 passed (60 QMS tests including 16 new Change Control tests), 1 deselected
  (`slow` marker), zero regressions.
- Live browser verification (1440×900 desktop, Flask dev server, real Gemini API — not mocked):
  created a Major/Equipment change control (auto-numbered `CC-2026-0001`); ran the live AI Impact
  Assessment and accepted a suggestion into the record; ran the live AI Implementation Plan
  (8 steps) and bulk-accepted them; linked an existing Deviation and CAPA; drove the full 13-stage
  approval workflow start to finish (Draft → ... → Closed, badge updating live at each transition);
  verified the audit trail captured all 14 entries in order; verified the compiled markdown report
  and DOCX export (42KB, valid `.docx` MIME type); confirmed zero console errors and zero network
  failures throughout. One AI narrative call (Risk Summary) hit a transient `503 UNAVAILABLE` from
  the Gemini API under high demand — reproduced independently via a standalone script to confirm it
  was an external API availability blip, not a code defect; `call_gemini()`'s existing try/except
  handled it exactly as designed (empty string → the service's documented fallback text, no crash).
  Tablet breakpoint (768px) checked and confirmed to behave per the existing documented limitation
  (sidebar hides, no replacement nav).

**Tests Executed**
- 16 new tests appended to `tests/test_qms_database.py` (schema/CRUD/linkage/dashboard-stats) and
  `tests/test_qms_routes.py` (CRUD lifecycle, AI-assist routes with mocked Gemini, linking, the full
  approval status map including rejection, DOCX export, shared generic endpoints) — following the
  same combined-file convention Phase 1 used rather than new per-module test files.

**Deployment Notes**
- Not yet deployed — pending git commit and version bump. No new environment variables required.

**Known Issues**
- Deviation/CAPA do not yet surface a "Related Change Controls" tab in their own detail views — the
  reverse-lookup helper (`get_change_controls_for_record()`) exists and is queryable, but wiring it
  into `qms_deviations.js`/`qms_capa.js` was deliberately deferred per the "don't modify completed
  modules unless integration requires it" instruction. See DECISIONS.md DEC-021 Future Review.
- Same pre-existing items carried over from Phase 1: Risk/URS/Qualification/Validation Report
  sidebar navigation still unwired; exported-DOCX styling still pre-redesign navy; mobile/tablet
  navigation still absent.

**Next Sprint**
- Commit and version this release alongside the still-uncommitted Phase 1 QMS work, Enterprise
  Workspace layout, and Design System redesign already sitting in the working tree. Then proceed to
  QMS Phase 3 (Audit Management, Supplier Quality, Training Management, Complaint Management) per
  [PROJECT_STATUS.md](PROJECT_STATUS.md) → Roadmap, reusing this same pattern.

---

## [Unreleased] — Pre-Deployment UI Audit

**Sprint Name:** Pre-Deployment UI Audit
**Status:** Complete in the working tree, browser-verified, **not yet committed to git**.

**Summary:** Full navigation audit of every accessible module, wizard, dialog, modal, dashboard,
and workspace to verify deployment-readiness of the v3.0 design system refinement. Completed the
icon sweep DEC-019 left unfinished and found/fixed four genuine pre-existing/in-progress defects
that a hex/emoji-literal audit alone could not have caught. See [DECISIONS.md](DECISIONS.md)
DEC-020 for full detail. No backend, API, database, route, or business-logic changes.

**Modules Touched**
- `pharmagpt/static/js/risk.js`, `urs.js`, `qual.js`, `report.js`, `knowledge_base.js`,
  `gen_document.js`, `validation.js`, `validation_config.js`, `val_workspace.js`, `documents.js`,
  `qms_deviations.js`, `qms_capa.js`, `qms_documents.js`, `qms_common.js`, `workspace.js`,
  `projects.js` — completed the Lucide icon sweep (484 emoji → icons or removed from plain-text
  contexts).
- `pharmagpt/templates/index.html` — remaining Risk/URS/Qualification/Validation Report view-header
  emoji converted; send-button and sidebar-collapse-chevron Unicode glyphs converted to Lucide;
  fixed an HTML-vs-JS quote-escaping regression introduced mid-sweep (see Bug Fixes).
- `pharmagpt/static/js/risk.js` — renamed `renderWizardStep`→`riskRenderWizardStep` and
  `renderApprovalPanel`→`riskRenderApprovalPanel` (7 + 2 call sites) to resolve a global-scope
  name collision with `urs.js`.
- `pharmagpt/static/css/urs.css` — added missing `flex-direction: column; align-items: center` to
  `.urs-empty`.
- `pharmagpt/static/css/report.css` — property-aware light-theme conversion of the entire content
  area (~45+ declarations: stat cards, panels, tables, badges, forms, section editor, AI review,
  traceability matrix, approval timeline, toasts); added `flex: 1; width: 100%` to
  `.report-container`; fixed `background: var(--bg-primary)` (an undefined CSS variable) to
  `var(--bg)`.
- `pharmagpt/static/js/report.js` — same light-theme conversion applied to 28 matching inline
  `style="..."` occurrences.
- `pharmagpt/static/js/risk.js`, `validation.js` — fixed one `th{background:...;color:#FFF}` each
  in their print/export `<style>` templates (`window.printReport`, PDF export) where the automated
  sweep had wrongly lightened a header background that's supposed to stay dark (white text needs a
  dark fill) — restored to a solid dark header, consistent with the print-document convention.
- `pharmagpt/templates/index.html` — three inline hex colours (`#475569`/`#64748b`/`#f1f5f9`) in
  the Validation Report Suite's static markup, left over from before any redesign pass, replaced
  with the appropriate `var(--text-muted)`/`var(--navy)` tokens.

**Bug Fixes**
- **Risk Management Suite's "New Assessment" wizard and Approval panel were silently non-functional**
  — global function-name collision between `risk.js` and `urs.js` (`renderWizardStep`/
  `renderApprovalPanel`); URS's versions silently won since it loads second. Pre-existing, not
  introduced by DEC-018/DEC-019; never caught because Risk's sidebar nav is unwired.
- **URS empty-state layout** — `.urs-empty` rendered its icon/title/subtitle/button in a row instead
  of stacked and centered, because `urs.js` sets `display: flex` via inline style and the CSS class
  never declared `flex-direction: column`.
- **Validation Report Management Suite rendered in a pre-DEC-018 dark theme at ~70% of the intended
  width** — its entire content-area component set had never actually been visually verified through
  two prior colour-sweep passes (both correctly translated hex *values* without detecting the
  underlying dark-card *role* was wrong for a light theme), compounded by a missing `flex: 1` on
  `.report-container`.
- **Self-inflicted-and-self-caught regression: `MutationObserver` infinite loop.** During the icon
  sweep's JS-string-escaping fix, an earlier attempt used backslash-escaped single quotes
  (`\'icon\'`) inside `templates/index.html`'s *plain HTML* (not JavaScript), where `\'` is not a
  recognized escape and corrupts the `class`/`data-lucide` attribute values into literal garbage
  text. Caught via live DOM inspection before being considered part of this pass's final state;
  fixed by stripping the erroneous backslashes (396 occurrences) since that file's icon insertions
  are all in plain HTML, not JS strings.
- **Self-inflicted-and-self-caught regression: JS syntax errors from quote conflicts.** The initial
  icon-conversion script inserted double-quoted HTML attributes into JS strings that were themselves
  double-quoted (e.g. `icon: "<span class="icon"...`), a syntax error. Caught via `node --check` on
  every touched `.js` file (and every inline `<script>` block extracted from `index.html`); fixed
  with backslash-escaped single quotes, which are valid inside single-quoted, double-quoted, and
  template-literal JS strings alike.

**Database Changes**
- None.

**API Changes**
- None.

**UI Changes**
- See Modules Touched and Bug Fixes above.

**Regression Results**
- Manually navigated and screenshotted every accessible view in a live browser (1440×900 desktop):
  Dashboard, Knowledge Base, AI Assistant/Chat, Generate Document (all 5 pre-generation wizard
  steps), Documents, Insights, Validation Workspace (dashboard + New Validation Project modal),
  single-shot Validation Generator, Risk Management Suite (Dashboard, New Assessment wizard step 1,
  Library, Templates, Reports, Approval, AI Assistant), URS Management Suite (Dashboard, List, New
  wizard step 1), Qualification Suite (Dashboard, New Qualification form), Validation Report Suite
  (Dashboard, List, New Report wizard all 3 steps), QMS (Dashboard, Documents list + a real
  document's detail view across 2 tabs, Deviations list + a real deviation's Overview and AI
  Investigation tabs, CAPA list), and all 3 modals (New Project, New Validation Project, Add to
  Knowledge Base). Zero console errors after fixes. Confirmed via `preview_inspect` that computed
  colours/widths match the intended design system values. Tablet breakpoint (768px) checked and
  confirmed to behave per documented pre-existing limitation (sidebar hides, no replacement nav —
  out of scope to build).
- Codebase-wide automated scans confirm: 0 emoji remaining (was 484), 0 hex literals outside the
  v3.0 palette, 0 undefined CSS custom properties, 0 Bootstrap/FontAwesome references, all `.js`
  files pass `node --check`.

**Known Issues**
- Risk/URS/Qualification/Validation Report sidebar navigation remains unwired (pre-existing,
  unrelated to this audit).
- Exported-DOCX styling still uses pre-redesign navy (pre-existing, DEC-018).
- Mobile/tablet navigation (hamburger menu or equivalent) still does not exist — deliberately out
  of scope for this audit (would be a new feature, not a fix).
- This codebase's suite `.js` files are not IIFE-wrapped or namespaced, so the same class of
  global-function-collision bug fixed here (`risk.js`/`urs.js`) could recur between any two suites
  that happen to choose the same generic function name (`render*`/`show*`/`init*` are the
  highest-risk patterns already seen colliding, including one still-open instance between the
  global `showView()` and `val_workspace.js`'s own — see PROJECT_STATUS.md Known Issues).

**Next Sprint**
- Commit this audit alongside the still-uncommitted "Executive Office"/v3.0 redesign work already
  sitting in the working tree. No further design work planned unless new issues are reported.

---

## [Unreleased] — "Premium Enterprise" Design System Refinement v3.0

**Sprint Name:** Design System Refinement v3.0 (UI-only)
**Status:** Complete in the working tree, browser-verified, **not yet committed to git**.

**Summary:** Second-pass UI-only refinement on top of the "Executive Office" redesign below — an
exact business-attire hex palette, removal of the sidebar's Regulatory Scope badge section, and a
switch from Unicode-emoji iconography to a single consistent icon library (Lucide). No backend,
API, database, route, or business-logic changes. See [DECISIONS.md](DECISIONS.md) DEC-019.

**Modules Touched**
- `pharmagpt/static/css/style.css` — `:root` tokens repointed to the exact new palette (see
  PROJECT_STATUS.md → Current UI Theme); new `--soft-blue`/`--soft-green`/`--soft-amber`/
  `--content-max` tokens; new global Lucide-icon sizing rules (`svg.lucide`, per-component
  overrides); KPI card subtitle styling (`.dash-stat-sub`).
- `pharmagpt/static/css/workspace.css`, `risk.css`, `urs.css`, `qual.css`, `report.css`, `qms.css`
  — every hardcoded hex literal from the DEC-018 palette swept to the new v3.0 equivalents (873 +
  19 replacements via a throwaway Python script, two passes) — zero DEC-018-era hex literals remain.
- `pharmagpt/templates/index.html` — Regulatory Scope sidebar section deleted; sidebar/QMS-nav/
  Dashboard/modal-close/Generate-Document-workspace/Knowledge-Base/Validation-Workspace emoji
  replaced with `<span data-lucide="...">` placeholders; stale IBM Plex Sans `<link>` replaced with
  Inter (style.css already used Inter — this was a leftover oversight from DEC-018); Lucide CDN
  script + global `refreshIcons()`/`MutationObserver` auto-conversion mechanism added at the end of
  `<body>`; Dashboard KPI cards gained descriptive subtitles.
- `pharmagpt/static/js/dashboard.js` — KPI subtitle population (CAPA/Deviation "Needs attention" vs
  "All caught up", derived from existing `/dashboard/stats` counts, not fabricated); folder icon in
  Recent Projects swapped to Lucide.
- `pharmagpt/static/js/projects.js` — sidebar project-list folder icon and delete button swapped to
  Lucide.
- `pharmagpt/static/js/qms_common.js` — QMS unified dashboard's three section headers (Document
  Control/Deviation Management/CAPA) swapped to Lucide; `toggleQMSSection()` updated to swap the
  chevron icon's `data-lucide` value instead of overwriting `textContent`.

**Bug Fixes**
- Found and fixed during browser verification (not present before this sprint, introduced and
  fixed within the same session): the initial `MutationObserver`-based icon-conversion
  implementation re-triggered on the DOM mutations `lucide.createIcons()` itself produces (the
  replacement `<svg>` retains the `data-lucide` attribute), causing a genuine infinite loop that
  hung the browser tab with no console output. Fixed by disconnecting the observer for the duration
  of each `createIcons()` call.
- Removed a stale IBM Plex Sans Google Fonts `<link>` in `index.html` left over from DEC-018's
  Inter migration (style.css already loaded Inter via `@import`; the head `<link>` was dead weight
  pointing at the old font).

**Database Changes**
- None.

**API Changes**
- None.

**UI Changes**
- See Modules Touched above.

**Regression Results**
- Manually walked (browser, 1440×900 desktop viewport, via the project's `.claude/launch.json`
  local Flask server): Dashboard (KPI cards with new subtitles, Refresh button) → Knowledge Base →
  Generate Document (Enterprise Workspace shell, step 1 project selection) → QMS Dashboard (all
  three section headers with new icons). Confirmed via `preview_inspect` that sidebar background,
  KPI card border-top colour, and icon SVG stroke/size all resolve to the exact new palette values.
  No console errors after the MutationObserver fix.

**Known Issues**
- Risk/URS/Qualification/Validation Report suite-internal emoji (inside their JS modules and
  `templates/index.html` view headers) and the three QMS sub-views (Document Control/Deviation/CAPA
  detail screens) were not swept to Lucide — same spot-check limitation DEC-018 hit, since those
  suites' sidebar navigation is still unwired. See [DECISIONS.md](DECISIONS.md) DEC-019 Future
  Review.
- `docx_generator.py`/`doc_exporter.py`'s exported-DOCX styling still uses pre-redesign navy —
  unchanged by this pass, still an open follow-up from DEC-018.

**Next Sprint**
- Commit and version this refinement alongside the still-uncommitted "Executive Office" redesign,
  Enterprise Workspace layout, and QMS Phase 1 work already sitting in the working tree. Consider
  the Lucide icon sweep and exported-DOCX styling follow-ups noted above.

---

## [Unreleased] — "Executive Office" Design System Redesign

**Sprint Name:** Design System Redesign (UI-only)
**Status:** Complete in the working tree, browser-verified, **not yet committed to git**.

**Summary:** Complete visual redesign of PharmaGPT's UI from the earlier navy/blue enterprise
theme to a warm, premium "business-attire" palette (Soft White, Warm Ivory, Stone, Sand, Beige,
Taupe, Walnut Brown, Charcoal, Soft Olive/Sage accents), per an explicit UI-only mandate: no
backend, API, database, route, or business-logic changes. See
[DECISIONS.md](DECISIONS.md) DEC-018 for the full approach and rationale, and
`docs/DESIGN_SYSTEM.md` (rewritten to v2.0) for the new token/component reference.

**Modules Touched**
- `pharmagpt/static/css/style.css` — `:root` tokens redefined (Warm Charcoal sidebar, Walnut Brown
  primary/buttons, Muted Sage accent, warm neutral backgrounds/borders/text tiers, new
  `--bg-secondary`/`--radius-lg`/`--radius-input` tokens); header/top-bar rebuilt white+minimal
  with a pill-shaped Gemini status badge and a secondary-styled Clear Chat button; sidebar active
  state gained a white left-indicator bar; dashboard KPI cards and other card components (
  `.dash-card`, `.insights-stat-card`, `.vw-project-card`, `.val-summary-card`,
  `.vw-overview-card`) bumped to 14px radius with softer borders/shadows; tables given distinct
  zebra vs. hover tints and a rounded header; Google Fonts `@import` switched from IBM Plex Sans to
  Inter.
- `pharmagpt/static/css/workspace.css`, `risk.css`, `urs.css`, `qual.css`, `report.css`, `qms.css`
  — every hardcoded hex/`rgb()`/`rgba()` colour literal that bypassed the shared `:root` tokens
  was swept to the new warm palette (883 hex + 80 rgb replacements across all 7 files combined).
  `risk.css`'s own small `--risk-*` severity token block repainted to the new palette.
  `.btn-urs-primary` and `.btn-qual-primary` (previously sharing the same literal hex as the
  general accent colour) were repointed to `var(--blue-light)` (Walnut Brown) so every suite's
  primary button now matches, after the shared `--accent` token was deliberately repointed to
  Muted Sage (a distinct accent, not a primary-button colour).
- `pharmagpt/static/js/*.js` (`dashboard.js`, `documents.js`, `gen_document.js`, `insights.js`,
  `qms_common.js`, `qual.js`, `report.js`, `risk.js`, `urs.js`, `validation.js`,
  `validation_config.js`) — inline-style hex colours (badges, status pills, doc-type accent
  colours) swept with the same translation table for full consistency between CSS and
  JS-rendered elements.

**Bug Fixes**
- None (this was a colour/typography/radius redesign, not a functional bug-fix sprint).

**Database Changes**
- None.

**API Changes**
- None.

**UI Changes**
- See Modules Touched above. Full before/after token reference in `docs/DESIGN_SYSTEM.md`.

**Regression Results**
- Manually walked (browser, 1440×900 desktop viewport): Dashboard (KPI cards, recent activity,
  system health) → Knowledge Base → AI Assistant chat → New Project modal → Generate Document
  (Enterprise Workspace shell, step progress) → Validation Workspace → QMS Dashboard → QMS Document
  Control → QMS Deviation Management → QMS CAPA. Risk Management, URS Management, Qualification,
  and Validation Report suites were spot-checked by temporarily forcing their views visible
  (their sidebar navigation remains unwired — a pre-existing gap, see Known Issues below, not
  introduced or fixed by this sprint) and confirmed to render consistently with the new palette.
  No console errors observed at any point.

**Known Issues**
- `docx_generator.py`/`doc_exporter.py`'s exported-DOCX styling (navy headings/table headers) was
  intentionally left unchanged — out of scope for a UI-only redesign. The on-screen document
  viewer and the exported `.docx` file will look slightly different until a follow-up repaints the
  Python-generated document styling to match.
- Risk/URS/Qualification/Validation Report sidebar navigation remains unwired (pre-existing gap,
  unrelated to this sprint — see [PROJECT_STATUS.md](PROJECT_STATUS.md) → Known Issues).

**Next Sprint**
- Commit and version this redesign alongside the still-uncommitted Quality Management Suite Phase
  1 and Enterprise Workspace Layout work already sitting in the working tree (see Current Sprint in
  [PROJECT_STATUS.md](PROJECT_STATUS.md)). Consider the exported-DOCX styling follow-up noted
  above.

---

## [Unreleased] — Enterprise Workspace Layout (Generate Document Redesign)

**Sprint Name:** Validation & Usability Testing Sprint
**Status:** Complete in the working tree, tested, **not yet committed to git**.

**Summary:** Redesigned the Generate Document module into a full-screen "Enterprise Workspace"
that no longer renders behind/inside the Dashboard. In the course of root-causing the reported
symptoms (Dashboard visible above the wizard, large blank white area, no professional way back to
the project), found and fixed a pre-existing HTML structural bug: `templates/index.html`'s
`.app-body` flex container was closed one `<main>` block too early (right after the old Validation
Document Generator view), so every view defined after that point — Generate Document, all Risk
Management views, all URS views, Qualification, Validation Report, and all QMS views — rendered
outside the sidebar layout entirely. This is the actual root cause of the reported blank-space /
missing-sidebar symptoms, and it affected more than just Generate Document (verified live on the
QMS Dashboard). No AI generation logic, APIs, or database schema were touched.

**Root Cause**
- `templates/index.html`: stray `</div>` closed `.app-body` immediately after `view-validation`
  instead of after the last view (`view-qms-capa`). Moved the closing tag to the correct location.

**Modules Added**
- `pharmagpt/static/css/workspace.css` — reusable Enterprise Workspace shell (`.ent-workspace`,
  `.ent-ws-header`, `.ent-ws-toolbar`, `.ent-ws-breadcrumb`, `.ent-ws-progress`, `.ent-ws-body`).
- `pharmagpt/static/js/workspace.js` — `window.Workspace` helper: `enter()`/`exit()` (hides the
  global top header while a workspace is open), `renderBreadcrumb()`, `renderProgress()`,
  `confirmDialog()` (styled Yes/No modal reusing existing `.modal`/`.btn-*` tokens).

**Enhancements**
- Generate Document (`view-gen-doc` / `gen_document.js`) is the first module to adopt the shell:
  dark header with current-project and current-document-type tags, breadcrumb (Dashboard > Project
  > Generate Document > Step), toolbar (Back to Project / Save Draft / Cancel), 6-step progress
  bar — all now backed by the reusable `Workspace` helper instead of Generate-Document-specific
  markup manipulation.
- "Back to Project" and "Cancel" now show a styled confirmation dialog ("Leave Generate Document?"
  / "Discard changes?") instead of a native browser `confirm()`, and the same guard now also fires
  when the user navigates away via a direct sidebar click mid-wizard (previously only the wizard's
  own buttons were guarded).
- Global top header (brand bar, Gemini status badge, Clear Chat) is hidden while any Enterprise
  Workspace is open (`body.ent-ws-active`), so only the sidebar remains — eliminating the
  double-header look and reclaiming the vertical space it used.

**Bug Fixes**
- Fixed the `.app-body` HTML nesting bug described above (affects Generate Document, Risk, URS,
  Qualification, Validation Report, and QMS views).

**Database Changes**
- None.

**API Changes**
- None. `Save Draft` still posts to the existing `POST /validation/save` endpoint unchanged.

**UI Changes**
- See Enhancements above. `style.css`'s Generate Document section was trimmed to wizard-body-only
  rules (`.gd-panel`, `.gd-step-content`, step buttons); the shell chrome rules moved to
  `workspace.css`.

**Regression Results**
- Manually walked: Dashboard → Generate Document → project selection → doc type selection →
  Next/Back through all 6 steps → Save Draft (confirmed `POST /validation/save` → 201) → sidebar-
  click-away guard (styled dialog, Stay/Leave both verified) → Cancel (styled "Discard changes?"
  dialog) → Back to Project (restores project + Chat view) → re-opened Generate Document (active
  project pre-selected, as before) → QMS Dashboard (confirmed same root-cause fix resolved its
  identical layout bug, no regressions) → tablet/mobile viewport resize (chrome wraps without
  breaking, consistent with the project's existing desktop-first stance). No console errors
  observed at any point.

**Known Issues**
- Generate Document (v0.9) still has no "resume a saved draft into the wizard" feature — Save
  Draft persists a structured-JSON snapshot to `generated_documents`, but there is no load-back-
  into-wizard flow. Pre-existing gap, not introduced or fixed by this sprint (out of scope: no
  business-logic changes were made).
- The Validation Workspace's own `.vw-ws-topbar` back-button pattern was not unified with the new
  `.ent-workspace` shell in this sprint, to keep the change scoped to Generate Document as
  instructed; see [DECISIONS.md](DECISIONS.md) DEC-017 Future Review.

**Next Sprint**
- Apply the Enterprise Workspace shell to Risk/URS/Qualification/Validation Report once their
  sidebar navigation is wired, and to QMS Phase 2/3 modules as they're built.

---

## [Unreleased] — Quality Management Suite (Phase 1)

**Sprint Name:** QMS Phase 1
**Status:** Complete in the working tree, tested, **not yet committed to git**.

**Summary:** Adds PharmaGPT's second major pillar — Quality Management — parallel in scope to the
existing Validation pillar. Three modules: Document Control, Deviation Management, CAPA, built on
new shared polymorphic tables for attachments, comments, audit trail, and approvals.

**Modules Added**
- Document Control (SOP/Protocol/Specification/etc. lifecycle, auto-numbering, versioning,
  training, distribution)
- Deviation Management (severity/category classification, investigation lifecycle, impact
  assessment)
- CAPA (corrective/preventive actions, escalation, effectiveness checks)

**Enhancements**
- Unified cross-module QMS dashboard and nested "Quality Management" sidebar section
- AI Investigation Assistant (Fishbone/Ishikawa + 5-Why + timeline + root cause in one call)
- AI regulatory compliance review for Document Control
- AI CAPA-seed suggestions with one-click create-and-link from a Deviation
- AI Quality Trend Summary across CAPAs and Deviations
- Deviation ↔ CAPA bidirectional linkage (`qms_deviation_capa_link`)

**Bug Fixes**
- `database.py::get_dashboard_stats()` now counts `pending_capas`/`pending_deviations` from the
  real `qms_capas`/`qms_deviations` tables instead of stale legacy `generated_documents` rows.

**Database Changes**
- New tables: `qms_documents`, `qms_document_versions`, `qms_document_distribution`,
  `qms_document_training`, `qms_deviations`, `qms_deviation_investigation`,
  `qms_deviation_impact`, `qms_deviation_capa_link`, `qms_capas`, `qms_capa_actions`,
  `qms_capa_effectiveness`, plus shared polymorphic `qms_attachments`, `qms_comments`,
  `qms_audit_trail`, `qms_approvals` (keyed on `record_type`/`record_id`).

**API Changes**
- New blueprints: `qms_common` (`/qms`), `qms_documents` (`/qms/documents`), `qms_deviations`
  (`/qms/deviations`), `qms_capa` (`/qms/capa`). Full endpoint list in root-level `API.md`.

**UI Changes**
- New "Quality Management" nested sidebar section; new `qms.css` (reuses existing `.modal`/
  `.badge`/`.form-field`/`.btn-primary` tokens rather than redefining them); 4 new JS modules
  (`qms_common.js`, `qms_documents.js`, `qms_deviations.js`, `qms_capa.js`).

**AI Improvements**
- 7 new AI-assisted flows across the three modules (draft generation, compliance review,
  investigation assistant, impact suggestions, CAPA suggestions, effectiveness suggestions, trend
  summary), all routed through a new shared `qms_shared.py::call_gemini()`/`stream_gemini()`.

**Performance Improvements**
- None specific to this release.

**Security Improvements**
- None specific to this release; e-signature approach matches the existing typed-name convention
  used by Risk/Qual approvals (no PKI — consistent, not a regression).

**Documentation Updates**
- Added `docs/QMS_PHASE1.md`. Updated root-level `API.md`, `DATABASE.md`, `CHANGELOG.md`,
  `PROJECT_STATUS.md`, `docs/ROADMAP.md` (all currently uncommitted alongside the code).

**Regression Results**
- Full suite passes: 83 tests (42 new QMS tests + ~41 pre-existing), excluding `-m slow`.

**Tests Executed**
- `tests/test_qms_database.py`, `tests/test_qms_routes.py` (new); full existing suite re-run for
  regression.

**Deployment Notes**
- Not yet deployed — pending git commit and version bump. No new environment variables required.

**Known Issues**
- See [PROJECT_STATUS.md](PROJECT_STATUS.md) → Known Issues (pre-existing security/perf items from
  the v0.7 code review remain open; this release does not address them).

**Next Sprint**
- Commit and version this release, then proceed to QMS Phase 2 (Change Control, Non-Conformance,
  OOS/OOT) or the remaining v0.8 Validation Workspace items, per
  [PROJECT_STATUS.md](PROJECT_STATUS.md) → Roadmap.

---

## [v0.9.8] — 2026-07-02

**Sprint Name:** Document Intelligence Engine and Validation UI improvements
**Commit:** `684ca7d`

**Summary:** Small follow-up release tightening the Document Intelligence Engine (added the
previous day) and improving validation-document generation UI.

**Enhancements**
- `pharmagpt/services/extraction/pipeline.py` refinements
- `pharmagpt/static/js/gen_document.js` — generated-document view/export UI improvements
- `.claude/launch.json` added for local dev server configuration

**Database Changes**
- Minor additions in `database.py` (documented in root `DATABASE.md`)

**Deployment Notes**
- `render.yaml` updated

---

## [2026-07-01 (b)] — Enterprise Document Processing Engine

**Commit:** `a6d6f2f`
**Summary:** Full rewrite of the document extraction subsystem — the single largest architectural
change to date (24 files changed). Replaces the earlier synchronous, single-engine
(`pdfplumber`-only) extractor with an async, multi-engine, timeout-bounded, quality-scored
pipeline. Triggered by a real production incident: a 48-page/1.43MB manual uploaded on Render
caused a synchronous in-request extraction call to exceed the gunicorn worker timeout, producing a
`SIGKILL` and an HTTP 500.

**Modules Added**
- `services/extraction/` package: `base.py`, `pipeline.py`, `registry.py`, `pdf_engines.py`,
  `simple_engines.py`, `stats.py`
- `services/document_processor.py`, `services/job_runner.py` (`ThreadPoolJobRunner`)
- `logging_config.py`

**Removed**
- `services/extractor.py`, `services/pdf_reader.py` (superseded, not kept as fallback)

**Database Changes**
- Additive columns on `document_text`/`kb_documents`: `extraction_progress_current`,
  `extraction_progress_total`, `extraction_engine`, `quality_score`, `extraction_seconds`,
  `pages_failed`, `error_message`. New status values: `pending`, `processing`, `partial`, `failed`.

**API Changes**
- New: `GET /documents/<id>/status`, `POST /documents/<id>/retry`, `GET
  /kb/documents/<id>/status`, `POST /kb/documents/<id>/retry`.

**Performance Improvements**
- 100-page PDF target <20s, 200-page target <40s — both met with large margin (measured: 200
  pages ~0.7s with `pypdf` primary engine; 1000-page stress fixture ~9s).

**Documentation Updates**
- Added `SYSTEM_ARCHITECTURE_DOCUMENT_PROCESSING.md` (root-level, full architecture writeup).

**Tests Executed**
- New: `test_document_processor.py`, `test_job_runner.py`, `test_pdf_engines.py`,
  `test_pipeline.py`, `test_routes_upload_async.py`; new fixture generator
  `tests/fixtures/generate_fixtures.py`.

**Known Issues**
- OCR remains a placeholder (`OCRPlaceholderEngine` always raises); password-protected PDFs still
  fail extraction; CPython cannot force-kill a hung extraction thread (abandoned, not terminated).

---

## [2026-07-01 (a)] — Dashboard & Workspace UX

**Commit:** `a3dd72e`
**Summary:** Improved dashboard navigation and project workspace UX (no schema/API changes
recorded).

---

## [2026-06-30] — Validation Report Management Suite

**Commit:** `2106f81`
**Summary:** Largest single commit in the project's history — ~19,338 lines added, introducing
four full backend+frontend suites in one release: Risk Management, URS Management, Qualification
(IQ/OQ/PQ), and Validation Report.

**Modules Added**
- Risk Management Suite (`risk_database.py`, `routes/risk.py`, `services/risk_service.py`,
  `prompts/risk_prompt.py`, `risk.css`/`risk.js`)
- URS Management Suite (`urs_database.py`, `services/urs_requirement_library.py`,
  `routes/urs.py`, `services/urs_service.py`, `urs.css`/`urs.js`)
- Qualification Suite (`qual_database.py`, `routes/qual.py`, `services/qual_service.py`,
  `qual.css`/`qual.js`)
- Validation Report Suite (`report_database.py`, `routes/report.py`,
  `services/report_service.py`, `report.css`/`report.js`)

**API Changes**
- New blueprints registered at `/risk`, `/urs`, `/qual`, `/report`.

**Known Issues (still open)**
- Sidebar navigation containers for all four suites exist in `templates/index.html` but are
  `display:none` — no live entry point in the current build.

---

## [2026-06-29] — Render Deployment Fixes

**Commits:** `e0a8094`, `02b42b2`, `5aa934a`, `a7fe878`, `196c7c0`, `75188a1`
**Summary:** Series of fixes to package imports (config, database, routes) and requirements to
make the app deployable on Render; completed the package import migration.

---

## [2026-06-28] — v0.9.5 Beta Release

**Commit:** `8c73eaa`
**Summary:** Beta stabilization milestone following the v1 refactor and code review.

---

## [2026-06-27 (e)] — Refactor v1 / Stable Foundation

**Commits:** `b87f396` (Refactor v1), `53eccc9` (Code Review v1), `8f33b56` (Project Documentation
v1)
**Summary:** Stabilization pass — code review (`docs/CODE_REVIEW.md`), refactor, and initial
project documentation set (predecessor to this PROJECT_MEMORY set).

---

## [0.8.0] — 2026-06-27 (d) — Validation Workspace & Home Dashboard

**Commits:** `1acf3f7` (Validation Workspace UI + SQLite), `36aabd1` (Home Dashboard)
**Summary:** Introduced `val_projects`/`val_audit_trail` tables and initial Validation Workspace
UI, plus a home dashboard with system overview stats.

---

## [0.7.0] — 2026-06-27 (c) — Knowledge Base

**Commit:** `c9a5944`
**Summary:** Project-independent Knowledge Base — permanent document library, 8 folders (SOP,
Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others), metadata
(title, folder, tags, version, effective date, review date), upload modal, 4 combinable search
filters, folder sidebar with counts, detail/preview panel with overdue-review highlighting.

**Database Changes**
- New table: `kb_documents`.

**API Changes**
- 7 new routes under Knowledge Base.

**UI Changes**
- New `knowledge_base.js` module.

---

## [0.6.0] — 2026-06-27 (b) — part of "Foundation with Projects, Documents and Validation
Framework"

**Commit:** `d7a50f7`
**Summary:** Validation Document Generator — 11 document types (URS, DQ, FAT, SAT, IQ, OQ, PQ,
FMEA, CAPA, Deviation, Change Control), 4-step wizard, config-driven (`validation_config.js`),
SSE generation at `temperature=0.3`, DOCX export via a custom Markdown→DOCX state machine,
client-side PDF export (`window.print()`), Save to Project.

**Database Changes**
- New table: `generated_documents`.

---

## [0.5.0] — AI Document Intelligence (v1)

**Summary:** Automatic text extraction on upload (pdfplumber/python-docx/openpyxl — the original
synchronous, single-engine extractor later replaced by the Document Intelligence Engine rewrite),
keyword search (400-word chunks, 60-word overlap, Jaccard scoring), "Use Project Documents"
context injection into chat (max ~2,500 words), sources strip, Document Insights panel, and RAG
stub functions (`generate_embedding`, `upsert_to_vector_store`, `vector_search`) reserved for a
future vector-search upgrade.

**Database Changes**
- New table: `document_text`.

---

## [0.4.0] — Document Management

**Summary:** Upload PDF/DOCX/XLSX/TXT (50MB max), drag-and-drop, inline view/download, delete with
disk removal.

**Database Changes**
- New table: `documents`.

---

## [0.3.0] — Project Management

**Summary:** Create/list/delete projects, per-project chat history persisted to SQLite, in-memory
history cache rebuilt from DB on access, "Clear History" action.

**Database Changes**
- New tables: `projects`, `messages`.

---

## [0.2.0] — PharmaGPT Web App

**Summary:** Flask SPA with dark sidebar theme, SSE streaming
(`generate_content_stream`), `PHARMA_SYSTEM_PROMPT` (Senior Pharma Validation Engineer persona),
regulatory scope established: USFDA 21 CFR Part 11, EU GMP Annex 11, MHRA, WHO-GMP, CDSCO, TGA.

---

## [0.1.0] — Foundation

**Summary:** `hello.py` — original CLI proof-of-concept chat client, `gemini-2.5-flash`
integration, streaming responses, retry logic, conversation memory. Kept in the repository as a
frozen historical artifact; not part of the running Flask app.

# Phase 5 — Enterprise UX Polish: Implementation Report

**Date:** 2026-07-23
**Scope:** UI/UX-only enterprise polish pass over PharmaGPT's single-page
app. No backend, database, route, RBAC, permission, authentication, or
business/validation logic was modified. No AI implementation. No new
business features or workflow redesign — matching the same guardrail every
prior phase report (`PHASE_1`–`PHASE_4`) documents.

**Files changed:** confined entirely to `pharmagpt/templates/index.html`,
`pharmagpt/static/css/*`, and `pharmagpt/static/js/*`. Verified continuously
throughout implementation (not just at the end) via a SHA-256 hash
tripwire over every file under `pharmagpt/routes/`, `pharmagpt/auth/`,
`pharmagpt/*.py`, `pharmagpt/services/`, and `migrations/` — snapshotted
before the first edit and re-checked after every batch; it never once
detected a change. This repository already had substantial unrelated,
pre-existing uncommitted work in flight (an RBAC/companies feature and the
Phase 4 nav report) when this phase began — none of it was touched.

---

## 1. Screens Updated

New, additive components — every one reuses pre-existing endpoints, reads
pre-existing global state (`window.activeProject`, `window.PharmaAuth`,
`window.showView`), and follows the codebase's own conventions (`auth.js`'s
IIFE + `STORAGE_KEY` shape for anything stateful, `qms_common.js`'s "shared
helper functions" shape for stateless renderers):

| File | Purpose |
|---|---|
| `static/js/ui_states.js` + `ui_states.css` | Shared `PharmaUI.skeleton/emptyState/errorState` renderers — the foundation every other batch builds on |
| `static/js/header.js` + `header.css` | Global header: Workspace/Company/Project chips, search + notifications mount points |
| `static/js/search.js` | Federated global search across 11 existing list/search endpoints |
| `static/js/notifications.js` | Notification center derived from existing dashboard aggregate endpoints |
| `static/js/favorites.js` | Browser-local Favorites (Projects/Equipment/SOPs/Validation Documents) |
| `static/js/recent_items.js` | Browser-local Recently Opened tracking |
| `static/js/error_pages.js` + `error_pages.css` | Full-page 403/404/500/Network Error/Permission Denied states |

Existing screens modified in place:

- **Global Header** (`index.html` `<header>`) — every existing id
  (`#header-breadcrumb`, `#btn-switch-workspace`, `#user-badge`,
  `#btn-assume-context`, `#btn-logout`, `#assume-context-banner`) was
  preserved as a literal, never-recreated DOM node; new chips/search/bell
  were inserted as siblings. Verified live: `admin_assume_context.js`'s
  listener on `#btn-assume-context` and `auth.js`'s `showUserBadge()` both
  still work identically to before this phase.
- **Home Dashboard** (`index.html` `#view-dashboard`, `dashboard.js`) —
  expanded from 7 stat cards to include Equipment, Controlled Documents,
  Change Controls, and Validation Status (all backed by pre-existing
  `/qms/dashboard`, `/urs/dashboard`, `/qual/dashboard`, `/report/dashboard`,
  `GET /equipment`), plus a Quick Actions panel, a Favorites card, and a
  Recent Items card (the latter two gracefully hidden when empty).
- **QMS Attachments/Comments/Audit-Trail/Approval panels**
  (`qms_common.js`) — shared by every CAPA/Deviation/Change-Control/Document
  detail screen — retrofitted once, fixing all four screens simultaneously.
- **List and detail views** across `qual.js`, `risk.js`, `qms_capa.js`,
  `qms_deviations.js`, `qms_change_control.js`, `qms_documents.js`,
  `knowledge_base.js`, `equipment.js`, `insights.js`, `validation.js`,
  `documents.js`, `project_workspace.js` — loading/error states upgraded to
  `PharmaUI`.
- **Favorites/pin controls** added to the Project sidebar list
  (`projects.js`), Equipment Library rows (`equipment.js`), and Knowledge
  Base SOP/Validation-folder rows (`knowledge_base.js`).

---

## 2. UX Improvements

- **Consistent loading states.** A shared shimmer-skeleton (`ui_states.css`)
  replaced bare `"Loading…"` text across the Dashboard, the four QMS shared
  panels, and the primary list/dashboard views of Qualification, Risk,
  Equipment, Knowledge Base, Documents, Insights, and Project History —
  wherever a screen genuinely had **no** loading indicator (or only bare
  text) before. Several suites (Risk, URS, Report, Qualification's
  `-empty` states, most QMS list loaders) already had a real spinner or a
  decent icon+text empty state before this phase; those were **left as-is**
  rather than rewritten for the sake of it, since replacing already-good UX
  with a different-but-equivalent pattern is churn, not improvement.
- **Consistent, actionable error states.** Every upgraded error path now
  shows an icon, a clear message, and — wherever the failing call has an
  obvious retry target — a **"Try again"** button that re-invokes the exact
  same load function. Verified live against a real 403 (QMS Dashboard) and
  a real record-fetch failure (CAPA list): both render the new
  `ui-error-state` component with a working retry button.
- **Dashboard** now surfaces Equipment, Controlled Documents, Change
  Controls, and Validation Status alongside the existing Projects/CAPA/
  Deviation cards — no calculation changed, every number comes from a
  pre-existing aggregate endpoint already used elsewhere in the app.
- **Quick Actions** launch the exact same modals/screens their equivalent
  sidebar item or "+ New" button already opens (verified function-by-
  function by reading each target module — no new parameter was ever
  passed to a create/open function that didn't already accept it).
- **Global search** federates 11 existing search-capable endpoints
  (confirmed via `request.args.get` in each `routes/*.py` file) into one
  grouped, debounced dropdown. `GET /projects` has no server-side keyword
  filter, so Projects are filtered client-side after fetching the
  (typically small, per-company) list — the one place this phase filters
  client-side instead of via a query param, exactly as the original spec
  anticipated.
- **Notifications** derive Approval-Pending / Review-Pending /
  Document-Published items from fields **already present** in
  `/qms/dashboard`, `/urs/?status=`, `/qual/?status=`, and
  `/risk/assessments?status=` responses — no new endpoint, no new field.
- **Favorites & Recent Items** are pure `localStorage`, mirroring
  `auth.js`'s own storage convention exactly. Verified live: pinning
  persists across a full reload; clearing storage makes both Dashboard
  sections disappear cleanly rather than rendering broken markup.

---

## 3. Two Honest Omissions (documented, not silently dropped)

The original spec named two things this phase could not build honestly
without inventing data or bypassing RBAC:

1. **"Project Assigned" notifications.** No assignment/ownership-change
   tracking exists anywhere in the schema. Rather than fabricate events,
   this category is simply not rendered — `notifications.js` only emits
   Approval Pending, Review Pending, and Document Published, all backed by
   real fields.
2. **"Current Company" name in the header, for non-Super-Admin users.**
   `TenantContext` (`pharmagpt/auth/context.py`) carries only `company_id`
   (a UUID) for every role; the only endpoints that resolve a name
   (`GET /auth/companies`, `GET /companies`) are both
   `@require_role("super_admin")`. A `company_admin`/`user` therefore sees
   a role label ("Company Admin", "User") in the Company chip instead of a
   fabricated name. A Super Admin with an active Assume-Context grant gets
   the real `assumed_company_name` already returned by the existing
   `/auth/assume-company` flow — verified live as the `jugalr@pharmagpt.ai`
   super-admin test account.

---

## 4. Accessibility Improvements

- App-wide `:focus-visible` outline (`style.css`) covering every button,
  link, input, and the new custom interactive elements (sidebar items,
  header chips, workspace-selector cards) — keyboard/Tab focus now has a
  consistent, visible indicator everywhere; mouse clicks are unaffected
  since `:focus-visible` (unlike `:focus`) doesn't fire on pointer
  interaction.
- `aria-label` added to every new icon-only control (notifications bell —
  plus `aria-haspopup`/`aria-expanded` — global search input, logout
  button, and the new Favorite/pin toggle buttons, which also carry
  `aria-pressed` reflecting their current state).
- **Known pre-existing limitation, not introduced by this phase:** the
  sidebar's navigation items are `<div class="sidebar-item">` rather than
  semantic `<button>`/`<a>` elements, so they aren't natively
  keyboard-focusable or screen-reader-announced as controls. Retrofitting
  this properly means adding `role="button" tabindex="0"` plus Enter/Space
  key handlers to every nav item across the whole sidebar tree — a
  meaningfully larger, higher-risk change than this phase's budget allowed
  for safely. Flagged here as the top follow-up accessibility item.

---

## 5. Responsive / Visual Consistency

- Confirmed (by reading each per-suite CSS file, not assuming) that the
  QMS/Risk/URS/Qualification/Report stat grids already use
  `grid-template-columns: repeat(auto-fit/auto-fill, minmax(...))`, which
  reflows reasonably at intermediate widths on its own — so this phase
  focused effort on the **real** gaps found by inspection rather than
  adding redundant breakpoints everywhere:
  - `qms.css`'s `.qms-table` (CAPA/Deviation/Change-Control/Document lists)
    had no horizontal-scroll safety net, unlike Risk/URS/Qualification/
    Report, which already wrap their tables in a `.xxx-table-wrapper`
    class. Fixed by making `.qms-body` scroll horizontally below 1024px
    and giving `.qms-table` a `min-width`, so a wide table degrades to a
    scrollable region instead of clipping or breaking the layout.
  - Added laptop-width (`≤1366px`) body-padding easing to `qms.css`,
    `urs.css`, and `qual.css`, matching the reduced-padding treatment the
    Dashboard's own `style.css` breakpoints already use.
- New components (header, search, notifications, error pages, skeleton/
  empty/error states) all consume only existing `style.css` design tokens
  (`--surface`, `--border`, `--divider`, `--radius*`, `--text-muted`,
  `--blue-light`, `--error`, `--warning`, `--success`, `--info`) — no new
  colors were introduced anywhere in this phase.
- Mobile behavior (sidebar collapse at ≤768px) was left untouched per the
  spec's explicit instruction to "maintain current mobile behavior."

---

## 6. Error Pages — What They Cover and Why

Five full-page states (403/404/500/Network Error/Permission Denied) were
built as reusable components (`window.PharmaErrorPages.show(kind, opts)`),
but **deliberately not wired to every failed fetch.** This app's suites
already degrade gracefully per-card/per-panel — a pattern this phase
extended in §2, not replaced — and that's the right UX when one card fails
while the rest of a screen still works. A full-page takeover is reserved
for failures that are global, not local to one panel:

- **Network Error** is wired to two real triggers: the browser's own
  `online`/`offline` events, and a genuine fetch-rejection (DNS/connection
  failure, as opposed to a non-2xx HTTP response) detected in
  `qms_common.js`'s `qmsFetch` — the one already-shared fetch wrapper every
  QMS module uses. Both were verified live (dispatching a synthetic
  `offline` event correctly shows the page; `online` correctly restores
  the previous view).
- **403 / 404 / 500 / Permission Denied** are built, styled, and verified
  (dynamic message injection and retry-button rebinding both tested live),
  but have no existing call site that needs them today — this app's
  per-record 403/404 cases are already handled inline (§2), and Super
  Admin's routine no-tenant-context 403 (a known, pre-existing condition
  documented in the Phase 4 report) is exactly the kind of case that
  should **not** become a full-page interruption. They're available via
  `window.PharmaErrorPages.show(...)` for any future call site — e.g. a
  role guard on the Administration screens — that needs one.

---

## 7. Regression Summary

Verified live against the running dev server
(`flask --app pharmagpt.app run`, port assigned by the preview tool),
logged in as the project's configured Super Admin account, after every
batch (not just at the end):

| Check | Result |
|---|---|
| Routes changed | ✅ None — `git diff` scope confined to `templates/`/`static/`; SHA-256 tripwire over every backend-sensitive path never triggered |
| Backend/DB/business logic changed | ✅ None |
| RBAC changed | ✅ None — `#btn-assume-context` still opens the picker, `#assume-context-banner` still renders, Administration nav visibility unchanged |
| API changed | ✅ None — every new fetch call target was cross-checked against an already-existing route decorator before being wired up; live Network-tab inspection during Batches 2/4/6 showed zero unexpected endpoint calls |
| Broken navigation | ✅ None — Workspace Selector cards, `#btn-switch-workspace`, sidebar clicks, and every suite's own internal tab/detail navigation all re-tested after the batches that touched them |
| Console errors | ✅ Zero, checked after every batch across Dashboard, QMS Dashboard/CAPA/Deviations/Change Control/Documents, Risk Dashboard, Qualification Dashboard/List, Equipment Library, Knowledge Base |
| Existing event listeners on preserved DOM nodes | ✅ Verified: `admin_assume_context.js`'s listener on `#btn-assume-context` (modal opens/closes correctly) and `auth.js`'s logout button both function identically post-header-rebuild |

**Environment limitations encountered (not regressions):** this sandbox's
Super Admin account has no standing tenant access and `GET /auth/companies`
returns 500 ("Could not load companies") — both pre-existing, documented
in the Phase 4 report, and reproduced identically before and after this
phase's changes. Several live checks (real populated Favorites/Recent
Items data, a fully-authenticated company-scoped dashboard) were
additionally verified via direct DOM/function-level testing
(`window.PharmaUI.*`, `window.PharmaFavorites.*` called directly with
synthetic data) since this sandbox cannot reach real tenant data — this
mirrors the Phase 4 report's own fallback to DOM/console inspection where
screenshots and live data weren't available.

## 8. Follow-Up Opportunities (not done in this phase, flagged for later)

- Sidebar nav items are `<div>`-based, not semantically focusable (§4).
- `error_pages.js`'s 403/Permission-Denied components have no wired call
  site yet (§6) — a role guard on the Administration screens would be the
  natural first user.
- `docx_generator.py`/`doc_exporter.py` DOCX export styling still uses the
  old palette per `docs/DESIGN_SYSTEM.md` §11 — unrelated to this phase,
  flagged there previously, still open.
- A handful of deeply-nested per-tab loaders (e.g. individual CAPA
  effectiveness-check or linked-deviation panels) still use the older
  bare-text pattern; they already show *something* (not a blank screen)
  and were judged lower-priority than the primary list/dashboard views
  this phase prioritized.

# 04 — Frontend Specification

**Document:** Yuktav / PharmaGPT — Frontend Specification
**Purpose:** Define expected UX/frontend behavior, based only on what exists in templates/JS today or is explicitly documented. Where behavior cannot be verified, it is marked **UNSPECIFIED / REQUIRES PRODUCT DECISION** rather than invented.
**Status:** Active
**Last reviewed:** 2026-08-23
**Source of truth / authority:** `pharmagpt/templates/index.html`, `pharmagpt/static/js/*.js`, `docs/DESIGN_SYSTEM.md`.
**Known limitations:** Projects UI and Knowledge Base/Equipment UI were confirmed only at the integration-point level (not read in full) — see §4–5. No live browser testing was performed for this document; all findings are static-code-derived.

---

## 1. Architecture Note

**CONFIRMED.** No per-page template files exist. `pharmagpt/templates/index.html` (~2,865 lines) is a single-page-app shell containing all `<main id="view-*">` blocks; `backup_dashboard.html` and `security_dashboard.html` are the only other templates. All view logic lives in ~41 vanilla-JS files under `pharmagpt/static/js/`; all styling in `pharmagpt/static/css/*.css` sharing tokens defined in `style.css` (per `docs/DESIGN_SYSTEM.md`).

## 2. Navigation

**CONFIRMED.** Sidebar sections by `data-workspace`: `dashboard`, `validation` (Validation Dashboard + Equipment Library), `quality` (QMS Dashboard, Deviation Management, CAPA, Change Control, Document Control), `knowledge` (Knowledge Base, with folder shortcuts for SOP/Validation), `documents` (Document Control — appears a second time in the nav tree), Feature Requests, an admin-only section (hidden by default, populated client-side by role), and PharmaPilot/Chat. A bottom mobile tab bar mirrors 5 top items via `mobile_nav.js` (click-forwarding only, no independent logic). Sidebar hides under ~768px per `docs/DESIGN_SYSTEM.md` §9.

## 3. Workspaces / Dashboard

**CONFIRMED.** `view-workspace-selector` is the post-login landing screen: 6 tiles (Executive / Validation / Quality / Knowledge / Document / PharmaPilot Workspace), each of which simply triggers the corresponding real sidebar item — no independent logic. The PharmaPilot tile is explicitly labeled "(placeholder only)" in the markup. `dashboard.js` drives the separate Executive Workspace view with its own skeleton/empty/error states.

## 4. Projects UI

**LIKELY / not directly inspected in full.** `project_workspace.js` exists and is referenced from Document Control (prefill for DQ/FAT/SAT tagged to a project). **UNSPECIFIED beyond confirmed integration points** — full Projects UI behavior requires a dedicated pass before being specified in detail.

## 5. Knowledge Base UI

**CONFIRMED (surface-level only).** `knowledge_base.js` plus `view-kb`/`view-equipment-library` containers exist; sidebar carries direct KB-folder shortcuts (SOP, Validation) and a KB-search-focus shortcut. Full detail not read.

## 6. Equipment UI

**CONFIRMED (surface-level only).** `equipment.js`, `equipment.css` (one mobile breakpoint), `view-equipment-library`, `view-equipment-profile`. Equipment also serves as the AI-Assisted SOP creation's context source (calls `GET /equipment`).

## 7. QMS UI (General)

**CONFIRMED.** Deviations, CAPA, and Change Control share the generic `workflow_panel.js` (`renderWorkflowPanel`) for step decisions — the same component Document Control's Workflow tab reuses. Deviations additionally keep their own richer "Lifecycle" tab, not identical to the others.

## 8. Document Control UI

This is the most actively developed and most thoroughly verified area of the frontend (`pharmagpt/static/js/qms_documents.js`).

### 8.1 SOP creation entry points — CONFIRMED

A single "New SOP" modal (`qmsDocOpenNewSOP`) offers a Title field and a route choice:
- **Route A — "Create from Controlled Template"** (default): creates the document, then downloads the real controlled DOCX template (`GET /qms/documents/templates/<id>/download`).
- **Route B — "AI-Assisted SOP Creation"**: reveals an Equipment selector (populated from `GET /equipment`); on create, streams a draft from `POST /qms/documents/<id>/generate`.

A separate, generic "New Document" modal (`qmsDocOpenNew`) remains for Project Workspace's non-SOP document types (DQ/FAT/SAT, 12-option type dropdown) — untouched by the SOP scope-lock.

### 8.2 Author Workspace — CONFIRMED

A 6-step stepper (`qmsDocRenderDraftStepper`), rendered only while version status is `draft`:
1. Download Draft DOCX
2. Content / AI Assist
3. Author Self-Check (confirmation dialog → `POST .../self-check`)
4. Upload Final Author Version (file input → `POST .../versions/upload`)
5. Assign Review & Approval Chain
6. Submit for Review — disabled unless self-check is done, final version is uploaded, and the chain is complete; the UI shows exactly which gate is still blocking submission.

### 8.3 Assignment Chain UI — CONFIRMED

Four role selectors — Reviewer, Department Head, Quality Head (all required), Plant Head (optional) — each a real `<select>` populated by `user_picker.js`'s `selectHTML()` from `GET /users/directory` (the tenant's existing user directory; no separate Approver Pool table backs this selector). Prefilled with the current assignment; saved via `POST /qms/documents/<id>/assign-chain`. This picker deliberately does **not** apply a designation-name filter, per the lesson recorded in `docs/LESSONS_LEARNED.md` §5 (exact-designation filtering can silently hide legitimate users).

### 8.4 Reviewer / Department Head / Quality Head / Plant Head Experience — CONFIRMED

Shown while version status is `under_review` or `pending_approval`:
- A read-only `<iframe>` (fixed 70vh height) at `/qms/documents/<id>/review-pdf` — the controlled, watermarked PDF (UNDER REVIEW / PENDING APPROVAL / APPROVED), reusing the same export pipeline end-to-end.
- Below it, the shared `renderWorkflowPanel()` drives per-step decisions: Approve / Reject / Request Changes / Delegate. A comment is mandatory for Reject/Request Changes. Every decision opens a fresh Electronic Signature dialog before it is recorded.
- Department Head → Quality Head → Plant Head are three sequential single-decider steps (not concurrent quorum); Plant Head auto-skips if unassigned.
- No per-role-name UI branching exists beyond "is this user one of the step's assigned approvers" — the same panel renders regardless of which named role is currently active.

### 8.5 Quality Release ("Made Effective" renamed) — CONFIRMED

Shown at `approved` status. Displays the training-completion gate (must reach the configured threshold, e.g. 90%). Release button visibility is gated: `role === "company_admin" || role === "reviewer_qa"`; other roles see an explanatory message ("Only a Quality Coordinator / authorized Quality role can perform Quality Release"). Effective Date defaults to today. The release action requires an Electronic Signature.

### 8.6 Effective State — CONFIRMED

Read-only view with a single "Start New Revision" action.

### 8.7 Status Indicators — CONFIRMED

A shared `qmsBadge(status)` helper renders a labeled badge, reused in the list table, detail header, and workflow steps. A status-label map supplies human-readable text for: Draft, Under Review, Pending Approval, Approved, Effective, Review Rejected, Approval Rejected, Superseded.

### 8.8 Approval Trail Tab — CONFIRMED read-only

Deliberately read-only by design (explicit code comment) — all decisions happen only via the Workflow tab, to avoid bypassing the state machine.

### 8.9 Approver Pool Settings — CONFIRMED, company_admin only

A settings screen (four roles: Reviewer/Dept Head/Quality Head/Plant Head) lets a company_admin configure department-scoped or company-wide **default** names to pre-fill the chain form — this is a convenience default, not a gating prerequisite (see [01 §5.3](01_PRODUCT_REQUIREMENTS.md)).

## 9. Forms and Selectors

**CONFIRMED.** Named component: `static/js/user_picker.js` (`window.UserPicker`), extracted from the Deviations workflow-builder picker. Two APIs: `datalistHTML`/`attachNamePicker`/`findByLabel` (free-text-with-suggestions, resolves to a display name only) and `selectHTML` (a genuine `<select>` resolving to `user_id`, used throughout Document Control). Backed by `GET /users/directory`. `workflow_panel.js` applies a soft designation filter with automatic fallback to the full directory when the filter yields nothing.

**LIKELY UX gap:** the "Delegate" action in `workflow_panel.js` uses a native browser `prompt()` for entering a user ID, rather than the name-picker used everywhere else in the chain UI.

## 10. Validation Messages

**CONFIRMED.** Toast-only pattern (`qmsToast` → `window.showToast`), used for every create/save/assign/submit success or failure. No inline field-level validation-message pattern found in Document Control. Native `confirm()`/`prompt()` dialogs are used for Self-Check confirmation and Delegate.

## 11. Empty / Error / Loading States

**CONFIRMED, systematic but inconsistently applied.**
- **Empty states:** `window.PharmaUI.emptyState()` (icon/title/message/action pattern) is used 59× across 16 JS files platform-wide. **Inconsistency:** `qms_documents.js` hand-rolls its own empty-state markup rather than calling the shared helper — worth normalizing.
- **Error states:** two tiers — per-panel `PharmaUI.errorState()` with a "Try again" retry button (used in list/detail loads), and full-page takeovers via `error_pages.js` reserved for global failures (network offline/online). No current code path forces a 403/404/500 full-page state.
- **Loading states:** `PharmaUI.skeleton()` (rows/table/text variants) plus ad hoc spinner + "Loading…" text coexist within the same file — skeleton in shared renderers (attachments/comments/audit trail), spinner-text in Document Control's own tab renders.

## 12. Permission-Based UI

**CONFIRMED examples:**
- "Configure Approver Pool" button gated to `company_admin`.
- Quality Release button gated to `company_admin` / `reviewer_qa`.
- Workflow step "Mark Complete" gated to users whose role is in the step's `eligible_roles`.
- Decision buttons shown only to the specific user_id assigned as approver for the current step; others see "Waiting for X to decide."
- Admin nav section hidden by default, toggled client-side by role.

**Reminder (see [03](03_SECURITY_ACCESS.md)):** every one of these UI gates has a corresponding backend check, except the Document Control `assign-chain` endpoint's "who may assign" restriction, which is UI-only today — do not read this section as implying that restriction is backend-enforced.

## 13. Responsive Behavior

**CONFIRMED breakpoints exist; Document Control itself has not been responsiveness-tested.** Breakpoints appear across `header.css`, `style.css`, `qms.css`, `equipment.css`, `mobile_nav.css`, `urs.css`, `qual.css`, `workspace.css`, `risk.css`, `report.css` (ranging 768–1400px). `docs/DESIGN_SYSTEM.md` §9 states "desktop-first (1280px+)" as design intent, not a QA-verified guarantee.

**UNSPECIFIED / REQUIRES PRODUCT DECISION:** the controlled-PDF review `<iframe>` (fixed 70vh) has no responsive override found — whether it degrades acceptably on mobile widths is undecided.

## 14. Recent Document Control Frontend Changes (for context)

Most recent commit (`75168a4`) added: the chain-assignment UI, the read-only controlled-PDF `<iframe>` review screen, and made Department Head/Quality Head/Plant Head sequential rather than concurrent. Prior commits removed a dead-end Markdown template download in favor of the real DOCX export, replaced raw user-ID/name text fields with the `user_picker.js` selector, scope-locked "New SOP" to the two-route modal, and renamed "Made Effective" to "Quality Release."

## 15. Open Questions / Conflicts

1. **Design-system color parity** — `docs/DESIGN_SYSTEM.md` §11 recommends aligning the exported DOCX/PDF heading color to the current warm-theme palette; the export pipeline still uses the older navy styling as of the latest commit. Open visual-parity gap between the on-screen UI and the exported/reviewed controlled document.
2. **Risk / URS / Qualification / Validation Report sidebar navigation** — `docs/DESIGN_SYSTEM.md` §4.2 states this is "unwired"; the sidebar markup shows a `risk-nav-*` path reached via a `showAllRiskViews` toggle, suggesting Risk may in fact be wired but reached differently than the doc describes. **Requires a closer read of that block before asserting Risk's wiring status one way or the other.**
3. **Empty-state consistency** — Document Control bypasses the shared `PharmaUI.emptyState()` helper used elsewhere; a product/design decision on whether to normalize this is open, not urgent.
4. **Mobile behavior of the controlled-PDF review iframe** — genuinely unspecified; needs a product decision, not an assumption.

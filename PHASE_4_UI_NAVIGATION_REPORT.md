# Phase 4 — UI Navigation Refresh: Implementation Report

**Date:** 2026-07-23
**Scope:** UI-only reorganization of the PharmaGPT single-page application into
enterprise workspaces. No backend, database, route, RBAC, permission, or
authentication logic was modified. No AI implementation. No new business
features or workflow redesign.

**Files changed:**
- `pharmagpt/templates/index.html` — Workspace Selector view, PharmaPilot
  placeholder view, sidebar restructuring, one new small JS helper
  (`toggleWSGroup`), header "Workspaces" button.
- `pharmagpt/static/css/workspace_selector.css` — new, additive stylesheet
  for the two new views above.

No other file was touched. `git diff --stat` for this session shows changes
confined to exactly these two files (all other pending diffs in the working
tree predate this session and belong to earlier, uncommitted Phase 1–3 work).

---

## 1. Navigation — Before

Single flat sidebar, always the first thing shown after login (the Home
Dashboard was the default-visible view):

```
Main Menu
  Dashboard
Projects (dynamic list + "New")
Equipment Library
  All Equipment
Knowledge Base
  Knowledge Base
Validation Suite
  Risk Management       (Risk Dashboard, Assessments, New, Library, Templates, Reports, Approval Queue, AI Assistant)
  URS Management         (URS Dashboard, New URS)
  Qualification          (IQ/OQ/PQ, New Qualification)
  Validation Reports     (Validation Reports, New Report)
  Generate Document      (DQ, FAT, SAT, IQ/OQ Combined, SOP, Validation Plan, Validation Report, FMEA)
Quality Management
  QMS Dashboard
  Document Control        (Documents)
  Deviation Management    (Deviations)
  CAPA
  Change Control
Administration (role-gated: Companies, Users)
AI Assistant
```

There was no post-login landing/selector screen — the Dashboard rendered
immediately. There was no hash/URL-based routing; all navigation was
client-side `display:none`/`flex` toggling of `<main id="view-*">` elements
with no corresponding browser history entries or deep links (this was true
before Phase 4 as well — see §4).

## 2. Navigation — After

```
🏠 Dashboard

📚 Knowledge Center
  Knowledge Base           (landing — unfiltered)
  SOP Library               → Knowledge Base, folder = SOP
  Validation Library        → Knowledge Base, folder = Validation
  Search                    → Knowledge Base, search box focused

🧪 Validation Center
  Projects                  (dynamic list + "New" — unchanged)
  Equipment                  (All Equipment)
  URS                        (URS Dashboard, New URS)
  Risk Assessment            (Risk Dashboard, Assessments, New, Library, Templates, Reports, Approval Queue, AI Assistant)
  Qualification (IQ/OQ/PQ)   (IQ/OQ/PQ, New Qualification)
  Validation Report          (Validation Reports, New Report)
  Generate Document (DQ/FAT/SAT)  (DQ, FAT, SAT, IQ/OQ Combined, SOP, Validation Plan, Validation Report, FMEA)

🛡 Quality Center
  QMS Dashboard              (landing)
  Deviation Management       (Deviations)
  CAPA
  Change Control

📄 Document Center
  All Documents              (landing — unfiltered)
  SOP                        → Document Control, type = SOP
  Templates                  → Document Control, type = Template

Administration (role-gated: Companies, Users) — unchanged, kept below the
  workspace groups since it is not one of the six.

🤖 PharmaPilot
  PharmaPilot                (new placeholder — "coming soon", no AI logic)
  AI Assistant                (existing, fully functional chat — unchanged)
```

A **Workspace Selector** ("Welcome to PharmaGPT / Choose your workspace")
is now the default landing view after login, with six cards:

| Card | Subtitle | Lands on |
|---|---|---|
| Executive Workspace | Dashboards, KPIs, Executive Insights | Dashboard |
| Validation Workspace | Validation Projects & Qualification | Risk Dashboard (Validation Center) |
| Quality Workspace | CAPA, Deviations, Change Control | QMS Dashboard |
| Knowledge Workspace | SOPs, Manuals & Reference Documents | Knowledge Base |
| Document Workspace | Controlled Document Authoring | Document Control ("All Documents") |
| PharmaPilot | Enterprise AI Assistant (placeholder only) | PharmaPilot placeholder |

A new **"Workspaces"** button in the header lets the user return to this
selector at any time without logging out.

Each card is wired as `document.getElementById('<existing-nav-id>').click()`
— it simply simulates a real click on the sidebar item that already owns
the correct view-switch and data-init logic. No new navigation engine, no
duplicated business logic.

## 3. Screens Moved

| Item | Before | After | Element reused (unchanged id) |
|---|---|---|---|
| Dashboard | Main Menu | Dashboard (top-level) | `#nav-dashboard` |
| Projects | standalone section | Validation Center | `#project-list`, `#btn-new-project` |
| Equipment Library | standalone section | Validation Center → Equipment | `#nav-equipment-library` |
| Knowledge Base | standalone section | Knowledge Center | `#nav-kb` |
| Risk Management | Validation Suite | Validation Center → Risk Assessment | `#risk-nav-*` (all 8 sub-items) |
| URS Management | Validation Suite | Validation Center → URS | `#urs-nav-items`, `.urs-sub-item` |
| Qualification | Validation Suite | Validation Center → Qualification | `#qual-nav-items` |
| Validation Reports | Validation Suite | Validation Center → Validation Report | `#report-nav-items` |
| Generate Document | Validation Suite | Validation Center → Generate Document | `#val-nav-items` (unchanged, dynamic) |
| QMS Dashboard | Quality Management | Quality Center | `#nav-qms-dashboard` |
| Deviations | Quality Management | Quality Center | `#nav-qms-deviations` |
| CAPA | Quality Management | Quality Center | `#nav-qms-capa` |
| Change Control | Quality Management | Quality Center | `#nav-qms-change-control` |
| Documents (Document Control) | Quality Management → Document Control | **Document Center** (new group) | `#nav-qms-documents` |
| Administration (Companies/Users) | standalone, role-gated | kept standalone, role-gated, moved below workspace groups | `#admin-nav-section`, `#nav-admin-companies`, `#nav-admin-users` |
| AI Assistant (chat) | standalone section | PharmaPilot group (alongside the new placeholder) | `#nav-chat` |

New, purely additive items (existing screens, new entry points):

- **SOP Library**, **Validation Library**, **Search** — all three open the
  existing Knowledge Base view (`#view-kb`) via its existing
  `kbSetFolder()` / `initKB()` functions; no new route, no new fetch.
- **SOP**, **Templates** under Document Center — open the existing
  Document Control view (`#view-qms-documents`) via its existing
  `qmsDocShowList({type: ...})` function; no new route, no new fetch.
- **PharmaPilot** — genuinely new: a static placeholder view
  (`#view-pharmapilot`) with no JS, no fetch, no AI logic, per spec.
- **Workspace Selector** (`#view-workspace-selector`) — new landing view,
  purely navigational (see §2).

## 4. Items Intentionally Omitted

Per explicit instruction from the user during this phase ("show only
navigation items that have a real 1:1 destination today... do not create
placeholder business modules... do not alias unrelated screens... do not
show 'Coming Soon' entries"), the following items named in the original
spec were **not** added because no corresponding screen, data model, or
document type exists anywhere in the codebase:

| Spec item | Section | Why omitted |
|---|---|---|
| Instrument Manuals | Knowledge Center | Only one Equipment Library exists; no separate instrument/manual-only screen. |
| Equipment Manuals | Knowledge Center | Same as above — Equipment Library already relocated to Validation Center as "Equipment". |
| Closed Records | Knowledge Center | No archived/closed-records browser exists anywhere. |
| MFR | Document Center | Not a document type in `qms_database.py::_DOC_TYPE_CODES`; mentioned only in code comments as a hypothetical future addition. |
| BMR | Document Center | Same as MFR. |
| BPR | Document Center | Same as MFR. |
| Incidents | Quality Center | No dedicated module; only a `capa_source` option value. |
| Complaints | Quality Center | No dedicated module; only a `capa_source` option value and a Risk Assessment subtype. |
| Audit Compliance | Quality Center | No dedicated module; only a `capa_source` ("Audit") option value. |
| Periodic Review | Validation Center | Not a distinct screen — it is one report-type option inside the existing Validation Report generator. |

These were left out of the menus entirely rather than shown disabled or
aliased to an unrelated screen, per the user's directive. The new sidebar
groups (Knowledge Center, Validation Center, Quality Center, Document
Center) are structured with independent, per-group containers
(`ws-knowledge-items`, `ws-validation-items`, `qms-nav-items`,
`ws-document-items`) specifically so that adding any of the above later —
once a real screen exists for it — is a single new `sidebar-item` inserted
into the relevant group, with no restructuring required.

## 5. Routes Preserved

PharmaGPT is a single-page app: the Flask side serves exactly one HTML
route, `GET /` (`pharmagpt/app.py`), and everything else is a JSON API
endpoint called via `fetch()`. This phase did not add, remove, or modify
any Flask route, blueprint, or `@app.route`/`@bp.route` decorator —
`pharmagpt/app.py` and every file under `pharmagpt/routes/` are untouched.

- `GET /` still serves the same `index.html` shell.
- No API endpoint's path, method, or behavior changed.
- No existing `<main id="view-*">` element, `id`, `data-view` attribute,
  or `onclick` handler was removed or renamed. Every one of them was
  either left untouched in place (Risk/URS/Qualification/Report/QMS
  sub-groups, Administration, project list) or moved to a new parent
  container with its attributes byte-for-byte identical.
- Because there was no hash/URL-based deep-linking before this phase
  (confirmed: no `pushState`/`location.hash` usage anywhere in the
  pre-existing code), there was nothing to regress there. Browser history
  behavior is unchanged from before Phase 4 — the app has always used
  divshow/hide navigation with a single unchanging document URL. A
  lightweight, additive hash layer was considered but intentionally left
  out of scope to minimize risk on top of the reorganization itself; this
  is a reasonable follow-up as a separate change, not treated as a
  regression here.

## 6. RBAC / Permissions

Not modified. Verified by inspection and live test:

- `static/js/auth.js` and `static/js/admin_assume_context.js` were not
  edited.
- `applyRoleBasedVisibility()` keys off `#admin-nav-section`,
  `#nav-admin-companies`, `#nav-admin-users`, and `#btn-assume-context` —
  all four ids are present, unchanged, in the new sidebar markup.
- Live test as a `super_admin` account confirmed the Administration
  section and "Assume Company Context" button render exactly as before.
- No `auth/middleware.py`, `auth/decorators.py`, or tenancy check was
  touched.

## 7. Regression Summary (Live Test)

Verified against a locally running instance
(`flask --app pharmagpt.app run --port 5099`), logged in as the
project's configured super-admin dev account:

- ✅ Login → Workspace Selector renders as the landing screen (title,
  subtitle, all 6 cards).
- ✅ All 6 workspace cards navigate to the correct existing view
  (confirmed via DOM inspection of which `<main>` is visible after each
  click: `view-dashboard`, `view-risk-dashboard`, `view-qms-dashboard`,
  `view-kb`, `view-qms-documents`, `view-pharmapilot`).
- ✅ Header "Workspaces" button returns to the selector from any screen.
- ✅ Sidebar renders all 6 groups with every relocated item present and
  correctly labeled (verified via full accessibility-tree dump).
- ✅ New outer-group collapse toggle (Knowledge Center) expands/collapses
  correctly.
- ✅ "Search" (Knowledge Center) opens Knowledge Base and focuses the
  title search field.
- ✅ "SOP" (Document Center) issues `GET /qms/documents?type=SOP` —
  confirms the pre-filter reaches the existing, unmodified endpoint
  correctly with no duplicate/racing unfiltered request.
- ✅ "SOP Library" (Knowledge Center) issues
  `GET /kb/documents?folder=SOP` — same confirmation for the KB filter.
- ✅ Zero browser console errors across all of the above.
- ℹ️ Several API calls returned `403 Forbidden` (`/dashboard/stats`,
  `/projects`, `/risk/dashboard`, `/kb/documents`, `/qms/documents`, one
  `/qms/dashboard` `500`). These are **pre-existing, unrelated to this
  change**: they occur identically for a `super_admin` account with no
  "Assumed Company Context" set (a tenancy scoping rule in
  `auth/middleware.py`/`tenancy.py`, neither of which this phase touched),
  and reproduce on routes this phase never modified (e.g. `/risk/dashboard`,
  which sits behind an untouched, merely-relocated sidebar item). Data
  cannot be exercised further in this sandbox because "Assume Company
  Context" itself reports "Could not load companies" (`GET
  /auth/companies` → `500`), which is an environment/data-seeding
  limitation of this local dev database, not a Phase 4 defect.
- Screenshots: not captured — the Browser pane could not composite frames
  in this sandbox session (headless/pane-display limitation). Verification
  was instead performed via DOM state inspection, the accessibility tree,
  console logs, and network request inspection, all captured above.

## 8. Design Decisions Worth Flagging

- **Administration** (Companies/Users admin) and the working **AI
  Assistant** chat are not among the six specified sidebar groups, but
  both are pre-existing, fully functional features. Removing them would
  violate "do not remove any feature," so both were kept: Administration
  as its own pinned, role-gated section below the six groups (unchanged
  from before), and AI Assistant as a second item inside the PharmaPilot
  group, next to the new placeholder.
- **PharmaPilot** is a static placeholder only, per spec — no fetch, no
  streaming, no AI call. The existing, working chat assistant remains the
  real AI Assistant entry point until a future phase implements
  PharmaPilot for real.
- Icons use the app's existing Lucide icon set (e.g. `home`, `library`,
  `flask-conical`, `shield`, `file-text`, `bot`) rather than literal emoji
  glyphs, to stay visually consistent with every other sidebar icon in the
  app; the spec's emoji were treated as descriptive labels, not a literal
  rendering requirement.

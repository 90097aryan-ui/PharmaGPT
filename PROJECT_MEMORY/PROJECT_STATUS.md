# PROJECT_STATUS.md — PharmaGPT Implementation Snapshot

> Part of the permanent [PROJECT_MEMORY](CLAUDE.md) set. A new developer or a new Claude session
> should be able to understand what PharmaGPT actually does today from this file alone, without
> reading source code. Last synchronized against the repository: **2026-07-23** (45 commits past
> `c995049`, HEAD `62106e3` plus the uncommitted Phase 1 architecture-recovery fixes described in
> "Update — 2026-07-23" immediately below). This is the file's **fourth** drift-and-resync — see
> [DECISIONS.md](DECISIONS.md) DEC-014/DEC-022/DEC-026 for the first three and
> `PharmaGPT_Implementation_Roadmap/REPOSITORY_AUDIT.md`'s Currency Note for this one. DEC-014's
> long-standing recommendation (a single machine-readable version/test-count source instead of
> hand-maintained prose) remains unimplemented and is the real fix for this recurring class of
> drift — flag it again if a fifth occurrence happens.

---

## Update — 2026-07-23 (Phase 1 Implementation)

Everything below this box was last true on **2026-07-10**. Rather than rewrite the entire file
(disproportionate to a Low-priority documentation-drift finding — see
`PharmaGPT_Implementation_Roadmap/REPOSITORY_AUDIT.md`), this box summarizes what changed across
the 45 commits and the uncommitted working-tree state since, grouped by theme. Treat the sections
below as historical background, **except** where a specific correction is noted inline.

- **Supabase Auth + RBAC + multi-tenancy shipped** (`6031296`, `ec249d1`, `aa15c66`) — real login/
  logout/session, a four-role model (`super_admin`/`company_admin`/`reviewer_qa`/`user`),
  `require_role()` enforcement on destructive/approval routes, and `company_id`-scoped tenant
  isolation across every domain table. **This supersedes "Known Limitations" below's "No
  authentication or authorization system (planned v0.9)"** — that system is now live.
- **Risk/URS/Qualification/Validation Report sidebar navigation is live and wired** — direct
  inspection of the current `templates/index.html` shows real, visible-by-default sidebar
  sections with working click handlers. **This supersedes every "Sidebar navigation not wired" /
  "no live entry point" claim below** (Completed Modules, Known Issues). The real, still-open gap
  is narrower: these suites open their global, unfiltered dashboard rather than a project-scoped
  view when reached via a Project Workspace tab (`DECISIONS.md` DEC-025 Future Review, unchanged).
- **Postgres dual-write migration scaffolding** (Phase 3.1–3.5, `4da4913` → `7d5b6ce`) — Projects,
  Knowledge Base, Equipment, and QMS (Deviations/CAPA/Change Control/Risk Assessments) all now
  dual-write to Postgres behind per-domain feature flags (`PROJECTS_BACKEND`, `KB_BACKEND`,
  `EQUIPMENT_BACKEND`, `QMS_BACKEND`), all still defaulting to `sqlite` as the live read path — no
  domain has cut over yet. See `docs/PHASE3_FLAGS.md` and `TENANCY_VALIDATION.md`.
- **Critical security fixes** (`aa15c66`, 2026-07-21): cross-tenant data access on the SQLite path
  (every domain now tenant-scoped), missing RBAC on destructive/approval routes, and e-signature
  spoofing at *approval* time. **A fourth fix, e-signature spoofing at record-*creation* time**
  (QMS `performed_by` on Deviation/CAPA/Change Control/Document creation), was found by
  `FUNCTIONAL_VALIDATION_REPORT.md` (2026-07-22) and fixed as part of this Phase 1 pass — see
  `PHASE_1_IMPLEMENTATION_REPORT.md`.
- **Generate Document duplication retired** (this Phase 1 pass) — the non-functional v0.9 stub
  (`gen_document.js`, "Generate Document" main-menu item) is removed entirely; the real AI
  generator remains, now reachable from a proper "Generate Document" sidebar section, restricted
  to the document types that don't yet have a dedicated suite (DQ/FAT/SAT/FMEA/IQ-OQ Combined/SOP/
  Validation Plan/Validation Report). URS/IQ/OQ/PQ/CAPA/Deviation/Change Control are generated
  from their own suite instead (server-side enforced too). See
  `PharmaGPT_Implementation_Roadmap/REPOSITORY_AUDIT.md` and `PHASE_1_IMPLEMENTATION_REPORT.md`.
- **Production deployment hardening** (`e578b1a`, 2026-07-22) — persistent-disk storage, gunicorn
  bound to `$PORT`, threaded workers, fail-safe debug default.
- **URS Management Suite materially improved** — a real Draft→Under Review→Approved→Effective→
  Obsolete lifecycle state machine (`urs_lifecycle.py`) now gates status changes; AI generation
  (`urs_generation_job.py`) moved off the request thread onto a background job runner, fixing
  request-cycle timeout crashes — the reference pattern the other 6 AI-generation endpoints should
  still be migrated to (unchanged, still open).
- **Test count**: this file's own "148 tests" claim (below) predates all of the above. See
  `PHASE_1_IMPLEMENTATION_REPORT.md` for the current, authoritative count — `README.md` and
  `TEST_SUMMARY.md` are resynchronized to the same number as part of this pass.

---

## Project Summary

PharmaGPT is an AI-powered Enterprise Pharmaceutical Digital Quality & Validation Platform built
by **The Lean Architect**. It combines an AI chat assistant (Google Gemini), project- and
knowledge-base-scoped document management with automated text extraction, an AI validation
document generator (URS/IQ/OQ/PQ/etc.), dedicated Risk/URS/Qualification/Validation-Report
suites, and — as of the current working tree — a Quality Management Suite (Document Control,
Deviation Management, CAPA).

---

## Current Version

**Last committed release: commit `c995049`, 2026-07-09, "Release v1.0 RC1 - Document Generation and
Validation Workspace Fixes."** `git log` shows this supersedes `3a94ccf` (2026-07-05) via two
commits this document had, until now, still described as uncommitted: `24c808b` ("Add Quality
Management Suite Phase 2 - Change Control", 2026-07-05) and `c995049` itself (Document Generation/
`gen_document.js` improvements, testing docs — unrelated to Change Control despite the commit
message grouping them). See [DECISIONS.md](DECISIONS.md) DEC-026 for this reconciliation (the third
occurrence of this drift class — see DEC-014, DEC-022).

**On top of `c995049`, the working tree contains the Foundation Refactoring — PharmaGPT v1.0
Modules 1–3** (Project/Validation-Workspace merge, Equipment as a first-class entity, Project
Workspace navigation refactoring) — functionally complete, browser-verified, 148 tests passing,
about to be committed as a single milestone and tagged **`Foundation v1.0`**. See
[FOUNDATION_ARCHITECTURE.md](../FOUNDATION_ARCHITECTURE.md) for the frozen capstone architecture and
[DECISIONS.md](DECISIONS.md) DEC-023/DEC-024/DEC-025 for the three modules' individual rationale.
Module 4 (AI Intelligence Integration) is next — see Upcoming Sprint.

---

## Architecture Summary

Monolithic Flask app, vanilla-JS SPA frontend, SQLite persistence, Google Gemini
(`gemini-2.5-flash`) for all AI features. See [ARCHITECTURE.md](ARCHITECTURE.md) for full detail.

---

## Technology Stack

| Layer | Choice |
|---|---|
| Backend | Flask 3.1.3, Werkzeug 3.1.8, gunicorn 26.0.0 |
| Database | SQLite 3 (raw `sqlite3`, no ORM) |
| AI | `google-genai` 2.10.0, model `gemini-2.5-flash` |
| Document generation | `python-docx` 1.2.0 |
| Document extraction | `pypdf`, `pdfplumber`, `PyMuPDF`, `openpyxl` (multi-engine fallback) |
| Frontend | Vanilla JavaScript, no framework, no build step |
| Background jobs | `concurrent.futures.ThreadPoolExecutor` |
| Testing | pytest 8.3.4 |
| Deployment | Render (gunicorn + persistent disk) |

---

## Deployment Status

- **Target:** Render, service type `web`, plan `starter`, Python runtime.
- **Build:** `pip install -r requirements.txt`
- **Start:** `gunicorn pharmagpt.app:app --workers=2 --threads=4 --timeout=60`
- **Persistence:** 1GB persistent disk mounted at `/var/data`, `DB_PATH=/var/data/pharmagpt.db` —
  required because Render's default filesystem is ephemeral and would otherwise lose the SQLite
  file on every restart/redeploy.
- **Secrets:** `GEMINI_API_KEY` set manually in the Render dashboard (not synced from repo);
  `FLASK_SECRET_KEY` auto-generated by Render; `FLASK_DEBUG=false` in production.
- **Local dev:** `.env` with `GEMINI_API_KEY`, `FLASK_SECRET_KEY=change-in-production`,
  `FLASK_DEBUG=true`, `FLASK_PORT=5000`; run via `python -m flask --app pharmagpt.app run` (see
  `.claude/launch.json`, port 5060 in that config) or `python pharmagpt/app.py`.

---

## Current Database

SQLite 3, single file (`pharmagpt.db`, path overridable via `DB_PATH`). No migration framework —
schema changes must be additive (guarded `_add_column_if_missing()` pattern) or require a manual
dev-only DB reset. Full schema in root-level `DATABASE.md` and summarized in
[ARCHITECTURE.md](ARCHITECTURE.md) §4.

---

## Current AI Model

Google Gemini **`gemini-2.5-flash`**, via the `google-genai` SDK. Used for: chat, validation
document generation, Risk/URS/Qual/Report content generation, and (uncommitted) QMS document
drafting, deviation investigation, CAPA suggestions, and quality trend summaries.
`temperature=0.3` for structured document generation; default temperature for conversational chat.

---

## Current UI Theme

**"Premium Enterprise" palette v3.0 (2026-07-05, uncommitted)** — refines the "Executive Office"
redesign (DEC-018) to an exact business-attire palette (Primary BG `#F7F5F2`, Secondary BG
`#F1ECE6`, Card `#FFFFFF`, Sidebar `#5B4C43`/hover `#6D5B52`/active `#8A6B52`, Primary Button
`#8A6B52`/hover `#9D7B60`, Primary Text `#2D2A28`, Secondary Text `#66615B`, Muted Text `#9A948C`,
Border `#E6DED6`, Divider `#EEE7E1`, Success `#5F8A61`, Warning `#C59A41`, Danger `#C35F5B`,
Information `#6E8FA5`, soft tints `#E7EEF6`/`#E8F2EA`/`#FFF4E5`), and swaps the previous Unicode
emoji iconography for a single consistent icon library, **Lucide** (loaded via CDN, converted
client-side by a body-level `MutationObserver` so no individual JS module needs to call
`lucide.createIcons()` itself — see `refreshIcons()` in `templates/index.html`). The **Regulatory
Scope** sidebar section (USFDA/MHRA/EU GMP/etc. badges) was removed entirely per explicit
instruction — regulatory context now belongs inside modules, not as sidebar chrome. Inter remains
the typeface (Google Fonts, same loading mechanism since v0.2); 14px card radius / 8px spacing /
soft shadows were already correct from DEC-018 and were preserved. The document viewer / DOCX
export on-screen component remains the deliberate light-background exception (its exported
`.docx` styling in `doc_exporter.py` still uses pre-redesign navy — still-open follow-up, unchanged
by this pass). Full detail in [DECISIONS.md](DECISIONS.md) DEC-019 (supersedes DEC-018's palette
values and icon strategy; DEC-018's architectural approach — token-based sweep — was reused, not
replaced).

---

## Current Testing Status

- Framework: pytest 8.3.4, config in `pytest.ini` (`testpaths = tests`, `slow` marker excluded by
  default for 1000-page stress tests).
- **148 tests total** across the committed Document Intelligence Engine suite (~41 tests), the
  uncommitted QMS suite (60 tests: 42 from Phase 1 Document Control/Deviation/CAPA + 16 new from
  Phase 2 Change Control), the uncommitted Module 1 Validation Workspace/`projects` merge
  (`test_projects_merge.py`), the Module 2 Equipment suite (33 tests: `test_equipment_database.py` +
  `test_equipment_routes.py`), and the new Module 3 suite (6 tests: `test_project_workspace.py` —
  project audit-trail logging, the `project` QMS record type, confirming `/val-projects` is gone).
  One pre-existing timing-sensitive test (`test_document_processor.py::test_small_pdf`, an absolute
  wall-clock assertion) is occasionally flaky under system load — confirmed unrelated to Module 3 by
  re-running it in isolation, where it passes.
- **Known collection issue:** running `pytest --collect-only` in a fresh environment currently
  fails to collect 4 modules (`test_document_processor.py`, `test_job_runner.py`,
  `test_pdf_engines.py`, `test_pipeline.py`) due to `ModuleNotFoundError` (`docx`, `dotenv`) — this
  is a virtualenv/dependency-install issue in the environment used to verify this snapshot, not a
  code defect; `requirements-dev.txt` + `requirements.txt` must both be installed
  (`pip install -r requirements-dev.txt`) before running the full suite.
- No CI pipeline configuration was found in the repository — tests are run manually.

---

## Completed Automated Tests

| Test file | Covers |
|---|---|
| `test_pdf_engines.py` | Each PDF extraction engine in isolation |
| `test_pipeline.py` | Multi-engine fallback, per-page timeout, gc interval, quality-score formula |
| `test_document_processor.py` | End-to-end extraction across all fixtures + performance targets |
| `test_job_runner.py` | `ThreadPoolJobRunner` execution and crash isolation |
| `test_routes_upload_async.py` | Upload → status polling → retry flow via Flask test client |
| `test_qms_database.py` *(uncommitted)* | QMS schema, CRUD, polymorphic tables, auto-numbering — Document Control/Deviation/CAPA/Change Control |
| `test_qms_routes.py` *(uncommitted)* | QMS HTTP routes, AI review/generation (mocked), DOCX export, approvals — Document Control/Deviation/CAPA/Change Control |

Two real bugs were found and fixed while writing the QMS tests: `generate_document_number()`
mishandling single-word abbreviated departments (e.g. "QA" → "Q"), and a Windows file-handle race
between `send_file` and `os.remove()` (fixed test-side).

---

## Current Sprint

**Foundation Refactoring (PharmaGPT v1.0 Modules 1–3) — approved and frozen, being committed as
`Foundation v1.0`.** The three sub-sprints below (Module 3, Module 2, and the underlying Module 1
merge) are being committed together as the first architectural milestone; per instruction, no
further navigation or structural refactoring should follow unless a critical defect is found. Module
4 (AI Intelligence Integration) is next — see Upcoming Sprint.

**PharmaGPT v1.0 Module 3 — Project Workspace & Navigation Refactoring** (functionally complete,
browser-verified end-to-end, full 148-test regression suite passing):
establishes "One Project = One Workspace" — Equipment, Documents (+ Insights), Risk Assessment, URS,
Qualification, Validation Report, Tasks, Approvals, and History are all reached from a single
unified Project Workspace (`view-project-workspace`, `project_workspace.js`, built on the Enterprise
Workspace shell) opened by selecting a project, replacing the standalone Equipment/Documents/
Insights sidebar items Module 2 had just added. Retired the legacy Validation Workspace entirely
(`routes/workspace.py`, `val_workspace.js`, `vw-*` CSS/markup, and the dead `val_projects` CRUD in
`database.py`) after discovering — during the navigation-architecture review required before this
module began — that it was still a fully live, writable flow on a separate `val_projects` entity,
contradicting the unified `projects` table from Module 1. Risk/URS/Qualification/Validation Report
got their first live entry points (as Project Workspace tabs) since those suites' sidebar sections
were added, though not yet project-filtered (see Known Issues). Also fixed two small pre-existing
bugs found along the way: `window.selectProject` was never exposed on `window`, silently breaking
the Dashboard's "Recent Projects" card navigation. See [ARCHITECTURE.md](ARCHITECTURE.md) and
[DECISIONS.md](DECISIONS.md) DEC-024 (retiring `val_projects`)/DEC-025 (Project Workspace
architecture) for full detail. This completes the Foundation Refactoring (Modules 1–3).

**PharmaGPT v1.0 Module 2 — Equipment as a First-Class Entity** (functionally complete,
browser-verified end-to-end, full 142-test regression suite passing at the time):
promotes Equipment from free-text project fields + a static per-type reference catalog into a real
database entity owned by a Project — `equipment` + `equipment_documents` tables
(`pharmagpt/equipment_database.py`), a full REST API (`routes/equipment.py`), and a project-scoped
list view + Enterprise-Workspace-based Equipment Profile page (`equipment.js`/`equipment.css`) with
Overview/Specifications/Documentation/Qualification/Validation History/Related Documents/Related
Risk Assessments/Future Modules (placeholder) tabs. Documents are referenced from the Knowledge Base
or a Project's own Documents, never duplicated. `projects.equipment_name/manufacturer/model/
equipment_id` (free text) and `pharmagpt/equipment/` (the static Intelligence Engine profile
catalog) are both left untouched — this is purely additive. A `POST /projects/<id>/equipment/
import-legacy` endpoint lets an existing project promote its legacy free-text info into a real
Equipment record in one click. An AI-context-bundle endpoint
(`services/equipment_service.py::get_equipment_context_bundle()`) is architecture-only — assembled
but not yet wired into actual document generation. See [ARCHITECTURE.md](ARCHITECTURE.md) and
[DECISIONS.md](DECISIONS.md) DEC-023 for full detail. Follows Module 1 (the "Phase 2 Module 1"
Validation Workspace/`projects` merge — see `routes/projects.py`/`test_projects_merge.py`).

All other work previously tracked here (Pre-Deployment UI Audit, "Executive Office"/v3.0 Design
System Redesign, Enterprise Workspace layout, QMS Phase 1, QMS Phase 2 Change Control, RC1 document-
generation fixes) is now committed — see Completed Sprints below for each, and DEC-022/DEC-026 for
how this file's earlier "uncommitted" framing was reconciled each time.

---

## Completed Sprints

| Sprint / Version | Theme | Highlights |
|---|---|---|
| v0.1 | Foundation | CLI chat (`hello.py`), Gemini integration, streaming, retry logic |
| v0.2 | PharmaGPT Web App | Flask SPA, SSE streaming, `PHARMA_SYSTEM_PROMPT`, regulatory scope defined |
| v0.3 | Project Management | Create/list/delete projects, per-project chat history |
| v0.4 | Document Management | Upload PDF/DOCX/XLSX/TXT, view/download/delete |
| v0.5 | AI Document Intelligence (v1) | Auto text extraction, keyword/Jaccard search, doc-context injection into chat |
| v0.6 | Validation Document Generator | 11 doc types, 4-step wizard, DOCX/PDF export, save to project |
| v0.7 | Knowledge Base | Project-independent library, 8 folders, metadata, 4 combinable search filters |
| v0.8 (partial) | Validation Workspace + Dashboard | `val_projects`/`val_audit_trail` tables, initial UI, home dashboard |
| — | Refactor v1 / Stable Foundation | Code review pass, stabilization (v0.9.5 Beta) |
| — | Render deployment fixes | Package/import fixes for production deployment |
| 2026-06-30 | Risk / URS / Qualification / Validation Report Suites | ~19,300 lines added in one commit — full backend + frontend for all four suites |
| 2026-07-01 | Dashboard & Workspace UX | Navigation and project-workspace UX improvements |
| 2026-07-01 → 07-02 | Document Intelligence Engine (v1.0 rewrite) | Async, multi-engine, timeout-bounded, quality-scored extraction pipeline; replaces synchronous single-engine extractor |
| v0.9.8 | Release | Document Intelligence Engine + Validation UI improvements (last committed release) |
| 2026-07-04 | Enterprise Workspace Layout (Validation & Usability Testing Sprint) | Fixed a pre-existing `.app-body` HTML nesting bug (Generate Document/Risk/URS/Qual/Report/QMS all rendered outside the sidebar layout); introduced reusable `workspace.css`/`workspace.js` shell; Generate Document is the first implementation |
| 2026-07-04, commit `6ffaa54` | Quality Management Suite — Phase 1 | Document Control, Deviation Management, CAPA; shared polymorphic Attachments/Comments/Audit-Trail/Approval tables (DEC-010/DEC-011); commit message says "v0.9.9 - QMS Phase 2" but the content is Phase 1 (Document Control/Deviation/CAPA) — a version-numbering/commit-message discrepancy, see DEC-022 |
| 2026-07-05 | "Executive Office" Design System Redesign | UI-only visual redesign, navy/blue → warm business-attire palette (Walnut Brown/Warm Charcoal/Muted Sage), across every screen; ~1,200 hardcoded colour literals swept to new tokens across all 7 CSS files + 11 JS modules; no backend/API/DB changes |
| 2026-07-05 | "Premium Enterprise" Palette v3.0 + Lucide Icons | Exact business-attire hex palette refinement, sidebar Regulatory Scope section removed, Unicode emoji → Lucide icon library (see DEC-019) |
| 2026-07-05 | Pre-Deployment UI Audit | Completed the Lucide icon sweep (0 emoji remain codebase-wide); fixed a cross-suite JS function-name collision (`risk.js`/`urs.js`), a `.urs-empty` layout bug, and the Validation Report suite's dark-theme/width leftovers (see DEC-020) |
| 2026-07-05, commit `3a94ccf` | "PharmaGPT v3.0 Premium Enterprise UI completed" | Single commit bundling the three rows immediately above (Executive Office redesign, Premium Enterprise v3.0/Lucide icons, Pre-Deployment UI Audit) |
| 2026-07-05, commit `24c808b` | Quality Management Suite — Phase 2: Change Control | 26 change categories, 6 change types, 13-stage workflow, 9 optional AI features, built on the Phase 1 polymorphic shared tables (`record_type='change_control'`); 16 tests. See [DECISIONS.md](DECISIONS.md) DEC-021/DEC-026 |
| 2026-07-09, commit `c995049` | "Release v1.0 RC1 - Document Generation and Validation Workspace Fixes" | Generate Document (`gen_document.js`/`doc_generator.py`) improvements, new prompt modules, testing/validation docs. Unrelated to Change Control despite the commit grouping — see DEC-026 |
| 2026-07-10 | **Foundation Refactoring — PharmaGPT v1.0 Modules 1–3, tagged `Foundation v1.0`** | Module 1: unified `projects` table (Validation Workspace fields merged in). Module 2: Equipment as a first-class entity (DEC-023). Module 3: Project Workspace navigation refactoring, legacy Validation Workspace retired (DEC-024/DEC-025). See [FOUNDATION_ARCHITECTURE.md](../FOUNDATION_ARCHITECTURE.md) |

---

## Upcoming Sprint

**PharmaGPT v1.0 Module 4 — AI Intelligence Integration** (per explicit instruction: focuses
exclusively on AI integration; no further navigation or structural refactoring unless a critical
defect is discovered). Candidate work already seeded as architecture-only stubs by prior modules:
`services/equipment_service.py::get_equipment_context_bundle()` (Module 2, DEC-023) and the
long-standing vector-RAG stubs in `document_search.py` (DEC-008) are the most likely integration
points. Then proceed per the Roadmap below (QMS Non-Conformance/OOS-OOT to complete Phase 2, or
Phase 3).

---

## Roadmap

| Target | Theme | Key items |
|---|---|---|
| v0.8 (remainder) | Validation Workspace & Signatures | Full Validation Workspace UI, electronic signatures, 21 CFR Part 11 audit trail (`audit_log`, `signatures` tables), Vector RAG upgrade (Gemini embeddings + vector store), dashboard enhancement |
| QMS Phase 2 | Change Control (done, committed `24c808b`), Non-Conformance, OOS/OOT | Reuse the existing polymorphic shared tables (attachments/comments/audit/approvals) |
| PharmaGPT v1.0 Module 4 | AI Intelligence Integration (next — see Upcoming Sprint) | Wire the Equipment AI-context bundle (DEC-023) and/or the vector-RAG stubs (DEC-008) into real generation |
| QMS Phase 3 | Audit Management, Supplier Quality, Training Management, Complaint Management | Same shared-table reuse pattern |
| v0.9 | Multi-User & RBAC | User accounts, roles, project-level permissions, `users`/`project_members` tables, admin panel, activity notifications |
| v1.0 | Production Hardening | Server-side PDF export, SOP/MVP template library, Audit Prep AI assistant, Docker packaging, PostgreSQL migration, rate limiting, HTTPS, security headers |
| Future / Exploration | — | NFC/RFID equipment tag linkage, BatchTrack (CDMO project/inventory management), regulatory change alerts, multi-tenant SaaS, mobile-responsive UI |

**Note:** the top-level `ROADMAP.md` at repo root is stale (predates QMS); `docs/ROADMAP.md` is
the current, authoritative roadmap. See [DECISIONS.md](DECISIONS.md) DEC-014.

---

## Completed Modules

### Project Workspace (PharmaGPT v1.0 Module 3)
Live and wired. "One Project = One Workspace" — Equipment, Documents (+ Insights), Risk Assessment,
URS, Qualification, Validation Report, Tasks (placeholder), Approvals (placeholder), and History are
all reached from a single unified Project Workspace (`view-project-workspace`,
`project_workspace.js`) opened by selecting a project, built on the Enterprise Workspace shell
(DEC-017). Replaces the standalone Equipment/Documents/Insights sidebar items and the retired legacy
Validation Workspace (see below). Risk/URS/Qualification/Validation Report tabs are live entry
points, not yet project-filtered (see Known Issues). See [ARCHITECTURE.md](ARCHITECTURE.md) and
[DECISIONS.md](DECISIONS.md) DEC-025.

### Equipment (PharmaGPT v1.0 Module 2)
Live and wired — now embedded as a tab inside the Project Workspace (Module 3) rather than a
standalone sidebar item. Equipment as a first-class entity owned by a Project — `equipment` +
`equipment_documents` tables, full CRUD/search/document-link REST API, and an Enterprise-Workspace-
based Equipment Profile page (Overview/Specifications/Documentation/Qualification/Validation
History/Related Documents/Related Risk Assessments/Future Modules tabs), reachable from the
Equipment tab. Architecture-only for now — Calibration/Preventive Maintenance/Breakdown History/
Spare Parts/Vendor Qualification/Environmental Monitoring/Utilities/Asset Management are not built,
only prepared for (future tables would FK to `equipment.id`). See
[ARCHITECTURE.md](ARCHITECTURE.md) and [DECISIONS.md](DECISIONS.md) DEC-023.

### Validation Workspace (v0.8) — RETIRED
Removed entirely by Module 3 (DEC-024) — was found to still be a live, writable flow on a separate
`val_projects` entity, contradicting the unified `projects` table from Module 1. `val_projects`/
`val_audit_trail` tables remain as read-only history; no route or UI reaches them anymore.

### Validation Management Suite
- **Validation Document Generator (wizard, v0.6)** — live, wired into the UI. 11 doc types
  (URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation, Change Control), 4-step wizard,
  `temperature=0.3` generation, DOCX export + client-side PDF export, save to project.
- **Validation Workspace (v0.8, partial)** — `val_projects`/`val_audit_trail`, owner/approver/
  target-date/risk-category tracking, initial UI. Full approval workflow not yet built.
- **Risk Management Suite** — backend-complete (`risk_database.py`, `routes/risk.py`,
  `services/risk_service.py`, `prompts/risk_prompt.py`, `risk.css`/`risk.js`). **Sidebar
  navigation not wired** — no live entry point in the current build.
- **URS Management Suite** — backend-complete (`urs_database.py` + `urs_requirement_library.py`,
  `routes/urs.py`, `services/urs_service.py`, `urs.css`/`urs.js`). **Sidebar navigation not
  wired.**
- **Qualification Suite (IQ/OQ/PQ)** — backend-complete (`qual_database.py`, 997 lines,
  `routes/qual.py`, `services/qual_service.py`, `qual.css`/`qual.js`). **Sidebar navigation not
  wired.**
- **Validation Report Suite** — backend-complete (`report_database.py`, `routes/report.py`,
  `services/report_service.py`, `report.css`/`report.js`). **Sidebar navigation not wired.**

### Knowledge Base
Live and wired. Project-independent document library, 8 fixed folders, rich metadata (tags,
version, effective/review dates), 4 combinable search filters, detail/preview panel with
overdue-review highlighting, uses the async Document Intelligence Engine.

### Document Intelligence Engine
Live. Async, multi-engine (pypdf → pdfplumber → PyMuPDF → OCR-placeholder for PDF; python-docx;
openpyxl), per-page timeout with automatic fallback, background-thread execution, quality scoring,
retry-on-failure. Replaced the earlier synchronous single-engine extractor entirely. Full detail
in [ARCHITECTURE.md](ARCHITECTURE.md) §9.

### AI Assistant
Live. Core chat (`POST /stream`, SSE), project-scoped conversation history, optional
"Use Project Documents" context injection (keyword/Jaccard RAG, max ~2,500 words injected),
sources strip, Document Insights panel.

### URS Management Suite
See Validation Management Suite above (backend-complete, nav not wired).

### Risk Management Suite
See Validation Management Suite above (backend-complete, nav not wired).

### Qualification Suite
See Validation Management Suite above (backend-complete, nav not wired).

### Validation Report Suite
See Validation Management Suite above (backend-complete, nav not wired).

### Quality Management Suite *(uncommitted, functionally complete)*
- **Document Control** — SOP/Protocol/etc. lifecycle, auto-numbering, version history, training
  tracking, distribution/acknowledgement, AI draft generation, AI compliance review.
- **Deviation** — severity/category classification, full investigation lifecycle, AI Investigation
  Assistant (Fishbone + 5-Why + timeline + root cause), AI impact assessment, AI CAPA suggestions.
- **CAPA** — corrective/preventive actions, escalation, effectiveness checks, AI draft/
  effectiveness suggestions, AI Quality Trend Summary.
- **Change Control** *(Phase 2)* — Equipment/Facility/Utility/Software/Process/Documentation/
  Specification/Engineering/Quality-System changes; Major/Minor/Critical/Temporary/Permanent/
  Emergency types; 13-stage workflow (Draft → ... → Closed) with rejection at every stage; AI
  impact assessment, implementation plan/checklist, risk summary, rollback plan, regulatory impact,
  change justification, executive summary, verification summary, effectiveness review; links to
  existing Deviations/CAPAs.
- Shared across all four: Attachments, Comments, Audit Trail, E-Signature/Approval, Print, DOCX
  Export, Status Badges, unified cross-module QMS dashboard.

### Document Control
See Quality Management Suite above.

### Deviation
See Quality Management Suite above.

### CAPA
See Quality Management Suite above.

### Change Control
See Quality Management Suite above.

---

## Modules Planned

| Module | Phase | Status |
|---|---|---|
| Change Control | QMS Phase 2 | **Done** (uncommitted — see Current Sprint / Completed Modules) |
| Non-Conformance | QMS Phase 2 | Not started |
| OOS/OOT | QMS Phase 2 | Not started |
| Audit | QMS Phase 3 | Not started |
| Supplier Quality | QMS Phase 3 | Not started |
| Training | QMS Phase 3 | Not started |
| Complaint Management | QMS Phase 3 | Not started |
| Equipment as a First-Class Entity | PharmaGPT v1.0 Module 2 | **Done** (uncommitted — see Completed Modules) |
| Project Workspace & Navigation Refactoring | PharmaGPT v1.0 Module 3 | **Done** (uncommitted — see Current Sprint / Completed Modules). Completes the Foundation Refactoring (Modules 1–3). |
| Calibration | Equipment sub-module (future) | Not started — architecture prepared (FK to `equipment.id`) |
| Preventive Maintenance | Equipment sub-module (future) | Not started — architecture prepared |
| Breakdown History | Equipment sub-module (future) | Not started — architecture prepared |
| Spare Parts | Equipment sub-module (future) | Not started — architecture prepared |
| Vendor Qualification | Equipment sub-module (future) | Not started — architecture prepared |
| Environmental Monitoring | Equipment sub-module (future) | Not started — architecture prepared |
| Utilities | Equipment sub-module (future) | Not started — architecture prepared |
| Asset Management | Equipment sub-module (future) | Not started — architecture prepared |

### Manufacturing Excellence Suite
| Module | Status |
|---|---|
| MES | Not started — no code, mentioned only as long-term platform vision |
| LIMS Integration | Not started |
| ERP Integration | Not started |

---

## Known Issues

From the repository's own code review (`docs/CODE_REVIEW.md`, scope v0.7, findings recorded but
**not yet fixed in code**):

- **Security (highest priority):** unsanitized `marked.parse()` output rendered via `innerHTML` in
  `chat.js` (XSS risk — no DOMPurify); hardcoded fallback secret key `"pharmagpt-dev-secret-key"`
  in `config.py`; no CSRF protection on POST/DELETE routes; silent exception swallowing in
  extraction-storage helpers (no logging); no rate limiting on `/stream` or
  `/validation/generate`; unused/misleading `session_id` implying isolation that doesn't exist.
- **Functional bug:** `doc_ids` parameter accepted but ignored in `/validation/generate` — a
  user's Step 3 document selection is silently discarded and search runs against all project
  documents instead.
- **Performance:** full text corpus loaded into RAM on every RAG search (no caching/index); no DB
  indexes on FK/filter columns; unbounded in-memory `history_cache` dict.
- **Duplication:** near-identical `_extract_and_store()` / `_extract_and_store_kb()` helpers;
  duplicated `esc()`/`escHtml()` helpers across 3+ JS modules; competing `showView()`
  implementations between the global scope and `val_workspace.js`.
- **UI gap:** Risk/URS/Qual/Report suites have no live sidebar navigation entry point (see
  Completed Modules above).
- **No "Related Change Controls" tab in Deviation/CAPA:** Change Control (QMS Phase 2) can link to
  an existing Deviation or CAPA, and a reverse-lookup helper
  (`qms_change_control_database.get_change_controls_for_record()`) is queryable, but
  `qms_deviations.js`/`qms_capa.js` were not modified to surface it — deferred per the "don't modify
  completed modules unless integration requires it" instruction. See DECISIONS.md DEC-021.
- **Risk Assessment/URS/Qualification/Validation Report Project Workspace tabs are live entry
  points, not project-filtered views (introduced by Module 3, 2026-07-10):** those four tables have
  no `project_id` (or `equipment_id`) column at all — clicking through from the Project Workspace
  opens the suite's existing global dashboard, unfiltered, with no "back to project" link inside the
  suite itself (returning today means reselecting the project from the sidebar). See
  [DECISIONS.md](DECISIONS.md) DEC-025 Future Review — fix by adding `project_id`/`equipment_id` FKs
  to those tables.
- **Equipment Profile "Validation History" and "Related Risk Assessments" are approximations/
  placeholders (introduced by Module 2, 2026-07-10):** Risk/URS/Qualification/Validation Report and
  `generated_documents` do not yet carry an `equipment_id` FK, so the Profile page's Validation
  History tab shows the *project's* generated-document history (not filtered to this specific
  Equipment record) and Related Risk Assessments is an empty-state placeholder. See
  [DECISIONS.md](DECISIONS.md) DEC-023 Future Review — fix by adding `equipment_id` to those tables
  once their wizards are updated to collect it.
- **Visual parity gap (introduced 2026-07-05):** `docx_generator.py`/`doc_exporter.py` still emit
  the pre-redesign navy heading/table styling in exported `.docx` files — the on-screen "Executive
  Office" redesign (DEC-018) deliberately did not touch Python-generated document styling (UI-only
  mandate). Recommended follow-up: repaint exported-document colours to Walnut Brown/Warm Charcoal
  to match the on-screen viewer.
- **Competing `showView()` implementations** entry above is the same *class* of bug as the
  `renderWizardStep`/`renderApprovalPanel` collision found and fixed between `risk.js` and `urs.js`
  during the 2026-07-05 UI audit (DEC-020) — this codebase's suite `.js` files are not IIFE-wrapped
  or namespaced, so any two suites declaring a same-named top-level function will silently collide
  (last-loaded wins). The `val_workspace.js`/global `showView()` pair listed here has not itself
  been fixed (out of scope for the UI audit, which fixed only the specific instance it found live-
  broke a wizard); treat this as a live, not just theoretical, risk for any future suite work.

## Resolved Issues

- **Extraction timeout/crash on large PDFs** — resolved by the Document Intelligence Engine
  rewrite (async, per-page-timeout, multi-engine fallback). See
  [RELEASE_NOTES.md](RELEASE_NOTES.md).
- **`get_dashboard_stats()` counting stale data** — previously counted pending CAPAs/Deviations
  from legacy `generated_documents` wizard rows instead of the real `qms_capas`/`qms_deviations`
  tables; fixed as part of the (uncommitted) QMS Phase 1 work.
- **Views rendered outside the sidebar layout (blank space / no sidebar bug)** — `templates/
  index.html`'s `.app-body` closing `</div>` was misplaced immediately after the old Validation
  Document Generator view instead of after the last view in the file, since the 2026-06-30 Risk/
  URS/Qual/Report commit. Every view after that point (Generate Document, all Risk views, all URS
  views, Qualification, Validation Report, all QMS views) rendered as a sibling of `.app-body` at
  the `<body>` level — full-width, no sidebar, with the collapsed-but-still-flex-sized `.app-body`
  showing as blank space above it. Fixed as part of the Enterprise Workspace redesign (2026-07-04);
  see [DECISIONS.md](DECISIONS.md) DEC-017.
- **Icon sweep completed** — the Lucide icon conversion left incomplete by DEC-019 (Risk/URS/
  Qualification/Validation Report suite-internal emoji, 484 occurrences across 18 files) was
  finished during the 2026-07-05 pre-deployment UI audit; zero emoji remain anywhere in the
  codebase. See [DECISIONS.md](DECISIONS.md) DEC-020.
- **Risk Management Suite's "New Assessment" wizard and Approval panel silently not rendering** —
  root cause was a global-scope function-name collision: `risk.js` and `urs.js` both declared
  top-level `renderWizardStep()`/`renderApprovalPanel()`, and since `urs.js` loads after `risk.js`
  in `templates/index.html`, URS's versions silently overwrote Risk's. Pre-existing defect, never
  caught before because Risk's sidebar nav is unwired; found and fixed (renamed risk.js's copies to
  `riskRenderWizardStep`/`riskRenderApprovalPanel`) during the 2026-07-05 UI audit. See
  [DECISIONS.md](DECISIONS.md) DEC-020.
- **URS empty-state layout broken (icon/title/button laid out in a row instead of stacked)** —
  `.urs-empty` was missing `flex-direction: column; align-items: center`; `urs.js` toggles it to
  `display: flex` via inline style, which without that property defaults to `flex-direction: row`.
  Fixed during the 2026-07-05 UI audit. See [DECISIONS.md](DECISIONS.md) DEC-020.
- **Validation Report Management Suite rendered in a pre-DEC-018 dark theme at ~70% width** — the
  entire content area (`report.css`/`report.js`, ~45+ declarations plus 30 inline styles) was still
  styled with dark card/table/panel backgrounds and light text, a leftover neither DEC-018 nor
  DEC-019's automated hex-value sweeps could detect (they correctly translated the literal hex
  values without knowing those values' *role* — a dark card — was wrong for a light theme); compounded
  by `.report-container` missing `flex: 1`, leaving the suite narrower than every other view. Fixed
  during the 2026-07-05 UI audit (property-aware light-theme conversion, print/export `<style>`
  templates in `risk.js`/`validation.js` deliberately kept dark-header-with-white-text since that's
  correct for a printed document). See [DECISIONS.md](DECISIONS.md) DEC-020.

## Known Limitations

- No authentication or authorization system (planned v0.9).
- No migration framework — schema changes require either the additive-column-guard pattern or a
  destructive dev-only DB reset.
- Real OCR is not implemented (`OCRPlaceholderEngine` always raises) — scanned/image-only PDF
  pages cannot be extracted yet.
- Password-protected PDFs fail extraction (only an empty-password attempt is made).
- CPython cannot forcibly terminate a hung extraction thread — a timed-out attempt is abandoned,
  not killed (documented, low-impact given daemon-thread design).
- E-signatures are typed-name only, no PKI (acceptable pre-auth; needs revisit once real auth
  exists).
- No CI pipeline configuration in the repository — testing is manual.
- Desktop-first UI (1280px+); mobile responsiveness is not yet a priority.

## Future Improvements

See Roadmap above. Near-term priorities per the code review: DOMPurify sanitization, required
(non-default) secret key, CSRF protection, extraction-error logging, then rate limiting, DB
indexes, and the `doc_ids` bug fix.

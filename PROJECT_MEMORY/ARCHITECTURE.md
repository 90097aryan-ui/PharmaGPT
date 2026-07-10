# ARCHITECTURE.md — PharmaGPT System Architecture

> Part of the permanent [PROJECT_MEMORY](CLAUDE.md) set. Describes the system as it exists in the
> working tree at commit `684ca7d` (v0.9.8) plus the uncommitted QMS Phase 1 work — see
> [PROJECT_STATUS.md](PROJECT_STATUS.md) for what's committed vs. in-progress.

---

## 1. System Overview

PharmaGPT is a **monolithic Flask web application** with a vanilla-JavaScript single-page
frontend. All application logic, file storage, and the database live in a single process on a
single machine — there are no microservices, message queues, or external caches.

```
 Browser (SPA)
     │  HTTP + Server-Sent Events (SSE)
     ▼
 Flask App (pharmagpt/app.py)
     │
     ├── SQLite (pharmagpt.db)  ── all persistent state
     ├── File System (uploads/{project_id}/, uploads/kb/)
     └── Google Gemini API (external, gemini-2.5-flash)
```

Rationale for the monolith (see [DECISIONS.md](DECISIONS.md) DEC-002): zero infrastructure to run
(`python -m flask run`), trivial to debug (single process, no distributed tracing), and a
documented migration path exists for each shortcut (SQLite → PostgreSQL, in-memory history cache →
Redis) when v1.0 scale requires it.

---

## 2. Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.14.6 | |
| Web framework | Flask 3.1.3 + Werkzeug 3.1.8 | Blueprint-per-domain |
| Production server | gunicorn 26.0.0 | `--workers=2 --threads=4 --timeout=60` |
| Database | SQLite 3 | raw `sqlite3` module, no ORM |
| AI | Google `google-genai` 2.10.0, model `gemini-2.5-flash` | streaming + non-streaming calls |
| Document generation | `python-docx` 1.2.0 | custom Markdown → DOCX state machine |
| Document extraction | `pypdf`, `pdfplumber`, `PyMuPDF`, `openpyxl` | multi-engine fallback pipeline |
| Frontend | Vanilla JavaScript (ES modules as IIFEs) | no build step, no framework |
| Templating | Jinja2 (single shell template) | `templates/index.html` |
| Background jobs | `concurrent.futures.ThreadPoolExecutor` | via `services/job_runner.py` |
| Deployment | Render (`render.yaml` + `Procfile`) | persistent disk for SQLite file |
| Testing | pytest 8.3.4 | `tests/`, ~83 tests total |

---

## 3. Folder Structure

```
D:\PharmaAgent\
├── pharmagpt/
│   ├── app.py                    Flask app factory; registers all blueprints; calls init_db()
│   ├── config.py                 Env-driven config: Gemini model, secret key, upload limits,
│   │                              extraction timeouts (PAGE_TIMEOUT_SECONDS, GC_INTERVAL_PAGES,
│   │                              EXTRACTION_WORKERS)
│   ├── database.py                Core schema + CRUD: projects, messages, documents,
│   │                              document_text, generated_documents, val_projects,
│   │                              val_audit_trail, kb_documents, dashboard stats
│   ├── state.py                   Shared runtime singletons: Gemini client, per-project
│   │                              conversation history cache (in-memory dict)
│   ├── logging_config.py          Logging setup
│   ├── documents.py                File upload/download utilities, filename collision handling
│   ├── prompts.py                  PHARMA_SYSTEM_PROMPT (core chat persona)
│   ├── risk_database.py            Risk Management Suite schema + CRUD
│   ├── urs_database.py             URS Management Suite schema + CRUD
│   ├── qual_database.py            Qualification (IQ/OQ/PQ) Suite schema + CRUD (997 lines)
│   ├── report_database.py          Validation Report Suite schema + CRUD
│   ├── qms_database.py             QMS shared polymorphic schema (attachments/comments/
│   │                              audit_trail/approvals) + numbering helpers   [uncommitted]
│   ├── qms_document_database.py    QMS Document Control schema + CRUD          [uncommitted]
│   ├── qms_deviation_database.py   QMS Deviation Management schema + CRUD      [uncommitted]
│   ├── qms_capa_database.py        QMS CAPA schema + CRUD                      [uncommitted]
│   ├── qms_change_control_database.py  QMS Change Control schema + CRUD (Phase 2) [uncommitted]
│   ├── equipment_database.py       Equipment entity schema + CRUD (PharmaGPT v1.0 Module 2)
│   │                              [uncommitted]
│   │
│   ├── routes/                    One Flask Blueprint per domain (see §5)
│   ├── services/                  Business logic / AI orchestration (see §6)
│   ├── services/extraction/       Document Intelligence Engine (see §8)
│   ├── review/                    Deterministic (non-AI) validation-document scoring engine
│   ├── equipment/profiles/        Equipment-type reference libraries (analytical, manufacturing,
│   │                              packaging, processing, quality_control, sterilization, testing)
│   ├── prompts/                   Per-domain Gemini prompt templates (17 files)
│   ├── static/css/                style.css (core, ~3,300 lines) + workspace.css (reusable
│   │                              Enterprise Workspace shell, see §7) + one CSS file per suite
│   │                              (risk.css, urs.css, qual.css, report.css, qms.css)
│   ├── static/js/                 One IIFE module per feature area (19 files, see §7), plus
│   │                              workspace.js (shared Enterprise Workspace shell helper)
│   ├── templates/index.html       Single SPA shell — all views are JS-toggled divs
│   └── uploads/                   {project_id}/ per-project files, kb/ Knowledge Base files
│
├── tests/                         pytest suite (~83 tests; see PROJECT_STATUS.md)
├── docs/                          Detailed reference docs (ARCHITECTURE, DESIGN_SYSTEM,
│                                  PRODUCT_REQUIREMENTS, CODE_REVIEW, QMS_PHASE1, ROADMAP,
│                                  CHANGELOG — some entries supersede root-level files; see
│                                  DECISIONS.md DEC-014 for which is authoritative)
├── PROJECT_MEMORY/                This document set (permanent project memory)
├── API.md, DATABASE.md            Root-level fine-grained technical references
├── render.yaml, Procfile          Deployment configuration
└── requirements.txt               Full pinned dependency list (pip freeze)
```

---

## 4. Database Architecture

Raw `sqlite3` throughout — no ORM (DEC-002). Every function opens and closes its own connection;
`PRAGMA foreign_keys = ON` is set on every connection because SQLite disables FK enforcement by
default. Row access uses `sqlite3.Row` (dict-like).

**No migration framework** (no Alembic / Flask-Migrate). Two coexisting strategies:
1. **Dev-only full reset** — delete `pharmagpt.db`, restart, `init_db()` recreates everything
   (documented as acceptable only pre-v1.0/pre-Postgres).
2. **Additive-only column guard** — `_add_column_if_missing()` pattern gated on
   `PRAGMA table_info()`, used by the Document Intelligence Engine to add extraction-progress
   columns without a destructive reset. **This is the required pattern for all future schema
   changes** (see [CLAUDE.md](CLAUDE.md) Development Rules).

**Table families:**

| Family | Tables | Owner file |
|---|---|---|
| Core | `projects`, `messages`, `documents`, `document_text`, `generated_documents` | `database.py` |
| Validation Workspace (v0.8) — **retired, read-only history** (DEC-024) | `val_projects`, `val_audit_trail` | `database.py` |
| Knowledge Base | `kb_documents` | `database.py` |
| Risk Management | risk assessment tables (hazard/likelihood/severity/mitigation) | `risk_database.py` |
| URS Management | URS projects + requirements | `urs_database.py` |
| Qualification | IQ/OQ/PQ phase + results tables | `qual_database.py` |
| Validation Report | report templates + completion records | `report_database.py` |
| QMS shared *(uncommitted)* | `qms_attachments`, `qms_comments`, `qms_audit_trail`, `qms_approvals` — all polymorphic on `(record_type, record_id)`, `record_type ∈ {document, deviation, capa, change_control}` | `qms_database.py` |
| QMS Document Control *(uncommitted)* | `qms_documents`, `qms_document_versions`, `qms_document_distribution`, `qms_document_training` | `qms_document_database.py` |
| QMS Deviation *(uncommitted)* | `qms_deviations`, `qms_deviation_investigation`, `qms_deviation_impact`, `qms_deviation_capa_link` | `qms_deviation_database.py` |
| QMS CAPA *(uncommitted)* | `qms_capas`, `qms_capa_actions`, `qms_capa_effectiveness` | `qms_capa_database.py` |
| QMS Change Control *(Phase 2, uncommitted)* | `qms_change_controls`, `qms_change_control_impact`, `qms_change_control_actions`, `qms_change_control_links` | `qms_change_control_database.py` |
| Equipment *(v1.0 Module 2, uncommitted)* | `equipment`, `equipment_documents` (polymorphic link to `kb_documents`/`documents`) | `equipment_database.py` |

Full column-level detail lives in the root-level `DATABASE.md` — this file summarizes structure
and relationships only.

**Foreign key policy:** most FKs `ON DELETE CASCADE` (child data is meaningless without the
parent). QMS master tables (`qms_documents`/`qms_deviations`/`qms_capas`) instead use a nullable
`project_id` with `ON DELETE SET NULL` — a deliberate choice (DEC-011) since GxP quality records
must legally outlive the equipment/project record that originated them.

---

## 5. Route Layer

14 Flask blueprints, registered in `pharmagpt/app.py`:

| Blueprint file | Name | URL prefix | Domain |
|---|---|---|---|
| `routes/projects.py` | `projects` | (none) | Project CRUD, chat history |
| `routes/chat.py` | `chat` | (none) | `POST /stream` — SSE AI chat |
| `routes/docs.py` | `documents` | (none) | Document upload/view/download/delete, extraction status |
| `routes/validation.py` | `validation` | (none) | One-shot validation document generator (wizard) |
| `routes/knowledge_base.py` | `knowledge_base` | (none) | Global Knowledge Base CRUD/search |
| `routes/dashboard.py` | `dashboard` | (none) | Home dashboard stats |
| `routes/risk.py` | `risk` | `/risk` | Risk Management Suite |
| `routes/urs.py` | `urs` | `/urs` | URS Management Suite |
| `routes/qual.py` | `qual` | `/qual` | Qualification (IQ/OQ/PQ) Suite |
| `routes/report.py` | `report` | `/report` | Validation Report Suite |
| `routes/qms_common.py` *(uncommitted)* | `qms_common` | `/qms` | QMS meta, dashboard, shared attachments/comments/audit/approval endpoints |
| `routes/qms_documents.py` *(uncommitted)* | `qms_documents` | `/qms/documents` | Document Control |
| `routes/qms_deviations.py` *(uncommitted)* | `qms_deviations` | `/qms/deviations` | Deviation Management |
| `routes/qms_capa.py` *(uncommitted)* | `qms_capa` | `/qms/capa` | CAPA |
| `routes/qms_change_control.py` *(Phase 2, uncommitted)* | `qms_change_control` | `/qms/change-control` | Change Control |
| `routes/equipment.py` *(v1.0 Module 2, uncommitted)* | `equipment` | (none) | Equipment CRUD, search, document links, AI-context bundle |

Full endpoint-level detail (every method/path/purpose) lives in the root-level `API.md`.

**Known gap (partially addressed by Module 3):** the Risk, URS, Qualification, and Validation Report
suites' own sidebar navigation containers still exist in `templates/index.html` but remain
`display:none` with no wired toggle. PharmaGPT v1.0 Module 3 gave all four a *different* live entry
point — a tab inside the Project Workspace (`view-project-workspace`) that calls the existing generic
`window.showView()` + each suite's `initX()` bootstrap — but this is not project-filtered (none of
these four tables have a `project_id` column) and does not re-enable their own sidebar sections. See
[PROJECT_STATUS.md](PROJECT_STATUS.md) → Known Issues and [DECISIONS.md](DECISIONS.md) DEC-025.

---

## 6. Service Layer

`pharmagpt/services/` — business logic and AI orchestration, kept separate from route handlers.

**Core / cross-cutting:**
- `document_processor.py` — async extraction orchestrator (submits to `job_runner`)
- `document_search.py` — keyword/Jaccard RAG search over project documents (feeds `/stream`)
- `retrieval_engine.py` — LLM-based document retrieval/ranking
- `doc_generator.py` — shared AI document-generation framework (validation wizard, risk, etc.)
- `doc_exporter.py` / `docx_generator.py` — Markdown → DOCX export (state-machine converter)
- `docx_reader.py`, `excel_reader.py` — format-specific text extraction (used by extraction engines)
- `job_runner.py` — `JobRunner` interface; active implementation `ThreadPoolJobRunner`
  (`ThreadPoolExecutor`); `CeleryJobRunner` stub reserved for future Redis-backed swap

**Per-domain AI services** (each pairs with a `prompts/*_prompt.py` template):
- `risk_service.py`, `urs_service.py` (+ `urs_requirement_library.py`), `qual_service.py`,
  `report_service.py`
- `qms_shared.py` *(uncommitted)* — shared `call_gemini()` / `stream_gemini()` /
  `parse_json_response()` helpers used by all four QMS services below
- `qms_document_service.py`, `qms_deviation_service.py`, `qms_capa_service.py` *(uncommitted)*
- `qms_change_control_service.py` *(Phase 2, uncommitted)*
- `equipment_service.py` *(v1.0 Module 2, uncommitted)* — `get_equipment_context_bundle()`
  (architecture-only AI-context data assembly, not yet called from `doc_generator.py`) and
  `get_equipment_type_catalog()` (autocomplete against `pharmagpt/equipment/`)

---

## 7. Frontend Layer

No client-side router, no framework. `templates/index.html` is a single shell; every "page" is a
`<div>` toggled via `display`. Each feature area is one vanilla-JS file in `static/js/`, written
as an IIFE that exposes a small API on `window` (e.g. `window.ProjectModule`). SSE is used for
both chat (`/stream`) and AI generation endpoints, with a critical implementation detail: **Flask's
request context is not available inside a generator function** — all `request.*` data must be
captured in the outer function scope before `generate()` is defined.

20 JS modules: `workspace.js` *(2026-07-04 — shared Enterprise Workspace shell, see below)*,
`dashboard.js`, `projects.js`, `chat.js`, `documents.js`, `insights.js`,
`validation.js`, `validation_config.js`, `knowledge_base.js`,
`gen_document.js`, `risk.js`, `urs.js`, `qual.js`, `report.js`, and *(uncommitted)* `qms_common.js`,
`qms_documents.js`, `qms_deviations.js`, `qms_capa.js`, `qms_change_control.js` *(Phase 2)*,
`equipment.js` *(v1.0 Module 2 — Equipment list/CRUD + Enterprise-Workspace-based Equipment Profile
page; all top-level functions `eq`-prefixed per the DEC-020 collision lesson)*,
`project_workspace.js` *(v1.0 Module 3 — the unified Project Workspace shell; `pw`-prefixed
functions; replaces the deleted `val_workspace.js`)*. `val_workspace.js` (legacy Validation Workspace)
was deleted by Module 3 — see DEC-024.

**Enterprise Workspace layout (`workspace.css` + `workspace.js`, 2026-07-04).** A reusable
full-screen "workspace" shell for any module that walks a user through a stateful, multi-step or
multi-tab flow — introduced during the Validation & Usability Testing Sprint and first applied to
Generate Document (`view-gen-doc` / `gen_document.js`). The pattern:

```
<main class="ent-workspace">        (fills .app-body; replaces the Dashboard entirely, not layered on top of it)
  .ent-ws-header                    dark bar: icon, title, "current project" / "current document" tags
  .ent-ws-toolbar                   breadcrumb (Dashboard > Project > Module > Step) + Back to
                                     Project / Save Draft / Cancel buttons
  .ent-ws-progress                  optional step-progress dots
  ...module-owned scrollable content (e.g. Generate Document's existing .gd-panel / .gd-step-content)...
```

`window.Workspace` (`workspace.js`) provides `enter()`/`exit()` (toggles `body.ent-ws-active`,
which hides the global top `<header>` so only the sidebar remains while a workspace is open),
`renderBreadcrumb()`, `renderProgress()`, and `confirmDialog()` (a styled Yes/No modal reusing the
existing `.modal`/`.btn-primary`/`.btn-secondary`/`.btn-danger` tokens instead of a native
`confirm()`). See [DECISIONS.md](DECISIONS.md) DEC-017 for the full root-cause writeup — the
motivating bug was a misplaced `.app-body` closing `</div>` that had, since the 2026-06-30 Risk/
URS/Qual/Report commit, put every view after the old Validation Document Generator view outside
the sidebar-flex layout entirely (fixed as part of the same change).

**Adoption contract for future modules:** wrap the module's view in `<main class="ent-workspace">`
with `.ent-ws-header`/`.ent-ws-toolbar`/`.ent-ws-progress` rows, call `Workspace.enter()` when the
view opens and `Workspace.exit()` when leaving it, and use `Workspace.confirmDialog()` for any
"unsaved changes" / "discard changes" prompts rather than inventing a new header or modal. Risk,
URS, Qualification, Validation Report, and future QMS Phase 2/3 modules (Change Control,
Non-Conformance, OOS/OOT, Audit, Supplier Quality, Training, Complaint Management) are expected to
adopt this same shell once their sidebar navigation is wired up, instead of each building its own.
The Equipment Profile page (v1.0 Module 2, `view-equipment-profile`) is the shell's second live
consumer — reachable from the Equipment tab rather than a sidebar nav item, so
`window.__ws_setActiveView()` was generalized from a single hardcoded `"view-gen-doc"` string
comparison to a `Set` of workspace view IDs (`equipment.js`'s `eqOpenProfile()`/`eqBackToList()`
call the same `enter()`/`exit()` contract as Generate Document). The Project Workspace (v1.0 Module
3, `view-project-workspace`) is the third — opened directly when a project is selected, and itself
the new home for the Equipment tab (`eqBackToList()` now calls `project_workspace.js`'s
`window.pwShowTab('equipment')` instead of referencing a since-deleted standalone view). It
introduces a new generic `.ws-tabs`/`.ws-tab` tab-strip component in `workspace.css`, visually
identical to `.eq-tabs`/`.eq-tab` (Equipment Profile) and `.qms-tabs`/`.qms-tab` (QMS), kept as its
own name so any future Enterprise Workspace consumer can reuse one shared tab-strip component.

---

## 8. AI Layer

Single Gemini client singleton (`state.py`), model `gemini-2.5-flash`, shared across every
feature. Two calling conventions:
- **Streaming** (SSE) — interactive chat, validation-doc generation, QMS document drafting —
  `temperature=0.3` for structured document generation (vs. default for conversational chat) to
  keep formal-document structure consistent across generations (DEC-006).
- **Non-streaming** (single JSON response) — AI Investigation Assistant, impact-assessment
  suggestions, CAPA suggestions, compliance review, quality trend summaries.

Prompts are centralized per domain in `pharmagpt/prompts/` (17 files) rather than inlined in
routes/services — reuse these before writing a new prompt.

---

## 9. Document Intelligence Engine (`services/extraction/`)

Replaces the earlier synchronous, single-engine (`pdfplumber`-only) extractor — the old
`extractor.py`/`pdf_reader.py` were deleted, not kept as a fallback (DEC-009). This rewrite was
triggered by a production incident on Render: a 48-page/1.43MB real-world manual caused a
synchronous in-request `pdfplumber` call to exceed the gunicorn worker timeout, producing a
`SIGKILL` and an HTTP 500 for the user.

**Extraction pipeline:**
1. Route layer (`routes/docs.py`, `routes/knowledge_base.py`) saves the file, inserts a `pending`
   DB row, and **returns HTTP 201 immediately** — extraction never blocks the upload request.
2. `document_processor.py::process_document_async()` is the single entry point.
3. `job_runner.py::ThreadPoolJobRunner.submit()` dispatches the work to a background thread.
4. `extraction/pipeline.py::extract_document()` loops page-by-page: try the primary engine
   (timeout-bounded) → on failure/timeout, try the next engine in the fallback chain → on total
   failure for that page, log and skip it, continuing the document. Progress is reported via a
   callback every page.
5. Result is written back into `document_text` / `kb_documents`; status flows
   `pending → processing → ok | partial | empty | failed`.
6. Frontend polls a `/status` endpoint every 1.5s and offers a **Retry Extraction** action on
   failure — the uploaded file is never deleted, so retry is always possible.

**Fallback chains** (`extraction/registry.py`):

| Format | Engine order |
|---|---|
| PDF | `pypdf` (primary, fastest) → `pdfplumber` (best layout/table fidelity) → `PyMuPDF` (most resilient to malformed PDFs) → `OCRPlaceholderEngine` (always raises — real OCR not implemented yet) |
| DOCX | `python-docx` |
| XLSX | `openpyxl` |
| TXT | plain read |

Fallback operates at two levels: **document-level** (which engine can even open the file) and
**page-level** (a specific page fails/times out on the primary engine — the next engine is opened
lazily, cached, and retried just for that page).

**Timeout mechanism:** each page-extraction attempt runs in its own fresh daemon thread, joined
with a configurable `PAGE_TIMEOUT_SECONDS` (default 10s). Known CPython limitation: a hung thread
cannot be force-killed — it is abandoned, not terminated. A `ProcessPoolExecutor`-based redesign
is the documented future path if this becomes a real problem (DEC-009).

**Memory management:** pages are processed one at a time; engine-specific caches are flushed after
each page; `gc.collect()` runs every `GC_INTERVAL_PAGES` (default 20) pages and once more after the
whole document completes.

**Quality scoring** (`extraction/stats.py`): `quality_score = pages_extracted / page_count * 100`
(1 decimal place). Status derives from this: `ok` (100%), `partial` (some pages failed), `empty`
(zero extractable text), `failed` (could not open the file at all).

**Background execution:** `ThreadPoolExecutor`, not Celery (DEC-004) — appropriate for the current
Flask + gunicorn + SQLite-on-Render stack with no Redis. All progress/results persist to SQLite
(not process memory), so status polling works correctly across gunicorn's multiple worker
processes.

**Backward compatibility:** every existing consumer of extracted text
(`document_search.py`, `retrieval_engine.py`, chat, validation generation, Risk/URS/Qual/Report
context injection) reads `document_text`/`kb_documents` unchanged, filtered on
`extraction_status='ok'` — zero code changes were required in those consumers. The only visible
behavior change is that a freshly-uploaded document is briefly invisible to search/RAG while
extraction runs in the background.

Full architectural detail (performance benchmarks, test fixture list, page-timeout regression
test) lives in the root-level `SYSTEM_ARCHITECTURE_DOCUMENT_PROCESSING.md`.

---

## 10. Knowledge Base

Project-independent document library (`kb_documents` table, files under `uploads/kb/`). 8 fixed
folders (SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents,
Others), metadata (title, tags, version, effective date, review date), 4 combinable search filters
(title, tag, file type, keyword). Uses the same Document Intelligence Engine as project documents
(async extraction, status polling, retry).

---

## 11. Validation Suite

Two distinct, currently-coexisting mechanisms — do not conflate them:

- **Validation Document Generator (wizard, v0.6)** — one-shot AI generation across 11 doc types
  (URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation, Change Control) via a 4-step form,
  config-driven (`validation_config.js`), saved to `generated_documents`. This is a quick draft
  tool, not a stateful workflow.
- **Validation Workspace (v0.8) — retired (DEC-024)**. Its owner/approver/target-date/risk-category
  fields were merged onto the unified `projects` table by Module 1 ("Phase 2 Module 1"); its own
  separate `val_projects`-based dashboard/create-flow/tabbed detail view was deleted outright by
  Module 3 after being found still live and writable, duplicating the now-unified Project entity.
  `val_projects`/`val_audit_trail` remain as read-only history.
- **Risk / URS / Qualification / Validation Report suites** — dedicated, fully-built backend
  modules (each with its own database file, routes, service, prompts, CSS, JS) added in a single
  commit on 2026-06-30. Backend-complete; their own sidebar navigation is still not wired (see §5
  Known gap), but Module 3 gave all four a live entry point via a Project Workspace tab (unfiltered
  — see DEC-025).

---

## 12. Quality Management Suite *(uncommitted working-tree code)*

PharmaGPT's second major pillar, parallel in scope to the Validation pillar. Phase 1 shipped three
modules — Document Control, Deviation Management, CAPA — built on the shared polymorphic tables
described in §4, with a nested "Quality Management" sidebar section (chosen over flat top-level
entries because Phases 2/3 will add more modules; a flat structure would leave many top-level suite
sections). Phase 2 (Change Control) adds a fourth module to the same nested section using the
identical pattern.

- **Document Control** — lifecycle `Draft → Under Review → Pending Approval → Effective → Under
  Revision → Obsolete`; auto-numbered (`SOP-QA-0001`); version history; training tracking;
  distribution/acknowledgement; AI draft generation (streamed) and AI regulatory compliance review.
- **Deviation Management** — severities Minor/Major/Critical/Market; lifecycle `Initiated → ... →
  Closed`; AI Investigation Assistant (Fishbone/Ishikawa + 5-Why + timeline + root cause in one
  call); AI impact-assessment and CAPA-seed suggestions with one-click create-and-link.
- **CAPA** — Corrective/Preventive actions, owners, due dates, escalation, effectiveness checks, AI
  draft/effectiveness suggestions, AI Quality Trend Summary across CAPAs and Deviations.
- **Deviation ↔ CAPA linkage** — real queryable relation via `qms_deviation_capa_link`; linking
  auto-transitions the deviation to `CAPA Assigned`.
- **Change Control** *(Phase 2)* — Equipment/Facility/HVAC/Water System/Compressed Air/Steam/
  Electrical/Software/PLC/SCADA/MES/ERP/Barcode System/Vision System/BMS/LIMS/Validation/SOP/
  Specification/Packaging/Warehouse/Quality/Engineering/Production/Utilities/IT categories;
  Major/Minor/Critical/Temporary/Permanent/Emergency types; a 13-stage lifecycle `Draft → Submitted
  → Initial Review → Impact Assessment → Risk Assessment → Department Review → QA Review → Approval
  → Implementation → Verification → Effectiveness Review → Closed`, with rejection from any stage
  back to `Draft`; auto-numbered (`CC-2026-0001`); AI impact assessment across 14 standard impact
  areas (Validation, Qualification, Risk, URS, SOP, Training, Equipment, Documents, Software,
  Utilities, Regulatory Compliance, Business Continuity, Electronic Records, Electronic Signatures),
  AI implementation plan/checklist, and five further AI narrative features (risk summary, rollback
  plan, regulatory impact, change justification, executive summary, verification summary,
  effectiveness review) persisted into a single `ai_narratives` JSON column.
- **Change Control ↔ Deviation/CAPA linkage** — `qms_change_control_links`
  (`linked_type ∈ {deviation, capa}`), one-directional from Change Control; a reverse-lookup helper
  (`qms_change_control_database.get_change_controls_for_record()`) exists for a future "Related
  Change Controls" tab inside Deviation/CAPA's own views (not built — see DECISIONS.md DEC-021).

Full detail lives in `docs/QMS_PHASE1.md` (Phase 1) and `docs/QMS_PHASE2.md` (Change Control).

---

## 13. Project Workspace / Document Generator

See §11 above (Validation Document Generator) for the wizard mechanism, and `doc_exporter.py` /
`docx_generator.py` for the export mechanism (Markdown → DOCX via a custom state machine, plus
client-side `window.print()` for PDF — chosen to avoid a WeasyPrint/GTK dependency on the Windows
development environment, DEC-007).

---

## 14. Module Relationships

Two parallel pillars share the same shared-service foundation:

```
                 ┌─────────────┐
                 │   Project   │
                 └──────┬──────┘
                        │
                 ┌──────▼──────┐
                 │Knowledge Base│  (project-independent, but referenced for context)
                 └──────┬──────┘
                        │
        ┌───────────────┼────────────────┐
        ▼                                 ▼
 ┌─────────────┐                   ┌─────────────┐
 │    Risk     │                   │     URS     │
 └──────┬──────┘                   └──────┬──────┘
        │                                 │
        └───────────────┬─────────────────┘
                         ▼
              ┌─────────────────────┐
              │  IQ → OQ → PQ (Qual) │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │  Validation Report   │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │      Deviation       │◄──────────┐
              └──────────┬──────────┘            │
                         ▼                        │ qms_deviation_capa_link
              ┌─────────────────────┐            │
              │         CAPA         │────────────┘
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │    Change Control     │  (Phase 2, uncommitted — built)
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │       Training        │  (planned — not yet built)
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │        Audit          │  (planned — not yet built)
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │  Management Review    │  (planned — not yet built)
              └─────────────────────┘
```

**Accuracy note:** this end-to-end chain represents the *intended* platform vision. In the current
codebase, the Risk → URS → Qual → Report leg is backend-complete but not linked to Deviation/CAPA
by any foreign key today. The real, queryable cross-suite links that exist are
`qms_deviation_capa_link` (Deviation ↔ CAPA) and `qms_change_control_links` (Change Control →
Deviation/CAPA, one-directional — see §12). Change Control now exists (QMS Phase 2, uncommitted);
Training, Audit, and Management Review do not exist in the codebase yet.

---

## 15. Database Philosophy

- One SQLite file, no ORM, additive-only schema changes (§4).
- **Shared Attachments / Shared Comments / Shared Audit Trail / Shared Approval Engine** —
  implemented once as polymorphic QMS tables and intended to be reused by every future module
  (Phase 2/3 QMS modules, and ideally Change Control/Training/Audit when built) by adding a new
  `record_type` string rather than new tables.
- **Shared Notifications** — not yet implemented; planned as a `notifications` table + SSE
  delivery for v0.9. Do not assume this exists.

---

## 16. Security Principles

Per the repository's own code review (`docs/CODE_REVIEW.md`, scope v0.7, findings-only — no code
was modified as part of that review):

- No authentication/authorization system exists yet (planned v0.9, RBAC with roles).
- E-signatures across Risk/Qual/QMS approvals are **typed-name, not PKI-based** — sufficient for
  the current pre-auth stage, explicitly flagged as needing revisit once real auth exists.
- Known, not-yet-remediated issues from the code review: unsanitized `marked.parse()` output
  rendered via `innerHTML` in `chat.js` (XSS risk, needs DOMPurify), a hardcoded fallback Flask
  secret key in `config.py`, no CSRF protection on POST/DELETE routes, no rate limiting on
  streaming endpoints. **Treat these as open items** — see [PROJECT_STATUS.md](PROJECT_STATUS.md)
  → Known Issues. Do not introduce new unsanitized `innerHTML` usage or new unauthenticated
  state-changing routes without flagging the same class of risk.
- Uploads are constrained by `secure_filename`, a 50MB size cap, and MIME/extension checks (400,
  413, 415 responses on violation). `.env` and `.db` are excluded from version control; API keys
  are never exposed client-side.

---

## 17. Coding Standards Summary

SOLID, DRY, KISS — enforced in practice by file-size discipline (split by responsibility once a
file nears ~1000 lines) and by the Development Rules in [CLAUDE.md](CLAUDE.md).

---

## 18. Enterprise Scalability

- **Future PostgreSQL** — SQLite was chosen for zero-config v0.x development; a migration path is
  a stated v1.0 goal (DEC-003). Avoid SQLite-only syntax in new code where a Postgres-compatible
  alternative is equally simple.
- **Future Microservices** — not currently planned; the monolith is deliberate for this stage
  (DEC-002). Revisit only if a specific module (e.g., the extraction engine) needs independent
  scaling.
- **Cloud Architecture Vision** — Render today (single web service + persistent disk); Docker
  packaging and rate limiting/HTTPS/security headers are stated v1.0 goals.

---

## Platform Vision

Become an enterprise Pharmaceutical Digital Quality & Validation Platform comparable to
**TrackWise, MasterControl, and Veeva Vault Quality.**

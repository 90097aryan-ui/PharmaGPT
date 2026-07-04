# RELEASE_NOTES.md — PharmaGPT Release History

> Part of the permanent [PROJECT_MEMORY](CLAUDE.md) set. **This file is append-only.** Never
> rewrite or delete a past entry — add a new entry at the top for every release. Reconstructed
> from `git log`, the root-level `CHANGELOG.md`, and `docs/QMS_PHASE1.md` as of 2026-07-02.

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

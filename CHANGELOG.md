# Changelog

All notable changes to PharmaGPT are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-07-10 — PharmaGPT v1.0 Module 3: Project Workspace & Navigation Refactoring

### Added
- **Project Workspace** — "One Project = One Workspace": Equipment, Documents, Risk Assessment,
  URS, Qualification, Validation Report, Tasks, Approvals, and History are all reached from one
  unified workspace opened by selecting a project.
  - Ten tabs, built on the existing Enterprise Workspace shell (new reusable `.ws-tabs`/`.ws-tab`
    tab-strip component in `workspace.css`).
  - Equipment and Documents (+ Document Insights) tab content is the same markup/JS from the
    now-removed standalone views, moved in with zero rendering-logic changes.
  - Risk Assessment/URS/Qualification/Validation Report tabs are live entry points into those
    previously-unwired suites (not project-filtered — those tables have no `project_id` column,
    documented as a Known Issue).
  - Tasks and Approvals are placeholder tabs (architecture only, no new schema).
  - Project History tab reuses the shared `qms_audit_trail` table (`record_type='project'`);
    `routes/projects.py` create/update/delete now log to it.
  - `static/js/project_workspace.js`, `tests/test_project_workspace.py` (6 new tests).

### Removed
- **Legacy Validation Workspace** — retired entirely: `routes/workspace.py`,
  `static/js/val_workspace.js`, `vw-*` CSS, and its views/modal. It was still a fully live, writable
  flow on a separate `val_projects` entity, contradicting the unified `projects` table from the
  Module 1 merge. `val_projects`/`val_audit_trail` tables are untouched (historical data preserved);
  the dead `*_val_project`/`*_val_audit_entry` CRUD functions were removed from `database.py`.

### Fixed
- `window.selectProject` was never actually exposed on `window` by `projects.js`, silently breaking
  the Dashboard's "Recent Projects" card navigation. Fixed alongside `dashboard.js`.

---

## [Unreleased] — 2026-07-10 — PharmaGPT v1.0 Module 2: Equipment as a First-Class Entity

### Added
- **Equipment** — a real database entity owned by a Project, replacing free-text-only equipment
  info for new records (architecture and core functionality only — Calibration, Preventive
  Maintenance, Breakdown History, Spare Parts, Vendor Qualification, Environmental Monitoring,
  Utilities, and Asset Management are explicitly not built, only prepared for).
  - `equipment` table: Basic Information (Equipment ID/Name/Category/Type/Tag Number/Model/
    Manufacturer/Vendor/Serial Number/Asset Number), Installation Information (Plant/Block/
    Department/Area/Room/Line/Installation Date/Commissioning Date), Qualification Information
    (Qualification Status/Validation Status/Qualification Type/Criticality/GMP Impact).
  - `equipment_documents` table: polymorphic link to existing `kb_documents`/`documents` rows
    (User Manual/Vendor Manual/SOP/Drawing/P&ID/Electrical Drawing/Pneumatic Drawing/FAT/SAT/URS/
    Other) — never duplicates a document; the same manual is reusable across Equipment records.
  - Full REST API: project-scoped list/create, single-record CRUD, search, type-catalog
    autocomplete, document link/unlink/list, a legacy-import endpoint
    (`POST /projects/<id>/equipment/import-legacy`), and an AI-context-bundle endpoint
    (architecture only — not yet wired into document generation).
  - Project-scoped Equipment list view + an Equipment Profile page (Overview/Specifications/
    Documentation/Qualification/Validation History/Related Documents/Related Risk Assessments/
    Future Modules tabs) built on the existing Enterprise Workspace shell.
  - `equipment_database.py`, `routes/equipment.py`, `services/equipment_service.py`,
    `static/js/equipment.js`, `static/css/equipment.css`.
  - Additive-only changes to shared files: `database.py`, `app.py`, `templates/index.html`
    (nav item, two views, two modals, script/CSS tags, generalized workspace-view tracking).
  - `tests/test_equipment_database.py`, `tests/test_equipment_routes.py` — 33 new tests, all
    passing alongside the existing 109 (142 total).
  - `pharmagpt/equipment/` (the static per-type Intelligence Engine profile catalog) and
    `projects.equipment_name/manufacturer/model/equipment_id` (free text) are both unchanged —
    fully backward compatible.

### Fixed
- None — new functionality only.

---

## [Unreleased] — 2026-07-05 — Quality Management Suite (Phase 2: Change Control)

### Added
- **Change Control** — QMS's fourth module (Phase 2), built on the exact Phase 1 shared-table
  pattern (`record_type='change_control'`, no new shared table).
  - Equipment/Facility/HVAC/Water System/Compressed Air/Steam/Electrical/Software/PLC/SCADA/MES/ERP/
    Barcode System/Vision System/BMS/LIMS/Validation/SOP/Specification/Packaging/Warehouse/Quality/
    Engineering/Production/Utilities/IT change categories; Major/Minor/Critical/Temporary/Permanent/
    Emergency change types.
  - 13-stage lifecycle: Draft → Submitted → Initial Review → Impact Assessment → Risk Assessment →
    Department Review → QA Review → Approval → Implementation → Verification → Effectiveness
    Review → Closed, with rejection supported from any stage back to Draft.
  - AI Impact Assessment across 14 standard impact areas (Validation, Qualification, Risk, URS,
    SOP, Training, Equipment, Documents, Software, Utilities, Regulatory Compliance, Business
    Continuity, Electronic Records, Electronic Signatures); AI Implementation Plan/Checklist; AI
    Risk Summary, Rollback Plan, Regulatory Impact, Change Justification, Executive Summary,
    Verification Summary, and Effectiveness Review narratives — all optional, routed through the
    existing shared `services/qms_shared.py::call_gemini()`.
  - Links to existing Deviations/CAPAs (`qms_change_control_links`).
  - Ships the full common feature set: Dashboard, List + Filters + Search, Detail View, Attachments,
    Comments, Audit Trail, Electronic Signature/Approval Workflow, Print, DOCX Export, Status Badges.
  - `qms_change_control_database.py`, `routes/qms_change_control.py`,
    `services/qms_change_control_service.py`, `prompts/qms_change_control_prompt.py`,
    `static/js/qms_change_control.js`.
  - Additive-only changes to shared files: `qms_database.py` (new tables + `QMS_META` enums),
    `routes/qms_common.py` (new `record_type`, dashboard stats), `qms_common.js` (dashboard card),
    `qms.css` (new badge colors), `app.py`, `templates/index.html` (nav + view + script tag).
  - `tests/test_qms_database.py`, `tests/test_qms_routes.py` — 16 new tests appended, all passing
    alongside the existing 42 QMS + ~41 Document Intelligence Engine tests (101 total).
  - Full reference: [`docs/QMS_PHASE2.md`](docs/QMS_PHASE2.md).

### Fixed
- None — new functionality only.

---

## [Unreleased] — 2026-07-02 — Quality Management Suite (Phase 1)

### Added
- **Quality Management Suite** — PharmaGPT's second major pillar, parallel in scope to the Validation pillar. Phase 1 ships three modules:
  - **Document Control** — SOP/Protocol/Specification/Test Method/Format/Template/Logbook/Checklist/Policy/Manual/Work Instruction lifecycle (Draft → Under Review → Pending Approval → Effective → Under Revision → Obsolete), auto-numbering, version history, training requirement tracking, distribution & acknowledgement, AI draft generation (streamed), AI regulatory compliance review.
  - **Deviation Management** — Minor/Major/Critical/Market deviations across Manufacturing/Laboratory/Engineering/Validation categories, full lifecycle (Initiated → ... → Closed), AI Investigation Assistant (Fishbone/Ishikawa + 5-Why + timeline + root cause in one call), AI impact-assessment suggestions, AI CAPA-seed suggestions with one-click create-and-link.
  - **CAPA** — Corrective/Preventive actions with owners, due dates, escalation, effectiveness checks, AI draft/effectiveness suggestions, AI Quality Trend Summary across CAPAs and Deviations.
  - Every module ships the full common feature set: Dashboard, List + Filters + Search, Detail View, Attachments, Comments, Audit Trail, Electronic Signature/Approval Workflow, Print, DOCX Export, Status Badges.
  - Deviation ↔ CAPA linkage is a real, queryable relationship in both directions, driven either manually or by the AI CAPA Suggestion flow.
  - New nested "Quality Management" sidebar section with independently-collapsible Document Control / Deviation Management / CAPA sub-groups, plus a unified cross-module QMS dashboard.
  - `qms_database.py` (schema + shared Attachments/Comments/Audit-Trail/Approval tables, polymorphic across all 3 modules) + `qms_document_database.py` / `qms_deviation_database.py` / `qms_capa_database.py`.
  - `routes/qms_common.py`, `routes/qms_documents.py`, `routes/qms_deviations.py`, `routes/qms_capa.py`.
  - `services/qms_shared.py`, `services/qms_document_service.py`, `services/qms_deviation_service.py`, `services/qms_capa_service.py`.
  - `prompts/qms_document_prompt.py`, `prompts/qms_deviation_prompt.py`, `prompts/qms_capa_prompt.py`.
  - `static/css/qms.css`, `static/js/qms_common.js`, `static/js/qms_documents.js`, `static/js/qms_deviations.js`, `static/js/qms_capa.js`.
  - `tests/test_qms_database.py`, `tests/test_qms_routes.py` — 42 new tests, all passing alongside the existing 41.
  - Full reference: [`docs/QMS_PHASE1.md`](docs/QMS_PHASE1.md).

### Fixed
- `database.py::get_dashboard_stats()` — `pending_capas`/`pending_deviations` now count from the real `qms_capas`/`qms_deviations` tables instead of the legacy one-shot `generated_documents` wizard rows.

---

## [0.7.0] — 2026-06-27 — Knowledge Base

### Added
- **Knowledge Base** — permanent, project-independent document library accessible from the sidebar
- 8 built-in folders: SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others
- Document metadata fields: **Title**, **Folder**, **Tags** (comma-separated), **Document Version**, **Effective Date**, **Review Date**
- Upload modal with full metadata form — auto-fills title from filename, pre-selects active folder
- **Search by title** — substring match on document title
- **Search by tag** — filter by any tag substring
- **Search by file type** — dropdown filter (PDF / DOCX / XLSX / TXT)
- **Keyword search inside document** — full-text search across extracted text content
- All four search filters can be combined; search runs on Enter or Search button
- **Folder sidebar** with live document counts per folder; click to filter
- **Document list** — shows folder pill, version badge, file type, effective date, review date, tags per row
- **Detail / preview panel** — opens on document click; shows complete metadata grid + text preview (first 2,500 chars)
- Overdue review date highlighted in red in the detail panel
- Inline View (PDF/TXT in browser tab) and force-download buttons in both list and detail panel
- `kb_documents` SQLite table: id, title, folder, tags, doc_version, effective_date, review_date, original_name, stored_filename, file_type, file_size, text_content, word_count, page_count, extraction_status, upload_date
- Text extraction on upload (same pipeline as project documents) — stored directly in `kb_documents.text_content`
- KB files stored at `uploads/kb/` (global, not per-project)
- `GET  /kb/documents` — list with optional filters (folder, tag, file_type, keyword, title)
- `POST /kb/documents` — upload file with metadata (multipart/form-data)
- `GET  /kb/documents/<id>` — single document including text_content for preview
- `GET  /kb/documents/<id>/view` — inline view or browser download
- `GET  /kb/documents/<id>/download` — force-download
- `DELETE /kb/documents/<id>` — delete metadata + file from disk
- `GET  /kb/folders/counts` — `{folder: count}` map for sidebar badges
- `knowledge_base.js` — self-contained IIFE module; all KB state and logic encapsulated
- `safe_save_kb()`, `get_kb_file_path()`, `delete_kb_from_disk()`, `kb_file_exists()` helpers in `documents.py`
- Full KB CRUD in `database.py`: `create_kb_document`, `get_kb_documents`, `get_kb_document`, `update_kb_document_text`, `delete_kb_document`, `get_kb_folder_counts`, `KB_FOLDERS` constant
- KB styles (~300 lines) appended to `style.css`; fully responsive collapse on mobile

---

## [0.6.0] — 2026-06-27 — Validation Document Generator

### Added
- Collapsible **Validation** sidebar section with 11 document type buttons
- 4-step generation wizard (Equipment → Details → Reference Docs → Generate)
  - Step 1: equipment name, manufacturer, department, validation type
  - Step 2: doc-type-specific fields driven by `validation_config.js`
  - Step 3: optional reference document selection from uploaded project files
  - Step 4: real-time streaming generation into A4 Word-like viewer
- 11 supported document types: URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation, Change Control
- Tailored AI prompt per document type with pharmaceutical section structure and regulatory citations
- **Export DOCX** — `markdown_to_docx()` state-machine parser → python-docx with pharma styling  
  (A4, 1.25" left / 1.0" right margins, navy headings, header/footer, auto page numbers)
- **Export PDF** — client-side `window.print()` with print-optimised CSS (no server-side deps)
- **Save to Project** — stores generated doc in `generated_documents` SQLite table
- Viewer toolbar: Regenerate · Export DOCX · Print/PDF · Save to Project
- `POST /validation/generate` — SSE endpoint, `temperature=0.3`
- `POST /validation/export/docx` — markdown → DOCX binary download
- `POST /validation/save` — save doc metadata + content to DB
- `GET  /projects/<id>/generated-docs` — list saved docs for a project
- `GET  /generated-docs/<id>` — retrieve a single saved doc
- `DELETE /generated-docs/<id>` — delete a saved doc
- `generated_documents` table in SQLite schema
- `validation_config.js` — single config file drives wizard fields for all 11 doc types
- `validation.js` — fully config-driven wizard engine (no hardcoded doc types)
- `doc_generator.py` — Gemini prompt builder for all 11 doc types
- `doc_exporter.py` — Markdown → styled DOCX converter (state-machine, table support, bold/italic)

---

## [0.5.0] — AI Document Intelligence

### Added
- Auto text extraction on upload: pdfplumber (PDF), python-docx (DOCX), openpyxl (XLSX)
- `document_text` table — extracted text stored with page/word counts and extraction status
- Upload never fails due to extraction errors (`extraction_status`: `ok` / `empty` / `error`)
- Keyword search: overlapping chunks (400 words, 60-word overlap), Jaccard scoring
- **"☑ Use Project Documents"** checkbox above chat input
- Document context injected into Gemini prompt (max 2,500 context words)
- Sources strip — "Sources: • URS.pdf • Equipment Manual.docx" rendered below AI responses
- SSE done event carries `sources` array of filenames
- **Document Insights panel** — doc count, total pages/words, file type badges, extraction progress bar
- RAG stubs: `generate_embedding`, `upsert_to_vector_store`, `vector_search` (ready for v0.7)
- `GET /projects/<id>/insights` — aggregated document statistics endpoint
- `document_search.py` — chunking, tokenisation, and scoring engine
- `pdf_reader.py`, `docx_reader.py`, `excel_reader.py` — dedicated extractors

---

## [0.4.0] — Document Management

### Added
- Upload PDF, DOCX, XLSX, TXT (max 50 MB per file)
- Drag-and-drop upload zone
- Inline view (PDF / TXT in browser) and force-download
- Delete with physical file removal from `uploads/{project_id}/`
- `documents` table in SQLite schema
- `GET/POST /projects/<id>/documents`, `GET /documents/<id>/view`, `GET /documents/<id>/download`, `DELETE /documents/<id>`
- `documents.py` — file-system helpers (save, delete, MIME types)

---

## [0.3.0] — Project Management

### Added
- Create / list / delete projects with equipment metadata (name, manufacturer, department, type)
- Per-project conversation history in SQLite `messages` table
- In-memory history cache (`dict[int, list]`) rebuilt from DB on server restart
- "Clear History" per project
- `projects` and `messages` tables in SQLite schema
- `GET/POST /projects`, `GET/DELETE /projects/<id>`, `GET /projects/<id>/messages`, `POST /clear`
- `projects.js` — project CRUD, sidebar rendering, active project state

---

## [0.2.0] — PharmaGPT Web App

### Added
- Flask SPA with dark sidebar and chat view
- SSE streaming via `generate_content_stream()` with per-token rendering
- `PHARMA_SYSTEM_PROMPT` — Senior Pharmaceutical Validation Engineer persona
- Regulatory scope: USFDA 21 CFR Part 11, EU GMP Annex 11, MHRA, WHO-GMP, CDSCO, TGA
- `app.py`, `config.py`, `prompts.py`, `database.py`
- `index.html` single-page shell; `style.css`; `chat.js`

---

## [0.1.0] — Foundation

### Added
- `hello.py` — interactive Gemini CLI chat with retry logic, streaming output, conversation memory
- `gemini-2.5-flash` model integration via `google-genai` SDK

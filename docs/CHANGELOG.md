# Changelog — PharmaGPT

All notable changes to PharmaGPT are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.7.0] — Knowledge Base — 2026-06-27

### Added
- **Global Knowledge Base** (`/kb/documents`) — project-independent permanent document library
- **8 KB folders:** SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others
- **KB document metadata:** Title, Folder, Tags (comma-separated), Version, Effective Date, Review Date stored per document
- **KB search:** filter by folder, tag, file type dropdown, and full-text keyword search against extracted document text
- **Folder sidebar with live counts** (`GET /kb/folders/counts`) — per-folder document count badges update in real-time
- **KB detail panel** — clicking any KB document row reveals a full metadata grid and 2,500-character text preview
- **Overdue date highlighting** — Review Date displayed in red/amber when past or within 30 days
- **KB inline viewer** — PDF and TXT files viewable in-browser; DOCX and XLSX force-download
- **`kb_documents` table** with `title`, `folder`, `tags`, `doc_version`, `effective_date`, `review_date`, `text_content`, `extraction_status` columns
- KB files stored at `uploads/kb/` (global, not per-project)
- `knowledge_base.js` — full client-side module for KB UI
- `GET /kb/documents` — list with filter params (`folder`, `tag`, `file_type`, `keyword`, `title`)
- `POST /kb/documents` — upload with metadata (multipart form)
- `GET /kb/documents/<id>` — retrieve single doc + preview text
- `GET /kb/documents/<id>/view` — inline or download
- `GET /kb/documents/<id>/download` — force download
- `DELETE /kb/documents/<id>` — remove record + physical file

### Changed
- Sidebar now includes 🗂 **Knowledge Base** navigation item
- Home dashboard updated to include KB document count stat
- `database.py` extended with `kb_documents` table init and full KB CRUD functions

---

## [0.6.0] — Validation Document Generator — 2026-05-15

### Added
- **11 validation document types:** URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation Report, Change Control
- **4-step generation wizard:**
  - Step 1: Equipment details (name, manufacturer, model, department, serial number)
  - Step 2: Document-type-specific fields (protocol number, version, scope, etc.)
  - Step 3: Select reference documents from uploaded project files
  - Step 4: Real-time AI generation into A4-style document viewer
- **SSE streaming validation generation** (`POST /validation/generate`) with `temperature=0.3` for structural consistency
- **DOCX export** (`POST /validation/export/docx`) — markdown → styled Word document with:
  - A4 page size, calibrated margins
  - Navy (#003366) headings
  - Table formatting with header row shading
  - Header: company name + document title
  - Footer: "CONFIDENTIAL — For Internal Use Only" + page numbers
- **PDF export** — client-side `window.print()` with print CSS (no server dependencies)
- **Save to Project** (`POST /validation/save`) — persists generated doc to `generated_documents` table
- **Saved documents list** (`GET /projects/<id>/generated-docs`) — re-openable from project sidebar
- **Document viewer toolbar:** Regenerate · Export DOCX · Print/PDF · Save to Project
- `validation_config.js` — single config file defining all 11 doc types (labels, icons, colours, wizard fields)
- `validation.js` — config-driven 4-step wizard engine
- `doc_generator.py` — prompt builder for all 11 doc types
- `doc_exporter.py` — line-by-line markdown → python-docx state machine
- `generated_documents` table: `id`, `project_id`, `doc_type`, `title`, `form_data` (JSON), `content`, `created_at`
- `GET /generated-docs/<id>` — retrieve full doc content
- `DELETE /generated-docs/<id>` — delete saved doc

### Changed
- Sidebar now includes collapsible **Validation** section with colour-coded doc type buttons
- Project view shows count of generated documents in header

---

## [0.5.0] — AI Document Intelligence — 2026-04-01

### Added
- **Automatic text extraction** on file upload (runs synchronously, non-blocking to HTTP response)
  - PDF: `pdfplumber` — per-page extraction, page count
  - DOCX: `python-docx` — paragraph text
  - XLSX: `openpyxl` — all sheets, all cells
  - TXT: UTF-8 read with error replacement
- **`document_text` table:** `document_id`, `project_id`, `text_content`, `page_count`, `word_count`, `extraction_status`
- **Keyword RAG pipeline** (`document_search.py`):
  - Overlapping chunk splitting (400 words, 60-word overlap)
  - Jaccard similarity scoring + length bonus
  - Top-k chunk retrieval (default k=5)
  - Max 2,500 context words injected per query
- **"Use Project Documents" checkbox** in chat UI — when checked, relevant document chunks are injected into Gemini prompt
- **Sources strip** below AI responses — shows filenames of documents used as context
- **Document Insights panel** — per-project stats: document count, total pages, total words, extraction status breakdown (OK / empty / error)
- `GET /projects/<id>/insights` endpoint
- `insights.js` client module

### Changed
- Upload endpoint (`POST /projects/<id>/documents`) now triggers extraction immediately and stores result in `document_text`
- Chat endpoint (`POST /stream`) accepts `use_docs: true` flag and optional `project_id` to inject context
- SSE done event now includes `sources` array

---

## [0.4.0] — Document Upload — 2026-03-10

### Added
- **File upload** (`POST /projects/<id>/documents`) — multipart form, stored with UUID-prefixed filename
- **Supported formats:** PDF, DOCX, XLSX, TXT (max 50 MB)
- **Drag-and-drop upload zone** in Documents view
- **Document list** (`GET /projects/<id>/documents`) — table with name, type, size, upload date
- **Inline viewer** (`GET /documents/<id>/view`) — PDF and TXT served with `Content-Disposition: inline`
- **Force download** (`GET /documents/<id>/download`) — all types
- **Delete document** (`DELETE /documents/<id>`) — removes DB record and physical file
- `documents` table: `id`, `project_id`, `original_name`, `stored_filename`, `file_type`, `file_size`, `upload_date`
- Per-project directory at `uploads/{project_id}/`
- `documents.py` — `safe_save_file()`, `delete_file()`, `get_upload_path()` utilities
- `documents.js` client module

### Changed
- Project delete now also removes all uploaded files from disk (cascade)

---

## [0.3.0] — Project Management — 2026-02-20

### Added
- **Create project** (`POST /projects`) — name, equipment_name, manufacturer, department, validation_type
- **List projects** (`GET /projects`) — sorted by created_at descending
- **Get project** (`GET /projects/<id>`)
- **Delete project** (`DELETE /projects/<id>`) — cascades to messages
- **Per-project conversation history** — loaded from DB on first access, cached in memory
- **Load messages** (`GET /projects/<id>/messages`) — full history
- **Clear history** (`POST /clear`) — resets DB + memory cache for project
- Projects list in sidebar — click to switch active project
- Project metadata displayed in chat view header
- `projects` table: `id`, `name`, `equipment_name`, `manufacturer`, `department`, `validation_type`, `created_at`
- `messages` table: `id`, `project_id`, `role`, `content`, `created_at`
- `database.py` — schema init, project CRUD, message CRUD
- `projects.js` client module

### Changed
- Chat endpoint now requires `project_id` parameter
- In-memory `history_cache` keyed by project_id

---

## [0.2.0] — Web App + Streaming Chat — 2026-02-01

### Added
- **Flask web application** (`pharmagpt/app.py`) with SPA shell (`templates/index.html`)
- **SSE streaming chat** (`POST /stream`) — Gemini tokens streamed token-by-token
- **`PHARMA_SYSTEM_PROMPT`** — 30+ years pharmaceutical operations persona with expertise in:
  - GMP, WHO-GMP, ISO 13485, Schedule M, GAMP 5, ICH Q8/Q9/Q10
  - IQ/OQ/PQ, CSV, cleaning validation, process validation
  - USFDA 21 CFR Parts 11/210/211/820, EU GMP Annex 11/15, MHRA, CDSCO, TGA, FSSAI
  - Oral solid dosage, sterile manufacturing, packaging, cleanroom/HVAC, water systems
- **Dark theme UI** — navy sidebar, dark content area, custom CSS (~3,300 lines)
- **Sidebar navigation** — Home, Chat, Documents, Insights, Knowledge Base sections
- **Regulatory tags footer** — USFDA, EU GMP, MHRA, WHO-GMP, CDSCO, TGA badges
- **Specialization tags** — OSD, Sterile, Packaging, Cleanroom/HVAC, Water Systems
- **marked.js** integration for markdown rendering in chat bubbles
- Streaming cursor animation during token delivery
- `chat.js` client module
- `config.py` — environment variable loading
- `prompts.py` — system prompt definition

### Changed
- Migrated from CLI (`hello.py`) to web application architecture

---

## [0.1.0] — CLI Foundation — 2026-01-15

### Added
- `hello.py` — command-line proof of concept
- Google Gemini 2.5 Flash integration via `google-generativeai` SDK
- Streaming console output with retry logic (3 attempts on `ServerError`)
- Multi-turn conversation with in-memory history
- Basic pharmaceutical persona in system prompt
- `.env` support via `python-dotenv`
- `requirements.txt` with initial dependencies
- `.gitignore` (excludes `venv/`, `.env`, `*.db`, `uploads/`)

---

## Unreleased (v0.8 in progress)

### In Progress
- Validation Workspace full UI (`val_workspace.js`, `val_projects` backend endpoints already live)
- `val_audit_trail` full UI (backend endpoints live at `GET/POST /val-projects/<id>/audit-trail`)
- Dashboard enhanced stats with activity feed

### Planned
- Vector RAG upgrade (Gemini text embeddings + cosine similarity)
- Electronic signature workflow (21 CFR Part 11)
- Document regeneration with diff view
- KB folder management (rename, reorder)

# Changelog

All notable changes to PharmaGPT are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

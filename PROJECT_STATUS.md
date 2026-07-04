# PharmaGPT — Development Status (v0.7)

**Last updated:** 2026-06-27  
**Stack:** Python 3.14 · Flask · SQLite · Google Gemini 2.5 Flash · Vanilla JS
**Version:** v0.7 Knowledge Base
**Server:** `http://127.0.0.1:5000` (Flask dev server, port configurable via `.env`)

---

## Folder Structure

```
D:\PharmaAgent\
├── .env                          # GEMINI_API_KEY, FLASK_SECRET_KEY, etc.
├── venv\                         # Python virtual environment
├── hello.py                      # ⚠ DO NOT MODIFY — original proof-of-concept
│
└── pharmagpt\                    # Main application package
    ├── app.py                    # Flask routes, SSE streaming, Gemini client
    ├── config.py                 # Env-var loading, model name, upload limits
    ├── database.py               # SQLite schema + all CRUD functions
    ├── documents.py              # File-system helpers (save, delete, mime types)
    ├── prompts.py                # PHARMA_SYSTEM_PROMPT (Senior Pharma Engineer persona)
    ├── pharmagpt.db              # SQLite database (auto-created on first run)
    │
    ├── services\                 # AI and document processing services
    │   ├── __init__.py
    │   ├── pdf_reader.py         # pdfplumber — extract text + page count from PDF
    │   ├── docx_reader.py        # python-docx — extract text + estimated pages
    │   ├── excel_reader.py       # openpyxl — extract text from all sheets
    │   ├── document_search.py    # Keyword search (TF-IDF-like), chunking, RAG stubs
    │   ├── doc_generator.py      # Gemini prompt builder for all 11 doc types
    │   └── doc_exporter.py       # Markdown → styled DOCX (python-docx)
    │
    ├── templates\
    │   └── index.html            # Single-page app shell
    │
    ├── static\
    │   ├── css\
    │   │   └── style.css         # All styles (~1,750 lines)
    │   └── js\
    │       ├── projects.js       # Project CRUD, sidebar, project switching
    │       ├── documents.js      # Upload, list, delete, drag-and-drop
    │       ├── insights.js       # Document Insights panel
    │       ├── chat.js           # SSE chat, streaming, sources strip
    │       ├── validation_config.js  # Config for all 11 doc types (fields, labels, colors)
    │       ├── validation.js     # 4-step wizard engine, viewer, export/save
    │       └── knowledge_base.js # KB panel: upload, search, folder filter, preview
    │
    └── uploads\
        └── {project_id}\         # Uploaded files, one folder per project
```

---

## Database Schema

**File:** `pharmagpt/pharmagpt.db` (SQLite 3)  
All foreign keys use `ON DELETE CASCADE`.

### `projects`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| name | TEXT NOT NULL | User-chosen project title |
| equipment_name | TEXT | e.g. "Agilent HPLC 1260" |
| manufacturer | TEXT | e.g. "Agilent Technologies" |
| department | TEXT | e.g. "Quality Control" |
| validation_type | TEXT | e.g. "IQ/OQ/PQ", "CSV", "FAT" |
| created_at | TIMESTAMP | Default: current timestamp |

### `messages`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| project_id | INTEGER FK → projects | Cascade delete |
| role | TEXT | `'user'` or `'model'` |
| content | TEXT | Full message text |
| created_at | TIMESTAMP | |

### `documents`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| project_id | INTEGER FK → projects | Cascade delete |
| original_name | TEXT | Browser filename (may have spaces) |
| stored_filename | TEXT | Sanitised on-disk name (secure_filename) |
| file_type | TEXT | Extension: `pdf`, `docx`, `xlsx`, `txt` |
| file_size | INTEGER | Bytes |
| upload_date | TIMESTAMP | |

### `document_text`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| document_id | INTEGER FK → documents UNIQUE | One row per doc |
| project_id | INTEGER FK → projects | |
| text_content | TEXT | Extracted plain text |
| page_count | INTEGER | Real pages (PDF) or word-count estimate |
| word_count | INTEGER | Total words extracted |
| extraction_status | TEXT | `'ok'` / `'empty'` / `'error'` |
| extracted_at | TIMESTAMP | |

### `kb_documents`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| title | TEXT NOT NULL | Display title |
| folder | TEXT | SOP / Validation / Qualification / Protocols / Reports / Regulations / Vendor Documents / Others |
| tags | TEXT | Comma-separated tags |
| doc_version | TEXT | Version string (e.g. "1.0", "2.3") |
| effective_date | TEXT | ISO date YYYY-MM-DD |
| review_date | TEXT | ISO date YYYY-MM-DD |
| original_name | TEXT | Browser filename |
| stored_filename | TEXT | On-disk sanitised name |
| file_type | TEXT | pdf / docx / xlsx / txt |
| file_size | INTEGER | Bytes |
| text_content | TEXT | Extracted plain text (used for keyword search) |
| word_count | INTEGER | Total words |
| page_count | INTEGER | Pages or estimate |
| extraction_status | TEXT | ok / empty / error |
| upload_date | TIMESTAMP | |

### `generated_documents`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| project_id | INTEGER FK → projects | Cascade delete |
| doc_type | TEXT | `'OQ'`, `'IQ'`, `'URS'`, etc. |
| title | TEXT | Auto-generated: `"{Equipment} — {Type} {Protocol}"` |
| form_data | TEXT | JSON blob of wizard form values |
| content | TEXT | Raw markdown from Gemini |
| created_at | TIMESTAMP | |

---

## API Routes

### Core
| Method | Route | Description |
|---|---|---|
| GET | `/` | Serve SPA shell |
| GET | `/projects` | List all projects |
| POST | `/projects` | Create project |
| GET | `/projects/<id>` | Get single project |
| DELETE | `/projects/<id>` | Delete project + cascade |
| GET | `/projects/<id>/messages` | Load chat history |
| POST | `/stream` | SSE chat stream (with optional doc context) |
| POST | `/clear` | Clear project chat history |

### Documents
| Method | Route | Description |
|---|---|---|
| GET | `/projects/<id>/documents` | List uploaded documents |
| POST | `/projects/<id>/documents` | Upload + auto-extract text |
| GET | `/documents/<id>/view` | Inline view (PDF/TXT) or download (DOCX/XLSX) |
| GET | `/documents/<id>/download` | Force-download |
| DELETE | `/documents/<id>` | Delete metadata + file from disk |
| GET | `/projects/<id>/insights` | Aggregated doc stats |

### Validation (v0.6)
| Method | Route | Description |
|---|---|---|
| POST | `/validation/generate` | SSE: generate a document with Gemini |
| POST | `/validation/export/docx` | Convert markdown → DOCX download |
| POST | `/validation/save` | Save generated doc to DB |
| GET | `/projects/<id>/generated-docs` | List saved generated docs |
| GET | `/generated-docs/<id>` | Get a single generated doc |
| DELETE | `/generated-docs/<id>` | Delete a generated doc |

### Knowledge Base (v0.7)
| Method | Route | Description |
|---|---|---|
| GET | `/kb/documents` | List KB docs (filters: folder, tag, file_type, keyword, title) |
| POST | `/kb/documents` | Upload file + metadata (multipart/form-data) |
| GET | `/kb/documents/<id>` | Get single KB doc including text_content |
| GET | `/kb/documents/<id>/view` | Inline view (PDF/TXT) or download (DOCX/XLSX) |
| GET | `/kb/documents/<id>/download` | Force-download |
| DELETE | `/kb/documents/<id>` | Delete metadata + file from disk |
| GET | `/kb/folders/counts` | `{folder: count}` map for sidebar badges |

---

## Features Completed

### v0.1 — Foundation
- Single-file interactive Gemini CLI chat (`hello.py`) with retry logic
- `gemini-2.5-flash` model, streaming output, conversation memory

### v0.2 — PharmaGPT Web App
- Flask SPA with dark sidebar + chat view
- SSE streaming (`generate_content_stream`) with per-token rendering
- `PHARMA_SYSTEM_PROMPT` — Senior Pharmaceutical Validation Engineer persona
- Regulatory compliance: USFDA 21 CFR Part 11, EU GMP Annex 11, MHRA, WHO-GMP, CDSCO, TGA

### v0.3 — Project Management
- Create / list / delete projects with equipment metadata
- Per-project conversation history (SQLite `messages` table)
- In-memory history cache (`dict[int, list]`) rebuilt from DB on restart
- "Clear History" per project

### v0.4 — Document Management
- Upload PDF, DOCX, XLSX, TXT (max 50 MB)
- Drag-and-drop upload zone
- Inline view (PDF/TXT in browser) and force-download
- Delete with physical file removal

### v0.5 — AI Document Intelligence
- Auto text extraction on upload: pdfplumber (PDF), python-docx (DOCX), openpyxl (XLSX)
- Extracted text stored in `document_text` table; upload never fails due to extraction errors
- Keyword search: overlapping chunks (400 words, 60-word overlap), TF-IDF-like Jaccard scoring
- "☑ Use Project Documents" checkbox above chat input
- Document context injected into Gemini prompt; source filenames returned in SSE done event
- "Sources: • URS.pdf • Equipment Manual.docx" strip rendered below AI responses
- Document Insights panel: doc count, total pages/words, file type badges, extraction progress bar
- RAG stubs (`generate_embedding`, `upsert_to_vector_store`, `vector_search`) ready for v0.7+

### v0.7 — Knowledge Base ✅ CURRENT
- Permanent, project-independent document library (🗂 Knowledge Base) in sidebar navigation
- 8 folders: SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others
- Document metadata: Title, Folder, Tags (comma-separated), Version, Effective Date, Review Date
- Upload modal with metadata form; auto-fills title from filename; pre-selects active folder
- Search by title, by tag, by file type (dropdown), and keyword inside document content
- All four search filters are combinable; Enter key or Search button triggers search
- Folder sidebar with live per-folder document counts
- Document rows show: folder pill, version badge, file type, effective/review dates, tags
- Detail panel (opens on row click): full metadata grid + 2,500-char text preview; overdue review date highlighted
- View inline (PDF/TXT) or force-download from list and detail panel
- `kb_documents` table: full metadata + extracted `text_content` for keyword search
- Files stored at `uploads/kb/` (global, not per-project)
- 7 new API routes under `/kb/documents` and `/kb/folders/counts`
- `knowledge_base.js` — self-contained IIFE; manages all KB state client-side
- KB CRUD helpers in `database.py`; KB file helpers in `documents.py`

### v0.6 — Validation Document Generator
- Collapsible "Validation" sidebar section with all 11 document types
- 4-step wizard (Equipment → Details → Reference Docs → Generate) — generic, config-driven
- 11 supported document types: URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation, Change Control
- Each type has tailored AI prompt with pharmaceutical section structure and regulatory citations
- Document generation streams in real-time via SSE into a Word-like A4 viewer
- Export DOCX: `markdown_to_docx()` state-machine parser → python-docx with pharma styling
- Export PDF: browser `window.print()` with print-optimised CSS (no server-side GTK/WeasyPrint needed)
- Save to Project: stored in `generated_documents` table, re-openable
- Viewer toolbar: Regenerate · Export DOCX · Print/PDF · Save to Project
- `temperature=0.3` for consistent document structure (vs `default` for chat)
- `validation_config.js` — single config file drives wizard fields for all 11 doc types

---

## Pending Features

### v0.8 — Saved Document Library
- View all previously generated documents per project
- Re-open, regenerate, or export from saved documents
- Diff view between two versions of the same doc type

### v0.8 — Vector RAG Upgrade
- Replace keyword search with real embeddings (`generate_embedding` stub is in `document_search.py`)
- Use Gemini text-embedding-004 or equivalent
- Vector store options: Chroma (local) or Pinecone (cloud)
- Upgrade chat and validation generation to use vector similarity search

### Future
- Audit trail / approval workflow (Author → Reviewer → Approver signatures)
- Multi-user support with role-based access (QA, Validation, Operator)
- Templates library for site-specific SOPs
- Audit Prep assistant (gap analysis against regulatory standards)
- Export to PDF server-side (WeasyPrint on Linux, or headless Chrome)

---

## Important Implementation Details

### SSE Streaming
- Chat: `POST /stream` → `generate_content_stream()` → `text/event-stream`
- Validation: `POST /validation/generate` → same pipeline, `temperature=0.3`
- Flask request context must be captured **before** entering the generator function
- History is appended to in-memory cache before the generator runs (not inside it)

### Document Text Extraction
- Runs synchronously during upload (`_extract_and_store()`)
- All exceptions are caught — upload HTTP 201 is always returned even if extraction fails
- `extraction_status` is `'ok'`, `'empty'`, or `'error'`
- TXT files: UTF-8 with `errors='replace'` — handles encoding issues gracefully

### DOCX Export
- `doc_exporter.py` is a line-by-line state machine (not a full markdown parser)
- Table rows are accumulated until a non-`|` line is seen, then flushed as a Word table
- Inline `**bold**` and `*italic*` are handled with regex split + multiple runs per paragraph
- Page header (right-aligned, thin bottom border) and footer (centred, auto page number) on every page
- A4 page, 1.25" left margin, 1.0" right margin — standard pharmaceutical document layout

### PDF Export
- Client-side: `printDocument()` opens a new window with stripped-down HTML + print CSS
- Professional output without server dependencies (no WeasyPrint, no GTK, no wkhtmltopdf)
- Print CSS targets standard pharma typography: Calibri/Segoe UI, navy headings, grid tables

### History Cache
- `history_cache: dict[int, list]` — maps project_id → list of `types.Content` objects
- Rebuilt from `messages` table on first access per project per server lifetime
- Cleared on project delete and on Gemini `ServerError`
- The clean user message (without injected doc context) is saved to `messages` table

### Keyword Search (v0.5 RAG)
- `chunk_text(text, chunk_size=400, overlap=60)` — word-level overlapping chunks
- `_tokenise(text)` — lowercase, strip punctuation, tokens > 2 chars
- `score_chunk(chunk, query_tokens)` — Jaccard overlap + mild length bonus
- Top-k chunks assembled into `=== DOCUMENT CONTEXT ===\n[Source: doc.pdf]\n...` block
- Max 2,500 context words sent to Gemini to stay within token budget

### Config-Driven Wizard
- `validation_config.js` is the single source of truth for all 11 doc types
- Each type defines: `label`, `short`, `icon`, `color`, `step2[]` (id, label, type, placeholder, required)
- `validation.js` is fully generic — it reads the config at runtime, never hardcodes fields
- Adding a new document type requires only: one entry in `validation_config.js` + one prompt function in `doc_generator.py`

---

## Current Architecture

```
Browser (SPA)
│
├── projects.js     — project list, create/delete, active project state
├── documents.js    — upload, list, delete, drag-and-drop
├── insights.js     — document stats panel
├── chat.js         — SSE stream, message rendering, sources strip, use-docs checkbox
├── validation_config.js  — 11 doc type definitions
├── validation.js   — 4-step wizard, SSE viewer, export/save
└── knowledge_base.js — KB panel: upload, folder filter, search, detail/preview

        ↕ HTTP / SSE (fetch + EventSource-style ReadableStream)

Flask app.py
│
├── /stream               → Gemini SSE (chat)
├── /validation/generate  → Gemini SSE (temperature=0.3, structured prompt)
├── /validation/export/docx → markdown_to_docx() → bytes download
├── /projects/*           → SQLite CRUD
├── /documents/*          → file system + SQLite CRUD
├── /projects/*/insights  → aggregated DB query
├── /kb/documents         → KB list + upload (uploads/kb/)
├── /kb/documents/<id>    → KB CRUD + serve
└── /kb/folders/counts    → folder badge counts

        ↕

services/
├── document_search.py   → keyword chunk search
├── doc_generator.py     → prompt builder (11 types)
└── doc_exporter.py      → markdown → DOCX

        ↕

SQLite (pharmagpt.db)
├── projects
├── messages
├── documents
├── document_text
├── generated_documents
└── kb_documents

        ↕

Google Gemini API
└── gemini-2.5-flash
    ├── Chat: system_instruction=PHARMA_SYSTEM_PROMPT, default temperature
    └── Validation: system_instruction=PHARMA_SYSTEM_PROMPT, temperature=0.3
```

---

## Environment Setup

```
# .env (at D:\PharmaAgent\.env)
GEMINI_API_KEY=your_key_here
FLASK_SECRET_KEY=change-in-production
FLASK_DEBUG=true
FLASK_PORT=5000

# Start server
cd D:\PharmaAgent
.\venv\Scripts\python pharmagpt\app.py
```

**Key dependencies** (installed in venv):
- `flask` — web framework
- `google-genai` — Gemini SDK (`genai.Client`)
- `pdfplumber` — PDF text extraction
- `python-docx` — DOCX read + write
- `openpyxl` — XLSX extraction
- `python-dotenv` — `.env` loading

---

## Quality Management Suite (Phase 1) — added 2026-07-02

Second major pillar, parallel to the Validation pillar. Document Control,
Deviation Management, and CAPA — complete, tested (42 new tests, all
passing), and manually verified end-to-end in the browser including live
Gemini AI calls (draft generation, AI Investigation Assistant, impact/CAPA/
effectiveness suggestions, Quality Trend Summary). Full reference:
[`docs/QMS_PHASE1.md`](docs/QMS_PHASE1.md).

New files: `qms_database.py`, `qms_document_database.py`,
`qms_deviation_database.py`, `qms_capa_database.py`,
`routes/qms_common.py`, `routes/qms_documents.py`, `routes/qms_deviations.py`,
`routes/qms_capa.py`, `services/qms_shared.py`, `services/qms_document_service.py`,
`services/qms_deviation_service.py`, `services/qms_capa_service.py`,
`prompts/qms_document_prompt.py`, `prompts/qms_deviation_prompt.py`,
`prompts/qms_capa_prompt.py`, `static/css/qms.css`, `static/js/qms_common.js`,
`static/js/qms_documents.js`, `static/js/qms_deviations.js`, `static/js/qms_capa.js`,
`tests/test_qms_database.py`, `tests/test_qms_routes.py`.

Phase 2 (Change Control, Non-Conformance, OOS/OOT) and Phase 3 (Audit
Management, Supplier Quality, Training Management, Complaint Management) are
not yet built — the shared Attachments/Comments/Audit-Trail/Approval tables
are already polymorphic and ready for them.

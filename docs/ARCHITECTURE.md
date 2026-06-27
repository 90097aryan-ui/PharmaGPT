# Architecture — PharmaGPT

**Version:** 1.0  
**Date:** 2026-06-27  
**Current Release:** v0.7

---

## 1. High-Level Overview

PharmaGPT is a **monolithic Flask web application** with a single-page frontend. All application logic, file storage, and the database live in a single process on a single machine. There are no microservices, queues, or external caches.

```
Browser (SPA)
     │  HTTP + SSE
     ▼
Flask Application (pharmagpt/app.py)
     │
     ├── SQLite (pharmagpt/pharmagpt.db)
     │
     ├── File System (pharmagpt/uploads/)
     │
     └── Google Gemini API (external)
```

This architecture was chosen deliberately for v0.x development:
- **Zero infrastructure** — runs with `python app.py`, no containers or services
- **Easy to debug** — single process, no distributed tracing needed
- **Migration path exists** — SQLite → PostgreSQL, in-memory cache → Redis are straightforward swaps for v1.0

---

## 2. Directory Structure

```
D:\PharmaAgent\
├── .env                        # Runtime secrets (never committed)
├── .gitignore
├── requirements.txt
├── hello.py                    # Original CLI proof-of-concept (frozen)
│
├── docs/                       # Project documentation (this folder)
│
└── pharmagpt/                  # Application package
    ├── app.py                  # All Flask routes (35 endpoints, ~822 lines)
    ├── config.py               # Env var loading + constants
    ├── database.py             # SQLite schema + all CRUD functions
    ├── documents.py            # File storage utilities (save, delete, path)
    ├── prompts.py              # PHARMA_SYSTEM_PROMPT definition
    ├── pharmagpt.db            # SQLite database (auto-created)
    │
    ├── services/
    │   ├── __init__.py
    │   ├── pdf_reader.py       # pdfplumber text extraction
    │   ├── docx_reader.py      # python-docx text extraction
    │   ├── excel_reader.py     # openpyxl text extraction
    │   ├── document_search.py  # Keyword RAG pipeline (chunking + scoring)
    │   ├── doc_generator.py    # Validation doc prompt builder (11 types)
    │   └── doc_exporter.py     # Markdown → styled DOCX conversion
    │
    ├── templates/
    │   └── index.html          # SPA shell (~200 lines)
    │
    ├── static/
    │   ├── css/style.css       # All UI styles (~3,309 lines)
    │   └── js/
    │       ├── projects.js
    │       ├── chat.js
    │       ├── documents.js
    │       ├── insights.js
    │       ├── validation_config.js
    │       ├── validation.js
    │       ├── knowledge_base.js
    │       ├── dashboard.js
    │       └── val_workspace.js
    │
    └── uploads/
        ├── {project_id}/       # Per-project document storage
        └── kb/                 # Global Knowledge Base file storage
```

---

## 3. Backend Architecture

### 3.1 Flask Application (`app.py`)

Single file containing all 35 route handlers. Organised into logical groups:

1. **Core / SPA** — `GET /` serves `index.html`
2. **Projects** — CRUD for project records
3. **Chat** — SSE streaming endpoint (`POST /stream`)
4. **Documents** — Upload, view, download, delete per-project files
5. **Insights** — Aggregated document statistics
6. **Validation Generator** — SSE generation, DOCX export, save/list/delete generated docs
7. **Knowledge Base** — KB CRUD + folder counts
8. **Validation Workspace** — val_projects + audit trail (v0.8 partial)
9. **Dashboard** — System-wide stats

**Key global state:**
```python
history_cache: dict[int, list] = {}  # project_id → Gemini Content list
```

This in-memory cache stores the Gemini conversation history objects. It is rebuilt from the DB on first access and invalidated on project delete or API error.

### 3.2 Database Layer (`database.py`)

Pure SQLite via Python's `sqlite3` module. No ORM.

**Schema initialisation:** `init_db()` is called once at startup and creates all tables if they don't exist. Uses `CREATE TABLE IF NOT EXISTS` — safe to call on every startup.

**Connection handling:** Each function opens its own connection and closes it after the transaction. Row factory set to `sqlite3.Row` for dict-like access.

```python
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

**PRAGMA foreign_keys = ON** is set on every connection because SQLite disables foreign key enforcement by default.

### 3.3 SSE Streaming

Both chat (`POST /stream`) and validation generation (`POST /validation/generate`) use **Server-Sent Events** for streaming Gemini output token-by-token to the browser.

**Pattern:**
```python
@app.route('/stream', methods=['POST'])
def stream():
    # Capture request data BEFORE entering generator
    data = request.get_json()
    
    def generate():
        for chunk in gemini_model.generate_content(..., stream=True):
            yield f"data: {json.dumps({'token': chunk.text})}\n\n"
        yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')
```

**Critical detail:** Flask's request context is not available inside the generator function. All `request.*` data must be captured in the outer function scope before `generate()` is defined.

### 3.4 RAG Pipeline (`document_search.py`)

Keyword-based retrieval — no vector embeddings in v0.7.

**Steps:**
1. **Chunking:** Split document text into overlapping 400-word chunks with 60-word overlap
2. **Query tokenisation:** Lowercase, strip punctuation, filter tokens > 2 chars
3. **Scoring:** Jaccard similarity between query token set and chunk token set + length bonus
4. **Selection:** Top-k chunks sorted by score
5. **Formatting:** Chunks wrapped in `=== DOCUMENT CONTEXT ===\n[Source: filename]\n...`
6. **Injection:** Context string prepended to user message in Gemini request

Max context: 2,500 words to stay within Gemini's token budget.

### 3.5 Validation Document Generator (`doc_generator.py`)

Each of the 11 document types maps to a prompt template function. The function receives:
- `form_data` dict (wizard step 2 fields)
- `equipment_info` dict (wizard step 1)
- `reference_texts` list (selected uploaded docs)

Returns a complete prompt string that is sent to Gemini with `temperature=0.3`.

### 3.6 DOCX Exporter (`doc_exporter.py`)

Line-by-line state machine that parses markdown and writes `python-docx` objects:

```
Input: markdown string
  │
  ▼
Parse line by line:
  - #, ##, ### → add_heading(level)
  - **, * → inline run with bold/italic
  - |...|..| → detect table, buffer rows, add_table()
  - - item, 1. item → add_paragraph(style='List Bullet/Number')
  - blank line → paragraph break
  │
  ▼
Output: .docx BytesIO object → sent as download
```

---

## 4. Frontend Architecture

### 4.1 Single-Page Application

`index.html` is the only HTML page. All content is rendered by JavaScript. There is no client-side router — view switching is done by toggling CSS `display` properties on view containers.

```javascript
function showView(viewName) {
  document.querySelectorAll('.view').forEach(v => v.style.display = 'none');
  document.getElementById(`${viewName}-view`).style.display = 'block';
}
```

### 4.2 JavaScript Modules

Each JS file is an IIFE (Immediately Invoked Function Expression) that exposes a small public API on the global `window` object:

```javascript
// Example: projects.js
(function() {
  async function loadProjects() { ... }
  async function createProject(data) { ... }
  
  window.ProjectModule = { loadProjects, createProject };
})();
```

**Module dependencies:**
```
dashboard.js     ← no deps
projects.js      ← no deps
chat.js          ← depends on projects.js (active project ID)
documents.js     ← depends on projects.js
insights.js      ← depends on projects.js, documents.js
validation.js    ← depends on projects.js, validation_config.js
knowledge_base.js ← no project dep (global KB)
val_workspace.js ← no deps (standalone)
```

### 4.3 SSE Client

```javascript
const es = new EventSource('/stream?' + params);
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.token) appendToLastBubble(data.token);
  if (data.done) { es.close(); renderSources(data.sources); }
  if (data.error) { es.close(); showError(data.error); }
};
```

### 4.4 Markdown Rendering

AI responses are rendered as HTML using `marked.js` (loaded from CDN):

```javascript
bubble.innerHTML = marked.parse(rawMarkdown);
```

The document viewer also uses `marked.parse()` to render generation output before the full document is complete, giving a live preview as tokens stream in.

---

## 5. Database Schema

### 5.1 Tables

```sql
CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  equipment_name TEXT,
  manufacturer TEXT,
  department TEXT,
  validation_type TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  role TEXT NOT NULL,           -- 'user' | 'model'
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  original_name TEXT NOT NULL,
  stored_filename TEXT NOT NULL,
  file_type TEXT,               -- 'pdf' | 'docx' | 'xlsx' | 'txt'
  file_size INTEGER,
  upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_text (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL,
  text_content TEXT,
  page_count INTEGER DEFAULT 0,
  word_count INTEGER DEFAULT 0,
  extraction_status TEXT DEFAULT 'pending'  -- 'ok' | 'empty' | 'error'
);

CREATE TABLE generated_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  doc_type TEXT NOT NULL,
  title TEXT NOT NULL,
  form_data TEXT,               -- JSON blob of wizard fields
  content TEXT,                 -- Full markdown output
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE kb_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  original_name TEXT,
  stored_filename TEXT,
  file_type TEXT,
  file_size INTEGER,
  folder TEXT DEFAULT 'Others',
  tags TEXT,                    -- comma-separated
  doc_version TEXT,
  effective_date TEXT,
  review_date TEXT,
  text_content TEXT,
  extraction_status TEXT DEFAULT 'pending',
  upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE val_projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  equipment_name TEXT,
  owner TEXT,
  approver TEXT,
  target_date TEXT,
  status TEXT DEFAULT 'Planning',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE val_audit_trail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  val_proj_id INTEGER NOT NULL REFERENCES val_projects(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  user_note TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 Foreign Key Cascades

All child tables cascade delete from their parent:
- `messages`, `documents`, `generated_documents` → `projects`
- `document_text` → `documents`
- `val_audit_trail` → `val_projects`
- `kb_documents` is independent (no parent)

---

## 6. API Design

### 6.1 Conventions

- All endpoints return JSON (except SSE streams, file downloads, and the root HTML)
- Error responses: `{"error": "message"}` with appropriate HTTP status code
- List endpoints return arrays directly (not wrapped in `{"data": [...]}`)
- Timestamps stored as ISO 8601 strings in SQLite

### 6.2 SSE Event Format

**Chat stream:**
```
data: {"token": "..."}          # per-token event
data: {"done": true, "sources": ["doc1.pdf", "doc2.docx"]}  # final event
data: {"error": "message"}      # error event
```

**Validation generation stream:**
```
data: {"token": "..."}          # per-token event
data: {"done": true}            # final event
data: {"error": "message"}      # error event
```

### 6.3 File Upload

Files are uploaded as `multipart/form-data`. The server:
1. Validates extension against `ALLOWED_EXTENSIONS`
2. Runs `secure_filename()` on the original name
3. Generates a UUID-prefixed stored filename to prevent collisions
4. Saves to `uploads/{project_id}/` or `uploads/kb/`
5. Runs text extraction synchronously
6. Returns `201 Created` with the document record

---

## 7. Configuration (`config.py`)

```python
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL      = "gemini-2.5-flash"
FLASK_SECRET_KEY  = os.getenv("FLASK_SECRET_KEY", "dev-secret")
FLASK_DEBUG       = os.getenv("FLASK_DEBUG", "false").lower() == "true"
FLASK_PORT        = int(os.getenv("FLASK_PORT", 5000))
MAX_FILE_SIZE     = 50 * 1024 * 1024   # 50 MB
UPLOAD_FOLDER     = os.path.join(BASE_DIR, "uploads")
DB_PATH           = os.path.join(BASE_DIR, "pharmagpt.db")
ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt"}
```

---

## 8. Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ORM | None (raw sqlite3) | Avoids dependency weight for a simple schema; easy to inspect DB directly |
| Frontend framework | None (vanilla JS) | No build toolchain; reduces moving parts during rapid v0.x development |
| PDF export | Browser `window.print()` | No WeasyPrint/GTK dependency on Windows; zero server-side overhead |
| Markdown → DOCX | Custom state machine | No pandoc binary required; full control over Word styling |
| History strategy | In-memory dict rebuilt from DB | SSE requires data captured pre-generator; cache rebuilt on restart |
| Validation temperature | 0.3 (vs default 1.0) | Structural consistency in formal documents vs. conversational flexibility in chat |
| RAG strategy | Keyword/Jaccard | Ships without embeddings API; establishes correctness baseline for v0.8 upgrade |

---

## 9. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Path traversal via file upload | `werkzeug.utils.secure_filename()` on all uploads |
| API key exposure | Loaded from `.env`, never sent to client, excluded from git |
| Database injection | Parameterised queries (`?` placeholders) throughout `database.py` |
| Large file DoS | `MAX_FILE_SIZE = 50 MB` enforced before saving |
| XSS in chat output | `marked.js` renders markdown; no raw `innerHTML` from user input in chat inputs |

---

## 10. Planned Architecture Changes (v0.8+)

| Change | Target | Rationale |
|--------|--------|-----------|
| Vector RAG (embeddings) | v0.8 | Replace Jaccard scoring with semantic similarity for better retrieval |
| Electronic signature workflow | v0.8 | 21 CFR Part 11 compliance for generated documents |
| Multi-user auth (session-based) | v0.9 | Teams need isolated workspaces |
| RBAC (role-based access control) | v0.9 | QA vs. engineer vs. admin permission levels |
| PostgreSQL migration | v1.0 | Multi-user concurrency + row-level security |
| Redis session/history cache | v1.0 | Replace in-memory dict for multi-process deployment |
| WSGI deployment (Gunicorn) | v1.0 | Replace Flask dev server for production |

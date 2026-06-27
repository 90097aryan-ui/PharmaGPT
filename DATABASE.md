# PharmaGPT — Database Reference

**Engine:** SQLite 3  
**File:** `pharmagpt/pharmagpt.db` (auto-created on first run)  
**Managed by:** `pharmagpt/database.py`  
All foreign keys use `ON DELETE CASCADE`.

---

## Schema Diagram

```
projects
  │
  ├──< messages          (project chat history)
  ├──< documents         (uploaded files)
  │       │
  │       └──< document_text   (extracted plain text, 1:1 with documents)
  └──< generated_documents     (AI-generated validation docs)
```

---

## Tables

### `projects`

Stores each project with its equipment metadata.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `name` | TEXT | NOT NULL | User-chosen project title |
| `equipment_name` | TEXT | | e.g. "Agilent HPLC 1260" |
| `manufacturer` | TEXT | | e.g. "Agilent Technologies" |
| `department` | TEXT | | e.g. "Quality Control" |
| `validation_type` | TEXT | | e.g. "IQ/OQ/PQ", "CSV", "FAT" |
| `created_at` | TIMESTAMP | DEFAULT current_timestamp | |

---

### `messages`

Per-project conversation history for the chat interface.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `project_id` | INTEGER | FK → projects(id) CASCADE | |
| `role` | TEXT | NOT NULL | `'user'` or `'model'` |
| `content` | TEXT | NOT NULL | Full message text (clean — no injected doc context) |
| `created_at` | TIMESTAMP | DEFAULT current_timestamp | |

**Index:** `project_id` (implicit via FK)

---

### `documents`

Metadata for every uploaded file; actual bytes live on disk.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `project_id` | INTEGER | FK → projects(id) CASCADE | |
| `original_name` | TEXT | NOT NULL | Browser filename (may have spaces) |
| `stored_filename` | TEXT | NOT NULL | Sanitised on-disk name (`secure_filename`) |
| `file_type` | TEXT | NOT NULL | Extension: `pdf`, `docx`, `xlsx`, `txt` |
| `file_size` | INTEGER | | Bytes |
| `upload_date` | TIMESTAMP | DEFAULT current_timestamp | |

**On-disk path:** `pharmagpt/uploads/{project_id}/{stored_filename}`

---

### `document_text`

Extracted plain text — one row per document, inserted during upload.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `document_id` | INTEGER | FK → documents(id) CASCADE, UNIQUE | One row per doc |
| `project_id` | INTEGER | FK → projects(id) CASCADE | Denormalised for fast project-scope queries |
| `text_content` | TEXT | | Extracted plain text |
| `page_count` | INTEGER | | Real pages (PDF) or word-count estimate (DOCX/XLSX) |
| `word_count` | INTEGER | | Total words extracted |
| `extraction_status` | TEXT | | `'ok'` / `'empty'` / `'error'` |
| `extracted_at` | TIMESTAMP | DEFAULT current_timestamp | |

**Note:** Upload always returns HTTP 201 even if extraction fails; status is recorded in `extraction_status`.

---

### `generated_documents`

AI-generated validation documents saved by the user from the wizard viewer.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, autoincrement | |
| `project_id` | INTEGER | FK → projects(id) CASCADE | |
| `doc_type` | TEXT | NOT NULL | `'OQ'`, `'IQ'`, `'URS'`, `'CAPA'`, etc. |
| `title` | TEXT | NOT NULL | Auto-generated: `"{Equipment} — {Type} Protocol"` |
| `form_data` | TEXT | | JSON blob of wizard step 1 & 2 values |
| `content` | TEXT | | Raw Markdown from Gemini |
| `created_at` | TIMESTAMP | DEFAULT current_timestamp | |

---

## CRUD Reference

All functions live in `pharmagpt/database.py`.

### Projects
| Function | Description |
|----------|-------------|
| `init_db()` | Create all tables if they don't exist |
| `create_project(name, equipment_name, manufacturer, department, validation_type)` | INSERT + return new id |
| `get_project(project_id)` | SELECT single project row |
| `get_all_projects()` | SELECT all, ordered by `created_at DESC` |
| `delete_project(project_id)` | DELETE + CASCADE to all child rows |

### Messages
| Function | Description |
|----------|-------------|
| `save_message(project_id, role, content)` | INSERT message row |
| `get_messages(project_id)` | SELECT all messages for project, ordered by `created_at ASC` |
| `clear_messages(project_id)` | DELETE all messages for project |

### Documents
| Function | Description |
|----------|-------------|
| `save_document(project_id, original_name, stored_filename, file_type, file_size)` | INSERT + return row id |
| `get_document(doc_id)` | SELECT single document row |
| `get_project_documents(project_id)` | SELECT all docs for project |
| `delete_document(doc_id)` | DELETE document + CASCADE to `document_text` |
| `save_document_text(document_id, project_id, text, page_count, word_count, status)` | INSERT extracted text |
| `get_document_text(document_id)` | SELECT extracted text row |
| `get_project_document_texts(project_id)` | SELECT all text rows for project |

### Generated Documents
| Function | Description |
|----------|-------------|
| `save_generated_document(project_id, doc_type, title, form_data, content)` | INSERT + return id |
| `get_generated_document(doc_id)` | SELECT single generated doc |
| `get_project_generated_documents(project_id)` | SELECT all generated docs for project |
| `delete_generated_document(doc_id)` | DELETE generated doc |

---

## Migrations

There is no migration framework in v0.6. Schema changes require:

1. Stop the Flask server.
2. Delete `pharmagpt/pharmagpt.db` (development only — data loss).
3. Restart the server — `init_db()` recreates all tables.

A migration framework (e.g. Flask-Migrate / Alembic) is planned for v1.0 when moving to PostgreSQL.

---

## Planned Changes (v0.7+)

```sql
-- v0.8: Audit trail
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    action      TEXT NOT NULL,       -- 'create', 'update', 'delete', 'sign'
    entity_type TEXT NOT NULL,       -- 'document', 'project', etc.
    entity_id   INTEGER,
    detail      TEXT,                -- JSON blob
    ip_address  TEXT,
    created_at  TIMESTAMP DEFAULT current_timestamp
);

-- v0.8: Electronic signatures
CREATE TABLE signatures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      INTEGER REFERENCES generated_documents(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,       -- 'author', 'reviewer', 'approver'
    user_name   TEXT NOT NULL,
    signed_at   TIMESTAMP DEFAULT current_timestamp,
    comment     TEXT
);

-- v0.9: Users & RBAC
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL,     -- 'qa', 'validation', 'operator', 'admin'
    created_at    TIMESTAMP DEFAULT current_timestamp
);
```

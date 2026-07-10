# PharmaGPT — Database Reference

**Engine:** SQLite 3  
**File:** `pharmagpt/pharmagpt.db` by default; overridable via the `DB_PATH` env var (auto-created on first run)  
**Managed by:** `pharmagpt/database.py`  
All foreign keys use `ON DELETE CASCADE`.

> **Deployment note:** `pharmagpt.db` is git-ignored and lives on the app
> filesystem by default. On platforms with an ephemeral filesystem (Render
> web services without a mounted disk, most PaaS free tiers, etc.), that
> file is wiped on every restart/redeploy/idle-spindown — writes commit
> successfully but vanish on the next cold start. `render.yaml` mounts a
> persistent disk at `/var/data` and sets `DB_PATH=/var/data/pharmagpt.db`
> so data survives restarts. If you deploy elsewhere, make sure `DB_PATH`
> points at a persistent volume.

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

---

## Quality Management Suite (Phase 1) — added 2026-07-02

Second major pillar (Document Control, Deviation Management, CAPA). Schema
lives in `pharmagpt/qms_database.py` (`QMS_SCHEMA`, hooked into
`database.py::init_db()`), CRUD is split across `qms_document_database.py` /
`qms_deviation_database.py` / `qms_capa_database.py`. Full reference:
[`docs/QMS_PHASE1.md`](docs/QMS_PHASE1.md).

```
qms_documents ──< qms_document_versions
              ──< qms_document_distribution
              ──< qms_document_training

qms_capas ──< qms_capa_actions
          ──< qms_capa_effectiveness

qms_deviations ──< qms_deviation_investigation (1:1)
               ──< qms_deviation_impact
               ──< qms_deviation_capa_link >── qms_capas

-- Shared across all four (and future Phase 3 modules), keyed by
-- (record_type, record_id) instead of one copy per module:
qms_attachments   -- record_type: 'document' | 'deviation' | 'capa' | 'change_control' | 'project'
qms_comments
qms_audit_trail
qms_approvals     -- e-signature trail: performed_by, role, electronic_sig (typed, no PKI)
```

`record_type='project'` was added by PharmaGPT v1.0 Module 3 (2026-07-10) — not a QMS module, but
`qms_audit_trail` is generically reusable, and `record_type='project'` rows already existed from the
one-time `_migrate_val_projects()` copy. `routes/projects.py` now calls
`qms_database.add_audit_entry("project", ...)` on create/update/delete going forward, so the Project
Workspace's History tab shows live history, not just the migrated snapshot. See
[DECISIONS.md](DECISIONS.md) DEC-025.

`qms_documents`, `qms_deviations`, `qms_capas`, and `qms_change_controls` each carry a nullable
`project_id REFERENCES projects(id) ON DELETE SET NULL` — quality records are
not deleted when the referenced validation project is.

---

## Quality Management Suite (Phase 2: Change Control) — added 2026-07-05

Fourth QMS module, built on the same shared polymorphic tables above via `record_type=
'change_control'` — no new shared table added. Schema appended to the same `QMS_SCHEMA` string in
`pharmagpt/qms_database.py`; CRUD lives in `qms_change_control_database.py`. Full reference:
[`docs/QMS_PHASE2.md`](docs/QMS_PHASE2.md).

```
qms_change_controls ──< qms_change_control_impact
                     ──< qms_change_control_actions
                     ──< qms_change_control_links >── qms_deviations | qms_capas
                                                        (linked_type discriminates which)
```

`qms_change_controls.ai_narratives` is a single JSON column (keyed by feature name: risk_summary,
rollback_plan, regulatory_impact, justification, executive_summary, verification_summary,
effectiveness_review) rather than one column per AI narrative feature — same pattern as
`ai_investigation_data`/`ai_review_data` elsewhere in QMS.

## Equipment (PharmaGPT v1.0 Module 2) — added 2026-07-10

Equipment as a first-class business entity, owned by a Project. Schema + CRUD live in
`pharmagpt/equipment_database.py` (new file, per the one-domain-one-file convention, DEC-012).
Two new tables, both additive:

```
projects ──< equipment ──< equipment_documents >── kb_documents | documents
                                                     (source_type discriminates which)
```

- **`equipment`** — one row per physical equipment record. `project_id` is `NOT NULL` with
  `ON DELETE CASCADE` (equipment is a project sub-entity, not a standalone quality record, unlike
  the QMS master tables' nullable `project_id`/`ON DELETE SET NULL` pattern). Carries Basic
  Information (equipment_code/name/category/equipment_type/tag_number/model/manufacturer/vendor/
  serial_number/asset_number), Installation Information (plant/block/department/area/room/line/
  installation_date/commissioning_date), and Qualification Information (qualification_status/
  validation_status/qualification_type/criticality/gmp_impact). Designed as the stable parent row
  future modules (Calibration, Preventive Maintenance, Breakdown History, Spare Parts, Vendor
  Qualification, Environmental Monitoring, Utilities, Asset Management) will FK against — none of
  those tables are created by this module (architecture only).
- **`equipment_documents`** — polymorphic link table (`source_type ∈ {kb, project}`, `source_id`)
  connecting an Equipment record to an existing `kb_documents` or `documents` row. Never copies
  file content, mirroring the "no duplicate documents" requirement and the QMS shared-table
  polymorphic-reference precedent (DEC-010/DEC-011), applied here to a link table rather than an
  owned attachment. `title_snapshot` is denormalized at link time so a broken link (source later
  deleted) still displays a readable label instead of failing silently.

Relationship to `pharmagpt/equipment/` (the pre-existing static Equipment Intelligence Engine
profile registry — HPLC/GC/Autoclave/etc. reference checklists): unchanged, and not merged with
this entity. An `equipment.equipment_type` value may match a catalog entry by string, used only for
AI-context assembly (`services/equipment_service.py`) — no FK or enum constraint ties them together.

`projects.equipment_name`/`manufacturer`/`model`/`equipment_id` (free-text, pre-existing) are
untouched for backward compatibility with existing consumers (chat, validation wizard, prompts).
`POST /projects/<id>/equipment/import-legacy` offers a one-click migration path from those fields
into a real Equipment record, so existing projects can adopt the new entity without duplicate data
entry.

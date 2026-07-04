# Roadmap — PharmaGPT

**Version:** 1.0  
**Date:** 2026-06-27  
**Current Release:** v0.7 (Knowledge Base)

---

## Release History (Completed)

| Version | Name | Status |
|---------|------|--------|
| v0.1 | CLI Foundation | ✅ Done |
| v0.2 | Web App + Streaming Chat | ✅ Done |
| v0.3 | Project Management | ✅ Done |
| v0.4 | Document Upload | ✅ Done |
| v0.5 | AI Document Intelligence (RAG) | ✅ Done |
| v0.6 | Validation Document Generator | ✅ Done |
| v0.7 | Knowledge Base | ✅ Done |
| — | Quality Management Suite — Phase 1 (Document Control, Deviation Management, CAPA) | ✅ Done (2026-07-02) |

---

## Quality Management Suite — Phases 2 & 3 (Not Yet Built)

QMS Phase 1 (Document Control, Deviation Management, CAPA) is complete —
see [`docs/QMS_PHASE1.md`](QMS_PHASE1.md). Its shared Attachments/Comments/
Audit-Trail/Approval tables are polymorphic (`record_type` + `record_id`) and
require no schema changes to extend to future modules — only a new
`record_type` string and the module's own master table.

**Phase 2:** Change Control · Non-Conformance · OOS/OOT
**Phase 3:** Audit Management · Supplier Quality · Training Management · Complaint Management

---

## v0.8 — Validation Workspace & Signatures

**Theme:** Audit-ready, multi-step validation execution with an electronic signature trail.

### Features

#### 1. Validation Workspace (partial backend in place)
- Full UI for `val_projects` — create, edit, track status (Planning → In Progress → Complete)
- Kanban or table view of all active validation projects
- Each project links to its generated IQ/OQ/PQ documents
- Status progression: `Planning → In Progress → Review → Approved → Archived`

#### 2. Electronic Signatures (21 CFR Part 11)
- Sign-off workflow on generated validation documents
- Signature fields: Prepared By, Reviewed By, Approved By (with date + reason)
- Signature records stored immutably in a new `document_signatures` table
- DOCX export includes signature block with locked fields

#### 3. Audit Trail (partial backend in place)
- Full UI for `val_audit_trail` per validation project
- Immutable log: every status change, signature, and document generation recorded
- Audit trail exportable to PDF

#### 4. Vector RAG Upgrade
- Replace keyword/Jaccard scoring with Gemini text embeddings
- New `document_embeddings` table (stores embedding vectors per chunk)
- Cosine similarity scoring for semantically accurate retrieval
- Backward compatible: fall back to keyword search for docs not yet embedded

#### 5. Dashboard Enhancement
- Live project status breakdown (pie chart or donut)
- Recent activity feed (last 10 actions across all projects)
- Upcoming review dates from Knowledge Base (overdue highlighted)

### Database Changes

```sql
-- New table
CREATE TABLE document_signatures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_doc_id INTEGER NOT NULL REFERENCES generated_documents(id) ON DELETE CASCADE,
  role TEXT NOT NULL,           -- 'prepared_by' | 'reviewed_by' | 'approved_by'
  signer_name TEXT NOT NULL,
  signer_title TEXT,
  reason TEXT,
  signed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_locked INTEGER DEFAULT 1   -- once signed, record is immutable
);

-- Add to document_text
ALTER TABLE document_text ADD COLUMN embedding BLOB;  -- serialised numpy array
```

---

## v0.9 — Multi-User & RBAC

**Theme:** Team collaboration with isolated workspaces and role-based permissions.

### Features

#### 1. User Authentication
- Session-based login (Flask-Login)
- User table: `id, email, name, password_hash, role, created_at`
- Password hashing with `bcrypt`
- Remember-me tokens with secure expiry

#### 2. Role-Based Access Control

| Role | Permissions |
|------|------------|
| **Admin** | All operations; manage users; delete any resource |
| **QA Manager** | Approve/sign documents; manage KB; view all projects |
| **Engineer** | Create projects; generate documents; upload files |
| **Viewer** | Read-only access to projects and KB |

#### 3. Organisation-Level Data Isolation
- All project/KB data scoped to an organisation
- New `organisations` and `org_memberships` tables
- Engineers can only see their own projects (unless QA Manager+)

#### 4. Shared Knowledge Base with Permissions
- KB documents can have `visibility: public | org | private`
- QA Manager controls which folders engineers can contribute to

#### 5. Activity Notifications
- In-app notifications for: document signed, project status changed, KB doc expiring soon
- Stored in `notifications` table; real-time delivery via SSE on login

### Database Changes

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'engineer',  -- 'admin' | 'qa_manager' | 'engineer' | 'viewer'
  org_id INTEGER REFERENCES organisations(id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE organisations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add user_id FK to projects, messages, generated_documents, kb_documents
```

---

## v1.0 — Production Hardening

**Theme:** Enterprise-grade reliability, performance, and deployment.

### Features

#### 1. PostgreSQL Migration
- Replace SQLite with PostgreSQL for:
  - Multi-user write concurrency
  - Row-level security for RBAC
  - Full-text search (pg_trgm, tsvector) for KB search upgrade
- SQLite → PostgreSQL migration script provided
- SQLAlchemy ORM introduced to abstract the DB layer

#### 2. Production WSGI Deployment
- Replace Flask dev server with Gunicorn (Linux) or Waitress (Windows)
- Docker Compose setup: app + PostgreSQL + optional Redis
- Environment-specific configs (`development`, `staging`, `production`)

#### 3. Redis for Session & History Cache
- Move `history_cache` dict from in-memory to Redis
- Flask-Session backed by Redis for multi-worker safety
- Cache TTL: history entries expire after 24h of inactivity

#### 4. File Storage Options
- Local disk (current) remains the default
- Optional: AWS S3 / Azure Blob Storage for cloud deployments
- Abstraction layer in `documents.py` so storage backend is swappable

#### 5. Comprehensive Test Suite
- Unit tests: `pytest` for all CRUD functions, RAG pipeline, DOCX exporter
- Integration tests: Flask test client for all 35 endpoints
- E2E tests: Playwright for critical paths (create project → generate doc → export)
- CI pipeline (GitHub Actions): run tests on every PR

#### 6. Observability
- Structured logging (JSON) with request IDs
- `/health` endpoint for load balancer checks
- Basic metrics: request count, SSE stream duration, Gemini API latency

#### 7. 21 CFR Part 11 Compliance Checklist
- Audit trail completeness review
- Electronic signature implementation review
- Access control documentation
- System validation documentation (the app validates itself)

---

## Future Considerations (Post-v1.0)

These items are not committed to any release but are tracked as potential directions:

| Idea | Notes |
|------|-------|
| **Mobile app** | React Native wrapper for field use during equipment qualification |
| **Batch document processing** | Upload a ZIP, extract + ingest all files at once |
| **Regulatory change alerts** | Notify when a KB document's referenced regulation is updated |
| **Third-party integrations** | LIMS, ERP, QMS systems via REST API |
| **Custom AI personas** | Allow orgs to fine-tune the system prompt for specific manufacturing contexts |
| **Offline mode** | IndexedDB-backed local cache for use in restricted network environments |
| **Document diffing** | Compare two versions of a generated document side-by-side |
| **Template library** | Pre-built document templates per equipment category (e.g., HPLC IQ) |
| **SaaS offering** | Multi-tenant cloud deployment with subscription tiers |

---

## Known Technical Debt

| Item | Impact | Priority |
|------|--------|----------|
| `history_cache` is lost on server restart | Users lose conversation context after restart | High |
| No error recovery for failed text extraction | Some docs silently have `extraction_status='error'` with no retry UI | Medium |
| `app.py` is 822 lines, all in one file | Hard to navigate; should be split into blueprints | Medium |
| No input sanitisation on project/KB metadata fields | XSS possible if output is rendered without escaping | Medium |
| `validation_config.js` duplicates field definitions from backend | Should be served from a single source of truth | Low |
| Print CSS is the only PDF export path | Client-side only; no server-side PDF for automation | Low |

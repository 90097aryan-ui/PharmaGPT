# PharmaGPT — Roadmap

**Current version:** v0.6  
**Stack:** Python · Flask · SQLite · Google Gemini 2.5 Flash · Vanilla JS

---

## Completed

| Version | Theme | Status |
|---------|-------|--------|
| v0.1 | Gemini CLI proof-of-concept | ✅ Done |
| v0.2 | Flask SPA + SSE streaming chat | ✅ Done |
| v0.3 | Project management + chat history | ✅ Done |
| v0.4 | Document upload + management | ✅ Done |
| v0.5 | AI document intelligence + RAG (keyword) | ✅ Done |
| v0.6 | Validation document generator (11 types) | ✅ Done |

---

## v0.7 — Saved Document Library + Vector RAG

### Saved Document Library
- View all previously generated documents per project in a dedicated panel
- Re-open, regenerate, or export saved documents directly
- Diff view between two versions of the same document type
- Version counter per doc type (e.g. "IQ Protocol — v3")

### Vector RAG Upgrade
- Replace keyword Jaccard search with real dense embeddings
- Use **Gemini text-embedding-004** (or equivalent) via the `generate_embedding` stub
- Vector store options: **Chroma** (local, zero-config) or **Pinecone** (cloud, production)
- Upgrade both chat and validation generation to use semantic similarity search
- Benchmark retrieval quality vs. current keyword approach

---

## v0.8 — Audit Trail & Approval Workflow

- Electronic signature workflow: **Author → Reviewer → Approver**
- 21 CFR Part 11 compliant audit trail: who did what, when, from which IP
- Document status states: Draft → Under Review → Approved → Superseded
- `audit_log` table: user, action, document_id, timestamp, ip_address
- `signatures` table: doc_id, role, user, signed_at, comment
- Export signed documents with signature block appended to DOCX

---

## v0.9 — Multi-User & RBAC

- User accounts: registration, login, JWT or session auth
- Roles: **QA Engineer**, **Validation Engineer**, **Operator**, **Admin**
- Project-level permissions: who can view / edit / approve
- `users` and `project_members` tables
- Admin panel for user and project management

---

## v1.0 — Production Ready

- Server-side PDF export (WeasyPrint on Linux, or headless Chrome)
- Templates library for site-specific SOPs and master validation plans
- Audit Prep assistant — gap analysis against 21 CFR Part 11, EU GMP Annex 11, ICH Q10
- Docker deployment (Dockerfile + docker-compose)
- PostgreSQL migration path from SQLite
- Rate limiting, HTTPS enforcement, security headers

---

## Future / Exploration

- **NFC/RFID integration** — link validation records to physical equipment tags
- **BatchTrack module** — CDMO project management and inventory tracking
- **Regulatory change alerts** — notify users when referenced standards are updated
- **Multi-tenant SaaS** — organisation isolation, billing, subdomain routing
- **Mobile-responsive UI** — field engineers on tablets

---

## Architecture Decision Log

| Decision | Rationale |
|----------|-----------|
| SQLite over PostgreSQL | Zero-config for v0.x development; migration path documented for v1.0 |
| Vanilla JS over React | Avoids build toolchain; SPA kept simple enough to manage without a framework |
| Client-side PDF via `window.print()` | No GTK/WeasyPrint dependency on Windows dev environment |
| `temperature=0.3` for validation | Consistent document structure; higher temps produce varying section ordering |
| Keyword RAG before vector RAG | Ships faster; establishes correctness baseline before introducing embeddings |

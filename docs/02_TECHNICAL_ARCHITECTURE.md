# 02 — Technical Architecture

**Document:** Yuktav / PharmaGPT — Technical Architecture
**Purpose:** Define HOW the system is technically built. Separates CURRENT STATE (verified from running code) from TARGET STATE (documented future direction) — never conflates them.
**Status:** Active
**Last reviewed:** 2026-08-23
**Source of truth / authority:** Code (`pharmagpt/app.py`, route/service files, `render.yaml`) is authoritative for CURRENT STATE. `docs/PLATFORM_ARCHITECTURE.md` and `docs/DATABASE_ARCHITECTURE.md` (frozen 2026-07-11) are authoritative for TARGET STATE only. `docs/ARCHITECTURE.md` and `PROJECT_MEMORY/ARCHITECTURE.md` are superseded snapshots (pre-QMS and pre-Document-Control respectively) — retained for lineage, not authoritative.
**Known limitations:** No live access to the deployed Render/Supabase environment during this review — statements about "live" behavior are marked accordingly.

---

## 1. Overall Architecture

**CONFIRMED.** A monolithic Flask application (`pharmagpt/app.py`) — one process, no microservices, no message queue. SQLite (raw `sqlite3`, no ORM) is the sole active read/write system of record for nearly all business data today. A partial, code-complete but **inactive** Postgres/Supabase dual-write layer exists for four domains (§5). Frontend is a single server-rendered Jinja2 shell plus vanilla-JS modules, no build step (see [04](04_FRONTEND_SPECIFICATION.md)). Deployed on Render as one web service with a mounted persistent disk (§18).

**TARGET STATE** (per `docs/PLATFORM_ARCHITECTURE.md`, `docs/DATABASE_ARCHITECTURE.md`): a true multi-tenant Supabase/Postgres platform — RLS on every tenant table, unified `documents` table, Supabase Storage for files, Supabase Auth. Current code has not reached this target for the majority of domains, most critically Document Control, which has **no** Postgres exposure at all.

## 2. Frontend Architecture

Brief summary only — full detail in [04_FRONTEND_SPECIFICATION.md](04_FRONTEND_SPECIFICATION.md). Single Jinja2 shell (`pharmagpt/templates/index.html`), ~40 vanilla-JS IIFE modules under `pharmagpt/static/js/` (one per feature area), no framework/router/build step, view switching via DOM display toggling.

## 3. Backend Architecture — Flask Structure

**CONFIRMED**, `pharmagpt/app.py:26-103`. 26 blueprints registered:

`auth`, `projects`, `chat`, `docs`, `validation`, `knowledge_base` (`kb`), `dashboard`, `risk`, `urs`, `qual`, `report`, `qms_common`, `qms_documents`, `qms_deviations`, `qms_capa`, `qms_change_control`, `qms_feature_requests`, `workflow_inbox`, `equipment`, `facility`, `companies`, `users`, `rbac`, `org_structure`, `backup_admin`, `security_admin`.

`db.init_db()` runs at import time; `register_auth_middleware(app)` wires the global tenant/auth gate (see [03](03_SECURITY_ACCESS.md)).

**Note:** `PROJECT_MEMORY/ARCHITECTURE.md` lists only 14 blueprints — it is stale, dated to an earlier commit. Treat `pharmagpt/app.py` as authoritative for the current module list.

## 4. Database Architecture — CURRENT vs TARGET

**CURRENT STATE (CONFIRMED):** SQLite (`DB_PATH`) is the sole read/write source of truth for the application. `pharmagpt/db/backend.py::is_postgres_backend()` always returns `False` in every deployed configuration (`DATABASE_BACKEND` is never set to `postgres`). Postgres/Supabase currently holds only:
- Identity/tenancy tables: `companies`, `users`, `roles`, `break_glass_access` (since migration 0001).
- An organizational-model schema (migration 0014) not yet read by any route.

**TARGET STATE** (frozen docs, 2026-07-11): Supabase Postgres with `company_id` + RLS on every tenant table, a unified `documents` table, Supabase Storage, Supabase Auth as the sole identity layer. Migration path is three phases (SQLite → validated Postgres schema → live Supabase cutover) — **not started for business data**.

## 5. SQLite Usage — Per-Domain Status

**CONFIRMED.** Dual-write to Postgres exists in code, gated by environment flags, all defaulting to `sqlite`, **none enabled in any deployed environment** (`render.yaml`):

| Domain | Flag | Status |
|---|---|---|
| Projects | `PROJECTS_BACKEND` | Dual-write code complete, flag unset (SQLite active) |
| Knowledge Base | `KB_BACKEND` | Dual-write code complete, flag unset; extracted text explicitly NOT synced even when enabled |
| Equipment | `EQUIPMENT_BACKEND` | Dual-write code complete, flag unset |
| Deviations / CAPA / Change Control / Risk Assessments | `QMS_BACKEND` | Dual-write code complete, flag unset |
| **Document Control (`qms_documents`)** | **none** | **SQLite-only. No dual-write path exists at all.** |

**CONFIRMED — Document Control has zero Postgres exposure.** `QMS_BACKEND` does not appear anywhere in `pharmagpt/routes/qms_documents.py` or `pharmagpt/qms_document_database.py`; the latter imports only `pharmagpt.database.get_connection` (SQLite), never `supabase_client`. `tests/test_qms_dual_write.py` covers only `deviation, capa, change_control, risk_assessment` — Document Control is absent from that test file entirely. This confirms `docs/LESSONS_LEARNED.md` §14 directly.

**Do not assume architectural uniformity across domains.** Each of the five domains above has an independently-gated, independently-progressed migration state.

## 6. Tenant Isolation (technical mechanism)

**CURRENT:** `pharmagpt/auth/context.py::TenantContext` + `pharmagpt/tenancy.py::scoped_or_none()` filter every SQLite query by `company_id` in application code. No database-level enforcement exists for SQLite-resident data — isolation is 100% application-layer there.
**TARGET:** dual-layer (app filter + Postgres RLS) for all tenant tables. Currently true only for the Postgres-resident identity tables (§4). See [03](03_SECURITY_ACCESS.md) for the full security picture.

## 7. QMS Architecture

**CONFIRMED.** Sub-modules: Document Control, Deviation Management, CAPA (Phase 1), Change Control (Phase 2). Schema lives in `qms_database.py` (`QMS_SCHEMA`), one CRUD file per domain. Shared polymorphic SQLite tables reused across all QMS domains: `qms_attachments`, `qms_comments`, `qms_audit_trail`, `qms_approvals` (keyed by `record_type`/`record_id`).

Persistence per domain:

| Domain | Persistence |
|---|---|
| Document Control | SQLite only (no Postgres path) |
| Deviations / CAPA / Change Control / Risk Assessments | SQLite (active) + optional Postgres dual-write (inactive, flagged) |

## 8. Document Control Architecture

**CONFIRMED, current build:**
- **Storage:** SQLite tables `qms_documents`, `qms_document_versions`, `qms_document_distribution`, `qms_document_training`, `qms_document_templates` (controlled-template structure: headings/sub-headings only, no content).
- **Versioning:** `pharmagpt/services/document_versioning.py` — pure-logic numbering (`0.1 → 0.2 → ... → 1.0`, then `X.1 → ... → (X+1).0` on each new Effective release); no DB access of its own.
- **Review/approval chain:** author-assigned Reviewer/Department Head/Quality Head/Plant Head; sequential dispatch via the generic workflow engine (§9).
- **Controlled PDF review:** `GET /qms/documents/<id>/review-pdf` → `qms_document_service.py::generate_review_pdf()` reuses the DOCX export pipeline, then converts DOCX→PDF via **PyMuPDF (`fitz`)**, stamping a per-page watermark manually. (Word's native watermark does not survive this conversion reliably — documented empirically in code.)
- **DOCX export:** `POST /qms/documents/<id>/export/docx`, same `markdown_to_docx` pipeline.
- **AI-assisted generation:** streamed via `qms_shared.stream_gemini`, prompts in `pharmagpt/prompts/qms_document_prompt.py`.
- **File storage:** local filesystem only (`UPLOAD_FOLDER`) — no Supabase Storage call exists anywhere in the codebase (`storage.from_` grep returns zero hits).

## 9. Workflow Engine

**CONFIRMED.** A genuinely reusable, record-type-agnostic engine exists: `pharmagpt/services/workflow_engine.py`, backed by `qms_workflow_database.py`, dispatching via a `STATUS_APPLIERS` registry (not per-module if/elif branching). Used by Document Control's review/approval chain and by Deviation investigation steps. It is a lightweight named-step/named-approver state machine, not a full BPMN engine.

**Gap (disclosed, not fixed):** CAPA and Change Control are **not** wired into this lifecycle engine — their status fields can transition to any value without a validated state machine (see ticket in [05](05_FEATURE_TICKETS.md)).

## 10. Knowledge Base Architecture

**CONFIRMED.** `kb_documents` SQLite table, files under `uploads/kb/`, 8 fixed folders, keyword/Jaccard-similarity search (no vector embeddings). `pharmagpt/services/kb_sync.py` auto-publishes approved documents from Document Control/URS/Qualification/Validation Reports into the KB via idempotent upsert keyed on `source_type`/`source_id`. The `KB_BACKEND` dual-write flag exists but explicitly does not sync extracted text even when enabled.

## 11. Equipment Library Architecture

**CURRENT:** `equipment` + `equipment_documents`/`equipment_links` polymorphic tables, **project-owned** (`project_id NOT NULL ON DELETE CASCADE`).
**TARGET:** company-owned (per `docs/PLATFORM_ARCHITECTURE.md` §10, `docs/DATABASE_ARCHITECTURE.md` §19.2) — re-parenting migration **not yet executed in code**.

## 12. AI Generation Architecture

**CONFIRMED.** Single Google Gemini client (`gemini-2.5-flash`). Streaming (SSE, `temperature=0.3` for document generation) and non-streaming calls. Retrieval is keyword/Jaccard scoring over chunked text (`document_search.py`) — **no vector embeddings/semantic search** in the current build; pgvector-based semantic search is TARGET STATE (v1.1) only. Prompts are centralized per-domain under `pharmagpt/prompts/`.

**ASSUMPTION, not independently reverified:** commit messages reference an "AI orchestration router" and pluggable-provider support (e.g. NVIDIA Nemotron); whether this has replaced single-provider Gemini as the default was not confirmed in this pass.

## 13. Document Generation / Export

**CONFIRMED.** Markdown → DOCX via a custom state machine (`doc_exporter.py` / `docx_generator.py`, built on `python-docx`) — no pandoc dependency. PDF: client-side `window.print()` for general documents; a dedicated PyMuPDF-based DOCX→PDF conversion specifically for Document Control's review surface (§8).

## 14. File Storage — CURRENT STATE

**CONFIRMED.** Local filesystem exclusively — `UPLOAD_FOLDER`, `GENERATED_DOCS_PATH`, both under Render's mounted persistent disk. No Supabase Storage bucket call exists anywhere in the codebase today.
**TARGET STATE:** Supabase Storage private buckets — not built.

## 15. Background Jobs

**CONFIRMED.** `ThreadPoolExecutor` via `pharmagpt/services/job_runner.py` (`ThreadPoolJobRunner`) for asynchronous document text extraction only. No Celery, no APScheduler in active use. A backup cron job is **documented in `render.yaml` but commented out / not deployed**.

## 16. API Structure

REST-ish JSON over Flask blueprints, one URL prefix per domain (`/qms/documents`, `/risk`, `/urs`, etc.), Server-Sent Events for streaming endpoints, uniform JSON error handlers (`app.py:134-152`).

## 17. External Services

**CONFIRMED.** Google Gemini (`google-genai`) for all AI generation; Supabase for Auth + the partial identity/tenancy Postgres layer + the four flagged (inactive) dual-write domains. No other third-party services — no Storage, no vector DB, no message queue.

## 18. Render Deployment — CURRENT STATE

**CONFIRMED**, `render.yaml`: single `runtime: python` web service, `starter` plan, gunicorn (`--worker-class=gthread --workers=2 --threads=4 --timeout=60`), a 5GB persistent disk mounted for the SQLite DB, uploads, and generated documents. `SUPABASE_SERVICE_ROLE_KEY` is required for the identity-admin path but must be set manually — not auto-populated by IaC. All migration flags are left unset (SQLite default). The backup cron job is present in the file but commented out.

## 19. Oracle Deployment Target — UNRESOLVED

**Only one reference to "Oracle" exists anywhere in the repository:** `docs/LESSONS_LEARNED.md` line ~642, inside a bare roadmap arrow-diagram ("Deploy the complete system to Oracle"), with no elaboration and no other doc or config referencing an Oracle Cloud or Oracle Database target. **This is not a documented, actionable architectural decision.** It must not be presented as a confirmed deployment target.

**CONFLICT / REQUIRES DECISION:** clarify with the product owner what "Oracle" refers to (Oracle Cloud Infrastructure, Oracle Database, or a placeholder name) before any architecture document treats it as a real target platform.

## 20. Environment Separation

**AS DOCUMENTED, NOT VERIFIED LIVE.** `docs/LESSONS_LEARNED.md` §13 documents the *intended* map:

```
PRODUCTION: Render Production → Supabase Production
STAGING:    Render Staging    → Supabase Staging
```

A historical investigation (`docs/FINAL_DATABASE_ROOT_CAUSE.md`, 2026-07-24) found **no actual staging/production split in config** at that time — `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY` were single, undifferentiated environment variables with no staging Supabase project referenced anywhere. That finding predates several later commits and is not necessarily current, but nothing found in this review contradicts it. **Treat environment separation as TARGET/aspirational, not confirmed current infrastructure**, until independently re-verified against the live Render dashboard.

## 21. Audit Architecture

**CURRENT:** polymorphic SQLite `qms_audit_trail` (`record_type`/`record_id`), append-only via `pharmagpt/audit.py::log()` / `log_failure()`, reused platform-wide (including `record_type='project'`).
**TARGET:** the same pattern, generalized platform-wide as a Postgres `audit_trail` table with INSERT/SELECT-only RLS (no UPDATE/DELETE policy at all) — not yet built for SQLite-resident domains.

## 22. Architectural Debt / Transitional Inconsistencies (explicit)

1. **Document Control has zero Postgres exposure** — no flag, no dual-write, no test coverage — while Deviations/CAPA/Change Control/Risk share one `QMS_BACKEND` flag with inactive dual-write.
2. **Projects/KB/Equipment** each have an independent migration flag, all inactive, all requiring a staging soak + 2-company RLS spot-check before SQLite retirement — none performed.
3. **Projects** cannot reach a Postgres read-cutover without a route/ID reshape (integer IDs → UUIDs) — not started.
4. **Equipment** is project-owned today; target schema is company-owned — an unstarted re-parenting migration.
5. **No Supabase Storage anywhere** — 100% local disk today vs. a Storage-based target.
6. **`PROJECT_MEMORY/ARCHITECTURE.md` is stale** (14 blueprints vs. current 26; predates Document Control entirely).
7. **Backup framework is fully coded but not deployed** (encryption key unset, cron commented out).

This debt is documented, not resolved, per this task's scope (see [LESSONS_LEARNED.md](LESSONS_LEARNED.md) §21, §26 — do not fix architecture while documenting it).

## 23. Open Questions / Conflicts

1. **Oracle deployment target (§19)** — needs product-owner clarification; not currently a real decision.
2. **`docs/FINAL_DATABASE_ROOT_CAUSE.md`'s "Company Administration never committed" finding (2026-07-24)** — superseded: `pharmagpt/routes/companies.py` and `pharmagpt/routes/users.py` are present and registered in `app.py` today. Cite that report only as a historical incident with its date, not as current state.
3. **Environment separation (§20)** — documented intent vs. unverified live config; needs a live Render/Supabase check, not a documentation fix.
4. **AI provider default (§12)** — needs a targeted code check to confirm whether a multi-provider router has superseded single-provider Gemini.

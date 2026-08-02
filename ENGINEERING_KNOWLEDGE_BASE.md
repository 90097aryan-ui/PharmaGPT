# PharmaGPT — Engineering Knowledge Base

Status: compiled from repository inspection on 2026-08-02.
Authority hierarchy: CLAUDE.md → FOUNDATION_ARCHITECTURE.md → PROJECT_MEMORY/ → docs/ → source.

## 1. Complete System Architecture

PharmaGPT is a monolithic Flask 3.1.3 application with a vanilla-JavaScript SPA frontend.
- Backend: Flask blueprints per domain, raw `sqlite3` (no ORM), REST-style JSON APIs, SSE for streaming AI output.
- Frontend: `templates/index.html` single shell; each feature area is one IIFE module under `pharmagpt/static/js/`.
- AI: Google `gemini-2.5-flash` via `google-genai`. Structured generation uses `temperature=0.3`; chat uses default.
- Background jobs: `concurrent.futures.ThreadPoolExecutor` through `services/job_runner.py` (`ThreadPoolJobRunner`).
- Deployment: Render (`render.yaml` + `Procfile`), gunicorn `--worker-class=gthread --workers=2 --threads=4`, persistent disk at `/var/data`.
- Database today: SQLite 3 file (`pharmagpt.db`, overridable via `DB_PATH`).
- Database target: PostgreSQL on Supabase, with Row-Level Security (RLS), dual-write scaffolding already merged but **not activated** in any environment.

## 2. Folder-by-Folder Explanation

- `pharmagpt/app.py` — Flask app factory; registers blueprints, initializes DB, serves SPA shell at `/`, provides `/health`, and installs JSON error handlers.
- `pharmagpt/config.py` — Env-driven config: Gemini model, secret key, debug/port, upload limits, extraction tuning, URS generation batching, and per-domain Postgres migration flags.
- `pharmagpt/database.py` — Core schema + CRUD for projects, messages, documents, document_text, generated_documents, val_* history tables, and KB. Contains `init_db()` and additive column guard pattern.
- `pharmagpt/logging_config.py` — Logging setup.
- `pharmagpt/documents.py` — File upload/download utilities, filename collision handling, extension allow-list.
- `pharmagpt/prompts.py` — Core `PHARMA_SYSTEM_PROMPT` chat persona.
- `pharmagpt/state.py` — Shared runtime singletons: Gemini client, per-project conversation history cache.
- `pharmagpt/*_database.py` — One file per domain for DB access: `risk_database.py`, `urs_database.py`, `qual_database.py`, `report_database.py`, `qms_database.py`, `qms_document_database.py`, `qms_deviation_database.py`, `qms_capa_database.py`, `qms_change_control_database.py`, `equipment_database.py`.
- `pharmagpt/routes/` — Flask Blueprints per domain; each owns its HTTP layer and delegates to services/databases.
- `pharmagpt/services/` — Business logic and AI orchestration: document processing, extraction, RAG search, retrieval, generation, domain services, workflow/lifecycle engines, Supabase client, job runner.
- `pharmagpt/services/extraction/` — Async document intelligence engine: multi-engine fallback, per-page timeout, progress callbacks.
- `pharmagpt/review/` — Deterministic non-AI validation-document scoring engine.
- `pharmagpt/equipment/profiles/` — Static equipment-type reference libraries.
- `pharmagpt/prompts/` — Per-domain Gemini prompt templates.
- `pharmagpt/static/css/` — Stylesheets: core `style.css`, reusable `workspace.css`, plus one per suite.
- `pharmagpt/static/js/` — One IIFE module per feature area; no build step.
- `pharmagpt/templates/index.html` — Single SPA shell; every view is a JS-toggled div.
- `pharmagpt/uploads/` — Project-scoped file storage; `kb/` for Knowledge Base.
- `pharmagpt/auth/` — Supabase Auth middleware, context resolution, decorators, tenant utilities.
- `tests/` — pytest suite with throwaway SQLite per test via `db_path` fixture.
- `migrations/` — SQL scripts for Supabase schema, RLS, grants, identity/admin features.
- `scripts/` — Admin/backfill/parity/seed scripts for Supabase operations; not web-reachable.
- `docs/` — Detailed reference docs.
- `PROJECT_MEMORY/` — Authoritative living memory: ARCHITECTURE.md, DECISIONS.md, PROJECT_STATUS.md, RELEASE_NOTES.md.

## 3. Database Architecture

SQLite 3 today; no ORM; every function opens/closes its own connection with `PRAGMA foreign_keys = ON`.
No migration framework. Schema changes must be additive-only, guarded by `_add_column_if_missing()` when needed.
Dev-only full reset is acceptable pre-v1.0.

### Core Tables
- `projects` — unified validation engagement owner; carries legacy free-text equipment fields plus merged Validation Workspace fields.
- `messages` — per-project chat history.
- `documents` — uploaded file metadata; bytes on disk.
- `document_text` — extracted plain text per document.
- `generated_documents` — saved AI-generated validation docs.
- `kb_documents` — Knowledge Base documents.
- `val_projects` / `val_audit_trail` — retired read-only history.

### QMS Shared Tables (polymorphic, `record_type` + `record_id`)
- `qms_attachments`
- `qms_comments`
- `qms_audit_trail`
- `qms_approvals`

### QMS Module Tables
- Document Control: `qms_documents`, `qms_document_versions`, `qms_document_distribution`, `qms_document_training`
- Deviation: `qms_deviations`, `qms_deviation_investigation`, `qms_deviation_impact`, `qms_deviation_capa_link`
- CAPA: `qms_capas`, `qms_capa_actions`, `qms_capa_effectiveness`
- Change Control: `qms_change_controls`, `qms_change_control_impact`, `qms_change_control_actions`, `qms_change_control_links`
- Workflow: `qms_workflow_templates`, `qms_workflow_template_steps`, `qms_workflow_instances`, `qms_workflow_instance_steps`, `qms_workflow_step_approvers`, `qms_deviation_workflow_steps`

### Other Domain Tables
- Risk: `risk_assessments`, hazard/likelihood/severity/mitigation sub-records.
- URS: `urs_projects`, `urs_requirements`.
- Qualification: IQ/OQ/PQ tables plus approval tables.
- Validation Report: report templates and completion records.
- Equipment: `equipment`, `equipment_documents`.

### Postgres Target Schema
Defined in `docs/DATABASE_ARCHITECTURE.md`. Key differences:
- Every tenant-scoped table carries `company_id NOT NULL`.
- RLS policies enforce `company_id` isolation.
- `project_members` for project-level membership.
- Unified `documents` table replacing `kb_documents` and `generated_documents`.
- `audit_trail`, `attachments`, `comments`, `approvals` are platform-wide polymorphic tables, not `qms_`-prefixed.
- Equipment is company-owned, not project-owned.
- `break_glass_access` for Super Admin tenant access.
- `equipment_links` replaces `equipment_documents`.

## 4. API Architecture

- Base URL: `http://127.0.0.1:5000`.
- All request/response bodies are JSON unless noted.
- 14 Flask blueprints registered in `app.py`.
- SSE (`text/event-stream`) for `/stream` and `/validation/generate`.

Key blueprints:
- `auth` — login/logout/assume-company/companies/users.
- `projects` — project CRUD, messages, generated docs, equipment import.
- `chat` — `/stream` SSE chat.
- `docs` — project document upload/view/download/delete, async extraction status, retry.
- `validation` — validation document generation, DOCX export, save.
- `knowledge_base` — KB CRUD/search.
- `dashboard` — home stats.
- `risk` — Risk Management Suite.
- `urs` — URS Management Suite.
- `qual` — Qualification Suite.
- `report` — Validation Report Suite.
- `qms_common` — shared QMS dashboard/meta/attachments/comments/audit/approvals.
- `qms_documents` — Document Control.
- `qms_deviations` — Deviation Management.
- `qms_capa` — CAPA.
- `qms_change_control` — Change Control.
- `workflow_inbox` — universal `/workflow/inbox` and `/workflow/inbox/stats`.
- `equipment` — Equipment CRUD, search, document links, AI-context bundle.
- `companies` / `users` — Company Administration / User Management.

## 5. Workflow Engine Architecture

`services/workflow_engine.py` is a generic, record-type-agnostic approval workflow engine.
- Templates: `qms_workflow_templates` + steps.
- Instances: `qms_workflow_instances` + instance steps.
- Decisions: `decide_step()` enforces named-approver checks for approval steps and `eligible_roles` checks for activity steps.
- Status application: `STATUS_APPLIERS` registry maps `record_type` to a status writer; adding a future module is one function + one registry entry.
- Audit: every transition logged via `audit.log()`.

`services/workflow_registry.py` provides `ModuleDescriptor` objects so the universal `/workflow/inbox` needs zero new code when a new module adopts the engine.

Deviation Workflow Builder:
- `routes/qms_deviations.py` exposes `GET|PUT /qms/deviations/{id}/workflow-builder`.
- Configuration is the sole place approvers are set for deviations; there is no runtime assignment action.
- On submit, the builder compiles a dynamic template from saved steps and auto-assigns all configured approvers.

## 6. Document Lifecycle

### Current Implemented Lifecycles
- QMS Document: Draft → Under Review → Pending Approval → Effective → Under Revision → Obsolete.
- URS: draft → under_review → pending_approval → approved → effective → obsolete.
- Qualification: draft → under_review → pending_approval → approved → closed → obsolete.
- Validation Report: draft → under_review → approved → released → archived → obsolete.
- Risk Assessment: Draft → In Review → Approved → Closed.
- Deviation: custom 10-step investigation workflow ending in Closed.
- CAPA: Draft-like progression into Open → Closed.
- Change Control: 13-stage Draft → ... → Closed.

### Target Spec
Draft → Under Review → Approved → Effective → Obsolete → Archived.

### Enforcement
`services/lifecycle_engine.py` centralizes `validate_transition()` for URS, QMS Document, Qualification, Validation Report, and Risk Assessment. CAPA and Change Control do **not** currently use the lifecycle engine.

## 7. QMS Modules

### Document Control
- Lifecycle, auto-numbering (`SOP-QA-0001`), version history, training tracking, distribution/acknowledgement.
- AI draft generation and AI regulatory compliance review.
- Shared attachments/comments/audit/approvals.

### Deviation Management
- Severity: Minor/Major/Critical/Market.
- Investigation: AI Investigation Assistant (fishbone/5-Why/timeline/root cause), impact assessment, CAPA linking.
- Workflow Builder for approval chain configuration.
- Shared polymorphic tables.

### CAPA
- Actions, escalation, effectiveness checks.
- AI draft/effectiveness suggestions.
- AI Quality Trend Summary across CAPAs and Deviations.
- Linked deviations via `qms_deviation_capa_link`.

### Change Control
- 26 categories, 6 types, 13-stage workflow.
- AI impact assessment, implementation plan, multiple AI narrative features persisted in `ai_narratives` JSON column.
- Links to Deviations and CAPAs via `qms_change_control_links`.

## 8. Equipment Library

- `equipment` table: project-owned entity with Basic/Installation/Qualification information.
- `equipment_documents`: polymorphic links to `kb_documents` or project `documents`.
- Static `pharmagpt/equipment/` catalog of equipment-type reference profiles.
- AI context bundle endpoint at `GET /equipment/{id}/ai-context` (architecture-only, not yet wired into generation).
- `POST /projects/{id}/equipment/import-legacy` migrates a project's free-text equipment fields into real Equipment records.

## 9. Risk Engine

- `risk_database.py` manages risk assessment CRUD.
- AI generation via `services/risk_service.py`.
- E-signature approval workflow.
- `/publish` endpoint exists and is noted in security findings as bypassing the gated approval action.

## 10. Investigation Engine

`services/investigation_engine.py` + `qms_investigation_database.py`:
- Locked/unlocked model gated by workflow approval.
- Evidence, SOP reviews, interviews, timeline events, root cause (Possible → Probable → Confirmed), investigation summary.
- AI assistant and AI report generation with prompt-guided refusal behavior.
- Tasks, dashboard with deterministic evidence scoring.
- Append-only AI history.

## 11. Authentication

- Supabase Auth is the sole identity provider.
- Global `before_request` hook (`pharmagpt/auth/middleware.py`) validates bearer token or session-cookie fallback.
- Session cookie is signed, HttpOnly, SameSite=Lax, Secure outside debug mode.
- Login/logout handled in `routes/auth.py`.
- Super Admin, Company Admin, Reviewer/QA, User roles.

## 12. Authorization

- Application-layer `@require_role` guards on destructive/approval routes.
- `tenancy.py` provides `scoped_or_none()` and `signing_identity()` utilities.
- **Known gap on SQLite path**: legacy tables lack `company_id` and SQLite queries do not filter by tenant. Postgres RLS is defined but not active.

## 13. Multi-Tenancy

- Model: shared database, shared schema, row-level isolation via `company_id` + PostgreSQL RLS.
- Current live path: SQLite with application-layer scoping. **SQLite schema itself has no `company_id` columns in legacy tables**; cross-tenant IDOR was fixed in code but the database-level backstop does not exist on SQLite.
- Postgres path: migrations 0001–0014 create identity, tenancy, RLS, grants, and organizational schema. Not active in production.
- Break-glass: `break_glass_access` table + explicit Super Admin Assume Company Context flow with time-boxed grants.

## 14. Supabase Migration Status

- Dual-write code merged for Projects, KB, Equipment, QMS; gated by env vars defaulting to `sqlite`.
- Backfill and parity-check scripts exist and have been run once with 0 drift.
- **No domain has cut over to Postgres reads.**
- Cutover gate (not satisfied): extended Staging soak per domain + live 2-company RLS isolation spot-check.
- Phase 3.6 (SQLite retirement) is not started and requires route/id-shape work before Projects can read from Postgres.

## 15. Testing Strategy

- Framework: pytest 8.3.4.
- Config: `pytest.ini` sets `testpaths = tests`, excludes `slow` by default.
- Isolation: `tests/conftest.py::db_path` points each test at a throwaway SQLite file; `init_db()` recreates schema per test.
- Auth bypass shim: most tests patch `is_exempt()` and receive a fixed `_TEST_TENANT`; `test_app_auth_integration.py` exercises real auth.
- No CI/CD pipeline found; tests run manually.
- Test count has drifted across reports; current suite is in the 390–514 range depending on snapshot.

## 16. Coding Standards

- Backend: Flask blueprints per domain, raw `sqlite3` (no ORM), REST JSON, SSE streaming.
- Database: avoid SQLite-only syntax where a Postgres-compatible alternative exists.
- Frontend: vanilla JS IIFE modules, `window` namespace exposure, Lucide icons, no framework, no build step.
- Theme: dark enterprise UI; document viewer/export is the deliberate light-background exception.
- File size: split files once they approach ~1000 lines.
- Background jobs: `ThreadPoolJobRunner` only; do not introduce Celery unless Redis is also introduced.
- Reuse existing `services/`, `routes/`, `prompts/` implementations; do not duplicate.
- Additive DB migrations only; use `_add_column_if_missing()` guards.
- Never change API request/response shapes without updating `API.md` and `RELEASE_NOTES.md`.

## 17. UI Standards

- Palette: Premium Enterprise v3.0 warm business-attire tokens defined in `static/css/style.css` `:root`.
- Icons: Lucide via CDN; auto-converted by global `refreshIcons()` + `MutationObserver` in `templates/index.html`.
- Workspace shell: `.ent-workspace` layout in `workspace.css` + `workspace.js` for full-screen flows.
- Tabs: `.ws-tabs`/`.ws-tab` generic component; per-suite `.eq-tabs`/`.qms-tabs` exist.
- Desktop-first; mobile not yet prioritized.

## 18. Validation Requirements

- Never weaken validation lifecycle sequencing: IQ → OQ → PQ.
- Never weaken Validation Report gating on qualification completeness.
- Never weaken document lifecycle transitions.
- Always perform regression testing (`pytest`) before considering a change complete.
- Always produce automated tests for new behavior.

## 19. Regulatory Requirements

- 21 CFR Part 11, EU GMP Annex 11, Annex 15, GAMP 5, ICH Q9/Q10 govern implementation decisions.
- Audit trail must capture Timestamp, User, Company, Old Value, New Value, Action.
- E-signature integrity is load-bearing; never allow client-spoofable identity on approval or creation paths.
- Cross-tenant isolation is a zero-tolerance requirement.
- Do not invent regulatory references; if compliance detail affects implementation, include it explicitly.

## 20. Technical Debt

- No migration framework (Alembic/Flask-Migrate).
- No CI/CD pipeline.
- SQLite→Postgres cutover incomplete; dual-write flags exist but are not exercised.
- `risk_database.py` leaks a SQLite connection in all functions.
- No per-request Supabase auth/tenant resolution caching.
- Vector RAG stubs exist but are unimplemented.
- DQ/FAT/SAT dedicated prompt modules are registered but never invoked.
- CAPA/Change Control lack lifecycle engine integration.
- Project status has no governed lifecycle.
- Exported DOCX styling still uses pre-redesign navy.

## 21. Known Issues

From repo-documented reports:
- C1: Company Administration routes/migrations uncommitted/undeployed in production.
- C2: Postgres GRANT/RLS for `companies`/`users`/`break_glass_access` not active in live Supabase.
- C3: `SUPABASE_SERVICE_ROLE_KEY` missing from production config and stale docs.
- C4: PUT/DELETE unaudited in most domains.
- C5: Audit trail schema lacks Old/New Value and Company columns.
- C6: Identity spoofable in non-canonical endpoints (attachments, comments, protocol completion, version snapshots).
- C7: Unguarded state-changing endpoints for Risk `/publish`, Qualification protocol completion, CAPA escalation, QMS distribution/training.
- Cross-tenant IDOR: fixed in application code on SQLite path; database-level backstop only exists on Postgres, which is not active.
- Raw exception text leaks to client on some error paths.
- `FLASK_SECRET_KEY` hardcoded dev fallback.
- File upload validation is extension-only; no magic-byte/MIME check.
- No CSRF token framework.

## 22. Future Roadmap

- v1.0 Module 4: AI Intelligence Integration (Equipment AI-context bundle, vector-RAG wiring).
- QMS Phase 3: Audit Management, Supplier Quality, Training Management, Complaint Management.
- v1.0 production hardening: server-side PDF export, Docker packaging, rate limiting, security headers.
- Postgres cutover: Staging soak, RLS spot-check, SQLite retirement.
- Future exploration: NFC/RFID, BatchTrack, regulatory change alerts, multi-tenant SaaS, mobile.

## 23. Recommended Development Workflow

1. Read `PROJECT_MEMORY/CLAUDE.md` first.
2. Read `FOUNDATION_ARCHITECTURE.md` for frozen architecture.
3. Read `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RELEASE_NOTES.md` before coding.
4. Create a feature branch; never modify `main` directly.
5. Inspect only the source files required for the task.
6. Reuse existing `services/`, `routes/`, `prompts/`; do not duplicate.
7. Make additive DB changes only; use guarded column helpers.
8. Write/update tests in `tests/test_*.py`; run `python3 -m pytest`.
9. Update `PROJECT_MEMORY/` and root docs in the same change if behavior/architecture changes.
10. Do not commit or push automatically.
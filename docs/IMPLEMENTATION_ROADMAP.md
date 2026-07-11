# PharmaGPT Implementation Roadmap v1.0

**Document class:** Master Execution Plan (Frozen)
**Author role:** Lead Software Architect / Technical Project Manager
**Status:** FROZEN — governs the order and shape of all migration work. Changes require a formal decision entry in §15, not silent drift.
**Date:** 2026-07-11
**Governing documents (not modified, not redesigned by this document):** [`PLATFORM_ARCHITECTURE.md`](PLATFORM_ARCHITECTURE.md) and [`DATABASE_ARCHITECTURE.md`](DATABASE_ARCHITECTURE.md). Every phase, task, and decision below implements a decision already made in those two documents; none is re-opened here. Where this document names a concrete file, table, or route, it is describing *how* the frozen architecture gets built, never *whether*.
**Scope:** This is a planning document. It contains no code, no SQL, and no implementation detail beyond what a developer needs to know which file to open, which table to touch, and in what order — consistent with the instruction that a developer should be able to execute this plan without making an architectural decision of their own.

---

## 1. Current State Assessment

### 1.1 What exists today

A single-tenant Flask application (`pharmagpt/`), currently at v0.9.5, deployed on Render with a mounted persistent disk, backed by SQLite (`pharmagpt.db`) and local-disk file storage (`uploads/`). Confirmed by direct inspection of the repository, not just prior documentation, the application is materially larger than `PROJECT_STATUS.md`'s last full description:

- **Core app:** `app.py`, `config.py`, `database.py`, `documents.py`, `state.py`, `logging_config.py`.
- **Domain databases** (SQLite CRUD, one file per domain): `database.py` (projects/messages/documents/kb_documents/generated_documents), `equipment_database.py`, `qms_database.py` + `qms_capa_database.py` + `qms_change_control_database.py` + `qms_deviation_database.py` + `qms_document_database.py`, `qual_database.py`, `report_database.py`, `risk_database.py`, `urs_database.py`.
- **Routes (Flask blueprints):** `chat.py`, `dashboard.py`, `docs.py`, `equipment.py`, `knowledge_base.py`, `projects.py`, `qms_capa.py`, `qms_change_control.py`, `qms_common.py`, `qms_deviations.py`, `qms_documents.py`, `qual.py`, `report.py`, `risk.py`, `urs.py`, `validation.py`.
- **Services:** document generation/export (`doc_generator.py`, `docx_generator.py`, `doc_exporter.py`), document reading (`docx_reader.py`, `excel_reader.py`), a multi-engine PDF **extraction pipeline** (`services/extraction/` — `base.py`, `pdf_engines.py`, `pipeline.py`, `registry.py`, `simple_engines.py`, `stats.py`), `document_search.py` (keyword RAG), `retrieval_engine.py`, `equipment_service.py`, `job_runner.py` (async job abstraction), five QMS/suite service files, `urs_generation_job.py`, `urs_requirement_library.py`.
- **Prompts:** 20 pharmaceutical-domain prompt-builder modules (`prompts/`), one per document type plus shared helpers.
- **Review engine:** `review/` — `review_engine.py`, `review_formatter.py`, `review_models.py`, `review_rules.py`.
- **Static equipment reference catalog:** `equipment/profiles/` — seven equipment-type profile modules (analytical, manufacturing, packaging, processing, quality_control, sterilization, testing), explicitly documented as unrelated to and unmodified by the Equipment entity (`FOUNDATION_ARCHITECTURE.md` §2.2).
- **Frontend:** one SPA shell (`templates/index.html`) plus 21 JS modules (`static/js/`).
- **Tests:** 148+ tests (`tests/`, pytest), covering Document Intelligence, QMS, Equipment, Project Workspace, URS generation.
- **Deployment substrate:** Render (`render.yaml`, `Procfile`, gunicorn), GitHub, no CI-enforced test gate beyond what's locally run.

### 1.2 What remains unchanged by this migration

Deliberately, and for the reasons in §2: the **prompt library** (`prompts/`), the **PDF/DOCX/XLSX extraction pipeline** (`services/extraction/`), the **document generation and export logic** (`doc_generator.py`, `docx_generator.py`, `doc_exporter.py`, `docx_reader.py`, `excel_reader.py`), the **review engine** (`review/`), the **static equipment-type reference catalog** (`equipment/profiles/`), and the **async job abstraction** (`job_runner.py`) — none of these are tenancy-coupled or storage-coupled today, and none require a rewrite to fit the target architecture. They require, at most, their inputs/outputs re-pointed at the new data and storage layer (§5).

### 1.3 What must be replaced

- **SQLite → PostgreSQL (Supabase):** every domain database module (`database.py` and its ten siblings) is SQLite-specific and has no `company_id` concept anywhere.
- **Local disk (`uploads/`) → Supabase Storage:** `documents.py`'s file-system helpers assume a local, single-instance filesystem — incompatible with `PLATFORM_ARCHITECTURE.md` §15's "Render filesystem is never a source of truth" rule and with the Render mounted-disk risk `DATABASE.md` already flags.
- **No authentication → Supabase Auth:** `API.md` states plainly, "Auth: None in v0.6" — confirmed still true in the running code (no login route, no session-scoped identity anywhere in `routes/`). This is the single largest capability gap between the current build and the frozen architecture.
- **In-memory conversation cache (`state.py`) → Postgres-backed `ai_conversations`/`ai_messages`:** `PROJECT_STATUS.md` itself documents `history_cache: dict[int, list]` as an in-process cache — structurally incompatible with a horizontally-scaled, stateless Render tier (`PLATFORM_ARCHITECTURE.md` §20).
- **Implicit single-tenant data model → explicit multi-tenant model:** every table today implicitly belongs to "the one deployment"; none carry `company_id`, none are RLS-protected, and Equipment is project-owned rather than company-owned (`FOUNDATION_ARCHITECTURE.md` §2.2 vs. `PLATFORM_ARCHITECTURE.md` §10 / `PA-013`).
- **Five overlapping document-output tables (`kb_documents`, `generated_documents`, `qms_documents`, plus URS/Qualification/Report outputs) → one unified `documents` engine** (`DATABASE_ARCHITECTURE.md` §4.4, `DB-002`).

### 1.4 Technical debt, found by direct inspection

- **`check/`** at the repo root is a stray, fully-materialized Python virtual environment (`pyvenv.cfg`, `Lib/`, `Scripts/`, `Include/`) — not referenced by any launch config or documentation. Recommended for deletion as ordinary repo hygiene; out of migration scope, called out here so it isn't mistaken for a real module during the migration.
- **`hello.py`** at the repo root is explicitly marked "DO NOT MODIFY — original proof-of-concept" and is not imported by `pharmagpt/app.py`. It stays exactly as-is, untouched, as a historical artifact — not part of any phase below.
- **Documentation drift:** `API.md`'s auth note ("planned for v0.9") and `PROJECT_STATUS.md`'s folder listing both undersell the current build relative to what's actually in the repository (the URS/Qualification/Risk/Report suites and the multi-engine extraction pipeline are real, tested, shipped code not reflected in either document's summary tables). This roadmap is grounded in the actual file tree, not in those summaries.
- **No migration framework.** `DATABASE.md` already documents this: schema changes today mean deleting `pharmagpt.db` and calling `init_db()` again. This is explicitly retired starting in Phase 3 (`PLATFORM_ARCHITECTURE.md` §5, §20).
- **No CI-enforced test gate.** The 148+ tests exist and pass locally but nothing in the repository enforces they pass before merge — addressed in Phase 1 alongside the rest of the infrastructure and CI/CD groundwork.

---

## 2. Migration Principles

1. **Zero unnecessary rewrites.** Any module that is not tenancy-coupled, storage-coupled, or schema-coupled ships forward with the smallest possible change — often none. §1.2 names the concrete, substantial body of code (prompts, extraction pipeline, document generation/export, review engine, job runner) this principle protects. Rewriting working, tested logic for its own sake is treated as a defect in the plan, not diligence.
2. **Preserve working functionality.** The 148+ existing tests are the migration's regression contract (`IMP-009`). A phase is not complete if it breaks a previously-passing test, even one that looks unrelated to that phase's stated objective.
3. **Incremental migration.** Twelve phases (§3), each independently shippable to Staging and independently verifiable, rather than one large rewrite. This mirrors `DATABASE_ARCHITECTURE.md` §19's three-phase SQLite → PostgreSQL → Supabase migration strategy, extended to the full application, and `PLATFORM_ARCHITECTURE.md` §27's "migrations are additive-first" development standard.
4. **Rollback strategy, per phase and overall.** Every phase in §4 states its own rollback plan. Structurally, this is achieved by: feature-flagging new code paths behind old ones during each phase's transition window (`IMP-008`); never dropping a source-of-truth table or column until the data it fed has been validated in the new shape (e.g., `equipment.project_id` retained temporarily, `IMP-004`); and keeping the SQLite database and local `uploads/` directory read-only and intact until Production cutover (Phase 12) is confirmed stable, exactly as `DATABASE_ARCHITECTURE.md` §19.3 specifies.

---

## 3. Migration Phases

| Phase | Name | One-line objective |
|---|---|---|
| 1 | Infrastructure | Stand up Supabase (Postgres + Storage + Auth) and Staging/Production environments; no business-logic change yet. |
| 2 | Authentication | Replace "no auth" with Supabase Auth, `users`/`roles`/`companies`, and the tenant-context resolver. |
| 3 | Database Migration | Apply the full target schema, enable RLS, migrate existing SQLite data. |
| 4 | Supabase Storage | Move file storage from local disk to Supabase Storage. |
| 5 | Knowledge Base Migration | Consolidate `kb_documents` into the unified `documents` engine. |
| 6 | Equipment Library | Re-parent Equipment from Project-owned to Company-owned; introduce `equipment_links`. |
| 7 | Project Workspace | Add `project_members`; resolve the disclosed "not project-filtered" limitation for Risk/URS/Qualification/Validation Report. |
| 8 | AI Engine | Introduce `ai_conversations`/`ai_messages`/`ai_jobs`/`ai_usage_ledger`; retire the in-memory chat cache. |
| 9 | Document Engine | Consolidate `generated_documents`, `qms_documents`, and URS/Qualification/Report outputs into the unified lifecycle-governed `documents` engine. |
| 10 | Validation | Architecture-conformance pass: confirm the running system matches every `PA-###`/`DB-###` decision. |
| 11 | Testing | Full testing pyramid against the migrated system. |
| 12 | Production Deployment | Cut production traffic over; retire SQLite/local-disk paths. |

Dependency shape: Phases 1→2→3 are strictly sequential (each is a prerequisite for the next). Phases 4–9 depend on Phase 3 and, in some cases, on each other as noted in §4 — Phase 6 depends on Phase 5, Phase 7 depends on Phase 6, Phase 9 depends on Phases 5 and 8. Phase 10 requires Phases 1–9 substantially complete. Phase 11 requires Phase 10. Phase 12 requires Phase 11 sign-off.

---

## 4. Detailed Task Breakdown

### Phase 1 — Infrastructure

- **Objective:** Provision Supabase (Postgres + Storage + Auth) for Staging and Production, add the base connection/configuration layer, and establish a CI test gate — all without touching business logic or cutting over any data path.
- **Files affected:** `config.py` (**modify** — add Supabase connection settings), new `pharmagpt/supabase_client.py` (**new**), `requirements.txt` (**modify** — add a Postgres driver/Supabase SDK and a JWT verification library), `render.yaml` / `Procfile` (**modify** — prepared but not yet activated), `.env.example` (**modify**).
- **Database impact:** None on existing data. An empty Supabase Postgres project is created for Staging and, separately, for Production; the target schema is not yet applied (that is Phase 3).
- **Risk:** Low–Medium. Mostly configuration and plumbing; the real risk is environment confusion (Staging credentials leaking into Production config or vice versa).
- **Dependencies:** None — first phase.
- **Estimated effort:** Small (2–3 dev-days).
- **Success criteria:** The application boots and can execute a trivial health-check query against Supabase Postgres in both Staging and Production projects; secrets are never committed to source control; CI runs the existing pytest suite on every PR.
- **Rollback plan:** Trivial — this phase makes no code path switch to the new infrastructure yet. Reverting config/env changes leaves the application running exactly as it does today, against SQLite.

### Phase 2 — Authentication

- **Objective:** Implement Supabase Auth-backed sessions, the `companies`/`users`/`roles`/`company_settings`/`break_glass_access` tables (`DATABASE_ARCHITECTURE.md` §4.1), the JWT-claim-based tenant-context resolver, and the Super Admin bootstrap flow that creates the first Company and Company Admin.
- **Files affected:** `app.py` (**modify** — register auth middleware), new `pharmagpt/auth/` module (**new** — JWT verification, tenant-context resolver), new `routes/auth.py` (**new**), `templates/index.html` (**modify** — add login shell), new `static/js/auth.js` (**new**).
- **Database impact:** First real application of the target schema, but scoped only to identity/tenancy tables — `companies`, `users`, `roles`, `company_settings`, `break_glass_access`. No existing business data is touched or migrated yet.
- **Risk:** High. Authentication and tenant-context resolution are the foundation every subsequent phase's RLS and authorization depends on; `PLATFORM_ARCHITECTURE.md` §27 mandates second-engineer review on every PR touching this area, without exception, starting here.
- **Dependencies:** Phase 1.
- **Estimated effort:** Large (5–8 dev-days).
- **Success criteria:** A Super Admin can log in and create a Company and its first Company Admin; the Company Admin can log in; unauthenticated requests to any route are rejected; the four roles (`DATABASE_ARCHITECTURE.md` §4.1) are seeded and enforced by the `users.role_id` check constraint pairing role with nullable `company_id`.
- **Rollback plan:** Auth is feature-flagged; while the flag is off, the application continues serving the current no-auth, single-tenant behavior in Staging for continued testing of unrelated work. No Production cutover has occurred yet at this phase.

### Phase 3 — Database Migration

- **Objective:** Apply the complete target Postgres schema (every table in `DATABASE_ARCHITECTURE.md` §4) to Supabase, activate the RLS policy set (§13 of that document), and migrate all existing SQLite data using the table mapping already defined in `DATABASE_ARCHITECTURE.md` §19.2.
- **Files affected:** `database.py` (**replace**, split into per-domain modules matching the target schema), `equipment_database.py` / `qms_database.py` and siblings / `qual_database.py` / `report_database.py` / `risk_database.py` / `urs_database.py` (**modify** — re-pointed at Postgres, `company_id` added), new `migrations/` directory (**new**), every file under `routes/` (**modify** — swap SQLite calls for the new data-access layer).
- **Database impact:** The largest single database event in the migration. Full schema creation; RLS activation; one-time data migration creating a bootstrap company (`IMP-007`) and backfilling `company_id` across every migrated row; consolidation of `kb_documents` + `generated_documents` into `documents`/`document_versions`; generalization of `qms_audit_trail`/`qms_attachments`/`qms_comments`/`qms_approvals` into the platform-wide `audit_trail`/`attachments`/`comments`/`approvals` tables (`DB-004`). Full sequencing is in §7.
- **Risk:** Critical. An RLS misconfiguration here is the platform's one zero-tolerance failure category (`PLATFORM_ARCHITECTURE.md` §27); a data migration error here is silent, cumulative, and expensive to discover later.
- **Dependencies:** Phase 2 (migrated data must be assignable to a real company and users).
- **Estimated effort:** X-Large (10–15 dev-days).
- **Success criteria:** Every row from the current SQLite database has a verified, row-count-reconciled counterpart in Postgres under the bootstrap company; a manual two-company RLS isolation test (create a second, empty company; confirm it returns zero rows for any query) passes; the full existing test suite passes against the new data layer in Staging.
- **Rollback plan:** `pharmagpt.db` is kept untouched and read-only throughout this phase. Production traffic is not cut over until the full Staging validation sequence in `DATABASE_ARCHITECTURE.md` §19.1/§19.3 is complete — this phase's work is entirely a Staging-side activity until Phase 12.

### Phase 4 — Supabase Storage

- **Objective:** Move all file storage from local disk (`uploads/`) to Supabase Storage private buckets, following the `{company_id}/{domain}/{record_id}/{version_or_filename}` path convention (`DATABASE_ARCHITECTURE.md` §16).
- **Files affected:** `documents.py` (**replace** with a Storage client wrapper), `doc_exporter.py` and any service touching local file paths (**modify**), file-serving/download routes across `routes/` (**modify** to issue signed URLs instead of serving from disk).
- **Database impact:** `documents`, `document_versions`, and `attachments` `storage_path` columns backfilled to the new Storage paths; content from `uploads/1`, `uploads/kb`, `uploads/qms` uploaded to Storage with checksum verification before any local copy is treated as retired.
- **Risk:** Medium — file-content integrity during transfer, and broken download links if path-rewriting has bugs.
- **Dependencies:** Phase 3 (document/attachment rows must exist to attach storage paths to).
- **Estimated effort:** Medium (4–6 dev-days).
- **Success criteria:** Every file previously reachable via local disk is reachable via a signed Supabase Storage URL, with matching checksum; no remaining code path reads or writes local `uploads/`.
- **Rollback plan:** The local `uploads/` directory is retained, untouched, and read-only until Storage migration is verified in full; a feature flag can route file reads back to local disk if a Storage-specific issue surfaces post-cutover.

### Phase 5 — Knowledge Base Migration

- **Objective:** Consolidate `kb_documents` into the unified `documents` table (`source_context = 'knowledge_base'`, `DB-002`), and wire the citation/reference model (`document_references`) and folder taxonomy (`document_categories`, `tags`/`document_tags`).
- **Files affected:** `routes/knowledge_base.py` (**modify**, folding toward the unified document routes), `static/js/knowledge_base.js` (**modify** for the new API shape).
- **Database impact:** `kb_documents` rows migrated into `documents` + `document_versions`; existing free-text folder/tag values normalized into `document_categories`/`tags`/`document_tags`.
- **Risk:** Medium — citation-pinning (`DATABASE_ARCHITECTURE.md` §7) is genuinely new behavior; the already-working KB browse/search UX must not regress.
- **Dependencies:** Phase 3, Phase 4.
- **Estimated effort:** Medium (4–6 dev-days).
- **Success criteria:** Every existing KB document remains browsable, searchable, and downloadable exactly as before; a manual test — cite a KB document from a Project document, then revise the KB document, then confirm the citation shows as stale — passes.
- **Rollback plan:** The unified-documents KB path ships behind a feature flag until parity with the current `kb_documents`-backed UI is confirmed in Staging.

### Phase 6 — Equipment Library

- **Objective:** Re-parent Equipment from `project_id`-owned to `company_id`-owned (`PA-013`/`DB-003`), introduce `equipment_links`, and generalize the current build's `equipment_documents` table into it.
- **Files affected:** `equipment_database.py` (**modify**, heavily), `routes/equipment.py` (**modify**), `services/equipment_service.py` (**modify**), `static/js/equipment.js` (**modify**); `equipment/profiles/*` (**keep**, entirely unaffected — the static reference catalog per `FOUNDATION_ARCHITECTURE.md` §2.2).
- **Database impact:** Every `equipment` row's `company_id` resolved from its current `project_id`'s owning company and re-parented; `equipment_links` backfilled from `equipment_documents` plus new links connecting each equipment record to every URS/DQ/FAT/SAT/IQ/OQ/PQ document that already concerned it under the old project-owned model.
- **Risk:** High — this is the one genuine structural/behavioral change from the current shipped build (one-to-many becoming many-to-many); a regression here affects every project that references equipment.
- **Dependencies:** Phase 3, Phase 5 (documents must already be migrated so `equipment_links` has something to point at).
- **Estimated effort:** Large (6–9 dev-days).
- **Success criteria:** Every existing equipment record is reachable from the now company-wide Equipment Library; every project that referenced it before migration still shows it correctly; a second, different project can be linked to the same equipment record without duplicating any equipment data.
- **Rollback plan:** `equipment.project_id` is retained as a deprecated, unused column through a transition window rather than dropped immediately (`IMP-004`), so reverting to project-owned behavior is a code change, not a data-recovery exercise, if a late-discovered bug requires it.

### Phase 7 — Project Workspace

- **Objective:** Add `project_members` (real, role-scoped project sharing — currently absent entirely), and resolve `FOUNDATION_ARCHITECTURE.md` §6's disclosed limitation that Risk, URS, Qualification, and Validation Report have no real `project_id` linkage by giving each suite genuine project-filtered data.
- **Files affected:** `routes/projects.py`, `routes/risk.py`, `routes/urs.py`, `routes/qual.py`, `routes/report.py` (**modify**), `static/js/project_workspace.js`, `static/js/projects.js` (**modify**).
- **Database impact:** `project_members` populated — every existing project's current single-implicit-user access becomes an explicit membership row at migration time, with Company Admins retaining implicit company-wide visibility; `risk_assessments` and the URS/Qualification/Report document rows gain real, non-null `project_id` values.
- **Risk:** Medium. This phase closes a disclosed gap rather than risking a working feature — the risk is scope (it touches many routes at once), not regression of something that currently works correctly.
- **Dependencies:** Phase 3, Phase 6.
- **Estimated effort:** Large (6–8 dev-days).
- **Success criteria:** A Project Workspace's Risk/URS/Qualification/Validation Report tabs show genuinely project-filtered content instead of unfiltered suite entry points; a User sees only Projects they're a member of; a Company Admin sees every Project in the company.
- **Rollback plan:** Project-filtering ships behind a per-suite feature flag; if one suite's filtering has bugs, that suite alone reverts to the current unfiltered entry-point behavior without affecting the other three.

### Phase 8 — AI Engine

- **Objective:** Introduce `ai_conversations`, `ai_messages`, `ai_jobs`, and `ai_usage_ledger`; retire the in-memory `history_cache` (`state.py`) in favor of Postgres-backed conversation state; wrap `job_runner.py` as the backing engine for `ai_jobs`.
- **Files affected:** `app.py` (**modify** — remove `history_cache`), `state.py` (**retire**), `services/job_runner.py` (**modify** — audited and adapted for multi-instance/company-scoped correctness), `services/retrieval_engine.py` (**modify**), `routes/chat.py` (**modify**), `static/js/chat.js` (**modify**).
- **Database impact:** `messages` table content migrated into `ai_conversations` + `ai_messages`; every AI call from this phase forward logged to `ai_usage_ledger` with company/user/token attribution.
- **Risk:** Medium. SSE streaming behavior (already a strength of the current build, preserved per `PLATFORM_ARCHITECTURE.md` §19) must not regress; multi-instance correctness genuinely depends on this phase fully removing the in-process cache, not just adding a database alongside it.
- **Dependencies:** Phase 2 (users/companies must exist), Phase 3.
- **Estimated effort:** Medium (5–7 dev-days).
- **Success criteria:** Chat history is correct and complete after a server restart and when two different Render instances alternately serve the same conversation — proving no in-memory dependency remains; every AI call appears in the usage ledger with correct attribution.
- **Rollback plan:** `state.py`'s current cache code path stays available behind a flag until multi-instance correctness is explicitly verified in Staging under a simulated restart/multi-instance test.

### Phase 9 — Document Engine

- **Objective:** Complete the unification of `generated_documents`, `qms_documents`, and the URS/Qualification/Report suites' outputs into the single `documents` + `document_versions` engine, governed by the six-state lifecycle (`PLATFORM_ARCHITECTURE.md` §12), and wire `approvals` for the In Review / QA Review stages.
- **Files affected:** `services/doc_generator.py`, `docx_generator.py`, `doc_exporter.py` (**modify** — re-pointed at the unified engine, logic itself largely unchanged per `IMP-003`), `routes/validation.py`, `routes/urs.py`, `routes/qual.py`, `routes/report.py`, `routes/qms_documents.py` (**modify**/**merge** toward unified document routes), `review/` package (**modify** to persist decisions into the generalized `approvals` table).
- **Database impact:** The single largest consolidation in the migration — `generated_documents`, `qms_documents`, and URS/Qualification/Report output rows all migrated into `documents` + `document_versions`; the current build's `qms_approvals`-equivalent history migrated into the generalized `approvals` table.
- **Risk:** High. This is the platform's core value proposition (AI-generated, lifecycle-governed documents) and the largest single-table consolidation in the plan.
- **Dependencies:** Phase 3, Phase 5, Phase 8.
- **Estimated effort:** X-Large (8–12 dev-days).
- **Success criteria:** Every document type from URS through Validation Report and SOP flows through the same Draft → In Review → QA Review → Approved → Obsolete → Archived lifecycle; a full content-diff of every pre-migration generated/QMS document against its post-migration counterpart shows zero content drift.
- **Rollback plan:** Migrated and content-diff-verified in Staging before Production cutover; the source tables (`generated_documents`, `qms_documents`, and the suite-specific output tables) are kept read-only for a defined post-cutover window (§14).

### Phase 10 — Validation

- **Objective:** An architecture-conformance pass — walk every `PA-###` decision in `PLATFORM_ARCHITECTURE.md` and every `DB-###` decision in `DATABASE_ARCHITECTURE.md` against the running Staging system and confirm each one is actually true of the implementation, not merely intended. Distinct from Phase 11's testing pyramid — see `IMP-010`.
- **Files affected:** None by default; any conformance gap found here produces a fix commit in whichever file the gap traces back to.
- **Database impact:** None beyond fixes surfaced by the pass.
- **Risk:** Medium — the risk this phase exists to catch is a system that passes its own tests while having quietly drifted from the frozen architecture (e.g., an RLS policy that technically isolates tenants but not in the way `PA-002` actually specified).
- **Dependencies:** Phases 1–9 substantially complete.
- **Estimated effort:** Medium (5–7 dev-days).
- **Success criteria:** Every `PA-###` and `DB-###` decision has a recorded conformance check against the running system; every `FOUNDATION_ARCHITECTURE.md` §6 disclosed limitation is confirmed either genuinely resolved (Phase 7) or still deliberately deferred per the frozen roadmap — never accidentally still broken and undocumented.
- **Rollback plan:** Not applicable — a verification phase produces fixes, not a data or deployment rollback.

### Phase 11 — Testing

- **Objective:** Execute the full testing pyramid — Unit, Integration, System, User Acceptance, Performance, Security (§9) — against the fully migrated Staging system.
- **Files affected:** `tests/` (**modify**/**extend** heavily — `conftest.py` rewritten for Postgres/multi-tenant fixtures), new test modules per domain added alongside the existing 148+.
- **Database impact:** A dedicated, isolated test Supabase project/schema — never Staging or Production.
- **Risk:** Low in isolation (this phase exists specifically to reduce risk elsewhere), but a compressed or shortened Phase 11 is itself flagged as a top migration risk (§12).
- **Dependencies:** Phases 1–10.
- **Estimated effort:** Large (8–10 dev-days).
- **Success criteria:** 100% of the pre-migration 148+ test suite passes against the new stack (adapted, per `IMP-009`, not skipped); new tenant-isolation and RLS-specific tests pass; a documented multi-tenant load test (§9) completes within the latency targets in `PLATFORM_ARCHITECTURE.md` §27.
- **Rollback plan:** Not applicable — a failing test blocks progression to Phase 12; it does not trigger a data rollback on its own.

### Phase 12 — Production Deployment

- **Objective:** Cut production traffic over from the current SQLite/local-disk deployment to the Supabase-backed multi-tenant deployment.
- **Files affected:** `render.yaml` / `Procfile` (**modify** — final production configuration, mounted disk and `DB_PATH` removed, Supabase environment variables added), deploy target/DNS.
- **Database impact:** The final production data migration run — a repeat, against live production data, of the exact procedure already validated in Phase 3/Staging, executed during a defined maintenance window; `pharmagpt.db` retained read-only per `DATABASE_ARCHITECTURE.md` §19.3.
- **Risk:** Critical — a production cutover, by nature difficult to reverse quickly once customer traffic depends on the new path.
- **Dependencies:** All prior phases; explicit Phase 11 sign-off.
- **Estimated effort:** Small–Medium (2–4 dev-days, dominated by runbook execution and a post-cutover monitoring window rather than new development).
- **Success criteria:** 100% of production traffic served from Supabase; no code path reads or writes SQLite/local disk; the post-cutover monitoring window shows zero tenant-isolation or data-integrity incidents.
- **Rollback plan:** A defined, written rollback runbook reverting the deploy target and DNS to the last-known-good SQLite-backed release, rehearsed at least once as a Staging drill before Production cutover is attempted — mirroring the restore-drill requirement in `DATABASE_ARCHITECTURE.md` §18.

---

## 5. Existing Modules

| Module | Current purpose | Disposition | Why |
|---|---|---|---|
| `app.py` | Flask entrypoint, route registration, Gemini client, SSE chat | **Modify** | Add auth middleware, tenant-context resolver, remove `history_cache` (Phase 2, Phase 8) |
| `config.py` | Env var loading | **Modify** | Add Supabase connection settings (Phase 1) |
| `database.py` | SQLite schema + CRUD for projects/messages/documents/kb_documents/generated_documents | **Replace** | SQLite-specific, no `company_id`; split into per-domain Postgres modules (Phase 3) |
| `documents.py` | Local filesystem file helpers | **Replace** | Incompatible with Storage strategy (Phase 4) |
| `equipment_database.py` | Equipment CRUD, project-owned | **Modify**, heavily | Re-parent to company-owned (Phase 6) |
| `qms_database.py` + 4 siblings | QMS domain + shared polymorphic tables | **Modify** | Add `company_id`; generalize shared tables (Phase 3, Phase 9) |
| `qual_database.py`, `report_database.py`, `urs_database.py` | Qualification/Report/URS suite CRUD | **Modify → folds into unified engine** | These record types are Documents per `DATABASE_ARCHITECTURE.md` §4.4 (Phase 9) |
| `risk_database.py` | Risk Assessment CRUD | **Modify** | Stays a distinct structured table per `DATABASE_ARCHITECTURE.md` §4.7 (`IMP-006`); gains `company_id` and real `project_id` (Phase 7) |
| `state.py` | In-memory chat history cache | **Retire** | Structurally incompatible with a stateless, horizontally-scaled tier (Phase 8) |
| `logging_config.py` | Logging setup | **Keep**, minor modify | Infrastructure-agnostic; may gain tenant-aware structured fields |
| `hello.py` | Original CLI proof-of-concept | **Keep, untouched** | Explicitly marked do-not-modify; not imported by the app |
| `routes/*.py` (all 16 files) | Flask blueprints | **Modify** | Add auth/tenant-context, swap data-access calls (all phases, per domain) |
| `services/doc_exporter.py`, `doc_generator.py`, `docx_generator.py`, `docx_reader.py`, `excel_reader.py` | Document generation/export/read | **Keep**, re-point I/O only | Not tenancy- or storage-coupled logic (`IMP-003`) |
| `services/document_processor.py`, `document_search.py` | Processing orchestration, keyword search | **Modify** | `document_search.py` becomes an input to `search_index` (Phase 3, later feeds `PLATFORM_ARCHITECTURE.md` §14) |
| `services/extraction/*` (6 files) | Multi-engine PDF/text extraction pipeline | **Keep**, near-unchanged | Pure processing logic, storage-agnostic (`IMP-003`) |
| `services/equipment_service.py` | Equipment business logic | **Modify** | Company-scoped, feeds `equipment_links` (Phase 6) |
| `services/job_runner.py` | Async job abstraction | **Keep**, audited | Becomes the backing engine for `ai_jobs` (`IMP-002`, Phase 8) |
| `services/retrieval_engine.py` | RAG retrieval | **Modify** | Becomes the AI Engine's retrieval service, later feeds Global Search semantic mode (Phase 8) |
| `services/qms_*_service.py` (4 files), `qual_service.py`, `report_service.py`, `risk_service.py`, `urs_service.py` | Domain business logic | **Modify** | Company scoping, data-access layer swap (Phase 3, Phase 9) |
| `services/urs_generation_job.py`, `urs_requirement_library.py` | URS-specific generation support | **Keep**, minor modify | Domain logic, not tenancy-coupled |
| `prompts/*` (20 files) | Pharmaceutical-domain prompt templates | **Keep**, unchanged | Pure prompt logic, zero tenancy/storage coupling (`IMP-003`) |
| `review/*` (4 files) | Review workflow engine | **Modify**, lightly | Persist decisions into the generalized `approvals` table (Phase 9) |
| `equipment/profiles/*` (7 files) | Static equipment-type reference catalog | **Keep**, unchanged | Explicitly unrelated to the Equipment entity per `FOUNDATION_ARCHITECTURE.md` §2.2 |
| `static/js/*` (21 files) | Frontend | **Modify**, per-domain | New API contracts, auth headers, company scoping (per phase) |
| `templates/index.html` | SPA shell | **Modify** | Add auth/login shell, company context (Phase 2) |
| `uploads/` (`1/`, `kb/`, `qms/`) | Local file storage | **Retire** | Migrated to Supabase Storage (Phase 4) |
| `tests/*` | Test suite (148+ tests) | **Modify**/**extend** | New fixtures (Postgres, multi-tenant), new test categories (Phase 11) |
| `render.yaml`, `Procfile` | Deployment config | **Modify** | Remove disk mount/`DB_PATH`, add Supabase env vars (Phase 1, finalized Phase 12) |
| `check/` (stray venv) | None — leftover artifact | **Delete** | Repo hygiene, out of migration scope (§1.4) |

---

## 6. Folder-by-Folder Migration

| Folder | Disposition | Notes |
|---|---|---|
| `pharmagpt/` (root package files) | **Refactor** | Domain database modules split/replaced per §5; `app.py`/`config.py` modified |
| `pharmagpt/routes/` | **Keep**, refactor contents | Blueprint-per-domain structure already matches `PLATFORM_ARCHITECTURE.md` §21's target shape — structure survives, contents change |
| `pharmagpt/services/` | **Keep**, refactor contents | Same — the domain-module folder structure is already correct |
| `pharmagpt/services/extraction/` | **Keep**, unchanged | §1.2, `IMP-003` |
| `pharmagpt/prompts/` | **Keep**, unchanged | §1.2, `IMP-003` |
| `pharmagpt/review/` | **Keep**, refactor contents | Light modification only (Phase 9) |
| `pharmagpt/equipment/` (module) | **Rename** → `pharmagpt/equipment_library/` (routes/business logic only) | Matches `PLATFORM_ARCHITECTURE.md` §21's target folder name for the company-wide domain |
| `pharmagpt/equipment/profiles/` | **Keep**, unchanged, un-renamed | Static reference catalog, explicitly separate from the Equipment Library entity — stays exactly where and what it is |
| `pharmagpt/static/` | **Keep**, refactor JS contents | Structure survives; individual files modified per phase |
| `pharmagpt/templates/` | **Keep**, refactor contents | Single SPA shell modified for auth (Phase 2) |
| `pharmagpt/uploads/` | **Delete**, after Phase 4 verification | Superseded entirely by Supabase Storage |
| `tests/` | **Keep**, refactor + extend | Mirrors the domain structure 1:1 per `PLATFORM_ARCHITECTURE.md` §21/§30; fixtures rewritten (Phase 11) |
| `docs/` | **Keep**, unchanged by this migration | This document family; unaffected by code changes |
| `PROJECT_MEMORY/` | **Keep**, unchanged | Historical decision record, not part of the running application |
| `check/` | **Delete** | Stray venv, no functional role (§1.4) |
| `venv/` | **Keep**, local-only | Ordinary local dev environment, regenerated as needed, not migration-relevant |
| New: `pharmagpt/auth/` | **New** | Phase 2 |
| New: `pharmagpt/integrations/` | **New**, created empty | Reserved per `PLATFORM_ARCHITECTURE.md` §21/§25 — no code ships in it during this migration; the folder exists so the first real integration has a pre-agreed home later |
| New: `migrations/` | **New** | Phase 3, reviewed schema-change history going forward |

---

## 7. Database Migration Sequence

### 7.1 Table creation order (respecting foreign-key dependency)

1. `companies`
2. `roles` (seeded with the four fixed rows)
3. `users` (depends on `companies`, `roles`)
4. `company_settings`, `break_glass_access` (depend on `companies`, `users`)
5. `projects` (depends on `companies`)
6. `project_members` (depends on `projects`, `users`)
7. `equipment` (depends on `companies`)
8. `document_categories`, `tags` (depend on `companies`)
9. `documents` (depends on `companies`, `projects` nullable, `document_categories`)
10. `document_versions`, `document_tags` (depend on `documents`)
11. `document_references` (depends on `documents`, `document_versions`)
12. `equipment_links` (depends on `equipment`; polymorphic reference to `documents`/QMS tables)
13. `deviations`, `capas`, `change_controls`, `risk_assessments` (depend on `companies`, `projects` nullable)
14. `audit_trail`, `attachments`, `comments`, `approvals` (polymorphic — no hard FK dependency, but created after the tables they will most commonly reference, for review clarity)
15. `ai_conversations` (depends on `companies`, `projects` nullable, `users`)
16. `ai_messages`, `ai_jobs`, `ai_usage_ledger` (depend on `ai_conversations`/`companies`/`users`)
17. `notifications` (depends on `companies`, `users`)
18. `search_index` (derived; created last among active v1.0 tables since it is populated from every table above)
19. Reserved tables (§21 of `DATABASE_ARCHITECTURE.md`): `permissions`, `role_permissions`, `calibration_records`, `preventive_maintenance_records`, `spare_parts`, `signature_events`, `data_retention_policies`, `integration_configs`, `api_keys`, `subscriptions`, `plans`, `invoices` — schema created, left empty, no code path touches them (Phase 3, but logically last)

### 7.2 Data migration order

1. Bootstrap company created (`IMP-007`).
2. Existing users/operators provisioned as `users` rows under the bootstrap company (Phase 2 groundwork, executed for real in Phase 3).
3. `projects` migrated, `company_id` backfilled.
4. `equipment` migrated and re-parented to `company_id`; `project_id` retained temporarily (`IMP-004`) (Phase 6, though schema-created in Phase 3).
5. `kb_documents` migrated into `documents`/`document_versions` (Phase 5).
6. `generated_documents`, `qms_documents`, and URS/Qualification/Report outputs migrated into `documents`/`document_versions` (Phase 9).
7. `equipment_documents` migrated into `equipment_links`, extended with links to the newly-migrated documents (Phase 6/9 coordination point).
8. `deviations`, `capas`, `change_controls`, `risk_assessments` migrated with `company_id` backfilled and existing `project_id` preserved (nullable, `SET NULL`-governed per `DATABASE_ARCHITECTURE.md` §5.3).
9. `qms_audit_trail`/`qms_attachments`/`qms_comments`/`qms_approvals` history migrated into the generalized `audit_trail`/`attachments`/`comments`/`approvals` tables.
10. `messages` migrated into `ai_conversations`/`ai_messages` (Phase 8).
11. `search_index` built from every table above, last.

### 7.3 Validation checkpoints

A row-count reconciliation and a spot-check sample (minimum 5% or 50 rows, whichever is larger, per migrated table) run after **every** numbered step above, before the next step begins — not only at the end of the whole sequence. After step 3 (Projects) and after step 6 (Document Engine consolidation), an additional full RLS isolation test runs (create a second, empty company; confirm zero cross-visibility) before continuing, since these are the two points where the largest volume of regulator-relevant data has just become newly tenant-scoped.

---

## 8. API Migration Plan

### 8.1 Existing endpoints (as of `API.md` and direct route inspection)

Core (`/`), Projects (`/projects`, `/projects/<id>`, `/projects/<id>/messages`), Chat (`/stream`, `/clear`), Documents (`/projects/<id>/documents`, `/documents/<id>/view`, `/documents/<id>/download`, `/projects/<id>/insights`), Validation (`/validation/generate`, `/validation/export/docx`, `/validation/save`, `/projects/<id>/generated-docs`), Knowledge Base (`/kb/documents/*`, `/kb/folders/counts`), plus the QMS, URS, Qualification, Risk, and Validation Report route groups confirmed present in `routes/` but not fully documented in `API.md`.

### 8.2 New endpoints required

Authentication (`/auth/login`, `/auth/logout`, session/JWT refresh), Company administration (`/companies` — Super Admin only; `/companies/<id>/users`, `/companies/<id>/settings`), Equipment Library at company scope (`/equipment` replacing the current project-scoped shape), unified Document Engine endpoints (`/documents`, `/documents/<id>/versions`, `/documents/<id>/approvals` — replacing the separate KB/generated-docs/QMS-docs endpoint families), Global Search (`/search`), AI Usage (`/companies/<id>/ai-usage`), Project membership (`/projects/<id>/members`).

### 8.3 Deprecated endpoints

`/kb/documents/*` (replaced by the unified `/documents` family, `source_context=knowledge_base`), `/projects/<id>/generated-docs` (replaced by `/documents?project_id=...`), the project-scoped equipment routes (replaced by company-scoped `/equipment` plus `equipment_links` filtering by project).

### 8.4 Compatibility strategy

All new and migrated endpoints ship under a versioned prefix, `/api/v1/...`, per `PLATFORM_ARCHITECTURE.md` §19. Because this is a monolith where frontend and backend deploy together (not an independently-versioned public API with third-party consumers at v1.0), deprecated endpoints are **not** maintained indefinitely in parallel — each is retired in the same phase that ships its replacement, with the old route returning a clear `410 Gone`-style deprecation response for one release cycle before removal, giving any missed frontend call site an obvious, loud failure during Staging testing rather than a silent one.

---

## 9. Testing Strategy

| Level | Scope | Approach |
|---|---|---|
| **Unit** | Individual functions/services — prompt builders, extraction engines, document generators, RLS-adjacent helper logic | Extends the existing 148+ test baseline; new tests required for every new/modified data-access function per phase |
| **Integration** | Route ↔ service ↔ database, within one domain | Per-phase — e.g., Phase 6's equipment re-parenting tested against a seeded multi-project, single-equipment scenario |
| **System** | End-to-end flows spanning multiple domains (e.g., generate a URS, cite it from an IQ, route the IQ through In Review → QA Review → Approved) | Primarily exercised in Phase 10 (Validation) and Phase 11 |
| **User Acceptance** | Real validation-engineer and QA-reviewer workflows, walked against Staging by non-engineering stakeholders | Scheduled at the end of Phase 11, before Phase 12 sign-off |
| **Performance** | Multi-tenant concurrency load test, per `PLATFORM_ARCHITECTURE.md` §25/§27 — many tenants concurrently, not one large tenant in isolation | Executed in Phase 11 against a dedicated test Supabase project seeded with realistic multi-tenant data volume |
| **Security** | RLS isolation (every table), authentication/session handling, signed-URL expiry behavior, break-glass access logging | A dedicated pass within Phase 11, plus the two mandatory RLS checkpoints already called out in §7.3 |

Every level above must pass in Staging before Phase 12; none are optional or "best effort" per `IMP-009`.

---

## 10. Deployment Strategy

Three environments, exactly as `PLATFORM_ARCHITECTURE.md` §20 specifies, made concrete against the tooling already in the repository:

- **Development:** Local, individual developer machines, against either a local Postgres instance or a shared Development Supabase project — never against Staging or Production credentials.
- **Staging:** A real, isolated Supabase project, standing up starting in Phase 1, used for every phase's validation work (§4) and for the pre-cutover migration dry-run in Phase 3/Phase 12.
- **Production:** The current Render web service (`render.yaml`), re-pointed from the mounted-disk/SQLite configuration to Supabase in Phase 12, with the mounted disk and `DB_PATH` removed once cutover is confirmed stable.

CI (introduced in Phase 1) runs the full test suite on every PR targeting any branch that deploys to Staging or Production; no phase's code merges without it passing.

---

## 11. Release Strategy

| Release | Contents |
|---|---|
| **v1.0** | The full output of this roadmap's twelve phases — multi-tenant SaaS foundation, exactly as scoped in `PLATFORM_ARCHITECTURE.md` §32/`PA-###` and `DATABASE_ARCHITECTURE.md` §24/`DB-###`. Nothing in `PLATFORM_ARCHITECTURE.md` §31 (Out of Scope) ships in this release. |
| **v1.1** | Per `PLATFORM_ARCHITECTURE.md` §32: cryptographic e-signatures, data-retention/archival automation, semantic search, enforced AI usage limits, Calibration/Preventive Maintenance modules — each building additively on the reserved tables this roadmap's phases created empty (§21 of `DATABASE_ARCHITECTURE.md`) but did not populate. |
| **v1.2** | SSO/SAML federation, billing/plan-tier enforcement, granular permission roles, first real integration adapters — built against the `integrations/` folder and `api_keys`/`integration_configs` tables this roadmap reserved but did not activate. |
| **Future** | Per `PLATFORM_ARCHITECTURE.md` §32 exploratory list — mobile applications, multi-region, dedicated search infrastructure, AI Engine service extraction — none of which this roadmap's twelve phases touch. |

This roadmap's scope is v1.0 only. Nothing in Phases 1–12 anticipates or partially builds v1.1/v1.2 features beyond leaving the reserved schema surface `DATABASE_ARCHITECTURE.md` §21 already committed to.

---

## 12. Risk Register

### 12.1 Technical risks

| Risk | Phase(s) | Mitigation |
|---|---|---|
| RLS policy gap or error | 2, 3, all | Mandatory second-engineer review (`PLATFORM_ARCHITECTURE.md` §27); two dedicated RLS checkpoints in §7.3; full security pass in Phase 11 |
| Data migration errors (row loss, mis-mapped `company_id`) | 3, 6, 9 | Row-count reconciliation + spot-check after every migration step (§7.3); content-diff verification for Phase 9 specifically |
| `job_runner.py` carrying hidden single-instance assumptions into `ai_jobs` | 8 | Explicit audit step called out in Phase 8's task breakdown before it's trusted as the `ai_jobs` backbone |
| Equipment re-parenting migration ambiguity (a legacy equipment row whose owning project's company can't be unambiguously resolved) | 6 | Flagged for manual review rather than silently defaulted, per `DATABASE_ARCHITECTURE.md` §22's equivalent risk entry |
| Feature-flag sprawl left unresolved after cutover | All | Tracked explicitly in the Final Checklist (§14) — every flag introduced must be either removed (old path deleted) or explicitly re-justified before Phase 12 sign-off |

### 12.2 Business risks

| Risk | Mitigation |
|---|---|
| Migration timeline extends and delays the multi-tenant go-to-market the platform architecture was designed for | Twelve independently-shippable phases mean partial progress is real progress — Staging can demonstrate multi-tenant capability well before Phase 12, even if Phase 12 itself slips |
| Existing (pilot) users experience disruption during Production cutover | A defined, time-boxed maintenance window for Phase 12's final migration run, with a rehearsed rollback runbook, keeps worst-case disruption bounded and reversible |
| Stakeholders assume "migration complete" prematurely, before regulatory-relevant guarantees (audit trail, lifecycle, RLS) are actually verified | Phase 10 (Validation) exists specifically to prevent this — it is a mandatory, separate gate, not folded into Phase 11's general testing |

### 12.3 Migration-specific risks

| Risk | Mitigation |
|---|---|
| SQLite and Supabase drift out of sync if Production cutover (Phase 12) is delayed after Phase 3's data migration is first run | Phase 3's migration is treated as re-runnable against Staging repeatedly; the actual Production data migration is a fresh, final run at Phase 12 time, not a stale copy carried forward |
| A phase's feature flag is quietly left permanently on/off instead of being resolved | Final Checklist (§14) explicitly enumerates every flag introduced across Phases 2–9 by name |
| Compressed Phase 11 testing under schedule pressure | Called out explicitly as a top risk in §4's Phase 11 entry; Phase 12 success criteria require explicit Phase 11 sign-off, not just "tests were run" |

---

## 13. Development Order

The exact sequence developers should build in, matching §3/§4's dependency shape:

1. Phase 1 — Infrastructure (Supabase provisioning, base config, CI gate)
2. Phase 2 — Authentication (identity/tenancy tables, tenant-context resolver)
3. Phase 3 — Database Migration (full schema, RLS, SQLite data migration)
4. Phase 4 — Supabase Storage (file storage cutover)
5. Phase 5 — Knowledge Base Migration (unify `kb_documents`)
6. Phase 6 — Equipment Library (re-parent to company, `equipment_links`) — *requires Phase 5 complete*
7. Phase 7 — Project Workspace (`project_members`, project-filter Risk/URS/Qual/Report) — *requires Phase 6 complete*
8. Phase 8 — AI Engine (conversations, jobs, usage ledger, retire in-memory cache) — *can proceed in parallel with Phases 5–7 once Phase 3 is complete, since it does not depend on Knowledge Base or Equipment*
9. Phase 9 — Document Engine (unify `generated_documents`/`qms_documents`/suite outputs) — *requires Phase 5 and Phase 8 complete*
10. Phase 10 — Validation (architecture-conformance pass)
11. Phase 11 — Testing (full pyramid)
12. Phase 12 — Production Deployment

The one legitimate parallelization opportunity in this sequence is Phase 8 alongside Phases 5–7 — both branches only require Phase 3 as a common ancestor. Every other phase is strictly sequential as listed. A team choosing to parallelize should still merge Phase 8 to the shared Staging environment before starting Phase 9, since Phase 9 depends on it directly.

---

## 14. Final Checklist

Everything required before this migration can be declared complete:

- [ ] All twelve phases' individual success criteria (§4) met and recorded.
- [ ] Every table in `DATABASE_ARCHITECTURE.md` §4 exists in Production with RLS active; every reserved table (§21 of that document) exists, is empty, and is confirmed untouched by any live code path.
- [ ] Row-count reconciliation for every migrated table, Production run, matches the pre-migration SQLite counts exactly (accounting for the documented consolidations in §7.2).
- [ ] Two-company RLS isolation test passes in Production, not just Staging.
- [ ] Every feature flag introduced across Phases 2–9 is explicitly resolved — either removed with its legacy code path deleted, or, if intentionally retained (e.g., `equipment.project_id` per `IMP-004`), tracked with an explicit follow-up owner and removal date.
- [ ] 100% of the pre-migration 148+ test suite passes against Production-equivalent Staging, plus all new tests added during Phases 2–11.
- [ ] Phase 10's full `PA-###`/`DB-###` conformance walk is complete with zero open gaps.
- [ ] No code path reads or writes local disk (`uploads/`) or SQLite (`pharmagpt.db`) — confirmed by code search, not assumption.
- [ ] Production rollback runbook (Phase 12) has been rehearsed at least once in Staging.
- [ ] `render.yaml`/`Procfile` no longer reference a mounted disk or `DB_PATH`.
- [ ] `check/` stray venv removed from the repository.
- [ ] `hello.py` confirmed still untouched and unreferenced (a negative check — nothing in the migration should have needed to touch it).
- [ ] `docs/API.md`, `docs/DATABASE.md` (or their successors), `PROJECT_STATUS.md`, and `ROADMAP.md` updated to reflect the post-migration reality, so the documentation-drift problem noted in §1.4 is not simply recreated in the new architecture.
- [ ] Post-cutover monitoring window (per Phase 12's success criteria) completed with zero tenant-isolation or data-integrity incidents.
- [ ] Explicit sign-off recorded from engineering leadership that the system, as deployed, matches `PLATFORM_ARCHITECTURE.md` and `DATABASE_ARCHITECTURE.md` in full.

---

## 15. Implementation Decision Log

**IMP-001 — Twelve-phase incremental migration, not a single big-bang cutover**
- **Decision:** The migration is sequenced as twelve independently shippable, independently verifiable phases (§3), each with its own rollback plan.
- **Reason:** Matches `PLATFORM_ARCHITECTURE.md` §27's additive-first migration standard and extends `DATABASE_ARCHITECTURE.md` §19's three-phase SQLite → PostgreSQL → Supabase strategy to the whole application, not just the data layer.
- **Trade-offs:** Longer total calendar time than a single rewrite; requires maintaining feature-flagged, dual code paths across multiple phases rather than a clean break.

**IMP-002 — Reuse `job_runner.py` as the `ai_jobs` backing engine**
- **Decision:** The existing async job abstraction is adapted, not replaced, to back the new `ai_jobs` table.
- **Reason:** It is already working, tested infrastructure (`tests/test_job_runner.py`) — Migration Principle "zero unnecessary rewrites" (§2).
- **Trade-offs:** Must be explicitly audited for hidden single-instance/in-memory assumptions before being trusted at multi-tenant, multi-instance scale (§4 Phase 8, §12.1).

**IMP-003 — Prompts, extraction pipeline, document generation/export, and the review engine carry forward with minimal change**
- **Decision:** `prompts/`, `services/extraction/`, `doc_generator.py`/`docx_generator.py`/`doc_exporter.py`/`docx_reader.py`/`excel_reader.py`, and `review/` are re-pointed at new inputs/outputs only, not rewritten.
- **Reason:** None of this logic is tenancy- or storage-coupled; rewriting it would violate the "zero unnecessary rewrites" principle for no architectural benefit.
- **Trade-offs:** None material — the residual risk is complacency, not code quality; Phase 11 still exercises this code end-to-end against the new pipeline rather than assuming it's automatically correct.

**IMP-004 — `equipment.project_id` retained, deprecated, through a transition window**
- **Decision:** Phase 6 does not drop the current build's `project_id` column from `equipment` immediately.
- **Reason:** Gives the highest-risk structural change in the whole migration (§4 Phase 6) a fast, code-only rollback path instead of a data-recovery exercise if bugs surface late.
- **Trade-offs:** A small amount of dead schema persists temporarily; must be tracked to actual removal (§14 Final Checklist) rather than left indefinitely, which would itself become new technical debt.

**IMP-005 — URS, Qualification, and Validation Report outputs consolidated into the unified `documents` engine in the same phase as `generated_documents`/`qms_documents`**
- **Decision:** All of these migrate together in Phase 9, rather than each suite getting its own separate migration phase.
- **Reason:** They are all instances of the same "Documents" unified object model (`DATABASE_ARCHITECTURE.md` §4.4); splitting them into separate phases would mean building, and then discarding, suite-specific interim logic that Phase 9 makes generic anyway.
- **Trade-offs:** Phase 9 becomes the single largest phase in the plan (X-Large effort) — accepted because splitting it would not reduce total risk or effort, only add integration seams between artificially separated phases.

**IMP-006 — Risk Assessment stays a distinct structured table, not folded into `documents`**
- **Decision:** `risk_assessments` remains its own table, parallel to `deviations`/`capas`/`change_controls`, not merged into the unified Document Engine.
- **Reason:** Conformance note, not an independent decision — `DATABASE_ARCHITECTURE.md` §4.7 already drew this line; this roadmap simply implements it faithfully rather than re-opening it.
- **Trade-offs:** None — recorded here purely for traceability, so a future engineer doesn't mistake the absence of Risk Assessment from Phase 9's consolidation list as an oversight.

**IMP-007 — A single bootstrap company receives all pre-migration data**
- **Decision:** Phase 3's data migration creates one company and assigns every existing SQLite row to it.
- **Reason:** The current build has no company concept at all, and its existing data logically belongs to one organization's pilot usage — the simplest, most literal mapping satisfying the new schema's `NOT NULL company_id` constraint.
- **Trade-offs:** If the current build's data actually mixes what should become multiple distinct companies (e.g., fixture/test data representing different fictitious customers), a manual data-triage pass is required before or during Phase 3 rather than assuming the bootstrap-company mapping is always correct.

**IMP-008 — Feature flags gate every phase's new code path behind the old one**
- **Decision:** Every phase in §4 ships its new behavior behind a flag during its transition window, rather than an immediate hard cutover.
- **Reason:** Matches `PLATFORM_ARCHITECTURE.md` §27's "feature flags gate incomplete work" development standard and gives every phase a genuine, low-cost rollback option, satisfying Migration Principle 4 (§2).
- **Trade-offs:** Temporary dual-code-path complexity during each phase's transition window; every flag must be explicitly resolved, not left permanently in place (tracked in §14).

**IMP-009 — The existing 148+ test suite is the migration's regression baseline in full, not "most of it"**
- **Decision:** Every currently-passing test must pass against the new stack before Phase 12; none are quietly dropped as "no longer relevant."
- **Reason:** It is the only concrete, already-agreed definition of "working functionality" (Migration Principle 2, §2) available at the start of this migration; redefining success criteria mid-migration would be scope creep.
- **Trade-offs:** Some existing tests are SQLite-specific and require genuine adaptation, not a mechanical re-run — this adaptation work is counted explicitly in Phase 11's effort estimate, not treated as free.

**IMP-010 — Architecture Conformance Validation (Phase 10) is distinct from and precedes Testing (Phase 11)**
- **Decision:** Phase 10 checks the running system against every `PA-###`/`DB-###` decision; Phase 11 runs the standard testing pyramid. These are two separate phases, in that order.
- **Reason:** Phase 10 answers "does this match the frozen architecture," Phase 11 answers "does this behave correctly" — conflating them risks a system that passes its own tests while having quietly drifted from what `PLATFORM_ARCHITECTURE.md`/`DATABASE_ARCHITECTURE.md` actually decided.
- **Trade-offs:** Some effort overlap between the two phases, since both touch the same running system — accepted because the distinct question each one answers is worth the modest duplication.

---

*This document is the frozen implementation roadmap for migrating PharmaGPT to the multi-tenant Supabase architecture defined in `PLATFORM_ARCHITECTURE.md` and `DATABASE_ARCHITECTURE.md`. Any future change to a decision in §15 requires a new, explicitly numbered entry — superseding, not silently editing, the original — matching the discipline both governing documents already established.*

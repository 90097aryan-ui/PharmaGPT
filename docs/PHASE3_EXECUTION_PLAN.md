# Phase 3 Execution Plan

**Status:** Execution checklist only — not an architecture document. Nothing here redesigns or reinterprets `PLATFORM_ARCHITECTURE.md`, `DATABASE_ARCHITECTURE.md`, or `IMPLEMENTATION_ROADMAP.md` (all frozen, unmodified). **Baseline:** tag `phase2-auth-complete`.

**Sequencing note:** this plan re-sequences the frozen roadmap's Phase 3 (Database Migration), Phase 5 (Knowledge Base), Phase 6 (Equipment), and the QMS portion of Phase 9 into six incremental, dual-running sub-phases (3.1–3.6) instead of the roadmap's single big-bang Phase 3/12 cutover. End-state schema, RLS, and relationships are exactly `DATABASE_ARCHITECTURE.md` §4 — only execution order and the dual-write transition strategy are new, per Migration Principles 3–4 (roadmap §2) and `IMP-008`.

## 1. Milestones

### 3.1 PostgreSQL Data Layer
- **Objective:** Stand up the full target Postgres schema (`DATABASE_ARCHITECTURE.md` §4) in Supabase, RLS enabled default-deny; add a backend-selection seam. SQLite untouched, zero route changes.
- **Files:** `migrations/0004_core_schema_up.sql` / `_down.sql` (new); `pharmagpt/config.py` (+`DATABASE_BACKEND` flag); `pharmagpt/db/__init__.py`, `pharmagpt/db/backend.py` (new).
- **DB impact:** 24 new empty tables + indexes in Supabase. Zero existing data touched.
- **Estimated commits:** 2.
- **Rollback point:** Run `0004_..._down.sql`; delete `pharmagpt/db/`; revert `config.py`. Nothing depends on this yet.
- **Testing:** Full existing pytest suite (must show 0 change); manual schema diff vs. §4; 2-company RLS default-deny spot check.
- **Success criteria:** App behaves identically to `phase2-auth-complete`; schema exists in Staging; no code path touches the new tables yet.

### 3.2 Projects Migration
- **Objective:** Dual-write `projects` (SQLite stays the read source of truth), backfill existing rows under a bootstrap company. `project_members` is created and RLS-protected but **not** populated here — SQLite has no real per-project membership data to backfill from (owner/approver are free-text, not user references); that is Phase 7 (Project Workspace) territory. **Read cutover is out of scope for 3.2**, corrected from the original wording below — the target `projects` table drops the equipment_name/manufacturer/department/validation_type/model/location fields (their home becomes the Equipment Library, 3.4) and uses uuid ids against routes typed `<int:project_id>`; flipping reads now would change the API shape, not just relocate bytes. Revisited once 3.4 and route/id-shape work land. *(Amended twice during implementation — see commit history.)*
- **Files:** `migrations/0005_projects_rls_*.sql` (new), `pharmagpt/db/projects_repo.py` (new), `pharmagpt/config.py` (+`PROJECTS_BACKEND` flag: `sqlite`|`dual`|`postgres`), `pharmagpt/routes/projects.py`, `scripts/backfill_projects.py` (new), `scripts/check_projects_parity.py` (new).
- **DB impact:** `projects` populated (name/status/owner text.../target_date/risk_category/protocol_number/report_number map directly; `equipment_name`/`manufacturer`/`department`/`validation_type`/`model`/`location` have no column in the target schema — per `PLATFORM_ARCHITECTURE.md` §10 that data's home is the Equipment Library, wired in 3.4 — so it stays SQLite-only until then, which is fine since SQLite remains the source of truth throughout 3.2). `owner_user_id`/`approver_user_id` stay `NULL` (current app stores free text, not a user reference; resolving that is Phase 7, not a 3.2 concern).
- **Estimated commits:** 4.
- **Rollback point:** Flag off → reverts to SQLite; Postgres rows ignorable.
- **Testing:** Existing project tests + new dual-write parity diff.
- **Success criteria:** Project CRUD identical from the UI; zero parity drift over a 48h Staging soak.

### 3.3 Knowledge Base Migration
- **Objective:** Dual-write `kb_documents` create/delete into `documents`/`document_versions`/`document_categories`/`tags`/`document_tags` per `DB-002` (SQLite stays the read source of truth), backfill existing rows under the same bootstrap company as 3.2. No frontend change — `static/js/knowledge_base.js` untouched, no API contract change.
- **Files:** `migrations/0006_documents_rls_*.sql` (new), `pharmagpt/db/kb_repo.py` (new), `pharmagpt/config.py` (+`KB_BACKEND` flag: `sqlite`|`dual`), `pharmagpt/database.py` (+`postgres_id` column/setter on `kb_documents`), `pharmagpt/routes/knowledge_base.py`, `scripts/backfill_kb_documents.py` / `check_kb_parity.py` (new).
- **DB impact:** `documents` (`source_context='knowledge_base'`, `document_type='kb_document'` — SQLite has no finer type taxonomy to draw from), `document_versions`, `document_categories` (from SQLite `folder`), `tags`/`document_tags` (from comma-separated `tags`) populated. Created directly in `status='approved'` — KB uploads have no review gate in the current app. `storage_path` records today's local-disk path as a placeholder; actual byte migration is roadmap Phase 4, not this milestone. **Extracted-text sync is out of scope for dual-write** — it arrives asynchronously via the shared `services/document_processor.py` pipeline (used by KB *and* project documents alike), which this milestone does not touch, per Migration Principle 1 (zero unnecessary rewrites to shared infrastructure); backfill does a one-time copy only, so parity checks on `extracted_text` are expected to drift and are deliberately not checked. Delete dual-writes as `status='archived'`, not a hard delete — Postgres RESTRICTs deleting a `documents` row with `document_versions`, and archival is the architecturally correct behavior anyway; SQLite's real hard delete is unchanged. *(Amended from the original wording during implementation — see commit history.)*
- **Estimated commits:** 4 (actual: 5, including a bugfix — see summary). **Rollback point:** Flag off (default) → fully inert; revert commits to remove code.
- **Testing:** 13 new tests (dual-write orchestration + both scripts, fully mocked) + full existing suite, 0 regression.
- **Success criteria:** Every KB doc browsable/searchable/downloadable exactly as before (verified: no route behavior changed, only additive dual-write side effects gated by a default-off flag).

### 3.4 Equipment Library Migration — *depends on 3.3*
- **Objective:** Dual-write `equipment` (company-owned per `PA-013`, no `project_id`) create/update/delete, and `equipment_documents` link/unlink into `equipment_links` for `source_type='kb'` only. `equipment.project_id` retained on the SQLite side (`IMP-004`) — SQLite behavior/shape is completely unchanged.
- **Files:** `migrations/0007_equipment_fixes_and_rls_*.sql` (new — also fixes two bugs found in 0004: `gmp_impact` was `boolean`, the shipped build stores a 3-value text enum; `notes` had no column at all), `pharmagpt/db/equipment_repo.py` (new), `pharmagpt/config.py` (+`EQUIPMENT_BACKEND`), `pharmagpt/equipment_database.py` (+`postgres_id` columns/setters, +`get_all_equipment()`), `pharmagpt/routes/equipment.py`, `scripts/backfill_equipment.py` / `check_equipment_parity.py` (new). `services/equipment_service.py` untouched (not tenancy/storage-coupled).
- **DB impact:** `equipment` populated with **full field fidelity** (every SQLite column has a target column, unlike Projects) under the shared bootstrap company. `equipment_links` populated only for `source_type='kb'` links whose KB document has already been dual-written/backfilled — `source_type='project'` links have no Postgres document to point at yet (project-generated documents are roadmap Phase 9, out of this plan's 3.1–3.6 scope) and are explicitly skipped/counted, not silently dropped. Delete dual-writes as a real Postgres delete (equipment has no lifecycle/archive field, unlike documents) and swallows the expected RESTRICT failure when links still reference it.
- **Estimated commits:** 4 (actual: 4). **Rollback point:** Flag off (default) → fully inert.
- **Testing:** 20 new tests (dual-write orchestration + both scripts, fully mocked) + full existing suite, 0 regression.
- **Success criteria:** Every equipment record reachable company-wide with no data duplication (verified in code/tests; live Staging RLS isolation check is a deployment-time step, not verifiable from here).

### 3.5 QMS Migration — *depends on 3.2*
- **Objective:** Migrate `qms_*` tables (deviations, capas, change_controls, risk_assessments) plus `qms_audit_trail/attachments/comments/approvals` into the generalized platform tables, behind a flag.
- **Files:** `pharmagpt/qms_*_database.py` (5 files), `pharmagpt/routes/qms_*.py` (5 files), `pharmagpt/risk_database.py`.
- **DB impact:** `deviations`/`capas`/`change_controls`/`risk_assessments`/`audit_trail`/`attachments`/`comments`/`approvals` populated.
- **Estimated commits:** 5. **Rollback point:** Flag off → QMS routes revert to `qms_*` SQLite tables.
- **Testing:** Existing QMS suite (largest single domain); polymorphic link integrity spot-check.
- **Success criteria:** Every QMS workflow (create/review/approve) behaves identically; audit trail entries match 1:1.

### 3.6 SQLite Retirement — *depends on 3.2–3.5 all stable*
- **Objective:** Remove dual-write paths and SQLite code once 3.2–3.5 have each run stable in Staging; `pharmagpt.db` kept read-only, not deleted (`DATABASE_ARCHITECTURE.md` §19.3).
- **Files:** `pharmagpt/database.py` + 9 sibling `*_database.py` files (drop SQLite branches), `pharmagpt/config.py` (remove flag), every route touched in 3.2–3.5.
- **DB impact:** None (data already migrated). `render.yaml`/`Procfile` disk/`DB_PATH` removal stays roadmap Phase 12 scope, not here.
- **Estimated commits:** 3. **Rollback point:** Last-known-good tag before this milestone; SQLite file intact.
- **Testing:** Full suite against Postgres-only path; `check/` hygiene pass.
- **Success criteria:** No code path imports `sqlite3`; full suite green; tag `phase3-complete` cut.

## 2. Risks
- **Dual-write drift** (SQLite/Postgres diverge silently) — mitigated by a parity diff at each milestone's exit.
- **Default-deny RLS blocks legitimate reads** once a flag flips — each milestone adds only its own narrow, reviewed policy set at flip time, never earlier.
- **Feature-flag sprawl** — tracked in one `PHASE3_FLAGS.md` ledger, fully resolved before 3.6 (mirrors roadmap §14).
- **Effort creep on 3.5** (5 files, largest domain) — matches roadmap's own Phase 9 X-Large estimate; do not compress.

## 3. Deployment checkpoints

**Execution mode (revised after 3.2):** code development for 3.3 onward proceeds continuously, module to module, without waiting for a full 48h Staging soak of the prior module — only for that module's code to be complete, locally tested, and (once deployed) show a clean initial backfill + parity check with no deployment errors. Parity checks for already-shipped modules continue in the background while later modules are built. This does not touch the non-negotiables: SQLite stays the sole read source of truth until final cutover, every write dual-writes to Postgres, and the actual PostgreSQL read cutover / SQLite retirement (3.6) does not happen until **every** migrated module (3.2–3.5) has completed validation with zero drift — that gate is unchanged and absolute.

- After **3.1**: schema-only deploy to Staging → validate → done (confirmed).
- After each of **3.2–3.5**: deploy → run backfill → run parity check once → if clean and no deployment errors, code development immediately continues to the next module. Parity checks keep running periodically against every already-shipped module in parallel. A full extended soak and the 2-company RLS isolation check still happen before any flag is flipped beyond `dual`, but no longer gate starting the *next* module's development.
- Before **3.6** (cutover): every one of 3.2–3.5 must independently show zero parity drift over its own extended soak — this checkpoint is not compressed, regardless of how fast 3.2–3.5's code shipped.
- After **3.6**: tag `phase3-complete`, full regression run, hand off to roadmap Phase 7+ (Project Workspace membership, AI Engine, Document Engine) — out of this plan's scope.

## 4. Go / No-Go checklist (per milestone)
- [ ] Prior milestone's flag fully resolved (on + verified + old path removable) or explicitly deferred with an owner.
- [ ] Full pytest suite green.
- [ ] Row-count/parity reconciliation matches.
- [ ] 2-company RLS isolation spot-check passes for any newly-active policy.
- [ ] Rollback (flag flip back) rehearsed at least once in Staging.
- [ ] No business-logic/API/UI difference beyond what the milestone states.

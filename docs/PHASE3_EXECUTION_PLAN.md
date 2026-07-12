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
- **Objective:** Dual-write `projects`/`project_members`, backfill existing rows under the bootstrap company, cut `routes/projects.py` reads over behind a flag.
- **Files:** `pharmagpt/database.py` (projects functions only), `pharmagpt/routes/projects.py`, new `pharmagpt/db/projects_repo.py`.
- **DB impact:** `projects`/`project_members` populated; SQLite remains source of truth until flag flip confirmed.
- **Estimated commits:** 4.
- **Rollback point:** Flag off → reverts to SQLite; Postgres rows ignorable.
- **Testing:** Existing project tests + new dual-write parity diff.
- **Success criteria:** Project CRUD identical from the UI; zero parity drift over a 48h Staging soak.

### 3.3 Knowledge Base Migration
- **Objective:** Migrate `kb_documents` into `documents`/`document_versions` per `DB-002`, behind a flag.
- **Files:** `pharmagpt/database.py`, `pharmagpt/routes/knowledge_base.py`, `pharmagpt/static/js/knowledge_base.js`.
- **DB impact:** `documents` (`source_context='knowledge_base'`)/`document_versions`/`document_categories`/`tags` populated.
- **Estimated commits:** 4. **Rollback point:** Flag off → KB routes revert to `kb_documents`.
- **Testing:** Existing KB tests; browse/search/download parity check.
- **Success criteria:** Every KB doc browsable/searchable/downloadable exactly as before.

### 3.4 Equipment Library Migration — *depends on 3.3*
- **Objective:** Re-parent `equipment` to `company_id`, introduce `equipment_links`, behind a flag.
- **Files:** `pharmagpt/equipment_database.py`, `pharmagpt/routes/equipment.py`, `pharmagpt/services/equipment_service.py`.
- **DB impact:** `equipment`/`equipment_links` populated; `equipment.project_id` retained on the SQLite side (`IMP-004`).
- **Estimated commits:** 4. **Rollback point:** Flag off → equipment routes revert to project-owned SQLite.
- **Testing:** Existing equipment tests; multi-project-same-equipment scenario.
- **Success criteria:** Every equipment record reachable company-wide; no data duplication.

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
- After **3.1**: schema-only deploy to Staging → validate → **stop; wait for user go-ahead** before 3.2.
- After each of **3.2–3.5**: ≥48h Staging dual-write soak → manual 2-company RLS isolation check → flag-flip deploy to Staging → then, separately and only after Staging is confirmed stable, Production.
- After **3.6**: tag `phase3-complete`, full regression run, hand off to roadmap Phase 7+ (Project Workspace membership, AI Engine, Document Engine) — out of this plan's scope.

## 4. Go / No-Go checklist (per milestone)
- [ ] Prior milestone's flag fully resolved (on + verified + old path removable) or explicitly deferred with an owner.
- [ ] Full pytest suite green.
- [ ] Row-count/parity reconciliation matches.
- [ ] 2-company RLS isolation spot-check passes for any newly-active policy.
- [ ] Rollback (flag flip back) rehearsed at least once in Staging.
- [ ] No business-logic/API/UI difference beyond what the milestone states.

# SQLite Reference Audit — PharmaGPT Phase 3 Migration

**Date:** 2026-07-21
**Scope:** Full repo grep for SQLite references (`sqlite3`, `sqlite://`, `.db` paths, `DATABASE_BACKEND`/`PROJECTS_BACKEND`/`KB_BACKEND`/`EQUIPMENT_BACKEND`/`QMS_BACKEND`, SQLite-specific SQL syntax, config, deployment, tests, docs). Excludes `venv/`, `.pytest_cache/`, `.git/`, `check/` (bundled venv).
**Read-only audit — no code, config, or data was modified.**

## Governing fact (do not re-litigate)

Per `docs/PHASE3_EXECUTION_PLAN.md` §3.6 and `docs/PHASE3_FLAGS.md`, SQLite retirement is gated on **(a)** an extended Staging soak of `PROJECTS_BACKEND`/`KB_BACKEND`/`EQUIPMENT_BACKEND`/`QMS_BACKEND` each running in `dual`, and **(b)** a 2-company RLS isolation spot-check for each of the 4 domains (Projects/KB/Equipment/QMS). **Neither has happened yet** (confirmed directly in `PHASE3_FLAGS.md`: "Extended Staging soak not yet started" for all four flags; `dual` is "not yet enabled in any deployed environment"). This gate is stated as absolute and non-negotiable in the plan §3. Consequently, every SQLite code path in the 4 gated domains (Projects, Knowledge Base, Equipment, QMS) — plus the shared `pharmagpt/database.py` and its domain siblings, the dual-write plumbing in `pharmagpt/db/`, the per-domain `*_BACKEND` flags, the backfill/parity scripts, `render.yaml`'s persistent-disk `DB_PATH`, and the SQLite-path test suite — is the **current, correct, intentionally active state of the system**, not leftover code. None of it is recommended for removal in this report.

## Summary — counts by classification

| Classification | Files | Notes |
|---|---|---|
| 1. ACTIVE (gated by Phase 3.6) | 44 | Core SQLite domain modules, dual-write seam (`pharmagpt/db/`), per-domain backend flags, route gating, backfill/parity scripts, deployment config |
| 2. DEAD/OBSOLETE (actionable now) | 2 | See explicit list below |
| 3. DOC/REFERENCE-ONLY | 25 | Markdown docs describing SQLite historically or as target-state migration narrative; one frontend JS comment |
| 4. TEST INFRASTRUCTURE (ACTIVE) | 20 | Tests legitimately exercising the still-active SQLite path and the mocked dual-write orchestration |
| **Total files with a SQLite reference** | **~91** | |

## DEAD/OBSOLETE — actionable this session

Only two findings qualified as genuinely dead/stale (safe to act on independent of the Phase 3.6 gate, since neither touches the active SQLite data path):

1. **`D:\PharmaAgent\pharmagpt.db`** (repo root, 4096 bytes, last modified 2026-07-05) — an orphaned stray SQLite file at the repo root. `pharmagpt/database.py:54` resolves `DB_PATH` to `pharmagpt/pharmagpt.db` (inside the package directory) by default, not the repo root, so this root-level file is never opened by the running app. It sits alongside the real, actively-used `pharmagpt/pharmagpt.db` (454,656 bytes, last modified 2026-07-13) purely as leftover clutter. Both are already `.gitignore`d (`*.db`), so this is a local working-tree cleanup only, not a git operation. **Safe to delete.**
2. **`pharmagpt/db/__init__.py:10-12`** — stale docstring. It states *"Nothing in `pharmagpt/database.py` or `pharmagpt/routes/` imports this package yet — it has zero effect on running behavior until a domain's cutover lands."* This was true when `db/__init__.py` was written in Phase 3.1, but Phases 3.2–3.5 have since landed and 6 route files now import from this package: `pharmagpt/routes/projects.py:28` (`projects_repo`), `knowledge_base.py:25` (`kb_repo`), `equipment.py:29` (`equipment_repo`), `risk.py:43`, `qms_capa.py:48`, `qms_deviations.py:47`, `qms_change_control.py:60` (all four import `qms_repo`). The docstring is factually wrong today — a stale comment, not a functional bug (the module itself has no runtime issue). **Safe to correct** (update the comment to reflect that all 4 domain repos are now wired in).

No other file contained a SQLite reference that was unused, commented-out, or safely removable — everything else is either the active source-of-truth path (gated) or documentation.

## 1. ACTIVE — gated by Phase 3.6, do not touch

Representative references per file (not exhaustive line-by-line for repetitive schema DDL — e.g. repeated `INTEGER PRIMARY KEY AUTOINCREMENT` column lines are collapsed to one row citing the line range).

| File | Line | Purpose | Classification | Replacement Required | Priority | Risk |
|---|---|---|---|---|---|---|
| `pharmagpt/database.py` | 36, 54, 63, 66/71/72 | `import sqlite3`; `DB_PATH` resolution; `sqlite3.connect()`; `PRAGMA foreign_keys/journal_mode/busy_timeout` | ACTIVE | No (gated) | P3 | Low — touching this before 3.6 breaks the sole source of truth for Projects/KB/Equipment/QMS reads |
| `pharmagpt/database.py` | 96,110,127,144,161,175,197,211 | Table DDL (`AUTOINCREMENT`) for projects/messages/documents/kb_documents/generated_documents etc. | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/database.py` | 353-419 | `_migrate_val_projects()` — one-time idempotent Phase 2 (not Phase 3) copy of legacy `val_projects`/`val_audit_trail` rows into unified `projects`. Guarded, non-destructive, still runs on every `init_db()`. Pre-existing decision (`PROJECT_MEMORY/DECISIONS.md` DEC-024), unrelated to the Phase 3 gate but still intentionally retained | ACTIVE (separate legacy decision, not Phase 3) | No | P3 | Low |
| `pharmagpt/database.py` | 626, 678 | `INSERT OR REPLACE INTO document_text` — SQLite-specific upsert syntax | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/equipment_database.py` | 34-35, 295, 341 | `import sqlite3`; `from pharmagpt.database import get_connection`; table DDL | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/qms_database.py` | 31, 33, 45-338 | `import sqlite3`; `get_connection`; 13 table DDLs (deviations/CAPA/change-control/etc.) | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/qms_deviation_database.py` | 15 | `from pharmagpt.database import get_connection` (dual-write bookkeeping columns added 3.5) | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/qms_change_control_database.py` | 21 | `from pharmagpt.database import get_connection` | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/qms_capa_database.py` | 16 | `from pharmagpt.database import get_connection` | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/qms_document_database.py` | 15 | `from pharmagpt.database import get_connection`; document lifecycle counts | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/risk_database.py` | 13-14, 459-566 | `import sqlite3`; `get_connection`; table DDL for risk assessments/library/actions | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/qual_database.py` | 18-19, 26-216 | `import sqlite3`; `get_connection`; table DDL | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/urs_database.py` | 13, 15, 22-89, 369 | `import sqlite3`; `get_connection`; table DDL; obsolete-status COUNT query | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/report_database.py` | 14, 21-121, 235 | `get_connection`; table DDL; `INSERT OR IGNORE INTO val_report_sections` | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/db/backend.py` | 11, 15-27 | `VALID_BACKENDS = ("sqlite", "postgres")`; `get_backend_name()`/`is_postgres_backend()` reading `config.DATABASE_BACKEND` | ACTIVE | No — this *is* the Phase 3 seam | P2 | Low, but this is the literal switch point for the eventual cutover |
| `pharmagpt/db/__init__.py` | 6-8 | Package docstring: seam reads/writes either SQLite (today's source of truth) or Postgres | ACTIVE | See DEAD/OBSOLETE #2 above for the stale sub-claim | P3 | Low |
| `pharmagpt/db/projects_repo.py` | 5, 16, 23 | Dual-write comments re: `config.PROJECTS_BACKEND`, SQLite free-text owner/approver, "never blocks the SQLite write" policy | ACTIVE | No (gated) | P2 | Medium — this is the dual-write orchestration itself; a bug here silently breaks parity, not the SQLite path |
| `pharmagpt/db/kb_repo.py` | 5, 14-43, 147, 156 | Dual-write comments re: `config.KB_BACKEND`, SQLite `folder`→category / comma-tags→tag-rows mapping, SQLite hard-delete vs Postgres archive | ACTIVE | No (gated) | P2 | Medium |
| `pharmagpt/db/equipment_repo.py` | 6, 12-15 | Dual-write comments re: `config.EQUIPMENT_BACKEND`, SQLite `project_id` vs company-owned target schema | ACTIVE | No (gated) | P2 | Medium |
| `pharmagpt/db/qms_repo.py` | 6, 20-29 | Dual-write comments re: `config.QMS_BACKEND`, SQLite-only sub-structures explicitly out of scope | ACTIVE | No (gated) | P2 | Medium |
| `pharmagpt/config.py` | 23-29 | `DATABASE_BACKEND = os.getenv(..., "sqlite")` — global seam flag | ACTIVE | No (gated) | P1 | High if flipped without the 3.6 gate satisfied |
| `pharmagpt/config.py` | 31-47 | `PROJECTS_BACKEND` (`sqlite`\|`dual`) + rationale for why no `postgres` read-cutover state exists yet | ACTIVE | No (gated) | P1 | High if flipped early |
| `pharmagpt/config.py` | 49-59 | `KB_BACKEND` (`sqlite`\|`dual`) | ACTIVE | No (gated) | P1 | High if flipped early |
| `pharmagpt/config.py` | 61-70 | `EQUIPMENT_BACKEND` (`sqlite`\|`dual`) | ACTIVE | No (gated) | P1 | High if flipped early |
| `pharmagpt/config.py` | 72-91 | `QMS_BACKEND` (`sqlite`\|`dual`) | ACTIVE | No (gated) | P1 | High if flipped early |
| `pharmagpt/routes/projects.py` | 28, 42/62/84 | `from pharmagpt.db import projects_repo`; `if config.PROJECTS_BACKEND != "dual": return` guards | ACTIVE | No (gated) | P1 | High — this is the flag-gate itself |
| `pharmagpt/routes/knowledge_base.py` | 25, 37/57 | `from pharmagpt.db import kb_repo`; `KB_BACKEND != "dual"` guards | ACTIVE | No (gated) | P1 | High |
| `pharmagpt/routes/equipment.py` | 29, 42/55/70/89/112 | `from pharmagpt.db import equipment_repo`; `EQUIPMENT_BACKEND != "dual"` guards | ACTIVE | No (gated) | P1 | High |
| `pharmagpt/routes/risk.py` | 43, 64/80/98 | `from pharmagpt.db import qms_repo`; `QMS_BACKEND != "dual"` guards | ACTIVE | No (gated) | P1 | High |
| `pharmagpt/routes/qms_deviations.py` | 47, 67/88/107 | Same pattern for deviations | ACTIVE | No (gated) | P1 | High |
| `pharmagpt/routes/qms_capa.py` | 48, 66/87/106 | Same pattern for CAPA | ACTIVE | No (gated) | P1 | High |
| `pharmagpt/routes/qms_change_control.py` | 60, 78/99/118 | Same pattern for change control | ACTIVE | No (gated) | P1 | High |
| `pharmagpt/app.py` | 8, ~20 | `from pharmagpt import database as db`; startup comment "Initialise the SQLite database tables" | ACTIVE | No (gated) | P1 | High — app boot depends on this |
| `pharmagpt/state.py` | 14 | `from pharmagpt import database as db` | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/services/document_processor.py` | 18, 32 | Persists extraction progress to SQLite; `from pharmagpt import database as db` | ACTIVE | No (gated) | P2 | Medium |
| `pharmagpt/services/job_runner.py` | 7, 42 | Job results/progress persisted to SQLite; "single-SQLite-file, no-extra-infra deployment" comment | ACTIVE | No (gated) | P2 | Medium |
| `pharmagpt/services/urs_generation_job.py` | 24 | URS generation progress persisted to SQLite | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/services/supabase_client.py` | 14 | Docstring referencing `DATABASE_BACKEND` "defaulting to sqlite" | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/services/retrieval_engine.py` | 45 | `from pharmagpt import database as db` | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/services/equipment_service.py` | 28 | `from pharmagpt import database as db` (explicitly untouched by 3.4 per plan) | ACTIVE | No (gated) | P3 | Low |
| `pharmagpt/services/document_search.py` | 23 | `from pharmagpt import database as db`; comment on 1MB-per-message SQLite text fetch (flagged separately in `docs/CODE_REVIEW.md:395` as a perf concern, not a migration concern) | ACTIVE | No (gated) | P3 | Low |
| `render.yaml` | 8-14 | Persistent disk (`pharmagpt-data` @ `/var/data`) + `DB_PATH=/var/data/pharmagpt.db` env var | ACTIVE | No — disk/`DB_PATH` removal is explicitly roadmap Phase 12 scope, not Phase 3.6 | P0 | Critical — removing this before cutover loses the production database on every redeploy |
| `.gitignore` | 21-26 | `*.db`, `*.db-shm`, `*.db-wal`, `*.sqlite`, `*.sqlite3` ignore rules | ACTIVE | No | P3 | Low |
| `scripts/backfill_projects.py` | 2, 16, 28, 83-99 | One-time (idempotent, re-runnable) Phase 3.2 backfill: SQLite → Postgres | ACTIVE | No (gated) | P2 | Medium — re-run periodically per plan §3 "parity checks keep running" |
| `scripts/backfill_kb_documents.py` | 2, 28, 80 | Phase 3.3 backfill | ACTIVE | No (gated) | P2 | Medium |
| `scripts/backfill_equipment.py` | 2, 12, 54 | Phase 3.4 backfill | ACTIVE | No (gated) | P2 | Medium |
| `scripts/backfill_qms.py` | 61-68 | Phase 3.5 backfill (4 record types) | ACTIVE | No (gated) | P2 | Medium |
| `scripts/check_projects_parity.py` | 5, 55, 77-92 | Ongoing SQLite vs. Postgres parity diff — plan §3 requires these keep running periodically until 3.6 | ACTIVE | No (gated) | P1 | High — this is the primary drift-detection signal the 3.6 gate depends on |
| `scripts/check_kb_parity.py` | 5, 64-80 | Same, for KB | ACTIVE | No (gated) | P1 | High |
| `scripts/check_equipment_parity.py` | 5, 61-74 | Same, for Equipment | ACTIVE | No (gated) | P1 | High |
| `scripts/check_qms_parity.py` | 5, 57-90 | Same, for all 4 QMS record types | ACTIVE | No (gated) | P1 | High |

## 2. DEAD/OBSOLETE — safe to remove now

| File | Line | Purpose | Classification | Replacement Required | Priority | Risk |
|---|---|---|---|---|---|---|
| `pharmagpt.db` (repo root) | n/a (whole file) | Orphaned stray SQLite file, 4KB, not on the resolved `DB_PATH`; superseded by `pharmagpt/pharmagpt.db` | DEAD/OBSOLETE | Delete the file | P3 | Low — never read by the running app; gitignored, so no git history impact |
| `pharmagpt/db/__init__.py` | 10-12 | Stale docstring claiming no route imports this package; false since Phase 3.2–3.5 | DEAD/OBSOLETE (comment only) | Update comment to reflect `projects_repo`/`kb_repo`/`equipment_repo`/`qms_repo` are now wired into 6 route files | P3 | Low — comment-only, no functional impact |

## 3. DOC/REFERENCE-ONLY

Markdown/JS-comment mentions describing SQLite historically, as current-state narrative, or as target-state migration context. None require action; informational only.

| File | Line(s) | Purpose | Classification | Replacement Required | Priority | Risk |
|---|---|---|---|---|---|---|
| `docs/PHASE3_EXECUTION_PLAN.md` | throughout, esp. 10,19-57 | The living Phase 3 execution checklist itself (source of the gate this audit respects) | DOC/REFERENCE-ONLY | Keep updated as milestones complete | P2 | Low, but this is the authoritative gate — misreading it wrongly is the main audit risk |
| `docs/PHASE3_FLAGS.md` | 7-17 | Flag ledger — confirms all 4 domain flags Open, soak/RLS-check not started | DOC/REFERENCE-ONLY | Keep updated per flag flip | P2 | Low |
| `docs/DATABASE_ARCHITECTURE.md` | 8, 499-536, 674-677 | Target Postgres schema + 3-phase migration strategy (SQLite→Postgres→Supabase) | DOC/REFERENCE-ONLY | No | P3 | Low |
| `docs/PLATFORM_ARCHITECTURE.md` | 8, 420 | Frozen multi-tenant target architecture; storage strategy contrasting SQLite-on-ephemeral-disk risk | DOC/REFERENCE-ONLY | No | P3 | Low |
| `docs/IMPLEMENTATION_ROADMAP.md` | 16-125, 207-502 | 12-phase roadmap; Phase 3/12 SQLite retirement narrative | DOC/REFERENCE-ONLY | No | P3 | Low |
| `docs/ARCHITECTURE.md` | 19-123, 360-410 | Current-build architecture doc (raw `sqlite3`, no ORM) | DOC/REFERENCE-ONLY | No — superseded in detail by `PROJECT_MEMORY/ARCHITECTURE.md` (newer, larger); consider consolidating later, out of scope here | P3 | Low |
| `docs/ROADMAP.md` | 4, 66, 85 | Older roadmap snapshot listing "PostgreSQL migration path from SQLite" as a future item | DOC/REFERENCE-ONLY | Stale relative to `docs/PHASE3_EXECUTION_PLAN.md` (Phase 3 already in flight) — informational only | P3 | Low |
| `docs/CHANGELOG.md` | — | Historical changelog snapshot | DOC/REFERENCE-ONLY | No | P3 | Low |
| `docs/PRODUCT_REQUIREMENTS.md` | 133, 174 | NFR listing SQLite as the zero-config storage requirement | DOC/REFERENCE-ONLY | No | P3 | Low |
| `docs/TESTING_VALIDATION_GUIDE.md` | 37, 341 | Manual test guide referencing `DB_PATH`/SQLite persistence | DOC/REFERENCE-ONLY | No | P3 | Low |
| `docs/CODE_REVIEW.md` | 395 | Perf note: SQLite full-text fetch per chat message (unrelated to Phase 3 migration; a performance finding, not a migration one) | DOC/REFERENCE-ONLY | Out of scope for this audit | P3 | Low |
| `docs/URS_STABILIZATION_REVIEW.md` | 23, 61 | URS batch generation persistence-to-SQLite notes | DOC/REFERENCE-ONLY | No | P3 | Low |
| `CHANGELOG.md` (root) | 151-237 | Historical schema-addition changelog entries | DOC/REFERENCE-ONLY | No — older/smaller than `docs/CHANGELOG.md`; both are stale relative to `PROJECT_MEMORY/RELEASE_NOTES.md` | P3 | Low |
| `ROADMAP.md` (root) | 4, 66, 85 | Older roadmap snapshot | DOC/REFERENCE-ONLY | Superseded by `docs/PHASE3_EXECUTION_PLAN.md`; duplicate/stale doc, not code | P3 | Low |
| `PROJECT_STATUS.md` (root) | 4, 21-24, 58, 198, 339-355 | Older project-status snapshot describing pre-migration SQLite-only architecture | DOC/REFERENCE-ONLY | Superseded by `PROJECT_MEMORY/PROJECT_STATUS.md` (newer, larger) | P3 | Low |
| `DATABASE.md` | 3 | "Engine: SQLite 3" — documents schema as it runs today (explicitly cross-referenced by `DATABASE_ARCHITECTURE.md:8` as still accurate) | DOC/REFERENCE-ONLY | No — deliberately kept accurate per `DATABASE_ARCHITECTURE.md` | P2 | Low |
| `PHASE2_COMPLETION.md` | 100 | Notes business data "still lives in SQLite" as of Phase 2 completion | DOC/REFERENCE-ONLY | No | P3 | Low |
| `SYSTEM_ARCHITECTURE_DOCUMENT_PROCESSING.md` | 182-216 | Confirms Flask+gunicorn+SQLite stack decision, no Redis/Celery; references throwaway-SQLite test pattern | DOC/REFERENCE-ONLY | No | P3 | Low |
| `PROJECT_MEMORY/CLAUDE.md` | 35, 74, 99, 107-110 | Agent-facing project memory: SQLite-first convention, raw `sqlite3`, test isolation pattern | DOC/REFERENCE-ONLY | No | P2 | Low — actively read by future coding sessions, keep accurate |
| `PROJECT_MEMORY/PROJECT_STATUS.md` | 47, 57, 74, 86 | Current authoritative status snapshot (newer than root `PROJECT_STATUS.md`) | DOC/REFERENCE-ONLY | No | P2 | Low |
| `PROJECT_MEMORY/DECISIONS.md` | 36-84, 357-370 | DEC-002 (raw sqlite3), DEC-003 (SQLite→Postgres path), DEC-015 (persistent disk for SQLite) | DOC/REFERENCE-ONLY | No | P2 | Low — decision record, should not be edited retroactively |
| `PROJECT_MEMORY/ARCHITECTURE.md` | 21-114, 342, 503-543 | Current authoritative architecture doc (newer/larger than `docs/ARCHITECTURE.md`) | DOC/REFERENCE-ONLY | No | P2 | Low |
| `PROJECT_MEMORY/RELEASE_NOTES.md` | 781, 846 | Historical release notes mentioning SQLite persistence | DOC/REFERENCE-ONLY | No | P3 | Low |
| `project_tree.txt` | 12 | Generated file-tree snapshot listing `pharmagpt.db` | DOC/REFERENCE-ONLY | Likely stale (generated at some earlier point) — regenerate or delete at maintainers' discretion, not urgent | P3 | Low |
| `pharmagpt/static/js/urs.js` | 1817 | Frontend comment: "a hung request (slow cold start, a busy SQLite writer, a dropped ...)" | DOC/REFERENCE-ONLY | No | P3 | Low |

## 4. TEST INFRASTRUCTURE — ACTIVE (tests legitimately exercise the still-active SQLite path)

| File | Line(s) | Purpose | Classification | Replacement Required | Priority | Risk |
|---|---|---|---|---|---|---|
| `tests/conftest.py` | 30-39 | `db_path` fixture: points `pharmagpt.database.DB_PATH` at a throwaway SQLite file per test, calls `init_db()` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P1 | High — nearly every test in the suite depends on this fixture |
| `tests/test_projects_dual_write.py` | 1-10 | Phase 3.2 dual-write orchestration coverage; mocks `projects_repo`, asserts SQLite response is never blocked by a Postgres failure | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_kb_dual_write.py` | 1-10 | Phase 3.3 dual-write orchestration coverage | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_equipment_dual_write.py` | 1-9 | Phase 3.4 dual-write orchestration coverage | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_qms_dual_write.py` | 1-9 | Phase 3.5 dual-write orchestration coverage (all 4 QMS record types) | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_backfill_projects.py` | — | Tests `scripts/backfill_projects.py` (mocked Supabase) | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_backfill_kb_documents.py` | — | Tests `scripts/backfill_kb_documents.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_backfill_equipment.py` | — | Tests `scripts/backfill_equipment.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_backfill_qms.py` | — | Tests `scripts/backfill_qms.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Medium |
| `tests/test_check_projects_parity.py` | — | Tests `scripts/check_projects_parity.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P1 | Medium — protects the drift-detection tool the 3.6 gate relies on |
| `tests/test_check_kb_parity.py` | — | Tests `scripts/check_kb_parity.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P1 | Medium |
| `tests/test_check_equipment_parity.py` | — | Tests `scripts/check_equipment_parity.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P1 | Medium |
| `tests/test_check_qms_parity.py` | — | Tests `scripts/check_qms_parity.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P1 | Medium |
| `tests/test_qms_database.py` | — | Direct SQLite CRUD tests for `qms_database.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Low |
| `tests/test_equipment_database.py` | — | Direct SQLite CRUD tests for `equipment_database.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Low |
| `tests/test_projects_merge.py` | — | Tests `_migrate_val_projects()` legacy-merge behavior | TEST INFRASTRUCTURE (ACTIVE) | No | P3 | Low |
| `tests/test_urs_generation_job.py` | — | Tests URS batch job persisting progress to SQLite | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Low |
| `tests/test_urs_lifecycle.py`, `test_urs_audit_logging.py`, `test_urs_docx_download_auth.py` | — | URS lifecycle/audit tests against the SQLite-backed `urs_database.py` | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Low |
| `tests/test_routes_upload_async.py` | — | Upload/async extraction tests against throwaway SQLite (`db_path` fixture) | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Low |
| `tests/test_app_auth_integration.py`, `test_login_ui.py` | — | Auth-gate integration tests using the `db_path`/`client` fixtures | TEST INFRASTRUCTURE (ACTIVE) | No (gated) | P2 | Low |

## Notes on things checked and found clean

- **`migrations/*.sql`** (0001–0009): pure Postgres DDL/RLS/grants, zero SQLite references — confirms the migration files stay cleanly separated from the SQLite path.
- **No CI/GitHub Actions files exist** in this repo; `pytest.ini` has no SQLite-specific config.
- **`requirements.txt`**: `sqlite3` is stdlib (no package entry needed); Supabase/Postgres client packages (`supabase`, `postgrest`, `realtime`, `storage3`) are present and current — no dead dependency found either direction.
- **`Procfile`**: no direct SQLite reference; it starts gunicorn against `pharmagpt.app:app`, which depends on `render.yaml`'s `DB_PATH` env var — consistent, no gap.
- The four root-level docs (`CHANGELOG.md`, `ROADMAP.md`, `PROJECT_STATUS.md`) plus `docs/ARCHITECTURE.md` and `docs/CHANGELOG.md`/`docs/ROADMAP.md` appear to be **older, superseded snapshots** of documents that now live in fuller/newer form under `PROJECT_MEMORY/`. This is a general documentation-hygiene observation, not a SQLite-migration issue — flagged for awareness only, no action taken or recommended here.

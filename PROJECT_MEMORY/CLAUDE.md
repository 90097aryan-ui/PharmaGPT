# CLAUDE.md — PharmaGPT Operating Manual

> **Read this file FIRST in every Claude Code session on this repository.**
> This is the permanent operating manual for how Claude works on PharmaGPT. It is part of the
> `PROJECT_MEMORY/` set — the project's permanent memory — alongside `PROJECT_STATUS.md`,
> `ARCHITECTURE.md`, `RELEASE_NOTES.md`, and `DECISIONS.md`.

---

## Project Identity

| | |
|---|---|
| **Company** | The Lean Architect |
| **Products** | PharmaGPT (this repository), YieldTrack (separate product — not in this repository) |
| **Platform** | Enterprise Pharmaceutical Digital Quality & Validation Platform |
| **Repository** | `D:\PharmaAgent` |
| **Current Version (last committed release)** | **v0.9.8** — "Document Intelligence Engine and Validation UI improvements" (commit `684ca7d`, 2026-07-02) |
| **Working tree state** | Quality Management Suite Phase 1 (Document Control, Deviation, CAPA) is complete, tested, and functionally wired into the app, but **not yet committed to git** as of this writing. See [PROJECT_STATUS.md](PROJECT_STATUS.md) → Current Sprint. |

Version numbering note: this repository has used two overlapping schemes historically — early feature-sprint labels (v0.1 through v0.8) and later semantic-style labels (v0.9.5 Beta → v0.9.8). Treat **git commit history** as the source of truth for the current version, not the version strings inside individual `.md` files, which drift. See [DECISIONS.md](DECISIONS.md) DEC-014 for full detail.

---

## Project Vision

Build the world's leading AI-powered Pharmaceutical Digital Quality, Validation and Manufacturing
Excellence Platform.

**Primary Goals**
- Enterprise Quality
- Regulatory Compliance (21 CFR Part 11, EU GMP Annex 11, GAMP 5, ICH Q9/Q10)
- AI-Assisted (Google Gemini throughout — chat, generation, review, investigation)
- Modular (suite-per-domain: Validation, Knowledge Base, Quality Management, and future Manufacturing Excellence)
- Scalable (SQLite → PostgreSQL migration path; ThreadPoolExecutor → Celery swap path already stubbed)
- Backward Compatible (additive-only schema changes; new consumers never break old ones)
- Production Ready (deployed on Render; gunicorn + persistent disk)

---

## Mandatory Development Workflow

**Before writing any code, ALWAYS read, in this order:**

1. [PROJECT_STATUS.md](PROJECT_STATUS.md) — what exists today, what's in progress, what's known-broken
2. [ARCHITECTURE.md](ARCHITECTURE.md) — how the system is structured, where new code belongs
3. [DECISIONS.md](DECISIONS.md) — why the system is built the way it is, so you don't re-litigate settled decisions
4. [RELEASE_NOTES.md](RELEASE_NOTES.md) — what shipped most recently, for continuity with the last session

**Only inspect the source files required for the requested task.** Do not recursively scan the
repository (`pharmagpt/`, `tests/`, etc.) unless the task is explicitly a repo-wide audit, or the
four documents above don't answer the question you have. These documents exist specifically so
that full-repo scans are no longer the default starting point.

If you discover that one of these five documents is stale or wrong while working, **fix it as
part of the same task** — do not leave the memory out of sync with the code you just changed.

---

## Development Rules

- Never redesign completed architecture. Extend it.
- Never duplicate functionality — check `services/`, `routes/`, and `prompts/` for an existing
  implementation before writing a new one (PharmaGPT already has a documented history of
  duplicate-code findings; see [DECISIONS.md](DECISIONS.md) DEC-013).
- Reuse existing services (`pharmagpt/services/*.py`).
- Reuse existing AI prompts (`pharmagpt/prompts/*.py`) — every domain (Risk, URS, Qual, Report,
  QMS Document/Deviation/CAPA) already has a dedicated prompt module.
- Reuse existing utilities (`documents.py`, `state.py`, `qms_shared.py::call_gemini/stream_gemini`).
- Reuse existing database helpers — raw `sqlite3` via each domain's `*_database.py`; do not
  introduce an ORM or a second database-access pattern (see DEC-002).
- Maintain backward compatibility. New extraction/status fields must be additive; existing
  consumers (`document_search.py`, `retrieval_engine.py`, chat/validation routes) must keep working
  unmodified.
- Maintain UI consistency — the "Premium Enterprise" palette v3.0 (Walnut Brown/warm neutrals,
  DEC-018 + DEC-019, 2026-07-05), existing `:root` color tokens and component classes in
  `static/css/style.css` (and suite-specific CSS that reuses those tokens, e.g. `qms.css`). Use
  Lucide icons (`<span class="icon" data-lucide="...">`, auto-converted by the global
  `refreshIcons()`/`MutationObserver` in `templates/index.html`) for any new icon — never a Unicode
  emoji or a hand-authored inline SVG. See `docs/DESIGN_SYSTEM.md` for the full token/component
  reference (needs a v3.0 update — see DEC-019).
- Use **additive database migrations only**. This project has no migration framework (Alembic /
  Flask-Migrate). Add columns via a guarded `_add_column_if_missing()`-style helper (see
  `document_processor`/`database.py` precedent). Never drop or rename a column or table in place.
- Never remove working functionality without explicit user instruction and a DECISIONS.md entry.
- Never change an API route's request/response shape without documenting it (update `API.md` at
  repo root and note the change in [RELEASE_NOTES.md](RELEASE_NOTES.md)).
- Never introduce duplicate database tables — check `DATABASE.md` (repo root) and
  [ARCHITECTURE.md](ARCHITECTURE.md) for the full current schema before adding a table. Prefer
  extending the existing polymorphic QMS tables (`qms_attachments`, `qms_comments`,
  `qms_audit_trail`, `qms_approvals`, keyed by `record_type`/`record_id`) over creating new
  per-module equivalents.
- Always perform regression testing (`pytest`) before considering a change complete.
- Always produce automated tests for new behavior, following the existing `tests/test_*.py`
  pattern (fixtures in `tests/conftest.py`, isolated throwaway SQLite DB — never the dev DB).
- Never commit automatically. Never push automatically.
- Never delete production code without justification recorded in [DECISIONS.md](DECISIONS.md).

---

## Coding Standards

- **Backend:** Flask (blueprints per domain), raw `sqlite3` (no ORM), REST-style JSON APIs, SSE
  (`text/event-stream`) for streaming AI output.
- **Database:** SQLite today; PostgreSQL-ready migration path is a stated v1.0 goal (DEC-003) —
  avoid SQLite-only syntax where a reasonable Postgres-compatible alternative exists.
- **Frontend:** Vanilla JavaScript SPA — one IIFE module per feature area under
  `pharmagpt/static/js/`, no build toolchain, no framework (DEC-005).
- **Theme:** Dark theme throughout (see [ARCHITECTURE.md](ARCHITECTURE.md) Design System summary
  for the color/typography tokens). The document viewer/export components are the deliberate
  light-background exception (they mimic a printed Word document).
- **Responsiveness:** Desktop-first (1280px+); mobile is not yet a priority (planned v0.8+ item).
- **Principles:** SOLID, DRY, KISS. Split files by single responsibility once they approach
  ~1000 lines (precedent: `qual_database.py` 997 lines, `report_database.py` 602 lines — the QMS
  module split its DB layer into `qms_document_database.py` / `qms_deviation_database.py` /
  `qms_capa_database.py` rather than one 2000+ line file for exactly this reason — see DEC-013).
- **Background processing:** `concurrent.futures.ThreadPoolExecutor` via `services/job_runner.py`
  (`ThreadPoolJobRunner`), not Celery (DEC-004). A `CeleryJobRunner` stub exists for a future swap;
  implement it only if/when Redis is actually introduced to the stack.
- **Shared Services** — reuse these, do not re-implement per module:
  - Shared Attachments — `qms_attachments` (polymorphic, `record_type` ∈ `document|deviation|capa`)
  - Shared Comments — `qms_comments` (polymorphic)
  - Shared Audit Trail — `qms_audit_trail` (polymorphic); `val_audit_trail` is the older,
    Validation-Workspace-specific equivalent — do not fork a third audit table.
  - Shared Approval Engine — `qms_approvals` (typed-name e-signature, no PKI; matches the
    `risk_approval`/`qual_approvals` convention)
  - Shared Notification Engine — **not yet implemented.** Only a planned v0.9 `notifications`
    table + SSE delivery exists in the roadmap. Do not assume it exists.

---

## Documentation Rules

**Whenever code changes, update the relevant PROJECT_MEMORY documents before considering the task
complete:**

- [PROJECT_STATUS.md](PROJECT_STATUS.md) — move items between Current Sprint / Completed / Planned;
  update Known Issues and Testing Status.
- [ARCHITECTURE.md](ARCHITECTURE.md) — update if folder structure, module relationships, or a
  layer's responsibilities changed.
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — **append** a new entry (never overwrite prior entries)
  once a change is ready to be considered part of a release.
- [DECISIONS.md](DECISIONS.md) — **append** a new decision record (never overwrite prior entries)
  for any non-trivial architectural or technical choice — new tables, new dependencies, new
  background-processing strategy, new API design pattern, etc.

Also keep the root-level `API.md`, `DATABASE.md`, and `CHANGELOG.md` in sync — they are the
detailed technical references that `PROJECT_MEMORY/` summarizes and indexes. `PROJECT_MEMORY/` is
the entry point; the root docs remain the fine-grained detail.

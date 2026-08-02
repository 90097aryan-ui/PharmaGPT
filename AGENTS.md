# PharmaGPT — AGENTS.md

Status: reflects repository state as of 2026-08-02.
Authority: CLAUDE.md → FOUNDATION_ARCHITECTURE.md → PROJECT_MEMORY/ → source.

## Overview

PharmaGPT is a monolithic Flask 3 / SQLite / vanilla-JS pharmaceutical quality platform.
Google Gemini 2.5 Flash powers AI features.
Postgres (Supabase) dual-write scaffolding exists but **must not be activated** without Staging soak + live 2-company RLS isolation.

## Dev Environment

- Python: use `python3`; create a venv.
- Install: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements-dev.txt`.
- Run: `python3 pharmagpt/app.py` → `http://127.0.0.1:5000`.
- No Makefile, no frontend build step, no package.json.

## Build & Test

- Run tests: `python3 -m pytest`.
- Config: `pytest.ini` sets `testpaths = tests` and excludes `slow` by default.
- Tests use a throwaway SQLite file via `tests/conftest.py::db_path`; no external services required for unit tests.
- Do not invent commands; use pytest directly.

## Conventions

- One Flask Blueprint per domain in `pharmagpt/routes/`.
- One `*_database.py` per domain for raw `sqlite3` access; no ORM.
- One IIFE JS module per feature area under `pharmagpt/static/js/`.
- Structured AI generation uses `temperature=0.3`; chat uses default.
- Background jobs use `services/job_runner.py::ThreadPoolJobRunner`; do not introduce Celery.
- Additive database changes only; use guarded `_add_column_if_missing()` style when adding columns.
- Never drop/rename a table or column without explicit instruction + DECISIONS.md entry.

## Environment

- Copy `.env.example` to `.env` for local dev.
- Minimum required: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `FLASK_SECRET_KEY`.
- `FLASK_DEBUG=true` is local-only; never enable in shared/production environments.
- Storage paths default inside repo; override `DB_PATH`, `UPLOAD_FOLDER`, `GENERATED_DOCS_PATH` for persistent storage.

## Migration Flags (Do Not Flip)

These default to `sqlite` and are gated:
- `DATABASE_BACKEND`
- `PROJECTS_BACKEND`
- `KB_BACKEND`
- `EQUIPMENT_BACKEND`
- `QMS_BACKEND`

Do not set any to `dual` or `postgres` outside a completed Staging soak + 2-company RLS isolation check.

## Pitfalls

- `.env` and SQLite DBs are gitignored; never hand-edit generated docs for behavior changes.
- `start_server.bat` is Windows-only; use `python3 pharmagpt/app.py` on Linux.
- Some tests are marked `slow` and excluded by default; full suite runs can be long.
- No CI/CD exists; tests are run manually.
- Company Administration / Assume Company Context features exist in the working tree but have documented production-readiness gaps.

## Mandatory Workflow

Before coding:
1. Read `PROJECT_MEMORY/CLAUDE.md`, `FOUNDATION_ARCHITECTURE.md`, `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RELEASE_NOTES.md`.
2. Work on a feature branch; never modify `main` directly.
3. Never bypass tests; always run `python3 -m pytest`.
4. Never weaken security, tenant isolation, audit trails, e-signatures, or GAMP 5 / Annex 11 / 21 CFR Part 11 controls.
5. Update `PROJECT_MEMORY/` and root docs if behavior/architecture changes.
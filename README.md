# PharmaGPT

AI-powered pharmaceutical Digital Quality & Validation platform: an AI chat assistant (Google
Gemini), project- and knowledge-base-scoped document management with automated text extraction,
an AI validation document generator (URS/IQ/OQ/PQ/FMEA/CAPA/Deviation/Change Control/etc.), and a
Quality Management Suite (Document Control, Deviation Management, CAPA, Change Control, Risk).
Multi-tenant, with company-scoped RBAC and electronic-signature-gated approvals.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask 3.1.3, gunicorn 26.0.0 |
| Database | SQLite 3 today, source of truth (raw `sqlite3`, no ORM). Postgres (Supabase) migration in progress — see [Database migration status](#database-migration-status) |
| AI | `google-genai`, model `gemini-2.5-flash` |
| Document generation | `python-docx` |
| Document extraction | multi-engine PDF/DOCX/XLSX text extraction with fallback (`pypdf`, `pdfplumber`, `PyMuPDF`, `openpyxl`) |
| Frontend | Vanilla JavaScript SPA, no framework, no build step |
| Background jobs | `concurrent.futures.ThreadPoolExecutor` |
| Testing | pytest |
| Deployment | Render (gunicorn + persistent disk) |

## Local setup

```bash
python -m venv venv
./venv/Scripts/pip install -r requirements-dev.txt   # includes requirements.txt + pytest
cp .env.example .env   # fill in GEMINI_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY at minimum
./venv/Scripts/python pharmagpt/app.py                # http://127.0.0.1:5000
```

See [.env.example](.env.example) for every environment variable the app reads, which are
required vs optional, and what each gates.

## Running tests

```bash
./venv/Scripts/python -m pytest
```

390 tests, all passing as of the last full run (2026-07-23; see `PHASE_1_IMPLEMENTATION_REPORT.md`
for the full run log). Tests use a throwaway SQLite file per test (`tests/conftest.py`'s `db_path`
fixture) — no external services required.

## Deployment

Deploys to [Render](https://render.com) from `render.yaml` (gunicorn + a persistent disk for
SQLite/uploads/generated documents). See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full
production checklist, and [docs/MIGRATION.md](docs/MIGRATION.md) for the SQLite → Postgres
migration status and cutover procedure.

## Database migration status

The app is mid-migration from SQLite (current source of truth) to Postgres (Supabase). Every
domain (Projects, Knowledge Base, Equipment, QMS) has dual-write code already built and flag-gated
(default `sqlite`, optionally `dual`), but the flags have **not** been flipped to `dual` in any
deployed environment — cutover is gated on an extended Staging soak plus a 2-company RLS isolation
spot-check per domain, and neither has run yet. Full detail: [docs/PHASE3_EXECUTION_PLAN.md](docs/PHASE3_EXECUTION_PLAN.md),
[docs/PHASE3_FLAGS.md](docs/PHASE3_FLAGS.md), [docs/MIGRATION.md](docs/MIGRATION.md).

## Further documentation

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — production deployment guide and checklist
- [docs/MIGRATION.md](docs/MIGRATION.md) — SQLite → Postgres migration status and cutover steps
- [PROJECT_MEMORY/](PROJECT_MEMORY/) — authoritative, actively-maintained architecture/status/decisions record
- [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [DATABASE.md](DATABASE.md), [API.md](API.md) — deeper reference

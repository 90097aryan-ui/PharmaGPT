import os
from dotenv import load_dotenv

# Load the .env file from the project root (one level up from this file)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Gemini model to use across the entire application
GEMINI_MODEL = "gemini-2.5-flash"

# API key loaded from .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Flask secret key — used to sign session cookies
# In production, replace this with a long random string stored in .env
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "pharmagpt-dev-secret-key")

# Flask debug mode — set to False in production
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"

# Port the Flask app will run on
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))

# ── Database backend (Phase 3 migration seam) ─────────────────────────────────
# "sqlite" (default) — every domain still reads/writes pharmagpt.db, unchanged.
# "postgres" — reserved for later Phase 3 sub-phases (3.2+) to flip per domain
# once that domain's Postgres tables are populated and parity-verified. Setting
# this alone does not change any behavior yet; no code reads it until a
# domain's dual-write cutover lands. See docs/PHASE3_EXECUTION_PLAN.md.
DATABASE_BACKEND = os.getenv("DATABASE_BACKEND", "sqlite")

# Per-domain migration flags (Phase 3.2+, docs/PHASE3_EXECUTION_PLAN.md).
# Each domain gets its own flag so one domain's cutover never gates another's.
#
# Projects specifically supports only two states, not three, on inspection:
#   "sqlite" (default) — unchanged today's behavior, reads+writes SQLite only.
#   "dual"             — SQLite stays the read source of truth; every write
#                         also best-effort syncs to Postgres (failures logged,
#                         never raised, SQLite write is never blocked).
# A "postgres" (read-cutover) state is deliberately not offered yet: the
# target `projects` table (DATABASE_ARCHITECTURE.md §4.2) drops the
# equipment_name/manufacturer/department/validation_type/model/location
# fields (that data's home becomes the Equipment Library, Phase 3.4) and
# uses uuid ids where every route today uses `<int:project_id>` — flipping
# reads over now would change the API shape and break the frontend, not
# just move where the bytes live. Read cutover is revisited once Equipment
# (3.4) and the route/id-shape work land, not silently attempted here.
PROJECTS_BACKEND = os.getenv("PROJECTS_BACKEND", "sqlite")

# KB_BACKEND: same two states as PROJECTS_BACKEND. Dual-write covers create
# and delete (as "archive" — see pharmagpt/db/kb_repo.py, Postgres RESTRICTs
# hard-deleting a documents row that still has document_versions, and the
# target architecture treats deletion as a lifecycle transition anyway).
# Extracted-text sync is NOT covered by dual-write in this iteration — that
# arrives asynchronously via the shared services/document_processor.py
# pipeline, which is not touched here (roadmap Migration Principle 1: zero
# unnecessary rewrites to shared, tenancy-agnostic infrastructure). A
# one-time copy happens at backfill time; ongoing drift is expected and
# accepted until a later increment wires the extraction-completion path.
KB_BACKEND = os.getenv("KB_BACKEND", "sqlite")

# EQUIPMENT_BACKEND: same two states. Dual-write covers create/update and a
# best-effort real delete (not an archive — equipment has no lifecycle/
# soft-delete field in the target schema, unlike documents; see
# pharmagpt/db/equipment_repo.py). equipment_links dual-write is scoped to
# source_type='kb' links only, and only once the linked KB document already
# has a Postgres mirror (kb_documents.postgres_id) — 'project'-sourced links
# have no Postgres-side document to point at yet (project-generated
# documents are roadmap Phase 9, out of this plan's 3.1-3.6 scope), so those
# are skipped and logged, not silently dropped.
EQUIPMENT_BACKEND = os.getenv("EQUIPMENT_BACKEND", "sqlite")

# ── Document upload settings ──────────────────────────────────────────────────

# Folder where uploaded files are stored, organised as uploads/{project_id}/
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")

# Maximum upload size in bytes (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# File types users are allowed to upload
ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt"}

# ── Document extraction engine settings ───────────────────────────────────────
# See pharmagpt/services/document_processor.py and services/extraction/ for
# how these are used.

# Maximum seconds a single page may take in a single engine before the
# pipeline abandons it and falls back to the next engine (or skips the page).
PAGE_TIMEOUT_SECONDS = int(os.getenv("PAGE_TIMEOUT_SECONDS", 10))

# Thread pool size for background extraction jobs (services/job_runner.py).
EXTRACTION_WORKERS = int(os.getenv("EXTRACTION_WORKERS", 2))

# Run gc.collect() + drop cached page objects every N pages during extraction,
# bounding peak memory on very large (1000+ page) documents.
GC_INTERVAL_PAGES = int(os.getenv("GC_INTERVAL_PAGES", 20))

# Persist extraction progress to SQLite every N pages (avoids a DB write per
# page on very large documents while keeping the progress UI responsive).
PROGRESS_WRITE_EVERY_N_PAGES = int(os.getenv("PROGRESS_WRITE_EVERY_N_PAGES", 5))

# ── URS AI generation settings ────────────────────────────────────────────────
# See services/urs_generation_job.py. Generation is batched into small Gemini
# calls run on job_runner's thread pool instead of one giant streamed request,
# so no single call risks exceeding gunicorn's --timeout (Procfile/render.yaml).

# Max requirement sections sent to Gemini in a single generate_content() call.
URS_GENERATION_BATCH_SIZE = int(os.getenv("URS_GENERATION_BATCH_SIZE", 2))

# Log a warning if a single Gemini call for one batch takes longer than this.
URS_GENERATION_SLOW_WARNING_SECONDS = int(os.getenv("URS_GENERATION_SLOW_WARNING_SECONDS", 20))

# Extra attempts for a batch after malformed/truncated Gemini output (parsing
# failures only — a genuine API error is never retried). 2 => 3 attempts total.
URS_GENERATION_MAX_RETRIES = int(os.getenv("URS_GENERATION_MAX_RETRIES", 2))

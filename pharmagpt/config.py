import logging
import os
import secrets
from dotenv import load_dotenv

# Load the .env file from the project root (one level up from this file)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)


class SecurityConfigError(RuntimeError):
    """Raised at startup when a security-critical secret is missing or
    invalid outside development mode. Never silently substitutes a default
    for anything security-relevant — see FLASK_SECRET_KEY below, and
    BACKUP_ENCRYPTION_KEY's docstring further down for the same principle
    applied to backups."""


# Gemini model to use across the entire application
GEMINI_MODEL = "gemini-2.5-flash"

# API key loaded from .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ── AI provider selection (pharmagpt/providers/factory.py) ───────────────────
# "gemini" (default) — unchanged behavior, routes through google.genai.Client.
# "nemotron" — routes all AI generation through NVIDIA's Nemotron 3 Ultra API
# instead (see pharmagpt/providers/nemotron_client.py). Requires
# NVIDIA_API_KEY and NVIDIA_MODEL below; pharmagpt/state.py fails fast at
# startup if either is missing while this is set to "nemotron".
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()

# NVIDIA API key for the Nemotron provider (https://build.nvidia.com/).
# Only required when AI_PROVIDER=nemotron; unused otherwise.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

# Exact NVIDIA model catalog slug to call. No hardcoded default — must be
# set explicitly when AI_PROVIDER=nemotron so the app never silently calls
# the wrong model. Verified current slug for Nemotron 3 Ultra on the hosted
# catalog API (build.nvidia.com), at time of writing: "nvidia/nemotron-3-ultra-550b-a55b".
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL")

# Flask debug mode — set to False in production.
# Defaults to False (fail-safe): an accidentally-unset env var in production
# must never silently enable the Werkzeug interactive debugger (arbitrary
# code execution) or disable the secure session cookie flag (see app.py's
# SESSION_COOKIE_SECURE = not FLASK_DEBUG). Local dev sets FLASK_DEBUG=true
# explicitly in .env. Computed before FLASK_SECRET_KEY below, which needs it.
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# Flask secret key — signs session cookies (and, by extension, the
# session-cookie auth fallback described in auth/middleware.py). Deliberately
# has NO hardcoded fallback: a shared/production process signing sessions
# with a well-known default string lets anyone forge a valid session cookie
# (previously flagged as a Critical finding — docs/CODE_REVIEW.md §1.2
# "Hardcoded Fallback Secret Key", SECURITY_REVIEW.md "Hardcoded Secrets /
# Credentials").
#   - Production (FLASK_DEBUG=false, the default): a missing key is fatal —
#     the application refuses to start rather than sign sessions with no
#     secret, or a re-derived/guessable one.
#   - Development (FLASK_DEBUG=true): a random key is generated in memory
#     for this process only — never written to disk, never persisted across
#     restarts — so `flask run` / pytest still work out of the box. A
#     warning is logged so it is never mistaken for a real, stable value.
# FLASK_SECRET_KEY_SOURCE records which path was taken, for the Security
# Configuration Status page (pharmagpt/services/security_config.py) — it is
# never the secret value itself.
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if FLASK_SECRET_KEY:
    FLASK_SECRET_KEY_SOURCE = "env"
elif FLASK_DEBUG:
    FLASK_SECRET_KEY = secrets.token_hex(32)
    FLASK_SECRET_KEY_SOURCE = "generated"
    logger.warning(
        "FLASK_SECRET_KEY is not set. Generated a temporary, in-memory-only "
        "development secret — sessions will not survive a restart, and this "
        "value is NOT suitable for production. Set FLASK_SECRET_KEY in .env "
        "to a long random value to silence this warning."
    )
else:
    raise SecurityConfigError(
        "Startup aborted: FLASK_SECRET_KEY is not set. Signing session "
        "cookies with no configured secret is a critical security risk "
        "(session forgery) and is refused outside development mode. Set "
        "FLASK_SECRET_KEY to a long random value in the environment, or set "
        "FLASK_DEBUG=true for local development only."
    )

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

# QMS_BACKEND: same two states, one flag covering all four Phase 3.5 record
# types (deviations, capas, change_controls, risk_assessments) — they are
# one milestone in docs/PHASE3_EXECUTION_PLAN.md, not four, and share one
# repo module (pharmagpt/db/qms_repo.py). Dual-write covers only the flat
# top-level fields with a column in DATABASE_ARCHITECTURE.md §4.7's target
# tables (title, status, project_id) plus audit_trail entries for the three
# QMS types that write one on create (deviation/capa/change_control — risk
# assessments use a separate, SQLite-only risk_approval table today, not
# qms_audit_trail, so there's no audit entry to mirror for that type here).
# The current build's much richer sub-structures — investigation
# (fishbone/5-why/timeline), impact assessments, CAPA actions/effectiveness
# checks, change-control impact/actions/links — have no table in the frozen
# target schema (DATABASE_ARCHITECTURE.md §4.7 defines only the four flat
# tables) and are intentionally NOT dual-written; they remain SQLite-only,
# same documented-gap treatment as Projects' equipment_name (3.2).
# attachments/comments/approvals dual-write is deferred entirely in this
# iteration — audit_trail already captures every state-changing action
# with actor/timestamp/reason, which is the regulator-relevant minimum;
# the remaining shared tables are a follow-up, not silently skipped.
QMS_BACKEND = os.getenv("QMS_BACKEND", "sqlite")

# ── Document upload settings ──────────────────────────────────────────────────

# Folder where uploaded files are stored, organised as uploads/{project_id}/
#
# IMPORTANT — deployment note: same ephemeral-filesystem hazard as DB_PATH
# above. The default below sits inside the pharmagpt/ package folder, which
# is wiped on every Render redeploy/restart unless overridden. Set
# UPLOAD_FOLDER to a directory on the mounted persistent disk in production
# (see render.yaml); it defaults to the in-package path for local dev.
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER") or os.path.join(os.path.dirname(__file__), "uploads")

# Maximum upload size in bytes (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# File types users are allowed to upload. csv/jpg/jpeg/png/mp4/mov added for
# Investigation Case Evidence (Phase 2 Part 2 — Photos, Videos, CSV exports);
# additive only, every existing upload path keeps working unchanged.
ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt", "csv", "jpg", "jpeg", "png", "mp4", "mov"}

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

# ── Backup & Recovery (services/backup_service.py) ────────────────────────────
# Remediates the Compliance Matrix's Critical "Backup & Recovery" finding —
# the production SQLite database previously had no automated backup at all.
# See docs/BACKUP_ARCHITECTURE.md for the full design and docs/BACKUP_SOP.md
# for the operating procedure. Purely additive: nothing here is read by any
# existing route, RBAC rule, audit-trail write path, or e-signature logic.

# Root directory backups are written to. Defaults next to the DB on the same
# mounted persistent disk in production (see render.yaml) — see the "Remaining
# risks" note in docs/BACKUP_ARCHITECTURE.md about same-disk backups not being
# a substitute for an offsite copy (BACKUP_OFFSITE_DIR below).
BACKUP_DIR = os.getenv("BACKUP_DIR") or os.path.join(os.path.dirname(__file__), "..", "backups")

# Optional second location (e.g. a second mounted disk or network share) each
# verified backup is additionally copied to. Unset by default — same-disk-only
# backup until an operator configures this; scripts/run_backup.py logs a
# CRITICAL warning on every run while it is unset (see docs/BACKUP_SOP.md).
BACKUP_OFFSITE_DIR = os.getenv("BACKUP_OFFSITE_DIR")

# Symmetric encryption key (Fernet — cryptography package, already a pinned
# dependency) protecting backup archives at rest. Deliberately has NO default
# value — same principle FLASK_SECRET_KEY above now also follows (its dev
# fallback was flagged as a Critical gap in the Compliance Matrix — CVE-class
# risk if it ever reached prod unset — and has since been removed): a
# security-critical secret must never silently default in any environment,
# since an attacker who obtained a default key could read every past backup.
# backup_service.py raises BackupConfigError immediately if this is unset
# when a backup/restore/verify actually runs. Generate one with
# scripts/generate_backup_key.py and store it in a secrets vault — never in
# the backup directory itself.
BACKUP_ENCRYPTION_KEY = os.getenv("BACKUP_ENCRYPTION_KEY")

# How often scripts/run_backup.py is expected to run (Render Cron Job / OS
# cron — see render.yaml). This value does not itself schedule anything; it
# is used to (a) compute the retention cutoffs below and (b) let the
# freshness check flag a stale backup (no successful run within 2x this
# interval) independently of whether the scheduler is actually still firing.
BACKUP_FREQUENCY_HOURS = int(os.getenv("BACKUP_FREQUENCY_HOURS", 6))

# Explicit operator acknowledgement that an external scheduler (Render Cron
# Job, OS cron, etc.) has actually been wired up to run scripts/run_backup.py
# — the running Flask process has no way to independently observe an
# external cron process, so this is a statement of configured intent, not a
# live health check. Defaults to "false" (fail-safe: the dashboard should
# never claim scheduling is healthy unless an operator has said so) — see
# get_configuration_status() in services/backup_service.py.
BACKUP_SCHEDULER_ENABLED = os.getenv("BACKUP_SCHEDULER_ENABLED", "false").lower() == "true"

# Rolling short-term retention (BACKUP_DIR/snapshots/) — every run.
BACKUP_SNAPSHOT_RETENTION_DAYS = int(os.getenv("BACKUP_SNAPSHOT_RETENTION_DAYS", 7))

# Long-term retention (BACKUP_DIR/daily/) — first successful run of each
# calendar day is promoted here. Default aligns with a 1-year GMP working
# retention window; the customer's actual regulatory record-retention
# requirement (often much longer) should override this via the env var.
BACKUP_DAILY_RETENTION_DAYS = int(os.getenv("BACKUP_DAILY_RETENTION_DAYS", 365))

# Optional generic webhook (Slack/Teams/PagerDuty/Opsgenie-compatible
# incoming-webhook JSON POST, or any custom endpoint) notified on backup
# failure and on stale-backup detection. Unset by default — see
# docs/BACKUP_SOP.md "Remaining risk" note; failures still always log at
# CRITICAL and surface on the /admin/backup dashboard either way.
BACKUP_ALERT_WEBHOOK_URL = os.getenv("BACKUP_ALERT_WEBHOOK_URL")

# Direct Postgres connection string for the Supabase project (Settings ->
# Database -> Connection string on the Supabase dashboard). Optional: not
# currently part of this app's configuration anywhere else (the app only
# ever talks to Supabase via PostgREST — see services/supabase_client.py).
# When set AND the `pg_dump` binary is on PATH, backup_service.py takes a
# logical pg_dump in addition to the PostgREST-based table export below,
# which runs regardless (no extra infra required). See docs/BACKUP_SOP.md.
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

# Live, populated Postgres tables backed up via PostgREST (service-role
# client) as JSON, one file per table. Deliberately excludes the much larger
# Phase 3 target-schema tables from migrations/0004_core_schema_up.sql
# (projects, documents, equipment, deviations, capas, ...) — those are
# confirmed dormant (every *_BACKEND flag defaults to "sqlite"; see
# docs/PHASE3_EXECUTION_PLAN.md) and dumping empty tables would only add
# noise and false confidence.
#
# List verified empirically (2026-08-07, this app's own dev Supabase
# project) by actually running a backup, not just read from migration
# files: migrations/0001_identity_tenancy_up.sql's tables are all present
# and populated (companies, roles, users, company_settings,
# break_glass_access), as are the 0014 org-structure tables (departments,
# modules, workflow_roles, user_departments, user_module_permissions) and
# the Phase 3.5 audit_trail mirror. The migrations/0015_rbac_org_framework_up.sql
# tables (designations, approval_levels, rbac_permissions, rbac_roles,
# rbac_role_permissions, rbac_user_roles, rbac_audit_log) returned
# PGRST205 "table not found in schema cache" against that live project —
# i.e. migration 0015 has NOT actually been applied there yet, confirming
# what docs/RBAC_FRAMEWORK.md could only describe as unverifiable from code
# alone. Add those 7 back to this list once 0015 is applied to the target
# Supabase project; until then, listing them here would either error on
# every run (if PostgREST 404s hard) or silently produce empty files —
# per-table failures are caught and logged rather than aborting the whole
# backup either way, so this list is a completeness setting, not a safety one.
POSTGRES_BACKUP_TABLES = [
    "companies", "roles", "users", "company_settings", "break_glass_access",
    "departments", "modules", "workflow_roles", "user_departments",
    "user_module_permissions", "audit_trail",
]

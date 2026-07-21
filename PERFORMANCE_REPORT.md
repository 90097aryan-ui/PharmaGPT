# PharmaGPT — Performance Review

Scope: Flask + SQLite/Postgres dual-write, multi-tenant SaaS, Gemini AI document
generation. Read-only review — no code was modified. All line numbers refer to
the current state of the repository at `D:\PharmaAgent`.

## Executive Summary

The codebase is in an active SQLite → Postgres (Supabase) migration ("Phase 3
dual-write"). The Postgres schema itself (`migrations/0004_core_schema_up.sql`)
is well-indexed — every tenant table has a `company_id` index plus compound
`(company_id, status)` indexes where needed, and RLS uses the standard
`stable security definer` helper-function pattern, which is not a per-row
performance trap. The real risk is concentrated in three places:

1. **Every authenticated request pays two blocking Supabase network round
   trips** (token verification + a `users` profile `SELECT`) with zero
   caching, via `pharmagpt/auth/context.py`'s `resolve_tenant_context()`,
   called from `pharmagpt/auth/middleware.py` on literally every request.
2. **Six of seven AI-generation endpoints still stream Gemini output
   synchronously inside the HTTP request** (`stream_with_context`), the exact
   pattern that URS generation was deliberately moved *off* of after it caused
   production `WORKER TIMEOUT` crashes on Render (`Procfile`:
   `--workers=2 --threads=4 --timeout=60`, only 8 total request slots).
   Only `routes/urs.py` was fixed; `qms_documents.py`, `risk.py`, `qual.py`,
   `report.py`, `validation.py`, and `chat.py` were not.
3. **`pharmagpt/risk_database.py` leaks a SQLite connection on every single
   call** — all 15 of its functions call `get_connection()` and never
   `conn.close()`, unlike every other `*_database.py` module in the codebase
   (all of which close correctly).

Beyond that: the legacy SQLite modules (10 of 11) define **no secondary
indexes at all** on foreign-key columns, so every filtered list/lookup query
is a full table scan — fine at today's data volume, not fine as tenants
accumulate history. There is one confirmed N+1 pattern
(`equipment_database.py::list_equipment_documents`), and the document
extraction pipeline has good bounded-memory design (page-by-page, periodic
`gc.collect()`, per-page timeout) but still accumulates the full extracted
text of a document in memory before persisting it.

---

## Findings by Category

### 1. N+1 Query Patterns

| # | Finding | Location | Severity |
|---|---------|----------|----------|
|1.1| `list_equipment_documents()` fetches all links for an equipment record with one query, then issues **one additional `SELECT` per link** (against `kb_documents` or `documents`) inside a Python `for` loop to resolve display title/file type. | `pharmagpt/equipment_database.py:221-255` (loop at `233-252`) | Low–Medium (SQLite today; would become Medium–High if/when mirrored into the Postgres repo layer, since each `SELECT` becomes a network round trip via PostgREST instead of a local file read) |

Everywhere else that returns "list + related data," the code already does the
right thing with a single `JOIN`/aggregate query instead of looping:
- `database.py::get_project_documents` (`577-593`) — one query, `LEFT JOIN document_text`.
- `database.py::get_all_document_texts` (`701-721`) — one query, `JOIN documents`.
- `database.py::get_project_insights` (`724-768`) and `get_dashboard_stats`
  (`1009-1089`) — aggregate queries, not per-row loops (though see 3.3 below
  for a related connection-count issue in the latter).
- `qual_database.py::build_traceability_matrix` (`950-997`) — one query for
  test cases, then pure in-memory Python looping (no further DB calls).

**Recommendation:** batch `list_equipment_documents()`'s per-link lookups into
two `WHERE id IN (...)` queries (one for `kb`-sourced links, one for
`project`-sourced links), keyed by the distinct `source_id`s already in hand
from the first query.

---

### 2. Missing Indexes

**Postgres (`migrations/0004_core_schema_up.sql`) — in good shape.** Every
tenant-scoped table has `company_id` indexed, and the tables queried by
status also get a compound index, e.g. `idx_projects_company_id_status`
(line 41), `idx_documents_company_id_status` (130),
`idx_documents_company_id_project_id` (131), `idx_deviations_company_id_status`
(211), `idx_capas_company_id_status` (224), `idx_ai_jobs_company_id_status`
(351). `search_index` has a GIN index for full-text search (395). No gaps
found here. RLS's `current_company_id()` helper (`migrations/0005_projects_rls_up.sql:19-27`)
is `stable security definer`, the standard Supabase pattern — not a per-row
re-evaluation risk.

**Legacy SQLite — the real gap.** Outside `equipment_database.py`'s two
indexes and `qms_database.py`'s polymorphic `(record_type, record_id)`
indexes, **no other SQLite table in the app defines a single secondary
index**, despite every one of them being queried by a foreign-key-style
column:

| Table | Filtered-by column(s) with no index | Defined in |
|---|---|---|
| `messages` | `project_id` (`database.py:534`) | `database.py:109-116` |
| `documents` | `project_id` (`database.py:588`) | `database.py:126-135` |
| `document_text` | `document_id`, `project_id` | `database.py:143-154` |
| `urs_requirements`, `urs_versions`, `urs_approvals` | `project_id`/`urs_id` | `urs_database.py:54-109` |
| `qual_protocols`, `qual_test_cases`, `qual_executions`, `qual_deviations`, `qual_attachments`, `qual_approvals`, `qual_versions`, `qual_ai_reviews` | `qual_id` | `qual_database.py:25-215` |
| `risk_items`, `risk_actions`, `risk_approval` | `assessment_id` | `risk_database.py:485-575` |
| `qms_capa_actions`, `qms_capa_effectiveness` | `capa_id` | `qms_database.py:181-214` |
| `qms_deviation_investigation`, `qms_deviation_impact`, `qms_deviation_capa_link` | `deviation_id` | `qms_database.py:244-280` |
| `qms_change_control_impact`, `qms_change_control_actions`, `qms_change_control_links` | `change_control_id` | `qms_database.py:312-350` |
| `val_report_sections`, `val_report_approvals`, `val_report_versions`, `val_report_ai_reviews` | `report_id` | `report_database.py:74-120` |

Severity: **Medium**. SQLite will silently full-scan these tables on every
lookup. At current pilot-scale data volumes this is invisible; it becomes a
real, user-visible slowdown once any single project/qualification/risk
assessment accumulates hundreds of child rows, or once the sqlite file itself
grows large enough that OS page cache no longer covers it.

---

### 3. Connection Usage

**3.1 — Confirmed connection leak: `pharmagpt/risk_database.py` (High severity).**
Every one of this module's 15 functions calls `get_connection()` and never
calls `conn.close()` — not even via a `with` block that would at least commit
correctly (SQLite's `with conn:` context manager only manages
commit/rollback, it does **not** close the connection). Confirmed by
structural analysis of all `def`-blocks in the file:

```
create_assessment, get_assessment, get_all_assessments, update_assessment,
delete_assessment, set_assessment_postgres_id, get_dashboard_stats, get_items,
save_items, get_library, add_library_entry, get_actions, upsert_action,
get_approval_trail, add_approval_entry
```
e.g. `get_assessment()` (`risk_database.py:58-68`) and `get_dashboard_stats()`
(`risk_database.py:149-193`) both open a connection and return without
closing it. Every *other* `*_database.py` module in the codebase (`qual_`,
`report_`, `urs_`, `qms_`, `equipment_`, plus the four `qms_*_database.py`
files, and `database.py` itself) closes its connections correctly — this is
an isolated regression in one file, not a systemic pattern. Under sustained
concurrent load (`--workers=2 --threads=4`), unclosed connections rely on
Python GC to eventually finalize the underlying SQLite file handle, which is
non-deterministic timing and can hold WAL locks/file descriptors open longer
than necessary, risking "database is locked" contention and file-descriptor
growth.

**3.2 — No connection pooling for SQLite (Low–Medium, by design but worth
flagging).** Every CRUD function across `database.py` and the ten
`*_database.py` modules opens a brand-new `sqlite3.connect()`
(`database.py::get_connection`, lines 57-73) and closes it at the end of that
one function — there is no per-request connection reuse (e.g. via
`flask.g`). Each new connection re-runs three `PRAGMA` statements
(`foreign_keys`, `journal_mode`, `busy_timeout`). This is cheap for a local
file but adds up: `get_dashboard_stats()` alone
(`database.py:1009-1089`) opens and closes **six separate connections**
to serve one logical page load, when one connection reused across all six
queries would do the same work with a sixth of the connect/PRAGMA overhead.

**3.3 — No pooling for Postgres/Supabase (Medium).**
`get_authenticated_client()` (`pharmagpt/services/supabase_client.py:21-36`)
and `get_anonymous_client()` (`39-48`) both explicitly create a **fresh
`supabase-py` `Client`** (and therefore a fresh underlying `httpx` client) on
every single call, by design ("no shared client instance may accumulate one
user's token"). There is no SQLAlchemy usage anywhere in the repo and no
pool-size/keep-alive configuration for the Postgres path at all. In
`PROJECTS_BACKEND=dual`/`KB_BACKEND=dual`/etc. mode, a single request that
does a dual-write (`routes/projects.py::_dual_write_create`, `41-58`) mints at
least one new client for the write and `auth/context.py` mints another for
the auth check earlier in the same request — no connection reuse even within
one request.

**3.4 — Auth resolution has no caching and is the single biggest per-request
cost (High).** `pharmagpt/auth/middleware.py`'s `before_request` hook
(`62-96`) calls `resolve_tenant_context(access_token)`
(`pharmagpt/auth/context.py:35-81`) on **every non-exempt request**. That
function does, per request:
  1. `get_authenticated_client(access_token)` — a fresh Supabase client (3.3).
  2. `client.auth.get_user(access_token)` (`context.py:49`) — a blocking
     network call to Supabase Auth.
  3. `client.table("users").select(...).eq("id", ...).maybe_single().execute()`
     (`context.py:57-63`) — a second blocking network call, a `users` +
     `roles` join via PostgREST.

  There is no cache of any kind (not even a short-TTL in-memory one) mapping
  a token/user id to its already-resolved `TenantContext`. Every route in the
  app pays this fixed ~2-round-trip tax before doing any of its own work.

---

### 4. Memory Usage on Large File Processing

`pharmagpt/services/extraction/pipeline.py::extract_document`
(`133-243`) is, overall, a well-designed bounded-memory pipeline:
- Iterates pages one at a time rather than loading the whole document
  (`184-209`).
- Runs `gc.collect()` every `GC_INTERVAL_PAGES` pages (default 20,
  `config.py:117`) and again unconditionally in the `finally` block
  (`pipeline.py:208-209, 216`).
- Wraps every page extraction in a hard `PAGE_TIMEOUT_SECONDS` (default 10,
  `config.py:110`) wall-clock timeout via a **fresh thread per attempt**
  (`pipeline.py:50-78`), specifically to avoid one hung call blocking the
  fallback engine's attempt on the same page.

Two residual concerns, both **Low–Medium**:

- **Full-document text is held in memory at the end.** Every page's text is
  appended to a Python list `texts` (`pipeline.py:180, 195-196`) and then
  joined into one `full_text` string (`218`) before being handed back to
  `_finalize()` in `document_processor.py` (`150-173`), which writes it as a
  single `TEXT` column via `save_document_text()` /
  `update_kb_document_text()`. For a 1000+ page document this can be tens of
  megabytes of text held fully in RAM at once (in addition to whatever the
  active PDF engine itself is holding), and written as one blob rather than
  incrementally. `GC_INTERVAL_PAGES` bounds *page-object* memory, not the
  accumulated text.
- **Abandoned per-page threads on timeout are never cleaned up.**
  Documented as a known, accepted limitation
  (`pipeline.py:21-31`): CPython cannot forcibly kill a thread, so a page that
  times out leaves its worker thread running in the background until it
  naturally finishes or errors. A document with many slow/hanging pages
  across multiple engine fallbacks can accumulate several abandoned daemon
  threads concurrently, each still holding whatever memory/file handle the
  engine allocated for that attempt.

`config.py`'s tuning knobs are all reasonable defaults for the current
single-dyno deployment: `GC_INTERVAL_PAGES=20` (117), `PAGE_TIMEOUT_SECONDS=10`
(110), `EXTRACTION_WORKERS=2` (113), `PROGRESS_WRITE_EVERY_N_PAGES=5` (121, an
explicit, well-reasoned choice to avoid one DB write per page).

---

### 5. Caching Opportunities

- **Biggest gap:** the per-request tenant/company/role resolution described
  in 3.4 — resolved fresh via two network calls on every request, with no
  cache at all. This is the clearest, highest-value caching opportunity in
  the codebase.
- **Positive existing pattern, worth extending:** `pharmagpt/state.py`
  already does caching correctly in two places — the Gemini client is a
  true module-level singleton (`state.py:22`), and per-project chat history
  is loaded from SQLite once and kept in `history_cache` for the life of the
  process (`state.py:29-45`), explicitly to avoid a DB round trip on every
  chat turn. The tenant-context problem above could use the same
  "resolve once, cache in a module-level dict, invalidate on the natural
  trigger" shape (e.g. keyed by user id with a short TTL, since a token itself
  shouldn't be used as a long-lived cache key).
- `equipment_service.get_equipment_type_catalog()`
  (`services/equipment_service.py:32-35`) reads a static in-memory
  `EQUIPMENT_REGISTRY` dict on every call — already effectively free, no
  action needed.
- `database.py::get_kb_folder_counts()` (`997-1004`) and
  `get_dashboard_stats()` (`1009-1089`) re-run full aggregate `GROUP BY`
  queries on every dashboard/KB sidebar load. Not urgent at current scale,
  but both are good short-TTL (e.g. 30-60s) cache candidates once table sizes
  grow, since neither needs to be real-time-accurate to the second.
- `risk_database.py::get_dashboard_stats()` (`149-193`) additionally does
  wasted work independent of caching: it runs a `GROUP BY status, priority`
  query (`151`) whose result (`rows`) is **never used**, then separately
  fetches `SELECT * FROM risk_assessments` in full (`159`, all columns
  including the `form_data`/`ai_review_data` JSON blobs) just to re-derive
  status/priority/type/department counts in a Python loop (`162-173`) — work
  SQL `GROUP BY`/`COUNT` could do directly, transferring far less data.

---

### 6. Background Job Architecture

**6.1 — Six AI-generation endpoints still block the request thread (High).**
`services/urs_generation_job.py`'s own module docstring (`1-47`) documents
that URS generation used to call Gemini's `generate_content_stream()` and
iterate it *inside* the HTTP request, holding a gunicorn worker for the whole
generation and routinely exceeding `--timeout=60` on Render, producing
`WORKER TIMEOUT` crashes. That module was rewritten to run on
`job_runner`'s thread pool with the frontend polling status instead
(`submit_generation_job`, `112-136`, wired into `routes/urs.py:270`).

That fix was **not** applied to six other AI-generation endpoints, which
still use `flask.stream_with_context` to stream Gemini output synchronously
within the request/response cycle — the exact pattern already known to cause
production timeouts:

| Route file | Line(s) | Endpoint |
|---|---|---|
| `pharmagpt/routes/qms_documents.py` | `104-130` | `POST /qms/documents/<id>/generate` |
| `pharmagpt/routes/risk.py` | `~250` (stream defined ~`200-249`) | AI risk-item generation |
| `pharmagpt/routes/qual.py` | `311` | AI generation |
| `pharmagpt/routes/report.py` | `230`, `293` | two AI generation/review endpoints |
| `pharmagpt/routes/validation.py` | `125` | AI generation |
| `pharmagpt/routes/chat.py` | `108` | chat message generation |

With `Procfile`/`render.yaml` both configured as
`gunicorn ... --workers=2 --threads=4 --timeout=60`, the app has **8 total
concurrent request slots**. Any of these six endpoints can occupy one of
those 8 slots for the full duration of a Gemini call (which the URS module's
own history shows can exceed 60s), simultaneously risking a worker-timeout
crash for that request and starving the other 7 slots for unrelated
requests (dashboard loads, CRUD, polling) for however long the generation
takes.

**6.2 — Shared thread pool sizing/contention (Medium).**
`services/job_runner.py`'s `ThreadPoolJobRunner` (`38-59`) is a single
module-level singleton (`job_runner`, line 80) sized by
`config.EXTRACTION_WORKERS` (default **2**, `config.py:113`). This one pool
is shared by two very different workloads:
- `services/document_processor.py::process_document_async` (`77-94`) —
  CPU/IO-heavy PDF/DOCX/XLSX page-by-page extraction, potentially minutes
  long for a 1000+ page document.
- `services/urs_generation_job.py::submit_generation_job` (`112-136`) —
  network-bound Gemini batch calls.

  With only 2 worker threads total, one long-running large-document
  extraction and one URS generation job compete directly for the same two
  slots — a second concurrent job of either kind queues behind whichever is
  already running, with no isolation between the two workloads. If the six
  endpoints in 6.1 are migrated to this same pattern (recommended), this
  contention will need to be resolved by either sizing the pool up or
  splitting it into two pools (e.g. one for extraction, one for AI
  generation) before adding that much more job volume onto it.

---

## Prioritized Recommendations

1. **(High)** Cache the resolved `TenantContext` (or at least the raw
   Supabase `auth.get_user` + `users` profile lookup) for a short TTL, keyed
   by access token or user id, in `pharmagpt/auth/context.py` /
   `middleware.py`. This removes two network round trips from every single
   request in the app — the highest-leverage single change available.
2. **(High)** Fix the connection leak in `pharmagpt/risk_database.py` — add
   `conn.close()` (or refactor to a context-manager helper shared with the
   other `*_database.py` modules) to all 15 functions.
3. **(High)** Extend the `job_runner` + status-polling pattern already proven
   out for URS generation (`services/urs_generation_job.py`,
   `routes/urs.py`) to the six remaining synchronous-SSE AI endpoints in
   `qms_documents.py`, `risk.py`, `qual.py`, `report.py`, `validation.py`,
   and `chat.py`, to eliminate the worker-timeout risk and stop tying up
   gunicorn request slots for the duration of a Gemini call.
4. **(Medium)** Add indexes on the foreign-key columns listed in Finding 2
   across the legacy SQLite modules (`urs_`, `qual_`, `risk_`, `qms_`,
   `report_database.py`) before per-tenant data volume grows large enough for
   the missing indexes to show up as user-visible latency.
5. **(Medium)** Once recommendation 3 lands, size or split `job_runner`'s
   thread pool (`config.EXTRACTION_WORKERS`) so document extraction and AI
   generation jobs don't contend for the same 2 worker threads.
6. **(Low–Medium)** Batch `equipment_database.py::list_equipment_documents()`'s
   per-link lookups (`233-252`) into two `IN (...)` queries instead of one
   query per link — cheap now, important to fix before this pattern is
   mirrored into `pharmagpt/db/equipment_repo.py`'s Postgres path, where each
   query is a network round trip rather than a local file read.
7. **(Low)** Replace `risk_database.py::get_dashboard_stats()`'s
   fetch-everything-then-count-in-Python approach (`159-173`) with SQL
   `GROUP BY`/`COUNT` aggregates (consistent with how the rest of the
   dashboard queries already work in `database.py::get_dashboard_stats()`),
   and drop the unused `GROUP BY` query at line 151.
8. **(Low)** Consider reusing one Supabase client per Flask request (stored
   on `flask.g`) instead of minting a new one in every `get_authenticated_client()`
   call within the same request, where multiple repo calls (auth check +
   dual-write) currently each create their own.
9. **(Low)** For extremely large documents, consider persisting extracted
   text incrementally (e.g. per-page appends) rather than accumulating the
   full document text in memory before one final write in
   `services/extraction/pipeline.py` (`180-220`).

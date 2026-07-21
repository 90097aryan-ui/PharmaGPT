# PharmaGPT Architecture Review

**Type:** Staff-engineer review of existing architecture (read-only — no code modified).
**Scope:** `D:\PharmaAgent` as of 2026-07-21, mid Phase 3 (SQLite→Postgres dual-write migration, sub-phases 3.1–3.5 shipped per `docs/PHASE3_EXECUTION_PLAN.md`).
**Method:** Read `docs/PLATFORM_ARCHITECTURE.md`, `docs/DATABASE_ARCHITECTURE.md`, `docs/PHASE3_EXECUTION_PLAN.md`, `FOUNDATION_ARCHITECTURE.md`, `pharmagpt/config.py`, then traced actual request flow through `pharmagpt/auth/`, `pharmagpt/routes/`, `pharmagpt/db/*_repo.py`, `pharmagpt/*_database.py`, `pharmagpt/services/`, `pharmagpt/app.py`, `render.yaml`/`Procfile`, and `migrations/`.

This review does not re-litigate the frozen target architecture in `PLATFORM_ARCHITECTURE.md`/`DATABASE_ARCHITECTURE.md`. It assesses the **gap between that target and what is actually running today**, since the codebase is mid-migration and the two diverge in load-bearing ways.

---

## Executive Summary

The target architecture (Supabase Auth, shared-schema + RLS multi-tenancy, unified document lifecycle, polymorphic audit trail) is well-designed and the Postgres-side scaffolding for it (migrations 0001–0009, `db/*_repo.py`, RLS policies) is real, reviewed-looking work, not vaporware. Authentication is fully wired: every request (with a small exempt list) passes through `auth/middleware.py`, which verifies a Supabase Auth token and resolves a `TenantContext` (`user_id`, `company_id`, `role`).

The problem is what happens **after** authentication. SQLite remains the sole read/write source of truth for every domain (Projects, Equipment, Knowledge Base, QMS) — Postgres is a best-effort side-write, not yet consulted for reads or enforcement. SQLite has **no `company_id` column and no row-level authorization of any kind**. The resolved `TenantContext` is used only to decide whether to attempt the Postgres side-write; it is never used to filter, scope, or authorize the SQLite queries that actually serve every request. Concretely: `GET /projects` returns every project in the database to any authenticated user regardless of company (`pharmagpt/routes/projects.py:101`), and every single-record route (`GET/PUT/DELETE /projects/<id>`, `/equipment/<id>`, `/kb/documents/<id>`, `/qms/deviations/<id>`, …) authorizes purely on "does this integer ID exist," not "does the caller's company own it." The four-role model (Super Admin/Company Admin/Reviewer/User) and its segregation-of-duties guarantee are likewise unenforced in code — role is read in exactly one place, for audit-log attribution text (`pharmagpt/routes/urs.py:88`), never for access control.

Compounding this, the QMS approval endpoint that is supposed to produce the GxP e-signature manifestation (actor, role, reason) takes `performed_by`, `role`, and `electronic_sig` straight from the client-supplied JSON body rather than the authenticated `g.tenant` (`pharmagpt/routes/qms_deviations.py:271-299`) — the audit trail's actor attribution is spoofable by any authenticated caller, not merely unenforced at the authorization layer.

If a second company is (or has been) onboarded while the app is in this state, there is no cross-tenant data leak *risk* — there is silent, ongoing cross-tenant data exposure, structurally, on every list/detail endpoint. This is the review's highest-priority finding by a wide margin; everything else here is secondary to it.

The dual-write mechanism itself is implemented consistently and safely with respect to *not breaking the app*: it never raises, never blocks the SQLite write, and is well-documented at every call site. But "safe for the user" and "safe for data integrity" are different properties — a Postgres write failure is `logger.exception()`'d to stdout and nothing else. There is no alerting, no dead-letter/retry queue, and no scheduled reconciliation (`render.yaml` defines no cron/worker service; parity checks are plain scripts, run by hand). Drift between SQLite and Postgres is real, expected by the plan's own docstrings (e.g., KB `extracted_text` is explicitly excluded from parity, `config.py:52-58`), and would only surface at the Phase 3.6 cutover gate if someone remembers to run the checker.

A second, independent, unrelated-to-tenancy risk: uploaded files (KB documents, project documents, generated documents) are stored under `pharmagpt/uploads/` — a path relative to the application package, not the persistent disk `render.yaml` mounts at `/var/data` for `DB_PATH`. Every file upload is wiped on Render restart/redeploy/idle-spindown, the exact failure mode the architecture doc (§15) and `database.py`'s own comments say has already been solved — solved for the database file, but not for the files it references.

None of this is a design-quality problem with the target architecture; it is an implementation-maturity gap consistent with being mid-migration. But two of these gaps (tenant isolation, actor-attribution spoofing) are precisely the two guarantees `PLATFORM_ARCHITECTURE.md` §2 calls non-negotiable, so they should be treated as blocking for any customer-facing multi-tenant milestone, not backlog items.

---

## 1. Authentication

**Risk: Low.** Well-implemented, matches the documented design.

- `pharmagpt/auth/context.py:35-81` (`resolve_tenant_context`) delegates all credential/session validity checking to Supabase (`client.auth.get_user`) rather than doing local JWT verification — the app never holds a signing secret more powerful than the anon key. This matches Design Principle 8 (prefer managed primitives).
- `pharmagpt/auth/middleware.py:62-96` installs a single `before_request` gate (`register_auth_middleware`), applied globally except a small allowlist (`/`, `/auth/login`, `/health`, `/favicon.ico`, `/static/*`) — confirmed wired in `pharmagpt/app.py:63`. This is good: uniform enforcement, not per-route decorators that are easy to forget on a new blueprint.
- Bearer-token-or-session-cookie dual channel (`pharmagpt/auth/middleware.py:70-96`, `pharmagpt/routes/auth.py:72-83`) exists for a real, narrow reason (plain `<a download>` navigations can't carry a custom header) and is scoped carefully: the header, when present, is always authoritative; the cookie is only consulted when no header exists at all. This is a reasonable, minimal-surface workaround, though it is a second authentication path to keep in sync and reason about during any future security review.
- `pharmagpt/services/supabase_client.py:21-36` creates a fresh Supabase client per call rather than a shared singleton — correctly called out in its own docstring as necessary because Flask serves concurrent requests from different users within one worker process; a shared client would leak one user's session/token into another's request. This is a subtle correctness point handled properly.
- Minor: `pharmagpt/config.py:15` — `FLASK_SECRET_KEY` falls back to a hardcoded literal (`"pharmagpt-dev-secret-key"`) if the env var is unset. `render.yaml:20-21` sets `generateValue: true` for this on the deployed target, so production-as-configured is fine, but any other deployment path (staging shortcuts, local-prod testing, a forked render.yaml) silently gets a public, guessable secret signing the session cookie that now also carries an access token. Low severity given the cookie's contents are independently re-verified by Supabase, but it's a footgun worth removing (no fallback, fail closed instead).

---

## 2. Authorization / Multi-Tenant Scoping

**Risk: Critical.** This is the review's central finding.

- `TenantContext.company_id` is resolved on every request (`pharmagpt/auth/context.py:75-81`) but is **only ever read in the dual-write helper functions** of each route file (e.g. `pharmagpt/routes/projects.py:44-46`, `pharmagpt/routes/equipment.py:44-46`, `pharmagpt/routes/knowledge_base.py:39-41`) to decide whether to attempt a Postgres side-write. It is never used to filter, scope, or authorize any SQLite read or write — and SQLite is the only backend that actually serves responses today.
- `pharmagpt/database.py` (1089 lines, the entire SQLite schema and query layer) has **zero occurrences of `company_id`** — confirmed by direct search. There is no tenant column to filter on even if a route wanted to.
- Concrete unscoped endpoints:
  - `GET /projects` → `db.get_all_projects()` returns every project row in the database to any authenticated user of any company (`pharmagpt/routes/projects.py:98-101`, `pharmagpt/database.py:438-445`).
  - `GET/PUT/DELETE /projects/<int:project_id>` authorize purely on row existence (`pharmagpt/routes/projects.py:139-171`) — no ownership check against the caller's company.
  - `GET/PUT/DELETE /equipment/<int:equipment_id>` and its document-link sub-routes — identical pattern (`pharmagpt/routes/equipment.py:183-259`).
  - `GET/PUT/DELETE /kb/documents/<id>` and `GET /kb/documents` (unfiltered list) — identical pattern (`pharmagpt/routes/knowledge_base.py:71-236`).
  - QMS routes (`qms_deviations.py`, `qms_capa.py`, `qms_change_control.py`) follow the same shape (confirmed via the same `company_id`/`g.tenant` grep — QMS route files only reference `g.tenant` inside their own dual-write helpers).
- IDs are sequential integers (SQLite `AUTOINCREMENT`), so this is not just "no authorization" but a directly enumerable IDOR: any authenticated user (any company, any role) can iterate `/equipment/1`, `/equipment/2`, ... and read or mutate another company's equipment, projects, KB documents, and QMS records.
- **Role-based authorization is equally absent.** A repo-wide search for role checks in `pharmagpt/routes/` found exactly one use of `tenant.role`, and it is for audit-log attribution text, not access control: `pharmagpt/routes/urs.py:88` (`return tenant.role or fallback`). There is no `require_role`/`require_permission` decorator anywhere in `pharmagpt/auth/` (confirmed — only `require_auth` exists, `pharmagpt/auth/decorators.py:28-45`). The four-role model and its "segregation of duties is architectural, not conventional" guarantee (`PLATFORM_ARCHITECTURE.md` §7) is fully unenforced: a `User` account can do anything a `Company Admin` can, and nothing stops the same account from authoring and approving the same record.
- **Actor attribution on approvals is spoofable, not just unauthorized.** `POST /qms/deviations/<id>/approval` (`pharmagpt/routes/qms_deviations.py:271-299`) takes `performed_by`, `role`, and `electronic_sig` directly from the request JSON body (`data.get("performed_by", "")`, `data.get("role", "")`, `data.get("electronic_sig", "")`) rather than from the authenticated `g.tenant`. Any authenticated caller can submit an approval claiming to be any named person with any role and any signature string. This directly undermines `PLATFORM_ARCHITECTURE.md` §17's "every entry captures ... actor" and Design Principle 4 ("every write is attributable and reconstructable") — for a GxP audit trail, this is a compliance-relevant defect, not a nice-to-have.
- Contrast: the Postgres-side repos (`pharmagpt/db/projects_repo.py:51-74`, `pharmagpt/db/qms_repo.py:59-69`) correctly scope every update/delete with `.eq("company_id", company_id)` in addition to relying on RLS, and RLS policies do exist in `migrations/0005_projects_rls_up.sql` etc. That correctness is real, but it currently only governs the side-write copy of the data, not the copy the application actually reads back to users.
- **Net effect:** the architecture's two-layer isolation model (§6: "application layer scopes, RLS enforces independently") is fully absent on layer 1 and not yet reachable on layer 2, for every read path in production today. This is the single highest-priority item in this report.

---

## 3. Repository Pattern Consistency

**Risk: Medium.**

- Two parallel data-access styles coexist by design, not by drift: legacy `pharmagpt/*_database.py` modules (`database.py`, `equipment_database.py`, `qms_deviation_database.py`, `qms_capa_database.py`, `qms_change_control_database.py`, `risk_database.py`, `urs_database.py`, `qual_database.py`, `report_database.py`, `qms_document_database.py`) are the actual, only-consulted-for-reads data layer; `pharmagpt/db/*_repo.py` (`projects_repo.py`, `equipment_repo.py`, `kb_repo.py`, `qms_repo.py`) are thin Postgres CRUD adapters used exclusively for the best-effort dual-write side path.
- This is explicitly the documented plan (`docs/PHASE3_EXECUTION_PLAN.md` §3.6: "Remove dual-write paths and SQLite code ... `pharmagpt/database.py` + 9 sibling `*_database.py` files (drop SQLite branches)"), so it is not an accidental inconsistency — but it is a real, present-day cost: every route file that touches a dual-written domain now has to import and branch between two data-access modules with different call conventions (procedural functions returning dicts vs. Supabase-client-based functions that raise on failure), e.g. `pharmagpt/routes/projects.py:1-96` imports both `pharmagpt.database as db` and `pharmagpt.db.projects_repo`.
- The `db/*_repo.py` modules are not a general repository abstraction over "whichever backend is active" — `pharmagpt/db/backend.py:24-27` (`is_postgres_backend()`) exists as a switch point but is not called from any route or repo function found in this review; each route hardcodes calls to both the legacy module and the repo module directly, with the branch logic (`if config.X_BACKEND != "dual": return`) duplicated per-domain per-route-file (e.g. `pharmagpt/routes/projects.py:42`, `equipment.py:42`, `knowledge_base.py:37`). Consistent in intent, but it's copy-pasted control flow rather than a shared helper — a straightforward simplification opportunity whenever a fifth domain is added.
- Error-handling asymmetry: `db/*_repo.py` functions raise on failure by design (documented in `projects_repo.py:21-24`, "this module raises on failure ... callers doing best-effort dual-write are responsible for catching and logging"), while the legacy `*_database.py` functions generally return `None`/empty and never raise for "not found." Callers must remember which convention applies to which import — a plausible source of an uncaught exception if a future call site skips the try/except the existing dual-write helpers all use correctly today.

---

## 4. Service Layer

**Risk: Low.**

- `pharmagpt/services/` is a genuine business-logic layer, reasonably well-factored by domain: `document_processor.py`/`extraction/` (text extraction pipeline), `docx_generator.py`/`doc_exporter.py`/`doc_generator.py` (export), `urs_generation_job.py`/`urs_service.py`/`urs_lifecycle.py`/`urs_requirement_library.py` (URS domain), `qms_*_service.py` (QMS domains), `equipment_service.py`, `retrieval_engine.py`/`document_search.py` (RAG stubs), `job_runner.py` (async execution strategy).
- Services import `*_database.py` modules directly (e.g. `urs_generation_job.py:55` imports `urs_database as udb`) — there's no strict service→repository→database layering, but this is consistent with the "well-modularized monolith, not microservices" choice `PLATFORM_ARCHITECTURE.md` §3 explicitly makes, and isn't a defect at this stage.
- `urs_lifecycle.py:1-60` is a genuinely good pattern worth calling out positively: a real state machine (`ALLOWED_TRANSITIONS` dict) that the route layer is forced through (`routes/urs.py` no longer accepts a raw `status` field in `PUT`), preventing exactly the "client POSTs `{"status": "approved"}` and skips review" bug its own docstring says it replaced. This is the one place in the codebase where the six-state-lifecycle intent from `PLATFORM_ARCHITECTURE.md` §12 is actually enforced in code, even though it predates that document and uses a slightly different state vocabulary (`draft → under_review → pending_approval → approved → effective → obsolete` vs. the frozen doc's `Draft → In Review → QA Review → Approved → Obsolete → Archived`). No equivalent state machine exists for KB documents or generated documents — those are created directly in an approved-equivalent state with no gate at all, a gap already disclosed in `docs/PHASE3_EXECUTION_PLAN.md` §3.3.

---

## 5. Dependency Injection / Connection Management

**Risk: Low-Medium.**

- No DI framework; module-level singletons are used deliberately and documented as such: `pharmagpt/state.py:22` (`gemini_client`), `pharmagpt/state.py:29` (`history_cache`, in-memory dict), `pharmagpt/services/job_runner.py:80` (`job_runner` instance). This is a reasonable choice for a monolith of this size.
- **In-memory `history_cache`** (`pharmagpt/state.py:29-45`) is a real scalability/correctness risk once the app runs with more than one worker/instance: `render.yaml:8` configures `gunicorn --workers=2 --threads=4`, meaning conversation history for a given project can be cached in one worker process and absent in the other — a user's follow-up chat message can silently miss context depending on which worker handles the request. `PLATFORM_ARCHITECTURE.md` §20 explicitly flags this exact pattern as "an architectural dead end for the multi-tenant platform," and it is still the active implementation.
- SQLite connection pattern: `pharmagpt/database.py:57-73` (`get_connection()`) opens a fresh connection per call (`sqlite3.connect(DB_PATH, timeout=30)`, WAL mode, `busy_timeout=30000`) and callers close it manually at the end of each function (e.g. `database.py:444`, `database.py:857`). There is no pooling (unnecessary for SQLite) but also no `try/finally`/context-manager guarantee — if an exception is raised between `get_connection()` and the trailing `conn.close()`, the connection leaks. Low real-world severity for SQLite specifically, but worth tightening given the number of call sites (74 `get_connection()`/`conn.close()` occurrences in one 1089-line file) that all repeat this manually.
- Supabase client construction is correct, as noted in §1: a fresh client per call, never a shared instance, avoiding cross-request session bleed (`pharmagpt/services/supabase_client.py:21-36`).

---

## 6. Transaction Handling / Dual-Write Failure Modes

**Risk: High.** This is the second-most important finding after §2, and the one the review was specifically asked to weight.

**What happens today if the Postgres write fails after the SQLite write succeeds:**

1. The SQLite write has already committed and the HTTP response has already been (or is about to be) built from it — the dual-write call happens *after* the primary write and its failure can never roll back or block the response. This is deliberate and documented consistently at every call site, e.g. `pharmagpt/routes/projects.py:35-39`: "a Postgres failure here is logged and swallowed, never raised — it must never turn a successful SQLite write into a failed request."
2. The failure is caught by a bare `except Exception:` and passed to `logger.exception(...)` (e.g. `pharmagpt/routes/projects.py:57-58`, `equipment.py:50-51`, `knowledge_base.py:52-53`) — a Python traceback to stdout, captured only by whatever log aggregation Render provides. **There is no alerting integration** (no Sentry/PagerDuty/webhook found anywhere in `pharmagpt/` or `requirements.txt`-adjacent config) and no metric/counter incremented on dual-write failure.
3. Nothing marks the row as "needs reconciliation." The only detection mechanism is running `scripts/check_projects_parity.py` / `check_kb_parity.py` / `check_equipment_parity.py` / `check_qms_parity.py` by hand. **`render.yaml` defines no cron/scheduled job** — confirmed by reading the full file (`render.yaml:1-21`): one `web` service only, no `cron` service type, no scheduled task. `docs/PHASE3_EXECUTION_PLAN.md` §3's "Parity checks keep running periodically" is aspirational/manual-operator language, not automation that exists in the repo.
4. Drift is not always even a bug to be caught: `config.py:52-58` documents that KB `extracted_text` sync is *intentionally* excluded from dual-write and "ongoing drift is expected and accepted." That's a reasonable, disclosed scope cut for that one field, but it means the parity checkers must already tolerate some known drift, which makes an unexpected drift (e.g. an actual dual-write bug) harder to distinguish from the accepted gap by inspection alone.

**On the specific "flag flips to `dual` without live RLS" scenario asked about:** the current sequencing actually protects against this reasonably well — RLS migrations (`migrations/0005_projects_rls_up.sql` through `0008_qms_rls_up.sql`) are applied in the same milestone that introduces each domain's dual-write flag, and the flag defaults to `"sqlite"` (off) in `config.py` for every domain (`PROJECTS_BACKEND`, `KB_BACKEND`, `EQUIPMENT_BACKEND`, `QMS_BACKEND` all default via `os.getenv(..., "sqlite")`). The more realistic version of that risk is operational rather than architectural: nothing in this codebase stops an operator from setting an env var like `PROJECTS_BACKEND=dual` in a Render environment where a *later* migration hasn't actually been applied yet (there is no runtime check that migration N is live before honoring flag N) — the safety here depends entirely on deployment discipline, not a code-level guard.

**Net assessment:** the dual-write mechanism is safe for user-facing correctness (it truly cannot turn a good SQLite write into a bad response) but is not yet safe for *data-integrity observability* — a sustained Postgres outage, a schema mismatch, or an RLS misconfiguration would silently degrade Phase 3.6's eventual cutover data quality with no automated signal, only whatever a human notices in logs or remembers to run a script for.

---

## 7. Async Jobs / Background Workers

**Risk: Low.** Well-engineered relative to its stated constraints.

- `pharmagpt/services/job_runner.py:38-59` (`ThreadPoolJobRunner`) wraps every submitted job in a try/except that logs any unhandled exception, explicitly to prevent "a crashed background job... take down the web process or silently vanish" — and it holds. `CeleryJobRunner` (`job_runner.py:62-75`) is a clean, honest not-yet-implemented extension point rather than a half-built abstraction.
- Job status is persisted to SQLite, not held only in memory (`job_runner.py:6-9`), so it survives independently of which thread/worker picks up the work — correct design given the multi-worker `gunicorn` config.
- `pharmagpt/services/urs_generation_job.py` is the most carefully engineered file in the codebase: batches Gemini calls to avoid gunicorn's 60s timeout (`config.py:129`, `Procfile`), distinguishes retryable failures (malformed/truncated JSON, `_RetryableGenerationError`) from non-retryable ones (`GenerationBlockedError` for safety/recitation stops, and genuine API errors which propagate untouched), persists partial progress per-batch rather than only at the end, and has a documented heuristic partial-JSON-recovery fallback (`urs_generation_job.py:401-438`) for when even retries are exhausted. This is a strong reference implementation for the rest of the AI-integration surface to be measured against.
- `pharmagpt/services/document_processor.py:97-137` (`_run_extraction_job`) follows the same discipline: `extract_sync()` is documented to never raise, but the job body still wraps it in try/except and records a `"failed"` result rather than leaving a document stuck in `"processing"` forever (`document_processor.py:119-131`).
- Minor gap: `submit_generation_job`'s `performed_by` parameter is explicitly noted as needing to be resolved by the caller from `g.tenant` *before* the call, "the background thread runs outside any Flask request context, so it has no way to read `g` itself" (`urs_generation_job.py:124-128`) — correct in isolation, but combined with §2's finding, whatever the caller passes as `performed_by` is only as trustworthy as the route that captured it, and (per the QMS approval finding) at least one sibling route pattern in this codebase already takes that value from client input rather than `g.tenant`.

---

## 8. File Storage

**Risk: High.** One concrete, currently-live gap.

- `pharmagpt/database.py:39-54` contains an unusually candid comment explaining that `DB_PATH` defaults to a path inside the application package, which is wiped on every Render restart/redeploy without a mounted disk — and `render.yaml:9-12` correctly mounts a persistent disk at `/var/data` and sets `DB_PATH=/var/data/pharmagpt.db` (`render.yaml:14-15`) to solve exactly that problem for the database file.
- **`UPLOAD_FOLDER` was not given the same treatment.** `pharmagpt/config.py:96` (`UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")`) is hardcoded relative to the package directory with no environment-variable override — confirmed by searching every reference to `UPLOAD_FOLDER` in the codebase (`documents.py:22,78,126`, `routes/qms_common.py:43,110`); none of them read from an env var, and `render.yaml` sets no `UPLOAD_FOLDER`/equivalent env var pointing at `/var/data`.
- Net effect: every uploaded Knowledge Base document, project document, and QMS attachment lives on the same ephemeral filesystem the team already diagnosed and fixed for the database file — it will be silently deleted on the next Render restart, redeploy, or idle-spindown, while the *metadata row* describing it (in the now-persistent SQLite file) survives, pointing at a file that no longer exists. This is the precise failure mode `PLATFORM_ARCHITECTURE.md` §15 says the target architecture "eliminates entirely" (files in Supabase Storage, never on Render's local filesystem) — but until that cutover, the current build doesn't even have the interim mitigation it already applied to its own database file.
- This is easy to fix in isolation (point `UPLOAD_FOLDER` at the same mounted disk, e.g. `/var/data/uploads`) but is flagged as a structural risk because it currently defeats the one persistent-disk investment already made.

---

## 9. AI Integration (Gemini)

**Risk: Low-Medium.**

- The URS generation path (§7 above) is a strong example of retry/timeout/error-handling discipline: structured output via `response_schema`/`response_mime_type="application/json"` (`urs_generation_job.py:76-92`), explicit `finish_reason` checking before trusting output (`urs_generation_job.py:359-380`), and a hard separation between retryable (malformed JSON, `MAX_TOKENS`) and non-retryable (network/auth/quota, `SAFETY`/`RECITATION`) failure classes.
- **Other AI call sites do not share this discipline and leak internals to the client on failure.** SSE streaming endpoints catch the generic Gemini exception and forward `str(e)` directly into the event stream payload the browser receives:
  - `pharmagpt/routes/qms_documents.py:123-124`: `except Exception as e: yield f"data: {json.dumps({'error': str(e)})}\n\n"`.
  - `pharmagpt/routes/report.py:227` (same pattern, confirmed via grep, not fully read in this pass but same `except Exception as e` / `str(e)` shape).
  - This contradicts `PLATFORM_ARCHITECTURE.md` §19's explicit API principle ("Errors are structured and never leak internals") — a raw Gemini SDK exception string can include request/response details not intended for end users. Low-to-medium severity (information disclosure, not an access-control bypass), but a straightforward, repo-wide fix (map to a generic user-facing message, log the real exception server-side) that isn't applied consistently even though the pattern for doing it right already exists elsewhere in the same codebase (`urs_generation_job.py`'s `_build_generation_message`).
- No visible request timeout configuration on the `google-genai` client calls themselves (relying on the library's defaults) beyond the batch-size mitigation for gunicorn's own `--timeout=60`; not verified further in this pass since it's a narrower, lower-impact concern than the above.

---

## 10. Export Pipeline (DOCX)

**Risk: Low.**

- `pharmagpt/services/doc_exporter.py:29-71` (`markdown_to_docx`) has a sensible resilience pattern: the QA review engine (`run_review`) is wrapped in its own try/except so a review-engine bug degrades to "export without the review report" rather than failing the export entirely (`doc_exporter.py:50-61`) — consistent with the codebase's general "never let a secondary concern block the primary deliverable" discipline seen elsewhere (extraction, dual-write).
- Export itself (`docx_generator.py`) was not deeply read in this pass; no risk signal surfaced from its consumers.

---

## 11. Configuration Management

**Risk: Low.**

- `pharmagpt/config.py` is a single, well-commented module; every Phase 3 flag (`DATABASE_BACKEND`, `PROJECTS_BACKEND`, `KB_BACKEND`, `EQUIPMENT_BACKEND`, `QMS_BACKEND`) defaults to the safe/inert value (`"sqlite"`) and each is documented in-line with exactly what it does and doesn't cover — genuinely good self-documentation for a migration-in-progress config surface.
- Secrets (`GEMINI_API_KEY`, Supabase keys) are loaded from `.env` via `python-dotenv` and never hardcoded; `.gitignore` correctly excludes `.env`/`.env.*` while allowlisting `.env.example` (confirmed by reading `.gitignore`). `render.yaml:16-17` marks `GEMINI_API_KEY` as `sync: false` (operator-supplied, not committed) — correct practice.
- `pharmagpt/services/supabase_client.py:8-18` (`_require_env`) defers the missing-env-var failure to first actual use rather than import time, deliberately, so the app can boot with zero Supabase configuration when no `*_BACKEND` flag is set to `"dual"` — a reasonable choice that avoids coupling app startup to infrastructure that isn't in use yet, though it does mean a misconfigured Supabase env in production surfaces as a runtime `ValueError` inside a request rather than a boot-time failure.
- The one weak spot already covered in §1: `FLASK_SECRET_KEY`'s hardcoded fallback (`config.py:15`).

---

## 12. Error Handling and Logging

**Risk: Medium.**

- `pharmagpt/logging_config.py:18-37` is a minimal but correct fix for a real prior bug (messages silently dropped below gunicorn's default log level) — a single idempotent `configure_logging()` call sets up one `StreamHandler` at INFO for the whole `pharmagpt` namespace.
- The logging *pattern* used throughout background jobs and dual-write helpers (`logger.exception(...)` at the point of failure, with domain identifiers in the message) is consistently applied and would make root-causing a specific incident from logs straightforward.
- What's missing platform-wide: no structured/JSON logging (harder to query at scale once log volume grows), and — as covered in §6 — no alerting layer sitting on top of these logs. `logger.exception` is necessary but not sufficient for anything the team needs to react to in near-real-time (a sustained dual-write failure, a spike in extraction failures, an AI provider outage).
- The client-facing error-detail leakage noted in §9 (`str(e)` streamed to the browser) is this section's most concrete citable instance of "errors leak internals," contrary to the stated API design principle.

---

## 13. Security Posture (Structural)

**Risk: High**, driven entirely by §2's findings; everything else here is secondary.

- Transport/session-cookie configuration is handled correctly: `HttpOnly`, `SameSite=Lax`, and `Secure` gated on non-debug mode (`pharmagpt/app.py:57-59`).
- File upload validation is extension-allowlist-based (`ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt"}`, `config.py:102`) with `werkzeug.secure_filename` used for on-disk naming (`documents.py:21`, confirmed via import) — reasonable baseline, not deeply audited for path-traversal edge cases in this pass (explicitly out of scope per the task: "defer deep vuln-hunting, just flag structural risks").
- The structural security posture is otherwise dominated by §2 (no tenant scoping, no role enforcement, spoofable approval actor) and §8 (files on ephemeral storage). Both are architecture-level gaps, not implementation bugs in the traditional sense — the auth *gate* is solid; nothing downstream of it enforces what the gate is supposed to protect.

---

## Prioritized Risk List

| # | Risk | Area | Severity | Primary citation |
|---|---|---|---|---|
| 1 | No tenant scoping on any SQLite-backed read/write path — `company_id` is resolved but never used to filter queries; every list/detail/update/delete endpoint is accessible cross-company by ID | Authorization / Multi-Tenancy | **Critical** | `pharmagpt/routes/projects.py:98-101`, `pharmagpt/database.py` (no `company_id` column anywhere) |
| 2 | No role-based authorization anywhere in the route layer; segregation of duties is unenforced | Authorization | **Critical** | `pharmagpt/routes/urs.py:88` (only use of `tenant.role`); no `require_role` exists in `pharmagpt/auth/decorators.py` |
| 3 | QMS approval actor/role/e-signature fields are taken from client-supplied JSON, not the authenticated session — audit trail attribution is spoofable | Authorization / Audit Integrity | **Critical** | `pharmagpt/routes/qms_deviations.py:271-299` |
| 4 | Uploaded files live on Render's ephemeral filesystem (no persistent-disk path), while the metadata pointing at them is now persistent — silent data loss on every restart/redeploy | File Storage | **High** | `pharmagpt/config.py:96`; contrast with `render.yaml:9-15`'s fix for `DB_PATH` |
| 5 | Dual-write failures are logged only — no alerting, no scheduled reconciliation job (`render.yaml` has no cron service); drift is invisible outside manual script runs | Transaction Handling | **High** | `pharmagpt/routes/projects.py:57-58`; `render.yaml:1-21` (no cron/worker service) |
| 6 | In-memory chat-history cache is per-process, not shared across the 2 configured gunicorn workers — already flagged as an architectural dead end in the target doc but still the active implementation | Connection/State Management | **Medium** | `pharmagpt/state.py:29-45`; `render.yaml:8` (`--workers=2`) |
| 7 | Raw exception text (`str(e)`) streamed to the browser on AI-generation failure, contrary to the stated "errors never leak internals" API principle | Error Handling / AI Integration | **Medium** | `pharmagpt/routes/qms_documents.py:123-124`, `pharmagpt/routes/report.py:227` |
| 8 | Two parallel data-access layers (`*_database.py` vs `db/*_repo.py`) with duplicated per-route feature-flag branching and inconsistent raise/return-None error conventions | Repository Pattern | **Medium** | `pharmagpt/routes/projects.py:41-96`; `pharmagpt/db/projects_repo.py:21-24` |
| 9 | `FLASK_SECRET_KEY` has a hardcoded dev-secret fallback if unset outside the Render-specific deploy config | Configuration | **Low** | `pharmagpt/config.py:15` |
| 10 | SQLite connections opened without a `try/finally`/context-manager guarantee — leak on exceptions mid-function | Connection Management | **Low** | `pharmagpt/database.py:57-73` and its ~74 call sites |

**Recommended sequencing:** Items 1–3 (tenant/role/actor authorization) are the same underlying gap — an authorization layer that reads `g.tenant` for enforcement, not just for optional side-writes — and should be closed together before any second company is onboarded to a shared deployment, regardless of where Phase 3's Postgres cutover stands. Item 4 (upload storage) is a quick, isolated fix. Item 5 (dual-write observability) matters most as a precondition for trusting the Phase 3.6 cutover gate, not for today's user-facing correctness.

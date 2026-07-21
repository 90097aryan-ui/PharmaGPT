# PharmaGPT — Deployment / Production-Readiness Review

**Scope:** `render.yaml`, `Procfile`, `requirements*.txt`, `.env` vs `pharmagpt/config.py`, health check, static file serving, file storage (`uploads/`, `generated_documents/`), Dockerfile presence, and lingering SQLite deployment references ahead of Phase 3.6.
**Method:** Static review only. No files modified. `.env` was inspected for variable *names* only — no values were read or printed.
**Date:** 2026-07-21

---

## Executive Summary

The app is deployable today for a small pilot, but there are two **launch-blocking** gaps and one **data-loss** gap that must be fixed before onboarding paying customers:

1. **Missing Supabase env vars in `render.yaml`.** `SUPABASE_URL` and `SUPABASE_ANON_KEY` are read at runtime on *every* authenticated request (`pharmagpt/auth/context.py` → `pharmagpt/services/supabase_client.py`), but `render.yaml`'s `envVars` block only declares `DB_PATH`, `GEMINI_API_KEY`, `FLASK_SECRET_KEY`, `FLASK_DEBUG`. If the Render service's env vars mirror only what's in `render.yaml` (i.e. nothing added by hand in the dashboard), **every authenticated request fails** — this is auth-critical, not optional.
2. **Gunicorn is not bound to Render's `$PORT`.** Both `Procfile` and `render.yaml`'s `startCommand` run `gunicorn pharmagpt.app:app --workers=2 --threads=4 --timeout=60 --worker-tmp-dir /dev/shm --keep-alive=5` with no `--bind 0.0.0.0:$PORT`. Gunicorn defaults to `127.0.0.1:8000` unless told otherwise, and Render's routing layer forwards traffic to the port in its injected `PORT` env var. If this hasn't been patched at the dashboard level, the deployed service is not reachable. **This needs to be verified against the live Render service today**, since the app is reportedly already running there.
3. **Uploaded files and generated documents are not on the persistent disk.** `render.yaml` mounts a 1 GB disk at `/var/data`, but only `DB_PATH` (the SQLite file) is pointed there. `UPLOAD_FOLDER` (`pharmagpt/config.py`) and the generated-document output directory (`pharmagpt/services/docx_generator.py`) both resolve to paths inside the *application source tree*, which is rebuilt from the git checkout on every deploy/restart on Render's ephemeral filesystem. Every uploaded PDF/DOCX/XLSX and every AI-generated protocol is lost on the next deploy or dyno restart.

Beyond these three, dev dependencies (`pytest`, its transitive deps) ship into the production image, there's no Dockerfile (Render builds natively from `requirements.txt`, which is a valid and simpler path — not a gap by itself), and the SQLite migration flags are honestly and thoroughly self-documented (`docs/PHASE3_FLAGS.md`) as **not yet safe to flip** — no flag has completed an extended Staging soak or the 2-company RLS isolation check, so Phase 3.6 (SQLite retirement) is correctly still gated.

---

## Findings by Category

### 1. `render.yaml`

```yaml
services:
  - type: web
    name: pharmagpt
    runtime: python
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn pharmagpt.app:app --workers=2 --threads=4 --timeout=60 --worker-tmp-dir /dev/shm --keep-alive=5
    disk:
      name: pharmagpt-data
      mountPath: /var/data
      sizeGB: 1
    envVars:
      - key: DB_PATH
        value: /var/data/pharmagpt.db
      - key: GEMINI_API_KEY
        sync: false
      - key: FLASK_SECRET_KEY
        generateValue: true
      - key: FLASK_DEBUG
        value: "false"
```

- **No `healthCheckPath`.** `app.py` exposes `GET /health` (unauthenticated liveness check, returns `{"status": "ok"}`), but `render.yaml` never tells Render to use it. Without it, Render can't do zero-downtime rollout health gating or auto-restart a wedged instance based on app-level health — it can only see whether the process is alive at the TCP/HTTP level via its own default probing.
- **No `--bind 0.0.0.0:$PORT` in `startCommand`.** See Executive Summary #2 — verify against the live service.
- **`plan: starter`** is a single, non-autoscaled instance. This is *consistent* with using a persistent disk (Render disks are per-instance and don't work across horizontally-scaled instances), but it also means the current architecture has a ceiling: scaling beyond one instance requires removing the disk dependency for anything that must survive redeploys (see §6).
- **Missing env vars**: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (required at runtime — see §4). `SUPABASE_SERVICE_ROLE_KEY`, `SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASSWORD`, `SUPER_ADMIN_DISPLAY_NAME` are **not** needed here — they're consumed only by `scripts/bootstrap_super_admin.py`, a CLI-only, one-time bootstrap script never imported by `app.py` and exposing no HTTP route, so their absence from `render.yaml` is correct, not a gap.
- **Disk size (1 GB)** is sized for the SQLite file alone (a few KB–MB today). If uploads/generated docs are later moved onto this same disk as a stopgap (not recommended — see §6), 1 GB will be exhausted quickly by even a handful of PDF uploads across 10–50 customers.

### 2. `Procfile` vs `pharmagpt/config.py` timeout settings

```
web: gunicorn pharmagpt.app:app --workers=2 --threads=4 --timeout=60 --worker-tmp-dir /dev/shm --keep-alive=5
```

Identical to `render.yaml`'s `startCommand` — no drift between the two. Render honors `render.yaml`'s `startCommand` over the `Procfile` when both exist, so the `Procfile` is currently vestigial but harmless (kept in sync).

- `--timeout=60` (worker kill timeout) is explicitly designed around in `pharmagpt/config.py`'s URS generation settings:
  > "Generation is batched into small Gemini calls run on job_runner's thread pool instead of one giant streamed request, so no single call risks exceeding gunicorn's `--timeout` (Procfile/render.yaml)."

  This is a genuinely good pattern — long-running Gemini calls for URS generation run on a background thread pool (`services/job_runner.py`) and the frontend polls status, rather than holding a gunicorn worker (and its `--timeout`) for the full generation duration. `PAGE_TIMEOUT_SECONDS` (10s/page, document extraction) and `URS_GENERATION_SLOW_WARNING_SECONDS` (20s) are both comfortably under the 60s worker timeout.
- `--workers=2 --threads=4` = 8 concurrent request slots on a `starter`-plan instance (modest CPU/RAM). Combined with SQLite in WAL mode (`pharmagpt/database.py`), this is workable for a pilot but should be load-tested before 10–50 concurrent-ish customers — SQLite's writer serialization and the starter plan's resource ceiling are the two levers to watch.
- `--worker-tmp-dir /dev/shm` is a sound gunicorn practice on Render (avoids slow disk for the heartbeat file).

### 3. `requirements.txt` / `requirements-dev.txt`

- `requirements-dev.txt` is just `-r requirements.txt` + `pytest==8.3.4` — but **`pytest==8.3.4` is already pinned directly inside `requirements.txt` itself** (line 59). So the "dev-only" separation doesn't actually exist: `pytest`, and its transitive dependencies `iniconfig` and `pluggy` (both otherwise unused by the app), ship into every production install via `buildCommand: pip install -r requirements.txt`.
- No other clearly dev/test-only packages were found in `requirements.txt` (the rest — Flask, Gemini/Google SDKs, Supabase client stack, PDF/DOCX/XLSX readers, gunicorn, etc. — are all runtime dependencies).
- **Recommendation:** move `pytest==8.3.4` out of `requirements.txt` into `requirements-dev.txt` only, so production installs don't pull test tooling.

### 4. `.env` variable names vs `pharmagpt/config.py` / runtime usage

`.env` declares these names (values not read):
`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASSWORD`, `SUPER_ADMIN_DISPLAY_NAME`

`pharmagpt/config.py` reads via `os.getenv`:
`GEMINI_API_KEY`, `FLASK_SECRET_KEY`, `FLASK_DEBUG`, `FLASK_PORT`, `DATABASE_BACKEND`, `PROJECTS_BACKEND`, `KB_BACKEND`, `EQUIPMENT_BACKEND`, `QMS_BACKEND`, `PAGE_TIMEOUT_SECONDS`, `EXTRACTION_WORKERS`, `GC_INTERVAL_PAGES`, `PROGRESS_WRITE_EVERY_N_PAGES`, `URS_GENERATION_BATCH_SIZE`, `URS_GENERATION_SLOW_WARNING_SECONDS`, `URS_GENERATION_MAX_RETRIES`

Two other modules read env vars directly (not via `config.py`):
- `pharmagpt/database.py`: `DB_PATH` (falls back to an in-package path if unset — see §6).
- `pharmagpt/services/supabase_client.py`: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (raised as a hard error only when a Supabase-backed code path actually runs — auth, or a domain repo with its `*_BACKEND` flag set to `"dual"`).

**Cross-check against `render.yaml`:**

| Var | In `.env` | Read by app at runtime | In `render.yaml` | Verdict |
|---|---|---|---|---|
| `GEMINI_API_KEY` | yes | yes (`config.py`) | yes (`sync: false`) | OK |
| `FLASK_SECRET_KEY` | no | yes (`config.py`, has an insecure hardcoded fallback) | yes (`generateValue: true`) | OK |
| `FLASK_DEBUG` | no | yes (`config.py`) | yes (`"false"`) | OK — see caution below |
| `DB_PATH` | no | yes (`database.py`, not `config.py`) | yes | OK |
| **`SUPABASE_URL`** | yes | **yes, every authenticated request** | **missing** | **Gap — likely breaks auth in prod** |
| **`SUPABASE_ANON_KEY`** | yes | **yes, every authenticated request** | **missing** | **Gap — likely breaks auth in prod** |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | only by `scripts/bootstrap_super_admin.py` (CLI, no HTTP route) | not needed | OK, correctly excluded |
| `SUPER_ADMIN_EMAIL`/`PASSWORD`/`DISPLAY_NAME` | yes | only by the same bootstrap script | not needed | OK, correctly excluded |
| `FLASK_PORT` | no | yes (`config.py`) but only used by the `app.run()` dev entrypoint, not by gunicorn | not set | Fine — irrelevant under gunicorn |
| `DATABASE_BACKEND`, `PROJECTS_BACKEND`, `KB_BACKEND`, `EQUIPMENT_BACKEND`, `QMS_BACKEND` | no | yes, all default to `"sqlite"` | not set | Intentional — see §7, none should be flipped yet |
| `PAGE_TIMEOUT_SECONDS`, `EXTRACTION_WORKERS`, `GC_INTERVAL_PAGES`, `PROGRESS_WRITE_EVERY_N_PAGES`, `URS_GENERATION_*` | no | yes, all have sane defaults | not set | Fine — tunable later if needed |

**Caution on `FLASK_DEBUG`:** `config.py` defaults it to `"true"` when the env var is *absent* (`os.getenv("FLASK_DEBUG", "true")`). `render.yaml` explicitly sets it to `"false"`, so production is currently safe — but if that key is ever removed from the Render dashboard/`render.yaml`, the app would silently fall back to **debug mode on in production**, exposing the Werkzeug interactive debugger (arbitrary code execution) and disabling the secure session cookie flag (`SESSION_COOKIE_SECURE = not FLASK_DEBUG`). Recommend flipping the code default to `"false"` so an accidental unset fails safe.

### 5. Health check endpoint

`pharmagpt/app.py`:
```python
@app.route("/health")
def health():
    """Unauthenticated liveness endpoint for deployment/uptime checks."""
    return jsonify({"status": "ok"})
```
Present, unauthenticated, correctly named. It is a pure liveness check only — it does not touch the database or Supabase, so it can return `200` even if SQLite or Supabase connectivity is broken. Not wired into `render.yaml` via `healthCheckPath` (see §1).

### 6. Static file serving

`app = Flask(__name__)` uses Flask's default static handling — `pharmagpt/static/` (css/js/images) is served directly by Flask/Werkzeug under `/static`, with no custom `static_folder`, no CDN, and no explicit cache-control headers. This is fine for a small pilot; for 10–50 customers it's a minor performance/cost item (every static asset request occupies a gunicorn worker slot) rather than a correctness risk. Consider a CDN or platform-level static asset offload later, not urgent now.

### 7. File storage — `uploads/` and `generated_documents/` (ephemeral vs persistent)

This is the most consequential finding after the two launch blockers.

- **`UPLOAD_FOLDER`** (`pharmagpt/config.py:96`): `os.path.join(os.path.dirname(__file__), "uploads")` → always resolves to `pharmagpt/uploads/` inside the application package, regardless of environment. There is no env var override.
- **Generated documents** (`pharmagpt/services/docx_generator.py:56`): `Path(__file__).resolve().parents[3] / "generated_documents"`. Note this is **fragile by construction** — it walks up a fixed number of parent directories from the file's own location, so it silently changes target depending on exactly how deep the repo is checked out. Locally, `parents[3]` from `pharmagpt/services/docx_generator.py` resolves to the *drive root* (`D:\generated_documents`, confirmed to exist and be a separate, empty directory from the real `D:\PharmaAgent\generated_documents` that actually holds the smoke-test output). On Render's container filesystem the same code would resolve to whatever sits three levels above `services/`, which is very unlikely to be the intended `generated_documents/` directory next to the repo root — this needs to be replaced with a directory computed from a fixed number of parents relative to a known anchor (e.g. an explicit project-root marker or an env var), not a hardcoded `parents[N]` walk.
- **Neither path is under `render.yaml`'s mounted disk** (`/var/data`). Only `DB_PATH` (the SQLite file) is redirected there. Everything a user uploads (`pharmagpt/uploads/{project_id}/...`, `pharmagpt/uploads/kb/...`, `pharmagpt/uploads/qms/document/...`) and everything the app generates (`generated_documents/*.docx`) lives on Render's ephemeral, redeploy-reset filesystem.
- **Practical consequence:** every redeploy (a code push, a Render restart, a plan change, a dyno respawn) silently discards all uploaded source documents and all AI-generated protocols/reports. Given the app is mid-migration to Supabase for structured data but this migration has **not yet extended to file storage** (no reference to Supabase Storage buckets was found anywhere in `pharmagpt/`), this is a real, currently-live data-loss risk, not a future one.
- **Recommendation, in order of preference:** (a) move file storage to Supabase Storage now, consistent with where auth/db are already headed, since it also solves the "disks don't work with >1 instance" scaling ceiling; or, as a stopgap only, (b) redirect `UPLOAD_FOLDER` and the generated-documents directory onto the existing `/var/data` mounted disk via env vars, accepting that this still caps you at a single Render instance.

### 8. Dockerfile

**No Dockerfile exists** anywhere in the repository (checked root and common locations). This is not a gap — `render.yaml` declares `runtime: python`, so Render builds and runs the app natively via `buildCommand`/`startCommand` against `requirements.txt`, which is a valid, simpler alternative to a container build for a `runtime: python` service on Render. Flagging only so it's an explicit, confirmed "no" rather than an oversight.

### 9. Lingering SQLite references ahead of Phase 3.6

Per `docs/PHASE3_FLAGS.md`, every `*_BACKEND` flag (`DATABASE_BACKEND`, `PROJECTS_BACKEND`, `KB_BACKEND`, `EQUIPMENT_BACKEND`, `QMS_BACKEND`) still defaults to `"sqlite"` and none has been flipped to `"dual"` in any deployed environment. The document is candid that **Phase 3.6 (SQLite retirement) is correctly still gated**: no flag has had an extended Staging soak, and the required 2-company RLS isolation spot-check has not been performed. Nothing in `render.yaml`/`Procfile` currently assumes Postgres is authoritative, so there is no deployment-config drift to fix today.

The only forward-looking note: `render.yaml`'s disk mount and `DB_PATH` env var exist solely to give the SQLite file a persistent home. Once Phase 3.6 completes and SQLite is actually retired, `DB_PATH`, the `disk:` block, and the 1 GB volume itself become dead configuration that should be removed from `render.yaml` in the same change — otherwise they'll linger as confusing, paid-for-but-unused infrastructure (Render disks are billed even if the app stops writing to them).

---

## Deployment Checklist

### Already production-ready
- [x] `GEMINI_API_KEY`, `FLASK_SECRET_KEY`, `FLASK_DEBUG`, `DB_PATH` correctly declared in `render.yaml`
- [x] `/health` liveness endpoint exists, unauthenticated, lightweight
- [x] Session cookie hardening (`HttpOnly`, `SameSite=Lax`, `Secure` tied to `FLASK_DEBUG`) is correctly wired
- [x] Long-running Gemini/URS generation runs off the request thread (background job + polling), correctly designed around gunicorn's `--timeout=60`
- [x] SQLite `DB_PATH` correctly redirected to the mounted persistent disk (`/var/data`)
- [x] Procfile and render.yaml `startCommand` are consistent with each other
- [x] SQLite→Postgres migration flags are conservative-by-default and honestly tracked (`docs/PHASE3_FLAGS.md`); nothing has been flipped prematurely
- [x] No Dockerfile needed — native Python runtime build is a valid, deliberate choice for this service

### Needs attention before onboarding 10–50 SaaS customers
- [ ] **Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to `render.yaml`'s `envVars`** (or confirm they're already set by hand in the Render dashboard) — auth will fail on every request without them
- [ ] **Verify the live Render service is actually reachable given no `--bind 0.0.0.0:$PORT`** in `startCommand`/`Procfile`; add it if the current deployment relies on an undocumented default
- [ ] **Move `uploads/` and `generated_documents/` off the ephemeral app filesystem** — either to Supabase Storage (preferred, matches the direction of the rest of the migration) or, as a stopgap, onto the existing mounted disk
- [ ] **Fix the `parents[3]` hardcoded path walk** in `pharmagpt/services/docx_generator.py` — it does not reliably resolve to the intended `generated_documents/` directory across environments (confirmed to resolve to the drive root locally)
- [ ] Add `healthCheckPath: /health` to `render.yaml` so Render can use it for rollout gating and instance health
- [ ] Move `pytest==8.3.4` out of `requirements.txt` into `requirements-dev.txt` only, so test tooling doesn't ship to production
- [ ] Change `FLASK_DEBUG`'s code-level default in `config.py` from `"true"` to `"false"` so an accidentally-unset env var fails safe rather than open
- [ ] Load-test `--workers=2 --threads=4` on the `starter` plan against expected concurrent load for 10–50 customers, particularly SQLite write contention
- [ ] Before flipping any `*_BACKEND` flag to `"dual"`/cutover: complete the extended Staging soak and 2-company RLS isolation check called out as still-required in `docs/PHASE3_FLAGS.md`
- [ ] Plan the removal of `DB_PATH`/the disk mount from `render.yaml` in the same change that eventually completes Phase 3.6 (SQLite retirement), so it doesn't linger as unused paid infrastructure
- [ ] Consider a CDN or platform static-asset offload for `pharmagpt/static/` once traffic volume makes gunicorn-served static assets a meaningful cost/latency factor (not urgent at current scale)

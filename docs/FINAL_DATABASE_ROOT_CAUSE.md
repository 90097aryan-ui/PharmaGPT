# Final Database Root Cause — Phase F.1

**Date:** 2026-07-24
**Method:** Direct inspection of `render.yaml`, `migrations/*.sql`, `pharmagpt/services/supabase_client.py`, `pharmagpt/services/identity_admin.py`, `pharmagpt/routes/companies.py`, `pharmagpt/routes/users.py`, `pharmagpt/auth/middleware.py`, git history and working-tree state (`git status`, `git ls-files`, `git log`, `git show`). No live Supabase/Render session available to this session — every claim below is either a direct read of a file on disk, a `git` fact, or a citation of `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`'s live-tested evidence from 2026-07-23. Nothing here is inferred from a prior report's conclusion without independently re-checking the underlying file it cites.

## Headline finding

**The stated root cause ("required GRANT permissions are not active in the live Supabase database") is correct but incomplete, and materially understates the blocker.** There are two independent, stacked problems, either one of which alone would make Company Administration / Assume Company Context non-functional in production:

1. **The GRANT/RLS-policy migrations are not active in Supabase** (the known issue).
2. **The application code that implements Company Administration has never been deployed to Render at all** — it does not exist in any commit reachable from `origin/main`, which is what Render builds from. This is a new finding from this session, not previously documented in these terms.

Fixing #1 alone (running the SQL in Supabase) would not produce a working feature, because the routes, JS, and even the migration files themselves are not on the server Render is running.

## Evidence for finding #2 (not deployed)

```
$ git log -1 --format="%H %cd" origin/main
7a98428fb8a074ea8f9da6c3e1fb3d9690e793be Thu Jul 23 10:33:14 2026 +0530

$ git status --porcelain=v1 -uall | grep -E '^\?\?' | grep -E 'companies.py|users.py|identity_admin.py|audit.py|migrations/001[012]'
?? migrations/0010_break_glass_rls_down.sql
?? migrations/0010_break_glass_rls_up.sql
?? migrations/0011_companies_admin_rls_down.sql
?? migrations/0011_companies_admin_rls_up.sql
?? migrations/0012_users_company_admin_rls_down.sql
?? migrations/0012_users_company_admin_rls_up.sql
?? pharmagpt/audit.py
?? pharmagpt/routes/companies.py
?? pharmagpt/routes/users.py
?? pharmagpt/services/identity_admin.py

$ git show HEAD:pharmagpt/routes/companies.py   → fatal: path does not exist in HEAD
$ git show HEAD:pharmagpt/audit.py              → fatal: path does not exist in HEAD
$ git show HEAD:migrations/0009_phase3_grants_up.sql → succeeds (0009 IS in HEAD)
```

`origin/main`'s HEAD (`7a98428`, "Phase 3: Shared Validation Engine, Document Lifecycle, Traceability and Knowledge Base Versioning", 2026-07-23) predates Phase 3.5 (Company Administration) entirely. Everything this Phase F.1 brief calls "Company Administration" — `routes/companies.py`, `routes/users.py`, `services/identity_admin.py`, the three admin-facing JS files (`admin_companies.js`, `admin_users.js`, `admin_assume_context.js`), the shared `audit.py` helper, and migrations `0010`–`0012` themselves — exists **only in this local working tree**, never committed, never pushed, never built by Render.

In addition, 14 previously-tracked files (`pharmagpt/app.py`, `auth/decorators.py`, `auth/middleware.py`, `database.py`, `routes/auth.py`, `routes/qual.py`, `routes/report.py`, `routes/risk.py`, etc. — full list via `git diff --stat`, 48 files, +2292/-408 lines) carry the rest of Phase F's fixes (audit-trail wiring, sequencing gates, RBAC guards) as **uncommitted local modifications**. None of this is live either.

**Render deploys from git** (`render.yaml`: `buildCommand: pip install -r requirements.txt`, `startCommand: gunicorn pharmagpt.app:app ...` — a standard git-triggered build, no other artifact source configured, no CI/CD pipeline file found in the repo). There is no mechanism by which uncommitted local files could be running on the live service. **Conclusion: the production Render deployment is currently running commit `7a98428` or earlier — a version of the application that does not contain a Company Administration feature at all**, not a version that contains it but fails on a missing grant.

## Evidence for finding #1 (grants not active), independently re-confirmed

This session did not have live Supabase access (per the credential-entry hard boundary — see Environmental Constraints below) and cannot re-run the live test itself. The claim rests on `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md` (2026-07-23), which tested this **directly against the live Postgres database, three independent ways** (browser, curl with a real JWT, and a raw Python call to the Supabase client bypassing Flask):

> `permission denied for table companies`, code `42501`, hint: `GRANT SELECT ON public.companies TO authenticated;` — i.e. Postgres itself naming the exact line `migrations/0011_companies_admin_rls_up.sql:35` already contains.

Same pattern independently reproduced for `users` (`0012`) and `break_glass_access` (`0010`). This is credible, specific, live evidence — not speculation — and this session found nothing to contradict it and no evidence anyone has since re-run these three files in the Supabase SQL Editor.

**Is it present in code?** Yes — all three `_up.sql` files exist on disk with correct, reviewed `GRANT`/`CREATE POLICY` statements (see [`DEPLOYMENT_VERIFICATION.md`](DEPLOYMENT_VERIFICATION.md) for the full statement-by-statement review).
**Was it deployed?** No — see finding #2; the files aren't even in git, let alone executed against Supabase through any tracked process.
**Was it executed?** No, per the live 42501 evidence above, as of the last live test (2026-07-23).
**Is it missing only in production?** There is no "non-production" Supabase project referenced anywhere in the codebase (`render.yaml`, `.env.example`, `docs/`) — `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY` are single, undifferentiated env vars with no staging/prod split documented. The identity/tenancy tables (`companies`, `users`, `roles`, `break_glass_access`) have lived in Postgres/Supabase since migration `0001`, independent of the `PROJECTS_BACKEND`/`KB_BACKEND`/`EQUIPMENT_BACKEND`/`QMS_BACKEND` SQLite/dual-write flags (still all `sqlite`, confirmed in `render.yaml`) — so this is not gated behind the separate, still-pending SQLite→Postgres cutover for business data.

## Finding #3 — a third, previously undocumented gap: missing `SUPABASE_SERVICE_ROLE_KEY` in production config

`pharmagpt/services/identity_admin.py::provision_user()` — the function both "create a company + its first admin" (`routes/companies.py`) and "invite a user" (`routes/users.py`) call — requires `get_service_role_client()`, which raises `ValueError: SUPABASE_SERVICE_ROLE_KEY not found in .env` if that env var is absent (`supabase_client.py::_require_env`).

`render.yaml`'s `envVars` block lists only `SUPABASE_URL` and `SUPABASE_ANON_KEY`. `SUPABASE_SERVICE_ROLE_KEY` is **not declared anywhere in `render.yaml`**. `.env.example` and `DEPLOYMENT_REVIEW.md` both explicitly document this key as *"CLI-only... not needed [by the web app]... their absence from render.yaml is correct, not a gap"* — **this was true when those documents were written (before Phase 3.5) and is now stale**: `identity_admin.py` is a new, live, HTTP-request-reachable code path that did not exist when that assessment was made.

**Consequence:** even after (a) migrations 0010-0012 are applied in Supabase and (b) the code is deployed, **Company creation and User invitation will still fail** in production with a clean 500 (`handle_postgrest_errors` catches the `ValueError`, so it won't crash the worker — but the feature won't work) unless someone separately adds `SUPABASE_SERVICE_ROLE_KEY` to the Render service's environment variables in the Render dashboard (a `sync: false` var is expected to be set manually outside `render.yaml`, but it must at least be *declared* as a placeholder key for an operator to know it's required — right now nothing in `render.yaml` signals this need exists).

## Corrected root-cause statement

> Company Administration / Assume Company Context is non-functional in production because **the feature has never been deployed** (its code and migrations exist only in an uncommitted local working tree, not in any commit Render builds from), **and**, independently, **the Postgres grants/RLS policies its Supabase-side tables require have not been executed against the live database** (confirmed by live 42501 errors on 2026-07-23), **and**, additionally, **the production environment is missing a required secret** (`SUPABASE_SERVICE_ROLE_KEY`) that two of the feature's write paths (company creation, user invite) depend on and that is undocumented as a web-app dependency in current deployment references.

This is still **entirely an operational/deployment gap, not an application-code defect** — the code itself (routes, migrations, RLS policy logic) was independently read in this session and is logically correct (see [`DEPLOYMENT_VERIFICATION.md`](DEPLOYMENT_VERIFICATION.md) and Work Package 4 in the final certification). But "Application Code: PASS" in the framing this brief was issued under is only true in the narrow sense of "the code that exists locally reads correctly" — it is not yet a true statement about what is running in production, because nothing described above has shipped.

## Environmental constraints on this verification

- No live Supabase SQL Editor session, no live Render dashboard/shell session, and no production credentials are available to this Claude Code session. Per this environment's standing safety rule, entering any password/credential into any field is never performed regardless of instruction, so a live authenticated walkthrough was not attempted.
- All conclusions above are drawn from: (a) direct reads of every file named, (b) `git` state, which is ground truth and required no credentials, and (c) citation of `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`'s specific, reproducible live-error evidence, cross-checked line-by-line against the migration files it quotes (confirmed accurate — e.g. `migrations/0011_companies_admin_rls_up.sql:35` is in fact `grant select, insert, update, delete on companies to authenticated;`).
- Items that genuinely require a live database/deploy session are marked **NOT VERIFIED** throughout this Phase F.1 deliverable set, with exact commands provided for whoever has that access — see [`PRODUCTION_RELEASE_CHECKLIST.md`](PRODUCTION_RELEASE_CHECKLIST.md).

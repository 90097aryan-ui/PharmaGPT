# Deployment Runbook — Company Administration Production Enablement
## Phase F.2

**Purpose:** exact, copy-pasteable steps to take Company Administration / Assume Company Context from "code exists, nothing deployed" to live in production, in the correct order, with rollback at every stage. Written for whoever executes the deploy — no assumed familiarity with the investigation that produced it (see `PHARMAGPT_v1.0_FINAL_RELEASE_CERTIFICATION.md` and `docs/FINAL_DATABASE_ROOT_CAUSE.md` for that history).

**This document does not claim any of these steps have been executed.** Phase F.2 is implementation-only — code and migrations are now commit-ready and idempotent (see `PHASE_F2_IMPLEMENTATION_REPORT.md`), but nothing has been pushed, deployed, or run against a live database from this session. Every step below still requires a human with the relevant access to actually run it.

---

## Stage 0 — Preconditions

- [ ] You have push access to `origin/main` on `https://github.com/90097aryan-ui/PharmaGPT.git` (or a PR-merge path with review).
- [ ] You have Supabase SQL Editor access to the project referenced by this environment's `SUPABASE_URL`.
- [ ] You have Render dashboard access to the `pharmagpt` service.
- [ ] You have the Supabase project's `service_role` secret key (Project Settings → API → `service_role` `secret`) ready to paste into Render — do not paste it anywhere else, and do not commit it.

## Stage 1 — Commit and push

```bash
cd /path/to/PharmaAgent
git status --porcelain=v1 -uall   # review the full change list one more time
git add -A
git commit -m "Phase F.2: commit Company Administration feature (routes, migrations, tests, idempotency, docs)"
git push origin main
```

If your workflow requires PR review instead of a direct push, open the PR against `main` and merge only after review — this diff has never been reviewed and includes 48+ modified and ~40 new files.

**Verification:**
```bash
git log -1 --format="%H %cd" origin/main
git show origin/main:pharmagpt/routes/companies.py | head -5   # should now succeed
```

## Stage 2 — Confirm Render deploy

Render auto-deploys from `origin/main` on push (per `render.yaml`, no separate CI step exists).

- [ ] Render dashboard → `pharmagpt` service → Events/Deploys tab → confirm a new deploy triggered from the commit in Stage 1, status reaches **Live**.
- [ ] `curl https://<your-render-url>/health` → expect `200`.

**Do not proceed to Stage 3 until this deploy is confirmed live** — running the migrations before the code that uses them is safe (RLS with no matching route just means the tables sit unused a little longer), but confirming deploy order avoids any ambiguity about what state the app was in during Stage 4's verification.

## Stage 3 — Database migrations

All three files (`migrations/0010_break_glass_rls_up.sql`, `0011_companies_admin_rls_up.sql`, `0012_users_company_admin_rls_up.sql`) are now idempotent as of Phase F.2 (see `docs/MIGRATION_VERIFICATION_GUIDE.md` for what changed and why it's safe to re-run). Run them in numeric order in the Supabase SQL Editor.

### 3.1 — Pre-flight state check (optional but recommended)

```sql
select tablename, policyname
from pg_policies
where tablename in ('break_glass_access', 'companies', 'users')
order by tablename, policyname;

select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_name in ('break_glass_access', 'companies', 'users', 'audit_trail')
  and grantee in ('authenticated', 'service_role')
order by table_name, grantee;
```

Record the output — useful to compare against Stage 3.5's post-migration check.

### 3.2 — Run `migrations/0010_break_glass_rls_up.sql`

Copy the full file contents into the Supabase SQL Editor and run. Expected: no errors, even if some or all of these objects already exist from a prior partial attempt (idempotent as of Phase F.2 — each `CREATE POLICY` is now preceded by a matching `DROP POLICY IF EXISTS`).

### 3.3 — Run `migrations/0011_companies_admin_rls_up.sql`

Same procedure.

### 3.4 — Run `migrations/0012_users_company_admin_rls_up.sql`

Same procedure.

### 3.5 — Post-migration verification

Re-run the Stage 3.1 queries. Expected results:

```
tablename            | policyname
----------------------+--------------------------------------
break_glass_access    | break_glass_insert_own
break_glass_access    | break_glass_select_own
break_glass_access    | break_glass_update_own_revoke
companies             | companies_company_admin_read_own
companies             | companies_super_admin_all
users                 | users_company_admin_read_company
users                 | users_company_admin_update_company
(and users_select_own from migration 0002, already present)

table_name           | grantee       | privilege_type
-----------------------+---------------+----------------
break_glass_access     | authenticated | SELECT / INSERT / UPDATE
companies              | authenticated | SELECT / INSERT / UPDATE / DELETE
users                  | authenticated | SELECT / UPDATE  (SELECT pre-existing from migration 0002/0003)
audit_trail            | authenticated | SELECT / INSERT  (from migration 0009 — verify separately, see Stage 3.6)
```

If any expected row is missing, stop and diagnose before proceeding — do not continue to Stage 4 on a partial migration state.

### 3.6 — Confirm migration 0009's grants (not previously independently verified live)

```sql
select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_name = 'audit_trail'
  and grantee in ('authenticated', 'service_role');
```

If `authenticated` is missing `SELECT`/`INSERT` here, re-run `migrations/0009_phase3_grants_up.sql` (also GRANT-only, already idempotent — GRANT is a no-op to re-run, never errors) before proceeding. Without this, Company/User admin actions will still "succeed" in the UI but silently fail to write their audit_trail row (`_audit_best_effort()` swallows the exception by design).

## Stage 4 — Environment variable

- [ ] Render dashboard → `pharmagpt` service → Environment → add `SUPABASE_SERVICE_ROLE_KEY` = `<the service_role secret from Supabase Project Settings → API>`.
- [ ] Save, allow Render to redeploy/restart the service with the new env var (Render restarts the service automatically on an env var change for this service type).

**Verification:** `SUPABASE_URL` and `SUPABASE_ANON_KEY` should already be pointing at the same Supabase project the migrations in Stage 3 were just run against — double check this now, since a project mismatch here would be silent (the app would boot fine, just against the wrong/unconfigured project).

## Stage 5 — Live verification (the actual GO gate)

Do not skip this stage or treat Stages 1-4 as sufficient on their own. Full step-by-step with expected responses: `docs/FINAL_RELEASE_EVIDENCE/MANUAL_VERIFICATION_CHECKLIST.md` (Phase F.1) plus the new automated coverage added in Phase F.2 (`tests/test_companies.py`, `tests/test_user_invite_and_list.py` — these run against a mock and were already passing before this deploy; they are not a substitute for this live pass, only for confirming the code logic itself didn't regress).

Minimum live pass, in order:
1. Log in as a real Super Admin test account (browser, human-entered credentials — do not automate this step).
2. `GET /auth/companies` → 200 with data.
3. `POST /companies` with a real test company + admin email → 201, temp password returned.
4. Log in as the newly created test Company Admin → succeeds.
5. As Super Admin: `POST /auth/assume-company` for the test company → 201; `GET /auth/me` shows assumed context; `GET /users` for the test company → 200 with the new admin's row.
6. As the test Company Admin: `GET /users` → only their own company's roster; attempt to `PATCH` a user id belonging to a *different* company (any pre-existing company works) → expect 403/404, never 200.
7. `POST /auth/end-assume-company` → 200; `GET /auth/me` no longer shows assumed context.
8. Query `select * from audit_trail where record_type in ('company','user') order by occurred_at desc limit 10;` — confirm rows exist for steps 3-7's actions.

If any of steps 1-8 fails, go to Stage 6 (rollback) rather than attempting a live forward-fix.

## Stage 6 — Rollback

**Code rollback (any time):** Render dashboard → Deploys → select the previous known-good deploy → "Rollback to this deploy." No data loss — SQLite DB/uploads live on the persistent disk, untouched by a code-only rollback.

**Database rollback (only after code is also rolled back to a version that doesn't call these routes):**
```sql
-- run in this order, in the Supabase SQL Editor
\i migrations/0012_users_company_admin_rls_down.sql
\i migrations/0011_companies_admin_rls_down.sql
\i migrations/0010_break_glass_rls_down.sql
```
(or paste each file's contents directly if `\i` isn't available in your SQL Editor). All three down-scripts use `DROP POLICY IF EXISTS`/plain `REVOKE`, safe to run even from a partially-applied state, no data loss — only removes policies/grants, never drops a table or column.

**Do not leave `SUPABASE_SERVICE_ROLE_KEY` configured or unconfigured as a rollback step** — it's inert without the code that reads it and safe to leave set either way.

## Stage 7 — Sign-off

Only after Stage 5 passes in full: update `PHARMAGPT_v1.0_FINAL_RELEASE_CERTIFICATION.md`'s verdict with a dated addendum citing this runbook's completion and the Stage 5 evidence, rather than editing the original NO-GO verdict in place (preserve the audit trail — see the pattern used for `DEPLOYMENT_REVIEW.md`'s correction note in Phase F.2).

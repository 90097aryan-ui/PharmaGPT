# Production Release Checklist — PharmaGPT v1.0 (Phase F.1)

Every item states what to run/check and what "done" looks like. Items marked **[BLOCKING]** must be complete before GO. This checklist assumes the deployment engineer has: a git remote push credential for `origin main` (or a PR-merge path), the live Supabase project's SQL Editor access, and the Render dashboard for this service.

## A. Source control / merge

- [ ] **[BLOCKING]** Review and commit all 48 modified + ~35 new/untracked files currently in the local working tree at `D:\PharmaAgent` (`git status --porcelain=v1 -uall` for the full list). This includes `pharmagpt/routes/companies.py`, `routes/users.py`, `services/identity_admin.py`, `pharmagpt/audit.py`, `migrations/0010`–`0012` (all 6 up/down files), and every Phase F audit/RBAC/sequencing fix.
- [ ] **[BLOCKING]** Push to `origin/main` (or merge the reviewing PR into it). Verify with `git log -1 origin/main` that the commit hash changes and `git show <new-hash>:pharmagpt/routes/companies.py` succeeds.
- [ ] Confirm Render's auto-deploy triggers and completes (Render dashboard → the service's Events/Deploys tab shows a new deploy from the new commit, status "Live").

## B. Database migrations

- [ ] **[BLOCKING] Pre-flight check before touching Supabase** — run this in the SQL Editor first to see what's already there (avoids the "policy already exists" abort risk documented in `DEPLOYMENT_VERIFICATION.md` §2/§4):
  ```sql
  select schemaname, tablename, policyname
  from pg_policies
  where tablename in ('break_glass_access', 'companies', 'users')
  order by tablename, policyname;

  select table_name, grantee, privilege_type
  from information_schema.role_table_grants
  where table_name in ('break_glass_access', 'companies', 'users', 'audit_trail')
    and grantee in ('authenticated', 'service_role')
  order by table_name, grantee;
  ```
- [ ] **[BLOCKING]** Run `migrations/0010_break_glass_rls_up.sql` in full in the Supabase SQL Editor. If any `create policy` statement errors "already exists," either skip just that statement (it's already applied) or run `0010_break_glass_rls_down.sql` first for a clean slate, then re-run `0010_..._up.sql` in full.
- [ ] **[BLOCKING]** Same for `migrations/0011_companies_admin_rls_up.sql`.
- [ ] **[BLOCKING]** Same for `migrations/0012_users_company_admin_rls_up.sql`.
- [ ] **[BLOCKING]** Re-run the pre-flight query above — confirm all expected policies now exist and `grantee='authenticated'` rows show `select`/`insert`/`update` (and `delete` for companies) on all three tables.
- [ ] Confirm `migrations/0009_phase3_grants_up.sql`'s grants (including `audit_trail`) are also active, using the same `information_schema.role_table_grants` query scoped to the 0009 table list — this migration is committed to git and presumed run historically, but was **not independently re-verified live** in this session; if its grants are also missing, Postgres-side audit-trail writes for the new admin routes will silently no-op.

## C. Environment variables

- [ ] **[BLOCKING]** In the Render dashboard (not `render.yaml` — this is a `sync: false` secret), add `SUPABASE_SERVICE_ROLE_KEY` to the `pharmagpt` service's environment variables. Without it, `POST /companies` (create company + first admin) and `POST /users` (invite user) will both fail with a 500 at the `get_service_role_client()` call — see `FINAL_DATABASE_ROOT_CAUSE.md` finding #3.
- [ ] Confirm `SUPABASE_URL` and `SUPABASE_ANON_KEY` are still set and point at the same Supabase project the migrations above were just run against (a mismatch here would silently point the app at an unconfigured project).
- [ ] Update `docs/DEPLOYMENT.md` / `.env.example` / `DEPLOYMENT_REVIEW.md` to remove the now-stale claim that `SUPABASE_SERVICE_ROLE_KEY` is "CLI-only, not needed by the web app" (documentation debt, not blocking, but should not ship stale).

## D. GRANT execution verification (repeat of B, framed as a gate)

- [ ] **[BLOCKING]** As a distinct sign-off step (not just "I ran the SQL"), execute the manual verification steps in Work Package 4 of the final certification report against the live, post-migration database and record the actual results (pass/fail per query) in `docs/FINAL_RELEASE_EVIDENCE/`.

## E. RLS verification

- [ ] **[BLOCKING]** With two real test accounts in two different companies (or one Super Admin + one Company Admin), manually exercise: `GET /companies` (Super Admin only, 200), `GET /companies` as a non-super-admin (403 before ever reaching Postgres, since `@require_role("super_admin")` gates it — confirm this stays a clean 403, not a raw DB error), `GET /users` as each Company Admin (should return only their own company's roster, never the other's).
- [ ] Confirm a Company Admin cannot `PATCH /companies/<id>` for any company (route is `@require_role("super_admin")`-only — no RLS-only reliance here, already enforced at the Flask layer).

## F. Storage verification

- [ ] Confirm the Render persistent disk (`pharmagpt-data`, 5GB, mounted at `/var/data`) is attached and `DB_PATH`/`UPLOAD_FOLDER`/`GENERATED_DOCS_PATH` all resolve under it (per `render.yaml`) — out of scope for this specific blocker but a standing pre-existing requirement worth re-confirming on any deploy touching `app.py`.

## G. Authentication verification

- [ ] Confirm ordinary login (non-admin) still works post-deploy — this is unaffected by this blocker but is the most basic smoke test and should be run first, before testing anything admin-specific.

## H. Company Administration verification

- [ ] **[BLOCKING]** Login as Super Admin. Confirm `GET /companies` returns data (not a 42501 error).
- [ ] **[BLOCKING]** Create a test company via `POST /companies` with a real test admin email. Confirm 201, a `temporary_password` in the response, and that the new admin can subsequently log in.
- [ ] Suspend then reactivate the test company; confirm both succeed and the audit_trail row (per §D) is written.

## I. Background jobs

- [ ] None specific to this blocker — no background job/queue infra was found referencing Company Administration or these migrations.

## J. Audit logging

- [ ] **[BLOCKING]** After each action in section H, query the Postgres `audit_trail` table directly (`select * from audit_trail where record_type = 'company' order by created_at desc limit 5;`) and confirm rows exist with the correct `company_id`, `actor_user_id`, and `action`. Recall this depends on 0009's grants (see §B) — if this table is also ungranted, `_audit_best_effort()` will silently swallow the failure and the UI action will still appear to succeed, masking a real audit gap. Do not skip this check.

## K. Health checks

- [ ] Confirm `/health` (Render's configured `healthCheckPath`) returns 200 post-deploy before considering the deploy stable.

## L. Rollback plan

If any **[BLOCKING]** item above fails after code is deployed:
1. **Code rollback**: Render dashboard → redeploy the previous commit (`7a98428` or whatever was last known-good) — standard Render rollback, no data loss (SQLite DB and uploads live on the persistent disk, untouched by a code-only rollback).
2. **Database rollback**: run `0012_users_company_admin_rls_down.sql`, `0011_companies_admin_rls_down.sql`, `0010_break_glass_rls_down.sql` (any order — reviewed as safe, idempotent, no data loss; see `DEPLOYMENT_VERIFICATION.md` §5). This returns `companies`/`users`/`break_glass_access` to default-deny, which is safe *only* if the application code is also rolled back to a version that doesn't call these routes — running the down-migrations while the new code is still live would reintroduce the original 42501 failures for admin routes (acceptable as a deliberate full rollback, not a partial one).
3. Do not roll back `SUPABASE_SERVICE_ROLE_KEY` — it is additive/harmless to leave configured even after a rollback.

## M. Go/No-Go checkpoints

1. **Checkpoint 1 (pre-deploy):** Sections A commit/push complete, B pre-flight query run and reviewed — proceed only if the plan for handling any pre-existing partial state (§B) is clear.
2. **Checkpoint 2 (post-migration, pre-code-deploy is not applicable here since code and DB must land together)**: Sections B, C complete — all pre-flight and post-migration verification queries return expected results.
3. **Checkpoint 3 (post-deploy smoke test):** Sections E, G, H, J, K all pass live. **This is the actual GO gate** — do not declare GO on code-deployed + migrations-run alone without this live pass.
4. If Checkpoint 3 fails on any blocking item: execute §L immediately, do not attempt forward-fixes in production under time pressure.

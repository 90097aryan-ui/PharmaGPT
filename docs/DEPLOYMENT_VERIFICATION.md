# Deployment Verification — Phase F.1

**Date:** 2026-07-24. Covers every Postgres migration (`migrations/0001`–`0012`), how/whether each has been executed, and deployment mechanics for the application code itself.

## 1. Migration inventory, order, and dependencies

| # | File | Purpose | Depends on | In git (`origin/main`)? | Executed live? |
|---|---|---|---|---|---|
| 0001 | `identity_tenancy` | Creates `companies`, `roles`, `users`, `company_settings`, `break_glass_access`; enables RLS default-deny on all five | — | Yes | Assumed yes — `roles` table must be populated for `routes/companies.py`'s `_get_role_id()` and login itself to work at all; no live evidence either way this session, but the app cannot authenticate anyone without it, so its absence would have been already fatal, not specific to this blocker |
| 0002 | `users_self_select` | `users_select_own` policy — a user reads their own row (login/TenantContext resolution) | 0001 | Yes | Assumed yes, same reasoning — login is reported working elsewhere in this codebase's test history |
| 0003 | `grants` | Base table GRANTs for 0001/0002 tables | 0001, 0002 | Yes | Assumed yes, same reasoning |
| 0004 | `core_schema` | `projects`, `documents`, etc. (Phase 2 business schema) | 0001 | Yes | Not this blocker's concern |
| 0005 | `projects_rls` | RLS for `projects`/`project_members` | 0004 | Yes | Not this blocker's concern |
| 0006 | `documents_rls` | RLS for `documents`/versions/categories/tags | 0004 | Yes | Not this blocker's concern |
| 0007 | `equipment_fixes_and_rls` | RLS for `equipment`/`equipment_links` | 0004 | Yes | Not this blocker's concern |
| 0008 | `qms_rls` | RLS for `deviations`/`capas`/`change_controls`/`risk_assessments`/`audit_trail` | 0004 | Yes | Not this blocker's concern |
| 0009 | `phase3_grants` | Base GRANTs for every 0005-0008 table, to both `service_role` and `authenticated` | 0004-0008 | **Yes** (`7d5b6ce`, in HEAD) | **NOT VERIFIED** — same class of gap as 0003 originally had (RLS policy without a paired base GRANT); no live re-test found in this session's available evidence. This table set includes `audit_trail`, which `pharmagpt/db/qms_repo.py::add_audit_entry()` writes to from the new `companies.py`/`users.py` audit calls — if 0009's grants are also not active, the Postgres-side audit trail for Company/User admin actions silently no-ops (it's wrapped in a bare `except Exception: logger.exception(...)`, by design, per the code's own comment acknowledging this exact risk) |
| 0010 | `break_glass_rls` | RLS + GRANT for `break_glass_access` (Assume Company Context) | 0001 | **No — untracked** | **FAIL**, confirmed live 2026-07-23 (`ENTERPRISE_ACCEPTANCE_TEST_REPORT.md` §4) |
| 0011 | `companies_admin_rls` | RLS + GRANT for `companies` (Company Administration) | 0001 | **No — untracked** | **FAIL**, confirmed live 2026-07-23 (§1) |
| 0012 | `users_company_admin_rls` | RLS + GRANT for `users` (User/Role Management) | 0001, 0002 | **No — untracked** | **FAIL**, confirmed live 2026-07-23 (§2) |

**Execution order requirement:** strictly sequential by number — each file's policies reference tables/columns created by earlier files (e.g. 0010-0012 all reference `roles`/`users` from 0001). Running 0010-0012 out of order relative to each other is safe (they touch disjoint tables: `break_glass_access`, `companies`, `users` respectively), but all three must run after 0001/0002, which is already satisfied since 0001/0002 are older, committed, and presumed applied.

## 2. How migrations are executed — this is itself a finding

**There is no migration framework, runner script, or CI/CD step anywhere in this codebase that executes `migrations/*.sql` against Postgres.** Confirmed by:

```
$ grep -rn "migrations/0010\|migration.*runner\|def run_migrations\|apply_migrations" --include=*.py .
(no runner found — only comments in application code referencing the files by name)
```

`docs/DATABASE.md:163` states explicitly: *"There is no migration framework in v0.6. Schema changes require [manual execution]... planned for v1.0."* Every migration file's own header comment confirms the intended process: **"Run in the Supabase SQL Editor."** This is a fully manual, human-driven, copy-paste operation with no tracking table recording which migrations have been applied to a given Supabase project (no `schema_migrations` or equivalent table is created by any of 0001-0012).

This has two consequences relevant to release-gating:

- **No automated or even queryable record exists of what has been run.** The only way to know migration state is to query live object privileges/policies directly (exact queries below) or to have a human's memory/notes — which is exactly the ambiguity that produced this blocker (0009's grants presumably ran fine via a similar manual process; 0010-0012 apparently did not, and no record exists explaining why, beyond `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`'s speculation).
- **The `up.sql` files are not idempotent** (`create policy`, not `create policy if not exists`) while the `down.sql` files are (`drop policy if exists`). If a partial run of e.g. `0011_companies_admin_rls_up.sql` already created `companies_super_admin_all` before failing on a later statement, re-running the whole file from the top will error `policy "companies_super_admin_all" already exists` and abort **before ever reaching the trailing `grant` line** — this is `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`'s own leading hypothesis for how this happened the first time, and it is a real risk for whoever re-attempts the fix, not merely a hypothetical. **Operational guidance:** before re-running any `_up.sql`, first query for pre-existing policies (query provided in `PRODUCTION_RELEASE_CHECKLIST.md`) and either run only the missing statements, or run the paired `_down.sql` first to get to a known-clean state, then the full `_up.sql`.

## 3. Missing execution — confirmed

0010, 0011, 0012 GRANT/CREATE POLICY statements are confirmed not active as of the last live test (2026-07-23, three independent reproductions — browser, curl+JWT, raw Python client — all yielding Postgres error `42501` with a hint naming the exact missing `GRANT` line). No later evidence exists in this repository that this has changed, and this session had no live access to re-test it directly.

## 4. Duplicate execution — cannot be ruled out, must be checked before re-running

Given point 2 above (no tracking table, non-idempotent `up.sql`), it is possible that 0010/0011/0012 were **partially** run at some point (e.g. the `create policy` statements succeeded, or some subset did) even though the end-to-end grant clearly did not take effect. Re-running a full `_up.sql` blind risks an abort on a "policy already exists" error partway through. See the checklist for the exact pre-flight query to run first.

## 5. Rollback risk

Each `_up.sql` has a paired `_down.sql` that has been reviewed and is low-risk:
- All three `_down.sql` files use `drop policy if exists` (safe to run even if the policy was never created) and a plain `revoke` (safe/no-op if the grant was never active).
- Rollback removes only the specific policies/grants each migration added — no data is deleted, no table is dropped, no column is altered. `companies`/`users`/`break_glass_access` themselves are untouched structurally.
- **Risk of rolling back**: reverting 0011/0012 while application code that expects them to be active is deployed would immediately reintroduce the exact 42501 failures described above for any live traffic hitting those routes — acceptable only as a deliberate "undo the whole feature" action, not a partial rollback.

## 6. Application code deployment status

Independent of the Postgres side entirely: **the application code for Company Administration is not deployed.** See [`FINAL_DATABASE_ROOT_CAUSE.md`](FINAL_DATABASE_ROOT_CAUSE.md) for full evidence (`git show HEAD:pharmagpt/routes/companies.py` fails — the file isn't in the commit Render builds). Deploying "just the database fix" without also merging and deploying the 48 files' worth of Phase F changes (`git diff --stat` from HEAD) would leave Render running a version of the app with no Company Administration UI or routes at all — the grants would be correctly configured for a feature that isn't there yet.

**No CI/CD pipeline file was found** in this repository (no `.github/workflows/`, no `render-build.sh` beyond the inline `buildCommand`) — deploys appear to be triggered by Render's standard "push to the connected branch" auto-deploy, meaning a `git push origin main` (after review/merge) is the actual mechanism that would ship this code, not a separate deploy step.

# Migration 0015 — Deployment Verification Procedure

Target: PharmaGPT Supabase project `qjhmqleaoelztruepmio` (region ap-south-1).
Current state (confirmed by direct inspection, 2026-08-14): none of migration 0015's
tables exist. `list_migrations` returns empty — this project does not use Supabase's
native migration tracking; `migrations/*.sql` are applied manually.

This procedure does not execute anything. It is the checklist to run through
at the point the deployment is explicitly approved.

## Pre-flight review (already completed, see final report)

- [x] `migrations/0015_rbac_org_framework_up.sql` reviewed line-by-line: every
      DDL statement is `create table if not exists` / `add column if not exists` /
      `create index if not exists` / idempotent `drop policy if exists` + `create policy`.
      No `drop table`, no `alter ... drop column`, no data-mutating statement anywhere.
- [x] The two helper functions the new RLS policies depend on
      (`current_user_company_id()`, `current_user_role_name()`) already exist live,
      confirmed via `information_schema.routines` — both are `SECURITY DEFINER`
      functions from migration 0013.
- [x] The one pre-existing table touched, `departments`, gets an additive
      `status` column with `default 'active' not null` — safe for its 7 existing
      rows — plus a new company_admin-scoped write policy (`departments` was
      previously read-only to `authenticated`). No existing policy is removed.
- [x] `users` gets two new nullable FK columns (`designation_id`,
      `reporting_manager_id`) — safe for its 31 existing rows, no backfill.
- [x] A matching, complete rollback file exists
      (`migrations/0015_rbac_org_framework_down.sql`), drops/revokes in correct
      reverse-dependency order.
- [x] Schema matches exactly what `pharmagpt/db/rbac_repo.py`,
      `pharmagpt/auth/rbac.py`, and `pharmagpt/routes/rbac.py` already query —
      no further schema change is needed for the existing Roles & Permissions
      UI (`admin_roles.js`) to become functional.

## Execution steps (when approved)

1. Take a manual note of current row counts for reference (already captured
   above: 8 companies, 31 users, 7 departments) so step 4 below has a baseline.
2. Run `migrations/0015_rbac_org_framework_up.sql` in the Supabase SQL Editor
   for project `qjhmqleaoelztruepmio` (per the migration file's own header
   comment — this codebase's established deployment method for these files).
3. If PostgREST does not pick up the new tables automatically within a minute,
   reload its schema cache (`NOTIFY pgrst, 'reload schema';` or a project
   restart from the Supabase dashboard).

## Post-deployment verification

### A. Tables exist
```sql
select table_name from information_schema.tables
where table_schema = 'public'
  and table_name in ('rbac_permissions','rbac_roles','rbac_role_permissions',
                      'rbac_user_roles','rbac_audit_log','designations','approval_levels');
```
Expect all 7 rows back.

### B. Permission catalog seeded correctly
```sql
select count(*) from rbac_permissions;  -- expect 120 (15 modules x 8 actions)
select count(*) from rbac_roles where company_id is null;  -- expect 21 (global templates)
```

### C. Existing companies/users/departments untouched
```sql
select count(*) from companies;    -- expect 8 (unchanged)
select count(*) from users;        -- expect 31 (unchanged)
select count(*) from departments;  -- expect 7 (unchanged)
select count(*) from departments where status = 'active';  -- expect 7 (new column, all default-backfilled)
select count(*) from users where designation_id is not null or reporting_manager_id is not null;
-- expect 0 (new columns, nullable, no backfill)
```

### D. Tenant isolation intact
- As an existing company_admin (real login), `GET /rbac/roles` returns only
  that company's own roles plus the 21 global templates — never another
  company's rows. RLS policies added by this migration are all scoped by
  `company_id = current_user_company_id()`, matching every other table's
  existing pattern; no cross-tenant read/write path is introduced.

### E. Authentication unchanged
- Existing login flow (`POST /auth/login`, `GET /auth/me`) is untouched by
  this migration — it adds new tables only, no change to `users`/`roles`/
  `companies` auth-relevant columns beyond the two new nullable FKs on `users`.
- Confirm an existing user can still log in and `GET /auth/me` returns the
  same shape as before, plus the (already-shipped) `accessible_workspaces` field.

### F. Existing admin access still functional
- An existing `company_admin` or `super_admin` account can still reach every
  screen they could before (Administration section, Assume Company Context,
  Companies/Users/Departments) — this migration does not modify `require_role`,
  `roles`, or any existing policy on those paths.
- `GET /rbac/permissions` (company_admin) now returns the 120-row catalog
  instead of a "table not found" error.

### G. Application-level regression
- Run: `pytest tests/test_rbac.py tests/test_org_structure.py tests/test_security_tenant_rbac_esig.py tests/test_workspace_access.py`
  and the full suite. `test_workspace_access.py`'s fail-open tests are
  expected to keep passing (deny-by-default is a separate, deliberate
  follow-up change — see `pharmagpt/auth/workspace_access.py`'s module
  docstring — not automatic just because the migration is applied).

## Rollback

If anything in section C/D/E/F fails: run
`migrations/0015_rbac_org_framework_down.sql` in the SQL Editor. It is a
complete, reverse-order teardown of everything this migration adds; nothing
outside the 7 new/altered objects listed above is touched.

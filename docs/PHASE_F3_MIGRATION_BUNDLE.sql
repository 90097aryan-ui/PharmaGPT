-- Phase F.3 — Supabase SQL Editor bundle
-- Run each section IN ORDER, top to bottom, in one Supabase SQL Editor session.
-- Source: migrations/0009_phase3_grants_up.sql, 0010_break_glass_rls_up.sql,
--         0011_companies_admin_rls_up.sql, 0012_users_company_admin_rls_up.sql
-- All four are idempotent (Phase F.2) — safe to re-run this whole file if interrupted.

-- ============================================================
-- STEP 0 — PRE-FLIGHT (read-only, run first, save the output)
-- ============================================================
select tablename, policyname
from pg_policies
where tablename in ('break_glass_access', 'companies', 'users')
order by tablename, policyname;

select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_name in ('break_glass_access', 'companies', 'users', 'audit_trail')
  and grantee in ('authenticated', 'service_role')
order by table_name, grantee;

-- ============================================================
-- STEP 1 — Confirm/repair migration 0009 grants (audit_trail)
-- Re-running is always safe: GRANT is a no-op if already applied.
-- ============================================================
grant select, insert, update, delete
    on projects, project_members,
       documents, document_versions, document_categories, tags, document_tags,
       equipment, equipment_links,
       deviations, capas, change_controls, risk_assessments, audit_trail
    to service_role;

grant select, insert, update, delete
    on projects, project_members,
       documents, document_versions, document_categories, tags, document_tags,
       equipment, equipment_links,
       deviations, capas, change_controls, risk_assessments
    to authenticated;

grant select, insert
    on audit_trail
    to authenticated;

-- ============================================================
-- STEP 2 — Migration 0010: break_glass_access (Assume Company Context)
-- ============================================================
drop policy if exists break_glass_insert_own on break_glass_access;
create policy break_glass_insert_own on break_glass_access
    for insert
    to authenticated
    with check (
        super_admin_user_id = auth.uid()
        and exists (
            select 1 from users u join roles r on r.id = u.role_id
            where u.id = auth.uid() and r.name = 'super_admin'
        )
    );

drop policy if exists break_glass_select_own on break_glass_access;
create policy break_glass_select_own on break_glass_access
    for select
    to authenticated
    using (super_admin_user_id = auth.uid());

drop policy if exists break_glass_update_own_revoke on break_glass_access;
create policy break_glass_update_own_revoke on break_glass_access
    for update
    to authenticated
    using (super_admin_user_id = auth.uid() and revoked_at is null)
    with check (super_admin_user_id = auth.uid());

grant select, insert, update on break_glass_access to authenticated;

-- ============================================================
-- STEP 3 — Migration 0011: companies
-- ============================================================
drop policy if exists companies_super_admin_all on companies;
create policy companies_super_admin_all on companies
    for all
    to authenticated
    using (
        exists (
            select 1 from users u join roles r on r.id = u.role_id
            where u.id = auth.uid() and r.name = 'super_admin'
        )
    )
    with check (
        exists (
            select 1 from users u join roles r on r.id = u.role_id
            where u.id = auth.uid() and r.name = 'super_admin'
        )
    );

drop policy if exists companies_company_admin_read_own on companies;
create policy companies_company_admin_read_own on companies
    for select
    to authenticated
    using (id = (select company_id from users where id = auth.uid()));

grant select, insert, update, delete on companies to authenticated;

-- ============================================================
-- STEP 4 — Migration 0012: users (company-scoped admin access)
-- ============================================================
drop policy if exists users_company_admin_read_company on users;
create policy users_company_admin_read_company on users
    for select
    to authenticated
    using (
        company_id = (select company_id from users where id = auth.uid())
        and company_id is not null
        and exists (
            select 1 from users u join roles r on r.id = u.role_id
            where u.id = auth.uid() and r.name = 'company_admin'
        )
    );

drop policy if exists users_company_admin_update_company on users;
create policy users_company_admin_update_company on users
    for update
    to authenticated
    using (
        company_id = (select company_id from users where id = auth.uid())
        and company_id is not null
        and exists (
            select 1 from users u join roles r on r.id = u.role_id
            where u.id = auth.uid() and r.name = 'company_admin'
        )
    )
    with check (company_id = (select company_id from users where id = auth.uid()));

grant select, update on users to authenticated;

-- ============================================================
-- STEP 5 — POST-MIGRATION VERIFICATION (run and save output)
-- Expect the same tables as Step 0 plus the 7 new policies below,
-- and audit_trail showing authenticated: SELECT, INSERT.
-- ============================================================
select tablename, policyname
from pg_policies
where tablename in ('break_glass_access', 'companies', 'users')
order by tablename, policyname;
-- Expected new rows:
--   break_glass_access | break_glass_insert_own
--   break_glass_access | break_glass_select_own
--   break_glass_access | break_glass_update_own_revoke
--   companies          | companies_company_admin_read_own
--   companies          | companies_super_admin_all
--   users              | users_company_admin_read_company
--   users              | users_company_admin_update_company

select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_name in ('break_glass_access', 'companies', 'users', 'audit_trail')
  and grantee in ('authenticated', 'service_role')
order by table_name, grantee;

select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_name = 'audit_trail'
  and grantee in ('authenticated', 'service_role');
-- Must show authenticated: SELECT, INSERT. If missing, re-run STEP 1.

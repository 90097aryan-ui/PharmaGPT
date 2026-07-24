-- Migration 0012 (up): RLS policies for User Management (Phase 3.5)
--
-- Root cause: users has only ever had users_select_own (migration 0002) —
-- a user reading their own row to resolve their TenantContext at login.
-- User Management (list/deactivate/reassign role within one's own company)
-- had no policy to operate under at all. This adds exactly that, scoped to
-- "your own company's roster," never cross-company — a company_admin
-- cannot see or touch another company's users through this policy.
--
-- Note: this does NOT add a policy letting a company_admin set role_id to
-- super_admin, or letting anyone give a super_admin row a company_id — the
-- trigger chk_users_super_admin_company_null (migration 0001) already
-- rejects both at the database level regardless of what RLS would allow,
-- so no additional CHECK is duplicated here.
--
-- A Super Admin's access to an existing company's user roster is
-- deliberately NOT granted here — it goes through Assume Company Context
-- (migration 0010): once assumed, the request's effective identity resolves
-- through the same company_admin-scoped policies below, because RLS
-- evaluates the session's real auth.uid() and role, and the assumed
-- company_id is a Flask-layer (not Postgres-layer) override applied to
-- SQLite business-data queries — the users/companies tables here are read
-- directly by the new admin routes using the authenticated user's own JWT,
-- so a Super Admin's browse-another-company's-users action is a distinct,
-- separately-designed path (see PHASE_3_5_IMPLEMENTATION_REPORT.md), not
-- something this policy needs to special-case.
--
-- Run in the Supabase SQL Editor. Rollback: 0012_users_company_admin_rls_down.sql.

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

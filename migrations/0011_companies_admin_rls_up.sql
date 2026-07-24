-- Migration 0011 (up): RLS policies for Company Administration (Phase 3.5)
--
-- Root cause: companies has existed since migration 0001 with RLS enabled
-- and zero policies (correctly default-deny — Company Administration had no
-- UI or backend at all until this phase). This activates the target policy
-- set: a super_admin has full CRUD (create/suspend/reactivate companies,
-- per PLATFORM_ARCHITECTURE.md §7's standing "creates companies" power);
-- a company_admin may read only their own company's row (basic profile
-- visibility), never another company's, and may not write to this table at
-- all (plan_tier/status changes stay Super-Admin-only).
--
-- Run in the Supabase SQL Editor. Rollback: 0011_companies_admin_rls_down.sql.

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

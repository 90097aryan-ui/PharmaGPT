-- Migration 0005 (up): current_company_id() helper + interim RLS for
-- projects/project_members (Phase 3.2, docs/PHASE3_EXECUTION_PLAN.md).
--
-- Scope: company_id-scoped access only. This is deliberately NARROWER than
-- DATABASE_ARCHITECTURE.md §13.2's full target policy for `projects` (which
-- also requires a project_members join, or Company Admin, for non-admin
-- visibility) — project_members has no real membership data yet (that lands
-- with Phase 7-equivalent work). Same "interim, not a preview" posture
-- 0002_users_self_select_up.sql already established for `users`.
--
-- Run this in the Supabase SQL Editor. Rollback: 0005_projects_rls_down.sql.

-- ── current_company_id() ────────────────────────────────────────────────────
-- Resolves the calling session's own company_id via auth.uid() -> users.
-- security definer + locked search_path: the standard Supabase pattern to
-- avoid RLS-policy self-recursion (this function is itself called FROM RLS
-- policies below, so it must not be re-subject to the calling policy).

create or replace function current_company_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
    select company_id from users where id = auth.uid();
$$;

-- ── projects ────────────────────────────────────────────────────────────────
-- Interim: any authenticated user may read/write rows in their own company.
-- Full target (company_admin OR project_members membership) lands once
-- project_members is populated with real data.

drop policy if exists projects_company_scoped on projects;
create policy projects_company_scoped on projects
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

-- ── project_members ─────────────────────────────────────────────────────────
-- Same interim posture. No rows exist yet (Phase 3.2 does not backfill
-- membership); this policy just means the table isn't default-deny-locked
-- once real membership rows start landing in a later phase.

drop policy if exists project_members_company_scoped on project_members;
create policy project_members_company_scoped on project_members
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

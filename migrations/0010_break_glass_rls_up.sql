-- Migration 0010 (up): RLS policies for break_glass_access — "Assume Company
-- Context" (Phase 3.5, Enterprise Validation Platform security remediation)
--
-- Root cause: break_glass_access has existed since migration 0001 with RLS
-- enabled and zero policies (deliberately default-deny at the time — no
-- application code touched it). A live Enterprise Acceptance Test found
-- Super Admin accounts (company_id IS NULL) could read every company's
-- business data unfiltered via several list endpoints, with no explicit,
-- logged, time-boxed grant of the kind PLATFORM_ARCHITECTURE.md §7/§13.2
-- already specifies ("administrative access to tenant content is an
-- explicit, logged, time-boxed break-glass action, not a standing
-- privilege"). This migration activates exactly that mechanism.
--
-- Scope: a super_admin may insert, select, and update (to set revoked_at)
-- only rows where they are the super_admin_user_id — never another admin's
-- grants, and never any other table. This uses the existing anon-key +
-- user-JWT pattern (get_authenticated_client) already used everywhere else
-- in the live app; no service-role client is introduced for this feature.
--
-- Run in the Supabase SQL Editor. Rollback: 0010_break_glass_rls_down.sql.

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

-- Update is scoped to revoking an still-open grant of your own — a
-- super_admin cannot extend expires_at or reassign a grant to someone else
-- via this policy (application code only ever sets revoked_at = now()).
drop policy if exists break_glass_update_own_revoke on break_glass_access;
create policy break_glass_update_own_revoke on break_glass_access
    for update
    to authenticated
    using (super_admin_user_id = auth.uid() and revoked_at is null)
    with check (super_admin_user_id = auth.uid());

-- Same "grant paired with a policy" discipline as 0003/0009 — a policy
-- alone is not sufficient without the base table-level GRANT.
grant select, insert, update on break_glass_access to authenticated;

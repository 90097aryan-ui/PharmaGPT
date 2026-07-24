-- Migration 0013 (up): HOTFIX — fix infinite recursion (42P17) in RLS
-- policies on `users`, introduced by migration 0012.
--
-- Root cause: users_company_admin_read_company and
-- users_company_admin_update_company (0012) each subquery `users` from
-- within a policy defined ON `users`:
--   (select company_id from users where id = auth.uid())
--   exists (select 1 from users u join roles r on r.id = u.role_id
--           where u.id = auth.uid() and r.name = 'company_admin')
-- Evaluating either policy for any SELECT/UPDATE on `users` re-triggers RLS
-- policy evaluation on `users` for the subquery, which re-triggers the same
-- policies again — infinite recursion, surfaced by Postgres as 42P17
-- "infinite recursion detected in policy for relation users". This broke
-- every login: routes/auth.py -> resolve_tenant_context() runs
-- `select ... from users where id = auth.uid()` as the authenticated user
-- (anon key + user JWT, RLS enforced) — see
-- pharmagpt/auth/context.py:57-63. Full writeup: HOTFIX_RLS_RECURSION.md.
--
-- Fix: replace the direct self-referencing subqueries with calls to two
-- SECURITY DEFINER helper functions. A SECURITY DEFINER function executes
-- as its owner (the role that ran this migration), and table owners are
-- exempt from RLS on their own tables by default (no `FORCE ROW LEVEL
-- SECURITY` is set anywhere in this schema) — so the lookup inside the
-- function bypasses RLS entirely instead of re-entering it, breaking the
-- recursion. This is the standard Postgres/Supabase pattern for this exact
-- failure mode. The scoping logic itself (own company only, company_admin
-- role only) is unchanged, so tenant isolation is preserved exactly as
-- migration 0012 defined it.
--
-- Scope: only the two 0012 policies that self-reference `users`. No other
-- policy in this schema subqueries its own table — 0010/break_glass_access
-- and 0011/companies subquery `users`, but that's a *different* table than
-- the one each policy is defined on, which is not self-reference and does
-- not recurse. Left untouched, per instruction not to modify unrelated
-- policies.
--
-- Idempotent: `create or replace function`, `drop policy if exists` +
-- `create policy`, and grants (safe to re-run) make this file safe to run
-- any number of times.
--
-- Run in the Supabase SQL Editor. Rollback: 0013_fix_users_rls_recursion_down.sql.

create or replace function current_user_company_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
    select company_id from users where id = auth.uid();
$$;

create or replace function current_user_role_name()
returns text
language sql
stable
security definer
set search_path = public
as $$
    select r.name from users u join roles r on r.id = u.role_id where u.id = auth.uid();
$$;

revoke all on function current_user_company_id() from public;
revoke all on function current_user_role_name() from public;
grant execute on function current_user_company_id() to authenticated;
grant execute on function current_user_role_name() to authenticated;

drop policy if exists users_company_admin_read_company on users;
create policy users_company_admin_read_company on users
    for select
    to authenticated
    using (
        company_id = current_user_company_id()
        and company_id is not null
        and current_user_role_name() = 'company_admin'
    );

drop policy if exists users_company_admin_update_company on users;
create policy users_company_admin_update_company on users
    for update
    to authenticated
    using (
        company_id = current_user_company_id()
        and company_id is not null
        and current_user_role_name() = 'company_admin'
    )
    with check (company_id = current_user_company_id());

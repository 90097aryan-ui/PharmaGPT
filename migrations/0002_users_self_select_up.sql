-- Migration 0002 (up): allow an authenticated user to read their own users row
--
-- Why this is needed now: Phase 2 auth is implemented with the anon key only
-- (no service-role key in application code — see pharmagpt/auth/context.py).
-- Migration 0001 enabled RLS on `users` with zero policies, which correctly
-- default-denies everyone — including a legitimately authenticated user
-- trying to read their own row to discover their company_id/role. Without
-- this policy, every login would succeed at the Supabase Auth layer and then
-- fail to resolve a TenantContext, because the `users` SELECT would return
-- zero rows under RLS.
--
-- Scope is deliberately minimal: a user may see only their own row (self,
-- not company-mates), via `id = auth.uid()`. This is strictly narrower than
-- the company_id-scoped policy set Phase 3 introduces, and does not preview
-- or replace it.

drop policy if exists users_select_own on users;
create policy users_select_own on users
    for select
    to authenticated
    using (id = auth.uid());

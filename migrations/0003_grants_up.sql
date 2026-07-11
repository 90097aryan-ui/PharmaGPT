-- Migration 0003 (up): base table-level GRANTs for the identity/tenancy tables
--
-- Root cause (Phase 2 step 2.4 investigation): migrations 0001/0002 enabled
-- RLS and added policies, but never issued explicit GRANT statements —
-- relying on Supabase's usual default-privilege provisioning to apply
-- automatically to new tables. It did not for this project. Confirmed
-- empirically: direct REST calls to /rest/v1/roles with both the anon and
-- service_role keys returned 403, { "code": "42501", "message":
-- "permission denied for table roles" }, with role-specific hints
-- ("GRANT SELECT ON public.roles TO service_role;" / "...TO anon;") —
-- reproduced identically on all five tables from migration 0001.
--
-- RLS policy evaluation is a separate, later-stage check than the base SQL
-- GRANT system: service_role's BYPASSRLS attribute skips RLS policies, but
-- does not substitute for a table-level GRANT, which was simply never
-- issued for these tables. This migration adds exactly that — nothing else.
--
-- Scope is deliberately minimal:
--   - service_role: full CRUD on all five tables. It is the platform's one
--     privileged administrative role (bootstrap, migrations, maintenance,
--     scheduled jobs) and already bypasses RLS by design — this GRANT is
--     what makes that bypass actually reach the tables, not a widening of
--     what service_role was always meant to be able to do.
--   - authenticated: SELECT only on `roles` and `users` — exactly the two
--     tables that already carry a `to authenticated` RLS policy
--     (roles_select_authenticated, users_select_own — migration 0002).
--     No grant is added for companies/company_settings/break_glass_access:
--     no RLS policy exists yet `to authenticated` on those tables, so a
--     table grant with no policy to pair it with would be inert today —
--     deferred to Phase 3's real policy set.
--   - anon: no grant is added. There is no RLS policy anywhere in this
--     schema scoped `to anon`, and Phase 2's auth code never queries these
--     tables as anon (it always presents either a user's access token,
--     which PostgREST evaluates as `authenticated`, or the service_role
--     key). A grant with no corresponding policy would be inert, so it is
--     intentionally omitted rather than added "just in case."

grant select, insert, update, delete
    on companies, roles, users, company_settings, break_glass_access
    to service_role;

grant select on roles to authenticated;
grant select on users to authenticated;

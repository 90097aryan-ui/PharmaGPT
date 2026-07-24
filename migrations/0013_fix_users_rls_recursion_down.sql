-- Migration 0013 (down): revert the RLS-recursion hotfix.
--
-- Drops the fixed company_admin policies and the two SECURITY DEFINER
-- helper functions this hotfix introduced. Deliberately does NOT recreate
-- migration 0012's original self-referencing policies (that would
-- reintroduce the 42P17 recursion this migration fixes) — run
-- 0012_users_company_admin_rls_down.sql afterward for a full rollback of
-- the User Management RLS feature back to migration 0011's state.

drop policy if exists users_company_admin_read_company on users;
drop policy if exists users_company_admin_update_company on users;

revoke execute on function current_user_company_id() from authenticated;
revoke execute on function current_user_role_name() from authenticated;

drop function if exists current_user_company_id();
drop function if exists current_user_role_name();

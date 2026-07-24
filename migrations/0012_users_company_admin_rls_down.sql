-- Migration 0012 (down): remove User Management RLS policies on users.

revoke update on users from authenticated;

drop policy if exists users_company_admin_read_company on users;
drop policy if exists users_company_admin_update_company on users;

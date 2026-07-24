-- Migration 0011 (down): remove Company Administration RLS policies on companies.

revoke select, insert, update, delete on companies from authenticated;

drop policy if exists companies_super_admin_all on companies;
drop policy if exists companies_company_admin_read_own on companies;

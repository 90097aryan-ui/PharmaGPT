-- Migration 0001 (down): drop Identity & Tenancy tables
-- Reverses 0001_identity_tenancy_up.sql in full. Safe to run at this stage
-- because no application code reads or writes these tables yet.

drop table if exists break_glass_access;
drop table if exists company_settings;

drop trigger if exists trg_users_super_admin_company_null on users;
drop function if exists chk_users_super_admin_company_null();
drop table if exists users;

drop policy if exists roles_select_authenticated on roles;
drop table if exists roles;

drop table if exists companies;

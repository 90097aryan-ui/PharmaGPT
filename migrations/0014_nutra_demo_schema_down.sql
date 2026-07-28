-- Migration 0014 (down): revert the enterprise organizational model
-- (modules, workflow_roles, departments, user_departments,
-- user_module_permissions, users.workflow_role_id).
--
-- Reverse dependency order: tables/columns that reference the two lookup
-- tables (user_module_permissions, user_departments, the users column)
-- before departments and workflow_roles/modules themselves.

revoke select on user_module_permissions from authenticated;
revoke select, insert, update, delete on user_module_permissions from service_role;
drop policy if exists user_module_permissions_company_admin_read_own on user_module_permissions;
drop table if exists user_module_permissions;

revoke select on user_departments from authenticated;
revoke select, insert, update, delete on user_departments from service_role;
drop policy if exists user_departments_company_admin_read_own on user_departments;
drop table if exists user_departments;

alter table users drop column if exists workflow_role_id;

revoke select on departments from authenticated;
revoke select, insert, update, delete on departments from service_role;
drop policy if exists departments_company_admin_read_own on departments;
drop table if exists departments;

revoke select on workflow_roles from authenticated;
revoke select, insert, update, delete on workflow_roles from service_role;
drop policy if exists workflow_roles_select_authenticated on workflow_roles;
drop table if exists workflow_roles;

revoke select on modules from authenticated;
revoke select, insert, update, delete on modules from service_role;
drop policy if exists modules_select_authenticated on modules;
drop table if exists modules;

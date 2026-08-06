-- Migration 0015 (down): revert the fine-grained RBAC + organizational
-- structure additions. Reverse dependency order.

revoke select, insert on rbac_audit_log from service_role;
drop policy if exists rbac_audit_log_company_admin_read_own on rbac_audit_log;
drop table if exists rbac_audit_log;

revoke select, insert, update, delete on rbac_user_roles from authenticated;
revoke select, insert, update, delete on rbac_user_roles from service_role;
drop policy if exists rbac_user_roles_company_admin_write_own on rbac_user_roles;
drop policy if exists rbac_user_roles_company_admin_read_own on rbac_user_roles;
drop table if exists rbac_user_roles;

revoke select, insert, update, delete on rbac_role_permissions from authenticated;
revoke select, insert, update, delete on rbac_role_permissions from service_role;
drop policy if exists rbac_role_permissions_company_admin_write on rbac_role_permissions;
drop policy if exists rbac_role_permissions_read on rbac_role_permissions;
drop table if exists rbac_role_permissions;

revoke select, insert, update on rbac_roles from authenticated;
revoke select, insert, update, delete on rbac_roles from service_role;
drop policy if exists rbac_roles_company_admin_update_own on rbac_roles;
drop policy if exists rbac_roles_company_admin_write_own on rbac_roles;
drop policy if exists rbac_roles_read on rbac_roles;
drop index if exists uq_rbac_roles_template_name;
drop index if exists uq_rbac_roles_company_name;
drop table if exists rbac_roles;

revoke select on rbac_permissions from authenticated;
revoke select, insert, update, delete on rbac_permissions from service_role;
drop policy if exists rbac_permissions_select_authenticated on rbac_permissions;
drop table if exists rbac_permissions;

revoke select on approval_levels from authenticated;
revoke select, insert, update, delete on approval_levels from service_role;
drop policy if exists approval_levels_company_admin_read_own on approval_levels;
drop table if exists approval_levels;

alter table users drop column if exists reporting_manager_id;
alter table users drop column if exists designation_id;

revoke select, insert, update on designations from authenticated;
revoke select, insert, update, delete on designations from service_role;
drop policy if exists designations_company_admin_update_own on designations;
drop policy if exists designations_company_admin_write_own on designations;
drop policy if exists designations_company_admin_read_own on designations;
drop table if exists designations;

revoke insert, update on departments from authenticated;
drop policy if exists departments_company_admin_write_own on departments;
alter table departments drop column if exists status;

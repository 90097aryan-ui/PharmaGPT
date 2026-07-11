-- Migration 0003 (down): revoke the grants added in 0003_grants_up.sql

revoke select on users from authenticated;
revoke select on roles from authenticated;

revoke select, insert, update, delete
    on companies, roles, users, company_settings, break_glass_access
    from service_role;

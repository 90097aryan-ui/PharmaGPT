-- Migration 0005 (down): remove the interim projects/project_members RLS
-- policies and the current_company_id() helper. Tables return to
-- default-deny (RLS still enabled, zero policies), same as immediately
-- after 0004.

drop policy if exists project_members_company_scoped on project_members;
drop policy if exists projects_company_scoped on projects;
drop function if exists current_company_id();

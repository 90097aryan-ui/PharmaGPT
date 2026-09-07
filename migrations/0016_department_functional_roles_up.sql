-- Migration 0016 (up): Department-scoped functional roles + department/
-- functional-role RBAC templates (Yuktav org/RBAC/workflow authorization
-- task).
--
-- Purely additive. Does NOT touch: roles, users.role_id, require_role(),
-- users.workflow_role_id (migration 0014, left in place for backward
-- compatibility — no route reads it for authorization; it is superseded as
-- a routing input by user_departments.workflow_role_id below, not removed),
-- the existing 21 rbac_roles templates (migration 0015), or any existing
-- RLS policy (the new column/rows ride on tables whose policies already
-- cover them: user_departments' existing company_admin policies apply to
-- all its columns; rbac_permissions'/rbac_roles' existing select-all /
-- template-read policies apply to all rows regardless of content).
--
-- Adds:
--   - user_departments.workflow_role_id   nullable FK -> workflow_roles.id.
--     Functional role becomes a property of the (user, department)
--     MEMBERSHIP, not a single global users.workflow_role_id — this is
--     what makes "QA Reviewer" and "Production Reviewer" distinct
--     assignments for the same user rather than one ambiguous global role.
--   - rbac_permissions: 'Submit' and 'Reject' actions, for all 15 existing
--     modules (additive rows only; the original 8 actions are untouched).
--   - rbac_roles: 23 new global templates (company_id null, is_template
--     true), one per (Department, Functional Role) cell in the target org
--     chart — QA Coordinator/Admin, QA/Production/Warehouse/PPIC/
--     Engineering/QC/Validation Initiator/Reviewer/Approver, and Plant
--     Head / Approver. Company-clonable via the existing, unmodified
--     pharmagpt/db/org_structure_repo.py::_clone_role_templates() /
--     provision_org_defaults_for_company() — no code change needed there;
--     grant computation for these templates is
--     pharmagpt/services/rbac_defaults.py::default_grants_for_role(),
--     extended in this same change to recognize these 23 names.
--
-- Run this in the Supabase SQL Editor. Rollback: 0016_department_functional_roles_down.sql.

-- ── user_departments.workflow_role_id ──────────────────────────────────────

alter table user_departments add column if not exists workflow_role_id smallint null
    references workflow_roles(id);

create index if not exists idx_user_departments_workflow_role_id on user_departments (workflow_role_id);

-- ── rbac_permissions: add 'Submit' and 'Reject' actions ───────────────────

insert into rbac_permissions (module, action)
select m, a
from unnest(array[
    'Dashboard', 'Projects', 'Validation', 'Risk Assessment', 'Equipment Library',
    'Document Control', 'Knowledge Base', 'AI Assistant', 'Deviations', 'CAPA',
    'Change Control', 'QMS', 'Warehouse', 'Administration', 'Reports'
]) as m
cross join unnest(array['Submit', 'Reject']) as a
on conflict (module, action) do nothing;

-- ── rbac_roles: 23 new department/functional-role global templates ───────
-- department_code matches the codes already seeded (or added) via
-- pharmagpt/services/rbac_defaults.py::DEFAULT_DEPARTMENTS — resolved to a
-- real departments.id only at clone time, never string-matched afterward
-- (same discipline the existing 21 templates already follow).

insert into rbac_roles (name, description, department_code, is_system, is_template) values
    ('QA Coordinator/Admin', 'Departmental QMS/Validation/Document Control administrator for Quality Assurance.', 'QA', true, true),
    ('QA Initiator',         'Initiates QMS and Document Control records for Quality Assurance.',                 'QA', true, true),
    ('QA Reviewer',          'Reviews QMS, Validation and Document Control records for Quality Assurance.',       'QA', true, true),
    ('QA Approver',          'Approves QMS, Validation and Document Control records for Quality Assurance.',      'QA', true, true),

    ('Production Initiator', 'Initiates QMS and Document Control records for Production.',                       'PRODUCTION', true, true),
    ('Production Reviewer',  'Reviews QMS, Validation and Document Control records for Production.',             'PRODUCTION', true, true),
    ('Production Approver',  'Approves QMS, Validation and Document Control records for Production.',            'PRODUCTION', true, true),

    ('Warehouse Initiator',  'Initiates QMS and Document Control records for Warehouse.',                         'WAREHOUSE', true, true),
    ('Warehouse Reviewer',   'Reviews QMS, Validation and Document Control records for Warehouse.',               'WAREHOUSE', true, true),
    ('Warehouse Approver',   'Approves QMS, Validation and Document Control records for Warehouse.',              'WAREHOUSE', true, true),

    ('PPIC Initiator',       'Initiates QMS and Document Control records for PPIC.',                              'PPIC', true, true),
    ('PPIC Reviewer',        'Reviews QMS and Document Control records for PPIC.',                                'PPIC', true, true),
    ('PPIC Approver',        'Approves QMS and Document Control records for PPIC.',                               'PPIC', true, true),

    ('Engineering Initiator','Initiates QMS and Document Control records for Engineering.',                       'ENGINEERING', true, true),
    ('Engineering Reviewer', 'Reviews QMS, Validation and Document Control records for Engineering.',             'ENGINEERING', true, true),
    ('Engineering Approver', 'Approves QMS, Validation and Document Control records for Engineering.',            'ENGINEERING', true, true),

    ('QC Initiator',         'Initiates QMS and Document Control records for Quality Control.',                   'QC', true, true),
    ('QC Reviewer',          'Reviews QMS, Validation and Document Control records for Quality Control.',         'QC', true, true),
    ('QC Approver',          'Approves QMS, Validation and Document Control records for Quality Control.',        'QC', true, true),

    ('Validation Initiator', 'Initiates QMS, Validation and Document Control records for Validation.',            'VALIDATION', true, true),
    ('Validation Reviewer',  'Reviews QMS, Validation and Document Control records for Validation.',              'VALIDATION', true, true),
    ('Validation Approver',  'Approves QMS, Validation and Document Control records for Validation.',             'VALIDATION', true, true),

    ('Plant Head / Approver','Highest cross-department approval authority across the plant.',                    'PLANT_HEAD', true, true)
on conflict (name) where company_id is null do nothing;

-- Migration 0016 (down): reverse 0016_department_functional_roles_up.sql.
-- Order matters: remove the 23 templates before their would-be dependents
-- (none exist yet — templates are never assigned directly, only cloned),
-- then the added actions, then the added column.

delete from rbac_roles where company_id is null and name in (
    'QA Coordinator/Admin', 'QA Initiator', 'QA Reviewer', 'QA Approver',
    'Production Initiator', 'Production Reviewer', 'Production Approver',
    'Warehouse Initiator', 'Warehouse Reviewer', 'Warehouse Approver',
    'PPIC Initiator', 'PPIC Reviewer', 'PPIC Approver',
    'Engineering Initiator', 'Engineering Reviewer', 'Engineering Approver',
    'QC Initiator', 'QC Reviewer', 'QC Approver',
    'Validation Initiator', 'Validation Reviewer', 'Validation Approver',
    'Plant Head / Approver'
);

delete from rbac_permissions where action in ('Submit', 'Reject');

drop index if exists idx_user_departments_workflow_role_id;
alter table user_departments drop column if exists workflow_role_id;

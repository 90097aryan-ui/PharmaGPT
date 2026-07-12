-- Migration 0008 (up): interim RLS for the Phase 3.5 QMS record tables
-- (docs/PHASE3_EXECUTION_PLAN.md) — deviations, capas, change_controls,
-- risk_assessments, and audit_trail (already RLS-enabled with zero
-- policies since 0004; this adds its first real policy).
--
-- attachments/comments/approvals are deliberately left at default-deny —
-- Phase 3.5's dual-write does not write to them yet (see
-- pharmagpt/db/qms_repo.py's module docstring: scope is the four flat
-- record tables plus audit_trail only, not the full shared-table set).
--
-- Run in the Supabase SQL Editor. Rollback: 0008_qms_rls_down.sql.

create policy deviations_company_scoped on deviations
    for all to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

create policy capas_company_scoped on capas
    for all to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

create policy change_controls_company_scoped on change_controls
    for all to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

create policy risk_assessments_company_scoped on risk_assessments
    for all to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

-- audit_trail is append-only by design (DATABASE_ARCHITECTURE.md §9.2):
-- "The table's RLS policy set grants INSERT and SELECT only ... A missing
-- policy is a hard database-level refusal, not a convention." INSERT and
-- SELECT are therefore two separate, narrower policies here, not "for all"
-- — there is deliberately no UPDATE/DELETE policy for any role.

create policy audit_trail_insert_company_scoped on audit_trail
    for insert to authenticated
    with check (company_id = current_company_id());

create policy audit_trail_select_company_scoped on audit_trail
    for select to authenticated
    using (company_id = current_company_id());

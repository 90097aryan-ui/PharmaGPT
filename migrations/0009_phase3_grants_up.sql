-- Migration 0009 (up): base table-level GRANTs for the Phase 3.2-3.5 tables
--
-- Root cause (discovered during Phase 3.6 pre-cutover validation): migrations
-- 0005-0008 enabled RLS and added policies for every Phase 3.2-3.5 table, but
-- -- exactly the same gap 0003 already fixed once for the identity/tenancy
-- tables -- never issued the paired GRANT statements. Confirmed empirically:
-- both the service_role key (used by scripts/backfill_*.py and
-- scripts/check_*_parity.py) and the authenticated role (used by the live
-- app's dual-write repos via get_authenticated_client()) got
-- "permission denied for table X" / 42501 on every table below.
--
-- Same rationale as 0003_grants_up.sql: RLS policy evaluation is a separate,
-- later-stage check than the base SQL GRANT system. service_role's
-- BYPASSRLS attribute skips RLS policies but does not substitute for a
-- table-level GRANT; authenticated needs a GRANT that pairs with each
-- existing "to authenticated" policy for that grant to do anything.
--
-- Scope: exactly the tables that already carry an authenticated-scoped RLS
-- policy from 0005-0008, nothing beyond -- same "grant paired with a policy,
-- not just in case" discipline as 0003.
--
-- Run in the Supabase SQL Editor. Rollback: 0009_phase3_grants_down.sql.

grant select, insert, update, delete
    on projects, project_members,
       documents, document_versions, document_categories, tags, document_tags,
       equipment, equipment_links,
       deviations, capas, change_controls, risk_assessments, audit_trail
    to service_role;

grant select, insert, update, delete
    on projects, project_members,
       documents, document_versions, document_categories, tags, document_tags,
       equipment, equipment_links,
       deviations, capas, change_controls, risk_assessments
    to authenticated;

-- audit_trail is append-only by design (DATABASE_ARCHITECTURE.md §9.2,
-- mirrored from 0008's insert-only/select-only policy split): no update or
-- delete grant for authenticated.
grant select, insert
    on audit_trail
    to authenticated;

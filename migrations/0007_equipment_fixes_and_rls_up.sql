-- Migration 0007 (up): Phase 3.4 (Equipment Library Migration,
-- docs/PHASE3_EXECUTION_PLAN.md) — two 0004 schema corrections found while
-- implementing this milestone, plus interim RLS for equipment/equipment_links.
--
-- Corrections (safe: `equipment` is still empty in every environment this
-- has been applied to, per Phase 3.1's confirmed deployment):
--   1. equipment.gmp_impact was created as `boolean`, but the current
--      shipped build (equipment_database.py EQUIPMENT_SCHEMA) stores it as
--      a three-value text enum ('Direct' | 'Indirect' | 'No Impact') — a
--      boolean cannot represent 'Indirect' without lossy collapsing.
--      DATABASE_ARCHITECTURE.md §4.3/§10 do not specify a type for this
--      field beyond naming it, so this is a 0004 implementation bug being
--      fixed, not a reinterpretation of the frozen document.
--   2. equipment.notes has no column at all in 0004, but the current
--      shipped build has a free-text `notes` field on every equipment
--      record. DATABASE_ARCHITECTURE.md §4.3 says the target table carries
--      "the same field groups already validated in the current build's
--      equipment table" — notes is part of that build; omitting it would
--      be silent data loss on migration, not a deliberate scope cut.
--
-- Run in the Supabase SQL Editor. Rollback: 0007_equipment_fixes_and_rls_down.sql.

alter table equipment alter column gmp_impact type text using gmp_impact::text;
alter table equipment add column if not exists notes text null;

drop policy if exists equipment_company_scoped on equipment;
create policy equipment_company_scoped on equipment
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

drop policy if exists equipment_links_company_scoped on equipment_links;
create policy equipment_links_company_scoped on equipment_links
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

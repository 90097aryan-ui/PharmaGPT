-- Migration 0007 (down): remove the interim equipment/equipment_links RLS
-- policies and revert the two 0004 corrections. Only safe while `equipment`
-- is still empty (gmp_impact text -> boolean will fail on any row holding
-- 'Indirect').

drop policy if exists equipment_links_company_scoped on equipment_links;
drop policy if exists equipment_company_scoped on equipment;

alter table equipment drop column if exists notes;
alter table equipment alter column gmp_impact type boolean using gmp_impact::boolean;

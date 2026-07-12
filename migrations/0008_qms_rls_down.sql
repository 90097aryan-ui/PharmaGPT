-- Migration 0008 (down): remove the interim QMS RLS policies. Tables
-- return to default-deny (RLS still enabled, zero policies).

drop policy if exists audit_trail_select_company_scoped on audit_trail;
drop policy if exists audit_trail_insert_company_scoped on audit_trail;
drop policy if exists risk_assessments_company_scoped on risk_assessments;
drop policy if exists change_controls_company_scoped on change_controls;
drop policy if exists capas_company_scoped on capas;
drop policy if exists deviations_company_scoped on deviations;

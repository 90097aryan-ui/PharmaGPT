-- Migration 0006 (down): remove the interim Document Engine RLS policies.
-- Tables return to default-deny (RLS still enabled, zero policies).

drop policy if exists document_tags_company_scoped on document_tags;
drop policy if exists tags_company_scoped on tags;
drop policy if exists document_categories_company_scoped on document_categories;
drop policy if exists document_versions_company_scoped on document_versions;
drop policy if exists documents_company_scoped on documents;

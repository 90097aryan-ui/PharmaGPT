-- Migration 0006 (up): interim RLS for the Document Engine tables used by
-- Phase 3.3 (Knowledge Base Migration, docs/PHASE3_EXECUTION_PLAN.md).
--
-- Same posture as 0005: company_id-scoped only, via the current_company_id()
-- helper 0005 already created. document_references is left untouched here
-- (default-deny) since nothing writes to it yet — citation support lands
-- when a document type actually cites another.
--
-- Run in the Supabase SQL Editor. Rollback: 0006_documents_rls_down.sql.

drop policy if exists documents_company_scoped on documents;
create policy documents_company_scoped on documents
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

drop policy if exists document_versions_company_scoped on document_versions;
create policy document_versions_company_scoped on document_versions
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

drop policy if exists document_categories_company_scoped on document_categories;
create policy document_categories_company_scoped on document_categories
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

drop policy if exists tags_company_scoped on tags;
create policy tags_company_scoped on tags
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

drop policy if exists document_tags_company_scoped on document_tags;
create policy document_tags_company_scoped on document_tags
    for all
    to authenticated
    using (company_id = current_company_id())
    with check (company_id = current_company_id());

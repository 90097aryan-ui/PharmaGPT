-- Migration 0017 (up): Company branding foundation (Yuktav — Client Company
-- Branding roadmap item).
--
-- Purely additive. Extends the existing company_settings table (created by
-- migration 0001 specifically to hold frequently-adjusted per-company
-- configuration separate from the companies tenant-root row, so this data
-- doesn't churn that row) — it already reserved a `branding` jsonb column
-- for exactly this purpose, so that column is reused for basic branding
-- preferences rather than duplicated. The companies table itself, and the
-- rest of the tenant/company architecture, are untouched by this migration.
--
-- New company_settings columns:
--   logo_url                   text null   -- path/URL to an uploaded logo.
--                               No Supabase Storage integration exists yet
--                               (docs/02_TECHNICAL_ARCHITECTURE.md §14) —
--                               this column only stores a reference string;
--                               upload handling and DOCX injection are
--                               explicitly out of scope for this migration.
--   address                    text null   -- company mailing address
--   contact_email               text null
--   contact_phone                text null
--   regulatory_identifiers      jsonb not null default '{}'::jsonb
--                               -- flexible per industry_segment (FDA
--                               registration #, GMP license #, ISO
--                               certificate #, ...); not a fixed column set
--                               since required identifiers vary by segment
--   document_numbering_prefix   text null   -- short prefix reserved for a
--                               future document-numbering scheme; NOT wired
--                               into any numbering logic by this migration
--
-- company_settings has zero application-code readers/writers as of this
-- migration (only migrations 0001/0003/0004 reference the table name, all
-- schema-only) and RLS on it remains at the migration-0001 default-deny
-- posture (enabled, zero policies) — unchanged here; server-side code
-- reaches it via the service-role client only, exactly as already
-- documented in 0001_identity_tenancy_up.sql. No existing row is affected:
-- no company_settings rows exist yet, and new columns default to NULL /
-- '{}'::jsonb, so no backfill is required and no existing company loses
-- functionality.
--
-- Run this in the Supabase SQL Editor. Rollback: 0017_company_branding_down.sql.

alter table company_settings add column if not exists logo_url text null;
alter table company_settings add column if not exists address text null;
alter table company_settings add column if not exists contact_email text null;
alter table company_settings add column if not exists contact_phone text null;
alter table company_settings add column if not exists regulatory_identifiers jsonb not null default '{}'::jsonb;
alter table company_settings add column if not exists document_numbering_prefix text null;

-- Reasonable length limits (defense in depth — also enforced at the
-- application layer in routes/companies.py). ALTER TABLE ADD CONSTRAINT has
-- no IF NOT EXISTS in Postgres — guarded via pg_constraint, same idiom as
-- migration 0004's fk_documents_current_version.
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_logo_url_len') then
        alter table company_settings add constraint chk_company_settings_logo_url_len
            check (logo_url is null or char_length(logo_url) <= 2048);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_address_len') then
        alter table company_settings add constraint chk_company_settings_address_len
            check (address is null or char_length(address) <= 1000);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_contact_email_len') then
        alter table company_settings add constraint chk_company_settings_contact_email_len
            check (contact_email is null or char_length(contact_email) <= 320);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_contact_phone_len') then
        alter table company_settings add constraint chk_company_settings_contact_phone_len
            check (contact_phone is null or char_length(contact_phone) <= 40);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_doc_prefix_len') then
        alter table company_settings add constraint chk_company_settings_doc_prefix_len
            check (document_numbering_prefix is null or char_length(document_numbering_prefix) <= 20);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_doc_prefix_format') then
        alter table company_settings add constraint chk_company_settings_doc_prefix_format
            check (document_numbering_prefix is null or document_numbering_prefix ~ '^[A-Za-z0-9-]+$');
    end if;
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_regulatory_identifiers_size') then
        alter table company_settings add constraint chk_company_settings_regulatory_identifiers_size
            check (char_length(regulatory_identifiers::text) <= 4000);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'chk_company_settings_branding_size') then
        alter table company_settings add constraint chk_company_settings_branding_size
            check (char_length(branding::text) <= 4000);
    end if;
end $$;

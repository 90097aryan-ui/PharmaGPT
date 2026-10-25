-- Migration 0017 (down): reverse 0017_company_branding_up.sql.
-- Drops the added constraints, then the added columns. The pre-existing
-- `branding` jsonb column (from migration 0001) is NOT dropped — it was
-- reused, not created, by the up migration; only the size constraint added
-- on top of it is removed.

alter table company_settings drop constraint if exists chk_company_settings_branding_size;
alter table company_settings drop constraint if exists chk_company_settings_regulatory_identifiers_size;
alter table company_settings drop constraint if exists chk_company_settings_doc_prefix_format;
alter table company_settings drop constraint if exists chk_company_settings_doc_prefix_len;
alter table company_settings drop constraint if exists chk_company_settings_contact_phone_len;
alter table company_settings drop constraint if exists chk_company_settings_contact_email_len;
alter table company_settings drop constraint if exists chk_company_settings_address_len;
alter table company_settings drop constraint if exists chk_company_settings_logo_url_len;

alter table company_settings drop column if exists document_numbering_prefix;
alter table company_settings drop column if exists regulatory_identifiers;
alter table company_settings drop column if exists contact_phone;
alter table company_settings drop column if exists contact_email;
alter table company_settings drop column if exists address;
alter table company_settings drop column if exists logo_url;

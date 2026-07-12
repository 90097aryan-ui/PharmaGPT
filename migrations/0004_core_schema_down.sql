-- Migration 0004 (down): drop the core platform schema.
-- Reverse dependency order. Does not touch companies/roles/users/
-- company_settings/break_glass_access (owned by 0001).

drop table if exists invoices;
drop table if exists plans;
drop table if exists subscriptions;
drop table if exists api_keys;
drop table if exists integration_configs;
drop table if exists data_retention_policies;
drop table if exists signature_events;
drop table if exists spare_parts;
drop table if exists preventive_maintenance_records;
drop table if exists calibration_records;
drop table if exists role_permissions;
drop table if exists permissions;

drop table if exists search_index;
drop table if exists notifications;

drop table if exists ai_usage_ledger;
drop table if exists ai_jobs;
drop table if exists ai_messages;
drop table if exists ai_conversations;

drop table if exists approvals;
drop table if exists comments;
drop table if exists attachments;
drop table if exists audit_trail;

drop table if exists risk_assessments;
drop table if exists change_controls;
drop table if exists capas;
drop table if exists deviations;

drop table if exists equipment_links;

drop table if exists document_references;
drop table if exists document_tags;
alter table if exists documents drop constraint if exists fk_documents_current_version;
drop table if exists document_versions;
drop table if exists documents;
drop table if exists tags;
drop table if exists document_categories;

drop table if exists equipment;

drop table if exists project_members;
drop table if exists projects;

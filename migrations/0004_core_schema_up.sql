-- Migration 0004 (up): Core platform schema
-- DATABASE_ARCHITECTURE.md §4.2-4.8 — every table beyond Identity & Tenancy
-- (companies/roles/users/company_settings/break_glass_access, already created
-- by 0001). Table order follows IMPLEMENTATION_ROADMAP.md §7.1 exactly.
--
-- Scope: schema only, Phase 3.1 (docs/PHASE3_EXECUTION_PLAN.md). No
-- application code reads or writes any table created here yet — that lands
-- per-domain in Phase 3.2 (Projects) through 3.5 (QMS). Every table is
-- created with RLS enabled and zero policies (default-deny), identical
-- posture to 0001: unreachable via the anon/authenticated PostgREST roles,
-- untouched by the service-role key path until each domain's own cutover
-- adds its reviewed company-scoped policy set.
--
-- Deletion policy follows DATABASE_ARCHITECTURE.md §5.3 exactly:
--   company_id FKs            -> no ON DELETE clause (= NO ACTION / restrict)
--   project_id FKs (nullable) -> ON DELETE SET NULL
--   true sub-entity FKs       -> ON DELETE CASCADE
--   polymorphic (record_type/record_id) -> no FK at all (§22 risk, accepted)
--
-- Run this in the Supabase SQL Editor (Project -> SQL Editor -> New query).
-- Rollback: run 0004_core_schema_down.sql.

-- ── Projects & Work Product (§4.2) ─────────────────────────────────────────

create table projects (
    id               uuid primary key default gen_random_uuid(),
    company_id       uuid not null references companies(id),
    name             text not null,
    status           text not null default 'active',
    owner_user_id    uuid null references users(id),
    approver_user_id uuid null references users(id),
    target_date      date null,
    risk_category    text null,
    protocol_number  text null,
    report_number    text null,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create index idx_projects_company_id on projects (company_id);
create index idx_projects_company_id_status on projects (company_id, status);

create table project_members (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    project_id  uuid not null references projects(id) on delete cascade,
    user_id     uuid not null references users(id),
    project_role text not null default 'member',
    created_at  timestamptz not null default now(),
    constraint uq_project_members_project_user unique (project_id, user_id)
);

create index idx_project_members_company_id on project_members (company_id);
create index idx_project_members_project_id on project_members (project_id);
create index idx_project_members_user_id on project_members (user_id);

-- ── Equipment Library (§4.3) ────────────────────────────────────────────────

create table equipment (
    id                    uuid primary key default gen_random_uuid(),
    company_id            uuid not null references companies(id),
    equipment_code        text null,
    name                  text not null,
    category              text null,
    equipment_type        text null,
    tag_number            text null,
    model                 text null,
    manufacturer          text null,
    vendor                text null,
    serial_number         text null,
    asset_number          text null,
    plant                 text null,
    block                 text null,
    department            text null,
    area                  text null,
    room                  text null,
    line                  text null,
    installation_date     date null,
    commissioning_date    date null,
    qualification_status  text null,
    validation_status     text null,
    qualification_type    text null,
    criticality            text null,
    gmp_impact            boolean null,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

create index idx_equipment_company_id on equipment (company_id);

-- ── Document Engine (§4.4) ──────────────────────────────────────────────────

create table document_categories (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    name        text not null,
    created_at  timestamptz not null default now(),
    constraint uq_document_categories_company_name unique (company_id, name)
);

create index idx_document_categories_company_id on document_categories (company_id);

create table tags (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    name        text not null,
    created_at  timestamptz not null default now(),
    constraint uq_tags_company_name unique (company_id, name)
);

create index idx_tags_company_id on tags (company_id);

create table documents (
    id                 uuid primary key default gen_random_uuid(),
    company_id         uuid not null references companies(id),
    project_id         uuid null references projects(id) on delete set null,
    source_context     text not null check (source_context in ('knowledge_base', 'project')),
    document_type      text not null,
    status             text not null default 'draft' check (status in
                           ('draft', 'in_review', 'qa_review', 'approved', 'obsolete', 'archived')),
    current_version_id uuid null,
    owner_user_id      uuid null references users(id),
    category_id        uuid null references document_categories(id),
    effective_date     date null,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create index idx_documents_company_id on documents (company_id);
create index idx_documents_company_id_status on documents (company_id, status);
create index idx_documents_company_id_project_id on documents (company_id, project_id);
create index idx_documents_company_id_type_status on documents (company_id, document_type, status);
create index idx_documents_active on documents (company_id, status) where status <> 'archived';

create table document_versions (
    id             uuid primary key default gen_random_uuid(),
    company_id     uuid not null references companies(id),
    document_id    uuid not null references documents(id),
    major_version  integer not null default 1,
    minor_version  integer not null default 0,
    storage_path   text null,
    checksum       text null,
    content_type   text null,
    size_bytes     bigint null,
    extracted_text text null,
    author_user_id uuid null references users(id),
    lifecycle_state_at_snapshot text null,
    created_at     timestamptz not null default now()
);

create index idx_document_versions_company_id on document_versions (company_id);
create index idx_document_versions_document_id on document_versions (document_id);

alter table documents
    add constraint fk_documents_current_version
    foreign key (current_version_id) references document_versions(id);

create table document_tags (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    document_id uuid not null references documents(id) on delete cascade,
    tag_id      uuid not null references tags(id) on delete cascade,
    constraint uq_document_tags_document_tag unique (document_id, tag_id)
);

create index idx_document_tags_company_id on document_tags (company_id);

create table document_references (
    id                     uuid primary key default gen_random_uuid(),
    company_id             uuid not null references companies(id),
    referencing_document_id uuid not null references documents(id),
    referenced_document_id  uuid not null references documents(id),
    referenced_version_id   uuid not null references document_versions(id),
    created_at             timestamptz not null default now()
);

create index idx_document_references_company_id on document_references (company_id);
create index idx_document_references_referencing on document_references (referencing_document_id);
create index idx_document_references_referenced on document_references (referenced_document_id);

-- ── Equipment <-> everything else (§6) ──────────────────────────────────────
-- Polymorphic: no FK on (record_type, record_id) by design (§22 risk,
-- accepted — application-layer validation + fixed enum for record_type).

create table equipment_links (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    equipment_id uuid not null references equipment(id),
    record_type  text not null,
    record_id    uuid not null,
    created_at   timestamptz not null default now()
);

create index idx_equipment_links_company_id on equipment_links (company_id);
create index idx_equipment_links_equipment_id on equipment_links (equipment_id);
create index idx_equipment_links_record on equipment_links (record_type, record_id);

-- ── Quality Records / QMS (§4.7) ────────────────────────────────────────────

create table deviations (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    project_id  uuid null references projects(id) on delete set null,
    title       text not null,
    status      text not null default 'open',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_deviations_company_id on deviations (company_id);
create index idx_deviations_company_id_status on deviations (company_id, status);

create table capas (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    project_id  uuid null references projects(id) on delete set null,
    title       text not null,
    status      text not null default 'open',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_capas_company_id on capas (company_id);
create index idx_capas_company_id_status on capas (company_id, status);

create table change_controls (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    project_id  uuid null references projects(id) on delete set null,
    title       text not null,
    status      text not null default 'open',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_change_controls_company_id on change_controls (company_id);
create index idx_change_controls_company_id_status on change_controls (company_id, status);

create table risk_assessments (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    project_id  uuid null references projects(id) on delete set null,
    title       text not null,
    status      text not null default 'open',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_risk_assessments_company_id on risk_assessments (company_id);
create index idx_risk_assessments_company_id_status on risk_assessments (company_id, status);

-- ── Shared / Polymorphic Infrastructure (§4.6, §9) ──────────────────────────
-- No FK on (record_type, record_id) — same accepted trade-off as equipment_links.

create table audit_trail (
    id                    uuid primary key default gen_random_uuid(),
    company_id            uuid not null references companies(id),
    actor_user_id         uuid null references users(id),
    action                text not null,
    record_type           text not null,
    record_id             uuid not null,
    prior_state_snapshot  jsonb null,
    reason                text null,
    occurred_at           timestamptz not null default now()
);

create index idx_audit_trail_company_id on audit_trail (company_id);
create index idx_audit_trail_record on audit_trail (record_type, record_id);

create table attachments (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    record_type  text not null,
    record_id    uuid not null,
    storage_path text not null,
    checksum     text null,
    content_type text null,
    size_bytes   bigint null,
    uploaded_by_user_id uuid null references users(id),
    created_at   timestamptz not null default now()
);

create index idx_attachments_company_id on attachments (company_id);
create index idx_attachments_record on attachments (record_type, record_id);

create table comments (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    record_type  text not null,
    record_id    uuid not null,
    author_user_id uuid null references users(id),
    body         text not null,
    created_at   timestamptz not null default now()
);

create index idx_comments_company_id on comments (company_id);
create index idx_comments_record on comments (record_type, record_id);

create table approvals (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    record_type  text not null,
    record_id    uuid not null,
    decision     text not null,
    reviewer_user_id uuid null references users(id),
    reason       text null,
    decided_at   timestamptz not null default now()
);

create index idx_approvals_company_id on approvals (company_id);
create index idx_approvals_record on approvals (record_type, record_id);

-- ── AI Workspace (§4.5) ──────────────────────────────────────────────────────

create table ai_conversations (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    project_id  uuid null references projects(id) on delete set null,
    user_id     uuid not null references users(id),
    created_at  timestamptz not null default now()
);

create index idx_ai_conversations_company_id on ai_conversations (company_id);

create table ai_messages (
    id               uuid primary key default gen_random_uuid(),
    company_id       uuid not null references companies(id),
    conversation_id  uuid not null references ai_conversations(id),
    role             text not null check (role in ('user', 'assistant')),
    content          text not null,
    token_count      integer null,
    created_at       timestamptz not null default now()
);

create index idx_ai_messages_company_id on ai_messages (company_id);
create index idx_ai_messages_conversation_id on ai_messages (conversation_id);

create table ai_jobs (
    id            uuid primary key default gen_random_uuid(),
    company_id    uuid not null references companies(id),
    job_type      text not null,
    status        text not null default 'queued' check (status in
                      ('queued', 'running', 'succeeded', 'failed')),
    input_ref     jsonb null,
    output_ref    jsonb null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index idx_ai_jobs_company_id on ai_jobs (company_id);
create index idx_ai_jobs_company_id_status on ai_jobs (company_id, status);

create table ai_usage_ledger (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    user_id     uuid null references users(id),
    ai_job_id   uuid null references ai_jobs(id),
    tokens      integer null,
    cost_cents  integer null,
    purpose     text null,
    created_at  timestamptz not null default now()
);

create index idx_ai_usage_ledger_company_id on ai_usage_ledger (company_id);

-- ── Operational / Platform (§4.8) ───────────────────────────────────────────

create table notifications (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    user_id     uuid not null references users(id),
    kind        text not null,
    payload     jsonb null,
    read_at     timestamptz null,
    created_at  timestamptz not null default now()
);

create index idx_notifications_company_id on notifications (company_id);
create index idx_notifications_user_id on notifications (user_id);

create table search_index (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    record_type text not null,
    record_id   uuid not null,
    title       text null,
    body        text null,
    search_vector tsvector generated always as (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))
    ) stored,
    updated_at  timestamptz not null default now()
);

create index idx_search_index_company_id on search_index (company_id);
create index idx_search_index_gin on search_index using gin (search_vector);

-- ── Reserved tables (§21) — schema only, empty, no code path touches them ──

create table permissions (
    id   uuid primary key default gen_random_uuid(),
    name text not null unique
);

create table role_permissions (
    id            uuid primary key default gen_random_uuid(),
    role_id       smallint not null references roles(id),
    permission_id uuid not null references permissions(id)
);

create table calibration_records (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    equipment_id uuid not null references equipment(id) on delete cascade,
    performed_at timestamptz null,
    created_at   timestamptz not null default now()
);

create index idx_calibration_records_company_id on calibration_records (company_id);

create table preventive_maintenance_records (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    equipment_id uuid not null references equipment(id) on delete cascade,
    performed_at timestamptz null,
    created_at   timestamptz not null default now()
);

create index idx_pm_records_company_id on preventive_maintenance_records (company_id);

create table spare_parts (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    equipment_id uuid not null references equipment(id) on delete cascade,
    name         text null,
    created_at   timestamptz not null default now()
);

create index idx_spare_parts_company_id on spare_parts (company_id);

create table signature_events (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id),
    approval_id  uuid not null references approvals(id),
    signed_at    timestamptz not null default now()
);

create index idx_signature_events_company_id on signature_events (company_id);

create table data_retention_policies (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    policy      jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index idx_data_retention_policies_company_id on data_retention_policies (company_id);

create table integration_configs (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    config      jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index idx_integration_configs_company_id on integration_configs (company_id);

create table api_keys (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    key_hash    text not null,
    created_at  timestamptz not null default now()
);

create index idx_api_keys_company_id on api_keys (company_id);

create table subscriptions (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    plan        text null,
    created_at  timestamptz not null default now()
);

create table plans (
    id   uuid primary key default gen_random_uuid(),
    name text not null unique
);

create table invoices (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    amount_cents integer null,
    created_at  timestamptz not null default now()
);

create index idx_invoices_company_id on invoices (company_id);

-- ── RLS: default-deny on every table above ──────────────────────────────────
-- Same posture as 0001_identity_tenancy_up.sql: RLS enabled, zero policies,
-- so anon/authenticated PostgREST roles get nothing. Real company-scoped
-- policies land per-domain in Phase 3.2-3.5 when each domain's code starts
-- depending on them (DATABASE_ARCHITECTURE.md §13). Service-role key
-- (server-side only) bypasses RLS and is unaffected.

alter table projects enable row level security;
alter table project_members enable row level security;
alter table equipment enable row level security;
alter table document_categories enable row level security;
alter table tags enable row level security;
alter table documents enable row level security;
alter table document_versions enable row level security;
alter table document_tags enable row level security;
alter table document_references enable row level security;
alter table equipment_links enable row level security;
alter table deviations enable row level security;
alter table capas enable row level security;
alter table change_controls enable row level security;
alter table risk_assessments enable row level security;
alter table audit_trail enable row level security;
alter table attachments enable row level security;
alter table comments enable row level security;
alter table approvals enable row level security;
alter table ai_conversations enable row level security;
alter table ai_messages enable row level security;
alter table ai_jobs enable row level security;
alter table ai_usage_ledger enable row level security;
alter table notifications enable row level security;
alter table search_index enable row level security;
alter table calibration_records enable row level security;
alter table preventive_maintenance_records enable row level security;
alter table spare_parts enable row level security;
alter table signature_events enable row level security;
alter table data_retention_policies enable row level security;
alter table integration_configs enable row level security;
alter table api_keys enable row level security;
alter table subscriptions enable row level security;
alter table invoices enable row level security;
-- permissions, role_permissions, plans: platform reference tables, no
-- company_id — left without RLS, same class as `roles` (0001), but with no
-- read policy either since nothing needs to read them yet at v1.0.
alter table permissions enable row level security;
alter table role_permissions enable row level security;
alter table plans enable row level security;

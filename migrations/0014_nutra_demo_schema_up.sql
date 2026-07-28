-- Migration 0014 (up): Enterprise organizational model — modules,
-- workflow_roles, departments, user_departments, user_module_permissions.
--
-- Purely additive, built to support the Nutra demo tenant
-- (scripts/seed_nutra_demo.py) while standing on its own as a durable
-- organizational layer. `roles` (migration 0001) stays frozen at its 4
-- rows — workflow_roles is a NEW, separate, platform-scoped lookup table
-- for organizational job-title metadata (Initiator/Coordinator/Reviewer/
-- Approver/Plant Head), not a change to RBAC. None of the tables below are
-- read by pharmagpt/services/workflow_engine.py's eligible_roles /
-- named-approver decision logic, by pharmagpt/auth/decorators.py's
-- require_role, or by any existing route — that surface is entirely
-- untouched by this migration. See docs/DATABASE_ARCHITECTURE.md's
-- reserved `permissions`/`role_permissions` (§21, decision DB-006): those
-- are a role-scoped v1.2 grant model and cannot represent the per-user
-- divergence this task requires, so they are left alone; user_module_permissions
-- is a distinct, user-scoped concept, not an early build-out of that
-- reserved schema.
--
-- Run this in the Supabase SQL Editor. Rollback: 0014_nutra_demo_schema_down.sql.

-- ── modules ──────────────────────────────────────────────────────────────
-- Platform-scoped, static reference table of product suites a user may be
-- granted access to. Seeded directly here — same pattern as `roles`
-- (migration 0001) and `workflow_roles` (below). Adding a future module
-- (Training, Calibration, Equipment, Audit, Supplier, ...) is one INSERT —
-- no schema change.

create table if not exists modules (
    id          uuid primary key default gen_random_uuid(),
    code        text not null unique,
    name        text not null,
    description text not null,
    created_at  timestamptz not null default now()
);

insert into modules (code, name, description) values
    ('QMS', 'QMS Suite', 'Quality Management System — deviations, CAPA, change control, documents.'),
    ('VALIDATION', 'Validation Suite', 'Validation protocols and reports — IQ/OQ/PQ, URS, risk assessments.'),
    ('DOCUMENT_GENERATOR', 'Document Generator', 'AI-assisted document drafting and export.')
on conflict (code) do nothing;

alter table modules enable row level security;

drop policy if exists modules_select_authenticated on modules;
create policy modules_select_authenticated on modules
    for select to authenticated using (true);

grant select, insert, update, delete on modules to service_role;
grant select on modules to authenticated;

-- ── workflow_roles ──────────────────────────────────────────────────────
-- Platform-scoped, static reference table of organizational job titles,
-- with capability fields describing (as future capability, not yet
-- consumed by workflow_engine.py) what a holder of this title is generally
-- entitled to do. Seeded directly here — same pattern as `roles`
-- (migration 0001).

create table if not exists workflow_roles (
    id                  smallint primary key,
    name                text not null unique,
    description         text not null,
    sequence            smallint not null,
    can_start_workflow  boolean not null default false,
    can_review          boolean not null default false,
    can_approve         boolean not null default false,
    is_final_approver   boolean not null default false,
    created_at          timestamptz not null default now()
);

insert into workflow_roles (id, name, description, sequence, can_start_workflow, can_review, can_approve, is_final_approver) values
    (1, 'Initiator',   'Authors and submits records for review within their department.', 10, true,  false, false, false),
    (2, 'Coordinator', 'Coordinates department-level QMS activity and routing.',           20, true,  true,  false, false),
    (3, 'Reviewer',    'Reviews submitted records prior to approval.',                     30, false, true,  false, false),
    (4, 'Approver',    'Approves or rejects reviewed records.',                            40, false, false, true,  false),
    (5, 'Plant Head',  'Highest approval authority across the plant.',                     50, false, false, true,  true)
on conflict (id) do nothing;

alter table workflow_roles enable row level security;

drop policy if exists workflow_roles_select_authenticated on workflow_roles;
create policy workflow_roles_select_authenticated on workflow_roles
    for select to authenticated using (true);

grant select, insert, update, delete on workflow_roles to service_role;
grant select on workflow_roles to authenticated;

-- ── departments ──────────────────────────────────────────────────────────
-- Company-scoped. `department_code` is the stable key (names may change
-- over time; codes should not) — see user_departments and
-- scripts/seed_nutra_demo.py, which look departments up by code. No write
-- grant to `authenticated` — only a service-role script populates this
-- table for now; no route manages departments yet.

create table if not exists departments (
    id               uuid primary key default gen_random_uuid(),
    company_id       uuid not null references companies(id),
    name             text not null,
    department_code  text not null,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    constraint uq_departments_company_name unique (company_id, name),
    constraint uq_departments_company_code unique (company_id, department_code)
);

create index if not exists idx_departments_company_id on departments (company_id);

alter table departments enable row level security;

drop policy if exists departments_company_admin_read_own on departments;
create policy departments_company_admin_read_own on departments
    for select to authenticated
    using (
        company_id = current_user_company_id()
        and current_user_role_name() = 'company_admin'
    );

grant select, insert, update, delete on departments to service_role;
grant select on departments to authenticated;

-- ── users.workflow_role_id ──────────────────────────────────────────────
-- Nullable, no backfill. Existing users rows remain valid as-is. No RLS
-- change to `users` — RLS is row-level, and migrations 0012/0013's
-- policies already govern who may read/write a row regardless of which
-- columns it carries. RESTRICT (no ON DELETE clause) — same class as
-- role_id -> roles, a static lookup table that is never deleted.

alter table users add column if not exists workflow_role_id smallint null
    references workflow_roles(id);

create index if not exists idx_users_workflow_role_id on users (workflow_role_id);

-- ── user_departments ────────────────────────────────────────────────────
-- Normalized many-to-many between users and departments (a user may
-- belong to more than one department in the future without another
-- migration), with at most one row per user marked `is_primary`. Every
-- Nutra seed user gets exactly one primary department today; Plant Head
-- gets none (a plant-wide role, not tied to one of the 7 departments).
--
-- company_id is denormalized onto this table, matching the convention
-- every other tenant-scoped table in this schema already follows
-- (documents, deviations, user_module_permissions, ...) rather than
-- requiring a join through `departments` for RLS scoping.

create table if not exists user_departments (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null references users(id) on delete cascade,
    department_id  uuid not null references departments(id),
    company_id     uuid not null references companies(id),
    is_primary     boolean not null default false,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    constraint uq_user_departments_user_department unique (user_id, department_id)
);

create index if not exists idx_user_departments_user_id on user_departments (user_id);
create index if not exists idx_user_departments_department_id on user_departments (department_id);
create index if not exists idx_user_departments_company_id on user_departments (company_id);

-- At most one primary department per user, enforced at the database level.
create unique index if not exists uq_user_departments_one_primary
    on user_departments (user_id) where is_primary;

alter table user_departments enable row level security;

drop policy if exists user_departments_company_admin_read_own on user_departments;
create policy user_departments_company_admin_read_own on user_departments
    for select to authenticated
    using (
        company_id = current_user_company_id()
        and current_user_role_name() = 'company_admin'
    );

grant select, insert, update, delete on user_departments to service_role;
grant select on user_departments to authenticated;

-- ── user_module_permissions ─────────────────────────────────────────────
-- Normalized, one row per (user, module). Cascades on user deletion via
-- users(id) -> auth.users(id) on delete cascade (migration 0001), which
-- this table's own on delete cascade extends transitively. User-scoped —
-- deliberately distinct from the reserved, role-scoped `role_permissions`
-- (see migration header comment and docs/DATABASE_ARCHITECTURE.md §21).

create table if not exists user_module_permissions (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references users(id) on delete cascade,
    company_id  uuid not null references companies(id),
    module_id   uuid not null references modules(id),
    enabled     boolean not null default false,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    constraint uq_user_module_permissions_user_module unique (user_id, module_id)
);

create index if not exists idx_user_module_permissions_company_id on user_module_permissions (company_id);
create index if not exists idx_user_module_permissions_user_id on user_module_permissions (user_id);

alter table user_module_permissions enable row level security;

drop policy if exists user_module_permissions_company_admin_read_own on user_module_permissions;
create policy user_module_permissions_company_admin_read_own on user_module_permissions
    for select to authenticated
    using (
        company_id = current_user_company_id()
        and current_user_role_name() = 'company_admin'
    );

grant select, insert, update, delete on user_module_permissions to service_role;
grant select on user_module_permissions to authenticated;

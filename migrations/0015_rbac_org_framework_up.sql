-- Migration 0015 (up): Fine-grained RBAC + organizational structure.
--
-- Purely additive. Does NOT touch: roles, users.role_id, require_role(),
-- workflow_roles, modules, user_module_permissions, or any RLS policy
-- other than the two write-policy additions on `departments` called out
-- below. The frozen 4-role platform model (migrations/0001) and the
-- workflow-sequencing job titles in `workflow_roles` (migration 0014) are
-- unrelated concepts and remain exactly as they are.
--
-- Adds:
--   - `designations`      company-scoped, configurable job-title labels
--                         (Production Executive, QA Executive, ...) — NOT
--                         the same thing as workflow_roles (0014), which is
--                         a fixed 5-row workflow-sequencing lookup consumed
--                         as future capability by the deviation workflow
--                         engine. Conflating the two would mean hardcoding
--                         designations into that frozen set, which this
--                         migration deliberately avoids.
--   - `approval_levels`   company-scoped placeholder ("Level 1/2/3"). No
--                         route or workflow_engine.py logic reads this yet
--                         — it exists only so a role can optionally be
--                         tagged with a level for future approval routing.
--   - `rbac_permissions`  static catalog: 15 modules x 8 actions.
--   - `rbac_roles`        company-scoped custom/system roles, plus global
--                         templates where company_id is null.
--   - `rbac_role_permissions`  the matrix: role x permission -> granted.
--   - `rbac_user_roles`   many-to-many user <-> rbac_roles (multi-role).
--   - `rbac_audit_log`    immutable audit trail for every RBAC/org change.
--   - departments.status, users.designation_id, users.reporting_manager_id
--     (additive columns, nullable/defaulted, no backfill required).
--
-- Run this in the Supabase SQL Editor. Rollback: 0015_rbac_org_framework_down.sql.

-- ── departments: additive column + write policy ────────────────────────────
-- departments (migration 0014) is currently read-only to `authenticated`
-- (only a service-role seed script writes to it — "no route manages
-- departments yet"). This migration adds the first route that does
-- (routes/org_structure.py), so a scoped write policy for company_admin is
-- added here. The existing read policy is untouched.

alter table departments add column if not exists status text not null default 'active'
    check (status in ('active', 'disabled'));

drop policy if exists departments_company_admin_write_own on departments;
create policy departments_company_admin_write_own on departments
    for all
    to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin')
    with check (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

grant insert, update on departments to authenticated;

-- ── designations ────────────────────────────────────────────────────────────

create table if not exists designations (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    name        text not null,
    status      text not null default 'active' check (status in ('active', 'disabled')),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    constraint uq_designations_company_name unique (company_id, name)
);

create index if not exists idx_designations_company_id on designations (company_id);

alter table designations enable row level security;

drop policy if exists designations_company_admin_read_own on designations;
create policy designations_company_admin_read_own on designations
    for select to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

drop policy if exists designations_company_admin_write_own on designations;
create policy designations_company_admin_write_own on designations
    for insert to authenticated
    with check (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

drop policy if exists designations_company_admin_update_own on designations;
create policy designations_company_admin_update_own on designations
    for update to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin')
    with check (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

grant select, insert, update, delete on designations to service_role;
grant select, insert, update on designations to authenticated;

-- ── users: designation_id, reporting_manager_id ────────────────────────────
-- Nullable, no backfill — same pattern 0014 used for users.workflow_role_id.

alter table users add column if not exists designation_id uuid null references designations(id);
alter table users add column if not exists reporting_manager_id uuid null references users(id);

create index if not exists idx_users_designation_id on users (designation_id);
create index if not exists idx_users_reporting_manager_id on users (reporting_manager_id);

-- ── approval_levels (placeholder only, no workflow logic reads this) ──────

create table if not exists approval_levels (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id),
    name        text not null,
    sequence    smallint not null,
    created_at  timestamptz not null default now(),
    constraint uq_approval_levels_company_sequence unique (company_id, sequence)
);

create index if not exists idx_approval_levels_company_id on approval_levels (company_id);

alter table approval_levels enable row level security;

drop policy if exists approval_levels_company_admin_read_own on approval_levels;
create policy approval_levels_company_admin_read_own on approval_levels
    for select to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

grant select, insert, update, delete on approval_levels to service_role;
grant select on approval_levels to authenticated;

-- ── rbac_permissions: static catalog, 15 modules x 8 actions ──────────────

create table if not exists rbac_permissions (
    id      uuid primary key default gen_random_uuid(),
    module  text not null,
    action  text not null,
    constraint uq_rbac_permissions_module_action unique (module, action)
);

insert into rbac_permissions (module, action)
select m, a
from unnest(array[
    'Dashboard', 'Projects', 'Validation', 'Risk Assessment', 'Equipment Library',
    'Document Control', 'Knowledge Base', 'AI Assistant', 'Deviations', 'CAPA',
    'Change Control', 'QMS', 'Warehouse', 'Administration', 'Reports'
]) as m
cross join unnest(array[
    'View', 'Create', 'Edit', 'Delete', 'Review', 'Approve', 'Export', 'Admin'
]) as a
on conflict (module, action) do nothing;

alter table rbac_permissions enable row level security;

drop policy if exists rbac_permissions_select_authenticated on rbac_permissions;
create policy rbac_permissions_select_authenticated on rbac_permissions
    for select to authenticated using (true);

grant select, insert, update, delete on rbac_permissions to service_role;
grant select on rbac_permissions to authenticated;

-- ── rbac_roles ──────────────────────────────────────────────────────────────
-- company_id null = global template (Platform Admin-managed). Non-null =
-- a real, assignable, company-owned role (cloned from a template or
-- created from scratch by that company's Company Admin).

create table if not exists rbac_roles (
    id                   uuid primary key default gen_random_uuid(),
    company_id           uuid null references companies(id),
    name                 text not null,
    description          text not null default '',
    department_code      text null,
    department_id        uuid null references departments(id),
    approval_level_id    uuid null references approval_levels(id),
    is_system            boolean not null default false,
    is_template          boolean not null default false,
    cloned_from_role_id  uuid null references rbac_roles(id),
    status               text not null default 'active' check (status in ('active', 'disabled')),
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);

-- Two partial unique indexes instead of one plain unique(company_id, name):
-- Postgres treats every NULL as distinct in an ordinary unique constraint,
-- so a single unique(company_id, name) would never actually deduplicate
-- the company_id-is-null template rows across a migration re-run.
create unique index if not exists uq_rbac_roles_template_name
    on rbac_roles (name) where company_id is null;
create unique index if not exists uq_rbac_roles_company_name
    on rbac_roles (company_id, name) where company_id is not null;

create index if not exists idx_rbac_roles_company_id on rbac_roles (company_id);
create index if not exists idx_rbac_roles_is_template on rbac_roles (is_template);

alter table rbac_roles enable row level security;

-- Templates (company_id is null) are readable by any authenticated user
-- (needed for Company Admin to browse/clone them); company-owned rows are
-- scoped to that company's own company_admin.
drop policy if exists rbac_roles_read on rbac_roles;
create policy rbac_roles_read on rbac_roles
    for select to authenticated
    using (
        company_id is null
        or (company_id = current_user_company_id() and current_user_role_name() = 'company_admin')
    );

drop policy if exists rbac_roles_company_admin_write_own on rbac_roles;
create policy rbac_roles_company_admin_write_own on rbac_roles
    for insert to authenticated
    with check (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

drop policy if exists rbac_roles_company_admin_update_own on rbac_roles;
create policy rbac_roles_company_admin_update_own on rbac_roles
    for update to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin')
    with check (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

grant select, insert, update, delete on rbac_roles to service_role;
grant select, insert, update on rbac_roles to authenticated;

-- ── rbac_role_permissions ──────────────────────────────────────────────────

create table if not exists rbac_role_permissions (
    id             uuid primary key default gen_random_uuid(),
    role_id        uuid not null references rbac_roles(id) on delete cascade,
    permission_id  uuid not null references rbac_permissions(id),
    granted        boolean not null default true,
    constraint uq_rbac_role_permissions_role_permission unique (role_id, permission_id)
);

create index if not exists idx_rbac_role_permissions_role_id on rbac_role_permissions (role_id);

alter table rbac_role_permissions enable row level security;

drop policy if exists rbac_role_permissions_read on rbac_role_permissions;
create policy rbac_role_permissions_read on rbac_role_permissions
    for select to authenticated
    using (
        exists (
            select 1 from rbac_roles r
            where r.id = rbac_role_permissions.role_id
              and (
                  r.company_id is null
                  or (r.company_id = current_user_company_id() and current_user_role_name() = 'company_admin')
              )
        )
    );

drop policy if exists rbac_role_permissions_company_admin_write on rbac_role_permissions;
create policy rbac_role_permissions_company_admin_write on rbac_role_permissions
    for all to authenticated
    using (
        exists (
            select 1 from rbac_roles r
            where r.id = rbac_role_permissions.role_id
              and r.company_id = current_user_company_id()
              and current_user_role_name() = 'company_admin'
        )
    )
    with check (
        exists (
            select 1 from rbac_roles r
            where r.id = rbac_role_permissions.role_id
              and r.company_id = current_user_company_id()
              and current_user_role_name() = 'company_admin'
        )
    );

grant select, insert, update, delete on rbac_role_permissions to service_role;
grant select, insert, update, delete on rbac_role_permissions to authenticated;

-- ── rbac_user_roles ─────────────────────────────────────────────────────────
-- company_id is denormalized here (matching this schema's existing
-- convention on user_departments/user_module_permissions) so RLS can scope
-- without a join through `users`.

create table if not exists rbac_user_roles (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references users(id) on delete cascade,
    role_id     uuid not null references rbac_roles(id) on delete cascade,
    company_id  uuid not null references companies(id),
    created_at  timestamptz not null default now(),
    constraint uq_rbac_user_roles_user_role unique (user_id, role_id)
);

create index if not exists idx_rbac_user_roles_user_id on rbac_user_roles (user_id);
create index if not exists idx_rbac_user_roles_company_id on rbac_user_roles (company_id);

alter table rbac_user_roles enable row level security;

drop policy if exists rbac_user_roles_company_admin_read_own on rbac_user_roles;
create policy rbac_user_roles_company_admin_read_own on rbac_user_roles
    for select to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

drop policy if exists rbac_user_roles_company_admin_write_own on rbac_user_roles;
create policy rbac_user_roles_company_admin_write_own on rbac_user_roles
    for all to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin')
    with check (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

grant select, insert, update, delete on rbac_user_roles to service_role;
grant select, insert, update, delete on rbac_user_roles to authenticated;

-- ── rbac_audit_log ──────────────────────────────────────────────────────────
-- Immutable: RLS enabled, only a select policy exists below — no
-- update/delete policy for any role, and no insert policy for
-- `authenticated` either. Every insert goes through the service-role
-- client from route code (pharmagpt/db/rbac_repo.py::add_rbac_audit_entry),
-- matching break_glass_access's convention for tamper-resistant records.

create table if not exists rbac_audit_log (
    id               uuid primary key default gen_random_uuid(),
    company_id       uuid null references companies(id),
    actor_user_id    uuid not null references users(id),
    target_user_id   uuid null references users(id),
    department_id    uuid null references departments(id),
    role_id          uuid null references rbac_roles(id),
    permission_id    uuid null references rbac_permissions(id),
    old_value        jsonb null,
    new_value        jsonb null,
    reason           text not null,
    created_at       timestamptz not null default now()
);

create index if not exists idx_rbac_audit_log_company_id on rbac_audit_log (company_id);
create index if not exists idx_rbac_audit_log_created_at on rbac_audit_log (created_at);

alter table rbac_audit_log enable row level security;

drop policy if exists rbac_audit_log_company_admin_read_own on rbac_audit_log;
create policy rbac_audit_log_company_admin_read_own on rbac_audit_log
    for select to authenticated
    using (company_id = current_user_company_id() and current_user_role_name() = 'company_admin');

grant select, insert on rbac_audit_log to service_role;
-- Deliberately no grant of insert/update/delete to `authenticated` —
-- immutability is enforced at the grant level, not just by policy absence.

-- ── rbac_roles: 21 global role templates (company_id = null) ──────────────
-- Platform Admin-managed defaults a Company Admin can clone into their own
-- company. Not frozen like the 4 platform roles — is_system=true here only
-- marks these as platform-authored starting points, not immutable.
-- department_code is a hint used only at clone time (pharmagpt/db/
-- org_structure_repo.py) to resolve the *company's own* departments.id —
-- never string-matched in route/service logic afterward.

insert into rbac_roles (name, description, department_code, is_system, is_template) values
    ('Platform Admin',        'Manages tenants and platform settings only. No standing access to tenant GMP records.', null,                  true, true),
    ('Company Admin',         'Full control within one company: users, roles, departments, all modules.',              null,                  true, true),
    ('Plant Head',            'Highest cross-department oversight and approval authority within the plant.',           'PLANT_HEAD',          true, true),
    ('QA Manager',            'Manages Quality Assurance activities, reviews and approves QMS records.',               'QA',                  true, true),
    ('QA Officer',            'Executes day-to-day Quality Assurance tasks.',                                          'QA',                  true, true),
    ('QC Manager',            'Manages Quality Control testing and release activities.',                               'QC',                  true, true),
    ('QC Analyst',            'Performs Quality Control testing and analysis.',                                        'QC',                  true, true),
    ('Validation Manager',    'Manages validation programs and protocol approval.',                                    'VALIDATION',          true, true),
    ('Validation Engineer',   'Executes validation protocols and documentation.',                                      'VALIDATION',          true, true),
    ('Production Manager',    'Manages production operations and schedules.',                                         'PRODUCTION',          true, true),
    ('Production Supervisor', 'Supervises shop-floor production activities.',                                          'PRODUCTION',          true, true),
    ('Production Operator',   'Executes production operations.',                                                       'PRODUCTION',          true, true),
    ('Engineering Manager',   'Manages engineering and equipment maintenance programs.',                                'ENGINEERING',         true, true),
    ('Maintenance Engineer',  'Performs equipment maintenance and calibration support.',                                'ENGINEERING',         true, true),
    ('Warehouse Manager',     'Manages warehouse and material movement operations.',                                    'WAREHOUSE',           true, true),
    ('Warehouse Executive',   'Executes warehouse and material handling tasks.',                                       'WAREHOUSE',           true, true),
    ('EHS Manager',           'Manages Environmental Health & Safety programs.',                                       'EHS',                 true, true),
    ('EHS Officer',           'Executes EHS inspections and reporting.',                                               'EHS',                 true, true),
    ('Regulatory Manager',    'Manages regulatory submissions and compliance tracking.',                               'REGULATORY_AFFAIRS',  true, true),
    ('Auditor',               'Read-only, export-capable access across all modules for audit purposes.',               null,                  true, true),
    ('Viewer',                'Read-only access across all modules.',                                                  null,                  true, true)
on conflict (name) where company_id is null do nothing;

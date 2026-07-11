-- Migration 0001 (up): Identity & Tenancy tables
-- DATABASE_ARCHITECTURE.md §4.1 — companies, roles, users, company_settings, break_glass_access
--
-- Scope: schema only. No application code depends on these tables yet
-- (that lands in Phase 2 steps 2.2+). Safe to run against Supabase now;
-- nothing currently running reads or writes these tables.
--
-- Run this in the Supabase SQL Editor (Project → SQL Editor → New query).
-- Rollback: run 0001_identity_tenancy_down.sql.

create extension if not exists pgcrypto;

-- ── companies ───────────────────────────────────────────────────────────────
-- The tenant root. Platform-scoped (no company_id column on itself).

create table companies (
    id                uuid primary key default gen_random_uuid(),
    legal_name        text not null,
    industry_segment  text not null check (industry_segment in
                          ('pharma', 'nutraceutical', 'medical_device', 'biotech', 'cdmo', 'cro')),
    plan_tier         text not null default 'standard',
    status            text not null default 'active' check (status in ('active', 'suspended')),
    onboarded_at      timestamptz not null default now(),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

-- ── roles ───────────────────────────────────────────────────────────────────
-- Platform-scoped, static reference table. Four frozen roles
-- (PLATFORM_ARCHITECTURE.md §7) — no custom roles at v1.0.

create table roles (
    id           smallint primary key,
    name         text not null unique,
    description  text not null
);

insert into roles (id, name, description) values
    (1, 'super_admin',   'Platform-wide. Creates/suspends companies and their first Company Admin. No standing access to tenant content.'),
    (2, 'company_admin', 'Full control within one company: users, Knowledge Base, Equipment Library, Projects, settings.'),
    (3, 'reviewer_qa',   'One company, project/KB-scoped by assignment. Reviews and approves/rejects documents.'),
    (4, 'user',          'One company, project-scoped by assignment. Authors and edits documents within assigned Projects.');

-- ── users ───────────────────────────────────────────────────────────────────
-- One row per human identity, 1:1 with a Supabase Auth identity (auth.users.id).
-- company_id is NULL only for Super Admin (chk_users_super_admin_company_null,
-- enforced below via trigger since a CHECK constraint cannot reference roles.name).

create table users (
    id            uuid primary key references auth.users(id) on delete cascade,
    company_id    uuid null references companies(id),
    role_id       smallint not null references roles(id),
    display_name  text not null,
    status        text not null default 'active' check (status in ('active', 'deactivated')),
    last_login_at timestamptz null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index idx_users_company_id on users (company_id);
create index idx_users_role_id on users (role_id);

create or replace function chk_users_super_admin_company_null()
returns trigger
language plpgsql
as $$
declare
    is_super_admin boolean;
begin
    select (name = 'super_admin') into is_super_admin from roles where id = new.role_id;

    if is_super_admin and new.company_id is not null then
        raise exception 'chk_users_super_admin_company_null: Super Admin users must have company_id = NULL';
    end if;

    if not is_super_admin and new.company_id is null then
        raise exception 'chk_users_super_admin_company_null: non-Super-Admin users must have a company_id';
    end if;

    return new;
end;
$$;

create trigger trg_users_super_admin_company_null
    before insert or update of role_id, company_id on users
    for each row execute function chk_users_super_admin_company_null();

-- ── company_settings ───────────────────────────────────────────────────────
-- One row per company. Kept separate from companies so frequently-adjusted
-- configuration doesn't churn the tenant-root row.

create table company_settings (
    id                       uuid primary key default gen_random_uuid(),
    company_id               uuid not null unique references companies(id),
    ai_usage_limits          jsonb not null default '{}'::jsonb,
    branding                 jsonb not null default '{}'::jsonb,
    notification_preferences jsonb not null default '{}'::jsonb,
    data_retention_policy    jsonb not null default '{}'::jsonb,
    created_at               timestamptz not null default now(),
    updated_at               timestamptz not null default now()
);

create index idx_company_settings_company_id on company_settings (company_id);

-- ── break_glass_access ─────────────────────────────────────────────────────
-- Logs every instance of a Super Admin accessing tenant content: a control,
-- not a convenience feature (DATABASE_ARCHITECTURE.md §4.1, §13.2).

create table break_glass_access (
    id                 uuid primary key default gen_random_uuid(),
    super_admin_user_id uuid not null references users(id),
    company_id         uuid not null references companies(id),
    reason             text not null,
    granted_at         timestamptz not null default now(),
    expires_at         timestamptz not null,
    revoked_at         timestamptz null,
    created_at         timestamptz not null default now(),
    constraint chk_break_glass_access_expires_after_granted check (expires_at > granted_at)
);

create index idx_break_glass_access_super_admin_user_id on break_glass_access (super_admin_user_id);
create index idx_break_glass_access_company_id on break_glass_access (company_id);

-- ── RLS: default-deny until Phase 3's full policy set lands ────────────────
-- Phase 3 (DATABASE_ARCHITECTURE.md §13) activates the real company_id-scoped
-- policy set. Until then these tables must not be readable/writable via the
-- anon/authenticated PostgREST roles at all — only the server, using the
-- service-role key (which bypasses RLS), may touch them. This is a safe
-- default, not the target policy set.

alter table companies enable row level security;
alter table roles enable row level security;
alter table users enable row level security;
alter table company_settings enable row level security;
alter table break_glass_access enable row level security;

-- roles is static reference data — safe to expose read-only to any
-- authenticated session (no company_id to leak, no PII).
create policy roles_select_authenticated on roles
    for select
    to authenticated
    using (true);

-- No policies created for companies/users/company_settings/break_glass_access:
-- RLS is enabled with zero policies, which denies all access to the anon and
-- authenticated roles by default. The service role bypasses RLS entirely, so
-- server-side code (routes/auth.py, pharmagpt/auth/) using
-- SUPABASE_SERVICE_ROLE_KEY continues to work unaffected.

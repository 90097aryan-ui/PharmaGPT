# Migration Verification Guide
## Phase F.2 — how to check migration state, and why the migrations are now safe to re-run

This guide is scoped to Postgres/Supabase migrations (`migrations/*.sql`) — it does not cover the SQLite side (`pharmagpt/database.py`'s `_add_column_if_missing` pattern, which was already additive/idempotent before this phase).

## 1. What changed in Phase F.2

Every `migrations/000N_..._up.sql` file (0001-0012) was made idempotent — safe to run zero, one, or many times against the same database and always converge to the same end state, with no error on a repeat run. Specifically:

| Statement type | Before | After |
|---|---|---|
| `CREATE TABLE x (...)` | Errors `relation "x" already exists` on a repeat run | `CREATE TABLE IF NOT EXISTS x (...)` |
| `CREATE INDEX idx_x ON t (...)` | Errors `relation "idx_x" already exists` | `CREATE INDEX IF NOT EXISTS idx_x ON t (...)` |
| `CREATE POLICY p ON t ...` | Errors `policy "p" for relation "t" already exists` — Postgres has no `IF NOT EXISTS` clause for policies | Preceded by `DROP POLICY IF EXISTS p ON t;`, then `CREATE POLICY p ON t ...` |
| `CREATE TRIGGER trg ON t ...` | Same class of error as policies — no `IF NOT EXISTS` clause | Preceded by `DROP TRIGGER IF EXISTS trg ON t;` |
| `INSERT INTO roles (...) VALUES (...)` (migration 0001 only) | Errors on the `id` primary key conflict on a repeat run | `... ON CONFLICT (id) DO NOTHING` |
| `ALTER TABLE documents ADD CONSTRAINT fk_... FOREIGN KEY (...)` (migration 0004 only) | Errors `constraint "fk_..." already exists` — no `IF NOT EXISTS` clause for `ADD CONSTRAINT` | Wrapped in a `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '...') THEN ... END IF; END $$;` guard |
| `GRANT ...` / `REVOKE ...` | Already idempotent — Postgres allows re-granting/re-revoking with no error | Unchanged |
| `CREATE EXTENSION IF NOT EXISTS pgcrypto` | Already idempotent | Unchanged |
| `CREATE OR REPLACE FUNCTION ...` | Already idempotent | Unchanged |
| `ALTER TABLE t ENABLE ROW LEVEL SECURITY` | Already idempotent (enabling twice is a no-op, not an error) | Unchanged |
| `ALTER TABLE equipment ALTER COLUMN gmp_impact TYPE text ...` (migration 0007) | Already effectively idempotent — converting `text` to `text` succeeds without error on a repeat run | Unchanged |

**This directly closes the mechanism believed to have caused the original incident**: `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md` (2026-07-23) hypothesized that a partial run of `migrations/0011_companies_admin_rls_up.sql` — e.g. `CREATE POLICY companies_super_admin_all` succeeding, then a later statement failing — would abort the script *before ever reaching the trailing `GRANT` line*, and that a naive re-run from the top would immediately hit "policy already exists" on the first statement and abort again in the same place. That failure mode is no longer possible: every `CREATE POLICY` in 0010-0012 is now preceded by its own `DROP POLICY IF EXISTS`, so a full top-to-bottom re-run always reaches every statement in the file, including the trailing `GRANT`, regardless of what partial state it starts from.

## 2. How to verify a specific migration's state before running it

Run these against the live database (Supabase SQL Editor) before applying any `_up.sql`:

```sql
-- Tables (any migration that creates tables)
select table_name
from information_schema.tables
where table_schema = 'public' and table_name = '<table_name>';

-- Indexes
select indexname from pg_indexes where indexname = '<index_name>';

-- Policies
select policyname from pg_policies where tablename = '<table_name>' and policyname = '<policy_name>';

-- Triggers
select tgname from pg_trigger where tgname = '<trigger_name>' and not tgisinternal;

-- Constraints (e.g. the migration 0004 FK)
select conname from pg_constraint where conname = '<constraint_name>';

-- Grants
select grantee, privilege_type
from information_schema.role_table_grants
where table_name = '<table_name>' and grantee in ('authenticated', 'service_role');
```

With Phase F.2's idempotency fixes, **this pre-check is now optional** (any `_up.sql` file can simply be re-run safely) — but it remains good practice for understanding what a "partial" prior attempt actually left behind, and is required by `docs/DEPLOYMENT_RUNBOOK.md` Stage 3.1 regardless.

## 3. How to verify a full migration file was applied completely

Run the file's own trailing `GRANT` line's target as the check — if the grant is present, every statement before it in the file necessarily ran without aborting (Postgres executes a pasted SQL Editor script statement-by-statement, top to bottom, and Editor UIs typically stop on the first error):

```sql
-- migrations/0010 — final check
select grantee, privilege_type from information_schema.role_table_grants
where table_name = 'break_glass_access' and grantee = 'authenticated';
-- expect: 3 rows — SELECT, INSERT, UPDATE

-- migrations/0011 — final check
select grantee, privilege_type from information_schema.role_table_grants
where table_name = 'companies' and grantee = 'authenticated';
-- expect: 4 rows — SELECT, INSERT, UPDATE, DELETE

-- migrations/0012 — final check
select grantee, privilege_type from information_schema.role_table_grants
where table_name = 'users' and grantee = 'authenticated';
-- expect: 2 rows — SELECT, UPDATE (SELECT may also show as originating from migration 0002/0003 — the two are not distinguishable by this query alone, but the presence of UPDATE is unique to 0012)
```

## 4. Migration order and dependency reference

Unchanged from the Phase F.1 audit (`docs/DEPLOYMENT_VERIFICATION.md` §1) — reproduced here for a single-document runbook reference:

```
0001 identity_tenancy      →  (no dependency)
0002 users_self_select     →  0001
0003 grants                →  0001, 0002
0004 core_schema           →  0001
0005 projects_rls          →  0004
0006 documents_rls         →  0004
0007 equipment_fixes_and_rls → 0004
0008 qms_rls                → 0004
0009 phase3_grants           → 0004, 0005, 0006, 0007, 0008
0010 break_glass_rls         → 0001
0011 companies_admin_rls     → 0001
0012 users_company_admin_rls → 0001, 0002
```

0010, 0011, 0012 touch disjoint tables (`break_glass_access`, `companies`, `users` respectively) and may be run in any order relative to each other, but all three require 0001 (and 0012 additionally requires 0002) to already be applied — which is already the case in any environment where login works at all, since `users`/`roles` are load-bearing for authentication itself.

## 5. What this guide does not and cannot verify

This is a static-analysis and reference document, produced without live database access (same constraint as Phase F.1 — see `PHARMAGPT_v1.0_FINAL_RELEASE_CERTIFICATION.md` §7). It tells you *what to run and what to check*; it does not certify that any specific live Supabase project is currently in any specific state. Run the queries in §2/§3 yourself against your actual environment — do not treat this document's "expected" output as a substitute for that.

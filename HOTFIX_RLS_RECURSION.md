# HOTFIX — RLS Infinite Recursion on `users` (42P17)

**Severity:** Critical — production login fully broken.
**Status:** Fix written and unit-tested this session. **Not yet applied to the live database** — see "Deployment" below.
**Migration:** `migrations/0013_fix_users_rls_recursion_up.sql` / `..._down.sql`.

## Symptom

Every login failed. Reported error:

```
PostgreSQL 42P17: infinite recursion detected in policy for relation "users"
```

Stack: `routes/auth.py` → `resolve_tenant_context()` → `SELECT ... FROM users WHERE id = auth.uid()`.

## Root cause

`pharmagpt/auth/context.py:57-63` resolves every authenticated request's tenant context with:

```python
client.table("users").select("company_id, display_name, status, roles(name)").eq("id", supabase_user.id).maybe_single().execute()
```

`client` here is the anon-key + user-JWT client (`get_authenticated_client`) — RLS-enforced, not the service-role client. This query is evaluated against **every** permissive `SELECT` policy defined on `users`.

Migration `0012_users_company_admin_rls_up.sql` added two policies on `users` whose `USING`/`WITH CHECK` clauses subquery `users` **from within a policy defined on `users` itself**:

```sql
-- users_company_admin_read_company (abridged)
using (
    company_id = (select company_id from users where id = auth.uid())   -- ← subqueries `users`
    and company_id is not null
    and exists (
        select 1 from users u join roles r on r.id = u.role_id          -- ← subqueries `users` again
        where u.id = auth.uid() and r.name = 'company_admin'
    )
)
```

Postgres re-runs RLS policy evaluation for any query against a table, including a subquery. A policy on `users` that subqueries `users` therefore re-invokes the same policy set to evaluate its own subquery, which subqueries `users` again, and so on — infinite recursion, reported as `42P17`. This affects the policy for *every* caller, not just company admins: RLS combines all permissive `SELECT` policies on a table with `OR`, so any `SELECT` on `users` — including the ordinary self-lookup covered by `users_select_own` (migration 0002, `id = auth.uid()`, itself not recursive) — must still evaluate `users_company_admin_read_company` as part of that combined predicate, and hits the recursion.

`users_company_admin_update_company` has the identical shape and the same defect.

**Not the cause:** migrations 0010 (`break_glass_access`) and 0011 (`companies`) also subquery `users`, but from policies defined on *different* tables — that's ordinary cross-table filtering, not self-reference, and does not recurse. Left unmodified.

## Fix

`migrations/0013_fix_users_rls_recursion_up.sql` replaces the two direct subqueries with calls to two `SECURITY DEFINER` helper functions:

```sql
create or replace function current_user_company_id() returns uuid
language sql stable security definer set search_path = public
as $$ select company_id from users where id = auth.uid(); $$;

create or replace function current_user_role_name() returns text
language sql stable security definer set search_path = public
as $$ select r.name from users u join roles r on r.id = u.role_id where u.id = auth.uid(); $$;
```

A `SECURITY DEFINER` function runs as its **owner** (the role that applies this migration). No table in this schema has `FORCE ROW LEVEL SECURITY` set (confirmed against every `migrations/000*_up.sql`), so the table owner is exempt from RLS by default — the lookup inside the function bypasses RLS entirely instead of re-entering it, which breaks the recursion. This is the standard, documented Postgres/Supabase pattern for this failure mode.

The two policies are then redefined with the *same scoping logic* as before — own company only, `company_admin` role only — just sourced from the function calls instead of inline subqueries:

```sql
using (
    company_id = current_user_company_id()
    and company_id is not null
    and current_user_role_name() = 'company_admin'
)
```

**Tenant isolation is unchanged.** A company admin still sees only rows where `company_id` matches their own; no scoping condition was widened, narrowed, or removed — only the mechanism for looking up "my own company_id / role" changed from a recursive subquery to a non-recursive function call.

**No application code was changed.** `pharmagpt/auth/context.py` and `routes/auth.py` issue the same query as before; they now simply succeed instead of erroring, once the database-side policy is fixed.

## Regression coverage

`tests/test_migrations_rls_recursion.py` (new): parses every `migrations/*_up.sql` statically (no live database required, consistent with the rest of this test suite) and computes the **effective** policy set — for each `(table, policy_name)`, the definition from the highest-numbered migration that (re)defines it, since later `drop policy if exists` + `create policy` supersedes earlier definitions when migrations are applied in order. It fails if any effective policy subqueries its own target table via `FROM`/`JOIN`. This is a general guard (any future table, any future policy), plus a named pin for this exact incident. Verified as a true positive: run directly against 0012's original file content, the detector correctly flags both offending policies (`self-ref: True`); against the effective (0013-superseded) set, both clear.

Full existing suite re-run after adding the fix and the new test: **536 passed, 1 deselected, 0 failed** (534 pre-hotfix baseline + 3 new recursion-guard tests; the 1 deselect is pre-existing and unrelated to this change) — no regressions. This hotfix is DB-policy-only and touches no Python/application code path.

## Deployment (not yet done — requires live database access this session does not have)

Run `migrations/0013_fix_users_rls_recursion_up.sql` in the Supabase SQL Editor. It is idempotent (`create or replace function`, `drop policy if exists` + `create policy`, plain `grant`/`revoke`) — safe to run once or to re-run if interrupted. No application deploy is required; this is a database-only fix.

**Verification query after applying:**

```sql
select policyname, pg_get_expr(polqual, polrelid) as using_clause
from pg_policy
where polrelid = 'users'::regclass
order by policyname;
```

Confirm `users_company_admin_read_company` / `users_company_admin_update_company` reference `current_user_company_id()`/`current_user_role_name()`, not a `select ... from users` subquery. Then re-attempt a real login — `resolve_tenant_context()`'s query should return normally instead of raising `42P17`.

## Rollback

`migrations/0013_fix_users_rls_recursion_down.sql` drops the two fixed policies and the two helper functions. It does **not** recreate migration 0012's original recursive policies (that would reintroduce this outage) — run `0012_users_company_admin_rls_down.sql` afterward for a full rollback of the User Management RLS feature to migration 0011's state.

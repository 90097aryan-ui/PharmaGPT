# Manual Verification Checklist — Company Administration (Work Package 4)

**Status of every item below: NOT VERIFIED.** This session has no live Supabase SQL Editor session, no live Render/production session, and — per this environment's standing safety rule — never enters a password into any field, including test/dev credentials, so a live authenticated browser walkthrough could not be performed even if the deploy blockers were already resolved. What follows is (a) what was verified by source-code reading in this session, and (b) exact steps/queries for whoever has live access to close the gap. Do not treat "code reads correctly" as equivalent to "PASS" for any row below.

For each area: **Code review finding** (this session, direct read) → **Live verification required** (exact commands).

## 1. Assume Company Context

**Code review finding:** `routes/auth.py::assume_company()` (lines 172-234) requires a non-empty `reason`, caps `duration_minutes` at `MAX_ASSUME_DURATION_MINUTES = 240`, rejects assuming a suspended company (`status != "active"` → 400), revokes any prior active grant for the session before starting a new one, and never trusts a client-supplied `company_id` for anything except as the *target* of a permission-checked action (`@require_role("super_admin")` gates the whole route). This matches `tests/test_assume_company_context.py`'s 220 lines of mocked-client tests, all passing (see `TEST_OUTPUT.md`). **This is a code-correctness finding only.**

**Live verification required (NOT VERIFIED):**
1. Log in as a real Super Admin test account in a browser (a human must do this — do not paste credentials into any automated tool).
2. `GET /auth/companies` → expect 200 with a company list, not `{"error": "Database error: permission denied for table companies"}`.
3. `POST /auth/assume-company` with `{"company_id": "<real id>", "reason": "release verification"}` → expect 201 with `assumed_company_id`/`break_glass_id`/`expires_at`.
4. `GET /auth/me` → expect `assumed_company_id`, `assumed_company_name`, `break_glass_expires_at` present.
5. `POST /auth/end-assume-company` → expect `{"success": true}`, then re-check `GET /auth/me` no longer shows assumed-context fields.
6. SQL confirmation: `select * from break_glass_access order by created_at desc limit 1;` — confirm the row exists with `revoked_at` now set after step 5.

## 2. Company switching

**Code review finding:** switching is "end current grant, start new one" (`_revoke_active_grant` is called unconditionally at the top of `assume_company()` before inserting the new grant) — a Super Admin can never hold two simultaneous grants. Confirmed by direct read of lines 209-221.

**Live verification required (NOT VERIFIED):** repeat steps 3-4 above for a second company without calling end-assume-company first; confirm the first grant's `revoked_at` gets set and only the second grant is active (`select * from break_glass_access where super_admin_user_id = '<id>' and revoked_at is null;` should return exactly one row).

## 3. Company isolation

**Code review finding:** `routes/companies.py`'s four routes are all `@require_role("super_admin")`-only. `routes/users.py::list_users`/`update_user` scope every Super-Admin-path query with an explicit `.eq("company_id", g.tenant.company_id)` filter (never trusting RLS alone for the service-role path — see module docstring, lines 17-32). `migrations/0011_companies_admin_rls_up.sql`'s `companies_company_admin_read_own` policy (`using (id = (select company_id from users where id = auth.uid()))`) and `0012`'s `users_company_admin_read_company`/`update_company` policies were read directly in this session and are logically scoped to "your own company only" — no cross-company clause found.

**Live verification required (NOT VERIFIED — this is the actual blocker, not a formality):**
1. Confirm the migration state matches what was read (run the `pg_policies`/`role_table_grants` queries in `PRODUCTION_RELEASE_CHECKLIST.md` §B).
2. With two real company_admin accounts in two different companies: `GET /users` as Company A's admin, confirm zero rows belonging to Company B; `PATCH /users/<a-company-b-user-id>` as Company A's admin, confirm 403/404, not success.
3. As an assumed-context Super Admin for Company A, attempt the same `PATCH` against a Company B user id — confirm the app-level `.eq("company_id", ...)` filter (point 3 of the code review finding) actually blocks it live, not just in the mocked test.

## 4. Permission inheritance

**Code review finding:** roles are frozen (`migrations/0001`, 4 rows: `super_admin`/`company_admin`/`reviewer_qa`/`user`), no custom-role or inheritance system exists — `routes/users.py::update_user` rejects `role_id` outside `{2,3,4}` before it reaches Postgres (line 162-163), and the DB trigger `chk_users_super_admin_company_null` (migration 0001) independently rejects any attempt to create a `company_id`-having super_admin or a `company_id`-null non-super-admin, regardless of what the route sends.

**Live verification required (NOT VERIFIED):** `PATCH /users/<id>` with `{"role_id": 1}` → expect clean 400 `"role_id must be one of 2 (company_admin), 3 (reviewer_qa), 4 (user)"`, confirming the route-level guard fires (this specific check needs no live DB and was already exercised by a mocked test — worth a quick live spot-check anyway since it's on the critical path).

## 5. Audit logging

**Code review finding:** `routes/companies.py::_audit_best_effort()` and `routes/users.py::_audit_best_effort()` both call `qms_repo.add_audit_entry()`, writing to the Postgres `audit_trail` table (migration `0008`/`0009`), wrapped in a bare `except Exception: logger.exception(...)` — deliberately non-blocking, per the code's own comment, *because* the author already anticipated `0009`'s grants might also not be confirmed active. **Note a real bug found in this session, not previously documented:** `routes/users.py:134`, `_audit_best_effort("User invited", provisioned.get("user_id", email), ...)` — `provision_user()`'s return dict has no `"user_id"` key (it returns `auth_user_id`/`temporary_password`), so this always falls back to logging `email` as the record id instead of the actual user id. Low-severity (the row still gets written with a valid company_id/actor/action, just an imprecise `record_id` for this one action type) — see final certification's Low findings.

**Live verification required (NOT VERIFIED):** after any Company/User admin action, `select * from audit_trail where record_type in ('company','user') order by created_at desc limit 10;` — confirm rows exist and are populated. If no rows appear despite the UI action succeeding, this indicates `0009`'s grants on `audit_trail` are also not active (best-effort logging swallowing the failure silently) — check `docs/DEPLOYMENT_VERIFICATION.md` §1 row for `0009`.

## 6. Cross-company protection

**Code review finding:** every code path reviewed above (companies.py role-gating, users.py explicit company_id filtering, the RLS policy text itself) is designed to prevent cross-company access. `docs/MULTI_TENANT_SECURITY_REPORT.md` (Phase F, independently spot-checked in this session against the actual route files it cites — `companies.py`/`users.py` — and found accurate) states this was **never live-tested** because the whole feature was broken closed (every request failing with 42501 regardless of target company) — so "no cross-tenant leak observed" reflects "nothing could be tested," not "isolation was proven."

**Live verification required (NOT VERIFIED, highest priority of this whole checklist):** the two-company spot-check in item 3 above is the actual test of this property. Do not sign off Company Administration as cross-tenant-safe without it, regardless of how correct the code reads.

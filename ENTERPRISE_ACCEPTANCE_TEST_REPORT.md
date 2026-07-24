# Enterprise Acceptance Test Report — Company Administration / User Management / Role Management / Assume Company Context

**Date:** 2026-07-23
**Tester:** Claude (Claude Code), acting as delegate for Platform Super Admin (`jugalr@pharmagpt.ai`)
**Scope:** Company Administration, User Management, Role Management, Assume Company Context (break-glass), Company Context Audit Trail, Cross-Tenant Isolation, Permission Error UX — the Phase 3.5 identity/admin feature set built on migrations `0010`/`0011`/`0012`.
**Method:** Real Flask dev server (`localhost:5187`, already running), real Supabase Auth logins (Platform Super Admin + the two pre-existing `e2e-admin-a`/`e2e-admin-b` company_admin test fixtures from `PHASE2_COMPLETION.md` §8), a real browser session for UI-level verification, direct curl/Python calls against the live Supabase project (both through the app and bypassing it entirely) to isolate root causes, and the full `pytest` suite for regression.

---

## Headline result: NO-GO

**The premise that migrations 0010, 0011, and 0012 "have been applied successfully" is not correct.** Direct, repeated testing against the live Postgres database — independent of the Flask app entirely — shows that the `GRANT` statements each migration ends with, and in the case of `0012` its two `CREATE POLICY` statements, are **not in effect**. As a result:

- **Company Administration is 100% non-functional** — every operation (list, create, suspend, reactivate) fails.
- **Assume Company Context is 100% non-functional** — the picker that lists companies to assume fails at the first step.
- **Company Context Audit Trail cannot be exercised** — it depends entirely on Assume Company Context.
- **User Management is functional for invite only** (which uses a service-role client that bypasses RLS/grants) but **broken for list-roster and role/status update** — a company_admin can only ever see their own single row, not their company's roster, and any `PATCH /users/<id>` fails with a raw Postgres permission error.
- **Role Management** (folded into `PATCH /users/<id>`) is blocked by the same update failure — the validation logic itself (rejecting `role_id=1`, requiring 2/3/4) is correct and was verified working, but no actual role reassignment can complete.

This is a **database/environment state issue, not an application code defect** — the code's own comments in `services/supabase_client.py` and `routes/companies.py` explicitly anticipated this exact failure mode ("a missing RLS GRANT — a real, observed failure mode the first time this phase's new migrations haven't been applied yet"). The fix is almost certainly re-running the tail end of each migration file. I raised this mid-test and asked for explicit direction on whether to apply the fix myself (it would only require the two `GRANT` lines already present in the reviewed `0010_up.sql`/`0011_up.sql`, both idempotent and reversible via the paired `_down.sql`); the response reiterated the original instructions without authorizing that change, so **no fix was applied** — this report documents the system as found.

---

## 1. Company Administration — **FAIL (Critical)**

**What was tested:** Login as Platform Super Admin via the real browser (`jugalr@pharmagpt.ai`), navigate to the "Companies" admin section, list existing companies, and create a new one ("Acceptance Test Pharma A", industry `pharma`, admin `admin-a@acceptancetest.local`).

**Result:**
- `GET /companies` → `500`
- `POST /companies` → `500`
- No company was created (confirmed both from the UI still showing "No companies yet." and from a direct service-role query of the `companies` table).

**Root cause, isolated three independent ways:**
1. Through the real browser session (network inspection): the client-side `postgrest` library raised `ValueError("Neither bearer token or basic authentication scheme is provided")` — traced to `venv/Lib/site-packages/postgrest/base_client.py:58`, thrown when [`get_authenticated_client()`](pharmagpt/services/supabase_client.py:38) is called with an empty token.
2. Via `curl` with a **real, manually-obtained, valid** Supabase JWT for the Super Admin (bypassing whatever the browser-side issue was): `GET /companies` → `500 {"error": "Database error: permission denied for table companies"}`.
3. Via a raw Python call to the Supabase client directly (bypassing Flask entirely, exactly reproducing what `get_authenticated_client()` does): identical Postgres error, code `42501`, with a hint that is the smoking gun: **`Grant the required privileges to the current role with: GRANT SELECT ON public.companies TO authenticated;`** — i.e., Postgres itself is telling us to run the exact line that [`migrations/0011_companies_admin_rls_up.sql:35`](migrations/0011_companies_admin_rls_up.sql:35) already contains.

Both failure modes are real and independent: even if the frontend/browser-side empty-token issue (#1) were fixed, path #2/#3 shows the request would still fail once it reached Postgres, because the grant genuinely isn't active.

**Also confirmed via service-role (bypasses RLS entirely):** the `companies` table itself is intact and has 4 rows (`Acme Pharma QA Co`, `Beta Biotech QA Co`, `PharmaGPT Bootstrap Company (pre-migration data)`, `Lean Architect`) — this is a permissions problem, not data loss or a missing table.

**Severity:** Critical / blocking. Nothing in this area can be used as delivered.

---

## 2. User Management — **PARTIAL FAIL (Critical)**

**What was tested:** Using the pre-existing `e2e-admin-a@pharmagpt-test.local` (company_admin, "Acme Pharma QA Co") test fixture documented in `PHASE2_COMPLETION.md` §8 (password reset via service-role Admin API for this session, since the original was never recorded — see **Test artifacts** below):

| Action | Result |
|---|---|
| `GET /users` (list company roster) | **FAIL** — returns `200` but with only **1 row** (the caller's own), not the 3 real users in Acme (`E2E Admin A`, `E2E Reviewer A`, `E2E User A`). |
| `POST /users` (invite new user, role `user`) | **PASS** — `201`, user correctly created with `company_id` scoped to Acme (verified via service-role query). |
| `PATCH /users/<id>` (update a *different* user in the same company) | **FAIL** — `400 {"error": "Could not update user: {'message': 'permission denied for table users', 'code': '42501', 'hint': 'Grant the required privileges to the current role with: GRANT UPDATE ON public.users TO authenticated;'}"}` |

**Root cause:** the same pattern as §1. `migrations/0012_users_company_admin_rls_up.sql` ends with `grant select, update on users to authenticated;` (line 55) and creates two new policies (`users_company_admin_read_company`, `users_company_admin_update_company`). The `SELECT` grant *appears* to work, but that's because a `SELECT` grant on `users` already existed from migration `0002` (`users_select_own`, "a user reading their own row") — it predates this feature. The single-row result on `GET /users` is exactly what you'd get from *only* that old self-select policy being active, with the new `users_company_admin_read_company` policy contributing nothing. The `UPDATE` grant is new to 0012 and has no such pre-existing fallback — its absence is directly visible as a `42501` error.

**Why `POST /users` (invite) works despite this:** [`routes/users.py:106`](pharmagpt/routes/users.py:106) calls `provision_user()`, which uses [`get_service_role_client()`](pharmagpt/services/identity_admin.py) — a service-role key that bypasses RLS and grants entirely by design (documented in `supabase_client.py:56-73` as the one sanctioned use of that client). Invite is therefore unaffected by the migration issue; list and update are not, because they correctly use the RLS-scoped anon-key client per the module's own defense-in-depth design.

**Severity:** Critical / blocking for the list and update paths — a company_admin cannot see or manage their team as delivered. Invite works.

---

## 3. Role Management — **BLOCKED (Critical, same root cause as §2)**

Role reassignment is folded into `PATCH /users/<id>` (`routes/users.py:139-142`), so it inherits §2's `UPDATE` failure entirely — no role change can be persisted right now.

**What was independently verified and passed:**
- `PATCH /users/<id>` with `{"role_id": 1}` (attempting to grant Super Admin) → **`400 {"error": "role_id must be one of 2 (company_admin), 3 (reviewer_qa), 4 (user)"}"`**, correctly rejected *before* it ever reaches Postgres, per `routes/users.py:139-141`. This validation logic is correct and independent of the DB issue.
- The automated test `tests/test_role_management.py` (102 lines, mocked Supabase client) already covers the happy path, the `role_id=1` rejection, and the assumed-context Super Admin company-scoping — all 102 lines' worth pass in the regression suite (§9). What it explicitly cannot cover (per its own docstring) is real RLS behavior against live Postgres, which is exactly what this session found broken.

**Severity:** Critical — the feature is fully specified and its guardrail logic is correct, but zero role reassignments can currently be completed end-to-end.

---

## 4. Assume Company Context (break-glass) — **FAIL (Critical)**

**What was tested:** Login as Super Admin, open the "Assume Company Context" modal (confirmed present and correctly rendered — company picker, required "Reason" field, duration field capped at 240 minutes). Attempted to load the company picker (`GET /auth/companies`) both through the real browser and via direct curl with a valid Super Admin JWT.

**Result:** `GET /auth/companies` → `500 {"error": "Database error: permission denied for table companies"}` — identical root cause to §1, since [`routes/auth.py:168`](pharmagpt/routes/auth.py:168) queries the same `companies` table under the same missing grant. The picker cannot even populate, so no assume-company session can be started at all. `POST /auth/assume-company` would fail identically (it queries `companies` at line 202 and inserts into `break_glass_access` at line 215 — the latter table's grant is *also* missing per migration `0010`, confirmed directly: `permission denied for table break_glass_access`, hint `GRANT SELECT ON public.break_glass_access TO authenticated;`).

**What was confirmed correct at the design/code level** (via source review, since the live path is blocked):
- The middleware's "standing Super Admin has no access to tenant data" guard (`auth/middleware.py`) is unaffected by this — it's a Flask-layer check, verified working (§6).
- `routes/auth.py`'s `reason` requirement, `duration_minutes` cap (240 min, `MAX_ASSUME_DURATION_MINUTES`), and re-revocation of any prior active grant before starting a new one are all present in code and covered by `tests/test_assume_company_context.py`'s 220 lines of mocked-client tests (all passing — see §9), but none of this can be exercised live right now.

**Severity:** Critical / blocking. This is the mechanism the entire "no standing Super Admin access to tenant data" security model depends on for legitimate access — it is currently unusable.

---

## 5. Company Context Audit Trail — **UNTESTABLE (blocked by §4)**

The audit trail *is* the `break_glass_access` table itself (no separate audit UI/route exists — confirmed by code search: `routes/`, `templates/index.html`, and `static/js/` were checked for any list/history view of past grants, and none exists). Since `break_glass_access` is unreachable under the current grant state (§4), no grant can be created, and there is nothing to audit yet.

**Pre-existing design gap, independent of the migration issue, worth flagging regardless:** even once the grant issue is fixed, there is **no admin-facing UI to review historical break-glass grants** — `GET /auth/me` only ever surfaces the *currently active* grant (for the "Acting as X, expires in N min" banner). A compliance/audit reviewer has no way to see *past* assume-company sessions (who, when, why, for how long) without querying Postgres directly. Given this feature exists specifically to satisfy an audit/compliance requirement (`PLATFORM_ARCHITECTURE.md` §7/§13.2: "administrative access to tenant content is an explicit, logged, time-boxed break-glass action"), a written record that's only queryable by direct database access, not through the product, is a real gap to weigh before calling this objective complete — separate from and in addition to the Critical blocker above.

**Severity:** Untestable now; Medium-High design gap once unblocked (no audit *viewer*, only raw storage).

---

## 6. Cross-Tenant Isolation — **PASS (with a caveat)**

**What was tested:** Standing (non-assumed) Super Admin access to a spot-check of business-data routes, confirming the previously-fixed guard (referenced in `auth/middleware.py`'s docstring as the finding from an earlier, undocumented Enterprise Acceptance Test) still holds:

| Route | Result |
|---|---|
| `GET /dashboard/stats` | `403` ("Super Admin has no standing access to tenant content") |
| `GET /projects` | `403` |
| `GET /risk/assessments` | `403` |
| `GET /equipment` | `403` |
| `GET /qms/deviations` | `403` |
| `GET /qms/capa` | `403` |
| `GET /qms/change-control` | `403` |
| `GET /dashboard/validation-score` | `200` — not tenant-scoped data (session-only stat), correctly not guarded |

All matched the existing `tests/test_security_super_admin_guard.py` parametrized expectations (18 routes, all passing in §9's regression run).

**The caveat:** for the *new* Phase 3.5 surface specifically (Company Administration, User Management, Assume Company Context), no cross-tenant leak was observed **only because the whole feature is broken closed, not because isolation was positively verified working**. I could not test, for example, "can Acme's company_admin see or edit a Beta Biotech user" in a meaningful way, because *no* update succeeds right now regardless of which company is targeted (§2's `42501` fires identically either way). This must be re-verified once the grants are fixed — do not read this section as clearing the new admin routes for cross-tenant safety, only the pre-existing 18-route guard.

**Severity:** Pass for the pre-existing guard; **Not Yet Verified** for the new admin routes' cross-tenant behavior specifically (blocked by §1-§4, not a known failure).

---

## 7. Permission Error UX — **MIXED**

**What worked well:**
- Clean, human-readable 400s for client-side validation (`role_id must be one of 2 (company_admin), 3 (reviewer_qa), 4 (user)`; `legal_name is required`; `reason is required`; etc.) — all correctly returned before touching the database.
- The standing-Super-Admin 403 message is clear and consistent across all 18 pre-existing guarded routes: `"Super Admin has no standing access to tenant content"` — verified both live and in `tests/test_security_super_admin_guard.py:63`.
- The global `window.fetch` patch in `static/js/auth.js` (lines 81-104) surfaces any `403` response as a toast automatically, app-wide, with zero per-module wiring needed — a good, general-purpose design.

**Two real findings:**
1. **Wording inconsistency (Low-Medium):** `routes/users.py` uses a slightly different 403 message for "Super Admin has no standing access" (`"...assume a company context first"` appended, lines 71-72, 92-93, 130-131) than the other 18 guarded routes (`"Super Admin has no standing access to tenant content"`, no suffix). Neither is wrong, but the split is inconsistent, and `routes/users.py` is not included in `test_security_super_admin_guard.py`'s `GUARDED_ROUTES` list, so nothing currently catches a future drift between the two.
2. **Raw infrastructure errors leak to the end user (Medium, surfaced directly by this test):** when the underlying Postgres call fails with a permissions error (as it currently does everywhere in §1-§4), the resulting message — e.g. `"Could not update user: {'message': 'permission denied for table users', 'code': '42501', 'hint': 'Grant the required privileges to the current role with: GRANT UPDATE ON public.users TO authenticated;'}"` — is passed straight through to the JSON response and would render verbatim in the `admin_users.js`/`admin_companies.js` toast (`showToast(data.error || ...)`). This is technically accurate but not a message any real user (or even most admins) should see; it exposes internal schema/role names. `handle_postgrest_errors` (`supabase_client.py:76-97`) should distinguish "environment misconfiguration" (should probably 503 with a generic message and get logged loudly server-side) from genuine "you don't have permission to do this" (should stay a clean 403/404). Right now both collapse into the same raw-passthrough 500.

**Severity:** Medium overall — nothing here is a security hole (no cross-tenant existence is leaked; errors are appropriately generic on the *data* front, just too technical on the *infrastructure* front), but #2 is a real, currently-live UX defect this test directly triggered, not a hypothetical.

---

## 8. Test artifacts / side effects from this session

Full transparency on what this test session touched in the live Supabase project, for whoever picks this up next:

- **Password reset:** `e2e-admin-a@pharmagpt-test.local`'s Supabase Auth password was reset (via service-role Admin API) to enable login, since no password was ever documented for this `PHASE2_COMPLETION.md` §8 fixture and it was needed to test the company_admin path live. The attempt to also reset `e2e-admin-b@pharmagpt-test.local`'s password failed with an unrelated Supabase Admin API/JWT-verification error (`unrecognized JWT kid <nil> for algorithm ES256`) — that account's password is unchanged. Neither reset nor attempted reset touched role, company assignment, or any business data.
- **One new company row** ("Acceptance Test Pharma A") was **not** created — the `POST /companies` attempt failed with `500` (§1), so nothing was persisted; verified via a direct service-role query showing the same 4 pre-existing companies as before this session.
- **One new user** was created: `e2e-newuser-a@pharmagpt-test.local` ("E2E New User A", role `user`) inside Acme Pharma QA Co, via the working `POST /users` invite path (§2). This is inert test data, consistent with the existing `e2e-*` fixture convention, and left in place for reuse by future test sessions (matching the precedent set in `PHASE2_COMPLETION.md` §8: "Not cleaned up per explicit instruction").
- No schema, RLS policy, or GRANT was modified — I explicitly did not apply the fix described in the headline section, pending clearer direction.

---

## 9. Regression suite

```
venv\Scripts\python.exe -m pytest -q
500 passed, 1 deselected, 21 warnings in 252.98s (0:04:12)
```

No failures, no regressions. This includes all 9 test files relevant to this feature set (`test_assume_company_context.py`, `test_role_management.py`, `test_security_super_admin_guard.py`, `test_security_tenant_rbac_esig.py`, `test_app_auth_integration.py`, `test_auth_context.py`, `test_auth_decorators.py`, `test_bootstrap_super_admin.py`, `test_routes_auth.py`) plus the full pre-existing suite (Document Engine, Approval Engine, Lifecycle, QMS, Equipment, Knowledge Base, etc.).

**Important caveat, unchanged from before this session:** every one of these tests mocks the Supabase client. **None of them would have caught anything in this report** — the entire set of findings above only surfaces when exercised against a real Postgres instance, which is exactly what this acceptance test did that the automated suite structurally cannot. A green regression suite is necessary but was never sufficient here, and should not be read as "the Phase 3.5 feature set works."

---

## 10. GO / NO-GO Recommendation

# **NO-GO**

Company Administration, Assume Company Context, and the list/update halves of User Management and Role Management are **not usable in their current deployed state** due to missing Postgres grants/policies from migrations 0010-0012. This is corrected by re-applying the tail-end `GRANT` (and, for 0012, `CREATE POLICY`) statements already written and reviewed in the migration files themselves — likely a five-minute fix — but it has not been applied during this session, since I raised it mid-test and did not receive clear authorization to modify the live database.

**Before this feature set can be called complete, in priority order:**
1. **Blocking:** Confirm and fix why migrations 0010/0011/0012's `GRANT`/`CREATE POLICY` statements aren't active (likely: re-run each `_up.sql` file in full in the Supabase SQL Editor, checking for an error partway through a prior attempt — e.g. a "policy already exists" that halted the script before reaching the trailing `GRANT` line).
2. **Blocking, re-test after #1:** Re-run this entire acceptance test end-to-end (all 7 areas) against a database where the grants are confirmed active — nothing in this report should be assumed to also apply post-fix; in particular, cross-tenant isolation for the *new* admin routes specifically (§6's caveat) has not yet been positively verified and must be, not just assumed.
3. **Should-fix, not blocking:** the raw-Postgres-error-passthrough UX issue (§7.2) and the `routes/users.py` 403-wording inconsistency (§7.1).
4. **Product decision needed, not blocking this GO/NO-GO:** whether a break-glass audit-log *viewer* (§5) is in scope for this milestone or a documented future item.

**Per your explicit instruction, do not proceed to AI or Phase 4 work until item 1 is resolved and this report is re-run to a clean GO.**

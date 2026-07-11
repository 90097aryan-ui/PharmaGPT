# Phase 2 Completion Report — Authentication (Supabase Auth)

> Status: **Approved.** Completed 2026-07-11. See [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md)
> Phase 2 for the original objective/success-criteria definition this report validates against.

---

## 1. Features implemented

- **Identity/tenancy schema**: `companies`, `roles` (4 frozen roles, seeded), `users` (1:1 with
  `auth.users`, `company_id` nullable only for `super_admin`, enforced by a trigger), `company_settings`,
  `break_glass_access`.
- **Session issuance**: `POST /auth/login` exchanges email/password for a Supabase Auth session via
  `sign_in_with_password` — the app never stores, hashes, or compares a password itself (Supabase Auth
  owns that entirely, anon key only).
- **Session teardown**: `POST /auth/logout` revokes the caller's session globally
  (`auth.admin.sign_out(token, "global")`) — verified live to invalidate the access token immediately,
  not just the refresh token.
- **Tenant-context resolution**: `GET /auth/me` and every protected route resolve a `TenantContext`
  (user_id, email, display_name, role, company_id) by verifying the bearer token with Supabase
  (`auth.get_user`) and then reading the caller's own `users` row *under RLS as that user*.
- **Global route protection**: a single `before_request` gate (`pharmagpt/auth/middleware.py`) rejects
  any request without a valid bearer token, except `/`, `/auth/login`, `/health`, `/static/*` — applied
  uniformly to every existing route blueprint with zero changes to those files.
- **Super Admin bootstrap**: `scripts/bootstrap_super_admin.py`, a CLI-only, idempotent, service-role
  script — the one deliberate use of `SUPABASE_SERVICE_ROLE_KEY` anywhere in the codebase, since
  creating the first Super Admin cannot happen under RLS as an ordinary authenticated user.
- **Login UI**: `static/js/auth.js` + `templates/index.html` — email/password/remember-me form, loading
  state, error handling, session storage (`localStorage` for Remember Me, `sessionStorage` otherwise),
  and a `window.fetch` patch that attaches the bearer token to every existing module's plain `fetch()`
  call app-wide, with zero changes to those modules.
- **Automatic routing by session state**: authenticated users land on the dashboard; unauthenticated
  users see the login screen; an existing-but-invalid stored session is detected via `/auth/me` and
  falls back to login without a stuck spinner.

## 2. Files changed

### Backend (Steps 2.1–2.5)
| File | Change |
|---|---|
| `pharmagpt/app.py` | Registers the auth middleware and `auth` blueprint; adds `/health` |
| `pharmagpt/auth/__init__.py`, `context.py`, `decorators.py`, `middleware.py` | New — JWT verification, tenant-context resolution, `require_auth` decorator, global gate |
| `pharmagpt/routes/auth.py` | New — `/auth/login`, `/auth/logout`, `/auth/me` |
| `pharmagpt/services/supabase_client.py` | Adds `get_authenticated_client()` (anon key + user token) and `get_anonymous_client()` |
| `scripts/bootstrap_super_admin.py` | New — one-time Super Admin creation (service-role key) |
| `requirements.txt` | Adds Supabase Python SDK + JWT-related dependencies |
| `tests/conftest.py`, `tests/test_routes_upload_async.py` | Adjusted for the new auth requirement on protected routes |
| `tests/test_app_auth_integration.py`, `test_auth_context.py`, `test_auth_decorators.py`, `test_bootstrap_super_admin.py`, `test_routes_auth.py` | New test coverage |

### Frontend (Step 2.6)
| File | Change |
|---|---|
| `pharmagpt/templates/index.html` | Login view, session-check view, user badge + logout control, script load order |
| `pharmagpt/static/js/auth.js` | New — login form, session storage, `fetch` patch, view routing; includes the post-login Projects-reload fix |
| `pharmagpt/static/css/style.css` | Login/session-check/user-badge styles only — no dashboard styling touched |
| `tests/test_login_ui.py` | New — asserts login markup/ids and script load order in the rendered SPA shell |

**26 files changed, 2012 insertions(+), 23 deletions(-)** across the three Phase 2 commits (see §7).

## 3. Database migrations applied

All three applied to the Staging Supabase project (`qjhmqleaoelztruepmio`) and confirmed live via direct
query — schema and seed data verified present, not just migration files existing on disk:

| Migration | Purpose |
|---|---|
| `0001_identity_tenancy_up.sql` | Creates `companies`, `roles` (seeded with the 4 frozen roles), `users` (+ super-admin/company_id trigger), `company_settings`, `break_glass_access`; enables RLS on all five with zero policies (default-deny) except a public `roles` read policy |
| `0002_users_self_select_up.sql` | Adds the one RLS policy Phase 2 needs: an authenticated user may read only their own `users` row (`id = auth.uid()`) — narrower than and not a preview of Phase 3's company-scoped policy set |
| `0003_grants_up.sql` | Adds the table-level `GRANT`s RLS policies need to take effect at all (`service_role`: full CRUD on all five tables; `authenticated`: `SELECT` on `roles` and `users` only) — root-caused during Phase 2 as a gap Supabase's default provisioning didn't fill automatically |

Corresponding `_down.sql` rollback scripts exist for all three (see §6).

## 4. Test summary

- **Automated**: **227 pytest tests passing**, 1 deselected (`slow` marker), 0 failing — includes all
  new auth/login-UI tests plus the full pre-existing suite, confirming zero regressions.
- **Live end-to-end validation** (Staging Supabase, two real test Companies + Company Admins created via
  a one-off service-role script — see §8):

| Check | Result |
|---|---|
| JWT issuance on login | Real ES256-signed Supabase JWT, correct `sub`/`email`/`exp` claims |
| `/auth/me` → TenantContext | Matched fixture data exactly (company_id, role, display_name) |
| Dashboard loads post-login | Full UI rendered, verified in-browser |
| Bearer token attached to all requests | Confirmed via network log: pre-login calls 401, post-login calls 200, with no per-module code changes |
| Logout invalidates session | Same still-unexpired token → 401 on every route immediately after logout |
| Page refresh restores session | Session, dashboard, and Projects list all restored without re-login |
| Remember Me = ON | `localStorage`; persisted to a brand-new browser tab |
| Remember Me = OFF | `sessionStorage`; did not persist to a new tab |
| `users` self-select RLS | Admin A's token returned zero rows for Admin B's row and for an unfiltered query (RLS-filtered at the database level, not app-filtered); `companies` table returned a hard permission-denied for `authenticated` |

## 5. Known limitations

- **No Company/Company-Admin creation flow in the app.** Neither an HTTP endpoint nor a UI exists for
  this — the roadmap lists it as a Phase 2 success criterion but not in Phase 2's own file list. The two
  Staging test Companies were created directly via the service-role key (same pattern as
  `bootstrap_super_admin.py`). A real operator has no way to do this today short of the same manual
  approach or direct Supabase dashboard access.
- **Full cross-tenant RLS is out of scope by design, not a gap.** Only the narrow `users` self-select
  policy exists. Business data (projects, documents, QMS, equipment, etc.) still lives in SQLite,
  untouched by `company_id` — Phase 3 activates the real company-scoped RLS policy set and migrates that
  data, per `migrations/0001_identity_tenancy_up.sql`'s own comments.
- **`test_supabase.py` and `project_tree.txt`** (repo root) remain untracked/uncommitted — ad hoc scratch
  artifacts from local development, not part of Phase 2 feature work. Left as-is; not part of this
  completion scope.

## 6. Rollback procedure

Auth is not feature-flagged at the code level, so rollback is a real branch/deploy revert plus a
database rollback, in this order:

1. **Application code**: `git revert` the three Phase 2 commits (§7), or redeploy the prior release tag —
   removes the middleware, auth routes, and login UI; the app returns to its pre-Phase-2 no-auth,
   single-tenant behavior.
2. **Database**: run the migration `_down.sql` files in **reverse** order against the same Supabase
   project:
   ```
   migrations/0003_grants_down.sql
   migrations/0002_users_self_select_down.sql
   migrations/0001_identity_tenancy_down.sql
   ```
3. **No Production cutover has occurred** — Render's `render.yaml` does not yet reference any
   `SUPABASE_*` environment variable, so a rollback at this stage has no live-traffic blast radius by
   construction. This is a Staging-only rollback.
4. Staging test fixtures (two Companies, two Company Admins — see §8) are independent of the schema and
   do not need separate cleanup as part of a rollback; dropping the tables in step 2 removes them.

## 7. Git commit hashes

| Commit | Subject |
|---|---|
| `ec249d17fa1cb67863f9d767e2b0479d9ec8227d` | Add Supabase login UI and session management (Phase 2 step 2.6) |
| `603129620dbe364facf1cc1be9f8a0d2bbbda2e2` | Add Supabase Auth backend: identity/tenancy schema, tenant-context resolver, auth middleware (Phase 2 steps 2.1-2.5) |
| `bc82a3e07ed3da84bcaf4c2cbf22e181294fc446` | Reload Projects sidebar immediately after login, not just on refresh |

Preceding Phase 1 (Supabase provisioning) commits, for reference: `c0d9180` (Add Supabase Python SDK),
`3dafe32` (Add Supabase client), `7c8aa4b` (Update Python dependencies).

Tagged as **`phase2-auth-complete`** at `bc82a3e07ed3da84bcaf4c2cbf22e181294fc446`.

## 8. Staging test fixtures (kept intentionally — reused in Phase 3)

Two Companies with Company Admin accounts exist in the Staging Supabase project for reuse in Phase 3's
multi-tenant and RLS validation. **Not cleaned up per explicit instruction.**

| Company | Admin email | Role |
|---|---|---|
| Acme Pharma QA Co | `e2e-admin-a@pharmagpt-test.local` | company_admin |
| Beta Biotech QA Co | `e2e-admin-b@pharmagpt-test.local` | company_admin |

## 9. Phase 3 prerequisites

Per `docs/IMPLEMENTATION_ROADMAP.md` Phase 3's own dependency line ("Phase 2 — migrated data must be
assignable to a real company and users"), plus two items surfaced during this validation:

1. **Satisfied**: Phase 2's auth foundation is committed, tested (227 tests), and live-verified against
   Staging — Phase 3 can build on it.
2. **Decide before starting**: how Companies/Company Admins get created going forward — accept the
   manual/service-role approach permanently, or schedule a minimal admin-provisioning flow before Phase 3
   needs to create real companies at scale (see §5).
3. **Carry forward**: the two Staging test fixtures (§8) are intended for Phase 3's multi-tenant/RLS
   validation — do not delete them as part of Phase 3 setup.
4. **Full RLS policy set** (`DATABASE_ARCHITECTURE.md` §13) is Phase 3's own deliverable, not a
   pre-existing gap to fix first — confirmed the current default-deny posture is correct and intentional.

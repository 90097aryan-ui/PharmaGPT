# PHASE F.2 — Production Enablement (Implementation Only)
## PharmaGPT v1.0

**Date:** 2026-07-24
**Mode:** Implementation only — no feature additions, no refactoring, no UI changes. Every change below is either (a) committing code that already existed on disk, (b) making existing SQL idempotent, (c) a one-line bug fix in existing audit-logging wiring, (d) documentation/config additions for an already-existing runtime dependency, or (e) new automated tests for already-existing routes.
**Follows:** `PHARMAGPT_v1.0_FINAL_RELEASE_CERTIFICATION.md` (Phase F.1, NO-GO, 64%), which found the "missing GRANTs" framing was incomplete — the larger problem was that Company Administration had never been committed to git or deployed at all.

---

## What this phase did, objective by objective

**1. Commit all untracked Company Administration files.**
Done. `git commit 559d14c` on `main` (local only — not pushed, see "Remaining manual actions"). All 121 previously modified/untracked files are now in git history, including `pharmagpt/routes/companies.py`, `routes/users.py`, `services/identity_admin.py`, `pharmagpt/audit.py`, the three admin JS files, and migrations `0010`-`0012`. This was committed as a single commit rather than split into "Company Administration only" vs. "everything else," because the two are not actually separable — the admin routes depend on `pharmagpt/audit.py`, `auth/decorators.py`, and `auth/middleware.py` changes that were part of the same accumulated, never-committed Phase F work, and splitting them would produce an intermediate commit that doesn't build/pass tests cleanly.

**2. Ensure routes, services, audit integration, and migrations are complete.**
Verified, not re-built: `pharmagpt/app.py` already registers both `companies_bp` and `users_bp` (lines 43-44, 88-89). Every endpoint the frontend JS calls (`admin_companies.js`, `admin_users.js`, `admin_assume_context.js`) has a matching backend route — checked by direct grep cross-reference, no mismatches found. One real gap was found and fixed: `routes/users.py:134`'s audit call read `provisioned.get("user_id", email)`, a key `provision_user()` never returns (it returns `auth_user_id`) — every "User invited" audit entry was silently logging the invitee's email instead of their real user id. Fixed to read `auth_user_id`. This is a one-line bug fix in existing wiring, not new functionality.

**3. Make all migrations idempotent.**
All 12 up-migrations (`migrations/0001`-`0012`) converted:
- `CREATE TABLE` → `CREATE TABLE IF NOT EXISTS` (36 occurrences, `0004` alone)
- `CREATE INDEX` → `CREATE INDEX IF NOT EXISTS` (56 occurrences)
- Every `CREATE POLICY` (24 occurrences across `0001`, `0002`, `0005`-`0008`, `0010`-`0012`) preceded by a matching `DROP POLICY IF EXISTS` — Postgres has no native `IF NOT EXISTS` for policies
- The one `CREATE TRIGGER` (`0001`) preceded by `DROP TRIGGER IF EXISTS`
- The `roles` seed `INSERT` (`0001`) given `ON CONFLICT (id) DO NOTHING`
- The one `ALTER TABLE ... ADD CONSTRAINT` (`0004`'s `fk_documents_current_version`, no native `IF NOT EXISTS` for constraints) wrapped in a `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint ...) ... $$` guard
- `GRANT`/`REVOKE`, `CREATE EXTENSION IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`, `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, and the one same-type `ALTER COLUMN TYPE` were already idempotent — left unchanged

Full before/after reference: `docs/MIGRATION_VERIFICATION_GUIDE.md` §1. This directly closes the failure mode `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md` hypothesized caused the original incident (a partial run aborting on "policy already exists," permanently short of the trailing `GRANT` line on every subsequent naive re-run).

**4. Add/document required `SUPABASE_SERVICE_ROLE_KEY` usage.**
- `render.yaml`: added as a declared `sync: false` placeholder with an inline comment explaining the dependency (`identity_admin.py::provision_user()`, called by `POST /companies`/`POST /users`) and where to find the real value.
- `docs/DEPLOYMENT.md`: added to the required-secrets list (§1) and deployment checklist (§3), explicitly correcting the prior "CLI-only" framing.
- `.env.example`: moved into the "Required" section with an explanation; the old "CLI-only" section retains a correction note rather than being silently rewritten.
- `DEPLOYMENT_REVIEW.md` (a dated, historical audit document from 2026-07-21): **not silently edited** — a dated correction blockquote was added at the top instead, preserving the original record's integrity while flagging the three places its "not needed by the web app" claim is now stale. This matches how a GxP-adjacent codebase's prior audit trail should be handled — corrections, not retroactive rewrites.

**5. Update deployment docs and render configuration guidance.**
Done as part of #4, plus two new documents (#6). No live Render or Supabase access was used or claimed — every change is a file on disk in this repository.

**6. Create a deployment runbook and migration verification guide.**
- `docs/DEPLOYMENT_RUNBOOK.md` — 7 stages (commit/push → confirm deploy → migrations → env var → live verification → rollback → sign-off), each with exact commands/SQL and explicit checkboxes. Supersedes Phase F.1's `docs/PRODUCTION_RELEASE_CHECKLIST.md` as the execution-ready version (that document remains as the original audit's checklist; the runbook is the "how," building on it).
- `docs/MIGRATION_VERIFICATION_GUIDE.md` — what changed for idempotency and why, plus copy-paste `information_schema`/`pg_policies`/`pg_constraint` queries to check any specific migration's live state before or after running it.

**7. Add automated tests covering Company Administration, tenant isolation, and Assume Company Context.**
Two new test files, 19 tests, all passing:
- `tests/test_companies.py` (11 tests) — `routes/companies.py` had **zero** direct test coverage before this phase. Covers: list (super_admin 200 / company_admin 403 / user 403), create (success + audit entry, missing `legal_name`, invalid `industry_segment`, non-super-admin 403, provisioning-failure response shape), suspend/reactivate (success + audit entries, 404 on unknown id, non-super-admin 403).
- `tests/test_user_invite_and_list.py` (8 tests) — `GET /users` and `POST /users` had no direct coverage before this phase (only `PATCH` was covered, in `tests/test_role_management.py`). Covers: company-scoped list, Super-Admin-without-assumed-context 403, assumed-Super-Admin company-scoped list (tenant isolation — a second company's user is confirmed absent from the result), invite success + corrected audit entry, invalid `role_id`, missing required fields, Super-Admin-without-assumed-context 403 on invite, provisioning-failure error passthrough.

Assume Company Context itself already had dedicated coverage (`tests/test_assume_company_context.py`, pre-existing, unmodified) — not duplicated here.

**Caveat carried forward from Phase F.1, unchanged by this phase:** every test above mocks the Supabase client. They prove the application logic is internally correct; they do not and cannot prove the live Postgres grants/RLS are active, or that live cross-tenant isolation holds — that remains genuinely unverifiable without live database access (see `docs/FINAL_RELEASE_EVIDENCE/MANUAL_VERIFICATION_CHECKLIST.md`).

**8. Keep all existing tests passing.**
Confirmed — see Tests Passed below.

---

## Files Changed

121 files in one commit (`559d14c`, local `main`, not pushed), +9414/-517 lines. By category:

| Category | Count | Examples |
|---|---|---|
| Migrations made idempotent | 8 files edited | `migrations/0001`, `0002`, `0004`-`0008` `_up.sql` |
| Migrations newly committed (already idempotent per above) | 6 files (3 up + 3 down) | `migrations/0010`-`0012` |
| Application code (new) | 4 files | `pharmagpt/routes/companies.py`, `routes/users.py`, `services/identity_admin.py`, `pharmagpt/audit.py` |
| Application code (bug fix) | 1 file | `pharmagpt/routes/users.py` (audit `record_id` key fix) |
| Application code (pre-existing Phase F changes, now committed) | ~30 files | `auth/decorators.py`, `auth/middleware.py`, `database.py`, `routes/qual.py`, `routes/report.py`, `routes/risk.py`, etc. |
| Frontend (new) | 11 files | `admin_companies.js`, `admin_users.js`, `admin_assume_context.js`, `error_pages.js`, `header.js`, `notifications.js`, etc. + 4 CSS |
| Frontend (pre-existing Phase F changes) | ~20 files | `dashboard.js`, `knowledge_base.js`, `equipment.js`, `templates/index.html`, etc. |
| Config/docs (Phase F.2-specific) | 8 files | `render.yaml`, `.env.example`, `DEPLOYMENT_REVIEW.md`, `docs/DEPLOYMENT.md`, `docs/DEPLOYMENT_RUNBOOK.md` (new), `docs/MIGRATION_VERIFICATION_GUIDE.md` (new) |
| Docs (Phase F.1 evidence, now committed) | ~20 files | `docs/FINAL_DATABASE_ROOT_CAUSE.md`, `docs/DEPLOYMENT_VERIFICATION.md`, `docs/PRODUCTION_RELEASE_CHECKLIST.md`, `docs/FINAL_RELEASE_EVIDENCE/*`, `PHARMAGPT_v1.0_FINAL_RELEASE_CERTIFICATION.md`, and earlier Phase E/F report markdown files |
| Tests (new, Phase F.2) | 2 files | `tests/test_companies.py`, `tests/test_user_invite_and_list.py` |
| Tests (pre-existing Phase F, now committed) | 5 files | `tests/test_assume_company_context.py`, `test_phase_f_compliance.py`, `test_risk_generate_endpoint.py`, `test_role_management.py`, `test_security_super_admin_guard.py` |

Full authoritative list: `git show --stat 559d14c`.

## Tests Passed

```
$ python -m pytest -q
533 passed, 1 deselected, 25 warnings in 266.22s (0:04:26)
```

514 pre-existing baseline + 19 new (`test_companies.py`: 11, `test_user_invite_and_list.py`: 8). **0 failed.** One transient error was observed on an earlier full-suite run (`test_security_tenant_rbac_esig.py::test_cross_tenant_cannot_read_another_companys_deviation`) that did not reproduce in isolation or on a clean re-run immediately after — treated as pre-existing test-order flakiness, not a regression introduced by this phase's changes (that specific test file and test were not touched by this phase).

All tests mock the Supabase/Postgres client — see the caveat under Objective 7 above and in `docs/FINAL_RELEASE_EVIDENCE/TEST_OUTPUT.md`. Passing tests are evidence of code correctness, not of live deployment or live database state.

## Remaining Manual Production Actions Only

Everything below requires human access this session does not have (live Supabase SQL Editor, live Render dashboard, a real Supabase `service_role` secret, and a real authenticated browser session) and was **not performed or claimed as performed** in this phase. Full detail and exact commands: `docs/DEPLOYMENT_RUNBOOK.md`.

1. **Push `559d14c` to `origin/main`** (or open/merge a PR) — this commit exists only in the local working tree used by this session; nothing has been pushed.
2. **Confirm Render's auto-deploy** picks up the new commit and reaches "Live" — `/health` should return 200.
3. **Run `migrations/0010`, `0011`, `0012` (in order) in the Supabase SQL Editor** against the live project — now idempotent, safe to run regardless of any prior partial state.
4. **Re-verify migration `0009`'s grants are active** on `audit_trail` and related tables (never independently confirmed live).
5. **Add `SUPABASE_SERVICE_ROLE_KEY`** to the Render service's environment variables in the dashboard (declared as a placeholder in `render.yaml`; the real secret value must still be entered by hand from Supabase Project Settings → API).
6. **Run the full live verification pass** (`docs/DEPLOYMENT_RUNBOOK.md` Stage 5 / `docs/FINAL_RELEASE_EVIDENCE/MANUAL_VERIFICATION_CHECKLIST.md`) — including the two-company cross-tenant isolation test that has never once been performed against a real database in this project's history. This is the actual GO gate; do not treat steps 1-5 as sufficient without it.
7. **Only after step 6 passes in full:** update the release certification with a dated addendum (do not edit the existing NO-GO verdict in place — append, per the same audit-trail-preservation discipline used for `DEPLOYMENT_REVIEW.md` in this phase).

No code, migration content, or test logic changes remain outstanding from this phase's scope — everything left is the operational sequence above.

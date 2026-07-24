# PharmaGPT v1.0 — Final Release Certification
## Phase F.1 — Operational Validation & Final Certification

**Date:** 2026-07-24
**Prepared as:** FDA Computer System Validation Lead / GAMP 5 2nd Edition Expert / 21 CFR Part 11 Auditor / EU GMP Annex 11 Consultant / Senior PostgreSQL Administrator / Supabase Database Architect / Release Manager
**Scope:** Fresh, independent re-audit of the single remaining Critical finding carried from Phase F (Company Administration / Assume Company Context), plus a full readiness re-score based on current evidence. Prior conclusions (Phase E, Phase F) are treated as claims to re-verify, not as settled fact — several are corrected below.

---

## 1. Executive Summary

The Phase F brief this session was issued under states one remaining Critical finding — "Company Administration / Assume Company Context fails because required PostgreSQL GRANT permissions are not active in the live Supabase database" — framed as a narrow, likely five-minute operational fix on top of application code that already **PASS**es.

**Independent re-investigation in this session found the situation is materially different and more serious than that framing.** The missing GRANTs are real and confirmed (§4), but they are the *smaller* of two independent blockers. The larger one, not previously documented anywhere in this repository's history: **the entire Company Administration feature — its routes, its migrations, and every other Phase F fix — exists only in an uncommitted local working tree and has never been deployed to the production Render service.** `git show HEAD:pharmagpt/routes/companies.py` fails; the file does not exist in the commit Render builds from. A third, independently discovered gap compounds both: the production environment is missing a secret (`SUPABASE_SERVICE_ROLE_KEY`) that two of the feature's core write paths require, and current deployment documentation incorrectly asserts this secret isn't needed by the web app.

None of this reflects new code defects — the application logic, read directly in this session, is well-designed and correctly scoped. It reflects that "Application Code: PASS" and "one operational fix remaining" understated what closing this blocker actually requires: a code review and deploy of a large, never-reviewed diff, a manual (non-idempotent, untracked) SQL migration run, a new production secret, and — critically — a live two-company isolation test that has **never once been performed** against a real database, at any point in this project's history.

**Verdict: NO-GO.** Full reasoning in §10.

## 2. Previous Phase F Status

Per `pharmagpt_phase_f_compliance_hardening` memory and `docs/PHASE_F_FINDING_TRACEABILITY.md`: Phase F fixed 6 of 7 Critical findings (audit-trail coverage/schema, IQ→OQ→PQ sequencing, unguarded endpoints, identity spoofing, terminal-state immutability) with automated-test evidence, raising readiness from 52% to a claimed 80%. The 7th Critical (A1/C1, this Company Administration finding) was explicitly left NOT VERIFIED, correctly, as an operational item outside a coding session's ability to close. Regression baseline at Phase F's end: 514 passed, 0 failed.

## 3. Remaining Blocker

As stated in the Phase F.1 brief: Company Administration → "Assume Company Context." Re-scoped by this session's investigation into three independently blocking parts — see §4.

## 4. Root Cause

Full detail: [`docs/FINAL_DATABASE_ROOT_CAUSE.md`](docs/FINAL_DATABASE_ROOT_CAUSE.md), [`docs/DEPLOYMENT_VERIFICATION.md`](docs/DEPLOYMENT_VERIFICATION.md). Summary:

1. **Not deployed.** `origin/main` HEAD (`7a98428`, 2026-07-23) predates Phase 3.5 entirely. `routes/companies.py`, `routes/users.py`, `services/identity_admin.py`, `pharmagpt/audit.py`, migrations `0010`-`0012`, and 48 other Phase F-modified files exist only in the local working tree (`git status --porcelain=v1 -uall`). Render deploys from git; nothing described in this certification is running in production.
2. **Grants not active.** Independently confirmed live on 2026-07-23 (`ENTERPRISE_ACCEPTANCE_TEST_REPORT.md`, three reproductions): Postgres error `42501` on `companies`/`users`/`break_glass_access`, with the error's own hint naming the exact `GRANT` line each migration file already contains. Not re-tested live this session (no DB access) but the evidence is specific, reproducible, and uncontradicted.
3. **Missing production secret.** `SUPABASE_SERVICE_ROLE_KEY`, required by `identity_admin.py::provision_user()` (used by both company creation and user invitation), is declared nowhere in `render.yaml` and is documented elsewhere (`.env.example`, `DEPLOYMENT_REVIEW.md`) as unneeded by the web app — true when written, stale now that `identity_admin.py` exists as a live HTTP-reachable path.

All three are operational/deployment gaps, not application-code defects.

## 5. Evidence Reviewed

- Direct reads: `render.yaml`, all 12 `migrations/*.sql` up/down pairs, `pharmagpt/services/supabase_client.py`, `services/identity_admin.py`, `routes/companies.py`, `routes/users.py`, `routes/auth.py` (assume-company section), `auth/middleware.py` (assume-context resolution), `.env.example`, `docs/DATABASE.md`, `DEPLOYMENT_REVIEW.md`.
- `git` ground truth: `git status`, `git log`, `git show HEAD:<path>`, `git ls-files`, `git check-ignore`, `git diff --stat` — see [`docs/FINAL_RELEASE_EVIDENCE/GIT_AND_MIGRATION_EVIDENCE.md`](docs/FINAL_RELEASE_EVIDENCE/GIT_AND_MIGRATION_EVIDENCE.md) for raw output.
- Live test evidence cited (not re-run, no DB access): `ENTERPRISE_ACCEPTANCE_TEST_REPORT.md` (2026-07-23), cross-checked line-by-line against the migration files it quotes — accurate.
- Phase F's own evidence documents (`docs/MULTI_TENANT_SECURITY_REPORT.md`, `docs/AUDIT_TRAIL_COVERAGE_REPORT.md`, `docs/PHASE_F_FINDING_TRACEABILITY.md`) — spot-checked against the source files they cite (`companies.py`, `users.py`, `qms_repo.py`) and found accurate; treated as supporting evidence, not re-derived from scratch line-by-line for every one of the ~15 domain files they cover (disclosed here as this certification's own evidentiary limit).
- Full and targeted regression suites, run live this session — see [`docs/FINAL_RELEASE_EVIDENCE/TEST_OUTPUT.md`](docs/FINAL_RELEASE_EVIDENCE/TEST_OUTPUT.md).

## 6. What Was Independently Verified

- **514 passed, 0 failed** on the full suite, re-run live this session (`239.31s`) — matches the claimed baseline exactly.
- **128 passed, 0 failed** on a targeted subset (Company Administration, Auth, RBAC, Tenant Isolation, Audit Trail — 9 test files), re-run live this session (`55.36s`). No regression introduced by anything currently in the working tree.
- **Migrations 0010-0012 are untracked in git** (`git ls-files` returns empty for all three), not `.gitignore`-excluded, simply never `git add`ed.
- **`routes/companies.py`, `routes/users.py`, `services/identity_admin.py`, `pharmagpt/audit.py` do not exist in `origin/main` HEAD** (`git show HEAD:<path>` fails for each).
- **`SUPABASE_SERVICE_ROLE_KEY` is absent from `render.yaml`'s `envVars` block** while being a hard runtime dependency of `identity_admin.py`.
- **The RLS policy SQL in `migrations/0010`-`0012`, read directly, is logically correct** — scoped to "own grants only" (break-glass), "read own company only" (company_admin on companies), "read/update own company's roster only" (company_admin on users), with no cross-company clause found.
- **No migration runner, CI/CD pipeline, or migration-tracking table exists** in this codebase — migrations are executed by manually pasting SQL into the Supabase SQL Editor, with no record of what has been run.
- **A previously undocumented Low-severity bug**: `routes/users.py:134`'s `_audit_best_effort` call reads `provisioned.get("user_id", ...)`, a key that does not exist in `provision_user()`'s return value, so "User invited" audit entries always log the email instead of the actual user id in that one field.

## 7. What Could NOT Be Verified

All marked **NOT VERIFIED** — see [`docs/FINAL_RELEASE_EVIDENCE/MANUAL_VERIFICATION_CHECKLIST.md`](docs/FINAL_RELEASE_EVIDENCE/MANUAL_VERIFICATION_CHECKLIST.md) for exact SQL/HTTP steps for each:

- Live functioning of `GET /auth/companies`, `POST /auth/assume-company`, `GET /auth/me`, `POST /auth/end-assume-company` against the real Supabase project (requires live DB access this session does not have).
- Live two-company cross-tenant isolation for Company Administration / User Management — **this has never been tested against a real database at any point in this project's documented history**, because the feature has always failed closed (100% of requests erroring identically regardless of target company) whenever it was live-tested.
- Whether migration `0009`'s grants (covering `audit_trail`, among others) are currently active — if not, Postgres-side audit logging for the very admin actions this certification is about will silently no-op (the code wraps this in a bare `except Exception`, by design, anticipating exactly this risk).
- Whether the deployed Render service's environment currently has (or lacks) `SUPABASE_SERVICE_ROLE_KEY` set outside `render.yaml` (a `sync: false` var could theoretically already be set manually in the dashboard — this session cannot see the dashboard).
- Any live authenticated browser walkthrough of admin flows — blocked by this environment's standing rule against entering any credential into any field, applying even to test/dev accounts.

## 8. Operational Actions Required

Full detail and exact commands: [`docs/PRODUCTION_RELEASE_CHECKLIST.md`](docs/PRODUCTION_RELEASE_CHECKLIST.md). Summary, in required order:

1. **Code review and merge** the current uncommitted working tree (48 modified + ~35 new files) into `main`, then push — this is a substantive review, not a formality, since none of it has been through any review process yet.
2. **Deploy** (Render auto-deploys from `origin/main`; confirm the new commit is live via `/health` and a version/commit check).
3. **Run migrations 0010, 0011, 0012** in the Supabase SQL Editor, after first querying `pg_policies`/`information_schema.role_table_grants` to check for partial prior application (the `up.sql` files are not idempotent).
4. **Add `SUPABASE_SERVICE_ROLE_KEY`** to the Render service's environment variables (dashboard, not `render.yaml`).
5. **Re-verify migration 0009's grants** on `audit_trail` and related tables — not previously confirmed live.
6. **Execute the full live verification checklist** (§7 above / `MANUAL_VERIFICATION_CHECKLIST.md`), including the two-company isolation test, with a real second company account.
7. **Update stale documentation** (`.env.example`, `DEPLOYMENT_REVIEW.md`) regarding `SUPABASE_SERVICE_ROLE_KEY`'s web-app dependency.

## 9. Final Readiness Score

Independent scoring by category, based only on evidence gathered in this session (§5-§7), not carried forward from Phase F's 80%:

| Category | Score | Basis |
|---|---|---|
| Architecture | 85% | Tenancy/RLS design is sound (frozen 4-role model, non-nullable break-glass reason/expiry, default-deny-until-policy pattern); no automated migration framework is a real gap for a regulated system |
| Validation | 75% | Strong automated test evidence (514/0, re-confirmed live) for logic correctness; validation-as-deployed is not demonstrated because nothing is deployed |
| Compliance (21 CFR Part 11 / Annex 11) | 65% | Audit-trail design and break-glass control model are compliant in intent; best-effort/silently-swallowed audit writes on exactly the actions this feature is about, plus zero live verification, are real gaps against Part 11 record-integrity expectations |
| Security | 70% | RBAC/tenancy code correctly written and tested; missing production secret and never-tested live isolation mean "secure" is not yet a demonstrated fact for this feature |
| Database | 55% | Schema/RLS logic is correct; zero migration tracking, non-idempotent scripts, and the actual blocking grant gap live here |
| Audit Trail | 65% | Design and SQLite-side wiring well-evidenced (Phase F, spot-checked); Postgres-side admin-route audit trail unverified live and has one disclosed field-mapping bug |
| Workflow | 85% | IQ→OQ→PQ and Validation Report gates verified by passing automated tests with documented, defensible scoping decisions |
| RBAC | 80% | Guards correctly implemented and tested; not live-verified for the new admin routes specifically |
| Multi-tenancy | 60% | Pre-existing SQLite-domain isolation well-evidenced; the new Postgres-backed admin surface is entirely unverified live and, more fundamentally, undeployed |
| Operational Readiness | 25% | No CI/CD, fully manual/untracked migration process, an undeployed feature, a missing required secret, and no documented live rollback drill |
| Commercial Readiness | 40% | The specific feature this release gate is about — enterprise Company Administration — cannot be used in production today; the rest of the product's evidenced functionality is commercially reasonable |

**Overall Readiness Score: 64%** (unweighted average across the 11 categories above).

### Finding counts (this session's independent audit)

| Severity | Count | Findings |
|---|---|---|
| **Critical** | 3 | C1: Company Administration feature (routes, migrations, audit helper) uncommitted and undeployed to production. C2: Postgres GRANT/RLS for `companies`/`users`/`break_glass_access` not active in live Supabase (evidenced, not independently re-tested live this session). C3: `SUPABASE_SERVICE_ROLE_KEY` not configured/declared for the production web service — blocks company creation and user invitation even after C1/C2 are resolved. |
| **High** | 4 | H1: Live cross-tenant isolation for the new admin routes has never been positively verified (only "broken closed" observed). H2: Migration 0009's grants (incl. `audit_trail`) not independently re-verified live — if inactive, admin-action audit logging silently no-ops. H3: CAPA/Change Control still lack a full lifecycle-transition graph beyond terminal-state immutability (carried from Phase F, H7). H4: No migration-tracking mechanism or idempotency guard for Postgres schema changes — contributed directly to this incident and remains a standing risk for any future migration. |
| **Medium** | 5 | M1: Raw Postgres/Gemini exception text leaks to the client on some error paths (carried, A4). M2: `routes/users.py` 403-wording inconsistency (carried, A5, cosmetic). M3: No admin-facing viewer for historical break-glass grants (carried, A6, product gap). M4: Lifecycle vocabularies (QMS Document, URS) missing a distinct "Archived" state (carried, Phase F traceability M2). M5: `.env.example`/`DEPLOYMENT_REVIEW.md` documentation is stale regarding `SUPABASE_SERVICE_ROLE_KEY`'s web-app dependency (new, this session). |
| **Low** | 2 | L1: `review_engine.py`'s `_score_cache` is a process-global, non-tenant-scoped dashboard statistic (disclosed, not fixed, Phase F WP5). L2: `routes/users.py:134` audit call reads a non-existent `provisioned["user_id"]` key, always logging email instead of user id for "User invited" audit entries (new, this session). |

Six additional items (Phase E's H1-H6: DQ/FAT/SAT schema linkage, dead prompt modules, `risk_database.py` connection leak, synchronous AI-generation performance, no per-request auth-resolution caching, SQLite→Postgres cutover soak) remain open, out-of-scope residual risks per Phase F's explicit "no new features/no optimization" boundary — not re-scored here, tracked in `docs/PHASE_F_FINDING_TRACEABILITY.md`.

This is lower than Phase F's claimed 80%, not because any code regressed, but because this session scored **Operational Readiness** and **Commercial Readiness** as first-class categories reflecting what is actually running in production today, which the prior 80% figure did not weight as heavily — and because this session found the blocker is three compounding gaps, not one.

## 10. Release Recommendation

# NO-GO

**Reasoning:** The brief's own most important rule is that this certification's credibility outweighs achieving a GO verdict. Three facts make GO or "GO WITH OPERATIONAL ACTIONS" unsupportable right now:

1. The remaining work is not a narrow, low-risk operational checklist — it starts with reviewing and merging a large, never-reviewed diff (48 modified + ~35 new files) into production, which carries its own real risk independent of the database issue.
2. The database fix itself carries a documented risk of a partial-failure loop (non-idempotent `CREATE POLICY` statements, no tracking of what's already applied) that this exact incident may already be an instance of.
3. Most importantly: **cross-tenant isolation for this feature has never been verified against a real database, at any point in this project's history.** Every prior live test found the feature failing closed for every account, so isolation was never actually exercised — only assumed safe by "broken means safe." Calling this "GO WITH OPERATIONAL ACTIONS" would mean certifying a compliance-sensitive multi-tenant admin feature as ready before its core safety property has ever once been positively demonstrated, which this certification is not willing to do on inference alone.

**Path to GO:** complete `docs/PRODUCTION_RELEASE_CHECKLIST.md` in full, including the live two-company isolation test in `docs/FINAL_RELEASE_EVIDENCE/MANUAL_VERIFICATION_CHECKLIST.md` §3/§6, and re-run this certification's Work Package 4 with real, positive (not "broken closed") evidence. If that pass succeeds with no new Critical/High findings, the recommendation would change to **GO**. Do not skip directly to GO on the assumption the checklist will succeed — re-certify after, not instead of, running it.

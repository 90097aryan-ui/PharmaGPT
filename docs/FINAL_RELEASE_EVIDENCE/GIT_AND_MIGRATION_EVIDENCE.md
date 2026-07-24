# Git and Migration Evidence — Phase F.1

Raw command output backing the root-cause finding in `docs/FINAL_DATABASE_ROOT_CAUSE.md`. All commands run live in this session, 2026-07-24, in `D:\PharmaAgent`.

## Deployed commit

```
$ git log -1 --format="%H %cd" origin/main
7a98428fb8a074ea8f9da6c3e1fb3d9690e793be Thu Jul 23 10:33:14 2026 +0530

$ git log --oneline -3
7a98428 Phase 3: Shared Validation Engine, Document Lifecycle, Traceability and Knowledge Base Versioning
cdcc48e Phase 2: Navigation, Equipment Library, Knowledge Base integration, RBAC hardening
64ffd21 Phase 1: Security hardening, Generate Document consolidation, documentation sync
```

## Company Administration code is not in the deployed commit

```
$ git show HEAD:pharmagpt/routes/companies.py
fatal: path 'pharmagpt/routes/companies.py' does not exist in 'HEAD'

$ git show HEAD:pharmagpt/routes/users.py
fatal: path 'pharmagpt/routes/users.py' does not exist in 'HEAD'

$ git show HEAD:pharmagpt/audit.py
fatal: path 'pharmagpt/audit.py' does not exist in 'HEAD'

$ git show HEAD:migrations/0009_phase3_grants_up.sql
[succeeds — 0009 predates Phase 3.5 and is committed]
```

## Migrations 0010-0012 are untracked (never committed)

```
$ git ls-files migrations/0010_break_glass_rls_up.sql migrations/0011_companies_admin_rls_up.sql migrations/0012_users_company_admin_rls_up.sql
[empty output — none of the three are tracked by git]

$ git status --porcelain=v1 -uall | grep migrations
?? migrations/0010_break_glass_rls_down.sql
?? migrations/0010_break_glass_rls_up.sql
?? migrations/0011_companies_admin_rls_down.sql
?? migrations/0011_companies_admin_rls_up.sql
?? migrations/0012_users_company_admin_rls_down.sql
?? migrations/0012_users_company_admin_rls_up.sql
```

Not a `.gitignore` exclusion — confirmed:

```
$ git check-ignore -v migrations/0010_break_glass_rls_up.sql pharmagpt/audit.py pharmagpt/routes/companies.py
[empty output — none are ignored; they were simply never `git add`ed]
```

## Full scope of uncommitted work

48 tracked files modified (`git diff --stat`, +2292/-408 lines across `pharmagpt/app.py`, `auth/decorators.py`, `auth/middleware.py`, `database.py`, `routes/auth.py`, `routes/qual.py`, `routes/report.py`, `routes/risk.py`, and 12 more) plus ~35 new untracked files (`pharmagpt/routes/companies.py`, `routes/users.py`, `services/identity_admin.py`, `pharmagpt/audit.py`, 6 migration files, 5 new test files, 8 new JS/CSS files, and this Phase F/F.1 documentation set itself). Full listing reproducible via `git status --porcelain=v1 -uall` in the repo root.

## No CI/CD pipeline exists

```
$ ls .github/workflows
ls: cannot access '.github/workflows': No such file or directory

$ find . -maxdepth 2 -iname "*.yml" -o -iname "*.yaml"
./render.yaml
```

Confirms deploys are Render's standard git-push-triggered auto-deploy from `origin/main`, with no intermediate CI gate.

## No migration runner or tracking table

```
$ grep -rn "migrations/0010\|migration.*runner\|def run_migrations\|apply_migrations" --include=*.py .
[no automated runner found — only human-authored comments in application code
 referencing migration filenames for documentation purposes]
```

`docs/DATABASE.md:163`: *"There is no migration framework in v0.6. Schema changes require [manual SQL Editor execution]... A migration framework (e.g. Flask-Migrate / Alembic) is planned for v1.0."*

## SUPABASE_SERVICE_ROLE_KEY not declared for the web service

```
$ grep -n "key:" render.yaml
      - key: DB_PATH
      - key: UPLOAD_FOLDER
      - key: GENERATED_DOCS_PATH
      - key: GEMINI_API_KEY
      - key: FLASK_SECRET_KEY
      - key: FLASK_DEBUG
      - key: SUPABASE_URL
      - key: SUPABASE_ANON_KEY
[SUPABASE_SERVICE_ROLE_KEY absent]

$ grep -n "SUPABASE_SERVICE_ROLE_KEY" pharmagpt/services/identity_admin.py pharmagpt/services/supabase_client.py
pharmagpt/services/supabase_client.py:73:    return create_client(_require_env("SUPABASE_URL"), _require_env("SUPABASE_SERVICE_ROLE_KEY"))
```

`identity_admin.py::provision_user()` calls `get_service_role_client()`; both `routes/companies.py::create_company()` and `routes/users.py::invite_user()` call `provision_user()`.

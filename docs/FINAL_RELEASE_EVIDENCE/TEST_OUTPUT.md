# Test Output Evidence — Phase F.1

Both runs executed live in this session (2026-07-24), against the current working tree (including all uncommitted Phase F changes — this is testing the code as it exists on disk, not what's deployed; see `docs/FINAL_DATABASE_ROOT_CAUSE.md` for the deployed-vs-local distinction).

## Full regression suite

```
$ python -m pytest -q
........................................................................ [ 14%]
........................................................................ [ 28%]
........................................................................ [ 42%]
........................................................................ [ 56%]
........................................................................ [ 70%]
........................................................................ [ 84%]
........................................................................ [ 98%]
..........                                                               [100%]
514 passed, 1 deselected, 25 warnings in 239.31s (0:03:59)
```

Matches the brief's stated baseline (514 passed, 0 failed) exactly, independently re-run.

## Targeted regression — Company Administration, Authentication, RBAC, Tenant Isolation, Audit Trail

Files selected: `test_assume_company_context.py`, `test_role_management.py`, `test_security_super_admin_guard.py`, `test_security_tenant_rbac_esig.py`, `test_auth_context.py`, `test_auth_decorators.py`, `test_routes_auth.py`, `test_app_auth_integration.py`, `test_phase_f_compliance.py`, `test_urs_audit_logging.py`.

```
$ python -m pytest -q tests/test_assume_company_context.py tests/test_role_management.py \
    tests/test_security_super_admin_guard.py tests/test_security_tenant_rbac_esig.py \
    tests/test_auth_context.py tests/test_auth_decorators.py tests/test_routes_auth.py \
    tests/test_app_auth_integration.py tests/test_phase_f_compliance.py tests/test_urs_audit_logging.py
........................................................................ [ 56%]
........................................................                 [100%]
128 passed, 5 warnings in 55.36s
```

**No regression introduced** — 0 failures in either run.

## Important caveat on what this evidence does and does not prove

Every test above runs against a **mocked** Supabase/Postgres client (confirmed by inspecting `tests/test_assume_company_context.py`, `tests/test_role_management.py` — both patch `resolve_tenant_context` and/or the Supabase client rather than hitting a real database). This means:

- **Proves:** the application logic (RBAC checks, request scoping, non-spoofable identity, audit-call wiring, sequencing gates) is internally correct given the mocked client's behavior.
- **Does not prove:** that the real, live Supabase database will behave as the mock assumes — specifically, it cannot and does not catch the actual production blocker (missing GRANTs), because the mock never exercises Postgres's actual permission system. This is the same limitation flagged in the Phase E audit and reconfirmed here, not a new gap — but it bears repeating precisely because "514 passed, 0 failed" can otherwise be misread as clearing the database-grant issue. It does not.

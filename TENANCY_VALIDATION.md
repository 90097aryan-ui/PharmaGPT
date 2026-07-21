# Multi-Tenancy Validation

**Scope:** Static/code-level validation of company_id isolation across the Phase 3.1–3.5 Postgres schema and the four dual-write domains (Projects, Knowledge Base, Equipment, QMS/Risk). Performed 2026-07-21 as part of the SQLite-elimination readiness pass.

**Not performed in this session, and explicitly out of scope for a static review:** the live 2-company RLS isolation spot-check. Both `docs/PHASE3_EXECUTION_PLAN.md` (§3.4 success criteria: *"live Staging RLS isolation check is a deployment-time step, not verifiable from here"*) and `docs/PHASE3_FLAGS.md` already concluded this requires two real company accounts exercising the live app against a deployed Staging environment — it cannot be faked from a repo checkout, and this session did not create test companies/data against the real Supabase project on file in `.env` in order to avoid writing test data into what may be a shared/production-adjacent database without explicit authorization. **This remains an outstanding operational step before any `*_BACKEND` flag moves past `dual`.**

## 1. Schema-level company_id coverage

Every table introduced in `migrations/0004_core_schema_up.sql` for the Phase 3 target schema carries a `company_id uuid not null references companies(id)` column plus a supporting index (`idx_<table>_company_id`, several with composite indexes for common filter+status queries). Verified by direct grep of the migration — no table in the Phase 3.2–3.5 scope (`projects`, `project_members`, `documents`, `document_versions`, `document_categories`, `tags`, `document_tags`, `document_references`, `equipment`, `equipment_links`, `deviations`, `capas`, `change_controls`, `risk_assessments`, `audit_trail`) is missing it.

Two tables (`permissions`, `role_permissions`, `plans`) are intentionally company-agnostic (global reference data) — RLS is enabled on them with no policy yet (default-deny), which is the documented-correct posture, not a gap.

## 2. RLS policy coverage

All 15 Phase 3.2–3.5 tables have RLS enabled (`migrations/0004_core_schema_up.sql` lines 504–518) and a matching `..._company_scoped` policy (`migrations/0005`–`0008_*_rls_up.sql`), all following one consistent pattern via a shared `current_company_id()` helper (`security definer`, locked `search_path`, resolves `auth.uid() → users.company_id`):

```sql
using (company_id = current_company_id())
with check (company_id = current_company_id())
```

`audit_trail` deliberately narrows this further to separate INSERT/SELECT-only policies (no UPDATE/DELETE for any role) — correct for an append-only audit table per `DATABASE_ARCHITECTURE.md` §9.2.

**Grants:** `migrations/0009_phase3_grants_up.sql` confirms a real bug was found and fixed during a prior validation pass — RLS policies existed with no paired table-level `GRANT`, which Postgres treats as a separate, earlier-stage check (a policy with no grant just means every query 42501s, not an isolation gap, but it does mean this was caught and closed, not missed).

**No table in the 3.2–3.5 scope has RLS disabled or a missing policy.**

## 3. Application-layer isolation (defense in depth)

Checked every domain repo (`pharmagpt/db/{projects,kb,equipment,qms}_repo.py`) and every route calling them (`pharmagpt/routes/{projects,knowledge_base,equipment,qms_deviations,qms_capa,qms_change_control,risk}.py`):

- **No repo ever uses the service-role client for a live request.** All four repos import and exclusively call `get_authenticated_client(access_token)` (`pharmagpt/services/supabase_client.py`), which authenticates PostgREST as the requesting user so RLS evaluates under `auth.uid()`. The service-role key (which has `BYPASSRLS`) is only ever used offline, in `scripts/backfill_*.py` / `scripts/check_*_parity.py` — never in a code path a live HTTP request can reach.
- **`company_id` is never accepted from the client.** Every route resolves `tenant.company_id` from `TenantContext` (`pharmagpt/auth/context.py::resolve_tenant_context`), which derives it server-side from the verified Supabase access token → `users.company_id`, under RLS, as that same user. No route reads a `company_id` from request JSON/query/form and passes it through to a write.
- Every write route additionally guards `if not tenant.company_id:` before calling into a repo (blocks super_admin, who has `company_id = None` by design, from writing tenant data through these paths).

This gives two independent layers: even if application code had a bug and passed the wrong `company_id`, the database-level RLS policy would still reject a cross-company write/read, since it re-derives the caller's own company_id itself rather than trusting the value the app sent.

## 4. Findings

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Live 2-company RLS isolation spot-check not yet performed | Required-before-cutover | **Open — operational, deployment-time step, not fixable from this session** |
| 2 | Extended Staging soak (48h+) per flag not yet performed | Required-before-cutover | **Open — same as above** |
| 3 | Schema/RLS/grants for all 3.2–3.5 tables | — | **Verified clean, no gap found** |
| 4 | Application never bypasses RLS on the live request path | — | **Verified clean** |
| 5 | No route trusts a client-supplied company_id | — | **Verified clean** |

## 5. Conclusion

No cross-company leakage risk was found in the code or schema reviewed. The only remaining tenancy-validation work is operational (live soak + live 2-company spot-check against a deployed Staging environment), exactly as the project's own `PHASE3_EXECUTION_PLAN.md` already scoped it — this is unchanged and is **not** something a static repo review can close out. Do not flip any `*_BACKEND` flag past `dual`, and do not proceed to Phase 3.6 (SQLite retirement), until both are done and recorded in `docs/PHASE3_FLAGS.md`.

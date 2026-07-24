# Validation Evidence — Open Issues

Issues still open at the close of Phase F, in priority order.

1. **A1/C1 — Company Administration / Assume Company Context non-functional.** Requires re-running migrations 0010-0012 in full against the live Supabase project and confirming the trailing GRANT/CREATE POLICY statements actually take effect, then re-testing end-to-end. **This is an operational action; it cannot be closed by a code-only session.**
2. **H7 residual — CAPA/Change Control have no full lifecycle-transition graph**, only terminal-state immutability. Recommended: design and wire a `lifecycle_engine` transition map for both modules, grounded in their existing `_STATUS_MAP` action vocabularies, as a dedicated follow-up (not attempted here to avoid inventing unverified business rules).
3. **Postgres Users/Companies audit-write verification.** Code is correct and non-blocking; whether it lands rows in the live database depends on resolving #1 first.
4. **DQ/FAT/SAT schema linkage + dead prompt modules (H1/H2).** Out of Phase F scope; still open exactly as Phase E found them.
5. **Performance items (H3-H5): risk_database.py connection leak, synchronous AI-generation endpoints, uncached auth resolution.** Explicitly excluded from Phase F ("DO NOT OPTIMIZE CODE"); still open.
6. **SQLite→Postgres cutover soak + 2-company RLS spot-check (H6).** Operational, deployment-time work; still open.
7. **`_score_cache` cross-tenant statistic leak** (new finding this session, Low severity). Disclosed, not fixed — see `docs/MULTI_TENANT_SECURITY_REPORT.md` §7.
8. **Test-coverage gaps disclosed in `TEST_SUMMARY.md`:** PQ-specific sequencing test, 7-of-8 terminal-immutability modules, live credentialed click-through, live 2-company RLS spot-check.
9. **Cosmetic/minor items carried from Phase E, unchanged and out of scope:** raw exception leakage (A4), `routes/users.py` 403-wording inconsistency (A5), no break-glass audit-log viewer (A6).

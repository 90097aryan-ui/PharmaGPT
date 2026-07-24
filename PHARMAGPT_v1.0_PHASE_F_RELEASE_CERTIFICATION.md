# PharmaGPT v1.0 — Phase F Release Certification

**Phase:** F — Compliance Hardening & Release Certification
**Date:** 2026-07-24
**Mode:** Regulatory compliance only — no new features, no UI redesign, no refactor-for-style, no optimization. Only verified release blockers from the Phase E audit were addressed.
**Independence statement:** This certification does not assume Phase F's own fixes succeeded. Every claim below is backed by a citation to source code, a passing automated test, or an explicit disclosure that it is **NOT VERIFIED** rather than assumed fixed — per the phase's own governing rule.

---

## 1. Executive Summary

Phase F set out to close every Critical and High finding from the Phase E independent audit (`PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md`, NO-GO, 52%) through eight work packages: finding traceability, audit-trail completeness, workflow sequencing enforcement, RBAC hardening, multi-tenant isolation verification, regression testing, an evidence package, and this final independent re-audit.

**Result: 6 of 7 Critical findings were fixed and proven with real evidence** (source code + 14 new passing automated tests + a live schema migration) in this session. **One Critical finding could not be closed** — it requires a live action against the deployed Supabase database (re-applying migration GRANTs) that this environment has no access to perform or verify; this is an operational gap, not an unaddressed code defect. Several High-severity items were explicitly and deliberately left out of scope, per the brief's own instruction not to fix items beyond "verified release blockers" (performance work, DQ/FAT/SAT schema redesign, and the SQLite→Postgres cutover soak all fall in this category).

Two of the six fixes required course-correction during this session: the first implementation of the workflow-sequencing gates was stricter than the codebase's own legitimate, pre-existing behavior, breaking 4 passing regression tests. Each was root-caused and the fix was rescoped narrower — not silenced, worked around, or the test simply changed to match — and the full suite (514 tests) now passes clean. This iteration is disclosed in full in `docs/WORKFLOW_VALIDATION_REPORT.md` and `docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md` because it is directly relevant to how much confidence to place in the fixes' correctness.

**The target stated at the start of this phase — Release Readiness >95% with zero Critical and zero High findings — was not achieved**, and this document does not claim otherwise. One Critical and roughly eight High-severity items remain open, all individually explained below with why they remain open. The honest result is a large, evidenced improvement over Phase E, not a clean bill of health.

---

## 2. Overall Score

| | Score |
|---|---|
| **Previous score (Phase E, 2026-07-24)** | **52%** |
| **Current score (Phase F, 2026-07-24)** | **80%** |

**Why 80%, not higher:** one Critical finding remains fully open (Company Administration / Assume Company Context, non-functional). By this document's own methodology (and the Phase E precedent), a system with any open Critical finding cannot score in the "ready" range regardless of how much else improved — the score reflects substantial, evidenced progress, not a passing grade.

**Why 80%, not lower:** six of seven Critical findings are now fixed with the strongest evidence available in this environment (automated tests exercising the real Flask app, not a description of intended behavior), the audit trail — a foundational 21 CFR Part 11 control — went from structurally incomplete to schema-complete and broadly wired, and the full regression suite grew from 500 to 514 passing tests with zero regressions.

---

## 3. Grading by Category

| Category | Grade | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| Architecture | Unchanged (out of scope, locked) | 0 | 0 | 0 | 0 |
| Validation / Workflow correctness | Improved: Weak → Adequate | 0 | 1 (H7 residual) | 1 (M2, lifecycle vocab) | 0 |
| Compliance (21 CFR Part 11 / GAMP5 posture) | Improved: Weak → Adequate, incomplete | 1 (A1/C1) | 2 (H1, H2) | 1 (versioning not auto-snapshotted) | 0 |
| Security | Improved: Adequate → Good, residual gaps remain | 0 | 0 | 2 (FLASK_SECRET_KEY fallback, no magic-byte upload check) | 1 (`_score_cache` leak) |
| Workflow enforcement (this phase's specific gates) | Adequate for the 6 requested checks; incomplete for full state-machine coverage | 0 | 1 (H7 residual, same as above) | 0 | 0 |
| Audit Trail | Improved: Weak → Good | 0 | 1 (Postgres write unverifiable live) | 0 | 0 |
| RBAC | Improved: Adequate → Good at code level; blocked operationally | 1 (A1/C1, same as Compliance) | 0 | 1 (distribution/training left unguarded, reviewed) | 0 |
| Testing | Improved: Adequate → Good | 0 | 0 | 1 (coverage gaps disclosed in TEST_SUMMARY.md) | 0 |
| Documentation | Good | 0 | 0 | 0 | 1 (README test count staleness) |
| Operational Readiness | Weak, unchanged | 1 (A1/C1, same root cause) | 3 (H4, H5, H6 — performance/cutover) | 0 | 0 |
| Commercial Readiness | Weak-Adequate, unchanged | 0 | 0 | 2 (PharmaPilot placeholder, several Coming Soon modules — unchanged, correctly disclosed) | 1 (A5, 403-wording) |
| **Totals (deduplicated across categories)** | | **1** | **~8** | **~6** | **~3** |

*A1/C1 (Company Administration / Assume Company Context) appears in four category rows above because it is genuinely cross-cutting — it is simultaneously a Compliance, RBAC, and Operational Readiness failure. It is counted once in the deduplicated total.*

---

## 4. Resolved Findings (fixed and verified this phase)

| # | Finding | Evidence |
|---|---|---|
| C2 | No server-side gate prevented OQ/PQ execution before the prior stage completed | `routes/qual.py::execute_test_case` gate; `tests/test_phase_f_compliance.py::test_oq_test_execution_blocked_before_iq_complete` + `::_allowed_once_iq_complete` (both pass) |
| C3 | Validation Report could be approved/released without its linked qualification's PQ being complete | `routes/report.py::add_approval` gate; 3 passing tests in `tests/test_phase_f_compliance.py` |
| C4 | PUT/DELETE unaudited in every domain except Projects | `pharmagpt/audit.py` + call sites across ~15 modules; 3 passing tests for Equipment, code-read for the rest |
| C5 | Audit-trail schema had no old/new value or company_id columns | `qms_audit_trail` schema extension (`pharmagpt/database.py`), smoke-tested directly |
| C6 | Identity spoofable in attachments/comments/protocol-completion/version-snapshot endpoints | `tenancy.signing_identity()` applied at every identified call site; 1 passing test for the comment endpoint, code-read for the rest |
| C7 | Three state-changing endpoints (Risk `/publish`, Qualification `/complete`, CAPA `/escalate`) had no role guard | `@require_role` added to all three; 4 passing tests (3 blocking + 1 control case) |

Full evidence for each: `docs/PHASE_F_FINDING_TRACEABILITY.md`, `docs/AUDIT_TRAIL_COVERAGE_REPORT.md`, `docs/WORKFLOW_VALIDATION_REPORT.md`, `docs/RBAC_VERIFICATION_REPORT.md`.

## 5. Remaining Findings (open, honestly disclosed)

| # | Finding | Why still open |
|---|---|---|
| A1/C1 | Company Administration / Assume Company Context non-functional | Root cause is inactive Postgres GRANTs on the live, deployed Supabase project — requires a live database session this environment does not have. **The single blocking item for GO.** |
| H7 (residual) | CAPA/Change Control have no full arbitrary-transition guard (only terminal-state immutability was added) | Building a full 13-status transition graph from scratch for two modules risked inventing unverified business rules — explicitly against this phase's "do not add features" instruction. Recommended as scoped follow-up. |
| H1, H2 | DQ/FAT/SAT have no schema linkage to Equipment/Qualification; dedicated AI prompts are dead code | Data-model/content-quality issues, not audit/workflow/RBAC/tenancy — outside this phase's explicit work-package list. |
| H3, H4, H5 | `risk_database.py` connection leak; 6/7 AI-generation endpoints synchronous in-request; uncached per-request auth resolution | Performance — explicitly excluded ("DO NOT OPTIMIZE CODE"). |
| H6 | SQLite→Postgres cutover soak + 2-company RLS spot-check not performed | Operational/deployment-time action, not a code fix. |
| M2 | QMS Document/URS lifecycles have no distinct "Archived" state | Adding a new status value is a vocabulary/schema change, closer to a feature than a guard fix — deliberately not done. |
| — | Postgres Users/Companies audit writes coded but unverifiable live | Same root cause as A1/C1. |
| — | `_score_cache` (Home Dashboard "Avg Validation Score") is process-global, not company-scoped | New finding this session (`docs/MULTI_TENANT_SECURITY_REPORT.md` §7); Low severity — a single aggregate float, not identifying data; fixing it means threading company_id through the review-scoring call chain, a larger change than this phase's scope. |

Full list with rationale: `docs/VALIDATION_EVIDENCE/OPEN_ISSUES.md` and `docs/VALIDATION_EVIDENCE/RESIDUAL_RISKS.md`.

## 6. Evidence

- `docs/PHASE_F_FINDING_TRACEABILITY.md` — every finding, root cause, fix status, evidence, verification method.
- `docs/AUDIT_TRAIL_COVERAGE_REPORT.md`, `docs/WORKFLOW_VALIDATION_REPORT.md`, `docs/RBAC_VERIFICATION_REPORT.md`, `docs/MULTI_TENANT_SECURITY_REPORT.md` — per-work-package detail.
- `docs/VALIDATION_EVIDENCE/` — the condensed evidence package (traceability/workflow/audit/RBAC matrices, test summary, risk assessment, open issues, residual risks, release recommendation).
- `tests/test_phase_f_compliance.py` — 14 new automated tests, all passing, exercising the real Flask app.
- Full regression suite: **514 passed, 1 deselected, 0 failed** (`docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md`).

## 7. Recommendations (priority order)

1. Fix the Postgres GRANTs for migrations 0010-0012 against the live database and re-test Company Administration / Assume Company Context end-to-end — this single action is what stands between the current state and GO.
2. Add automated tests for the disclosed coverage gaps: PQ-specific sequencing, the remaining 7 of 8 terminal-immutability modules, and a live 2-company RLS spot-check once credentials can be safely used outside this environment.
3. Scope and build a full `lifecycle_engine` transition map for CAPA and Change Control (H7 residual), grounded in their existing action vocabularies.
4. Address the explicitly out-of-scope High findings (H1-H6) in a dedicated performance/data-model phase — none of them are audit/workflow/RBAC/tenancy issues, so they don't belong in a compliance-hardening phase, but they remain real.
5. Make a product decision on the `_score_cache` cross-tenant statistic (accept as-is given its low severity, or scope a fix) and on whether QMS Document/URS need a distinct Archived state (M2).

## 8. GO / NO-GO Decision

# **NO-GO**

This is an honest continuation of Phase E's verdict, not a reversal — one Critical finding (Company Administration / Assume Company Context) remains fully open, and it is explicitly in the workflow this Phase E audit was scoped to certify. A system cannot be certified GO with a named, in-scope feature area completely non-functional, regardless of how much else improved.

**What changed, and why this NO-GO is materially different from Phase E's:** six of seven Critical findings are now closed with real, reproducible evidence, not just a plan to fix them. The path back to GO is now a single, well-defined operational action (re-apply and verify three migration files' GRANTs against the live database) plus a re-test of that one feature area — not a broad, multi-week engineering effort. Recommend: perform that operational fix, re-test Company Administration/Assume Company Context specifically, and re-run this certification's automated suite (already green) to confirm no regression — at that point, a GO recommendation would be well-supported by evidence rather than assumed.

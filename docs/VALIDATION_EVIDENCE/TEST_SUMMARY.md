# Validation Evidence — Test Summary

**Run date:** 2026-07-24, end of Phase F.
**Command:** `pytest tests/` (full suite, `venv` active).

## Result

**514 passed, 1 deselected, 0 failed, 25 warnings, in 255.66s.**

This is a live, independently re-run count from this session (not cited from a prior report). It reflects:
- **500** tests that existed at the start of Phase F (independently re-confirmed at the very start of this session too, before any Phase F code change — see `PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md` §0).
- **14 new tests** added in `tests/test_phase_f_compliance.py`, covering the RBAC fixes (C7), the workflow sequencing gates (C2, C3), one terminal-immutability guard (CAPA), the audit-trail schema/company/old-new-value capture, and one identity-non-spoofability case (C6).

## Iteration history (disclosed, not hidden)

The first implementation of the C2/C3 workflow gates was **too strict** and broke 4 pre-existing tests:
- `test_docx_export_regression.py::test_qual_protocol_export_docx`
- `test_kb_sync.py::test_approved_qualification_publishes_each_protocol_to_kb`
- `test_kb_sync.py::test_released_validation_report_is_published_to_kb`
- `test_lifecycle_engine.py::test_validation_report_route_rejects_invalid_transition`

Each was root-caused (not silenced or worked around): the gates were rescoped — C2 to execution-time only rather than protocol-creation time, and C3 to only fire when a qualification is actually linked rather than making linkage mandatory — both changes are narrower, more defensible interpretations of the original findings, documented in `docs/WORKFLOW_VALIDATION_REPORT.md` §1/§2. After rescoping, the full suite (514 tests, including these 4 and the 14 new ones) passes clean.

## What is NOT covered by an automated test (disclosed)

- Live, credentialed browser click-through of any workflow — blocked by this environment's hard rule against entering credentials into any field, including this app's own test credentials (see `PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md` §0).
- PQ-before-OQ sequencing specifically (only IQ-before-OQ has a dedicated test; the code path is identical for both, verified by direct read).
- Terminal-state immutability for 7 of 8 modules (only CAPA has a dedicated test; the other 7 use the identical guard pattern, verified by direct read).
- Whether the Postgres-side Users/Companies audit writes actually land in the live database (depends on the A1/C1 grants issue, outside this session's reach).
- A live 2-company RLS isolation spot-check against the deployed Supabase project (same operational limitation carried from Phase E).

## Coverage tooling

`pytest-cov` is still not configured in this repo (unchanged from Phase E) — no line/branch coverage percentage is available.

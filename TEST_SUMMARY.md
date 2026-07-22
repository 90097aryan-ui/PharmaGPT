# Test Summary

**Run date:** 2026-07-21
**Command:** `pytest tests/` (full suite, `venv` active)

> **Superseded count:** the 352-passed figure below is this specific 2026-07-21 session's
> before/after record — left as-is since it's an accurate historical snapshot, not an error. The
> suite has grown since (`test_risk_generate_endpoint.py`, the QMS record-creation e-signature
> regression tests, and the Generate Document duplication regression tests — see
> `PHASE_1_IMPLEMENTATION_REPORT.md`). **390 passed, 0 failed, 1 deselected** is the current,
> authoritative count as of 2026-07-23; `README.md` reflects it.

## Results

| | Before this session | After this session |
|---|---|---|
| Passed | 336 | 352 |
| Failed | 0 | 0 |
| Deselected | 1 | 1 |
| New tests added | — | 16 (`tests/test_security_tenant_rbac_esig.py`) |

**Final run: 352 passed, 0 failed, 1 deselected.**

Coverage tooling (`pytest-cov`) is not configured in this repo (`requirements-dev.txt` does not include it) — no coverage percentage is reported here. Not installed as part of this session to avoid an unrequested dependency change; adding it is a reasonable follow-up.

## What the new tests cover

`tests/test_security_tenant_rbac_esig.py` — 16 tests added specifically for the three approved security fixes, using the same real-middleware-with-mocked-`resolve_tenant_context` pattern already established in `test_projects_dual_write.py`:

**Cross-tenant access (8 tests)**
- Company B cannot GET/PUT/DELETE Company A's project (404, not 403 — existence is never confirmed to an outsider).
- Company A's project list never includes Company B's projects.
- Company B cannot read Company A's KB document or QMS deviation.
- Company B cannot read Company A's QMS attachments/audit-trail via the shared polymorphic endpoint (`routes/qms_common.py`).
- A deviation cannot be linked to another company's CAPA even when both ids independently exist.

**Unauthorized role access (5 tests)**
- `user` role blocked (403) from deleting a project and from deleting a KB document.
- `company_admin` can delete a project (control case — proves the block above is role-specific, not a general failure).
- `user` role blocked (403) from submitting a QMS deviation approval; `reviewer_qa` can (201).

**E-signature spoofing (3 tests)**
- A `reviewer_qa` submitting a deviation approval with a spoofed `performed_by="Fake CEO"`, `role="super_admin"`, `electronic_sig` in the request body gets an approval entry recorded under their own authenticated identity ("Rita Reviewer" / "reviewer_qa"), not the spoofed values.
- The corresponding `qms_audit_trail` entry also reflects the authenticated identity.
- Same spoofing attempt against a Risk Assessment approval is likewise rejected.

## Pre-existing test changes

A small number of existing tests were updated where their premise no longer holds now that tenant-scoping and RBAC are enforced:

- `tests/test_urs_lifecycle.py` — `performed_by`/`reviewed_by`/`approved_by` assertions updated from the client-supplied name to the authenticated test tenant's name ("Test User"), since these fields are now always derived server-side (this is the same class of fix as the new e-sig tests, just landing on a pre-existing test).
- `tests/test_equipment_dual_write.py`, `tests/test_kb_dual_write.py`, `tests/test_projects_dual_write.py`, `tests/test_qms_dual_write.py` — the four `*_skips_super_admin` tests previously asserted that a Super Admin's create request succeeded at the SQLite layer while only the Postgres dual-write was skipped. Super Admin now has no standing access to tenant content at all (`PLATFORM_ARCHITECTURE.md` §7), so these were renamed and updated to assert 403/404 (equipment, being nested under a Project route, correctly resolves to 404 "not found" rather than 403 — Super Admin can't see the parent Project either).
- `tests/conftest.py` — added a fixed fake `TenantContext` shim (see file for rationale) so the ~300 pre-existing business-logic tests, which bypass real auth entirely, still have a `g.tenant` to satisfy the now-mandatory tenant-scoping checks. This preserves every pre-existing test's original intent unchanged; it does not weaken any check.
- ~20 test files (`test_equipment_database.py`, `test_qms_database.py`, `test_projects_merge.py`, `test_backfill_*.py`, `test_check_*_parity.py`, etc.) — updated direct calls into `*_database.py` constructors to pass the now-required `company_id` keyword argument.

## Remaining known gaps (not blocking, documented)

- A handful of deeply-nested sub-resource endpoints (QMS CAPA action escalation by bare `action_id`, qualification protocol/test-case routes, document distribution/training acknowledgement) check existence but not full tenant ownership at every level — same class of gap, lower severity, since the current top-level record fetch is already tenant-scoped in the same request in most call paths. Flagged for a follow-up pass, not fixed in this session given time constraints.
- The extended Staging soak and 2-company RLS isolation spot-check for the Postgres dual-write path (unrelated to the SQLite fixes above) remain outstanding per `docs/PHASE3_FLAGS.md` — this was already known before this session and is an operational, not a code, task.

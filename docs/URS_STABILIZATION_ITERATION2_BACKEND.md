# URS Workflow — Stabilization Iteration 2: Backend Implementation

Follows [docs/URS_STABILIZATION_REVIEW.md](URS_STABILIZATION_REVIEW.md) (Iteration 1). Backend/API only — no frontend files were modified. Per the agreed working method, this stops here pending confirmation to proceed to **Iteration 3 (frontend)**.

---

## Files changed

**Backend (production code):**

| File | Change |
|---|---|
| `pharmagpt/urs_database.py` | New `urs_numbering` table + `_next_document_number()`; `create_urs()` now server-issues urs_number/doc_number/revision/version/status and blanks reviewed_by/approved_by/effective_date regardless of client input; new `append_requirements()`; `finish_generation()` now writes status+progress+count atomically in one statement; `create_version_snapshot()` syncs `urs_projects.version`. |
| `pharmagpt/database.py` | Added `urs_projects.version` column migration (`_add_column_if_missing`). |
| `pharmagpt/services/urs_lifecycle.py` | **New file.** Status state machine (`validate_transition`, `InvalidTransitionError`) and `bump_revision()`. |
| `pharmagpt/services/urs_generation_job.py` | `submit_generation_job()`/`_run_generation_job()` take a `performed_by` param for audit logging; requirements now persisted per-batch via `append_requirements()` instead of one bulk save at the end; final batch's progress write is folded into the atomic `finish_generation()` call; logs "Generation Started"/"Generation Completed"/"Generation Failed". |
| `pharmagpt/routes/urs.py` | `create_urs()` derives `prepared_by` from `g.tenant`; `update_urs()` (PUT) rejects direct status changes (400) and strips system-controlled fields; `generate_requirements()` resolves and passes `performed_by`; `add_approval()` rewritten around the lifecycle state machine, derives performed_by/role from `g.tenant`, sets reviewed_by/approved_by/effective_date/revision as side effects of the relevant transitions, returns 409 on invalid transitions; `export_docx()` wrapped with DOCX Generated/Downloaded/Download Failed audit logging. |
| `pharmagpt/routes/auth.py` | `login()` mirrors the access token into the Flask session cookie; `logout()` clears it. |
| `pharmagpt/auth/middleware.py` | `before_request` hook falls back to the session-cookie token when a request has no `Authorization` header, and re-syncs the cookie on every successful header-based request. |
| `pharmagpt/app.py` | `SESSION_COOKIE_HTTPONLY`/`SAMESITE`/`SECURE` configured. |

**Tests:**

| File | Change |
|---|---|
| `tests/test_urs_lifecycle.py` | **New.** 19 tests — auto-numbering, system-field protection, transition enforcement, revision bump, effective-date auto-set, identity-derived approval fields. |
| `tests/test_urs_docx_download_auth.py` | **New.** 4 tests exercising the real auth gate end-to-end for the download-auth fix. |
| `tests/test_urs_audit_logging.py` | **New.** 5 tests — DOCX Generated/Downloaded/Download Failed, Generation Started/Completed/Failed. |
| `tests/test_urs_generation_job.py` | Appended 4 tests for incremental persistence and atomic terminal-state writes. |
| `tests/test_routes_auth.py` | Added `app.secret_key` to the standalone test fixture (now required since `login()` writes to `flask.session`). |

---

## Database changes

- **New table** `urs_numbering(series, year, last_seq)` — atomic per-year sequence counters backing auto-numbering. Composite PK `(series, year)`.
- **New column** `urs_projects.version TEXT NOT NULL DEFAULT '1.0'`.
- Both are additive (`_add_column_if_missing` / `CREATE TABLE IF NOT EXISTS`), applied automatically by `init_db()` on next startup — no manual migration step, no data loss, existing rows get `version='1.0'` by default.

## API changes (breaking)

- `PUT /urs/<id>`: now returns **400** if `status` is present in the body (use `POST /urs/<id>/approval` instead). Silently ignores `urs_number`, `doc_number`, `revision`, `version`, `prepared_by`, `reviewed_by`, `approved_by`, `effective_date` if present, rather than applying them.
- `POST /urs/` (create): `urs_number`, `doc_number`, `revision`, `version`, `status`, `reviewed_by`, `approved_by`, `effective_date` in the request body are now ignored — always server-issued/blank. `prepared_by` is overridden by the authenticated user's identity when available.
- `POST /urs/<id>/approval`: now returns **409** if `action` maps to a status not reachable from the document's current status. Added `"Make Effective"` action (Approved → Effective; no frontend trigger yet). `performed_by`/`role` are now derived from the authenticated user when available, overriding client-supplied values (client-supplied values remain a fallback only for unauthenticated/test contexts).
- `GET /urs/<id>/generate/status`: `generation_status`/`generation_progress_current`/`generation_progress_total`/`generation_result_count` are now guaranteed to always be mutually consistent (see below) — no field shape change.

## Migration requirements

None beyond the existing automatic `init_db()` path — restart the app once and the new table/column are created. No backfill needed (defaults are safe for existing rows: `version` defaults to `'1.0'`, existing `urs_number`/`doc_number` values are untouched since numbering only applies going forward to new records).

---

## What each priority actually fixed

**1. DOCX export auth.** Confirmed root cause: the app is bearer-token-only (token in `localStorage`, attached only to `fetch()` calls), but the download button navigates via `<a download href="...">`, which cannot carry a custom header — the server correctly 401'd it, and Chrome rendered that as "sign in to the site." Fix: `login()` now also mirrors the access token into a signed, HttpOnly session cookie; the global auth gate falls back to it only when a request has no `Authorization` header at all (never overrides a present one, even a bad one), and re-syncs it on every successful header-based request so it can't go stale after a client-side token refresh. **Zero frontend changes** — the existing `<a>` click now just works.

**2. Generation status/count race.** Confirmed root cause: `generation_result_count` was published (via a per-batch progress write) before a separate, later `finish_generation()` call flipped `generation_status` to terminal — the gap was as wide as the final bulk `save_requirements()` call. Fix: switched to per-batch incremental persistence (`append_requirements()`), and folded the last batch's progress into the same single `UPDATE` statement that sets the terminal status — status, final progress, and result_count are now written together, atomically, in every case. This also closes a data-loss gap: a crash mid-job now only loses the batch in flight, not every requirement generated so far.

**3. Lifecycle transitions.** New `urs_lifecycle` module enforces Draft → Under Review → (Pending Approval) → Approved → Effective, with Rejected-to-Draft and Obsolete-from-Effective. Closed **two** bypasses: `PUT /urs/<id>` could set status directly (now 400s), and `create_urs()` itself honored a client-supplied `status` at creation (now hardcoded to `draft`).

**4. Auto document control fields.** `urs_number`/`doc_number` via a dedicated atomic per-year sequence table (never reuses a number even if the row is deleted). `revision` always starts `'A'`; `version` always starts `'1.0'` and stays synced to the latest version snapshot. `prepared_by` derived from `g.tenant.display_name` when authenticated.

**5. Reviewed By / Approved By.** Blanked at creation; set only as a side effect of the approval workflow's "Review Complete" / "Approved" actions, using the authenticated approver's identity (not a free-text field the caller could set to anyone's name).

**6. Audit logging.** Added Generation Started/Completed/Failed and DOCX Generated/Downloaded/Download Failed to the existing `urs_approvals` audit table (kept as the single audit log rather than introducing a new table, consistent with how it already logs "URS Created" and "Version Snapshot Created"). "DOCX Downloaded" is a best-effort signal — it confirms the server successfully handed the response to Flask, not that the browser's download completed, since there's no client-side completion callback in this iteration.

---

## Regression risks

- **Breaking API change**: any external caller relying on `PUT /urs/<id>` to set `status` or the now-system-controlled fields will start getting 400s / silently-ignored fields. No such caller exists in this codebase's own frontend (verified — the wizard's PUT resubmits these fields but never changes them).
- **Session cookie is a new secondary auth channel.** It's scoped narrowly (falls back only when no header is present, HttpOnly/SameSite=Lax/Secure-in-production, cleared on logout, always re-verified against Supabase like the header path), but it does mean any route is now also reachable via a valid session cookie, not just a bearer header — this is an intentional, uniform extension of the existing single-global-gate design, not a per-route special case.
- **Revision-bump semantics** (`bump_revision`) only trigger when a document re-enters Draft from Approved/Effective. If a real-world workflow expects a revision bump on rejection from Under Review too, this will need adjusting in Iteration 3+.
- **`urs_numbering` never reuses a number.** Deleting and recreating URS documents will produce gaps in the sequence — this is intentional (document-control numbering must never repeat), not a bug, but worth calling out since it looks unusual in testing.
- The AI-review endpoint's exception handling (swallows stack traces, no `exc_info`) was **not** touched — flagged in Iteration 1 but out of this iteration's explicit priority list.

## Tests executed

```
pytest tests/ -q
336 passed, 1 deselected (pre-existing @slow marker, unrelated), 152s
```

New/updated test files specifically exercising this iteration's changes:
- `tests/test_urs_lifecycle.py` (19 tests)
- `tests/test_urs_docx_download_auth.py` (4 tests, real auth gate)
- `tests/test_urs_audit_logging.py` (5 tests)
- `tests/test_urs_generation_job.py` (+4 tests, atomicity/incremental persistence)
- `tests/test_routes_auth.py` (existing 8 tests, fixture updated)
- Full existing suite (`test_app_auth_integration.py`, `test_docx_export_regression.py`, `test_urs_routes.py`, all QMS/equipment/document-processing suites) — all still pass unmodified, confirming no regressions outside the URS/auth surface touched here.

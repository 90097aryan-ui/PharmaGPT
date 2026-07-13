# URS Workflow — Stabilization Architecture Review (Iteration 1)

**Scope:** PharmaGPT v1.0 Stabilization. No new modules, no new business features — this document reviews the existing URS lifecycle end-to-end (Login → Create URS → AI Generation → Review → Approval → Document Generation → DOCX Download → Audit Trail → Version History) as one workflow, identifies every gap, and proposes a redesign. Per the agreed working method, this is **Iteration 1: architecture review only**. No code changes are included in this document.

All findings below are code-grounded (file:line citations against the `D:\PharmaAgent` repo as of 2026-07-12). Where a claim could not be verified in code, it is marked as such.

---

## 1. Current Workflow (as-built)

```
Login (Supabase bearer token, stored in localStorage)
   │
   ▼
Create URS  ── POST /urs/  ── wizard collects EVERYTHING up front:
   │              - Category/Equipment (master-data driven, hardcoded JS list)
   │              - URS Number, Doc Number, Revision, Effective Date (free text)
   │              - Prepared By, Reviewed By, Approved By (free text, all three, at creation)
   │              - Department, Site, Manufacturer, Model... (free text)
   ▼
AI Generation ── POST /urs/<id>/generate (202, fire-and-forget)
   │              Background: ThreadPoolExecutor, sequential Gemini calls per
   │              2-section batch, state persisted to SQLite columns on urs_projects
   │              Frontend: polls GET /urs/<id>/generate/status every 1.5s,
   │              client-side 5-min wall-clock deadline
   ▼
Review ── GET AI-review endpoint, manual read-through
   ▼
Approval ── POST /urs/<id>/approval → urs_approvals log entry,
   │          separately, PUT /urs/<id> can set status directly (bypass)
   ▼
Document Generation ── on-demand, in-memory DOCX build per request
   ▼
DOCX Download ── <a download> synthetic click, direct navigation
   ▼
Audit Trail ── urs_approvals table only (partial coverage)
   ▼
Version History ── urs_versions, full JSON snapshot per version (on demand)
```

---

## 2. Problems, by workflow stage

### 2.1 Document Control Automation — **not implemented**

| Requirement | Current state | Evidence |
|---|---|---|
| Auto URS Number / Doc Number / Version / Revision / Effective Date | 100% manual free text, no server-side generator, no sequence, no uniqueness check | `urs_database.py:20-51,105-146`, `urs.js:517-578` |
| Prepared By = logged-in user | Manual free-text field; no identity resolution occurs on `urs_bp` at all | `urs_database.py:135`, `urs.js:582`, `routes/urs.py` (no `@require_auth`/`g.tenant` anywhere in the file, unlike `risk.py`/`equipment.py`/`qms_*.py`) |
| Reviewed By / Approved By / QA Approval collected at final approval step | Collected as free text **at creation time**, before review or generation even happen; a separate `urs_approvals` log exists but is disconnected from these columns | `urs_database.py:136-137`, `routes/urs.py:301-328` |
| Document lifecycle state machine (Draft → Under Review → Approved → Effective) | `status` is a bare TEXT column, default `'draft'`, directly settable via generic `PUT /urs/<id>`; no transition guard exists — a client can jump straight to `"approved"` | `urs_database.py:26`, `routes/urs.py:103-109,187,316-323` |
| Electronic signature readiness | None. `performed_by` is a free-text name string, no user_id FK, no re-auth, no hash/tamper-evidence. DOCX export renders **hardcoded blank** signature/date cells | `urs_database.py:75-85`, `routes/urs.py:308`, `urs_service.py:176-178` |

**Root cause:** the URS module was built as a CRUD form, not a controlled-document workflow. Every field GMP document control expects to be system-derived (numbering, preparer identity, revision, status transitions, signatures) is instead operator-typed and enforced nowhere.

### 2.2 AI Generation — contradictory UI state (the "59 requirements / taking longer than expected" bug)

**This is a confirmed race condition, not a display glitch.** Two independent, uncoordinated signals drive the UI:

- `generation_result_count` is written to SQLite on **every batch**, including the final one, from an in-memory running tally (`urs_database.py:235-244`, called from `urs_generation_job.py:175`).
- `generation_status` only flips to `"completed"` **after** the (separate, slower) final `save_requirements()` call that writes all accumulated requirements to the `requirements` table in one shot (`urs_generation_job.py:177-188`).

Between those two writes there is a real window where a poll can observe `generation_result_count = 59` while `generation_status` is still `"running"`. The frontend polling loop (`urs.js:777-790`) has **no single source of truth**: `genCount` is updated unconditionally on every poll (`urs.js:786`), but `genText` is only overwritten by whichever of three mutually-exclusive branches fires when the loop exits (`urs.js:803, 807, 811`). If the client-side 5-minute wall-clock deadline (`urs.js:746`, entirely uncorrelated with actual job state) elapses while status is still `"running"`, the timeout branch (`urs.js:803-806`) rewrites only `genText` to "taking longer than expected" and **never touches the stale `genCount` node** — producing the exact contradiction reported.

Secondary findings in the same pipeline:
- Gemini calls are **strictly sequential** per 2-section batch (`urs_generation_job.py:152`), no fan-out — this is also why generation is slow enough for the timeout to matter.
- No prompt caching between batches; each batch rebuilds the full prompt from scratch (`urs_service.py:24-75`).
- Retry logic only covers malformed/truncated JSON (2 extra attempts); genuine API errors and safety blocks are never retried (`urs_generation_job.py:95-109, 212-255, 324-345`).
- If the worker process dies mid-job, the DB row is permanently stuck at `generation_status='running'` with no process left to ever finish it — no watchdog/reaper exists.
- Requirements are stored **all-at-once at the end**, not incrementally — so "real progress" (count of requirements actually persisted) cannot currently be shown mid-generation without also fixing storage to be incremental.

**Root cause:** two independently-mutated pieces of UI state, backed by two independently-updated DB signals with no ordering guarantee between them, plus a client timeout with no awareness of actual job state.

### 2.3 DOCX Export — download failure (the "sign in to the site" bug)

**Confirmed root cause: auth-header-vs-navigation mismatch**, not a session/cookie/CORS problem.

- Auth is 100% bearer-token based: token lives in `localStorage`/`sessionStorage`, injected **only** into requests made via the patched `window.fetch` (`auth.js:59-73`). There is no cookie-based session in use.
- `exportURSDocx()` (`urs.js:1602-1610`, called from 3 places) downloads via a synthetic `<a download href="/urs/<id>/export/docx">` click — a **real browser navigation**, which never passes through `fetch` and therefore never carries `Authorization: Bearer <token>`.
- The global `before_request` auth gate (`middleware.py:44-58`) correctly rejects the un-authenticated navigation with `401 {"error": "Missing or malformed Authorization header"}` — valid JSON, not an HTML redirect.
- Chrome's download manager, however, treats any failed/blocked response to a `download`-attribute navigation as a generic **"Try to sign in to the site. Then download again"** — which is exactly the symptom reported. The download endpoint itself (`routes/urs.py:359-393`) is correctly implemented (`send_file` with correct `Content-Type`/`Content-Disposition`) — it simply never receives a valid request.
- No pre-generation, no signed URL, no streaming/blob mechanism exists — DOCX is built fully in-memory per request.

**Root cause:** the frontend never adapted its download mechanism to the token-based auth model introduced elsewhere in the app. Fix is isolated to the frontend download trigger (fetch + blob + `URL.createObjectURL`), not the backend.

### 2.4 Error Handling — errors are ephemeral and unactionable

- All URS errors surface through a single custom toast (`ursToast`, `urs.js:206-217`) that **auto-dismisses after 3000ms** — no retry, dismiss, copy-details, or error-ID affordance exists anywhere (repo-wide grep for these terms returns nothing).
- Server-side stack traces are preserved for generation-job failures (`logger.exception`, `urs_generation_job.py:172,182`) but **lost entirely** for AI-review failures — that endpoint uses a bare `except Exception as e: str(e)` with no `exc_info` (`routes/urs.py:268-281`).
- No error categorization (Auth/Authorization/Validation/Generation/Download/Database/Unexpected) exists — every failure produces the same undifferentiated red toast.
- No APM/Sentry-equivalent integration anywhere in the URS files.

### 2.5 Loading States — mostly present, with one hard gap

- Spinner-based (not skeleton) loading exists for dashboard load, AI review, approval trail, versions list (`urs.css:722-732`, multiple call sites in `urs.js`).
- Empty states are already well-designed (dashboard, list view, versions, approval trail all have dedicated "no data" UI with CTAs) — this is in better shape than the brief assumed.
- Generation progress text (batch N/N) is the most informative loading UX already present — a good foundation for the "real progress" requirement.
- **Gap:** DOCX export has **zero** loading feedback — a toast fires before the request even completes, then nothing until the browser's native download UI appears (and currently fails per §2.3).

### 2.6 UX / Manual Entry

- Step 1 (Category + Equipment Type) is genuinely master-data driven, but the master data is a **hardcoded JS constant** (`URS_CATEGORIES`, `urs.js:24-161`), not backend-sourced.
- Step 2 ("Project Information") is almost entirely free text — Department, Site, Manufacturer, Model, Prepared/Reviewed/Approved By are all plain inputs. Only "Validation Type" is a real dropdown.
- Notably, the codebase **already contains** richer structured equipment data (`pharmagpt/equipment/profiles/*.py`, `get_equipment_profile()`) used elsewhere for AI prompt enrichment, but it is **not wired into the URS wizard** — meaning the fix here is largely integration, not new data modeling (consistent with "no new modules").

### 2.7 Performance

- Gemini calls: sequential per-batch, no parallelism, no prompt caching — largest lever for perceived wait time.
- `save_requirements()` does one `INSERT` per requirement in a Python loop inside a single transaction (`urs_database.py:326-361`) — not N+1 *connections*, but still N sequential statement executions where `executemany` would suffice.
- No pagination/indexing considerations found in `urs_database.py`.

### 2.8 Audit Trail — large gaps against the required event list

Only `urs_approvals` exists as a URS-specific audit table (a separate `qms_audit_trail` table exists but is never called from any URS file). Coverage against the required 8 events:

| Event | Logged today? |
|---|---|
| URS Created | ✅ `urs_database.py:144-145` |
| Generation Started / Completed | ❌ Python log lines only (not persisted rows); overwritten on next run |
| Review | ⚠️ Only if `POST /urs/<id>/approval` is explicitly called — not enforced |
| Approval | ⚠️ Same as above, and disconnected from the `reviewed_by`/`approved_by` columns |
| DOCX Generated | ❌ Not logged |
| DOCX Downloaded | ❌ Not logged |
| Download Failed | ❌ Not logged — `export_docx()` has no try/except at all |

### 2.9 Regression Testing — coverage concentrated in one place

- `tests/test_urs_generation_job.py` (12 tests) and `tests/test_urs_routes.py` (3 tests) give solid coverage of the **background generation job's resilience mechanics** (partial batch failure, retries, status transitions).
- **Zero automated test coverage** for: frontend (`urs.js`), AI-review endpoint, DOCX export/download, approval workflow, version snapshots, or `urs_database.py` CRUD/save-requirements logic.

---

## 3. Redesign (proposed direction — for Iteration 2+ approval)

This section states direction only; no implementation in this document.

1. **Document control**: server-side numbering service (sequence per org/year), `prepared_by` derived from the authenticated user (requires wiring auth into `urs_bp`, currently entirely absent), and a proper `Draft → Under Review → Approved → Effective` status enum enforced by a transition guard on `PUT /urs/<id>` (reject any status change that doesn't come through the approval endpoint). `reviewed_by`/`approved_by`/QA fields move out of the creation wizard into the approval step and become populated from the approval action, not free text at creation.
2. **AI generation**: make `generation_status` and `generation_result_count` update in the same transaction/order so they can never be observed inconsistently; make requirement storage incremental (persist per-batch, not all-at-once) so real progress can be shown; replace the client-side wall-clock-only timeout with logic that also checks last-observed progress (a stalled-but-still-running job vs. a genuinely hung one are different UX states); add a watchdog for jobs orphaned by process death.
3. **DOCX download**: switch `exportURSDocx()` from `<a href>` navigation to `fetch()` (which already carries the token via the patched `window.fetch`) + blob + `URL.createObjectURL` download. This is a small, contained frontend fix.
4. **Error handling**: introduce one shared error-notification component (persistent until dismissed, Retry/Dismiss/Copy-Details, generated error ID, category tag), and fix the AI-review endpoint to log with `exc_info`.
5. **Audit trail**: log all 8 required events, including DOCX generated/downloaded/failed, ideally via a single decorator/helper wrapping URS-mutating routes rather than manual calls scattered per-route.
6. **Master data wiring**: connect `pharmagpt/equipment/profiles` to the URS wizard's Department/Equipment fields (no new data modeling needed — integration only).
7. **Testing**: extend coverage to the gaps in §2.9, especially DOCX export and the approval/status-transition guard once built.

---

## 4. Risk Assessment

| Area | Risk if unaddressed | Severity |
|---|---|---|
| Status bypass via `PUT /urs/<id>` | A document can reach "approved"/"effective" state without ever going through review — a GMP data-integrity finding in any audit | **High** |
| No audit logging on DOCX generate/download/fail | Cannot demonstrate document distribution control — a direct 21 CFR Part 11 / ALCOA+ gap | **High** |
| DOCX download bug | Blocks the core deliverable of the entire workflow; user-facing and already reported | **High** (but low-risk, contained fix) |
| Generation race condition | Confuses users about whether generation succeeded; could cause premature retry/duplicate generation | **Medium** |
| No electronic signature | Acceptable for now since `DATABASE.md` already scopes this to a future v0.7+ release — not a stabilization-scope regression, just confirmed still-pending | **Low (tracked)** |
| Manual document numbering | Operational/data-quality risk (duplicates, inconsistent formats) more than a hard bug | **Medium** |
| Test coverage gaps | Regressions in DOCX export, approval, or frontend generation-state logic would ship undetected | **Medium** |

---

## 5. Sign-off

Per the agreed working method, this concludes **Iteration 1 (architecture review only)**. No backend or frontend code has been modified. Awaiting confirmation to proceed to **Iteration 2 (backend implementation)**.

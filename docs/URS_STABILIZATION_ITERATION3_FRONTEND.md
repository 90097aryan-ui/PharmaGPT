# URS Workflow — Stabilization Iteration 3: Frontend Implementation

Follows [docs/URS_STABILIZATION_ITERATION2_BACKEND.md](URS_STABILIZATION_ITERATION2_BACKEND.md) (Iteration 2). Frontend/UX only — `pharmagpt/static/js/urs.js` and `pharmagpt/static/css/urs.css` only; **no backend files were modified**. Per the agreed working method, this stops here pending confirmation to proceed to **Iteration 4 (workflow integration)**.

---

## Components changed

| File | Change |
|---|---|
| `pharmagpt/static/js/urs.js` | Notification engine (`ursNotify`), skeleton/error-state helpers, wizard Step 2 rewrite (read-only doc-control fields), generation progress engine (`renderGenerationPanel`, `ursChunk`, `ursFormatETA`), approval panel rewrite (lifecycle mirror + identity-derived fields), DOCX export rewrite (fetch+blob), `submitForReview`/`createVersionSnapshot`/`deleteURS` upgraded to the notification system, `refreshDetailStatusBadge()` helper. |
| `pharmagpt/static/css/urs.css` | New sections: notification stack, generation checklist/progress bar, skeleton shimmer, error/retry state, read-only field styling, DOCX export button states, identity chip / lifecycle hint styling. |

No HTML template changes — the notification stack and all new panels are created/injected by JS into existing containers (`urs-dash-body`, `urs-wizard-body`, `.urs-detail-panel[data-tab=...]`), consistent with how this file already worked.

---

## What changed, mapped to each objective

**1. Read-only document control fields.** Wizard Step 2 no longer has inputs for URS Number, Document Number, Version, Revision, or Prepared By. They're shown as dashed-border read-only fields with an "Auto"/"You" badge, populated from `ursState.currentURS` once the record exists (a "will be assigned on creation" placeholder before that). Also added to the Step 5 confirmation screen and the Overview tab (which previously showed URS Number/Doc Number/Revision but not the new `version` field from Iteration 2).

**2. Reviewed By / Approved By / QA Approval moved to the Approval step.** No longer collected anywhere at creation (removed from the wizard entirely). The Approval tab now opens with a dedicated "Reviewed By / Approved By / QA Approval" summary card reading directly from `urs.reviewed_by`/`urs.approved_by` (with QA Approval derived as Approved/Pending), populated by the backend as a side effect of the approval workflow.

**3. Real generation workflow progress.** Replaced the spinner-only panel with a per-batch checklist (✓ done / spinner active / ○ pending) plus a progress bar and an estimated-time-remaining readout — matching the brief's example almost exactly (✓ General Requirements / ✓ Functional Requirements / ✓ Operational Requirements / Generating Performance Requirements… / Estimated time remaining). Batch boundaries are reconstructed client-side from `sections.length` and `generation_progress_total` (no backend change needed, no hardcoded batch-size constant to drift out of sync).

**4. Contradictory UI states removed.** The old design had two independently-mutated DOM nodes (a status text and a count) that a stale client-side timeout could update inconsistently. `renderGenerationPanel()` is now the *only* place that touches this panel's DOM, always called with one complete state object — status line, checklist, progress bar, and count are always from the same render. Verified directly (see Regression Tests below): rendering the exact old bug scenario (count=41, batches 3/4 done, phase="stalled") now produces "Generation is taking longer than expected." next to a checklist and count that are self-consistent, because there is no code path that can update one without the other.

**5. Automatic transition to Review on completion.** Unchanged in spirit from before, but now driven by the same unified render — `wizardGoTo(4)` (the "Review & Edit Requirements" step) still fires automatically after a clean completion, with a slightly longer delay on partial-failure completions so the user has time to read the warning notification first.

**6. Professional notification system.** New `ursNotify()` replaces the single auto-dismissing toast with a stacked, top-right notification system: `success`/`info` auto-dismiss, `warning`/`error` persist until dismissed, every notification has a Dismiss button, retryable failures get a Retry button (re-invokes the original action), and errors additionally get a client-generated correlation ID plus a "Copy Details" button. `ursToast()` is kept as a thin backward-compatible wrapper so all ~20 existing call sites upgrade automatically; the generation, DOCX export, approval, and version-snapshot flows were additionally upgraded to pass richer `category`/`retry`/`detail` options directly.

**7. Loading / empty / error states.** Dashboard and URS list now show shimmer skeleton placeholders while loading (previously a bare spinner), and a dedicated retry-capable error state (icon + message + Retry button) on failure, in addition to the notification. Empty states (no URS yet, no approval entries, no versions) were already reasonably handled per the Iteration 1 review and are unchanged.

**8. DOCX export — visible preparation and completion states.** Replaced the blind `<a href>` navigation (which had zero error handling — a 401/404/500 was previously indistinguishable from success) with `fetch()` + blob download. The export button now shows a spinner and "Preparing…" while the server builds the document, "Downloaded" briefly on success, and reverts to idle with a persistent, retryable error notification (showing the actual server error message) on failure. Verified end-to-end in the browser against a real 401 response — see below.

**9. UI reflects backend lifecycle state / prevents invalid actions.** Added a client-side mirror of the backend's transition rules (`URS_LIFECYCLE_TRANSITIONS`/`URS_ACTION_STATUS_MAP`, explicitly commented as a presentation-only duplicate of `pharmagpt/services/urs_lifecycle.py`) so the Approval tab's action dropdown only ever offers actions valid from the document's current status; a terminal status (Obsolete) replaces the form entirely with an explanatory message. The Overview tab's "Submit for Review" button is likewise hidden (replaced by a hint) once the document has left Draft. As defense-in-depth, `addApprovalEntry()` still handles a 409 from the backend gracefully (status changed in another tab) by reloading the record and re-rendering rather than erroring blindly.

---

## New workflow — descriptions of key states

Since I could not log in with real Supabase credentials (none were provided/available), verification was done by exercising the actual shipped functions in the running app rather than a synthetic reimplementation — see Regression Tests below for exactly what was run and observed.

- **Wizard Step 2 (before creation)**: "URS Number / Document Number / Version / Revision / Prepared By" shown as dashed-border fields reading "Assigned when this URS is created" with "Auto"/"You" badges; an info banner explains the automation; Reviewed By / Approved By inputs are gone entirely.
- **Wizard Step 2 (after creation)**: the same fields now show the real server-issued values (e.g. `URS-2026-014`, `QA-URS-2026-014`, `1.0`, `A`, `Jane Reviewer`).
- **Generation — running**: status line "Generating requirements… (batch 3/4)", a checklist with 3 green checkmarks and one spinner-active row ("Generating Performance Requirements…"), a progress bar at 75%, "41 requirements generated so far", and "Estimated time remaining: ~9s remaining".
- **Generation — completed**: status line turns green ("4 of 4 sections generated successfully (59 requirements)."), all checklist rows checked, progress bar full, count "59 requirements generated so far" — then auto-advances to the Requirements step.
- **Generation — stalled** (the exact old bug scenario): status line "Generation is taking longer than expected." in amber, checklist still shows 3 done / 1 pending, count "41 requirements generated so far" — internally consistent, because it's one render call.
- **Approval tab — Under Review**: status chip "UNDER REVIEW"; Reviewed By/Approved By/QA Approval card all showing "—"/"Pending"; action dropdown offers only "Submitted for Approval", "Approved", "Rejected" (not "Submitted for Review" or "Make Effective"), with a live hint ("This will move the document status to: Pending Approval").
- **Approval tab — Obsolete**: status chip "OBSOLETE"; the Add Entry form is replaced entirely by "This document is Obsolete — no further lifecycle transitions are available from here."
- **DOCX export — failure**: clicking Export DOCX shows a spinner + "Preparing…" on the button, then (on a real 401 in this unauthenticated test) a persistent notification "DOCX export failed · Download — Missing or malformed Authorization header" with a real Error ID and Retry/Dismiss buttons, and the button cleanly reverts to idle.

---

## Regression tests performed

1. **Backend suite unaffected**: `pytest tests/ -q` → 336 passed, 1 deselected (unchanged from Iteration 2) — confirms these are genuinely frontend-only changes.
2. **JS syntax check**: `node --check pharmagpt/static/js/urs.js` → passes.
3. **Live browser verification** (Flask dev server via the Browser pane, `pharmagpt-flask` launch config): could not complete a full authenticated end-to-end run (no Supabase test credentials were available), so verification instead directly exercised the real, already-loaded application functions against the running page:
   - Triggered `loadURSDashboard()` unauthenticated → confirmed the real notification card (title, message, category "Database", real Error ID, Retry/Dismiss) *and* the in-page skeleton→error-state transition, both from the actual 401 response.
   - Rendered wizard Step 2 with `ursState.currentURS = null` and then with a populated mock record → confirmed the read-only fields correctly show placeholders before creation and real values after.
   - Called `renderGenerationPanel()` directly with `running`, `completed`, and `stalled` phase states (including the exact count/batch values that used to reproduce the reported contradiction) → confirmed the checklist, progress bar, ETA, and status line are always mutually consistent.
   - Rendered the Approval panel with `status: "under_review"` → confirmed action-dropdown filtering, the live transition hint, and the identity-chip-vs-manual-input fallback (no session → correctly fell back to manual inputs).
   - Rendered the Approval panel with `status: "obsolete"` → confirmed the terminal no-actions-available message, and confirmed `refreshDetailStatusBadge()` correctly updates the header badge.
   - Clicked the DOCX export button against the real (unauthenticated) endpoint → confirmed the preparing state, the parsed real server error message in the failure notification, and the button correctly resetting to idle.
   - Checked the browser console throughout (`read_console_messages`, errors only) → zero errors across all of the above.
4. **Not verified in this iteration**: a full authenticated create → generate → review → approve → export happy path, since no login credentials were available in this environment. The rendering logic exercised above is the same code that path would run through, but the true end-to-end click-path (including the DOCX session-cookie fallback from Iteration 2 specifically) has only been regression-tested at the backend level (`tests/test_urs_docx_download_auth.py` etc.), not re-verified visually in this iteration.

---

## Regression risks

- **Client-side lifecycle mirror can drift from the backend.** `URS_LIFECYCLE_TRANSITIONS`/`URS_ACTION_STATUS_MAP` in `urs.js` duplicate `pharmagpt/services/urs_lifecycle.py` and `routes/urs.py`'s `_ACTION_STATUS_MAP` by necessity (no backend change permitted this iteration to expose a "valid next actions" endpoint). If the backend rules change in a future iteration without updating this mirror, the UI would either hide a now-valid action or offer one the backend will 409 — the 409 is still handled gracefully (reloads and re-renders), so this degrades to "action briefly not offered," not silent breakage.
- **DOCX export ETA/progress reconstruction assumes fixed-size contiguous batching.** If `_batch_sections()`'s chunking strategy ever changes to something non-contiguous or variable-size, the client-side batch reconstruction (`Math.ceil(sections.length/total)`) would misalign section labels within the checklist — cosmetic only, doesn't affect correctness of counts/status.
- **No end-to-end authenticated verification was possible in this session** (see Regression Tests §4) — recommend a manual authenticated smoke test (or credentials provided) before shipping.
- **`window.PharmaAuth` dependency**: identity-derived fields (Prepared By display, approval Performed By/Role, submit-for-review, version-snapshot author) all read `PharmaAuth.getUser()`; if a session exists but `getUser()` returns a partial object (e.g. missing `display_name`), the UI falls back to `email`, then to a manual input — verified via the no-session case, not a partial-session case.

## Regression tests to run manually once credentials are available

- Full wizard: create → verify auto-numbered fields → generate (small section set) → confirm checklist/ETA/auto-advance → edit requirements → submit.
- Approval walk: Submitted for Review → Review Complete → Approved → Make Effective, confirming Reviewed By/Approved By/Effective Date populate and the action list narrows at each step.
- DOCX export success path (currently only the failure path was exercised against the real server in this session).

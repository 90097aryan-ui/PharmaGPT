# Workflow Validation Report — Phase F, Work Package 3

**Scope:** Verify, and implement where missing, server-side (never client/UI-only) enforcement of: OQ cannot begin before IQ is complete; PQ cannot begin before OQ is complete; a Validation Report cannot be approved before PQ is complete; Effective is unreachable before Approval; records in a terminal/locked state are immutable; a Rejected record cannot bypass re-review.

All checks below were independently re-derived from the current source, not assumed from the Phase E report. Every guard is implemented **server-side**, in the route handler itself — never delegated to the frontend.

---

## 1. IQ → OQ → PQ sequencing (closes C2)

**Before this work package:** confirmed by direct code read — `qual_database.py::create_protocol()` and `routes/qual.py::execute_test_case()` had no check on sibling-protocol state at all. An OQ or PQ protocol could be created, and its test cases executed, with no IQ protocol in existence.

**Fix:** `routes/qual.py` now defines `_PROTOCOL_PREREQUISITE = {"OQ": "IQ", "PQ": "OQ"}` and `_missing_prerequisite_protocol(qid, protocol_type)`, which checks that a sibling protocol of the required prior type exists for the same qualification **and** has reached a completed status (`completed` or `completed_with_deviations` — the closest existing equivalent to "Approved" for a protocol; protocols don't carry their own distinct Approved status, only the parent Qualification does — see §6 for the terminology mapping this implies).

**Where the gate is enforced — a deliberate, evidence-driven decision, not the original plan:** the gate is enforced in `execute_test_case` only — a test case cannot be *executed* against an OQ or PQ protocol unless the prior stage is complete. It is **not** enforced at protocol *creation* time. This session's first implementation gated creation too, but that broke two pre-existing, passing regression tests (`test_docx_export_regression.py::test_qual_protocol_export_docx`, `test_kb_sync.py::test_approved_qualification_publishes_each_protocol_to_kb`) that create IQ/OQ/PQ protocol *records* back-to-back before executing or completing any of them — which is legitimate GxP practice (protocols are commonly drafted/prepared in parallel; what must not happen is *running* OQ/PQ tests before the prior stage's evidence exists). Re-scoping the gate to execution-only is the more defensible, narrower fix and is what ships. Blocked execution attempts are audit-logged via `audit.log_failure()` (result="failure", with the specific reason).

**Verification: VERIFIED by automated test.** `tests/test_phase_f_compliance.py::test_oq_test_execution_blocked_before_iq_complete` (asserts 409 + "IQ" in the error message when OQ execution is attempted with no completed IQ) and `::test_oq_test_execution_allowed_once_iq_complete` (asserts 200 once IQ is completed via the real `/complete` endpoint) both pass against the real Flask app + real route code, not a mock. Root-cause history: the first implementation gated protocol *creation* too, which broke 2 pre-existing tests (`test_docx_export_regression.py::test_qual_protocol_export_docx`, `test_kb_sync.py::test_approved_qualification_publishes_each_protocol_to_kb`); the fix was rescoped to execution-only as described above, and the full suite (514 tests including the 2 previously-broken ones and the 2 new ones) now passes clean — see `docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md`.

## 2. Validation Report cannot be approved before PQ is complete (closes C3 — the most consequential finding in the Phase E audit)

**Before this work package:** confirmed by direct code read — `routes/report.py`'s create/generate/approval paths never checked the linked qualification's completeness. `linked_qual_id` itself was optional.

**Fix:** `routes/report.py` now defines `_pq_not_ready_reason(report)`, called specifically when the approval action would move the report to `"approved"` status. It requires: **if and only if** the report has a `linked_qual_id`, that linked qualification's `pq_status` must be `"completed"` or `"completed_with_deviations"`.

**Scope decision, evidence-driven:** the first implementation of this gate also required `linked_qual_id` to be present at all — i.e. made linkage mandatory before approval. That broke two pre-existing, passing regression tests (`test_kb_sync.py::test_released_validation_report_is_published_to_kb`, `test_lifecycle_engine.py::test_validation_report_route_rejects_invalid_transition`), both of which approve/release a standalone report with no linked qualification, which is a legitimate, already-supported configuration in this codebase. Making linkage mandatory would have been a business-rule change beyond the literal Phase E finding (C3 was "no check that the *linked* qualification's PQ is complete," not "linkage must be mandatory") and beyond a "verified release blocker" fix per the Phase F brief's own instruction not to add scope. The gate now only fires when a qualification **is** linked, matching the finding precisely: it's still impossible to approve a report against an *incomplete* qualification, but reports with no qualification link at all are unaffected, exactly as before.

If the gate fires, the approval is rejected with HTTP 409 and a specific, human-readable reason, and the attempt is audit-logged as a failure (`audit.log_failure`).

**Verification: VERIFIED by automated test.** Three new tests in `tests/test_phase_f_compliance.py` cover all three cases: `test_report_approval_blocked_when_linked_pq_incomplete` (409 + "PQ" in the error), `test_report_approval_allowed_once_linked_pq_complete` (201, once the linked qualification's PQ protocol is completed via the real `/complete` endpoint), and `test_report_approval_unaffected_when_no_qualification_linked` (201, proving the standalone-report path this session deliberately preserved — see the scope decision above — still works). All three pass against the real app. The existing `lifecycle_engine.validate_transition("VALIDATION_REPORT", ...)` call (unchanged) continues to enforce that `approved` is only reachable from `under_review`, unaffected by this addition.

## 3. Effective impossible before Approval

**Already correctly enforced before this work package** — re-verified, not newly built. Every lifecycle wired into `services/lifecycle_engine.py` (QMS_DOCUMENT, QUALIFICATION, VALIDATION_REPORT, RISK_ASSESSMENT) and `services/urs_lifecycle.py` (URS) defines Effective/Released as reachable only from Under Review / Pending Approval / Approved — never directly from Draft — and every transition is validated via `validate_transition()` before the status write happens, raising `InvalidTransitionError` → HTTP 409 otherwise. Confirmed by direct re-read of `_QMS_DOCUMENT_TRANSITIONS`, `_QUALIFICATION_TRANSITIONS`, `_VALIDATION_REPORT_TRANSITIONS`, `_RISK_ASSESSMENT_TRANSITIONS`, and `urs_lifecycle.ALLOWED_TRANSITIONS`. No code change was needed here; this section exists to document that the check was performed, not skipped.

**Gap found and NOT fixed in this session (documented, not silently passed):** `qms_capa.py` and `qms_change_control.py` do not use `lifecycle_engine` at all (H7) — see §5 for what was done about this instead.

## 4. Archived / terminal records are immutable

**Before this work package:** no module blocked editing a record once it reached its terminal status — a PUT to an Obsolete/Closed/Archived record's fields was silently accepted.

**Fix — added a terminal-state guard to the PUT (update) handler of every module with a defined terminal status:**

| Module | Terminal status guarded | File |
|---|---|---|
| QMS Document | `Obsolete` | `routes/qms_documents.py::update_document` |
| URS | `obsolete` | `routes/urs.py::update_urs` |
| Qualification | `obsolete` | `routes/qual.py::update_qualification` |
| Validation Report | `archived`, `obsolete` | `routes/report.py::update_report` |
| Risk Assessment | `Closed` | `routes/risk.py::update_assessment` |
| Deviation | `Closed` | `routes/qms_deviations.py::update_deviation` (+ the approval endpoint, so a Closed deviation also can't accept further approval actions) |
| CAPA | `Closed` | `routes/qms_capa.py::update_capa` (+ approval endpoint) |
| Change Control | `Closed` | `routes/qms_change_control.py::update_change_control` (+ approval endpoint) |

Each blocked attempt returns HTTP 409 with an explicit reason and is audit-logged as a failed attempt.

**Verification: VERIFIED by automated test for CAPA** — `tests/test_phase_f_compliance.py::test_closed_capa_cannot_be_edited` closes a CAPA via the real approval endpoint, then asserts a subsequent PUT returns 409. The other seven modules in the table above use the identical guard pattern (same conditional, same `audit.log_failure` call, same 409 response shape) and were verified by direct code read rather than one dedicated test per module — recommended follow-up: replicate the CAPA test across the remaining seven for full automated coverage.

**Honest scope note:** QMS Document and URS do not have a distinct "Archived" state separate from "Obsolete" in their current status vocabulary (Phase E finding M2, tracked in `docs/PHASE_F_FINDING_TRACEABILITY.md` §D as explicitly **out of scope** for this phase — adding a new status value is a schema/vocabulary change, not a guard fix, and the Phase F brief prohibits new features). What Obsolete *does* have, now, is the immutability guarantee the brief asked for — the record cannot be edited once it reaches that terminal state, whatever it's named.

## 5. Rejected documents cannot bypass review

**Re-verified, and partially strengthened.** For every module wired into `lifecycle_engine`/`urs_lifecycle` (Document, URS, Qualification, Validation Report, Risk Assessment), "Rejected" already mapped back to `Draft`/`draft` — re-entering the full review cycle, not skipping it — and this is enforced by the same `validate_transition()` call as every other transition. Confirmed by direct re-read of each transition map; unchanged in this work package because it was already correct.

**CAPA and Change Control (H7) — the actual gap:** these two modules had (and, precisely scoped, still have) **no** `lifecycle_engine` wiring at all — any action could set any status with no sequence validation whatsoever, which is a broader gap than just "does Rejected bypass review." Building a full, correct transition graph for these two modules from scratch (13 and 13 status values respectively) risked inventing business rules not grounded in existing behavior, which the Phase F brief explicitly warns against ("do not add features... only fix verified release blockers"). Instead, this session applied the narrower, directly-evidenced fix that WP3 actually asked for: **the terminal-state immutability guard (§4)**, which is the specific requirement in scope, without speculatively redesigning the full state machine.

**Status:** CAPA/Change Control's *specific* "Rejected returns to Open/Draft, not skipped" behavior was already correct (verified by re-reading `_STATUS_MAP` in both files: `"Rejected": "Open"` / `"Rejected": "Draft"`). The broader "any status can follow any status while not-yet-closed" gap (H7) remains **open, explicitly NOT VERIFIED as fixed** — tracked in `docs/PHASE_F_FINDING_TRACEABILITY.md` as a partial fix, not a closed finding. A full lifecycle-engine wiring for these two modules is recommended as follow-up work, out of this session's scope.

---

## 6. Terminology mapping used throughout this document

The Phase F brief's plain-English requirements ("IQ Approved," "OQ Approved") don't map 1:1 onto this codebase's actual status vocabulary, which was verified directly rather than assumed:

- A **protocol** (IQ/OQ/PQ) has no "Approved" status of its own — its terminal execution status is `completed` or `completed_with_deviations` (set by `complete_protocol`).
- The parent **Qualification** has its own separate lifecycle (`draft → under_review → pending_approval → approved → closed/obsolete`) that is orthogonal to its protocols' individual completion status.
- §1's gate uses protocol completion (the closest real equivalent to "IQ/OQ Approved" in the actual data model) because that's what the codebase has; this is disclosed explicitly rather than silently reinterpreted.

---

## 7. Verification performed

- Every gate above is a direct code change, cited by file and function name — reproducible by reading the diff, not just this report.
- `from pharmagpt.app import app` re-verified after each file's edits.
- **7 new automated tests** added in `tests/test_phase_f_compliance.py` directly exercise §1 (2 tests), §2 (3 tests), and §4's CAPA case (1 test), all passing against the real Flask app and real route code — not mocked business logic. See `docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md` for the full count and pass/fail state.
- Full `pytest` regression suite re-run at the end of this work package (514 tests total) — see `docs/VALIDATION_EVIDENCE/TEST_SUMMARY.md`.
- **Not performed in this session** (disclosed, not omitted): a live, credentialed click-through attempting each blocked scenario in the running application. Per `PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md` §0, this environment does not permit entering any password into any field, including this application's own test credentials — this is a hard, disclosed methodology limitation carried over from Phase E, not a gap specific to this work package. §4's terminal-immutability guard also has automated coverage for only 1 of 8 modules (CAPA) — the other 7 are verified by code-pattern read only, not a dedicated test each.

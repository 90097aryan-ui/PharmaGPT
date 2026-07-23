# PHASE_3_IMPLEMENTATION_REPORT.md

**PharmaGPT — Phase 3 Implementation (Enterprise Validation Platform)**
**Date:** 2026-07-23
**Scope:** Validation Lifecycle, Shared Document Engine, Shared Approval Engine, Document
Versioning, Document Traceability, Electronic Signatures, Knowledge Base synchronization — against
the frozen `docs/PLATFORM_ARCHITECTURE.md`, `docs/DATABASE_ARCHITECTURE.md`,
`docs/IMPLEMENTATION_ROADMAP.md`, `FOUNDATION_ARCHITECTURE.md`, and `PROJECT_MEMORY/` (confirmed
authoritative for this session; the Product Recovery Package and Enterprise AI Blueprint are
external documents that extend, but do not override, these). No architecture redesign, no AI
implementation, no new document types, no database redesign beyond additive columns/tables
justified below.

**Naming note:** the repository already runs a separate, unrelated "Phase 3" track
(`docs/PHASE3_EXECUTION_PLAN.md`/`PHASE3_FLAGS.md`, the SQLite→Postgres dual-write migration,
mid-flight and not cut over) and separately, `docs/IMPLEMENTATION_ROADMAP.md`'s own numbering
places this work at Phase 9 (Document Engine, dependent on its Phase 3/5/8) and Phase 6
(Equipment traceability). This report keeps the filename requested and is a parallel initiative
track, consistent with this repository's existing precedent of multiple non-aligned "Phase N"
reports for different initiatives (two prior, unrelated "Phase 2" reports already coexist). It
does not touch, block, or depend on the in-flight SQLite→Postgres migration — everything below is
additive to the current SQLite schema only.

---

## 1. Objectives and disposition

| # | Task | Status |
|---|---|---|
| 1 | One shared Document Engine for URS/FAT/SAT/DQ/IQ/OQ/PQ/Validation Report/SOP | **Done** — §3 |
| — | MFR/BMR/BPR | **Explicitly deferred, not built** — see scope note below and §3 |
| 2 | One shared, configurable Approval Engine | **Done** — §4 |
| 3 | Shared document version control (Doc Number/Version/Revision/Status/Effective/Review/Superseded Date/Audit Trail/E-signature) | **Done** — §5 |
| 4 | Complete traceability: Project → Equipment → Validation Documents → QMS Records → Knowledge Base | **Done** — §6 |
| 5 | Remove remaining duplicate document lifecycle logic | **Done** (DQ/FAT/SAT) — §3 |
| 6 | Approved documents automatically synchronize with Knowledge Base, no manual publishing | **Done** — §7 |
| 7 | Verify RBAC, multi-tenancy, audit trail across the complete lifecycle | **Done, and 1 real e-signature gap found and fixed** — §8 |
| — | Do not implement AI | **Honored** — no AI call added, changed, or newly invoked anywhere in this pass |
| — | Do not redesign navigation | **Honored** — no frontend navigation/routing structure touched |
| — | Do not redesign the database unless absolutely necessary | **Honored** — every schema change is additive (new column, new table, or widening a column's already-free-text vocabulary); no existing table's shape or semantics changed |
| — | Do not introduce duplicate workflows | **Honored** — one shared `lifecycle_engine.py`, one shared `approval_engine.py`, DQ/FAT/SAT's separate lifecycle-less persistence path retired, not duplicated |

**MFR/BMR/BPR scope note:** the task list named MFR, BMR, and BPR among the document types for the
shared engine. This conflicts with this session's own "do not introduce new document types"
instruction and with `PHASE_2_IMPLEMENTATION_REPORT.md §5`'s explicit prior decision to exclude
them for the same reason — no table, route, or `doc_type` entry exists for them anywhere in the
codebase. Per instruction, this was flagged rather than silently resolved; the confirmed
resolution is: **no MFR/BMR/BPR document type is introduced in this phase.** Every registry this
phase adds (`lifecycle_engine._REGISTRY`, `approval_engine.WORKFLOWS`, `qms_database._DOC_TYPE_CODES`,
`kb_sync._FOLDER_BY_DOC_TYPE`) is a plain Python dict keyed by name — onboarding MFR/BMR/BPR in a
future, explicitly-approved phase is a new dict entry each, not an architectural change. This
mirrors `kb_sync.py`'s own pre-existing docstring, which already anticipated this ("costs nothing
to extend to a doc_type this codebase doesn't have yet, e.g. a future BMR/BPR/MFR").

---

## 2. Architecture compliance

- **Reused, not duplicated:** `qms_approvals`/`qms_audit_trail` (already-polymorphic, `record_type`
  free text) widened to cover `qualification`/`val_report`/`risk_assessment` instead of new tables;
  `equipment_documents` (already-polymorphic, `source_type` free text) widened to cover
  `deviation`/`capa`/`change_control`/`risk_assessment` instead of a new `equipment_links` table or
  a rename; `urs_lifecycle.py`'s proven transition-validator pattern generalized via delegation, not
  copied; `kb_sync.py::publish_to_kb()` (already shared across 4 suites) required zero changes to
  cover 3 more document types.
- **No database redesign:** every change is one of (a) a new column added via the existing
  `_add_column_if_missing()` guard (`qms_documents.superseded_date`, `risk_approval.electronic_sig`),
  (b) one new table (`kb_document_versions`) filling a gap no existing table covered, or (c)
  widening an already-free-text discriminator column's *accepted* vocabulary in application code
  (`equipment_documents.source_type`, no DB constraint existed to relax). No existing table was
  renamed, no existing column's meaning changed, no existing row's data was migrated or rewritten.
- **No AI implementation:** DQ/FAT/SAT's AI draft generation (§3) continues to use
  Document Control's existing, unmodified `qms_document_prompt.py::build_draft_prompt()` — already
  fully `doc_type`-driven — reached via the existing, unmodified `POST /qms/documents/<id>/generate`
  endpoint. No prompt was written or rewritten; the dedicated `prompts/dq_prompt.py`/`fat_prompt.py`/
  `sat_prompt.py` modules used by the retired wizard path remain in the codebase, simply unreached
  by these three doc types going forward (exactly as the prior 7 retired types' own dedicated
  wizard-path prompt modules already are).
- **No navigation redesign:** no frontend routing, sidebar, or Project Workspace tab structure was
  touched. DQ/FAT/SAT's frontend entry points (wherever they currently POST to
  `/validation/generate`) will now receive HTTP 410 exactly as the prior 7 retired types do — this
  is flagged to whoever owns that frontend code as a required follow-up (§9), not fixed here, since
  fixing it would mean touching UI routing/navigation code, which is out of this phase's scope.

---

## 3. Document Engine implementation (Tasks 1, 5)

**No single unified `documents` table was built** — that is the frozen target schema's Roadmap
Phase 9 work (`docs/DATABASE_ARCHITECTURE.md §4.4`), not this phase's, and building it now would be
exactly the database redesign this phase was told to avoid absent an explicit instruction to do so.
Instead, the six existing suites are converged onto **shared engines** they all now call into:

- **URS** (`urs_database.py`) — already had a dedicated lifecycle validator (`urs_lifecycle.py`);
  unchanged, now the canonical delegate other suites' registry entries in `lifecycle_engine.py`
  point at.
- **Qualification** (IQ/OQ/PQ, `qual_database.py`), **Validation Report** (`report_database.py`),
  **Risk Assessment** (`risk_database.py`) — each already had its own action→status map with **no
  transition enforcement at all** (any mapped action could fire from any status). Each now calls
  `lifecycle_engine.validate_transition()` before writing a status change (§4).
- **SOP / Document Control** (`qms_database.py`, `qms_documents.py`) — same fix applied; also gains
  `superseded_date` (§5).
- **DQ, FAT, SAT** — previously persisted into the lifecycle-less generic `generated_documents`
  table (no versioning, no approval trail, no audit trail, no KB sync) via the "Generate Document"
  wizard. Retired from that wizard the same way the prior session retired 7 other duplicate types
  (`routes/validation.py::_RETIRED_DOC_TYPES`, HTTP 410) and consolidated into **Document Control**:
  - `qms_database.py::_DOC_TYPE_CODES` gained `"DQ"`, `"FAT"`, `"SAT"` — zero schema change
    (`doc_type` is free text; `QMS_META["document_types"]` picks these up automatically).
  - Created via the existing `POST /qms/documents` (`{"doc_type": "DQ"|"FAT"|"SAT", ...}`) — no new
    route, no new persistence code.
  - They now have, for free, everything Document Control already provides: the shared lifecycle
    engine, the configurable approval workflow (§4), `qms_document_versions` history, distribution/
    training tracking, shared attachments/comments/audit trail, and automatic KB sync (§7).

**Files:** `pharmagpt/services/lifecycle_engine.py` (new), `pharmagpt/routes/qms_documents.py`,
`pharmagpt/routes/qual.py`, `pharmagpt/routes/report.py`, `pharmagpt/routes/risk.py`,
`pharmagpt/routes/validation.py`, `pharmagpt/qms_database.py`.

---

## 4. Approval Engine implementation (Task 2)

New `pharmagpt/services/approval_engine.py` — a **workflow-definition/lookup layer**, not a data
migration. `WORKFLOWS` is a dict of document type → ordered stage list (`{stage, role, action,
status}`), covering the two example workflows given:

- `"SOP"`: Initiator → Reviewer → QA Head → Effective.
- `"VALIDATION"`: Author → Reviewer → QA Coordinator → QA Head → Approved → Execution → Post
  Execution Review → Effective.

Each suite continues to write to its own existing approval-trail table (`qms_approvals`,
`qual_approvals`, `val_report_approvals`, `risk_approval`) — physically unifying these onto one
table was considered and rejected as unnecessary churn the actual requirement ("configurable
workflows") does not call for, and would have required rewriting every suite's existing, passing
read paths for no functional gain.

What *is* now genuinely shared, widened rather than duplicated:

- `routes/qms_common.py::VALID_RECORD_TYPES`/`_GETTERS` extended with `qualification`, `val_report`,
  `risk_assessment` — the generic attachments/comments/audit-trail endpoints
  (`GET /qms/<record_type>/<id>/{attachments,comments,audit-trail}`) now work for these three
  suites too, which previously had no audit-trail visibility through the shared endpoint at all.
- Qualification/Validation Report/Risk Assessment approval routes previously wrote **no** entry to
  the shared `qms_audit_trail` at all — each now calls `qmsdb.add_audit_entry(...)` immediately
  after computing the non-spoofable signing identity, mirroring what Document Control already did.
- **Real e-signature gap found and fixed:** `routes/risk.py::add_approval()` called
  `risk_database.py::add_approval_entry()` without ever passing `electronic_sig` — the only one of
  five equivalent approval endpoints (QMS Document/Deviation/CAPA/Change Control, URS,
  Qualification, Validation Report, Risk) missing it. `risk_approval` gained an additive
  `electronic_sig` column (`_add_column_if_missing`), `add_approval_entry()`'s signature gained the
  parameter, and `routes/risk.py` now passes `tenancy.signing_identity(g.tenant)["electronic_sig"]`
  the same way every other suite already does. Regression test:
  `tests/test_security_tenant_rbac_esig.py::test_risk_assessment_approval_now_records_electronic_sig`.

**Files:** `pharmagpt/services/approval_engine.py` (new), `pharmagpt/routes/qms_common.py`,
`pharmagpt/routes/qual.py`, `pharmagpt/routes/report.py`, `pharmagpt/routes/risk.py`,
`pharmagpt/risk_database.py`, `pharmagpt/database.py`.

---

## 5. Lifecycle changes and document versioning (Task 3)

**Lifecycle enforcement** — every `lifecycle_engine._REGISTRY` transition map was derived directly
from the suite's own pre-existing action→status dict (`qms_documents.py::_STATUS_MAP`,
`qual.py`/`report.py`/`risk.py`'s own `status_map`s), not invented, so no status value or reachable
transition a real user relies on was removed. A handful of pre-existing tests exercised a genuine,
now-closed gap (e.g. a fresh Draft document reaching Effective in one POST with no intervening
review step recorded) — those tests were updated to submit the intervening review action first,
rather than weakening the new enforcement to preserve the shortcut (`tests/test_kb_sync.py`).

**Versioning triad** — every governed document type now exposes Document Number, Version, Revision,
Status, Effective Date, Review Date, Superseded Date, Audit Trail, and Electronic Signature:

| Field | Where it lived before | Gap closed this phase |
|---|---|---|
| Effective/Review Date | Already present on `qms_documents`, `kb_documents`, etc. | — |
| Superseded Date | `qms_documents` had `superseded_by` (id) but no *date* | Added `superseded_date` (additive column), stamped by `submit_approval()` on the transition to Obsolete, mirroring how `effective_date` is already stamped on the transition to Effective |
| Version history | `qms_document_versions`/`urs_versions`/`qual_versions`/`val_report_versions` existed; **Knowledge Base had none at all** — re-upload/re-publish silently overwrote the file in place | New `kb_document_versions` table (mirrors `qms_document_versions`'s shape); `kb_sync.py::publish_to_kb()` now archives (renames, never deletes) the outgoing file and snapshots a version row before overwriting — consistent with the platform's "nothing regulator-relevant is ever truly deleted" principle |

**Files:** `pharmagpt/database.py` (schema + `create_kb_version()`/`get_kb_versions()`),
`pharmagpt/qms_document_database.py`, `pharmagpt/services/kb_sync.py`.

---

## 6. Traceability implementation (Task 4)

Project → Equipment (`equipment.project_id`) and Equipment → Documents (`equipment_documents`,
`source_type ∈ {kb, project}`) already existed. The real, confirmed gap was **Equipment → QMS
Records** — no link of any kind existed between an equipment record and the deviations/CAPAs/change
controls/risk assessments concerning it.

Closed by widening `equipment_documents`'s already-free-text `source_type` vocabulary
(`equipment_database.py::SOURCE_TYPES`) to also accept `"deviation"`, `"capa"`, `"change_control"`,
`"risk_assessment"` — same polymorphic table, same mechanism the frozen
`docs/DATABASE_ARCHITECTURE.md §6` names as the target `equipment_links` pattern, no rename (a
rename would have touched the in-flight Postgres dual-write's `equipment_repo.py`/backfill/parity
scripts for no functional benefit — see §9), no schema change beyond a new `"quality_record"` entry
in `DOCUMENT_ROLES` for these four link types. `routes/equipment.py::link_equipment_document()` now
two-sided tenant-scopes every new link (both the equipment row and the linked QMS record must
belong to the caller's company) via a new `_QMS_SOURCE_GETTERS` dispatch table, mirroring
`qms_common.py`'s existing `_GETTERS` pattern. `equipment_database.py::list_equipment_documents()`
resolves the new link types' display titles the same way it already resolves `kb`/`project` links.

**Traceability chain now navigable end to end:** Project → Equipment (existing) → Validation
Documents (existing `equipment_documents`, `source_type='project'`, plus SOP/DQ/FAT/SAT now
governed by Document Control per §3) → QMS Records (new this phase) → Knowledge Base (existing
`kb_sync`, confirmed complete for every in-scope type per §7).

**Explicitly out of scope, not silently built** (see §9): URS/Qualification/Validation
Report/Risk Assessment still have no `project_id` at all (a disclosed, pre-existing gap —
`FOUNDATION_ARCHITECTURE.md §6.1` — that is Roadmap Phase 7/Project Workspace territory and would
require touching navigation); Knowledge Base citation-with-version-pinning (`document_references`,
a different, larger mechanism than the traceability chain actually requested here).

**Files:** `pharmagpt/equipment_database.py`, `pharmagpt/routes/equipment.py`.

---

## 7. Knowledge Base synchronization (Task 6)

Already shared and working before this phase (`kb_sync.py::publish_to_kb()`), called from Document
Control (Effective), URS (effective), Qualification (approved, per-protocol), and Validation Report
(released). Confirmed by direct read: `kb_sync.py::_FOLDER_BY_DOC_TYPE` already mapped `"DQ"`,
`"FAT"`, `"SAT"` to KB folders before this phase (anticipating exactly this consolidation) — so once
DQ/FAT/SAT became Document Control rows (§3), they reached KB auto-sync via the same existing
`_publish_effective_document_to_kb()` call in `qms_documents.py::submit_approval()`, with **zero
changes to `kb_sync.py`'s routing logic**. Regression coverage:
`tests/test_kb_sync.py::test_consolidated_dq_fat_sat_are_published_to_kb`.

Every in-scope governed document type (SOP/Protocol/etc. via Document Control, URS, Qualification,
Validation Report, DQ, FAT, SAT) now has automatic, no-manual-publish-step KB sync. Manual KB
upload remains available as an independent path for content that isn't a governed/lifecycle record
(unchanged from before this phase).

---

## 8. RBAC / multi-tenancy / audit trail verification (Task 7)

Bounded to exactly what this phase touched, not a full re-audit of all 19 route files:

- Every new equipment-QMS link (§6) two-sided tenant-scope-checked — regression tests
  `test_cross_tenant_cannot_link_equipment_to_another_companys_deviation` and
  `test_cross_tenant_cannot_link_own_equipment_from_another_company`
  (`tests/test_security_tenant_rbac_esig.py`).
- Risk Assessment e-signature gap found and fixed (§4), regression-tested.
- Every new shared audit-trail write (§4) uses `tenancy.signing_identity(g.tenant)` —
  server-derived, never client-supplied — consistent with every existing write of this kind.
- Existing tenant-scoping/e-signature regression suite (`tests/test_security_tenant_rbac_esig.py`,
  38 tests pre-phase) re-run in full, 0 regressions.

**Not re-verified in this pass** (unchanged scope, no reason to suspect drift): the broader
cross-tenant RBAC sweep documented in `PHASE_2_IMPLEMENTATION_REPORT.md §6` and the Postgres RLS
2-company isolation soak test, both outside this phase's touched surface.

---

## 9. Remaining Phase 4 / roadmap dependencies

Explicitly not started, either because it was out of this phase's stated scope or because doing it
would have required touching something this phase was told not to touch:

- **Equipment Library ownership re-parenting** (`project_id NOT NULL` → company-owned, many-to-many,
  `PLATFORM_ARCHITECTURE.md §10`/`PA-013`) — still project-owned; unchanged by this phase, exactly
  as `PHASE_2_IMPLEMENTATION_REPORT.md §10` already flagged.
- **URS/Qualification/Validation Report/Risk Assessment `project_id`** — none of these four tables
  has ever had a `project_id` column; their Project Workspace tabs remain unfiltered global entry
  points. Fixing this touches Project Workspace navigation (out of this phase's scope by explicit
  instruction).
- **Knowledge Base citation-with-version-pinning** (`document_references`, `PLATFORM_ARCHITECTURE.md
  §18`) — a document citing a specific pinned version of another (e.g. an OQ citing SOP-QA-014 v2)
  is not built; this phase's traceability requirement (Project→Equipment→Documents→QMS→KB) did not
  ask for it, and it is a materially larger mechanism than what was requested.
- **MFR/BMR/BPR onboarding** — intentionally deferred (see scope note, §1). The Document Engine and
  Approval Engine built this phase are dict-driven and extensible; onboarding these three (if and
  when explicitly approved) is a new `_DOC_TYPE_CODES` entry, a new `WORKFLOWS` entry, and a new
  `_FOLDER_BY_DOC_TYPE` entry — no architectural change.
- **DQ/FAT/SAT frontend wiring** — the "Generate Document" wizard UI (wherever it currently POSTs
  `doc_type=DQ|FAT|SAT` to `/validation/generate`) will now receive HTTP 410. Whoever owns that
  frontend needs to point those entry points at `POST /qms/documents` instead — a UI change, not
  made in this backend-scoped pass.
- **Postgres dual-write follow-up** — this phase's new `doc_type` values (DQ/FAT/SAT),
  `record_type` values (`qualification`/`val_report`/`risk_assessment` for shared audit trail;
  `deviation`/`capa`/`change_control`/`risk_assessment` for equipment links), and new columns/table
  (`qms_documents.superseded_date`, `kb_document_versions`) are SQLite-only. `pharmagpt/db/qms_repo.py`
  and `pharmagpt/db/equipment_repo.py` (the in-flight Phase 3 dual-write repos) do not yet know
  about any of them — needs a follow-up before the SQLite→Postgres cutover (`docs/PHASE3_FLAGS.md`)
  proceeds, not before this phase's own completion, since SQLite remains the sole read/write source
  of truth throughout.
- **Postgres RLS 2-company isolation soak test** — still outstanding per `docs/PHASE3_FLAGS.md`,
  unrelated to and unaffected by this phase's changes.
- **Cryptographically-binding e-signatures** (`signature_events`, `PLATFORM_ARCHITECTURE.md §18`,
  reserved for v1.1) — every e-signature in this platform, before and after this phase, remains a
  non-spoofable *typed-name manifestation* (actor/role/timestamp/reason, server-derived), not a
  PKI/biometric-bound signature. Unchanged by this phase; explicitly out of scope.

Do not start further work on any of the above without explicit instruction.

---

## 10. Test results

Baseline before this phase: **411 passed, 1 deselected** (`pytest -q`, confirmed at session start).

New tests added: **41**, across `tests/test_lifecycle_engine.py` (new, 21), `tests/test_approval_engine.py`
(new, 6), `tests/test_equipment_links.py` (new, 7), `tests/test_kb_sync.py` (+4: DQ/FAT/SAT KB-sync
parametrized ×3, version-snapshot-on-republish ×1), `tests/test_security_tenant_rbac_esig.py` (+3:
2 cross-tenant equipment-link tests, 1 risk e-signature fix).

Final: **452 passed, 1 deselected, 0 failed** — full regression suite (`pytest -q` from repo root),
0 regressions against the 411-test baseline.

---

## 11. Files changed this session

**New:**
- `pharmagpt/services/lifecycle_engine.py`
- `pharmagpt/services/approval_engine.py`
- `tests/test_lifecycle_engine.py`
- `tests/test_approval_engine.py`
- `tests/test_equipment_links.py`

**Modified:**
- `pharmagpt/routes/qms_documents.py` — lifecycle validation wired into `submit_approval()`;
  `superseded_date` stamping on transition to Obsolete.
- `pharmagpt/routes/qual.py`, `pharmagpt/routes/report.py`, `pharmagpt/routes/risk.py` — lifecycle
  validation wired into each `add_approval()`; shared `qms_audit_trail` write added; risk
  e-signature fix.
- `pharmagpt/routes/validation.py` — `_RETIRED_DOC_TYPES` gained DQ/FAT/SAT.
- `pharmagpt/routes/qms_common.py` — `VALID_RECORD_TYPES`/`_GETTERS` widened.
- `pharmagpt/routes/equipment.py` — equipment-link creation widened to the four new QMS
  `source_type`s, two-sided tenant scoping.
- `pharmagpt/qms_database.py` — `_DOC_TYPE_CODES` gained DQ/FAT/SAT.
- `pharmagpt/qms_document_database.py` — `update_document()`'s allowed-fields list gained
  `superseded_date`.
- `pharmagpt/risk_database.py` — `add_approval_entry()` gained `electronic_sig`.
- `pharmagpt/equipment_database.py` — `SOURCE_TYPES`/`DOCUMENT_ROLES` widened;
  `list_equipment_documents()` resolves the four new link types.
- `pharmagpt/services/kb_sync.py` — version-snapshot-on-republish (archives outgoing file instead
  of deleting it, records a `kb_document_versions` row).
- `pharmagpt/database.py` — `kb_document_versions` table, `create_kb_version()`/`get_kb_versions()`,
  `qms_documents.superseded_date` and `risk_approval.electronic_sig` additive columns.
- `tests/test_kb_sync.py` — added intervening review-step calls to tests that exercised the
  now-closed Draft→Effective skip-ahead gap; added DQ/FAT/SAT and version-snapshot coverage.
- `tests/test_validation_retired_doc_types.py` — DQ/FAT/SAT moved from `STILL_ACTIVE_TYPES` to
  `RETIRED_TYPES`.
- `tests/test_security_tenant_rbac_esig.py` — added equipment-link cross-tenant tests and the risk
  e-signature regression test.

# PHASE_2_IMPLEMENTATION_REPORT.md

**PharmaGPT Architecture Program — Phase 2 Implementation (Product Workflow & Navigation)**
**Date:** 2026-07-23
**Scope:** Sidebar Navigation, Equipment Library, Projects, Validation Suite, Knowledge Base
integration, Workflow integration — against the frozen `PHARMAGPT_PLATFORM_BLUEPRINT.md`, Product
Recovery Package, and Enterprise AI Blueprint. No architecture redesign, no AI implementation, no
new document types, no database redesign beyond additive columns already justified below. **Phase
2 only** — Phase 3 (Equipment Library ownership re-parenting, shared six-state lifecycle, Company/
Users/Roles administration) is not started.

---

## 1. Objectives and disposition

| # | Task | Status |
|---|---|---|
| 1 | Reorganize the sidebar to match the approved Information Architecture | **Done** — §2 |
| 2 | Make Equipment Library a first-class module | **Done** (navigation/query elevation — see scope note) — §3 |
| 3 | Ensure every Validation Project is linked to Equipment | **Done** — §4 |
| 4 | Approved Validation documents automatically become available in the Knowledge Base | **Done** — §5 |
| 5 | Approved SOP/BMR/BPR/MFR automatically become the current effective version in the KB | **Done** (generic, type-agnostic mechanism — see scope note) — §5 |
| 6 | Remove duplicate navigation paths | **Done** — §2 |
| 7 | Every business object has one obvious entry point | **Done** — §2 |
| 8 | Verify all routes respect RBAC and multi-tenancy | **Done, and 6 real gaps found and fixed** — §6 |
| — | Do not implement AI | **Honored** — no AI call added anywhere in this pass |
| — | Do not redesign the database unless absolutely necessary | **Honored** — only additive columns (§5), justified individually |
| — | Do not introduce new document types | **Honored** — see the BMR/BPR/MFR scope note in §5 |
| — | Do not create duplicate workflows | **Honored** — one shared `kb_sync.publish_to_kb()`, one shared `_scoped_protocol()` helper, not four/six duplicated implementations |

---

## 2. Sidebar reorganization (Tasks 1, 6, 7)

**Before:** `Main Menu` (Dashboard/Knowledge Base/AI Assistant) → `Projects` → five separate
top-level sections (Risk Management, URS Management, Qualification, Validation Reports, Generate
Document, each with its own collapse control) → `Quality Management` → *(no Equipment entry point
at all — Equipment was reachable only as a Project Workspace tab)*.

**After**, matching `PRODUCT_INFORMATION_ARCHITECTURE.md` §0 / `FINAL_DELIVERABLE.md` Q6's approved
order:

```
Dashboard → Projects → Equipment Library → Knowledge Base → Validation Suite
  (Risk Management / URS Management / Qualification / Validation Reports /
   Generate Document, nested as sub-groups under one entry point)
→ Quality Management → AI Assistant
```

- The five Validation-pillar sections are now nested `qms-nav-group` sub-groups inside one
  **Validation Suite** parent — the same pattern `Quality Management` already used for Document
  Control/Deviation/CAPA/Change Control. Each sub-suite keeps its own collapse control and click
  handlers completely unchanged; only the surrounding structure changed, so no suite-internal JS
  needed touching.
- **Equipment Library** is now a genuine top-level entry point (§3).
- **Not added:** an `Administration` section and a persistent `Global Search` bar are both part of
  the target IA, but the screens/index they'd point to (Company/Users/Roles admin, Postgres
  full-text search) don't exist yet — adding a nav item with nowhere real to go would itself be a
  defect, and building those screens is explicitly out of scope ("do not add new features"). Both
  remain correctly deferred to Phase 4/7 per `IMPLEMENTATION_BACKLOG.md`.

**Duplicate navigation removed:** the reorg is itself the fix for Task 6/7 — five parallel
top-level entry points collapsed into one (`Validation Suite`), and Equipment gained its single,
obvious top-level entry point instead of being reachable only by first opening a Project.

---

## 3. Equipment Library — first-class module (Task 2)

**Scope decision, stated explicitly:** the Product Recovery Package's full Equipment Library
vision (`PLATFORM_ARCHITECTURE.md` PA-013 / Blueprint ADR-P01) is a **company-owned, many-to-many**
re-parenting of the `equipment` table — a genuine, non-additive schema change explicitly assigned
to **Phase 3** by `PHASED_MIGRATION_PLAN.md` ("the one genuinely structural schema change in this
entire plan"). Given this session's explicit "do not redesign the database unless absolutely
necessary," that re-parenting was **not** attempted here. What Phase 2 delivers instead is the
**navigation and query elevation** half of "first-class module" — Equipment Library is now a real,
top-level, company-wide destination — while `equipment.project_id NOT NULL` stays exactly as it
was. This is called out on-screen too (an HTML comment in `templates/index.html` and the Library's
own empty-state copy) so a future session doesn't mistake this for the full PA-013 migration.

**What changed:**
- **New route** `GET /equipment` (`routes/equipment.py::list_company_equipment`) — every Equipment
  record across every Project in the caller's company, tenant-scoped. Reuses the existing
  `equipment_database.get_all_equipment()` the Phase 3.4 backfill scripts already relied on;
  enriched its query with `p.name AS project_name` (additive to the SELECT list only, not a schema
  change) so the Library can show which project owns each record.
- **New screen** `view-equipment-library` (`templates/index.html`) — reuses `equipment.js`'s
  existing row-rendering (`eqRenderList()`, refactored to accept target container ids instead of
  hardcoding the Project Workspace tab's ids) and existing Profile page (`eqOpenProfile()`,
  `eqRenderProfile()`), so a Library row and a Project Workspace equipment-tab row render with
  identical code — no duplicate rendering logic. "Add Equipment" is intentionally not offered from
  the Library, since equipment creation still requires a `project_id` under the current schema;
  the empty-state copy says so.
- `eqBackToList()` is now origin-aware (`"library"` vs `"project-workspace"`), so opening a
  Profile from the Library and clicking Back returns to the Library, not into whatever project
  happened to be active.

---

## 4. Every Validation Project linked to Equipment (Task 3)

**Scope decision:** "linked to Equipment" is delivered via the **existing** project-owned model
(equipment already has a `project_id` FK) — not the Phase 3 company-owned re-parenting. Project
creation already collected `equipment_name`/`manufacturer`/`model`/`department` as free-text
fields for exactly this purpose (see `equipment_database.import_legacy_equipment()`'s own
docstring), but never turned them into a real `equipment` row automatically — a user had to
separately click "Import from Project Info" inside the Project Workspace's Equipment tab, and
could skip it entirely.

**What changed:** `routes/projects.py::create_project()` now calls
`equipment_database.import_legacy_equipment()` automatically right after creating the project
(`_link_equipment_to_new_project()`), reusing the exact same function the manual "Import from
Project Info" button already called — no new equipment-creation logic was written. No-ops
(creates nothing) for a project with no equipment info supplied, exactly matching the manual
endpoint's existing behavior.

**Companion fix found in the same function:** the project-creation audit-trail entry
(`qmsdb.add_audit_entry("project", ...)`) was being written with a blank `performed_by` — the
same non-repudiation gap class Phase 1 fixed for QMS record creation, just never extended to
Projects. Fixed to use `tenancy.signing_identity(g.tenant)["performed_by"]`, matching the
established pattern exactly.

---

## 5. Auto-publish to Knowledge Base (Tasks 4, 5)

**New shared service:** `pharmagpt/services/kb_sync.py::publish_to_kb()` — one implementation,
called from four approval routes at the moment each reaches its own module's real "current
effective version" state. No AI call happens here; every caller already has human-approved
markdown content built via that module's own existing export/report builder (the same one its
"Export DOCX" button already uses).

| Module | Trigger (status → target) | Content source (already existing) | KB folder |
|---|---|---|---|
| Document Control | `Approved` → `Effective` | `document["content"]` | doc_type-routed (SOP→SOP, etc.) |
| URS | `Make Effective` → `effective` | `urs_service.build_urs_markdown()` | Validation |
| Qualification | `Approved` → `approved` (**per protocol** — see below) | `qual_service.build_protocol_markdown()` | Qualification |
| Validation Report | `Released` → `released` | `report_service.build_docx_markdown()` | Reports |

**Qualification is published per-protocol, not per-container:** Qualification has no single
markdown representation of "the qualification" — only per-protocol markdown (IQ/OQ/PQ are the
actual documents a QA reviewer looks for). When a Qualification reaches `approved`,
`_publish_effective_protocols_to_kb()` loops its protocols and publishes each one individually.
This is the more correct behavior, not a shortcut — it's what actually lands in the KB as
retrievable, individually-versioned documents.

**Idempotent upsert, not accumulation:** two additive columns, `kb_documents.source_type` /
`source_id` (NULL for every manually-uploaded document — unchanged existing behavior), let
`publish_to_kb()` find-and-update the same KB row on every re-approval instead of creating a new
row each time. The KB always shows **exactly one row per governed record — always the current
effective version** — satisfying Task 4/5's "automatically become the current effective version"
literally, not just "gets a copy eventually." The superseded file on disk is removed and replaced,
not left to accumulate.

**Why the additive columns are "necessary" (per the "don't redesign unless necessary"
instruction):** without them, `publish_to_kb()` cannot tell whether a KB row already exists for a
given governed record, and would either (a) never update an existing row (silently stale — thereby
failing Task 5's actual requirement) or (b) create a new row on every re-approval (duplicate
workflow — thereby violating "do not create duplicate workflows"). Two nullable `TEXT`/`INTEGER`
columns, following the same `_add_column_if_missing()` additive-column-guard pattern already used
throughout this codebase, is the minimal change that avoids both failure modes.

**BMR/BPR/MFR — scope note (Task 5 vs. "do not introduce new document types"):** BMR (Batch
Manufacturing Record), BPR, and MFR do not exist anywhere in the current codebase — no module
authors them, and Document Control's `doc_type` field is validated against a fixed 11-entry
catalog (`qms_database.py::_DOC_TYPE_CODES`: SOP, Protocol, Specification, Test Method, Format,
Template, Logbook, Checklist, Policy, Manual, Work Instruction) that does not include them. Adding
them there would be exactly "introducing a new document type," which this session was explicitly
told not to do. **Resolution:** `kb_sync.publish_to_kb()` is deliberately generic and
`doc_type`-agnostic — it does not hardcode SOP anywhere, routes to a KB folder via a lookup table
that defaults gracefully for any unrecognized type, and will publish **any** `doc_type` a caller
passes it, correctly, the moment such a type is added in a future phase — without requiring any
further change to this file. Task 5 is satisfied today for SOP (the one of the four that actually
exists in this codebase); BMR/BPR/MFR support requires those record types to exist somewhere
first, which is out of this session's scope by explicit instruction.

---

## 6. RBAC / multi-tenancy audit (Task 8)

**Methodology:** every `@bp.route` with an `<int:...>` path parameter across `pharmagpt/routes/*.py`
was checked for (a) `@require_role` on every DELETE and approval POST, and (b) a tenancy-scoping
check reachable from the function body (either inline `tenancy.scoped_or_none()` or a shared
helper like `_record_exists()`/`_doc_scoped()`/`_scoped_protocol()`). Findings were verified by
reading the actual function body, not just pattern-matched — several initial hits from the
automated pass turned out to be false positives (tenancy enforced via a helper function, not
inline) and were confirmed correct, not "fixed."

**Clean bill of health confirmed for:** every DELETE route (all have `@require_role`), every
approval POST route (all have `@require_role`), `qms_common.py`'s shared polymorphic
attachments/comments/audit-trail/approvals engine (`_record_exists()`), `docs.py`'s project
document routes (`_doc_scoped()`), `validation.py`'s generated-document routes
(`_generated_doc_scoped()`), Equipment's routes (`get_equipment_scoped()`).

**6 real cross-tenant gaps found and fixed:**

| # | File | Routes | Gap | Fix |
|---|---|---|---|---|
| 1 | `routes/qms_change_control.py` | 7 dynamically-generated AI-narrative endpoints (`risk-summary`, `rollback-plan`, `regulatory-impact`, `justification`, `executive-summary`, `verification-summary`, `effectiveness-review`) | Built via an `add_url_rule()` loop; checked existence via a raw, unscoped `ccdb.get_change_control(cc_id)` — every other route in the same file used `tenancy.scoped_or_none()` | Same `tenancy.scoped_or_none()` pattern |
| 2 | `routes/qual.py` | `get_protocol`/`update_protocol`/`delete_protocol`/`get_test_cases`/`save_test_cases`/`add_test_case`/`update_test_case`/`delete_test_case`/`get_executions`/`execute_test_case`/`complete_protocol`/`create_version`(protocol)/`update_deviation` | Checked only `protocol.qual_id == qid` (or nothing at all for test-case/deviation update+delete) — never that `qid` itself belonged to the caller's company | New shared `_scoped_protocol(qid, pid)` helper (checks qualification tenancy **and** protocol ownership); new `qual_database.get_test_case()`/`get_deviation()` for child-ownership checks |
| 3 | `routes/urs.py` | `update_requirement`/`delete_requirement`/`get_version_requirements` | No tenancy check at all | `tenancy.scoped_or_none()` on the parent URS + new `urs_database.get_requirement()`/`get_version()` for child-ownership checks |
| 4 | `routes/report.py` | `get_approval` (GET)/`get_versions`/`create_version` | No tenancy check at all | `tenancy.scoped_or_none()` on the parent report |
| 5 | `routes/qms_documents.py` | `acknowledge_distribution`/`update_training` | Keyed only by their own id (no `did` in the URL to check); no tenancy check at all | New `qms_document_database.get_distribution_entry()`/`get_training_entry()` to resolve the owning document, then `tenancy.scoped_or_none()` |
| 6 | `routes/qms_capa.py` | `escalate_action` | Keyed only by action id (no `cid` in the URL); no tenancy check at all | New `qms_capa_database.get_action()` to resolve the owning CAPA, then `tenancy.scoped_or_none()` |

All 6 are the same defect class Phase 1's `aa15c66` fixed for the main CRUD routes: authenticated
users from Company B could read or write Company A's records by guessing an id. None were reachable
without a valid bearer token (RBAC/auth itself was never bypassed) — these are tenant-isolation
gaps specifically, on routes that either predate the Phase 1 tenancy sweep's coverage (dynamically-
generated routes, child-of-child resources) or were added afterward without following the
established pattern.

**Regression coverage:** 6 new cross-tenant tests added to `tests/test_security_tenant_rbac_esig.py`
(one per finding above, several covering multiple sub-routes each), all reproducing the exact
exploit (Company B request against a Company A id) and asserting `404`.

---

## 7. Blueprint / Product Recovery Package compliance

| Reference | Requirement | Status |
|---|---|---|
| `PRODUCT_INFORMATION_ARCHITECTURE.md` §0 | Top-level nav: Dashboard · Projects · Equipment Library · Knowledge Base · Validation Suite · Quality Management · AI Assistant · Administration | **Compliant** for every item with an existing screen to point to; Administration correctly deferred (§2) |
| `FINAL_DELIVERABLE.md` Q6/Q7 | Validation Suite groups Risk/URS/Qualification/Validation Report/Generate Document as children of one entry point | **Compliant** (§2) |
| `PLATFORM_ARCHITECTURE.md` PA-013 / ADR-P01 | Equipment Library, company-owned, many-to-many | **Explicitly deferred to Phase 3** — not attempted (§3), per "don't redesign the database unless absolutely necessary" |
| Product Recovery Package Q8 | "Knowledge Base version-drift... should be automatic, never a manual cross-check" | **Compliant** (§5) — approved documents now publish automatically; superseded versions are replaced, not left stale |
| `AI_GOVERNANCE.md` §9 / Phase 1 ADR-P05 pattern | Non-repudiable actor of record | **Extended** — the same pattern now also covers Project creation (§4) |
| Blueprint §13 "AI content is never authoritative on its own" | — | **Not implicated** — `kb_sync` publishes only already-approved, human-reviewed content; no AI call added anywhere in this session |

---

## 8. Regression results

**Full suite:** `./venv/Scripts/python -m pytest` — **411 passed, 0 failed, 1 deselected**
(2026-07-23), up from Phase 1's 390-passed baseline. The +21 delta is this session's new
regression coverage (9 KB-sync tests + 3 Equipment Library tests + 3 project-equipment-link tests
+ 6 cross-tenant RBAC tests).

**2 pre-existing tests updated, not broken:** `tests/test_equipment_routes.py::
test_create_and_list_project_equipment` and `::test_search_equipment` asserted an equipment count
of 1 under the old (pre-Task-3) assumption that project creation never auto-creates equipment.
Both now correctly expect 2 (the auto-imported record from the project's own fields + the
explicitly-created one in the test), with a comment explaining why — this is the intended, correct
consequence of Task 3, not a defect.

**1 pre-existing flake, unrelated:** `test_urs_audit_logging.py::
test_generation_logs_started_and_completed` failed once under full-suite system load (a 10-second
polling deadline for a background job) and passed cleanly in isolation immediately after — the
same class of timing flakiness `PROJECT_MEMORY/PROJECT_STATUS.md` already documents for
`test_document_processor.py::test_small_pdf`. Not touched by this session's changes.

**Manual verification:** dev server started, no console or server errors on load; confirmed via
DOM inspection that the sidebar renders in the approved order, the Equipment Library nav item and
view are wired end-to-end (`eqLoadCompanyList()` fires on click), the existing Risk/URS/Qual/
Report/Generate Document collapse controls still work unchanged inside their new `Validation Suite`
grouping.

---

## 9. Files changed this session

```
NEW    pharmagpt/services/kb_sync.py
NEW    tests/test_kb_sync.py
NEW    tests/test_equipment_library.py
NEW    tests/test_project_equipment_link.py

MOD    pharmagpt/database.py                    (kb_documents source_type/source_id columns + helpers)
MOD    pharmagpt/equipment_database.py           (get_all_equipment: + project_name)
MOD    pharmagpt/qual_database.py                (+ get_test_case, get_deviation)
MOD    pharmagpt/urs_database.py                 (+ get_requirement, get_version)
MOD    pharmagpt/qms_capa_database.py            (+ get_action)
MOD    pharmagpt/qms_document_database.py        (+ get_distribution_entry, get_training_entry)

MOD    pharmagpt/routes/equipment.py             (+ GET /equipment)
MOD    pharmagpt/routes/projects.py              (auto-link equipment; audit performed_by fix)
MOD    pharmagpt/routes/qms_documents.py         (kb_sync hook; distribution/training tenancy fix)
MOD    pharmagpt/routes/urs.py                   (kb_sync hook; requirement/version tenancy fix)
MOD    pharmagpt/routes/qual.py                  (kb_sync hook; _scoped_protocol + tenancy fixes)
MOD    pharmagpt/routes/report.py                (kb_sync hook; approval/version tenancy fix)
MOD    pharmagpt/routes/qms_capa.py              (escalate_action tenancy fix)
MOD    pharmagpt/routes/qms_change_control.py    (AI-narrative-endpoint tenancy fix)

MOD    pharmagpt/static/js/equipment.js          (eqRenderList parametrized; eqLoadCompanyList; origin-aware eqBackToList)
MOD    pharmagpt/templates/index.html            (sidebar reorg; Equipment Library view)

MOD    tests/test_security_tenant_rbac_esig.py   (+6 cross-tenant regression tests)
MOD    tests/test_equipment_routes.py            (2 assertions updated for Task 3's new behavior)
```

(`pharmagpt/app.py`, `routes/validation.py`, and several `static/js/*` files carry pre-existing
uncommitted changes from prior sessions, unrelated to Phase 2 and not further modified here — see
`PHASE_1_IMPLEMENTATION_REPORT.md` §9 for that inventory.)

---

## 10. Remaining Phase 3 dependencies

Explicitly not started, per this session's instruction:

- **Equipment Library ownership re-parenting** (`project_id NOT NULL` → company-owned,
  many-to-many, Blueprint ADR-P01/PA-013) — the one genuinely structural schema change in the
  whole program; Phase 2 delivered the navigation/query half only (§3).
- **Company / Users / Roles administration UI** — blocks adding the `Administration` sidebar
  section for real (§2).
- **Global Search** — blocks adding the persistent search bar; needs the Postgres full-text index
  target, which needs the SQLite→Postgres cutover.
- **Shared six-state lifecycle convergence** — Document Control/Deviation/CAPA/Change Control/
  Validation Suite still have independent status vocabularies; this session hooked into each
  module's own existing terminal state rather than unifying them (unifying is Phase 2's *original*
  scope per `PHASED_MIGRATION_PLAN.md`, but was not requested in this session's task list).
- **Postgres RLS 2-company soak test** — still outstanding per `docs/PHASE3_FLAGS.md`, unrelated to
  this session's changes.

Do not start Phase 3 without explicit instruction.

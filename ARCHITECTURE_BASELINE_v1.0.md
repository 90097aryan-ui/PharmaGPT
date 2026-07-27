# PharmaGPT — Architecture Baseline v1.0

Status: **Official architecture baseline**, established at the close of Investigation
Case Phase 2. Everything under "Framework Components" below is frozen — extend it,
never redesign it, except for a documented critical defect.

---

## 1. Module Architecture

### 1.1 Workflow Engine (`services/workflow_engine.py` + `qms_workflow_database.py`)

Gated, named-approver approval flow over a **high-level lifecycle only**
(Draft → Submitted → Review → Investigation → CAPA → Effectiveness Check → Closure for
deviations). Record-type-agnostic: every function takes `(record_type, record_id)` and
is driven by a seeded `qms_workflow_templates`/`qms_workflow_template_steps` pair (e.g.
`DEVIATION_LIFECYCLE_V2`). Public surface:

```python
get_instance_state(record_type, record_id) -> dict
is_unlocked(record_type, record_id, unlock_step_key) -> (bool, reason)
start_instance(workflow_key, record_type, record_id, company_id, performed_by) -> dict
assign_approvers(record_type, record_id, step_order, approvers) -> dict
decide_step(record_type, record_id, step_order, decision, *, user_id, role, performed_by, comments="") -> dict
```

`is_unlocked` is a pure read — any module can call it to gate a downstream feature
(exactly how the Investigation Case and, as of Phase 2, Investigation Tasks/Knowledge
Base gate themselves) without the Workflow Engine ever needing to know that caller exists.

### 1.2 Approval Engine

Not a separate module — "approval" is one of the Workflow Engine's own step *types*
(`decide_step` with `decision="approve"`), backed by the shared `qms_approvals` table
(e-signature trail) exposed read-only at `GET /qms/<record_type>/<id>/approval`. Unchanged
since Phase 1.

### 1.3 Investigation Engine (`services/investigation_engine.py` + `qms_investigation_database.py`)

Answers "what work has been done to find the root cause" — Evidence, SOP Review,
Interviews, Timeline, Investigation Tasks (Phase 2), AI Assistant/Report runs, Root
Cause (Possible → Probable → Confirmed), and the finalized CAPA-handoff Summary. Every
table is polymorphic on `(record_type, record_id)`, exactly like `qms_attachments`/
`qms_comments` — deviations are the only consumer today, but nothing in this engine
references `qms_deviations` directly. Every mutating function takes an explicit
`unlocked: bool` (computed by the caller via `workflow_engine.is_unlocked(...)`) and
raises `InvestigationLockedError` if `False` — the engine refuses the write itself, so a
route can't accidentally skip the check. Reads never require `unlocked`.

Also owns the one deterministic, non-AI calculation in this module:
`get_dashboard()` — Evidence Score, per-dimension completeness percentages, Outstanding
Tasks, and Investigation Progress, all computed by fixed formula from stored rows.
`latest_ai_recommendations` is the sole exception: a read-only pass-through of the most
recent AI Assistant run's own output, clearly labelled advisory and never folded into
any percentage.

### 1.4 AI Orchestration (`prompts/investigation_prompt.py`)

Two independent modes, both logged to the same append-only `qms_investigation_ai_runs`
table (`mode` column distinguishes them):

- **Assistant** (`build_assistant_prompt`) — interactive, question-driven, re-runnable
  any number of times, never gates a workflow step.
- **Report Generation** (`build_report_prompt`) — formal, evidence-based write-up. Each
  call is a new row in the append-only log, which *is* the report's version history
  (surfaced in the UI as "Report Generation (v1)", "(v2)", ...).

Both prompts pass the AI an **itemized** evidence summary (`_evidence_summary()`:
real category/doc/interview/timeline content, not just counts) and enforce, verbatim,
the Phase 2 AI Quality Rules:

- Never invent evidence, interviews, SOPs, calibration data, or root causes.
- If the evidence provided doesn't support a conclusion, the response must contain
  exactly: `"Unable to determine root cause. Additional evidence is required."`
  (`investigation_prompt.INSUFFICIENT_EVIDENCE_STATEMENT` — checked verbatim by tests,
  used as both the JSON-parse-failure fallback and the instructed refusal text).
- Every AI run records `evidence_references` (which specific evidence/SOP/interview/
  timeline rows were shown to the model) for traceability.
- AI output never overwrites an investigator's own Root Cause fields — `save_root_cause`
  is only ever called with investigator-supplied data; the AI's `possible_cause` and the
  investigator's `probable_cause`/`confirmed_root_cause` are independent fields the
  caller chooses to set.

### 1.5 RBAC / Tenant Isolation

Unchanged (frozen). Four roles (`super_admin | company_admin | reviewer_qa | user`),
enforced via `auth/decorators.py::require_role`. Every record with its own `company_id`
column is scoped via `tenancy.scoped_or_none`; polymorphic child tables with no
`company_id` of their own (all Investigation Case tables) are scoped transitively — a
route resolves the owning record first (`_record_scoped_or_404`) and every child read/
write goes through that route, never a bare `record_id` lookup. Investigation Tasks
follow this same transitive-scoping rule (`get_task_scoped` verifies a task actually
belongs to the deviation in the URL before any update).

### 1.6 Audit Engine (`audit.py`)

Single `audit.log(record_type, record_id, action, *, old=None, new=None, reason="", result="success", detail="")`
entry point. `performed_by`/`company_id`/`ip_address`/`session_id` are always derived
from the authenticated `g.tenant` / request context, never from client input.
Investigation Case sub-entities (evidence, interviews, tasks, ...) log against the
**owning deviation's** `record_type`/`record_id` — there is no separate audit trail per
evidence item or per task; it all rolls up to the deviation's own Audit tab, exactly
like Phase 1.

### 1.7 Knowledge Base Integration (Phase 2)

No new retrieval logic — reuses `services/retrieval_engine.py::retrieve_context()`
(the same function `routes/validation.py` already calls) for SOP/WI/Validation
Protocol/Risk Assessment suggestions. Suggestions are never persisted directly; the
investigator explicitly accepts one, which writes through the existing
`investigation_engine.add_sop_review()` — no new table. Previous Deviations/CAPAs/
Equipment History are live-queried (best-effort match on product/equipment/department)
each time the Knowledge Base tab loads, never cached or persisted, so they're always
current and can never go stale.

---

## 2. Folder Structure (relevant subset)

```
pharmagpt/
  qms_database.py                 QMS_SCHEMA (all CREATE TABLE statements) + record numbering
  qms_investigation_database.py   Pure CRUD for Investigation Case tables (incl. Tasks)
  qms_workflow_database.py        Pure CRUD for Workflow Engine tables
  qms_deviation_database.py       Pure CRUD for qms_deviations
  audit.py                        Unified audit-trail logging entry point
  tenancy.py                      Tenant-scoping helpers (scoped_or_none, signing_identity)
  services/
    investigation_engine.py       Investigation Case business rules (lock enforcement, dashboard, AI orchestration)
    workflow_engine.py            Workflow Engine business rules (lock state, step decisions)
    retrieval_engine.py           Knowledge Base retrieval (chunking, scoring, source dedup)
  prompts/
    investigation_prompt.py       AI Assistant / AI Report prompt builders + AI Quality Rules text
  routes/
    qms_deviations.py             Deviation Management + Investigation Case + Knowledge Base routes
    qms_common.py                 Shared attachments/comments/audit-trail/approval/dashboard/meta
  static/js/investigation_case.js Reusable Investigation Case UI component (record-type-agnostic)
  static/css/investigation_case.css
tests/
  test_investigation_engine.py    Service-layer tests (no Flask, direct engine calls)
  test_workflow_engine.py         Same, for the Workflow Engine
  test_qms_routes.py              Flask test-client integration tests (all QMS modules)
```

---

## 3. Database Overview

All Investigation Case tables are polymorphic on `(record_type, record_id)` with a
matching `idx_qms_inv_<name>_record` index — the same pattern as the pre-existing shared
`qms_attachments`/`qms_comments` tables. No table has a foreign key to `qms_deviations`;
every relationship is by the `(record_type, record_id)` pair alone, which is what makes
the same tables reusable for CAPA/OOS/OOT/Complaint/Audit Finding/Supplier/Validation
investigations later with zero schema change.

| Table | Cardinality | Notes |
|---|---|---|
| `qms_investigation_evidence` | many per record | `category`, `attachment_id` (FK), `source`, `version` (Phase 2), `review_status` |
| `qms_investigation_sop_review` | many per record | doubles as the Knowledge Base "accept suggestion" target |
| `qms_investigation_interviews` | many per record | `notes`, `attachment_id` (FK) added Phase 2 |
| `qms_investigation_timeline_events` | many per record | `source`: manual \| automatic \| ai |
| `qms_investigation_ai_runs` | many per record, append-only | `mode`: assistant \| report_generation |
| `qms_investigation_root_cause` | **one** per record (`UNIQUE`) | Possible/Probable/Confirmed tiers |
| `qms_investigation_summary` | **one** per record (`UNIQUE`) | `open_questions_json` added Phase 2 |
| `qms_investigation_tasks` | many per record | **new in Phase 2** — see below |

`qms_investigation_tasks` (Phase 2 Part 1):

```sql
id, record_type, record_id, title, description, assigned_user, department,
priority ('Low'|'Medium'|'High'|'Critical'), due_date,
status ('Pending'|'In Progress'|'Completed'|'Cancelled'), completion_date,
evidence_attachment_id (FK -> qms_attachments), comments, created_by,
created_at, updated_at
```

**Migration convention**: new tables ship inside `qms_database.QMS_SCHEMA`
(`CREATE TABLE IF NOT EXISTS`, executed by `database.py::init_db()`). Additive columns
on existing tables use `database.py::_add_column_if_missing(conn, table, column, ddl)`
— SQLite has no `ADD COLUMN IF NOT EXISTS`, so this checks `PRAGMA table_info` first.
Phase 2 added: `qms_investigation_evidence.source/version`,
`qms_investigation_interviews.notes/attachment_id`,
`qms_investigation_summary.open_questions_json`. All backward compatible — every
pre-Phase-2 row reads back with empty-string/`[]` defaults.

---

## 4. API Conventions

- Every Investigation Case sub-route lives under the owning module's own blueprint
  (`/qms/deviations/<id>/investigation/*`) — there is no standalone Investigation
  blueprint. A route is a thin wrapper: resolve + tenant-scope the parent record, resolve
  the lock via `workflow_engine.is_unlocked(...)`, delegate to `investigation_engine`,
  catch `InvestigationLockedError` → **HTTP 423** with `{"error": "Investigation Case
  Locked — <reason>"}`, then `audit.log("deviation", did, "<Action>", ...)`.
- GET routes never check the lock — reads are always allowed.
- Child-record routes (e.g. `PUT .../tasks/<task_id>`) verify the child actually belongs
  to the parent in the URL (`investigation_engine.get_task_scoped`) before mutating —
  never trust a bare child id.
- File uploads reuse the existing generic `/qms/<record_type>/<id>/attachments` endpoint
  (`routes/qms_common.py`) — Investigation Case entities never get their own upload
  route; they store an `attachment_id` FK and let the frontend fetch/display via the
  shared endpoint.

---

## 5. Coding Standards

- **Three-layer split, always**: `qms_investigation_database.py` (pure CRUD, one
  connection per call, never rejects a write) → `services/investigation_engine.py`
  (business rules: lock enforcement, dashboard formula, AI orchestration) → 
  `routes/qms_deviations.py` (HTTP concerns: tenant scoping, lock resolution, audit
  logging, status codes).
- Every mutating service function's last keyword argument is `unlocked: bool` —
  grep-able, impossible to add a write path that forgets it.
- Constants shared between the AI prompt and the deterministic dashboard
  (`REQUIRED_EVIDENCE_CATEGORIES`, `EXPECTED_TIMELINE_EVENT_TYPES`) are defined **once**,
  in `investigation_engine.py`, so the two can never silently disagree about what
  "complete" means.
- Deterministic vs. advisory data is never mixed in one field — `get_dashboard()`'s
  percentages are 100% rule-based; `latest_ai_recommendations` is a separate,
  clearly-labelled key.

---

## 6. Extension Rules

To add Investigation Case support to a new record type (CAPA, OOS, OOT, Complaint,
Audit Finding, Supplier Investigation, Validation Investigation):

1. Add a `record_type` string (e.g. `"capa"`) — no new table, no `investigation_engine.py`
   change. Every existing table already accepts any `record_type` value.
2. In that module's own route file, add `/investigation/*` sub-routes following the exact
   thin-wrapper pattern in `routes/qms_deviations.py` (§4 above), pointing
   `RECORD_TYPE = "capa"` and choosing whatever workflow step key gates the lock for that
   module (or `unlocked=True` always, if that module has no gating workflow step).
3. Mount the frontend: `InvestigationCase.mount(containerId, "capa", capaId, "/qms/capa")`
   — `static/js/investigation_case.js` is already fully generic (verified: it only reads
   `recordType`/`recordId`/`baseRoutePrefix` from `mount()`, nothing deviation-specific).
4. If Knowledge Base cross-referencing (Part 3) is wanted, replicate
   `qms_deviations.py::_related_records()` in the new module's own route file — it's
   deliberately kept there (not in `investigation_engine.py`) because it queries
   deviation-shaped fields (`product`/`equipment`); a CAPA/OOS module would write its own
   version matching its own schema.

**Never** move lock enforcement, the dashboard formula, or AI orchestration into a
per-module copy — those stay in `investigation_engine.py`/`investigation_prompt.py`
exactly once.

---

## 7. Decision Log (Phase 2)

| Decision | Rationale |
|---|---|
| Knowledge Base suggestions write into the existing `sop_review` table, not a new table | It already has the exact Reviewed/Not Applicable/Requires Clarification vocabulary Part 3 asks for |
| Previous Deviations/CAPAs/Equipment History are live-queried, never persisted | Always fresh, zero staleness risk, no new table |
| Evidence/Interview/Task attachments reuse the existing `/qms/deviation/<id>/attachments` endpoint | Avoids adding new `record_type`s to `qms_common.py`'s tenant-scoping allowlist, which would need new join-scoped-getter plumbing for record types that have no `company_id` of their own |
| Task "Comments" is a flat column, not a threaded sub-table | Spec lists it as one field per task, not a comment thread; matches how Interviews' `observation`/`notes` are also flat columns |
| Task "Audit Trail" rolls up to the deviation's existing audit trail | Same pattern already used for evidence/interview/timeline mutations — no per-task audit surface |
| Report "Versioning" is the existing append-only `ai_runs` table + a UI-computed version number | Every `run_ai_report()` call is already a new, timestamped, queryable row — no new versioning column needed |
| `REQUIRED_EVIDENCE_CATEGORIES` widened from 8 to 10 items and renamed to match Part 2's full vocabulary | Two pre-existing dashboard tests encoded the old 8-item list; updated deliberately, not a regression |
| Task "no tasks yet" counts as 0% task-completeness, not 100% | An untouched dimension should read as 0% progress like every other empty dimension (interviews, SOP review), not be treated as vacuously complete |

---

## 8. Framework Components (frozen)

Workflow Engine · Approval Engine · Investigation Engine · RBAC · Tenant Isolation ·
Audit Engine · AI Run History · Lifecycle UI · Investigation Case · Evidence Score
Calculation.

Modify only for a documented critical defect — no architectural redesign.

---

## 9. Future Roadmap

- **Equipment History matching** currently does a name-substring search
  (`equipment_database.search_equipment`); a dedicated equipment-to-deviation link table
  would allow exact matching instead of best-effort string search.
- **Richer AI evidence-linking**: `evidence_references` currently records *which rows
  were shown* to the model, not which specific row the model's conclusion actually cites
  — a future prompt version could ask the model to cite reference IDs inline.
  Test the RIGHT thing: keep this deterministic-vs-advisory separation intact even as the
  citation granularity improves.
- **Task-gates-workflow as an opt-in rule**: today, completing a task never advances the
  Workflow Engine (by design). A future business rule could make specific task types
  mandatory-before-advance for specific workflow steps — this should be implemented as a
  new, explicit check in the *route* layer (e.g. `qms_deviations.py`'s `decide_step`
  call site), never by changing `investigation_engine.py`'s or `workflow_engine.py`'s
  core contracts.
- **Report versioning as first-class**: if a "compare version N vs N-1" UI is ever
  needed, the append-only `ai_runs` history already has everything required — no schema
  change, just a new read-only route/view.

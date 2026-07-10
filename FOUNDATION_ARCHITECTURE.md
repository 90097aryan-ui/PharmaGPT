# FOUNDATION_ARCHITECTURE.md — PharmaGPT Foundation v1.0

**Status: FROZEN.** This document captures the architecture of PharmaGPT as of the **Foundation
Refactoring** (PharmaGPT v1.0 Modules 1–3), approved and tagged **`Foundation v1.0`** on
2026-07-10. It is a capstone snapshot, not a living document — for ongoing architecture detail as
the system continues to evolve, see [PROJECT_MEMORY/ARCHITECTURE.md](PROJECT_MEMORY/ARCHITECTURE.md)
(the living document this one was distilled from) and [PROJECT_MEMORY/DECISIONS.md](PROJECT_MEMORY/DECISIONS.md)
DEC-023 (Equipment), DEC-024 (Validation Workspace retirement), DEC-025 (Project Workspace), and
DEC-026 (this reconciliation) for the full rationale behind each decision recorded here.

**What follows must not be re-litigated or restructured in Module 4 (AI Intelligence Integration)
or later modules unless a critical defect is discovered.** Module 4 builds *on* this foundation; it
does not change it.

---

## 1. What the Foundation Refactoring Was

Three sequential modules, each reviewed and approved before the next began, that consolidated what
had grown into several parallel, overlapping structures into one coherent core:

| Module | Theme | Resolved |
|---|---|---|
| **Module 1** ("Phase 2 Module 1") | Unify the Project entity | Merged the separate Validation Workspace project fields (owner/approver/target_date/risk_category/status/model/location/protocol_number/report_number) onto the single `projects` table. |
| **Module 2** | Equipment as a first-class entity | Replaced free-text-only equipment info with a real `equipment` entity owned by a Project, without disturbing the pre-existing static equipment-type reference catalog. |
| **Module 3** | Project Workspace & Navigation Refactoring | Replaced a growing set of separate project-scoped sidebar items (and a still-live legacy Validation Workspace entity that Module 1 was supposed to have already retired) with one unified Project Workspace: "One Project = One Workspace." |

None of this added a new user-facing capability on its own — it is entirely a consolidation and
navigation exercise, deliberately kept separate from Module 4's AI-integration scope.

---

## 2. Core Entities

### 2.1 Project (`projects` table)

The single source of truth for "a validation engagement." Every other entity in the system either
belongs to a Project (`project_id` FK) or is referenced from one.

Carries, on one row: `name`, `equipment_name`/`manufacturer`/`model`/`equipment_id`/`department`/
`validation_type` (original v0.1–v0.3 fields, still free text, still read by Chat/Validation
wizard/prompts) plus `owner`/`approver`/`target_date`/`risk_category`/`status`/`location`/
`protocol_number`/`report_number` (merged in by Module 1). `migrated_from_val_project_id` marks rows
copied from the now-retired legacy entity (§4).

**Why the legacy free-text equipment fields were not removed:** they are read, unmodified, by code
that predates Equipment (Module 2) and was deliberately not touched — the Chat context injector, the
Validation Document Generator wizard, and AI prompt builders. Equipment (§2.2) is additive on top,
not a replacement.

### 2.2 Equipment (`equipment` + `equipment_documents` tables)

A first-class entity owned by exactly one Project (`project_id NOT NULL ON DELETE CASCADE`).
Carries Basic Information (name/category/type/tag number/model/manufacturer/vendor/serial number/
asset number), Installation Information (plant/block/department/area/room/line/installation date/
commissioning date), and Qualification Information (qualification status/validation status/
qualification type/criticality/GMP impact).

`equipment_documents` links an Equipment record to an existing Knowledge Base document or Project
document (`source_type ∈ {kb, project}`) by role (User Manual/Vendor Manual/SOP/Drawing/P&ID/
Electrical Drawing/Pneumatic Drawing/FAT/SAT/URS/Other) — **it never copies a document**, only
references it, so the same manual is reusable across every Equipment record and Project that needs
it.

Deliberately architecture-only beyond this: no Calibration, Preventive Maintenance, Breakdown
History, Spare Parts, Vendor Qualification, Environmental Monitoring, Utilities, or Asset Management
tables exist yet. Any of those, when built, should FK to `equipment.id` rather than re-deriving
equipment identity another way.

`equipment.equipment_type` is a free-text field that *may* match an entry in the separate, static
`pharmagpt/equipment/` Intelligence Engine registry (HPLC, GC, Autoclave, ...) — a plain string
match, not a foreign key. That registry is a reference catalog of equipment *types*, unrelated to
and unmodified by the Equipment entity.

---

## 3. Navigation Architecture — "One Project = One Workspace"

Selecting a project (sidebar, or a Dashboard "Recent Projects" card) opens **one** Project Workspace
(`view-project-workspace`, `project_workspace.js`) — an Enterprise Workspace shell (§5) with ten
tabs:

| Tab | What it shows | Nature |
|---|---|---|
| Overview | Project info (name, status, risk category, protocol/report numbers, owner/approver, target date, legacy equipment fields) | Live, project-scoped |
| Equipment | The Module 2 Equipment list (add/edit/delete, "Open Profile" drill-down) | Live, project-scoped |
| Documents | Project document upload/list + a Document Insights stats strip | Live, project-scoped |
| Risk Assessment | Entry point into the Risk Management Suite | **Not project-filtered** — see §6 |
| URS | Entry point into the URS Management Suite | **Not project-filtered** — see §6 |
| Qualification | Entry point into the Qualification (IQ/OQ/PQ) Suite | **Not project-filtered** — see §6 |
| Validation Report | Entry point into the Validation Report Suite | **Not project-filtered** — see §6 |
| Tasks | Placeholder ("Planned") | Architecture only, no schema |
| Approvals | Placeholder ("Planned") | Architecture only, no schema |
| History | Live audit trail (`qms_audit_trail`, `record_type='project'`) | Live, project-scoped |

The Equipment tab can drill further into a full **Equipment Profile** page (`view-equipment-profile`,
also an Enterprise Workspace) with its own tabs: Overview, Specifications, Documentation,
Qualification, Validation History, Related Documents, Related Risk Assessments, Future Modules.
"Back to Project Workspace" returns to the Equipment tab.

**What used to be separate, permanent sidebar items — Project Documents, Document Insights,
Equipment, and Validation Workspace — no longer exist as standalone nav items.** Chat ("AI
Assistant") and Generate Document remain separate top-level items; they were out of scope for this
refactoring.

---

## 4. What Was Retired

The legacy **Validation Workspace** (`val_projects`/`val_audit_trail` tables, `routes/workspace.py`,
`val_workspace.js`, its own dashboard/create-modal/tabbed detail view) is **gone**. It was discovered,
during the review that preceded Module 3, to still be a fully live, writable flow on a *separate*
entity — contradicting the unified Project (§2.1) that Module 1 was supposed to have already made
the single source of truth. `val_projects`/`val_audit_trail` **tables** were not dropped (no data
loss, no destructive migration) — they are now genuinely read-only history, reachable only via the
one-time `_migrate_val_projects()` copy already performed. See DEC-024 for the full incident
writeup.

---

## 5. Shared Infrastructure Reused (Not Duplicated)

The Foundation Refactoring added **zero** new cross-cutting mechanisms — every new capability reuses
something that already existed:

- **Enterprise Workspace shell** (`workspace.css`/`workspace.js`, `enter()`/`exit()`/
  `renderBreadcrumb()`/`renderProgress()`/`confirmDialog()`) — first built for Generate Document, now
  also powers the Equipment Profile and the Project Workspace. A new generic `.ws-tabs`/`.ws-tab`
  tab-strip component was added to `workspace.css` for any current or future consumer.
- **Polymorphic QMS shared tables** (`qms_audit_trail`, keyed by `record_type`/`record_id`) — Project
  History reuses this via `record_type='project'` rather than a new project-specific audit table.
- **Knowledge Base linking model** — Equipment's document references use the same "link, don't
  duplicate" principle the Knowledge Base already established for cross-project document reuse.

---

## 6. Known, Disclosed Limitations (Not Defects)

These are deliberate scope boundaries, not oversights — each was an explicit decision, not a bug:

1. **Risk, URS, Qualification, and Validation Report have no `project_id` (or `equipment_id`)
   column.** Their Project Workspace tabs are genuine entry points (reusing each suite's existing
   `initX()` bootstrap), not project-filtered views. There is no "back to project" link inside those
   suites yet. Fix: add the FK columns, a Module 4+ candidate, not part of this foundation.
2. **Tasks and Approvals are placeholder tabs.** No schema, no data. Real implementations are future
   modules.
3. **Equipment Profile's Validation History and Related Risk Assessments tabs are approximations/
   placeholders** for the same reason as (1) — no suite yet references `equipment.id`.
4. **The Equipment AI-context bundle
   (`services/equipment_service.py::get_equipment_context_bundle()`) is assembled but not called from
   anywhere.** It is the most likely Module 4 (AI Intelligence Integration) starting point.

---

## 7. Testing Status at Freeze

148 automated tests passing (0 failures on a clean run; one wall-clock-timing test is occasionally
flaky under system load, confirmed unrelated by isolated re-run). Full regression suite covers the
pre-existing Document Intelligence Engine and QMS suites plus the three new test files this
refactoring added: `test_projects_merge.py` (Module 1), `test_equipment_database.py` +
`test_equipment_routes.py` (Module 2), `test_project_workspace.py` (Module 3).

---

## 8. What Comes Next

**Module 4 — AI Intelligence Integration** is scoped to focus exclusively on wiring AI capability
into what this foundation established (starting candidates: the Equipment AI-context bundle, §6.4;
the long-standing vector-RAG stubs in `document_search.py`). **No further navigation or structural
refactoring should be performed in Module 4 or later unless a critical defect is discovered** in
what this document describes — per explicit instruction accompanying the `Foundation v1.0` freeze.

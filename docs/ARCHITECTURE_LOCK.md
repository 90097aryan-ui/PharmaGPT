# PharmaGPT — Architecture Lock Document (ALD-001)

**Status:** FINAL — pending sign-off
**Type:** Information Architecture / Navigation / Workflow correction only
**Explicitly out of scope:** backend architecture, database schema, authentication, AI service design, business logic
**Supersedes:** the Phase 4 "Validation Center" cosmetic sidebar grouping (`PHASE_4_UI_NAVIGATION_REPORT.md`) and all prior informal proposals in this thread
**Amendment 1:** "Project Workspace" retired as a top-level sidebar module. Projects is now a direct sub-item of Validation Suite (alongside Validation Dashboard) and is the sole entry point into a project — enforced below as a single-navigation-path rule.

---

## 1. Executive Summary

PharmaGPT's functionality is mature — URS, Qualification (IQ/OQ/PQ), Risk Assessment with an auto-populating Risk Library, Deviations/CAPA/Change Control, a company-wide Equipment record, and an AI document generator all exist and work. What does not reflect how a validation engineer thinks is the **Information Architecture** wrapped around them: Projects sat beside the suite that should contain them, the suite itself had no landing view, Knowledge Base used a flat generic folder list, and the AI document generator mixed operational GMP paperwork with validation-lifecycle documents that already have dedicated, more capable suites elsewhere in the app.

This document locks the corrected IA. It changes **navigation, grouping, and screen composition only**. No Flask route is renamed, no table is altered, no authentication path changes, and no AI service is redesigned. Every item below is traceable to an existing file, route, or component; where a genuine backend addition is unavoidable (a small number of read-only aggregation points, called out explicitly in §9), it is flagged for separate sign-off rather than smuggled in as "just IA."

## 2. Product Philosophy

1. **Project-centric drill-down for lifecycle work.** A validation engineer opens a project once and does everything inside it — equipment, URS, qualification, approval, report — as tabs in one workspace, not as unrelated top-level menu hops.
2. **Company-wide master data is selected, not re-created.** Equipment and Risk data are authored once at the company level and *referenced* by projects, never duplicated per project.
3. **One workflow per document type.** If a document type already has a dedicated suite (URS, Qualification, Risk, Deviation, CAPA, Change Control, Validation Report), the generic AI Document Generator must not offer a second path to the same output. This principle already exists in the codebase as **ADR-P02** (`static/js/validation_config.js`, `routes/validation.py::_RETIRED_DOC_TYPES`) and this document extends it consistently to the remaining duplicates.
4. **The sidebar is a table of contents, not the application.** It lists modules once, at one level. Depth lives inside each module's own dashboard.

## 3. Information Architecture

Every module in the application, without exception, follows the same three-tier shape:

| Tier | Purpose | Example |
|---|---|---|
| 1 — Sidebar entry | One click to enter a module | "Validation Suite" |
| 2 — Module dashboard | Landing/aggregation view, lists + KPIs + entry points into records | Validation Dashboard |
| 3 — Workspace / detail screen | Drill-down: tabs, forms, individual records | Project Workspace tabs |

No module may skip tier 2 (a bare list of links is not a dashboard) and no module may expose tier-3 depth directly in the sidebar (this is what caused the original overload).

## 4. Complete Sidebar Hierarchy (LOCKED)

```
🏠 Dashboard            — global home, cross-module KPIs (unchanged)
🧪 Validation Suite     — company-wide validation module
    • Validation Dashboard   — KPI Dashboard, Quality & Compliance, Approval Queue, Recent Activity
    • Projects               — project list/create; the ONLY entry point into a Project Workspace
📚 Knowledge Base        — controlled reference document repository (retaxonomized)
🏭 Equipment Library     — company master equipment data (promoted, not rebuilt)
⚠ Risk Management       — company-wide risk dashboard, assessments, library, templates, reports
📄 Document Generator    — operational GMP documents ONLY (scope narrowed)
⚙ Administration        — unchanged, role-gated (Companies, Users)
🤖 AI Assistant          — unchanged (PharmaPilot placeholder + working chat)
```

**Final correction (Amendment 1):** Project Workspace is **not** a top-level sidebar module and must never be re-added as one. It is reached exclusively via **Validation Suite → Projects** — there is exactly **one** navigation path to any project. An earlier draft of this lock exposed Project Workspace as its own sidebar entry to satisfy "keep Projects visible"; that entry is retired here and replaced by making Projects a direct sub-item of Validation Suite, sitting alongside Validation Dashboard rather than nested inside it or duplicated as a second top-level module.

**Resolved ambiguity:** Equipment Library and Risk Management are **top-level sidebar modules**, not sub-sections of Validation Suite — they are company master data / company-wide functions consumed by, but independent of, any single validation project.

## 5. Module Hierarchy (LOCKED)

```
Validation Suite
├── Validation Dashboard (landing)
│   ├── KPI Dashboard              (active projects, open URS/DQ/IQ/OQ/PQ, pending approvals, reports issued)
│   ├── Quality & Compliance       (Deviations / CAPA / Change Control — company-wide, reused as-is)
│   ├── Approval Queue             (unified, cross-suite: URS/DQ/IQ/OQ/PQ/Risk/Validation Report/Change Control)
│   └── Recent Activity            (cross-module activity feed)
│
└── Projects                       (project list, "New Project" — reuses #project-list / projects.js;
                                     the SOLE entry point into a Project Workspace — no other path exists)
    └── Project Workspace (per project, opened by selecting a project here)
        ├── Project Dashboard             (NEW — replaces "Overview"; stats scoped to this one project)
        ├── Equipment                     (equipment selected from Equipment Library, project-scoped view)
        ├── URS
        ├── DQ
        ├── FAT
        ├── SAT
        ├── Qualification
        │      ├── IQ
        │      ├── OQ
        │      └── PQ
        ├── Approvals                     (this project's items — filtered slice of the suite-wide queue)
        └── Validation Report

Knowledge Base
├── SOP
│      ├── General SOP    ├── Production        ├── Quality
│      ├── Warehouse      ├── Quality Control    ├── Technology Transfer
│      ├── Human Resource └── Supply Chain
├── Risk Management
│      ├── Process        ├── Alarms             └── Miscellaneous
├── Validation Documents
│      ├── URS  ├── FAT  ├── SAT  ├── IQ  ├── OQ  └── PQ
├── Master Formula Record
├── BMR
├── BPR
└── Manuals
       ├── Equipment      └── Instruments

Equipment Library (company master data — NOT project-specific; projects SELECT from it)
└── Equipment record
    ├── Equipment Details
    ├── Manuals                    (reuses equipment_links role=user_manual/vendor_manual)
    ├── URS Reference               (reuses equipment_links role=urs)
    ├── DQ / IQ / OQ / PQ           (reuses equipment_links; DQ/IQ/OQ/PQ added as role values — see §9)
    ├── Calibration                 (document-linked for MVP — see §16)
    ├── Preventive Maintenance      (document-linked for MVP — see §16)
    ├── Spare Parts                 (document-linked for MVP — see §16)
    ├── Drawings                    (reuses equipment_links role=drawing/pnid/electrical_drawing/pneumatic_drawing)
    ├── Risk Assessment              (reuses equipment_links source_type=risk_assessment)
    ├── Qualification History        (reuses equipment_links source_type=project, filtered to IQ/OQ/PQ docs)
    └── Change History               (see §16)

Risk Management
├── Dashboard
├── Risk Assessment
├── Risk Library              (auto-populated from approved assessments — already implemented, see §9)
├── Templates
└── Reports

Document Generator (operational GMP documents ONLY)
├── SOP            ├── BMR              ├── BPR
├── MFR            ├── Specifications   ├── Formats
├── Templates      ├── Checklists       ├── Logbooks
├── Training Records                    └── Investigation Reports, Reports
```

## 6. Screen Hierarchy

| Tier 1 (sidebar) | Tier 2 (dashboard/landing) | Tier 3 (drill-down) |
|---|---|---|
| Dashboard | — | — |
| Validation Suite → Validation Dashboard | KPI Dashboard, Quality & Compliance, Approval Queue, Recent Activity | — (aggregation only; no project drill-down from here) |
| Validation Suite → Projects | project list ("New Project") — the only door into a project | Project Workspace: Project Dashboard, Equipment, URS, DQ, FAT, SAT, Qualification (IQ/OQ/PQ), Approvals, Validation Report |
| Knowledge Base | folder tree landing | SOP/Risk Mgmt/Validation Docs/MFR/BMR/BPR/Manuals leaf views |
| Equipment Library | company equipment list | per-equipment record (11 sub-sections, §5) |
| Risk Management | Risk Dashboard | Risk Assessment, Risk Library, Templates, Reports |
| Document Generator | doc-type picker | wizard (Step 1 type → Step 2 fields → generate) |
| Administration | — | Companies, Users (role-gated) |
| AI Assistant | — | Chat |

## 7. Navigation Flow

```
Login
 └─ Dashboard (global)
      ├─ Validation Suite
      │    ├─ Validation Dashboard
      │    │    ├─ Quality & Compliance → Deviations | CAPA | Change Control (reused screens)
      │    │    └─ Approval Queue → jumps into the specific pending item's own screen
      │    └─ Projects  (the ONLY path into a project — no other sidebar item opens one)
      │         └─ select/create project → Project Workspace
      │              Project Dashboard → Equipment → URS → DQ → FAT → SAT → Qualification(IQ→OQ→PQ) → Approvals → Validation Report
      ├─ Knowledge Base → SOP | Risk Management | Validation Documents | MFR | BMR | BPR | Manuals
      ├─ Equipment Library → equipment record (Manuals/URS Ref/DQ/IQ/OQ/PQ/Calibration/PM/Spares/Drawings/Risk/Qual History/Change History)
      ├─ Risk Management → Dashboard | Risk Assessment | Risk Library | Templates | Reports
      ├─ Document Generator → operational doc types only
      ├─ Administration (role-gated)
      └─ AI Assistant
```

## 8. User Workflow

**Primary validation lifecycle (the flow this lock exists to enforce):**
Dashboard → Validation Suite → Projects → open/create Project → Project Workspace (Project Dashboard) → select Equipment (from Equipment Library) → URS → DQ → FAT → SAT → IQ → OQ → PQ → Approvals → Validation Report.

**Equipment master-data workflow:** Equipment Library → create/maintain an equipment record once → it becomes selectable inside any Project Workspace's Equipment tab → all qualification, risk, and document links accumulate against the one master record, visible under Qualification History / Risk Assessment / Change History regardless of which project touched it.

**Risk workflow:** Risk Management → Risk Assessment → complete → approve → **automatically publishes to Risk Library** (already implemented, `routes/risk.py::publish_assessment_to_library`) → future assessments and the Equipment Library's own Risk Assessment section draw on the same library entries.

**Reference lookup workflow:** Knowledge Base → SOP / Risk Management / Validation Documents / MFR / BMR / BPR / Manuals — pure document retrieval, no workflow state.

**Operational documentation workflow:** Document Generator → pick an operational GMP doc type (SOP, BMR, BPR, MFR, etc.) → generate → file into Knowledge Base / Document Center. Validation-lifecycle documents (URS, DQ, FAT, SAT, IQ, OQ, PQ, Validation Plan, Validation Report) are **never** generated from here — only from inside Project Workspace.

## 9. Route Mapping

All routes below already exist. Column "Change type" states exactly what happens to each: **R** = reused unchanged, **C** = client-side relocation only (same route, new mount point in the UI), **A** = new additive read-only endpoint required (flagged for explicit sign-off, not covered by "no backend redesign" being read as "zero backend changes").

| Screen | Backend route(s) | Change type |
|---|---|---|
| Validation Dashboard — KPI Dashboard | `/dashboard/stats`, `/urs/dashboard`, `/qual/dashboard`, `/report/dashboard`, `/risk/dashboard`, `GET /equipment` | **A** — needs one small aggregation call combining these; each underlying query is unchanged |
| Validation Suite — Projects | `GET/POST /projects` (`routes/projects.py`) | R — this is the sole route surface for entering a project; no duplicate list is mounted anywhere else |
| Validation Dashboard — Quality & Compliance | `GET /qms/deviations`, `GET /qms/capa`, `GET /qms/change-control` | C |
| Validation Dashboard — Approval Queue | `POST /risk/assessments/<id>/approval` pattern extended to read pending items from URS/Qual/Report/Change Control | **A** — read-only aggregation of existing per-suite "pending approval" states |
| Project Workspace — Project Dashboard | existing `pwRenderOverview` data + per-suite dashboard endpoints, project-filtered | **A** (thin, project-scoped variant of the above) |
| Project Workspace — Equipment | `GET/POST /projects/<id>/equipment`, `GET /equipment` | R |
| Project Workspace — URS | `/urs/*` (`routes/urs.py`) | C |
| Project Workspace — DQ/FAT/SAT | `/validation/generate`, `/validation/export/docx`, `/validation/save` (`routes/validation.py`) | C |
| Project Workspace — Qualification (IQ/OQ/PQ) | `/qual/*` (`routes/qual.py`) | C |
| Project Workspace — Approvals | project-filtered slice of the same sources as the suite-wide queue | C |
| Project Workspace — Validation Report | `/report/*` (`routes/report.py`) | C |
| Knowledge Base (all leaves) | `/kb/*` (`routes/knowledge_base.py`) | R — only the `folder` value taxonomy changes (app constant, not schema) |
| Equipment Library | `/equipment/*` (`routes/equipment.py`), `equipment_database.py` polymorphic links | R, with `DOCUMENT_ROLES` tuple extended to include `dq`, `iq`, `oq`, `pq` — a Python-level enum edit, not a schema change (`source_type`/`document_role` are already free text, per the comment at `equipment_database.py:45`) |
| Risk Management (all screens) | `/risk/*` (`routes/risk.py`) | R |
| Document Generator | `/validation/generate` + `static/js/validation_config.js` | C, with `IQ/OQ Combined` and `Validation Report` entries **removed** (duplicate the Qualification and Validation Report suites) |
| Quality & Compliance sources | `/qms/deviations`, `/qms/capa`, `/qms/change-control` | R — reused verbatim, only their landing surface moves |

## 10. Component Reuse Matrix

| Component | Currently used for | Reused for |
|---|---|---|
| `dash-stat-card` (index.html) | Global Dashboard KPIs | Validation Dashboard's KPI Dashboard panel |
| `PW_TABS` / `pwSwitchTab` / `pwRenderTab` (`project_workspace.js`) | Overview/Equipment/Documents/URS/Report/Approvals tabs | Extended with DQ/FAT/SAT and Qualification tabs; Overview upgraded to Project Dashboard |
| Risk Approval Queue pattern (`showRiskApproval`, `/risk/assessments/<id>/approval`) | Risk-only approval queue | Template for the suite-wide Approval Queue |
| `eqLoadCompanyList` / `#eqlib-*` (`equipment.js`) | Equipment Library list | Unchanged, promoted to top-level sidebar |
| `loadLibrary` / `GET /risk/library` (`risk.js`) | Risk Library | Unchanged, promoted to top-level sidebar |
| KB folder sidebar + document list/detail panel (`knowledge_base.js`) | Flat 8-folder KB | Same component, new leaf-folder data + a grouping header layer |
| AI Document Generator wizard (`validation.js` + `validation_config.js`) | Sidebar "Generate Document" | Relocated into Project Workspace's DQ/FAT/SAT tab; scope narrowed |
| Equipment polymorphic link table (`equipment_database.py::DOCUMENT_ROLES/SOURCE_TYPES`) | Linking KB docs / project docs / QMS records to equipment | Backbone for 8 of the Equipment Library's 11 sub-sections (§5) with zero schema change |
| `PharmaUI` shared loading/empty/error states (`ui_states.js`) | All Phase 5 screens | Every new/relocated screen in this lock |

## 11. Pages to Keep

Projects list/create, all Project Workspace tabs' underlying screens, Equipment CRUD + record detail, URS Management, Qualification (IQ/OQ/PQ) suite, Risk Assessment/Library/Templates/Reports, Validation Report suite, Deviations/CAPA/Change Control screens, Document Center's controlled-document CRUD engine (becomes the Document Generator's file store), global Dashboard, Administration, AI Assistant chat.

## 12. Pages to Move

- Projects' primary access point → out of a nested "Validation Center" sidebar group, into a **"Projects" sub-item directly under Validation Suite** (sibling to Validation Dashboard). This is the only place a project can be opened from.
- Equipment "All Equipment" view → promoted from a Validation Suite sub-item to its own top-level sidebar module.
- Risk "Library"/"Templates"/"Reports"/"Dashboard" → promoted from a Validation Suite sub-group to their own top-level "Risk Management" module.
- DQ, FAT, SAT wizard entries → out of the generic Document Generator, into Project Workspace as dedicated tabs.
- QMS Dashboard (standalone landing) → retired as a landing page; its figures feed the Validation Dashboard's Quality & Compliance panel instead.

## 13. Pages to Remove

- The 7 expandable sidebar sub-groups previously under "Validation Center" (Projects/Equipment/URS/Risk/Qualification/Report/Generate Document as separate expandable sidebar sections) — removed as **sidebar UI only**; every underlying screen survives at its new location.
- **"Project Workspace" as a top-level sidebar module** — an interim draft of this lock exposed it as its own sidebar entry; that entry is removed. Project Workspace still exists as a screen, reached exclusively through Validation Suite → Projects.
- `IQ/OQ Combined` entry in `validation_config.js` — duplicates the Qualification suite.
- `Validation Report` entry in `validation_config.js` — duplicates the Validation Report suite.
- The standalone "Quality Center" top-level sidebar module.

## 14. Features to Merge

- Deviations + CAPA + Change Control → merge into Validation Suite's Quality & Compliance panel. **No workflow is rebuilt** — same screens, same routes, new landing surface only.
- Risk's per-suite approval queue → merge into the Validation Suite's single, unified Approval Queue (URS/DQ/IQ/OQ/PQ/Validation Report/Change Control/Risk all surface here; no duplicate queues).

## 15. Features to Deprecate

- `FMEA` entry in the generic Document Generator — duplicates Risk Assessment's own AI-assisted generation (`routes/risk.py::generate_items`). **Flagged, not removed without separate sign-off** — it was not explicitly named in the locked scope and its removal should be confirmed before implementation touches it.

## 16. Future Expansion Points (explicitly deferred — require their own ADR + approval)

- **Equipment Library — Calibration, Preventive Maintenance, Spare Parts, structured Change History.** For this lock, these ship as document-linked lists reusing the existing polymorphic `equipment_links` table (a calibration certificate, PM record, or spare-part sheet is just a linked document). Turning them into first-class scheduled/tracked records (due dates, recurrence, stock counts) requires new tables and is out of scope for an IA-only lock.
- **Knowledge Base true two-level taxonomy.** The SOP/Risk Management/Validation Documents/Manuals parent groupings are a **front-end rendering layer over a flat leaf-folder list** (`KB_FOLDERS` remains a flat, unconstrained `TEXT` value — see §18). A genuine parent/child schema relation is a future option, not required now.
- **Unified cross-suite Approval Queue** as a first-class backend concept (currently an aggregation view over existing per-suite approval fields) could later become its own table if approval routing/escalation logic grows.

## 17. Implementation Phases

| Phase | Scope |
|---|---|
| A | Sidebar restructuring to the 8 locked top-level items (Validation Suite carrying Validation Dashboard + Projects as its two sub-items); remove the old nested groups and the interim "Project Workspace" top-level entry (UI only, no backend touch) |
| B | Build Validation Dashboard (KPI Dashboard, Quality & Compliance, Approval Queue, Recent Activity) incl. the flagged aggregation endpoints (§9, **A** rows); build the Projects sub-item as the sole project entry point |
| C | Extend Project Workspace: upgrade Overview → Project Dashboard; add DQ/FAT/SAT tab; add Qualification tab |
| D | Prune Document Generator (`validation_config.js`); confirm FMEA disposition; expand Document Generator's operational doc-type coverage (BMR/BPR/MFR/Specifications/Formats/Checklists/Logbooks/Training Records/Investigation Reports) |
| E | Retaxonomize Knowledge Base folders (leaf list + grouping headers); plan a one-time data remap for existing rows (§18) |
| F | Promote Equipment Library and Risk Management to top-level; extend `DOCUMENT_ROLES` with `dq`/`iq`/`oq`/`pq`; wire the 11 Equipment record sub-sections |
| G | Merge Quality & Compliance into Validation Suite; de-duplicate the approval queue |
| H | Full regression pass (§19) |

## 18. Risks During Migration

- **Orphaned event handlers.** Many current sidebar rows are wired by DOM `id`/`onclick` directly (e.g. `risk-nav-library`, `nav-equipment-library`). Removing/relocating sidebar markup without auditing every inline handler risks silently breaking a feature that still "loads" but does nothing.
- **Duplicate approval queues if de-dup is incomplete.** If the Risk approval queue isn't fully folded into the unified queue, engineers could approve the same item from two places.
- **Existing KB rows use the old flat folder values** (`SOP`, `Validation`, `Qualification`, `Protocols`, `Reports`, `Regulations`, `Vendor Documents`, `Others`). Switching `KB_FOLDERS` to the new leaf list does not automatically remap already-uploaded documents — a one-time data remediation pass (not a schema change) is required so existing documents don't become invisible under the new taxonomy.
- **RBAC-gated Administration visibility** must be re-verified untouched, since it sits inside the same sidebar markup being restructured.
- **`_RETIRED_DOC_TYPES` server-side enforcement** (`routes/validation.py`) must be updated in lockstep with any further doc-type removal from `validation_config.js`, or the frontend and backend disagree on what's retired.

## 19. Testing Checklist

- [ ] Sidebar shows exactly the 8 locked top-level items, no nested Validation Center groups remain, and no "Project Workspace" top-level entry exists
- [ ] Validation Suite shows exactly two sub-items: Validation Dashboard and Projects
- [ ] Validation Dashboard loads all 4 panels with real data (KPI, Quality & Compliance, Approval Queue, Recent Activity) and contains no project-picking UI of its own
- [ ] There is exactly ONE way to open a project: Validation Suite → Projects. No other screen (Dashboard, Validation Dashboard, sidebar) opens a project directly
- [ ] Project Dashboard tab shows project-scoped stats distinct from the suite-wide KPI Dashboard
- [ ] DQ/FAT/SAT and Qualification tabs generate/save/export correctly from inside Project Workspace
- [ ] Document Generator no longer offers DQ, FAT, SAT, Validation Plan, IQ/OQ Combined, or Validation Report
- [ ] Document Generator offers the full operational set (SOP, BMR, BPR, MFR, Specifications, Formats, Templates, Checklists, Logbooks, Training Records, Investigation Reports, Reports)
- [ ] Knowledge Base displays the new nested tree; existing documents remain visible after the folder-value remap
- [ ] Equipment Library is reachable as its own sidebar item and shows all 11 record sub-sections
- [ ] Risk Library still auto-populates on assessment approval; still reachable as its own sidebar item
- [ ] Deviations/CAPA/Change Control fully functional from inside Validation Suite; no standalone Quality Center remains
- [ ] No duplicate approval queue exists anywhere in the app
- [ ] Administration section visibility/RBAC unchanged for non-admin and admin roles
- [ ] No console errors from orphaned `onclick`/`data-view` references after sidebar markup changes

## 20. Architecture Decision Record (ADR)

| ID | Decision | Rationale |
|---|---|---|
| ALD-001-01 | Knowledge Base's nested taxonomy is implemented as a flat leaf-folder list plus a front-end grouping layer, not a schema change | `KB_FOLDERS` is already an unconstrained `TEXT` value (`database.py:956`); no `CHECK` constraint exists; adding a real parent/child relation would violate "no schema changes" |
| ALD-001-02 | Quality Center is removed as a top-level module; Deviations/CAPA/Change Control relocate into Validation Suite's Quality & Compliance panel | These three are already company-wide with optional project linkage (`project_id` on all three), the same shape as Validation Suite itself — same tier-2 dashboard pattern applies |
| ALD-001-03 | Equipment Library and Risk Management are top-level sidebar modules, independent of Validation Suite | Both are company master/reference data consumed by, not owned by, any single project |
| ALD-001-04 | `IQ/OQ Combined` and `Validation Report` are removed from the generic Document Generator | Direct duplicates of the existing Qualification and Validation Report suites — same class of problem ADR-P02 already solved for URS/IQ/OQ/PQ/CAPA/Deviation/Change Control |
| ALD-001-05 | FMEA's removal from the Document Generator is flagged but not executed without separate confirmation | Not explicitly named in the locked scope; duplicates Risk Assessment's own generation path but wasn't called out by name |
| ALD-001-06 | Equipment Library's Manuals/URS Reference/Drawings/Risk Assessment/Qualification History sub-sections reuse the existing polymorphic `equipment_links` table (`equipment_database.py`) | `DOCUMENT_ROLES`/`SOURCE_TYPES` are already free-text, already cover 8 of 11 required sub-sections; extending the Python tuple with `dq`/`iq`/`oq`/`pq` values is a code edit, not a schema migration |
| ALD-001-07 | Calibration, Preventive Maintenance, Spare Parts, and structured Change History are deferred as Future Expansion Points | They require genuinely new structured fields (due dates, recurrence, stock counts) beyond a linked-document model — out of scope for an IA-only lock |
| ALD-001-08 | A small number of new **read-only aggregation endpoints** are required for the Validation Dashboard and Project Dashboard | Composing existing per-suite queries into one dashboard view is additive, not a backend redesign — flagged explicitly in §9 for separate sign-off rather than silently bundled into "IA correction" |
| ALD-001-09 (Amendment 1) | "Project Workspace" is removed as a top-level sidebar module; Projects becomes a direct sub-item of Validation Suite, alongside Validation Dashboard, and is the sole navigation path to any project | An interim draft exposed Project Workspace as its own sidebar entry to satisfy visibility of Projects; this created two possible paths to a project (direct entry + Validation Dashboard's project list). Explicit correction: one module, one path — Validation Suite → Projects |

---

=========================================================
## ARCHITECTURE LOCK
=========================================================

This document is the **Single Source of Truth (SSOT)** for PharmaGPT's Information Architecture, Navigation, Module Hierarchy, Screen Hierarchy, and User Workflow, effective upon approval.

No implementation, refactor, or AI-assisted change may alter the sidebar structure, module hierarchy, screen hierarchy, navigation flow, or workflow defined in this document without an explicit, separately recorded approval. Every future implementation prompt referencing PharmaGPT's navigation or IA must conform to this document exactly. Where an implementation requires deviation — including the read-only aggregation endpoints flagged in §9 and §20 — that deviation must be raised and approved before work begins, not discovered after.

**This document does not authorize implementation.** It is the reference implementation must conform to once authorized separately.

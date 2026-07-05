# Quality Management Suite — Phase 2

**Added:** 2026-07-05
**Modules:** Change Control
**Status:** Complete, tested, browser-verified end-to-end (including live Gemini calls)

---

## Why this exists

Phase 1 shipped Document Control, Deviation Management, and CAPA on a shared polymorphic-table
architecture explicitly designed to make Phase 2/3 modules "reuse them for free — just add a new
`record_type` string" (see `docs/QMS_PHASE1.md` and `PROJECT_MEMORY/DECISIONS.md` DEC-010/DEC-011).
Phase 2 adds the next module on the roadmap — Change Control — proving that design out: zero new
shared tables, zero new shared frontend helpers, only additive touches to the four shared files
(`qms_database.py`, `routes/qms_common.py`, `qms_common.js`, `qms.css`).

## Architecture

Follows the identical per-module convention used by Deviation Management and CAPA
(`qms_<module>_database.py` / `routes/qms_<module>.py` / `services/qms_<module>_service.py` /
`prompts/qms_<module>_prompt.py` / `static/js/qms_<module>.js`):

```
pharmagpt/
├── qms_database.py                    # QMS_SCHEMA gains 4 new tables (see Data model below) +
│                                        #   generate_change_control_number() + QMS_META enums
├── qms_change_control_database.py     # CRUD: qms_change_controls, qms_change_control_impact,
│                                        #   qms_change_control_actions, qms_change_control_links
│
├── routes/
│   ├── qms_common.py                  # (additive) record_type='change_control' added to
│   │                                    #   VALID_RECORD_TYPES/_GETTERS; /qms/dashboard extended
│   └── qms_change_control.py          # /qms/change-control/*  (+ approval POST, status transitions)
│
├── services/
│   └── qms_change_control_service.py  # AI orchestration via the existing qms_shared.call_gemini();
│                                        #   markdown report builder
│
├── prompts/
│   └── qms_change_control_prompt.py   # Impact assessment, implementation plan, and 6 more
│                                        #   AI narrative prompt builders
│
└── static/
    ├── css/qms.css                     # (additive) new badge color variants only
    └── js/
        ├── qms_common.js               # (additive) 4th dashboard stat-card pair + section card
        └── qms_change_control.js       # Change Control UI
```

### Why not a new shared table for Deviation/CAPA linkage

Deviation ↔ CAPA already has its own dedicated `qms_deviation_capa_link` table (Phase 1). Change
Control needs to link to *either* a Deviation *or* a CAPA, and potentially other record types in a
future phase — so rather than adding a second dedicated link table
(`qms_change_control_deviation_link` + `qms_change_control_capa_link`), one generic
`qms_change_control_links` table with a `linked_type` discriminator column (`'deviation' | 'capa'`)
was used instead, avoiding a second `qms_deviation_capa_link`-style table pair for a relationship
that's inherently one-to-many-of-different-types from the Change Control side.

### Why the AI narrative outputs share one JSON column

Seven of the nine AI features (Risk Summary, Rollback Plan, Regulatory Impact, Change
Justification, Executive Summary, Verification Summary, Effectiveness Review) are free-text
narratives with no further structure to query on — adding seven `TEXT` columns to
`qms_change_controls` for these would work but adds schema noise for content that's only ever
displayed, never filtered or joined on. A single `ai_narratives TEXT DEFAULT '{}'` JSON column
(read-modify-write via `qms_change_control_database.set_narrative()`) follows the same pattern
already used for `ai_investigation_data`/`ai_review_data` elsewhere in QMS.

## Data model

### New tables

| Table | Purpose |
|---|---|
| `qms_change_controls` | Master record — cc_number, title, change_type, change_category, department, area, equipment_system, requested_by, dates, change_description, reason_for_change, current_state, proposed_state, status, risk_level, qa_reviewer, approver, `ai_narratives` JSON |
| `qms_change_control_impact` | Impact assessment entries — impact_area, impacted (Yes/No/Potential), extent, action_required |
| `qms_change_control_actions` | Implementation plan / checklist steps — step_no, activity, responsible, start/target/completion dates, status |
| `qms_change_control_links` | Links to an existing Deviation or CAPA — `linked_type ∈ {deviation, capa}`, `linked_id` |

Reuses the Phase 1 shared tables (`qms_attachments`, `qms_comments`, `qms_audit_trail`,
`qms_approvals`) via `record_type='change_control'` — no schema change to any of those four tables
beyond what Phase 1 already established (they were always generically typed).

`qms_change_controls.project_id` is nullable with `ON DELETE SET NULL`, matching
`qms_documents`/`qms_deviations`/`qms_capas`.

### Change types, categories, and workflow

- **Change types:** Major, Minor, Critical, Temporary, Permanent, Emergency
- **Change categories:** Equipment, Facility, HVAC, Water System, Compressed Air, Steam,
  Electrical, Software, PLC, SCADA, MES, ERP, Barcode System, Vision System, BMS, LIMS, Validation,
  SOP, Specification, Packaging, Warehouse, Quality, Engineering, Production, Utilities, IT
- **Status lifecycle:** `Draft → Submitted → Initial Review → Impact Assessment → Risk Assessment →
  Department Review → QA Review → Approval → Implementation → Verification → Effectiveness Review →
  Closed`, with a `Rejected` action available from any stage that returns the record to `Draft`
  (`routes/qms_change_control.py::_STATUS_MAP`)

Numbering: `generate_change_control_number()` → `CC-2026-0001` (year + sequence, same
`_next_sequence()` helper `generate_deviation_number()`/`generate_capa_number()` already use).

### Integration

- **Project** — every Change Control carries a nullable `project_id`, same convention as every
  other QMS master table.
- **Deviation / CAPA** — `POST /qms/change-control/<id>/link-deviation` and `.../link-capa` create a
  row in `qms_change_control_links`; `GET .../deviations` and `.../capas` list the linked records.
  This is **one-directional** in the UI: Change Control's own "Related Records" tab shows what it
  links to, but Deviation/CAPA's own detail views (`qms_deviations.js`/`qms_capa.js`) were not
  modified to show a reverse "Related Change Controls" tab, per the instruction not to touch
  completed modules unless integration requires it. The reverse lookup is fully queryable today via
  `qms_change_control_database.get_change_controls_for_record(record_type, record_id)` — a future
  session scoped to Deviation/CAPA can wire it into those modules' own tab lists in a few lines.
- **Knowledge Base, Risk, URS, Qualification, Validation Report, SOP/Documents** — satisfied via the
  standard Impact Assessment mechanism (free-text `impact_area`/`extent`/`action_required` entries
  covering exactly these areas, per `QMS_META.change_control_impact_areas`) and the shared
  Attachments mechanism for supporting documents, rather than inventing new live foreign-key
  relationships to suites that have no existing cross-suite linkage precedent in this codebase
  (Risk/URS/Qual/Report are backend-complete but still have no wired sidebar navigation, and no
  other QMS module links to them either — see `PROJECT_MEMORY/ARCHITECTURE.md` §14).

## AI features

| Feature | Route | Output |
|---|---|---|
| Impact Assessment | `POST /qms/change-control/<id>/suggest-impact` | JSON array (not auto-persisted — reviewed and accepted into `qms_change_control_impact`) |
| Implementation Plan / Checklist | `POST /qms/change-control/<id>/suggest-implementation-plan` | JSON array (reviewed and accepted into `qms_change_control_actions`) |
| Risk Summary | `POST /qms/change-control/<id>/risk-summary` | Text, persisted into `ai_narratives.risk_summary` |
| Rollback Plan | `POST /qms/change-control/<id>/rollback-plan` | Text, persisted into `ai_narratives.rollback_plan` |
| Regulatory Impact | `POST /qms/change-control/<id>/regulatory-impact` | Text, persisted into `ai_narratives.regulatory_impact` |
| Change Justification | `POST /qms/change-control/<id>/justification` | Text, persisted into `ai_narratives.justification` |
| Executive Summary | `POST /qms/change-control/<id>/executive-summary` | Text, persisted into `ai_narratives.executive_summary` |
| Verification Summary | `POST /qms/change-control/<id>/verification-summary` | Text, persisted into `ai_narratives.verification_summary` |
| Effectiveness Review | `POST /qms/change-control/<id>/effectiveness-review` | Text, persisted into `ai_narratives.effectiveness_review` |

All nine features are optional and go through `services/qms_shared.py::call_gemini()` — the exact
same helper Document Control/Deviation/CAPA already use. No new AI-calling convention, no new
dependency, and no direct `google.genai` import anywhere in `qms_change_control_service.py` or
`routes/qms_change_control.py` — the only place a future Pharma Knowledge Engine swap would need to
touch is `qms_shared.py`, same as every other QMS module.

## Export

Reuses `services/doc_exporter.py::markdown_to_docx()` unchanged, same as Deviation/CAPA (a fourth
freeform `doc_type` string, `"Change-Control-Record"`, passed at the call site — no branching logic
touched). Print/PDF follows the existing app-wide `window.print()` convention on a
`marked.parse()`-rendered markdown report.

## UI

Adds a fourth sub-group ("Change Control") to the existing nested "Quality Management" sidebar
section, using the identical `qms-nav-group`/`qms-sub-item` markup Document Control/Deviation/CAPA
already use. Renders into its own `<main id="view-qms-change-control">` container via the same
generic `.sidebar-item[data-view]` click-handling loop — no new navigation framework.

The Enterprise Workspace shell (`workspace.css`/`workspace.js`, see `PROJECT_MEMORY/ARCHITECTURE.md`
§7) was deliberately not adopted here, for consistency: Document Control/Deviation/CAPA never
adopted it either (their `qms-page-header`/`qms-tabs` pattern predates it), so applying it only to
Change Control would make the QMS section internally inconsistent. Unifying all four QMS modules
onto the Enterprise Workspace shell is a reasonable future cleanup, not scoped to this module.

## Testing

- `tests/test_qms_database.py` — 8 new tests appended (schema, CRUD, narratives roundtrip, impact
  entries, action upsert, Deviation/CAPA linkage both directions, dashboard stats, delete).
- `tests/test_qms_routes.py` — 8 new tests appended (CRUD lifecycle, title-required validation,
  impact/implementation-plan AI routes with mocked Gemini, all 7 narrative endpoints, Deviation/CAPA
  linking, the full approval status map including rejection back to Draft, DOCX export, and the
  shared generic comment/audit-trail endpoints under `record_type='change_control'`).
- Full suite (`pytest`, excluding `-m slow`): **101 passed**, zero regressions.

Live browser verification (see `PROJECT_MEMORY/DECISIONS.md` DEC-021 for full detail) drove the
complete 13-stage lifecycle end-to-end and exercised two of the nine AI features live against the
real Gemini API successfully; a third (Risk Summary) hit a transient upstream `503 UNAVAILABLE`,
independently reproduced via a standalone script and confirmed to be an external API availability
condition, not a defect — `call_gemini()`'s existing exception handling degraded gracefully exactly
as designed.

# Quality Management Suite — Phase 1

**Added:** 2026-07-02
**Modules:** Document Control · Deviation Management · CAPA
**Status:** Complete, tested, manually verified end-to-end (including live Gemini calls)

---

## Why this exists

QMS is PharmaGPT's second major pillar, parallel in scope to the Validation pillar
(Risk / URS / Qualification / Validation Report suites). Phase 1 ships the three
highest-priority modules from the QMS roadmap — Document Control, Deviation
Management, CAPA — built to the same architectural pattern as the existing
suites, with Phase 2 (Change Control, Non-Conformance, OOS/OOT) and Phase 3
(Audit Management, Supplier Quality, Training Management, Complaint Management)
left as future additions.

## Architecture

Follows the existing per-suite convention (`risk_database.py` / `routes/risk.py`
/ `services/risk_service.py` / `prompts/risk_prompt.py` / `static/js/risk.js`)
with one deliberate structural change, disclosed and approved before
implementation: **shared polymorphic tables** for the four "Common Features"
every module needs (Attachments, Comments, Audit Trail, Approval/E-Signature),
instead of each module defining its own copies. This avoids tripling those
tables now and lets Phase 2/3 modules reuse them for free — just add a new
`record_type` string.

```
pharmagpt/
├── qms_database.py              # QMS_SCHEMA (all tables) + shared CRUD:
│                                 #   attachments, comments, audit trail, approvals,
│                                 #   record-numbering (generate_document_number,
│                                 #   generate_deviation_number, generate_capa_number),
│                                 #   QMS_META (enum source for /qms/meta)
├── qms_document_database.py     # CRUD: qms_documents, qms_document_versions,
│                                 #   qms_document_distribution, qms_document_training
├── qms_deviation_database.py    # CRUD: qms_deviations, qms_deviation_investigation,
│                                 #   qms_deviation_impact, qms_deviation_capa_link
├── qms_capa_database.py         # CRUD: qms_capas, qms_capa_actions, qms_capa_effectiveness
│
├── routes/
│   ├── qms_common.py             # /qms/dashboard, /qms/meta, generic
│   │                              #   attachments/comments/audit-trail/approval(GET) endpoints
│   ├── qms_documents.py          # /qms/documents/*  (+ approval POST, status transitions)
│   ├── qms_deviations.py         # /qms/deviations/* (+ approval POST, status transitions)
│   └── qms_capa.py               # /qms/capa/*       (+ approval POST, status transitions)
│
├── services/
│   ├── qms_shared.py             # call_gemini / stream_gemini / parse_json_response —
│   │                              #   used by all 3 QMS services instead of each
│   │                              #   re-implementing them (risk_service.py does this alone)
│   ├── qms_document_service.py   # AI regulatory-compliance review + markdown report builder
│   ├── qms_deviation_service.py  # AI Investigation Assistant + impact/CAPA suggestions + report
│   └── qms_capa_service.py       # AI draft/effectiveness suggestions + trend summary + report
│
├── prompts/
│   ├── qms_document_prompt.py    # SOP/Policy/etc. draft generation, compliance review
│   ├── qms_deviation_prompt.py   # Investigation (fishbone/5-Why/timeline), impact, CAPA seed
│   └── qms_capa_prompt.py        # CAPA draft, effectiveness checks, quality trend summary
│
└── static/
    ├── css/qms.css                # Shared QMS styles — reuses .modal/.badge/.form-field/
    │                               #   .btn-primary etc. already loaded from style.css/risk.css
    └── js/
        ├── qms_common.js          # Sidebar toggles, qmsFetch(), qmsStream() (SSE),
        │                          #   shared panel renderers (Attachments/Comments/
        │                          #   AuditTrail/Approval), unified QMS dashboard
        ├── qms_documents.js       # Document Control UI
        ├── qms_deviations.js      # Deviation Management UI
        └── qms_capa.js            # CAPA UI
```

### Why NOT one giant `qms_database.py`

The task brief asked for "a separate database layer `qms_database.py`". That's
honored literally for **schema** (one `QMS_SCHEMA` string, hooked into
`database.py::init_db()` exactly like `RISK_SCHEMA`/`QUAL_SCHEMA`) and for the
**shared tables' CRUD**. Splitting each module's *own* CRUD into
`qms_document_database.py` / `qms_deviation_database.py` / `qms_capa_database.py`
keeps files at the ~300-1000 line norm already established by
`risk_database.py` (565 lines) / `qual_database.py` (997 lines) instead of one
2000+ line file — a Single-Responsibility split, not a departure from "one
database layer for QMS."

### Existing one-shot document generation is untouched

`routes/validation.py`'s wizard already generates a single ad-hoc markdown
document for `doc_type='CAPA'` / `'Deviation'` (see `prompts/capa_prompt.py`,
`prompts/deviation_prompt.py`, saved into `generated_documents`). That feature
is unrelated to and unmodified by this work — it's a quick one-shot draft tool,
whereas the new QMS modules are stateful, workflow-driven records with
lifecycle, approvals, linkage, and reporting. Both coexist. The new AI features
use their own `prompts/qms_*_prompt.py` files, referencing the older prompts'
narrative structure only as inspiration.

## Data model

### Shared (record_type ∈ `'document' | 'deviation' | 'capa'`)

| Table | Purpose |
|---|---|
| `qms_attachments` | File attachments, keyed by `(record_type, record_id)` |
| `qms_comments` | Threaded comments |
| `qms_audit_trail` | Immutable action log (mirrors `val_audit_trail`, made polymorphic) |
| `qms_approvals` | E-signature/approval trail — `performed_by` + `role` + `electronic_sig` (typed name, no PKI — matches the `risk_approval`/`qual_approvals` convention; no auth system exists yet, that's a v0.9 roadmap item) |

### Document Control

`qms_documents` (doc_number, doc_type, title, department, version, status,
effective/review/expiry dates, owner/reviewer/approver, content markdown,
ai_review_data) → `qms_document_versions`, `qms_document_distribution`,
`qms_document_training`.

Status lifecycle: `Draft → Under Review → Pending Approval → Effective →
Under Revision → Obsolete`.

Numbering: `generate_document_number(doc_type, department)` → e.g. `SOP-QA-0001`
(department abbreviated to initials if multi-word, used as-is if already an
acronym like "QA").

### Deviation Management

`qms_deviations` (deviation_number, title, type, category, department, area,
product, batch_lot, equipment, description, status, risk_level) →
`qms_deviation_investigation` (fishbone_data / five_why_data / timeline_data
JSON, root_cause_category/statement), `qms_deviation_impact`,
`qms_deviation_capa_link`.

Status lifecycle: `Initiated → Under Investigation → Root Cause Identified →
Impact Assessed → Risk Assessed → CAPA Assigned → QA Review → Approved →
Closed` (or `Rejected`).

Numbering: `generate_deviation_number()` → `DEV-2026-0001` (year + sequence).

### CAPA

`qms_capas` (capa_number, title, capa_source, source_reference, problem_statement,
root_cause, status) → `qms_capa_actions` (action_type Corrective/Preventive,
owner, due_date, status, escalation fields), `qms_capa_effectiveness`.

Status lifecycle: `Open → Root Cause Analysis → CA Planned → PA Planned →
Implementation → Effectiveness Check → QA Review → Closed` (or `Rejected`).

Numbering: `generate_capa_number()` → `CAPA-2026-0001`.

### Integration

`Deviation → CAPA` is a real link (`qms_deviation_capa_link`), populated either
manually (`POST /qms/deviations/<id>/link-capa`) or via the AI CAPA Suggestion
flow, which drafts problem statement / root cause / corrective / preventive
actions from a deviation's investigation and creates + links a new CAPA in one
step (`qmsDevCreateCapaFromSuggestion()` in `qms_deviations.js`). Linking a
CAPA auto-transitions the deviation to `CAPA Assigned`.

All three master tables carry a nullable `project_id` (`ON DELETE SET NULL`,
not `CASCADE`) so quality records survive deletion of the validation
project/equipment record they reference — a deliberate choice, since GxP
records must outlive the equipment record that originated them.

## AI features (Phase 1 subset of the full QMS AI list)

| Feature | Where |
|---|---|
| SOP/document draft generation (streamed) | `POST /qms/documents/<id>/generate` |
| Regulatory Compliance Review | `POST /qms/documents/<id>/review` |
| AI Investigation Assistant (fishbone + 5-Why + timeline + root cause) | `POST /qms/deviations/<id>/investigate` |
| Impact Assessment suggestions | `POST /qms/deviations/<id>/suggest-impact` |
| CAPA draft suggestion (from a deviation) | `POST /qms/deviations/<id>/suggest-capa` |
| CAPA draft suggestion (standalone) | `POST /qms/capa/<id>/suggest-draft` |
| Effectiveness check suggestions | `POST /qms/capa/<id>/suggest-effectiveness` |
| Quality Trend Summary | `GET /qms/capa/trend-summary` |

All AI calls go through `services/qms_shared.py::call_gemini()` /
`stream_gemini()`, using the same `gemini_client` singleton and
`PHARMA_SYSTEM_PROMPT` persona as every other suite.

## Export

DOCX export reuses `services/doc_exporter.py::markdown_to_docx()` and
`services/docx_generator.py` unchanged except for additive entries in
`_DOC_TYPE_LABELS` (`SOP`, `Policy`, `Manual`, `Work Instruction`,
`Deviation-Record`, `CAPA-Record`, etc.) — no branching logic was touched.
PDF export follows the existing app-wide convention (client-side
`window.print()` on a `marked.parse()`-rendered markdown report) rather than
introducing a new server-side PDF pipeline.

## UI

One nested **"Quality Management"** sidebar section (collapsible), containing
three independently-labeled sub-groups (Document Control / Deviation
Management / CAPA) — chosen over three flat top-level sections (the pattern
used by Risk/URS/Qual/Report) because Phase 2/3 will add 6 more modules, and a
flat structure would leave the sidebar with 9 top-level suite sections.

Each module renders into its own `<main id="view-qms-*">` container using the
existing generic `.sidebar-item[data-view]` click-handling loop already in
`templates/index.html` — no new navigation framework was introduced.

> **Note on the pre-existing suites:** while wiring this in, `.sidebar` was
> found to render with `display:none` at narrow viewport widths — this is
> `style.css`'s existing `@media` mobile breakpoint (line ~2825), not a bug.
> Separately, the Risk/URS/Qual/Report suites' sidebar nav containers
> (`risk-nav-items` etc.) exist in the DOM but are marked
> `style="display:none"` with no visible toggle wired to them — those suites
> currently have no live navigation entry point in this build. That's
> pre-existing and out of scope here; QMS's sidebar entries are fully wired
> and visible, not modeled on that dormant pattern.

## Testing

- `tests/test_qms_database.py` — CRUD + schema tests for all 3 modules + shared tables, using the existing `db_path` fixture.
- `tests/test_qms_routes.py` — Flask test-client integration tests for the full route surface, using a new `client` fixture (added to `tests/conftest.py`, composes `db_path`). AI-backed routes are tested with `call_gemini`/`stream_gemini` monkeypatched to canned output — the real Gemini pipeline was verified manually end-to-end in a live browser preview (draft generation, AI investigation, impact/CAPA/effectiveness suggestions, trend summary) before these tests were written.
- Full existing suite (`pytest`, excluding `-m slow`) passes unchanged: 83 passed.

Two real bugs were caught and fixed during test-writing:
1. `generate_document_number()` mishandled a single-word, already-abbreviated department (e.g. `"QA"` → `"Q"` instead of `"QA"`) — fixed to use short single-word departments as-is.
2. A Windows-specific file handle race between `send_file` (download) and `os.remove()` (delete) in the test client — fixed on the test side (fully consuming/closing the download response before deleting); not a production concern since a real WSGI server closes the file handle as part of the request lifecycle.

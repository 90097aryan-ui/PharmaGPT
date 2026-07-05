# DECISIONS.md — PharmaGPT Architectural Decision Log

> Part of the permanent [PROJECT_MEMORY](CLAUDE.md) set. **This file is append-only.** Never
> rewrite or delete a past decision — if a decision is later reversed, add a new entry that
> supersedes it and cross-reference the old ID. Reconstructed from `docs/ARCHITECTURE.md`,
> `docs/QMS_PHASE1.md`, top-level and `docs/ROADMAP.md`, `SYSTEM_ARCHITECTURE_DOCUMENT_PROCESSING.md`,
> and `docs/CODE_REVIEW.md` as of 2026-07-02.

---

### DEC-001 — Single Integrated Platform

**Date:** Project inception (v0.1–v0.2)
**Problem Statement:** Whether to build PharmaGPT as one integrated application covering chat,
document management, and validation-document generation, or as separate tools.
**Options Considered:** (a) Separate tools/scripts per capability; (b) one integrated Flask
application with shared project/document context.
**Decision Taken:** One integrated platform — a single Flask app where chat, documents, and
generation all share the same project context.
**Reason:** A validation engineer's workflow moves fluidly between asking questions, referencing
uploaded manuals, and generating formal documents — splitting these into separate tools would
force constant context-switching and duplicate project/document state.
**Benefits:** Single source of truth for project context; documents uploaded once are usable
everywhere (chat RAG, validation generation, insights).
**Trade-offs:** Larger single codebase; harder to scale/deploy sub-components independently.
**Impact:** All subsequent modules (Knowledge Base, Risk/URS/Qual/Report, QMS) were built as
blueprints within the same app rather than separate services.
**Future Review Required:** Revisit if/when a module needs independent scaling (see DEC-016).

---

### DEC-002 — Flask Monolith Architecture, No ORM

**Date:** v0.2 onward, formalized in `docs/ARCHITECTURE.md`
**Problem Statement:** How to structure the backend and access the database.
**Options Considered:** (a) Flask monolith with raw `sqlite3`; (b) Flask + SQLAlchemy ORM; (c)
FastAPI or Django; (d) microservices split by domain.
**Decision Taken:** Flask monolith, raw `sqlite3` (no ORM).
**Reason (quoted):** "Zero infrastructure — runs with `python app.py`, no containers or
services"; "Easy to debug — single process, no distributed tracing needed"; ORM avoided because it
"avoids dependency weight for a simple schema; easy to inspect DB directly."
**Benefits:** Minimal operational overhead during rapid v0.x development; direct SQL is easy to
reason about and debug with a plain SQLite browser.
**Trade-offs:** No automatic migrations, no query builder safety net, manual connection
management in every function.
**Impact:** Every domain module (`risk_database.py`, `qual_database.py`, `qms_database.py`, etc.)
follows the same raw-`sqlite3` pattern — this is now a hard convention, not a per-module choice.
**Future Review Required:** Revisit at the PostgreSQL migration point (DEC-003) — an ORM becomes
more attractive once multi-user concurrent writes are common.

---

### DEC-003 — SQLite Initially, with a PostgreSQL Migration Path

**Date:** v0.1 onward
**Problem Statement:** Which database engine to use for a single-developer, pre-multi-user
product.
**Options Considered:** (a) SQLite; (b) PostgreSQL from day one; (c) a hosted DB service.
**Decision Taken:** SQLite now; PostgreSQL migration planned for v1.0.
**Reason (quoted):** "Zero-config for v0.x development; migration path documented for v1.0."
**Benefits:** No database server to install/manage locally or in early deployment; the whole DB is
one portable file.
**Trade-offs:** No real concurrent-write scalability; requires a persistent disk mount on Render
to survive redeploys (see DEC-015); no built-in replication/backup tooling.
**Impact:** All schema code must remain reasonably Postgres-portable (avoid SQLite-only syntax)
per [CLAUDE.md](CLAUDE.md) coding standards, even though Postgres isn't wired up yet.
**Future Review Required:** Mandatory review at v1.0 (multi-user/RBAC makes single-writer SQLite
untenable).

---

### DEC-004 — ThreadPoolExecutor Instead of Celery for Background Jobs

**Date:** 2026-07-01, Enterprise Document Processing Engine rewrite
**Problem Statement:** Long-running document text extraction was blocking the HTTP request thread,
causing gunicorn worker timeouts and 500 errors on large files (production incident on Render).
Needed a background-execution strategy.
**Options Considered:** (a) `concurrent.futures.ThreadPoolExecutor` in-process; (b) Celery +
Redis; (c) `ProcessPoolExecutor` for true process isolation.
**Decision Taken:** `ThreadPoolExecutor`, wrapped behind a `JobRunner` interface
(`services/job_runner.py`), with a `CeleryJobRunner` stub reserved for future use.
**Reason:** The current stack (Flask + gunicorn + SQLite on Render) has no Redis and no message
broker; adding one purely for background jobs would be disproportionate infrastructure for the
current scale. Progress/results are persisted to SQLite (not process memory), so status polling
already works correctly across gunicorn's multiple worker processes — the main practical benefit
Celery would add (cross-process state) is already achieved.
**Benefits:** No new infrastructure dependency; simple to reason about; swappable later behind the
same interface.
**Trade-offs:** CPython threads cannot be forcibly killed — a hung extraction attempt on a
malformed file is abandoned (daemon thread), not terminated, though it cannot block the rest of
the pipeline since each page attempt runs in its own fresh thread with a join timeout.
**Impact:** `services/job_runner.py::ThreadPoolJobRunner` is the standard for all future
background work in this codebase; do not introduce a second background-execution mechanism.
**Future Review Required:** Revisit if/when Redis is introduced for another reason (e.g., caching,
rate limiting) — implementing `CeleryJobRunner` at that point becomes low-cost. Also revisit if
true process-level kill semantics are needed (`ProcessPoolExecutor`).

---

### DEC-005 — Vanilla JavaScript SPA, No Frontend Framework

**Date:** v0.2 onward
**Problem Statement:** How to build an interactive single-page frontend without React/Vue/etc.
**Options Considered:** (a) Vanilla JS, IIFE-per-module, no build step; (b) React/Vue with a
bundler (Webpack/Vite); (c) server-rendered multi-page app.
**Decision Taken:** Vanilla JavaScript SPA — one IIFE module per feature area, `display`-toggled
divs instead of a client-side router, no build toolchain.
**Reason (quoted):** "No build toolchain; reduces moving parts during rapid v0.x development";
"SPA kept simple enough to manage without a framework."
**Benefits:** Zero build step (edit → refresh); no `node_modules`/bundler dependency; easy to
onboard on a Windows dev machine with just Python installed.
**Trade-offs:** No component reactivity system — state updates and DOM updates are manual; code
duplication risk across modules (already flagged in `docs/CODE_REVIEW.md`, e.g. duplicated
`esc()`/`escHtml()` helpers).
**Impact:** All 18 JS modules follow the IIFE-on-`window` convention; new frontend code must
follow the same pattern rather than introducing a framework for just one module.
**Future Review Required:** Revisit if the frontend complexity/state-management burden grows
significantly (e.g., once RBAC and multi-user real-time features land in v0.9).

---

### DEC-006 — `temperature=0.3` for Validation Document Generation

**Date:** v0.6, Validation Document Generator
**Problem Statement:** Formal validation documents (URS, IQ, OQ, PQ, etc.) need consistent
structure across generations; the default Gemini temperature is tuned for conversational variety.
**Options Considered:** (a) Default temperature for all Gemini calls; (b) lower, fixed temperature
specifically for document-generation calls.
**Decision Taken:** `temperature=0.3` for all structured document-generation calls (validation
wizard, and later QMS document drafting); default/higher temperature retained for conversational
chat.
**Reason (quoted):** "Consistent document structure; higher temps vary section ordering."
**Benefits:** Predictable, audit-friendly document structure across repeated generations of the
same doc type.
**Trade-offs:** Slightly less creative/varied phrasing — acceptable for formal regulatory
documents.
**Impact:** Any new AI-generation feature producing a structured document (not free-form chat)
should default to `temperature=0.3` unless a specific reason argues otherwise.
**Future Review Required:** None currently planned.

---

### DEC-007 — Client-Side PDF Export via `window.print()`

**Date:** v0.6, Validation Document Generator
**Problem Statement:** Users need to export generated validation documents as PDF, in addition to
DOCX.
**Options Considered:** (a) Browser-native `window.print()` with print-specific CSS; (b) server-side
rendering via WeasyPrint/GTK; (c) headless-Chrome PDF rendering.
**Decision Taken:** Client-side `window.print()`.
**Reason (quoted):** "No GTK/WeasyPrint dependency on Windows dev environment; zero server-side
overhead."
**Benefits:** No new server dependency, no Windows-specific GTK installation headache, instant
availability.
**Trade-offs:** Less control over pixel-perfect PDF output than a dedicated rendering engine;
depends on the user's browser print dialog.
**Impact:** `@media print` CSS rules in `style.css` govern PDF output layout; the `.doc-viewer`
component is deliberately the one light-background UI element so it matches printed output.
**Future Review Required:** Server-side PDF export (WeasyPrint or headless Chrome) is an explicit
v1.0 roadmap item once cross-platform deployment (Docker) removes the Windows-GTK constraint.

---

### DEC-008 — Keyword/Jaccard RAG Before Vector RAG

**Date:** v0.5, AI Document Intelligence
**Problem Statement:** Need a way to surface relevant chunks of uploaded documents into chat/
generation context without loading the entire corpus into every prompt.
**Options Considered:** (a) Keyword-overlap search (Jaccard scoring on 400-word chunks, 60-word
overlap); (b) embeddings-based vector search from the start.
**Decision Taken:** Keyword/Jaccard search first; vector RAG stubs (`generate_embedding`,
`upsert_to_vector_store`, `vector_search`) written but left unimplemented (`NotImplementedError`).
**Reason (quoted):** "Ships faster; establishes correctness baseline before embeddings."
**Benefits:** No embeddings API cost/latency, no vector store infrastructure, immediately useful.
**Trade-offs:** Lower recall/precision than semantic search, especially for paraphrased queries;
whole-corpus loading into RAM on every search (flagged as a performance issue in
`docs/CODE_REVIEW.md`).
**Impact:** `document_search.py` remains the production RAG path; the vector-search stub functions
exist as a clearly-marked seam for the v0.8 upgrade.
**Future Review Required:** Scheduled for v0.8 — replace with Gemini `text-embedding-004` (or
equivalent) + Chroma (local) or Pinecone (cloud), benchmarked against the keyword baseline before
full cutover.

---

### DEC-009 — Document Intelligence Engine Replacing the Old Synchronous Extractor

**Date:** 2026-07-01
**Problem Statement:** A real production upload (48-page/1.43MB pharmaceutical manual) caused a
synchronous, single-engine (`pdfplumber`-only) extraction call to run past the gunicorn worker
timeout, resulting in a `SIGKILL` and an HTTP 500 for the user. The old extractor had no timeout,
no fallback engine, and no memory management.
**Options Considered:** (a) Patch the existing synchronous extractor with a timeout; (b) full
rewrite as an async, multi-engine, page-level-fallback pipeline running in a background thread.
**Decision Taken:** Full rewrite. `services/extractor.py` and `services/pdf_reader.py` were
deleted outright, not kept as a fallback path.
**Reason:** A single timeout patch would not address the underlying single-engine fragility
(certain malformed/complex PDFs fail entirely on `pdfplumber` but succeed on `pypdf` or PyMuPDF),
nor the fact that extraction was blocking the request thread at all. The problem required both a
background-execution model and a resilient multi-engine fallback strategy.
**Benefits:** Uploads return HTTP 201 immediately regardless of document size; per-page timeout
and fallback mean a single bad page no longer fails the whole document; quality scoring gives
users visibility into partial-extraction results; retry is always available since the source file
is never deleted.
**Trade-offs:** Meaningfully more complex pipeline (6 new files under `services/extraction/`);
CPython's inability to force-kill a thread means a hung attempt is abandoned rather than
terminated (mitigated by giving each page attempt its own thread, so it cannot block the rest of
the document).
**Impact:** All future extraction-adjacent work (e.g., real OCR, cloud document intelligence APIs)
should be added as a new `ExtractionEngine` subclass in the existing registry, not as a parallel
mechanism.
**Future Review Required:** Real OCR (`pytesseract` or a cloud OCR API) to replace
`OCRPlaceholderEngine`; `ProcessPoolExecutor` if true kill-on-timeout semantics become necessary;
password-protected PDF support with user-supplied passwords.

---

### DEC-010 — Shared Audit Trail (Polymorphic, QMS)

**Date:** QMS Phase 1 (uncommitted)
**Problem Statement:** Document Control, Deviation, and CAPA all need an audit trail; building
three separate audit tables would triple maintenance for identical behavior, and Phase 2/3 QMS
modules will need the same capability again.
**Options Considered:** (a) One audit table per module; (b) a single polymorphic audit table keyed
by `(record_type, record_id)`.
**Decision Taken:** Single polymorphic `qms_audit_trail` table, mirroring the pre-existing
`val_audit_trail` pattern from the Validation Workspace but generalized across record types.
**Reason (quoted):** "This avoids tripling those tables now and lets Phase 2/3 modules reuse them
for free — just add a new `record_type` string."
**Benefits:** One implementation to maintain and test; new modules get audit trail "for free."
**Trade-offs:** Slightly less type-safety than a dedicated table per module (relies on application
code to keep `record_type` values consistent).
**Impact:** Every future QMS module (Change Control, Non-Conformance, OOS/OOT, Audit, Supplier
Quality, Training, Complaint Management) should add itself as a new `record_type` value rather
than creating a new audit table.
**Future Review Required:** None currently planned — pattern is expected to hold through Phase 3.

---

### DEC-011 — Shared Attachments, Comments, and Approval Engine (Polymorphic, QMS)

**Date:** QMS Phase 1 (uncommitted)
**Problem Statement:** Same reasoning as DEC-010, applied to file attachments, threaded comments,
and the e-signature/approval workflow.
**Options Considered:** Same as DEC-010.
**Decision Taken:** `qms_attachments`, `qms_comments`, and `qms_approvals` are all polymorphic on
`(record_type, record_id)`, `record_type ∈ {document, deviation, capa}` today, extensible to future
QMS modules.
**Reason:** Same rationale as DEC-010 — avoid per-module duplication, make future modules cheap to
add.
**Benefits:** Consistent UI/behavior for attachments, comments, and approvals across every QMS
module; centralized generic GET endpoints in `routes/qms_common.py`.
**Trade-offs:** Same as DEC-010.
**Impact:** Related decision — QMS master tables (`qms_documents`/`qms_deviations`/`qms_capas`)
use a **nullable** `project_id` with `ON DELETE SET NULL` (not `CASCADE`), a deliberate choice
since GxP quality records must legally outlive the equipment/project record that originated them.
E-signatures use `electronic_sig` (typed name, no PKI) — matching the pre-existing
`risk_approval`/`qual_approvals` convention, acceptable because no authentication system exists
yet (v0.9 roadmap item).
**Future Review Required:** Revisit the typed-name e-signature approach once real authentication
(v0.9) exists — it may need to become a proper cryptographic/PKI-backed signature for full 21 CFR
Part 11 compliance.

---

### DEC-012 — Modular Suite Architecture (Blueprint + Database + Service + Prompt + JS per Domain)

**Date:** Established v0.6–2026-06-30, formalized in QMS Phase 1
**Problem Statement:** As PharmaGPT grew from a single chat app into a multi-suite platform (Risk,
URS, Qual, Report, then QMS), needed a consistent way to add a new domain without one module's code
sprawling across unrelated files.
**Options Considered:** (a) One large shared database/routes/services file for everything; (b) a
strict per-domain convention: `<domain>_database.py`, `routes/<domain>.py`,
`services/<domain>_service.py`, `prompts/<domain>_prompt.py`, `static/css/<domain>.css`,
`static/js/<domain>.js`.
**Decision Taken:** Strict per-domain file convention (option b).
**Reason (quoted, re: QMS specifically):** "Splitting each module's own CRUD into
`qms_document_database.py` / `qms_deviation_database.py` / `qms_capa_database.py` keeps files at
the ~300-1000 line norm already established by `risk_database.py` (565 lines) / `qual_database.py`
(997 lines) instead of one 2000+ line file — a Single-Responsibility split, not a departure from
'one database layer for QMS.'"
**Benefits:** Predictable file locations for any given domain; easy to onboard a new contributor
or a new Claude session to "where does X live"; keeps individual files within a manageable size.
**Trade-offs:** More files overall; shared cross-domain logic (like the QMS polymorphic tables,
DEC-010/DEC-011) must be deliberately factored into its own shared file (`qms_database.py`,
`qms_shared.py`) rather than living in one domain's file.
**Impact:** This is now the required pattern — see [CLAUDE.md](CLAUDE.md) Development Rules and
[ARCHITECTURE.md](ARCHITECTURE.md) §3 folder structure.
**Future Review Required:** None — expected to hold for all future modules (Change Control,
Training, Audit, Manufacturing Excellence Suite).

---

### DEC-013 — AI-First Document Generation, Deterministic Review Kept Separate

**Date:** v0.6 onward
**Problem Statement:** Whether AI-generated content should also be AI-scored/reviewed, or whether
document quality/compliance scoring should be deterministic.
**Options Considered:** (a) Use Gemini to both generate and score/review documents; (b) generate
via Gemini, but score/review via a deterministic, rule-based engine.
**Decision Taken:** AI (Gemini) generates content; a separate deterministic engine
(`pharmagpt/review/` — `review_engine.py`, `review_rules.py`, `review_models.py`,
`review_formatter.py`) scores it against a fixed compliance-check matrix per document type, with
no AI calls in the review path.
**Reason:** A deterministic, rule-based reviewer gives reproducible, auditable scores — important
for a regulated-industry tool where "why did this document score X" needs a non-AI, inspectable
answer. An in-memory SHA-1-keyed cache avoids re-scoring identical content.
**Benefits:** Reproducible scoring; no additional AI cost/latency for review; scoring logic is
directly inspectable and testable.
**Trade-offs:** Review rules must be manually maintained per document type as new doc types are
added; cannot catch nuanced compliance issues an AI reviewer might catch (this exists separately
as the AI-powered "regulatory compliance review" feature in QMS Document Control, which is
AI-based and complements rather than replaces the deterministic reviewer).
**Impact:** New document types added to the Validation wizard should get a corresponding entry in
`review_rules.py`'s compliance matrix.
**Future Review Required:** None currently planned.

---

### DEC-014 — Documentation Versioning Reconciliation (Meta-Decision)

**Date:** 2026-07-02, at PROJECT_MEMORY creation
**Problem Statement:** The repository's `.md` files disagree on the current version number and on
which of several duplicate documents (`ROADMAP.md` vs `docs/ROADMAP.md`, `CHANGELOG.md` vs
`docs/CHANGELOG.md`) is authoritative. Specifically: top-level `PROJECT_STATUS.md`/`ROADMAP.md`
say v0.7; `API.md` references "v0.6"/"v0.9" inconsistently; `requirements.txt`'s header comment
says v0.9.5; the latest git commit message says "Release v0.9.8"; `docs/QMS_PHASE1.md` and the
top-level `CHANGELOG.md` describe QMS Phase 1 work dated 2026-07-02 that is not reflected in
`PROJECT_STATUS.md`'s architecture/folder-structure sections at all.
**Options Considered:** (a) Pick one version string arbitrarily; (b) treat `git log` as the source
of truth for the current committed version, and treat the newer-dated file in each duplicate pair
as authoritative, documenting the discrepancy rather than silently resolving it.
**Decision Taken:** Option (b). **Current committed version = v0.9.8** (last commit message,
`684ca7d`, 2026-07-02). **`docs/ROADMAP.md`** is authoritative over the stale top-level
`ROADMAP.md` (the `docs/` version includes the QMS Phase 1 entry and a "Known Technical Debt"
table; the top-level version predates QMS and was never updated). **Top-level `CHANGELOG.md`** is
authoritative over `docs/CHANGELOG.md` (the top-level version has the `[Unreleased]` QMS Phase 1
entry dated 2026-07-02; `docs/CHANGELOG.md` stops at `[0.7.0]`).
**Reason:** Git history cannot drift the way hand-edited Markdown can; commit messages and dates
are the least-disputable record of "what actually happened when." Between two duplicate docs, the
one containing the more recent, more complete information wins.
**Benefits:** Gives future Claude sessions and developers a single, stated answer instead of
silently picking whichever file they happen to open first.
**Trade-offs:** The reconciliation is a snapshot judgment, not a structural fix — the underlying
problem (two ROADMAP files, two CHANGELOG files, version strings hand-typed into multiple `.md`
headers) still exists in the repository and will drift again unless addressed.
**Impact:** [PROJECT_MEMORY](CLAUDE.md) documents are now the entry point and should be kept in
sync going forward (see [CLAUDE.md](CLAUDE.md) Documentation Rules) precisely so this kind of
drift doesn't recur for anything that matters operationally.
**Future Review Required:** Recommended cleanup (not yet actioned): delete or merge the duplicate
`ROADMAP.md`/`CHANGELOG.md` pairs into single root-level files, and adopt a single machine-readable
version source (e.g., a `VERSION` file or `__version__` string) referenced by all docs instead of
hand-typed version numbers.

---

### DEC-015 — Render Deployment Strategy (Persistent Disk for SQLite)

**Date:** 2026-06-29 (Render deployment fixes), formalized in `render.yaml`
**Problem Statement:** Render's default filesystem is ephemeral — a SQLite database file written
to the default working directory is lost on every restart, redeploy, or idle-spindown.
**Options Considered:** (a) Deploy with no persistence and accept data loss; (b) mount a Render
persistent disk and point `DB_PATH` at it; (c) migrate to a managed Postgres add-on immediately.
**Decision Taken:** Mount a 1GB Render persistent disk at `/var/data`, set
`DB_PATH=/var/data/pharmagpt.db`; keep SQLite for now (consistent with DEC-003).
**Reason:** Immediate, low-effort fix that preserves the SQLite-first strategy without forcing a
premature Postgres migration; `gunicorn --workers=2 --threads=4 --timeout=60` was tuned alongside
this to balance concurrency against Render's starter-plan resources.
**Benefits:** Data survives restarts/redeploys without introducing a new database dependency.
**Trade-offs:** Still single-writer SQLite — does not solve multi-instance/multi-region scaling;
remains a documented deployment risk for anyone deploying this repo elsewhere without an
equivalent persistent volume.
**Impact:** `render.yaml` and `Procfile` both encode this; any change to the deployment target must
preserve either the persistent-disk approach or complete the Postgres migration (DEC-003) first.
**Future Review Required:** Superseded by the PostgreSQL migration once v1.0 lands (DEC-003).

---

### DEC-016 — Background Document Processing (see also DEC-004 and DEC-009)

**Date:** 2026-07-01
**Problem Statement:** Cross-reference entry — background processing strategy is fully documented
under DEC-004 (why ThreadPoolExecutor, not Celery) and DEC-009 (why the extraction engine itself
was rewritten). This entry exists so "background document processing" is discoverable as its own
search term in this log.
**Decision Taken:** See DEC-004 and DEC-009.
**Impact:** See DEC-004 and DEC-009.
**Future Review Required:** See DEC-004 and DEC-009.

---

### DEC-017 — Enterprise Workspace Layout Pattern (Reusable Shell), First Applied to Generate Document

**Date:** 2026-07-04, Validation & Usability Testing Sprint
**Problem Statement:** Real validation testing on Generate Document surfaced what looked like a
UX/layout complaint ("the Dashboard stays visible above the wizard," "half the screen is blank
white space," "no professional way back to the project," "doesn't feel like enterprise software").
Root-cause investigation found this was not primarily a visual-design problem — it was a genuine
HTML structural bug: the `.app-body` flex container (which holds `.sidebar` + every `<main
id="view-*">` view) was closed one `</main>` too early, immediately after the old Validation
Document Generator view (`view-validation`), instead of after the very last view in the file. Every
view defined after that point — Generate Document, all four Risk Management views, all four URS
views, Qualification, Validation Report, and all four QMS views — was rendered as a sibling of
`.app-body` at the `<body>` level instead of inside it. Visually this produced exactly the reported
symptoms: the (now-empty) `.app-body` flex box still consumed its allotted vertical space above the
misplaced view, and the misplaced view rendered full-width with no sidebar next to it. This
confirms the bug was pre-existing and affected the QMS suite too (verified live), not something
introduced by this sprint's work.
**Options Considered:** (a) Patch only Generate Document's markup/CSS to visually compensate for
the misplaced position (e.g. absolute-position a fake sidebar-width offset); (b) fix the actual
HTML nesting so every view lives inside `.app-body` as originally intended, then build a proper
reusable workspace shell on top of the now-correctly-nested Generate Document view.
**Decision Taken:** Option (b). Moved the stray `</div>` (closing `.app-body`) from immediately
after `view-validation` to immediately after the last QMS view (`view-qms-capa`), so every
existing view is nested correctly. On top of that fix, introduced a new reusable **Enterprise
Workspace** layout pattern: `pharmagpt/static/css/workspace.css` (`.ent-workspace` /
`.ent-ws-header` / `.ent-ws-toolbar` / `.ent-ws-breadcrumb` / `.ent-ws-progress` / `.ent-ws-body`)
and `pharmagpt/static/js/workspace.js` (`Workspace.enter()/exit()`, `renderBreadcrumb()`,
`renderProgress()`, `confirmDialog()`). Generate Document (`gen_document.js` + its
`view-gen-doc` markup) is the first and, as of this writing, only consumer, but the shell is
domain-agnostic by design — see [ARCHITECTURE.md](ARCHITECTURE.md) §7 for the adoption contract
future modules (Risk, URS, Qualification, Validation Report, QMS Change Control/CAPA/Deviation/NCR/
OOS-OOT) should follow.
**Reason:** Fixing only the symptom (Generate Document specifically) would have left the identical
bug live for every other post-validation view, including the QMS suite that PROJECT_STATUS.md
already describes as "fully wired" and in active use — an enterprise pharma customer could hit the
same blank-space/no-sidebar defect there next. A shared, reusable shell was chosen over a
one-off Generate-Document-specific header because the sprint's explicit objective was "this becomes
the standard workspace template for PharmaGPT... future modules must reuse this layout," and because
duplicating header/breadcrumb/toolbar/progress markup per module would violate the project's
existing anti-duplication rule (DEC-012/DEC-013 precedent).
**Benefits:** One root-cause fix resolves the reported defect for Generate Document *and* silently
fixes the same pre-existing defect on every Risk/URS/Qual/Report/QMS view. The new shell gives every
future module a ready-made, consistent header/breadcrumb/toolbar/progress pattern with zero new
CSS/JS required beyond wrapping their own view in the right class names and calling into
`window.Workspace`. The discard/leave confirmation dialogs reuse the existing `.modal` /
`.btn-primary` / `.btn-secondary` / `.btn-danger` tokens (no new modal CSS invented), consistent
with DEC-012's per-domain-file convention and the project's DRY principle.
**Trade-offs:** `body.ent-ws-active` hides the entire global top header (brand bar, Gemini status
badge, Clear Chat button) while any workspace is open, per the sprint's explicit "only the global
sidebar should remain" requirement — this is a deliberate, scoped exception to the normal app chrome,
not a general header removal (Dashboard/Chat/Documents/Insights/Knowledge Base/Validation Workspace
are unaffected). The wizard body content itself (`.gd-panel`, `.gd-step-content`, step-specific
buttons) was deliberately left untouched in `style.css` — only the shell chrome (outer container,
header, toolbar, progress bar) was extracted into the new generic classes, per the sprint's "do not
redesign business logic" constraint.
**Impact:** Any future module adopting a full-screen, stateful multi-step or multi-tab flow should
wrap its view in `<main class="ent-workspace">` with `.ent-ws-header` / `.ent-ws-toolbar` /
`.ent-ws-progress` (optional) rows and call `window.Workspace.enter()/exit()`,
`renderBreadcrumb()`, `renderProgress()`, and `confirmDialog()` rather than reinventing a
module-specific header/breadcrumb/toolbar/confirm-dialog pattern. The existing `.vw-ws-topbar`
pattern in the Validation Workspace (`view-val-project`) was evaluated as a possible precedent but
not merged into this abstraction in this sprint — it remains its own component; unifying it with
`.ent-workspace` is a reasonable future cleanup, not done here to avoid scope creep beyond Generate
Document.
**Future Review Required:** When Risk/URS/Qualification/Validation Report sidebar navigation is
finally wired (see the long-standing "Known gap" in [ARCHITECTURE.md](ARCHITECTURE.md) §5) or when
QMS Phase 2/3 modules (Change Control, Non-Conformance, OOS/OOT, Audit, Supplier Quality, Training,
Complaint Management) are built, adopt this same Enterprise Workspace shell rather than each
inventing its own header/toolbar. Consider unifying `.vw-ws-topbar` into `.ent-ws-header` at that
point if the duplication becomes bothersome.

---

### DEC-018 — "Executive Office" Design System Redesign (Navy/Blue → Warm Business-Attire Palette)

**Date:** 2026-07-05
**Problem Statement:** The user requested a complete visual redesign of PharmaGPT — a UI-only
change, explicitly excluding backend/API/database/route/business-logic changes — to move the
product from "an old dark enterprise application" feel to a premium executive-office aesthetic
comparable to Stripe Dashboard, Linear, Notion Enterprise, Arc Browser, and modern SAP Fiori, using
a specified business-attire colour palette (Soft White, Warm Ivory, Stone, Sand, Beige, Taupe,
Walnut Brown, Charcoal, Soft Olive/Sage accents) in place of the existing navy/blue theme
(`#1E293B`/`#0F4C81`/`#1565C0` family, documented in `docs/DESIGN_SYSTEM.md` v1.0).
**Options Considered:** (a) Hand-edit every colour reference file-by-file across all 7 CSS files
(~3,750 + ~4,600 lines) and 11 JS modules with inline styles; (b) redefine the shared `:root` token
block in `style.css` (already the single source of truth every suite CSS reuses per DEC-012) and
programmatically sweep the remaining hardcoded hex/`rgb()`/`rgba()` literals that bypassed those
tokens, using one consistent old-hex→new-hex translation table across every file.
**Decision Taken:** Option (b). Repointed the existing `:root` variables (`--navy`, `--blue`,
`--blue-light`, `--accent`, `--sidebar-bg`, `--sidebar-hover`, `--sidebar-active`, `--success`,
`--warning`, `--info`, `--error`, `--bg`, `--surface`, `--border`, `--divider`, `--text`,
`--text-muted`, `--text-disabled`) to the new palette rather than renaming them, so every existing
`var()` consumer across `style.css`, `workspace.css`, `risk.css`, `urs.css`, `qual.css`,
`report.css`, and `qms.css` repainted for free. Added new tokens (`--bg-secondary`, `--radius-lg`,
`--radius-input`) for concepts the old system didn't have (a distinct secondary background, a
14px card radius, a 10px input radius). Then wrote a one-time Python translation script (not
committed to the repo — a throwaway tool, not application code) mapping every one of the ~170
distinct hardcoded hex colours and ~15 distinct `rgb()`/`rgba()` triples found across all 7 CSS
files and 11 JS modules (badges, status tints, chat bubbles, doc-type accent colours in
`validation_config.js`, etc.) to warm equivalents, and applied it uniformly everywhere in one pass
(883 hex + 80 rgb replacements total). Swapped the Google Fonts `@import` from IBM Plex Sans to
Inter (same loading mechanism the app has used since v0.2 — not a new offline-capability
regression). Manually fixed two colour-role collisions the automated sweep couldn't resolve on its
own: `.btn-urs-primary` and `.btn-qual-primary` had originally shared the same literal hex as the
general brand accent, so after repointing `--accent` to Muted Sage (a deliberately distinct token
from the Walnut Brown primary-button colour) those two buttons rendered sage instead of walnut;
repointed both to `var(--blue-light)` (Walnut) to match every other suite's primary CTA.
**Reason:** A token-based sweep was the only approach that could realistically stay internally
consistent across 7 CSS files and 11 JS files within one session while guaranteeing "no screen
looks different from another" (an explicit requirement) — hand-editing hundreds of individual
color declarations file-by-file would have risked exactly the kind of per-suite drift the
consistency requirement was meant to prevent, and would not have been practically completable.
Keeping the historical variable *names* (rather than renaming `--navy`→`--walnut` etc.) avoided
touching hundreds of `var(--navy)`/`var(--blue)` call sites across every suite file for no
functional benefit.
**Benefits:** Full palette consistency across Dashboard, Knowledge Base, Chat, Generate Document
(Enterprise Workspace shell), Validation Workspace, QMS (Document Control/Deviation/CAPA), and the
backend-complete-but-unwired Risk/URS/Qualification/Validation Report suites (verified by
temporarily forcing each suite's view visible in a live browser session, since their sidebar
navigation isn't wired — see DEC-017/Known Issues); zero JS logic, API routes, or database schema
touched; zero console errors observed across every screen tested.
**Trade-offs:** The automated hex-translation approach is a *value* substitution, not a semantic
re-audit of every single usage — the two button-color collisions above were caught by manual
spot-checking during browser verification, not by the script itself, meaning a handful of other
low-visibility role collisions could theoretically remain undiscovered in screens not directly
exercised (Risk/URS/Qual/Report were spot-checked but not exhaustively interacted with, since their
nav is unwired). `docx_generator.py`/`doc_exporter.py`'s exported-DOCX styling (navy headings,
navy table headers) was deliberately left untouched — it's Python-generated document styling, not
UI CSS, and out of scope for a UI-only redesign; the on-screen document viewer and the exported
.docx file will look slightly different until/unless that's addressed in a follow-up (see
`docs/DESIGN_SYSTEM.md` §11).
**Impact:** `docs/DESIGN_SYSTEM.md` was rewritten to v2.0 to document the new token values and
component patterns. Any future PharmaGPT UI work should continue reusing the existing `:root`
tokens (`var(--blue-light)` for primary buttons, `var(--accent)` reserved for Sage
accents/focus-rings only, never for primary CTAs) rather than reintroducing hardcoded hex colours,
per the project's existing anti-duplication convention (DEC-012/DEC-013 precedent).
**Future Review Required:** Consider repainting `docx_generator.py`/`doc_exporter.py`'s exported
DOCX styling to match (Walnut Brown / Warm Charcoal instead of navy) for full on-screen/exported
visual parity — not done here per the UI-only mandate. Consider a full interactive audit of
Risk/URS/Qualification/Validation Report once their sidebar navigation is finally wired (see
DEC-017 Future Review), since this redesign's verification of those four suites was necessarily a
spot-check (forced-visible views) rather than the full click-through possible on live-wired
screens.

---

### DEC-019 — "Premium Enterprise" Palette v3.0, Sidebar Regulatory-Scope Removal, Lucide Icon System

**Date:** 2026-07-05, same day as DEC-018, second pass
**Problem Statement:** The user requested a further-refined visual pass on top of DEC-018's
"Executive Office" redesign: (1) an exact, precisely-specified business-attire hex palette
(different literal values than DEC-018's, though the same conceptual warm-neutral-plus-walnut-brown
direction) to read as premium enterprise software (Apple Business / Stripe Dashboard / Linear /
Notion Enterprise / SAP Fiori / Atlassian Cloud reference quality); (2) permanent removal of the
sidebar's "Regulatory Scope" badge section (USFDA/MHRA/EU GMP/WHO GMP/ICH Q9/21 CFR/GAMP 5/
Annex 15/CDSCO/TGA/Schedule M/PIC's) as sidebar clutter with low operational value — regulatory
context should live inside modules instead; (3) replacement of the existing Unicode-emoji
iconography (explicitly called out in DEC-018/PROJECT_STATUS.md as "no icon library") with a single
consistent icon library, Lucide, per an explicit "ICONS" requirement (consistent stroke/size/
spacing); (4) meaningful (not purely decorative) subtitles on Dashboard KPI cards.
**Options Considered:**
- *Palette:* (a) hand-edit every colour declaration file-by-file; (b) repeat DEC-018's approach —
  repoint the shared `:root` tokens (already the single source of truth per DEC-012) plus a
  one-time scripted hex-literal translation sweep for everything that bypassed those tokens.
- *Icons:* (a) hand-author individual inline SVGs per icon usage; (b) adopt a CDN-hosted icon
  library (Lucide) with `data-lucide="<name>"` placeholder spans, converted client-side.
- *Icon conversion trigger:* (a) require every JS module to call `lucide.createIcons()` after its
  own renders; (b) a single global mechanism (`MutationObserver` on `document.body`) that detects
  newly-inserted `[data-lucide]` elements and converts them automatically, so existing and future
  modules never need to know Lucide exists.
**Decision Taken:** (b) for all three. Repointed `:root` tokens in `style.css` to the exact new hex
values (Primary BG `#F7F5F2`, Secondary BG `#F1ECE6`, Card `#FFFFFF`, Sidebar `#5B4C43`/hover
`#6D5B52`/active `#8A6B52`, Primary Button `#8A6B52`/hover `#9D7B60` — note hover is *lighter* than
default, per the user's literal spec, a reversal of DEC-018's darken-on-hover convention — Primary
Text `#2D2A28`, Secondary Text `#66615B`, Muted Text `#9A948C`, Border `#E6DED6`, Divider
`#EEE7E1`, Success `#5F8A61`, Warning `#C59A41`, Danger `#C35F5B`, Information `#6E8FA5`, plus new
`--soft-blue`/`--soft-green`/`--soft-amber` tokens for `#E7EEF6`/`#E8F2EA`/`#FFF4E5`). `--accent`
(previously DEC-018's Muted Sage, used only for a handful of focus-ring/active-tab-border/spinner
accents — see grep across `qual.css`/`urs.css`/`qms.css`) was repointed to Information
(`#6E8FA5`) since the new palette specifies no separate accent hue and Information already served
an equivalent "distinct, non-primary" role in DEC-018. Wrote a throwaway Python translation script
(same pattern as DEC-018, not committed) mapping all ~95 distinct DEC-018-era hex literals found
across all 7 CSS files and the JS modules that had inline colours to their nearest new-palette
equivalent (873 + 19 replacements in two passes); verified zero DEC-018-era hex literals remained
afterward. Removed the entire "Regulatory Coverage" `<div class="sidebar-section">` block (label +
`.expertise-tags`) from `templates/index.html` outright — not hidden, deleted, since the instruction
was explicit removal, not a hide/collapse. Added Lucide via the `unpkg` CDN (same "just a
`<script src>`, no build step" pattern the app already uses for `marked.js` via jsdelivr and Google
Fonts) and converted the highest-traffic, structurally-shared icon locations to
`<span class="icon" data-lucide="...">`: sidebar primary nav, sidebar QMS nav + its collapse
chevron, Dashboard header/KPI cards/section-card headers, the shared modal-close button (used by
every modal in the app), Generate Document's Enterprise Workspace header/toolbar, Knowledge Base
header/search/empty-states, Validation Workspace header/empty-states, the sidebar project-list
folder icon and delete button, and the QMS unified dashboard's three module section headers.
Implemented conversion via a single `refreshIcons()` helper plus a `MutationObserver` at the bottom
of `templates/index.html`, guarded against the observer re-triggering on its own DOM mutations
(Lucide's `createIcons()` replaces the host element with a new `<svg>` that **retains the
`data-lucide` attribute**, which on first implementation caused the observer to call
`createIcons()` again indefinitely — a genuine infinite loop that hung the browser tab with no
console output, since the render thread never yielded; caught during browser verification, fixed by
disconnecting the observer for the duration of each `createIcons()` call). Added descriptive,
non-fabricated KPI subtitles ("Across all active work", "In the Validation Workspace", "Needs
attention" / "All caught up" for CAPA/Deviation counts derived from data already returned by
`/dashboard/stats`) rather than inventing week-over-week deltas the backend does not track.
**Reason:** Reusing DEC-018's token-repointing architecture was the only way to guarantee the "one
premium enterprise application, not per-screen drift" requirement within one pass, exactly as
DEC-018 itself argued — the token system built then is what makes this kind of full-palette
refinement cheap the second time. A global icon-conversion mechanism (MutationObserver) was chosen
over "every module calls `createIcons()`" specifically because this codebase has 19+ independent
JS modules (DEC-005/DEC-012) with no shared render pipeline; requiring each one to remember a new
API call is exactly the kind of per-module drift risk DEC-012's shared-file conventions exist to
avoid.
**Benefits:** Every existing `var()` consumer across all 7 suite CSS files repainted for free, same
as DEC-018; the icon system is now genuinely one library with consistent stroke/size, and any
*future* module that emits `<span data-lucide="...">` anywhere in the DOM gets working icons with
zero additional wiring; the sidebar is visibly lighter/less cluttered with the Regulatory Scope
section gone; KPI cards now answer "why does this number matter" per the Dashboard's stated
three-questions mandate (What needs my attention / What am I working on / What should I do next).
**Trade-offs:** Same value-substitution caveat as DEC-018 — the hex-translation sweep is a
context-free mapping, not a full semantic re-audit, so a handful of low-visibility, low-frequency
decorative colours (chart accents, severity-tint variants used only 1–3 times each) were mapped by
best-effort proportional judgement rather than exact design-system derivation. The Lucide icon
conversion is **not exhaustive**: Risk/URS/Qualification/Validation Report suite-internal emoji
(inside `risk.js`/`urs.js`/`qual.js`/`report.js` and their `templates/index.html` view headers)
were left untouched, for the same reason DEC-018 could only spot-check those suites — their sidebar
navigation is still unwired (see PROJECT_STATUS.md Known Issues), so a full interactive
click-through audit isn't possible yet. QMS's *sub-views* (Document Control/Deviation/CAPA detail
screens rendered by `qms_documents.js`/`qms_deviations.js`/`qms_capa.js`) were likewise not swept —
only the unified QMS dashboard's three top-level section headers were, since that dashboard is the
single highest-traffic QMS screen.
**Impact:** Any future PharmaGPT UI work should (1) continue reusing the existing `:root` tokens
rather than hardcoding hex, per DEC-012/DEC-013/DEC-018 precedent; (2) use
`<span class="icon" data-lucide="<lucide-icon-name>">` for any new icon rather than a Unicode
emoji or a hand-authored inline SVG — the global `refreshIcons()`/`MutationObserver` mechanism in
`templates/index.html` will convert it automatically, no per-module wiring needed; (3) never
reintroduce a Regulatory Scope-style sidebar badge list — regulatory context belongs inside the
relevant module's own view.
**Future Review Required:** Complete the Lucide icon sweep for Risk/URS/Qualification/Validation
Report and the three QMS sub-views once their content is more actively iterated on or their
navigation is wired (see DEC-017/DEC-018 Future Review threads, now joined by this one). Consider
repainting `docx_generator.py`/`doc_exporter.py`'s exported DOCX styling to the v3.0 hex values
(still outstanding from DEC-018, unchanged by this pass).

---

### DEC-020 — Pre-Deployment UI Audit: Completed Icon Sweep, Fixed Report Suite Dark-Theme Leftover, Fixed Two Layout Bugs, Fixed a Cross-Suite JS Naming Collision

**Date:** 2026-07-05, same day, third pass — pre-deployment verification of DEC-018/DEC-019
**Problem Statement:** Before considering the v3.0 redesign deployment-ready, the user requested a
complete UI audit of every accessible module/wizard/dialog/modal/dashboard/workspace, explicitly
checking for remaining legacy colors, inconsistent spacing, emoji icons, Bootstrap icons,
half-width layouts, unused whitespace, and broken responsive behavior — with instructions to fix
whatever was found. DEC-019's own "Known Issues" already flagged the icon sweep as incomplete for
Risk/URS/Qualification/Validation Report and the QMS sub-views; this audit closed that gap and, in
the process of navigating every suite by force-showing its views (their sidebar nav is still
unwired), turned up several genuine, previously-undiscovered defects — some UI-only, one functional.
**What Was Found and Fixed:**
1. **Completed the Lucide icon sweep.** Converted all remaining emoji (484 occurrences across 18
   files) to `<span class="icon" data-lucide="...">` using the same conversion mechanism from
   DEC-019, across `risk.js`, `urs.js`, `qual.js`, `report.js`, `knowledge_base.js`,
   `gen_document.js`, `validation.js`, `validation_config.js`, `val_workspace.js`, `documents.js`,
   `qms_deviations.js`, `qms_capa.js`, `qms_documents.js`, `qms_common.js`, `workspace.js`, and the
   remaining Risk/URS/Qualification/Validation-Report view headers in `templates/index.html`. Final
   codebase-wide scan confirms **zero** remaining emoji and **zero** Bootstrap/FontAwesome
   references (none were ever present).
2. **Infinite-loop regression in the icon-conversion script, caught before it shipped.** The
   `<span class="icon" data-lucide="X">` → JS-string conversion initially used the wrong quote style
   in two different ways during the sweep: (a) inserting literal double-quoted HTML attributes
   (`class="icon"`) inside JS strings that were *themselves* double-quoted (e.g.
   `icon: "<span class="icon"...`), which is a syntax error since the inner `"` prematurely closes
   the outer string — found via `node --check` on every touched file, not caught by the browser
   (which simply fails to execute the whole script silently); (b) a follow-up fix that
   escaped the quotes as `\'` correctly for JS-string contexts but was then also (wrongly) applied
   to *plain HTML* in `templates/index.html`, where `\'` is not a recognized escape at all and
   corrupts the `class`/`data-lucide` attribute values into literal garbage text, silently breaking
   every icon on the page (found via live DOM inspection, not caught by a syntax checker since it's
   valid HTML, just wrong). Resolved by using backslash-escaped-single-quotes
   (`class=\'icon\' data-lucide=\'X\'`) universally inside `.js` files (valid regardless of whether
   the enclosing JS string is single-, double-, or backtick-quoted) and plain single-quotes in
   `templates/index.html` (which contains no such JS-string context for these insertions). Verified
   with `node --check` on every `.js` file plus every inline `<script>` block extracted from
   `index.html`.
3. **Flask/Jinja2 template caching produced false-positive test results mid-audit.** With
   `FLASK_DEBUG=false`, Jinja2 compiles and caches `index.html` in memory on first render and does
   not recheck the file on disk; repeated `location.reload()` calls against a `dev server that had
   been running since before a template edit kept serving the *stale, pre-edit* compiled template,
   which momentarily looked like several icon fixes and the Report-suite width fix "hadn't taken
   effect." Restarting the Flask process (not just reloading the browser) resolved it. **Lesson for
   future sessions:** any edit to `templates/index.html` requires a dev-server restart to verify,
   not just a page reload — static `.css`/`.js` file edits do not have this problem (Werkzeug serves
   those by file mtime per-request regardless of debug mode).
4. **Genuine functional bug: `renderWizardStep` / `renderApprovalPanel` name collision between
   `risk.js` and `urs.js`.** Both files are loaded as classic (non-module, non-IIFE-wrapped)
   `<script>` tags sharing one global scope, and both declared top-level functions with these exact
   names. Since `urs.js` loads after `risk.js` in `templates/index.html`'s script list, URS's
   versions silently overwrote Risk's — meaning Risk's "New Assessment" wizard's Step 1
   (`risk-type-selector`) never rendered, and Risk's Approval panel never rendered, regardless of
   the UI redesign, whenever both scripts were loaded (which is always, since every suite's `<script
   src>` loads unconditionally on every page load). This is a pre-existing defect, not introduced by
   DEC-018/DEC-019, that had never been caught because Risk's sidebar navigation is unwired and the
   suite is only reachable by forcing its views visible (exactly what this audit did). Fixed by
   renaming risk.js's copies to `riskRenderWizardStep`/`riskRenderApprovalPanel` and updating its own
   7+2 call sites; `urs.js` was not touched (its own internal calls already correctly resolved to its
   own functions and its wizard/approval flows already worked). A repo-wide scan for other
   top-level-function-name collisions across all suite `.js` files found none of the same severity
   (the ~130 other name matches the scan surfaced were all function-local `const`/`let` variable
   reuse, not global collisions).
5. **`urs.css`'s `.urs-empty` class was missing `flex-direction: column; align-items: center`.**
   `urs.js` toggles this element's visibility via `element.style.display = "flex"` (inline style,
   which wins over any CSS `display`), and without an explicit `flex-direction: column` the default
   `row` direction laid the icon/title/subtitle/button out side-by-side instead of stacked — visibly
   broken compared to every other suite's empty state (`.risk-empty`, `.doc-empty`, `.vw-empty`,
   etc.), all of which either declare the flex properties explicitly or never get their `display`
   toggled to `flex` via JS in the first place. Fixed by adding the missing properties; verified this
   was the *only* file exhibiting the pattern (checked every `element.style.display = "flex"` call
   site touching a `*-empty` element across every JS module).
6. **`report.css`'s entire content-area component set (`.report-stat-card`, `.report-panel`,
   `.report-list-table`, `.report-badge`/`.badge-*`, `.report-section-*`, `.report-review-*`,
   `.report-trace-*`, form inputs, etc. — ~45+ declarations) was still styled for a dark theme that
   predates even DEC-018.** DEC-018's and DEC-019's automated hex-translation sweeps (both
   context-free value substitutions, by design — see DEC-018's own stated trade-off) correctly
   translated the *old* dark-theme hex literals to their *new-palette* equivalents, but a
   value-for-value substitution cannot detect that the underlying *role* of those colours (a dark
   card background with light text, meant for a dark UI that this suite's content area apparently
   never actually had removed) is wrong for a light theme — it just repainted the same dark cards
   with new-palette dark tones (e.g. `background: #2D2A28` — literally the new `--navy`/text-colour
   value being used as a *background*). This was invisible to a text-based hex-audit (the literals
   were all "valid v3.0 palette values") and was only caught by actually rendering the Report
   Management Suite's dashboard in a browser, which is why this audit's explicit "navigate through
   every accessible module" instruction mattered. Fixed with a second, *property-aware* pass specific
   to `report.css` (content area only — the dark `.report-header` bar and the saturated colour-pill
   `.report-btn-primary/success/warning/danger` buttons were deliberately left alone, since a dark
   header bar and solid-colour buttons are correct in this theme too, matching every other suite's
   page-header convention): `background: #2D2A28|#5B4C43` → white/`--bg-secondary`,
   `color: #F1ECE6|#E6DED6` → `--navy`/`--text`, and dark border values → the light `--border`
   token, followed by manual correction of a few resulting badge/hover/recommendation states that
   the mechanical substitution left with insufficient contrast (e.g. white-background hover states
   that were indistinguishable from the non-hover white background — repointed to the `--bg-secondary`
   tint used for hover states everywhere else in the app). The identical inline-style version of the
   same bug was separately found and fixed in `report.js`'s JS-rendered templates (28 occurrences)
   plus one each in `risk.js` and `validation.js` — the latter two were **print/export template**
   `<style>` blocks (`window.printReport`, PDF export HTML) where a solid dark table-header
   background with white text is the *correct*, deliberate choice (print documents mimic the
   existing light-document-viewer convention, DEC-007) — the automated pass had wrongly lightened
   just the header backgrounds there too, leaving white-on-white-ish text; both were corrected back
   to a solid dark header fill.
7. **Genuine "half-width layout" bug: `.report-container` was missing `flex: 1`.** Every other
   suite's top-level view container (`.qual-container`, `.urs-container`, Risk's inline
   `flex-direction:column;flex:1`, `.dash-container`, etc.) sets `flex: 1` so it grows to fill the
   remaining horizontal space next to the 240px sidebar inside `.app-body`'s flex row; `.report-container`
   only set `height: 100%`, so it fell back to shrink-to-fit sizing based on its content — the
   entire Validation Report Management Suite rendered at roughly 828px instead of the expected
   ~1200px on a 1440px-wide viewport, with the sidebar-adjacent remainder left as plain background.
   Fixed by adding `flex: 1; width: 100%;` to match the pattern used everywhere else. This,
   combined with item 6, means the Report suite was almost certainly the single most
   visually-broken screen in the entire application prior to this audit, despite two prior
   "redesign" passes — both had swept its colour *values* without ever actually rendering the
   screen to check the *result*.
**Reason:** A hex/emoji/hardcoded-literal grep-based audit — while fast and how DEC-018/DEC-019 were
largely executed — cannot catch defects that only manifest at render time: wrong flex sizing, a
missing CSS property whose absence is invisible in a diff, or two files silently overwriting each
other's same-named global function. The user's instruction to actually "navigate through every
accessible module" and "fix any issues found" is precisely the verification step that catches this
class of bug, and this pass proved that class of bug was real and non-trivial (a suite's wizard
silently non-functional; a suite's entire content area in the wrong theme; a suite's layout at
~70% of its intended width).
**Benefits:** Every suite (Dashboard, Knowledge Base, AI Assistant, Generate Document, Documents,
Insights, Validation Workspace, single-shot Validation Generator, Risk, URS, Qualification,
Validation Report, QMS Dashboard/Documents/Deviations/CAPA, and all three modals) has now been
individually navigated and visually verified in a live browser at desktop width, with zero console
errors, zero remaining emoji, zero remaining legacy-palette hex literals, and zero Bootstrap/
FontAwesome references anywhere in the codebase.
**Trade-offs:** Tablet/mobile breakpoints were checked and found to behave exactly as documented
(`.sidebar { display: none; }` below 768px with no replacement navigation) — this is a pre-existing,
explicitly-documented limitation (see PROJECT_STATUS.md → Known Limitations, "Desktop-first UI;
mobile responsiveness is not yet a priority") and was deliberately **not** built out further here,
since adding mobile navigation would be a new feature, not a fix, and was explicitly out of scope
("Do not introduce new features"). The Risk/URS/Qualification/Validation Report suites and QMS
sub-views were verified by force-showing their views (`window.showView()`/`showAllRiskViews()`),
the same methodology DEC-018 used, since their sidebar navigation remains unwired — this is
necessarily a manual-navigation verification, not the full click-through possible on live-wired
screens, though this pass went considerably further into each suite's sub-views (wizards, detail
tabs, AI panels) than DEC-018's spot-check did.
**Impact:** The `renderWizardStep`/`renderApprovalPanel` rename in `risk.js` means any future work
on the Risk Management Suite must use `riskRenderWizardStep`/`riskRenderApprovalPanel`, not the
bare names (which now correctly belong only to `urs.js`). Any future suite JS module should be
mindful that this codebase's suite scripts are **not** IIFE-wrapped or namespaced — a new module
should either give its internal helper functions suite-prefixed names for anything even loosely
generic (`render*`, `show*`, `init*` are the highest-risk patterns already seen colliding) or wrap
itself in an IIFE per the `val_workspace.js` precedent, which is immune to this entire class of bug.
Any future automated colour-value sweep (per DEC-018/DEC-019's established approach) should be
paired with an actual render-and-look verification pass per screen before being considered
complete — a hex-diff alone cannot prove a screen looks right, only that its colours are drawn from
the current palette.
**Future Review Required:** None of the remaining known gaps changed: Risk/URS/Qualification/
Validation Report sidebar navigation is still unwired (pre-existing); exported-DOCX styling is
still pre-redesign navy (pre-existing, DEC-018); mobile/tablet navigation is still absent
(pre-existing, explicitly out of scope). Recommend that whichever future session finally wires up
Risk/URS/Qualification/Validation Report's sidebar navigation also do one more full click-through
of those suites now that they can be reached normally instead of via `showView()`, since a handful
of interaction paths (e.g. deep wizard branches) were not individually exercised in this pass.

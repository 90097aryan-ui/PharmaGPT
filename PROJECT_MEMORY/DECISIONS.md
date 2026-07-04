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

# PharmaGPT — Pre-Demo Testing & Validation Guide

**Purpose:** Validate every module built so far (~80% of planned scope) so the demo runs with
zero visible errors. Organized as: critical blockers to clear first, then a process-flow +
test-script pair for every module, then cross-cutting checks and a suggested demo order.

**Baseline verified while writing this guide (2026-07-06):** server boots clean on
`http://127.0.0.1:5187` (via `.claude/launch.json` → `pharmagpt-flask`), Home Dashboard loads with
no console errors, and Knowledge Base / QMS Dashboard / Generate Document nav clicks produced no
console errors. This is a smoke check, not full coverage — use the scripts below for that.

---

## 0. Environment Setup (do this first)

```
cd D:\PharmaAgent
.\venv\Scripts\python -m flask --app pharmagpt.app run --port 5077
# or: .\venv\Scripts\python pharmagpt\app.py
```

- `.env` must have a valid `GEMINI_API_KEY` (already present) — every AI feature (chat, document
  generation, QMS AI assist) will silently fail or error without it.
- Run the automated suite before any manual pass — it catches regressions for free:
  ```
  .\venv\Scripts\pip install -r requirements-dev.txt
  .\venv\Scripts\python -m pytest
  ```
  Expect **101 passed**. If 4 modules fail to *collect* (`test_document_processor.py`,
  `test_job_runner.py`, `test_pdf_engines.py`, `test_pipeline.py`) with `ModuleNotFoundError`, it's
  a missing-dependency issue in that venv (`docx`/`dotenv` not installed), not a code defect —
  reinstall `requirements-dev.txt` + `requirements.txt` in that venv.
- **Demo data hygiene:** the current dev database (`pharmagpt.db`) contains leftover test
  artifacts — projects named "WAL Mode Test", "Repro Test Project", "UI Flow Test Project", and a
  document literally named `corrupted.pdf`. These will show up on the Home Dashboard's Recent
  Activity / Recent Projects panels. **Before the real demo, either delete these test projects/docs
  through the UI, or point `DB_PATH` at a fresh SQLite file** so the audience sees clean, realistic
  data.

---

## 1. Critical Pre-Demo Blockers

Fix or consciously accept these *before* sharing the demo — ranked by how likely they are to
produce a visible error or an awkward "why can't I click that" moment.

| # | Issue | Impact on demo | Recommendation |
|---|---|---|---|
| 1 | **Risk / URS / Qualification / Validation Report suites are backend-complete but have no sidebar entry point** (`risk-nav-items`, `urs-nav-items`, `qual-nav-items`, `report-nav-items` are all `display:none` in `templates/index.html`) | 4 fully-built modules are **invisible and unreachable** through the UI today | Decide now: either wire the nav before the demo (moderate frontend task — the JS/CSS/routes already exist, verified working via API) or explicitly scope them out of the demo narrative. Don't let a stakeholder ask "where's Risk Assessment?" and get a blank sidebar. |
| 2 | **QMS Change Control is fully built but uncommitted in git** (working tree only) | If anything resets the environment (redeploy, `git checkout`, machine swap) before the demo, the newest module disappears | Commit it (`git add` the listed new/modified files, per `CHANGELOG.md`'s "Unreleased — 2026-07-05" entry) before demo day. |
| 3 | **`doc_ids` bug** — `/validation/generate` accepts a `doc_ids` field (from wizard Step 3 "select reference documents") but ignores it; search always runs against *all* project documents | If a presenter demos "select these 2 specific docs" and the output clearly used a different document, it looks broken live | Test this specifically (§2.F below) before demo; if reproducible, either fix it or avoid selecting a subset live — always click "select all". |
| 4 | **Chat renders AI output via `marked.parse()` → raw `innerHTML`, no sanitization (DOMPurify not installed)** | A Gemini response containing something that looks like an HTML tag (or a pasted user question with `<script>`/`<img onerror>`) can break rendering or execute unexpected script in the browser | Avoid pasting arbitrary external text into chat during the demo; test with a message containing `<b>`, `<script>`, `<img src=x onerror=alert(1)>` beforehand (§2.B) to see what actually happens in this browser/version before relying on it live. |
| 5 | **Competing `showView()` implementations** (global scope vs `val_workspace.js`) and a prior same-name collision already found/fixed once between `risk.js`/`urs.js` | If Risk/URS nav does get wired for the demo, retest navigation between Validation Workspace and any newly-wired suite — this exact bug class has bitten this codebase before | Click every sidebar item once, in sequence, after any nav-wiring change (§4 regression pass). |
| 6 | Hardcoded fallback `FLASK_SECRET_KEY` in `config.py`, no CSRF protection on POST/DELETE | Not visibly broken, but flag if anyone inspects network requests or asks about security posture | Mention it's a known, tracked item (`docs/CODE_REVIEW.md`) for the pre-v1.0 hardening pass, not a surprise. |

If you want, I can wire the Risk/URS/Qualification/Validation Report nav items next — the backend
and JS are already there, so this is realistically the single highest-leverage fix before the demo.
Say the word and I'll do it.

---

## 2. Module-by-Module: Process Flow + Test Script

Legend: 🟢 Live & wired · 🟡 Backend-complete, not reachable via sidebar · 🔵 Partial

### A. 🟢 Home Dashboard
**Process flow:** App loads → `GET /dashboard/stats` + `/dashboard/validation-score` fire on load
→ cards populate (Projects, Validation Projects, KB Docs, Protocols Generated, Pending CAPAs,
Pending Deviations, Avg Validation Score) → Recent Activity / Recent Projects / Upcoming Reviews /
Recent AI Conversations / System Health panels render from the same payload.

**Test script:**
1. Load `/` fresh (hard refresh). Expect all 7 stat cards to show a number (not stuck on a
   spinner or blank).
2. Click **Refresh**. Numbers should re-fetch without a full page reload or console error.
3. Confirm counts match reality: create one project, refresh, "Projects" count should increment.
4. Check **System Health** panel (Uploaded Files / Extracted OK / Extraction Errors / KB Extracted
   / Chat Messages / Audit Entries) — cross-check "Extraction Errors" is 0 if all uploaded demo
   docs are known-good.

### B. 🟢 AI Chat Assistant
**Process flow:** Select/create a project → open Chat view → type message → optional "☑ Use
Project Documents" toggles RAG context injection → `POST /stream` (SSE) → tokens render live →
on completion, a "Sources: • file.pdf" strip appears if doc-context was used → message pair
persisted to `messages` table.

**Test script:**
1. Create a project, send a message with no documents uploaded. Expect a normal streamed answer,
   no "Sources" strip, no console error.
2. Upload a PDF/DOCX to the project, wait for extraction to finish (poll `/documents/<id>/status`
   or just watch the UI), enable "Use Project Documents", ask a question the document actually
   answers. Expect the answer to reference the doc and a Sources strip naming it.
3. Click **Clear Chat**. Expect history to empty and `/projects/<id>/messages` to return `[]`.
4. Adversarial input test (per Blocker #4): send `<b>bold</b>`, `<script>alert(1)</script>`, and
   `<img src=x onerror=alert(1)>` as chat messages. Confirm nothing pops an alert or breaks the
   page layout; note actual behavior either way.
5. Restart the Flask server mid-conversation, reload the page, reopen the same project. Expect
   history to rebuild from the `messages` table (the in-memory cache is expected to reset — this is
   documented behavior, not a bug).

### C. 🟢 Project Management
**Process flow:** Sidebar/dashboard → "New Project" → fill name, equipment, manufacturer,
department, validation type → `POST /projects` → appears in project list/sidebar → selecting a
project loads its chat history, documents, and generated docs scoped to that `project_id`.

**Test script:**
1. Create a project with all fields filled; confirm it appears immediately without reload.
2. Create a second project with only the required field(s); confirm optional fields don't crash
   creation.
3. Delete a project. Confirm its documents, messages, and generated docs are gone too (cascade
   delete) — check the Knowledge Base is *unaffected* (KB is project-independent).
4. Switch rapidly between 2-3 projects; confirm chat/documents panels always reflect the
   currently-selected project (no stale data from the previous one).

### D. 🟢 Document Management + Document Intelligence Engine
**Process flow:** Upload (drag-drop or file picker) → file saved to `uploads/<project_id>/` →
async extraction job queued (`ThreadPoolJobRunner`) → multi-engine fallback for PDFs
(pypdf → pdfplumber → PyMuPDF → OCR-placeholder) → status polled via
`GET /documents/<id>/status` → `document_text` row written with `extraction_status` ok/empty/error
→ Document Insights panel aggregates stats.

**Test script:**
1. Upload a normal text-based PDF. Poll status until `ok`; open **Document Insights** — page/word
   count should be non-zero.
2. Upload a DOCX and an XLSX. Confirm both extract (`ok`) and both are viewable inline / downloadable.
3. Upload a corrupted/empty PDF (there's literally a `corrupted.pdf` already in the dev DB you can
   reuse). Confirm the upload still returns success (HTTP 201) and `extraction_status` becomes
   `error` — **the UI must not crash**, just show the doc as unextracted. Try **Retry**
   (`POST /documents/<id>/retry`).
4. Upload a file >50MB. Confirm a clean rejection message, not a server 500 or hung request.
5. Delete a document. Confirm the physical file is removed from `uploads/<project_id>/` and the
   row disappears from the list.
6. View + force-download both a PDF and a DOCX from the same document to confirm both code paths
   work (`/documents/<id>/view` vs `/documents/<id>/download`).

### E. 🟢 Knowledge Base
**Process flow:** Sidebar → Knowledge Base → pick a folder (SOP/Validation/Qualification/
Protocols/Reports/Regulations/Vendor Documents/Others) → Upload modal (title auto-fills from
filename, folder pre-selected) → metadata (tags, version, effective/review date) → file uploads to
`uploads/kb/` → async extraction → appears in list with folder pill/version badge/dates/tags →
click row → detail panel with full metadata + text preview (overdue review date shown in red).

**Test script:**
1. Upload one document per folder (or at least 3 folders) with different metadata; confirm folder
   sidebar counts update live.
2. Search by title substring, then by tag, then by file type, then by in-document keyword —
   individually, then combine 2+ filters at once. Confirm results narrow correctly each time.
3. Set a `review_date` in the past on one document; open its detail panel and confirm the overdue
   date is visibly highlighted (red).
4. View inline (PDF/TXT) and force-download from both the list row and the detail panel.
5. Delete a KB document; confirm it disappears from the folder count and the file is removed from
   `uploads/kb/`.

### F. 🟢 Validation Document Generator (11 doc types: URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation, Change Control)
**Process flow:** Sidebar → Generate Document → pick doc type → 4-step wizard: **Equipment →
Details → Reference Docs → Generate** → `POST /validation/generate` streams via SSE into an A4
Word-like viewer (`temperature=0.3`) → toolbar: Regenerate · Export DOCX · Print/PDF · Save to
Project → optional `POST /validation/review` (AI compliance pass) → `POST /validation/save`
persists to `generated_documents`.

**Test script:**
1. Generate one document per type (or at minimum OQ, IQ, URS, CAPA to cover distinct prompt
   structures) with only Equipment + Details filled, no reference docs selected. Confirm each
   streams to completion without an SSE error and produces a structurally sane document (headings,
   not garbled markdown).
2. **Reference-doc subset test (Blocker #3):** upload 2 documents to the project, in Step 3 select
   only 1 of them, generate, and check whether the output content actually reflects only that one
   document or clearly pulled from both. Record the actual result — this is the known `doc_ids` bug.
3. Click **Export DOCX**; open the downloaded file and confirm formatting (headers/footers, tables,
   bold/italic) renders correctly in Word.
4. Click **Print/PDF**; confirm the browser print dialog opens with clean print-CSS (no broken
   layout, no dark background bleeding through).
5. Click **Save to Project**, then reload and confirm the saved doc is retrievable via
   `GET /projects/<id>/generated-docs` and re-viewable.
6. Click **Regenerate** on an already-generated doc; confirm it doesn't duplicate the save or
   corrupt the viewer state.

### G. 🔵 Validation Workspace (partial)
**Process flow:** Create a `val_project` (owner, approver, target date, risk category, status:
Planning → In Progress → Complete) → view/edit/delete → per-project audit trail entries logged.

**Test script:**
1. Create a validation workspace project; confirm it appears on the Home Dashboard's "Validation
   Projects" count.
2. Update its status field; confirm the change is reflected and an audit-trail entry is created
   (`GET /val-projects/<id>/audit-trail`).
3. Note to presenter: **this is intentionally partial** (no full approval/signature workflow yet —
   that's v0.8 remainder). Don't demo it as if it's the finished e-signature flow.

### H. 🟡 Risk Management Suite — *not reachable via sidebar today*
**Process flow (as built):** Create assessment → add risk items → `POST /assessments/<id>/generate`
(AI-assisted risk content) → review → mitigate → track mitigation actions → approval workflow
(`GET`/`POST /assessments/<id>/approval`) → publish → export DOCX.

**Test script (via direct API/curl or by temporarily un-hiding `#risk-nav-items` in dev tools):**
1. `POST /risk/assessments` to create one; `GET /risk/assessments/<id>` to confirm persistence.
2. Add items via `/assessments/<id>/items`, then `POST /assessments/<id>/generate` and confirm a
   Gemini-backed response streams/returns without error.
3. Walk one assessment through review → mitigate → approval → publish → export docx end to end.
4. **If including this in the demo:** wire the nav first (see Blocker #1) rather than showing raw
   API calls to a non-technical audience.

### I. 🟡 URS Management Suite — *not reachable via sidebar today*
**Process flow:** Create URS → add requirements (manual or from the built-in requirement library,
`/library/types`, `/library/sections`) → `POST /<id>/generate` (AI drafts requirement text) →
review → approval → versioning (`/<id>/versions`) → export DOCX.

**Test script:** same pattern as Risk (§H) — create → populate from library → generate → review →
approval → version → export. Confirm the requirement library endpoints
(`/library/types`, `/library/sections`) return non-empty lists before relying on them in a demo.

### J. 🟡 Qualification Suite (IQ/OQ/PQ) — *not reachable via sidebar today*
**Process flow:** Create qualification → add protocols → add test cases per protocol → AI-generate
protocol content → review → **execute test cases** (`/execute/<tcid>`) → complete protocol → log
deviations found during execution → approval → traceability matrix → export DOCX (both per-protocol
and full traceability export).

**Test script:**
1. Create a qualification, one protocol, 2-3 test cases.
2. Execute each test case (this suite is the only one with a live "execution" step — confirm
   pass/fail recording actually works, since it's the most complex lifecycle in the codebase).
3. Log a deviation against the protocol via `/deviations`; confirm it's queryable.
4. Complete the protocol, run approval, then pull `/traceability` and confirm it correctly maps
   requirements → test cases → results.
5. Export both the single-protocol DOCX and the full traceability DOCX; check both open cleanly.

### K. 🟡 Validation Report Suite — *not reachable via sidebar today*
**Process flow:** Create report, linked to a completed Qualification (`/linked/<qual_id>`) →
per-section content (`/sections/<key>`) generated individually or all at once
(`/generate/<key>` vs `/generate`) → review → approval → versioning → export DOCX.

**Test script:**
1. Create a report linked to a Qualification created in §J; confirm the link actually pulls that
   qualification's data in (this is the one module with a genuine cross-module dependency — good
   thing to test since it's the most likely place for an integration bug).
2. Generate one section individually, then generate all remaining sections in bulk; confirm no
   section gets silently skipped or duplicated.
3. Export DOCX; confirm all generated sections are present and in order.

### L. 🟢 QMS — Document Control
**Process flow:** Create document (auto-numbered) → lifecycle: **Draft → Under Review → Pending
Approval → Effective → Under Revision → Obsolete** → AI draft generation (streamed) → AI
regulatory-compliance review → version history → distribution list + acknowledgement tracking →
training-requirement tracking → e-signature approval → DOCX export.

**Test script:**
1. Create a document; confirm auto-numbering produces a sane ID (this is the exact spot where a
   real bug was found and fixed: single-word abbreviated departments like "QA" mis-numbering to
   "Q" — retest with a department name like "QA" specifically).
2. Run AI draft generation; confirm it streams and the result is saved as a version.
3. Move it through the full lifecycle (Draft → ... → Effective); confirm the audit trail captures
   every transition (`GET /<record_type>/<id>/audit-trail`).
4. Add a distribution entry, then acknowledge it (`/distribution/<dist_id>/acknowledge`); confirm
   acknowledgement status updates.
5. Add a training requirement, mark it complete; confirm status updates.
6. Attach a file, add a comment, sign/approve, export DOCX. Confirm all four "shared feature set"
   pieces (Attachments, Comments, Audit Trail, Approval) work identically to how they do in
   Deviation/CAPA/Change Control — they share the same backend tables, so a bug here likely means a
   bug everywhere.

### M. 🟢 QMS — Deviation Management
**Process flow:** Create deviation (Minor/Major/Critical/Market × Manufacturing/Laboratory/
Engineering/Validation) → **AI Investigation Assistant** (Fishbone/Ishikawa + 5-Why + timeline +
root cause in one call) → AI impact-assessment suggestion → AI CAPA-seed suggestion → one-click
create-and-link a CAPA from that suggestion → full lifecycle to Closed → approval → export DOCX.

**Test script:**
1. Create a deviation, run `/investigate` (AI Investigation Assistant); confirm the response
   includes all four expected sections (fishbone, 5-why, timeline, root cause) — this is a single
   larger AI call, worth confirming it doesn't time out or return partial/malformed content.
2. Run `/suggest-impact`; confirm a sane suggestion returns.
3. Run `/suggest-capa`, then use the **one-click create-and-link** action. Confirm: (a) a new CAPA
   is actually created, (b) `GET /<did>/capas` shows the link, and (c) the reverse direction also
   works from the CAPA side.
4. Progress the deviation through its full status lifecycle to Closed; confirm audit trail entries
   at each step.
5. Export DOCX and confirm the investigation/impact/CAPA-link content is included, not just the
   base fields.

### N. 🟢 QMS — CAPA
**Process flow:** Create CAPA (Corrective/Preventive) → owners, due dates → AI draft suggestion →
track actions → escalation → effectiveness check → AI effectiveness suggestion → **AI Quality Trend
Summary** across CAPAs + Deviations → approval → export DOCX.

**Test script:**
1. Create a CAPA manually (not via deviation link) to confirm the standalone path also works, not
   just the deviation → CAPA seed path tested in §M.
2. Add actions, escalate one past its due date (`/actions/<aid>/escalate`); confirm status/flagging
   is visible.
3. Record an effectiveness check and run `/suggest-effectiveness`.
4. Hit `/trend-summary` with at least 2-3 CAPAs/deviations in the dev DB present; confirm the AI
   summary reads sensibly (this is a cross-record aggregate call — good one to sanity-check output
   quality specifically, since a demo audience will notice if it's generic filler text).
5. Confirm `GET /<cid>/deviations` correctly shows any linked deviation from §M.

### O. 🟢 QMS — Change Control *(newest module — verify carefully, it's uncommitted)*
**Process flow:** Create change (category: Equipment/Facility/HVAC/Water System/... × type: Major/
Minor/Critical/Temporary/Permanent/Emergency) → 13-stage lifecycle: **Draft → Submitted → Initial
Review → Impact Assessment → Risk Assessment → Department Review → QA Review → Approval →
Implementation → Verification → Effectiveness Review → Closed**, with rejection returning to Draft
from *any* stage → up to 9 optional AI features (impact assessment, implementation plan/checklist,
risk summary, rollback plan, regulatory impact, change justification, executive summary,
verification summary, effectiveness review) → link to existing Deviation/CAPA → approval → export
DOCX.

**Test script:**
1. Create a change control record; step it through all 13 stages sequentially, confirming the UI
   only allows valid forward transitions.
2. From at least 2 different stages (not just Draft), trigger a **rejection** and confirm it
   correctly resets to Draft (this is called out as supported "from any stage" — worth confirming
   it's not just supported from the stage immediately before Approval).
3. Run at least 3 of the 9 AI features (e.g., Impact Assessment, Rollback Plan, Executive Summary)
   and confirm each returns distinct, relevant content — not the same generic text for every field
   (a known transient `503` from Gemini was already observed once during prior verification; treat
   a single retry-and-succeed as acceptable, but a persistent failure is not).
4. Link to an existing Deviation and an existing CAPA (`/link-deviation`, `/link-capa`); confirm
   both directions are queryable (`/<cc_id>/deviations`, `/<cc_id>/capas`).
5. **Known gap:** the reverse link does *not* yet surface inside the Deviation/CAPA detail views
   themselves (only queryable via API). Don't demo "click into the deviation and see the linked
   change" — it isn't there yet.
6. Full attachments/comments/audit-trail/approval/export pass, same as §L/§M/§N.
7. **Before demo day:** commit this module (see Blocker #2) so it can't be lost.

---

## 3. Cross-Cutting Non-Functional Checks

Run these once, across whichever modules you've decided to include in the demo:

1. **Console check on every screen** — open browser DevTools console, click through every
   sidebar item you plan to demo, confirm zero red errors. This catches JS load-order bugs (the
   `showView()`/`renderWizardStep()` collision class of bug in this codebase) before an audience
   does.
2. **Network tab check** — same walkthrough, filter to 4xx/5xx responses. Zero expected.
3. **SSE resilience** — start a chat message or document generation, then navigate away mid-stream.
   Confirm no orphaned request or broken UI state when you navigate back.
4. **Two-tab test** — open the app in two browser tabs, create/edit a project in one, refresh the
   other. Confirms no data corruption from lack of multi-user locking (there's no auth/RBAC yet, so
   this is the closest thing to a concurrency test available today).
5. **Fresh-restart test** — stop the Flask process, start it again, reload the browser. Confirm
   chat history rebuilds correctly and no project/document data was lost (SQLite file persists on
   disk regardless of process restart).
6. **Viewport check** — the UI is documented as desktop-first (1280px+), not mobile-responsive.
   Confirm the demo machine/screen-share is at a normal desktop resolution — don't demo on a narrow
   window or projector set to a portrait aspect ratio.
7. **Full regression** — `pytest` one more time immediately before the demo, after any fixes made
   from this checklist. 101/101 expected.

---

## 4. Suggested Demo Order

Given what's actually wired today, a safe golden-path narrative that avoids dead ends:

1. **Home Dashboard** — overview, live stats.
2. **AI Chat Assistant** — ask a pharma-regulatory question, show streaming.
3. **Project Management** — create a project with equipment metadata.
4. **Document Management** — upload a real SOP/manual PDF, show extraction + insights.
5. **AI Chat with "Use Project Documents"** — same question as step 2, now grounded in the
   uploaded doc, show the Sources strip.
6. **Knowledge Base** — show the permanent library, folders, combinable search.
7. **Generate Document (Validation wizard)** — generate an OQ or IQ end-to-end, export DOCX, show
   the Word-quality formatting.
8. **Quality Management Suite** — Document Control → Deviation (run the AI Investigation Assistant
   live, it's the most impressive single AI feature) → CAPA (show the link) → Change Control (show
   the 13-stage lifecycle and at least one AI feature).
9. *(Only if wired before the demo)* Risk / URS / Qualification / Validation Report suites.

Skip the Validation Workspace unless directly asked — it's the most visibly "partial" piece today.

---

## 5. Sign-Off Checklist

- [ ] `pytest` run, 101/101 passing
- [ ] Dev/demo database cleaned of test artifacts (or fresh `DB_PATH`)
- [ ] Decision made on Risk/URS/Qual/Report: wire nav, or explicitly excluded from demo scope
- [ ] QMS Change Control committed to git
- [ ] `doc_ids` behavior in Validation Generator confirmed (bug reproduced or ruled out) and demo
      script adjusted accordingly
- [ ] Chat XSS/adversarial-input behavior confirmed safe enough for the demo environment
- [ ] Full click-through of every screen in the planned demo order with DevTools console open,
      zero errors
- [ ] `GEMINI_API_KEY` confirmed valid and not near any quota limit
- [ ] Demo run once, start to finish, on the actual machine/network that will be used live

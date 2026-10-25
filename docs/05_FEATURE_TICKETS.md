# 05 — Feature Ticket Backlog

**Document:** Yuktav / PharmaGPT — Controlled Engineering/Product Backlog
**Purpose:** One normalized backlog of product/engineering work, derived from git history, existing verification reports, and code evidence — not a raw TODO dump.
**Status:** Active
**Last reviewed:** 2026-08-23
**Source of truth / authority:** Commit history (`git log`), `docs/RBAC_VERIFICATION_REPORT.md`, `docs/WORKFLOW_VALIDATION_REPORT.md`, `docs/MULTI_TENANT_SECURITY_REPORT.md`, `docs/AUDIT_TRAIL_COVERAGE_REPORT.md`, `docs/PHASE3_FLAGS.md`, code inspection.
**Known limitations:** `docs/CHANGELOG.md` and `docs/ROADMAP.md` are stale (predate RBAC, e-signature, multi-tenant migration, and all Document Control phase work) and were **not used as evidence** for any status below. A status of DONE below means: a specific commit implements it AND current code still reflects it. Where that pairing could not be established, status is **REQUIRES VERIFICATION** — never DONE by default.

**Status values:** DONE · IN PROGRESS · READY · BLOCKED · DEFERRED · PROPOSED · DEPRECATED · REQUIRES VERIFICATION
**Priority values:** P0 Critical · P1 High · P2 Medium · P3 Low

---

## Module: Document Control

### DC-001 — Author-assigned sequential review/approval chain
- **Priority:** P0 | **Status:** DONE | **Source:** commit `75168a4`, confirmed in `pharmagpt/routes/qms_documents.py`, `workflow_engine.py`
- **Description:** Author assigns Reviewer/Department Head/Quality Head/Plant Head(optional); chain locks on submission; decisions are sequential.
- **Dependencies:** DC-002, DC-003
- **Acceptance Criteria:** Chain cannot be reassigned once version leaves Draft; decisions occur in order; Plant Head auto-skips if unassigned.
- **Notes:** Supersedes DC-006 (Approver Pool prerequisite, removed).

### DC-002 — Immutable version architecture & version numbering engine
- **Priority:** P0 | **Status:** DONE | **Source:** commits `78d2503`, `ff498ff`; `pharmagpt/services/document_versioning.py`
- **Description:** Pure-logic version numbering (0.1→0.2→...→1.0, then X.1→(X+1).0 per Effective release).
- **Dependencies:** —
- **Acceptance Criteria:** Version numbers advance correctly across draft/review/effective cycles.

### DC-003 — Author Self-Check hard gate + new-revision cycle
- **Priority:** P0 | **Status:** DONE | **Source:** commits `6333f9a`, `b3ac7c6`
- **Description:** Self-check must be cleared and Final Author Version uploaded before Submit for Review is enabled.
- **Dependencies:** —
- **Acceptance Criteria:** Submit blocked (409) until both gates cleared; UI states exactly which gate is missing.

### DC-004 — Controlled template DOCX export/import
- **Priority:** P1 | **Status:** DONE | **Source:** commits `cedb51a`, `85b10d2`
- **Description:** Real controlled DOCX template download for Route A SOP creation.
- **Dependencies:** —

### DC-005 — AI-Assisted SOP DOCX output
- **Priority:** P1 | **Status:** DONE | **Source:** commit `54cc647`
- **Description:** Route B generation produces a real DOCX (not Markdown); enforces "no invented equipment information" rule.
- **Dependencies:** —

### DC-006 — Approver Pool prerequisite (removed)
- **Priority:** — | **Status:** DEPRECATED | **Source:** commit `3199d31`
- **Description:** A separate SQLite approval pool duplicating the tenant user directory. Removed in favor of direct name-based assignment (DC-001).
- **Notes:** Do not re-propose without a documented reason (see `docs/LESSONS_LEARNED.md` §20).

### DC-007 — Configurable quorum approval
- **Priority:** — | **Status:** DEPRECATED | **Source:** commits `6e4b052`, `b3a01f1`
- **Description:** Generic quorum approval was added, then narrowed to final-approval-only, then superseded entirely by DC-001's sequential named-approver model.

### DC-008 — Controlled PDF review with UNDER REVIEW watermark
- **Priority:** P0 | **Status:** DONE | **Source:** commit `75168a4`; `qms_document_service.py::generate_review_pdf()`
- **Description:** Read-only, watermarked, exact-version PDF for reviewer/approver review.
- **Dependencies:** DC-004

### DC-009 — Quality Release (renamed from "Made Effective") + training gate
- **Priority:** P1 | **Status:** DONE | **Source:** commit `4b0d172`
- **Description:** Release to Effective restricted to company_admin/reviewer_qa; requires ≥90% training completion.
- **Dependencies:** DC-001, DC-008

### DC-010 — Terminal-state (Obsolete) immutability guard
- **Priority:** P1 | **Status:** REQUIRES VERIFICATION | **Source:** `docs/WORKFLOW_VALIDATION_REPORT.md` §4; code-read only
- **Description:** Obsolete documents must reject further edits.
- **Notes:** Verified by code read, not a dedicated automated test (unlike the CAPA pattern). See WF-004.

### DC-011 — Document Control Postgres dual-write path
- **Priority:** P2 | **Status:** PROPOSED | **Source:** [02 §5](02_TECHNICAL_ARCHITECTURE.md)
- **Description:** Document Control currently has zero Postgres exposure, unlike Deviations/CAPA/Change Control/Risk (which share `QMS_BACKEND`).
- **Dependencies:** DB-003

### DC-012 — `assign-chain` endpoint: no server-side "who may assign" check
- **Priority:** P1 | **Status:** READY | **Source:** this review, [03 §5](03_SECURITY_ACCESS.md)
- **Description:** Only Draft-state is enforced server-side; identity of the assigner (Author-only) is UI convention only.
- **Acceptance Criteria:** Decide and implement either a server-side Author-only check, or formally document the accepted risk.

### DC-013 — DOCX/PDF export color parity with UI design system
- **Priority:** P3 | **Status:** PROPOSED | **Source:** `docs/DESIGN_SYSTEM.md` §11; [04 §15](04_FRONTEND_SPECIFICATION.md)
- **Description:** Exported documents still use navy heading color vs. the current warm-theme UI palette.

### DC-014 — Risk/URS/Qualification/Validation Report sidebar navigation completeness
- **Priority:** P2 | **Status:** REQUIRES VERIFICATION | **Source:** `docs/DESIGN_SYSTEM.md` §4.2, `docs/QMS_PHASE1.md`, [04 §15](04_FRONTEND_SPECIFICATION.md)
- **Description:** Repeatedly flagged as "unwired" across three docs; sidebar markup suggests Risk may in fact be reachable via a different path than assumed. Needs direct re-verification, not documentation guesswork.

### DC-015 — Mobile responsiveness of controlled-PDF review iframe
- **Priority:** P3 | **Status:** PROPOSED | **Source:** [04 §13](04_FRONTEND_SPECIFICATION.md)
- **Description:** Fixed 70vh iframe has no responsive override; behavior on mobile widths is a genuine open product decision.

### DC-016 — Document Control empty-state consistency
- **Priority:** P3 | **Status:** PROPOSED | **Source:** [04 §11](04_FRONTEND_SPECIFICATION.md)
- **Description:** `qms_documents.js` hand-rolls empty states instead of using the shared `PharmaUI.emptyState()` helper used elsewhere.

### DC-017 — Delegate action uses native `prompt()` instead of user picker
- **Priority:** P3 | **Status:** PROPOSED | **Source:** [04 §9](04_FRONTEND_SPECIFICATION.md); `workflow_panel.js`
- **Description:** Inconsistent with the name-based picker used throughout the rest of the chain UI.

---

## Module: URS

### URS-001 — URS Stabilization (auto-numbering, identity resolution, lifecycle guard, e-signature)
- **Priority:** P1 | **Status:** REQUIRES VERIFICATION | **Source:** `docs/URS_STABILIZATION_REVIEW.md` (Iteration 1 findings), commit `53afea2` (Iterations 2–4)
- **Description:** Iteration 1 found URS had no document-control automation at all (no auth/tenant context in `routes/urs.py`, free-text sign-off fields, no lifecycle guard). Iteration 2–4 commit claims these are fixed.
- **Notes:** No later report re-confirms current URS state against code the way Iteration 1 originally audited it. Recommend a fresh verification pass before marking DONE.

---

## Module: RBAC

### RBAC-001 — Fine-grained RBAC framework
- **Priority:** P1 | **Status:** DONE | **Source:** commit `8829ff0`; `pharmagpt/auth/rbac.py`, `tests/test_rbac.py`
- **Description:** Departments, roles, permission matrix, audit trail; 15 modules × 8 actions.

### RBAC-002 — Company-admin multi-role support + diagnostic logging
- **Priority:** P2 | **Status:** DONE | **Source:** commits `9df40cb`, `81686f5`

### RBAC-003 — Close 3 unguarded mutating endpoints
- **Priority:** P0 | **Status:** DONE | **Source:** `docs/RBAC_VERIFICATION_REPORT.md` §3; `tests/test_phase_f_compliance.py`
- **Description:** Risk publish, protocol-complete, CAPA-escalate lacked role guards; fixed and test-verified.

### RBAC-004 — Wire fine-grained RBAC permissions into business routes
- **Priority:** P2 | **Status:** PROPOSED | **Source:** [03 §2](03_SECURITY_ACCESS.md)
- **Description:** Currently the 15-module RBAC permission layer governs only `/rbac` and `/org` administration routes, not Document Control/Deviations/CAPA/etc.

### RBAC-005 — Document distribution/training routes left unguarded by role
- **Priority:** P2 | **Status:** DEFERRED | **Source:** `docs/RBAC_VERIFICATION_REPORT.md` §4
- **Description:** Explicitly flagged for a product-owner decision, not an oversight.

### RBAC-006 — Confirm RBAC framework branch merged/deployed
- **Priority:** P1 | **Status:** REQUIRES VERIFICATION | **Source:** [03 §2, §14](03_SECURITY_ACCESS.md)

---

## Module: Electronic Signature

### ESIG-001 — E-signature framework, integrated into all GMP decision endpoints
- **Priority:** P0 | **Status:** DONE | **Source:** commits `da4b2a3`, `aff3871`; `pharmagpt/services/esignature_service.py`

### ESIG-002 — Fix identity-spoofing on signature-adjacent fields
- **Priority:** P0 | **Status:** DONE | **Source:** `docs/AUDIT_TRAIL_COVERAGE_REPORT.md` §4 (8 call sites fixed)

### ESIG-003 — MFA re-authentication enforcement
- **Priority:** P2 | **Status:** PROPOSED | **Source:** `esignature_service.py` (`reauth_method` field reserved, unenforced)

### ESIG-004 — Equipment Release / Batch Record e-signature integration
- **Priority:** P3 | **Status:** PROPOSED | **Source:** `docs/ESIGNATURE_MODULE_INTEGRATION.md` §3
- **Notes:** No such module/route exists yet in this codebase — this is a future-module dependency, not a current gap.

### ESIG-005 — Confirm e-signature framework branch merged/deployed
- **Priority:** P1 | **Status:** REQUIRES VERIFICATION | **Source:** [01 §10](01_PRODUCT_REQUIREMENTS.md), [03 §2, §14](03_SECURITY_ACCESS.md)

---

## Module: Multi-Tenant Security

### MT-001 — Company-scoped queries + 404-not-403 tenant isolation
- **Priority:** P0 | **Status:** DONE | **Source:** `docs/MULTI_TENANT_SECURITY_REPORT.md` §1–5

### MT-002 — Live 2-company RLS isolation spot-check on Supabase
- **Priority:** P1 | **Status:** BLOCKED | **Source:** `docs/MULTI_TENANT_SECURITY_REPORT.md` §32; `docs/PHASE_F_FINDING_TRACEABILITY.md` A1–A3
- **Notes:** Blocked on live Supabase/ops access, not on engineering work.

### MT-003 — Company-scope or remove cross-tenant `_score_cache`
- **Priority:** P2 | **Status:** READY | **Source:** `docs/MULTI_TENANT_SECURITY_REPORT.md` §7; `review_engine.py`

### MT-004 — Confirm Company Administration RLS grants + `SUPABASE_SERVICE_ROLE_KEY` set live
- **Priority:** P1 | **Status:** BLOCKED | **Source:** `docs/PRODUCTION_RELEASE_CHECKLIST.md` §B/C
- **Notes:** Blocked on live Render/Supabase environment access.

---

## Module: Audit Trail

### AUD-001 — Shared audit writer wired into 12 route files
- **Priority:** P0 | **Status:** DONE | **Source:** `docs/AUDIT_TRAIL_COVERAGE_REPORT.md` §1–3; `tests/test_phase_f_compliance.py`

### AUD-002 — Postgres-side audit for Users/Companies
- **Priority:** P2 | **Status:** REQUIRES VERIFICATION | **Source:** `docs/AUDIT_TRAIL_COVERAGE_REPORT.md` §5 (self-flagged "not verified")

### AUD-003 — Individual sub-record audit (URS requirements/test cases/distribution training)
- **Priority:** P3 | **Status:** DEFERRED | **Notes:** Documented as an intentional scope cut, not a gap.

### AUD-004 — Audit-log viewer for break-glass grants
- **Priority:** P2 | **Status:** PROPOSED | **Source:** [03 §13](03_SECURITY_ACCESS.md)

---

## Module: Workflow / Lifecycle

### WF-001 — Generic workflow engine (`STATUS_APPLIERS` registry)
- **Priority:** P1 | **Status:** DONE | **Source:** `pharmagpt/services/workflow_engine.py`

### WF-002 — Wire CAPA and Change Control into lifecycle_engine
- **Priority:** P1 | **Status:** READY | **Source:** `docs/WORKFLOW_VALIDATION_REPORT.md` §5, finding H7
- **Description:** Currently any status can follow any status for these two modules — no validated transition guard.

### WF-003 — IQ→OQ→PQ sequencing gate + PQ-completeness gate on Report approval
- **Priority:** P1 | **Status:** DONE | **Source:** `docs/WORKFLOW_VALIDATION_REPORT.md` §1–4

### WF-004 — Terminal-state immutability test coverage for remaining 7 modules
- **Priority:** P2 | **Status:** READY | **Source:** `docs/WORKFLOW_VALIDATION_REPORT.md` §4
- **Description:** Only CAPA has a dedicated automated test; replicate for the other 7.
- **Dependencies:** DC-010

---

## Module: Database Migration (SQLite → Postgres/Supabase)

### DB-001 — Dual-write code for Projects/KB/Equipment/QMS (Deviations/CAPA/Change Control/Risk)
- **Priority:** P1 | **Status:** IN PROGRESS | **Source:** commits `d235c86`…`7dc015e`, `608f132`, `7d5b6ce`; `docs/PHASE3_FLAGS.md`
- **Description:** Code complete for 4 domains; all flags still default to `sqlite`; no staging soak performed.

### DB-002 — Staging soak + 2-company RLS spot-check per domain
- **Priority:** P1 | **Status:** BLOCKED | **Source:** `docs/PHASE3_FLAGS.md`
- **Dependencies:** DB-001; blocked on ops/staging environment access.

### DB-003 — Document Control Postgres dual-write path
- **Priority:** P2 | **Status:** PROPOSED | **Source:** [02 §5](02_TECHNICAL_ARCHITECTURE.md)
- **Dependencies:** DC-011 (same item, cross-referenced from Document Control module)

### DB-004 — Phase 3.6 SQLite retirement
- **Priority:** P2 | **Status:** PROPOSED | **Dependencies:** DB-002

### DB-005 — Phases 4–12 (Storage, Project Workspace, AI Engine, Document Engine, Validation, Testing, Production cutover)
- **Priority:** P3 | **Status:** PROPOSED | **Source:** `docs/IMPLEMENTATION_ROADMAP.md`
- **Notes:** No commits found matching these phase numbers beyond Phase 3.x — not started.

### DB-006 — Resolve "Phase 3" naming collision
- **Priority:** P3 | **Status:** READY | **Source:** this review
- **Description:** `IMPLEMENTATION_ROADMAP.md`'s Phase 3 ("Database Migration") and commit `7a98428` ("Phase 3: Shared Validation Engine, Document Lifecycle...") are two unrelated plans sharing a phase number. Docs-only fix.

### DB-007 — Projects ID reshape (integer → UUID) required before Postgres cutover
- **Priority:** P2 | **Status:** PROPOSED | **Source:** `docs/DATABASE_ARCHITECTURE.md`

---

## Module: Equipment

### EQ-001 — Re-parent Equipment from project-owned to company-owned
- **Priority:** P2 | **Status:** PROPOSED | **Source:** [01 §8](01_PRODUCT_REQUIREMENTS.md), [02 §11](02_TECHNICAL_ARCHITECTURE.md)

### EQ-002 — Risk Assessment ↔ Equipment integration
- **Priority:** P3 | **Status:** PROPOSED | **Source:** `static/js/equipment.js:469` ("Risk Management Suite does not reference Equipment directly yet")

### EQ-003 — Calibration / Preventive Maintenance / Spare Parts modules
- **Priority:** P3 | **Status:** PROPOSED | **Source:** `EQ_FUTURE_MODULES` UI tab, reserved-but-empty tables
- **Notes:** Explicit v1.1+ scope; do not build during current Document Control work (per `docs/LESSONS_LEARNED.md` §21).

### EQ-004 — Wire Equipment AI-context bundle into generation
- **Priority:** P2 | **Status:** READY | **Source:** `routes/equipment.py:328` (`equipment_ai_context`, code exists, explicitly commented "not yet wired into generation")

---

## Module: Extraction / OCR

### EXT-001 — OCR engine implementation
- **Priority:** P3 | **Status:** PROPOSED | **Source:** `pharmagpt/services/extraction/pdf_engines.py:161-168` (`EngineOpenError("OCR engine is not implemented yet")` — deliberate, logged fallback, not a silent bug)

---

## Module: Feature Requests (Internal Backlog Tool)

### FRQ-001 — Feature Requests module v2 (workflow/approvals/dual-write)
- **Priority:** P3 | **Status:** PROPOSED | **Source:** `pharmagpt/routes/qms_feature_requests.py` module docstring (explicitly deferred)
- **Notes:** Confirmed to be an internal/in-app backlog CRUD tool, not an end-user-facing feature-request system.

---

## Module: Infrastructure / Deployment

### INFRA-001 — Backup framework deployment (encryption key, cron activation)
- **Priority:** P1 | **Status:** READY | **Source:** [02 §15, §18](02_TECHNICAL_ARCHITECTURE.md); `render.yaml` (cron present but commented out)

### INFRA-002 — Environment separation (staging vs. production Supabase/Render)
- **Priority:** P1 | **Status:** PROPOSED | **Source:** `docs/LESSONS_LEARNED.md` §13; `docs/FINAL_DATABASE_ROOT_CAUSE.md` (historical finding of a single undifferentiated environment)
- **Notes:** Needs live re-verification against the current Render dashboard, not a documentation change.

### INFRA-003 — Oracle deployment target clarification
- **Priority:** P2 | **Status:** REQUIRES VERIFICATION | **Source:** [02 §19](02_TECHNICAL_ARCHITECTURE.md)
- **Description:** Single, unelaborated mention in `docs/LESSONS_LEARNED.md`; needs a product-owner decision on what platform is actually intended.

### INFRA-004 — Confirm AI provider router status (multi-provider vs. single Gemini)
- **Priority:** P2 | **Status:** REQUIRES VERIFICATION | **Source:** [01 §9](01_PRODUCT_REQUIREMENTS.md), [02 §12](02_TECHNICAL_ARCHITECTURE.md)

---

## Module: Documentation

### DOC-001 — Retire or clearly mark `docs/CHANGELOG.md` and `docs/ROADMAP.md` as historical
- **Priority:** P2 | **Status:** READY | **Source:** this review
- **Description:** Both predate RBAC, e-signature, multi-tenant migration, and all Document Control phase work by roughly two months of major shipped work; risk of being mistaken for current status.

---

## Open Questions / Conflicts (backlog-level)

1. Several tickets (RBAC-006, ESIG-005) depend on confirming whether their frameworks' branches have merged to `main` — this blocks accurately setting DONE vs. IN PROGRESS status for a meaningful share of the backlog.
2. MT-002, MT-004, DB-002 are all blocked on live Supabase/Render access that this review did not have — these should be picked up by whoever holds deployment credentials, not re-attempted by inference from code.
3. DB-006's naming collision should be resolved in the roadmap documents themselves before further phase-numbered work is planned, to avoid future confusion between the two unrelated "Phase 3" efforts.

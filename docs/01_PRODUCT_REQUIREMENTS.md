# 01 — Product Requirements

**Document:** Yuktav / PharmaGPT — Product Requirements
**Purpose:** Define WHAT the product must do, for whom, and why — business/product perspective only. Not architecture (see [02](02_TECHNICAL_ARCHITECTURE.md)), not access control (see [03](03_SECURITY_ACCESS.md)), not UI detail (see [04](04_FRONTEND_SPECIFICATION.md)).
**Status:** Active — consolidated from prior documentation + verified current code
**Last reviewed:** 2026-08-23
**Source of truth / authority:** Current code (`pharmagpt/routes/qms_documents.py`, `pharmagpt/auth/`, `pharmagpt/routes/companies.py`, `pharmagpt/routes/equipment.py`) is authoritative for CURRENT state. `docs/PLATFORM_ARCHITECTURE.md` (frozen 2026-07-11) is authoritative for TARGET/PROPOSED state unless superseded below. `docs/PRODUCT_REQUIREMENTS.md` (v0.7, 2026-06-27) is a **historical baseline only** — largely superseded, retained for lineage.
**Known limitations:** This document was assembled without live access to the deployed Render/Supabase environment; branch/merge status of some frameworks (RBAC, e-signature) relative to `main` was not independently re-verified (see §12).

---

## 1. Product Vision & Purpose

**CONFIRMED.** Yuktav (product/UI name; codebase and company name remain "PharmaGPT") is an AI-native system of record for GxP documentation and quality operations, targeting pharmaceutical, nutraceutical, medical device, biotech, CDMO, and CRO organizations. Positioned as an alternative to Veeva Vault, MasterControl, and TrackWise Digital. *Source: `docs/PLATFORM_ARCHITECTURE.md` §1.*

**CONFIRMED (historical origin, still true of the AI-consultation core):** The product began as an AI validation/compliance consultant that answers compliance questions and generates regulatory-grade documents grounded in the user's own uploaded material. *Source: `docs/PRODUCT_REQUIREMENTS.md` §1 (v0.7).*

The product has since grown from a single-tenant AI consultant into a multi-tenant SaaS quality management system. Both descriptions are true of different layers of the current product — the AI-consultation core described in the v0.7 baseline still exists (Chat module) alongside the newer multi-tenant QMS/Document Control layer.

## 2. Target Users / Personas

**CONFIRMED (original personas, still directionally valid for the AI-consultation core):**
- **Validation Engineer** (primary) — runs IQ/OQ/PQ, produces URS/DQ/FAT/SAT, values speed and structural accuracy.
- **QA/QC Manager** (secondary) — reviews deviations/CAPA/change controls, manages Knowledge Base structure, values traceability and version control.
- **Regulatory Affairs Specialist** (tertiary) — prepares regulatory submissions, values citation accuracy.
*Source: `docs/PRODUCT_REQUIREMENTS.md` §3.*

**CONFIRMED (current platform roles, superseding any older role vocabulary — see §6):** `super_admin`, `company_admin`, `reviewer_qa`, `user`. *Source: `pharmagpt/auth/decorators.py`.*

## 3. Tenant / Company Model

**CONFIRMED.** Multi-tenant. A `companies` table holds `legal_name`, `industry_segment` (enum), `status` (active/suspended). Only a Super Admin can create a company and its first Company Admin — **no public self-signup**. *Source: `pharmagpt/routes/companies.py:60-146`.*

**CONFIRMED.** Every request resolves a server-side `TenantContext(user_id, email, display_name, role, company_id)` from the authenticated session; `company_id` is never client-supplied. *Source: `pharmagpt/auth/context.py:24-32`.*

This directly supersedes the v0.7 PRD, which listed "multi-user authentication/RBAC" and "cloud deployment/multi-tenancy" as **out of scope, planned v0.9** (§11 below) — both have since shipped.

## 4. Core Modules

**CONFIRMED**, from route inventory and `PROJECT_MEMORY/ARCHITECTURE.md`:

| Module | Status |
|---|---|
| Chat (AI consultation, SSE streaming) | Current |
| Projects / Project Workspace | Current |
| Knowledge Base (company-wide) | Current |
| Equipment Library | Current (project-owned today — see [02 §11](02_TECHNICAL_ARCHITECTURE.md)) |
| Validation Document Generator (URS, DQ, FAT, SAT, IQ, OQ, PQ, FMEA, CAPA, Deviation, Change Control — 11 types) | Current |
| Risk Assessment / URS / Qualification / Validation Report suites | Current backend; sidebar navigation completeness **not reverified this pass** — flagged in [04](04_FRONTEND_SPECIFICATION.md) |
| QMS: Deviation Management, CAPA, Change Control | Current |
| QMS: Document Control | Current — most actively developed module (10 phase commits since 2026-07); see §5 |
| Company Administration (Super Admin / Company Admin) | Current |
| Org Structure / User Directory | Current |

## 5. Document Control / SOP Lifecycle

This is the newest and most detailed area of the product. Treat this section as authoritative over any older doc (e.g. `docs/QMS_PHASE1.md`'s simpler lifecycle description, which is **superseded**).

### 5.1 Two SOP creation routes — CURRENT / APPROVED

- **Route A — Controlled Template.** Author downloads the real controlled DOCX template (`GET /qms/documents/templates/<id>/download`) and prepares the SOP from that template.
- **Route B — AI-Assisted SOP Creation.** Author selects relevant equipment; the system uses that equipment's linked Knowledge Base documents as generation context (`POST /qms/documents/<id>/generate`, streamed).

**Hard constraint (CONFIRMED, `pharmagpt/prompts/qms_document_prompt.py:133-135`):** the AI must not invent missing equipment information. Where information is absent it must emit `[INFORMATION GAP — not found in Knowledge Base; confirm with equipment owner/manual]`. The generated result becomes a real controlled DOCX document, never a Markdown download.

### 5.2 Document lifecycle states — CURRENT / APPROVED

Document-level: `Draft → Under Review → Pending Approval → Approved → Effective → Under Revision → Obsolete`.
Version-level: `draft → approved → effective`.

### 5.3 Review / approval chain — CURRENT / APPROVED

Workflow roles (distinct from platform roles, see §6): **Reviewer, Department Head, Quality Head, Plant Head (optional)**.

- **The Author assigns the complete chain.** Reviewers and approvers do not assign other people.
- The chain **locks once the document leaves Draft** (a re-assign attempt after submission is rejected server-side).
- Decision order is sequential: Reviewer → Department Head → Quality Head → Plant Head (if assigned) → Approved.
- Plant Head is optional and auto-skipped server-side if unassigned.

This directly supersedes the earlier **Approver Pool** model (a separate SQLite pool of pre-registered approvers), which was deliberately removed (commit `3199d31`) in favor of assigning named individuals directly from the existing tenant user directory (commit `75168a4`). Any reference to "Approver Pool" as a *prerequisite* is **DEPRECATED**; a per-role default "Approver Pool" **settings/configuration** convenience still exists in the UI (see [04 §8](04_FRONTEND_SPECIFICATION.md)) but is not a gating requirement.

### 5.4 Hard gates before Submit for Review — CURRENT / APPROVED

1. Author Self-Check cleared.
2. Final Author Version uploaded (text extraction must succeed).
3. Complete chain assigned (Reviewer + Department Head + Quality Head mandatory; Plant Head optional).

Submission is blocked server-side if any gate is unmet — this is a **business rule**, not merely a UI convenience, and must never be bypassed to "unblock testing" (per `docs/LESSONS_LEARNED.md` §19).

### 5.5 Controlled PDF review — CURRENT / APPROVED

Reviewer/Department Head/Quality Head/Plant Head review a **read-only, watermarked "UNDER REVIEW" PDF** representing the exact version under review (`GET /qms/documents/<id>/review-pdf`) — never an unrelated template, Markdown, an editable Word document, an old version, or an Effective copy. The watermark reflects lifecycle state (UNDER REVIEW / PENDING APPROVAL / APPROVED) and is removed once the document reaches Effective.

### 5.6 Release to Effective ("Quality Release") — CURRENT / APPROVED

Restricted to `company_admin` / `reviewer_qa` roles — never the Author. Requires version status `approved` **and** a training-completion gate (≥90% target audience acknowledgment). Named "Quality Release" in the UI (renamed from "Made Effective").

## 6. User Roles

Two distinct role vocabularies exist in the current product — do not conflate them:

- **Platform/workspace roles** (exact code strings, govern route-level authorization): `super_admin`, `company_admin`, `reviewer_qa`, `user`. See [03](03_SECURITY_ACCESS.md) for enforcement detail.
- **Document Control workflow-assignment roles** (per-document, name-based, not tied 1:1 to platform roles): `Reviewer`, `Department Head`, `Quality Head`, `Plant Head`.

**Important lesson, preserved from `docs/LESSONS_LEARNED.md` §5:** designation names in an org chart (e.g. "Quality Reviewer", "Production Head") must not be assumed equivalent to these exact workflow-role strings. The system uses the existing tenant user directory as the source of truth and lets the Author select the appropriate person, rather than filtering by exact designation match.

**PROPOSED / not wired to business routes:** a 21-role RBAC template set (Platform Admin, Plant Head, QA/QC/Validation/Production/Engineering/Warehouse/EHS Managers+Officers, Regulatory Manager, Auditor, Viewer, etc.) exists in `docs/RBAC_FRAMEWORK.md` and in code (`pharmagpt/auth/rbac.py`), but is currently used only by `/rbac/*` and `/org/*` administration routes — no business route (Document Control, Deviations, CAPA, etc.) currently checks fine-grained RBAC permissions. See [03 §2](03_SECURITY_ACCESS.md).

## 7. Knowledge Base — Role in the Product

**CONFIRMED.** One centralized Knowledge Base per company (not per-project), with 8 fixed folders: SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others. Serves two purposes:
1. Reference material for AI-Assisted SOP generation (via equipment linkage).
2. General document library with metadata (title, tags, version, effective/review dates) and full-text/keyword search.

Approved documents from Document Control, URS, Qualification, and Validation Reports are auto-published into the Knowledge Base.

## 8. Equipment Library — Role in the Product

**CONFIRMED.** Acts as the central reference "hub" for equipment-related work: referenced (not copied) by URS, DQ, FAT, SAT, IQ, OQ, PQ, SOPs, Validation Reports, Risk Assessments, Change Controls, Deviations, and CAPA, and used as AI-generation context for Document Control's AI-Assisted route.

**CURRENT STATE vs TARGET STATE:** Equipment is currently **project-owned** in code (`project_id NOT NULL`); the target/approved direction is **company-owned** equipment, matching how it is described product-wise in §8 of `docs/PLATFORM_ARCHITECTURE.md`. This re-parenting has **not yet been executed in code** — see [02 §11](02_TECHNICAL_ARCHITECTURE.md) and ticket EQ-001 in [05](05_FEATURE_TICKETS.md).

## 9. AI-Assisted Generation

**CONFIRMED:**
- Google Gemini (`gemini-2.5-flash`) powers generation; streamed via SSE at `temperature=0.3` for structural consistency.
- AI-generated documents always start in Draft and must pass through the full review/approval chain — there is no AI fast-path to Approved or Effective.
- Document Control's AI-assisted route enforces the "no invented equipment information" rule (§5.1).

**ASSUMPTION / not independently reverified this pass:** whether a pluggable multi-provider AI router (referenced by commit messages mentioning an "AI orchestration router" and "NVIDIA Nemotron support") is the current default, versus Gemini alone. Flagged for a targeted code check before being stated as CURRENT in any downstream material.

## 10. Auditability / Compliance-Related Product Requirements

**CONFIRMED:**
- Every document state transition writes an audit-trail entry (actor, timestamp, prior/new state, reason where applicable).
- Every document reaching In Review is versioned as an immutable snapshot.
- Electronic signature (typed identity + password re-authentication + timestamp + reason, hashed) gates every GMP decision endpoint, including Document Control's workflow decisions. See [03 §10](03_SECURITY_ACCESS.md) for the exact mechanism and its limits.

**CONFLICT / REQUIRES DECISION:** `docs/PLATFORM_ARCHITECTURE.md` (frozen 2026-07-11) describes electronic signature as "future, v1.1, typed-name only, not cryptographically binding." Current code (`pharmagpt/services/esignature_service.py`) implements password re-authentication + SHA-256 hashed signature records, already wired into Document Control and other GMP decision endpoints. Code is more recent and more directly verifiable than the frozen architecture doc, but whether this branch is merged to `main`/deployed to production was **not independently confirmed** in this pass. **Decision needed:** confirm deployment status before describing e-signature as "live in production" in any external-facing material.

## 11. Current / MVP Scope vs Historical Out-of-Scope List

The v0.7 PRD (§6) listed six items as out of scope. Current status of each:

| v0.7 "Out of Scope" item | Current status |
|---|---|
| Multi-user authentication / RBAC | **DONE** — shipped (§3, §6) |
| Vector embedding RAG | **NOT DONE** — current search is keyword/Jaccard-based (`document_search.py`); vector/pgvector search remains TARGET STATE only |
| Electronic signature workflows | **DONE in code**, deployment status unconfirmed — see §10 conflict |
| Email notifications | **NOT DONE** — a `notifications` table is reserved but unused |
| Cloud deployment / multi-tenancy | **DONE** |
| Mobile-native app | **NOT DONE** — no mobile app; responsive web only (see [04](04_FRONTEND_SPECIFICATION.md)) |

## 12. Open Questions / Conflicts

1. **E-signature maturity** — see §10. Code shows an implemented mechanism; the frozen architecture doc calls it future work. Needs a decision on which is authoritative for external communication, and confirmation of production deployment status.
2. **RBAC/e-signature branch status** — `docs/RBAC_FRAMEWORK.md` and `docs/ESIGNATURE_FRAMEWORK.md` both state, as authored, that their branches were "not merged into `main`, not deployed." Current work is on `feature/document-control-redesign`. Whether these have since merged to `main` was not reverified — **requires confirmation before treating either as live in production**.
3. **AI provider** — whether a multi-provider router has replaced single-provider Gemini as the current default (§9) requires a targeted code check.
4. **Risk/URS/Qualification/Validation Report sidebar navigation completeness** — repeatedly flagged across three older docs as a gap; current status post-Document-Control-redesign not reverified this pass (see [04 §16](04_FRONTEND_SPECIFICATION.md)).
5. **Vocabulary drift** — `docs/ROADMAP.md`'s historical "v0.9 RBAC" plan proposed roles (`Admin | QA Manager | Engineer | Viewer`) that were never shipped; the actual roles are the four listed in §6. `docs/ROADMAP.md` and `docs/CHANGELOG.md` predate RBAC, e-signature, multi-tenant migration, and all Document Control phase work — **do not use either as evidence of current product state.**

## Traceability

| Requirement area | Primary source |
|---|---|
| Vision, personas | `docs/PRODUCT_REQUIREMENTS.md` (v0.7, historical), `docs/PLATFORM_ARCHITECTURE.md` |
| Tenant/company model | `pharmagpt/routes/companies.py`, `pharmagpt/auth/context.py` |
| Document Control lifecycle | `pharmagpt/routes/qms_documents.py`, `pharmagpt/prompts/qms_document_prompt.py`, `docs/LESSONS_LEARNED.md` §3–4, §9 |
| Roles | `pharmagpt/auth/decorators.py`, `docs/RBAC_FRAMEWORK.md` |
| Knowledge Base | `pharmagpt/routes/knowledge_base.py`, `docs/PLATFORM_ARCHITECTURE.md` §9 |
| Equipment | `pharmagpt/routes/equipment.py`, `docs/PLATFORM_ARCHITECTURE.md` §10 |

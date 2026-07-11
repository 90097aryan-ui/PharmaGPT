# PharmaGPT Multi-Tenant SaaS Architecture v1.0

**Document class:** Master Architecture Reference (Frozen)
**Author role:** Chief Software Architect / Enterprise Solution Architect
**Status:** FROZEN — governs all future development. Changes require a formal decision entry in §33, not silent drift.
**Date:** 2026-07-11
**Revision:** Review pass 2 (pre-freeze) — added Equipment Library (§10), standardized the platform-wide document lifecycle to six states (§12), added Global Search (§14) and Future Integration Architecture (§25), and renumbered accordingly. All decisions from the first pass remain intact; nothing already frozen was reversed. New decisions are logged as PA-013–PA-016 in §33.
**Supersedes for tenancy/platform matters:** Nothing. This document does not touch, contradict, or re-litigate [`FOUNDATION_ARCHITECTURE.md`](../FOUNDATION_ARCHITECTURE.md) (the frozen record of the Project/Equipment/Workspace consolidation on the current single-tenant build). It defines the destination architecture — multi-tenant SaaS on Supabase — that the current SQLite/local-disk build migrates into. Where the two documents describe the same entity (Project, Equipment, Knowledge Base, QMS), this document is authoritative for the target state; `FOUNDATION_ARCHITECTURE.md` remains authoritative for what shipped and why, as history. One deliberate exception, called out explicitly rather than left implicit: §10 elevates Equipment from a project-owned entity (its current shipped shape) to a company-owned, centrally referenced one — a genuine platform-level change, not a restatement.

---

## 0. How to Read This Document

This is not a design proposal. It is a decision record. Every section states what PharmaGPT *is*, not what it could be — optionality is called out explicitly where it exists, and closed off where it doesn't. Engineers, in this session or in future sessions months from now, should be able to open this document and know, without asking, whether a given implementation choice is compliant with the architecture or a deviation from it.

Where a decision has real trade-offs, this document states the choice made, the reason it was made, and the cost being knowingly accepted. That is the difference between an architecture document and a wish list.

---

## 1. Product Vision

PharmaGPT is the AI-native system of record for GxP documentation and quality operations across the pharmaceutical, nutraceutical, medical device, biotech, CDMO, and CRO industries.

The regulated-industry documentation stack today is a patchwork: validation protocols in Word templates, SOPs in SharePoint, deviations in spreadsheets, and AI assistance living nowhere at all — bolted on, if present, as an unauditable chat window with no connection to the controlled record. Incumbents (Veeva Vault, MasterControl, TrackWise Digital) solved the controlled-document and workflow problem at large enterprise price points and multi-year implementation timelines. None of them were built AI-first: their AI features are additive, not foundational.

PharmaGPT's vision is to be the platform where **AI-generated and AI-assisted GxP documentation is the default way the work gets done**, not a bolt-on — while meeting the same controlled-document, audit-trail, and access-control bar the incumbents set. It is built multi-tenant from day one so that a five-person nutraceutical startup and a thousand-user CDMO run on the same platform, the same codebase, and the same compliance guarantees, differentiated only by configuration and scale, never by a fork.

The commercial wedge is speed and cost: AI-drafted URS/DQ/FAT/SAT/IQ/OQ/PQ and quality records at a fraction of the authoring time incumbents require, without giving up the controlled-record rigor regulated customers cannot compromise on.

---

## 2. Design Principles

These principles are the lens every future architectural decision is checked against. When a proposed change conflicts with one of these, the change is wrong until proven otherwise — not the principle.

1. **Tenant isolation is non-negotiable.** No code path may return, log, or expose one company's data to another, under any error condition. This is checked at the data layer, not trusted to application logic alone (§6, §16).
2. **Metadata and content are never conflated.** The database is the source of truth for *what exists, who owns it, and what state it's in*. Object storage holds bytes only. Nothing about a document's lifecycle, permissions, or relationships is ever inferable only from a file on disk or in a bucket (§15).
3. **Reference, never duplicate.** A controlled document exists in exactly one place (the Knowledge Base); a piece of equipment exists in exactly one place (the Equipment Library). Every project, generated document, or quality record that needs either links to it — it is never copied, never re-entered, never forked. This is already validated practice in the current build (Equipment's `equipment_documents` link table) and is elevated here to a platform-wide rule spanning both document content and equipment identity (§9, §10, §12).
4. **Every write is attributable and reconstructable.** Who did what, when, from where, and to which prior state is captured for every record that matters to a regulator, without exception, from v1.0 — not bolted on when a customer asks for it (§17).
5. **The platform is boring in the middle and rigorous at the edges.** Business logic (document generation, workflow state machines) can evolve quickly. The tenancy, storage, identity, and audit layers must not — they are the load-bearing walls (§6, §15, §16, §17).
6. **Build for thousands of tenants, not for one large customer.** Every design decision is evaluated against "does this work unmodified for company #4,000," not "does this work for our first pilot customer." This rules out per-tenant databases, per-tenant schemas, and per-tenant code branches (§6).
7. **No feature ships without knowing what regulatory posture it affects.** This platform's customers operate under FDA, EMA, MHRA, WHO-GMP, CDSCO, and TGA oversight. A feature that looks like a UX nicety (e.g., editing a submitted record) can be a compliance violation. Regulatory impact is a first-class review criterion (§16, §17, §18).
8. **Prefer managed primitives over custom infrastructure.** Supabase Auth over a hand-rolled auth system, Supabase Storage over a self-managed object store, PostgreSQL RLS over application-only access checks, Postgres full-text search over a bolted-on search cluster until scale genuinely demands one. A 30-person engineering org does not out-build the primitives a managed platform gives for free, and every hand-rolled equivalent is a future incident (§6, §13, §14, §16).

---

## 3. System Architecture

PharmaGPT is a three-tier architecture: a Flask monolith serving both the application UI and its API, a managed PostgreSQL database for all structured data, and managed object storage for all file content. There is deliberately no microservice split at v1.0 (see §24 for when that changes).

```
                         ┌─────────────────────────────┐
                         │        Browser Client        │
                         │   (server-rendered + JS)     │
                         └───────────────┬───────────────┘
                                         │ HTTPS
                         ┌───────────────▼───────────────┐
                         │      Render Web Service        │
                         │   Flask application (monolith) │
                         │  ─────────────────────────────│
                         │  Auth & session middleware     │
                         │  Tenant-context resolver        │
                         │  Domain modules (blueprints):   │
                         │   Company · User · Project ·    │
                         │   Knowledge Base · Equipment     │
                         │   Library · Validation · QMS ·   │
                         │   AI Engine · Search             │
                         │  Audit trail writer              │
                         │  (Integrations: reserved, §25 —  │
                         │   no module ships at v1.0)       │
                         └──────┬───────────────┬─────────┘
                                │               │
                 SQL (pooled)   │               │  Signed URLs / Storage API
                                │               │
                  ┌─────────────▼───┐   ┌───────▼─────────────┐
                  │ Supabase         │   │ Supabase Storage     │
                  │ PostgreSQL       │   │ (private buckets,    │
                  │  - Row-Level     │   │  per-company paths)  │
                  │    Security      │   │                      │
                  │  - All app       │   │  DOCX / PDF / images │
                  │    tables        │   │  / annexures         │
                  │  - Full-text     │   │                      │
                  │    search index  │   │                      │
                  └─────────────────┘   └──────────────────────┘
                                │
                  ┌─────────────▼───┐
                  │ Supabase Auth    │
                  │ (identity, JWT,  │
                  │  MFA)            │
                  └──────────────────┘

                         ┌───────────────────────┐
                         │   AI Provider(s)        │
                         │  (LLM for generation,   │
                         │   embeddings for RAG     │
                         │   and semantic search)   │
                         │  called server-side      │
                         │  from Render only         │
                         └───────────────────────┘
```

**Why a monolith and not microservices at v1.0:** the team size, deployment cadence, and current transaction volume do not justify the operational tax of distributed systems (service discovery, distributed tracing, network-partition handling). A well-modularized monolith with clean internal boundaries (blueprint-per-domain, service-layer separation already established in the current codebase) gets 90% of the maintainability benefit of microservices at a fraction of the operational cost, and it is the same pattern every mature SaaS company ships before it splits services out from real, measured bottlenecks — not anticipated ones.

---

## 4. High-Level Architecture Diagram

The diagram in §3 shows the runtime topology. The diagram below shows the **tenant data shape** — the conceptual model every future feature must fit into. It is organized around seven company-level pillars, each a first-class platform entity in its own right (not a sub-feature of another):

```
PharmaGPT Platform
│
├── Super Admin (platform-level, not tenant-scoped)
│     └── creates / suspends / deletes Companies
│
└── Company  (tenant boundary — everything below is isolated per company)
      │
      ├── Users  (Company Admin, Reviewer/QA, User)
      │     └── Role assignments, Project memberships
      │
      ├── Projects  (many per company)
      │     ├── URS / DQ / FAT / SAT / IQ / OQ / PQ
      │     ├── Validation Reports
      │     ├── Risk Assessments
      │     ├── Deviations / CAPA / Change Controls
      │     ├── References into Equipment Library     (never a copy, §10)
      │     └── References into Knowledge Base         (never a copy, §9)
      │
      ├── Knowledge Base  (ONE per company, centralized, §9)
      │     └── SOPs, Vendor Documents, Specifications, Drawings,
      │         Validation Templates, Regulatory Documents,
      │         Company Standards
      │
      ├── Equipment Library  (ONE per company, centralized — §10)
      │     └── Equipment master records — referenced, not owned, by every
      │         Project and every document type that concerns that
      │         equipment (URS/DQ/FAT/SAT/IQ/OQ/PQ, SOP, Validation
      │         Reports, Risk Assessments, Calibration, Preventive
      │         Maintenance, Vendor Documents, Spare Parts, Change
      │         Controls, Deviations, CAPA)
      │
      ├── AI Workspace  (per company — §13)
      │     └── Generation service, RAG retrieval, conversations, and the
      │         AI Usage Ledger — every AI action is tenant-scoped and
      │         logged
      │
      ├── Documents  (the unified document object model — §12, §14)
      │     └── Every controlled document, wherever it is authored
      │         (Knowledge Base, Project, or Equipment-linked), moves
      │         through one lifecycle (§12), one version model (§18), and
      │         one audit trail (§17). This unified model — not a fourth
      │         copy of the content living elsewhere — is what Global
      │         Search (§14) indexes across the whole company.
      │
      └── Audit Log  (per company, immutable, append-only, §17)
```

Every box under "Company" carries a `company_id`. There is no entity in the system, other than the platform-level Super Admin and Company records themselves, that does not belong to exactly one company. **"Documents" is deliberately not a third storage location alongside Knowledge Base and Equipment Library — it is the shared lifecycle/version/audit shape that content in every other box takes on**, consistent with Design Principle 3 (reference, never duplicate).

---

## 5. Database Architecture

**Engine:** Supabase PostgreSQL (managed Postgres 15+, with connection pooling via Supabase's built-in PgBouncer).

**Structural rules, binding on all future schema work:**

- **Every tenant-scoped table carries a `company_id` foreign key**, not nullable, indexed, and enforced by Row-Level Security (§6). This is not optional per-table judgment — it is the platform's single tenancy mechanism, and every table participates in it unless it is explicitly platform-global (Super Admin, Company registry, system configuration).
- **Metadata lives in Postgres; bytes live in Storage.** No table stores file content as a BLOB. Tables that reference a stored file hold a storage path/key, content type, size, and checksum — never the bytes.
- **Soft state, not destructive deletes, for anything with regulatory relevance.** Documents, records, and audit-relevant rows are never hard-deleted by user action; they move through Obsolete and Archived (§12) and are retained. Hard deletion is a Super Admin / data-retention-policy operation only, logged as such (§17).
- **Polymorphic shared tables over per-domain duplicates**, following the pattern already proven in the current codebase's QMS suite (`qms_audit_trail`, `qms_attachments`, `qms_comments`, `qms_approvals`, each keyed by `record_type` + `record_id`) and its Equipment-to-document linking (`equipment_documents`, `source_type` discriminator). Audit trail, comments, attachments, approvals, version history, and now equipment linkage are each a single shared table family across the whole platform, not one per document type. This is the single highest-leverage structural decision in this document: it is what lets thirty-plus document and record types (URS, DQ, IQ, OQ, PQ, CAPA, Deviation, Change Control, Calibration, Preventive Maintenance, and everything added after v1.0) share one audit engine, one approval engine, one attachment engine, and one equipment-linkage engine instead of thirty parallel, drifting implementations.
- **No cross-tenant foreign keys.** A row in Company A's schema space may never reference a row belonging to Company B. The one deliberate exception is the Knowledge Base template library the platform may ship pre-loaded (§9) — those are platform-owned reference rows a company can copy into its own Knowledge Base, never referenced live across the tenant boundary.
- **Migrations are code, reviewed, and reversible.** A managed migration tool (the specific tool is an implementation choice, not an architectural one) replaces the current build's "drop and recreate the dev database" approach the moment this platform has its first paying multi-tenant customer. There is no version of this platform where schema changes happen by hand against production.

---

## 6. Multi-Tenant Design

**Chosen model: shared database, shared schema, row-level isolation via `company_id` + PostgreSQL Row-Level Security (RLS).**

### The three options, and why this one

| Model | Description | Verdict |
|---|---|---|
| Database-per-tenant | Each company gets its own Postgres database/instance | **Rejected.** Does not operationally scale to "thousands of companies" — thousands of databases to patch, migrate, monitor, and back up individually. Connection pooling collapses. Cost scales linearly with tenant count regardless of tenant size. This is the model incumbents used when multi-tenant SaaS wasn't mature; it is not the model a new platform should choose in 2026. |
| Schema-per-tenant | One Postgres database, one schema per company | **Rejected.** Better than database-per-tenant but still fails at scale: Postgres has practical and operational limits well below "thousands" of schemas per database (catalog bloat, migration tooling that must iterate every schema, connection-pooler awkwardness). It also doesn't meaningfully improve isolation over RLS while costing significantly more operational complexity. |
| **Shared schema + RLS (chosen)** | One database, one set of tables, every tenant-scoped row carries `company_id`, Postgres RLS policies enforce that a session can only see/write rows matching its authenticated company | **Chosen.** Scales to any number of tenants on infrastructure that does not grow linearly with tenant count. Isolation is enforced at the database engine level — not just in application code — so a bug in a Flask route cannot leak cross-tenant data; the database itself refuses the query. This is the native pattern Supabase is built around, meaning it is a supported, well-trodden path rather than something fought against the platform. |

### How isolation is actually enforced

Tenant isolation is a two-layer guarantee, not one:

1. **Application layer:** every authenticated session resolves to exactly one `company_id` (from the user's identity, never from client-supplied input) and every query the application issues is implicitly scoped to it.
2. **Database layer (the layer that actually matters for a security incident):** RLS policies on every tenant-scoped table enforce `company_id = current_company()` regardless of what the application layer does or fails to do. A SQL injection, an application bug, or a forgotten `WHERE` clause still cannot return another company's rows, because the database rejects it independent of application logic.

Layer 2 is what makes this defensible to an enterprise security review and to an FDA-regulated customer's vendor audit. Layer 1 alone — "the application always filters by company" — is the standard that gets multi-tenant SaaS companies breached. This platform does not ship on Layer 1 alone, ever.

### Noisy-neighbor and blast-radius containment

A shared database means one company's usage spike can, in principle, affect another's performance. This is accepted and mitigated, not avoided: connection pooling caps concurrent load, slow-query monitoring is per-tenant attributable (every query is taggable by `company_id` in logs), and the AI Usage Ledger (§13) gives the platform the hooks to rate-limit a specific tenant without a code deploy. A tenant that is a genuine outlier (regulatory requirement for physical data segregation, unusual scale) is the documented escape hatch to a dedicated database — an exception process, not the default architecture.

---

## 7. User & Permission Model

### Roles (frozen — four roles, platform-wide, no per-company custom roles at v1.0)

| Role | Scope | Can do |
|---|---|---|
| **Super Admin** | Platform-wide, not tied to any company | Create, suspend, and delete Companies. Create the first Company Admin for a new company. View platform-level usage/billing. Cannot see a company's Knowledge Base, Equipment Library, or Project content by default (see below) — administrative access to tenant content is an explicit, logged, time-boxed break-glass action, not a standing privilege. |
| **Company Admin** | One company | Full control within their company: invite/deactivate Users, assign roles, manage the Knowledge Base and Equipment Library, create/archive Projects, configure company-level settings, view the company's full audit trail. |
| **Reviewer / QA** | One company, project- and KB-scoped by assignment | Review and approve/reject documents routed to them (URS, validation protocols, deviations, CAPA, change controls) at both the In Review and QA Review stages (§12). Cannot author new Projects or manage users. This role is the electronic-signature actor once e-signature ships (§18). |
| **User** | One company, project-scoped by assignment | Author and edit documents within Projects they are a member of. Read access to the company Knowledge Base and Equipment Library. Cannot approve their own submissions (segregation of duties, enforced at the workflow level, not just the UI). |

**Why four fixed roles and not a granular permission-builder:** a permission-builder (custom roles with checkbox-level capability grants) is what enterprise platforms eventually need, and it is explicitly deferred (§31). At v1.0, four roles that map directly onto how a quality organization already operates (someone who administers, someone who does the work, someone who reviews it, someone who runs the company) cover the real-world org chart of every target customer segment without the implementation and QA cost of a general-purpose permission engine. This is revisited when a customer's org structure genuinely doesn't fit four roles — not preemptively.

**Segregation of duties is architectural, not conventional.** The same user account cannot author and approve the same record. This is enforced in the workflow state machine (§12, §18), not left as a process suggestion. The lifecycle's two-stage review (In Review, then a separate QA Review — §12) gives this principle a structural home rather than relying on a single reviewer's discipline.

### No public signup

Company Admin accounts are provisioned exclusively by Super Admin. There is no self-service "create your company" flow at v1.0 (§31). This is a deliberate sales and compliance posture: every tenant on the platform is a known, vetted enterprise customer, not an anonymous signup, which matters both commercially (this is an enterprise sale, not PLG) and from a compliance standpoint (every company's regulatory identity is verified before they can store GxP records on the platform).

---

## 8. Company Workspace Architecture

A **Company** is the tenant root. Every Company record carries, at minimum: legal name, industry segment (Pharma / Nutraceutical / Medical Device / Biotech / CDMO / CRO), subscription/plan tier, status (active/suspended), and the `company_id` that every downstream table hangs off.

The Company Workspace — what a Company Admin sees when they administer their tenant — is a distinct surface from the Project Workspace (§11). It is where company-level, cross-project concerns live:

- **User management:** invite, deactivate, reassign roles, view login/session history.
- **Knowledge Base administration:** the centralized document library (§9).
- **Equipment Library administration:** the centralized equipment master list (§10).
- **Project directory:** the list of all Projects belonging to the company, with cross-project status visibility (a Company Admin can see every project; a User only sees projects they're a member of).
- **Company-level Audit Trail:** every action taken by any user in the company, filterable by user/date/record type (§17).
- **AI Usage:** the company's AI consumption against plan limits (§13).
- **Search:** the entry point to Global Search (§14), scoped to everything the signed-in user is authorized to see.

A company never sees, references, or is discoverable by another company. There is no cross-company directory, no shared "community" Knowledge Base or Equipment Library content visible by default, and no way for a Company Admin of one tenant to enumerate other tenants' existence.

---

## 9. Knowledge Base Architecture

**Frozen decision, restated and formalized:** the Knowledge Base is not inside Projects. Each Company owns exactly one centralized Knowledge Base.

### What it holds

Controlled, reusable documents: SOPs, Vendor Documents, Specifications, Drawings, Validation Templates, Regulatory Documents, Company Standards. (Equipment Manuals, previously listed here, now belong conceptually to the Equipment Library, §10 — see that section for how equipment-related documents are organized; the underlying "store the file once, link to it" mechanism is unchanged.)

### Why centralization, not per-project libraries

The alternative — each Project keeps its own copy of the SOPs and manuals it needs — is how paper-based and early digital QMS systems worked, and it is the single biggest source of controlled-document drift in regulated industries: SOP v3 gets updated company-wide, and eleven projects are still silently referencing v2 because nobody re-uploaded it eleven times. Centralizing means an SOP update is one write, and every Project that references it sees the update (or is flagged that the version it cited has since changed — see §18 versioning behavior for referenced documents). This is the same principle already validated in the current codebase's Equipment-to-document linking (`equipment_documents`, "link, don't copy") — elevated here from one feature's pattern to the platform's document law (Design Principle 3).

### How Projects use it

A Project never stores a copy of a Knowledge Base document. It stores a **reference** — a link to a specific Knowledge Base document, at a specific version, for a specific purpose (e.g., "this OQ protocol cites SOP-QA-014 v2 as its reference procedure"). The reference resolves live to the current Knowledge Base record for display, while the version pinned at time of use is preserved for audit purposes — so a report generated in March can be reproduced exactly as it was generated, even if the underlying SOP has since moved to v3.

### Structure

Folder/category taxonomy (SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others — as already validated in the current build) plus metadata: title, tags, version, effective date, review date, owner, approval status. Full-text search across the company's Knowledge Base is a platform primitive delivered through Global Search (§14), not a per-feature reimplementation; semantic search arrives in v1.1 through the same mechanism.

### Platform-seeded content

The platform may offer a starter library of generic, non-company-specific templates (a blank IQ protocol template, a generic FMEA template) that a new company can copy into their own Knowledge Base at onboarding. This is the one deliberate case of platform-owned reference content (§5) — companies copy it in as their own, editable record; they never reference it live, and Company A's copy is fully independent of Company B's.

---

## 10. Equipment Library Architecture

**New platform-wide rule, frozen at this revision:** the Equipment Library is company-wide, not project-specific. Each Company owns exactly one centralized Equipment Library, structurally parallel to the Knowledge Base (§9) and to the same "reference, never duplicate" law (Design Principle 3).

### Why this changes the current build's model, explicitly

The current shipped single-tenant build owns Equipment at the Project level (`FOUNDATION_ARCHITECTURE.md` §2.2: `project_id NOT NULL ON DELETE CASCADE` — equipment belongs to exactly one Project, and is deleted if that Project is). That was the right call for a single-project-at-a-time build. It is the wrong shape for a platform where the same physical asset — an HPLC unit, an autoclave, a filling line — is qualified once, then referenced by every subsequent project that touches it over its operational life: a periodic requalification project, a change-control-triggered revalidation, a deviation investigation, a CAPA. A project-owned equipment record forces the same equipment to be re-entered (or copy-pasted, drifting immediately) every time a new project needs it — precisely the failure mode Design Principle 3 exists to prevent. Elevating Equipment to a company-owned, centrally referenced entity is therefore not a stylistic preference; it is the same correction, applied to equipment identity, that centralizing the Knowledge Base already applied to document content.

### What it holds

One master record per physical equipment/system, carrying the same field groups already validated in the current build's `equipment` table — Basic Information (equipment code, name, category, equipment type, tag number, model, manufacturer, vendor, serial number, asset number), Installation Information (plant, block, department, area, room, line, installation date, commissioning date), and Qualification Information (qualification status, validation status, qualification type, criticality, GMP impact) — now scoped by `company_id` rather than `project_id`.

### The central-object rule

Equipment is the hub every other record type spokes off of. The following are architected to reference an Equipment Library record by `equipment_id` (a direct foreign key where the relationship is inherently one equipment record to many child records, or a polymorphic link — the same `record_type`/`record_id` pattern used elsewhere, §5 — where the relationship is many-to-many):

- URS, DQ, FAT, SAT, IQ, OQ, PQ
- SOP (via the Knowledge Base's equipment-linkage, mirroring the current build's `equipment_documents` pattern)
- Validation Reports
- Risk Assessments
- Calibration
- Preventive Maintenance
- Vendor Documents
- Spare Parts
- Change Controls
- Deviations
- CAPA

Calibration, Preventive Maintenance, and Spare Parts do not exist as tables in the current build (`FOUNDATION_ARCHITECTURE.md` §2.2 already flagged them as architecture-only, future FKs against `equipment.id`). This document confirms that plan at the platform level: when built, each is a table that references the Equipment Library, never a re-derivation of equipment identity inside its own domain.

### Relationship to Projects

A Project references one or more Equipment Library records; a single Equipment Library record can be referenced by multiple Projects across its lifetime (initial qualification, later periodic revalidation, a deviation investigation project, and so on). This many-to-many shape is the structural change from the current build's one-to-many ownership, called out in the revision note at the top of this document and logged as PA-013 (§33). Equipment never belongs to a Project; it is always merely referenced by one, exactly like a Knowledge Base document (§9).

### Access control

Equipment Library records follow the company-wide RBAC model (§7): visible to every User in the company (equipment is a shared company asset, not project-membership-gated the way Project-generated documents are), editable by Company Admins and by Users/Reviewers explicitly granted equipment-management capability. Every change to an Equipment Library record's qualification/validation status is audit-logged (§17) — this is what lets multiple concurrent projects referencing the same equipment see a single, consistent, attributable status rather than a fragmented per-project view.

### Documents about equipment

Equipment manuals, vendor documents, and drawings are not stored inside the Equipment Library as file content — they live in the Knowledge Base (§9) or as Project-generated documents, and the Equipment Library links to them via the same polymorphic `equipment_documents`-style table already proven in the current build (`source_type ∈ {kb, project}`). The Equipment Library is a hub of references, not a second file store.

---

## 11. Project Workspace Architecture

A **Project** is a validation or quality engagement: a piece of equipment being qualified, a system being validated, a study being run. It belongs to exactly one Company and can be shared among multiple Users of that company via role-based project membership (a User is only a member of the Projects they're assigned to; a Company Admin implicitly sees all).

### What lives in a Project

URS, DQ, FAT, SAT, IQ, OQ, PQ, Validation Reports, Risk Assessments, Deviations, CAPA, Change Controls, plus references to the Equipment Library record(s) the project concerns (§10) and the Project's own audit trail. A Project generates and owns its own documents; it never owns the equipment those documents concern.

### The generated-vs-reusable boundary

This is the organizing rule spanning §9, §10, and this section: **documents and records a Project produces belong to the Project. Content a Project consults — controlled documents or equipment identity — is always a reference into the Knowledge Base or the Equipment Library, never a copy.** An IQ protocol drafted for a specific piece of equipment is a Project artifact; the SOP that protocol cites and the equipment record it qualifies are both referenced, not duplicated. This boundary is what keeps the Knowledge Base and Equipment Library from becoming cluttered with one-off, drifting copies, and keeps Projects from silently forking controlled content or equipment identity.

### Project membership and access

Project-level access is role-scoped, not all-or-nothing: a User can be a project contributor without being a Reviewer on that project's records, and a Reviewer can be assigned to review specific document types within a project without being a general project member. This mirrors how real validation teams are structured (a validation engineer authors, a QA reviewer approves, and they are frequently not the same access level even within one project).

### Workspace shape

Consistent with the "one entity, one workspace" navigation principle already proven in the current codebase (`FOUNDATION_ARCHITECTURE.md` §3), a Project is a single workspace with tabbed access to its Overview, Equipment (the Equipment Library records referenced by this project, §10, with drill-through to the full Equipment Library profile), Documents, Risk Assessment, Qualification (IQ/OQ/PQ), Validation Reports, Deviations/CAPA/Change Control, Team (membership/roles), and History (audit trail) — not a scattering of separate top-level navigation items per document type.

---

## 12. Document Lifecycle

Every controlled document in the system — whether a Knowledge Base document, a Project-generated record, or an Equipment Library-linked document — moves through the same six-state lifecycle. One state machine, reused everywhere, is what makes the audit trail (§17) and version control (§18) engines universal instead of per-document-type reimplementations, and what gives the "Documents" object model in §4 a concrete, shared shape.

```
  Draft ──► In Review ──► QA Review ──► Approved ──► Obsolete ──► Archived
    ▲            │              │
    │            ▼              ▼
    └── Revision Requested (returns to Draft; reason mandatory) ──┘

  Withdrawn (special case): Draft or In Review/QA Review ──► Obsolete directly,
  bypassing Approved, always with a mandatory logged reason.
```

- **Draft:** author-editable, not visible outside the authoring team, no audit-trail-significant state yet beyond edit history.
- **In Review:** first-pass technical review, routed to an assigned Reviewer/QA user; edits by the original author are locked (a new draft revision is required to change content mid-review — this is what prevents "the reviewer approved something different from what they saw"). A reviewer may return the document to Draft with a mandatory reason (**Revision Requested**).
- **QA Review:** a distinct, second-stage quality/compliance gate, separate from the technical review in In Review. This split is what gives segregation of duties (§7) a structural home rather than relying on one reviewer's discipline — the person who checks technical correctness need not be the person who signs off on compliance. QA Review may also return the document to Draft with a mandatory reason.
- **Approved:** QA sign-off recorded (electronic signature manifestation, §18); content is now immutable and is the current, in-force version — this is the state Knowledge Base and Equipment Library references resolve to by default. A document may carry a future-dated `effective_date` as an attribute of the Approved record (e.g., an SOP approved today but effective next Monday); this is a scheduling detail on the Approved state, not a separate lifecycle state.
- **Obsolete:** a newer Approved version now exists, or the document has been manually retired (project closure, deviation, explicit withdrawal). Retained, read-only, fully auditable, and still visible in Global Search (§14) by default.
- **Archived:** past the active retention/reference window under the company's data-retention policy (§26, §31). Moved to long-term retention; excluded from default Global Search results but never deleted, and always retrievable by Company Admin or in response to an audit/regulatory request.

**AI-generated documents must always start in Draft state and can never transition to Approved without passing through both In Review and QA Review — the same two human review gates as any other document, with no shortcut.** This is restated here, not only in §13, because it is a lifecycle rule, not an AI Engine implementation detail: the constraint belongs to the state machine every document obeys, and it applies identically regardless of who or what authored the Draft.

No state transition is silent. Every transition writes an audit trail entry (§17) with actor, timestamp, prior state, new state, and (where applicable) reason.

---

## 13. AI Engine Architecture

The AI Engine is the layer that drafts documents, answers questions against company content (RAG), and assists reviewers — it is a service the rest of the platform calls, not a feature embedded ad hoc in each module.

### Structure

- **Generation service:** takes a document type, structured inputs (Equipment Library data via reference, §10, project context), and Knowledge Base references, and produces a draft via an LLM call, using the pharmaceutical-domain system prompt already established in the current codebase.
- **Retrieval service (RAG):** company-scoped retrieval over the Knowledge Base, Equipment Library, and Project documents. Retrieval is tenant-scoped at the same enforcement layer as everything else (§6) — a retrieval query can never surface another company's content, embeddings included. The embeddings this service generates are the same embeddings Global Search's semantic mode reuses (§14) — one embedding pipeline, two consumers, not two pipelines.
- **AI Usage Ledger:** every AI call (generation or retrieval) is logged with `company_id`, user, tokens/cost, and purpose. This is both a cost-accounting primitive (billing, plan limits) and a compliance primitive (a regulator or customer can ask "which parts of this document were AI-drafted, from what sources, and when").

### Provider abstraction

The AI Engine calls a provider interface, not a specific vendor SDK directly from business logic. This is not "build for multi-provider on day one" over-engineering — it is the minimum insulation needed so that a provider pricing change, rate limit, or outage is a configuration change, not a rewrite. Model/provider selection itself remains a single configured choice at any given time.

### AI content is never authoritative on its own

An AI-generated draft is always created in **Draft** state (§12). Nothing the AI produces reaches Approved without passing through In Review and QA Review — the same human review and electronic-signature workflow as any other document, with no AI-specific fast path. This is both a regulatory necessity (an FDA-regulated customer cannot ship an AI-authored, AI-approved validation record) and a product trust necessity.

---

## 14. Global Search Architecture

A single, company-scoped search surface across every searchable domain: Projects, Equipment Library, Knowledge Base, Documents (the unified object model, §4/§12), SOPs and Regulations (both Knowledge Base categories), AI Conversations, and Validation Records (URS/DQ/FAT/SAT/IQ/OQ/PQ/Validation Reports). One search box, one relevance model, reused everywhere — not a separate per-module search box repeated seven times.

### Why unified, and why Postgres full-text at v1.0

The alternative — each module (Projects, Knowledge Base, Equipment Library, AI conversation history) ships its own local search — is how the current single-tenant build works today, and it is the search equivalent of the document-duplication problem Design Principle 3 exists to prevent: a user has to know which module a piece of information lives in before they can look for it. A unified index removes that burden.

At v1.0 scale, that unified index is built on **Postgres full-text search** (a denormalized, company-scoped index — title, type, tags, extracted text snippet, `company_id`, `record_type`, `record_id` — kept current from the same write paths that already update each domain's tables) rather than a dedicated search cluster. This is the "prefer managed primitives" choice (Design Principle 8): the platform already runs Postgres, and Postgres full-text search comfortably covers keyword search at the tenant and document volumes v1.0 targets, without standing up and operating a second data store whose consistency with the system of record then has to be separately guaranteed.

### Indexing strategy

- **Structured metadata (titles, tags, record type, status) is indexed synchronously** — the moment a record is created or updated, its search-index entry is current, because both writes happen in the same transaction.
- **Extracted document text and (from v1.1) embeddings are indexed asynchronously**, consistent with the current build's proven pattern that upload/creation never fails or blocks on downstream processing — an indexing failure degrades search recall for that one document, never the write path.
- **The source of truth is always the domain table, never the search index.** The index is a derived, rebuildable projection (Design Principle 2) — it can be dropped and regenerated from the domain tables at any time without data loss.

### Semantic search (v1.1)

Semantic/AI-ranked search is a v1.1 capability (§32) built on embeddings the AI Engine's RAG retrieval service already generates for generation and Q&A (§13) — reused, not reimplemented, for search ranking. Keyword (full-text) and semantic search coexist; semantic mode augments relevance ranking, it does not replace the full-text index as the base layer.

### Authorization, not just tenancy

Search enforces the same two-layer model as every other read path (§6, §7): results are filtered first by `company_id` (RLS), then by the requesting user's actual authorization to the specific record (project membership, role scope). Search is a read path through the platform's existing authorization layer — never a parallel path that could surface a record a direct lookup would have denied.

### Lifecycle-aware results

Archived documents (§12) are excluded from default search results (they're still in the system, just past their active-reference window) and surfaced only via an explicit "include archived" filter — keeping default results focused on current, effective content while never actually hiding anything from an authorized user who asks for it.

### Beyond v1.0

If index volume or query latency ever outgrows Postgres full-text search, a dedicated search/vector database is the designed next step (§24) — an additive service sitting behind the same search API and authorization layer described here, not a rewrite of every feature that calls search.

---

## 15. Storage Strategy

**Files (DOCX, PDF, images, annexures) live in Supabase Storage. Metadata lives in PostgreSQL. Render's local filesystem is never a source of truth for anything, under any circumstance.**

This closes the exact failure mode already documented as a known risk in the current build (`DATABASE.md`: SQLite on Render's ephemeral filesystem is wiped on every restart/redeploy without a mounted disk). The platform architecture eliminates the failure mode entirely rather than working around it with a mounted disk band-aid: Render web instances are treated as fully stateless and disposable. A Render redeploy, restart, or horizontal scale-out event has zero effect on stored data, because none of it was ever there.

### Bucket and path strategy

- **Private buckets only.** No PharmaGPT storage bucket is public. All access is via short-lived signed URLs issued by the application after an authorization check.
- **Path convention encodes tenant boundary:** every object's storage path is prefixed by `company_id`, so tenant isolation is visible and enforceable at the storage layer too, not just the database layer — a second, independent line of defense consistent with Design Principle 1.
- **Immutability of approved content:** once a document reaches Approved (§12), its stored file is never overwritten. A revision is a new object at a new path/version; the old object is retained for exactly as long as the record retention policy requires.

### What is never stored in Postgres

Row content limits in Postgres make this a hard rule, not just a preference: no file bytes, no large binary blobs. The database holds the path, checksum, size, content-type, and version pointer; Storage holds the bytes.

---

## 16. Security Architecture

Security is layered — no single control is trusted alone, consistent with Design Principle 5.

| Layer | Control |
|---|---|
| **Identity** | Supabase Auth (managed identity provider): email/password plus MFA support, JWT-based sessions. No custom-built password storage or session mechanism — this is exactly the class of infrastructure Design Principle 8 says not to hand-roll. |
| **Authorization** | Role checks in application middleware (§7) as the first gate, PostgreSQL RLS as the enforced gate (§6) that holds even if the application layer has a bug. |
| **Transport** | HTTPS everywhere, enforced at the Render edge. No plaintext HTTP path exists in any environment, including internal calls to Supabase. |
| **Storage access** | Private buckets, signed URLs with short expiry, no direct public bucket access ever (§15). |
| **Secrets** | API keys, database credentials, and AI provider keys live in Render's environment/secret store, never in source control, never in a table. |
| **Audit** | Every state-changing action is logged, tenant-scoped, immutable (§17). |
| **Data at rest** | Encrypted at rest by the managed platforms (Supabase Postgres and Storage both encrypt at rest by default) — not a custom encryption layer the application maintains. |
| **Electronic signature (future)** | Architected for from v1.0 (approval actor, timestamp, and reason captured on every Approved transition, §12) even though a cryptographically binding e-signature is a v1.1+ capability (§18, §31). |

**RBAC and RLS are the same policy expressed twice, deliberately.** The role model in §7 and the RLS policies in §6 must never drift apart — a role capability that exists in application code but isn't backed by a matching RLS policy is a defect, not an acceptable gap, because it means the safety net (§6, Layer 2) doesn't actually cover that capability. The same applies to Global Search (§14): a search result is not a new authorization surface, so it must never expose more than a direct record lookup would.

---

## 17. Audit Trail Strategy

**One polymorphic, append-only audit trail table family, shared platform-wide**, following the pattern already proven in the current codebase (`qms_audit_trail`, keyed by `record_type` + `record_id`) — elevated here to cover every auditable entity on the platform, including the Equipment Library (§10), not just the QMS suite.

### What every entry captures

Company, actor (user), action (create/update/state-transition/delete-request/view-of-sensitive-record where applicable), record type, record ID, timestamp, prior-state snapshot (for updates and transitions), and reason (mandatory for revision requests, withdrawals, and any correction to an Approved record).

### Properties, non-negotiable

- **Append-only.** No application code path updates or deletes an audit trail row. Ever.
- **Tenant-scoped, same RLS enforcement as every other table** (§6) — a company can see its own audit trail in full, never another's.
- **Independent of the record it describes.** If a Project is archived, its audit trail survives — audit history is never cascade-deleted with its subject.
- **Covers reads, not only writes, for sensitive record types.** Viewing an approved regulatory document, an Equipment Library record, or another user's account details is itself logged where the customer's compliance posture requires it (configurable by record type, default-on for anything in Approved state and beyond — Approved, Obsolete, or Archived).

### Why one shared table family and not one audit table per module

Thirty-plus document and record types with as many separate audit implementations is thirty-plus places for the audit logic to drift, thirty-plus things to test, and thirty-plus things to get right under regulatory scrutiny. One audit engine, reused everywhere, is auditable itself — a customer's auditor can be shown one mechanism and trust it covers the whole platform, rather than needing to verify thirty-plus.

---

## 18. Version Control Strategy

Every document that reaches In Review (§12) is versioned from that point forward. Draft edits before first review are not separately versioned (that would version every keystroke); the meaningful version boundary is "this was submitted for review."

### Model

Each version is an immutable snapshot: content (or content pointer, per §15), the metadata that produced it (form inputs, Knowledge Base and Equipment Library references pinned at that version's creation time), author, and lifecycle state at time of snapshot. The "current" version is a pointer, never an in-place edit of a prior version's row.

### Referenced-document version pinning

When a Project document cites a Knowledge Base document (§9) or an Equipment Library record (§10), the citation pins that record's version at time of citation. If the underlying record is later revised, the Project document's citation is flagged ("this reference has been updated since you cited it") rather than silently changing what the Project document points to — critical for reproducing exactly what a validation report asserted at the time it was approved.

### Electronic signature readiness (explicitly future, architected for now)

v1.0 captures the *manifestation* of approval (actor, role, timestamp, reason — §12, §16) but not a cryptographically binding electronic signature meeting the full 21 CFR Part 11 signature-manifestation and signature-linking requirements (typed name + meaning + biometric/credential binding at time of signing). That is a defined v1.1 capability (§31, §32). The schema and workflow are shaped so that adding true e-signature is additive — a new signature-event table linked to the existing approval action — not a redesign of the approval workflow itself.

---

## 19. API Design Principles

- **Resource-oriented REST**, versioned under a URL prefix (`/api/v1/...`), so a breaking API change ships as `/api/v2/...` alongside the old version rather than forcing simultaneous client/server upgrades.
- **Tenant scope is never a client-supplied parameter.** `company_id` is derived server-side from the authenticated session on every request. An API that accepted a client-supplied tenant ID would make tenant isolation a trust exercise instead of an enforced guarantee — this is a direct consequence of Design Principle 1 and §6.
- **Idempotent writes where the operation allows it**, particularly for anything AI-generation-triggered (a retried "generate document" request must not silently create two documents).
- **Errors are structured and never leak internals.** A permission-denied response looks identical whether a record doesn't exist or the user isn't authorized to see it — not revealing which, to avoid leaking the existence of another tenant's or another user's records.
- **Streaming endpoints (AI generation, chat) remain a first-class citizen**, not a special case bolted on — this is already a strength of the current build (SSE streaming) and is preserved as a platform capability, generalized across every AI-generation surface rather than reimplemented per feature.
- **Pagination and filtering are mandatory on every list and search endpoint from v1.0.** A platform designed for "thousands of companies, millions of documents" cannot retrofit pagination later — an unbounded list or search-results endpoint is a scalability defect the day it ships, not a future one.

---

## 20. Deployment Architecture

| Component | Platform | Notes |
|---|---|---|
| Application | Render (Web Service) | Flask app, stateless, horizontally scalable — no reliance on local disk or in-process memory for anything durable (§15; this also retires the current build's in-memory chat-history cache pattern as an architectural dead end for the multi-tenant platform — session/conversation state must live in Postgres, not process memory, so any instance can serve any request). |
| Database | Supabase PostgreSQL | Managed, pooled connections, automated backups (§29), RLS-enforced (§6), hosts the Global Search full-text index (§14). |
| File storage | Supabase Storage | Private buckets, signed URLs (§15). |
| Identity | Supabase Auth | Managed, MFA-capable (§16). |
| Source control | GitHub | Single repository, protected main branch, PR-based review required for anything touching tenancy, auth, or audit-trail code. |
| CI/CD | GitHub → Render auto-deploy on merge to main, with a required test-suite gate | No manual production deploys; no direct-to-production hotfixes that bypass the pipeline. |

### Environments

Three environments, not two: **Development** (local/individual), **Staging** (a real Supabase project, isolated from production, used for pre-release validation including migration dry-runs), and **Production**. Migrations are always exercised against Staging before Production. This is a change from the current build's "delete the dev database" migration model (§5) and is treated as mandatory infrastructure, not optional process, the moment real tenant data exists.

### Why Render + Supabase, and the trade-off being accepted

This combination was chosen for time-to-market and operational leverage: a small team gets managed Postgres, managed auth, managed storage, and managed compute without running any of it. The accepted trade-off is a degree of vendor coupling to Supabase's specific Postgres extensions (RLS policy syntax, Supabase Auth's JWT claim structure) — mitigated by the fact that both are built on open standards (plain PostgreSQL, standard JWT) rather than proprietary Supabase-only mechanisms, so a future migration off Supabase, if ever required, is a real project but not a rewrite.

---

## 21. Folder Structure

Organizational, not implementation-level — the principle each module below encodes is separation by business domain, not by technical layer, consistent with the one-domain-one-file convention already established in the current codebase (`FOUNDATION_ARCHITECTURE.md`, DEC-012 pattern):

```
pharmagpt/
├── app/
│   ├── auth/                — identity, session, tenant-context resolution
│   ├── companies/           — Super Admin company provisioning, company settings
│   ├── users/               — user management, roles, invitations
│   ├── projects/            — Project Workspace domain
│   ├── knowledge_base/      — centralized KB domain
│   ├── equipment_library/   — company-wide Equipment Library domain (§10)
│   ├── qms/                 — Deviations, CAPA, Change Control, Document Control
│   ├── validation/          — URS/DQ/FAT/SAT/IQ/OQ/PQ, Validation Reports
│   ├── ai_engine/           — generation service, retrieval/RAG, usage ledger
│   ├── search/               — unified index, full-text now, semantic-ready (§14)
│   ├── audit/                — shared audit trail engine
│   ├── integrations/         — reserved adapter boundary (§25); empty at v1.0
│   └── shared/                — cross-domain primitives: attachments, comments,
│                                approvals, versioning — the polymorphic tables (§5)
├── migrations/                 — versioned, reviewed schema changes
├── static/ & templates/        — presentation layer
├── tests/                       — mirrors app/ structure 1:1
└── docs/                        — this document and its siblings
```

Each domain module owns its own routes, service logic, and data-access functions. Cross-domain reuse happens through `shared/`, never by one domain module importing another domain module's internals directly — this is what keeps the monolith modular enough to split into services later (§24) if that ever becomes necessary. The `integrations/` directory exists in this structure from v1.0 specifically so that the first real integration (§25) has an obvious, pre-agreed home rather than being scattered into whichever domain module happens to need it first.

---

## 22. Naming Conventions

- **Tables:** `snake_case`, plural nouns (`companies`, `projects`, `knowledge_base_documents`, `equipment_library_records`), consistent with the current codebase's existing convention.
- **Foreign keys:** `<singular_table>_id` (`company_id`, `project_id`, `equipment_id`) — never abbreviated.
- **Shared/polymorphic tables:** prefixed to signal cross-domain scope (`audit_trail`, `attachments`, `approvals`, `equipment_links`), discriminated by a `record_type` column holding the owning domain's singular entity name (`'project'`, `'deviation'`, `'capa'`), matching the pattern already validated in the current codebase's QMS suite.
- **Enums / status fields:** lower_snake_case string values matching the lifecycle in §12 (`'in_review'`, `'qa_review'`, `'approved'`, `'obsolete'`, `'archived'`), never raw integers — a string status is self-documenting in every log line and every database query a support engineer runs at 2am.
- **API routes:** `/api/v1/<plural-resource>/<id>/<sub-resource>`, kebab-case in the URL, matching REST convention.
- **Files/modules:** one domain per file/module (§21), named after the domain, not after the feature that happened to create it.

---

## 23. Database Naming Standards

Extending §22 with the standards specific to schema design:

- Every table has a surrogate primary key (`id`), never a natural key, so identity is stable even if a business attribute (like a protocol number) is later corrected.
- Every tenant-scoped table's `company_id` is the **first** foreign key column by convention, both for schema readability and because it is the column every RLS policy and every index strategy centers on.
- Timestamps are `created_at` / `updated_at` on every table, plus lifecycle-specific timestamps where relevant (`approved_at`, `obsolete_at`, `archived_at`) rather than inferring lifecycle timing from the audit trail alone — the record itself should answer "when did this become Approved" without a join.
- Every foreign key has an explicit `ON DELETE` policy chosen deliberately per relationship (`CASCADE` for true sub-entities a parent fully owns, like a Project's own generated Validation Reports; `SET NULL` or `RESTRICT` for records that must survive their referenced parent's archival — Equipment Library records surviving a Project's archival, since equipment is company-owned and merely referenced, §10, or QMS records surviving Project archival) — never left to the database default, and never chosen without considering the audit-trail implication (§5, §17).
- Indexes are mandatory on every foreign key and every column used in an RLS policy predicate or a Global Search filter — an RLS-enforced platform that isn't indexed on its RLS predicate columns is a platform that silently gets slow as tenant count grows, which is precisely the scaling failure this architecture exists to avoid.

---

## 24. Future Scalability Plan

The architecture in this document is designed to absorb the following growth vectors without a structural rewrite:

1. **Tenant count growth (tens → thousands of companies):** handled by the shared-schema + RLS model (§6) — infrastructure scales with total load, not tenant count.
2. **Document volume growth (thousands → millions of documents):** handled by Storage being the content layer (§15, effectively unlimited object storage) and by the mandatory pagination/indexing standards (§19, §23) that keep query performance flat as row counts grow.
3. **Read-heavy scaling:** Postgres read replicas are the designed next step when a single primary's read load becomes the bottleneck — the RLS + `company_id` model requires no redesign to add replicas, since isolation logic lives in the query layer, which replicas inherit unchanged.
4. **Compute scaling:** the Render web tier is stateless by design (§15, §20), so horizontal scale-out (more instances) is a configuration change, not an architecture change.
5. **Caching layer (future, not v1.0):** a Redis (or equivalent) caching tier for Knowledge Base/Equipment Library reads and session data is the designed next addition once read latency, not throughput, becomes the constraint — deliberately deferred because premature caching is a correctness risk (stale controlled-document reads) before it's a performance win.
6. **Service extraction (future, conditional):** the AI Engine (§13) is the most likely first candidate to extract into its own deployable service if AI workload characteristics (burstiness, GPU/inference cost profile) diverge enough from the web tier's to justify independent scaling — the module boundary already drawn in §21 makes this an extraction, not a rewrite, when the time comes. This is explicitly not a v1.0 decision; it is what the monolith-first choice in §3 is designed to make cheap later rather than expensive never.
7. **Multi-region (future, conditional):** deferred until a customer's regulatory jurisdiction or latency requirement actually demands it (§31) — Supabase and Render both support multi-region expansion without requiring this document's core model (shared schema + RLS + Storage-for-bytes) to change.
8. **Search scaling (future, conditional):** if Global Search's Postgres full-text approach (§14) outgrows a single primary's capacity, a dedicated search/vector service is the designed next step — already anticipated in §14, not a surprise decision made under pressure.
9. **Integration load (future, conditional):** inbound event volume from future integrations (§25) is handled by the same async/queue-based ingestion pattern used elsewhere, keeping third-party system load and availability decoupled from the synchronous web request path.

---

## 25. Future Integration Architecture

This section reserves architecture — boundaries and extension points — for integrations the platform does not build at v1.0. **Nothing in this section is implemented now.** Its purpose is that when a customer requires one of these integrations, engineering has a pre-agreed place for it to go, instead of architecting it ad hoc under deal-closing pressure in a way that risks compromising tenant isolation or RBAC.

### Integration categories and their defined boundary

| System | What it would exchange with PharmaGPT | Boundary / extension point |
|---|---|---|
| **SAP / ERP** | Equipment master data, purchase/vendor records, asset numbers | An adapter that syncs *into* the Equipment Library (§10) and Vendor Document metadata via a defined, scheduled or event-driven sync contract. Reconciles identifiers (SAP asset number ↔ Equipment Library `asset_number`, already a field per §10) — it does not make PharmaGPT query SAP live inside a user-facing request, and PharmaGPT remains the system of record for GxP documentation regardless of what ERP a customer runs. |
| **TrackWise (or an incumbent QMS)** | Deviations, CAPA, Change Control records, for migration or federation | Import/export adapter at the QMS record level. An `external_system_id` column, nullable and unused at v1.0, is reserved on the Deviation/CAPA/Change Control tables now, specifically so this integration never requires a schema migration on live regulated-record tables later. |
| **LIMS** | Laboratory instrument/sample results feeding equipment calibration and qualification | Inbound event/webhook receiver: LIMS pushes results, PharmaGPT records them against the relevant Equipment Library record (§10). PharmaGPT never queries LIMS synchronously inside a request path — this keeps the platform's availability and latency independent of a third-party lab system's uptime. |
| **OPC/SCADA** | Real-time equipment/process data | Same inbound-event pattern as LIMS, via a message queue or scheduled batch ingester rather than a persistent live connection held open by the Flask monolith. This is explicitly the kind of workload that would justify the service extraction anticipated in §24 if it ever ships — not something bolted onto the web tier. |
| **Microsoft Entra ID (Azure AD)** | Enterprise identity federation | SSO/SAML or OIDC federation into Supabase Auth's existing JWT-based session model (§7, §16) — an additional login method for a customer's users, not a replacement for the tenant/role model in §7. This is the mechanism the SSO/SAML roadmap item already scheduled for v1.2 (§32) lands inside. |
| **Google Workspace** | Enterprise identity federation; document interop | Identity: same federation boundary as Entra ID, above. Document interop (e.g., linking a Google Doc as a Knowledge Base reference) is a lower-priority, clearly separate extension point — never a replacement for Supabase Storage as the system of record for controlled documents (§15). |
| **Microsoft 365** | Identity federation; Word/Excel document interop | Identity: same boundary as Entra ID. Document interop ("open in Word," "save to OneDrive") is scoped identically to Google Workspace's — an editing-convenience integration, never a second source of truth for a controlled document. |

### The shared extension-point pattern

Every integration in the table above, whenever it is eventually built, follows the same three rules:

1. **Lives in its own module boundary** (`integrations/`, §21) — never scattered as hooks inside `projects/`, `equipment_library/`, or any other domain module.
2. **Asynchronous by default** — webhook, event, or scheduled batch, not a synchronous call to a third-party system inside a user-facing request path. This keeps PharmaGPT's own availability and latency (§27) independent of every external system it might one day integrate with.
3. **Authenticates as a company-scoped service identity, never a platform-wide one** — an integration adapter is subject to exactly the same RLS (§6) and RBAC (§7) enforcement as a human user's session. No integration is ever granted cross-tenant or platform-wide data access as a matter of convenience.

---

## 26. Risks and Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Cross-tenant data leakage (application bug) | Catastrophic — regulatory and trust-ending | Two-layer enforcement, RLS as the layer that holds independent of application bugs (§6, §16). |
| Noisy-neighbor performance impact | Degraded experience for unrelated tenants | Per-tenant attributable monitoring, connection pooling limits, documented dedicated-database escape hatch for genuine outliers (§6). |
| Vendor lock-in to Supabase/Render | Migration cost if either platform becomes untenable | Both built on open standards (Postgres, JWT, S3-compatible storage semantics) — real migration effort, not a rewrite, if ever needed (§20). |
| Runaway AI cost from unbounded usage | Margin erosion, possible abuse | AI Usage Ledger (§13) gives per-tenant visibility and the enforcement hook for plan-based limits from v1.0, even if limits themselves are a plan/billing-layer decision (§31). |
| Audit trail or version data growing unbounded | Storage cost, query performance decay over years of operation | Append-only design is deliberate (§17) — mitigation is partitioning/archival strategy for cold audit data, not deleting it; a defined data-retention and archival policy is a required v1.x deliverable, not a v1.0 gap that's ignored. |
| Regulatory scrutiny of AI-authored content | Customer audit findings, regulatory rejection of AI-assisted records | AI content is never authoritative without human approval (§12, §13); every AI action is logged in the Usage Ledger with full provenance. |
| Single-region latency for a geographically distant customer | Poor UX for e.g. an APAC customer on a US-region deployment | Explicitly deferred, not solved, at v1.0 (§24, §31) — flagged here so it is a known, chosen trade-off rather than a surprise. |
| Team's operational unfamiliarity with RLS policy authorship | Misconfigured policy silently under- or over-restricts access | RLS policies are treated as security-critical code: required PR review, and RLS policy coverage is part of the definition of done for any new tenant-scoped table (§16, §22). |
| Equipment Library contention across concurrent projects (e.g., two active projects revalidating the same equipment) | Unclear source of truth for in-flight qualification status, confusing UX | Equipment master fields are Company-Admin/assigned-role editable, not project-editable; every status change is audit-logged per record (§17), so concurrent projects see one consistent, attributable equipment state instead of silently overwriting each other's view (§10). |
| Global Search surfacing content a user isn't authorized to see | Access-control bypass — the same severity class as cross-tenant leakage | Search enforces the same RLS + role-scoping as direct record access (§6, §7, §14); it is a read path through the existing authorization layer, never a parallel one. |
| A future integration (§25) becoming a backdoor around tenant isolation or RBAC | A compromised or misconfigured adapter exposing cross-tenant data | Every integration authenticates as a company-scoped service identity, enforced by the same RLS/RBAC as a human session (§6, §7, §25) — no integration is ever granted platform-wide access. |

---

## 27. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Availability** | Target 99.9% for the application tier in production (≈8.7 hours/year allowed downtime), bounded by Render and Supabase's own SLAs — the platform does not promise higher availability than its managed dependencies provide. |
| **Latency** | Interactive page/API/search responses: p95 under 500ms for non-AI operations. AI generation/streaming operations are exempt from this budget (bounded instead by provider response time) but must begin streaming visible output within 2 seconds of request. |
| **Data durability** | No acknowledged write is ever lost — guaranteed by Supabase's managed Postgres durability plus the backup strategy in §29. |
| **Tenant isolation** | Zero cross-tenant data exposure incidents — the only NFR in this table with a target of literally zero, because it is the one failure category with no acceptable partial-credit outcome. |
| **Auditability** | 100% of state-changing actions on regulated record types produce an audit trail entry — not "most," not "the ones we remembered." |
| **Scalability** | Architecture supports tenant count and document volume growth (§24) without structural redesign, verified by periodic load testing against realistic multi-tenant traffic patterns, not single-tenant benchmarks. |
| **Recoverability** | See §29 (RTO/RPO). |
| **Security** | No plaintext secrets in source control or logs; no unencrypted data at rest or in transit; RBAC/RLS parity maintained (§16) as an ongoing invariant, checked on every PR touching access control. |

---

## 28. Performance Strategy

- **Query performance is a schema-design responsibility, not an afterthought.** Indexing standards (§23) apply from the first migration that creates a table, not retrofitted once a table is slow.
- **N+1 query patterns are treated as defects.** A list endpoint that issues one query per row instead of one query for the page is not shipped, full stop — this matters disproportionately in a shared-database multi-tenant model because inefficient queries compound across every tenant sharing the database.
- **Pagination is mandatory** (§19) — the single highest-leverage performance rule at this scale, because it bounds the worst case of every list-shaped or search-shaped endpoint regardless of how large any one tenant's data grows.
- **AI latency is treated separately from application latency** (§27) — streaming output (already proven in the current build's SSE pattern) is the mitigation for AI operations' inherently higher latency, so perceived responsiveness doesn't wait on total generation time.
- **Search indexing is asynchronous where it would otherwise block a write** (§14) — structured metadata updates the index synchronously, but full-text extraction and (later) embeddings never hold up the user-facing write path.
- **Caching is deferred, not premature** (§24) — the platform optimizes for correctness of controlled-document and equipment reads first, and introduces caching only once profiling shows it's the actual bottleneck, with cache-invalidation rules that respect document versioning (§18) from the moment caching is introduced.
- **Load testing simulates realistic multi-tenant concurrency**, not a single large tenant in isolation — a scaling profile that only accounts for "the customer with the most data" misses the actual production shape of "many tenants concurrently, unevenly."

---

## 29. Backup & Disaster Recovery

- **Automated, continuous backups via Supabase's managed Postgres backup/PITR (point-in-time recovery) capability.** The platform relies on this managed capability rather than a custom backup pipeline (Design Principle 8) — one fewer piece of undifferentiated infrastructure the team builds and maintains.
- **Storage (Supabase Storage) durability** relies on the underlying object storage's redundancy guarantees — files are not additionally backed up to a second location at v1.0 unless a specific customer's regulatory posture requires it (tracked as a plan-tier / contractual capability, not a platform default).
- **Recovery targets:**
  - **RPO (Recovery Point Objective): under 5 minutes** for database state, consistent with continuous PITR backup.
  - **RTO (Recovery Time Objective): under 4 hours** for full platform restoration in a disaster scenario, driven primarily by Supabase project restoration time, not application-layer complexity (the application tier itself is stateless and redeploys in minutes, §20).
- **DR is tested, not assumed.** A documented, periodically executed restore drill (restoring a backup into Staging and verifying data integrity) is a required operational practice from the first paying tenant onward — a backup that has never been restored is not a verified backup.
- **Tenant-level recovery, not only platform-level:** because RLS and `company_id` scoping (§6) make a single tenant's data addressable independently, a single-company data-recovery request (e.g., a customer's accidental mass-deletion) is architecturally possible without a full-platform restore — this is a direct benefit of the shared-schema model over database-per-tenant, where the same operation would require restoring an entire dedicated database.

---

## 30. Development Standards

- **Every PR touching tenancy, auth, RLS policies, or the audit trail requires review from a second engineer**, no exceptions — this is the one class of code where "it worked in my testing" is not sufficient sign-off, given §27's zero-tolerance NFR on tenant isolation.
- **Tests mirror the domain structure (§21), 1:1.** A new domain module ships with its test module; there is no "we'll add tests later" for tenant-scoped or audit-relevant code paths.
- **Migrations are additive-first.** A schema change that can be done as an additive migration (new nullable column, new table) followed by a separate backfill/cutover step is preferred over a single destructive migration, to keep every deploy safely rollback-able.
- **No direct production database access for routine work.** Debugging and data fixes go through reviewed tooling or migrations, not ad hoc production SQL — this is both a safety practice and a tenant-isolation practice (a human running ad hoc SQL is a human who can bypass RLS if connected with elevated credentials).
- **Feature flags gate incomplete work, not half-shipped code paths left live.** Consistent with the "no half-finished implementations" standard this platform is held to at every layer.
- **Every new tenant-scoped table ships with its RLS policy in the same PR that creates the table** — never as a follow-up, per §16 and §26.
- **Any future code under `integrations/` (§25) meets the same PR-review, RLS, and audit-trail bar as core domain modules.** An adapter is not exempt from §6/§7 enforcement because it is external-facing — if anything, it warrants more scrutiny, not less.

---

## 31. Features Explicitly OUT OF SCOPE for v1.0

Stating what is deliberately not built is as important as stating what is. Each item below is a known future capability, not an oversight:

- **Public self-service company signup.** Super Admin provisioning only (§7).
- **Granular/custom permission builder.** Four fixed roles only (§7).
- **Cryptographically binding electronic signatures (full 21 CFR Part 11 signature manifestation).** Approval-actor capture ships now; true e-signature is v1.1+ (§18, §32).
- **SSO / SAML / enterprise identity federation.** Supabase Auth's native email/MFA only at v1.0; the federation boundary is defined (§25) but not built.
- **Billing, subscription management, and plan-tier enforcement UI.** The AI Usage Ledger (§13) provides the data hooks; billing itself is out of scope for this architecture document and this version.
- **Multi-region deployment.** Single-region at v1.0 (§24, §26).
- **Mobile native applications.** Web-only, responsive-capable but not a dedicated mobile app.
- **Offline mode / local-first sync.** Requires connectivity; no offline authoring or offline-first conflict resolution.
- **Cross-company benchmarking, analytics, or a marketplace of shared templates between tenants.** No cross-tenant data product exists at v1.0, consistent with the strict tenant-isolation posture (§6).
- **Redis/caching layer.** Deferred per §24 and §28 until profiling justifies it.
- **Microservice decomposition.** Monolith-first per §3 and §24.
- **Data-retention/archival automation for cold audit and version data.** The append-only requirement and the Obsolete/Archived states ship now (§12, §17, §26); automated archival tooling is a defined near-term follow-on, not a v1.0 deliverable.
- **Any live/synchronous connection to ERP, TrackWise, LIMS, OPC/SCADA, or an identity provider.** §25 defines the boundary only; no adapter is built or connected at v1.0.
- **Dedicated/vector search infrastructure.** v1.0 ships Postgres full-text search only (§14); a dedicated search service is a conditional future step (§24), not a v1.0 build.

---

## 32. Product Roadmap

| Release | Theme | Key capabilities |
|---|---|---|
| **v1.0 (this document)** | Multi-tenant SaaS foundation | Companies, RBAC (4 roles), centralized Knowledge Base, centralized Equipment Library (§10), Project Workspace, six-state document lifecycle + versioning (§12), platform-wide audit trail, Postgres full-text Global Search (§14), Supabase Postgres + Storage, AI generation with usage ledger, the `integrations/` extension boundary reserved but empty (§25). |
| **v1.1** | Compliance depth | Cryptographically binding electronic signatures (full 21 CFR Part 11 manifestation + signature linking), data-retention/archival policy automation, semantic (vector) search across Global Search reusing AI Engine embeddings (§14), per-tenant configurable AI usage limits enforced (not just logged), Calibration and Preventive Maintenance as real Equipment Library-linked modules (§10). |
| **v1.2** | Enterprise identity & commercial readiness | SSO/SAML federation into Supabase Auth (built on the boundary defined in §25), billing and plan-tier enforcement, custom/granular permission roles for large customers whose org structure outgrows the four fixed roles, expanded QMS modules (Audit Management, Supplier Quality, Training Management, Complaint Management — already architecturally anticipated by the polymorphic QMS pattern, §5, §17), first real integration adapters built against the §25 boundary (leading candidates: SAP/ERP equipment sync, Entra ID federation). |
| **v2.0** | Scale & platform maturity | Read replicas / caching layer as load demands (§24), dedicated search infrastructure if Postgres full-text search outgrows scale (§14, §24), AI Engine service extraction if warranted by measured load characteristics, LIMS/OPC-SCADA event ingestion, multi-region deployment for geographically distant enterprise customers, deeper AI copilot capabilities across the full document lifecycle (not just drafting — review assistance, gap analysis against cited regulations). |
| **Exploratory / unscheduled** | Longer-horizon bets | Mobile applications, cross-tenant benchmarking as an opt-in tenant-controlled product (not a default), NFC/RFID-linked Equipment Library records, BatchTrack-style CDMO inventory/project tracking. |

---

## 33. Final Frozen Architecture Decision Log

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| PA-001 | Multi-tenant via shared schema + `company_id` + PostgreSQL RLS, not database-per-tenant or schema-per-tenant | Only model that scales operationally to thousands of tenants on infrastructure that doesn't grow linearly with tenant count (§6) | Shared infrastructure means noisy-neighbor risk exists; mitigated, not eliminated, at v1.0 (§26) |
| PA-002 | Tenant isolation enforced at both application and database (RLS) layers, never application-only | A single enforcement layer is one bug away from a catastrophic leak (§6, §16) | Every new tenant-scoped table requires RLS policy authorship discipline (§30) |
| PA-003 | No public company self-signup; Super Admin provisions all companies | Enterprise sales motion and pre-vetted regulatory identity for every tenant (§7) | No product-led growth path at v1.0 — a deliberate, revisitable choice (§31) |
| PA-004 | Four fixed roles (Super Admin, Company Admin, Reviewer/QA, User); no custom permission builder | Covers the real org chart of target customers without general-purpose-permission-engine cost (§7) | Large customers with atypical org structures wait for v1.2 (§32) |
| PA-005 | Knowledge Base is one centralized library per company, structurally separate from Projects; Projects reference, never copy | Eliminates controlled-document drift, the single biggest failure mode of per-project document libraries (§9) | Requires disciplined reference-versioning UX so users understand a citation is pinned, not live, without confusion (§18) |
| PA-006 | Files in Supabase Storage; metadata only in Postgres; Render filesystem never authoritative | Closes the exact data-loss failure mode already identified in the current single-tenant build (§15) | None material — this is a strict improvement with no real downside |
| PA-007 | One shared, polymorphic audit-trail/attachments/approvals/equipment-linkage table family platform-wide, not per-document-type | One audit and linkage engine to build, test, and defend to an auditor instead of thirty-plus (§5, §17) | Slightly more complex query patterns (discriminator column) than a dedicated table per type |
| PA-008 | Every state-changing action on a regulated record is audit-logged; audit trail is append-only, immutable, never cascade-deleted | Non-negotiable for FDA/EMA/regulatory customer trust (§17, §27) | Audit data grows without bound; requires a future archival strategy, deliberately not solved at v1.0 (§26, §31) |
| PA-009 | AI-generated content always enters at Draft state; never reaches Approved without passing both In Review and QA Review | Regulatory necessity and product trust — AI is an assistant, not an approver (§12, §13) | Slower "time to approved document" than a hypothetical AI-auto-approve flow — an intentional constraint, not a limitation to be removed later |
| PA-010 | Monolith-first architecture (single Flask application), explicitly not microservices, at v1.0 | Matches current team size and load; module boundaries (§21) make future extraction cheap when actually warranted | Revisit only when a measured bottleneck justifies it — not a standing invitation to split services speculatively (§24) |
| PA-011 | Render + Supabase (Postgres, Storage, Auth) as the managed platform stack | Maximizes team leverage; avoids hand-rolling identity, storage, and database infrastructure (Design Principle 8, §20) | Real but bounded vendor coupling, mitigated by both platforms' reliance on open standards (§20, §26) |
| PA-012 | Full 21 CFR Part 11 cryptographic electronic signatures deferred to v1.1; approval-actor manifestation ships at v1.0 | Ships a usable, review-gated workflow immediately without blocking on the harder compliance capability (§18) | v1.0 alone is not sufficient for customers requiring full Part 11 signature compliance on day one — known and disclosed (§31, §32) |
| PA-013 | Equipment Library elevated to a company-wide, centralized first-class entity, structurally separate from Projects; Projects reference Equipment Library records rather than owning them | Equipment (e.g., an HPLC unit) is qualified, revalidated, and referenced across multiple projects over its operational life — a project-owned equipment record (the current shipped build's model) forces re-entry or duplication every time a new project concerns the same physical asset, violating the reference-never-duplicate principle (§10, Design Principle 3) | A genuine structural change from the current shipped build (`FOUNDATION_ARCHITECTURE.md` §2.2, where equipment is `project_id NOT NULL`) — the migration path re-parents existing equipment rows to their owning company and introduces a project↔equipment many-to-many relationship where today it is a strict one-to-many |
| PA-014 | Standardized six-state document lifecycle (Draft → In Review → QA Review → Approved → Obsolete → Archived) applies platform-wide, replacing the five-state model (Draft/Under Review/Approved/Effective/Superseded) drafted in the prior revision of this document | Splitting review into a distinct technical In Review stage and a distinct QA Review stage gives segregation-of-duties (§7) a structural home instead of relying on process discipline alone; separating Obsolete from Archived gives the platform a real answer to data-retention/archival policy (§26) instead of one undifferentiated "old document" bucket (§12) | Slightly more workflow steps for the simplest customers/documents than a leaner model would require — accepted because the two-stage review is the more defensible posture for a regulated-industry audit |
| PA-015 | Global Search ships at v1.0 as Postgres full-text search over a unified, company-scoped index spanning every searchable domain; semantic/vector search is deferred to v1.1, reusing the AI Engine's existing embedding pipeline rather than standing up parallel infrastructure | Full-text search on the platform's existing Postgres instance is the "prefer managed primitives" choice (Design Principle 8) for v1.0 scale; reusing AI Engine embeddings for the later semantic layer avoids building two separate embedding pipelines for what is fundamentally one capability (§13, §14) | v1.0 search quality is keyword-based, not semantic — acceptable because it matches the current build's already-shipped keyword-search baseline (`ROADMAP.md`: "keyword RAG before vector RAG — ships faster, establishes correctness baseline") and is a known, scheduled upgrade, not a gap |
| PA-016 | Future integrations (SAP/ERP, TrackWise, LIMS, OPC/SCADA, Microsoft Entra ID, Google Workspace, Microsoft 365) are architected as boundary/extension points only at v1.0 — no adapter is implemented | Committing to the integration boundary now (async/event-driven adapters, a dedicated `integrations/` module, `external_system_id` columns reserved on the record types most likely to need them) means the first real integration is additive when a customer requires it, not a scramble that risks compromising tenant isolation or RBAC under deadline pressure (§25) | A small amount of schema (`external_system_id` columns) ships unused at v1.0 — a deliberate, minor, and reversible cost in exchange for never having to retrofit linkage columns onto live regulated-record tables later |

---

*This document is the frozen foundation for PharmaGPT's multi-tenant SaaS platform. Any future change to a decision in §33 requires a new, explicitly numbered entry — superseding, not silently editing, the original — so the architectural history of the platform remains reconstructable, in the same spirit as the audit trail this document mandates for the product itself.*

# PharmaGPT Database Architecture v1.0

**Document class:** Official Database Design Reference (Frozen)
**Author role:** Chief Database Architect
**Status:** FROZEN — governs all future schema and data-access implementation. Changes require a formal decision entry in §24, not silent drift.
**Date:** 2026-07-11
**Primary source of truth:** [`PLATFORM_ARCHITECTURE.md`](PLATFORM_ARCHITECTURE.md). This document is that document's database-layer elaboration — every decision here traces to a `PA-###` decision or a numbered section of `PLATFORM_ARCHITECTURE.md`, and none contradicts it. Where this document adds a decision `PLATFORM_ARCHITECTURE.md` did not make (e.g., how the "Documents" unified object model in its §4/§12 is physically table-shaped), that decision is logged here as `DB-###` and is additive, not a reversal.
**Relationship to `DATABASE.md`:** `DATABASE.md` remains the accurate reference for the schema actually running today — a single-tenant SQLite database. This document does not edit it and does not pretend the current build already looks like this. §19 (Migration Strategy) is the explicit, table-by-table bridge between the two.
**Relationship to `FOUNDATION_ARCHITECTURE.md`:** treated as the authoritative record of what the current build's entities (Project, Equipment, QMS) mean and why they're shaped the way they are. Where this document changes that shape (principally: Equipment moving from project-owned to company-owned, per `PLATFORM_ARCHITECTURE.md` §10 / `PA-013`), the change is called out explicitly, never silently assumed.

---

## 1. Database Design Principles

These are the database-specific expressions of the Design Principles in `PLATFORM_ARCHITECTURE.md` §2. Every schema decision in this document is checked against them.

1. **`company_id` is load-bearing, not decorative.** Every tenant-scoped table carries it, it is never nullable on a tenant-scoped table, and it is the first column every Row-Level Security policy and every composite index is built around (`PLATFORM_ARCHITECTURE.md` §6).
2. **Reference over duplication, enforced structurally, not by convention.** Where two things can be linked instead of copied — a document, a piece of equipment, a Knowledge Base citation — the schema provides a link table or a foreign key, and nothing in the design permits a working copy to silently drift from its source of truth.
3. **Polymorphism is a deliberate, limited tool, not a default.** Shared tables (audit trail, attachments, approvals, comments, equipment linkage) exist because thirty-plus domain tables would otherwise each reinvent the same mechanism. They are used only where that trade-off — flexibility purchased at the cost of a database-enforced foreign key — is worth it (§5, §22 Risks).
4. **Nothing regulator-relevant is ever truly deleted.** Documents, equipment, and quality records move through lifecycle states (`PLATFORM_ARCHITECTURE.md` §12); hard deletion is a rare, explicit, Super-Admin/data-retention operation, never an incidental side effect of a normal user action or a careless cascade (§5, `DB-016`).
5. **The schema is written for the tenant who doesn't exist yet.** Every table, every index, every partitioning decision is evaluated against "does this hold up for company #4,000 with 500 users and 50,000 documents," not against the first pilot customer's dataset.
6. **Metadata and content are separate concerns, physically.** No table in this schema stores file bytes. Every file-bearing table stores a storage path, checksum, size, and content type (`PLATFORM_ARCHITECTURE.md` §15).
7. **Every table declares its `ON DELETE` behavior on purpose.** There is no foreign key in this design left at a database default — each one is a considered answer to "what should happen to this child row if its parent goes away" (§5).

---

## 2. Multi-Tenant Strategy

**Shared database, shared schema, row-level isolation via `company_id` + PostgreSQL Row-Level Security.** This is `PA-001` from `PLATFORM_ARCHITECTURE.md` §6, restated here at the level a schema designer needs to act on it, not re-litigated.

### Why this is the only viable choice at the database layer, restated with DB-specific weight

A database-per-tenant or schema-per-tenant model fails specifically at the database layer before it fails anywhere else: connection pools are sized per database/schema, migration tooling has to fan out across every tenant's copy of the schema, and query planner statistics, autovacuum, and backup jobs all operate per database. None of that scales to "thousands of companies" as an operational matter — it's not a philosophical objection, it's a specific, measurable ceiling every team that has tried it has hit. Shared-schema-plus-RLS keeps exactly one schema to migrate, one connection pool to size, one set of query plans to tune, regardless of whether there are ten tenants or ten thousand.

### What "row-level isolation" means concretely in this schema

Every tenant-scoped table's isolation is enforced twice, independently:

1. **Every query the application issues is already scoped** by `company_id`, resolved server-side from the authenticated session (never from client input) — this is the ordinary, expected path.
2. **Every tenant-scoped table carries an RLS policy that re-checks `company_id` at the database engine level**, regardless of what the application did. This is what makes a forgotten `WHERE` clause, a SQL injection, or an application bug non-catastrophic instead of a breach — the database itself refuses to return or accept rows outside the authenticated session's company (§13).

A small number of platform-level tables (`companies`, `roles`, the platform side of `users`, `break_glass_access`) are intentionally **not** tenant-scoped — they are the tables Super Admin operates on, and they carry their own, separate RLS posture (§13).

---

## 3. Entity Relationship Overview

The schema is organized into six functional layers. The diagrams below show each layer's shape; §4 defines every entity in full, and §5–§9 go deeper on the relationships that matter most.

### 3.1 Platform layer (not tenant-scoped)

```
                    ┌──────────────┐
                    │  companies    │  (tenant root)
                    └──────┬───────┘
                           │ 1
                           │
                           │ N  (nullable — NULL only for Super Admin)
                    ┌──────▼───────┐        ┌───────────────┐
                    │    users      │───N:1──│     roles      │  (4 fixed rows,
                    └──────┬───────┘        └───────────────┘   §6, §12)
                           │ 1
                           │ N
                    ┌──────▼────────────┐
                    │ break_glass_access │  (Super Admin → company,
                    └────────────────────┘   explicit + time-boxed, §7)
```

### 3.2 Company-level pillars (every table below carries `company_id`)

```
company_id
   │
   ├── projects ──< project_members >── users
   │
   ├── equipment ──< equipment_links >── (documents, deviations, capas,
   │                                       change_controls, risk_assessments,
   │                                       calibration_records*, pm_records*)
   │
   ├── documents ──< document_versions
   │             ──< document_references >── documents (KB citations, pinned)
   │             ──< approvals (polymorphic)
   │
   ├── ai_conversations ──< ai_messages
   │   ai_jobs
   │   ai_usage_ledger
   │
   ├── deviations / capas / change_controls / risk_assessments
   │
   ├── audit_trail (polymorphic, every record type above)
   ├── attachments (polymorphic)
   ├── comments (polymorphic)
   ├── notifications
   └── company_settings

   * reserved at v1.0 — see §21
```

Every arrow in both diagrams is either a direct foreign key (owned, one-to-many) or a polymorphic link through a shared table (referenced, many-to-many-capable) — §5 defines exactly which relationships are which and why.

---

## 4. Complete Entity List

Grouped by function. "Scope" states whether the table is tenant-scoped (carries `company_id`), platform-scoped (no `company_id`), or derived (a rebuildable projection, not a source of truth). Entities marked **Reserved** are schema-planned in this document but not built at v1.0 — see §21 for the full reserved-tables rationale.

### 4.1 Identity & Tenancy

| Entity | Scope | Purpose |
|---|---|---|
| `companies` | Platform | The tenant root. Legal name, industry segment, plan tier, status, onboarding date. |
| `users` | Platform (nullable `company_id`) | One row per human identity, linked to its Supabase Auth identity. `company_id` is `NULL` only for the Super Admin role — every other user has exactly one company. Carries `role_id`, status (active/deactivated), display name, last-login. |
| `roles` | Platform | A small, mostly-static reference table: the four frozen roles (`PLATFORM_ARCHITECTURE.md` §7) — Super Admin, Company Admin, Reviewer/QA, User. |
| `permissions` | Platform — **Reserved** | Granular capability grants, for the custom-permission-builder capability scheduled at v1.2 (`PLATFORM_ARCHITECTURE.md` §32). Not consulted by any v1.0 code path. |
| `role_permissions` | Platform — **Reserved** | Junction between `roles`/custom roles and `permissions`, same v1.2 horizon as above. |
| `company_settings` | Tenant | One row per company: AI usage limits, branding, notification preferences, data-retention policy parameters. Kept separate from `companies` so frequently-adjusted configuration doesn't churn the tenant-root row. |
| `break_glass_access` | Platform | Logs every instance of a Super Admin accessing tenant content: who, which company, stated reason, granted-at, expires-at, revoked-at. A control, not a convenience feature — see §7 (Authentication) and §9 (Audit). |

### 4.2 Projects & Work Product

| Entity | Scope | Purpose |
|---|---|---|
| `projects` | Tenant | A validation/quality engagement. Carries the fields already validated by the current build's Module 1 consolidation (name, status, owner, approver, target date, risk category, protocol/report numbers). |
| `project_members` | Tenant | Junction: which users belong to which project, and at what project-level role/capability (§5, §11 of `PLATFORM_ARCHITECTURE.md`). |

### 4.3 Equipment Library

| Entity | Scope | Purpose |
|---|---|---|
| `equipment` | Tenant | One master record per physical asset. Company-owned (`PLATFORM_ARCHITECTURE.md` §10, `PA-013`) — never project-owned. Basic/Installation/Qualification field groups, unchanged in shape from the current build's `equipment` table. |
| `equipment_links` | Tenant | Polymorphic link table: connects an `equipment` row to any of the sixteen record types listed in §6, without ever copying equipment data into the linked record. |
| `calibration_records` | Tenant — **Reserved** | One row per calibration event, owned directly by `equipment_id`. Scheduled for v1.1 (`PLATFORM_ARCHITECTURE.md` roadmap). |
| `preventive_maintenance_records` | Tenant — **Reserved** | One row per PM event, owned directly by `equipment_id`. Same v1.1 horizon. |
| `spare_parts` | Tenant — **Reserved** | Spare-parts inventory associated with equipment. Architecture-only per `FOUNDATION_ARCHITECTURE.md` §2.2; this document preserves that status. |

### 4.4 Document Engine (the "Documents" pillar of `PLATFORM_ARCHITECTURE.md` §4)

| Entity | Scope | Purpose |
|---|---|---|
| `documents` | Tenant | **Unified** document object — one table for Knowledge Base documents and Project-generated documents alike, discriminated by `source_context` (`knowledge_base` / `project`) and a nullable `project_id`. Replaces the current build's separate `kb_documents` and `generated_documents` tables — see `DB-002`. Carries `document_type` (URS, DQ, FAT, SAT, IQ, OQ, PQ, VALIDATION_REPORT, SOP, VENDOR_DOCUMENT, SPECIFICATION, DRAWING, REGULATORY_DOCUMENT, COMPANY_STANDARD, …), lifecycle `status` (§8, six states), `current_version_id`, owner, category/tags. |
| `document_versions` | Tenant | One immutable snapshot per submitted revision. Storage pointer (§16), extracted-text reference, author, lifecycle state at time of snapshot, `major_version`/`minor_version`. |
| `document_references` | Tenant | Records a citation from one document (typically Project-generated) to another (typically a Knowledge Base document), **pinned to a specific `document_versions` row** at the time of citation — the mechanism behind `PLATFORM_ARCHITECTURE.md` §18's version-pinning guarantee. |
| `document_categories` | Tenant (platform-seeded starter set) | The Knowledge Base folder taxonomy (SOP, Validation, Qualification, Protocols, Reports, Regulations, Vendor Documents, Others). |
| `tags` / `document_tags` | Tenant | Free-form tagging, many-to-many. |
| **"Document Approvals"** | *(modeled, not a dedicated table)* | Requested as a named entity in scope — realized as `approvals` rows where `record_type = 'document_version'` (§4.6). A dedicated `document_approvals` table was considered and rejected — see `DB-004`. |

### 4.5 AI Workspace

| Entity | Scope | Purpose |
|---|---|---|
| `ai_conversations` | Tenant | One row per chat/generation session — optionally tied to a `project_id`, always tied to the initiating `user_id`. |
| `ai_messages` | Tenant | One row per turn in a conversation (`role`: user/assistant), content, token counts. |
| `ai_jobs` | Tenant | The general async-task ledger for AI work: document generation, text extraction, embedding generation. `job_type`, `status` (queued/running/succeeded/failed), input/output references, timestamps. |
| `ai_usage_ledger` | Tenant | Every billable AI action — `company_id`, `user_id`, `ai_job_id`, tokens, computed cost, purpose. The cost-accounting and provenance primitive from `PLATFORM_ARCHITECTURE.md` §13. |

### 4.6 Shared / Polymorphic Infrastructure

One table family, reused by every domain above — the physical realization of `PLATFORM_ARCHITECTURE.md` §5's "polymorphic shared tables over per-domain duplicates" rule, generalized from the current build's `qms_`-prefixed tables to a platform-wide namespace (`DB-004`).

| Entity | Scope | Purpose |
|---|---|---|
| `audit_trail` | Tenant | Append-only. Every state-changing action on every record type, platform-wide (§9). |
| `attachments` | Tenant | Supporting files (photos, emails, misc evidence) attached to any record — distinct from `documents`, which are lifecycle/version-governed controlled records. An attachment has no lifecycle of its own. |
| `comments` | Tenant | Threaded discussion attached to any record. |
| `approvals` | Tenant | Every review/sign-off decision, on any record type — document versions, deviations, CAPAs, change controls alike. |
| `equipment_links` | Tenant | (Also listed in §4.3 — it is equipment's half of this same architectural pattern.) |

### 4.7 Quality Records (QMS)

| Entity | Scope | Purpose |
|---|---|---|
| `deviations` | Tenant | Nullable `project_id` (`SET NULL` on project archival — quality records outlive the project that spawned them, per the pattern already validated in `DATABASE.md`). |
| `capas` | Tenant | Same pattern. |
| `change_controls` | Tenant | Same pattern. |
| `risk_assessments` | Tenant | Same pattern. |

### 4.8 Operational / Platform

| Entity | Scope | Purpose |
|---|---|---|
| `notifications` | Tenant | In-app notifications: review assigned, approval requested, document approved, mention in a comment. |
| `search_index` | Tenant, **derived** | The Global Search projection (`PLATFORM_ARCHITECTURE.md` §14) — rebuildable at any time from the domain tables, never a source of truth. |
| `integration_configs` | Tenant — **Reserved** | Per-company configuration for the integrations `PLATFORM_ARCHITECTURE.md` §25 defines a boundary for. Schema exists; no code path activates it at v1.0. |
| `api_keys` | Tenant — **Reserved** | Company-scoped service-identity credentials, the mechanism `PLATFORM_ARCHITECTURE.md` §25 requires future integrations to authenticate through. |
| `signature_events` | Tenant — **Reserved** | The cryptographically-binding e-signature record scheduled for v1.1 (`PLATFORM_ARCHITECTURE.md` §18), additive to `approvals`. |
| `subscriptions` / `plans` / `invoices` | Platform / Tenant — **Reserved** | Billing, out of scope for v1.0 product (`PLATFORM_ARCHITECTURE.md` §31) but schema-anticipated so it doesn't require a retrofit onto live tenant data later. |
| `data_retention_policies` | Tenant — **Reserved** | Per-company archival/retention rules, feeding the v1.1 archival-automation roadmap item. |

---

## 5. Relationships

### 5.1 Cardinalities, by example

| Relationship | Cardinality | Mechanism |
|---|---|---|
| Company → Users | One-to-Many | Direct FK (`users.company_id`) |
| Company → Projects, Equipment, Documents, … | One-to-Many | Direct FK on every tenant-scoped table |
| User ↔ Roles | Many-to-One | Direct FK (`users.role_id`) — one role per user at v1.0 |
| Project ↔ Users | Many-to-Many | Cross-reference table `project_members` |
| Document → Document Versions | One-to-Many | Direct FK (`document_versions.document_id`), plus `documents.current_version_id` pointing back |
| Document ↔ Document (citation) | Many-to-Many, version-pinned | Cross-reference table `document_references` |
| Equipment ↔ (Documents, Deviations, CAPAs, Change Controls, Risk Assessments) | Many-to-Many | Cross-reference table `equipment_links` (§6) |
| Equipment → Calibration/PM/Spare Parts *(reserved)* | One-to-Many | Direct FK (`equipment_id`) — these are true sub-entities, not references |
| Any record type ↔ Audit Trail, Attachments, Comments, Approvals | One-to-Many, polymorphic | Shared tables keyed by (`record_type`, `record_id`) |
| Company ↔ Super Admin | Many-to-Many (temporally scoped) | `break_glass_access`, one row per access grant |

### 5.2 Ownership rules

**Ownership** in this schema means: the parent's identity is required for the child to make sense, and the child's data has no life of its own outside that parent. **Reference** means the child merely points at something that exists independently.

- A **Project owns** its `project_members` rows, its generated `documents` (via `project_id`), and its QMS records. It does **not** own Equipment — it only references it (`PA-013`).
- **Equipment owns** its (reserved) Calibration, Preventive Maintenance, and Spare Parts records — these cannot exist without a specific equipment row. It does **not** own the documents, QMS records, or validation records that merely reference it via `equipment_links`.
- The **Knowledge Base owns** its `documents` rows (`source_context = 'knowledge_base'`). A Project that cites one does not own it, and gets a `document_references` row instead of a copy.
- **Every shared/polymorphic table is owned by nothing** — `audit_trail`, `attachments`, `comments`, and `approvals` rows persist independently of whatever record they describe (§9), by design.

### 5.3 Deletion policy

Consistent with Design Principle 4 (§1) and `PLATFORM_ARCHITECTURE.md`'s soft-state rule (§5): **almost nothing in this schema is ever hard-deleted by a normal user action.** The table below is therefore mostly about what happens in the rare cases — Super Admin operations, data-retention purges — where a row genuinely goes away.

| Parent | Child | `ON DELETE` policy | Why |
|---|---|---|---|
| Company | anything (`company_id` FK) | **RESTRICT — never CASCADE** | See `DB-016`. A company is suspended, not deleted, in the ordinary course of business; true erasure is a separate, controlled purge procedure, never a side effect of one DELETE statement. |
| Project | `project_members` | **CASCADE** | Membership has no meaning without the project. |
| Project | `documents` (`project_id`) | **SET NULL** | A regulator-relevant document outlives the project record that generated it, exactly as the current build's QMS tables already do for `project_id`. |
| Project | `deviations` / `capas` / `change_controls` / `risk_assessments` | **SET NULL** | Same reasoning — quality records are never deleted because a project was. |
| Project | `equipment_links` rows referencing that project | **CASCADE** (the link row only) | Deleting the link does not touch the `equipment` row it pointed to. |
| Equipment | (reserved) Calibration / PM / Spare Parts | **CASCADE** | True sub-entities — see §5.2. |
| Equipment | `equipment_links` rows referencing that equipment | **RESTRICT** | Equipment hard-deletion is itself a rare, Super-Admin/data-retention operation (§21); the platform does not silently orphan every citing document's link. |
| Document | `document_versions` | **RESTRICT** | Versions are immutable historical fact; they are never deleted even if the parent document is later marked Obsolete or Archived (§12 lifecycle, §10 of this document). |
| Any record | `audit_trail`, `attachments`, `comments`, `approvals` rows | **Never cascade-deleted** | Independently retained by design (§9) — the audit and approval history of a record must survive even a rare hard-delete of the record itself. |

---

## 6. Equipment Library Relationships

This section demonstrates, concretely, how one `equipment` row is linked — never duplicated — to every record type `PLATFORM_ARCHITECTURE.md` §10 names: URS, DQ, FAT, SAT, IQ, OQ, PQ, Validation Reports, Risk Assessment, Calibration, PM, Vendor Documents, SOP, Deviation, CAPA, Change Control.

### 6.1 The mechanism: two link types, chosen per relationship nature

```
                         ┌─────────────────┐
                         │    equipment      │  (company-owned, §10)
                         └───┬───────────┬──┘
                             │           │
               polymorphic   │           │   direct FK (owned sub-entity)
               reference     │           │
                             ▼           ▼
        ┌────────────────────────┐   ┌──────────────────────────┐
        │    equipment_links       │   │  calibration_records*     │
        │  (record_type, record_id)│   │  preventive_maintenance_  │
        └──────────┬────────────────┘   │  records*                │
                    │                    │  spare_parts*            │
     ┌──────────────┼────────────────┐  └──────────────────────────┘
     ▼              ▼                ▼        * reserved, §21
 documents      deviations       change_controls
 (URS/DQ/FAT/    capas           risk_assessments
  SAT/IQ/OQ/PQ/
  SOP/Vendor
  Document/
  Validation
  Report — all
  document_type
  values)
```

- **Documents (URS, DQ, FAT, SAT, IQ, OQ, PQ, Validation Reports, SOP, Vendor Documents)** are all rows in the single `documents` table (§4.4), discriminated by `document_type`. Each is linked to the equipment it concerns via an `equipment_links` row (`record_type = 'document'`, `record_id = documents.id`). One equipment record can be the subject of many documents over its life (initial IQ, a later OQ after a change control, a recurring PQ); one document can, where genuinely relevant, reference more than one equipment record (a FAT for an integrated line touching three connected units) — this is precisely why a polymorphic many-to-many link, not a single FK column on `documents`, is the correct mechanism.
- **Deviations, CAPAs, Change Controls, Risk Assessments** are structured QMS records (§4.7), not "documents" in the lifecycle sense — but they link to equipment through the exact same `equipment_links` mechanism (`record_type = 'deviation'`, `'capa'`, `'change_control'`, `'risk_assessment'`), so a support engineer or an auditor only ever has to understand one linkage pattern, not five.
- **Calibration, Preventive Maintenance, Spare Parts** are the one category that gets a **direct foreign key** (`equipment_id`, not-nullable) rather than a polymorphic link, because — unlike a URS or a CAPA, which exist independently of any one piece of equipment and merely reference it — a calibration event or a PM record has no meaning without the specific equipment it was performed on. This is the ownership distinction drawn in §5.2, applied concretely: reference for things equipment is *cited by*, direct ownership for things that exist *because of* equipment.

### 6.2 Why this avoids duplication

At no point does any equipment attribute (tag number, manufacturer, serial number, qualification status) get copied into a URS, a CAPA, or a calibration record. Every one of those consuming records holds a pointer (`equipment_links` row or `equipment_id` FK); the equipment's actual data lives in exactly one place, and a status change (e.g., qualification status moving to "requalification due") is visible instantly and consistently to every document, project, and quality record that has ever cited it — with the change itself captured once in `equipment`'s own `audit_trail` history (§9), not fragmented across sixteen different consuming tables.

---

## 7. Knowledge Base Relationships

The Knowledge Base is not a separate table family from the rest of the Document Engine — it is the `documents` table (§4.4) filtered to `source_context = 'knowledge_base'`. This is a deliberate consolidation from the current build's dedicated `kb_documents` table (`DB-002`) and is what makes "reusable document architecture" a structural property of the schema rather than a convention two different tables have to independently honor.

### 7.1 How reuse actually works

```
   documents                          document_references
  (source_context =                  ─────────────────────
   'knowledge_base')                  referencing_document_id ──► documents
        │                                                          (source_context = 'project')
        │ 1                           referenced_document_id ──► documents
        │                              (source_context = 'knowledge_base')
        │ N
        ▼                             referenced_version_id ──► document_versions
   document_versions                   (the PINNED version — §10, §18 of
  (v1, v2, v3 …)                        PLATFORM_ARCHITECTURE.md)
```

A Project document (an OQ protocol, say) that cites a controlled SOP does not copy the SOP's text. It creates one `document_references` row pointing at the SOP's `documents` row **and** at the specific `document_versions` row that was current SOP version at the moment of citation. Two consequences follow directly from this shape:

- **Live resolution:** any UI surface asking "what does this OQ cite, and is it current" joins through to the SOP's `documents.current_version_id` and compares it against the pinned `referenced_version_id` — a mismatch is exactly the "this reference has since been updated" flag `PLATFORM_ARCHITECTURE.md` §18 requires, and it falls out of the schema shape rather than needing separate bookkeeping.
- **Reproducibility:** because the pin is to an immutable `document_versions` row (§10), the OQ can always be regenerated exactly as it looked when approved, even if the SOP has since moved to v4.

### 7.2 Platform-seeded templates

The one deliberate exception to "every `documents` row belongs to exactly one company" (`PLATFORM_ARCHITECTURE.md` §5): a small platform-owned set of starter templates, copied — never referenced live — into a new company's Knowledge Base at onboarding. This is a one-time `INSERT ... SELECT`-shaped data operation, not a live cross-tenant foreign key; once copied, Company A's copy and Company B's copy are fully independent rows with no relationship to each other or to the platform template they originated from.

---

## 8. Document Architecture

Every controlled document in the system — Knowledge Base or Project-generated — is the same shape, described here end to end.

| Concern | Where it lives | Notes |
|---|---|---|
| **Metadata** | `documents` | Title, `document_type`, `source_context`, `project_id` (nullable), `company_id`, category/tags, owner, `status` (lifecycle, §12/§10 of `PLATFORM_ARCHITECTURE.md`), `current_version_id`. |
| **Storage reference** | `document_versions` | Storage path/key, checksum, size, content type — never the bytes themselves (§16). |
| **Version history** | `document_versions` | One immutable row per submitted revision — see §10 of this document. |
| **Approval status** | `approvals` (polymorphic, `record_type = 'document_version'`) | Every In Review / QA Review decision, who made it, when, and why. |
| **Lifecycle** | `documents.status` | The six states from `PLATFORM_ARCHITECTURE.md` §12: Draft → In Review → QA Review → Approved → Obsolete → Archived. |
| **Ownership** | `documents.owner_user_id`, `documents.project_id` | Who authored it; which Project it belongs to (`NULL` for Knowledge Base documents). |
| **Revision history** | `document_versions` + `audit_trail` | `document_versions` is the content history; `audit_trail` is the action history (every transition, every edit event) — together they answer both "what did version 2 say" and "who did what, when." |

### 8.1 Why metadata and version content are two tables, not one

Putting everything on a single `documents` row (current version's content included) is the obvious first design and the wrong one for a regulated-document platform: it makes "what did this look like when it was approved on March 3rd" a query that has to be reconstructed from an audit log instead of a direct read of an immutable row. Splitting `documents` (identity, current state, current pointer) from `document_versions` (an append-only history of exactly what was submitted and when) makes reproducibility a first-class, cheap operation rather than a forensic exercise — directly serving `PLATFORM_ARCHITECTURE.md` §18's reproducibility requirement.

---

## 9. Audit Architecture

**One append-only, polymorphic `audit_trail` table, platform-wide.** This is `PLATFORM_ARCHITECTURE.md` §17 realized at the schema level, generalized from the current build's proven `qms_audit_trail` (`DB-004`).

### 9.1 Shape

Every row captures: `company_id`, `actor_user_id` (nullable — system-initiated actions, e.g. an AI job completing, are attributed to a system actor, not a human), `action` (create / update / state-transition / view-of-sensitive-record / delete-request), `record_type`, `record_id`, `prior_state_snapshot` (for updates and transitions), `reason` (mandatory for revision requests, withdrawals, corrections to an Approved record), and `occurred_at`.

### 9.2 Why immutability is a schema property, not a policy

Append-only is enforced two ways, neither of which is "developers agree not to write an UPDATE against this table":

1. **No application code path issues an `UPDATE` or `DELETE`** against `audit_trail` — this is a code-review-enforced convention (`PLATFORM_ARCHITECTURE.md` §27), the first layer.
2. **The table's RLS policy set (§13) grants `INSERT` and `SELECT` only** — there is no `UPDATE`/`DELETE` policy at all for any role, Super Admin included, short of the documented, logged, break-glass exception. A missing policy is a hard database-level refusal, not a convention — the same two-layer posture (§2, §13) applied to write-immutability instead of tenant isolation.

### 9.3 Independence from the record it describes

`audit_trail` rows never carry a foreign key with `ON DELETE CASCADE` back to the record they describe (§5.3) — deliberately, so that even in the rare case a record is genuinely purged, its history survives as evidence that the record existed, what happened to it, and why it was purged.

---

## 10. Version Control Strategy

### 10.1 What gets versioned, and when

Versioning begins the moment a document first reaches **In Review** (`PLATFORM_ARCHITECTURE.md` §18) — not on every Draft save, which would version every keystroke and make the version history noise rather than signal. Each version is a row in `document_versions`, immutable from the moment it's created.

### 10.2 Major vs. minor revisions

A version carries both a `major_version` and `minor_version` number:

- **Minor version increments** cover a revision cycle that returns to Draft and comes back for review without a change in scope or regulatory intent (a typo fix requested during In Review, a formatting correction).
- **Major version increments** cover a substantive content change — different test steps, a different acceptance criterion, a scope change — typically triggered by a Change Control record (§4.7) or a significant CAPA-driven revision.

This distinction is a metadata attribute on `document_versions`, decided by the author/reviewer at submission time, not an automatically inferred diff — automatic content-diffing to classify "major vs. minor" is explicitly not attempted at v1.0; it is a plausible, low-priority AI Engine enhancement for a later release, not a database concern today.

### 10.3 Approval history

Every version's path through In Review and QA Review is captured as `approvals` rows keyed to that specific `document_versions.id` (not just to the parent `documents.id`) — so the approval history of version 2 and version 3 of the same document are never conflated, even though both belong to the same logical document.

### 10.4 Rollback strategy

There is deliberately no "rollback" operation that rewrites `documents.current_version_id` back to an older version silently. In a controlled-document system, "going back" to an earlier version is itself a regulator-relevant event: it happens by **creating a new version whose content matches the earlier one**, submitted through the same In Review → QA Review → Approved path as any other change, with an explicit `audit_trail` entry and `reason` recording that this version reinstates version N's content. This preserves the platform's core guarantee (§12 of `PLATFORM_ARCHITECTURE.md`: no state transition is silent) even for the one operation ("undo") that every other kind of software treats as free.

---

## 11. Authentication Model

Identity is provided entirely by **Supabase Auth** (`PLATFORM_ARCHITECTURE.md` §14/§16) — this document does not define a custom password or session table, consistent with Design Principle 8 (prefer managed primitives).

- **`users`** rows are linked to their Supabase Auth identity by a stored auth-provider reference (not a duplicated credential). `users` holds *platform* profile data (role, company, status, display name) — Supabase Auth holds the actual credential and session material.
- **Session claims:** on authentication, a JWT is issued carrying `user_id`, `company_id` (or `NULL` for Super Admin), and `role` as custom claims. These claims are what every RLS policy in §13 reads — the database never has to separately query "which company does this session belong to," because the session already asserts it, signed and tamper-evident.
- **MFA** is a Supabase Auth capability, enabled at the company or user level via `company_settings`, not a database table this schema needs to model beyond that configuration flag.
- **Service identities** (future integrations, `api_keys`, §4.8) authenticate through a parallel, company-scoped credential rather than a human JWT — but resolve to the same `company_id`-scoped claim shape RLS expects (`PLATFORM_ARCHITECTURE.md` §25), so no RLS policy needs a special case for "is this a human or a service."

---

## 12. Authorization Model

Two layers, matching `PLATFORM_ARCHITECTURE.md` §6/§16 exactly, expressed at the schema level:

1. **Application-layer role check:** `users.role_id` (§4.1) is read by middleware to gate UI surfaces and feature access — the first, convenience-oriented layer.
2. **Database-layer enforcement (RLS, §13):** the layer that actually holds under a bug. Critically, RLS in this schema is **not just a `company_id` check** — for tables whose visibility depends on more than tenancy (chiefly `projects` and project-scoped `documents`), the RLS policy also joins through `project_members` to confirm the requesting user is actually a member of the project the row belongs to, or holds a company-wide role (Company Admin) that implicitly sees everything. Company-wide entities — Knowledge Base documents, Equipment Library records — are visible to every user in the company by default (§7 of `PLATFORM_ARCHITECTURE.md`) and so their RLS policies check `company_id` only, with no membership join.

This distinction — "company-scoped visibility" vs. "company-scoped-plus-membership-scoped visibility" — is the single most important nuance in the authorization model, and it is why RLS policy authorship is treated as security-critical, individually-reviewed work (`PLATFORM_ARCHITECTURE.md` §27) rather than a copy-paste template applied identically to every table.

---

## 13. Row Level Security Strategy

### 13.1 The default policy shape, described conceptually

Every tenant-scoped table carries a policy requiring the row's `company_id` to equal the `company_id` claim embedded in the requester's authenticated session (§11). This is true without exception for every table in §4 marked "Tenant" scope.

### 13.2 Where policies go further than `company_id`

- **`projects`, and any `documents`/QMS row with a non-null `project_id`:** the policy additionally requires either (a) the requester holds the Company Admin role for that company, or (b) the requester has a `project_members` row for that specific project. This is what makes "Projects can be shared among multiple users using role-based permissions" (a frozen `PLATFORM_ARCHITECTURE.md` §7 requirement) an enforced database property, not a UI-only filter.
- **`break_glass_access`-gated reads:** Super Admin's default RLS posture grants access to `companies`, `users`, and platform tables only — **not** to tenant content (`equipment`, `documents`, `projects`, etc.). Access to tenant content requires an active, unexpired `break_glass_access` row for that specific company; the RLS policy on tenant tables checks for that row's existence in addition to the ordinary path, meaning Super Admin tenant-content access is itself something the database enforces as time-boxed, not merely something the application chooses to log.

### 13.3 Company isolation, stated as an invariant

No query, from any role, under any application-layer bug, can return a row whose `company_id` does not match the requester's session `company_id` — except the single, explicit, logged, time-boxed break-glass path above. This is the schema-level form of the zero-tolerance NFR in `PLATFORM_ARCHITECTURE.md` §27 ("Tenant isolation: zero cross-tenant data exposure incidents").

### 13.4 Service/integration sessions

A future integration authenticating via `api_keys` (§4.8, reserved) resolves to a `company_id`-scoped session exactly like a human user, and is bound by the identical RLS policies — there is no "trusted service" bypass anywhere in this design (`PLATFORM_ARCHITECTURE.md` §25).

---

## 14. Indexing Strategy

### 14.1 Baseline (every tenant-scoped table)

- A B-tree index on `company_id` — the column every RLS policy predicate filters on, and therefore the single highest-value index in the schema.
- A B-tree index on every foreign key column, without exception (`PLATFORM_ARCHITECTURE.md` §23).
- Composite indexes matched to the platform's actual query shapes: (`company_id`, `status`) on `documents`, `deviations`, `capas`, `change_controls`; (`company_id`, `project_id`) on every project-scoped table; (`company_id`, `document_type`, `status`) on `documents` specifically, since "all Approved SOPs" and "all Draft URS documents in this project" are the platform's two most common list queries.

### 14.2 Performance indexes for lifecycle-aware queries

- **Partial indexes** on `documents` (and the other lifecycle-bearing tables) covering only non-`archived` rows — since Archived is explicitly excluded from default Global Search and default list views (`PLATFORM_ARCHITECTURE.md` §12, §14), the overwhelming majority of real queries never need to scan Archived rows, and a partial index keeps those queries fast regardless of how large the Archived population grows over a ten-year retention horizon.

### 14.3 Search indexes

- A **GIN index** on a generated full-text search (`tsvector`) column in `search_index` (§4.8) — the concrete mechanism behind `PLATFORM_ARCHITECTURE.md` §14's Postgres full-text search at v1.0. `search_index` itself carries `company_id`, `record_type`, `record_id`, and the searchable text projection, indexed the same way as any other tenant-scoped table (§13).

### 14.4 Future semantic search

When semantic search ships (`PLATFORM_ARCHITECTURE.md` §14, v1.1), the concrete mechanism is Postgres's `pgvector` extension — natively supported by Supabase — adding a vector-embedding column to `search_index` (or a dedicated companion table) with an approximate-nearest-neighbor index (HNSW or IVFFlat). This is additive to the full-text GIN index, not a replacement for it: keyword and semantic search continue to coexist exactly as `PLATFORM_ARCHITECTURE.md` §14 specifies, and no existing index or table needs to be dropped or restructured to add it.

---

## 15. Naming Standards

Extends `PLATFORM_ARCHITECTURE.md` §22/§23 with the full set of database object conventions.

| Object | Convention | Example |
|---|---|---|
| Tables | `snake_case`, plural noun | `documents`, `equipment_links` |
| Primary keys | Always `id`, surrogate (never a natural key) | `documents.id` |
| Foreign keys | `<singular_referenced_table>_id` | `company_id`, `project_id`, `equipment_id` |
| Polymorphic discriminator + key pair | `record_type` + `record_id` | `audit_trail.record_type` / `audit_trail.record_id` |
| Junction/cross-reference tables | `<table_a>_<table_b>` or a purpose-named table when the relationship carries its own attributes | `project_members` (not `projects_users`, because membership carries a role attribute — a purpose name reads better than a mechanical concatenation) |
| Boolean columns | `is_<state>` or `has_<thing>` | `is_active`, `has_mfa_enabled` |
| Timestamps | `created_at`, `updated_at`, plus lifecycle-specific (`approved_at`, `obsolete_at`, `archived_at`) | per `PLATFORM_ARCHITECTURE.md` §23 |
| Enum-like status columns | lower_snake_case string values matching the lifecycle exactly | `'in_review'`, `'qa_review'`, `'approved'` |
| Indexes | `idx_<table>_<column(s)>` | `idx_documents_company_id_status` |
| Unique constraints | `uq_<table>_<column(s)>` | `uq_users_auth_provider_id` |
| Check constraints | `chk_<table>_<rule>` | `chk_users_super_admin_company_null` (the invariant from §4.1: Super Admin rows require `company_id IS NULL`) |
| Foreign key constraints | `fk_<table>_<referenced_table>` | `fk_documents_projects` |

---

## 16. Storage Strategy

Restates `PLATFORM_ARCHITECTURE.md` §15 with the column-level detail a schema designer needs.

| Layer | Where | What it holds |
|---|---|---|
| **Metadata** | PostgreSQL (`documents`, `document_versions`, `attachments`) | Everything queryable: title, type, status, owner, timestamps, storage pointer, checksum, size, content type. |
| **Files** | Supabase Storage, private buckets | The actual bytes — DOCX, PDF, images, annexures. |
| **Attachments** | Same Storage buckets as Documents, distinct path prefix | Supporting files without lifecycle/version governance (§4.6). |
| **Path convention** | `{company_id}/{domain}/{record_id}/{version_or_filename}` | Encodes the tenant boundary directly into the storage path — a second, independent enforcement point beyond RLS (`PLATFORM_ARCHITECTURE.md` §15). |
| **Signed access** | Application-issued, short-lived signed URLs | No bucket is ever public; no client holds a durable Storage credential. |

No table in this schema stores file content directly — this is a hard rule, not a style preference (§1).

---

## 17. Backup Strategy

- **Continuous point-in-time recovery (PITR)** via Supabase's managed Postgres backup capability — the platform's RPO target of under 5 minutes (`PLATFORM_ARCHITECTURE.md` §29) is a direct function of PITR granularity, not a custom backup job this schema or its operators maintain.
- **Retention:** PITR window sized to the company's contractual/regulatory retention requirement at minimum 30 days, with periodic longer-horizon snapshots for the multi-year retention regulated documents require — the specific retention duration is a `company_settings`/`data_retention_policies` (§4.1, §4.8) configuration matter, not a fixed schema constant, because different customer segments (pharma vs. nutraceutical, different jurisdictions) carry different regulatory retention minimums.
- **Storage backup:** Supabase Storage's own redundancy guarantees cover file durability; a second backup location is a plan-tier/contractual capability, not a v1.0 default (`PLATFORM_ARCHITECTURE.md` §29).
- **Tenant-level export:** because every tenant's data is addressable by `company_id` alone (§2), a single company's full dataset can be exported independently of a platform-wide backup/restore operation — useful both for a customer-requested data export and for a scoped restore that doesn't require touching any other tenant's data.

---

## 18. Disaster Recovery

- **RTO target: under 4 hours** for full platform restoration (`PLATFORM_ARCHITECTURE.md` §29), driven primarily by Supabase project restoration time — the application tier is stateless (§20 of `PLATFORM_ARCHITECTURE.md`) and redeploys independently in minutes, so it is never the bottleneck in a DR scenario.
- **Restore drills are mandatory, not aspirational:** a periodic, documented drill restores a production backup into Staging and verifies referential and RLS integrity — specifically confirming that restored RLS policies still correctly isolate tenants, since a botched restore that silently drops or misconfigures a policy is a worse outcome than downtime.
- **Tenant-scoped recovery** (§17) is DR's most valuable schema-level property for this platform's actual failure mode: the far more common "disaster" a regulated-industry SaaS customer experiences is not the whole platform going down, but one company's data being mistakenly altered or deleted — and the shared-schema-plus-`company_id` design makes recovering exactly that company's data, and only that company's data, an operation the schema supports directly, rather than requiring a full-platform restore that would needlessly roll back every other tenant.

---

## 19. Migration Strategy

### 19.1 Three phases, not a big-bang rewrite

```
   Phase 1 (today)              Phase 2                       Phase 3
   ─────────────────           ───────────────────           ───────────────────
   SQLite                  →   PostgreSQL                →   Supabase
   Single-tenant                Same schema shape as           (Postgres + Storage +
   Local-disk uploads            Phase 3, but exercised          Auth, managed)
   No RLS, no company_id          in a controlled staging        RLS enabled
                                   environment first               `company_id` live on
                                                                     every tenant-scoped
                                                                     row
                                                                    Storage cut over from
                                                                     local disk
```

Phase 2 exists specifically so that "does the new schema behave correctly under PostgreSQL" and "does RLS actually isolate tenants correctly" are validated **before** the irreversible step of pointing production traffic at Supabase — consistent with `PLATFORM_ARCHITECTURE.md` §20's three-environment (Development/Staging/Production) requirement.

### 19.2 Entity mapping — current build → target schema

This is the concrete answer to "does the new design account for everything that exists today":

| Current (`DATABASE.md`) | Target (this document) | Notes |
|---|---|---|
| `projects` | `projects` | Carries forward unchanged in spirit; gains `company_id`. |
| `messages` | `ai_conversations` + `ai_messages` | Chat history becomes a first-class AI Workspace entity (§4.5) instead of a flat per-project table. |
| `documents` (uploaded files) | `documents` (`document_type = 'project_upload'` or similar) + `document_versions` | Folded into the unified Document Engine (§4.4) rather than kept as a separate upload table. |
| `document_text` | `document_versions.extracted_text` (or a companion extraction table) feeding `search_index` | Extraction becomes an input to Global Search (§14 of `PLATFORM_ARCHITECTURE.md`) rather than a standalone table with no consumer beyond keyword search. |
| `kb_documents` | `documents` (`source_context = 'knowledge_base'`) | Consolidated — see `DB-002`. |
| `generated_documents` | `documents` (`source_context = 'project'`) + `document_versions` | Same consolidation; gains full lifecycle/versioning it did not have before. |
| `qms_documents`, `qms_deviations`, `qms_capas`, `qms_change_controls` | `documents`/`deviations`/`capas`/`change_controls`, gaining `company_id` | Structural shape carries forward — the current build's QMS domain design was already correct at the pattern level. |
| `qms_audit_trail`, `qms_attachments`, `qms_comments`, `qms_approvals` | `audit_trail`, `attachments`, `comments`, `approvals` (namespace generalized, scope widened) | See `DB-004` — same mechanism, now used platform-wide instead of QMS-only. |
| `equipment` (`project_id NOT NULL`) | `equipment` (`company_id`, no `project_id`) | Re-parented from Project to Company — see `PA-013` and `DB-003`. Existing rows are migrated by resolving each equipment record's owning company through its current project, then dropping the `project_id` column in favor of `equipment_links` rows connecting it back to that (and any other) project. |
| `equipment_documents` | `equipment_links` (`record_type = 'document'`) | Generalized to also cover deviations, CAPAs, change controls, and risk assessments (§6), not just documents. |
| `val_projects` / `val_audit_trail` (already retired, read-only per `FOUNDATION_ARCHITECTURE.md` §4) | Not migrated | Remains exactly what `FOUNDATION_ARCHITECTURE.md` already made it: historical, read-only, reachable only via the one-time copy already performed. No further action. |

### 19.3 Cutover mechanics

1. Stand up the target schema in Supabase Staging (Phase 2 validated first).
2. Backfill `company_id` across every migrated row — for a single-tenant source database, every row maps to the one bootstrap company being onboarded first.
3. Migrate file content from local/Render disk to Supabase Storage, rewriting stored paths to the new convention (§16) as part of the same pass — not as a follow-up.
4. Run the full test suite plus a manual RLS-isolation check against Staging before promoting.
5. Cut production traffic over; keep the SQLite source read-only and retained for a defined window as a rollback reference, then retire it.

---

## 20. Scalability Strategy

Extends `PLATFORM_ARCHITECTURE.md` §24 with the database-specific mechanisms that deliver it.

1. **Tenant and document volume growth:** absorbed by the shared-schema + RLS model itself (§2) — no schema change is needed as tenant count grows, only infrastructure sizing.
2. **Read replicas:** the designed next step once a single primary's read load is the bottleneck; because isolation logic lives entirely in RLS policy predicates evaluated per-query, replicas inherit correct tenant isolation automatically, with no policy duplication required.
3. **Table partitioning (new in this document, additive to `PLATFORM_ARCHITECTURE.md` §24, not a contradiction of it):** the platform's largest, fastest-growing, append-only tables — `audit_trail`, `ai_messages`, `ai_usage_ledger` — are the designed candidates for time-based (monthly or quarterly) range partitioning once their row counts warrant it. This is a standard, well-understood PostgreSQL scaling technique for exactly this shape of data (high insert volume, queries that are almost always time-bounded), and because these tables are already append-only by design (§1, §9), partitioning introduces no complication around updates crossing partition boundaries.
4. **Connection pooling:** Supabase's managed PgBouncer absorbs the connection-count pressure of a growing tenant base without requiring the application tier to manage its own pool sizing per tenant.
5. **Cold-data strategy for Archived documents:** the six-state lifecycle's Archived state (`PLATFORM_ARCHITECTURE.md` §12) is the schema's built-in answer to "what happens to old data as the table grows for ten years" — Archived rows are excluded from the partial indexes in §14.2 and from default `search_index` results, keeping the working set that ordinary queries touch flat even as total historical volume grows without bound.

---

## 21. Reserved Tables

Tables and columns intentionally schema-planned in this document but **not built, not populated, and not queried by any v1.0 code path.** Reserving them now — rather than retrofitting them onto live regulated-record tables later — is the explicit trade-off `PLATFORM_ARCHITECTURE.md` §25 and `PA-016` already committed to; this section is the database-level inventory of that commitment.

| Reserved object | Feeds | Scheduled |
|---|---|---|
| `permissions`, `role_permissions` | Custom/granular permission builder | v1.2 |
| `calibration_records`, `preventive_maintenance_records`, `spare_parts` | Equipment Library expansion | v1.1 |
| `signature_events` | Cryptographically-binding 21 CFR Part 11 e-signatures, additive to `approvals` | v1.1 |
| `data_retention_policies` | Archival-policy automation | v1.1 |
| `integration_configs`, `api_keys` | SAP/ERP, TrackWise, LIMS, OPC/SCADA, identity-federation integrations | v1.2+ |
| `external_system_id` columns on `deviations`, `capas`, `change_controls` | TrackWise/QMS federation, reserved on the record types most likely to need it | v1.2+ |
| `subscriptions`, `plans`, `invoices` | Billing and plan-tier enforcement | v1.2 |

No reserved table or column participates in any RLS policy, index, or foreign-key relationship that a v1.0 read or write path depends on — they exist purely as forward-declared shape, not live infrastructure.

---

## 22. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Polymorphic tables (`audit_trail`, `attachments`, `approvals`, `equipment_links`) have no database-enforced foreign key to their target — a typo'd `record_type` or a stale `record_id` is silently possible | Orphaned or mismatched references, undetected by the database itself | Application-layer validation on every write to a polymorphic table; `record_type` values are a fixed, code-reviewed enum, not free text; periodic integrity-check jobs can flag orphaned polymorphic rows without needing a schema-level constraint that would defeat the pattern's purpose. |
| RLS policy authorship error (an omitted or incorrect policy) | Silent under- or over-restriction of tenant data — the platform's single zero-tolerance failure category (§27 of `PLATFORM_ARCHITECTURE.md`) | Mandatory second-engineer review on every PR touching RLS (`PLATFORM_ARCHITECTURE.md` §27); RLS policy coverage is part of the definition of done for any new tenant-scoped table. |
| Unified `documents` table becoming a single hot table under heavy concurrent write load across thousands of tenants | Contention, index bloat, slower writes as the platform scales | Indexing strategy (§14) targets exactly this table's real query shapes; partitioning (§20) is the designed next step if row count alone becomes the bottleneck. |
| Company re-parenting migration for Equipment (§19.2) resolving an ambiguous or missing project-to-company mapping for a legacy row | Incorrect or failed migration for a subset of historical equipment records | Migration runs against Staging first (§19.1) with an explicit validation pass reconciling every migrated equipment row's resolved `company_id` before Production cutover; any row that can't be unambiguously resolved is flagged for manual review rather than silently defaulted. |
| Ten-year data retention on append-only audit/version tables growing without a partitioning or archival strategy in place before it's needed | Query performance decay, backup/restore duration growth | Partitioning (§20) and Archived-state exclusion from default indexes (§14.2) are designed in from v1.0, not retrofitted; §21's reserved `data_retention_policies` table gives the platform the hook to automate archival before it becomes a performance problem, not after. |

---

## 23. Trade-offs

A synthesis of the deliberate costs this design accepts, each already justified in its own section and cross-referenced to the `DB-###` decision that owns it:

- **Shared schema over per-tenant isolation** buys operational scalability at the cost of a shared blast radius, mitigated but not eliminated by two-layer enforcement (§2, §13, `DB-001`).
- **Polymorphic linkage over per-domain foreign keys** buys one audit/attachment/approval/equipment-linkage engine instead of thirty-plus, at the cost of database-enforced referential integrity on those specific relationships (§22, `DB-004`).
- **A unified `documents` table over specialized per-source tables** buys one lifecycle/versioning/search engine for every controlled document, at the cost of a wider, more general table than a narrowly-typed `kb_documents` or `generated_documents` table would be (§8, `DB-002`).
- **Reserved-but-unbuilt schema (§21) shipped now** buys a clean, additive path for e-signatures, integrations, billing, and permission-builder features later, at the cost of a small amount of schema surface that sits unused at v1.0 (`DB-013`).
- **No cascade-delete from Company** buys protection against catastrophic accidental data loss, at the cost of requiring an explicit, separately-designed offboarding/purge procedure rather than a single DELETE statement (§5.3, `DB-016`).

---

## 24. Final Database Decision Log

**DB-001 — Shared schema, `company_id`, PostgreSQL RLS**
- **Decision:** One PostgreSQL database, one schema, every tenant-scoped table carries `company_id`, isolation enforced by RLS.
- **Reason:** The only model that scales operationally to thousands of tenants without infrastructure growing linearly with tenant count (`PLATFORM_ARCHITECTURE.md` §6, `PA-001`).
- **Alternative considered:** Database-per-tenant, schema-per-tenant.
- **Trade-offs:** Shared blast radius and noisy-neighbor risk, mitigated by two-layer enforcement and per-tenant monitoring (§2, §22).

**DB-002 — Unified `documents` table across Knowledge Base and Project-generated content**
- **Decision:** One `documents` table, discriminated by `source_context` and nullable `project_id`, replacing the current build's separate `kb_documents` and `generated_documents` tables.
- **Reason:** Gives every controlled document — regardless of where it was authored — one lifecycle engine, one versioning engine, and one search surface (§8, §14), directly realizing the "Documents" unified object model `PLATFORM_ARCHITECTURE.md` §4/§12 already committed to conceptually.
- **Alternative considered:** Keep separate tables per source, as the current build does.
- **Trade-offs:** A wider, more general table than a narrowly-typed alternative; requires disciplined use of `document_type`/`source_context` discriminators rather than relying on "which table it's in" to convey meaning.

**DB-003 — Equipment re-parented from Project-owned to Company-owned**
- **Decision:** `equipment.company_id`, not `equipment.project_id`; Projects reference Equipment via `equipment_links`.
- **Reason:** Physical equipment is qualified and referenced across multiple projects over its life; project ownership forced re-entry/duplication (`PLATFORM_ARCHITECTURE.md` §10, `PA-013`).
- **Alternative considered:** Keep the current build's `project_id NOT NULL` shape and let Projects "share" equipment via a separate copy-linking mechanism.
- **Trade-offs:** Requires the explicit re-parenting migration in §19.2; a genuine structural change from the current shipped build, not a pure additive one.

**DB-004 — Platform-wide shared tables generalized from the current build's `qms_`-prefixed pattern**
- **Decision:** `audit_trail`, `attachments`, `comments`, `approvals`, `equipment_links` — one namespace, used by every domain, not just QMS.
- **Reason:** Thirty-plus record types sharing one audit/attachment/approval/linkage engine is dramatically more auditable and maintainable than thirty-plus parallel implementations (`PLATFORM_ARCHITECTURE.md` §5, §17).
- **Alternative considered:** A dedicated `document_approvals` table (as the task's entity list names it) separate from a QMS-specific approvals table.
- **Trade-offs:** No database-enforced FK integrity on the polymorphic key (§22); "Document Approvals" is a logical entity realized as rows in a shared physical table, which requires clear documentation (§4.4) so engineers don't go looking for a table that doesn't exist by that name.

**DB-005 — Single `users` table with nullable `company_id` for Super Admin, not a separate platform-admin table**
- **Decision:** One identity table for every human user, Super Admin included; `company_id` is `NULL` only for that role, enforced by a check constraint.
- **Reason:** Avoids duplicating authentication/session mechanics across two parallel identity tables for what is, at the schema level, still "a user with a role."
- **Alternative considered:** A separate `platform_admins` table, fully outside the `users`/`roles` model.
- **Trade-offs:** Every query and RLS policy touching `users` must correctly handle the `NULL` `company_id` case rather than being able to assume it's always populated.

**DB-006 — `roles` as a small reference table; `permissions`/`role_permissions` reserved, not built**
- **Decision:** Four fixed rows in `roles`; no permission-matrix tables populated or consulted at v1.0.
- **Reason:** Matches the frozen four-role model (`PLATFORM_ARCHITECTURE.md` §7, `PA-004`) exactly, while leaving a clean, additive path to the granular permission builder already scheduled for v1.2.
- **Alternative considered:** Build the full permission-matrix schema now, unused, "to save a migration later."
- **Trade-offs:** None material — `roles` as a lookup table costs nothing extra now and the reserved tables (§21) already provide the future path without needing to build it early.

**DB-007 — Versioning begins at In Review, not at Draft**
- **Decision:** `document_versions` rows are created starting from a document's first submission to In Review.
- **Reason:** Versioning every Draft keystroke would make the version history noise, not signal (§10).
- **Alternative considered:** Version every save, including Draft.
- **Trade-offs:** Draft-stage edit history is available only through `audit_trail`, not as full `document_versions` snapshots — an acceptable asymmetry, since Draft content isn't yet regulator-relevant.

**DB-008 — `document_references` pins a specific `document_versions` row, not just a document**
- **Decision:** Every Knowledge Base/Equipment citation from a Project document records the exact version cited, not merely "cites document X."
- **Reason:** Reproducibility — a report must be regenerable exactly as it looked when approved, even after the cited SOP moves to a later version (`PLATFORM_ARCHITECTURE.md` §18).
- **Alternative considered:** Reference the document only, always resolving to "whatever is current" at read time.
- **Trade-offs:** Requires a flagging mechanism (§7.1) to surface when a pinned reference has fallen behind the current version, rather than silently always showing the latest.

**DB-009 — `search_index` as a derived, rebuildable projection, not a second source of truth**
- **Decision:** Global Search's index is a denormalized table built from the domain tables, never authoritative on its own.
- **Reason:** Keeps metadata/content ownership unambiguous (§1, Design Principle 2) — the index can be dropped and rebuilt at any time with zero data loss.
- **Alternative considered:** A dedicated external search service as the v1.0 default.
- **Trade-offs:** Requires disciplined synchronous/asynchronous update discipline (§14 of `PLATFORM_ARCHITECTURE.md`) so the index doesn't silently drift stale relative to the domain tables it's derived from.

**DB-010 — RLS policies join through `project_members` for project-scoped tables, not `company_id` alone**
- **Decision:** Project and project-scoped document visibility is enforced at the database level based on actual project membership, not just tenant membership.
- **Reason:** "Projects can be shared among multiple users using role-based permissions" is a frozen requirement (`PLATFORM_ARCHITECTURE.md` §7) that must hold even if application-layer filtering has a bug (§12, §13).
- **Alternative considered:** Company-wide visibility for all tenant data, with project-level restriction enforced only in the application layer.
- **Trade-offs:** More complex RLS policies (a join, not a flat equality check) for every project-scoped table — accepted because the alternative fails the same "must hold under a bug" bar tenant isolation itself is held to.

**DB-011 — `break_glass_access` as an explicit, time-boxed, audited table**
- **Decision:** Super Admin access to tenant content requires an active row in a dedicated grant table, itself logged; there is no standing superuser bypass of tenant RLS.
- **Reason:** `PLATFORM_ARCHITECTURE.md` §7 commits to exactly this posture as a v1.0 behavior, not a future hardening step.
- **Alternative considered:** A blanket `is_super_admin` bypass evaluated inline in every RLS policy.
- **Trade-offs:** Adds a join/lookup to the RLS policy path for tenant tables (§13.2) and requires Super Admin tooling to request/grant access explicitly rather than always having it — accepted as the correct cost for a genuinely audited break-glass control.

**DB-012 — Calibration, Preventive Maintenance, and Spare Parts modeled as direct equipment-owned child tables, not polymorphic links**
- **Decision:** `equipment_id` is a direct, not-nullable foreign key on these (reserved) tables, unlike the polymorphic `equipment_links` used for Documents and QMS records.
- **Reason:** These records have no existence independent of the specific equipment they concern — true ownership, not reference (§5.2, §6.1).
- **Alternative considered:** Route these through `equipment_links` as well, for mechanical consistency with every other equipment relationship.
- **Trade-offs:** Two different linkage mechanisms for "things related to equipment" instead of one — accepted because the ownership/reference distinction is real and collapsing it would misrepresent the data's actual dependency structure.

**DB-013 — Reserve schema for e-signatures, integrations, billing, and permissions, unbuilt at v1.0**
- **Decision:** `signature_events`, `integration_configs`, `api_keys`, `subscriptions`/`plans`/`invoices`, `permissions`/`role_permissions`, and `external_system_id` columns are declared in this document but not implemented (§21).
- **Reason:** Avoids retrofitting linkage columns onto live, regulated-record tables later, and gives each future capability an additive rather than migratory path (`PLATFORM_ARCHITECTURE.md` §25, `PA-016`).
- **Alternative considered:** Design these only when each feature is actually built.
- **Trade-offs:** A small amount of forward-declared schema shape (documented here, not yet created) that could theoretically need revision before it's ever used — a minor, reversible cost.

**DB-014 — Three-phase migration (SQLite → PostgreSQL → Supabase), not a single cutover**
- **Decision:** An intermediate PostgreSQL-on-Staging phase validates schema and RLS correctness before Supabase production cutover (§19.1).
- **Reason:** Separates "does the new schema work on PostgreSQL" from "does the managed platform's specific RLS/Auth integration work correctly" — two different risk categories that a single big-bang cutover would conflate and make harder to debug if something fails.
- **Alternative considered:** Migrate directly from SQLite to Supabase production in one step.
- **Trade-offs:** A longer migration timeline in exchange for a materially lower-risk cutover — accepted given the cost of a tenant-isolation mistake discovered in production (§22) vastly exceeds the cost of an extra staging phase.

**DB-015 — Indexing prioritizes `company_id` + status composite predicates, with GIN full-text and future `pgvector` support**
- **Decision:** Baseline indexing (§14) is built around the platform's actual query shapes (tenant + lifecycle status), not a generic "index everything" approach; full-text search uses GIN now, with `pgvector` reserved for semantic search.
- **Reason:** These are the columns every RLS policy and every real list/search query actually filters on (§13, §14); `pgvector`'s native Supabase support means semantic search requires no new infrastructure decision when v1.1 arrives.
- **Alternative considered:** A dedicated external search/vector database from v1.0.
- **Trade-offs:** Postgres full-text search is less capable than a purpose-built search engine at very high scale — an accepted, explicitly time-boxed limitation (§14.4, §24 of `PLATFORM_ARCHITECTURE.md`) revisited only if profiling actually demands it.

**DB-016 — `company_id` foreign keys are never `ON DELETE CASCADE`**
- **Decision:** No table in this schema automatically cascades a delete from `companies` — company offboarding is a separate, explicit, controlled procedure, never a side effect of one DELETE statement.
- **Reason:** The blast radius of an accidental or mistaken company deletion — potentially millions of rows across every tenant-scoped table — is too large to leave to an automatic cascade (§5.3, §23).
- **Alternative considered:** `CASCADE` for simplicity, relying on application-layer confirmation dialogs to prevent accidents.
- **Trade-offs:** Company offboarding requires a dedicated, explicitly-designed purge runbook/procedure rather than a single database operation — a deliberate friction, not an oversight.

---

*This document is the frozen database architecture for PharmaGPT's multi-tenant SaaS platform, subordinate to and fully compatible with `PLATFORM_ARCHITECTURE.md`. Any future change to a decision in §24 requires a new, explicitly numbered entry — superseding, not silently editing, the original — matching the same discipline `PLATFORM_ARCHITECTURE.md` §33 already established for the platform as a whole.*

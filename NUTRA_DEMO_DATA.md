# Nutra Demo Tenant

Demo seed data for end-to-end PharmaGPT testing — a complete, realistic pharmaceutical/nutraceutical
company with departments, users, and workflow roles spanning the full approval hierarchy.

Seeded by [`scripts/seed_nutra_demo.py`](scripts/seed_nutra_demo.py), which is idempotent and safe
to rerun. Backing schema: [`migrations/0014_nutra_demo_schema_up.sql`](migrations/0014_nutra_demo_schema_up.sql)
(documented in [`DATABASE.md`](DATABASE.md#organizational-model-departments-workflow-roles-module-permissions--added-2026-07-28)).

```bash
python scripts/seed_nutra_demo.py           # create or update the Nutra tenant
python scripts/seed_nutra_demo.py --reset   # remove Nutra's demo users/departments, then reseed
```

## Company

| Field | Value |
|---|---|
| Legal name | Nutra |
| Industry segment | `nutraceutical` |

## Departments

Seven departments, each with a stable code (the idempotency key — the display name may change
without breaking lookups):

| Department | Code |
|---|---|
| Quality Assurance | `QA` |
| Production | `PROD` |
| Warehouse | `WH` |
| PPIC | `PPIC` |
| Engineering | `ENG` |
| Quality Control | `QC` |
| Validation | `VAL` |

Plant Head is not tied to any single department (a plant-wide role) — that user has no
`user_departments` row.

## Workflow hierarchy

Five organizational job titles (`workflow_roles`, migration 0014), each carrying capability flags:

| Workflow role | Sequence | Can start | Can review | Can approve | Final approver |
|---|---|---|---|---|---|
| Initiator | 10 | Yes | No | No | No |
| Coordinator | 20 | Yes | Yes | No | No |
| Reviewer | 30 | No | Yes | No | No |
| Approver | 40 | No | No | Yes | No |
| Plant Head | 50 | No | No | Yes | Yes |

**Future capability, not yet enforced.** These flags are recorded and queryable
(`pharmagpt/services/org_directory.py::get_workflow_role_id`) but are **not** consulted by
`pharmagpt/services/workflow_engine.py`, which continues to decide step eligibility exactly as
before (via each workflow template step's own `eligible_roles`/named-approver assignment). This is
organizational metadata layered alongside the Workflow Engine, not a change to it.

## Role mapping (Likely — a documented judgment call)

Platform RBAC (`roles`, migration 0001) is frozen at 4 rows and is **not** extended by this work.
Every Nutra user still resolves to a real platform role:

| Workflow role | Platform role (`roles.name`) | Why |
|---|---|---|
| Initiator | `user` | "Authors and edits documents within assigned Projects" — matches. |
| Coordinator | `reviewer_qa` | "Reviews and approves/rejects documents" — matches. |
| Reviewer | `reviewer_qa` | Same. |
| Approver | `reviewer_qa` | Same. |
| Plant Head | `reviewer_qa` | Same — highest approval authority, still not `company_admin`. |

No Nutra user is ever assigned `company_admin` or `super_admin`. `company_admin` grants
platform tenant-owner powers (managing Users, Settings, Knowledge Base, Equipment, Projects) that
no demo persona here needs — mapping a business title like "Plant Head" onto that role would be a
real over-grant, not a naming choice.

## Users

Password for every account: **`Qazwsx@123`**. Set only when an identity is first created —
**reruns of the seed script never reset an existing user's password.**

| Email | Display name | Department | Workflow role | QMS | Validation | Doc Generator |
|---|---|---|---|:---:|:---:|:---:|
| c@nutra.com | Coordinator | Quality Assurance | Coordinator | ✓ | ✓ | ✓ |
| qr@nutra.com | Quality Reviewer | Quality Assurance | Reviewer | ✓ | ✓ | ✓ |
| qh@nutra.com | Quality Head | Quality Assurance | Approver | ✓ | ✓ | ✓ |
| qi@nutra.com | Quality Initiator | Quality Assurance | Initiator | ✓ | | ✓ |
| pi@nutra.com | Production Initiator | Production | Initiator | ✓ | | ✓ |
| pr@nutra.com | Production Reviewer | Production | Reviewer | ✓ | ✓ | ✓ |
| ph@nutra.com | Production Head | Production | Approver | ✓ | ✓ | ✓ |
| wi@nutra.com | Warehouse Initiator | Warehouse | Initiator | ✓ | | ✓ |
| wr@nutra.com | Warehouse Reviewer | Warehouse | Reviewer | ✓ | ✓ | ✓ |
| wh@nutra.com | Warehouse Head | Warehouse | Approver | ✓ | ✓ | ✓ |
| ppi@nutra.com | PPIC Initiator | PPIC | Initiator | ✓ | | ✓ |
| ppr@nutra.com | PPIC Reviewer | PPIC | Reviewer | ✓ | | ✓ |
| pph@nutra.com | PPIC Head | PPIC | Approver | ✓ | | ✓ |
| ei@nutra.com | Engineering Initiator | Engineering | Initiator | ✓ | | ✓ |
| er@nutra.com | Engineering Reviewer | Engineering | Reviewer | ✓ | ✓ | ✓ |
| eh@nutra.com | Engineering Head | Engineering | Approver | ✓ | ✓ | ✓ |
| qci@nutra.com | QC Initiator | Quality Control | Initiator | ✓ | | ✓ |
| qcr@nutra.com | QC Reviewer | Quality Control | Reviewer | ✓ | ✓ | ✓ |
| qch@nutra.com | QC Head | Quality Control | Approver | ✓ | ✓ | ✓ |
| vi@nutra.com | Validation Initiator | Validation | Initiator | ✓ | ✓ | ✓ |
| vr@nutra.com | Validation Reviewer | Validation | Reviewer | ✓ | ✓ | ✓ |
| vh@nutra.com | Validation Head | Validation | Approver | ✓ | ✓ | ✓ |
| plh@nutra.com | Plant Head | *(none)* | Plant Head | ✓ | ✓ | ✓ |

23 users total.

## Module permissions

Recorded per user in `user_module_permissions` (keyed on `modules.code`: `QMS`, `VALIDATION`,
`DOCUMENT_GENERATOR`) via `pharmagpt/services/module_permissions.py`. Real, normalized, queryable
data — see **Scope boundary** below for what it does not (yet) do.

## Intended testing scenarios

- **Initiator-only view** — log in as `qi@nutra.com` (Quality Initiator) to see a QMS-only,
  Validation-disabled account with `role_id` = `user`.
- **Reviewer/Approver views** — `qr@nutra.com` / `qh@nutra.com` to compare a Reviewer's and an
  Approver's workflow-role capability flags against the same platform role (`reviewer_qa`).
- **Cross-department comparison** — `ppr@nutra.com` (PPIC Reviewer, Validation disabled) vs.
  `vr@nutra.com` (Validation Reviewer, Validation enabled): same workflow role, same platform role,
  different module access — the concrete case that requires `user_module_permissions` to be
  user-scoped rather than role-scoped.
- **Highest authority** — `plh@nutra.com` (Plant Head) to exercise the top of the org hierarchy,
  with no department tie.
- **Full-suite Coordinator** — `c@nutra.com`, the one user with all three modules enabled and a
  Coordinator workflow role, useful as a general-purpose demo login.
- **Reset between demo runs** — `python scripts/seed_nutra_demo.py --reset` clears only Nutra's 23
  users and 7 departments (never the `companies` row, never another tenant) and immediately reseeds.

## Scope boundary

This organizational model is **recorded and queryable, not yet enforced**:

- `user_module_permissions` is not consulted by any route's `@require_role` check. Module-level
  UI/API gating (e.g. hiding the Validation Suite for a user with `VALIDATION = false`) is a
  deliberate future step, not part of this change.
- `workflow_roles`' capability flags (`can_start_workflow`, `can_review`, `can_approve`,
  `is_final_approver`) are not consulted by `pharmagpt/services/workflow_engine.py`. Step eligibility
  continues to be decided exactly as before this change — by each workflow template step's own
  `eligible_roles` (matched against the platform `roles.name`) or named per-instance approver
  assignment.
- `department_id`/`user_departments` is organizational membership only — no route currently filters
  data by department.

Existing users, routes, RBAC, and the Workflow Engine are entirely unaffected by this schema; every
Nutra user is additive demo data layered on top of the same authentication and authorization
architecture every other tenant uses.

# Validation Evidence — Audit Trail Matrix

**Full detail:** `docs/AUDIT_TRAIL_COVERAGE_REPORT.md`.

## Required fields — schema evidence

| Field | Column | Status |
|---|---|---|
| Timestamp | `created_at` | Pre-existing |
| User | `performed_by` | Pre-existing, now always server-derived (never client-supplied) |
| Company | `company_id` | **New** (Phase F) |
| Object Type | `record_type` | Pre-existing |
| Object ID | `record_id` | Pre-existing |
| Action | `action` | Pre-existing |
| Old Value | `old_values` | **New** (Phase F), diff-computed |
| New Value | `new_values` | **New** (Phase F), diff-computed |
| Reason | `reason` | **New** (Phase F) |
| Session/IP | `session_id`, `ip_address` | **New** (Phase F) |
| Result | `result` | **New** (Phase F), success/failure |

## Coverage by domain (create / update / delete / approval)

| Domain | Coverage | Verification |
|---|---|---|
| Project | Full (pre-existing, upgraded) | Code read |
| Equipment | Full — **new** | 3 automated tests (create/update/delete) |
| URS | Full — **new** (update/delete/review/version); approval pre-existing | Code read |
| Qualification / Protocols / IQ / OQ / PQ | Full — **new** | Code read |
| Validation Report | Full — **new** | Code read |
| QMS Document | Full — **new** (update/delete/generate/version); create/approval upgraded | Code read |
| Deviation | Full — **new** (update/delete/investigation); create/approval upgraded | Code read |
| CAPA | Full — **new** (update/delete/escalation); create/approval upgraded | Code read |
| Change Control | Full — **new** (update/delete); create/approval upgraded | Code read |
| Risk Assessment | Full — **new** (update/delete/publish); create/approval upgraded | Code read |
| Knowledge Base | Create/delete — **new** | Code read |
| Attachments/Comments (shared) | Comment create — **new**; attachment upload upgraded, delete — **new** | 1 automated test (comment non-spoofability) |
| Project Documents | Delete — **new** | Code read |
| Users (Postgres) | Invite/update — **new**, best-effort | Code read only — **cannot be verified as landing live**, see below |
| Companies (Postgres) | Create/suspend/reactivate — **new**, best-effort | Code read only — **cannot be verified as landing live**, see below |

**Known, disclosed limitation:** Users/Companies audit writes go through the pre-existing Postgres `audit_trail` table, whose own GRANTs are not confirmed active in the live database (see A1/C1). The code is correct and wrapped in try/except so a logging failure never blocks the primary action, but whether it **actually writes today** is marked NOT VERIFIED pending that separate operational fix.

**Not extended in Phase F (documented, not overlooked):** individual URS-requirement / qualification-test-case / QMS-document-distribution-and-training sub-record CRUD remain unaudited at the field level — these are line items inside an already-audited parent record.

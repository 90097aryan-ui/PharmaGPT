# Validation Evidence — RBAC Matrix

**Full detail:** `docs/RBAC_VERIFICATION_REPORT.md`.

**Actual role set (corrects the brief's terminology):** `super_admin` | `company_admin` | `reviewer_qa` | `user`.

| Action class | Guard | Verified by |
|---|---|---|
| Authentication (all routes except exempt list) | `auth/middleware.py` before_request hook | Live 401 checks in Phase E + code read |
| Create / generate (any module) | Open to any authenticated role — deliberate, consistent pattern | Code read across all modules |
| Update (most modules) | Open to any authenticated role, but scoped to caller's company | Code read |
| Delete (every module) | `@require_role("company_admin")` | Code read, pre-existing |
| Approval / status transition (every module) | `@require_role("company_admin","reviewer_qa")` | Code read, pre-existing |
| Risk `/publish` | **Fixed this phase**: `@require_role("company_admin","reviewer_qa")` + status check | Automated test |
| Qualification protocol `/complete` | **Fixed this phase**: `@require_role("company_admin","reviewer_qa")` | Automated test |
| CAPA action `/escalate` | **Fixed this phase**: `@require_role("company_admin","reviewer_qa")` | Automated test |
| Super-admin-only routes (`/auth/companies`, `/companies/*`, `/auth/assume-company`) | `@require_role("super_admin")` | Code read, pre-existing |
| Company_admin/super_admin self-escalation to `super_admin` role | Blocked server-side (`role_id=1` rejected) + DB trigger | Code read, pre-existing |

**Reviewed, deliberately not changed:** QMS document distribution/training record endpoints (routine record-keeping, not a QA sign-off — see `docs/RBAC_VERIFICATION_REPORT.md` §4 for the reasoning against guessing an unverified business rule).

**Not performed:** live credentialed privilege-escalation testing (disclosed hard constraint — see `PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md` §0). Automated `pytest`-level equivalent added instead (4 tests, all passing).

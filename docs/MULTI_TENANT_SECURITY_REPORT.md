# Multi-Tenant Security Report — Phase F, Work Package 5

**Scope:** Verify every query (ORM/SQL/API/search/reports/exports/audit logs) includes `company_id` scoping; ensure Company A can never retrieve Company B's data. Method: direct re-read of every route file's data-access pattern in this session (not assumed from Phase E), cross-checked against the schema.

## 1. Enforcement mechanism (re-verified)

Every SQLite-backed route resolves its scoping value from `g.tenant.company_id` — populated server-side by `pharmagpt/auth/middleware.py` from the verified Supabase access token, **never** from request body/query/header — and passes it through `pharmagpt/tenancy.py::scoped_or_none()` (single-record reads: 404, not 403, on a cross-company id, so a probing request can't distinguish "wrong company" from "doesn't exist" — closes an enumeration side-channel) or as an explicit `company_id` filter argument on every list/search query. This pattern was re-confirmed, file by file, across every route touched in Work Packages 2–4 (`equipment.py`, `urs.py`, `qual.py`, `report.py`, `risk.py`, `qms_documents.py`, `qms_deviations.py`, `qms_capa.py`, `qms_change_control.py`, `knowledge_base.py`, `projects.py`, `docs.py`, `chat.py`, `dashboard.py`), plus `qms_common.py`'s shared attachments/comments/audit-trail/approval endpoints.

## 2. Schema-level company_id coverage — corrects a stale Phase E citation

Phase E's report (§4, citing a prior, now-outdated `SECURITY_REVIEW.md`) stated the live SQLite path had "no company_id column anywhere." **This session verified directly against `pharmagpt/database.py`'s migration block that this is no longer true** — `company_id` columns exist and are backfilled (to a bootstrap company for pre-migration legacy rows, never left NULL/orphaned) on: `projects`, `kb_documents`, `risk_assessments`, `risk_library`, `urs_projects`, `qual_qualifications`, `val_reports`, `qms_documents`, `qms_deviations`, `qms_capas`, `qms_change_controls`. `equipment` is deliberately scoped by joining through its owning Project's `company_id` rather than carrying its own column (`equipment_database.py::get_equipment_scoped()` — a documented, consistent design choice, not a gap). This correction is carried into `docs/PHASE_F_FINDING_TRACEABILITY.md`.

## 3. Shared polymorphic tables (attachments/comments/audit-trail/approvals)

`qms_attachments`, `qms_comments`, `qms_audit_trail`, `qms_approvals` are keyed only by `(record_type, record_id)` with no `company_id` column of their own — isolation for these depends entirely on `qms_common.py::_record_exists()` re-validating that the *parent* record belongs to the caller's company before any attachment/comment/audit-trail/approval read or write. Re-verified in this session (this function was directly edited in Work Package 2 to add `urs`/`equipment`/`kb_document` as new record types — see `docs/AUDIT_TRAIL_COVERAGE_REPORT.md`) — every new record type added routes through the same check, no exception introduced.

**Audit trail's own schema gap, noted for completeness (see also C5 in the Phase E report):** the newly-added `company_id` column on `qms_audit_trail` (Work Package 2) is populated from `g.tenant.company_id` at write time, but the table itself is still not directly filterable by company for a cross-tenant admin view (reads always go through the per-record `/qms/<type>/<id>/audit-trail` endpoint, which is already tenant-scoped via `_record_exists()`) — this is adequate for the current UI (no company-wide audit log browser exists) but would need a dedicated index/query path if such a view is ever built.

## 4. Search / list / dashboard endpoints

Every list/search/dashboard endpoint reviewed passes `g.tenant.company_id` as a required filter, and every one explicitly rejects the request (403, "Super Admin has no standing access to tenant content") rather than falling through to an unscoped query when `g.tenant.company_id` is `None` (i.e., an unassumed Super Admin session) — re-confirmed across `dashboard.py`, `urs.py`, `qual.py`, `report.py`, `risk.py`, `qms_common.py`, `qms_documents.py`, `qms_deviations.py`, `qms_capa.py`, `qms_change_control.py`, `equipment.py`, `knowledge_base.py`.

## 5. DOCX/export endpoints

Every export endpoint reviewed (`urs.py::export_docx`, `qual.py::export_protocol_docx`/`export_traceability_docx`, `report.py::export_docx`, `qms_documents.py::export_docx`) fetches its source record via `tenancy.scoped_or_none()` (or `_scoped_protocol()`, which chains the same check) before generating the file — no export path was found that bypasses tenant scoping to read a record.

## 6. Postgres/Supabase path (Users, Companies, Assume Company Context)

- `routes/users.py`: Company Admin path uses `get_authenticated_client()` (RLS-scoped by the caller's own JWT). Super Admin path (only reachable with an active Assume Company Context grant) uses the service-role client but applies an explicit `.eq("company_id", ...)` filter using `g.tenant.company_id`, which middleware only ever sets non-None for a super_admin after verifying a live grant — re-confirmed by direct code read in this session (also flagged in Phase E as "relies on Postgres RLS, not independently re-verified" for the Company Admin path specifically; this session did not independently re-verify the RLS policy SQL itself either — carried forward as the same open caveat, not newly resolved).
- `routes/companies.py`: all four routes are `@require_role("super_admin")`-only; `suspend_company`/`reactivate_company` take a `company_id` from the URL path as a legitimate target-resource id under that guard, not as a trusted identity/scoping field from an untrusted caller.

**Not independently verified in this session** (same disclosed limitation as Phase E, unchanged): a live 2-company RLS isolation spot-check against the deployed Supabase project. This requires two real company accounts and a live database session neither Phase E nor this session had access to — tracked in `docs/PHASE_F_FINDING_TRACEABILITY.md` as an operational item, not something a code-level session can close.

## 7. New finding this session — Low severity, disclosed rather than fixed

**`pharmagpt/review/review_engine.py`'s `_score_cache`** (backing `GET /dashboard/validation-score`) is a **process-global, non-tenant-scoped, in-memory dictionary** keyed by a content hash, not by company. Any two companies' users hitting the same server process share one running average — the "Avg Validation Score" dashboard tile for Company A is influenced by documents Company B reviewed in the same process lifetime.

**Assessed severity: Low, not a release blocker.** The leak is a single aggregate float, not a document, record, or any identifying content — the content-hash key is not reversible to the source document, and the module's own docstring already scopes this explicitly as "across all reviewed documents in this session" (i.e., an already-disclosed, session-level statistic, not a per-company one) rather than a silently-broken tenant boundary. Fixing it properly would mean threading `company_id` through the review-scoring call chain (`services/qms_document_service.py` and every module that calls `run_review`/`get_score_cache`) — a change with a larger blast radius than "add a check," and not something this session found evidence was expected to already be tenant-scoped. **Disclosed here, not fixed in this session** — recommended as a scoped follow-up (either make the cache company-keyed, or remove the dashboard tile's cross-tenant implication by making it explicitly per-session/per-browser rather than server-process-wide).

## 8. Summary

| # | Area | Status |
|---|---|---|
| 1 | SQLite schema company_id coverage | Verified present and backfilled on all 10 tenant tables + equipment's join-based scoping |
| 2 | Application-layer scoping on every route touched in WP2-4 | Verified — no route trusts client-supplied company_id |
| 3 | Shared polymorphic tables (attachments/comments/audit/approvals) | Verified — `_record_exists()` re-checked, new record types added correctly |
| 4 | List/search/dashboard endpoints | Verified — no unscoped fallback found |
| 5 | Export endpoints | Verified — every export fetches its source via a scoped getter |
| 6 | Postgres Users/Companies path | Verified at the application-layer-filter level; RLS policy SQL itself and a live 2-company spot-check remain **NOT VERIFIED**, same as Phase E |
| 7 | `_score_cache` dashboard statistic | **New finding, Low severity, disclosed and NOT fixed** — process-global, not company-scoped |

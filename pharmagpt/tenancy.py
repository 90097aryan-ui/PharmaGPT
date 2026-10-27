"""
pharmagpt/tenancy.py — tenant-isolation enforcement for the SQLite-backed
live routes.

Context: pharmagpt/database.py and its siblings (risk_database.py,
urs_database.py, qual_database.py, report_database.py, qms_database.py,
equipment_database.py) predate multi-tenancy — they were built before
company_id existed anywhere in the app. The Postgres/Supabase side
(pharmagpt/db/*_repo.py) already enforces company_id via RLS for its
Phase 3 dual-write tables, but SQLite remains the sole source of truth for
every domain today (every *_BACKEND flag in config.py still defaults to
"sqlite" — see docs/PHASE3_FLAGS.md), so RLS never runs for a live request.
This module is the equivalent enforcement point for that SQLite path.

BOOTSTRAP_COMPANY_ID exists so pre-existing rows (created before this
column existed) have somewhere valid to land instead of becoming globally
inaccessible or globally visible — it is the same bootstrap company Postgres
already uses (scripts/backfill_projects.py's find_or_create_bootstrap_company,
confirmed present in Supabase as "PharmaGPT Bootstrap Company
(pre-migration data)"), so legacy data lines up with the same tenant
identity on both sides of the dual-write.
"""

BOOTSTRAP_COMPANY_ID = "52df3b4a-d37e-4176-8a52-7171adf39637"


def signing_identity(tenant) -> dict:
    """Return the non-spoofable identity fields for an e-signature/approval
    entry — performed_by, role, and electronic_sig — always derived from
    the authenticated TenantContext, never from client-supplied JSON.

    Context: several QMS/Risk/Qualification/Report approval endpoints
    accepted `performed_by`, `role`, and `electronic_sig` as free-text
    fields straight from the request body, so any authenticated caller
    could submit an approval/e-signature entry claiming to be anyone —
    undermining the legal validity of the GxP audit trail itself (see
    SECURITY_REVIEW.md). This app has no separate password-reentry or
    cryptographic signing step, so the strongest non-spoofable attestation
    available is "this action was taken by the identity that authenticated
    this HTTP session" — exactly what TenantContext already represents.
    `electronic_sig` is set to the same identity string rather than an
    arbitrary client-supplied value, closing the impersonation vector
    completely rather than narrowing it.
    """
    name = tenant.display_name or tenant.email
    return {"performed_by": name, "role": tenant.role, "electronic_sig": name}


def missing_or_inactive_users(client, company_id: str, user_ids: set) -> set:
    """CRIT-02 (Security Audit remediation): which of `user_ids` do NOT
    correspond to a real, active user of `company_id` right now — so a
    workflow-step-assign endpoint (routes/qms_capa.py, qms_change_control.py,
    qms_deviations.py) can reject naming a user from a different company (or
    a deactivated/nonexistent one) as an approver for a record it doesn't
    belong to. `client` is caller-supplied (each route already imports
    `get_service_role_client` at module level for this exact purpose — see
    routes/qms_deviations.py::_missing_or_inactive_approvers, whose query
    shape this mirrors exactly) rather than obtained here, so each route's
    existing test-mocking convention (`monkeypatch.setattr("pharmagpt.
    routes.<module>.get_service_role_client", ...)`) keeps working
    unchanged — this function only centralizes the shared query logic, not
    which client instance answers it.

    Uses the service-role client with an explicit company_id filter, same
    reasoning as routes/users.py::list_users_directory(): RLS on `users`
    doesn't grant a non-admin caller read access to their company-mates'
    rows at all, so a plain per-caller client can't answer this query."""
    if not user_ids:
        return set()
    active = (
        client.table("users").select("id")
        .eq("company_id", company_id).eq("status", "active").execute()
    ).data or []
    active_ids = {row["id"] for row in active}
    return {uid for uid in user_ids if uid not in active_ids}


def scoped_or_none(record: dict | None, company_id: str | None) -> dict | None:
    """Return `record` only if it exists and its company_id matches the
    caller's. Otherwise return None — callers should treat that identically
    to "not found" (404), never a distinct "forbidden" message, so a probing
    request can't distinguish "wrong company" from "no such id" and enumerate
    other companies' valid ids.

    `company_id` must come from the authenticated TenantContext
    (`g.tenant.company_id`), never from client input (query string, JSON
    body, header) — that is the exact class of bug this module exists to
    close.
    """
    if not record or not company_id:
        return None
    if record.get("company_id") != company_id:
        return None
    return record

"""
routes/companies.py — Company Administration (Phase 3.5).

Routes
------
GET  /companies                     list all companies
POST /companies                     create a company + its first Company Admin
POST /companies/<id>/suspend        set status = 'suspended'
POST /companies/<id>/reactivate     set status = 'active'

Standing Super Admin capability — PLATFORM_ARCHITECTURE.md §7 explicitly
lists "creates companies and their first Company Admin" as a standing power,
distinct from viewing an existing company's ongoing business content (which
requires Assume Company Context, routes/auth.py::assume_company). Every
route here is @require_role("super_admin"); a company_admin's own read-only
visibility into their own company row is enforced by RLS
(migrations/0011_companies_admin_rls_up.sql), not by any route in this file.
"""

import json
import logging
import re

from flask import Blueprint, g, jsonify, request

from pharmagpt import audit_events as evt
from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import org_structure_repo, qms_repo, rbac_repo
from pharmagpt.services.identity_admin import IdentityProvisioningError, provision_user
from pharmagpt.services.supabase_client import (
    get_authenticated_client,
    get_service_role_client,
    handle_postgrest_errors,
)

bp = Blueprint("companies", __name__)
logger = logging.getLogger(__name__)


def _audit_best_effort(action: str, company_id: str, reason: str = "") -> None:
    """Phase F (WP2): best-effort audit entry, mirroring routes/users.py's
    helper. The record's company_id is the *target* company (a Super Admin
    action has no company_id of their own — g.tenant.company_id is always
    None for super_admin outside an Assume Company Context grant).

    Yuktav P0-4 policy (see FINAL REPORT §D for the full rationale): kept
    best-effort for events that create or describe state rather than
    revoking/granting an existing principal's access — company creation
    (the company row + its own created_at is itself durable evidence even
    if this specific audit_trail row fails to write), the RBAC/org-defaults
    provisioning sub-step (already a best-effort step by design), and
    branding updates (cosmetic, non-access data). Company suspend/reactivate
    are NOT best-effort — see `_audit_fail_closed` below."""
    try:
        qms_repo.add_audit_entry(
            extract_bearer_token(), company_id, "company", str(company_id),
            action, actor_user_id=g.tenant.user_id, reason=reason or None,
        )
    except Exception:
        logger.exception("Phase F audit: failed to write company audit entry (%s)", action)


def _audit_fail_closed(action: str, company_id: str, reason: str = "") -> None:
    """Yuktav P0-4: fail-closed counterpart to `_audit_best_effort` above,
    used only for company suspend/reactivate — a suspension gates access for
    every user in that company, and a reactivation restores it; either one
    happening without a durable audit record is a material compliance gap
    (an admin could silently cut off, or silently restore, an entire
    tenant's access). Deliberately does NOT catch the exception here: the
    caller is responsible for aborting the mutation if this raises, so the
    state change can never complete without a corresponding audit row. See
    FINAL REPORT §D for the full classification."""
    qms_repo.add_audit_entry(
        extract_bearer_token(), company_id, "company", str(company_id),
        action, actor_user_id=g.tenant.user_id, reason=reason or None,
    )


VALID_INDUSTRY_SEGMENTS = {
    "pharma", "nutraceutical", "medical_device", "biotech", "cdmo", "cro",
}


def _get_role_id(client, role_name: str) -> int | None:
    result = client.table("roles").select("id").eq("name", role_name).maybe_single().execute()
    row = result.data if result else None
    return row["id"] if row else None


@bp.route("/companies", methods=["GET"])
@require_role("super_admin")
@handle_postgrest_errors
def list_companies():
    client = get_authenticated_client(extract_bearer_token())
    result = client.table("companies").select("*").order("legal_name").execute()
    return jsonify(result.data or [])


@bp.route("/companies", methods=["POST"])
@require_role("super_admin")
@handle_postgrest_errors
def create_company():
    """Body: {legal_name, industry_segment, plan_tier?, admin_email, admin_display_name}

    Creates the company row, then provisions its first Company Admin in the
    same call. If company creation succeeds but admin provisioning fails,
    the response says so explicitly (the company is NOT rolled back —
    Supabase has no cross-call transaction here — so the caller can retry
    provisioning against the now-existing company rather than getting a
    silent partial failure)."""
    data = request.get_json(silent=True) or {}
    legal_name = (data.get("legal_name") or "").strip()
    industry_segment = (data.get("industry_segment") or "").strip()
    admin_email = (data.get("admin_email") or "").strip()
    admin_display_name = (data.get("admin_display_name") or "").strip()

    if not legal_name:
        return jsonify({"error": "legal_name is required"}), 400
    if industry_segment not in VALID_INDUSTRY_SEGMENTS:
        return jsonify({"error": f"industry_segment must be one of: {', '.join(sorted(VALID_INDUSTRY_SEGMENTS))}"}), 400
    if not admin_email or not admin_display_name:
        return jsonify({"error": "admin_email and admin_display_name are required"}), 400

    client = get_authenticated_client(extract_bearer_token())

    company_payload = {"legal_name": legal_name, "industry_segment": industry_segment}
    if data.get("plan_tier"):
        company_payload["plan_tier"] = data["plan_tier"]

    inserted = client.table("companies").insert(company_payload).execute()
    company_row = (inserted.data or [None])[0]
    if not company_row:
        return jsonify({"error": "Could not create company"}), 500

    company_admin_role_id = _get_role_id(client, "company_admin")
    if not company_admin_role_id:
        return jsonify({
            "company": company_row,
            "error": "Company created, but no 'company_admin' role row exists — "
                     "has migrations/0001_identity_tenancy_up.sql been applied?",
        }), 500

    try:
        provisioned = provision_user(
            email=admin_email, display_name=admin_display_name,
            company_id=company_row["id"], role_id=company_admin_role_id,
        )
    except IdentityProvisioningError as exc:
        logger.exception("create_company: admin provisioning failed for company %s", company_row["id"])
        return jsonify({
            "company": company_row,
            "error": f"Company created, but admin provisioning failed — retry provisioning "
                     f"for company {company_row['id']}: {exc}",
        }), 500

    # RBAC framework (migration 0015): seed this company's default
    # departments/approval-levels/role set. Best-effort — a failure here
    # must not block company creation (the company and its admin already
    # exist); the Company Admin can retry from the new Role Management UI,
    # or a service-role script can re-run provision_org_defaults_for_company
    # for this company_id. Not audited via rbac_audit_log itself (there is
    # no acting human "reason" for an automatic provisioning step) —
    # subsequent edits to these seeded rows are audited normally.
    try:
        provisioning_summary = org_structure_repo.provision_org_defaults_for_company(client, company_row["id"])
        company_admin_rbac_role = next(
            (r for r in client.table("rbac_roles").select("id, name")
             .eq("company_id", company_row["id"]).eq("name", "Company Admin").execute().data or []),
            None,
        )
        if company_admin_rbac_role:
            rbac_repo.assign_user_role(
                client, provisioned["auth_user_id"], company_admin_rbac_role["id"], company_row["id"],
            )
    except Exception:
        logger.exception("create_company: RBAC/org defaults provisioning failed for company %s", company_row["id"])
        provisioning_summary = None
        # Wave 4B: this specific sub-step (unlike the rest of company
        # creation) previously had zero audit coverage of its own — see the
        # comment above this try/except. A server-derived, no-client-input
        # failure event is safe to add without touching rbac_audit_log or
        # the RBAC provisioning logic itself.
        _audit_best_effort(evt.RBAC_DEFAULTS_PROVISIONED, company_row["id"], reason="failed — see server logs")
    else:
        _audit_best_effort(evt.RBAC_DEFAULTS_PROVISIONED, company_row["id"], reason="succeeded")

    _audit_best_effort("Company created", company_row["id"], reason=legal_name)
    return jsonify({
        "company": company_row,
        "admin": {
            "email": admin_email,
            "display_name": admin_display_name,
            "temporary_password": provisioned["temporary_password"],
        },
        "org_defaults_provisioned": provisioning_summary is not None,
    }), 201


@bp.route("/companies/<company_id>/suspend", methods=["POST"])
@require_role("super_admin")
@handle_postgrest_errors
def suspend_company(company_id):
    client = get_authenticated_client(extract_bearer_token())

    # Yuktav P0-4: confirm the target exists BEFORE writing the fail-closed
    # audit entry below — an audit row must never be written for a company
    # that turns out not to exist.
    existing = client.table("companies").select("id").eq("id", company_id).maybe_single().execute()
    if not (existing.data if existing else None):
        return jsonify({"error": "Company not found"}), 404

    try:
        _audit_fail_closed("Company suspended", company_id)
    except Exception:
        logger.exception("Company suspend BLOCKED: audit write failed for company %s", company_id)
        return jsonify({
            "error": "Could not record the required audit entry for this suspension; the "
                     "company was NOT suspended. Retry once the audit trail is writable.",
        }), 500

    result = client.table("companies").update({"status": "suspended"}).eq("id", company_id).execute()
    row = (result.data or [None])[0]
    if not row:
        return jsonify({"error": "Company not found"}), 404
    return jsonify(row)


@bp.route("/companies/<company_id>/reactivate", methods=["POST"])
@require_role("super_admin")
@handle_postgrest_errors
def reactivate_company(company_id):
    client = get_authenticated_client(extract_bearer_token())

    existing = client.table("companies").select("id").eq("id", company_id).maybe_single().execute()
    if not (existing.data if existing else None):
        return jsonify({"error": "Company not found"}), 404

    try:
        _audit_fail_closed("Company reactivated", company_id)
    except Exception:
        logger.exception("Company reactivate BLOCKED: audit write failed for company %s", company_id)
        return jsonify({
            "error": "Could not record the required audit entry for this reactivation; the "
                     "company was NOT reactivated. Retry once the audit trail is writable.",
        }), 500

    result = client.table("companies").update({"status": "active"}).eq("id", company_id).execute()
    row = (result.data or [None])[0]
    if not row:
        return jsonify({"error": "Company not found"}), 404
    return jsonify(row)


# ── Company Branding (Yuktav — Client Company Branding foundation) ──────────
#
# Backed by company_settings (migration 0001), extended additively by
# migration 0017. company_settings carries RLS enabled with zero policies
# (default-deny for both anon and authenticated PostgREST roles — see
# migrations/0001_identity_tenancy_up.sql), so it is reachable only via the
# service-role client, exactly like routes/users.py's identity-admin paths.
# Because RLS cannot scope access here, every query below is explicitly
# filtered by company_id in application code and a company_admin's
# company_id is always taken from the server-derived g.tenant, never from
# the URL — the same discipline routes/users.py already documents and uses.
#
# DOCX injection of these fields, and any change to Document Control, are
# explicitly out of scope for this route (see docs/05_FEATURE_TICKETS.md
# DC-013 and the Phase 1 architecture audit) — this endpoint only stores and
# returns the data.

BRANDING_FIELD_LIMITS = {
    "logo_url": 2048,
    "address": 1000,
    "contact_email": 320,
    "contact_phone": 40,
    "document_numbering_prefix": 20,
}
DOC_NUMBERING_PREFIX_RE = re.compile(r"^[A-Za-z0-9-]+$")
BRANDING_JSON_FIELDS = ("regulatory_identifiers", "branding")
BRANDING_JSON_MAX_KEYS = 20
BRANDING_JSON_MAX_SERIALIZED_LEN = 4000
BRANDING_JSON_MAX_VALUE_LEN = 500


def _validate_branding_payload(data: dict) -> tuple[dict, str | None]:
    """Returns (cleaned_fields, error_message). cleaned_fields contains only
    recognized keys that were actually present in `data`, so a partial PUT
    only updates the fields the caller sent. Mirrors the length/format
    constraints enforced at the database layer by migration 0017 — this is
    defense in depth, not a substitute for the DB CHECK constraints."""
    cleaned: dict = {}

    for field, max_len in BRANDING_FIELD_LIMITS.items():
        if field not in data:
            continue
        value = data[field]
        if value is None:
            cleaned[field] = None
            continue
        if not isinstance(value, str):
            return {}, f"{field} must be a string"
        value = value.strip()
        if len(value) > max_len:
            return {}, f"{field} must be at most {max_len} characters"
        cleaned[field] = value or None

    if "document_numbering_prefix" in cleaned and cleaned["document_numbering_prefix"] is not None:
        if not DOC_NUMBERING_PREFIX_RE.match(cleaned["document_numbering_prefix"]):
            return {}, "document_numbering_prefix may only contain letters, digits, and hyphens"

    for field in BRANDING_JSON_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if value is None:
            cleaned[field] = {}
            continue
        if not isinstance(value, dict):
            return {}, f"{field} must be an object"
        if len(value) > BRANDING_JSON_MAX_KEYS:
            return {}, f"{field} may have at most {BRANDING_JSON_MAX_KEYS} entries"
        for k, v in value.items():
            if not isinstance(k, str) or not isinstance(v, str):
                return {}, f"{field} keys and values must be strings"
            if len(v) > BRANDING_JSON_MAX_VALUE_LEN:
                return {}, f"{field}.{k} must be at most {BRANDING_JSON_MAX_VALUE_LEN} characters"
        if len(json.dumps(value)) > BRANDING_JSON_MAX_SERIALIZED_LEN:
            return {}, f"{field} is too large (max {BRANDING_JSON_MAX_SERIALIZED_LEN} serialized characters)"
        cleaned[field] = value

    return cleaned, None


def _branding_scope_error(company_id: str):
    """Enforces the same scoping rule as routes/users.py::_scoped_client_and_company:
    a company_admin may only ever act on their own company; a super_admin may
    act on any company_id via the path, matching this file's existing
    standing-power pattern for create/suspend/reactivate. Returns a Flask
    error response if forbidden, else None."""
    if g.tenant.role == "company_admin" and g.tenant.company_id != company_id:
        return jsonify({"error": "company_admin may only access their own company's branding"}), 403
    return None


DEFAULT_BRANDING_ROW = {
    "logo_url": None,
    "address": None,
    "contact_email": None,
    "contact_phone": None,
    "regulatory_identifiers": {},
    "document_numbering_prefix": None,
    "branding": {},
}


@bp.route("/companies/<company_id>/branding", methods=["GET"])
@require_role("company_admin", "super_admin")
@handle_postgrest_errors
def get_company_branding(company_id):
    scope_error = _branding_scope_error(company_id)
    if scope_error:
        return scope_error

    client = get_service_role_client()
    result = (
        client.table("company_settings").select("*").eq("company_id", company_id).maybe_single().execute()
    )
    row = result.data if result else None
    if not row:
        # No settings row exists yet for this company — existing companies
        # created before this feature must keep working, so this returns
        # defaults rather than a 404.
        return jsonify({"company_id": company_id, **DEFAULT_BRANDING_ROW})
    return jsonify(row)


@bp.route("/companies/<company_id>/branding", methods=["PUT"])
@require_role("company_admin", "super_admin")
@handle_postgrest_errors
def update_company_branding(company_id):
    scope_error = _branding_scope_error(company_id)
    if scope_error:
        return scope_error

    data = request.get_json(silent=True) or {}
    cleaned, error = _validate_branding_payload(data)
    if error:
        return jsonify({"error": error}), 400
    if not cleaned:
        return jsonify({"error": "No recognized branding fields provided"}), 400

    client = get_service_role_client()
    existing = (
        client.table("company_settings").select("id").eq("company_id", company_id).maybe_single().execute()
    )
    existing_row = existing.data if existing else None

    if existing_row:
        result = client.table("company_settings").update(cleaned).eq("company_id", company_id).execute()
    else:
        result = client.table("company_settings").insert({"company_id": company_id, **cleaned}).execute()
    row = (result.data or [None])[0]
    if not row:
        return jsonify({"error": "Could not save company branding"}), 500

    _audit_best_effort(evt.COMPANY_BRANDING_UPDATED, company_id, reason=", ".join(sorted(cleaned.keys())))
    return jsonify(row)

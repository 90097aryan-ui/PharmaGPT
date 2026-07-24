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

import logging

from flask import Blueprint, g, jsonify, request

from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import qms_repo
from pharmagpt.services.identity_admin import IdentityProvisioningError, provision_user
from pharmagpt.services.supabase_client import get_authenticated_client, handle_postgrest_errors

bp = Blueprint("companies", __name__)
logger = logging.getLogger(__name__)


def _audit_best_effort(action: str, company_id: str, reason: str = "") -> None:
    """Phase F (WP2): best-effort audit entry, mirroring routes/users.py's
    helper. The record's company_id is the *target* company (a Super Admin
    action has no company_id of their own — g.tenant.company_id is always
    None for super_admin outside an Assume Company Context grant)."""
    try:
        qms_repo.add_audit_entry(
            extract_bearer_token(), company_id, "company", str(company_id),
            action, actor_user_id=g.tenant.user_id, reason=reason or None,
        )
    except Exception:
        logger.exception("Phase F audit: failed to write company audit entry (%s)", action)

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
        return jsonify({
            "company": company_row,
            "error": f"Company created, but admin provisioning failed — retry provisioning "
                     f"for company {company_row['id']}: {exc}",
        }), 500

    _audit_best_effort("Company created", company_row["id"], reason=legal_name)
    return jsonify({
        "company": company_row,
        "admin": {
            "email": admin_email,
            "display_name": admin_display_name,
            "temporary_password": provisioned["temporary_password"],
        },
    }), 201


@bp.route("/companies/<company_id>/suspend", methods=["POST"])
@require_role("super_admin")
@handle_postgrest_errors
def suspend_company(company_id):
    client = get_authenticated_client(extract_bearer_token())
    result = client.table("companies").update({"status": "suspended"}).eq("id", company_id).execute()
    row = (result.data or [None])[0]
    if not row:
        return jsonify({"error": "Company not found"}), 404
    _audit_best_effort("Company suspended", company_id)
    return jsonify(row)


@bp.route("/companies/<company_id>/reactivate", methods=["POST"])
@require_role("super_admin")
@handle_postgrest_errors
def reactivate_company(company_id):
    client = get_authenticated_client(extract_bearer_token())
    result = client.table("companies").update({"status": "active"}).eq("id", company_id).execute()
    row = (result.data or [None])[0]
    if not row:
        return jsonify({"error": "Company not found"}), 404
    _audit_best_effort("Company reactivated", company_id)
    return jsonify(row)

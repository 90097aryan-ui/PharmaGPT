"""
routes/users.py — User Management + Role Management (Phase 3.5).

Routes
------
GET   /users              list users in the effective company
POST  /users              invite a new user into the effective company
PATCH /users/<id>         deactivate / reactivate / reassign role
GET   /users/directory    minimal read-only user directory for approver
                           pickers etc. — open to any authenticated tenant
                           member, not just admins (see list_users_directory)

"Effective company" is g.tenant.company_id — for a Company Admin this is
always their own company (unchanged, ordinary case). For a Super Admin it
is only ever non-None when pharmagpt/auth/middleware.py's
apply_assumed_company_context() has already validated an active, unexpired,
unrevoked break_glass_access grant for this session (routes/auth.py::
assume_company) — company_id is NEVER client-supplied here.

Why this file cannot rely on RLS alone for the Super Admin path: Postgres
RLS's auth.uid() always resolves to the caller's OWN real JWT subject — a
Super Admin's own `users` row permanently has company_id = NULL and
role = super_admin, so migrations/0012_users_company_admin_rls_up.sql's
policies (which check the requester's own row) can never match any real
company for them, no matter what Assume Company Context's Flask-session
override sets g.tenant.company_id to. RLS has no visibility into that
Flask-layer override at all. Rather than engineer a way to smuggle the
assumed company into the Postgres JWT/session (out of scope for this
phase), an assumed-context Super Admin's requests here use the
service-role client and apply the SAME g.tenant.company_id scoping the rest
of this app already trusts everywhere else (never client input) — this is
safe specifically because g.tenant.company_id can only be non-None for a
super_admin after middleware.py already verified a live grant. A Company
Admin's requests continue to use the ordinary RLS-scoped
get_authenticated_client() — untouched, unaffected by any of this.

Role Management (Objective 7) is folded in here — no new table, no
permission builder. PATCH /users/<id> accepts {"role_id": 1-4}; the four
rows in `roles` are frozen (migrations/0001_identity_tenancy_up.sql) and
the Postgres trigger chk_users_super_admin_company_null enforces the
super_admin/company_id invariant regardless of what this route sends.
"""

import logging

from postgrest.exceptions import APIError

from flask import Blueprint, g, jsonify, request

from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import qms_repo
from pharmagpt.services.identity_admin import IdentityProvisioningError, provision_user
from pharmagpt.services.supabase_client import get_authenticated_client, get_service_role_client, handle_postgrest_errors

bp = Blueprint("users", __name__)
logger = logging.getLogger(__name__)


def _audit_best_effort(action: str, record_id: str, reason: str = "") -> None:
    """Phase F (WP2): best-effort audit entry into the Postgres-side
    `audit_trail` table (pharmagpt/db/qms_repo.py) for the identity/admin
    routes, which are Postgres-backed and have no SQLite equivalent. Never
    raises — a logging failure must not block a Users/Companies action, and
    per docs/PHASE_F_FINDING_TRACEABILITY.md A1, this table's own
    GRANTs are not currently confirmed active in the live database, so a
    failure here is expected until that operational item is resolved."""
    try:
        qms_repo.add_audit_entry(
            extract_bearer_token(), g.tenant.company_id, "user", str(record_id),
            action, actor_user_id=g.tenant.user_id, reason=reason or None,
        )
    except Exception:
        logger.exception("Phase F audit: failed to write user audit entry (%s)", action)


def _scoped_client_and_company():
    """Return (client, company_id) for the caller's effective company.

    Company Admin: RLS-scoped anon-key client, their own company_id.
    Super Admin (only reachable with an active Assume Company Context grant
    — see module docstring): service-role client, explicitly filtered to
    g.tenant.company_id by every query below (never trusts RLS to do it,
    since service-role bypasses RLS entirely by design).
    """
    if g.tenant.role == "super_admin":
        return get_service_role_client(), g.tenant.company_id
    return get_authenticated_client(extract_bearer_token()), g.tenant.company_id


@bp.route("/users", methods=["GET"])
@require_role("company_admin", "super_admin")
@handle_postgrest_errors
def list_users():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content — "
                                  "assume a company context first"}), 403
    client, company_id = _scoped_client_and_company()
    query = client.table("users").select(
        "id, company_id, role_id, display_name, status, last_login_at, created_at, roles(name)"
    )
    if g.tenant.role == "super_admin":
        query = query.eq("company_id", company_id)
    result = query.execute()
    return jsonify(result.data or [])


@bp.route("/users/directory", methods=["GET"])
@handle_postgrest_errors
def list_users_directory():
    """Minimal, read-only company user directory (user_id, display_name,
    department, designation) for approver pickers etc. — active users only.

    Deliberately open to any authenticated tenant member, not admin-gated
    like GET /users: RLS on `users` only lets a non-admin caller read their
    own row (migration 0002_users_self_select), so an ordinary user's own
    RLS-scoped client can't list their company-mates at all. This uses the
    service-role client instead and applies the SAME g.tenant.company_id
    scoping the rest of this app already trusts everywhere else — never
    client input, never relying on RLS to do it, matching the reasoning in
    this file's module docstring for the Super Admin path above.

    No email: the `users` profile table doesn't store one (Supabase Auth
    owns it) and it isn't needed to identify an approver — this is not a
    user-management surface, just enough to name someone to assign."""
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    company_id = g.tenant.company_id
    client = get_service_role_client()

    users = (
        client.table("users").select("id, display_name, workflow_role_id")
        .eq("company_id", company_id).eq("status", "active").execute()
    ).data or []
    roles_by_id = {
        r["id"]: r["name"] for r in (client.table("workflow_roles").select("id, name").execute().data or [])
    }
    departments_by_id = {
        d["id"]: d["name"]
        for d in (client.table("departments").select("id, name").eq("company_id", company_id).execute().data or [])
    }
    primary_department_by_user = {
        ud["user_id"]: ud["department_id"]
        for ud in (
            client.table("user_departments").select("user_id, department_id")
            .eq("company_id", company_id).eq("is_primary", True).execute().data or []
        )
    }

    return jsonify([
        {
            "user_id": u["id"],
            "display_name": u["display_name"],
            "department": departments_by_id.get(primary_department_by_user.get(u["id"]), ""),
            "designation": roles_by_id.get(u.get("workflow_role_id"), ""),
        }
        for u in users
    ])


@bp.route("/users", methods=["POST"])
@require_role("company_admin", "super_admin")
@handle_postgrest_errors
def invite_user():
    """Body: {email, display_name, role_id}. Always scoped to the caller's
    effective company — never client-supplied, matching the
    non-spoofable-identity discipline already used elsewhere
    (pharmagpt/tenancy.py)."""
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content — "
                                  "assume a company context first"}), 403

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    display_name = (data.get("display_name") or "").strip()
    role_id = data.get("role_id")

    if not email or not display_name:
        return jsonify({"error": "email and display_name are required"}), 400
    if role_id not in (2, 3, 4):
        return jsonify({"error": "role_id must be one of 2 (company_admin), 3 (reviewer_qa), 4 (user)"}), 400

    try:
        provisioned = provision_user(
            email=email, display_name=display_name,
            company_id=g.tenant.company_id, role_id=role_id,
        )
    except IdentityProvisioningError as exc:
        return jsonify({"error": str(exc)}), 500

    _audit_best_effort("User invited", provisioned.get("auth_user_id", email), reason=f"role_id={role_id}")
    return jsonify({
        "email": email,
        "display_name": display_name,
        "temporary_password": provisioned["temporary_password"],
    }), 201


@bp.route("/users/<user_id>", methods=["PATCH"])
@require_role("company_admin", "super_admin")
@handle_postgrest_errors
def update_user(user_id):
    """Body may include: {"status": "active"|"deactivated", "role_id": 1-4}.
    role_id=1 (super_admin) is rejected here before it ever reaches Postgres
    — neither a company_admin nor an assumed-context super_admin has a
    legitimate reason to attempt it, and this gives a clean 400 instead of
    relying solely on the DB trigger's exception."""
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content — "
                                  "assume a company context first"}), 403

    data = request.get_json(silent=True) or {}
    updates = {}
    if "status" in data:
        if data["status"] not in ("active", "deactivated"):
            return jsonify({"error": "status must be 'active' or 'deactivated'"}), 400
        updates["status"] = data["status"]
    if "role_id" in data:
        if data["role_id"] not in (2, 3, 4):
            return jsonify({"error": "role_id must be one of 2 (company_admin), 3 (reviewer_qa), 4 (user)"}), 400
        updates["role_id"] = data["role_id"]

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    client, company_id = _scoped_client_and_company()
    query = client.table("users").update(updates).eq("id", user_id)
    if g.tenant.role == "super_admin":
        # service-role bypasses RLS entirely — this app-level filter is the
        # only thing preventing an assumed-context Super Admin from
        # updating a user outside the company they explicitly assumed.
        query = query.eq("company_id", company_id)

    try:
        result = query.execute()
    except APIError as exc:
        return jsonify({"error": f"Could not update user: {exc}"}), 400

    row = (result.data or [None])[0]
    if not row:
        return jsonify({"error": "User not found"}), 404
    _audit_best_effort("User updated", user_id, reason=str(updates))
    return jsonify(row)

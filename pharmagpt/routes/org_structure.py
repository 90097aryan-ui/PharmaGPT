"""
pharmagpt/routes/org_structure.py — Department & Designation Management.

Routes
------
GET   /org/departments            list this company's departments
POST  /org/departments            create a department
PATCH /org/departments/<id>       rename / disable / re-enable a department
GET   /org/designations           list this company's designations
POST  /org/designations           create a designation
PATCH /org/designations/<id>      rename / disable / re-enable a designation
GET   /org/approval-levels        list this company's approval levels (seeded
                                    defaults only — "store levels only", no
                                    workflow logic reads this; see migration
                                    0015's header)

Company-scoped only — same pattern as routes/users.py: Company Admin acts on
their own company; a Super Admin needs an active Assume Company Context
grant (g.tenant.company_id is otherwise None and every route here 403s).
Every mutation writes an immutable rbac_audit_log entry via
pharmagpt/db/rbac_repo.py::add_rbac_audit_entry — a required, non-optional
`reason` field, not best-effort.
"""

from flask import Blueprint, g, jsonify, request

from pharmagpt.auth.decorators import extract_bearer_token
from pharmagpt.auth.rbac import require_rbac_admin_access
from pharmagpt.db import org_structure_repo, rbac_repo
from pharmagpt.services.supabase_client import get_authenticated_client, get_service_role_client, handle_postgrest_errors

bp = Blueprint("org_structure", __name__, url_prefix="/org")


def _scoped_client_and_company():
    """Same RLS/legacy-role caveat as pharmagpt/routes/rbac.py::_scoped_client:
    the departments company_admin write policy (migration 0015) also gates
    on current_user_role_name() = 'company_admin' — the frozen legacy role,
    blind to the new RBAC role system. A caller reaching this module only
    via an active RBAC "Company Admin" assignment (require_rbac_admin_access)
    needs the same service-role-client-plus-app-scoping treatment already
    used for super_admin, or RLS would silently block them."""
    if g.tenant.role != "company_admin":
        return get_service_role_client(), g.tenant.company_id
    return get_authenticated_client(extract_bearer_token()), g.tenant.company_id


def _require_company_context():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content — "
                                  "assume a company context first"}), 403
    return None


def _audit(client, company_id, *, action, department_id=None, reason):
    rbac_repo.add_rbac_audit_entry(
        client, company_id=company_id, actor_user_id=g.tenant.user_id,
        department_id=department_id, reason=f"{action}: {reason}" if reason else action,
    )


@bp.route("/departments", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def list_departments():
    guard = _require_company_context()
    if guard:
        return guard
    client, company_id = _scoped_client_and_company()
    return jsonify(org_structure_repo.list_departments(client, company_id))


@bp.route("/departments", methods=["POST"])
@require_rbac_admin_access
@handle_postgrest_errors
def create_department():
    guard = _require_company_context()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    department_code = (data.get("department_code") or "").strip().upper().replace(" ", "_")
    reason = (data.get("reason") or "").strip()
    if not name or not department_code:
        return jsonify({"error": "name and department_code are required"}), 400
    if not reason:
        return jsonify({"error": "reason is required"}), 400

    client, company_id = _scoped_client_and_company()
    inserted = client.table("departments").insert({
        "company_id": company_id, "name": name, "department_code": department_code,
    }).execute()
    row = inserted.data[0]
    _audit(client, company_id, action="Department created", department_id=row["id"], reason=reason)
    return jsonify(row), 201


@bp.route("/departments/<department_id>", methods=["PATCH"])
@require_rbac_admin_access
@handle_postgrest_errors
def update_department(department_id):
    guard = _require_company_context()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "reason is required"}), 400

    updates = {}
    if "name" in data:
        updates["name"] = (data["name"] or "").strip()
    if "status" in data:
        if data["status"] not in ("active", "disabled"):
            return jsonify({"error": "status must be 'active' or 'disabled'"}), 400
        updates["status"] = data["status"]
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    client, company_id = _scoped_client_and_company()
    row = org_structure_repo.update_department(client, department_id, company_id, updates)
    if not row:
        return jsonify({"error": "Department not found"}), 404
    _audit(
        client, company_id, action="Department updated", department_id=department_id,
        reason=f"{reason} ({updates})",
    )
    return jsonify(row)


@bp.route("/designations", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def list_designations():
    guard = _require_company_context()
    if guard:
        return guard
    client, company_id = _scoped_client_and_company()
    return jsonify(org_structure_repo.list_designations(client, company_id))


@bp.route("/designations", methods=["POST"])
@require_rbac_admin_access
@handle_postgrest_errors
def create_designation():
    guard = _require_company_context()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    reason = (data.get("reason") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not reason:
        return jsonify({"error": "reason is required"}), 400

    client, company_id = _scoped_client_and_company()
    row = org_structure_repo.create_designation(client, company_id, name)
    _audit(client, company_id, action="Designation created", reason=reason)
    return jsonify(row), 201


@bp.route("/designations/<designation_id>", methods=["PATCH"])
@require_rbac_admin_access
@handle_postgrest_errors
def update_designation(designation_id):
    guard = _require_company_context()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "reason is required"}), 400

    updates = {}
    if "name" in data:
        updates["name"] = (data["name"] or "").strip()
    if "status" in data:
        if data["status"] not in ("active", "disabled"):
            return jsonify({"error": "status must be 'active' or 'disabled'"}), 400
        updates["status"] = data["status"]
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    client, company_id = _scoped_client_and_company()
    row = org_structure_repo.update_designation(client, designation_id, company_id, updates)
    if not row:
        return jsonify({"error": "Designation not found"}), 404
    _audit(client, company_id, action="Designation updated", reason=f"{reason} ({updates})")
    return jsonify(row)


@bp.route("/approval-levels", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def list_approval_levels():
    guard = _require_company_context()
    if guard:
        return guard
    client, company_id = _scoped_client_and_company()
    return jsonify(org_structure_repo.list_approval_levels(client, company_id))

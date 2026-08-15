"""
pharmagpt/routes/rbac.py — Role & Permission Management (fine-grained RBAC,
migrations/0015_rbac_org_framework_up.sql). Additive to, and independent of,
the frozen 4-role platform model in routes/users.py.

Routes
------
GET    /rbac/permissions                         the 15x8 permission catalog
GET    /rbac/roles                                list roles (company-owned + templates)
POST   /rbac/roles                                create a role
POST   /rbac/roles/<id>/clone                     clone a role/template
PATCH  /rbac/roles/<id>                           rename / disable / re-enable
GET    /rbac/roles/<id>/permissions               one role's full matrix
PUT    /rbac/roles/<id>/permissions               toggle one matrix cell
GET    /rbac/users/<user_id>/roles                a user's assigned roles
POST   /rbac/users/<user_id>/roles                assign a role
DELETE /rbac/users/<user_id>/roles/<role_id>      revoke a role
GET    /rbac/users/<user_id>/effective-permissions
GET    /rbac/audit                                this company's RBAC audit trail

Two operating modes, mirroring routes/companies.py / routes/users.py:
- company_admin (or an assumed-context super_admin): acts on their own
  company's roles (rbac_roles.company_id = that company).
- super_admin with NO assumed context: acts on global role TEMPLATES
  (rbac_roles.company_id IS NULL) only — "Platform Admin can manage
  platform roles / create default role templates", never standing tenant
  content. User-role assignment and the audit trail always require a
  company context (there is no such thing as a "platform user role").

Every mutation writes an immutable rbac_audit_log entry via
pharmagpt/db/rbac_repo.py::add_rbac_audit_entry — `reason` is required on
every mutating request body, not best-effort.
"""

from flask import Blueprint, g, jsonify, request

from pharmagpt.auth.decorators import extract_bearer_token
from pharmagpt.auth.rbac import require_rbac_admin_access
from pharmagpt.db import rbac_repo
from pharmagpt.services.supabase_client import get_authenticated_client, get_service_role_client, handle_postgrest_errors

bp = Blueprint("rbac", __name__, url_prefix="/rbac")


def _scoped_client():
    """RLS on rbac_roles/rbac_user_roles/rbac_role_permissions/rbac_audit_log
    (migrations/0015_rbac_org_framework_up.sql) all gate on
    current_user_role_name() = 'company_admin', which resolves strictly
    from the frozen LEGACY role (users.role_id) — it has no notion of the
    new RBAC role system. A caller who only reaches this module via an
    active RBAC "Company Admin" assignment (require_rbac_admin_access,
    pharmagpt/auth/rbac.py) but whose legacy role is reviewer_qa/user would
    therefore be silently blocked by RLS under the ordinary RLS-scoped
    client. Any non-company_admin legacy role that got past the decorator
    — that's super_admin, or reviewer_qa/user with the RBAC role — is
    handled the same way super_admin already is: the service-role client,
    with company scope enforced explicitly in app code (_role_scope_company_id,
    _authorize_role_scope, and every route's g.tenant.company_id filter)
    rather than left to RLS."""
    if g.tenant.role != "company_admin":
        return get_service_role_client()
    return get_authenticated_client(extract_bearer_token())


def _role_scope_company_id():
    """None means 'template scope' (super_admin, no assumed context)."""
    return g.tenant.company_id


def _require_company_context():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content — "
                                  "assume a company context first"}), 403
    return None


def _require_reason(data: dict):
    reason = (data.get("reason") or "").strip()
    if not reason:
        return None, (jsonify({"error": "reason is required"}), 400)
    return reason, None


def _authorize_role_scope(client, role_id: str):
    """Verify `role_id` actually belongs to the caller's allowed scope
    before any update/clone/permission-toggle proceeds.

    Necessary because a company_admin's client is RLS-scoped (Postgres
    itself blocks cross-company access), but a super_admin's client is the
    service-role client, which bypasses RLS entirely — without this
    explicit, app-level check, a Platform Admin with no assumed company
    context could otherwise mutate any tenant's role by id, and an
    assumed-context Platform Admin could reach a company other than the one
    they assumed. Same defense-in-depth discipline routes/users.py already
    applies to its own service-role paths.

    Returns (role, None) on success, or (None, error_response) to return
    directly from the caller.
    """
    role = rbac_repo.get_role(client, role_id)
    if not role:
        return None, (jsonify({"error": "Role not found"}), 404)

    scope_company_id = _role_scope_company_id()
    if scope_company_id is None:
        # Template scope (super_admin, no assumed context): only templates.
        if role.get("company_id") is not None:
            return None, (jsonify({"error": "Role not found"}), 404)
    else:
        if role.get("company_id") != scope_company_id:
            return None, (jsonify({"error": "Role not found"}), 404)

    return role, None


def _authorize_clone_source(client, role_id: str):
    """Looser than _authorize_role_scope: a clone SOURCE may be a global
    template (any caller may clone from one) or a role already in the
    caller's own scope — but never another company's role."""
    role = rbac_repo.get_role(client, role_id)
    if not role:
        return None, (jsonify({"error": "Role not found"}), 404)

    source_company_id = role.get("company_id")
    scope_company_id = _role_scope_company_id()
    if source_company_id is not None and source_company_id != scope_company_id:
        return None, (jsonify({"error": "Role not found"}), 404)

    return role, None


@bp.route("/permissions", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def get_permission_catalog():
    return jsonify(rbac_repo.get_permission_catalog(_scoped_client()))


@bp.route("/roles", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def list_roles():
    client = _scoped_client()
    company_id = _role_scope_company_id()
    if company_id:
        return jsonify(rbac_repo.list_roles(client, company_id))
    # Template scope: only templates are visible/manageable.
    templates = client.table("rbac_roles").select("*").eq("is_template", True).order("name").execute()
    return jsonify(templates.data or [])


@bp.route("/roles", methods=["POST"])
@require_rbac_admin_access
@handle_postgrest_errors
def create_role():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    reason, error = _require_reason(data)
    if error:
        return error
    if not name:
        return jsonify({"error": "name is required"}), 400

    client = _scoped_client()
    company_id = _role_scope_company_id()

    if company_id:
        row = rbac_repo.create_role(
            client, company_id, name=name, description=(data.get("description") or ""),
            department_id=data.get("department_id"), approval_level_id=data.get("approval_level_id"),
        )
    else:
        # Platform Admin creating a new default role template.
        inserted = client.table("rbac_roles").insert({
            "company_id": None, "name": name, "description": data.get("description") or "",
            "department_code": data.get("department_code"), "is_system": False, "is_template": True,
        }).execute()
        row = inserted.data[0]

    rbac_repo.add_rbac_audit_entry(
        client, company_id=company_id, actor_user_id=g.tenant.user_id,
        role_id=row["id"], reason=f"Role created: {reason}", new_value={"name": name},
    )
    return jsonify(row), 201


@bp.route("/roles/<role_id>/clone", methods=["POST"])
@require_rbac_admin_access
@handle_postgrest_errors
def clone_role(role_id):
    data = request.get_json(silent=True) or {}
    new_name = (data.get("name") or "").strip()
    reason, error = _require_reason(data)
    if error:
        return error
    if not new_name:
        return jsonify({"error": "name is required"}), 400

    client = _scoped_client()
    company_id = _role_scope_company_id()
    if not company_id:
        return jsonify({"error": "Cloning a template into another template is not supported — "
                                  "assume a company context or act as a Company Admin"}), 400

    _source_role, error = _authorize_clone_source(client, role_id)
    if error:
        return error

    try:
        row = rbac_repo.clone_role(client, company_id, role_id, new_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    rbac_repo.add_rbac_audit_entry(
        client, company_id=company_id, actor_user_id=g.tenant.user_id,
        role_id=row["id"], reason=f"Role cloned from {role_id}: {reason}", new_value={"name": new_name},
    )
    return jsonify(row), 201


@bp.route("/roles/<role_id>", methods=["PATCH"])
@require_rbac_admin_access
@handle_postgrest_errors
def update_role(role_id):
    data = request.get_json(silent=True) or {}
    reason, error = _require_reason(data)
    if error:
        return error

    updates = {}
    if "name" in data:
        updates["name"] = (data["name"] or "").strip()
    if "description" in data:
        updates["description"] = data["description"] or ""
    if "status" in data:
        if data["status"] not in ("active", "disabled"):
            return jsonify({"error": "status must be 'active' or 'disabled'"}), 400
        updates["status"] = data["status"]
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    client = _scoped_client()
    old_role, error = _authorize_role_scope(client, role_id)
    if error:
        return error
    row = rbac_repo.update_role(client, role_id, updates)
    if not row:
        return jsonify({"error": "Role not found"}), 404

    rbac_repo.add_rbac_audit_entry(
        client, company_id=_role_scope_company_id(), actor_user_id=g.tenant.user_id,
        role_id=role_id, reason=f"Role updated: {reason}",
        old_value=old_role, new_value=updates,
    )
    return jsonify(row)


@bp.route("/roles/<role_id>/permissions", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def get_role_permissions(role_id):
    client = _scoped_client()
    _role, error = _authorize_role_scope(client, role_id)
    if error:
        return error
    return jsonify(rbac_repo.get_role_permissions(client, role_id))


@bp.route("/roles/<role_id>/permissions", methods=["PUT"])
@require_rbac_admin_access
@handle_postgrest_errors
def set_role_permission(role_id):
    data = request.get_json(silent=True) or {}
    permission_id = data.get("permission_id")
    granted = data.get("granted")
    reason, error = _require_reason(data)
    if error:
        return error
    if not permission_id or not isinstance(granted, bool):
        return jsonify({"error": "permission_id and a boolean granted are required"}), 400

    client = _scoped_client()
    _role, error = _authorize_role_scope(client, role_id)
    if error:
        return error
    result = rbac_repo.set_role_permission(client, role_id, permission_id, granted)

    rbac_repo.add_rbac_audit_entry(
        client, company_id=_role_scope_company_id(), actor_user_id=g.tenant.user_id,
        role_id=role_id, permission_id=permission_id, reason=f"Permission toggled: {reason}",
        old_value={"granted": result["old_value"]}, new_value={"granted": result["new_value"]},
    )
    return jsonify(result)


@bp.route("/users/<user_id>/roles", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def list_user_roles(user_id):
    guard = _require_company_context()
    if guard:
        return guard
    return jsonify(rbac_repo.list_user_roles(_scoped_client(), user_id, g.tenant.company_id))


@bp.route("/users/<user_id>/roles", methods=["POST"])
@require_rbac_admin_access
@handle_postgrest_errors
def assign_user_role(user_id):
    guard = _require_company_context()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    role_id = data.get("role_id")
    reason, error = _require_reason(data)
    if error:
        return error
    if not role_id:
        return jsonify({"error": "role_id is required"}), 400

    client = _scoped_client()
    target_role = rbac_repo.get_role(client, role_id)
    if not target_role or target_role.get("company_id") != g.tenant.company_id:
        # Never assign a role belonging to another company (or a template
        # directly) to a user — same isolation discipline as _authorize_role_scope.
        return jsonify({"error": "Role not found"}), 404
    row = rbac_repo.assign_user_role(client, user_id, role_id, g.tenant.company_id)

    rbac_repo.add_rbac_audit_entry(
        client, company_id=g.tenant.company_id, actor_user_id=g.tenant.user_id,
        target_user_id=user_id, role_id=role_id, reason=f"Role assigned: {reason}",
        new_value={"role_id": role_id},
    )
    return jsonify(row), 201


@bp.route("/users/<user_id>/roles/<role_id>", methods=["DELETE"])
@require_rbac_admin_access
@handle_postgrest_errors
def revoke_user_role(user_id, role_id):
    guard = _require_company_context()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    reason, error = _require_reason(data)
    if error:
        return error

    client = _scoped_client()
    rbac_repo.revoke_user_role(client, user_id, role_id)

    rbac_repo.add_rbac_audit_entry(
        client, company_id=g.tenant.company_id, actor_user_id=g.tenant.user_id,
        target_user_id=user_id, role_id=role_id, reason=f"Role revoked: {reason}",
        old_value={"role_id": role_id},
    )
    return "", 204


@bp.route("/users/<user_id>/effective-permissions", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def get_user_effective_permissions(user_id):
    guard = _require_company_context()
    if guard:
        return guard
    # Resolve as the target user, not the caller — reuses the same
    # table-driven resolution get_effective_permissions() uses for
    # authorization checks, applied to whichever user_id was asked about.
    client = _scoped_client()
    role_rows = (
        client.table("rbac_user_roles").select("role_id")
        .eq("user_id", user_id).eq("company_id", g.tenant.company_id)
        .execute()
    ).data or []
    role_ids = [r["role_id"] for r in role_rows]
    if not role_ids:
        return jsonify([])

    grants = (
        client.table("rbac_role_permissions")
        .select("granted, permissions:rbac_permissions(module, action)")
        .in_("role_id", role_ids).eq("granted", True)
        .execute()
    ).data or []
    permissions = sorted({
        (row["permissions"]["module"], row["permissions"]["action"])
        for row in grants if row.get("permissions")
    })
    return jsonify([{"module": m, "action": a} for m, a in permissions])


@bp.route("/audit", methods=["GET"])
@require_rbac_admin_access
@handle_postgrest_errors
def get_audit_log():
    guard = _require_company_context()
    if guard:
        return guard
    return jsonify(rbac_repo.list_audit_log(_scoped_client(), g.tenant.company_id))

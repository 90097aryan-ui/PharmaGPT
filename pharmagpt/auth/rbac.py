"""
pharmagpt/auth/rbac.py — central authorization layer for the fine-grained,
per-module/per-action RBAC framework (migrations/0015_rbac_org_framework_up.sql).

This is additive to, not a replacement for, pharmagpt/auth/decorators.py's
require_role(): the frozen 4-role platform check (super_admin | company_admin
| reviewer_qa | user) stays exactly as it is, on every one of its existing
42 call sites. require_permission() below is a second, finer-grained gate
used only by the new Role & Permission Management surface
(pharmagpt/routes/rbac.py, pharmagpt/routes/org_structure.py) and by any
future route that opts in — no existing route is changed to use it.

Uses get_service_role_client() rather than the caller's own RLS-scoped
client, for the same reason pharmagpt/routes/users.py's
list_users_directory already does: RLS on rbac_user_roles/rbac_roles/
rbac_role_permissions only lets a company_admin read those tables (see the
migration's policies), but any authenticated tenant member needs their own
effective permissions resolved here. This applies the SAME g.tenant.user_id
/ g.tenant.company_id scoping the rest of this app already trusts
everywhere else — never client input, never relying on RLS to enforce it.
"""

from functools import wraps

from flask import g, jsonify

from pharmagpt.auth.context import TenantContext
from pharmagpt.services.supabase_client import get_service_role_client


def get_effective_permissions(tenant: TenantContext) -> set[tuple[str, str]]:
    """Return the set of (module, action) pairs granted to this tenant via
    any of their assigned rbac_user_roles, union'd across all active roles.

    Platform Admin (super_admin) never has standing tenant-module access —
    resolved permissions for a super_admin are always empty here, regardless
    of any rbac_user_roles row (there should never be one, but this does not
    trust that invariant blindly). Administration-module access for
    Platform Admin is handled as a separate, explicit case in
    has_permission() below, not through this table-driven resolution.
    """
    if tenant.role == "super_admin" or not tenant.company_id:
        return set()

    client = get_service_role_client()

    user_roles = (
        client.table("rbac_user_roles").select("role_id")
        .eq("user_id", tenant.user_id).eq("company_id", tenant.company_id)
        .execute()
    ).data or []
    role_ids = [r["role_id"] for r in user_roles]
    if not role_ids:
        return set()

    active_roles = (
        client.table("rbac_roles").select("id")
        .in_("id", role_ids).eq("status", "active")
        .execute()
    ).data or []
    active_role_ids = [r["id"] for r in active_roles]
    if not active_role_ids:
        return set()

    grants = (
        client.table("rbac_role_permissions").select("granted, permissions:rbac_permissions(module, action)")
        .in_("role_id", active_role_ids).eq("granted", True)
        .execute()
    ).data or []

    return {
        (row["permissions"]["module"], row["permissions"]["action"])
        for row in grants
        if row.get("permissions")
    }


def has_permission(tenant: TenantContext, module: str, action: str) -> bool:
    """Central permission check. Platform Admin (super_admin) is restricted
    to the Administration module only, and only outside an Assume Company
    Context grant — "Platform Admin must NOT automatically access tenant
    GMP records" is enforced here, not left to the caller to remember."""
    if tenant.role == "super_admin":
        return module == "Administration" and not tenant.company_id

    if tenant.role == "company_admin":
        # The frozen platform tier already grants company_admin blanket
        # authority within their own company everywhere else in this app
        # (routes/users.py, routes/companies.py, ...) — this layer narrows
        # what OTHER rbac-assigned roles (reviewer_qa/user, or any custom
        # role) may do; it does not weaken company_admin's existing,
        # pre-existing authority. Avoids a lockout scenario where a
        # pre-migration company_admin has no rbac_user_roles row yet.
        return True

    return (module, action) in get_effective_permissions(tenant)


def require_permission(module: str, action: str):
    """Reject the request (403) unless the caller's effective RBAC
    permissions grant `action` on `module`. Must run after require_auth has
    populated g.tenant. Independent of, and stacked alongside, require_role
    where a route wants both the coarse and fine-grained gate."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not has_permission(g.tenant, module, action):
                return jsonify({
                    "error": f"This action requires '{action}' permission on '{module}'",
                }), 403
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


COMPANY_ADMIN_RBAC_ROLE_NAME = "Company Admin"


def has_active_rbac_role(tenant: TenantContext, role_name: str) -> bool:
    """True if `tenant` holds an active rbac_user_roles assignment to an
    active rbac_roles row named exactly `role_name`, scoped to their own
    company. Mirrors get_effective_permissions()'s two-step resolution
    (assignment -> role) but checks role identity (name) instead of
    unioning permissions, so it can answer "does this user hold role X"
    for a specific named role rather than "what can this user do".

    Cross-company assignments can never match: the rbac_user_roles lookup
    is scoped to tenant.company_id, and the rbac_roles lookup additionally
    requires company_id == tenant.company_id as defense in depth — the
    same discipline routes/rbac.py::_authorize_role_scope already applies,
    since a service-role client (used for super_admin) bypasses RLS.
    An assignment row's mere presence is what "active assignment" means
    here: revoking a role deletes the rbac_user_roles row outright
    (pharmagpt/db/rbac_repo.py::revoke_user_role) — there is no separate
    inactive/active flag to check on that table, only on rbac_roles.status.
    """
    if tenant.role == "super_admin" or not tenant.company_id:
        return False

    client = get_service_role_client()

    user_roles = (
        client.table("rbac_user_roles").select("role_id")
        .eq("user_id", tenant.user_id).eq("company_id", tenant.company_id)
        .execute()
    ).data or []
    role_ids = [r["role_id"] for r in user_roles]
    if not role_ids:
        return False

    matches = (
        client.table("rbac_roles").select("id")
        .in_("id", role_ids).eq("status", "active")
        .eq("name", role_name).eq("company_id", tenant.company_id)
        .execute()
    ).data or []
    return len(matches) > 0


def has_rbac_admin_access(tenant: TenantContext) -> bool:
    """Central authorization check for the RBAC/org-structure
    ADMINISTRATION surfaces (routes/rbac.py, routes/org_structure.py) —
    distinct from has_permission()'s 'Administration' module gate, which is
    Platform-Admin-only and unrelated to managing a company's own roles.

    Authorized if:
      - legacy role is company_admin (unchanged, frozen-tier authority), or
      - legacy role is super_admin (unchanged — the route body itself still
        enforces template-vs-company scope / Assume Company Context), or
      - the caller holds an active RBAC role literally named "Company
        Admin" for their own company, regardless of legacy role.

    A user whose only RBAC role is "QA Reviewer" (or anything other than
    "Company Admin") gets nothing from this check, and legacy
    reviewer_qa/user get no automatic access either — only an actual
    active "Company Admin" RBAC assignment closes that gap. Roles are
    additive: holding "Company Admin" plus other RBAC roles simultaneously
    still grants access, and does not require dropping the other roles.
    """
    if tenant.role in ("company_admin", "super_admin"):
        return True
    return has_active_rbac_role(tenant, COMPANY_ADMIN_RBAC_ROLE_NAME)


def require_rbac_admin_access(view_func):
    """Route decorator for the RBAC/org-structure administration surfaces.
    Same shape/placement as require_role, but additionally accepts an
    active RBAC 'Company Admin' role assignment when the caller's legacy
    role is reviewer_qa/user — the single centralized fix for the
    Coordinator-with-legacy-reviewer_qa 403, instead of a special-case
    check duplicated inside every route."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not has_rbac_admin_access(g.tenant):
            return jsonify({
                "error": "This action requires Company Admin access "
                         "(legacy role or an active RBAC 'Company Admin' role assignment)",
            }), 403
        return view_func(*args, **kwargs)

    return wrapped

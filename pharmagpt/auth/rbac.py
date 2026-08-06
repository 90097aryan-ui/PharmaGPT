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

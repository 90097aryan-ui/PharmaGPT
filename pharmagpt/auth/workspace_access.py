"""
pharmagpt/auth/workspace_access.py — Role-based workspace visibility, built
on top of pharmagpt/auth/rbac.py — the existing central authorization layer
for the fine-grained, per-module/per-action RBAC framework (migrations/0015_
rbac_org_framework_up.sql). No new tables, no new permission system, and no
second effective-permissions resolver: this module only groups that
framework's existing 15-module permission catalog into the 6 workspaces the
UI presents (pharmagpt/templates/index.html's workspace-selector cards +
top-level sidebar sections), and answers "can this user see/reach
workspace X" by delegating the actual grant lookup to
pharmagpt.auth.rbac.get_effective_permissions().

IMPORTANT — current default is fail-open, and why:

The intended, target policy is deny-by-default: a user with no RBAC role
assignment should NOT automatically see restricted workspaces, only
company_admin/super_admin should always see everything, and an assigned
role's granted permissions should be the only thing that opens a
restricted workspace up. That is what this module implements in
has_workspace_access() below for anyone whose effective permissions
resolve to a non-empty set.

However: migrations/0015_rbac_org_framework_up.sql (rbac_permissions /
rbac_roles / rbac_role_permissions / rbac_user_roles — the tables
pharmagpt.auth.rbac.get_effective_permissions() reads) has NOT been
applied to the live PharmaGPT Supabase project as of this writing
(verified directly: list_tables on the `public` schema shows none of
those five tables exist). Until that migration is applied, EVERY user's
effective permissions resolve to empty — including company_admin's own
staff — so a strict deny-by-default would lock every non-admin account in
every company out of every restricted workspace, with no way for a
Company Admin to grant it back (the Roles & Permissions screen itself
depends on the same missing tables). That is a platform-wide outage, not
a security tightening, so _effective_modules() below deliberately treats
"empty effective permissions" as fail-open (unrestricted) rather than deny.

To switch to strict deny-by-default once migration 0015 is confirmed live
and companies have had a chance to configure roles: change the single
DENY_BY_DEFAULT constant below from False to True. No other change is
needed — _effective_modules() already resolves real grants correctly
once the tables exist; only the "empty grants" fallback changes meaning.

company_admin / super_admin always see everything regardless of any of
the above — same "admin bypass" pharmagpt.auth.rbac.has_permission()
already applies for company_admin, and the same "admin sees everything"
pattern used throughout routes/rbac.py and routes/users.py.
"""

from __future__ import annotations

import logging

from flask import g, jsonify
from postgrest.exceptions import APIError

from pharmagpt.auth.rbac import get_effective_permissions

logger = logging.getLogger(__name__)

ADMIN_ROLES = ("company_admin", "super_admin")

# The one-line activation switch (see module docstring). False: a tenant
# with empty effective permissions (no RBAC role assigned, or migration
# 0015 not yet applied) is treated as unrestricted. True: empty effective
# permissions means no restricted-workspace access — only an explicit
# grant opens one up. Flip this to True only after migration 0015 is
# confirmed deployed (docs/MIGRATION_0015_DEPLOYMENT_VERIFICATION.md).
DENY_BY_DEFAULT = False

# workspace key -> rbac_permissions.module names that grant it. A user needs
# ANY granted permission (any action) on ANY listed module to see the
# workspace. "Document Control" intentionally appears under both "quality"
# and "documents" — Document Control is a shared entry point between the
# Quality Management and Document Generator sidebar sections (see the
# ALD-001-R1 comment in index.html), so either grant is sufficient.
WORKSPACE_MODULES: dict[str, list[str]] = {
    "dashboard": ["Dashboard"],
    "validation": ["Validation", "Risk Assessment", "Equipment Library", "Projects"],
    "quality": ["QMS", "Deviations", "CAPA", "Change Control", "Document Control"],
    "knowledge": ["Knowledge Base"],
    "documents": ["Document Control"],
    "pharmapilot": ["AI Assistant"],
}

ALL_WORKSPACES = tuple(WORKSPACE_MODULES.keys())


def _effective_modules(tenant) -> set[str]:
    """The set of rbac_permissions.module names `tenant` currently has any
    granted permission for, via pharmagpt.auth.rbac.get_effective_permissions
    (rbac_user_roles -> rbac_role_permissions -> rbac_permissions). Empty if
    the tenant has no assignments, or if the RBAC tables can't be queried at
    all (migration 0015 not applied — see module docstring) — has_workspace_
    access() below is what decides whether "empty" means fail-open or deny.
    Memoized on flask.g for the ambient request's g.tenant so a blueprint's
    before_request gate and any in-handler check don't issue the same query
    twice."""
    is_ambient = tenant is getattr(g, "tenant", None)
    if is_ambient and hasattr(g, "_workspace_effective_modules"):
        return g._workspace_effective_modules

    try:
        modules = {module for module, _action in get_effective_permissions(tenant)}
    except APIError:
        logger.exception("workspace_access: could not read RBAC tables — treating as no grants")
        modules = set()

    if is_ambient:
        g._workspace_effective_modules = modules
    return modules


def has_workspace_access(workspace_key: str, tenant=None) -> bool:
    """True if `tenant` (defaults to the current request's g.tenant) may
    see/reach the given workspace. company_admin/super_admin always can.
    Anyone else: see the module docstring / DENY_BY_DEFAULT — empty
    effective permissions currently fail open (DENY_BY_DEFAULT = False);
    flip that one constant to switch to strict deny-by-default."""
    tenant = tenant if tenant is not None else g.tenant
    if tenant.role in ADMIN_ROLES:
        return True
    if not tenant.company_id:
        return False
    granted_modules = _effective_modules(tenant)
    if not granted_modules:
        return not DENY_BY_DEFAULT
    return any(module in granted_modules for module in WORKSPACE_MODULES.get(workspace_key, []))


def accessible_workspaces_for(tenant) -> list[str]:
    """All workspace keys `tenant` currently has access to — the single
    list the frontend needs to filter workspace cards + sidebar sections,
    and to decide single-workspace auto-entry. Used by routes/auth.py's
    login() and me() responses."""
    return [key for key in ALL_WORKSPACES if has_workspace_access(key, tenant=tenant)]


def require_workspace_access(*workspace_keys: str):
    """Flask before_request-friendly guard: returns a 403 JSON response
    unless the caller (g.tenant) has access to at least one of the given
    workspaces, else None (proceed). Mirrors
    pharmagpt.auth.decorators.require_role's response shape. Usage:

        @bp.before_request
        def _gate():
            return require_workspace_access("validation")
    """
    if any(has_workspace_access(key) for key in workspace_keys):
        return None
    return jsonify({
        "error": f"Your role does not have access to this workspace ({', '.join(workspace_keys)})",
    }), 403

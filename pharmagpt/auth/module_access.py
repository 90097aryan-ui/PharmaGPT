"""
pharmagpt/auth/module_access.py — authoritative BUSINESS-action permission
resolver for the Yuktav org/RBAC/workflow authorization task, built on top
of pharmagpt.auth.rbac (migrations/0015/0016's rbac_user_roles ->
rbac_roles -> rbac_role_permissions) via pharmagpt.services.rbac_defaults'
MAJOR_MODULE_MAP.

Distinct from, and does not replace, either existing gate:
  - pharmagpt.auth.decorators.require_role — the frozen 4-role platform
    check, unchanged, every existing call site untouched.
  - pharmagpt.auth.workspace_access.has_workspace_access /
    DENY_BY_DEFAULT — the coarse, already-shipped, already-tested UI-
    workspace-visibility gate. Left exactly as-is (DENY_BY_DEFAULT stays
    False) — flipping it is a separate decision gated on confirming
    migration 0015 is live in production, which cannot be verified from a
    local checkout. This module's fail-closed behavior only governs the
    NEW business-route enforcement points this task adds; it does not
    touch workspace-level sidebar/card visibility at all.

Fail-closed by design: an authenticated tenant with no grant on the
requested (major_module, action) is DENIED, not treated as unrestricted.
This is safe to enable from day one for a brand-new gate (nothing depended
on it granting access before this task), unlike flipping the pre-existing
workspace_access.DENY_BY_DEFAULT switch, which would retroactively change
what already-shipped behavior currently allows — that switch is untouched
by this change and remains a separate, later decision.

REVISION (RBAC enforcement closure task): company_admin and reviewer_qa no
longer get an unconditional bypass here. Earlier in this task's rollout,
before any production company had been cloned into or backfilled, an
unconditional bypass for these two frozen roles was a deliberate,
documented compatibility measure ("preserve existing behavior until real
RBAC data exists to resolve against"). Production RBAC data is now
authoritative — every provisioned company's `company_admin`-tier role is
cloned with a full (module, action) grant set (`rbac_defaults.
default_grants_for_role`'s "company_admin" tier: every module x every
action), so a properly-provisioned company_admin gets identical business
access as before, just resolved through the same table-driven path
everyone else uses instead of a hardcoded exception. This is the
"separate platform administration from business functional authority"
principle finally applied: `require_role("company_admin")`,
`has_rbac_admin_access()`, and every /rbac, /org, /users, /companies
administrative surface are completely untouched by this change — those
never call this function. Only this function's BUSINESS-action answer for
company_admin/reviewer_qa changes: it now depends on an actual RBAC role
assignment, exactly like a plain `user`.

Known consequence, not silently absorbed: any company that has not yet
been through provision_org_defaults_for_company() + a user backfill (at
the time of this change, that is every company except the one target
company this task's backfill covered) has zero cloned roles and zero
rbac_user_roles rows — a company_admin/reviewer_qa there will now be
DENIED every business-permission-gated action until that company is
provisioned and its users backfilled. This is flagged prominently in the
implementation report rather than deployed silently.

super_admin is unaffected — always False, no standing tenant/business
access, matching the same invariant enforced everywhere else in this app.

A failed RBAC-table read (e.g. migration 0015/0016 not yet applied/live,
matching pharmagpt.auth.workspace_access._effective_modules()'s identical,
pre-existing handling of the exact same failure mode) is treated as "no
grants" — fail-closed denies rather than raising a 500.
"""

from __future__ import annotations

import logging
from functools import wraps

from flask import g, jsonify
from postgrest.exceptions import APIError

from pharmagpt.auth.context import TenantContext
from pharmagpt.auth.rbac import get_effective_permissions
from pharmagpt.services.rbac_defaults import MAJOR_MODULE_MAP

logger = logging.getLogger(__name__)


def has_business_permission(tenant: TenantContext, major_module: str, action: str) -> bool:
    """True if `tenant` may perform `action` on `major_module` (one of
    "QMS", "Validation", "Document Control", "PharmaPilot").

    - super_admin: always False — no standing tenant/business access,
      matching the same invariant pharmagpt.auth.rbac.has_permission and
      pharmagpt.tenancy already enforce everywhere else in this app.
    - everyone else (company_admin, reviewer_qa, plain `user`, and any
      future department/functional-role-only identity): resolved via the
      existing pharmagpt.auth.rbac.get_effective_permissions(tenant)
      (rbac_user_roles -> rbac_roles -> rbac_role_permissions), checked
      against every rbac_permissions.module MAJOR_MODULE_MAP says belongs
      to `major_module`. No grant on any of them -> False. This is the
      actual fail-closed behavior: an unconfigured user (no
      rbac_user_roles row at all) gets nothing, never an "empty means
      unrestricted" fallback — see module docstring for the frozen-role
      bypass this replaces and its known consequence for unprovisioned
      companies.
    """
    if tenant.role == "super_admin":
        return False

    sub_modules = MAJOR_MODULE_MAP.get(major_module, set())
    if not sub_modules:
        return False

    try:
        effective = get_effective_permissions(tenant)
    except APIError:
        logger.exception("module_access: could not read RBAC tables — treating as no grants")
        effective = set()
    return any((module, action) in effective for module in sub_modules)


def require_business_permission(major_module: str, action: str):
    """Route decorator, same response shape as
    pharmagpt.auth.decorators.require_role / pharmagpt.auth.rbac.require_permission
    — 403 JSON if the caller lacks `action` on `major_module`, else calls
    through. Stacks alongside an existing @require_role on the same route
    (both must pass) rather than replacing it."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not has_business_permission(g.tenant, major_module, action):
                return jsonify({
                    "error": f"This action requires '{action}' permission on '{major_module}'",
                }), 403
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


# record_type (services/workflow_engine.py / qms_workflow_database.py) ->
# the major_module it belongs to, for workflow_engine.decide_step()'s
# business-permission check. Validation-suite modules (qualification,
# val_report, risk_assessment) don't route through decide_step today (they
# have their own dedicated approval endpoints, see routes/qual.py,
# routes/risk.py, routes/report.py) — included here anyway so a future
# caller that does route them through the generic engine gets correct
# behavior for free, not a KeyError.
RECORD_TYPE_MAJOR_MODULE: dict[str, str] = {
    "deviation": "QMS",
    "capa": "QMS",
    "change_control": "QMS",
    "document": "Document Control",
    "qualification": "Validation",
    "val_report": "Validation",
    "risk_assessment": "Validation",
    "market_complaint": "QMS",
}

# workflow_engine.decide_step()'s `decision` argument -> the business action
# it represents, for the same check.
DECISION_ACTION: dict[str, str] = {
    "advance": "Submit",
    "approve": "Approve",
    "reject": "Reject",
    "return": "Reject",
}


def major_module_for_record_type(record_type: str) -> str | None:
    return RECORD_TYPE_MAJOR_MODULE.get(record_type)


def action_for_decision(decision: str) -> str | None:
    return DECISION_ACTION.get(decision)

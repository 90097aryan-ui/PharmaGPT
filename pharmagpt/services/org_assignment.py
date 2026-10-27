"""
pharmagpt/services/org_assignment.py — ties together the previously
disconnected organizational layers (Yuktav org/RBAC/workflow authorization
task):

  - migration 0014's departments / user_departments / workflow_roles
    (pharmagpt/services/org_directory.py)
  - migration 0015/0016's rbac_roles / rbac_user_roles / rbac_audit_log
    (pharmagpt/db/rbac_repo.py, pharmagpt/services/rbac_defaults.py)

Two responsibilities:

1. assign_user_to_department() — the single call site an admin route uses
   to put a user into a department with a department-scoped functional
   role AND the matching cloned RBAC role, audited as one logical change.
   Reuses org_directory.add_department_membership() and
   rbac_repo.assign_user_role()/add_rbac_audit_entry() as-is — no new
   tables, no new audit mechanism.

2. resolve_department_approver() — workflow routing input for
   services/workflow_engine.py: "who is today's Production Reviewer for
   this company", used to auto-resolve a named approver at workflow start
   time (a snapshot into the existing qms_workflow_step_approvers
   mechanism, not a live reference — see workflow_engine.py's own
   docstring for why that matters).
"""

from __future__ import annotations

import logging

from pharmagpt.db import rbac_repo
from pharmagpt.services import org_directory
from pharmagpt.services.rbac_defaults import DEPARTMENT_ROLE_TEMPLATES

# (department_code, functional_role) -> template display name — the reverse
# of rbac_defaults.DEPARTMENT_ROLE_TEMPLATES, built once at import time.
_TEMPLATE_NAME_BY_CELL: dict[tuple[str, str], str] = {
    cell: name for name, cell in DEPARTMENT_ROLE_TEMPLATES.items()
}


logger = logging.getLogger(__name__)


def _department_role_template_name(department_code: str, functional_role: str) -> str | None:
    return _TEMPLATE_NAME_BY_CELL.get((department_code, functional_role))


def _find_company_role_by_name(client, company_id: str, name: str) -> dict | None:
    """A company's own cloned copy of a global template, by name — never a
    template row itself (company_id is null on those)."""
    for role in rbac_repo.list_roles(client, company_id):
        if role.get("company_id") == company_id and role.get("name") == name:
            return role
    return None


def _compensate(client, user_id, company_id, department_id, before, role_inserted) -> None:
    """Undo this call's writes after a failure. Best effort and itself never raises
    over the original error (which the caller re-raises)."""
    try:
        if role_inserted:
            rbac_repo.revoke_user_role(client, user_id, role_inserted)
        if before is None:
            client.table("user_departments").delete()                 .eq("user_id", user_id).eq("department_id", department_id).execute()
        else:
            client.table("user_departments").update(
                {"workflow_role_id": before["workflow_role_id"], "is_primary": before["is_primary"]}
            ).eq("user_id", user_id).eq("department_id", department_id).execute()
    except Exception:  # noqa: BLE001
        logger.exception("org_assignment: compensation failed for user %s dept %s — manual check needed",
                         user_id, department_id)


def assign_user_to_department(client, *, user_id: str, company_id: str, department_id: str,
                                department_code: str, workflow_role_id: int, functional_role_name: str,
                                is_primary: bool, actor_user_id: str, reason: str) -> dict:
    """Add `user_id` to `department_id` with functional role
    `functional_role_name` (must match a workflow_roles.name), and assign
    the matching company-scoped RBAC role (the company's own clone of
    e.g. "Production Reviewer") if one has been provisioned for this
    company (see provision_org_defaults_for_company). Writes exactly one
    rbac_audit_log entry describing the combined change — reason is
    required, matching every other RBAC/org mutation in this codebase.

    Returns {"membership": ..., "rbac_role_assigned": <role dict or None>}.
    A None rbac_role_assigned means the company hasn't cloned that
    template yet (e.g. provisioned before this department/role combination
    existed) — the membership itself still succeeds; the caller is
    responsible for deciding whether that's acceptable or should trigger a
    (re-)provisioning call.
    """
    if not reason or not reason.strip():
        raise ValueError("reason is required for a department/role assignment")

    # PostgREST has no multi-statement transaction, so the change is applied step by
    # step and compensated if any later step (RBAC insert or the audit write) fails:
    # a membership/role change must never persist without its audit row.
    before = (
        client.table("user_departments").select("id, workflow_role_id, is_primary")
        .eq("user_id", user_id).eq("department_id", department_id).execute()
    ).data or []
    before = before[0] if before else None
    role_inserted = None
    try:
        membership = org_directory.add_department_membership(
            client, user_id, company_id, department_id,
            workflow_role_id=workflow_role_id, is_primary=is_primary,
        )

        rbac_role_assigned = None
        already_held = None
        template_name = _department_role_template_name(department_code, functional_role_name)
        if template_name:
            matching_role = _find_company_role_by_name(client, company_id, template_name)
            if matching_role:
                # rbac_user_roles is UNIQUE (user_id, role_id): re-inserting a role the
                # user already holds would raise after the membership change committed.
                already_held = (
                    client.table("rbac_user_roles").select("id")
                    .eq("user_id", user_id).eq("role_id", matching_role["id"]).execute()
                ).data
                if not already_held:
                    rbac_repo.assign_user_role(client, user_id, matching_role["id"], company_id)
                    role_inserted = matching_role["id"]
                rbac_role_assigned = matching_role

        rbac_repo.add_rbac_audit_entry(
            client, company_id=company_id, actor_user_id=actor_user_id, target_user_id=user_id,
            department_id=department_id, role_id=(rbac_role_assigned or {}).get("id"),
            reason=f"Department/functional-role assignment ({functional_role_name}): {reason}",
            old_value=({"workflow_role_id": before["workflow_role_id"], "is_primary": before["is_primary"]}
                       if before else None),
            new_value={"department_id": department_id, "functional_role": functional_role_name,
                       "is_primary": is_primary, "rbac_role_id": (rbac_role_assigned or {}).get("id"),
                       "rbac_role_already_held": bool(already_held)},
        )
    except Exception:
        _compensate(client, user_id, company_id, department_id, before, role_inserted)
        raise

    return {"membership": membership, "rbac_role_assigned": rbac_role_assigned}


def resolve_department_approver(client, company_id: str, department_code: str,
                                  functional_role_name: str) -> dict | None:
    """The active user currently holding `functional_role_name` in the
    department identified by `department_code`, for workflow auto-
    resolution (services/workflow_engine.py). Deterministic: the earliest-
    assigned (oldest user_departments.created_at) active match wins, so
    repeated resolution against unchanged org data always picks the same
    person. Returns {"user_id": ..., "display_name": ...} or None if
    nobody currently holds that (department, role) combination — the
    caller (workflow_engine) must treat that as "no auto-resolved
    approver", never silently skip the step.
    """
    departments = (
        client.table("departments").select("id")
        .eq("company_id", company_id).eq("department_code", department_code)
        .execute()
    ).data or []
    if not departments:
        return None
    department_id = departments[0]["id"]

    role_rows = (
        client.table("workflow_roles").select("id").eq("name", functional_role_name)
        .execute()
    ).data or []
    if not role_rows:
        return None
    workflow_role_id = role_rows[0]["id"]

    memberships = (
        client.table("user_departments")
        .select("user_id, created_at, users(display_name, status)")
        .eq("company_id", company_id).eq("department_id", department_id)
        .eq("workflow_role_id", workflow_role_id)
        .order("created_at")
        .execute()
    ).data or []

    for membership in memberships:
        user = membership.get("users") or {}
        if user.get("status", "active") == "active":
            return {"user_id": membership["user_id"], "display_name": user.get("display_name", "")}
    return None

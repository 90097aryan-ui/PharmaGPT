"""
pharmagpt/services/org_directory.py — read/write access to the
organizational-model tables added in migration 0014: `departments` and
`user_departments` (department assignment), plus lookups against the
static `workflow_roles` reference table.

Organizational metadata, not platform authorization or Workflow Engine
input — pharmagpt/services/workflow_engine.py and pharmagpt/auth/decorators.py
are untouched by this module and do not read from it. See
docs/NUTRA_DEMO_DATA.md's scope-boundary note.

Every function takes an already-constructed Supabase client, matching
pharmagpt/services/module_permissions.py's convention.
"""

from __future__ import annotations


def get_workflow_role_id(client, name: str) -> int | None:
    """Resolve a `workflow_roles.name` (e.g. "Initiator") to its `id`, or
    None if the name is unrecognized."""
    result = client.table("workflow_roles").select("id").eq("name", name).maybe_single().execute()
    row = result.data if result else None
    return row["id"] if row else None


def find_or_create_department(client, company_id: str, name: str, department_code: str) -> dict:
    """Look up a department by its stable (company_id, department_code) key.

    If found and `name` has drifted from what's stored, updates it in
    place (department_code is the stable identity; name may legitimately
    change over time). If not found, inserts a new row."""
    existing = (
        client.table("departments")
        .select("id, name, department_code")
        .eq("company_id", company_id)
        .eq("department_code", department_code)
        .maybe_single()
        .execute()
    )
    row = existing.data if existing else None
    if row:
        if row["name"] != name:
            updated = (
                client.table("departments")
                .update({"name": name})
                .eq("id", row["id"])
                .execute()
            )
            return (updated.data or [row])[0]
        return row

    inserted = (
        client.table("departments")
        .insert({"company_id": company_id, "name": name, "department_code": department_code})
        .execute()
    )
    return inserted.data[0]


def add_department_membership(client, user_id: str, company_id: str, department_id: str,
                                workflow_role_id: int | None = None, is_primary: bool = False) -> dict:
    """Add/update `user_id`'s membership in `department_id`, optionally with
    a department-scoped functional role (migrations/0016_department_
    functional_roles_up.sql's user_departments.workflow_role_id) — the fix
    for "QA Reviewer must not be equivalent to Production Reviewer": a
    user's functional role is a property of THIS membership row, not a
    single global users.workflow_role_id (migration 0014, left untouched
    for backward compatibility).

    A user may belong to multiple departments (multiple rows, one per
    department) — this does not touch is_primary unless `is_primary=True`,
    in which case it delegates to set_primary_department() below for the
    single-primary invariant, then re-applies workflow_role_id (upsert
    order: primary-flag first, since set_primary_department's own upsert
    does not know about workflow_role_id and would otherwise clobber it).
    """
    if is_primary:
        set_primary_department(client, user_id, company_id, department_id)

    payload = {"user_id": user_id, "department_id": department_id, "company_id": company_id}
    if workflow_role_id is not None:
        payload["workflow_role_id"] = workflow_role_id
    if is_primary:
        payload["is_primary"] = True

    result = client.table("user_departments").upsert(
        payload, on_conflict="user_id,department_id",
    ).execute()
    return result.data[0]


def list_user_departments(client, user_id: str, company_id: str) -> list[dict]:
    """Every department `user_id` belongs to, each with its own
    (possibly-null) department-scoped functional role — the source of
    truth for "does this user hold Production Reviewer" style questions,
    used by services/org_assignment.py::resolve_department_approver()."""
    return (
        client.table("user_departments")
        .select("id, department_id, workflow_role_id, is_primary, departments(name, department_code), "
                "workflow_roles(name)")
        .eq("user_id", user_id).eq("company_id", company_id)
        .execute()
    ).data or []


def set_primary_department(client, user_id: str, company_id: str, department_id: str) -> None:
    """Idempotently make `department_id` this user's one primary department.

    Safe to call again with a different department_id on a later rerun:
    first clears is_primary on any other row for this user (so the
    database's partial unique index on is_primary is never violated), then
    upserts (user_id, department_id) with is_primary=true. A no-op if this
    is already the user's primary department.
    """
    existing_primary = (
        client.table("user_departments")
        .select("id, department_id")
        .eq("user_id", user_id)
        .eq("is_primary", True)
        .maybe_single()
        .execute()
    )
    primary_row = existing_primary.data if existing_primary else None

    if primary_row and primary_row["department_id"] == department_id:
        return

    if primary_row and primary_row["department_id"] != department_id:
        client.table("user_departments").update({"is_primary": False}).eq("id", primary_row["id"]).execute()

    client.table("user_departments").upsert(
        {"user_id": user_id, "department_id": department_id, "company_id": company_id, "is_primary": True},
        on_conflict="user_id,department_id",
    ).execute()

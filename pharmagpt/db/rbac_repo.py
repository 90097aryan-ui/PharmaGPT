"""
pharmagpt/db/rbac_repo.py — CRUD for company-scoped rbac_roles, the
permission matrix (rbac_role_permissions), user-role assignment
(rbac_user_roles), and the immutable rbac_audit_log.

Unlike pharmagpt/routes/users.py's _audit_best_effort (which swallows a
logging failure so it never blocks the underlying action), add_rbac_audit_entry
below is NOT best-effort: deliverable 7 requires an immutable audit trail
for every RBAC change, so a failed audit write must fail the mutating
request rather than silently proceed unaudited.
"""

from __future__ import annotations


def list_roles(client, company_id: str) -> list[dict]:
    """Company-owned roles plus global templates (company_id is null) —
    templates are included so a Company Admin can browse/clone them."""
    company_roles = (
        client.table("rbac_roles").select("*")
        .eq("company_id", company_id).order("name")
        .execute()
    ).data or []
    templates = (
        client.table("rbac_roles").select("*")
        .eq("is_template", True).order("name")
        .execute()
    ).data or []
    return company_roles + templates


def get_role(client, role_id: str) -> dict | None:
    result = client.table("rbac_roles").select("*").eq("id", role_id).maybe_single().execute()
    return result.data if result else None


def create_role(client, company_id: str, *, name: str, description: str = "",
                 department_id: str | None = None, approval_level_id: str | None = None) -> dict:
    inserted = client.table("rbac_roles").insert({
        "company_id": company_id, "name": name, "description": description,
        "department_id": department_id, "approval_level_id": approval_level_id,
        "is_system": False, "is_template": False,
    }).execute()
    return inserted.data[0]


def update_role(client, role_id: str, updates: dict) -> dict | None:
    result = client.table("rbac_roles").update(updates).eq("id", role_id).execute()
    return (result.data or [None])[0]


def clone_role(client, company_id: str, source_role_id: str, new_name: str) -> dict:
    """Clone a role (template or company-owned) into a new company-owned
    role, copying its granted permissions."""
    source = get_role(client, source_role_id)
    if not source:
        raise ValueError("Source role not found")

    new_role = create_role(
        client, company_id, name=new_name, description=source.get("description", ""),
        department_id=source.get("department_id"), approval_level_id=source.get("approval_level_id"),
    )
    client.table("rbac_roles").update(
        {"cloned_from_role_id": source_role_id}
    ).eq("id", new_role["id"]).execute()
    new_role["cloned_from_role_id"] = source_role_id

    source_grants = (
        client.table("rbac_role_permissions").select("permission_id, granted")
        .eq("role_id", source_role_id).eq("granted", True)
        .execute()
    ).data or []
    if source_grants:
        client.table("rbac_role_permissions").insert([
            {"role_id": new_role["id"], "permission_id": g["permission_id"], "granted": True}
            for g in source_grants
        ]).execute()

    return new_role


def get_permission_catalog(client) -> list[dict]:
    return (
        client.table("rbac_permissions").select("id, module, action")
        .order("module").order("action")
        .execute()
    ).data or []


def get_role_permissions(client, role_id: str) -> list[dict]:
    """Full matrix row-set for one role: every catalog permission plus
    whether this role currently grants it (False if no row exists yet)."""
    catalog = get_permission_catalog(client)
    grants = (
        client.table("rbac_role_permissions").select("permission_id, granted")
        .eq("role_id", role_id)
        .execute()
    ).data or []
    granted_by_id = {g["permission_id"]: g["granted"] for g in grants}
    return [
        {"permission_id": p["id"], "module": p["module"], "action": p["action"],
         "granted": granted_by_id.get(p["id"], False)}
        for p in catalog
    ]


def set_role_permission(client, role_id: str, permission_id: str, granted: bool) -> dict:
    """Toggle one matrix cell. Returns {permission_id, old_value, new_value}
    for the caller to write into the audit log."""
    existing = (
        client.table("rbac_role_permissions").select("id, granted")
        .eq("role_id", role_id).eq("permission_id", permission_id)
        .maybe_single().execute()
    )
    row = existing.data if existing else None
    if row:
        client.table("rbac_role_permissions").update(
            {"granted": granted}
        ).eq("id", row["id"]).execute()
        return {"permission_id": permission_id, "old_value": row["granted"], "new_value": granted}

    client.table("rbac_role_permissions").insert({
        "role_id": role_id, "permission_id": permission_id, "granted": granted,
    }).execute()
    return {"permission_id": permission_id, "old_value": False, "new_value": granted}


def list_user_roles(client, user_id: str, company_id: str) -> list[dict]:
    return (
        client.table("rbac_user_roles").select("id, role_id, rbac_roles(id, name, status)")
        .eq("user_id", user_id).eq("company_id", company_id)
        .execute()
    ).data or []


def assign_user_role(client, user_id: str, role_id: str, company_id: str) -> dict:
    inserted = client.table("rbac_user_roles").insert({
        "user_id": user_id, "role_id": role_id, "company_id": company_id,
    }).execute()
    return inserted.data[0]


def revoke_user_role(client, user_id: str, role_id: str) -> None:
    client.table("rbac_user_roles").delete().eq("user_id", user_id).eq("role_id", role_id).execute()


def add_rbac_audit_entry(client, *, company_id: str | None, actor_user_id: str, reason: str,
                          target_user_id: str | None = None, department_id: str | None = None,
                          role_id: str | None = None, permission_id: str | None = None,
                          old_value=None, new_value=None) -> dict:
    """Insert one immutable audit row. Deliberately NOT best-effort/swallowed
    — raises if the insert fails, so the caller's mutation fails too rather
    than proceeding unaudited (see module docstring)."""
    if not reason or not reason.strip():
        raise ValueError("reason is required for every RBAC audit entry")

    inserted = client.table("rbac_audit_log").insert({
        "company_id": company_id,
        "actor_user_id": actor_user_id,
        "target_user_id": target_user_id,
        "department_id": department_id,
        "role_id": role_id,
        "permission_id": permission_id,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
    }).execute()
    return inserted.data[0]


def list_audit_log(client, company_id: str) -> list[dict]:
    return (
        client.table("rbac_audit_log").select("*")
        .eq("company_id", company_id).order("created_at", desc=True)
        .execute()
    ).data or []

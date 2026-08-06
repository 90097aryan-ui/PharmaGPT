"""
pharmagpt/db/org_structure_repo.py — CRUD for departments, designations, and
approval_levels, plus provision_org_defaults_for_company(): the one shared
routine that seeds a company's default org structure and role set. Called
from routes/companies.py::create_company for every new company; existing
companies are backfilled once by migrations/0015_rbac_org_framework_up.sql's
own INSERT statements (a one-time SQL backfill, not this Python path — see
docs/RBAC_FRAMEWORK.md for why the two aren't the same code path).

Department read/write for the underlying `departments` table continues to
go through pharmagpt/services/org_directory.py (migration 0014's existing
module for that table) rather than being duplicated here — this module only
adds the pieces 0014 didn't: designations, approval_levels, and role-
template cloning.
"""

from __future__ import annotations

from pharmagpt.services import org_directory
from pharmagpt.services.rbac_defaults import (
    DEFAULT_APPROVAL_LEVELS,
    DEFAULT_DEPARTMENTS,
    default_grants_for_role,
)


def list_departments(client, company_id: str) -> list[dict]:
    return (
        client.table("departments").select("id, name, department_code, status")
        .eq("company_id", company_id).order("name")
        .execute()
    ).data or []


def update_department(client, department_id: str, updates: dict) -> dict | None:
    result = client.table("departments").update(updates).eq("id", department_id).execute()
    return (result.data or [None])[0]


def list_designations(client, company_id: str) -> list[dict]:
    return (
        client.table("designations").select("id, name, status")
        .eq("company_id", company_id).order("name")
        .execute()
    ).data or []


def create_designation(client, company_id: str, name: str) -> dict:
    inserted = client.table("designations").insert({"company_id": company_id, "name": name}).execute()
    return inserted.data[0]


def update_designation(client, designation_id: str, updates: dict) -> dict | None:
    result = client.table("designations").update(updates).eq("id", designation_id).execute()
    return (result.data or [None])[0]


def list_approval_levels(client, company_id: str) -> list[dict]:
    return (
        client.table("approval_levels").select("id, name, sequence")
        .eq("company_id", company_id).order("sequence")
        .execute()
    ).data or []


def _permission_catalog_map(client) -> dict[tuple[str, str], str]:
    rows = client.table("rbac_permissions").select("id, module, action").execute().data or []
    return {(r["module"], r["action"]): r["id"] for r in rows}


def _clone_role_templates(client, company_id: str) -> list[dict]:
    templates = (
        client.table("rbac_roles").select("id, name, description, department_code")
        .eq("is_template", True)
        .execute()
    ).data or []
    if not templates:
        return []

    departments = list_departments(client, company_id)
    department_id_by_code = {d["department_code"]: d["id"] for d in departments if d.get("department_code")}
    permission_catalog = _permission_catalog_map(client)

    created = []
    for tpl in templates:
        existing = (
            client.table("rbac_roles").select("id")
            .eq("company_id", company_id).eq("name", tpl["name"])
            .maybe_single().execute()
        )
        if existing and existing.data:
            continue  # idempotent — already cloned for this company

        inserted = client.table("rbac_roles").insert({
            "company_id": company_id,
            "name": tpl["name"],
            "description": tpl["description"],
            "department_code": tpl.get("department_code"),
            "department_id": department_id_by_code.get(tpl.get("department_code")),
            "is_system": True,
            "is_template": False,
            "cloned_from_role_id": tpl["id"],
        }).execute()
        new_role = inserted.data[0]
        created.append(new_role)

        grant_rows = [
            {"role_id": new_role["id"], "permission_id": permission_catalog[pair], "granted": True}
            for pair in default_grants_for_role(tpl["name"])
            if pair in permission_catalog
        ]
        if grant_rows:
            client.table("rbac_role_permissions").insert(grant_rows).execute()

    return created


def provision_org_defaults_for_company(client, company_id: str) -> dict:
    """Idempotent. Safe to call more than once for the same company (e.g. a
    retry after a partial failure) — every step either upserts by a stable
    key or skips rows that already exist."""
    for name, code in DEFAULT_DEPARTMENTS:
        org_directory.find_or_create_department(client, company_id, name, code)

    existing_sequences = {lvl["sequence"] for lvl in list_approval_levels(client, company_id)}
    for name, sequence in DEFAULT_APPROVAL_LEVELS:
        if sequence not in existing_sequences:
            client.table("approval_levels").insert({
                "company_id": company_id, "name": name, "sequence": sequence,
            }).execute()

    created_roles = _clone_role_templates(client, company_id)
    return {
        "departments": len(DEFAULT_DEPARTMENTS),
        "approval_levels": len(DEFAULT_APPROVAL_LEVELS),
        "roles_created": len(created_roles),
    }

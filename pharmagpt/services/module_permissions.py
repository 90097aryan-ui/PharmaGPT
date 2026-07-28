"""
pharmagpt/services/module_permissions.py — read/write access to
`user_module_permissions` (migration 0014), keyed on the stable `modules.code`
so callers never need to know a `module_id`.

This is organizational capability data, not platform authorization: it is
not consulted by pharmagpt/auth/decorators.py::require_role or by any route
in this codebase. Wiring enforcement into routes is a deliberate future step,
not part of this module's job — see docs/NUTRA_DEMO_DATA.md's scope-boundary
note.

Every function takes an already-constructed Supabase client (works for both
a service-role client, e.g. scripts/seed_nutra_demo.py, and a future
RLS-scoped get_authenticated_client() caller) rather than constructing one
itself, matching pharmagpt/services/supabase_client.py's guidance that only
identity_admin.py builds a service-role client directly.
"""

from __future__ import annotations

VALID_MODULE_CODES = {"QMS", "VALIDATION", "DOCUMENT_GENERATOR"}


def get_module_id(client, code: str) -> str | None:
    """Resolve a `modules.code` (e.g. "QMS") to its `id`, or None if the
    code is unrecognized."""
    result = client.table("modules").select("id").eq("code", code).maybe_single().execute()
    row = result.data if result else None
    return row["id"] if row else None


def get_module_permissions(client, user_id: str) -> dict[str, bool]:
    """Return {"QMS": bool, "VALIDATION": bool, "DOCUMENT_GENERATOR": bool}.

    Fail-closed: a module with no row for this user (or an unrecognized
    code, which should never happen given the FK) defaults to False."""
    permissions = {code: False for code in VALID_MODULE_CODES}
    result = (
        client.table("user_module_permissions")
        .select("enabled, modules(code)")
        .eq("user_id", user_id)
        .execute()
    )
    for row in result.data or []:
        module = row.get("modules") or {}
        code = module.get("code")
        if code in permissions:
            permissions[code] = bool(row.get("enabled"))
    return permissions


def has_module_permission(client, user_id: str, code: str) -> bool:
    """True only if an enabled=True row exists for (user_id, module).
    False for a missing row or an unrecognized module code."""
    if code not in VALID_MODULE_CODES:
        return False
    return get_module_permissions(client, user_id).get(code, False)


def set_module_permission(client, user_id: str, company_id: str, code: str, enabled: bool) -> dict:
    """Upsert one (user_id, module) row on_conflict=(user_id, module_id).

    Raises ValueError if `code` is not a recognized module code."""
    if code not in VALID_MODULE_CODES:
        raise ValueError(f"Unrecognized module code: {code!r}")

    module_id = get_module_id(client, code)
    if module_id is None:
        raise ValueError(f"No 'modules' row for code {code!r} — has migrations/0014 been applied?")

    result = (
        client.table("user_module_permissions")
        .upsert(
            {"user_id": user_id, "company_id": company_id, "module_id": module_id, "enabled": enabled},
            on_conflict="user_id,module_id",
        )
        .execute()
    )
    return (result.data or [None])[0]

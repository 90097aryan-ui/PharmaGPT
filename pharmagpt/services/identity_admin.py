"""
pharmagpt/services/identity_admin.py — provision a brand-new PharmaGPT
identity (Supabase Auth user + `users` profile row) in one call.

Phase 3.5 (Enterprise Validation Platform security remediation). This is
the one live-request code path allowed to use
pharmagpt.services.supabase_client.get_service_role_client() — creating a
new Supabase Auth identity cannot happen under any Row Level Security
policy with the anon key, exactly the same structural reason
scripts/bootstrap_super_admin.py needs the service-role key to create the
very first Super Admin. Used by:
  - routes/companies.py — Super Admin creating a new company's first
    Company Admin (a standing capability, PLATFORM_ARCHITECTURE.md §7).
  - routes/users.py — a Company Admin inviting a new user into their own
    company.

Every caller must check @require_role(...) BEFORE calling into this module
— there is no other guard here beyond what the caller already enforced,
exactly mirroring bootstrap_super_admin.py's own trust model (a script run
by a human with .env access, versus here, a route reached only after the
global auth gate + role check already passed).

Uses auth.admin.create_user() with a generated temporary password and
email_confirm=True — deliberately NOT inviteUserByEmail() — so provisioning
a user never sends a real outbound email as a side effect of this phase's
implementation or its own tests. Relaying the temporary password to the new
user out-of-band is the inviting admin's responsibility; wiring an actual
email invitation is a distinct, later, explicitly-approved product decision.
"""

from __future__ import annotations

import secrets

from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

from pharmagpt.services.supabase_client import get_service_role_client


class IdentityProvisioningError(Exception):
    """Raised when a new identity cannot be created or its profile row
    cannot be inserted. Callers should surface this as a clean 4xx/5xx,
    never a raw traceback."""


def _generate_temporary_password() -> str:
    return secrets.token_urlsafe(16)


def provision_user(*, email: str, display_name: str, company_id: str | None, role_id: int) -> dict:
    """Create a new Supabase Auth identity and its `users` profile row.

    Returns {"auth_user_id": ..., "temporary_password": ...}. The temporary
    password is generated here and returned exactly once — it is never
    stored by this application beyond the return value.

    Raises IdentityProvisioningError on any failure (email already
    registered without an existing profile row for it, Postgres insert
    failure, etc.) — callers should catch this and return a clean error
    response rather than letting a raw exception surface.
    """
    client = get_service_role_client()
    temporary_password = _generate_temporary_password()

    try:
        response = client.auth.admin.create_user({
            "email": email,
            "password": temporary_password,
            "email_confirm": True,
            "user_metadata": {"display_name": display_name},
        })
        auth_user = response.user
    except AuthApiError as exc:
        raise IdentityProvisioningError(f"Could not create identity for {email}: {exc}") from exc

    try:
        client.table("users").insert({
            "id": auth_user.id,
            "company_id": company_id,
            "role_id": role_id,
            "display_name": display_name,
            "status": "active",
        }).execute()
    except APIError as exc:
        raise IdentityProvisioningError(
            f"Auth identity created for {email} but the profile row failed to insert: {exc}"
        ) from exc

    return {"auth_user_id": auth_user.id, "temporary_password": temporary_password}

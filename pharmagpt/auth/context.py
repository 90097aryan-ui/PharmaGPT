"""
pharmagpt/auth/context.py — Supabase Auth verification and tenant-context resolution.

Verification is delegated to Supabase itself (`auth.get_user`) rather than
performed locally against a JWT signing secret. This means the application
never holds any credential more powerful than the anon key: token validity,
expiry, and revocation are all checked server-side by Supabase Auth on every
call, and the only local state this module touches is our own `users` table,
read under Row Level Security as the requesting user
(see pharmagpt/services/supabase_client.py:get_authenticated_client).
"""

from dataclasses import dataclass
from typing import Optional

from pharmagpt.services.supabase_client import get_authenticated_client


class AuthenticationError(Exception):
    """Raised when a bearer token is missing, invalid, expired, or belongs
    to an identity with no active PharmaGPT profile."""


@dataclass(frozen=True)
class TenantContext:
    """The resolved identity + tenancy facts for one authenticated request."""

    user_id: str
    email: str
    display_name: str
    role: str
    company_id: Optional[str]  # None only for role == "super_admin"


def resolve_tenant_context(access_token: str) -> TenantContext:
    """Verify a Supabase Auth access token and resolve it to a TenantContext.

    Raises AuthenticationError for any failure — missing/malformed token,
    a token Supabase rejects as invalid or expired, an identity with no
    corresponding `users` row, or a deactivated account. Never returns a
    partially-populated context.
    """
    if not access_token:
        raise AuthenticationError("Missing bearer token")

    client = get_authenticated_client(access_token)

    try:
        auth_response = client.auth.get_user(access_token)
    except Exception as exc:
        raise AuthenticationError("Invalid or expired session") from exc

    supabase_user = getattr(auth_response, "user", None)
    if supabase_user is None:
        raise AuthenticationError("Invalid or expired session")

    profile_result = (
        client.table("users")
        .select("company_id, display_name, status, roles(name)")
        .eq("id", supabase_user.id)
        .maybe_single()
        .execute()
    )
    profile = profile_result.data if profile_result else None
    if profile is None:
        raise AuthenticationError("No PharmaGPT profile exists for this identity")

    if profile["status"] != "active":
        raise AuthenticationError("This account has been deactivated")

    role_row = profile.get("roles")
    if not role_row or not role_row.get("name"):
        raise AuthenticationError("This account has no role assigned")

    return TenantContext(
        user_id=supabase_user.id,
        email=supabase_user.email,
        display_name=profile["display_name"],
        role=role_row["name"],
        company_id=profile["company_id"],
    )

"""
scripts/bootstrap_super_admin.py — One-time Super Admin bootstrap.

CLI-only. Never imported by pharmagpt/app.py and exposes no HTTP route —
there is no route anywhere that calls into this module. This is the one
deliberate, explicitly-approved use of SUPABASE_SERVICE_ROLE_KEY in this
codebase: creating the very first Super Admin is the one operation that
cannot happen under RLS as an ordinary authenticated user, because no user
exists yet to be authenticated as. Every other Phase 2 auth code path
(pharmagpt/auth/, routes/auth.py) uses the anon key only.

Usage:
    python scripts/bootstrap_super_admin.py

Reads from .env (nothing is ever hardcoded):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    SUPER_ADMIN_EMAIL
    SUPER_ADMIN_PASSWORD
    SUPER_ADMIN_DISPLAY_NAME   (optional, defaults to "Super Admin")

Idempotent and self-disabling: if a Super Admin already exists, the script
detects it via the `users` table and exits without making any change
(requirement 5 — detecting an existing Super Admin is what disables it).
Safe to re-run after a partial failure: if a prior run created the Supabase
Auth identity but crashed before inserting the `users` row, this run reuses
that identity instead of erroring out or creating a duplicate.
"""

import os
import sys

from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError

SUPER_ADMIN_ROLE_NAME = "super_admin"
REQUIRED_ENV_VARS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPER_ADMIN_EMAIL",
    "SUPER_ADMIN_PASSWORD",
)


class BootstrapError(Exception):
    """Raised for any condition that should stop the bootstrap script."""


def load_config(env: dict) -> dict:
    """Pull bootstrap configuration out of an environment mapping.

    Takes a plain dict (rather than reading os.environ directly) so tests
    can exercise the validation logic without touching real environment
    variables or a real .env file.
    """
    config = {name: env.get(name) for name in REQUIRED_ENV_VARS}
    config["SUPER_ADMIN_DISPLAY_NAME"] = env.get("SUPER_ADMIN_DISPLAY_NAME") or "Super Admin"

    missing = [name for name in REQUIRED_ENV_VARS if not config[name]]
    if missing:
        raise BootstrapError("Missing required .env values: " + ", ".join(missing))

    return config


def build_service_role_client(supabase_url: str, service_role_key: str) -> Client:
    """Construct a Supabase client authorised as service_role.

    This script needs its own client because it must run before any user or
    route exists to authenticate through. Phase 3.5 adds the one other,
    narrowly-scoped use of this key in the codebase —
    pharmagpt/services/supabase_client.py::get_service_role_client(), used
    only by pharmagpt/services/identity_admin.py behind an authenticated,
    @require_role-checked route, for the same "mint a new Auth identity"
    operation this script performs once at bootstrap. Every other Flask
    request-handling code path still uses the anon key only.
    """
    return create_client(supabase_url, service_role_key)


def get_super_admin_role_id(client: Client) -> int:
    result = (
        client.table("roles")
        .select("id")
        .eq("name", SUPER_ADMIN_ROLE_NAME)
        .single()
        .execute()
    )
    if not result.data:
        raise BootstrapError(
            f"No '{SUPER_ADMIN_ROLE_NAME}' row in roles table — "
            "has migrations/0001_identity_tenancy_up.sql been applied?"
        )
    return result.data["id"]


def find_existing_super_admin(client: Client, super_admin_role_id: int):
    """Return the first `users` row with the Super Admin role, or None."""
    result = (
        client.table("users")
        .select("id, display_name")
        .eq("role_id", super_admin_role_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def find_auth_user_by_email(client: Client, email: str):
    """Look up an existing Supabase Auth identity by email.

    The admin API has no direct "get by email", so this pages through
    list_users(). Only reached on the rare resume-after-partial-failure
    path, so the extra listing cost is a non-issue for a one-time script.
    """
    page = 1
    per_page = 200
    while True:
        users = client.auth.admin.list_users(page=page, per_page=per_page)
        if not users:
            return None
        for user in users:
            if user.email and user.email.lower() == email.lower():
                return user
        if len(users) < per_page:
            return None
        page += 1


def create_super_admin_auth_identity(client: Client, email: str, password: str, display_name: str):
    try:
        response = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"display_name": display_name},
            }
        )
        return response.user
    except AuthApiError as exc:
        message = (exc.message or "").lower()
        if "already" in message and "registered" in message:
            existing = find_auth_user_by_email(client, email)
            if existing is not None:
                return existing
        raise BootstrapError(f"Failed to create Super Admin Auth identity: {exc}") from exc


def insert_super_admin_profile(client: Client, auth_user_id: str, display_name: str, super_admin_role_id: int) -> None:
    client.table("users").insert(
        {
            "id": auth_user_id,
            "company_id": None,
            "role_id": super_admin_role_id,
            "display_name": display_name,
            "status": "active",
        }
    ).execute()


def bootstrap_super_admin(client: Client, email: str, password: str, display_name: str) -> str:
    """Run the bootstrap against an already-constructed service-role client.

    Returns a human-readable status message. Idempotent: if a Super Admin
    already exists, this makes no changes and returns immediately.
    """
    super_admin_role_id = get_super_admin_role_id(client)

    existing = find_existing_super_admin(client, super_admin_role_id)
    if existing is not None:
        return (
            f"Super Admin already exists (id={existing['id']}, "
            f"display_name={existing['display_name']!r}) — bootstrap is a no-op."
        )

    auth_user = create_super_admin_auth_identity(client, email, password, display_name)

    try:
        insert_super_admin_profile(client, auth_user.id, display_name, super_admin_role_id)
    except APIError as exc:
        # Only benign under a race: someone else finished inserting the
        # profile row between our check above and this insert. Re-check
        # before deciding this was actually a failure.
        existing = find_existing_super_admin(client, super_admin_role_id)
        if existing is not None:
            return (
                f"Super Admin already exists (id={existing['id']}, "
                f"display_name={existing['display_name']!r}) — bootstrap is a no-op."
            )
        raise BootstrapError(f"Failed to insert Super Admin profile row: {exc}") from exc

    return f"Super Admin created (id={auth_user.id}, email={email})."


def main() -> int:
    load_dotenv()

    try:
        config = load_config(os.environ)
        client = build_service_role_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
        message = bootstrap_super_admin(
            client,
            email=config["SUPER_ADMIN_EMAIL"],
            password=config["SUPER_ADMIN_PASSWORD"],
            display_name=config["SUPER_ADMIN_DISPLAY_NAME"],
        )
    except BootstrapError as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())

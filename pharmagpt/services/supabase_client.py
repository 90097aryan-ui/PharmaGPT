import os
from functools import wraps

from flask import jsonify
from postgrest.exceptions import APIError
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    """Read a required Supabase env var, raising only at the point a
    Supabase-backed code path actually runs (auth, or a domain repo with its
    *_BACKEND flag set to "dual") — never at module import time. This lets
    the app boot with no Supabase configuration at all when nothing calls
    into this module (see pharmagpt/config.py's *_BACKEND flags, all
    defaulting to "sqlite")."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not found in .env")
    return value


def get_authenticated_client(access_token: str) -> Client:
    """Return a Supabase client scoped to one user's access token.

    Uses the anon key only (never the service role). Attaching the user's
    token makes PostgREST evaluate Row Level Security as that authenticated
    user (`auth.uid()` resolves to their id) instead of as an anonymous
    caller — this is what lets application code read/write tenant tables
    under RLS without a service-role key.

    A fresh client is created per call, since Flask serves concurrent
    requests from different users within the same worker process and no
    shared client instance may accumulate one user's token or session.
    """
    client = create_client(_require_env("SUPABASE_URL"), _require_env("SUPABASE_ANON_KEY"))
    client.postgrest.auth(access_token)
    return client


def get_anonymous_client() -> Client:
    """Return a fresh, credential-free Supabase client (anon key only).

    Used for calls that establish a session rather than presenting one
    (sign-in, password reset). `auth.sign_in_with_password` and similar
    gotrue methods save the resulting session onto the *client instance*
    they were called on — a shared client would leak one concurrent login's
    session state into another's request. A fresh client per call avoids
    that entirely.
    """
    return create_client(_require_env("SUPABASE_URL"), _require_env("SUPABASE_ANON_KEY"))


def get_service_role_client() -> Client:
    """Return a Supabase client authorised as service_role — bypasses RLS
    entirely. Only ever call this from pharmagpt/services/identity_admin.py
    (Phase 3.5), the one live-request code path allowed to use it, for the
    one operation the anon key structurally cannot perform: minting a brand
    new Supabase Auth identity (creating a user is not something a Row Level
    Security policy can grant under the anon key, regardless of how it's
    written). Every other admin/business-data operation in this codebase —
    Company/User CRUD, business-data reads/writes — uses
    get_authenticated_client() and RLS instead.

    scripts/bootstrap_super_admin.py builds its own equivalent client
    directly (it must run before any user or route exists to call through);
    this is that same pattern's only other, narrowly-scoped use, reached
    through an authenticated, role-checked Flask route instead of a CLI
    script.
    """
    return create_client(_require_env("SUPABASE_URL"), _require_env("SUPABASE_SERVICE_ROLE_KEY"))


def handle_postgrest_errors(view_func):
    """Route decorator: catch postgrest.exceptions.APIError (e.g. a missing
    RLS GRANT — a real, observed failure mode the first time this phase's
    new migrations haven't been applied yet) and any other exception from a
    Supabase call, returning a clean JSON 500 instead of letting it surface
    as an unhandled exception / raw debugger page. Applied to
    routes/companies.py, routes/users.py, and the Assume Company Context
    endpoints in routes/auth.py — the first live-request code paths that
    call Supabase directly as the *primary* data path (every other Supabase
    caller in this codebase is a best-effort dual-write with its own
    try/except at the call site)."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        try:
            return view_func(*args, **kwargs)
        except APIError as exc:
            return jsonify({"error": f"Database error: {exc.message}"}), 500
        except Exception as exc:
            return jsonify({"error": f"Unexpected error: {exc}"}), 500

    return wrapped
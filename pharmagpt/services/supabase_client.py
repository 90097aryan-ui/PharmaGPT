import os
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
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL not found in .env")

if not SUPABASE_ANON_KEY:
    raise ValueError("SUPABASE_ANON_KEY not found in .env")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_ANON_KEY
)


def get_authenticated_client(access_token: str) -> Client:
    """Return a Supabase client scoped to one user's access token.

    Uses the anon key only (never the service role). Attaching the user's
    token makes PostgREST evaluate Row Level Security as that authenticated
    user (`auth.uid()` resolves to their id) instead of as an anonymous
    caller — this is what lets application code read/write tenant tables
    under RLS without a service-role key.

    A fresh client is created per call rather than mutating the shared
    `supabase` singleton above, since Flask serves concurrent requests from
    different users within the same worker process and the singleton must
    stay anonymous/token-free for any code path that doesn't hold a user
    token.
    """
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client


def get_anonymous_client() -> Client:
    """Return a fresh, credential-free Supabase client (anon key only).

    Used for calls that establish a session rather than presenting one
    (sign-in, password reset). `auth.sign_in_with_password` and similar
    gotrue methods save the resulting session onto the *client instance*
    they were called on — reusing the shared `supabase` singleton for this
    would leak one concurrent login's session state into another's request.
    A fresh client per call avoids that entirely.
    """
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
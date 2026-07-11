"""
pharmagpt/auth/decorators.py — Flask route protection built on pharmagpt.auth.context.

Not yet wired into app.py or any blueprint (that's IMPLEMENTATION_ROADMAP.md
Phase 2 step 2.5, once routes/auth.py exists and there is a login flow to
issue tokens in the first place). Written and unit-tested now so step 2.5 is
a pure wiring change, not new logic.
"""

from functools import wraps

from flask import g, jsonify, request

from pharmagpt.auth.context import AuthenticationError, resolve_tenant_context

BEARER_PREFIX = "Bearer "


def extract_bearer_token() -> str:
    """Return the bearer token from the current request's Authorization
    header, or "" if it is missing or not a Bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith(BEARER_PREFIX):
        return ""
    return auth_header[len(BEARER_PREFIX):].strip()


def require_auth(view_func):
    """Reject the request unless it carries a valid Supabase Auth bearer
    token, and make the resolved TenantContext available as `g.tenant`."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        access_token = extract_bearer_token()
        if not access_token:
            return jsonify({"error": "Missing or malformed Authorization header"}), 401

        try:
            g.tenant = resolve_tenant_context(access_token)
        except AuthenticationError as exc:
            return jsonify({"error": str(exc)}), 401

        return view_func(*args, **kwargs)

    return wrapped

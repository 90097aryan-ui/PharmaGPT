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
    token, and make the resolved TenantContext available as `g.tenant`.

    If `g.tenant` is already set (the global before_request gate in
    pharmagpt/auth/middleware.py already resolved it for every non-exempt
    route, including Assume Company Context's company_id override — see
    middleware.py::apply_assumed_company_context), this is a no-op
    passthrough rather than a second resolution: re-resolving here would
    silently discard that override with a fresh, non-assumed TenantContext.
    Still performs its own full resolution when `g.tenant` isn't already
    present (e.g. exercised directly against a throwaway app in tests, or a
    future route exempted from the global gate)."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if hasattr(g, "tenant"):
            return view_func(*args, **kwargs)

        access_token = extract_bearer_token()
        if not access_token:
            return jsonify({"error": "Missing or malformed Authorization header"}), 401

        try:
            g.tenant = resolve_tenant_context(access_token)
        except AuthenticationError as exc:
            return jsonify({"error": str(exc)}), 401

        return view_func(*args, **kwargs)

    return wrapped


def require_role(*allowed_roles: str):
    """Reject the request (403) unless `g.tenant.role` is one of
    `allowed_roles`. The four roles are frozen at v1.0 (migrations/0001_
    identity_tenancy_up.sql, PLATFORM_ARCHITECTURE.md §7):
    super_admin | company_admin | reviewer_qa | user.

    Must run after the global auth gate (pharmagpt/auth/middleware.py) has
    already set `g.tenant` — every route reached in production already has
    it; this decorator only narrows which roles may proceed.

    Usage: @require_role("company_admin") or @require_role("company_admin", "reviewer_qa")
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if g.tenant.role not in allowed_roles:
                return jsonify({
                    "error": f"This action requires one of these roles: {', '.join(allowed_roles)}",
                }), 403
            return view_func(*args, **kwargs)

        return wrapped

    return decorator

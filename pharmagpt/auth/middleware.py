"""
pharmagpt/auth/middleware.py — global authentication gate for the Flask app.

Wired into pharmagpt/app.py by register_auth_middleware() (Phase 2 step
2.5). Every request must carry a valid Supabase Auth bearer token and
resolve to a TenantContext (available as `g.tenant`), except the small,
fixed set of paths that must be reachable before any session exists:

    /            the SPA shell (templates/index.html) — must stay public
                 so a logged-out browser has something to load the login
                 UI from at all (Phase 2 step 2.6 puts that UI here).
    /auth/login  obviously can't itself require a session.
    /health      infrastructure/uptime check.
    /static/*    JS/CSS/images the SPA shell needs before login.
    /favicon.ico requested unconditionally by browsers.

This is a single before_request hook rather than a per-route decorator so
that every existing route in routes/ (projects, chat, docs, qms_*, risk,
urs, qual, report, equipment, knowledge_base, dashboard, validation) is
protected uniformly with zero changes to any of those files.
"""

from flask import Flask, g, jsonify, request

from pharmagpt.auth.context import AuthenticationError, resolve_tenant_context
from pharmagpt.auth.decorators import extract_bearer_token

EXEMPT_PATHS = frozenset({
    "/",
    "/auth/login",
    "/health",
    "/favicon.ico",
})
EXEMPT_PREFIXES = ("/static/",)


def is_exempt(path: str) -> bool:
    return path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES)


def register_auth_middleware(app: Flask) -> None:
    """Attach the global before_request authentication gate to `app`."""

    @app.before_request
    def _require_authentication():
        if is_exempt(request.path):
            return None

        access_token = extract_bearer_token()
        if not access_token:
            return jsonify({"error": "Missing or malformed Authorization header"}), 401

        try:
            g.tenant = resolve_tenant_context(access_token)
        except AuthenticationError as exc:
            return jsonify({"error": str(exc)}), 401

        return None

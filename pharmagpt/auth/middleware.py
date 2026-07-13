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

Session-cookie fallback (Stabilization Iteration 2)
----------------------------------------------------
Auth here is bearer-token only: the frontend (static/js/auth.js) stores the
Supabase access token in localStorage/sessionStorage and attaches it via a
patched window.fetch(). That works for every fetch() call, but a plain
browser navigation — e.g. the DOCX export `<a download>` link in
static/js/urs.js — cannot carry a custom Authorization header at all; the
request that reaches this hook has none. Previously that meant this hook
always 401-JSON'd those requests, which Chrome's download manager renders
as its generic "Try to sign in to the site. Then download again." error —
the reported DOCX download bug.

Fix: when a request has no Authorization header, fall back to the access
token mirrored into the signed, HttpOnly Flask session cookie at login
(see routes/auth.py login()/logout()). This never overrides a header that
is present — if a header is present it is authoritative and any resolution
failure still 401s immediately, exactly as before. When a header-based
resolution *does* succeed, the session cookie is (re-)synced to that same
token on every request, so it can never go stale relative to whatever the
frontend is currently using (e.g. after a client-side token refresh).
"""

from flask import Flask, g, jsonify, request, session

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

        if access_token:
            try:
                g.tenant = resolve_tenant_context(access_token)
            except AuthenticationError as exc:
                return jsonify({"error": str(exc)}), 401
            # Keep the session-cookie fallback in sync with whatever token
            # the frontend is actively using, so it's never stale for a
            # subsequent header-less navigation (e.g. a download link).
            session["access_token"] = access_token
            return None

        # No Authorization header at all — this is the shape of a plain
        # browser navigation, not a fetch() call. Fall back to the token
        # mirrored into the session cookie at login, if any.
        cookie_token = session.get("access_token")
        if not cookie_token:
            return jsonify({"error": "Missing or malformed Authorization header"}), 401

        try:
            g.tenant = resolve_tenant_context(cookie_token)
        except AuthenticationError as exc:
            session.pop("access_token", None)
            return jsonify({"error": str(exc)}), 401

        return None

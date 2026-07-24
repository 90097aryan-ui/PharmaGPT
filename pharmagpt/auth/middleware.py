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

Assume Company Context (Phase 3.5)
-----------------------------------
A live Enterprise Acceptance Test found Super Admin (company_id IS NULL)
could read every company's business data unfiltered on several list
endpoints — those routes now guard against it (pharmagpt/tenancy.py-style
403s across routes/), but Super Admin legitimately needs an explicit,
logged, time-boxed way to view one specific company's data on purpose
(PLATFORM_ARCHITECTURE.md §7/§13.2's "break-glass" concept, previously
schema-only — see migrations/0010_break_glass_rls_up.sql). After the real
identity resolves via resolve_tenant_context(), if that identity is a
Super Admin with an active (unexpired, unrevoked) break_glass_access grant
recorded in this session, `g.tenant` is rebuilt (TenantContext is a frozen
dataclass — never mutated) with `company_id` overridden to the assumed
company for the remainder of this one request only. This is a Flask-layer
override for the SQLite business-data path (100% of live business data is
still SQLite, not Postgres/RLS, per docs/PHASE3_FLAGS.md) — it does not and
cannot grant any elevated *role*; a Super Admin acting inside an assumed
company is still `role == "super_admin"`, so any route gated by
`@require_role("company_admin", ...)` still correctly denies them. Assumed
context only ever affects which company_id a read/list route sees.
"""

import dataclasses
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request, session

from pharmagpt.auth.context import AuthenticationError, resolve_tenant_context
from pharmagpt.auth.decorators import extract_bearer_token
from pharmagpt.services.supabase_client import get_authenticated_client

EXEMPT_PATHS = frozenset({
    "/",
    "/auth/login",
    "/health",
    "/favicon.ico",
})
EXEMPT_PREFIXES = ("/static/",)


def is_exempt(path: str) -> bool:
    return path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES)


def _grant_is_active(row: dict | None) -> bool:
    if not row or row.get("revoked_at"):
        return False
    expires_at = row.get("expires_at")
    if not expires_at:
        return False
    try:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return expires_dt > datetime.now(timezone.utc)


def apply_assumed_company_context(tenant, access_token: str):
    """Return `tenant` unchanged unless it's a Super Admin with an active
    Assume Company Context grant recorded in this session — in which case
    return a *new* TenantContext (never mutate — frozen dataclass) with
    company_id overridden to the assumed company. Clears stale session keys
    if the grant has expired or been revoked, so the request continues as
    the real (standing, company_id=None) Super Admin identity rather than
    erroring mid-session."""
    if tenant.role != "super_admin":
        return tenant

    assumed_company_id = session.get("assumed_company_id")
    break_glass_id = session.get("break_glass_id")
    if not assumed_company_id or not break_glass_id:
        return tenant

    try:
        client = get_authenticated_client(access_token)
        result = (
            client.table("break_glass_access")
            .select("expires_at, revoked_at")
            .eq("id", break_glass_id)
            .maybe_single()
            .execute()
        )
        row = result.data if result else None
    except Exception:
        row = None

    if not _grant_is_active(row):
        session.pop("assumed_company_id", None)
        session.pop("break_glass_id", None)
        return tenant

    return dataclasses.replace(tenant, company_id=assumed_company_id)


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
            g.tenant = apply_assumed_company_context(g.tenant, access_token)
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

        g.tenant = apply_assumed_company_context(g.tenant, cookie_token)
        return None

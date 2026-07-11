"""
routes/auth.py — Supabase Auth-backed login/logout/session endpoints.

Routes
------
POST /auth/login    email + password -> Supabase session + resolved tenant context
POST /auth/logout   revoke the caller's current Supabase session
GET  /auth/me        the caller's resolved tenant context

Credential handling is entirely Supabase Auth's responsibility (anon key
only, PLATFORM_ARCHITECTURE.md §7's "no custom-built password storage or
session mechanism"). This module never sees, stores, or compares a
password — it forwards email/password to `sign_in_with_password` and
returns whatever Supabase decides.

Not registered on the Flask app yet — that's IMPLEMENTATION_ROADMAP.md
Phase 2 step 2.5.
"""

from dataclasses import asdict

from flask import Blueprint, g, jsonify, request
from supabase_auth.errors import AuthApiError

from pharmagpt.auth.context import AuthenticationError, TenantContext, resolve_tenant_context
from pharmagpt.auth.decorators import extract_bearer_token, require_auth
from pharmagpt.services.supabase_client import get_anonymous_client

bp = Blueprint("auth", __name__)


def _tenant_to_dict(tenant: TenantContext) -> dict:
    return asdict(tenant)


@bp.route("/auth/login", methods=["POST"])
def login():
    """Exchange an email/password for a Supabase session.

    Request body: {"email": "...", "password": "..."}
    Response: {"access_token", "refresh_token", "expires_at", "user": {...}}
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    client = get_anonymous_client()

    try:
        auth_response = client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except AuthApiError:
        return jsonify({"error": "Invalid email or password"}), 401

    session = auth_response.session
    if session is None:
        return jsonify({"error": "Invalid email or password"}), 401

    try:
        tenant = resolve_tenant_context(session.access_token)
    except AuthenticationError as exc:
        # Credentials were valid at Supabase but there is no active
        # PharmaGPT profile for this identity (not yet provisioned, or
        # deactivated) — do not hand back a session for it.
        return jsonify({"error": str(exc)}), 403

    return jsonify({
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
        "user": _tenant_to_dict(tenant),
    })


@bp.route("/auth/logout", methods=["POST"])
@require_auth
def logout():
    """Revoke the caller's current Supabase session (all refresh tokens)."""
    access_token = extract_bearer_token()
    client = get_anonymous_client()
    client.auth.admin.sign_out(access_token, "global")
    return jsonify({"success": True})


@bp.route("/auth/me", methods=["GET"])
@require_auth
def me():
    """Return the resolved tenant context for the caller's current session."""
    return jsonify(_tenant_to_dict(g.tenant))

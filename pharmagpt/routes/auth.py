"""
routes/auth.py — Supabase Auth-backed login/logout/session endpoints.

Routes
------
POST /auth/login              email + password -> Supabase session + resolved tenant context
POST /auth/logout             revoke the caller's current Supabase session
GET  /auth/me                  the caller's resolved tenant context (+ assumed-context info)
GET  /auth/companies           list companies (Super Admin only) — feeds the Assume Context picker
POST /auth/assume-company      Super Admin: start a time-boxed, logged Assume Company Context grant
POST /auth/end-assume-company  Super Admin: revoke the active grant early

Credential handling is entirely Supabase Auth's responsibility (anon key
only, PLATFORM_ARCHITECTURE.md §7's "no custom-built password storage or
session mechanism"). This module never sees, stores, or compares a
password — it forwards email/password to `sign_in_with_password` and
returns whatever Supabase decides.

Assume Company Context (Phase 3.5) — see pharmagpt/auth/middleware.py's
module docstring for the full request-time mechanics. This file only
creates/revokes the break_glass_access grant and session keys; the
per-request company_id override itself lives in middleware.py.
"""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from flask import session as flask_session
from supabase_auth.errors import AuthApiError

from pharmagpt import audit
from pharmagpt import audit_events as evt
from pharmagpt.auth.context import AuthenticationError, TenantContext, resolve_tenant_context
from pharmagpt.auth.decorators import extract_bearer_token, require_auth, require_role
from pharmagpt.auth.workspace_access import accessible_workspaces_for
from pharmagpt.services.supabase_client import get_anonymous_client, get_authenticated_client, handle_postgrest_errors

bp = Blueprint("auth", __name__)

DEFAULT_ASSUME_DURATION_MINUTES = 60
MAX_ASSUME_DURATION_MINUTES = 240


def _tenant_to_dict(tenant: TenantContext) -> dict:
    body = asdict(tenant)
    body["accessible_workspaces"] = accessible_workspaces_for(tenant)
    return body


def _revoke_active_grant(access_token: str) -> None:
    """Set revoked_at on the current session's Assume Company Context grant,
    if any, and clear the session keys. Best-effort: a Postgres failure here
    must not block logout/end-assume itself."""
    break_glass_id = flask_session.pop("break_glass_id", None)
    flask_session.pop("assumed_company_id", None)
    if not break_glass_id:
        return
    try:
        client = get_authenticated_client(access_token)
        client.table("break_glass_access").update(
            {"revoked_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", break_glass_id).execute()
    except Exception:
        pass


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
        audit.log_unauthenticated("auth", 0, evt.AUTH_LOGIN_FAILURE,
                                   attempted_identifier=email, reason="Invalid credentials")
        return jsonify({"error": "Invalid email or password"}), 401

    session = auth_response.session
    if session is None:
        audit.log_unauthenticated("auth", 0, evt.AUTH_LOGIN_FAILURE,
                                   attempted_identifier=email, reason="No session returned")
        return jsonify({"error": "Invalid email or password"}), 401

    try:
        tenant = resolve_tenant_context(session.access_token)
    except AuthenticationError as exc:
        # Credentials were valid at Supabase but there is no active
        # PharmaGPT profile for this identity (not yet provisioned, or
        # deactivated) — do not hand back a session for it.
        audit.log_unauthenticated("auth", 0, evt.AUTH_LOGIN_FAILURE,
                                   attempted_identifier=email, reason=str(exc))
        return jsonify({"error": str(exc)}), 403

    # Mirror the access token into a signed, HttpOnly Flask session cookie
    # as a secondary auth channel alongside the primary bearer-token one.
    # This exists for exactly one reason: a browser navigation (e.g. the
    # DOCX export <a download> link in static/js/urs.js) cannot attach a
    # custom Authorization header, only cookies — so without this, any
    # download triggered by a plain link click has no way to prove who it
    # is and gets rejected. auth/middleware.py's before_request hook checks
    # this cookie only when a request has no Authorization header at all,
    # and re-syncs it on every authenticated header-based request so it
    # never goes stale relative to whatever token the frontend is currently
    # using. Never used in place of the header when a header is present.
    flask_session["access_token"] = session.access_token

    # Server-verified identity (just resolved above, never client-supplied)
    # — set g.tenant so audit.log()'s normal, non-spoofable derivation
    # applies here exactly as it does for every other authenticated call
    # site, rather than adding a second actor-resolution path. Harmless
    # side channel for this request only: the response below is already
    # built from the local `tenant` variable, not from g.tenant.
    g.tenant = tenant
    audit.log("auth", 0, evt.AUTH_LOGIN_SUCCESS)

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
    _revoke_active_grant(access_token)
    client = get_anonymous_client()
    client.auth.admin.sign_out(access_token, "global")
    # g.tenant is still the caller's real identity here (set by the global
    # auth gate before this view ran) — log before clearing the session,
    # which only affects Flask's own cookie, not g.tenant.
    audit.log("auth", 0, evt.AUTH_LOGOUT, detail="All refresh tokens revoked (global sign-out)")
    flask_session.clear()
    return jsonify({"success": True})


@bp.route("/auth/me", methods=["GET"])
@require_auth
def me():
    """Return the resolved tenant context for the caller's current session,
    plus Assume Company Context info when an active grant is present —
    `g.tenant.company_id` is already the *effective* (possibly assumed) one
    by the time this runs (pharmagpt/auth/middleware.py), so the frontend
    banner needs the assumed company's name and the grant's expiry on top
    of that to render "Acting as Company X, expires in Ny min"."""
    body = _tenant_to_dict(g.tenant)
    break_glass_id = flask_session.get("break_glass_id")
    if break_glass_id and g.tenant.role == "super_admin":
        try:
            client = get_authenticated_client(extract_bearer_token())
            grant = (
                client.table("break_glass_access")
                .select("expires_at, revoked_at, companies(legal_name)")
                .eq("id", break_glass_id)
                .maybe_single()
                .execute()
            )
            row = grant.data if grant else None
        except Exception:
            row = None
        if row and not row.get("revoked_at"):
            body["assumed_company_id"] = g.tenant.company_id
            body["assumed_company_name"] = (row.get("companies") or {}).get("legal_name")
            body["break_glass_expires_at"] = row.get("expires_at")
    return jsonify(body)


@bp.route("/auth/companies", methods=["GET"])
@require_role("super_admin")
@handle_postgrest_errors
def list_companies_for_assume():
    """List companies for the Assume Company Context picker. Super Admin only."""
    client = get_authenticated_client(extract_bearer_token())
    result = client.table("companies").select("id, legal_name, status").order("legal_name").execute()
    return jsonify(result.data or [])


@bp.route("/auth/assume-company", methods=["POST"])
@require_role("super_admin")
@handle_postgrest_errors
def assume_company():
    """Start a time-boxed, logged Assume Company Context grant.

    Body: {"company_id": "...", "reason": "...", "duration_minutes": 60}
    reason is required — mirrors the non-nullable break_glass_access.reason
    column and the who/why discipline already used by
    pharmagpt/tenancy.py::signing_identity elsewhere in this codebase.
    """
    body = request.get_json(silent=True) or {}
    company_id = (body.get("company_id") or "").strip()
    reason = (body.get("reason") or "").strip()
    duration_minutes = body.get("duration_minutes") or DEFAULT_ASSUME_DURATION_MINUTES

    if not company_id:
        return jsonify({"error": "company_id is required"}), 400
    if not reason:
        return jsonify({"error": "reason is required"}), 400
    try:
        duration_minutes = min(int(duration_minutes), MAX_ASSUME_DURATION_MINUTES)
        if duration_minutes <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "duration_minutes must be a positive integer"}), 400

    access_token = extract_bearer_token()
    client = get_authenticated_client(access_token)

    company = client.table("companies").select("id, legal_name, status").eq("id", company_id).maybe_single().execute()
    company_row = company.data if company else None
    if not company_row:
        return jsonify({"error": "Company not found"}), 404
    if company_row.get("status") != "active":
        return jsonify({"error": "Cannot assume context for a suspended company"}), 400

    # Revoke any grant already active for this session before starting a new
    # one, so a Super Admin is never implicitly holding two open grants.
    #
    # Yuktav P0-3 final hardening (re-entry): if a grant IS already active,
    # this is a re-entry, not a first-time assume — the old context is about
    # to be silently replaced. Capture its id/target company from the
    # session and log its exit BEFORE revoking it, exactly as an explicit
    # /auth/end-assume-company call would, so the replaced grant is never
    # dropped from the audit trail. Read directly from the session rather
    # than teaching `_revoke_active_grant` to log — that helper is also
    # called by logout(), which must not gain this behavior (out of scope
    # here; logout's own revoke stays exactly as it was). Absent entirely on
    # a first-time assume (no prior break_glass_id in session), so that path
    # is unaffected — no EXITED event, matching today's behavior.
    prior_break_glass_id = flask_session.get("break_glass_id")
    prior_assumed_company_id = flask_session.get("assumed_company_id")
    if prior_break_glass_id:
        audit.log_cross_company(
            "auth", 0, evt.BREAK_GLASS_CONTEXT_EXITED,
            target_company_id=prior_assumed_company_id,
            detail=f"break_glass_id={prior_break_glass_id} reason=replaced_by_re_entry",
        )
    _revoke_active_grant(access_token)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=duration_minutes)
    inserted = client.table("break_glass_access").insert({
        "super_admin_user_id": g.tenant.user_id,
        "company_id": company_id,
        "reason": reason,
        "granted_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }).execute()
    grant_row = (inserted.data or [None])[0]
    if not grant_row:
        return jsonify({"error": "Could not create Assume Company Context grant"}), 500

    flask_session["assumed_company_id"] = company_id
    flask_session["break_glass_id"] = grant_row["id"]

    # Yuktav P0-3: log the grant itself as an audit-trail event, distinct
    # from break_glass_access's own row (which records the grant but isn't
    # surfaced through the same audit-trail read path as everything else).
    # `log_cross_company` records g.tenant (the super_admin) as the actor —
    # never the target company's own users — filed under the TARGET
    # company_id, not the super_admin's own (always None outside a grant).
    audit.log_cross_company(
        "auth", 0, evt.BREAK_GLASS_CONTEXT_ENTERED,
        target_company_id=company_id, reason=reason,
        detail=f"break_glass_id={grant_row['id']} company={company_row.get('legal_name')} "
               f"duration_minutes={duration_minutes}",
    )

    return jsonify({
        "assumed_company_id": company_id,
        "assumed_company_name": company_row.get("legal_name"),
        "break_glass_id": grant_row["id"],
        "expires_at": grant_row["expires_at"],
    }), 201


@bp.route("/auth/end-assume-company", methods=["POST"])
@require_role("super_admin")
@handle_postgrest_errors
def end_assume_company():
    """Revoke the caller's active Assume Company Context grant, if any."""
    # Yuktav P0-3: capture the grant/company identifiers BEFORE
    # _revoke_active_grant() pops them from the Flask session below — there
    # is nothing left to log afterward. Only log an exit event when a grant
    # was actually active (matches _revoke_active_grant's own no-op-if-absent
    # behavior); calling /auth/end-assume-company with nothing to end is not
    # itself a break-glass event.
    break_glass_id = flask_session.get("break_glass_id")
    assumed_company_id = flask_session.get("assumed_company_id")
    _revoke_active_grant(extract_bearer_token())
    if break_glass_id:
        audit.log_cross_company(
            "auth", 0, evt.BREAK_GLASS_CONTEXT_EXITED,
            target_company_id=assumed_company_id,
            detail=f"break_glass_id={break_glass_id}",
        )
    return jsonify({"success": True})

"""
pharmagpt/services/security_config.py — startup-secret status checks powering
the Security Configuration Status page (pharmagpt/routes/security_admin.py).

Remediates the Compliance Validation Report's Critical finding "Hardcoded
Flask session-signing secret fallback" (docs/CODE_REVIEW.md §1.2,
SECURITY_REVIEW.md "Hardcoded Secrets / Credentials"): FLASK_SECRET_KEY no
longer has an insecure default (see pharmagpt/config.py). This module is the
read-only status surface an administrator uses to confirm every
security-critical secret is actually configured — it never returns a
secret's value, only a status and a plain-English message.

Status vocabulary matches pharmagpt/services/backup_service.py's existing
get_configuration_status() convention: "configured" | "missing" | "failed"
("failed" = present but structurally invalid — rendered as Invalid by the
dashboard).
"""

import os

from pharmagpt import config
from pharmagpt.services.backup_service import get_configuration_status as _backup_configuration_status


def _check_flask_secret_key() -> dict[str, str]:
    if config.FLASK_SECRET_KEY_SOURCE == "env":
        return {"status": "configured", "message": "Session-signing secret is set from the environment."}
    # If the app is running at all, FLASK_DEBUG must be true here — a
    # missing key in production raises SecurityConfigError at startup
    # (pharmagpt/config.py) before this code can ever run.
    return {
        "status": "missing",
        "message": "FLASK_SECRET_KEY is not set — a temporary development-only secret was generated in "
                    "memory for this process (FLASK_DEBUG=true). It is not persisted and is NOT suitable "
                    "for production. Set FLASK_SECRET_KEY before deploying.",
    }


def _check_jwt_secret() -> dict[str, str]:
    return {
        "status": "configured",
        "message": "Not applicable to this application. Token verification is delegated entirely to "
                    "Supabase Auth (auth.get_user) rather than performed locally against a JWT signing "
                    "secret — PharmaGPT never holds a JWT-signing credential of its own "
                    "(pharmagpt/auth/context.py).",
    }


def _check_backup_encryption_key() -> dict[str, str]:
    return _backup_configuration_status()["encryption_key"]


def _check_env_secret(name: str, failure_message: str) -> dict[str, str]:
    if not os.getenv(name):
        return {"status": "missing", "message": failure_message}
    return {"status": "configured", "message": f"{name} is set."}


def get_security_configuration_status() -> dict[str, dict[str, str]]:
    """One check per security-critical secret this application reads.
    Never returns a secret's actual value — status + a plain-English
    message only."""
    return {
        "flask_secret_key": _check_flask_secret_key(),
        "jwt_secret": _check_jwt_secret(),
        "backup_encryption_key": _check_backup_encryption_key(),
        "supabase_url": _check_env_secret(
            "SUPABASE_URL", "SUPABASE_URL is not set — authentication and all Supabase-backed features will fail."
        ),
        "supabase_anon_key": _check_env_secret(
            "SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY is not set — authentication and all Supabase-backed features will fail."
        ),
        "supabase_service_role_key": _check_env_secret(
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_SERVICE_ROLE_KEY is not set — creating companies or inviting users will fail.",
        ),
    }


def get_session_hardening_status() -> dict[str, dict]:
    """Static report of the session-cookie / CSRF hardening actually applied
    in pharmagpt/app.py — informational only, nothing here is a secret.
    These flags are hardcoded in app.py (not independently configurable via
    env), so this reads pharmagpt.config directly rather than the live Flask
    app object, avoiding any import-order dependency on app.py."""
    secure_enabled = not config.FLASK_DEBUG
    return {
        "httponly": {
            "enabled": True,
            "message": "Session cookie is HttpOnly (SESSION_COOKIE_HTTPONLY=True in app.py) — not "
                       "readable by page JavaScript.",
        },
        "samesite": {
            "enabled": True,
            "message": "Session cookie SameSite=Lax (app.py) — not sent on cross-site POST/PUT/DELETE "
                       "requests, only same-site or top-level GET navigations.",
        },
        "secure": {
            "enabled": secure_enabled,
            "message": (
                "Session cookie Secure flag is ON — only sent over HTTPS (SESSION_COOKIE_SECURE = not "
                "FLASK_DEBUG, app.py)."
                if secure_enabled else
                "Session cookie Secure flag is OFF because FLASK_DEBUG=true (local HTTP-only dev). It "
                "turns on automatically whenever FLASK_DEBUG is false, which is the production default."
            ),
        },
        "csrf": {
            "enabled": True,
            "message": "No dedicated CSRF token is issued. State-changing requests are authorized by a "
                       "bearer token in the Authorization header (pharmagpt/auth/middleware.py), which a "
                       "cross-site page cannot attach — the classic CSRF vector does not apply to that "
                       "path. The session cookie is only used as a same-site (SameSite=Lax) fallback for "
                       "header-less GET navigations (e.g. the DOCX export download link), never for "
                       "state-changing requests.",
        },
        "session_timeout": {
            "enabled": False,
            "message": "No idle/absolute timeout is set on the Flask session cookie itself "
                       "(PERMANENT_SESSION_LIFETIME is unset, so it is a non-permanent, "
                       "browser-session-only cookie). The Supabase access token it mirrors has its own "
                       "short expiry, enforced server-side by Supabase on every request "
                       "(pharmagpt/auth/context.py).",
        },
        "session_rotation": {
            "enabled": True,
            "message": "The session cookie's signed value is the Supabase access token itself, freshly "
                       "issued by Supabase on every login (pharmagpt/routes/auth.py::login()) — a new "
                       "login always produces a new signed cookie value, never a reused one.",
        },
    }

"""
pharmagpt/routes/security_admin.py — Security Configuration Status dashboard.

Routes
------
GET  /admin/security                 dashboard page (super_admin only)
GET  /admin/security/api/config      per-secret configuration status, JSON
GET  /admin/security/api/hardening   session-cookie/CSRF hardening status, JSON

Remediates the Compliance Validation Report's Critical finding "Hardcoded
Flask session-signing secret fallback" (docs/CODE_REVIEW.md §1.2). Read-only:
this module never accepts a secret value as input and never returns one —
see pharmagpt/services/security_config.py for the underlying checks.

Platform-wide, not tenant-scoped, gated by the existing
@require_role("super_admin") decorator (pharmagpt/auth/decorators.py,
unmodified) — same pattern as pharmagpt/routes/backup_admin.py.

Error handling contract: every route returns a JSON body with a
"user_message" field safe to render directly in the UI — never a raw
exception string, stack trace, or file path.
"""

import logging

from flask import Blueprint, jsonify, render_template

from pharmagpt.auth.decorators import require_role
from pharmagpt.services import security_config

logger = logging.getLogger(__name__)

bp = Blueprint("security_admin", __name__, url_prefix="/admin/security")

GENERIC_ERROR_MESSAGE = "Something went wrong loading security configuration status. Please try again in a moment."


def _safe(fn):
    try:
        return jsonify(fn()), 200
    except Exception:  # noqa: BLE001 — last-resort guard, see module docstring
        logger.exception("Unexpected error in security_admin route")
        return jsonify({"user_message": GENERIC_ERROR_MESSAGE}), 500


@bp.route("", methods=["GET"])
@require_role("super_admin")
def dashboard_page():
    return render_template("security_dashboard.html")


@bp.route("/api/config", methods=["GET"])
@require_role("super_admin")
def api_config():
    return _safe(lambda: {"configuration": security_config.get_security_configuration_status()})


@bp.route("/api/hardening", methods=["GET"])
@require_role("super_admin")
def api_hardening():
    return _safe(lambda: {"hardening": security_config.get_session_hardening_status()})

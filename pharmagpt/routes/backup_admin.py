"""
pharmagpt/routes/backup_admin.py — Backup & Recovery status dashboard.

Routes
------
GET  /admin/backup                     dashboard page (super_admin only)
GET  /admin/backup/api/status          dashboard summary (latest/failed run,
                                        freshness, last verification, next
                                        scheduled run, health), JSON
GET  /admin/backup/api/config          configuration-detection status for
                                        the 6 tracked components, JSON
GET  /admin/backup/api/history         last N backup runs, JSON
GET  /admin/backup/api/verification-history   last N verification drills, JSON
POST /admin/backup/api/run             trigger an on-demand backup (background)
POST /admin/backup/api/verify          trigger a restore-drill verification (synchronous)
POST /admin/backup/api/restore         trigger a safe restore drill into a
                                        throwaway staging directory (synchronous)
                                        — never DB_PATH/UPLOAD_FOLDER; a real
                                        live-data restore stays CLI-only
                                        (scripts/restore_from_backup.py)

Platform-wide, not tenant-scoped — a backup covers every company's data, so
this is gated by the existing @require_role("super_admin") decorator
(pharmagpt/auth/decorators.py, unmodified) rather than any tenant/company
check. No RBAC rule, audit-trail write path, or e-signature logic is read or
modified anywhere in this file — it only calls pharmagpt.services.backup_service.

Error handling contract: every route here returns a JSON body with a
"user_message" field safe to render directly in the UI — never a raw
exception string, stack trace, or bare HTTP-status text. backup_service's
public functions (verify_backup, run_restore_drill, get_dashboard_status,
get_configuration_status) are themselves hardened to never raise, but every
route still wraps its body in a broad try/except as a second line of
defense — an uncaught exception here would otherwise fall through to
app.py's generic 500 handler, which is exactly the kind of unhelpful
message ("Internal server error") this module exists to keep out of a
compliance-facing admin surface.
"""

from flask import Blueprint, jsonify, render_template, request

from pharmagpt.auth.decorators import require_role
from pharmagpt.services import backup_service
from pharmagpt.services.job_runner import job_runner
import logging

logger = logging.getLogger(__name__)

bp = Blueprint("backup_admin", __name__, url_prefix="/admin/backup")

GENERIC_ERROR_MESSAGE = "Something went wrong loading backup information. Please try again in a moment."


def _safe(fn, *, on_error_message: str = GENERIC_ERROR_MESSAGE):
    """Run fn(), translating any unexpected exception into a friendly JSON
    500 instead of letting it reach app.py's generic error handler. Used
    only around calls into backup_service — every function reached this way
    is expected to already be defensive, so hitting this path at all
    indicates a genuine bug worth the full traceback in the server log."""
    try:
        return fn(), 200
    except Exception:  # noqa: BLE001 — last-resort guard, see module docstring
        logger.exception("Unexpected error in backup_admin route")
        return jsonify({"user_message": on_error_message}), 500


@bp.route("", methods=["GET"])
@require_role("super_admin")
def dashboard_page():
    return render_template("backup_dashboard.html")


@bp.route("/api/status", methods=["GET"])
@require_role("super_admin")
def api_status():
    return _safe(lambda: jsonify(backup_service.get_dashboard_status()))


@bp.route("/api/config", methods=["GET"])
@require_role("super_admin")
def api_config():
    return _safe(lambda: jsonify({"configuration": backup_service.get_configuration_status()}))


@bp.route("/api/history", methods=["GET"])
@require_role("super_admin")
def api_history():
    raw_limit = request.args.get("limit", "20")
    try:
        limit = max(1, min(int(raw_limit), 200))
    except (TypeError, ValueError):
        limit = 20  # a malformed ?limit= must never 500 — fall back quietly
    return _safe(lambda: jsonify({"runs": backup_service.get_history(limit)}))


@bp.route("/api/verification-history", methods=["GET"])
@require_role("super_admin")
def api_verification_history():
    raw_limit = request.args.get("limit", "20")
    try:
        limit = max(1, min(int(raw_limit), 200))
    except (TypeError, ValueError):
        limit = 20
    return _safe(lambda: jsonify({"verifications": backup_service.get_verification_history(limit)}))


@bp.route("/api/run", methods=["POST"])
@require_role("super_admin")
def api_run():
    try:
        runnable, reason = backup_service.is_backup_runnable()
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error checking backup configuration")
        return jsonify({"user_message": GENERIC_ERROR_MESSAGE}), 500

    if not runnable:
        # A 409 (not 400/500): the request itself is well-formed, the
        # *system* just isn't ready — this is the "never allow an action
        # guaranteed to fail" gate, checked server-side as well as
        # client-side (the dashboard also disables the button, but the API
        # must not trust that alone).
        return jsonify({"success": False, "user_message": reason}), 409

    try:
        job_runner.submit(backup_service.run_full_backup)
    except Exception:  # noqa: BLE001 — e.g. a shut-down executor; still must not 500 raw
        logger.exception("Failed to submit backup job")
        return jsonify({"success": False, "user_message": "Could not start the backup. Please try again."}), 500

    return jsonify({
        "success": True,
        "user_message": "Backup started. This page will update automatically as it progresses.",
    }), 202


@bp.route("/api/verify", methods=["POST"])
@require_role("super_admin")
def api_verify():
    try:
        available, reason = backup_service.is_archive_available_for_verification_or_restore()
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error checking backup availability")
        return jsonify({"user_message": GENERIC_ERROR_MESSAGE}), 500

    if not available:
        return jsonify({"success": False, "overall": "unavailable", "user_message": reason}), 409

    # verify_backup() is hardened to never raise (see backup_service.py
    # docstring) — this try/except is only a last-resort safety net.
    try:
        report = backup_service.verify_backup()
    except Exception:  # noqa: BLE001
        logger.exception("Verification drill raised unexpectedly at the route layer")
        return jsonify({
            "success": False, "overall": "fail",
            "user_message": "The verification drill could not complete. Please try again or contact support.",
        }), 500

    passed = report.get("overall") == "pass"
    user_message = (
        "Verification passed — the most recent backup was decrypted and checked successfully."
        if passed else
        "Verification did not pass — the backup could not be fully confirmed. Contact your platform administrator."
    )
    return jsonify({"success": passed, "user_message": user_message, **report}), (200 if passed else 502)


@bp.route("/api/restore", methods=["POST"])
@require_role("super_admin")
def api_restore():
    try:
        available, reason = backup_service.is_archive_available_for_verification_or_restore()
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error checking backup availability")
        return jsonify({"user_message": GENERIC_ERROR_MESSAGE}), 500

    if not available:
        return jsonify({"success": False, "user_message": reason}), 409

    # run_restore_drill() is hardened to never raise — last-resort net only.
    try:
        result = backup_service.run_restore_drill()
    except Exception:  # noqa: BLE001
        logger.exception("Restore drill raised unexpectedly at the route layer")
        return jsonify({
            "success": False,
            "user_message": "The restore drill could not complete. Please try again or contact support.",
        }), 500

    if result.get("success"):
        user_message = "Restore drill succeeded — the backup was fully restored into an isolated test location."
        return jsonify({"user_message": user_message, **result}), 200

    return jsonify({
        "user_message": "The restore drill did not complete successfully. Contact your platform administrator.",
        **result,
    }), 502

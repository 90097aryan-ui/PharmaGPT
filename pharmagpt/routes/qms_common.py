"""
routes/qms_common.py — Shared Quality Management Suite endpoints.

These endpoints are used by all three Phase 1 QMS modules (Document Control,
Deviation Management, CAPA) and will keep serving future Phase 2/3 modules
without any new tables or routes — only a new `record_type` string.

Routes
------
GET    /qms/dashboard                                   unified stats across all QMS modules
GET    /qms/meta                                         enums for dropdowns (doc types, statuses, ...)

GET    /qms/<record_type>/<id>/attachments               list attachments
POST   /qms/<record_type>/<id>/attachments               upload a file attachment
GET    /qms/attachments/<attachment_id>/download          download an attachment
DELETE /qms/attachments/<attachment_id>                   delete an attachment

GET    /qms/<record_type>/<id>/comments                  list comments
POST   /qms/<record_type>/<id>/comments                  add a comment

GET    /qms/<record_type>/<id>/audit-trail                list audit trail entries

GET    /qms/<record_type>/<id>/approval                   list approval/e-signature trail

Note: POSTing a new approval/e-signature entry is handled by each module's own
Blueprint (routes/qms_documents.py, qms_deviations.py, qms_capa.py) because
each module maps its approval "action" to a different status-transition —
see e.g. qms_documents.py::submit_approval(). That keeps status-transition
semantics local to the module that owns the status vocabulary, while the
underlying qms_approvals table (and this read endpoint) stays shared.
"""

import os
from werkzeug.utils import secure_filename
from flask import Blueprint, jsonify, request, send_file

from pharmagpt import qms_database as qmsdb
from pharmagpt import qms_document_database as qdocdb
from pharmagpt import qms_deviation_database as qdevdb
from pharmagpt import qms_capa_database as qcapadb
from pharmagpt import qms_change_control_database as qccdb
from pharmagpt.config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS
from pharmagpt.documents import get_extension, get_mime_type

bp = Blueprint("qms_common", __name__, url_prefix="/qms")

VALID_RECORD_TYPES = {"document", "deviation", "capa", "change_control"}

_GETTERS = {
    "document": qdocdb.get_document,
    "deviation": qdevdb.get_deviation,
    "capa": qcapadb.get_capa,
    "change_control": qccdb.get_change_control,
}


def _record_exists(record_type: str, record_id: int) -> bool:
    getter = _GETTERS.get(record_type)
    return bool(getter and getter(record_id))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route("/dashboard")
def dashboard():
    """Unified stats across Document Control, Deviations, CAPA, and Change Control."""
    doc_stats = qdocdb.get_dashboard_stats()
    dev_stats = qdevdb.get_dashboard_stats()
    capa_stats = qcapadb.get_dashboard_stats()
    cc_stats = qccdb.get_dashboard_stats()
    return jsonify({
        "documents": doc_stats,
        "deviations": dev_stats,
        "capa": capa_stats,
        "change_control": cc_stats,
        "summary": {
            "total_documents": doc_stats["total"],
            "total_deviations": dev_stats["total"],
            "open_deviations": dev_stats["open"],
            "total_capas": capa_stats["total"],
            "open_capas": capa_stats["open"],
            "overdue_capas": capa_stats["overdue"],
            "docs_due_for_review": len(doc_stats.get("due_for_review", [])),
            "total_changes": cc_stats["total"],
            "open_changes": cc_stats["open"],
            "pending_change_approvals": cc_stats["pending_approvals"],
            "emergency_changes": cc_stats["emergency_open"],
        },
    })


# ── Meta / enums ──────────────────────────────────────────────────────────────

@bp.route("/meta")
def meta():
    """Single source of truth for QMS enum lists — fetched once by qms_common.js
    and shared across all module frontends, avoiding backend/JS duplication."""
    return jsonify(qmsdb.QMS_META)


# ── Attachments ───────────────────────────────────────────────────────────────

def _qms_upload_dir(record_type: str, record_id: int) -> str:
    path = os.path.join(UPLOAD_FOLDER, "qms", record_type, str(record_id))
    os.makedirs(path, exist_ok=True)
    return path


def _resolve_collision(upload_dir: str, safe_name: str) -> str:
    if not os.path.exists(os.path.join(upload_dir, safe_name)):
        return safe_name
    base, ext = os.path.splitext(safe_name)
    counter = 1
    while os.path.exists(os.path.join(upload_dir, f"{base}_{counter}{ext}")):
        counter += 1
    return f"{base}_{counter}{ext}"


@bp.route("/<record_type>/<int:record_id>/attachments", methods=["GET"])
def get_attachments(record_type, record_id):
    if record_type not in VALID_RECORD_TYPES:
        return jsonify({"error": "Invalid record type"}), 400
    if not _record_exists(record_type, record_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(qmsdb.get_attachments(record_type, record_id))


@bp.route("/<record_type>/<int:record_id>/attachments", methods=["POST"])
def upload_attachment(record_type, record_id):
    if record_type not in VALID_RECORD_TYPES:
        return jsonify({"error": "Invalid record type"}), 400
    if not _record_exists(record_type, record_id):
        return jsonify({"error": "Not found"}), 404
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    extension = get_extension(file.filename)
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "File type not allowed. Accepted: PDF, DOCX, XLSX, TXT"}), 400

    upload_dir = _qms_upload_dir(record_type, record_id)
    safe_name = _resolve_collision(upload_dir, secure_filename(file.filename))
    file.save(os.path.join(upload_dir, safe_name))
    file_size = os.path.getsize(os.path.join(upload_dir, safe_name))

    attachment = qmsdb.add_attachment(
        record_type, record_id, safe_name, file.filename, extension, file_size,
        request.form.get("description", ""), request.form.get("uploaded_by", ""),
    )
    qmsdb.add_audit_entry(record_type, record_id, "Attachment uploaded",
                          request.form.get("uploaded_by", ""), file.filename)
    return jsonify(attachment), 201


@bp.route("/attachments/<int:attachment_id>/download", methods=["GET"])
def download_attachment(attachment_id):
    attachment = qmsdb.get_attachment(attachment_id)
    if not attachment:
        return jsonify({"error": "Not found"}), 404
    path = os.path.join(_qms_upload_dir(attachment["record_type"], attachment["record_id"]), attachment["filename"])
    if not os.path.exists(path):
        return jsonify({"error": "File missing on disk"}), 404
    return send_file(
        path,
        mimetype=get_mime_type(attachment.get("file_type", "")),
        as_attachment=True,
        download_name=attachment["original_name"],
    )


@bp.route("/attachments/<int:attachment_id>", methods=["DELETE"])
def delete_attachment(attachment_id):
    attachment = qmsdb.get_attachment(attachment_id)
    if not attachment:
        return jsonify({"error": "Not found"}), 404
    path = os.path.join(_qms_upload_dir(attachment["record_type"], attachment["record_id"]), attachment["filename"])
    if os.path.exists(path):
        os.remove(path)
    qmsdb.delete_attachment(attachment_id)
    return jsonify({"deleted": True})


# ── Comments ──────────────────────────────────────────────────────────────────

@bp.route("/<record_type>/<int:record_id>/comments", methods=["GET"])
def get_comments(record_type, record_id):
    if record_type not in VALID_RECORD_TYPES:
        return jsonify({"error": "Invalid record type"}), 400
    if not _record_exists(record_type, record_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(qmsdb.get_comments(record_type, record_id))


@bp.route("/<record_type>/<int:record_id>/comments", methods=["POST"])
def add_comment(record_type, record_id):
    if record_type not in VALID_RECORD_TYPES:
        return jsonify({"error": "Invalid record type"}), 400
    if not _record_exists(record_type, record_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    if not data.get("comment", "").strip():
        return jsonify({"error": "Comment text is required"}), 400
    comment = qmsdb.add_comment(record_type, record_id, data.get("author", ""),
                                data["comment"], data.get("role", ""))
    return jsonify(comment), 201


# ── Audit trail ───────────────────────────────────────────────────────────────

@bp.route("/<record_type>/<int:record_id>/audit-trail", methods=["GET"])
def get_audit_trail(record_type, record_id):
    if record_type not in VALID_RECORD_TYPES:
        return jsonify({"error": "Invalid record type"}), 400
    if not _record_exists(record_type, record_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(qmsdb.get_audit_trail(record_type, record_id))


# ── Approvals / e-signatures ──────────────────────────────────────────────────

@bp.route("/<record_type>/<int:record_id>/approval", methods=["GET"])
def get_approval(record_type, record_id):
    if record_type not in VALID_RECORD_TYPES:
        return jsonify({"error": "Invalid record type"}), 400
    if not _record_exists(record_type, record_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(qmsdb.get_approval_trail(record_type, record_id))

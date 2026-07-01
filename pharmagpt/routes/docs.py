"""
routes/docs.py — Project document upload, view, download, delete, and insights.

Routes
------
GET    /projects/<id>/documents      list documents for a project
POST   /projects/<id>/documents      upload a file (extraction runs in the background)
GET    /documents/<id>/status        poll extraction progress/result
POST   /documents/<id>/retry         re-run extraction after a failure
GET    /documents/<id>/view          view inline (PDF/TXT) or download
GET    /documents/<id>/download      force-download
DELETE /documents/<id>               delete file + metadata
GET    /projects/<id>/insights       aggregated document statistics
"""

from pharmagpt import database as db
from pharmagpt import documents as doc_utils
from pharmagpt.services.document_processor import process_document_async
from flask import Blueprint, jsonify, request, send_file

bp = Blueprint("documents", __name__)


@bp.route("/projects/<int:project_id>/documents", methods=["GET"])
def list_documents(project_id):
    """Return all document metadata rows for a project, newest first."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_documents(project_id))


@bp.route("/projects/<int:project_id>/documents", methods=["POST"])
def upload_document(project_id):
    """
    Accept a multipart/form-data file upload, store it inside the project,
    and kick off text extraction in the background. The HTTP response
    returns as soon as the file is saved to disk — never blocked on
    extraction, no matter how large the document is (see
    services/document_processor.py).

    Form field: file  (PDF, DOCX, XLSX, or TXT — max 50 MB)
    Returns the new document metadata dict (extraction_status: "pending").
    """
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    if not doc_utils.allowed_file(file.filename):
        return jsonify({"error": "File type not allowed. Accepted: PDF, DOCX, XLSX, TXT"}), 400

    stored_filename, file_size = doc_utils.safe_save(file, project_id)
    extension = doc_utils.get_extension(file.filename)

    doc = db.save_document(
        project_id=project_id,
        original_name=file.filename,
        stored_filename=stored_filename,
        file_type=extension,
        file_size=file_size,
    )

    db.create_pending_document_text(doc["id"], project_id)
    process_document_async(
        "project", doc["id"],
        doc_utils.get_file_path(project_id, stored_filename),
        extension,
        project_id=project_id,
    )
    doc["extraction_status"] = "pending"
    return jsonify(doc), 201


@bp.route("/documents/<int:doc_id>/status", methods=["GET"])
def document_extraction_status(doc_id):
    """Poll extraction progress/result for a project document."""
    if not db.get_document(doc_id):
        return jsonify({"error": "Document not found"}), 404

    status = db.get_document_text_status(doc_id)
    if not status:
        # Extremely unlikely — the row is created synchronously at upload —
        # but report "pending" rather than 404 so a poller never has to
        # special-case a brief race.
        status = {"document_id": doc_id, "extraction_status": "pending"}
    return jsonify(status)


@bp.route("/documents/<int:doc_id>/retry", methods=["POST"])
def retry_document_extraction(doc_id):
    """Re-run extraction for a document whose previous attempt failed (or
    partially failed). Never deletes the stored file — it is retried in place."""
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    if not doc_utils.file_exists(doc["project_id"], doc["stored_filename"]):
        return jsonify({"error": "File not found on disk — cannot retry"}), 404

    db.create_pending_document_text(doc_id, doc["project_id"])
    process_document_async(
        "project", doc_id,
        doc_utils.get_file_path(doc["project_id"], doc["stored_filename"]),
        doc["file_type"],
        project_id=doc["project_id"],
    )
    return jsonify({"status": "pending"}), 202


@bp.route("/documents/<int:doc_id>/view")
def view_document(doc_id):
    """
    Serve a document so the browser can display it inline (PDF, TXT).
    DOCX and XLSX — which browsers cannot render — fall back to a download.
    """
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    if not doc_utils.file_exists(doc["project_id"], doc["stored_filename"]):
        return jsonify({"error": "File not found on disk"}), 404

    file_path     = doc_utils.get_file_path(doc["project_id"], doc["stored_filename"])
    as_attachment = doc["file_type"] not in doc_utils.VIEWABLE_IN_BROWSER
    return send_file(
        file_path,
        mimetype=doc_utils.get_mime_type(doc["file_type"]),
        as_attachment=as_attachment,
        download_name=doc["original_name"],
    )


@bp.route("/documents/<int:doc_id>/download")
def download_document(doc_id):
    """Force-download a document regardless of file type."""
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    if not doc_utils.file_exists(doc["project_id"], doc["stored_filename"]):
        return jsonify({"error": "File not found on disk"}), 404

    file_path = doc_utils.get_file_path(doc["project_id"], doc["stored_filename"])
    return send_file(
        file_path,
        mimetype=doc_utils.get_mime_type(doc["file_type"]),
        as_attachment=True,
        download_name=doc["original_name"],
    )


@bp.route("/documents/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    """Delete a document's metadata from the DB and its file from disk.
    ON DELETE CASCADE in the schema removes the document_text row automatically."""
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    doc_utils.delete_from_disk(doc["project_id"], doc["stored_filename"])
    db.delete_document(doc_id)
    return jsonify({"status": "deleted"})


@bp.route("/projects/<int:project_id>/insights", methods=["GET"])
def project_insights(project_id):
    """
    Return aggregated document statistics for the Insights panel.

    Response: { document_count, total_pages, total_words,
                extracted_count, last_upload, file_types: {ext: N} }
    """
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_insights(project_id))

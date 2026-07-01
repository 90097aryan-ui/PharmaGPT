"""
routes/knowledge_base.py — Global Knowledge Base document management.

Routes
------
GET    /kb/documents                 list KB docs with optional filters
POST   /kb/documents                 upload a file with metadata (extraction runs in the background)
GET    /kb/documents/<id>            get single doc + text preview
GET    /kb/documents/<id>/status     poll extraction progress/result
POST   /kb/documents/<id>/retry      re-run extraction after a failure
GET    /kb/documents/<id>/view       view inline (PDF/TXT) or download
GET    /kb/documents/<id>/download   force-download
DELETE /kb/documents/<id>            delete doc + file
GET    /kb/folders/counts            per-folder document counts for sidebar badges
"""

from pharmagpt import database as db
from pharmagpt import documents as doc_utils
from pharmagpt.services.document_processor import process_document_async
from flask import Blueprint, jsonify, request, send_file

bp = Blueprint("knowledge_base", __name__)


@bp.route("/kb/documents", methods=["GET"])
def kb_list_documents():
    """
    List Knowledge Base documents with optional filters.

    Query params:
        folder    — exact folder name match
        tag       — substring match within comma-separated tags
        file_type — exact extension match (pdf, docx, xlsx, txt)
        keyword   — substring match in title and extracted text_content
        title     — substring match in title only
    """
    folder    = request.args.get("folder",    "").strip() or None
    tag       = request.args.get("tag",       "").strip() or None
    file_type = request.args.get("file_type", "").strip() or None
    keyword   = request.args.get("keyword",   "").strip() or None
    title     = request.args.get("title",     "").strip() or None

    return jsonify(db.get_kb_documents(
        folder=folder, tag=tag, file_type=file_type,
        keyword=keyword, title=title,
    ))


@bp.route("/kb/documents", methods=["POST"])
def kb_upload_document():
    """
    Upload a file to the Knowledge Base with metadata.

    Form fields:
        file           — binary (PDF, DOCX, XLSX, TXT; max 50 MB)
        title          — display title (defaults to the original filename)
        folder         — one of the 8 KB folders (defaults to 'Others')
        tags           — comma-separated tag strings
        doc_version    — version string (defaults to '1.0')
        effective_date — ISO date YYYY-MM-DD (optional)
        review_date    — ISO date YYYY-MM-DD (optional)
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    if not doc_utils.allowed_file(file.filename):
        return jsonify({"error": "File type not allowed. Accepted: PDF, DOCX, XLSX, TXT"}), 400

    folder = request.form.get("folder", "Others").strip()
    if folder not in db.KB_FOLDERS:
        folder = "Others"

    title          = request.form.get("title",          "").strip() or file.filename
    tags           = request.form.get("tags",           "").strip()
    doc_version    = request.form.get("doc_version",    "1.0").strip() or "1.0"
    effective_date = request.form.get("effective_date", "").strip() or None
    review_date    = request.form.get("review_date",    "").strip() or None

    stored_filename, file_size = doc_utils.safe_save_kb(file)
    extension = doc_utils.get_extension(file.filename)

    kb_doc = db.create_kb_document(
        title=title,
        folder=folder,
        tags=tags,
        doc_version=doc_version,
        effective_date=effective_date,
        review_date=review_date,
        original_name=file.filename,
        stored_filename=stored_filename,
        file_type=extension,
        file_size=file_size,
    )

    db.mark_kb_pending(kb_doc["id"])
    process_document_async("kb", kb_doc["id"], doc_utils.get_kb_file_path(stored_filename), extension)
    return jsonify(db.get_kb_document(kb_doc["id"])), 201


@bp.route("/kb/documents/<int:kb_id>/status", methods=["GET"])
def kb_extraction_status(kb_id):
    """Poll extraction progress/result for a Knowledge Base document."""
    status = db.get_kb_document_status(kb_id)
    if not status:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(status)


@bp.route("/kb/documents/<int:kb_id>/retry", methods=["POST"])
def kb_retry_extraction(kb_id):
    """Re-run extraction for a KB document whose previous attempt failed (or
    partially failed). Never deletes the stored file — it is retried in place."""
    doc = db.get_kb_document(kb_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    if not doc_utils.kb_file_exists(doc["stored_filename"]):
        return jsonify({"error": "File not found on disk — cannot retry"}), 404

    db.mark_kb_pending(kb_id)
    process_document_async(
        "kb", kb_id, doc_utils.get_kb_file_path(doc["stored_filename"]), doc["file_type"],
    )
    return jsonify({"status": "pending"}), 202


@bp.route("/kb/documents/<int:kb_id>", methods=["GET"])
def kb_get_document(kb_id):
    """Return a single KB document including its text_content for the preview panel."""
    doc = db.get_kb_document(kb_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(doc)


@bp.route("/kb/documents/<int:kb_id>/view")
def kb_view_document(kb_id):
    """Serve the KB file inline (PDF/TXT) or as a download (DOCX/XLSX)."""
    doc = db.get_kb_document(kb_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    if not doc_utils.kb_file_exists(doc["stored_filename"]):
        return jsonify({"error": "File not found on disk"}), 404

    file_path     = doc_utils.get_kb_file_path(doc["stored_filename"])
    as_attachment = doc["file_type"] not in doc_utils.VIEWABLE_IN_BROWSER
    return send_file(
        file_path,
        mimetype=doc_utils.get_mime_type(doc["file_type"]),
        as_attachment=as_attachment,
        download_name=doc["original_name"],
    )


@bp.route("/kb/documents/<int:kb_id>/download")
def kb_download_document(kb_id):
    """Force-download a KB file."""
    doc = db.get_kb_document(kb_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    if not doc_utils.kb_file_exists(doc["stored_filename"]):
        return jsonify({"error": "File not found on disk"}), 404

    file_path = doc_utils.get_kb_file_path(doc["stored_filename"])
    return send_file(
        file_path,
        mimetype=doc_utils.get_mime_type(doc["file_type"]),
        as_attachment=True,
        download_name=doc["original_name"],
    )


@bp.route("/kb/documents/<int:kb_id>", methods=["DELETE"])
def kb_delete_document(kb_id):
    """Delete a KB document from the database and remove its file from disk."""
    doc = db.get_kb_document(kb_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    doc_utils.delete_kb_from_disk(doc["stored_filename"])
    db.delete_kb_document(kb_id)
    return jsonify({"status": "deleted"})


@bp.route("/kb/folders/counts", methods=["GET"])
def kb_folder_counts():
    """Return document count per folder for the KB sidebar badges."""
    return jsonify(db.get_kb_folder_counts())

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

Yuktav Brain — Global Regulatory Knowledge (super_admin only; see
PROJECT_MEMORY/DECISIONS.md for the architecture this implements)
------------------------------------------------------------------
GET    /kb/global/documents                    list global docs, any lifecycle stage
POST   /kb/global/documents                    stage a new global document (not yet retrievable)
POST   /kb/global/documents/<id>/publish       publish a staged document (different super_admin required)
POST   /kb/global/documents/<id>/retire        retire an active document (excluded from retrieval, kept for audit)
"""

import logging

from flask import Blueprint, g, jsonify, request, send_file

from pharmagpt import audit
from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import documents as doc_utils
from pharmagpt import tenancy
from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.auth.workspace_access import require_workspace_access
from pharmagpt.db import kb_repo
from pharmagpt.services.document_processor import process_document_async

bp = Blueprint("knowledge_base", __name__)
logger = logging.getLogger(__name__)


@bp.before_request
def _require_workspace_access():
    return require_workspace_access("knowledge")


# ── Phase 3.3 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────
# Same policy as routes/projects.py: active only when KB_BACKEND=dual, never
# raises, SQLite stays the source of truth and the response the caller sees.

def _dual_write_create(kb_doc: dict) -> None:
    if config.KB_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return  # Super Admin has no company — nothing to dual-write against
    try:
        result = kb_repo.create_kb_document(
            extract_bearer_token(), tenant.company_id,
            title=kb_doc["title"], folder=kb_doc["folder"],
            tags_csv=kb_doc.get("tags") or "",
            stored_filename=kb_doc["stored_filename"],
            file_type=kb_doc["file_type"], file_size=kb_doc["file_size"],
            effective_date=kb_doc.get("effective_date"),
        )
        db.set_kb_document_postgres_id(kb_doc["id"], result["document_id"])
    except Exception:
        logger.exception("Phase 3.3 dual-write: failed to sync new KB document %s to Postgres", kb_doc["id"])


def _dual_write_delete(kb_doc: dict) -> None:
    if config.KB_BACKEND != "dual":
        return
    postgres_id = kb_doc.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        kb_repo.archive_document(extract_bearer_token(), tenant.company_id, postgres_id)
    except Exception:
        logger.exception("Phase 3.3 dual-write: failed to archive KB document %s in Postgres", kb_doc["id"])


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
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403

    folder    = request.args.get("folder",    "").strip() or None
    tag       = request.args.get("tag",       "").strip() or None
    file_type = request.args.get("file_type", "").strip() or None
    keyword   = request.args.get("keyword",   "").strip() or None
    title     = request.args.get("title",     "").strip() or None

    return jsonify(db.get_kb_documents(
        g.tenant.company_id,
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
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403

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
        company_id=g.tenant.company_id,
        created_by=g.tenant.display_name or g.tenant.email,
    )

    db.mark_kb_pending(kb_doc["id"])
    _dual_write_create(kb_doc)
    audit.log("kb_document", kb_doc["id"], "Uploaded", new={"title": title, "folder": folder, "original_name": file.filename})
    process_document_async("kb", kb_doc["id"], doc_utils.get_kb_file_path(stored_filename), extension)
    return jsonify(db.get_kb_document(kb_doc["id"])), 201


@bp.route("/kb/documents/<int:kb_id>/status", methods=["GET"])
def kb_extraction_status(kb_id):
    """Poll extraction progress/result for a Knowledge Base document."""
    if not tenancy.scoped_or_none(db.get_kb_document(kb_id), g.tenant.company_id):
        return jsonify({"error": "Document not found"}), 404
    status = db.get_kb_document_status(kb_id)
    if not status:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(status)


@bp.route("/kb/documents/<int:kb_id>/retry", methods=["POST"])
def kb_retry_extraction(kb_id):
    """Re-run extraction for a KB document whose previous attempt failed (or
    partially failed). Never deletes the stored file — it is retried in place."""
    doc = tenancy.scoped_or_none(db.get_kb_document(kb_id), g.tenant.company_id)
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
    doc = tenancy.scoped_or_none(db.get_kb_document(kb_id), g.tenant.company_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(doc)


@bp.route("/kb/documents/<int:kb_id>/view")
def kb_view_document(kb_id):
    """Serve the KB file inline (PDF/TXT) or as a download (DOCX/XLSX)."""
    doc = tenancy.scoped_or_none(db.get_kb_document(kb_id), g.tenant.company_id)
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
    doc = tenancy.scoped_or_none(db.get_kb_document(kb_id), g.tenant.company_id)
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
@require_role("company_admin")
def kb_delete_document(kb_id):
    """Delete a KB document from the database and remove its file from disk."""
    doc = tenancy.scoped_or_none(db.get_kb_document(kb_id), g.tenant.company_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    doc_utils.delete_kb_from_disk(doc["stored_filename"])
    db.delete_kb_document(kb_id)
    _dual_write_delete(doc)
    audit.log("kb_document", kb_id, "Deleted", old={"title": doc.get("title"), "original_name": doc.get("original_name")})
    return jsonify({"status": "deleted"})


@bp.route("/kb/folders/counts", methods=["GET"])
def kb_folder_counts():
    """Return document count per folder for the KB sidebar badges."""
    return jsonify(db.get_kb_folder_counts(g.tenant.company_id))


# ── Yuktav Brain: Global Regulatory Knowledge ────────────────────────────────
# Global knowledge is a kb_documents row with company_id='' (same sentinel
# qms_document_database.py already uses for platform-wide templates — see
# PROJECT_MEMORY/DECISIONS.md for the full architecture). Only super_admin
# — the one role with no company_id, i.e. the only role that can act for
# the platform rather than for one tenant — may reach any route below.
# `_require_workspace_access` above does not block super_admin
# (auth/workspace_access.py's ADMIN_ROLES bypass), so no additional gate is
# needed for that hook.
#
# Staging (author) and publishing (activate) must be two different
# super_admin identities — the same segregation-of-duty principle
# services/workflow_engine.py::reject_creator_as_approver already enforces
# for record approvers, applied here to the one action that makes content
# visible to every tenant's Brain at once. Global rows record the
# authenticated author's stable `user_id` in `created_by` (not the
# display-name convention the ordinary tenant upload route below uses) —
# it's the only reliable way to compare "is the publisher the same person
# who staged this."

_GLOBAL_CONTENT_CATEGORIES = {"regulatory_source", "yuktav_interpretation"}


@bp.route("/kb/global/documents", methods=["GET"])
@require_role("super_admin")
def kb_global_list_documents():
    """List every global document at any lifecycle stage (staged, active,
    superseded, retired) — super_admin administration view."""
    return jsonify(db.get_kb_documents(company_id=""))


@bp.route("/kb/global/documents", methods=["POST"])
@require_role("super_admin")
def kb_global_stage_document():
    """Stage a new global regulatory document. content_status='staged' —
    not retrievable by the Brain until a *different* super_admin publishes
    it via POST /kb/global/documents/<id>/publish."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    if not doc_utils.allowed_file(file.filename):
        return jsonify({"error": "File type not allowed. Accepted: PDF, DOCX, XLSX, TXT"}), 400

    content_category = request.form.get("content_category", "").strip()
    if content_category not in _GLOBAL_CONTENT_CATEGORIES:
        return jsonify({
            "error": f"content_category must be one of {sorted(_GLOBAL_CONTENT_CATEGORIES)}",
        }), 400

    folder = request.form.get("folder", "Regulations").strip()
    if folder not in db.KB_FOLDERS:
        folder = "Regulations"

    supersedes_raw = request.form.get("supersedes", "").strip()
    supersedes = None
    if supersedes_raw:
        try:
            supersedes = int(supersedes_raw)
        except ValueError:
            return jsonify({"error": "supersedes must be a document id"}), 400
        if not db.get_global_kb_document(supersedes):
            return jsonify({"error": "supersedes must reference an existing global document"}), 400

    title            = request.form.get("title",            "").strip() or file.filename
    tags             = request.form.get("tags",             "").strip()
    doc_version      = request.form.get("doc_version",      "1.0").strip() or "1.0"
    effective_date   = request.form.get("effective_date",   "").strip() or None
    review_date      = request.form.get("review_date",      "").strip() or None
    source_authority = request.form.get("source_authority", "").strip() or None
    source_reference = request.form.get("source_reference", "").strip() or None
    jurisdiction     = request.form.get("jurisdiction",     "").strip() or None
    publication_date = request.form.get("publication_date", "").strip() or None

    stored_filename, file_size = doc_utils.safe_save_kb(file)
    extension = doc_utils.get_extension(file.filename)

    kb_doc = db.create_kb_document(
        title=title, folder=folder, tags=tags, doc_version=doc_version,
        effective_date=effective_date, review_date=review_date,
        original_name=file.filename, stored_filename=stored_filename,
        file_type=extension, file_size=file_size,
        company_id="",
        created_by=g.tenant.user_id,
        content_category=content_category,
        source_authority=source_authority, source_reference=source_reference,
        jurisdiction=jurisdiction, publication_date=publication_date,
        content_status="staged", supersedes=supersedes,
    )

    db.mark_kb_pending(kb_doc["id"])
    audit.log("kb_document", kb_doc["id"], "Global knowledge staged",
              new={"title": title, "content_category": content_category})
    process_document_async("kb", kb_doc["id"], doc_utils.get_kb_file_path(stored_filename), extension)
    return jsonify(db.get_kb_document(kb_doc["id"])), 201


@bp.route("/kb/global/documents/<int:kb_id>/publish", methods=["POST"])
@require_role("super_admin")
def kb_global_publish_document(kb_id):
    """Publish a staged global document, making it retrievable by the Brain
    for every tenant. Requires a super_admin *other than* the one who
    staged it. Identity is always read from the authenticated session
    (g.tenant) — any published_by/approved_by/role/company_id in the
    request body is ignored, never trusted."""
    doc = db.get_global_kb_document(kb_id)
    if not doc:
        return jsonify({"error": "Global document not found"}), 404
    if doc["content_status"] != "staged":
        return jsonify({
            "error": f"Only staged documents can be published (current status: {doc['content_status']})",
        }), 409
    if doc.get("created_by") == g.tenant.user_id:
        return jsonify({
            "error": "The super_admin who staged this document cannot also publish it (segregation of duties)",
        }), 403

    published = db.publish_global_kb_document(kb_id, published_by=g.tenant.user_id)
    audit.log("kb_document", kb_id, "Global knowledge published", new={"published_by": g.tenant.user_id})
    return jsonify(published)


@bp.route("/kb/global/documents/<int:kb_id>/retire", methods=["POST"])
@require_role("super_admin")
def kb_global_retire_document(kb_id):
    """Retire an active global document — excluded from Brain retrieval,
    retained in the table for audit. Never a physical delete."""
    doc = db.get_global_kb_document(kb_id)
    if not doc:
        return jsonify({"error": "Global document not found"}), 404
    if doc["content_status"] != "active":
        return jsonify({
            "error": f"Only active documents can be retired (current status: {doc['content_status']})",
        }), 409

    retired = db.retire_global_kb_document(kb_id)
    audit.log("kb_document", kb_id, "Global knowledge retired")
    return jsonify(retired)

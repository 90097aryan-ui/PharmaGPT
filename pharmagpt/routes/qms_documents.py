"""
routes/qms_documents.py — Document Control module API endpoints.

All routes return JSON except the SSE draft-generation stream and the DOCX
export download. Attachments/comments/audit-trail/approval-trail reads are
served by routes/qms_common.py (record_type='document'); this file owns the
approval POST because it maps each action to a Document Control status
transition (Draft → Under Review → Pending Approval → Effective → Under
Revision → Obsolete).

Routes
------
GET    /qms/documents                        list documents (filterable, includes keyword search)
POST   /qms/documents                        create document (auto doc_number)
GET    /qms/documents/<id>                   get one document
PUT    /qms/documents/<id>                   update document fields (effective_date/review_date
                                              are system-controlled and silently ignored here —
                                              see _AUTHOR_READONLY_FIELDS)
DELETE /qms/documents/<id>                   delete document

POST   /qms/documents/<id>/generate          AI draft generation (SSE stream). Body may carry
                                              `equipment_id` (AI-Assisted SOP Creation, spec §4) to
                                              retrieve that equipment's linked Knowledge Base
                                              documents as generation context, instead of/in
                                              addition to a raw `knowledge_base` string.
POST   /qms/documents/<id>/review            AI regulatory compliance review

POST   /qms/documents/<id>/self-check        Author Self-Check hard gate
GET    /qms/documents/<id>/versions          version history (read-only timeline)
GET    /qms/documents/<id>/versions/current  the document's current version row
POST   /qms/documents/<id>/versions/upload   Upload Final Author Version (becomes the
                                              controlled content for the current Draft version)
POST   /qms/documents/<id>/versions/start-revision   fork a new Draft off an Effective version
POST   /qms/documents/<id>/versions          company_admin-only escape hatch — snapshot current
                                              content as a free-labelled version. NOT part of the
                                              normal author workflow (system controls all normal
                                              version numbering — see services/document_versioning.py)

GET    /qms/documents/<id>/distribution      distribution list
POST   /qms/documents/<id>/distribution      add distribution entry
POST   /qms/documents/distribution/<did>/acknowledge   acknowledge distribution

GET    /qms/documents/<id>/training          training list
GET    /qms/documents/<id>/training/gate     computed >=90% training-gate status
POST   /qms/documents/<id>/training          add training record
PUT    /qms/documents/training/<tid>         update training status

GET    /qms/documents/<id>/workflow          workflow instance/steps, enriched with approver-pool
                                              role labels + quorum summary on the final Approval step
POST   /qms/documents/<id>/workflow/start    Submit for Review (Author Self-Check + Final Author
                                              Version required first)
POST   /qms/documents/<id>/workflow/steps/<order>/decide   Review Accept/Reject, Approval vote
POST   /qms/documents/<id>/release           Quality Coordinator release to Effective — only legal
                                              once the version is 'approved' AND the training gate
                                              (>=90%) has cleared; author roles are not permitted

POST   /qms/documents/<id>/approval          status transition + e-signature entry (legacy)

GET    /qms/documents/<id>/report            markdown report (preview / print)
POST   /qms/documents/<id>/export/docx       DOCX export

GET    /qms/documents/templates/<tid>/download   blank Controlled Template as DOCX (SOP
                                              creation workflow, Option 1 "Create from
                                              Controlled Template") — no document required
"""

import io
import json
import logging
import re
from flask import Blueprint, g, jsonify, request, Response, stream_with_context, send_file

from pharmagpt import audit
from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_database as qmsdb
from pharmagpt import qms_workflow_database as wfdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import require_role
from pharmagpt.auth.workspace_access import require_workspace_access
from pharmagpt.services import esignature_service
from pharmagpt.services import kb_sync
from pharmagpt.services import lifecycle_engine
from pharmagpt.services import qms_document_service as svc
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.services.qms_shared import stream_gemini
from pharmagpt.prompts import qms_document_prompt as qp

logger = logging.getLogger(__name__)

bp = Blueprint("qms_documents", __name__, url_prefix="/qms/documents")
RECORD_TYPE = "document"
WORKFLOW_KEY = "DOCUMENT_WORKFLOW_V1"


@bp.before_request
def _require_workspace_access():
    # Document Control is a shared entry point (Quality Management's
    # "Document Control" item and the Document Generator workspace both
    # resolve here, see index.html) — either grant is sufficient.
    return require_workspace_access("quality", "documents")


# ── Documents ─────────────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_documents():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    filters = {
        "doc_type": request.args.get("type"),
        "status": request.args.get("status"),
        "department": request.args.get("department"),
        "category": request.args.get("category"),
        "keyword": request.args.get("q"),
    }
    return jsonify(qdb.get_all_documents(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_document():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "Document title is required"}), 400
    # Document Control Information (spec §2): "Prepared By" is always the
    # authenticated creator, mirroring routes/urs.py's identical
    # _current_display_name() pattern — never a client-supplied value.
    data["prepared_by"] = g.tenant.display_name or g.tenant.email
    document = qdb.create_document(data, company_id=g.tenant.company_id)
    audit.log("document", document["id"], "Document created", new=document)
    if document.get("template_id"):
        template = qdb.get_template(document["template_id"])
        audit.log("document", document["id"], "Controlled SOP Template selected",
                  detail=template.get("name", "") if template else str(document["template_id"]))
    return jsonify(document), 201


# ── Templates (Document Control redesign, Phase 5) ───────────────────────────
# Index + headings + sub-headings only — no procedure content. AI Assist
# fills content within this structure (constraining the AI prompt itself
# to preserve controlled headings is a separate, deferred follow-up — see
# services/qms_document_prompt.py; this is the data model + CRUD half).

@bp.route("/templates", methods=["GET"])
def list_templates_route():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    return jsonify(qdb.list_templates(request.args.get("doc_type", ""), g.tenant.company_id))


@bp.route("/templates", methods=["POST"])
@require_role("company_admin")
def create_template_route():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    structure = data.get("structure")
    if not name:
        return jsonify({"error": "Template name is required"}), 400
    if not isinstance(structure, list) or not structure:
        return jsonify({"error": "structure must be a non-empty list of {heading, sub_headings}"}), 400
    template = qdb.create_template(
        data.get("doc_type", "SOP"), name, structure,
        company_id=g.tenant.company_id, created_by=g.tenant.display_name or g.tenant.email,
    )
    audit.log("document_template", template["id"], "Template created", detail=name)
    return jsonify(template), 201


@bp.route("/templates/<int:tid>", methods=["GET"])
def get_template_route(tid):
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    template = qdb.get_template(tid)
    if not template or (template["company_id"] not in ("", g.tenant.company_id)):
        return jsonify({"error": "Not found"}), 404
    return jsonify(template)


@bp.route("/templates/<int:tid>/download", methods=["GET"])
def download_template_docx(tid):
    """Manual SOP path (spec §2/§9, Option 1 "Create from Controlled
    Template"): the blank controlled template as a real DOCX — headings/
    sub-headings only, no procedure content — for the author to prepare
    offline in Word. Reuses the same DOCX pipeline as document export
    (doc_exporter.markdown_to_docx / services/docx_generator.py) so the file
    is a genuine .docx package, never a renamed .md."""
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    template = qdb.get_template(tid)
    if not template or (template["company_id"] not in ("", g.tenant.company_id)):
        return jsonify({"error": "Not found"}), 404
    from pharmagpt.services.doc_exporter import markdown_to_docx
    md = svc.render_template_skeleton_markdown(template)
    docx_bytes = markdown_to_docx(md, template.get("doc_type", "SOP"), {"title": template.get("name", "")})
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", template.get("name", "Controlled_Template"))[:60]
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"{safe_name}.docx",
    )


# ── Approver pool (Document Control redesign, Phase 3) ───────────────────────
# Department Head + Quality Head/Designee mandatory, Plant Head optional.
# Company-admin only — this configures who the final Approval stage's
# quorum votes are auto-assigned to for the whole company (or one
# department, overriding the company-wide default for just that
# department). Not tied to a specific document id.

@bp.route("/approver-pool", methods=["GET"])
def get_approver_pool_route():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    department = request.args.get("department", "")
    return jsonify(qdb.get_approver_pool(g.tenant.company_id, department))


@bp.route("/approver-pool", methods=["POST"])
@require_role("company_admin")
def set_approver_pool_route():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    pool_role = data.get("pool_role", "")
    if pool_role not in qdb.ALL_POOL_ROLES:
        return jsonify({"error": f"pool_role must be one of {', '.join(qdb.ALL_POOL_ROLES)}"}), 400
    if not data.get("user_id"):
        return jsonify({"error": "user_id is required"}), 400
    entry = qdb.set_approver_pool_member(
        g.tenant.company_id, data.get("department", ""), pool_role,
        data["user_id"], data.get("display_name", ""),
    )
    audit.log("document_approver_pool", 0, f"Approver pool set: {pool_role}", detail=entry.get("display_name", ""))
    return jsonify(entry), 201


@bp.route("/<int:did>", methods=["GET"])
def get_document(did):
    d = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not d:
        return jsonify({"error": "Not found"}), 404
    return jsonify(d)


# Document Control redesign (spec §2/§8/§9/§22): the whole Document Control
# Information header is system-controlled, not author-editable. Review Date/
# Reviewed By are auto-stamped when the Review step is accepted
# (workflow_engine.py's _document_version_on_step_approved), Approved By when
# the final Approval step is decided, and Effective Date only by the Quality
# Coordinator's explicit release (see release_document() below). Prepared By
# is stamped once at create_document() and never changes afterward. Silently
# dropped here rather than 400ing — the author-facing Overview form no longer
# renders these as inputs, but this keeps the API defensive against a stale
# client build.
_AUTHOR_READONLY_FIELDS = ("effective_date", "review_date", "prepared_by", "reviewed_by", "approved_by")


@bp.route("/<int:did>", methods=["PUT"])
def update_document(did):
    existing = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    # Phase F (WP3, workflow enforcement): Obsolete is the terminal state in
    # QMS_DOCUMENT's lifecycle (services/lifecycle_engine.py) — a record must
    # be immutable once it reaches it, or Obsolete carries no real guarantee.
    if existing["status"] == "Obsolete":
        audit.log_failure("document", did, "Update blocked (record is Obsolete)",
                           reason="Obsolete documents are immutable")
        return jsonify({"error": "This document is Obsolete and cannot be edited"}), 409
    data = request.get_json() or {}
    for f in _AUTHOR_READONLY_FIELDS:
        data.pop(f, None)
    # Configurable quorum approval: a positive integer requires that many
    # distinct Approver votes on this document's next review/approval steps
    # (services/workflow_engine.py::start_instance's default_quorum); null
    # reverts to the existing single-decider 'any' behaviour. Snapshotted
    # onto the workflow instance only when the *next* review is started, so
    # changing this never retroactively alters a review already in progress.
    if "approval_quorum" in data:
        aq = data.get("approval_quorum")
        if aq is not None and (not isinstance(aq, int) or isinstance(aq, bool) or aq < 1):
            return jsonify({"error": "approval_quorum must be a positive integer or null"}), 400
    updated = qdb.update_document(did, data)
    audit.log("document", did, "Updated", old=existing, new=updated)
    return jsonify(updated)


@bp.route("/<int:did>", methods=["DELETE"])
@require_role("company_admin")
def delete_document(did):
    existing = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    qdb.delete_document(did)
    audit.log("document", did, "Deleted", old=existing)
    return jsonify({"deleted": True})


# ── AI Draft Generation (SSE streaming) ───────────────────────────────────────

@bp.route("/<int:did>/generate", methods=["POST"])
def generate_draft(did):
    """Stream AI-generated document content as SSE events, then persist it."""
    body = request.get_json() or {}
    document = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not document:
        return jsonify({"error": "Not found"}), 404

    info = {**document, **body}
    template = qdb.get_template(document["template_id"]) if document.get("template_id") else None
    # AI-Assisted SOP Creation (spec §4): equipment_id resolves to that
    # equipment's linked Knowledge Base documents (manuals, vendor docs,
    # existing controlled references) — retrieved server-side so the
    # frontend never has to assemble or transmit KB content itself. Falls
    # back to a raw `knowledge_base` string for backward compatibility with
    # any existing caller that doesn't pass equipment_id.
    knowledge_base = body.get("knowledge_base", "")
    equipment_id = body.get("equipment_id")
    if equipment_id:
        knowledge_base = svc.build_equipment_knowledge_base_context(int(equipment_id), g.tenant.company_id)
    prompt = qp.build_draft_prompt(info, knowledge_base, template=template)

    def stream():
        full = ""
        try:
            for chunk in stream_gemini(prompt, temperature=0.3):
                full += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            qdb.update_document(did, {"content": full})
            audit.log("document", did, "AI draft generated", new={"content_length": len(full)})
            # Controlled-template structure enforcement (Document Control
            # redesign, fix): a prompt instruction alone cannot *guarantee*
            # the AI preserved every controlled heading — this is the
            # actual, deterministic check. Content is still saved either
            # way (discarding the AI's work entirely would leave the author
            # with nothing to fix), but a violation is logged to the audit
            # trail and surfaced in the SSE 'done' event so the caller can
            # warn the author — who must still pass the existing Author
            # Self-Check hard gate before this document can ever reach
            # Submit for Review, which is the actual enforcement backstop.
            structure_check = None
            if template and template.get("structure"):
                structure_check = qp.validate_template_structure(full, template["structure"])
                if not structure_check["valid"]:
                    audit.log_failure(
                        "document", did, "AI draft generation violated controlled template structure",
                        reason=f"missing={structure_check['missing_headings']} "
                               f"out_of_order={structure_check['out_of_order']}",
                    )
            yield f"data: {json.dumps({'done': True, 'structure_check': structure_check})}\n\n"
        except Exception as e:
            audit.log_failure("document", did, "AI draft generation failed", reason=str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── AI Regulatory Compliance Review ───────────────────────────────────────────

@bp.route("/<int:did>/review", methods=["POST"])
def review_document(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    review = svc.ai_review_document(did)
    return jsonify(review)


# ── Author Self-Check (Document Control redesign, Phase 5, hard gate) ───────

@bp.route("/<int:did>/self-check", methods=["POST"])
def record_self_check(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    try:
        version = qdb.record_self_check(did, tenancy.signing_identity(g.tenant)["performed_by"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    audit.log("document", did, "Author Self-Check completed", detail=f"version {version['version_number']}")
    return jsonify(version)


# ── Version history ────────────────────────────────────────────────────────────

@bp.route("/<int:did>/versions", methods=["GET"])
def get_versions(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(qdb.get_versions(did))


@bp.route("/<int:did>/versions/current", methods=["GET"])
def get_current_version_route(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    version = qdb.get_current_version(did)
    if not version:
        return jsonify({"error": "This document has no current version"}), 404
    return jsonify(version)


@bp.route("/<int:did>/versions/upload", methods=["POST"])
def upload_final_author_version(did):
    """Author Local Edit / Upload Final Author Version (Document Control
    redesign, Phase 5): the uploaded file becomes the authoritative content
    for the CURRENT Draft version — not a parallel/competing source of
    truth alongside qms_documents.content. Reuses the exact same
    attachment-storage pipeline routes/qms_common.py's generic upload
    already uses (qmsdb.add_attachment, same upload dir/collision
    handling) and the same synchronous text-extraction service KB document
    ingestion uses (services/document_processor.extract_sync) — no new
    storage or extraction mechanism. The extracted text is written through
    qdb.update_document(..., content=...), which (as of this redesign)
    already syncs into the version's content_snapshot for a Draft version,
    so this is the same single write path "Save Content"/AI-draft
    generation already use, just sourced from an uploaded file instead of
    typed/generated text."""
    import os
    from werkzeug.utils import secure_filename
    from pharmagpt.config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS
    from pharmagpt.documents import get_extension
    from pharmagpt.routes.qms_common import _qms_upload_dir, _resolve_collision
    from pharmagpt.services.document_processor import extract_sync

    document = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not document:
        return jsonify({"error": "Not found"}), 404
    version = qdb.get_current_version(did)
    if not version or version["status"] != "draft":
        return jsonify({
            "error": "The Final Author Version can only be uploaded while the current version is Draft",
        }), 409
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    extension = get_extension(file.filename)
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "File type not allowed"}), 400

    upload_dir = _qms_upload_dir(RECORD_TYPE, did)
    safe_name = _resolve_collision(upload_dir, secure_filename(file.filename))
    file_path = os.path.join(upload_dir, safe_name)
    file.save(file_path)
    file_size = os.path.getsize(file_path)

    uploader = g.tenant.display_name or g.tenant.email
    attachment = qmsdb.add_attachment(
        RECORD_TYPE, did, safe_name, file.filename, extension, file_size,
        "Final Author Version", uploader,
    )

    result = extract_sync(file_path, extension)
    if result.status == "failed" or not result.text.strip():
        audit.log_failure("document", did, "Final Author Version upload rejected",
                           reason=f"extraction status: {result.status}")
        return jsonify({"error": f"Could not extract usable text from the uploaded file "
                                  f"(status: {result.status})"}), 400

    qdb.update_document(did, {"content": result.text})
    qdb.transition_version_status(version["id"], "draft", source_attachment_id=attachment["id"])
    audit.log("document", did, "Final Author Version uploaded",
              detail=f"{file.filename} ({result.status}, {result.word_count} words)")
    return jsonify(qdb.get_current_version(did)), 201


@bp.route("/<int:did>/versions", methods=["POST"])
@require_role("company_admin")
def create_version(did):
    """Document Control redesign (spec §3/§21): the normal author workflow
    NEVER creates a version this way — version numbering is entirely system
    controlled (0.1 -> 0.2 -> ... -> 1.0, driven by Self-Check + Final Author
    Version + Review + Approval + Training, see services/document_versioning.py
    and qms_document_database.transition_version_status/reject_and_fork_version/
    start_new_revision/try_clear_training_gate). This free-text-labelled
    snapshot endpoint is kept only as a company_admin-only escape hatch (e.g.
    correcting a legacy/imported record) and is deliberately NOT exposed in
    the author-facing UI."""
    document = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not document:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    new_version = data.get("version", "").strip()
    if not new_version:
        return jsonify({"error": "Version label is required"}), 400

    # Phase F fix (C6): changed_by is derived from the authenticated
    # session, never taken from the request body — see
    # PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md C6.
    changed_by = tenancy.signing_identity(g.tenant)["performed_by"]
    qdb.create_version(did, document.get("version", "1.0"), data.get("change_summary", ""),
                       document.get("content", ""), changed_by)
    qdb.update_document(did, {"version": new_version})
    audit.log("document", did, "New version created",
              old={"version": document.get("version")}, new={"version": new_version})
    return jsonify(qdb.get_document(did)), 201


# ── Distribution ───────────────────────────────────────────────────────────────

@bp.route("/<int:did>/distribution", methods=["GET"])
def get_distribution(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(qdb.get_distribution(did))


@bp.route("/<int:did>/distribution", methods=["POST"])
def add_distribution(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = qdb.add_distribution(did, data)
    return jsonify(entry), 201


@bp.route("/distribution/<int:dist_id>/acknowledge", methods=["POST"])
def acknowledge_distribution(dist_id):
    existing = qdb.get_distribution_entry(dist_id)
    if not existing or not tenancy.scoped_or_none(qdb.get_document(existing["document_id"]), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = qdb.acknowledge_distribution(dist_id, data.get("acknowledged_date", ""))
    if not entry:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


# ── Training ───────────────────────────────────────────────────────────────────

@bp.route("/<int:did>/training", methods=["GET"])
def get_training(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(qdb.get_training(did))


@bp.route("/<int:did>/training/gate", methods=["GET"])
def get_training_gate(did):
    """Document Control redesign (Phase 4): computed training-gate status
    for the document's CURRENT version — completion percentage, trainee
    count, whether the >=90%-with->=1-trainee gate has cleared. The single
    source of truth try_clear_training_gate() itself reads, so the UI can
    never show a percentage that disagrees with what actually gates
    Effective."""
    document = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not document:
        return jsonify({"error": "Not found"}), 404
    version = qdb.get_current_version(did)
    if not version:
        return jsonify({"error": "This document has no current version"}), 404
    return jsonify(qdb.training_gate_status(version["id"]))


@bp.route("/<int:did>/training", methods=["POST"])
def add_training(did):
    if not tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = qdb.add_training(did, data)
    return jsonify(entry), 201


@bp.route("/training/<int:tid>", methods=["PUT"])
def update_training(tid):
    existing = qdb.get_training_entry(tid)
    document = qdb.get_document(existing["document_id"]) if existing else None
    if not existing or not tenancy.scoped_or_none(document, g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    new_training_status = data.get("training_status", "Pending")

    # Electronic Signature gate (21 CFR Part 11 / EU GMP Annex 11) — only
    # the completion attestation is a GMP decision; leaving a training
    # record "Pending" (its default at creation) is not a lifecycle
    # transition and does not require a signature.
    if new_training_status == "Completed":
        try:
            esignature_service.require_esignature(
                g.tenant, data.get("password", ""), data.get("meaning", "Verified"), data.get("reason", ""),
            )
        except esignature_service.ReauthenticationError as exc:
            audit.log_failure("document", existing["document_id"], "Training completion blocked — e-signature failed", reason=str(exc))
            return jsonify({"error": str(exc)}), 401
        except esignature_service.ESignatureError as exc:
            return jsonify({"error": str(exc)}), 400

    entry = qdb.update_training_status(tid, new_training_status, data.get("training_date", ""))
    if not entry:
        return jsonify({"error": "Not found"}), 404

    if new_training_status == "Completed":
        esignature_service.record_signature(
            tenant=g.tenant, meaning=data.get("meaning", "Verified"), reason=data.get("reason", "Training completed"),
            record_type="document", record_id=existing["document_id"],
            old_status=existing.get("training_status", ""), new_status="Completed",
        )
        # Document Control redesign (spec §17/§20, corrected — training
        # completion no longer auto-flips the document to Effective; that
        # let ANY user with training-update access silently perform what
        # must be an explicit Quality Coordinator action). Once this update
        # brings the gate to >=90%, GET .../training/gate reports
        # cleared=true and the UI surfaces a "Release / Make Effective"
        # action to an authorized role — see release_document() below.
    return jsonify(entry)


# ── Workflow: named-approver, gated Document Control lifecycle ───────────────
# Same engine as routes/qms_deviations.py — see services/workflow_engine.py.

def _record_scoped_or_404(did):
    return tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)


@bp.route("/<int:did>/workflow", methods=["GET"])
def get_workflow(did):
    document = _record_scoped_or_404(did)
    if not document:
        return jsonify({"error": "Not found"}), 404
    state = wfe.get_instance_state(RECORD_TYPE, did)
    # Document Control redesign (spec §13/§15/§20): attach approver-pool role
    # labels ("Department Head" / "Quality Head" / "Plant Head") and a
    # quorum summary to the final Approval step so the UI can render
    # "Department Head Pending / Quality Head Pending / Plant Head Optional"
    # and "Required approvals: X of Y" without a second round trip or
    # duplicating pool-resolution logic. Purely additive keys — every other
    # record_type's workflow response (CAPA/Deviation/Change Control, which
    # don't reach this route) and every pre-existing key here are unchanged.
    pool = qdb.get_approver_pool(document.get("company_id", ""), document.get("department", ""))
    pool_by_user = {p["user_id"]: p["pool_role"] for p in pool if p.get("user_id")}
    configured_roles = {p["pool_role"] for p in pool if p.get("user_id")}
    for step in state.get("steps", []):
        if step.get("step_type") != "approval":
            continue
        for a in step.get("approvers", []):
            a["pool_role"] = pool_by_user.get(a["user_id"], "")
        if step.get("step_key") == "effective":
            step["pool_summary"] = [
                {"pool_role": r, "configured": r in configured_roles, "optional": r == "plant_head"}
                for r in qdb.ALL_POOL_ROLES
            ]
    return jsonify(state)


def _effective_quorum_and_pool_approvers(document: dict) -> tuple[int | None, list[dict] | None]:
    """Document Control redesign (Phase 3): if this document's department
    (or the company-wide default) has both mandatory approver-pool roles
    configured, the final Approval stage always uses quorum=2 (2-of-2
    without Plant Head, 2-of-3 with) — a fixed business rule, not the
    manually-set `approval_quorum` field. Falls back to the pre-existing
    `approval_quorum` behaviour (None = single-decider 'any' mode) when no
    pool is configured yet, so a company that hasn't set one up is
    completely unaffected — same as before this phase."""
    try:
        approvers = qdb.resolve_pool_approvers(document)
        return qdb.APPROVAL_QUORUM_REQUIRED, approvers
    except ValueError:
        return document.get("approval_quorum"), None


_SELF_CHECK_REQUIRED_ERROR = (
    "Author Self-Check must be completed for the current version before Submit for Review "
    "— see POST /qms/documents/<id>/self-check"
)
_FINAL_VERSION_REQUIRED_ERROR = (
    "The Final Author Version must be uploaded for the current version before Submit for Review "
    "— see POST /qms/documents/<id>/versions/upload. Attachments are supporting records only and "
    "do not satisfy this requirement."
)
_START_REVISION_REQUIRED_ERROR = (
    "This document is Effective. Start a new revision first — see "
    "POST /qms/documents/<id>/versions/start-revision — complete Author Self-Check on the "
    "new draft, then submit for review. A version forked from an Effective document can "
    "never already have a Self-Check recorded, so this cannot be done in a single call."
)


def _submission_gate_error(did) -> str | None:
    """Author Self-Check + Final Author Version hard gates, corrected: if the
    CURRENT version is still 'draft', checks its own self-check and Final
    Author Version upload (spec §10: "The workflow must require Final Author
    Version before Review submission" — Attachments are supporting records
    only and must never satisfy this). If it's 'effective' (Submit for
    Review would otherwise trigger qms_document_database.start_new_revision()
    to fork a fresh Draft as a side effect of wfe.start_instance()'s own
    version lookup), submission is now always blocked here instead — a
    version that doesn't exist yet cannot possibly already have a recorded
    Self-Check or Final Author Version, so the old single-call "fork and
    submit" shortcut could never have satisfied a fresh gate. Callers must
    fork explicitly via POST .../versions/start-revision, complete both
    gates on the resulting new Draft, then submit — matching the fact that a
    human must actually review the carried-over draft in between. Returns
    None when it's safe to proceed, else the error string to return as a
    409."""
    version = qdb.get_current_version(did)
    if not version:
        return None
    if version["status"] == "effective":
        return _START_REVISION_REQUIRED_ERROR
    if not qdb.is_self_check_cleared(did):
        return _SELF_CHECK_REQUIRED_ERROR
    if not version.get("source_attachment_id"):
        return _FINAL_VERSION_REQUIRED_ERROR
    return None


@bp.route("/<int:did>/versions/start-revision", methods=["POST"])
def start_revision(did):
    """Explicitly start a new revision cycle against an Effective document
    (the spec's '1.0 Effective -> 1.1 Revision Draft' case) — forks a fresh
    Draft version (qms_document_database.start_new_revision()) WITHOUT
    submitting it, so the author can review/edit it and complete a genuine
    Author Self-Check before Submit for Review. Kept as its own explicit
    step specifically so a fresh Self-Check is always possible before
    submission — see _submission_gate_error()'s docstring."""
    document = _record_scoped_or_404(did)
    if not document:
        return jsonify({"error": "Not found"}), 404
    try:
        version = qdb.start_new_revision(did)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    audit.log("document", did, "New revision cycle started", detail=f"version {version['version_number']}")
    return jsonify(version), 201


@bp.route("/<int:did>/workflow/start", methods=["POST"])
def start_workflow(did):
    document = _record_scoped_or_404(did)
    if not document:
        return jsonify({"error": "Not found"}), 404
    # Author Self-Check hard gate (Document Control redesign, Phase 5, fixed
    # post-Phase-5a): blocks Submit for Review until recorded against the
    # CURRENT version — never carried forward from a prior version (see
    # qms_document_database.record_self_check's docstring and
    # _submission_gate_error() above for the Effective-document case).
    gate_error = _submission_gate_error(did)
    if gate_error:
        audit.log_failure("document", did, "Workflow start blocked", reason=gate_error)
        return jsonify({"error": gate_error}), 409
    sig = tenancy.signing_identity(g.tenant)
    effective_quorum, pool_approvers = _effective_quorum_and_pool_approvers(document)
    try:
        state = wfe.start_instance(WORKFLOW_KEY, RECORD_TYPE, did, g.tenant.company_id, sig["performed_by"],
                                    default_quorum=effective_quorum)
        if pool_approvers:
            approval_step = next(s for s in state["steps"] if s["step_key"] == "effective")
            state = wfe.assign_approvers(RECORD_TYPE, did, approval_step["step_order"], pool_approvers)
    except wfe.WorkflowError as e:
        audit.log_failure("document", did, "Workflow start blocked", reason=str(e))
        return jsonify({"error": str(e)}), 409
    return jsonify(state), 201


@bp.route("/<int:did>/workflow/steps/<int:step_order>/assign", methods=["POST"])
def assign_workflow_step(did, step_order):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    approvers = data.get("approvers") or []
    if not isinstance(approvers, list) or not all(a.get("user_id") for a in approvers):
        return jsonify({"error": "approvers must be a non-empty list of {user_id, display_name}"}), 400
    try:
        state = wfe.assign_approvers(RECORD_TYPE, did, step_order, approvers)
    except wfe.WorkflowError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify(state)


@bp.route("/<int:did>/workflow/steps/<int:step_order>/decide", methods=["POST"])
def decide_workflow_step(did, step_order):
    document = _record_scoped_or_404(did)
    if not document:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    decision = data.get("decision", "")
    if decision not in ("approve", "reject", "advance"):
        return jsonify({"error": "decision must be one of approve/reject/advance"}), 400

    # Electronic Signature gate (21 CFR Part 11 / EU GMP Annex 11) — same gate
    # already applied to this record type's legacy submit_approval() below;
    # this newer Workflow Panel path decides the exact same workflow steps
    # and must not be a way to bypass the signature requirement.
    old_status = document["status"]
    try:
        esignature_service.require_esignature(
            g.tenant, data.get("password", ""), data.get("meaning", ""), data.get("reason", ""),
        )
    except esignature_service.ReauthenticationError as exc:
        audit.log_failure("document", did, f"Workflow decision blocked ({decision}) — e-signature failed", reason=str(exc))
        return jsonify({"error": str(exc)}), 401
    except esignature_service.ESignatureError as exc:
        return jsonify({"error": str(exc)}), 400

    sig = tenancy.signing_identity(g.tenant)
    try:
        state = wfe.decide_step(
            RECORD_TYPE, did, step_order, decision,
            user_id=g.tenant.user_id, role=g.tenant.role,
            performed_by=sig["performed_by"], comments=data.get("comments", ""),
        )
    except wfe.WorkflowPermissionError as e:
        audit.log_failure("document", did, f"Workflow decision blocked ({decision})", reason=str(e))
        return jsonify({"error": str(e)}), 403
    except wfe.WorkflowError as e:
        audit.log_failure("document", did, f"Workflow decision blocked ({decision})", reason=str(e))
        return jsonify({"error": str(e)}), 409

    document = qdb.get_document(did)
    esignature_service.record_signature(
        tenant=g.tenant, meaning=data.get("meaning", ""), reason=data.get("reason", ""),
        record_type="document", record_id=did, version_number=str(document.get("version", "")),
        old_status=old_status, new_status=document.get("status", ""),
    )
    return jsonify(state)


# ── Quality Coordinator release (Document Control redesign, spec §17/§20) ────

@bp.route("/<int:did>/release", methods=["POST"])
@require_role("company_admin", "reviewer_qa")
def release_document(did):
    """Quality Coordinator / authorized Quality role release: the ONLY way a
    document ever becomes Effective. Requires the current version to already
    be 'approved' (quorum achieved) AND the training gate (>=90% completion,
    >=1 trainee — see qms_document_database.training_gate_status) to have
    cleared. The Author role is never granted company_admin/reviewer_qa, so
    this enforces spec §7's "Author is NOT responsible for ... making the
    SOP Effective" at the route layer, not just in the UI."""
    document = _record_scoped_or_404(did)
    if not document:
        return jsonify({"error": "Not found"}), 404
    version = qdb.get_current_version(did)
    if not version or version["status"] != "approved":
        return jsonify({"error": "This document is not awaiting release — the current version must "
                                  "have completed Quorum Approval first"}), 409
    gate = qdb.training_gate_status(version["id"])
    if not gate["cleared"]:
        return jsonify({"error": f"Training completion is {gate['completion_pct'] or 0:.0f}% — "
                                  f"must reach {gate['threshold_pct']:.0f}% with at least 1 trainee "
                                  f"before this document can be released"}), 409
    if not (document.get("content") or "").strip():
        return jsonify({"error": "This document has no drafted content — required document "
                                  "information must be complete before Quality Release"}), 409

    old_status = document["status"]
    data = request.get_json() or {}
    # Effective date is supplied/confirmed at release (spec §4) — defaults to
    # today when the caller doesn't pass one; validated so a malformed value
    # never gets silently written to an otherwise-immutable version row.
    effective_date = (data.get("effective_date") or "").strip() or None
    if effective_date:
        try:
            from datetime import date as _date
            _date.fromisoformat(effective_date)
        except ValueError:
            return jsonify({"error": "effective_date must be an ISO date (YYYY-MM-DD)"}), 400
    try:
        esignature_service.require_esignature(
            g.tenant, data.get("password", ""), data.get("meaning", "Released"), data.get("reason", ""),
        )
    except esignature_service.ReauthenticationError as exc:
        audit.log_failure("document", did, "Release blocked — e-signature failed", reason=str(exc))
        return jsonify({"error": str(exc)}), 401
    except esignature_service.ESignatureError as exc:
        return jsonify({"error": str(exc)}), 400

    audit.log("document", did, "Quality Release requested",
              detail=f"version {version.get('version_number', '')}")
    released_document = qdb.try_clear_training_gate(did, effective_date=effective_date)
    if not released_document:
        # Gate was verified above; a concurrent change (e.g. training record
        # edited between the check and here) can still legitimately race.
        return jsonify({"error": "Release conditions are no longer met — please retry"}), 409
    audit.log("document", did, "Quality Release approved — document made Effective",
              detail=f"version {released_document.get('version', '')}")
    esignature_service.record_signature(
        tenant=g.tenant, meaning=data.get("meaning", "Released"), reason=data.get("reason", ""),
        record_type="document", record_id=did, version_number=str(released_document.get("version", "")),
        old_status=old_status, new_status="Effective",
    )
    if (released_document.get("content") or "").strip():
        _publish_effective_document_to_kb(released_document)
    return jsonify(released_document)


# ── Approval / status transition (legacy compatibility wrapper) ──────────────

_STATUS_MAP = {
    "Submitted for Review": "Under Review",
    "Reviewed": "Under Review",
    "Submitted for Approval": "Pending Approval",
    "Approved": "Effective",
    "Rejected": "Draft",
    "Send for Revision": "Under Revision",
    "Made Obsolete": "Obsolete",
}

# These two actions only ever apply to an already-Effective document, i.e.
# after the approval workflow instance has already completed — they're
# post-effective archival transitions, not part of the Draft->Effective
# approval gate the Workflow Engine enforces, so they're applied directly
# (exactly as before), same as routes/qms_documents.py always did.
_POST_EFFECTIVE_ACTIONS = {"Made Obsolete", "Send for Revision"}


@bp.route("/<int:did>/approval", methods=["POST"])
@require_role("company_admin", "reviewer_qa")
def submit_approval(did):
    """Legacy-URL compatibility wrapper (kept for backward compatibility
    during deployment — see docs/plan). Same URL, request shape, and
    response shape as before. Actions that gate the initial Draft->Effective
    approval sequence now decide the document's current Workflow Engine step
    instead of writing `status` directly (one call advances exactly one
    step — see the identical rationale in routes/qms_capa.py's
    submit_approval); the two post-Effective archival actions are unchanged.
    Safe to retire once the frontend only calls /workflow/steps/<order>/decide."""
    document = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not document:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action_name = data.get("action", "")
    if not action_name:
        return jsonify({"error": "Action is required"}), 400
    if action_name not in _STATUS_MAP:
        return jsonify({"error": f"Unknown action '{action_name}'"}), 400

    # Electronic Signature gate (21 CFR Part 11 / EU GMP Annex 11) — every
    # GMP decision on this endpoint requires a fresh password confirmation,
    # not just the caller's existing session. Raises before anything below
    # is mutated if the password is wrong or meaning/reason are missing.
    # See pharmagpt/services/esignature_service.py module docstring.
    old_status = document["status"]
    try:
        esignature_service.require_esignature(
            g.tenant, data.get("password", ""), data.get("meaning", ""), data.get("reason", ""),
        )
    except esignature_service.ReauthenticationError as exc:
        audit.log_failure("document", did, f"Approval action blocked ({action_name}) — e-signature failed", reason=str(exc))
        return jsonify({"error": str(exc)}), 401
    except esignature_service.ESignatureError as exc:
        return jsonify({"error": str(exc)}), 400

    sig = tenancy.signing_identity(g.tenant)
    comments = data.get("comments", "")

    if action_name in _POST_EFFECTIVE_ACTIONS:
        new_status = _STATUS_MAP[action_name]
        try:
            lifecycle_engine.validate_transition("QMS_DOCUMENT", document["status"], new_status)
        except lifecycle_engine.InvalidTransitionError as exc:
            return jsonify({"error": str(exc)}), 409
        updates = {"status": new_status}
        if new_status == "Obsolete" and not document.get("superseded_date"):
            from datetime import date
            updates["superseded_date"] = date.today().isoformat()
        document = qdb.update_document(did, updates)
    else:
        try:
            if not wfdb.get_active_instance(RECORD_TYPE, did):
                # Fixed (previously a documented known limitation): this
                # auto-start branch used to check the OUTGOING Effective
                # version's self-check flag when reached via action="Rejected"
                # on an already-Effective document, not a fresh one on the new
                # draft start_instance() was about to fork mid-call — meaning
                # a version could reach Submit for Review having never had a
                # real Self-Check recorded on it. _submission_gate_error() now
                # blocks this case outright (a forked-but-not-yet-created
                # version can never already have a Self-Check): the caller
                # must call POST .../versions/start-revision explicitly,
                # complete Self-Check on the resulting new Draft, then
                # resubmit — the same gate /workflow/start applies.
                gate_error = _submission_gate_error(did)
                if gate_error:
                    audit.log_failure("document", did, f"Approval action blocked ({action_name})",
                                       reason=gate_error)
                    return jsonify({"error": gate_error}), 409
                effective_quorum, pool_approvers = _effective_quorum_and_pool_approvers(document)
                start_state = wfe.start_instance(WORKFLOW_KEY, RECORD_TYPE, did, g.tenant.company_id,
                                                  sig["performed_by"], default_quorum=effective_quorum)
                if pool_approvers:
                    approval_step = next(s for s in start_state["steps"] if s["step_key"] == "effective")
                    wfe.assign_approvers(RECORD_TYPE, did, approval_step["step_order"], pool_approvers)
            state = wfe.get_instance_state(RECORD_TYPE, did)
            instance = state["instance"]
            if not instance or instance["status"] != "in_progress":
                return jsonify({"error": "No active workflow step to act on"}), 409
            step = next(s for s in state["steps"] if s["step_order"] == instance["current_step_order"])
            if action_name == "Rejected":
                if step["step_type"] != "approval":
                    return jsonify({"error": f"'{step['step_name']}' cannot be rejected directly"}), 409
                decision = "reject"
            else:
                decision = "approve" if step["step_type"] == "approval" else "advance"
            if step["step_type"] == "approval":
                approver_ids = {a["user_id"] for a in step.get("approvers", [])}
                # Document Control redesign (Phase 3): only auto-self-assign
                # when NO approver is set yet at all. Once approvers exist
                # (whether pool-derived mandatory Dept Head/Quality Head/
                # Plant Head, or manually assigned by someone else), a
                # caller who isn't one of them must never silently overwrite
                # that assignment — decide_step()'s own
                # WorkflowPermissionError (403) is the correct outcome for
                # that case, exactly as it already is for the Workflow Panel
                # path (/workflow/steps/<order>/decide).
                if not approver_ids and g.tenant.user_id not in approver_ids:
                    wfe.assign_approvers(RECORD_TYPE, did, step["step_order"],
                                          [{"user_id": g.tenant.user_id, "display_name": sig["performed_by"]}])
            wfe.decide_step(RECORD_TYPE, did, step["step_order"], decision,
                             user_id=g.tenant.user_id, role=g.tenant.role,
                             performed_by=sig["performed_by"], comments=comments)
        except (wfe.WorkflowPermissionError, wfe.WorkflowError) as e:
            audit.log_failure("document", did, f"Approval action blocked ({action_name})", reason=str(e))
            return jsonify({"error": str(e)}), 409
        document = qdb.get_document(did)
        if document.get("status") == "Effective" and not document.get("effective_date"):
            from datetime import date
            document = qdb.update_document(did, {"effective_date": date.today().isoformat()})

    entry = qmsdb.add_approval_entry(
        "document", did, action_name,
        sig["performed_by"], sig["role"],
        comments, sig["electronic_sig"],
    )
    esignature_service.record_signature(
        tenant=g.tenant, meaning=data.get("meaning", ""), reason=data.get("reason", ""),
        record_type="document", record_id=did, version_number=str(document.get("version", "")),
        old_status=old_status, new_status=document.get("status", ""),
    )
    return jsonify(entry), 201


def _publish_effective_document_to_kb(document: dict) -> None:
    """Phase 2: an Effective Document Control record becomes the current
    version in the Knowledge Base automatically — no manual upload. Failures
    are logged, never raised: a KB-sync problem must not block the approval
    itself (the approval and its audit trail are already committed)."""
    try:
        kb_sync.publish_to_kb(
            source_type="document", source_id=document["id"], company_id=g.tenant.company_id,
            title=document.get("title", "Untitled Document"), doc_type=document.get("doc_type", "SOP"),
            doc_number=document.get("doc_number", ""), version=document.get("version", "1.0"),
            content_markdown=document["content"], effective_date=document.get("effective_date"),
            form_data={"title": document.get("title", ""), "department": document.get("department", "")},
        )
    except Exception:
        logger.exception(
            "kb_sync: failed to publish Document Control record %s to Knowledge Base", document["id"]
        )


# ── Report / Export ────────────────────────────────────────────────────────────

def _requested_version_id(did):
    """?version_id=<id> (Document Control redesign) — export a specific
    historical version instead of the document's live current state.
    Validates it actually belongs to this document before use."""
    raw = request.args.get("version_id")
    if not raw:
        return None
    try:
        version_id = int(raw)
    except (TypeError, ValueError):
        return None
    version = qdb.get_version(version_id)
    if not version or version["document_id"] != did:
        return None
    return version_id


@bp.route("/<int:did>/report", methods=["GET"])
def get_report(did):
    document = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not document:
        return jsonify({"error": "Not found"}), 404
    md = svc.generate_report_markdown(did, _requested_version_id(did))
    return jsonify({"markdown": md, "title": document.get("title", "")})


@bp.route("/<int:did>/export/docx", methods=["POST"])
def export_docx(did):
    document = tenancy.scoped_or_none(qdb.get_document(did), g.tenant.company_id)
    if not document:
        return jsonify({"error": "Not found"}), 404
    from pharmagpt.services.doc_exporter import markdown_to_docx
    md = svc.generate_report_markdown(did, _requested_version_id(did))
    docx_bytes = markdown_to_docx(md, document.get("doc_type", "SOP"), {
        "title": document.get("title", ""),
        "department": document.get("department", ""),
    })
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", document.get("title", "Document"))[:40]
    filename = f"{document.get('doc_number', 'DOC')}_{safe_title}.docx"
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )

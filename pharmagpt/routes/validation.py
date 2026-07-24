"""
routes/validation.py — Validation document generation, DOCX export, and saved-doc management.

Routes
------
POST /validation/generate                   SSE: generate a validation document
POST /validation/export/docx                convert markdown content to DOCX download
POST /validation/save                       save a generated doc to the project library
GET  /projects/<id>/generated-docs          list saved generated docs (metadata only)
GET  /generated-docs/<id>                   get a single saved doc (with full content)
DELETE /generated-docs/<id>                 delete a saved generated doc
"""

import json
import logging
from io import BytesIO

from pharmagpt import database as db
from pharmagpt import tenancy
from pharmagpt.auth.decorators import require_role
from flask import Blueprint, g, jsonify, request, Response, send_file, stream_with_context
from google.genai import errors, types
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from pharmagpt.review import run_review
from pharmagpt.services.doc_generator import build_generation_prompt
from pharmagpt.services.doc_exporter import markdown_to_docx
from pharmagpt.services.retrieval_engine import retrieve_context
from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL

logger = logging.getLogger(__name__)

bp = Blueprint("validation", __name__)

# URS/IQ/OQ/PQ/CAPA/Deviation/Change Control each now have their own
# dedicated, more capable suite (URS Management, Qualification, QMS
# CAPA/Deviation/Change Control) with its own AI generation, lifecycle, and
# approval trail. Generating them here too was a Critical finding
# (REPOSITORY_AUDIT.md, DUPLICATE_FUNCTION_ANALYSIS.md §1) — a duplicate,
# review-gate-free path to the same document type — retired per Blueprint
# ADR-P02. Rejected server-side, not just hidden client-side, so the
# duplicate path can't be reached by a direct API call either.
#
# Phase 3 (Enterprise Validation Platform) retires DQ/FAT/SAT the same way:
# they used to persist here into the lifecycle-less generic
# `generated_documents` table with no versioning/approval/audit trail at all.
# They are now qms_documents rows (doc_type='DQ'|'FAT'|'SAT') created via
# POST /qms/documents, gaining the shared lifecycle engine, configurable
# approval workflow, versioning, distribution/training tracking, and
# automatic Knowledge Base sync that Document Control already provides —
# no new persistence code, no new document type.
_RETIRED_DOC_TYPES = {
    "URS": "URS Management",
    "IQ": "Qualification",
    "OQ": "Qualification",
    "PQ": "Qualification",
    "CAPA": "Quality Management → CAPA",
    "Deviation": "Quality Management → Deviations",
    "Change Control": "Quality Management → Change Control",
    "DQ": "Quality Management → Document Control (qms/documents)",
    "FAT": "Quality Management → Document Control (qms/documents)",
    "SAT": "Quality Management → Document Control (qms/documents)",
}


@bp.route("/validation/generate", methods=["POST"])
def validation_generate():
    """
    SSE endpoint: generate a validation document with Gemini.

    Body: {
        "doc_type":    "DQ" | "FAT" | "SAT" | "FMEA" | "IQ/OQ Combined" |
                       "SOP" | "Validation Plan" | "Validation Report",
        "project_id":  3,
        "form_data":   { equipment Step-1 fields, "details": { Step-2 fields } },
        "doc_ids":     [1, 2]   -- optional; IDs of uploaded docs to use as context
    }
    Stream: data: {"chunk": "..."}\n\n
            data: {"done": true}\n\n
            data: {"error": "..."}\n\n
    """
    data       = request.get_json()
    doc_type   = data.get("doc_type", "OQ")
    project_id = data.get("project_id")
    form_data  = data.get("form_data", {})
    doc_ids    = data.get("doc_ids", [])

    if doc_type in _RETIRED_DOC_TYPES:
        return jsonify({
            "error": f"{doc_type} is no longer generated here. Use the {_RETIRED_DOC_TYPES[doc_type]} "
                     f"suite instead, which has its own AI generation, lifecycle, and approval trail."
        }), 410

    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    project = tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Retrieve relevant context from all knowledge sources (project docs, KB,
    # SOPs, equipment manuals, regulations, previous validations).
    # retrieve_context() is called once per generation and self-caches within
    # the request — no repeated document scans.
    equipment_name = " ".join(filter(None, [
        form_data.get("equipment_name", ""),
        form_data.get("model", ""),
        form_data.get("manufacturer", ""),
    ]))
    retrieval = retrieve_context(
        document_type=doc_type,
        project_id=project_id,
        equipment_name=equipment_name,
        questionnaire=form_data.get("details", {}),
        max_chunks=10,
    )
    doc_context = retrieval.context_text if retrieval.found else ""

    form_data["project_name"] = project["name"]
    prompt = build_generation_prompt(doc_type, form_data, doc_context, project["name"])

    # Most doc types generate from a single prompt. A few (see
    # doc_generator.COMBINED_DOC_TYPES) are assembled from more than one
    # proven single-purpose prompt, each generated in its own Gemini call and
    # streamed back-to-back — see build_generation_prompt() docstring.
    prompt_parts = prompt if isinstance(prompt, list) else [prompt]

    def generate():
        try:
            for i, part in enumerate(prompt_parts):
                if i > 0:
                    yield f"data: {json.dumps({'chunk': chr(10) + chr(10) + '---' + chr(10) + chr(10)})}\n\n"

                for chunk in gemini_client.models.generate_content_stream(
                    model=GEMINI_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=part)])],
                    config=types.GenerateContentConfig(
                        system_instruction=PHARMA_SYSTEM_PROMPT,
                        temperature=0.3,   # lower temperature for consistent document structure
                        max_output_tokens=12000,   # bound worst-case output; full protocols normally run 3-8K tokens
                        # frequency_penalty was previously set here to mitigate repetition
                        # loops on long structured output, but gemini-2.5-flash rejects any
                        # penalty parameter with a 400 INVALID_ARGUMENT ("Penalty is not
                        # enabled for models/gemini-2.5-flash"), which broke every generation
                        # call. Removed until the API/model supports it.
                    ),
                ):
                    if chunk.text:
                        yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except errors.ServerError:
            yield f"data: {json.dumps({'error': 'Gemini server temporarily unavailable. Please try again.'})}\n\n"

        except errors.ClientError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/validation/export/docx", methods=["POST"])
def validation_export_docx():
    """
    Convert markdown content to a professional DOCX and return it as a download.

    Body: {
        "doc_type":   "OQ",
        "title":      "HPLC OQ Protocol",
        "form_data":  { ...wizard fields... },
        "content":    "# OPERATIONAL QUALIFICATION...",
        "project_id": 3   (optional — used for DB record)
    }

    form_data may include any of:
        company_name, site_name, department, equipment_name, equipment_id,
        manufacturer, model, protocol_number, revision_number, effective_date,
        document_status ("Draft"|"Final"), prepared_by, reviewed_by, approved_by,
        logo_path, revision_history (list), signatories (list)
    """
    data       = request.get_json()
    doc_type   = data.get("doc_type", "DOC")
    title      = data.get("title", f"{doc_type} Protocol")
    form_data  = data.get("form_data", {})
    content    = data.get("content", "")
    project_id = data.get("project_id", 0)

    if not content:
        return jsonify({"error": "No content to export"}), 400

    # Inject title and project_id so build_document_data can use them
    form_data.setdefault("title",      title)
    form_data.setdefault("project_id", project_id)

    try:
        docx_bytes = markdown_to_docx(content, doc_type, form_data)
    except Exception as exc:
        logger.exception("DOCX export failed")
        return jsonify({"error": f"Export failed: {exc}"}), 500

    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    return send_file(
        BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"{safe_title}.docx",
    )


@bp.route("/validation/review", methods=["POST"])
def validation_review():
    """
    Run the deterministic Validation Review Engine on provided markdown content.

    Body: {
        "content":   "# OPERATIONAL QUALIFICATION...",
        "doc_type":  "OQ",
        "form_data": { ...wizard fields... }
    }

    Returns the full ReviewResult as JSON — no AI calls are made, runs synchronously.
    """
    data      = request.get_json() or {}
    content   = data.get("content", "")
    doc_type  = data.get("doc_type", "DOC")
    form_data = data.get("form_data", {})

    if not content:
        return jsonify({"error": "content is required"}), 400

    try:
        result = run_review(content, doc_type, form_data)
        return jsonify(result.to_dict())
    except Exception as exc:
        logger.exception("Review engine error")
        return jsonify({"error": f"Review failed: {exc}"}), 500


@bp.route("/validation/save", methods=["POST"])
def validation_save():
    """
    Persist a generated validation document to the project's saved-docs library.

    Body: { "project_id": 3, "doc_type": "OQ", "title": "...",
            "form_data": {...}, "content": "..." }
    """
    data       = request.get_json()
    project_id = data.get("project_id")
    doc_type   = data.get("doc_type", "DOC")
    title      = data.get("title", f"{doc_type} Document")
    form_data  = data.get("form_data", {})
    content    = data.get("content", "")

    if not project_id or not content:
        return jsonify({"error": "project_id and content are required"}), 400

    if not tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id):
        return jsonify({"error": "Project not found"}), 404

    doc = db.save_generated_document(
        project_id=project_id,
        doc_type=doc_type,
        title=title,
        form_data_json=json.dumps(form_data),
        content=content,
    )
    return jsonify({"status": "saved", "id": doc["id"]}), 201


@bp.route("/projects/<int:project_id>/generated-docs", methods=["GET"])
def list_generated_docs(project_id):
    """Return all saved generated documents for a project (metadata only, no content)."""
    if not tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_generated_documents(project_id))


def _generated_doc_scoped(doc_id):
    """Return the generated document only if it exists AND its owning
    Project belongs to the caller's company (generated_documents has no
    company_id of its own — it inherits tenancy from project_id, which is
    NOT NULL — pharmagpt/tenancy.py)."""
    doc = db.get_generated_document(doc_id)
    if not doc:
        return None
    if not tenancy.scoped_or_none(db.get_project(doc["project_id"]), g.tenant.company_id):
        return None
    return doc


@bp.route("/generated-docs/<int:doc_id>", methods=["GET"])
def get_generated_doc(doc_id):
    """Return a single generated document including its full markdown content."""
    doc = _generated_doc_scoped(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(doc)


@bp.route("/generated-docs/<int:doc_id>", methods=["DELETE"])
@require_role("company_admin")
def delete_generated_doc(doc_id):
    """Delete a saved generated document by ID."""
    if not _generated_doc_scoped(doc_id):
        return jsonify({"error": "Document not found"}), 404
    db.delete_generated_document(doc_id)
    return jsonify({"status": "deleted"})

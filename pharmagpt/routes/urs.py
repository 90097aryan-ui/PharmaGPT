"""
routes/urs.py — URS Management Suite API endpoints.

All routes return JSON. AI generation runs as a background job (see
services/urs_generation_job.py) — the frontend polls for status rather than
holding a request open.

Routes
------
GET    /urs/dashboard                        dashboard statistics
GET    /urs/                                 list all URS (filterable)
POST   /urs/                                 create new URS
GET    /urs/<id>                             get single URS
PUT    /urs/<id>                             update URS fields
DELETE /urs/<id>                             delete URS

GET    /urs/<id>/requirements                get requirements
POST   /urs/<id>/requirements                save (replace) all requirements
POST   /urs/<id>/requirements/add            add single requirement
PUT    /urs/<id>/requirements/<req_id>       update single requirement
DELETE /urs/<id>/requirements/<req_id>       delete single requirement

POST   /urs/<id>/generate                    start AI generation (returns immediately)
GET    /urs/<id>/generate/status             poll AI generation job status/progress
POST   /urs/<id>/review                      AI review URS
POST   /urs/<id>/library                     load library requirements

GET    /urs/<id>/approval                    get approval trail
POST   /urs/<id>/approval                    add approval entry

GET    /urs/<id>/versions                    get version list
POST   /urs/<id>/versions                    create version snapshot
GET    /urs/<id>/versions/<vid>/requirements get version requirements

GET    /urs/<id>/export/docx                 export as DOCX
GET    /urs/library/types                    list equipment types in library
"""

import json
import logging
import time
from flask import Blueprint, jsonify, request

from pharmagpt import urs_database as udb
from pharmagpt.services import urs_service as svc
from pharmagpt.services.urs_generation_job import submit_generation_job
from pharmagpt.services.urs_requirement_library import (
    build_numbered_requirements,
    list_equipment_types,
    get_sections_for_type,
)
from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from pharmagpt.services.doc_exporter import markdown_to_docx
from google.genai import types

logger = logging.getLogger(__name__)

bp = Blueprint("urs", __name__, url_prefix="/urs")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route("/dashboard")
def dashboard():
    return jsonify(udb.get_dashboard_stats())


# ── URS CRUD ──────────────────────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
def list_urs():
    filters = {
        "status":         request.args.get("status"),
        "category":       request.args.get("category"),
        "department":     request.args.get("department"),
        "equipment_type": request.args.get("equipment_type"),
        "keyword":        request.args.get("q"),
    }
    return jsonify(udb.get_all_urs({k: v for k, v in filters.items() if v}))


@bp.route("/", methods=["POST"])
def create_urs():
    data = request.get_json() or {}
    if not data.get("title", "").strip() and not data.get("equipment_name", "").strip():
        return jsonify({"error": "Title or equipment name is required"}), 400
    if not data.get("title", "").strip():
        data["title"] = f"URS – {data.get('equipment_name', 'New Equipment')}"
    urs = udb.create_urs(data)
    return jsonify(urs), 201


@bp.route("/<int:uid>", methods=["GET"])
def get_urs(uid):
    urs = udb.get_urs(uid)
    if not urs:
        return jsonify({"error": "URS not found"}), 404
    return jsonify(urs)


@bp.route("/<int:uid>", methods=["PUT"])
def update_urs(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    data = request.get_json() or {}
    updated = udb.update_urs(uid, data)
    return jsonify(updated)


@bp.route("/<int:uid>", methods=["DELETE"])
def delete_urs(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    udb.delete_urs(uid)
    return jsonify({"deleted": True})


# ── Requirements ──────────────────────────────────────────────────────────────

@bp.route("/<int:uid>/requirements", methods=["GET"])
def get_requirements(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    return jsonify(udb.get_requirements(uid))


@bp.route("/<int:uid>/requirements", methods=["POST"])
def save_requirements(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    reqs = request.get_json() or []
    saved = udb.save_requirements(uid, reqs)
    return jsonify(saved)


@bp.route("/<int:uid>/requirements/add", methods=["POST"])
def add_requirement(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    req = request.get_json() or {}
    new_req = udb.add_requirement(uid, req)
    return jsonify(new_req), 201


@bp.route("/<int:uid>/requirements/<int:rid>", methods=["PUT"])
def update_requirement(uid, rid):
    data = request.get_json() or {}
    updated = udb.update_requirement(rid, data)
    if not updated:
        return jsonify({"error": "Requirement not found"}), 404
    return jsonify(updated)


@bp.route("/<int:uid>/requirements/<int:rid>", methods=["DELETE"])
def delete_requirement(uid, rid):
    udb.delete_requirement(rid)
    return jsonify({"deleted": True})


# ── Library Requirements ──────────────────────────────────────────────────────

@bp.route("/<int:uid>/library", methods=["POST"])
def load_library(uid):
    """Load pre-built library requirements for the URS equipment type."""
    urs = udb.get_urs(uid)
    if not urs:
        return jsonify({"error": "URS not found"}), 404
    data = request.get_json() or {}
    equipment_type = data.get("equipment_type") or urs.get("equipment_type", "")
    if not equipment_type:
        return jsonify({"error": "Equipment type required"}), 400
    reqs = build_numbered_requirements(equipment_type)
    saved = udb.save_requirements(uid, reqs)
    return jsonify({"loaded": len(reqs), "requirements": saved})


@bp.route("/library/types", methods=["GET"])
def library_types():
    return jsonify({"types": list_equipment_types()})


@bp.route("/library/sections", methods=["GET"])
def library_sections():
    equipment_type = request.args.get("type", "")
    if not equipment_type:
        return jsonify({"sections": []})
    return jsonify({"sections": get_sections_for_type(equipment_type)})


# ── AI Generation (background job — poll for status) ─────────────────────────

@bp.route("/<int:uid>/generate", methods=["POST"])
def generate_requirements(uid):
    """Start AI requirement generation as a background job and return immediately.

    Generation used to run inline via generate_content_stream(), holding the
    request (and a gunicorn worker) open for the full generation time — long
    enough on large section selections to exceed Render's worker timeout and
    get SIGKILLed mid-stream. See services/urs_generation_job.py.
    """
    route_start = time.perf_counter()
    urs = udb.get_urs(uid)
    if not urs:
        return jsonify({"error": "URS not found"}), 404

    data = request.get_json() or {}
    sections = data.get("sections", [
        "General Requirements", "Functional Requirements", "Performance Requirements",
        "Safety Requirements", "GMP Requirements", "Data Integrity Requirements",
        "Alarm Requirements", "Audit Trail",
    ])

    urs_info = dict(urs)
    urs_info.update({k: data.get(k, urs.get(k, "")) for k in (
        "equipment_name", "equipment_type", "category", "purpose",
        "intended_use", "process_description",
    )})

    submit_generation_job(uid, urs_info, sections)

    logger.info(
        "URS %s generation job submitted (%d sections) — request handled in %.3fs",
        uid, len(sections), time.perf_counter() - route_start,
    )
    return jsonify({"status": "started", "urs_id": uid}), 202


@bp.route("/<int:uid>/generate/status", methods=["GET"])
def generation_status(uid):
    """Poll the background generation job's current status/progress."""
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    status = udb.get_generation_status(uid)
    return jsonify(status)


# ── AI Review ─────────────────────────────────────────────────────────────────

@bp.route("/<int:uid>/review", methods=["POST"])
def review_urs(uid):
    """AI review of the complete URS — scores and improvement suggestions."""
    urs = udb.get_urs(uid)
    if not urs:
        return jsonify({"error": "URS not found"}), 404
    requirements = udb.get_requirements(uid)
    if not requirements:
        return jsonify({"error": "No requirements to review"}), 400

    prompt = svc.build_ai_review_prompt(urs, requirements)
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=PHARMA_SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=4096,
            ),
        )
        raw = response.text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        review_data = json.loads(raw)
    except Exception as e:
        review_data = {
            "compliance_score": 0,
            "completeness_score": 0,
            "overall_assessment": f"Review failed: {str(e)}",
            "strengths": [],
            "missing_requirements": [],
            "improvements": [],
            "regulatory_gaps": [],
            "data_integrity_assessment": "",
            "csv_readiness": "",
            "risk_flags": [],
            "recommendation": "Review Error",
        }

    # Save review data to URS
    udb.update_urs(uid, {
        "ai_review_data": review_data,
        "compliance_score": review_data.get("compliance_score", 0),
        "completeness_score": review_data.get("completeness_score", 0),
    })
    return jsonify(review_data)


# ── Approval Workflow ─────────────────────────────────────────────────────────

@bp.route("/<int:uid>/approval", methods=["GET"])
def get_approval(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    return jsonify(udb.get_approval_trail(uid))


@bp.route("/<int:uid>/approval", methods=["POST"])
def add_approval(uid):
    urs = udb.get_urs(uid)
    if not urs:
        return jsonify({"error": "URS not found"}), 404
    data = request.get_json() or {}
    action = data.get("action", "")
    performed_by = data.get("performed_by", "")
    role = data.get("role", "")
    comments = data.get("comments", "")

    if not action or not performed_by:
        return jsonify({"error": "action and performed_by are required"}), 400

    # Update URS status based on action
    status_map = {
        "Submitted for Review": "under_review",
        "Review Complete": "under_review",
        "Submitted for Approval": "pending_approval",
        "Approved": "approved",
        "Rejected": "draft",
        "Obsolete": "obsolete",
    }
    if action in status_map:
        udb.update_urs(uid, {"status": status_map[action]})

    entry = udb.add_approval_entry(uid, action, performed_by, role, comments, urs.get("revision", "A"))
    return jsonify(entry), 201


# ── Version History ───────────────────────────────────────────────────────────

@bp.route("/<int:uid>/versions", methods=["GET"])
def get_versions(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    return jsonify(udb.get_versions(uid))


@bp.route("/<int:uid>/versions", methods=["POST"])
def create_version(uid):
    if not udb.get_urs(uid):
        return jsonify({"error": "URS not found"}), 404
    data = request.get_json() or {}
    change_summary = data.get("change_summary", "Version snapshot")
    created_by = data.get("created_by", "System")
    snapshot = udb.create_version_snapshot(uid, change_summary, created_by)
    udb.add_approval_entry(uid, "Version Snapshot Created", created_by, "", change_summary)
    return jsonify(snapshot), 201


@bp.route("/<int:uid>/versions/<int:vid>/requirements", methods=["GET"])
def get_version_requirements(uid, vid):
    return jsonify(udb.get_version_requirements(vid))


# ── Export ────────────────────────────────────────────────────────────────────

@bp.route("/<int:uid>/export/docx", methods=["GET", "POST"])
def export_docx(uid):
    """Export URS as a professional DOCX document."""
    from flask import send_file
    import io

    urs = udb.get_urs(uid)
    if not urs:
        return jsonify({"error": "URS not found"}), 404
    requirements = udb.get_requirements(uid)

    markdown_content = svc.build_urs_markdown(urs, requirements)
    title = urs.get("title", "URS Document")
    form_data = {
        "title": title,
        "urs_number": urs.get("urs_number", ""),
        "doc_number": urs.get("doc_number", ""),
        "revision": urs.get("revision", "A"),
        "equipment_name": urs.get("equipment_name", ""),
        "department": urs.get("department", ""),
        "prepared_by": urs.get("prepared_by", ""),
        "reviewed_by": urs.get("reviewed_by", ""),
        "approved_by": urs.get("approved_by", ""),
        "effective_date": urs.get("effective_date", ""),
    }

    docx_bytes = markdown_to_docx(markdown_content, "URS", form_data)
    safe_name = f"URS_{urs.get('urs_number', uid)}.docx".replace(" ", "_")

    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=safe_name,
    )

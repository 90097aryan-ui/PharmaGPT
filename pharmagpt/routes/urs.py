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
import re
import time
from datetime import date, datetime
from flask import Blueprint, g, jsonify, request

from pharmagpt import urs_database as udb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import require_role
from pharmagpt.services import urs_service as svc
from pharmagpt.services import urs_lifecycle as lifecycle
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

# Fields the document-control automation now owns end-to-end (see
# urs_database.create_urs() and add_approval() below). A client may still
# send them in a PUT body (the wizard's "edit" form resubmits the full
# record it loaded), but the values are silently ignored rather than
# applied — these are no longer freeform-editable fields.
_SYSTEM_CONTROLLED_FIELDS = {
    "urs_number", "doc_number", "revision", "version",
    "prepared_by", "reviewed_by", "approved_by", "effective_date",
}


def _current_display_name(fallback: str = "") -> str:
    """Best-effort identity of the authenticated caller for audit/document-
    control fields. Falls back to `fallback` when no tenant context is
    available (e.g. in tests that intentionally bypass the auth gate — see
    tests/conftest.py's `client` fixture)."""
    tenant = getattr(g, "tenant", None)
    if tenant is not None:
        return tenant.display_name or tenant.email or fallback
    return fallback


def _current_role(fallback: str = "") -> str:
    tenant = getattr(g, "tenant", None)
    if tenant is not None:
        return tenant.role or fallback
    return fallback


bp = Blueprint("urs", __name__, url_prefix="/urs")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route("/dashboard")
def dashboard():
    return jsonify(udb.get_dashboard_stats(g.tenant.company_id))


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
    return jsonify(udb.get_all_urs(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("/", methods=["POST"])
def create_urs():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip() and not data.get("equipment_name", "").strip():
        return jsonify({"error": "Title or equipment name is required"}), 400
    if not data.get("title", "").strip():
        data["title"] = f"URS – {data.get('equipment_name', 'New Equipment')}"
    # Prepared By is always the authenticated creator, never a client-
    # supplied value — urs_database.create_urs() also unconditionally
    # ignores urs_number/doc_number/revision/status/reviewed_by/approved_by/
    # effective_date from `data` regardless of what's set here.
    data["prepared_by"] = _current_display_name(fallback=data.get("prepared_by", ""))
    urs = udb.create_urs(data, company_id=g.tenant.company_id)
    return jsonify(urs), 201


@bp.route("/<int:uid>", methods=["GET"])
def get_urs(uid):
    urs = tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id)
    if not urs:
        return jsonify({"error": "URS not found"}), 404
    return jsonify(urs)


@bp.route("/<int:uid>", methods=["PUT"])
def update_urs(uid):
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
        return jsonify({"error": "URS not found"}), 404
    data = request.get_json() or {}
    if "status" in data:
        return jsonify({
            "error": "status cannot be changed via PUT — use POST /urs/<id>/approval "
                     "to move the document through its lifecycle",
        }), 400
    # urs_number/doc_number/revision/version/prepared_by/reviewed_by/
    # approved_by/effective_date are system-controlled (see create_urs() and
    # add_approval()) — silently drop them rather than error, since the
    # wizard's "edit" form resubmits the full record it loaded, including
    # these read-only fields.
    data = {k: v for k, v in data.items() if k not in _SYSTEM_CONTROLLED_FIELDS}
    updated = udb.update_urs(uid, data)
    return jsonify(updated)


@bp.route("/<int:uid>", methods=["DELETE"])
@require_role("company_admin")
def delete_urs(uid):
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
        return jsonify({"error": "URS not found"}), 404
    udb.delete_urs(uid)
    return jsonify({"deleted": True})


# ── Requirements ──────────────────────────────────────────────────────────────

@bp.route("/<int:uid>/requirements", methods=["GET"])
def get_requirements(uid):
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
        return jsonify({"error": "URS not found"}), 404
    return jsonify(udb.get_requirements(uid))


@bp.route("/<int:uid>/requirements", methods=["POST"])
def save_requirements(uid):
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
        return jsonify({"error": "URS not found"}), 404
    reqs = request.get_json() or []
    saved = udb.save_requirements(uid, reqs)
    return jsonify(saved)


@bp.route("/<int:uid>/requirements/add", methods=["POST"])
def add_requirement(uid):
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
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
@require_role("company_admin")
def delete_requirement(uid, rid):
    udb.delete_requirement(rid)
    return jsonify({"deleted": True})


# ── Library Requirements ──────────────────────────────────────────────────────

@bp.route("/<int:uid>/library", methods=["POST"])
def load_library(uid):
    """Load pre-built library requirements for the URS equipment type."""
    urs = tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id)
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
    urs = tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id)
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

    performed_by = _current_display_name(fallback="System")
    submit_generation_job(uid, urs_info, sections, performed_by=performed_by)

    logger.info(
        "URS %s generation job submitted (%d sections) — request handled in %.3fs",
        uid, len(sections), time.perf_counter() - route_start,
    )
    return jsonify({"status": "started", "urs_id": uid}), 202


@bp.route("/<int:uid>/generate/status", methods=["GET"])
def generation_status(uid):
    """Poll the background generation job's current status/progress."""
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
        return jsonify({"error": "URS not found"}), 404
    status = udb.get_generation_status(uid)
    return jsonify(status)


# ── AI Review ─────────────────────────────────────────────────────────────────

@bp.route("/<int:uid>/review", methods=["POST"])
def review_urs(uid):
    """AI review of the complete URS — scores and improvement suggestions.

    On success, the review is persisted and returned with HTTP 200. On
    failure, nothing is written to the URS (a transient Gemini error must
    not clobber a previously-saved good review — see get_review below,
    which is how the frontend re-displays the latest saved review) and the
    response is a non-2xx status with a human-readable "error" message, so
    the frontend can render an explicit failure state instead of silently
    treating a broken response as "no review yet".
    """
    urs = tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id)
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
        raw = (response.text or "").strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        if not raw:
            raise ValueError("Gemini returned an empty response")
        try:
            review_data = json.loads(raw)
        except json.JSONDecodeError:
            # Model sometimes prefixes/suffixes the JSON with prose despite
            # the "return ONLY JSON" instruction — fall back to extracting
            # the first {...} block (mirrors the list-extraction fallback
            # already used for the risk-assessment reviewer, routes/risk.py).
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                raise
            review_data = json.loads(match.group())
    except Exception as e:
        logger.exception("AI review failed for URS %s", uid)
        return jsonify({
            "error": f"AI review failed: {e}",
        }), 502

    review_data["reviewed_at"] = datetime.utcnow().isoformat()

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
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
        return jsonify({"error": "URS not found"}), 404
    return jsonify(udb.get_approval_trail(uid))


# Action -> target lifecycle status. Kept as the same action vocabulary the
# approval-panel UI already sends (see static/js/urs.js addApprovalEntry())
# so no frontend change is required — only the status each one maps to, and
# the validation now applied to it, are new. "Make Effective" is a new
# action with no UI trigger yet (Iteration 3); the backend supports it now
# so the lifecycle's terminal Approved -> Effective step isn't left
# unreachable pending that frontend work.
_ACTION_STATUS_MAP = {
    "Submitted for Review":   lifecycle.UNDER_REVIEW,
    "Review Complete":        lifecycle.UNDER_REVIEW,
    "Submitted for Approval": lifecycle.PENDING_APPROVAL,
    "Approved":               lifecycle.APPROVED,
    "Rejected":                lifecycle.DRAFT,
    "Make Effective":          lifecycle.EFFECTIVE,
    "Obsolete":                 lifecycle.OBSOLETE,
}

# "Submitted for Review" is the author moving their own draft into review —
# it must NOT set reviewed_by (the author isn't the reviewer). Only "Review
# Complete" (a reviewer logging that they finished reviewing it) does.
_REVIEW_ACTIONS = {"Review Complete"}
_APPROVAL_ACTIONS = {"Approved"}


@bp.route("/<int:uid>/approval", methods=["POST"])
@require_role("company_admin", "reviewer_qa")
def add_approval(uid):
    urs = tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id)
    if not urs:
        return jsonify({"error": "URS not found"}), 404
    data = request.get_json() or {}
    action = data.get("action", "")
    if not action:
        return jsonify({"error": "action is required"}), 400

    # Reviewed By / Approved By / QA Approval now come from the
    # authenticated identity performing this action, not a free-text field
    # the caller could set to anyone's name — the client-supplied
    # performed_by/role are only used as a fallback when there is no
    # authenticated tenant (e.g. tests that bypass the auth gate).
    performed_by = _current_display_name(fallback=data.get("performed_by", ""))
    role = _current_role(fallback=data.get("role", ""))
    comments = data.get("comments", "")
    if not performed_by:
        return jsonify({"error": "performed_by is required"}), 400

    revision = urs.get("revision", "A")
    updates: dict = {}
    if action in _ACTION_STATUS_MAP:
        new_status = _ACTION_STATUS_MAP[action]
        try:
            lifecycle.validate_transition(urs["status"], new_status)
        except lifecycle.InvalidTransitionError as exc:
            return jsonify({"error": str(exc)}), 409

        if new_status != urs["status"]:
            updates["status"] = new_status
            # Rework cycle: a document leaving Draft never had a prior
            # approval to rework, so only bump revision when Draft is
            # re-entered *from* a state that had actually been approved.
            if new_status == lifecycle.DRAFT and urs["status"] in (
                lifecycle.APPROVED, lifecycle.EFFECTIVE,
            ):
                revision = lifecycle.bump_revision(revision)
                updates["revision"] = revision
            if new_status == lifecycle.EFFECTIVE and not urs.get("effective_date"):
                updates["effective_date"] = date.today().isoformat()

        if action in _REVIEW_ACTIONS:
            updates["reviewed_by"] = performed_by
        if action in _APPROVAL_ACTIONS:
            updates["approved_by"] = performed_by

    if updates:
        udb.update_urs(uid, updates)

    entry = udb.add_approval_entry(uid, action, performed_by, role, comments, revision)
    return jsonify(entry), 201


# ── Version History ───────────────────────────────────────────────────────────

@bp.route("/<int:uid>/versions", methods=["GET"])
def get_versions(uid):
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
        return jsonify({"error": "URS not found"}), 404
    return jsonify(udb.get_versions(uid))


@bp.route("/<int:uid>/versions", methods=["POST"])
def create_version(uid):
    if not tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id):
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
    """Export URS as a professional DOCX document.

    Every outcome is written to the audit trail (urs_approvals): "DOCX
    Generated" once the document bytes are built, "DOCX Downloaded" once
    the response is handed to Flask to stream back, and "DOCX Download
    Failed" (with the error) if generation or the send itself raises.
    "DOCX Downloaded" is a best-effort signal — it confirms the server
    successfully served the response, not that the browser's download
    completed, since Flask streams the body after this function returns and
    there is no client-side completion callback in this iteration.
    """
    from flask import send_file
    import io

    urs = tenancy.scoped_or_none(udb.get_urs(uid), g.tenant.company_id)
    if not urs:
        return jsonify({"error": "URS not found"}), 404

    performed_by = _current_display_name(fallback="Unknown")
    revision = urs.get("revision", "A")

    try:
        requirements = udb.get_requirements(uid)
        markdown_content = svc.build_urs_markdown(urs, requirements)
        title = urs.get("title", "URS Document")
        form_data = {
            "title": title,
            "urs_number": urs.get("urs_number", ""),
            "doc_number": urs.get("doc_number", ""),
            "revision": revision,
            "equipment_name": urs.get("equipment_name", ""),
            "department": urs.get("department", ""),
            "prepared_by": urs.get("prepared_by", ""),
            "reviewed_by": urs.get("reviewed_by", ""),
            "approved_by": urs.get("approved_by", ""),
            "effective_date": urs.get("effective_date", ""),
            "document_status": urs.get("status", lifecycle.DRAFT),
        }
        docx_bytes = markdown_to_docx(markdown_content, "URS", form_data)
    except Exception as exc:
        logger.exception("URS %s: DOCX generation failed", uid)
        udb.add_approval_entry(uid, "DOCX Download Failed", performed_by, "", str(exc), revision)
        return jsonify({"error": "Failed to generate the DOCX document"}), 500

    udb.add_approval_entry(uid, "DOCX Generated", performed_by, "", "", revision)
    safe_name = f"URS_{urs.get('urs_number', uid)}.docx".replace(" ", "_")

    try:
        response = send_file(
            io.BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=safe_name,
        )
    except Exception as exc:
        logger.exception("URS %s: DOCX send_file failed", uid)
        udb.add_approval_entry(uid, "DOCX Download Failed", performed_by, "", str(exc), revision)
        return jsonify({"error": "Failed to send the DOCX document"}), 500

    udb.add_approval_entry(uid, "DOCX Downloaded", performed_by, "", "", revision)
    return response

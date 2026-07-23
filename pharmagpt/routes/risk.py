"""
routes/risk.py — Risk Management Suite API endpoints.

All routes return JSON. SSE streaming used only for AI generation.

Routes
------
GET    /risk/dashboard                           dashboard statistics
GET    /risk/assessments                         list assessments (filterable)
POST   /risk/assessments                         create assessment
GET    /risk/assessments/<id>                    get single assessment
PUT    /risk/assessments/<id>                    update assessment fields
DELETE /risk/assessments/<id>                    delete assessment

GET    /risk/assessments/<id>/items              get risk items
POST   /risk/assessments/<id>/items              save (replace) all items

POST   /risk/assessments/<id>/generate           AI generate risk items (SSE stream)
POST   /risk/assessments/<id>/review             AI review assessment
POST   /risk/assessments/<id>/mitigate           AI suggest mitigations for one item

GET    /risk/assessments/<id>/actions            get mitigation actions
POST   /risk/assessments/<id>/actions            upsert a mitigation action

GET    /risk/assessments/<id>/approval           get approval trail
POST   /risk/assessments/<id>/approval           add approval entry
POST   /risk/assessments/<id>/publish            publish to risk library

GET    /risk/library                             get library entries
POST   /risk/library                             add library entry

GET    /risk/assessments/<id>/report             generate markdown report
POST   /risk/assessments/<id>/export/docx        export as DOCX
"""

import json
import logging
from flask import Blueprint, g, jsonify, request, Response, stream_with_context

from pharmagpt import config
from pharmagpt import risk_database as rdb
from pharmagpt import qms_database as qmsdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import qms_repo
from pharmagpt.services import lifecycle_engine
from pharmagpt.services import risk_service as svc
from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from pharmagpt.prompts.risk_prompt import get_generation_prompt
from google.genai import types

bp = Blueprint("risk", __name__, url_prefix="/risk")
logger = logging.getLogger(__name__)
RECORD_TYPE = "risk_assessment"


# ── Phase 3.5 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────
# risk_assessments has no project_id in SQLite at all (a disclosed roadmap
# limitation, Phase 7 territory — FOUNDATION_ARCHITECTURE.md §6) so
# project_id is always None here, and creation doesn't call
# qms_database.add_audit_entry (risk uses its own separate risk_approval
# table, not qms_audit_trail) so there's no audit entry to mirror.

def _dual_write_create(assessment: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        pg_row = qms_repo.create_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE,
            title=assessment["title"], status=assessment.get("status") or "open",
        )
        rdb.set_assessment_postgres_id(assessment["id"], pg_row["id"])
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync new risk assessment %s to Postgres", assessment["id"])


def _dual_write_update(assessment: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = assessment.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.update_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id,
            title=assessment["title"], status=assessment.get("status") or "open",
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync risk assessment %s update to Postgres", assessment["id"])


def _dual_write_delete(assessment: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = assessment.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.delete_record(extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id)
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to delete risk assessment %s in Postgres", assessment["id"])


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route("/dashboard")
def dashboard():
    return jsonify(rdb.get_dashboard_stats(g.tenant.company_id))


# ── Assessments ───────────────────────────────────────────────────────────────

@bp.route("/assessments", methods=["GET"])
def list_assessments():
    filters = {
        "assessment_type": request.args.get("type"),
        "methodology": request.args.get("methodology"),
        "status": request.args.get("status"),
        "priority": request.args.get("priority"),
        "department": request.args.get("department"),
        "keyword": request.args.get("q"),
    }
    return jsonify(rdb.get_all_assessments(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("/assessments", methods=["POST"])
def create_assessment():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "Assessment title is required"}), 400
    assessment = rdb.create_assessment(data, company_id=g.tenant.company_id)
    rdb.add_approval_entry(assessment["id"], "Assessment created", data.get("assessment_owner", ""), "Owner")
    _dual_write_create(assessment)
    return jsonify(assessment), 201


@bp.route("/assessments/<int:aid>", methods=["GET"])
def get_assessment(aid):
    a = tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    return jsonify(a)


@bp.route("/assessments/<int:aid>", methods=["PUT"])
def update_assessment(aid):
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    updated = rdb.update_assessment(aid, data)
    _dual_write_update(updated)
    return jsonify(updated)


@bp.route("/assessments/<int:aid>", methods=["DELETE"])
@require_role("company_admin")
def delete_assessment(aid):
    existing = tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    rdb.delete_assessment(aid)
    _dual_write_delete(existing)
    return jsonify({"deleted": True})


# ── Risk Items ────────────────────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/items", methods=["GET"])
def get_items(aid):
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(rdb.get_items(aid))


@bp.route("/assessments/<int:aid>/items", methods=["POST"])
def save_items(aid):
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    items = request.get_json() or []
    if not isinstance(items, list):
        return jsonify({"error": "Expected array of items"}), 400
    saved = rdb.save_items(aid, items)
    # Auto-update status to In Review if was Draft and has items
    a = rdb.get_assessment(aid)
    if a and a.get("status") == "Draft" and saved:
        rdb.update_assessment(aid, {"status": "In Progress"})
    return jsonify(saved)


# ── AI Generation (SSE streaming) ─────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/generate", methods=["POST"])
def generate_items(aid):
    """Stream AI-generated risk items as SSE events."""
    body = request.get_json() or {}
    a = tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    # Merge request body into assessment info
    info = {**a, **body}
    methodology = info.get("methodology", "FMEA")

    # Build library context
    category = rdb._type_to_category(info.get("assessment_type", ""))
    library_entries = rdb.get_library(g.tenant.company_id, category=category, keyword=info.get("equipment", ""))
    lib_context = _fmt_lib(library_entries[:5])

    prompt = get_generation_prompt(methodology, info, lib_context)

    def stream():
        full = ""
        try:
            for chunk in gemini_client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=PHARMA_SYSTEM_PROMPT,
                    temperature=0.4,
                ),
            ):
                if chunk.text:
                    full += chunk.text
                    yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"

            # After streaming, parse and save items
            import re
            text = re.sub(r"```(?:json)?", "", full).strip().rstrip("`")
            try:
                items = json.loads(text)
            except Exception:
                m = re.search(r'\[[\s\S]*\]', text)
                items = json.loads(m.group()) if m else []

            if isinstance(items, list) and items:
                saved = rdb.save_items(aid, items)
                yield f"data: {json.dumps({'done': True, 'count': len(saved)})}\n\n"
            else:
                yield f"data: {json.dumps({'done': True, 'count': 0, 'error': 'Could not parse items'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── AI Review ─────────────────────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/review", methods=["POST"])
def review_assessment(aid):
    """Run AI review on an assessment. Returns review data."""
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    review = svc.ai_review_assessment(aid)
    return jsonify(review)


# ── AI Mitigation Suggestions ─────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/mitigate", methods=["POST"])
def suggest_mitigations(aid):
    a = tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    item_data = request.get_json() or {}
    suggestions = svc.suggest_mitigations(item_data, a.get("methodology", "FMEA"), a)
    return jsonify(suggestions)


# ── Actions ───────────────────────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/actions", methods=["GET"])
def get_actions(aid):
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(rdb.get_actions(aid))


@bp.route("/assessments/<int:aid>/actions", methods=["POST"])
def upsert_action(aid):
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action = rdb.upsert_action(aid, data)
    return jsonify(action), 201


# ── Approval ──────────────────────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/approval", methods=["GET"])
def get_approval(aid):
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(rdb.get_approval_trail(aid))


@bp.route("/assessments/<int:aid>/approval", methods=["POST"])
@require_role("company_admin", "reviewer_qa")
def add_approval(aid):
    a = tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action_name = data.get("action", "")

    # Update assessment status based on approval action
    status_map = {
        "Submitted for Review": "In Review",
        "Reviewed": "In Review",
        "Approved": "Approved",
        "Rejected": "Draft",
        "Closed": "Closed",
    }
    if action_name in status_map:
        new_status = status_map[action_name]
        try:
            lifecycle_engine.validate_transition("RISK_ASSESSMENT", a["status"], new_status)
        except lifecycle_engine.InvalidTransitionError as exc:
            return jsonify({"error": str(exc)}), 409
        rdb.update_assessment(aid, {"status": new_status})

    # If approved, publish to library
    if action_name == "Approved":
        count = rdb.publish_assessment_to_library(aid)
        data["_library_count"] = count

    sig = tenancy.signing_identity(g.tenant)
    entry = rdb.add_approval_entry(
        aid, action_name,
        sig["performed_by"],
        sig["role"],
        data.get("comments", ""),
        sig["electronic_sig"],
    )
    qmsdb.add_audit_entry("risk_assessment", aid, action_name, sig["performed_by"])
    return jsonify(entry), 201


# ── Publish to Library ────────────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/publish", methods=["POST"])
def publish_to_library(aid):
    if not tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    count = rdb.publish_assessment_to_library(aid)
    return jsonify({"published": count})


# ── Risk Library ──────────────────────────────────────────────────────────────

@bp.route("/library", methods=["GET"])
def get_library():
    category = request.args.get("category")
    keyword = request.args.get("q")
    return jsonify(rdb.get_library(g.tenant.company_id, category=category, keyword=keyword))


@bp.route("/library", methods=["POST"])
def add_library():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    entry = rdb.add_library_entry(data, company_id=g.tenant.company_id)
    return jsonify(entry), 201


# ── Report ────────────────────────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/report", methods=["GET"])
def get_report(aid):
    a = tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    report_type = request.args.get("type", "full")
    md = svc.generate_report_markdown(aid, report_type)
    return jsonify({"markdown": md, "title": a.get("title", "")})


# ── DOCX Export ───────────────────────────────────────────────────────────────

@bp.route("/assessments/<int:aid>/export/docx", methods=["POST"])
def export_docx(aid):
    a = tenancy.scoped_or_none(rdb.get_assessment(aid), g.tenant.company_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    from pharmagpt.services.doc_exporter import markdown_to_docx
    md = svc.generate_report_markdown(aid)
    docx_bytes = markdown_to_docx(md, "RISK", {
        "title": a.get("title", ""),
        "equipment_name": a.get("equipment", ""),
        "department": a.get("department", ""),
    })
    filename = f"Risk_Assessment_{aid}_{a.get('title','').replace(' ','_')[:30]}.docx"
    from flask import send_file
    import io
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_lib(entries: list[dict]) -> str:
    lines = []
    for e in entries:
        fm = e.get("failure_mode") or e.get("hazard", "")
        if fm:
            lines.append(f"- {fm}: {e.get('failure_effect', '')} (RPN: {e.get('typical_rpn', 'N/A')})")
    return "\n".join(lines)

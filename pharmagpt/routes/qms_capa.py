"""
routes/qms_capa.py — CAPA (Corrective and Preventive Action) module API endpoints.

Attachments/comments/audit-trail/approval-trail reads are served by
routes/qms_common.py (record_type='capa'); this file owns the approval POST
because it maps each action to a CAPA status transition (Open → Root Cause
Analysis → CA Planned → PA Planned → Implementation → Effectiveness Check →
QA Review → Closed).

Routes
------
GET    /qms/capa                            list CAPAs (filterable, keyword search)
POST   /qms/capa                            create CAPA (auto capa_number)
GET    /qms/capa/<id>                       get one CAPA
PUT    /qms/capa/<id>                       update CAPA fields
DELETE /qms/capa/<id>                       delete CAPA

POST   /qms/capa/<id>/suggest-draft         AI CAPA draft (root cause + actions, not persisted)
POST   /qms/capa/<id>/suggest-effectiveness AI effectiveness-check suggestions (not persisted)
GET    /qms/capa/trend-summary              AI Quality Trend Summary across CAPAs & Deviations

GET    /qms/capa/<id>/actions               list corrective/preventive actions
POST   /qms/capa/<id>/actions               upsert an action
POST   /qms/capa/actions/<aid>/escalate     escalate an overdue action

GET    /qms/capa/<id>/effectiveness         list effectiveness checks
POST   /qms/capa/<id>/effectiveness         upsert an effectiveness check

GET    /qms/capa/<id>/deviations            linked deviations

POST   /qms/capa/<id>/approval              status transition + e-signature entry

GET    /qms/capa/<id>/report                markdown report (preview / print)
POST   /qms/capa/<id>/export/docx           DOCX export
"""

import io
import logging
import re
from flask import Blueprint, g, jsonify, request, send_file

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import qms_capa_database as cdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_database as qmsdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import qms_repo
from pharmagpt.services import qms_capa_service as svc

bp = Blueprint("qms_capa", __name__, url_prefix="/qms/capa")
logger = logging.getLogger(__name__)
RECORD_TYPE = "capa"


# ── Phase 3.5 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────

def _resolve_project_postgres_id(project_id):
    if not project_id:
        return None
    project = db.get_project(project_id)
    return (project or {}).get("postgres_id")


def _dual_write_create(capa: dict, audit_action: str, performed_by: str) -> None:
    if config.QMS_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        pg_row = qms_repo.create_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE,
            title=capa["title"], status=capa.get("status") or "open",
            project_id=_resolve_project_postgres_id(capa.get("project_id")),
        )
        cdb.set_capa_postgres_id(capa["id"], pg_row["id"])
        qms_repo.add_audit_entry(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, pg_row["id"],
            audit_action, actor_user_id=tenant.user_id,
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync new CAPA %s to Postgres", capa["id"])


def _dual_write_update(capa: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = capa.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.update_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id,
            title=capa["title"], status=capa.get("status") or "open",
            project_id=_resolve_project_postgres_id(capa.get("project_id")),
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync CAPA %s update to Postgres", capa["id"])


def _dual_write_delete(capa: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = capa.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.delete_record(extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id)
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to delete CAPA %s in Postgres", capa["id"])


# ── CAPAs ──────────────────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_capas():
    filters = {
        "capa_source": request.args.get("source"),
        "status": request.args.get("status"),
        "department": request.args.get("department"),
        "keyword": request.args.get("q"),
    }
    return jsonify(cdb.get_all_capas(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_capa():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "CAPA title is required"}), 400
    capa = cdb.create_capa(data, company_id=g.tenant.company_id)
    qmsdb.add_audit_entry("capa", capa["id"], "CAPA created", data.get("initiated_by", ""))
    _dual_write_create(capa, "CAPA created", data.get("initiated_by", ""))
    return jsonify(capa), 201


@bp.route("/trend-summary", methods=["GET"])
def trend_summary():
    return jsonify({"summary": svc.ai_trend_summary(g.tenant.company_id)})


@bp.route("/<int:cid>", methods=["GET"])
def get_capa(cid):
    c = tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id)
    if not c:
        return jsonify({"error": "Not found"}), 404
    return jsonify(c)


@bp.route("/<int:cid>", methods=["PUT"])
def update_capa(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    updated = cdb.update_capa(cid, data)
    _dual_write_update(updated)
    return jsonify(updated)


@bp.route("/<int:cid>", methods=["DELETE"])
@require_role("company_admin")
def delete_capa(cid):
    existing = tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    cdb.delete_capa(cid)
    _dual_write_delete(existing)
    return jsonify({"deleted": True})


# ── AI suggestions ──────────────────────────────────────────────────────────────

@bp.route("/<int:cid>/suggest-draft", methods=["POST"])
def suggest_draft(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_draft(cid))


@bp.route("/<int:cid>/suggest-effectiveness", methods=["POST"])
def suggest_effectiveness(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_effectiveness(cid))


# ── Actions (corrective / preventive tasks) ────────────────────────────────────

@bp.route("/<int:cid>/actions", methods=["GET"])
def get_actions(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(cdb.get_actions(cid))


@bp.route("/<int:cid>/actions", methods=["POST"])
def upsert_action(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action = cdb.upsert_action(cid, data)
    return jsonify(action), 201


@bp.route("/actions/<int:aid>/escalate", methods=["POST"])
def escalate_action(aid):
    data = request.get_json() or {}
    action = cdb.escalate_action(aid, data.get("escalated_to", ""), data.get("escalated_date", ""))
    if not action:
        return jsonify({"error": "Not found"}), 404
    return jsonify(action)


# ── Effectiveness checks ────────────────────────────────────────────────────────

@bp.route("/<int:cid>/effectiveness", methods=["GET"])
def get_effectiveness(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(cdb.get_effectiveness(cid))


@bp.route("/<int:cid>/effectiveness", methods=["POST"])
def upsert_effectiveness(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = cdb.upsert_effectiveness(cid, data)
    return jsonify(entry), 201


# ── Linked deviations ────────────────────────────────────────────────────────────

@bp.route("/<int:cid>/deviations", methods=["GET"])
def get_linked_deviations(cid):
    if not tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(ddb.get_linked_deviations(cid))


# ── Approval / status transition ──────────────────────────────────────────────

_STATUS_MAP = {
    "Root Cause Analysis Started": "Root Cause Analysis",
    "Corrective Actions Planned": "CA Planned",
    "Preventive Actions Planned": "PA Planned",
    "Implementation Started": "Implementation",
    "Effectiveness Check Started": "Effectiveness Check",
    "Submitted for QA Review": "QA Review",
    "Closed": "Closed",
    "Rejected": "Open",
}


@bp.route("/<int:cid>/approval", methods=["POST"])
@require_role("company_admin", "reviewer_qa")
def submit_approval(cid):
    capa = tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id)
    if not capa:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action_name = data.get("action", "")
    if not action_name:
        return jsonify({"error": "Action is required"}), 400

    sig = tenancy.signing_identity(g.tenant)

    updates = {}
    if action_name in _STATUS_MAP:
        updates["status"] = _STATUS_MAP[action_name]
    if action_name == "Closed":
        updates["closure_date"] = data.get("closure_date", "")
    if action_name == "Submitted for QA Review":
        updates["qa_reviewer"] = sig["performed_by"]
    if action_name == "Closed":
        updates["approver"] = sig["performed_by"]
    if updates:
        cdb.update_capa(cid, updates)

    entry = qmsdb.add_approval_entry(
        "capa", cid, action_name,
        sig["performed_by"], sig["role"],
        data.get("comments", ""), sig["electronic_sig"],
    )
    qmsdb.add_audit_entry("capa", cid, action_name, sig["performed_by"])
    return jsonify(entry), 201


# ── Report / Export ────────────────────────────────────────────────────────────

@bp.route("/<int:cid>/report", methods=["GET"])
def get_report(cid):
    capa = tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id)
    if not capa:
        return jsonify({"error": "Not found"}), 404
    md = svc.generate_report_markdown(cid)
    return jsonify({"markdown": md, "title": capa.get("title", "")})


@bp.route("/<int:cid>/export/docx", methods=["POST"])
def export_docx(cid):
    capa = tenancy.scoped_or_none(cdb.get_capa(cid), g.tenant.company_id)
    if not capa:
        return jsonify({"error": "Not found"}), 404
    from pharmagpt.services.doc_exporter import markdown_to_docx
    md = svc.generate_report_markdown(cid)
    docx_bytes = markdown_to_docx(md, "CAPA-Record", {
        "title": capa.get("title", ""),
        "department": capa.get("department", ""),
    })
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", capa.get("title", "CAPA"))[:40]
    filename = f"{capa.get('capa_number', 'CAPA')}_{safe_title}.docx"
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )

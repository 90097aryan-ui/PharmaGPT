"""
routes/qms_deviations.py — Deviation Management module API endpoints.

Attachments/comments/audit-trail/approval-trail reads are served by
routes/qms_common.py (record_type='deviation'); this file owns the approval
POST because it maps each action to a Deviation Management status transition
(Initiated → Under Investigation → Root Cause Identified → Impact Assessed →
Risk Assessed → CAPA Assigned → QA Review → Approved → Closed).

Routes
------
GET    /qms/deviations                       list deviations (filterable, keyword search)
POST   /qms/deviations                       create deviation (auto deviation_number)
GET    /qms/deviations/<id>                  get one deviation
PUT    /qms/deviations/<id>                  update deviation fields
DELETE /qms/deviations/<id>                  delete deviation

POST   /qms/deviations/<id>/investigate      AI Investigation Assistant (fishbone/5-Why/timeline/root cause)
GET    /qms/deviations/<id>/investigation    get investigation record
PUT    /qms/deviations/<id>/investigation    manually edit investigation record

POST   /qms/deviations/<id>/suggest-impact   AI-suggested impact assessment entries (not persisted)
GET    /qms/deviations/<id>/impact           list impact assessment entries
POST   /qms/deviations/<id>/impact           add impact assessment entry

POST   /qms/deviations/<id>/suggest-capa     AI-suggested CAPA seed content (not persisted)
POST   /qms/deviations/<id>/link-capa        link this deviation to an existing/new CAPA
GET    /qms/deviations/<id>/capas            list linked CAPAs

POST   /qms/deviations/<id>/approval         status transition + e-signature entry

GET    /qms/deviations/<id>/report           markdown report (preview / print)
POST   /qms/deviations/<id>/export/docx      DOCX export
"""

import io
import logging
import re
from flask import Blueprint, g, jsonify, request, send_file

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_capa_database as cdb
from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.decorators import extract_bearer_token
from pharmagpt.db import qms_repo
from pharmagpt.services import qms_deviation_service as svc

bp = Blueprint("qms_deviations", __name__, url_prefix="/qms/deviations")
logger = logging.getLogger(__name__)
RECORD_TYPE = "deviation"


# ── Phase 3.5 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────
# Same non-blocking policy as every other Phase 3 domain: active only when
# QMS_BACKEND=dual, never raises, SQLite stays the source of truth.

def _resolve_project_postgres_id(project_id):
    if not project_id:
        return None
    project = db.get_project(project_id)
    return (project or {}).get("postgres_id")


def _dual_write_create(deviation: dict, audit_action: str, performed_by: str) -> None:
    if config.QMS_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        pg_row = qms_repo.create_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE,
            title=deviation["title"], status=deviation.get("status") or "open",
            project_id=_resolve_project_postgres_id(deviation.get("project_id")),
        )
        ddb.set_deviation_postgres_id(deviation["id"], pg_row["id"])
        qms_repo.add_audit_entry(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, pg_row["id"],
            audit_action, actor_user_id=tenant.user_id,
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync new deviation %s to Postgres", deviation["id"])


def _dual_write_update(deviation: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = deviation.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.update_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id,
            title=deviation["title"], status=deviation.get("status") or "open",
            project_id=_resolve_project_postgres_id(deviation.get("project_id")),
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync deviation %s update to Postgres", deviation["id"])


def _dual_write_delete(deviation: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = deviation.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.delete_record(extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id)
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to delete deviation %s in Postgres", deviation["id"])


# ── Deviations ─────────────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_deviations():
    filters = {
        "deviation_type": request.args.get("type"),
        "deviation_category": request.args.get("category"),
        "status": request.args.get("status"),
        "department": request.args.get("department"),
        "keyword": request.args.get("q"),
    }
    return jsonify(ddb.get_all_deviations({k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_deviation():
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "Deviation title is required"}), 400
    deviation = ddb.create_deviation(data)
    qmsdb.add_audit_entry("deviation", deviation["id"], "Deviation initiated", data.get("initiated_by", ""))
    _dual_write_create(deviation, "Deviation initiated", data.get("initiated_by", ""))
    return jsonify(deviation), 201


@bp.route("/<int:did>", methods=["GET"])
def get_deviation(did):
    d = ddb.get_deviation(did)
    if not d:
        return jsonify({"error": "Not found"}), 404
    return jsonify(d)


@bp.route("/<int:did>", methods=["PUT"])
def update_deviation(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    updated = ddb.update_deviation(did, data)
    _dual_write_update(updated)
    return jsonify(updated)


@bp.route("/<int:did>", methods=["DELETE"])
def delete_deviation(did):
    existing = ddb.get_deviation(did)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    ddb.delete_deviation(did)
    _dual_write_delete(existing)
    return jsonify({"deleted": True})


# ── AI Investigation Assistant ────────────────────────────────────────────────

@bp.route("/<int:did>/investigate", methods=["POST"])
def run_investigation(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    investigation = svc.ai_run_investigation(did)
    qmsdb.add_audit_entry("deviation", did, "AI investigation run")
    return jsonify(investigation)


@bp.route("/<int:did>/investigation", methods=["GET"])
def get_investigation(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    investigation = ddb.get_investigation(did)
    return jsonify(investigation or {})


@bp.route("/<int:did>/investigation", methods=["PUT"])
def update_investigation(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    return jsonify(ddb.upsert_investigation(did, data))


# ── Impact assessment ────────────────────────────────────────────────────────

@bp.route("/<int:did>/suggest-impact", methods=["POST"])
def suggest_impact(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_impact(did))


@bp.route("/<int:did>/impact", methods=["GET"])
def get_impacts(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(ddb.get_impacts(did))


@bp.route("/<int:did>/impact", methods=["POST"])
def add_impact(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = ddb.add_impact(did, data)
    return jsonify(entry), 201


# ── CAPA suggestion & linkage ──────────────────────────────────────────────────

@bp.route("/<int:did>/suggest-capa", methods=["POST"])
def suggest_capa(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_capa(did))


@bp.route("/<int:did>/link-capa", methods=["POST"])
def link_capa(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    capa_id = data.get("capa_id")
    if not capa_id or not cdb.get_capa(capa_id):
        return jsonify({"error": "Valid capa_id is required"}), 400
    link = ddb.link_capa(did, capa_id)
    ddb.update_deviation(did, {"status": "CAPA Assigned"})
    qmsdb.add_audit_entry("deviation", did, "Linked to CAPA", detail=cdb.get_capa(capa_id).get("capa_number", ""))
    return jsonify(link), 201


@bp.route("/<int:did>/capas", methods=["GET"])
def get_linked_capas(did):
    if not ddb.get_deviation(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(ddb.get_linked_capas(did))


# ── Approval / status transition ──────────────────────────────────────────────

_STATUS_MAP = {
    "Investigation Started": "Under Investigation",
    "Root Cause Identified": "Root Cause Identified",
    "Impact Assessed": "Impact Assessed",
    "Risk Assessed": "Risk Assessed",
    "CAPA Assigned": "CAPA Assigned",
    "Submitted for QA Review": "QA Review",
    "Approved": "Approved",
    "Rejected": "Initiated",
    "Closed": "Closed",
}


@bp.route("/<int:did>/approval", methods=["POST"])
def submit_approval(did):
    deviation = ddb.get_deviation(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action_name = data.get("action", "")
    if not action_name:
        return jsonify({"error": "Action is required"}), 400

    updates = {}
    if action_name in _STATUS_MAP:
        updates["status"] = _STATUS_MAP[action_name]
    if action_name == "Closed":
        updates["closure_date"] = data.get("closure_date", "")
    if action_name == "Submitted for QA Review":
        updates["qa_reviewer"] = data.get("performed_by", deviation.get("qa_reviewer", ""))
    if action_name == "Approved":
        updates["approver"] = data.get("performed_by", deviation.get("approver", ""))
    if updates:
        ddb.update_deviation(did, updates)

    entry = qmsdb.add_approval_entry(
        "deviation", did, action_name,
        data.get("performed_by", ""), data.get("role", ""),
        data.get("comments", ""), data.get("electronic_sig", ""),
    )
    qmsdb.add_audit_entry("deviation", did, action_name, data.get("performed_by", ""))
    return jsonify(entry), 201


# ── Report / Export ────────────────────────────────────────────────────────────

@bp.route("/<int:did>/report", methods=["GET"])
def get_report(did):
    deviation = ddb.get_deviation(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    md = svc.generate_report_markdown(did)
    return jsonify({"markdown": md, "title": deviation.get("title", "")})


@bp.route("/<int:did>/export/docx", methods=["POST"])
def export_docx(did):
    deviation = ddb.get_deviation(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    from pharmagpt.services.doc_exporter import markdown_to_docx
    md = svc.generate_report_markdown(did)
    docx_bytes = markdown_to_docx(md, "Deviation-Record", {
        "title": deviation.get("title", ""),
        "department": deviation.get("department", ""),
    })
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", deviation.get("title", "Deviation"))[:40]
    filename = f"{deviation.get('deviation_number', 'DEV')}_{safe_title}.docx"
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )

"""
routes/qms_change_control.py — Change Control module API endpoints
(Quality Management Suite, Phase 2).

Attachments/comments/audit-trail/approval-trail reads are served by
routes/qms_common.py (record_type='change_control'); this file owns the
approval POST because it maps each action to a Change Control status
transition (Draft -> Submitted -> Initial Review -> Impact Assessment ->
Risk Assessment -> Department Review -> QA Review -> Approval ->
Implementation -> Verification -> Effectiveness Review -> Closed), with
rejection supported from any stage back to Draft.

Routes
------
GET    /qms/change-control                              list change controls (filterable, keyword search)
POST   /qms/change-control                               create change control (auto cc_number)
GET    /qms/change-control/<id>                          get one change control
PUT    /qms/change-control/<id>                          update change control fields
DELETE /qms/change-control/<id>                          delete change control

POST   /qms/change-control/<id>/suggest-impact           AI-suggested impact assessment entries (not persisted)
GET    /qms/change-control/<id>/impact                   list impact assessment entries
POST   /qms/change-control/<id>/impact                   add impact assessment entry

POST   /qms/change-control/<id>/suggest-implementation-plan  AI-suggested implementation plan/checklist steps (not persisted)
GET    /qms/change-control/<id>/actions                  list implementation plan steps
POST   /qms/change-control/<id>/actions                  upsert an implementation plan step

POST   /qms/change-control/<id>/risk-summary             AI Risk Summary (persisted into ai_narratives)
POST   /qms/change-control/<id>/rollback-plan            AI Rollback Plan (persisted)
POST   /qms/change-control/<id>/regulatory-impact        AI Regulatory Impact (persisted)
POST   /qms/change-control/<id>/justification            AI Change Justification (persisted)
POST   /qms/change-control/<id>/executive-summary        AI Executive Summary (persisted)
POST   /qms/change-control/<id>/verification-summary     AI Verification Summary (persisted)
POST   /qms/change-control/<id>/effectiveness-review     AI Effectiveness Review (persisted)

POST   /qms/change-control/<id>/link-deviation           link this change control to an existing deviation
POST   /qms/change-control/<id>/link-capa                link this change control to an existing CAPA
GET    /qms/change-control/<id>/deviations                list linked deviations
GET    /qms/change-control/<id>/capas                     list linked CAPAs

POST   /qms/change-control/<id>/approval                 status transition + e-signature entry

GET    /qms/change-control/<id>/report                    markdown report (preview / print)
POST   /qms/change-control/<id>/export/docx               DOCX export
"""

import io
import logging
import re
from flask import Blueprint, g, jsonify, request, send_file

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import qms_change_control_database as ccdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_capa_database as cdb
from pharmagpt import qms_database as qmsdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import qms_repo
from pharmagpt.services import qms_change_control_service as svc

bp = Blueprint("qms_change_control", __name__, url_prefix="/qms/change-control")
logger = logging.getLogger(__name__)
RECORD_TYPE = "change_control"


# ── Phase 3.5 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────

def _resolve_project_postgres_id(project_id):
    if not project_id:
        return None
    project = db.get_project(project_id)
    return (project or {}).get("postgres_id")


def _dual_write_create(cc: dict, audit_action: str, performed_by: str) -> None:
    if config.QMS_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        pg_row = qms_repo.create_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE,
            title=cc["title"], status=cc.get("status") or "open",
            project_id=_resolve_project_postgres_id(cc.get("project_id")),
        )
        ccdb.set_change_control_postgres_id(cc["id"], pg_row["id"])
        qms_repo.add_audit_entry(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, pg_row["id"],
            audit_action, actor_user_id=tenant.user_id,
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync new change control %s to Postgres", cc["id"])


def _dual_write_update(cc: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = cc.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.update_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id,
            title=cc["title"], status=cc.get("status") or "open",
            project_id=_resolve_project_postgres_id(cc.get("project_id")),
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync change control %s update to Postgres", cc["id"])


def _dual_write_delete(cc: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = cc.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.delete_record(extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id)
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to delete change control %s in Postgres", cc["id"])


# ── Change Controls ────────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_change_controls():
    filters = {
        "change_type": request.args.get("type"),
        "change_category": request.args.get("category"),
        "status": request.args.get("status"),
        "department": request.args.get("department"),
        "keyword": request.args.get("q"),
    }
    return jsonify(ccdb.get_all_change_controls(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_change_control():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "Change control title is required"}), 400
    cc = ccdb.create_change_control(data, company_id=g.tenant.company_id)
    performed_by = tenancy.signing_identity(g.tenant)["performed_by"]
    qmsdb.add_audit_entry("change_control", cc["id"], "Change control drafted", performed_by)
    _dual_write_create(cc, "Change control drafted", performed_by)
    return jsonify(cc), 201


@bp.route("/<int:cc_id>", methods=["GET"])
def get_change_control(cc_id):
    cc = tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id)
    if not cc:
        return jsonify({"error": "Not found"}), 404
    return jsonify(cc)


@bp.route("/<int:cc_id>", methods=["PUT"])
def update_change_control(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    updated = ccdb.update_change_control(cc_id, data)
    _dual_write_update(updated)
    return jsonify(updated)


@bp.route("/<int:cc_id>", methods=["DELETE"])
@require_role("company_admin")
def delete_change_control(cc_id):
    existing = tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    ccdb.delete_change_control(cc_id)
    _dual_write_delete(existing)
    return jsonify({"deleted": True})


# ── Impact assessment ──────────────────────────────────────────────────────────

@bp.route("/<int:cc_id>/suggest-impact", methods=["POST"])
def suggest_impact(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_impact(cc_id))


@bp.route("/<int:cc_id>/impact", methods=["GET"])
def get_impacts(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(ccdb.get_impacts(cc_id))


@bp.route("/<int:cc_id>/impact", methods=["POST"])
def add_impact(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = ccdb.add_impact(cc_id, data)
    return jsonify(entry), 201


# ── Implementation plan ────────────────────────────────────────────────────────

@bp.route("/<int:cc_id>/suggest-implementation-plan", methods=["POST"])
def suggest_implementation_plan(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_implementation_plan(cc_id))


@bp.route("/<int:cc_id>/actions", methods=["GET"])
def get_actions(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(ccdb.get_actions(cc_id))


@bp.route("/<int:cc_id>/actions", methods=["POST"])
def upsert_action(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action = ccdb.upsert_action(cc_id, data)
    return jsonify(action), 201


# ── AI narratives ───────────────────────────────────────────────────────────────

_NARRATIVE_ENDPOINTS = {
    "risk-summary": svc.ai_risk_summary,
    "rollback-plan": svc.ai_rollback_plan,
    "regulatory-impact": svc.ai_regulatory_impact,
    "justification": svc.ai_justification,
    "executive-summary": svc.ai_executive_summary,
    "verification-summary": svc.ai_verification_summary,
    "effectiveness-review": svc.ai_effectiveness_review,
}

for _path, _fn in _NARRATIVE_ENDPOINTS.items():
    def _make_view(fn=_fn):
        def _view(cc_id):
            if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
                return jsonify({"error": "Not found"}), 404
            text = fn(cc_id)
            return jsonify({"text": text})
        return _view
    bp.add_url_rule(f"/<int:cc_id>/{_path}", endpoint=f"narrative_{_path.replace('-', '_')}",
                     view_func=_make_view(), methods=["POST"])


# ── Deviation / CAPA linkage ────────────────────────────────────────────────────

@bp.route("/<int:cc_id>/link-deviation", methods=["POST"])
def link_deviation(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    deviation_id = data.get("deviation_id")
    deviation = deviation_id and tenancy.scoped_or_none(ddb.get_deviation(deviation_id), g.tenant.company_id)
    if not deviation:
        return jsonify({"error": "Valid deviation_id is required"}), 400
    link = ccdb.link_record(cc_id, "deviation", deviation_id)
    qmsdb.add_audit_entry("change_control", cc_id, "Linked to Deviation", detail=deviation.get("deviation_number", ""))
    return jsonify(link), 201


@bp.route("/<int:cc_id>/link-capa", methods=["POST"])
def link_capa(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    capa_id = data.get("capa_id")
    capa = capa_id and tenancy.scoped_or_none(cdb.get_capa(capa_id), g.tenant.company_id)
    if not capa:
        return jsonify({"error": "Valid capa_id is required"}), 400
    link = ccdb.link_record(cc_id, "capa", capa_id)
    qmsdb.add_audit_entry("change_control", cc_id, "Linked to CAPA", detail=capa.get("capa_number", ""))
    return jsonify(link), 201


@bp.route("/<int:cc_id>/deviations", methods=["GET"])
def get_linked_deviations(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    links = ccdb.get_linked_records(cc_id, "deviation")
    return jsonify([ddb.get_deviation(l["linked_id"]) for l in links if ddb.get_deviation(l["linked_id"])])


@bp.route("/<int:cc_id>/capas", methods=["GET"])
def get_linked_capas(cc_id):
    if not tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    links = ccdb.get_linked_records(cc_id, "capa")
    return jsonify([cdb.get_capa(l["linked_id"]) for l in links if cdb.get_capa(l["linked_id"])])


# ── Approval / status transition ──────────────────────────────────────────────

_STATUS_MAP = {
    "Submitted": "Submitted",
    "Initial Review Started": "Initial Review",
    "Impact Assessment Started": "Impact Assessment",
    "Risk Assessment Started": "Risk Assessment",
    "Sent for Department Review": "Department Review",
    "Submitted for QA Review": "QA Review",
    "Sent for Approval": "Approval",
    "Approved": "Implementation",
    "Implementation Complete": "Verification",
    "Verified": "Effectiveness Review",
    "Closed": "Closed",
    "Rejected": "Draft",
}


@bp.route("/<int:cc_id>/approval", methods=["POST"])
@require_role("company_admin", "reviewer_qa")
def submit_approval(cc_id):
    cc = tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id)
    if not cc:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    action_name = data.get("action", "")
    if not action_name:
        return jsonify({"error": "Action is required"}), 400

    sig = tenancy.signing_identity(g.tenant)

    updates = {}
    if action_name in _STATUS_MAP:
        updates["status"] = _STATUS_MAP[action_name]
    if action_name == "Submitted for QA Review":
        updates["qa_reviewer"] = sig["performed_by"]
    if action_name == "Approved":
        updates["approver"] = sig["performed_by"]
    if action_name == "Implementation Complete":
        updates["implementation_date"] = data.get("effective_date", "")
    if action_name == "Verified":
        updates["verification_date"] = data.get("effective_date", "")
    if action_name == "Closed":
        updates["closure_date"] = data.get("effective_date", "")
    if updates:
        ccdb.update_change_control(cc_id, updates)

    entry = qmsdb.add_approval_entry(
        "change_control", cc_id, action_name,
        sig["performed_by"], sig["role"],
        data.get("comments", ""), sig["electronic_sig"],
    )
    qmsdb.add_audit_entry("change_control", cc_id, action_name, sig["performed_by"])
    return jsonify(entry), 201


# ── Report / Export ────────────────────────────────────────────────────────────

@bp.route("/<int:cc_id>/report", methods=["GET"])
def get_report(cc_id):
    cc = tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id)
    if not cc:
        return jsonify({"error": "Not found"}), 404
    md = svc.generate_report_markdown(cc_id)
    return jsonify({"markdown": md, "title": cc.get("title", "")})


@bp.route("/<int:cc_id>/export/docx", methods=["POST"])
def export_docx(cc_id):
    cc = tenancy.scoped_or_none(ccdb.get_change_control(cc_id), g.tenant.company_id)
    if not cc:
        return jsonify({"error": "Not found"}), 404
    from pharmagpt.services.doc_exporter import markdown_to_docx
    md = svc.generate_report_markdown(cc_id)
    docx_bytes = markdown_to_docx(md, "Change-Control-Record", {
        "title": cc.get("title", ""),
        "department": cc.get("department", ""),
    })
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", cc.get("title", "ChangeControl"))[:40]
    filename = f"{cc.get('cc_number', 'CC')}_{safe_title}.docx"
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )

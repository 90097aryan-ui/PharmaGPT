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
import re
from flask import Blueprint, jsonify, request, send_file

from pharmagpt import qms_capa_database as cdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_database as qmsdb
from pharmagpt.services import qms_capa_service as svc

bp = Blueprint("qms_capa", __name__, url_prefix="/qms/capa")


# ── CAPAs ──────────────────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_capas():
    filters = {
        "capa_source": request.args.get("source"),
        "status": request.args.get("status"),
        "department": request.args.get("department"),
        "keyword": request.args.get("q"),
    }
    return jsonify(cdb.get_all_capas({k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_capa():
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "CAPA title is required"}), 400
    capa = cdb.create_capa(data)
    qmsdb.add_audit_entry("capa", capa["id"], "CAPA created", data.get("initiated_by", ""))
    return jsonify(capa), 201


@bp.route("/trend-summary", methods=["GET"])
def trend_summary():
    return jsonify({"summary": svc.ai_trend_summary()})


@bp.route("/<int:cid>", methods=["GET"])
def get_capa(cid):
    c = cdb.get_capa(cid)
    if not c:
        return jsonify({"error": "Not found"}), 404
    return jsonify(c)


@bp.route("/<int:cid>", methods=["PUT"])
def update_capa(cid):
    if not cdb.get_capa(cid):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    return jsonify(cdb.update_capa(cid, data))


@bp.route("/<int:cid>", methods=["DELETE"])
def delete_capa(cid):
    if not cdb.get_capa(cid):
        return jsonify({"error": "Not found"}), 404
    cdb.delete_capa(cid)
    return jsonify({"deleted": True})


# ── AI suggestions ──────────────────────────────────────────────────────────────

@bp.route("/<int:cid>/suggest-draft", methods=["POST"])
def suggest_draft(cid):
    if not cdb.get_capa(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_draft(cid))


@bp.route("/<int:cid>/suggest-effectiveness", methods=["POST"])
def suggest_effectiveness(cid):
    if not cdb.get_capa(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_effectiveness(cid))


# ── Actions (corrective / preventive tasks) ────────────────────────────────────

@bp.route("/<int:cid>/actions", methods=["GET"])
def get_actions(cid):
    if not cdb.get_capa(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(cdb.get_actions(cid))


@bp.route("/<int:cid>/actions", methods=["POST"])
def upsert_action(cid):
    if not cdb.get_capa(cid):
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
    if not cdb.get_capa(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(cdb.get_effectiveness(cid))


@bp.route("/<int:cid>/effectiveness", methods=["POST"])
def upsert_effectiveness(cid):
    if not cdb.get_capa(cid):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = cdb.upsert_effectiveness(cid, data)
    return jsonify(entry), 201


# ── Linked deviations ────────────────────────────────────────────────────────────

@bp.route("/<int:cid>/deviations", methods=["GET"])
def get_linked_deviations(cid):
    if not cdb.get_capa(cid):
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
def submit_approval(cid):
    capa = cdb.get_capa(cid)
    if not capa:
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
        updates["qa_reviewer"] = data.get("performed_by", capa.get("qa_reviewer", ""))
    if action_name == "Closed":
        updates["approver"] = data.get("performed_by", capa.get("approver", ""))
    if updates:
        cdb.update_capa(cid, updates)

    entry = qmsdb.add_approval_entry(
        "capa", cid, action_name,
        data.get("performed_by", ""), data.get("role", ""),
        data.get("comments", ""), data.get("electronic_sig", ""),
    )
    qmsdb.add_audit_entry("capa", cid, action_name, data.get("performed_by", ""))
    return jsonify(entry), 201


# ── Report / Export ────────────────────────────────────────────────────────────

@bp.route("/<int:cid>/report", methods=["GET"])
def get_report(cid):
    capa = cdb.get_capa(cid)
    if not capa:
        return jsonify({"error": "Not found"}), 404
    md = svc.generate_report_markdown(cid)
    return jsonify({"markdown": md, "title": capa.get("title", "")})


@bp.route("/<int:cid>/export/docx", methods=["POST"])
def export_docx(cid):
    capa = cdb.get_capa(cid)
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

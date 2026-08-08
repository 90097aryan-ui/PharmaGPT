"""
routes/qms_feature_requests.py — Feature Requests module API endpoints.

v1 is CRUD only (no workflow, no approvals, no dual-write) — see
qms_feature_request_database.py. Attachments/comments/audit-trail reads are
served by routes/qms_common.py (record_type='feature_request').

Routes
------
GET    /qms/feature-requests            list feature requests (filterable, keyword search)
POST   /qms/feature-requests            create feature request (auto fr_number)
GET    /qms/feature-requests/<id>       get one feature request
PUT    /qms/feature-requests/<id>       update feature request fields
DELETE /qms/feature-requests/<id>       delete feature request
"""

from flask import Blueprint, g, jsonify, request

from pharmagpt import audit
from pharmagpt import qms_feature_request_database as frdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import require_role

bp = Blueprint("qms_feature_requests", __name__, url_prefix="/qms/feature-requests")
RECORD_TYPE = "feature_request"


@bp.route("", methods=["GET"])
def list_feature_requests():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    filters = {
        "status": request.args.get("status"),
        "priority": request.args.get("priority"),
        "module": request.args.get("module"),
        "keyword": request.args.get("q"),
    }
    return jsonify(frdb.get_all_feature_requests(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_feature_request():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "Title is required"}), 400
    if not data.get("description", "").strip():
        return jsonify({"error": "Description is required"}), 400
    created_by = g.tenant.display_name or g.tenant.email
    fr = frdb.create_feature_request(data, company_id=g.tenant.company_id, created_by=created_by)
    audit.log(RECORD_TYPE, fr["id"], "Feature request created", new=fr)
    return jsonify(fr), 201


@bp.route("/<int:fr_id>", methods=["GET"])
def get_feature_request(fr_id):
    fr = tenancy.scoped_or_none(frdb.get_feature_request(fr_id), g.tenant.company_id)
    if not fr:
        return jsonify({"error": "Not found"}), 404
    return jsonify(fr)


@bp.route("/<int:fr_id>", methods=["PUT"])
def update_feature_request(fr_id):
    existing = tenancy.scoped_or_none(frdb.get_feature_request(fr_id), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    if "title" in data and not data["title"].strip():
        return jsonify({"error": "Title is required"}), 400
    if "description" in data and not data["description"].strip():
        return jsonify({"error": "Description is required"}), 400
    updated = frdb.update_feature_request(fr_id, data)
    audit.log(RECORD_TYPE, fr_id, "Feature request updated", old=existing, new=updated)
    return jsonify(updated)


@bp.route("/<int:fr_id>", methods=["DELETE"])
@require_role("company_admin")
def delete_feature_request(fr_id):
    existing = tenancy.scoped_or_none(frdb.get_feature_request(fr_id), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    frdb.delete_feature_request(fr_id)
    audit.log(RECORD_TYPE, fr_id, "Feature request deleted", old=existing)
    return jsonify({"deleted": True})

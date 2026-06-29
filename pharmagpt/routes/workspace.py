"""
routes/workspace.py — Validation Workspace projects and audit trail (v0.8).

Routes
------
GET    /val-projects                          list all validation projects
POST   /val-projects                          create a validation project
GET    /val-projects/<id>                     get single project
PUT    /val-projects/<id>                     update project fields
DELETE /val-projects/<id>                     delete project + audit trail
GET    /val-projects/<id>/audit-trail         get full audit trail
POST   /val-projects/<id>/audit-trail         append a manual audit entry
"""

from pharmagpt import database as db
from flask import Blueprint, jsonify, request

bp = Blueprint("workspace", __name__)


@bp.route("/val-projects", methods=["GET"])
def list_val_projects():
    """Return all validation workspace projects, newest first."""
    return jsonify(db.get_all_val_projects())


@bp.route("/val-projects", methods=["POST"])
def create_val_project():
    """
    Create a new validation project.
    Body: { name, equipment_name, equipment_id, department, manufacturer,
            model, location, validation_type, protocol_number, report_number,
            owner, approver, target_date, risk_category }
    """
    data = request.get_json() or {}
    if not data.get("name", "").strip():
        return jsonify({"error": "Project name is required"}), 400

    project = db.create_val_project(data)
    db.add_val_audit_entry(project["id"], "Project created")
    return jsonify(project), 201


@bp.route("/val-projects/<int:vp_id>", methods=["GET"])
def get_val_project(vp_id):
    """Return a single validation project by ID."""
    project = db.get_val_project(vp_id)
    if not project:
        return jsonify({"error": "Not found"}), 404
    return jsonify(project)


@bp.route("/val-projects/<int:vp_id>", methods=["PUT"])
def update_val_project(vp_id):
    """Update a validation project's mutable fields."""
    if not db.get_val_project(vp_id):
        return jsonify({"error": "Not found"}), 404
    data    = request.get_json() or {}
    updated = db.update_val_project(vp_id, data)
    db.add_val_audit_entry(vp_id, "Project details updated")
    return jsonify(updated)


@bp.route("/val-projects/<int:vp_id>", methods=["DELETE"])
def delete_val_project(vp_id):
    """Delete a validation project; the audit trail is removed by CASCADE."""
    if not db.get_val_project(vp_id):
        return jsonify({"error": "Not found"}), 404
    db.delete_val_project(vp_id)
    return jsonify({"status": "deleted"})


@bp.route("/val-projects/<int:vp_id>/audit-trail", methods=["GET"])
def get_val_audit_trail(vp_id):
    """Return the full audit trail for a validation project, oldest first."""
    if not db.get_val_project(vp_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(db.get_val_audit_trail(vp_id))


@bp.route("/val-projects/<int:vp_id>/audit-trail", methods=["POST"])
def add_val_audit_entry(vp_id):
    """
    Append a manual audit entry to a validation project.
    Body: { "action": "...", "user_note": "..." }
    """
    if not db.get_val_project(vp_id):
        return jsonify({"error": "Not found"}), 404
    data  = request.get_json() or {}
    entry = db.add_val_audit_entry(
        vp_id,
        data.get("action", "Manual entry"),
        data.get("user_note", ""),
    )
    return jsonify(entry), 201

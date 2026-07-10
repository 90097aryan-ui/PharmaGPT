"""
routes/projects.py — Project management and conversation history.

Routes
------
GET  /projects                       list all projects
POST /projects                       create a project
GET  /projects/<id>                  get single project
PUT  /projects/<id>                  update project fields (incl. former Validation
                                      Workspace fields — owner/approver/target_date/
                                      risk_category/status/model/location/
                                      protocol_number/report_number — merged in by
                                      Phase 2 Module 1; replaces the retired
                                      PUT /val-projects/<id>)
DELETE /projects/<id>                delete project + cascade
GET  /projects/<id>/messages         load chat history for replay
POST /clear                          clear chat history for a project
"""

from pharmagpt import database as db
from pharmagpt import qms_database as qmsdb
from flask import Blueprint, jsonify, request
from pharmagpt.state import history_cache

bp = Blueprint("projects", __name__)


@bp.route("/projects", methods=["GET"])
def list_projects():
    """Return all projects as a JSON array, newest first."""
    return jsonify(db.get_all_projects())


@bp.route("/projects", methods=["POST"])
def create_project():
    """
    Create a new project.
    Body: { name, equipment_name, manufacturer, department, validation_type,
            owner?, approver?, target_date?, risk_category?, status?, model?,
            location?, protocol_number?, report_number? }
    Returns the new project dict with its auto-assigned id.
    """
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    project = db.create_project(
        name=name,
        equipment_name=data.get("equipment_name", "").strip(),
        manufacturer=data.get("manufacturer", "").strip(),
        department=data.get("department", "").strip(),
        validation_type=data.get("validation_type", "").strip(),
        owner=data.get("owner", "").strip(),
        approver=data.get("approver", "").strip(),
        target_date=data.get("target_date") or None,
        risk_category=data.get("risk_category", "").strip(),
        status=data.get("status", "In Progress").strip() or "In Progress",
        model=data.get("model", "").strip(),
        location=data.get("location", "").strip(),
        protocol_number=data.get("protocol_number", "").strip(),
        report_number=data.get("report_number", "").strip(),
    )
    qmsdb.add_audit_entry("project", project["id"], "Project created")
    return jsonify(project), 201


@bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id):
    """Return a single project by ID."""
    project = db.get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@bp.route("/projects/<int:project_id>", methods=["PUT"])
def update_project(project_id):
    """Update a project's mutable fields (see module docstring for the field list)."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    data    = request.get_json() or {}
    updated = db.update_project(project_id, data)
    qmsdb.add_audit_entry("project", project_id, "Project details updated")
    return jsonify(updated)


@bp.route("/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    """Delete a project and cascade to its messages, documents, and generated docs."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    qmsdb.add_audit_entry("project", project_id, "Project deleted")
    db.delete_project(project_id)
    history_cache.pop(project_id, None)
    return jsonify({"status": "deleted"})


@bp.route("/projects/<int:project_id>/messages", methods=["GET"])
def project_messages(project_id):
    """Return all saved messages for a project so the UI can replay them on load."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(db.get_project_messages(project_id))


@bp.route("/clear", methods=["POST"])
def clear_conversation():
    """Clear all messages for the given project (DB and in-memory cache)."""
    data       = request.get_json() or {}
    project_id = data.get("project_id")
    if project_id:
        db.clear_project_messages(project_id)
        history_cache.pop(project_id, None)
    return jsonify({"status": "cleared"})

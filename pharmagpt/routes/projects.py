"""
routes/projects.py — Project management and conversation history.

Routes
------
GET  /projects                       list all projects
POST /projects                       create a project
GET  /projects/<id>                  get single project
DELETE /projects/<id>                delete project + cascade
GET  /projects/<id>/messages         load chat history for replay
POST /clear                          clear chat history for a project
"""

import database as db
from flask import Blueprint, jsonify, request
from state import history_cache

bp = Blueprint("projects", __name__)


@bp.route("/projects", methods=["GET"])
def list_projects():
    """Return all projects as a JSON array, newest first."""
    return jsonify(db.get_all_projects())


@bp.route("/projects", methods=["POST"])
def create_project():
    """
    Create a new project.
    Body: { name, equipment_name, manufacturer, department, validation_type }
    Returns the new project dict with its auto-assigned id.
    """
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    project = db.create_project(
        name=name,
        equipment_name=data.get("equipment_name", "").strip(),
        manufacturer=data.get("manufacturer", "").strip(),
        department=data.get("department", "").strip(),
        validation_type=data.get("validation_type", "").strip(),
    )
    return jsonify(project), 201


@bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id):
    """Return a single project by ID."""
    project = db.get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@bp.route("/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    """Delete a project and cascade to its messages, documents, and generated docs."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
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

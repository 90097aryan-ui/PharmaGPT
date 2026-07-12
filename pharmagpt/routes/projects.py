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

import logging

from flask import Blueprint, g, jsonify, request

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.decorators import extract_bearer_token
from pharmagpt.db import projects_repo
from pharmagpt.state import history_cache

bp = Blueprint("projects", __name__)
logger = logging.getLogger(__name__)


# ── Phase 3.2 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────
# Active only when PROJECTS_BACKEND=dual. SQLite remains the source of truth
# and the response the caller sees; a Postgres failure here is logged and
# swallowed, never raised — it must never turn a successful SQLite write into
# a failed request.

def _dual_write_create(project: dict) -> None:
    if config.PROJECTS_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return  # Super Admin has no company — nothing to dual-write against
    try:
        pg_row = projects_repo.create_project(
            extract_bearer_token(), tenant.company_id,
            name=project["name"], status=project.get("status") or "active",
            target_date=project.get("target_date"),
            risk_category=project.get("risk_category") or "",
            protocol_number=project.get("protocol_number") or "",
            report_number=project.get("report_number") or "",
        )
        db.set_project_postgres_id(project["id"], pg_row["id"])
    except Exception:
        logger.exception("Phase 3.2 dual-write: failed to sync new project %s to Postgres", project["id"])


def _dual_write_update(project: dict) -> None:
    if config.PROJECTS_BACKEND != "dual":
        return
    postgres_id = project.get("postgres_id")
    if not postgres_id:
        return  # never dual-written on create (e.g. flag was off then) — skip
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        projects_repo.update_project(
            extract_bearer_token(), tenant.company_id, postgres_id,
            name=project["name"], status=project.get("status") or "active",
            target_date=project.get("target_date"),
            risk_category=project.get("risk_category") or "",
            protocol_number=project.get("protocol_number") or "",
            report_number=project.get("report_number") or "",
        )
    except Exception:
        logger.exception("Phase 3.2 dual-write: failed to sync project %s update to Postgres", project["id"])


def _dual_write_delete(project: dict) -> None:
    if config.PROJECTS_BACKEND != "dual":
        return
    postgres_id = project.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        projects_repo.delete_project(extract_bearer_token(), tenant.company_id, postgres_id)
    except Exception:
        logger.exception("Phase 3.2 dual-write: failed to sync project %s delete to Postgres", project["id"])


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
    _dual_write_create(project)
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
    _dual_write_update(updated)
    return jsonify(updated)


@bp.route("/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    """Delete a project and cascade to its messages, documents, and generated docs."""
    existing = db.get_project(project_id)
    if not existing:
        return jsonify({"error": "Project not found"}), 404
    qmsdb.add_audit_entry("project", project_id, "Project deleted")
    db.delete_project(project_id)
    _dual_write_delete(existing)
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

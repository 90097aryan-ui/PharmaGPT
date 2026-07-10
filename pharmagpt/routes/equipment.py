"""
routes/equipment.py — Equipment CRUD, search, document links (PharmaGPT v1.0 Module 2).

Routes
------
GET    /projects/<id>/equipment              list Equipment records for a project
POST   /projects/<id>/equipment              create an Equipment record
POST   /projects/<id>/equipment/import-legacy  create one from the project's legacy
                                              equipment_name/manufacturer/model fields
GET    /equipment/search?q=&project_id=      search equipment (optionally project-scoped)
GET    /equipment/types                      equipment-type catalog (autocomplete)
GET    /equipment/<id>                       get one Equipment record
PUT    /equipment/<id>                       update
DELETE /equipment/<id>                       delete (cascades to document links)
GET    /equipment/<id>/documents             list linked documents
POST   /equipment/<id>/documents             link a document (kb or project)
DELETE /equipment/<id>/documents/<link_id>   unlink a document
GET    /equipment/<id>/ai-context            assembled AI-context bundle (architecture only)
"""

from flask import Blueprint, jsonify, request

from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb
from pharmagpt.services import equipment_service

bp = Blueprint("equipment", __name__)


# ── Project-scoped list / create ──────────────────────────────────────────────

@bp.route("/projects/<int:project_id>/equipment", methods=["GET"])
def list_project_equipment(project_id):
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(equipdb.get_project_equipment(project_id))


@bp.route("/projects/<int:project_id>/equipment", methods=["POST"])
def create_equipment(project_id):
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json() or {}
    if not (data.get("name") or "").strip():
        return jsonify({"error": "Equipment name is required"}), 400

    equipment = equipdb.create_equipment(project_id, data)
    return jsonify(equipment), 201


@bp.route("/projects/<int:project_id>/equipment/import-legacy", methods=["POST"])
def import_legacy_equipment(project_id):
    """Create an Equipment record pre-filled from this project's legacy
    equipment_name/manufacturer/model/equipment_id free-text fields."""
    if not db.get_project(project_id):
        return jsonify({"error": "Project not found"}), 404

    equipment = equipdb.import_legacy_equipment(project_id)
    if not equipment:
        return jsonify({"error": "Project has no legacy equipment information to import"}), 400
    return jsonify(equipment), 201


# ── Search / catalog ──────────────────────────────────────────────────────────

@bp.route("/equipment/search", methods=["GET"])
def search_equipment():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    project_id = request.args.get("project_id", type=int)
    return jsonify(equipdb.search_equipment(query, project_id))


@bp.route("/equipment/types", methods=["GET"])
def equipment_types():
    """Canonical equipment-type names for autocomplete (from the static
    Equipment Intelligence Engine registry)."""
    return jsonify(equipment_service.get_equipment_type_catalog())


# ── Single-record CRUD ────────────────────────────────────────────────────────

@bp.route("/equipment/<int:equipment_id>", methods=["GET"])
def get_equipment(equipment_id):
    equipment = equipdb.get_equipment(equipment_id)
    if not equipment:
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify(equipment)


@bp.route("/equipment/<int:equipment_id>", methods=["PUT"])
def update_equipment(equipment_id):
    if not equipdb.get_equipment(equipment_id):
        return jsonify({"error": "Equipment not found"}), 404
    data = request.get_json() or {}
    if "name" in data and not (data.get("name") or "").strip():
        return jsonify({"error": "Equipment name cannot be empty"}), 400
    updated = equipdb.update_equipment(equipment_id, data)
    return jsonify(updated)


@bp.route("/equipment/<int:equipment_id>", methods=["DELETE"])
def delete_equipment(equipment_id):
    if not equipdb.get_equipment(equipment_id):
        return jsonify({"error": "Equipment not found"}), 404
    equipdb.delete_equipment(equipment_id)
    return jsonify({"status": "deleted"})


# ── Document links ────────────────────────────────────────────────────────────

@bp.route("/equipment/<int:equipment_id>/documents", methods=["GET"])
def list_equipment_documents(equipment_id):
    if not equipdb.get_equipment(equipment_id):
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify(equipdb.list_equipment_documents(equipment_id))


@bp.route("/equipment/<int:equipment_id>/documents", methods=["POST"])
def link_equipment_document(equipment_id):
    if not equipdb.get_equipment(equipment_id):
        return jsonify({"error": "Equipment not found"}), 404

    data = request.get_json() or {}
    document_role = data.get("document_role", "")
    source_type = data.get("source_type", "")
    source_id = data.get("source_id")

    if document_role not in equipdb.DOCUMENT_ROLES:
        return jsonify({"error": f"Invalid document_role. Must be one of: {', '.join(equipdb.DOCUMENT_ROLES)}"}), 400
    if source_type not in equipdb.SOURCE_TYPES:
        return jsonify({"error": "source_type must be 'kb' or 'project'"}), 400
    if not source_id:
        return jsonify({"error": "source_id is required"}), 400

    # Verify the referenced document actually exists before linking.
    source_doc = db.get_kb_document(source_id) if source_type == "kb" else db.get_document(source_id)
    if not source_doc:
        return jsonify({"error": "Referenced document not found"}), 404

    title_snapshot = source_doc.get("title") or source_doc.get("original_name") or ""
    link = equipdb.link_equipment_document(equipment_id, document_role, source_type, source_id, title_snapshot)
    return jsonify(link), 201


@bp.route("/equipment/<int:equipment_id>/documents/<int:link_id>", methods=["DELETE"])
def unlink_equipment_document(equipment_id, link_id):
    if not equipdb.get_equipment(equipment_id):
        return jsonify({"error": "Equipment not found"}), 404
    equipdb.unlink_equipment_document(link_id)
    return jsonify({"status": "unlinked"})


# ── AI context (architecture only — not yet wired into generation) ───────────

@bp.route("/equipment/<int:equipment_id>/ai-context", methods=["GET"])
def equipment_ai_context(equipment_id):
    bundle = equipment_service.get_equipment_context_bundle(equipment_id)
    if not bundle:
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify(bundle)

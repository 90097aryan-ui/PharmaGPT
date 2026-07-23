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
GET    /equipment/<id>/documents             list linked documents/QMS records
POST   /equipment/<id>/documents             link a document (kb/project) or QMS record
                                              (deviation/capa/change_control/risk_assessment —
                                              Phase 3 traceability, equipment_documents widened)
DELETE /equipment/<id>/documents/<link_id>   unlink a document/QMS record
GET    /equipment/<id>/ai-context            assembled AI-context bundle (architecture only)
"""

import logging

from flask import Blueprint, g, jsonify, request

from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb
from pharmagpt import qms_deviation_database as qdevdb
from pharmagpt import qms_capa_database as qcapadb
from pharmagpt import qms_change_control_database as qccdb
from pharmagpt import risk_database as riskdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import equipment_repo
from pharmagpt.services import equipment_service

bp = Blueprint("equipment", __name__)
logger = logging.getLogger(__name__)

# Phase 3 (Enterprise Validation Platform): tenant-scoped getters for the four
# QMS record source_types equipment_documents was widened to accept
# (equipment_database.py::SOURCE_TYPES) — mirrors routes/qms_common.py's
# _GETTERS dispatch pattern, used here for the two-sided tenant check below
# (both the equipment row AND the linked record must belong to the caller's
# company).
_QMS_SOURCE_GETTERS = {
    "deviation": qdevdb.get_deviation,
    "capa": qcapadb.get_capa,
    "change_control": qccdb.get_change_control,
    "risk_assessment": riskdb.get_assessment,
}


# ── Phase 3.4 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────
# Same non-blocking policy as routes/projects.py and routes/knowledge_base.py:
# active only when EQUIPMENT_BACKEND=dual, never raises, SQLite stays the
# source of truth and the response the caller sees.

def _dual_write_create(equipment: dict) -> None:
    if config.EQUIPMENT_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        pg_row = equipment_repo.create_equipment(extract_bearer_token(), tenant.company_id, equipment)
        equipdb.set_equipment_postgres_id(equipment["id"], pg_row["id"])
    except Exception:
        logger.exception("Phase 3.4 dual-write: failed to sync new equipment %s to Postgres", equipment["id"])


def _dual_write_update(equipment: dict) -> None:
    if config.EQUIPMENT_BACKEND != "dual":
        return
    postgres_id = equipment.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        equipment_repo.update_equipment(extract_bearer_token(), tenant.company_id, postgres_id, equipment)
    except Exception:
        logger.exception("Phase 3.4 dual-write: failed to sync equipment %s update to Postgres", equipment["id"])


def _dual_write_delete(equipment: dict) -> None:
    if config.EQUIPMENT_BACKEND != "dual":
        return
    postgres_id = equipment.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        equipment_repo.delete_equipment(extract_bearer_token(), tenant.company_id, postgres_id)
    except Exception:
        logger.exception(
            "Phase 3.4 dual-write: failed to delete equipment %s in Postgres "
            "(expected if equipment_links still reference it — Postgres RESTRICTs)",
            equipment["id"],
        )


def _dual_write_link(equipment_id: int, link: dict) -> None:
    if config.EQUIPMENT_BACKEND != "dual":
        return
    if link.get("source_type") != "kb":
        return  # project-sourced links have no Postgres document yet — see config.py
    tenant = g.tenant
    if not tenant.company_id:
        return
    equipment = equipdb.get_equipment(equipment_id)
    kb_doc = db.get_kb_document(link["source_id"])
    equipment_postgres_id = (equipment or {}).get("postgres_id")
    kb_postgres_id = (kb_doc or {}).get("postgres_id")
    if not equipment_postgres_id or not kb_postgres_id:
        return  # one or both sides not dual-written yet — nothing to link to
    try:
        pg_link = equipment_repo.link_kb_document(
            extract_bearer_token(), tenant.company_id, equipment_postgres_id, kb_postgres_id
        )
        equipdb.set_equipment_document_postgres_id(link["id"], pg_link["id"])
    except Exception:
        logger.exception("Phase 3.4 dual-write: failed to sync equipment link %s to Postgres", link["id"])


def _dual_write_unlink(link: dict) -> None:
    if config.EQUIPMENT_BACKEND != "dual":
        return
    postgres_id = link.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        equipment_repo.unlink(extract_bearer_token(), tenant.company_id, postgres_id)
    except Exception:
        logger.exception("Phase 3.4 dual-write: failed to unlink equipment link %s in Postgres", link["id"])


# ── Company-wide list (Phase 2: Equipment Library, first-class top-level
#    module) ──────────────────────────────────────────────────────────────────

@bp.route("/equipment", methods=["GET"])
def list_company_equipment():
    """Every Equipment record across every Project in the caller's company —
    the Equipment Library's list view. Equipment itself is still
    project-owned at the schema level (re-parenting to a company-owned,
    many-to-many model is Blueprint ADR-P01/PA-013, Phase 3 — out of scope
    here); this route only elevates the *navigation* entry point, reusing
    the existing tenant-scoped get_all_equipment() Phase 3.4 already relies
    on for its cross-project backfill/parity view."""
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    return jsonify(equipdb.get_all_equipment(g.tenant.company_id))


# ── Project-scoped list / create ──────────────────────────────────────────────

@bp.route("/projects/<int:project_id>/equipment", methods=["GET"])
def list_project_equipment(project_id):
    if not tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(equipdb.get_project_equipment(project_id))


@bp.route("/projects/<int:project_id>/equipment", methods=["POST"])
def create_equipment(project_id):
    if not tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id):
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json() or {}
    if not (data.get("name") or "").strip():
        return jsonify({"error": "Equipment name is required"}), 400

    equipment = equipdb.create_equipment(project_id, data)
    _dual_write_create(equipment)
    return jsonify(equipment), 201


@bp.route("/projects/<int:project_id>/equipment/import-legacy", methods=["POST"])
def import_legacy_equipment(project_id):
    """Create an Equipment record pre-filled from this project's legacy
    equipment_name/manufacturer/model/equipment_id free-text fields."""
    if not tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id):
        return jsonify({"error": "Project not found"}), 404

    equipment = equipdb.import_legacy_equipment(project_id)
    if not equipment:
        return jsonify({"error": "Project has no legacy equipment information to import"}), 400
    _dual_write_create(equipment)
    return jsonify(equipment), 201


# ── Search / catalog ──────────────────────────────────────────────────────────

@bp.route("/equipment/search", methods=["GET"])
def search_equipment():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    project_id = request.args.get("project_id", type=int)
    return jsonify(equipdb.search_equipment(query, g.tenant.company_id, project_id))


@bp.route("/equipment/types", methods=["GET"])
def equipment_types():
    """Canonical equipment-type names for autocomplete (from the static
    Equipment Intelligence Engine registry)."""
    return jsonify(equipment_service.get_equipment_type_catalog())


# ── Single-record CRUD ────────────────────────────────────────────────────────

@bp.route("/equipment/<int:equipment_id>", methods=["GET"])
def get_equipment(equipment_id):
    equipment = equipdb.get_equipment_scoped(equipment_id, g.tenant.company_id)
    if not equipment:
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify(equipment)


@bp.route("/equipment/<int:equipment_id>", methods=["PUT"])
def update_equipment(equipment_id):
    if not equipdb.get_equipment_scoped(equipment_id, g.tenant.company_id):
        return jsonify({"error": "Equipment not found"}), 404
    data = request.get_json() or {}
    if "name" in data and not (data.get("name") or "").strip():
        return jsonify({"error": "Equipment name cannot be empty"}), 400
    updated = equipdb.update_equipment(equipment_id, data)
    _dual_write_update(updated)
    return jsonify(updated)


@bp.route("/equipment/<int:equipment_id>", methods=["DELETE"])
@require_role("company_admin")
def delete_equipment(equipment_id):
    existing = equipdb.get_equipment_scoped(equipment_id, g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Equipment not found"}), 404
    equipdb.delete_equipment(equipment_id)
    _dual_write_delete(existing)
    return jsonify({"status": "deleted"})


# ── Document links ────────────────────────────────────────────────────────────

@bp.route("/equipment/<int:equipment_id>/documents", methods=["GET"])
def list_equipment_documents(equipment_id):
    if not equipdb.get_equipment_scoped(equipment_id, g.tenant.company_id):
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify(equipdb.list_equipment_documents(equipment_id))


@bp.route("/equipment/<int:equipment_id>/documents", methods=["POST"])
def link_equipment_document(equipment_id):
    if not equipdb.get_equipment_scoped(equipment_id, g.tenant.company_id):
        return jsonify({"error": "Equipment not found"}), 404

    data = request.get_json() or {}
    document_role = data.get("document_role", "")
    source_type = data.get("source_type", "")
    source_id = data.get("source_id")

    if document_role not in equipdb.DOCUMENT_ROLES:
        return jsonify({"error": f"Invalid document_role. Must be one of: {', '.join(equipdb.DOCUMENT_ROLES)}"}), 400
    if source_type not in equipdb.SOURCE_TYPES:
        return jsonify({"error": f"source_type must be one of: {', '.join(equipdb.SOURCE_TYPES)}"}), 400
    if not source_id:
        return jsonify({"error": "source_id is required"}), 400

    # Verify the referenced record actually exists AND belongs to this
    # tenant before linking — otherwise a caller could link another
    # company's document or QMS record into their own equipment record.
    # Two-sided check: the equipment row was already tenant-scoped above,
    # this scopes the *linked* record too.
    if source_type == "kb":
        source_doc = tenancy.scoped_or_none(db.get_kb_document(source_id), g.tenant.company_id)
    elif source_type == "project":
        doc = db.get_document(source_id)
        owning_project = tenancy.scoped_or_none(db.get_project(doc["project_id"]), g.tenant.company_id) if doc else None
        source_doc = doc if owning_project else None
    else:  # deviation | capa | change_control | risk_assessment — Phase 3
        getter = _QMS_SOURCE_GETTERS[source_type]
        source_doc = tenancy.scoped_or_none(getter(source_id), g.tenant.company_id)
    if not source_doc:
        return jsonify({"error": "Referenced record not found"}), 404

    title_snapshot = source_doc.get("title") or source_doc.get("original_name") or ""
    link = equipdb.link_equipment_document(equipment_id, document_role, source_type, source_id, title_snapshot)
    _dual_write_link(equipment_id, link)
    return jsonify(link), 201


@bp.route("/equipment/<int:equipment_id>/documents/<int:link_id>", methods=["DELETE"])
@require_role("company_admin")
def unlink_equipment_document(equipment_id, link_id):
    if not equipdb.get_equipment_scoped(equipment_id, g.tenant.company_id):
        return jsonify({"error": "Equipment not found"}), 404
    existing_link = equipdb.get_equipment_document_link(link_id)
    equipdb.unlink_equipment_document(link_id)
    if existing_link:
        _dual_write_unlink(existing_link)
    return jsonify({"status": "unlinked"})


# ── AI context (architecture only — not yet wired into generation) ───────────

@bp.route("/equipment/<int:equipment_id>/ai-context", methods=["GET"])
def equipment_ai_context(equipment_id):
    if not equipdb.get_equipment_scoped(equipment_id, g.tenant.company_id):
        return jsonify({"error": "Equipment not found"}), 404
    bundle = equipment_service.get_equipment_context_bundle(equipment_id)
    if not bundle:
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify(bundle)

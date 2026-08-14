"""
routes/facility.py — Facility CRUD, Building/Floor/Area/Room hierarchy, and
Facility Systems registry (Greenfield Facility URS, Stage 1).

Mirrors routes/equipment.py's structure (Facility is a Project sub-entity,
scoped the same way Equipment is) but without the Postgres dual-write layer
— Stage 1 is SQLite-only, matching the rest of the URS Management Suite.

Routes
------
GET    /projects/<id>/facility               list Facility records for a project
POST   /projects/<id>/facility               create a Facility record

GET    /facility/<id>                        get one Facility record
PUT    /facility/<id>                        update
DELETE /facility/<id>                        delete (cascades to its node tree)

GET    /facility/<id>/nodes                  flat node list (building/floor/area/room)
GET    /facility/<id>/nodes/tree             nested tree (for the layout UI)
POST   /facility/<id>/nodes                  create a node
PUT    /facility/nodes/<node_id>             update a node
DELETE /facility/nodes/<node_id>             delete a node (cascades to descendants)

GET    /facility/types                       facility-type dropdown values
GET    /facility/classifications             facility-classification dropdown values (Stage 1.1)
GET    /facility/systems                     facility systems registry, grouped by category
GET    /facility/systems/<name>              single facility system profile
GET    /facility/design-basis-options        Stage 1.1 dropdown value sets (product category,
                                              regulatory package, utility philosophy, validation
                                              strategy, requirement source, capacity units)
"""

from flask import Blueprint, g, jsonify, request

from pharmagpt import audit
from pharmagpt import database as db
from pharmagpt import facility_database as facdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import require_role
from pharmagpt.facility_database import FACILITY_CLASSIFICATIONS
from pharmagpt.facility_systems import (
    get_facility_system_profile,
    list_facility_systems_by_category,
)
from pharmagpt.services.facility_requirement_library import (
    list_facility_types,
    PRODUCT_CATEGORIES,
    REGULATORY_PACKAGE_OPTIONS,
    UTILITY_PHILOSOPHY_OPTIONS,
    UTILITY_SYSTEMS_FOR_PHILOSOPHY,
    VALIDATION_STRATEGY_OPTIONS,
    REQUIREMENT_SOURCE_OPTIONS,
    CAPACITY_UNIT_OPTIONS,
)

bp = Blueprint("facility", __name__)


@bp.before_request
def _require_workspace_access():
    from pharmagpt.auth.workspace_access import require_workspace_access
    return require_workspace_access("validation")


# ── Project-scoped list / create ──────────────────────────────────────────────

@bp.route("/projects/<int:project_id>/facility", methods=["GET"])
def list_project_facilities(project_id):
    if not tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id):
        return jsonify({"error": "Project not found"}), 404
    return jsonify(facdb.get_project_facilities(project_id))


@bp.route("/projects/<int:project_id>/facility", methods=["POST"])
def create_facility(project_id):
    if not tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id):
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json() or {}
    if not (data.get("facility_name") or "").strip():
        return jsonify({"error": "Facility name is required"}), 400
    # Stage 1.1: Facility Classification is mandatory in the wizard (client-
    # side) and always has a value on the stored record (facility_database.
    # create_facility defaults to DEFAULT_CLASSIFICATION when omitted) — but
    # is NOT hard-rejected here if absent, so a caller that predates Stage
    # 1.1 (including Stage 1's own test suite) keeps working unmodified.
    # Only a caller that supplies an out-of-set value is rejected — that was
    # never valid input to begin with, so this isn't a compatibility break.
    if (data.get("classification") or "").strip() and data["classification"].strip() not in FACILITY_CLASSIFICATIONS:
        return jsonify({"error": f"classification must be one of: {', '.join(FACILITY_CLASSIFICATIONS)}"}), 400

    tenant = g.tenant
    created_by = tenant.display_name or tenant.email or ""
    facility = facdb.create_facility(project_id, data, created_by=created_by)
    audit.log("facility", facility["id"], "Created", new=facility)
    return jsonify(facility), 201


# ── Single-record CRUD ────────────────────────────────────────────────────────

@bp.route("/facility/<int:facility_id>", methods=["GET"])
def get_facility(facility_id):
    facility = facdb.get_facility_scoped(facility_id, g.tenant.company_id)
    if not facility:
        return jsonify({"error": "Facility not found"}), 404
    return jsonify(facility)


@bp.route("/facility/<int:facility_id>", methods=["PUT"])
def update_facility(facility_id):
    existing = facdb.get_facility_scoped(facility_id, g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Facility not found"}), 404
    data = request.get_json() or {}
    if "facility_name" in data and not (data.get("facility_name") or "").strip():
        return jsonify({"error": "Facility name cannot be empty"}), 400
    updated = facdb.update_facility(facility_id, data)
    audit.log("facility", facility_id, "Updated", old=existing, new=updated)
    return jsonify(updated)


@bp.route("/facility/<int:facility_id>", methods=["DELETE"])
@require_role("company_admin")
def delete_facility(facility_id):
    existing = facdb.get_facility_scoped(facility_id, g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Facility not found"}), 404
    facdb.delete_facility(facility_id)
    audit.log("facility", facility_id, "Deleted", old=existing)
    return jsonify({"deleted": True})


# ── Building / Floor / Area / Room node tree ──────────────────────────────────

@bp.route("/facility/<int:facility_id>/nodes", methods=["GET"])
def list_nodes(facility_id):
    if not facdb.get_facility_scoped(facility_id, g.tenant.company_id):
        return jsonify({"error": "Facility not found"}), 404
    return jsonify(facdb.get_facility_nodes(facility_id))


@bp.route("/facility/<int:facility_id>/nodes/tree", methods=["GET"])
def node_tree(facility_id):
    if not facdb.get_facility_scoped(facility_id, g.tenant.company_id):
        return jsonify({"error": "Facility not found"}), 404
    return jsonify(facdb.build_node_tree(facility_id))


@bp.route("/facility/<int:facility_id>/nodes", methods=["POST"])
def create_node(facility_id):
    if not facdb.get_facility_scoped(facility_id, g.tenant.company_id):
        return jsonify({"error": "Facility not found"}), 404
    data = request.get_json() or {}

    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent = facdb.get_node(parent_id)
        if not parent or parent.get("facility_id") != facility_id:
            return jsonify({"error": "parent_id does not belong to this facility"}), 400

    try:
        node = facdb.create_node(facility_id, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    audit.log("facility_node", node["id"], "Created", new=node)
    return jsonify(node), 201


@bp.route("/facility/nodes/<int:node_id>", methods=["PUT"])
def update_node(node_id):
    existing = facdb.get_node(node_id)
    if not existing or not facdb.get_facility_scoped(existing["facility_id"], g.tenant.company_id):
        return jsonify({"error": "Node not found"}), 404
    data = request.get_json() or {}
    updated = facdb.update_node(node_id, data)
    audit.log("facility_node", node_id, "Updated", old=existing, new=updated)
    return jsonify(updated)


@bp.route("/facility/nodes/<int:node_id>", methods=["DELETE"])
def delete_node(node_id):
    existing = facdb.get_node(node_id)
    if not existing or not facdb.get_facility_scoped(existing["facility_id"], g.tenant.company_id):
        return jsonify({"error": "Node not found"}), 404
    facdb.delete_node(node_id)
    audit.log("facility_node", node_id, "Deleted", old=existing)
    return jsonify({"deleted": True})


# ── Facility types / Facility Systems registry (reference data) ──────────────

@bp.route("/facility/types", methods=["GET"])
def facility_types():
    return jsonify({"types": list_facility_types()})


@bp.route("/facility/classifications", methods=["GET"])
def facility_classifications():
    return jsonify({"classifications": list(FACILITY_CLASSIFICATIONS)})


@bp.route("/facility/design-basis-options", methods=["GET"])
def facility_design_basis_options():
    """Stage 1.1 — every dropdown/checklist value set the wizard's Step 1
    (Classification, Product Category, Regulatory Package) and Step 2 Design
    Basis panel (Utility Philosophy, Validation Strategy, Requirement
    Source, capacity units) needs, from one call."""
    return jsonify({
        "classifications": list(FACILITY_CLASSIFICATIONS),
        "product_categories": PRODUCT_CATEGORIES,
        "regulatory_package": REGULATORY_PACKAGE_OPTIONS,
        "utility_systems": UTILITY_SYSTEMS_FOR_PHILOSOPHY,
        "utility_philosophy": UTILITY_PHILOSOPHY_OPTIONS,
        "validation_strategy": VALIDATION_STRATEGY_OPTIONS,
        "requirement_source": REQUIREMENT_SOURCE_OPTIONS,
        "capacity_units": CAPACITY_UNIT_OPTIONS,
    })


@bp.route("/facility/systems", methods=["GET"])
def facility_systems():
    return jsonify({"categories": list_facility_systems_by_category()})


@bp.route("/facility/systems/<string:name>", methods=["GET"])
def facility_system_detail(name):
    profile = get_facility_system_profile(name)
    if not profile:
        return jsonify({"error": "Facility system not found"}), 404
    return jsonify({
        "name": profile.name,
        "category": profile.category,
        "description": profile.description,
        "applicable_regulations": profile.applicable_regulations,
        "design_considerations": profile.design_considerations,
        "critical_parameters": profile.critical_parameters,
        "typical_interfaces": profile.typical_interfaces,
        "common_risks": profile.common_risks,
    })

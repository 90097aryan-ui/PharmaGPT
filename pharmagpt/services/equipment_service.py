"""
services/equipment_service.py — Equipment support services (PharmaGPT v1.0 Module 2).

Two responsibilities, both deliberately architecture-only per Module 2 scope
(no advanced AI logic implemented here — see module docstrings below):

1. get_equipment_context_bundle() — assembles everything a future AI document-
   generation call *would* need to retrieve automatically before asking the
   user any questions (Equipment Details, Equipment Manual, Vendor Documents,
   SOP, Drawings, Previous Qualification Documents), per the Module 2 AI
   Integration requirement. This is a straightforward data-assembly function,
   not a retrieval-ranking or embedding pipeline — the same "ship the seam,
   wire it up later" precedent as the vector-RAG stubs in document_search.py
   (see PROJECT_MEMORY/DECISIONS.md DEC-008). It is NOT yet called from
   services/doc_generator.py or any prompt-building path; wiring it into
   actual document generation is a follow-up module, not this one.

2. get_equipment_type_catalog() — exposes the canonical equipment-type names
   from the static pharmagpt/equipment/ Intelligence Engine registry, so the
   Equipment form's "Equipment Type" field can offer autocomplete against
   catalog entries (HPLC, GC, Autoclave, ...) without coupling the two
   systems any further than a plain string match.
"""

from __future__ import annotations

from pharmagpt import equipment_database as equipdb
from pharmagpt import database as db
from pharmagpt.equipment import EQUIPMENT_REGISTRY, get_equipment_profile


def get_equipment_type_catalog() -> list[str]:
    """Canonical equipment-type names from the static Equipment Intelligence
    Engine registry (pharmagpt/equipment/), sorted for stable UI display."""
    return sorted(EQUIPMENT_REGISTRY.keys())


def get_equipment_context_bundle(equipment_id: int) -> dict | None:
    """
    Assemble the full context a future AI document-generation feature should
    retrieve automatically for this Equipment, before asking the user any
    questions:

      - equipment        : the Equipment record itself
      - intelligence_profile : matching static EquipmentProfile, if the
                            equipment_type string matches a catalog entry
                            (IQ/OQ/PQ checklists, applicable regulations, etc.)
      - documents         : linked manuals/SOPs/drawings grouped by role
                            (resolved against Knowledge Base / Project
                            Documents — never duplicated, see
                            equipment_database.py)
      - validation_history : validation documents previously generated for
                            this Equipment's project (approximate — the
                            existing Validation wizard's generated_documents
                            table is project-scoped, not yet equipment-scoped;
                            precise per-equipment linkage is a follow-up once
                            the wizard is updated to accept an equipment_id)

    Returns None if the equipment record does not exist. This function
    performs no Gemini calls and does not truncate/rank content — that
    "advanced AI logic" is explicitly out of scope for Module 2.
    """
    equipment = equipdb.get_equipment(equipment_id)
    if not equipment:
        return None

    profile = get_equipment_profile(equipment.get("equipment_type", ""))

    documents_by_role: dict[str, list[dict]] = {}
    for link in equipdb.list_equipment_documents(equipment_id):
        documents_by_role.setdefault(link["document_role"], []).append(link)

    validation_history = db.get_project_generated_documents(equipment["project_id"])

    return {
        "equipment": equipment,
        "intelligence_profile": {
            "matched": profile is not None,
            "name": profile.name if profile else None,
            "applicable_regulations": profile.applicable_regulations if profile else [],
        },
        "documents": documents_by_role,
        "validation_history": validation_history,
    }

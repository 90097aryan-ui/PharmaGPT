"""
tests/test_project_equipment_link.py — Regression coverage for Phase 2's
"every Validation Project is linked to Equipment" requirement
(PHASE_2_IMPLEMENTATION_REPORT.md; routes/projects.py::create_project).

Project creation already collects equipment_name/manufacturer/model/
department as free-text fields; this reuses the existing
equipment_database.import_legacy_equipment() one-click-import logic
automatically at creation time instead of requiring a manual follow-up
click, so a real Equipment record always exists wherever the project
supplied equipment info.
"""

from pharmagpt import equipment_database as equipdb
from pharmagpt import qms_database as qmsdb


def test_project_with_equipment_info_gets_a_real_equipment_record(client):
    project = client.post("/projects", json={
        "name": "HPLC Qualification Project", "equipment_name": "HPLC System",
        "manufacturer": "Agilent", "department": "QC", "validation_type": "IQ/OQ/PQ",
    }).get_json()

    equipment = equipdb.get_project_equipment(project["id"])
    assert len(equipment) == 1
    assert equipment[0]["name"] == "HPLC System"
    assert equipment[0]["manufacturer"] == "Agilent"


def test_project_without_equipment_info_creates_no_equipment_record(client):
    """No-op, exactly like the manual import-legacy endpoint: nothing to
    import means nothing is created, not an empty placeholder row."""
    project = client.post("/projects", json={"name": "Process-only Project"}).get_json()

    assert equipdb.get_project_equipment(project["id"]) == []


def test_project_creation_audit_entry_attributes_the_authenticated_user(client):
    """Companion fix found during the Phase 2 RBAC/audit-trail pass: the
    audit entry previously recorded performed_by="" (blank), not the
    authenticated creator — a non-repudiation gap for the same reason as
    Phase 1's QMS creation-time e-sig fix."""
    project = client.post("/projects", json={"name": "Audit Attribution Project"}).get_json()

    audit = qmsdb.get_audit_trail("project", project["id"])
    creation_entries = [a for a in audit if a["action"] == "Project created"]
    assert creation_entries
    assert all(a["performed_by"] == "Test User" for a in creation_entries)
    assert not any(a["performed_by"] == "" for a in creation_entries)

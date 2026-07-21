"""
tests/test_equipment_database.py — PharmaGPT v1.0 Module 2: Equipment entity.

Covers the equipment_database.py CRUD layer directly (schema creation, create/
get/list/update/delete, search, legacy-import consolidation, and the
equipment_documents polymorphic link table).
"""

from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb


def _make_project(**overrides):
    defaults = dict(
        name="HPLC IQ", equipment_name="Agilent HPLC 1260", manufacturer="Agilent",
        department="QC", validation_type="IQ/OQ/PQ",
    )
    defaults.update(overrides)
    return db.create_project(**defaults, company_id="test-company-1")


def test_create_and_get_equipment(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {
        "name": "HPLC System 1", "equipment_code": "EQ-1001", "category": "Analytical",
        "equipment_type": "HPLC", "manufacturer": "Agilent", "vendor": "Agilent India",
        "serial_number": "SN12345", "criticality": "Critical", "gmp_impact": "Direct",
        "installation_date": "2025-01-10",
    })
    assert equipment["id"] is not None
    assert equipment["project_id"] == project["id"]
    assert equipment["name"] == "HPLC System 1"
    assert equipment["equipment_code"] == "EQ-1001"
    assert equipment["installation_date"] == "2025-01-10"

    fetched = equipdb.get_equipment(equipment["id"])
    assert fetched["serial_number"] == "SN12345"
    assert fetched["criticality"] == "Critical"


def test_get_equipment_missing_returns_none(db_path):
    assert equipdb.get_equipment(999999) is None


def test_project_equipment_list_scoped_per_project(db_path):
    p1 = _make_project(name="Project 1")
    p2 = _make_project(name="Project 2")
    equipdb.create_equipment(p1["id"], {"name": "Equipment A"})
    equipdb.create_equipment(p1["id"], {"name": "Equipment B"})
    equipdb.create_equipment(p2["id"], {"name": "Equipment C"})

    p1_equipment = equipdb.get_project_equipment(p1["id"])
    assert len(p1_equipment) == 2
    assert {e["name"] for e in p1_equipment} == {"Equipment A", "Equipment B"}

    p2_equipment = equipdb.get_project_equipment(p2["id"])
    assert len(p2_equipment) == 1
    assert p2_equipment[0]["name"] == "Equipment C"


def test_update_equipment(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "Autoclave"})

    updated = equipdb.update_equipment(equipment["id"], {
        "name": "Autoclave", "qualification_status": "Qualified",
        "validation_status": "Validated", "criticality": "Major",
        "commissioning_date": "2026-02-01",
    })
    assert updated["qualification_status"] == "Qualified"
    assert updated["validation_status"] == "Validated"
    assert updated["commissioning_date"] == "2026-02-01"


def test_update_equipment_missing_returns_none(db_path):
    assert equipdb.update_equipment(999999, {"name": "X"}) is None


def test_delete_equipment_cascades_document_links(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "Tablet Press"})
    equipdb.link_equipment_document(equipment["id"], "sop", "kb", 1, "Some SOP")

    equipdb.delete_equipment(equipment["id"])

    assert equipdb.get_equipment(equipment["id"]) is None
    conn = db.get_connection()
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM equipment_documents WHERE equipment_id = ?", (equipment["id"],)
    ).fetchone()["n"]
    conn.close()
    assert remaining == 0


def test_search_equipment(db_path):
    project = _make_project()
    equipdb.create_equipment(project["id"], {"name": "HPLC System 1", "manufacturer": "Agilent"})
    equipdb.create_equipment(project["id"], {"name": "Autoclave", "manufacturer": "Getinge"})

    results = equipdb.search_equipment("Agilent", "test-company-1")
    assert len(results) == 1
    assert results[0]["name"] == "HPLC System 1"

    results_scoped = equipdb.search_equipment("Agilent", "test-company-1", project_id=project["id"])
    assert len(results_scoped) == 1

    other_project = _make_project(name="Other")
    results_wrong_scope = equipdb.search_equipment("Agilent", "test-company-1", project_id=other_project["id"])
    assert len(results_wrong_scope) == 0


def test_import_legacy_equipment_creates_prefilled_record(db_path):
    project = _make_project(
        name="Legacy Project", equipment_name="Shimadzu GC-2010",
        manufacturer="Shimadzu", department="QC", validation_type="OQ",
    )
    equipment = equipdb.import_legacy_equipment(project["id"])
    assert equipment is not None
    assert equipment["name"] == "Shimadzu GC-2010"
    assert equipment["manufacturer"] == "Shimadzu"
    assert equipment["department"] == "QC"


def test_import_legacy_equipment_no_legacy_data_returns_none(db_path):
    project = db.create_project(
        name="Blank Project", equipment_name="", manufacturer="", department="", validation_type="",
    company_id="test-company-1")
    assert equipdb.import_legacy_equipment(project["id"]) is None


def test_import_legacy_equipment_missing_project_returns_none(db_path):
    assert equipdb.import_legacy_equipment(999999) is None


def test_link_and_list_equipment_documents(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC"})

    kb_doc = db.create_kb_document(
        title="HPLC User Manual", folder="Vendor Documents", tags="hplc,manual",
        doc_version="1.0", effective_date=None, review_date=None,
        original_name="manual.pdf", stored_filename="manual.pdf",
        file_type="pdf", file_size=1024,
    company_id="test-company-1")
    link = equipdb.link_equipment_document(equipment["id"], "user_manual", "kb", kb_doc["id"], "HPLC User Manual")
    assert link["document_role"] == "user_manual"

    links = equipdb.list_equipment_documents(equipment["id"])
    assert len(links) == 1
    assert links[0]["resolved"] is True
    assert links[0]["display_title"] == "HPLC User Manual"


def test_list_equipment_documents_unresolved_falls_back_to_snapshot(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC"})
    equipdb.link_equipment_document(equipment["id"], "sop", "kb", 999999, "Deleted SOP")

    links = equipdb.list_equipment_documents(equipment["id"])
    assert links[0]["resolved"] is False
    assert links[0]["display_title"] == "Deleted SOP"


def test_unlink_equipment_document(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC"})
    link = equipdb.link_equipment_document(equipment["id"], "sop", "project", 1, "Some SOP")

    equipdb.unlink_equipment_document(link["id"])
    assert equipdb.list_equipment_documents(equipment["id"]) == []


def test_link_equipment_document_rejects_invalid_role(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC"})
    try:
        equipdb.link_equipment_document(equipment["id"], "not_a_role", "kb", 1)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_link_equipment_document_rejects_invalid_source_type(db_path):
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC"})
    try:
        equipdb.link_equipment_document(equipment["id"], "sop", "not_a_source", 1)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_equipment_project_cascade_delete(db_path):
    """Deleting a Project must cascade-delete its Equipment records too."""
    project = _make_project()
    equipment = equipdb.create_equipment(project["id"], {"name": "Autoclave"})

    db.delete_project(project["id"])

    assert equipdb.get_equipment(equipment["id"]) is None

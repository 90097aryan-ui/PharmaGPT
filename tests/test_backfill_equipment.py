"""
tests/test_backfill_equipment.py — scripts/backfill_equipment.py, fully
mocked against the Supabase client and a throwaway SQLite database.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb
from scripts.backfill_equipment import backfill_equipment, backfill_equipment_links


def _project(db_path):
    return db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ")


def test_backfill_equipment_migrates_and_records_postgres_id(db_path):
    project = _project(db_path)
    equipdb.create_equipment(project["id"], {"name": "HPLC System 1", "manufacturer": "Agilent"})
    equipdb.create_equipment(project["id"], {"name": "GC System 1", "manufacturer": "Waters"})

    responses = iter([
        SimpleNamespace(data=[{"id": "pg-equip-a"}]),
        SimpleNamespace(data=[{"id": "pg-equip-b"}]),
    ])
    q = MagicMock()
    q.insert.return_value = q
    q.execute.side_effect = lambda: next(responses)
    client = MagicMock()
    client.table.return_value = q

    summary = backfill_equipment(client, "company-1")

    assert summary == {"migrated": 2, "skipped_already_migrated": 0}
    postgres_ids = {e["postgres_id"] for e in equipdb.get_all_equipment()}
    assert postgres_ids == {"pg-equip-a", "pg-equip-b"}


def test_backfill_equipment_skips_already_migrated(db_path):
    project = _project(db_path)
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC System 1"})
    equipdb.set_equipment_postgres_id(equipment["id"], "already-there")

    client = MagicMock()

    summary = backfill_equipment(client, "company-1")

    assert summary == {"migrated": 0, "skipped_already_migrated": 1}
    client.table.assert_not_called()


def test_backfill_equipment_links_skips_project_sourced(db_path):
    project = _project(db_path)
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC System 1"})
    equipdb.set_equipment_postgres_id(equipment["id"], "pg-equip-1")

    doc = db.save_document(project["id"], "manual.pdf", "stored.pdf", "pdf", 100)
    equipdb.link_equipment_document(equipment["id"], "user_manual", "project", doc["id"], "manual.pdf")

    client = MagicMock()

    summary = backfill_equipment_links(client, "company-1")

    assert summary == {"migrated": 0, "skipped_already_migrated": 0, "skipped_no_target": 1}
    client.table.assert_not_called()


def test_backfill_equipment_links_skips_unmigrated_kb_document(db_path):
    project = _project(db_path)
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC System 1"})
    equipdb.set_equipment_postgres_id(equipment["id"], "pg-equip-1")

    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    )
    equipdb.link_equipment_document(equipment["id"], "sop", "kb", kb_doc["id"], "SOP-1")

    client = MagicMock()

    summary = backfill_equipment_links(client, "company-1")

    assert summary == {"migrated": 0, "skipped_already_migrated": 0, "skipped_no_target": 1}
    client.table.assert_not_called()


def test_backfill_equipment_links_migrates_kb_sourced_when_ready(db_path):
    project = _project(db_path)
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC System 1"})
    equipdb.set_equipment_postgres_id(equipment["id"], "pg-equip-1")

    kb_doc = db.create_kb_document(
        title="SOP-1", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name="sop1.pdf",
        stored_filename="stored1.pdf", file_type="pdf", file_size=1024,
    )
    db.set_kb_document_postgres_id(kb_doc["id"], "pg-kb-doc-1")
    link = equipdb.link_equipment_document(equipment["id"], "sop", "kb", kb_doc["id"], "SOP-1")

    client = MagicMock()
    q = MagicMock()
    q.insert.return_value = q
    q.execute.return_value = SimpleNamespace(data=[{"id": "pg-link-1"}])
    client.table.return_value = q

    summary = backfill_equipment_links(client, "company-1")

    assert summary == {"migrated": 1, "skipped_already_migrated": 0, "skipped_no_target": 0}
    assert equipdb.get_equipment_document_link(link["id"])["postgres_id"] == "pg-link-1"

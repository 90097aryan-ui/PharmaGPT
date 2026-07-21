"""
tests/test_check_equipment_parity.py — scripts/check_equipment_parity.py,
fully mocked against the Supabase client and a throwaway SQLite database.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb
from scripts.check_equipment_parity import check_equipment_parity


def _query_mock(execute_return):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.maybe_single.return_value = q
    q.execute.return_value = execute_return
    return q


def _project():
    return db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ", company_id="test-company-1")


def test_check_parity_skips_equipment_never_migrated(db_path):
    project = _project()
    equipdb.create_equipment(project["id"], {"name": "HPLC System 1"})
    client = MagicMock()

    drifted = check_equipment_parity(client)

    assert drifted == []
    client.table.assert_not_called()


def test_check_parity_flags_missing_in_postgres(db_path):
    project = _project()
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC System 1"})
    equipdb.set_equipment_postgres_id(equipment["id"], "pg-equip-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=None))

    drifted = check_equipment_parity(client)

    assert len(drifted) == 1
    assert drifted[0]["issue"] == "missing_in_postgres"


def test_check_parity_passes_when_fields_match(db_path):
    project = _project()
    equipment = equipdb.create_equipment(project["id"], {
        "name": "HPLC System 1", "manufacturer": "Agilent", "gmp_impact": "Direct",
    })
    equipdb.set_equipment_postgres_id(equipment["id"], "pg-equip-1")

    pg_row = {f: (equipment.get(f) or None) for f in (
        "equipment_code", "name", "category", "equipment_type", "tag_number",
        "model", "manufacturer", "vendor", "serial_number", "asset_number",
        "plant", "block", "department", "area", "room", "line",
        "installation_date", "commissioning_date",
        "qualification_status", "validation_status", "qualification_type",
        "criticality", "gmp_impact", "notes",
    )}

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=pg_row))

    drifted = check_equipment_parity(client)

    assert drifted == []


def test_check_parity_flags_field_drift(db_path):
    project = _project()
    equipment = equipdb.create_equipment(project["id"], {"name": "HPLC System 1"})
    equipdb.set_equipment_postgres_id(equipment["id"], "pg-equip-1")

    pg_row = {f: None for f in (
        "equipment_code", "name", "category", "equipment_type", "tag_number",
        "model", "manufacturer", "vendor", "serial_number", "asset_number",
        "plant", "block", "department", "area", "room", "line",
        "installation_date", "commissioning_date",
        "qualification_status", "validation_status", "qualification_type",
        "criticality", "gmp_impact", "notes",
    )}
    pg_row["name"] = "Different Name In Postgres"

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=pg_row))

    drifted = check_equipment_parity(client)

    assert len(drifted) == 1
    assert "name" in drifted[0]["diffs"]

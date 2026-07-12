"""
tests/test_check_projects_parity.py — scripts/check_projects_parity.py,
fully mocked against the Supabase client and a throwaway SQLite database.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pharmagpt import database as db
from scripts.check_projects_parity import (
    REQUIRED_ENV_VARS,
    ParityCheckError,
    check_projects_parity,
    load_config,
)


def test_load_config_missing_vars_raises():
    with pytest.raises(ParityCheckError, match="SUPABASE_URL"):
        load_config({})


def test_load_config_all_present():
    env = {name: "x" for name in REQUIRED_ENV_VARS}
    assert load_config(env) == env


def _query_mock(execute_return):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.maybe_single.return_value = q
    q.execute.return_value = execute_return
    return q


def test_check_parity_skips_projects_never_migrated(db_path):
    db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ")
    client = MagicMock()

    drifted = check_projects_parity(client)

    assert drifted == []
    client.table.assert_not_called()


def test_check_parity_flags_missing_in_postgres(db_path):
    project = db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ")
    db.set_project_postgres_id(project["id"], "pg-a")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=None))

    drifted = check_projects_parity(client)

    assert len(drifted) == 1
    assert drifted[0]["issue"] == "missing_in_postgres"
    assert drifted[0]["postgres_id"] == "pg-a"


def test_check_parity_passes_when_fields_match(db_path):
    project = db.create_project(
        "Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ",
        status="Approved", risk_category="High",
        protocol_number="PROT-1", report_number="REP-1",
    )
    db.set_project_postgres_id(project["id"], "pg-a")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "name": "Proj A", "status": "Approved", "target_date": None,
        "risk_category": "High", "protocol_number": "PROT-1",
        "report_number": "REP-1",
    }))

    drifted = check_projects_parity(client)

    assert drifted == []


def test_check_parity_flags_name_drift(db_path):
    project = db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ")
    db.set_project_postgres_id(project["id"], "pg-a")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "name": "Proj A (renamed in Postgres only)", "status": "In Progress",
        "target_date": None, "risk_category": None,
        "protocol_number": None, "report_number": None,
    }))

    drifted = check_projects_parity(client)

    assert len(drifted) == 1
    assert "name" in drifted[0]["diffs"]


def test_check_parity_treats_none_and_empty_string_as_equal(db_path):
    project = db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ")
    db.set_project_postgres_id(project["id"], "pg-a")

    client = MagicMock()
    # SQLite stores risk_category="" by default; Postgres stores NULL.
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "name": "Proj A", "status": "In Progress", "target_date": None,
        "risk_category": None, "protocol_number": None, "report_number": None,
    }))

    drifted = check_projects_parity(client)

    assert drifted == []

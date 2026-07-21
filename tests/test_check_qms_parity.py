"""
tests/test_check_qms_parity.py — scripts/check_qms_parity.py, fully mocked
against the Supabase client and a throwaway SQLite database.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pharmagpt import qms_deviation_database as ddb
from scripts.check_qms_parity import check_record_type_parity


def _query_mock(execute_return):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.maybe_single.return_value = q
    q.execute.return_value = execute_return
    return q


def test_check_parity_skips_never_migrated(db_path):
    ddb.create_deviation({"title": "Dev 1"}, company_id="test-company-1")
    client = MagicMock()

    drifted = check_record_type_parity(client, "deviation", ddb.get_all_deviations())

    assert drifted == []
    client.table.assert_not_called()


def test_check_parity_flags_missing_in_postgres(db_path):
    deviation = ddb.create_deviation({"title": "Dev 1"}, company_id="test-company-1")
    ddb.set_deviation_postgres_id(deviation["id"], "pg-dev-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=None))

    drifted = check_record_type_parity(client, "deviation", ddb.get_all_deviations())

    assert len(drifted) == 1
    assert drifted[0]["issue"] == "missing_in_postgres"


def test_check_parity_passes_when_fields_match(db_path):
    deviation = ddb.create_deviation({"title": "Dev 1", "status": "Initiated"}, company_id="test-company-1")
    ddb.set_deviation_postgres_id(deviation["id"], "pg-dev-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "title": "Dev 1", "status": "Initiated", "project_id": None,
    }))

    drifted = check_record_type_parity(client, "deviation", ddb.get_all_deviations())

    assert drifted == []


def test_check_parity_flags_status_drift(db_path):
    deviation = ddb.create_deviation({"title": "Dev 1", "status": "Initiated"}, company_id="test-company-1")
    ddb.set_deviation_postgres_id(deviation["id"], "pg-dev-1")

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={
        "title": "Dev 1", "status": "Closed", "project_id": None,
    }))

    drifted = check_record_type_parity(client, "deviation", ddb.get_all_deviations())

    assert len(drifted) == 1
    assert "status" in drifted[0]["diffs"]

"""
tests/test_backfill_qms.py — scripts/backfill_qms.py, fully mocked against
the Supabase client and a throwaway SQLite database.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pharmagpt import database as db
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import risk_database as rdb
from scripts.backfill_qms import backfill_record_type


def test_backfill_record_type_migrates_deviation_with_resolved_project(db_path):
    project = db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ", company_id="test-company-1")
    db.set_project_postgres_id(project["id"], "pg-project-1")
    deviation = ddb.create_deviation({"title": "Dev 1", "project_id": project["id"]}, company_id="test-company-1")

    client = MagicMock()
    q = MagicMock()
    q.insert.return_value = q
    q.execute.return_value = SimpleNamespace(data=[{"id": "pg-dev-1"}])
    client.table.return_value = q

    summary = backfill_record_type(
        client, "company-1", "deviation", ddb.get_all_deviations(), ddb.set_deviation_postgres_id
    )

    assert summary == {"migrated": 1, "skipped_already_migrated": 0}
    assert ddb.get_deviation(deviation["id"])["postgres_id"] == "pg-dev-1"
    payload = q.insert.call_args[0][0]
    assert payload["project_id"] == "pg-project-1"
    assert payload["title"] == "Dev 1"


def test_backfill_record_type_skips_already_migrated(db_path):
    deviation = ddb.create_deviation({"title": "Dev 1"}, company_id="test-company-1")
    ddb.set_deviation_postgres_id(deviation["id"], "already-there")

    client = MagicMock()

    summary = backfill_record_type(
        client, "company-1", "deviation", ddb.get_all_deviations(), ddb.set_deviation_postgres_id
    )

    assert summary == {"migrated": 0, "skipped_already_migrated": 1}
    client.table.assert_not_called()


def test_backfill_record_type_risk_assessment_has_no_project_id(db_path):
    assessment = rdb.create_assessment({"title": "Risk 1"}, company_id="test-company-1")

    client = MagicMock()
    q = MagicMock()
    q.insert.return_value = q
    q.execute.return_value = SimpleNamespace(data=[{"id": "pg-risk-1"}])
    client.table.return_value = q

    backfill_record_type(
        client, "company-1", "risk_assessment", rdb.get_all_assessments(), rdb.set_assessment_postgres_id
    )

    payload = q.insert.call_args[0][0]
    assert payload["project_id"] is None
    assert rdb.get_assessment(assessment["id"])["postgres_id"] == "pg-risk-1"

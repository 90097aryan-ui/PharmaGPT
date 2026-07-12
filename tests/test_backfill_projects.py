"""
tests/test_backfill_projects.py — scripts/backfill_projects.py, fully
mocked against the Supabase client and a throwaway SQLite database (no
live Supabase project needed to run these tests).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pharmagpt import database as db
from scripts.backfill_projects import (
    DEFAULT_INDUSTRY_SEGMENT,
    REQUIRED_ENV_VARS,
    BackfillError,
    backfill_projects,
    find_or_create_bootstrap_company,
    load_config,
    to_iso_utc,
)


# ── load_config ──────────────────────────────────────────────────────────

def test_load_config_missing_vars_raises():
    with pytest.raises(BackfillError, match="SUPABASE_URL"):
        load_config({})


def test_load_config_uses_default_company_name():
    env = {name: "x" for name in REQUIRED_ENV_VARS}
    config = load_config(env)
    assert "Bootstrap Company" in config["BOOTSTRAP_COMPANY_NAME"]


def test_load_config_respects_custom_company_name():
    env = {name: "x" for name in REQUIRED_ENV_VARS}
    env["BOOTSTRAP_COMPANY_NAME"] = "Acme Pharma QA Co"
    config = load_config(env)
    assert config["BOOTSTRAP_COMPANY_NAME"] == "Acme Pharma QA Co"


# ── to_iso_utc ───────────────────────────────────────────────────────────

def test_to_iso_utc_none_passthrough():
    assert to_iso_utc(None) is None


def test_to_iso_utc_sqlite_naive_timestamp_gets_utc_marker():
    assert to_iso_utc("2026-07-11 10:30:00") == "2026-07-11T10:30:00Z"


def test_to_iso_utc_already_offset_passthrough():
    assert to_iso_utc("2026-07-11T10:30:00+00:00") == "2026-07-11T10:30:00+00:00"


# ── find_or_create_bootstrap_company ────────────────────────────────────

def _query_mock(execute_return):
    q = MagicMock()
    q.select.return_value = q
    q.insert.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.execute.return_value = execute_return
    return q


def test_find_or_create_bootstrap_company_reuses_existing():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[{"id": "company-1"}]))

    company_id = find_or_create_bootstrap_company(client, "Bootstrap Co")

    assert company_id == "company-1"


def test_find_or_create_bootstrap_company_creates_when_missing():
    client = MagicMock()
    select_result = _query_mock(SimpleNamespace(data=[]))
    insert_result = _query_mock(SimpleNamespace(data=[{"id": "company-new"}]))
    client.table.side_effect = [select_result, insert_result]

    company_id = find_or_create_bootstrap_company(client, "Bootstrap Co")

    assert company_id == "company-new"
    insert_result.insert.assert_called_once_with(
        {"legal_name": "Bootstrap Co", "industry_segment": DEFAULT_INDUSTRY_SEGMENT}
    )


# ── backfill_projects ────────────────────────────────────────────────────

def test_backfill_projects_migrates_and_records_postgres_id(db_path):
    db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ")
    db.create_project("Proj B", "GC", "Waters", "QC", "OQ")

    client = MagicMock()
    inserted_ids = iter(["pg-a", "pg-b"])
    client.table.return_value = _query_mock(None)
    client.table.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"id": next(inserted_ids)}]) for _ in range(2)
    ]

    summary = backfill_projects(client, "company-1")

    assert summary == {"migrated": 2, "skipped_already_migrated": 0}
    projects = db.get_all_projects()
    assert {p["postgres_id"] for p in projects} == {"pg-a", "pg-b"}


def test_backfill_projects_skips_already_migrated(db_path):
    project = db.create_project("Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ")
    db.set_project_postgres_id(project["id"], "already-there")

    client = MagicMock()

    summary = backfill_projects(client, "company-1")

    assert summary == {"migrated": 0, "skipped_already_migrated": 1}
    client.table.assert_not_called()


def test_backfill_projects_only_maps_target_schema_fields(db_path):
    db.create_project(
        "Proj A", "HPLC", "Agilent", "QC", "IQ/OQ/PQ",
        owner="Jane Doe", approver="John Smith", risk_category="High",
        status="Approved", protocol_number="PROT-1", report_number="REP-1",
    )

    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[{"id": "pg-a"}]))

    backfill_projects(client, "company-1")

    payload = client.table.return_value.insert.call_args[0][0]
    assert payload["company_id"] == "company-1"
    assert payload["name"] == "Proj A"
    assert payload["status"] == "Approved"
    assert payload["risk_category"] == "High"
    assert payload["protocol_number"] == "PROT-1"
    assert payload["report_number"] == "REP-1"
    # No equipment/free-text-owner fields — no home in the target schema yet.
    assert "equipment_name" not in payload
    assert "manufacturer" not in payload
    assert "owner" not in payload
    assert "owner_user_id" not in payload

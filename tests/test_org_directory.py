"""
tests/test_org_directory.py — pharmagpt/services/org_directory.py, fully
mocked against the Supabase client (no live Supabase project).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pharmagpt.services.org_directory import (
    find_or_create_department,
    get_workflow_role_id,
    set_primary_department,
)


def _chain_mock():
    q = MagicMock()
    for method in ("select", "eq", "maybe_single", "insert", "update", "upsert"):
        getattr(q, method).return_value = q
    return q


# ── get_workflow_role_id ─────────────────────────────────────────────────

def test_get_workflow_role_id_found():
    client = MagicMock()
    client.table.return_value = _chain_mock()
    client.table.return_value.execute.return_value = SimpleNamespace(data={"id": 3})

    assert get_workflow_role_id(client, "Reviewer") == 3


def test_get_workflow_role_id_not_found():
    client = MagicMock()
    client.table.return_value = _chain_mock()
    client.table.return_value.execute.return_value = SimpleNamespace(data=None)

    assert get_workflow_role_id(client, "Not A Role") is None


# ── find_or_create_department ───────────────────────────────────────────

def test_find_or_create_department_creates_when_absent():
    client = MagicMock()
    q = _chain_mock()
    q.execute.side_effect = [
        SimpleNamespace(data=None),
        SimpleNamespace(data=[{"id": "dept-1", "name": "Quality Assurance", "department_code": "QA"}]),
    ]
    client.table.return_value = q

    result = find_or_create_department(client, "company-1", "Quality Assurance", "QA")

    assert result["id"] == "dept-1"
    q.insert.assert_called_once_with(
        {"company_id": "company-1", "name": "Quality Assurance", "department_code": "QA"}
    )


def test_find_or_create_department_reuses_existing_unchanged():
    client = MagicMock()
    q = _chain_mock()
    existing_row = {"id": "dept-1", "name": "Quality Assurance", "department_code": "QA"}
    q.execute.side_effect = [SimpleNamespace(data=existing_row)]
    client.table.return_value = q

    result = find_or_create_department(client, "company-1", "Quality Assurance", "QA")

    assert result == existing_row
    q.insert.assert_not_called()
    q.update.assert_not_called()


def test_find_or_create_department_updates_name_when_changed():
    """department_code is the stable key; name may legitimately change."""
    client = MagicMock()
    q = _chain_mock()
    existing_row = {"id": "dept-1", "name": "QA (old name)", "department_code": "QA"}
    q.execute.side_effect = [
        SimpleNamespace(data=existing_row),
        SimpleNamespace(data=[{"id": "dept-1", "name": "Quality Assurance", "department_code": "QA"}]),
    ]
    client.table.return_value = q

    result = find_or_create_department(client, "company-1", "Quality Assurance", "QA")

    assert result["name"] == "Quality Assurance"
    q.update.assert_called_once_with({"name": "Quality Assurance"})


# ── set_primary_department ──────────────────────────────────────────────

def test_set_primary_department_creates_first_primary():
    client = MagicMock()
    q = _chain_mock()
    q.execute.side_effect = [
        SimpleNamespace(data=None),
        SimpleNamespace(data=[{"id": "ud-1"}]),
    ]
    client.table.return_value = q

    set_primary_department(client, "user-1", "company-1", "dept-1")

    q.upsert.assert_called_once_with(
        {"user_id": "user-1", "department_id": "dept-1", "company_id": "company-1", "is_primary": True},
        on_conflict="user_id,department_id",
    )


def test_set_primary_department_is_noop_when_already_primary():
    client = MagicMock()
    q = _chain_mock()
    q.execute.side_effect = [SimpleNamespace(data={"id": "ud-1", "department_id": "dept-1"})]
    client.table.return_value = q

    set_primary_department(client, "user-1", "company-1", "dept-1")

    q.update.assert_not_called()
    q.upsert.assert_not_called()


def test_set_primary_department_switches_primary_never_leaves_two():
    client = MagicMock()
    q = _chain_mock()
    q.execute.side_effect = [
        SimpleNamespace(data={"id": "ud-old", "department_id": "dept-old"}),
        SimpleNamespace(data=[{"id": "ud-old", "is_primary": False}]),
        SimpleNamespace(data=[{"id": "ud-new"}]),
    ]
    client.table.return_value = q

    set_primary_department(client, "user-1", "company-1", "dept-new")

    q.update.assert_called_once_with({"is_primary": False})
    q.upsert.assert_called_once_with(
        {"user_id": "user-1", "department_id": "dept-new", "company_id": "company-1", "is_primary": True},
        on_conflict="user_id,department_id",
    )

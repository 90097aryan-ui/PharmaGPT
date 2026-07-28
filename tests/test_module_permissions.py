"""
tests/test_module_permissions.py — pharmagpt/services/module_permissions.py,
fully mocked against the Supabase client (no live Supabase project).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pharmagpt.services.module_permissions import (
    get_module_id,
    get_module_permissions,
    has_module_permission,
    set_module_permission,
)


def _query_mock(execute_return):
    q = MagicMock()
    for method in ("select", "eq", "maybe_single", "insert", "update", "upsert"):
        getattr(q, method).return_value = q
    q.execute.return_value = execute_return
    return q


# ── get_module_id ────────────────────────────────────────────────────────

def test_get_module_id_found():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data={"id": "mod-qms"}))
    assert get_module_id(client, "QMS") == "mod-qms"


def test_get_module_id_not_found():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=None))
    assert get_module_id(client, "NOT_REAL") is None


# ── get_module_permissions / has_module_permission ─────────────────────

def test_get_module_permissions_defaults_missing_modules_to_false():
    client = MagicMock()
    rows = [{"enabled": True, "modules": {"code": "QMS"}}]
    client.table.return_value = _query_mock(SimpleNamespace(data=rows))

    result = get_module_permissions(client, "user-1")

    assert result == {"QMS": True, "VALIDATION": False, "DOCUMENT_GENERATOR": False}


def test_has_module_permission_true_when_row_enabled():
    client = MagicMock()
    rows = [{"enabled": True, "modules": {"code": "VALIDATION"}}]
    client.table.return_value = _query_mock(SimpleNamespace(data=rows))

    assert has_module_permission(client, "user-1", "VALIDATION") is True


def test_has_module_permission_false_when_row_disabled():
    client = MagicMock()
    rows = [{"enabled": False, "modules": {"code": "VALIDATION"}}]
    client.table.return_value = _query_mock(SimpleNamespace(data=rows))

    assert has_module_permission(client, "user-1", "VALIDATION") is False


def test_has_module_permission_false_when_no_row_fail_closed():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[]))

    assert has_module_permission(client, "user-1", "QMS") is False


def test_has_module_permission_false_for_unrecognized_code():
    client = MagicMock()
    assert has_module_permission(client, "user-1", "NOT_REAL") is False


# ── set_module_permission ───────────────────────────────────────────────

def test_set_module_permission_rejects_invalid_module():
    client = MagicMock()
    with pytest.raises(ValueError, match="Unrecognized module code"):
        set_module_permission(client, "user-1", "company-1", "NOT_REAL", True)


def test_set_module_permission_raises_when_module_row_missing():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=None))

    with pytest.raises(ValueError, match="No 'modules' row"):
        set_module_permission(client, "user-1", "company-1", "QMS", True)


def test_set_module_permission_upserts_on_conflict():
    client = MagicMock()
    modules_q = _query_mock(SimpleNamespace(data={"id": "mod-qms"}))
    ump_q = _query_mock(SimpleNamespace(data=[{"id": "row-1", "enabled": True}]))
    client.table.side_effect = lambda name: {"modules": modules_q, "user_module_permissions": ump_q}[name]

    result = set_module_permission(client, "user-1", "company-1", "QMS", True)

    assert result == {"id": "row-1", "enabled": True}
    ump_q.upsert.assert_called_once_with(
        {"user_id": "user-1", "company_id": "company-1", "module_id": "mod-qms", "enabled": True},
        on_conflict="user_id,module_id",
    )

"""
tests/test_check_rls_isolation.py — scripts/check_rls_isolation.py, fully
mocked against the Supabase client. No network access, no real Supabase
project — every test here exercises pure logic and mocked-client behavior
only, matching tests/test_check_projects_parity.py's conventions.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.check_rls_isolation import (
    ENV_CONFIRM_VAR,
    REQUIRED_ENV_VARS,
    CheckResult,
    IsolationTestError,
    check_update_blocked,
    cleanup_fixtures,
    find_or_create_company,
    find_or_create_row,
    load_config,
    marker_value,
    print_summary,
    run_checks_for_table,
    assert_safe_target,
)


def _query_mock(execute_return):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.maybe_single.return_value = q
    q.update.return_value = q
    q.delete.return_value = q
    q.insert.return_value = q
    q.execute.return_value = execute_return
    return q


# ── load_config / assert_safe_target ────────────────────────────────────

def test_load_config_missing_vars_raises():
    with pytest.raises(IsolationTestError, match="SUPABASE_URL"):
        load_config({})


def test_load_config_all_present_and_forwards_confirm_var():
    env = {name: "x" for name in REQUIRED_ENV_VARS}
    env[ENV_CONFIRM_VAR] = "staging"
    config = load_config(env)
    assert config[ENV_CONFIRM_VAR] == "staging"


def test_load_config_confirm_var_optional_at_load_time():
    """Missing confirm var doesn't fail loading — assert_safe_target is
    what enforces it, so the two failure messages stay distinct."""
    env = {name: "x" for name in REQUIRED_ENV_VARS}
    config = load_config(env)
    assert config[ENV_CONFIRM_VAR] is None


def test_assert_safe_target_refuses_without_confirm_var():
    with pytest.raises(IsolationTestError, match=ENV_CONFIRM_VAR):
        assert_safe_target("https://staging-project.supabase.co", None)


def test_assert_safe_target_refuses_with_wrong_confirm_value():
    with pytest.raises(IsolationTestError, match=ENV_CONFIRM_VAR):
        assert_safe_target("https://staging-project.supabase.co", "yes please")


def test_assert_safe_target_refuses_prod_url_even_with_confirm():
    with pytest.raises(IsolationTestError, match="prod"):
        assert_safe_target("https://myapp-prod.supabase.co", "staging")


def test_assert_safe_target_passes_for_staging_url_with_confirm():
    assert_safe_target("https://myapp-staging.supabase.co", "staging") is None


# ── marker_value ─────────────────────────────────────────────────────────

def test_marker_value_is_distinctive_and_deterministic():
    m1 = marker_value("projects", "a")
    m2 = marker_value("projects", "b")
    assert m1 != m2
    assert "projects" in m1
    assert marker_value("projects", "a") == m1  # deterministic, not random


# ── find_or_create_company / find_or_create_row ─────────────────────────

def test_find_or_create_company_reuses_existing():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[{"id": "existing-co"}]))

    company_id = find_or_create_company(client, "RLS Isolation Test — Company A (safe to delete)")

    assert company_id == "existing-co"


def test_find_or_create_company_creates_when_missing():
    client = MagicMock()
    select_mock = _query_mock(SimpleNamespace(data=[]))
    insert_mock = _query_mock(SimpleNamespace(data=[{"id": "new-co"}]))
    client.table.return_value.select.return_value = select_mock
    client.table.return_value.insert.return_value = insert_mock

    company_id = find_or_create_company(client, "RLS Isolation Test — Company A (safe to delete)")

    assert company_id == "new-co"


def test_find_or_create_row_reuses_existing():
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[{"id": "existing-row"}]))

    row_id = find_or_create_row(client, "projects", "co-a", "name", "RLS-ISOLATION-TEST::projects::company-a", {})

    assert row_id == "existing-row"


def test_find_or_create_row_creates_when_missing():
    client = MagicMock()
    select_mock = _query_mock(SimpleNamespace(data=[]))
    insert_mock = _query_mock(SimpleNamespace(data=[{"id": "new-row"}]))
    client.table.return_value.select.return_value = select_mock
    client.table.return_value.insert.return_value = insert_mock

    row_id = find_or_create_row(client, "projects", "co-a", "name", "RLS-ISOLATION-TEST::projects::company-a", {})

    assert row_id == "new-row"


# ── check_update_blocked ─────────────────────────────────────────────────

def test_check_update_blocked_passes_when_zero_affected_and_unchanged():
    auth_client = MagicMock()
    auth_client.table.return_value = _query_mock(SimpleNamespace(data=[]))

    service_client = MagicMock()
    service_client.table.return_value = _query_mock(
        SimpleNamespace(data={"name": "RLS-ISOLATION-TEST::projects::company-b"})
    )

    passed, detail = check_update_blocked(
        auth_client, service_client, "projects", "name", "row-b",
        "RLS-ISOLATION-TEST::projects::company-b",
    )

    assert passed is True
    assert "unchanged" in detail


def test_check_update_blocked_fails_when_value_actually_changed():
    """Distrusts the update call's own affected-row count alone — a
    service-role read-back showing a mutated value must still fail the
    check even if the update response looked empty."""
    auth_client = MagicMock()
    auth_client.table.return_value = _query_mock(SimpleNamespace(data=[]))

    service_client = MagicMock()
    service_client.table.return_value = _query_mock(
        SimpleNamespace(data={"name": "RLS-ISOLATION-TEST::projects::company-b::TAMPER-ATTEMPT"})
    )

    passed, detail = check_update_blocked(
        auth_client, service_client, "projects", "name", "row-b",
        "RLS-ISOLATION-TEST::projects::company-b",
    )

    assert passed is False
    assert "LEAK" in detail


def test_check_update_blocked_fails_when_rows_reported_affected():
    auth_client = MagicMock()
    auth_client.table.return_value = _query_mock(
        SimpleNamespace(data=[{"id": "row-b", "name": "tampered"}])
    )

    service_client = MagicMock()
    service_client.table.return_value = _query_mock(
        SimpleNamespace(data={"name": "RLS-ISOLATION-TEST::projects::company-b"})
    )

    passed, detail = check_update_blocked(
        auth_client, service_client, "projects", "name", "row-b",
        "RLS-ISOLATION-TEST::projects::company-b",
    )

    assert passed is False
    assert "LEAK" in detail


# ── run_checks_for_table ─────────────────────────────────────────────────

_SPEC = {"domain": "Projects", "table": "projects", "marker_field": "name", "extra": {}}
_ROW_IDS = {"projects": {"a": "row-a", "b": "row-b"}}


def _isolated_client(own_row_id: str) -> MagicMock:
    """An authenticated client whose list/fetch/update never surface the
    other company's row — the fully-isolated (correct) case. select() with
    no further .eq() chained is the list call; select().eq() is the direct
    fetch call — both hang off the same select.return_value mock, so they
    can be set independently without conflict."""
    client = MagicMock()
    select_mock = client.table.return_value.select.return_value
    select_mock.execute.return_value = SimpleNamespace(data=[{"id": own_row_id, "name": "own-marker"}])
    select_mock.eq.return_value.execute.return_value = SimpleNamespace(data=[])
    client.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[])
    return client


def _unchanged_service_client(row_id_to_marker: dict[str, str]) -> MagicMock:
    """A service-role client whose read-back always echoes each row id's
    real, unmutated marker — i.e. simulates the update never having taken
    effect, regardless of which row id a given check queries for."""
    service_client = MagicMock()

    def eq_side_effect(_field, row_id):
        m = MagicMock()
        m.maybe_single.return_value.execute.return_value = SimpleNamespace(
            data={"name": row_id_to_marker.get(row_id, "UNEXPECTED-ROW-ID")}
        )
        return m

    service_client.table.return_value.select.return_value.eq.side_effect = eq_side_effect
    return service_client


def test_run_checks_for_table_all_pass_when_fully_isolated():
    auth_clients = {"a": _isolated_client("row-a"), "b": _isolated_client("row-b")}
    service_client = _unchanged_service_client({
        "row-a": marker_value("projects", "a"),
        "row-b": marker_value("projects", "b"),
    })

    results = run_checks_for_table(_SPEC, auth_clients, service_client, _ROW_IDS)

    assert len(results) == 8  # 2 directions x 4 checks
    assert all(r.passed and not r.inconclusive for r in results)


def test_run_checks_for_table_flags_leak_when_other_row_in_list():
    leaking_client = MagicMock()
    leaking_client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "row-a", "name": "own"}, {"id": "row-b", "name": "leaked"}]
    )
    leaking_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[])
    )

    quiet_client = MagicMock()
    quiet_client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "row-b", "name": "own"}]
    )
    quiet_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[])
    )

    auth_clients = {"a": leaking_client, "b": quiet_client}
    service_client = MagicMock()
    service_client.table.return_value.select.return_value.eq.return_value \
        .maybe_single.return_value.execute.return_value = SimpleNamespace(data={"name": "unchanged"})

    results = run_checks_for_table(_SPEC, auth_clients, service_client, _ROW_IDS)

    a_to_b_leak = [r for r in results if r.direction == "A→B" and r.check == "list_excludes_other_company"]
    assert len(a_to_b_leak) == 1
    assert a_to_b_leak[0].passed is False
    assert "LEAK" in a_to_b_leak[0].detail


def test_run_checks_for_table_inconclusive_when_own_row_not_visible():
    blind_client = MagicMock()
    blind_client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(data=[])

    other_client = MagicMock()
    other_client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "row-b", "name": "own"}]
    )
    other_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[])
    )

    auth_clients = {"a": blind_client, "b": other_client}
    service_client = MagicMock()
    service_client.table.return_value.select.return_value.eq.return_value \
        .maybe_single.return_value.execute.return_value = SimpleNamespace(data={"name": "unchanged"})

    results = run_checks_for_table(_SPEC, auth_clients, service_client, _ROW_IDS)

    a_to_b = [r for r in results if r.direction == "A→B"]
    # Only the precondition check ran for this leg — the rest were skipped.
    assert len(a_to_b) == 1
    assert a_to_b[0].check == "precondition_own_row_visible"
    assert a_to_b[0].inconclusive is True
    assert a_to_b[0].passed is False


# ── print_summary verdict computation ────────────────────────────────────

def _result(passed=True, inconclusive=False) -> CheckResult:
    return CheckResult("Projects", "projects", "A→B", "list_excludes_other_company", passed, inconclusive, "detail")


def test_print_summary_pass_only_when_zero_failed_and_zero_inconclusive(capsys):
    verdict = print_summary("https://staging.supabase.co", [_result(True), _result(True)])
    assert verdict == "PASS"


def test_print_summary_fails_on_any_failure(capsys):
    verdict = print_summary("https://staging.supabase.co", [_result(True), _result(False)])
    assert verdict == "FAIL"


def test_print_summary_fails_on_any_inconclusive(capsys):
    verdict = print_summary("https://staging.supabase.co", [_result(True), _result(False, inconclusive=True)])
    assert verdict == "FAIL"


def test_print_summary_fails_on_empty_results(capsys):
    verdict = print_summary("https://staging.supabase.co", [])
    assert verdict == "FAIL"


# ── cleanup_fixtures scoping ─────────────────────────────────────────────

def test_cleanup_fixtures_only_deletes_by_known_markers(monkeypatch):
    """Every delete call must be scoped by .eq() to one of this script's
    own fixed markers/legal names — never an unscoped table-wide delete."""
    client = MagicMock()
    client.table.return_value = _query_mock(SimpleNamespace(data=[]))

    monkeypatch.setattr(
        "scripts.check_rls_isolation.find_auth_user_by_email",
        lambda c, email: None,
    )

    cleanup_fixtures(client)

    eq_calls = [call for call in client.table.return_value.eq.call_args_list]
    assert len(eq_calls) > 0
    for call in eq_calls:
        args = call.args
        assert args[0] in ("name", "title", "document_type", "legal_name")
        assert isinstance(args[1], str) and args[1]  # never an empty/None filter value

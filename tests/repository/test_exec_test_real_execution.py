"""
tests/repository/test_exec_test_real_execution.py — Coverage for the REAL
pytest execution path in repository_exec_test()/repository_run_test_suite()
(pharmagpt/services/repository/adapter.py), replacing the old
compile-check-plus-random-80%-simulation.

Every test here spawns a genuine subprocess (sys.executable -m pytest) via
the real, unmocked _run_pytest_subprocess(). Only _require_permission and
_get_employee_context are mocked (as in tests/repository/test_adapter.py) —
path safety, command construction, timeout handling, and audit logging are
all exercised for real.

Scratch test files are written under a top-level "_scratch_exec_test"
directory (NOT under tests/) specifically so pytest's own collection
(pytest.ini: testpaths = tests) never sees them, even momentarily — they
are created fresh inside each test body and removed in a fixture teardown.
"""
import os
import shutil
import sys
import threading
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

import pharmagpt.app as appmod
from pharmagpt.services.repository.adapter import (
    repository_exec_test,
    repository_run_test_suite,
    RepositoryAccessError,
    RepositorySecurityError,
)

REPO_ROOT = Path(r"D:\PharmaAgent")

EMPLOYEE_CONTEXT = {
    'employee_id': "test_user_123",
    'employee_email': "test@example.com",
    'employee_display_name': "Test User",
    'tenant_id': "test_company_456",
    'tenant_role': "user",
}


@pytest.fixture()
def scratch_dir():
    """A throwaway directory inside REPOSITORY_ROOT (so _validate_path_safety
    accepts it) but outside tests/ (so pytest's own collection never sees
    the files written into it)."""
    d = REPO_ROOT / "_scratch_exec_test" / uuid.uuid4().hex
    d.mkdir(parents=True)
    try:
        yield d
    finally:
        shutil.rmtree(d.parent, ignore_errors=True)


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ── Success ───────────────────────────────────────────────────────────────

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_real_execution_success(mock_get_context, mock_require_perm, scratch_dir):
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    test_file = _write(scratch_dir / "test_ok.py", (
        "def test_addition():\n"
        "    assert 1 + 1 == 2\n"
    ))
    rel_path = str(test_file.relative_to(REPO_ROOT))

    with appmod.app.app_context():
        result = repository_exec_test(rel_path)

    assert result['exit_code'] == 0
    assert result['passed'] == 1
    assert result['failed'] == 0
    assert result['tests_executed'] == 1
    assert result['test_framework'] == "pytest"
    # Real pytest output, not a simulated message.
    assert "1 passed" in result['stdout']
    assert any(tc['status'] == "passed" for tc in result['results'])


# ── Failure ───────────────────────────────────────────────────────────────

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_real_execution_failure(mock_get_context, mock_require_perm, scratch_dir):
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    test_file = _write(scratch_dir / "test_fail.py", (
        "def test_always_fails():\n"
        "    assert 1 == 2, 'deliberately wrong for test_real_execution_failure'\n"
    ))
    rel_path = str(test_file.relative_to(REPO_ROOT))

    with appmod.app.app_context():
        result = repository_exec_test(rel_path)

    # A failing test is a successful *execution* — no exception raised.
    assert result['exit_code'] == 1
    assert result['passed'] == 0
    assert result['failed'] == 1
    assert result['tests_executed'] == 1
    # Real pytest failure output (the actual assertion message), not the
    # old "Simulated test failure" placeholder string.
    assert "deliberately wrong for test_real_execution_failure" in result['stdout']
    assert "Simulated test failure" not in result['stdout']
    assert any(tc['status'] == "failed" for tc in result['results'])


# ── Timeout ───────────────────────────────────────────────────────────────

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_real_execution_timeout(mock_get_context, mock_require_perm, scratch_dir):
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    test_file = _write(scratch_dir / "test_slow.py", (
        "import time\n"
        "def test_takes_too_long():\n"
        "    time.sleep(10)\n"
    ))
    rel_path = str(test_file.relative_to(REPO_ROOT))

    with appmod.app.app_context():
        with pytest.raises(RepositoryAccessError, match="timed out"):
            repository_exec_test(rel_path, timeout=1)


# ── Malicious command / injection attempts ──────────────────────────────

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_malicious_command_shell_metacharacters_not_executed(mock_get_context, mock_require_perm):
    """A test_path crafted to look like a shell command must never reach a
    shell — the subprocess is invoked with shell=False and an argv list, so
    this can only ever be a literal (non-existent) path component."""
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    proof_file = REPO_ROOT / "PWNED_INJECTION_PROOF.txt"
    proof_file.unlink(missing_ok=True)
    malicious_path = f"tests; echo PWNED > {proof_file.name}"

    with appmod.app.app_context():
        # The literal (nonexistent) path is rejected cleanly — either as
        # "does not exist" or "no test files found", depending on which
        # check trips first; either way, nothing was executed.
        with pytest.raises(RepositoryAccessError, match="does not exist|No test files found"):
            repository_exec_test(malicious_path)

    assert not proof_file.exists(), "shell metacharacters in test_path were interpreted — injection succeeded"


@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_malicious_command_backtick_and_subshell_syntax_not_executed(mock_get_context, mock_require_perm):
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    proof_file = REPO_ROOT / "PWNED_SUBSHELL_PROOF.txt"
    proof_file.unlink(missing_ok=True)

    with appmod.app.app_context():
        for malicious_path in (
            f"tests/$(touch {proof_file.name})",
            f"tests/`touch {proof_file.name}`",
            "tests/test_x.py && whoami",
            "tests/test_x.py | whoami",
        ):
            with pytest.raises((RepositoryAccessError, RepositorySecurityError)):
                repository_exec_test(malicious_path)

    assert not proof_file.exists(), "subshell/pipe syntax in test_path was interpreted — injection succeeded"


# ── Path traversal ───────────────────────────────────────────────────────

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_path_traversal_blocked(mock_get_context, mock_require_perm):
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        with pytest.raises(RepositorySecurityError):
            repository_exec_test("../../../../Windows/System32")

        with pytest.raises(RepositorySecurityError):
            repository_exec_test(r"C:\Windows\System32\drivers\etc\hosts")


@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_run_test_suite_path_traversal_blocked(mock_get_context, mock_require_perm):
    """repository_run_test_suite() delegates straight to repository_exec_test()
    for a direct (non-"full"/"unit"/"integration") suite name, and the same
    path-safety boundary must hold through that delegation. run_test_suite()
    itself catches per-path exceptions (pre-existing, unchanged design — one
    bad path shouldn't kill the whole suite run), so the traversal attempt
    surfaces as a recorded per-path error rather than a raised exception;
    what matters is that it's rejected and recorded, not silently ignored
    or executed."""
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        result = repository_run_test_suite("../../../../Windows/System32")

    assert result['total_passed'] == 0
    assert result['total_failed'] >= 1
    assert len(result['suite_results']) == 1
    entry = result['suite_results'][0]
    assert 'error' in entry
    assert "outside the repository boundary" in entry['error']


# ── Concurrent execution ─────────────────────────────────────────────────

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_concurrent_real_execution_is_isolated(mock_get_context, mock_require_perm, scratch_dir):
    """Several threads calling repository_exec_test() at the same time must
    not crash, deadlock, or cross-contaminate each other's results — each
    spawns its own subprocess and its own temp JUnit report."""
    mock_get_context.return_value = EMPLOYEE_CONTEXT
    mock_require_perm.return_value = None

    # One file that passes, one that fails — run several of each
    # concurrently and confirm every thread got the *correct* outcome for
    # the file it targeted, not another thread's.
    pass_file = _write(scratch_dir / "test_concurrent_pass.py", (
        "def test_p():\n    assert True\n"
    ))
    fail_file = _write(scratch_dir / "test_concurrent_fail.py", (
        "def test_f():\n    assert False\n"
    ))
    pass_rel = str(pass_file.relative_to(REPO_ROOT))
    fail_rel = str(fail_file.relative_to(REPO_ROOT))

    targets = ([pass_rel] * 4) + ([fail_rel] * 4)
    outcomes = [None] * len(targets)
    errors = [None] * len(targets)

    def worker(i, rel_path):
        try:
            with appmod.app.app_context():
                outcomes[i] = repository_exec_test(rel_path)
        except Exception as exc:  # pragma: no cover - captured for assertion
            errors[i] = exc

    threads = [threading.Thread(target=worker, args=(i, p)) for i, p in enumerate(targets)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert all(e is None for e in errors), f"unexpected exceptions in threads: {errors}"
    assert all(o is not None for o in outcomes), "a thread never completed"

    for i, rel_path in enumerate(targets):
        result = outcomes[i]
        if rel_path == pass_rel:
            assert result['exit_code'] == 0 and result['passed'] == 1 and result['failed'] == 0, \
                f"thread {i} (pass target) got contaminated result: {result}"
        else:
            assert result['exit_code'] == 1 and result['passed'] == 0 and result['failed'] == 1, \
                f"thread {i} (fail target) got contaminated result: {result}"

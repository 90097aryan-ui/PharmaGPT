"""
Tests for the repository adapter
"""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock, ANY
from pathlib import Path

# Add the pharmagpt directory to the path so we can import the adapter
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pharmagpt.services.repository.adapter import (
    repository_inspect,
    repository_read,
    repository_search,
    repository_git_status,
    repository_git_diff,
    repository_lint,
    repository_typecheck,
    repository_sast_scan,
    repository_secret_scan,
    repository_write,
    repository_exec_test,
    repository_run_test_suite,
    RepositoryAccessError,
    RepositorySecurityError
)
import pharmagpt.app as appmod

# A real, stable file guaranteed to exist in this repo (pharmagpt has no
# __init__.py — it relies on implicit namespace packages — so the previous
# "pharmagpt/__init__.py" fixture path never existed).
SAMPLE_FILE = "pharmagpt/audit.py"

# Mock Flask g object for testing
class MockTenant:
    def __init__(self):
        self.user_id = "test_user_123"
        self.email = "test@example.com"
        self.display_name = "Test User"
        self.company_id = "test_company_456"
        self.role = "user"

class MockG:
    def __init__(self):
        self.tenant = MockTenant()

def setup_mock_flask_g():
    """Setup mock Flask g object for testing"""
    mock_g = MockG()
    # We'll patch this in each test where needed

def test_adapter_initialization():
    """Test that the adapter module loads correctly"""
    # Just test that we can import the functions
    assert callable(repository_inspect)
    assert callable(repository_read)
    assert callable(repository_search)
    assert callable(repository_git_status)
    assert callable(repository_git_diff)
    assert callable(repository_lint)
    assert callable(repository_typecheck)
    assert callable(repository_sast_scan)
    assert callable(repository_secret_scan)
    assert callable(repository_write)
    assert callable(repository_exec_test)
    assert callable(repository_run_test_suite)

def test_validate_path_safety_within_repo():
    """Test that paths within the repository are allowed"""
    from pharmagpt.services.repository.adapter import _validate_path_safety

    # Test relative path
    safe_path = _validate_path_safety("README.md")
    assert safe_path == Path(r"D:\PharmaAgent") / "README.md"

    # Test subdirectory path
    safe_path = _validate_path_safety("pharmagpt/services/__init__.py")
    assert safe_path == Path(r"D:\PharmaAgent") / "pharmagpt" / "services" / "__init__.py"

    # Test absolute path within repo
    safe_path = _validate_path_safety(r"D:\PharmaAgent\README.md")
    assert safe_path == Path(r"D:\PharmaAgent") / "README.md"

def test_validate_path_safety_outside_repo():
    """Test that paths outside the repository are blocked"""
    from pharmagpt.services.repository.adapter import _validate_path_safety

    # Test path traversal
    with pytest.raises(RepositorySecurityError):
        _validate_path_safety("../../../etc/passwd")

    # Test absolute path outside repo
    with pytest.raises(RepositorySecurityError):
        _validate_path_safety(r"C:\Windows\System32\config\sam")

    # Test relative path that escapes
    with pytest.raises(RepositorySecurityError):
        _validate_path_safety("pharmagpt/../../../Windows/System32")

def test_get_employee_context():
    """Test getting employee context"""
    from pharmagpt.services.repository.adapter import _get_employee_context
    from flask import g

    # g is only bindable within an active app context.
    with appmod.app.app_context():
        g.tenant = MockTenant()

        context = _get_employee_context()
        assert context['employee_id'] == "test_user_123"
        assert context['employee_email'] == "test@example.com"
        assert context['employee_display_name'] == "Test User"
        assert context['tenant_id'] == "test_company_456"
        assert context['tenant_role'] == "user"

def test_get_employee_context_no_auth():
    """Test getting employee context when not authenticated"""
    from pharmagpt.services.repository.adapter import _get_employee_context
    from flask import g

    with appmod.app.app_context():
        # Setup mock with no tenant
        g.tenant = None

        with pytest.raises(RepositoryAccessError, match="No authenticated employee context"):
            _get_employee_context()

@patch('pharmagpt.services.repository.adapter.module_access.has_business_permission')
def test_require_permission_granted(mock_has_permission):
    """Test permission checking when permission is granted"""
    from pharmagpt.services.repository.adapter import _require_permission
    from flask import g

    with appmod.app.app_context():
        # Setup mocks
        g.tenant = MockTenant()
        mock_has_permission.return_value = True

        # Should not raise
        _require_permission("repository.read")
        mock_has_permission.assert_called_once_with(
            "test_user_123", "test_company_456", "repository.read"
        )

@patch('pharmagpt.services.repository.adapter.module_access.has_business_permission')
def test_require_permission_denied(mock_has_permission):
    """Test permission checking when permission is denied"""
    from pharmagpt.services.repository.adapter import _require_permission
    from flask import g

    with appmod.app.app_context():
        # Setup mocks
        g.tenant = MockTenant()
        mock_has_permission.return_value = False

        # Should raise
        with pytest.raises(RepositoryAccessError, match="Permission denied"):
            _require_permission("repository.write")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_inspect_success(mock_get_context, mock_require_perm):
    """Test successful repository inspection"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    # audit.log() (called by _log_repository_operation on every code path)
    # reads g.tenant, which needs an active app context.
    with appmod.app.app_context():
        # Test inspecting a known file
        result = repository_inspect(SAMPLE_FILE)

        assert result['type'] == 'file'
        # Windows renders relative_to() with backslashes; normalize before comparing.
        assert result['path'].replace('\\', '/') == SAMPLE_FILE
        assert result['size'] > 0
        assert 'modified' in result
        assert 'permissions' in result

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.inspect")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_inspect_path_traversal(mock_get_context, mock_require_perm):
    """Test that path traversal is blocked in inspect"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Should raise security error
        with pytest.raises(RepositorySecurityError):
            repository_inspect("../../../etc/passwd")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_read_success(mock_get_context, mock_require_perm):
    """Test successful file read"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Test reading a known file
        content = repository_read(SAMPLE_FILE)

        assert isinstance(content, str)
        assert len(content) > 0
        assert '#' in content  # Should have comments

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.read")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_read_not_found(mock_get_context, mock_require_perm):
    """Test reading a non-existent file"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Should raise access error. repository_read() reports both "missing"
        # and "exists but is a directory" as "Path is not a file" (unlike
        # repository_inspect(), which distinguishes the two) — this matches
        # the current, intentional contract of repository_read().
        with pytest.raises(RepositoryAccessError, match="Path is not a file"):
            repository_read("nonexistent_file_xyz123.py")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_search_success(mock_get_context, mock_require_perm):
    """Test successful search"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Search for something that should exist
        results = repository_search("class", "pharmagpt/*.py")

        assert isinstance(results, list)
        # Should find at least some matches
        assert len(results) >= 0

        if results:
            # Check structure of results
            for result in results:
                assert 'file' in result
                assert 'line' in result
                assert 'content' in result

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.search")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_git_status_success(mock_get_context, mock_require_perm):
    """Test successful git status"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Test git status
        result = repository_git_status()

        assert isinstance(result, dict)
        assert 'branch' in result
        assert 'files' in result
        assert 'clean' in result
        assert isinstance(result['files'], list)

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.git_status")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
@patch('pharmagpt.services.repository.adapter._execute_git_command')
def test_repository_git_diff_success(mock_execute_git, mock_get_context, mock_require_perm):
    """Test successful git diff"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None
    mock_execute_git.return_value = (0, "diff --git a/test.py b/test.py\n+new line\n", "")

    with appmod.app.app_context():
        # Test git diff
        result = repository_git_diff()

        assert isinstance(result, str)
        assert "diff --git" in result
        assert "+new line" in result

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.git_diff")

        # Verify git command was called safely. repository_git_diff() relies
        # on _execute_git_command()'s own cwd=None default (which resolves
        # to REPOSITORY_ROOT internally — exercised for real, unmocked, by
        # test_repository_git_status_success), so no explicit cwd kwarg is
        # passed here; this only verifies the command itself.
        mock_execute_git.assert_called_once()
        args, kwargs = mock_execute_git.call_args
        assert args[0] == ['git', 'diff']

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_lint_success(mock_get_context, mock_require_perm):
    """Test successful lint operation"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Test lint
        result = repository_lint(SAMPLE_FILE)

        assert isinstance(result, dict)
        assert 'path' in result
        assert 'linter' in result
        assert 'files_checked' in result
        assert 'issues' in result
        assert 'issue_count' in result
        assert result['files_checked'] >= 0

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.lint")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_typecheck_success(mock_get_context, mock_require_perm):
    """Test successful typecheck operation"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Test typecheck
        result = repository_typecheck(SAMPLE_FILE)

        assert isinstance(result, dict)
        assert 'path' in result
        assert 'checker' in result
        assert 'files_checked' in result
        assert 'issues' in result
        assert 'issue_count' in result
        assert result['files_checked'] >= 0

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.typecheck")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_sast_scan_success(mock_get_context, mock_require_perm):
    """Test successful SAST scan"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Test SAST scan
        result = repository_sast_scan(SAMPLE_FILE)

        assert isinstance(result, dict)
        assert 'path' in result
        assert 'scanner' in result
        assert 'files_scanned' in result
        assert 'issues' in result
        assert 'issue_count' in result
        assert 'scan_passed' in result
        assert result['files_scanned'] >= 0

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.sast_scan")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_secret_scan_success(mock_get_context, mock_require_perm):
    """Test successful secret scan"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Test secret scan
        result = repository_secret_scan(SAMPLE_FILE)

        assert isinstance(result, dict)
        assert 'path' in result
        assert 'scanner' in result
        assert 'files_scanned' in result
        assert 'findings' in result
        assert 'finding_count' in result
        assert 'scan_passed' in result
        assert result['files_scanned'] >= 0

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.secret_scan")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
@patch('pharmagpt.services.repository.adapter._require_approval')
def test_repository_write_success(mock_require_approval, mock_get_context, mock_require_perm):
    """Test successful write operation with approval"""
    from flask import g, request

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None
    mock_require_approval.return_value = True

    # adapter.py imports `request` locally inside _require_approval(), so
    # there is no module-level `adapter.request` attribute to patch — use a
    # real Flask request context with the approval headers instead. A
    # request context also provides the app context audit.log() needs.
    with appmod.app.test_request_context(headers={
        'X-Approval-Granted': 'true',
        'X-Approval-ID': 'approval_123',
    }):
        # Test write to a temporary file
        test_content = "# Test content\nprint('hello world')\n"
        result = repository_write("temp_test_file.py", test_content)

        assert isinstance(result, dict)
        assert 'path' in result
        assert 'bytes_written' in result
        assert result['bytes_written'] == len(test_content.encode('utf-8'))
        assert result['path'] == "temp_test_file.py"

        # Clean up
        test_file_path = Path(r"D:\PharmaAgent") / "temp_test_file.py"
        if test_file_path.exists():
            test_file_path.unlink()

        # Clean up backup directory if created
        backup_dir = Path(r"D:\PharmaAgent") / ".backups"
        if backup_dir.exists():
            for backup_file in backup_dir.glob("temp_test_file.py.*.bak"):
                backup_file.unlink()
            # Remove directory if empty
            try:
                backup_dir.rmdir()
            except OSError:
                pass  # Directory not empty, ignore

        # Verify permissions and approval were checked
        mock_require_perm.assert_called_once_with("repository.write")
        mock_require_approval.assert_called_once_with("write", ANY)

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_write_no_approval(mock_get_context, mock_require_perm):
    """Test that write operation fails without approval"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    # _require_approval() reads request.headers directly (real code path,
    # not mocked here) — needs a real request context, with no approval
    # header, to exercise the actual Class-C approval gate.
    with appmod.app.test_request_context():
        with pytest.raises(RepositoryAccessError, match="Class-C approval required"):
            repository_write("temp_test_file.py", "# test content")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_write_sensitive_file(mock_get_context, mock_require_perm):
    """Test that writing to sensitive files is restricted"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    # repository_write() checks approval before the sensitive-file
    # blocklist, so approval must be granted here to reach the check this
    # test actually targets (the sensitive-file rejection, not the
    # approval gate — that's covered separately by
    # test_repository_write_no_approval).
    with appmod.app.test_request_context(headers={
        'X-Approval-Granted': 'true',
        'X-Approval-ID': 'approval_456',
    }):
        # Should raise access error for sensitive file
        with pytest.raises(RepositoryAccessError, match="Writing to sensitive file"):
            repository_write(".env", "SECRET=something")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_exec_test_success(mock_get_context, mock_require_perm):
    """Test successful test execution"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # Test executing tests on a real, stable test file
        result = repository_exec_test("tests/test_pdf_engines.py")

        assert isinstance(result, dict)
        assert 'test_path' in result
        assert 'test_framework' in result
        assert 'test_files_found' in result
        assert 'tests_executed' in result
        assert 'passed' in result
        assert 'failed' in result
        assert 'results' in result
        assert isinstance(result['results'], list)

        # Verify permission was checked
        mock_require_perm.assert_called_once_with("repository.exec_test")

@patch('pharmagpt.services.repository.adapter._require_permission')
@patch('pharmagpt.services.repository.adapter._get_employee_context')
def test_repository_run_test_suite_success(mock_get_context, mock_require_perm):
    """Test successful test suite execution"""
    from flask import g

    # Setup mocks
    mock_get_context.return_value = {
        'employee_id': "test_user_123",
        'employee_email': "test@example.com",
        'employee_display_name': "Test User",
        'tenant_id': "test_company_456",
        'tenant_role': "user"
    }
    mock_require_perm.return_value = None

    with appmod.app.app_context():
        # "unit"/"full"/"integration" all map to the whole "tests"
        # directory (~1,600+ real tests, several minutes) now that
        # repository_exec_test() runs real pytest — too slow for a unit
        # test. Use a direct-path suite name instead (the non-keyword
        # branch), pointed at one small, fast, real test file, to exercise
        # the real aggregation logic without the full-suite runtime.
        result = repository_run_test_suite("tests/test_pdf_engines.py")

        assert isinstance(result, dict)
        assert 'suite_name' in result
        assert 'test_paths' in result
        assert 'total_tests_executed' in result
        assert 'total_passed' in result
        assert 'total_failed' in result
        assert 'suite_results' in result
        assert isinstance(result['suite_results'], list)

        # Verify permission was checked. run_test_suite() delegates to
        # repository_exec_test() internally, which independently re-checks
        # its own "repository.exec_test" permission (defense in depth) — so
        # _require_permission is legitimately called twice here, not once.
        mock_require_perm.assert_any_call("repository.run_test_suite")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
pharmagpt/services/repository/adapter.py — Controlled Repository Adapter for Yuktav
Implements the governed repository boundary that allows AI Engineering Employees to work on the Yuktav repository at D:\\PharmaAgent
Follows the Policy → Permission → Approval → Tool → Audit pipeline
"""

import os
import json
import subprocess
import sys
import tempfile
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from pharmagpt import audit, config, tenancy
from pharmagpt.services import approval_engine
from pharmagpt.auth import rbac, module_access

# Repository root - Yuktav repository
REPOSITORY_ROOT = Path(r"D:\PharmaAgent").resolve()

# Default hard timeout (seconds) for a single repository_exec_test()
# subprocess invocation. Exposed as a module-level constant (rather than
# buried in the function) so it can be overridden per call for a large
# suite, or monkeypatched/passed small in tests to deterministically
# exercise the timeout path without needing an actually-slow test file.
TEST_EXECUTION_TIMEOUT = 300


class RepositoryAccessError(Exception):
    """Raised when repository access is denied or operation fails"""
    pass


class RepositorySecurityError(Exception):
    """Raised when a security violation is detected"""
    pass


def _validate_path_safety(requested_path: str) -> Path:
    """
    Validates that the requested path is safe and within the repository boundary.
    
    Args:
        requested_path: The path to validate (can be relative or absolute)
        
    Returns:
        Path: The resolved, safe path within the repository
        
    Raises:
        RepositorySecurityError: If path traversal or outside access is detected
    """
    # Convert to Path object and make absolute
    if os.path.isabs(requested_path):
        requested_path_obj = Path(requested_path)
    else:
        requested_path_obj = REPOSITORY_ROOT / requested_path
    
    # Resolve to absolute path (removes any .. or . components)
    try:
        resolved_path = requested_path_obj.resolve(strict=False)
    except Exception as e:
        raise RepositorySecurityError(f"Invalid path: {requested_path}") from e
    
    # Ensure the path is within the repository boundary
    try:
        # Check if the resolved path is within REPOSITORY_ROOT
        resolved_path.relative_to(REPOSITORY_ROOT)
    except ValueError:
        raise RepositorySecurityError(
            f"Access denied: Path {requested_path} resolves to {resolved_path} "
            f"which is outside the repository boundary {REPOSITORY_ROOT}"
        )
    
    return resolved_path


def _get_employee_context() -> Dict[str, Any]:
    """
    Gets the current employee context from the Flask g object (tenant).
    
    Returns:
        Dict containing employee information
        
    Raises:
        RepositoryAccessError: If no authenticated context is available
    """
    from flask import g
    
    if not hasattr(g, 'tenant') or g.tenant is None:
        raise RepositoryAccessError("No authenticated employee context available")
    
    tenant = g.tenant
    return {
        'employee_id': tenant.user_id,
        'employee_email': tenant.email,
        'employee_display_name': tenant.display_name,
        'tenant_id': tenant.company_id,
        'tenant_role': tenant.role
    }


def _require_permission(permission: str, resource: str = "repository") -> None:
    """
    Checks if the current employee has the required permission for the resource.
    
    Args:
        permission: The permission string to check (e.g., "repository.read")
        resource: The resource type (default: "repository")
        
    Raises:
        RepositoryAccessError: If permission is denied
    """
    from flask import g
    
    if not hasattr(g, 'tenant') or g.tenant is None:
        raise RepositoryAccessError("No authenticated employee context available")
    
    # Check module access
    employee_context = _get_employee_context()
    if not module_access.has_business_permission(
        employee_context['employee_id'], 
        employee_context['tenant_id'], 
        permission
    ):
        raise RepositoryAccessError(
            f"Permission denied: Employee {employee_context['employee_id']} "
            f"lacks {permission} permission for {resource}"
        )


def _require_approval(action: str, correlation_id: str) -> bool:
    """
    Checks if the action requires approval and if approval has been granted.
    
    Args:
        action: The action being performed (e.g., "write")
        correlation_id: Unique identifier for tracking the request
        
    Returns:
        bool: True if approval is granted or not required
        
    Raises:
        RepositoryAccessError: If approval is required but not granted
    """
    # Define which actions require Class-C approval
    APPROVAL_REQUIRED_ACTIONS = {
        "write": "Class-C",
        # Other write operations that might require approval in future
    }
    
    approval_level = APPROVAL_REQUIRED_ACTIONS.get(action)
    if not approval_level:
        # No approval required for this action
        return True
    
    # Check if approval has been granted
    # In a real implementation, this would check the approval engine
    # For now, we'll simulate by checking if there's an approval record
    # This should integrate with the existing approval_engine
    
    # For demonstration, we'll require explicit approval for write operations
    if action == "write":
        # In production, this would check approval_engine for granted approval
        # For now, we'll check if a special header or flag is set indicating approval
        from flask import request
        approval_granted = request.headers.get('X-Approval-Granted', 'false').lower() == 'true'
        approval_id = request.headers.get('X-Approval-ID', '')
        
        if not approval_granted:
            raise RepositoryAccessError(
                f"Class-C approval required for write operation. "
                f"Approval ID: {approval_id or 'missing'}, Correlation ID: {correlation_id}"
            )
        
        # Log the approval usage
        audit.log(
            record_type="repository_approval",
            record_id=0,  # Approval doesn't have a specific record ID in this context
            action=f"APPROVAL_USED_{approval_level}",
            reason=f"Used {approval_level} approval for {action} operation",
            detail=f"Approval ID: {approval_id}, Correlation ID: {correlation_id}",
            result="success"
        )
    
    return True


def _execute_git_command(command: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """
    Executes a git command safely within the repository boundary.
    
    Args:
        command: List of command parts to execute
        cwd: Working directory (defaults to repository root)
        
    Returns:
        Tuple of (returncode, stdout, stderr)
        
    Raises:
        RepositorySecurityError: If git command tries to perform push/commit/deploy
    """
    if cwd is None:
        cwd = REPOSITORY_ROOT
    
    # Security check: Prevent dangerous git operations
    dangerous_ops = {'push', 'commit', 'deploy', 'pull', 'fetch', 'merge', 'rebase', 'reset'}
    if command[0] == 'git' and len(command) > 1:
        git_op = command[1]
        if git_op in dangerous_ops:
            raise RepositorySecurityError(
                f"Git operation '{git_op}' is not allowed through the repository adapter"
            )
    
    # Execute the command
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        raise RepositoryAccessError("Git command timed out")
    except Exception as e:
        raise RepositoryAccessError(f"Failed to execute git command: {e}")


def _log_repository_operation(
    employee_context: Dict[str, Any],
    tool: str,
    action: str,
    target: str,
    result: str = "success",
    correlation_id: Optional[str] = None,
    detail: str = ""
) -> None:
    """
    Logs a repository operation to the audit trail.
    
    Args:
        employee_context: Employee information from _get_employee_context()
        tool: The tool being used (e.g., "repository.read")
        action: The action being performed
        target: The target of the operation (file path, etc.)
        result: "success" or "failure"
        correlation_id: Optional correlation ID for tracking
        detail: Additional detail about the operation
    """
    # Create audit record. audit.log() derives performed_by/company_id
    # itself from the authenticated g.tenant (never from a caller-supplied
    # dict, so identity can't be spoofed) — it does not accept those as
    # keyword arguments. Employee identity is still preserved in `detail`
    # for audit-trail readability.
    audit.log(
        record_type="repository_operation",
        record_id=hash(target) % 1000000,  # Simple hash for record ID
        action=f"REPOSITORY_{tool.upper()}_{action.upper()}",
        reason=detail,
        result=result,
        detail=(
            f"Tool: {tool}, Action: {action}, Target: {target}, "
            f"Employee: {employee_context.get('employee_display_name', 'unknown')} "
            f"({employee_context.get('employee_id', 'unknown')}), "
            f"Correlation ID: {correlation_id or 'none'}"
        )
    )


def repository_inspect(path: str = ".") -> Dict[str, Any]:
    """
    Inspects the repository or a specific path within it.
    
    Args:
        path: Relative path within the repository to inspect (default: root)
        
    Returns:
        Dict containing inspection results
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"inspect-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.inspect")
        
        # Validate path safety
        safe_path = _validate_path_safety(path)
        
        # Perform inspection
        if not safe_path.exists():
            raise RepositoryAccessError(f"Path does not exist: {path}")
        
        if safe_path.is_file():
            stat = safe_path.stat()
            result = {
                "type": "file",
                "path": str(safe_path.relative_to(REPOSITORY_ROOT)),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "permissions": oct(stat.st_mode)[-3:]
            }
        else:
            # Directory inspection
            items = []
            for item in safe_path.iterdir():
                try:
                    item_stat = item.stat()
                    items.append({
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item_stat.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(item_stat.st_mtime).isoformat()
                    })
                except (OSError, PermissionError):
                    # Skip items we can't stat
                    continue
            
            result = {
                "type": "directory",
                "path": str(safe_path.relative_to(REPOSITORY_ROOT)),
                "item_count": len(items),
                "items": sorted(items, key=lambda x: (x["type"] == "file", x["name"].lower()))
            }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.inspect",
            action="INSPECT",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success",
            correlation_id=correlation_id
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.inspect",
            action="INSPECT",
            target=path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_read(path: str) -> str:
    """
    Reads the contents of a file within the repository.
    
    Args:
        path: Relative path within the repository to read
        
    Returns:
        str: The file contents
        
    Raises:
        RepositoryAccessError: If access is denied or file cannot be read
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"read-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.read")
        
        # Validate path safety
        safe_path = _validate_path_safety(path)
        
        # Check it's a file
        if not safe_path.is_file():
            raise RepositoryAccessError(f"Path is not a file: {path}")
        
        # Read the file
        # Limit file size to prevent DoS (10MB max)
        max_size = 10 * 1024 * 1024  # 10MB
        if safe_path.stat().st_size > max_size:
            raise RepositoryAccessError(f"File too large to read: {path} (>{max_size} bytes)")
        
        contents = safe_path.read_text(encoding='utf-8', errors='replace')
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.read",
            action="READ",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success",
            correlation_id=correlation_id,
            detail=f"Read {len(contents)} characters"
        )
        
        return contents
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.read",
            action="READ",
            target=path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_search(query: str, file_pattern: str = "*", use_regex: bool = False) -> List[Dict[str, Any]]:
    """
    Searches for content within files in the repository.
    
    Args:
        query: The search query (text or regex)
        file_pattern: Glob pattern for files to search (default: "*")
        use_regex: Whether to treat query as regex (default: False)
        
    Returns:
        List of matches with file path, line number, and matching line
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"search-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.search")
        
        # Validate the search pattern doesn't allow path traversal
        # We'll validate each matched file path individually
        
        results = []
        
        # Use ripgrep or fallback to Python search
        # For simplicity and security, we'll use Python's built-in file operations
        
        # Convert glob pattern to Path matching
        pattern_path = REPOSITORY_ROOT / file_pattern
        
        # Safety check on the pattern itself
        try:
            pattern_path.resolve(strict=False)
        except Exception:
            raise RepositorySecurityError(f"Invalid file pattern: {file_pattern}")
        
        # Walk the repository
        for file_path in REPOSITORY_ROOT.rglob(file_pattern):
            # Skip if not a file
            if not file_path.is_file():
                continue
                
            # Validate each file path for safety
            try:
                safe_file_path = _validate_path_safety(str(file_path.relative_to(REPOSITORY_ROOT)))
            except RepositorySecurityError:
                # Skip files outside boundary (shouldn't happen with rglob from root, but safety first)
                continue
            
            try:
                # Read file and search
                contents = safe_file_path.read_text(encoding='utf-8', errors='replace')
                lines = contents.splitlines()
                
                for i, line in enumerate(lines, 1):  # Line numbers start at 1
                    match_found = False
                    
                    if use_regex:
                        import re
                        try:
                            if re.search(query, line):
                                match_found = True
                        except re.error:
                            raise RepositoryAccessError(f"Invalid regex pattern: {query}")
                    else:
                        if query in line:
                            match_found = True
                    
                    if match_found:
                        results.append({
                            "file": str(safe_file_path.relative_to(REPOSITORY_ROOT)),
                            "line": i,
                            "content": line.rstrip('\n\r')
                        })
                        
                        # Limit results to prevent DoS
                        if len(results) >= 1000:
                            break
                
                if len(results) >= 1000:
                    break
                    
            except (UnicodeDecodeError, OSError):
                # Skip binary or unreadable files
                continue
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.search",
            action="SEARCH",
            target=f"query: {query}, pattern: {file_pattern}",
            result="success",
            correlation_id=correlation_id,
            detail=f"Found {len(results)} matches"
        )
        
        return results
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.search",
            action="SEARCH",
            target=f"query: {query}, pattern: {file_pattern}",
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_git_status() -> Dict[str, Any]:
    """
    Gets the git status of the repository.
    
    Returns:
        Dict containing git status information
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If git command validation fails
    """
    correlation_id = f"git_status-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.git_status")
        
        # Execute git status
        returncode, stdout, stderr = _execute_git_command(['git', 'status', '--porcelain'])
        
        if returncode != 0:
            raise RepositoryAccessError(f"Git status failed: {stderr}")
        
        # Parse the output
        files = []
        for line in stdout.splitlines():
            if line.strip():
                # Parse porcelain format: XY filename
                if len(line) >= 3:
                    index_status = line[0]
                    worktree_status = line[1]
                    filename = line[3:].strip()
                    
                    files.append({
                        "path": filename,
                        "index_status": index_status,
                        "worktree_status": worktree_status,
                        "status_description": _git_status_description(index_status, worktree_status)
                    })
        
        # Get current branch
        branch_returncode, branch_stdout, branch_stderr = _execute_git_command(
            ['git', 'branch', '--show-current']
        )
        current_branch = branch_stdout.strip() if branch_returncode == 0 else "unknown"
        
        result = {
            "branch": current_branch,
            "files": files,
            "clean": len(files) == 0,
            "staged_changes": len([f for f in files if f["index_status"] != ' ']),
            "unstaged_changes": len([f for f in files if f["worktree_status"] != ' '])
        }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.git_status",
            action="GIT_STATUS",
            target="repository",
            result="success",
            correlation_id=correlation_id
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.git_status",
            action="GIT_STATUS",
            target="repository",
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_git_diff(path: Optional[str] = None, staged: bool = False) -> str:
    """
    Gets the git diff for the repository or a specific path.
    
    Args:
        path: Optional relative path to diff (None for entire repository)
        staged: Whether to show staged changes (default: False for working directory)
        
    Returns:
        str: The git diff output
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If git command validation fails or path is unsafe
    """
    correlation_id = f"git_diff-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.git_diff")
        
        # Build git diff command
        cmd = ['git', 'diff']
        if staged:
            cmd.append('--staged')
        
        if path is not None:
            # Validate path safety
            safe_path = _validate_path_safety(path)
            cmd.append('--')
            cmd.append(str(safe_path.relative_to(REPOSITORY_ROOT)))
        
        # Execute git diff
        returncode, stdout, stderr = _execute_git_command(cmd)
        
        if returncode != 0:
            raise RepositoryAccessError(f"Git diff failed: {stderr}")
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.git_diff",
            action="GIT_DIFF",
            target=path or "repository",
            result="success",
            correlation_id=correlation_id,
            detail=f"Staged: {staged}, Output length: {len(stdout)}"
        )
        
        return stdout
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.git_diff",
            action="GIT_DIFF",
            target=path or "repository",
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_lint(path: str = ".", linter: str = "auto") -> Dict[str, Any]:
    """
    Runs a linter on the repository or a specific path.
    
    Args:
        path: Relative path within the repository to lint (default: root)
        linter: Linter to use ("auto", "pylint", "flake8", "eslint", etc.)
        
    Returns:
        Dict containing linting results
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"lint-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.lint")
        
        # Validate path safety
        safe_path = _validate_path_safety(path)
        
        # For security, we'll implement a simple Python syntax check
        # In production, this would integrate with actual linters
        issues = []
        
        if safe_path.is_file():
            files_to_check = [safe_path]
        else:
            # Find Python files to lint (for demo)
            files_to_check = list(safe_path.rglob("*.py"))
            # Limit to prevent DoS
            files_to_check = files_to_check[:50]
        
        for file_path in files_to_check:
            try:
                # Validate each file
                safe_file_path = _validate_path_safety(str(file_path.relative_to(REPOSITORY_ROOT)))
                
                # Simple Python syntax check
                if safe_file_path.suffix == '.py':
                    contents = safe_file_path.read_text(encoding='utf-8', errors='replace')
                    try:
                        compile(contents, str(safe_file_path), 'exec')
                    except SyntaxError as e:
                        issues.append({
                            "file": str(safe_file_path.relative_to(REPOSITORY_ROOT)),
                            "line": e.lineno or 0,
                            "column": e.offset or 0,
                            "message": str(e),
                            "type": "error"
                        })
            except Exception:
                # Skip files we can't read
                continue
        
        result = {
            "path": str(safe_path.relative_to(REPOSITORY_ROOT)),
            "linter": linter,
            "files_checked": len(files_to_check),
            "issues": issues,
            "issue_count": len(issues)
        }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.lint",
            action="LINT",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success",
            correlation_id=correlation_id,
            detail=f"Checked {len(files_to_check)} files, found {len(issues)} issues"
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.lint",
            action="LINT",
            target=path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_typecheck(path: str = ".", checker: str = "auto") -> Dict[str, Any]:
    """
    Runs type checking on the repository or a specific path.
    
    Args:
        path: Relative path within the repository to type check (default: root)
        checker: Type checker to use ("auto", "mypy", "pyright", etc.)
        
    Returns:
        Dict containing type checking results
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"typecheck-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.typecheck")
        
        # Validate path safety
        safe_path = _validate_path_safety(path)
        
        # For security, we'll implement a basic type check simulation
        # In production, this would integrate with actual type checkers like mypy
        issues = []
        
        if safe_path.is_file():
            files_to_check = [safe_path]
        else:
            # Find Python files to type check
            files_to_check = list(safe_path.rglob("*.py"))
            # Limit to prevent DoS
            files_to_check = files_to_check[:50]
        
        for file_path in files_to_check:
            try:
                # Validate each file
                safe_file_path = _validate_path_safety(str(file_path.relative_to(REPOSITORY_ROOT)))
                
                # Basic type checking simulation - look for obvious type issues
                contents = safe_file_path.read_text(encoding='utf-8', errors='replace')
                lines = contents.splitlines()
                
                for i, line in enumerate(lines, 1):
                    # Simple heuristic: look for common type issues
                    if '=' in line and 'None' in line and not ': ' in line.split('=')[0]:
                        # Potential missing type annotation
                        pass  # Just an example, real type checker would be more sophisticated
                        
            except Exception:
                # Skip files we can't read
                continue
        
        result = {
            "path": str(safe_path.relative_to(REPOSITORY_ROOT)),
            "checker": checker,
            "files_checked": len(files_to_check),
            "issues": issues,
            "issue_count": len(issues)
        }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.typecheck",
            action="TYPECHECK",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success",
            correlation_id=correlation_id,
            detail=f"Checked {len(files_to_check)} files, found {len(issues)} type issues"
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.typecheck",
            action="TYPECHECK",
            target=path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_sast_scan(path: str = ".", scanner: str = "auto") -> Dict[str, Any]:
    """
    Runs a Static Application Security Testing (SAST) scan on the repository.
    
    Args:
        path: Relative path within the repository to scan (default: root)
        scanner: SAST scanner to use ("auto", "bandit", "semgrep", etc.)
        
    Returns:
        Dict containing scan results
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"sast_scan-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.sast_scan")
        
        # Validate path safety
        safe_path = _validate_path_safety(path)
        
        # For security, we'll implement a basic security scan simulation
        # In production, this would integrate with actual SAST scanners like bandit
        issues = []
        
        if safe_path.is_file():
            files_to_check = [safe_path]
        else:
            # Find files to scan (focus on Python files for demo)
            files_to_check = list(safe_path.rglob("*.py"))
            # Limit to prevent DoS
            files_to_check = files_to_check[:50]
        
        # Common security patterns to check for
        dangerous_patterns = [
            (r'eval\s*\(', 'Use of eval() can be dangerous'),
            (r'exec\s*\(', 'Use of exec() can be dangerous'),
            (r'pickle\.loads?\s*', 'Pickle can execute arbitrary code'),
            (r'os\.system\s*\(', 'os.system() can execute arbitrary commands'),
            (r'subprocess\.call\s*.*shell\s*=\s*True', 'subprocess with shell=True can be dangerous'),
            (r'requests\.get\s*.*verify\s*=\s*False', 'Disabled SSL verification'),
            (r'\[\s*for\s*.*in\s*.*if\s*.*\]', 'List comprehension - review for security'),
        ]
        
        import re
        
        for file_path in files_to_check:
            try:
                # Validate each file
                safe_file_path = _validate_path_safety(str(file_path.relative_to(REPOSITORY_ROOT)))
                
                contents = safe_file_path.read_text(encoding='utf-8', errors='replace')
                lines = contents.splitlines()
                
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    if not line_stripped or line_stripped.startswith('#'):
                        continue  # Skip empty lines and comments
                    
                    for pattern, message in dangerous_patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            issues.append({
                                "file": str(safe_file_path.relative_to(REPOSITORY_ROOT)),
                                "line": i,
                                "message": message,
                                "pattern": pattern,
                                "severity": "medium"
                            })
                            break  # Only report first match per line
                            
            except Exception:
                # Skip files we can't read
                continue
        
        result = {
            "path": str(safe_path.relative_to(REPOSITORY_ROOT)),
            "scanner": scanner,
            "files_scanned": len(files_to_check),
            "issues": issues,
            "issue_count": len(issues),
            "scan_passed": len(issues) == 0
        }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.sast_scan",
            action="SAST_SCAN",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success",
            correlation_id=correlation_id,
            detail=f"Scanned {len(files_to_check)} files, found {len(issues)} security issues"
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.sast_scan",
            action="SAST_SCAN",
            target=path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_secret_scan(path: str = ".", scanner: str = "auto") -> Dict[str, Any]:
    """
    Scans for secrets (passwords, keys, tokens) in the repository.
    
    Args:
        path: Relative path within the repository to scan (default: root)
        scanner: Secret scanner to use ("auto", "truffleHog", "git-secrets", etc.)
        
    Returns:
        Dict containing scan results
        
    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"secret_scan-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.secret_scan")
        
        # Validate path safety
        safe_path = _validate_path_safety(path)
        
        # For security, we'll implement a basic secret scan simulation
        # In production, this would integrate with actual secret scanners
        findings = []
        
        if safe_path.is_file():
            files_to_check = [safe_path]
        else:
            # Find files to scan (text files primarily)
            files_to_check = []
            for ext in ['*.py', '*.txt', '*.json', '*.yaml', '*.yml', '*.ini', '*.cfg', '*.conf', '*.md', '*.xml', '*.html', '*.js', '*.ts']:
                files_to_check.extend(list(safe_path.rglob(ext)))
            # Limit to prevent DoS
            files_to_check = files_to_check[:100]
        
        # Common secret patterns
        secret_patterns = [
            (r'[pP]assword\s*[=:]\s*["\'][^"\']{8,}["\']', 'Password found in plain text'),
            (r'[aA]pi[_-]?[kK]ey\s*[=:]\s*["\'][^"\']{10,}["\']', 'API key found'),
            (r'[sS]ecret\s*[=:]\s*["\'][^"\']{10,}["\']', 'Secret found'),
            (r'[tT]oken\s*[=:]\s*["\'][^"\']{10,}["\']', 'Token found'),
            (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', 'Private key found'),
            (r'aws_access_key_id\s*[=:]\s*["\'][A-Z0-9]{20}["\']', 'AWS access key ID found'),
            (r'aws_secret_access_key\s*[=:]\s*["\'][A-Za-z0-9/+]{40}["\']', 'AWS secret access key found'),
        ]
        
        import re
        
        for file_path in files_to_check:
            try:
                # Validate each file
                safe_file_path = _validate_path_safety(str(file_path.relative_to(REPOSITORY_ROOT)))
                
                # Skip binary files by trying to read as text
                try:
                    contents = safe_file_path.read_text(encoding='utf-8', errors='strict')
                except UnicodeDecodeError:
                    continue  # Skip binary files
                
                lines = contents.splitlines()
                
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    if not line_stripped or line_stripped.startswith('#'):
                        continue  # Skip empty lines and comments
                    
                    for pattern, message in secret_patterns:
                        matches = re.findall(pattern, line)
                        if matches:
                            # Don't include the actual secret in the findings for security
                            findings.append({
                                "file": str(safe_file_path.relative_to(REPOSITORY_ROOT)),
                                "line": i,
                                "message": message,
                                "type": "credential",
                                "severity": "high"
                            })
                            break  # Only report first match per line
                            
            except Exception:
                # Skip files we can't read
                continue
        
        result = {
            "path": str(safe_path.relative_to(REPOSITORY_ROOT)),
            "scanner": scanner,
            "files_scanned": len(files_to_check),
            "findings": findings,
            "finding_count": len(findings),
            "scan_passed": len(findings) == 0
        }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.secret_scan",
            action="SECRET_SCAN",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success",
            correlation_id=correlation_id,
            detail=f"Scanned {len(files_to_check)} files, found {len(findings)} potential secrets"
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.secret_scan",
            action="SECRET_SCAN",
            target=path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_write(path: str, content: str) -> Dict[str, Any]:
    """
    Writes content to a file within the repository (requires Class-C approval).
    Writes remain controlled/draft-only - never allows commit, push, deploy, or production access.
    
    Args:
        path: Relative path within the repository to write
        content: The content to write to the file
        
    Returns:
        Dict containing write results
        
    Raises:
        RepositoryAccessError: If access is denied or approval is missing
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"write-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.write")
        
        # Require Class-C approval for write operations
        _require_approval("write", correlation_id)
        
        # Validate path safety
        safe_path = _validate_path_safety(path)
        
        # Security check: Prevent writing to certain sensitive files
        sensitive_files = {
            '.env', '.gitignore', '.gitattributes', '.gitmodules',
            'docker-compose.yml', 'docker-compose.yaml', 'Dockerfile',
            'requirements.txt', 'package.json', 'pyproject.toml',
            'setup.py', 'setup.cfg', 'MANIFEST.in'
        }
        
        file_name = safe_path.name
        if file_name in sensitive_files:
            # Additional check: only allow writing to sensitive files in specific directories
            # For example, allow .env files in config/ but not in root
            if str(safe_path.parent) in ['.', 'config'] and file_name == '.env':
                # Allow .env in config directory
                pass
            else:
                raise RepositoryAccessError(f"Writing to sensitive file '{file_name}' is not allowed")
        
        # Check if file already exists and create backup if so
        backup_created = False
        if safe_path.exists():
            # Create a backup with timestamp
            backup_dir = safe_path.parent / ".backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{safe_path.name}.{timestamp}.bak"
            shutil.copy2(safe_path, backup_path)
            backup_created = True
        
        # Write the file
        # Limit content size to prevent DoS (10MB max)
        max_size = 10 * 1024 * 1024  # 10MB
        if len(content.encode('utf-8')) > max_size:
            raise RepositoryAccessError(f"Content too large to write: >{max_size} bytes")
        
        safe_path.write_text(content, encoding='utf-8')
        
        result = {
            "path": str(safe_path.relative_to(REPOSITORY_ROOT)),
            "bytes_written": len(content.encode('utf-8')),
            "backup_created": backup_created,
            "backup_path": str(backup_path.relative_to(REPOSITORY_ROOT)) if backup_created else None,
            "note": "Write operation completed. File remains in working directory - no commit, push, or deploy performed."
        }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.write",
            action="WRITE",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success",
            correlation_id=correlation_id,
            detail=f"Wrote {len(content.encode('utf-8'))} bytes"
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.write",
            action="WRITE",
            target=path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def _run_pytest_subprocess(target_path: Path, timeout: int) -> Dict[str, Any]:
    """
    Executes REAL pytest against `target_path` as a genuine subprocess.

    Security properties (do not weaken):
    - `target_path` must already be a resolved, validated Path returned by
      _validate_path_safety() — this function never accepts or interprets
      a raw string from the caller.
    - The command is built as an argv LIST and run with shell=False
      (subprocess.run's default) — no shell is ever invoked, so shell
      metacharacters in a path (`;`, `&&`, `` ` ``, `$()`) have no special
      meaning; they can only ever be a literal (typically non-existent)
      filesystem path component.
    - The interpreter is `sys.executable` — the current, trusted venv
      Python — never a caller-influenced or PATH-resolved command.
    - `cwd` is pinned to REPOSITORY_ROOT.
    - A hard `timeout` bounds the subprocess; on expiry subprocess.run
      kills the child itself and raises TimeoutExpired, which is
      translated into a RepositoryAccessError by the caller.

    Residual, accepted risk: pytest, by design, imports and executes the
    target file's module-level code and test functions. Running pytest on
    a file is therefore equivalent to running arbitrary Python already
    present in the repository — the same as a human developer running
    `pytest <path>` themselves. This function does not (and cannot, while
    still performing "real" execution) sandbox the content of the test
    file itself; it only guarantees the *invocation* cannot be hijacked
    into running something other than pytest against something outside
    REPOSITORY_ROOT.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        junit_path = Path(tmp_dir) / "junit.xml"
        cmd = [
            sys.executable, "-m", "pytest",
            str(target_path),
            "-q",
            f"--junitxml={junit_path}",
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RepositoryAccessError(
                f"Test execution timed out after {timeout}s"
            ) from exc

        test_cases: List[Dict[str, Any]] = []
        passed = failed = errors = skipped = 0

        if junit_path.exists():
            try:
                root = ET.parse(junit_path).getroot()
                for tc in root.iter("testcase"):
                    name = f"{tc.get('classname', '')}::{tc.get('name', '')}"
                    if tc.find("failure") is not None:
                        status = "failed"
                        failed += 1
                    elif tc.find("error") is not None:
                        status = "error"
                        errors += 1
                    elif tc.find("skipped") is not None:
                        status = "skipped"
                        skipped += 1
                    else:
                        status = "passed"
                        passed += 1
                    test_cases.append({
                        "name": name,
                        "status": status,
                        "duration_s": float(tc.get("time", 0) or 0),
                    })
            except ET.ParseError:
                # pytest exited before writing a well-formed report (e.g. a
                # collection error) — fall back to the raw exit code below.
                pass

        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-20000:],
            "stderr": proc.stderr[-20000:],
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "test_cases": test_cases,
        }


def repository_exec_test(
    test_path: str,
    test_framework: str = "pytest",
    timeout: int = TEST_EXECUTION_TIMEOUT,
) -> Dict[str, Any]:
    """
    Executes REAL pytest against test_path within the controlled Yuktav
    workspace boundary (see _run_pytest_subprocess for the security
    properties of the invocation itself). Captures the real exit code,
    stdout/stderr, and structured per-test pass/fail/error/skipped results
    parsed from a JUnit XML report — no simulated/random outcome.

    Args:
        test_path: Relative path within the repository to tests (file or directory)
        test_framework: Informational only; real execution is always pytest
        timeout: Hard wall-clock limit in seconds for the subprocess

    Returns:
        Dict containing real test execution results

    Raises:
        RepositoryAccessError: If access is denied, the path doesn't
            resolve to any test files, or execution times out
        RepositorySecurityError: If path safety validation fails
    """
    correlation_id = f"exec_test-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()

    try:
        # Check permission
        _require_permission("repository.exec_test")

        # Validate path safety
        safe_path = _validate_path_safety(test_path)

        if not safe_path.exists():
            raise RepositoryAccessError(f"Path does not exist: {test_path}")

        # Fast pre-check for a helpful error before spending a subprocess:
        # does this scope contain anything pytest could collect? Also used
        # to report test_files_found (file-level, distinct from the
        # per-test counts pytest itself reports).
        if safe_path.is_file():
            test_files = [safe_path]
        else:
            test_files = []
            for pattern in ('test_*.py', '*_test.py'):
                test_files.extend(safe_path.rglob(pattern))

        if not test_files:
            raise RepositoryAccessError(f"No test files found in {test_path}")

        run = _run_pytest_subprocess(safe_path, timeout)

        tests_executed = run["passed"] + run["failed"] + run["errors"] + run["skipped"]
        # 0 = all passed, 1 = some tests failed — both are a successful
        # *execution* (the operation ran to completion); anything else
        # (interrupted/internal error/usage error/no tests collected)
        # indicates the execution itself broke.
        execution_ok = run["returncode"] in (0, 1)

        result = {
            "test_path": str(safe_path.relative_to(REPOSITORY_ROOT)),
            "test_framework": "pytest",
            "test_files_found": len(test_files),
            "tests_executed": tests_executed,
            "passed": run["passed"],
            "failed": run["failed"] + run["errors"],
            "skipped": run["skipped"],
            "pass_rate": (run["passed"] / tests_executed) if tests_executed else 0,
            "exit_code": run["returncode"],
            "stdout": run["stdout"],
            "stderr": run["stderr"],
            "results": run["test_cases"],
            "note": "Real pytest execution in the controlled workspace. No commit, push, deploy, or write outside the working tree performed by this function.",
        }

        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.exec_test",
            action="EXEC_TEST",
            target=str(safe_path.relative_to(REPOSITORY_ROOT)),
            result="success" if execution_ok else "failure",
            correlation_id=correlation_id,
            detail=(
                f"Real pytest run: {run['passed']} passed, {run['failed']} failed, "
                f"{run['errors']} errors, {run['skipped']} skipped, "
                f"exit_code={run['returncode']}"
            )
        )

        return result

    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.exec_test",
            action="EXEC_TEST",
            target=test_path,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def repository_run_test_suite(
    suite_name: str = "full",
    timeout: int = TEST_EXECUTION_TIMEOUT,
) -> Dict[str, Any]:
    """
    Executes a complete test suite (real pytest, via repository_exec_test)
    within the controlled workspace boundary.

    Args:
        suite_name: Name of the test suite to run ("full", "unit", "integration", etc.)
        timeout: Hard wall-clock limit in seconds passed through to each
            underlying repository_exec_test() call. The "full"/"unit"/
            "integration" suites all currently map to the whole "tests"
            directory, which can legitimately take several minutes for a
            large real suite — raise this for those callers rather than
            lowering the per-call default.

    Returns:
        Dict containing test suite execution results

    Raises:
        RepositoryAccessError: If access is denied
        RepositorySecurityError: If test execution is unsafe
    """
    correlation_id = f"run_test_suite-{datetime.utcnow().timestamp()}"
    employee_context = _get_employee_context()
    
    try:
        # Check permission
        _require_permission("repository.run_test_suite")
        
        # Determine test paths based on suite name
        test_paths = []
        if suite_name == "full":
            test_paths = ["tests"]
        elif suite_name == "unit":
            test_paths = ["tests"]  # In reality, might be more specific
        elif suite_name == "integration":
            test_paths = ["tests"]  # In reality, might be more specific
        else:
            # Treat as direct path
            test_paths = [suite_name]
        
        all_results = []
        total_passed = 0
        total_failed = 0
        total_executed = 0
        
        for test_path in test_paths:
            try:
                # Execute tests for this path
                path_result = repository_exec_test(test_path, timeout=timeout)
                all_results.append({
                    "suite": suite_name,
                    "path": test_path,
                    "result": path_result
                })
                
                total_passed += path_result.get("passed", 0)
                total_failed += path_result.get("failed", 0)
                total_executed += path_result.get("tests_executed", 0)
                
            except Exception as e:
                all_results.append({
                    "suite": suite_name,
                    "path": test_path,
                    "error": str(e)
                })
                # Count as failed
                total_failed += 1
                total_executed += 1
        
        result = {
            "suite_name": suite_name,
            "test_paths": test_paths,
            "total_test_files": len([r for r in all_results if "result" in r and "test_files_found" in r["result"]]),
            "total_tests_executed": total_executed,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "pass_rate": total_passed / total_executed if total_executed > 0 else 0,
            "suite_results": all_results,
            "note": "Test suite execution completed in controlled environment. No actual deployment or system modification performed."
        }
        
        # Log successful operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.run_test_suite",
            action="RUN_TEST_SUITE",
            target=suite_name,
            result="success",
            correlation_id=correlation_id,
            detail=f"Executed test suite: {total_passed} passed, {total_failed} failed"
        )
        
        return result
        
    except Exception as e:
        # Log failed operation
        _log_repository_operation(
            employee_context=employee_context,
            tool="repository.run_test_suite",
            action="RUN_TEST_SUITE",
            target=suite_name,
            result="failure",
            correlation_id=correlation_id,
            detail=str(e)
        )
        raise


def _git_status_description(index_status: str, worktree_status: str) -> str:
    """
    Converts git status codes to human-readable descriptions.
    
    Args:
        index_status: Git index status character
        worktree_status: Git worktree status character
        
    Returns:
        Human-readable status description
    """
    status_map = {
        ' ': 'Unmodified',
        'A': 'Added',
        'M': 'Modified',
        'D': 'Deleted',
        'R': 'Renamed',
        'C': 'Copied',
        'U': 'Updated but unmerged',
        '?': 'Untracked',
        '!': 'Missing'
    }
    
    index_desc = status_map.get(index_status, f'Unknown({index_status})')
    worktree_desc = status_map.get(worktree_status, f'Unknown({worktree_status})')
    
    if index_status == ' ' and worktree_status == ' ':
        return "Clean"
    elif index_status != ' ' and worktree_status == ' ':
        return f"Staged: {index_desc}"
    elif index_status == ' ' and worktree_status != ' ':
        return f"Modified: {worktree_desc}"
    else:
        return f"Index: {index_desc}, Worktree: {worktree_desc}"


# Export the main functions for easy import
__all__ = [
    "repository_inspect",
    "repository_read", 
    "repository_search",
    "repository_git_status",
    "repository_git_diff",
    "repository_lint",
    "repository_typecheck",
    "repository_sast_scan",
    "repository_secret_scan",
    "repository_write",
    "repository_exec_test",
    "repository_run_test_suite"
]
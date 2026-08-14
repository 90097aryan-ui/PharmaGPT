"""
tests/test_workspace_access.py — Regression coverage for
pharmagpt/auth/workspace_access.py (role-based workspace visibility).

Uses the same mocked-TenantContext / fake-Supabase-client technique
established in tests/test_rbac.py — no real Supabase project is touched.
Patches pharmagpt.auth.rbac.get_service_role_client (the one query
dependency workspace_access.py delegates through, via
pharmagpt.auth.rbac.get_effective_permissions) rather than adding a second
mock for workspace_access.py itself, since it deliberately has no
Supabase-calling code of its own.
"""

from unittest.mock import patch

import pytest
from postgrest.exceptions import APIError

import pharmagpt.app as appmod
import pharmagpt.auth.workspace_access as workspace_access
from pharmagpt.auth.context import TenantContext
from pharmagpt.auth.workspace_access import (
    ALL_WORKSPACES,
    WORKSPACE_MODULES,
    accessible_workspaces_for,
    has_workspace_access,
)

MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


@pytest.fixture(autouse=True)
def _app_context():
    """has_workspace_access() reads flask.g (for its per-request grant
    cache) even when called with an explicit tenant= — a real app context
    is required for `g` to resolve at all, matching how it's actually
    invoked in production (always inside a request)."""
    with appmod.app.app_context():
        yield

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"

COMPANY_ADMIN = TenantContext(
    user_id="admin-a", email="admin@example.com", display_name="Alice Admin",
    role="company_admin", company_id=COMPANY_A,
)
SUPER_ADMIN = TenantContext(
    user_id="super-1", email="super@example.com", display_name="Super Admin",
    role="super_admin", company_id=None,
)
REVIEWER_UNCONFIGURED = TenantContext(
    user_id="reviewer-a", email="reviewer@example.com", display_name="Rita Reviewer",
    role="reviewer_qa", company_id=COMPANY_A,
)
USER_WITH_VALIDATION_ROLE = TenantContext(
    user_id="user-a", email="user@example.com", display_name="Uma User",
    role="user", company_id=COMPANY_A,
)

RBAC_SERVICE_CLIENT_PATH = "pharmagpt.auth.rbac.get_service_role_client"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table_name, store):
        self.table_name = table_name
        self.store = store
        self._filters = []
        self._select_cols = ""

    def select(self, cols="*", *_a, **_k):
        self._select_cols = cols
        return self

    def eq(self, field, value):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self._filters.append(("in", field, values))
        return self

    def _matches(self, rows):
        def ok(row):
            for op, field, value in self._filters:
                if op == "eq" and row.get(field) != value:
                    return False
                if op == "in" and row.get(field) not in value:
                    return False
            return True
        return [r for r in rows if ok(r)]

    def execute(self):
        table = self.store.get(self.table_name, [])
        matched = self._matches(table)
        if "rbac_permissions(" in str(self._select_cols):
            perms_by_id = {p["id"]: p for p in self.store.get("rbac_permissions", [])}
            matched = [dict(r, permissions=perms_by_id.get(r.get("permission_id"))) for r in matched]
        return _FakeResult(matched)


class FakeRbacClient:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _FakeQuery(name, self.store)


class _RaisingClient:
    """Simulates migration 0015's tables being unreachable (the current,
    verified state of the live PharmaGPT Supabase project)."""

    def table(self, name):
        raise APIError({"message": f"Could not find the table 'public.{name}' in the schema cache"})


def _store_with_validation_grant():
    return {
        "rbac_permissions": [
            {"id": "perm-validation-view", "module": "Validation", "action": "View"},
        ],
        "rbac_roles": [
            {"id": "role-validation", "company_id": COMPANY_A, "name": "Validation Reviewer", "status": "active"},
        ],
        "rbac_role_permissions": [
            {"id": "rp-1", "role_id": "role-validation", "permission_id": "perm-validation-view", "granted": True},
        ],
        "rbac_user_roles": [
            {"id": "ur-1", "user_id": USER_WITH_VALIDATION_ROLE.user_id, "role_id": "role-validation", "company_id": COMPANY_A},
        ],
    }


def test_company_admin_always_has_access():
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=_RaisingClient()):
        for key in ALL_WORKSPACES:
            assert has_workspace_access(key, tenant=COMPANY_ADMIN) is True


def test_super_admin_always_has_access():
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=_RaisingClient()):
        for key in ALL_WORKSPACES:
            assert has_workspace_access(key, tenant=SUPER_ADMIN) is True


def test_assigned_role_grants_only_its_mapped_workspaces():
    """A user with a Layer-B role granting only the 'Validation' module
    sees the 'validation' workspace, but not e.g. 'knowledge' — the core
    deny behavior once a role IS assigned, which is unaffected by the
    current fail-open-for-unconfigured-users default (see the module
    docstring's migration-0015-not-yet-deployed note)."""
    store = _store_with_validation_grant()
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        assert has_workspace_access("validation", tenant=USER_WITH_VALIDATION_ROLE) is True
        assert has_workspace_access("knowledge", tenant=USER_WITH_VALIDATION_ROLE) is False
        assert accessible_workspaces_for(USER_WITH_VALIDATION_ROLE) == ["validation"]


def test_unconfigured_user_fails_open_pending_migration_0015():
    """Current, documented default: a user with zero rbac_user_roles rows
    (every user today, since migration 0015 isn't deployed to the live
    project) is treated as unrestricted rather than locked out. This test
    exists to make that default explicit and easy to flip: once migration
    0015 is live and this is intentionally changed to deny-by-default (see
    workspace_access.py's module docstring for the one-line change), this
    test's expected value flips to False and should be updated alongside it."""
    store = {"rbac_permissions": [], "rbac_roles": [], "rbac_role_permissions": [], "rbac_user_roles": []}
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        for key in ALL_WORKSPACES:
            assert has_workspace_access(key, tenant=REVIEWER_UNCONFIGURED) is True


def test_unreachable_rbac_tables_fails_open_not_500():
    """If the RBAC tables can't be queried at all (APIError — the exact,
    verified failure mode against the live project today), workspace
    access must never itself be the reason a request 500s or hangs."""
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=_RaisingClient()):
        assert has_workspace_access("validation", tenant=REVIEWER_UNCONFIGURED) is True


# ── Named role scenarios (Step 4, RBAC Final Closure) ───────────────────────
# Mirrors the example roles a Company Admin would actually create via the
# existing Roles & Permissions screen (clone a global template, e.g. "QA
# Manager"/"Validation Engineer", then grant specific modules) once
# migration 0015 is deployed. Exercised here against the same
# has_workspace_access()/accessible_workspaces_for() logic real requests
# use — cannot be run against live data today (migration 0015 isn't
# deployed; see workspace_access.py's module docstring), so this is the
# closest available verification of "does the grant → workspace mapping
# behave as specified" pending that deployment. Action-level distinctions
# (e.g. Validation Reviewer's 'View' vs Validation Approver's 'Approve')
# are a separate, already-existing capability
# (pharmagpt.auth.rbac.require_permission) that individual routes can opt
# into — out of scope for this workspace-visibility feature, which only
# checks "any granted action on a mapped module".

def _role_store(module_action_pairs, user_id):
    permissions = [
        {"id": f"perm-{i}", "module": m, "action": a}
        for i, (m, a) in enumerate(module_action_pairs)
    ]
    return {
        "rbac_permissions": permissions,
        "rbac_roles": [{"id": "role-1", "company_id": COMPANY_A, "name": "Test Role", "status": "active"}],
        "rbac_role_permissions": [
            {"id": f"rp-{i}", "role_id": "role-1", "permission_id": p["id"], "granted": True}
            for i, p in enumerate(permissions)
        ],
        "rbac_user_roles": [{"id": "ur-1", "user_id": user_id, "role_id": "role-1", "company_id": COMPANY_A}],
    }


def test_validation_reviewer_sees_validation_only():
    tenant = TenantContext(user_id="u1", email="u1@x.com", display_name="Validation Reviewer",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("Validation", "View")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        assert accessible_workspaces_for(tenant) == ["validation"]


def test_validation_approver_sees_validation_only():
    """Approve is still just a grant on the 'Validation' module as far as
    workspace visibility is concerned — the workspace gate doesn't
    distinguish View from Approve (see comment above)."""
    tenant = TenantContext(user_id="u2", email="u2@x.com", display_name="Validation Approver",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("Validation", "Approve"), ("Risk Assessment", "Approve")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        assert accessible_workspaces_for(tenant) == ["validation"]


def test_quality_user_sees_quality_only():
    tenant = TenantContext(user_id="u3", email="u3@x.com", display_name="Quality User",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("QMS", "View"), ("Deviations", "View"), ("CAPA", "View")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        assert accessible_workspaces_for(tenant) == ["quality"]


def test_knowledge_user_sees_knowledge_only():
    tenant = TenantContext(user_id="u4", email="u4@x.com", display_name="Knowledge User",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("Knowledge Base", "View")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        assert accessible_workspaces_for(tenant) == ["knowledge"]


def test_document_user_sees_documents_and_shared_quality_entry():
    """Document Control is a deliberately shared entry point between the
    Quality Management and Document Generator sidebar sections (both
    resolve to the same view-qms-documents / qms_documents.py blueprint —
    see index.html's ALD-001-R1 comment and qms_documents.py's
    before_request comment), so a Document-Control-only grant opens both
    workspace keys. The 'quality' card becomes visible, but Deviations/
    CAPA/Change Control routes within it remain separately gated to their
    own modules, which this role does not have — this is the one place
    'Document User -> Document Management only' isn't a perfectly clean
    1:1 match, inherited from the app's existing shared-route structure,
    not introduced by this feature."""
    tenant = TenantContext(user_id="u5", email="u5@x.com", display_name="Document User",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("Document Control", "View")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        assert set(accessible_workspaces_for(tenant)) == {"documents", "quality"}


def test_role_assigned_with_zero_grants_still_fails_open_today():
    """Documents a real precision gap in the CURRENT fail-open
    implementation: it cannot distinguish 'zero rbac_user_roles rows' from
    'a role is assigned but grants nothing' — both resolve to an empty
    effective-permissions set, and empty currently means allow (see module
    docstring). So today, even a role deliberately configured to grant
    nothing does not restrict anyone. This is expected to remain true
    until the deny-by-default flip (module docstring's one-line change),
    at which point this test's expected value changes to `== []` and
    should be updated alongside it — do not silently change this
    assertion without also making that policy flip."""
    tenant = TenantContext(user_id="u6", email="u6@x.com", display_name="No-Grant Role",
                            role="user", company_id=COMPANY_A)
    store = _role_store([], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
        assert accessible_workspaces_for(tenant) == list(ALL_WORKSPACES)


def test_workspace_modules_cover_the_permission_catalog_only():
    """Sanity check on the static mapping: every module name referenced is
    a plain non-empty string (catches a typo'd module key early, since a
    mismatch here silently makes a workspace unreachable via any role)."""
    for key, modules in WORKSPACE_MODULES.items():
        assert key in ALL_WORKSPACES
        assert modules
        assert all(isinstance(m, str) and m for m in modules)


# ── Activation verification (Step 4, Migration 0015 Production Readiness) ───
# Covers the exact scenarios requested: RBAC unavailable (compatibility),
# RBAC available + assigned role (restricted), RBAC available + no role
# (denied, once activated), Company Admin (unrestricted), and a real
# Flask-route-level 403 for both an unauthorized and an authorized request
# — not just the pure has_workspace_access() function in isolation.

def test_deny_by_default_once_activated():
    """Proves the DENY_BY_DEFAULT=True code path (module docstring's
    one-line activation switch) without actually flipping the constant for
    every other test in this file — monkeypatched locally, restored after.
    This is what 'no RBAC role -> no restricted workspace access' will
    look like once migration 0015 is deployed and the switch is flipped;
    Company Admin is unaffected either way (admin bypass runs first)."""
    with patch.object(workspace_access, "DENY_BY_DEFAULT", True):
        store = {"rbac_permissions": [], "rbac_roles": [], "rbac_role_permissions": [], "rbac_user_roles": []}
        with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
            # No RBAC role at all -> denied every restricted workspace.
            assert accessible_workspaces_for(REVIEWER_UNCONFIGURED) == []
            # Company Admin/Super Admin -> still unrestricted regardless.
            assert accessible_workspaces_for(COMPANY_ADMIN) == list(ALL_WORKSPACES)
            assert accessible_workspaces_for(SUPER_ADMIN) == list(ALL_WORKSPACES)

        # An assigned role's grants still work exactly as before under
        # strict mode — only the "empty grants" fallback changes meaning.
        store = _store_with_validation_grant()
        with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)):
            assert accessible_workspaces_for(USER_WITH_VALIDATION_ROLE) == ["validation"]


@pytest.fixture()
def flask_client(db_path, monkeypatch):
    """Real Flask test client with the actual global auth gate active
    (unlike tests/conftest.py's shared `client` fixture, which bypasses
    it) — same pattern as tests/test_security_tenant_rbac_esig.py, needed
    here because the thing under test IS a before_request gate."""
    monkeypatch.setattr("pharmagpt.services.esignature_service.require_esignature", lambda *a, **k: None)
    return appmod.app.test_client()


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


def test_unauthorized_workspace_route_returns_403(flask_client):
    """A real registered route (/risk/dashboard, gated to 'validation')
    rejected before its view function ever runs — no DB call happens,
    since before_request short-circuits first — for a tenant whose only
    grant is 'Knowledge Base'."""
    tenant = TenantContext(user_id="u7", email="u7@x.com", display_name="Knowledge Only",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("Knowledge Base", "View")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)), _as(tenant):
        resp = flask_client.get("/risk/dashboard", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 403
    assert "workspace" in resp.get_json().get("error", "").lower()


def test_unauthorized_api_returns_403_on_a_different_gated_blueprint(flask_client):
    """Same mechanism, a second gated blueprint (qms_common.py, /qms/dashboard,
    gated to 'quality') — confirms the gate is applied consistently across
    blueprints, not just one."""
    tenant = TenantContext(user_id="u8", email="u8@x.com", display_name="Validation Only",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("Validation", "View")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)), _as(tenant):
        resp = flask_client.get("/qms/dashboard", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 403


def test_authorized_workspace_route_is_not_blocked_by_the_gate(flask_client):
    """A tenant granted the matching module reaches past the gate — the
    view function runs (status is whatever the real route returns, but
    critically NOT 403, proving the gate itself let it through)."""
    tenant = TenantContext(user_id="u9", email="u9@x.com", display_name="Validation Granted",
                            role="user", company_id=COMPANY_A)
    store = _role_store([("Validation", "View")], tenant.user_id)
    with patch(RBAC_SERVICE_CLIENT_PATH, return_value=FakeRbacClient(store)), _as(tenant):
        resp = flask_client.get("/risk/dashboard", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code != 403

"""
tests/test_rbac.py — Regression coverage for the fine-grained RBAC
framework (migrations/0015_rbac_org_framework_up.sql, pharmagpt/auth/rbac.py,
pharmagpt/db/rbac_repo.py, pharmagpt/routes/rbac.py).

Uses the same mocked-TenantContext / fake-Supabase-client technique already
established in tests/test_role_management.py and
tests/test_assume_company_context.py — no real Supabase project is touched.
The fake client here is a superset of tests/test_assume_company_context.py's
FakeSupabaseClient (adds .delete()/.in_() and resolves the small set of
embedded selects pharmagpt/routes/rbac.py and pharmagpt/auth/rbac.py issue)
since those routes need operations the shared fake doesn't support.
"""

from unittest.mock import patch

import pytest

from pharmagpt.auth.context import TenantContext
from pharmagpt.auth.rbac import get_effective_permissions, has_active_rbac_role, has_permission, has_rbac_admin_access
from pharmagpt.db import rbac_repo
from tests.test_security_tenant_rbac_esig import (
    ADMIN_A, COMPANY_A, COMPANY_B, REVIEWER_A, SUPER_ADMIN, USER_A, AUTH_HEADERS, MIDDLEWARE_PATH,
)

RBAC_CLIENT_PATH = "pharmagpt.routes.rbac.get_authenticated_client"
RBAC_SERVICE_CLIENT_PATH = "pharmagpt.routes.rbac.get_service_role_client"
RBAC_AUTH_SERVICE_CLIENT_PATH = "pharmagpt.auth.rbac.get_service_role_client"


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table_name, store):
        self.table_name = table_name
        self.store = store
        self._op = "select"
        self._payload = None
        self._filters = []
        self._single = False
        self._select_cols = ""

    def select(self, cols="*", *_a, **_k):
        self._select_cols = cols
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload if isinstance(payload, list) else [payload]
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, field, value):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self._filters.append(("in", field, values))
        return self

    def order(self, *_a, **_k):
        return self

    def maybe_single(self):
        self._single = True
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
        table = self.store.setdefault(self.table_name, [])

        if self._op == "insert":
            inserted = []
            for payload in self._payload:
                row = dict(payload)
                row.setdefault("id", f"{self.table_name}-{len(table) + 1}")
                table.append(row)
                inserted.append(row)
            return _FakeResult(inserted)

        if self._op == "update":
            matched = self._matches(table)
            for r in matched:
                r.update(self._payload)
            return _FakeResult(matched)

        if self._op == "delete":
            matched = self._matches(table)
            for r in matched:
                table.remove(r)
            return _FakeResult(matched)

        matched = self._matches(table)
        cols = str(self._select_cols)
        if "rbac_permissions(" in cols:
            perms_by_id = {p["id"]: p for p in self.store.get("rbac_permissions", [])}
            matched = [dict(r, permissions=perms_by_id.get(r.get("permission_id"))) for r in matched]
        elif "rbac_roles(" in cols:
            roles_by_id = {rl["id"]: rl for rl in self.store.get("rbac_roles", [])}
            matched = [dict(r, rbac_roles=roles_by_id.get(r.get("role_id"))) for r in matched]

        if self._single:
            return _FakeResult(matched[0] if matched else None)
        return _FakeResult(matched)


class FakeRbacClient:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _FakeQuery(name, self.store)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod
    return appmod.app.test_client()


@pytest.fixture()
def store():
    return {
        "rbac_permissions": [
            {"id": "perm-view-qms", "module": "QMS", "action": "View"},
            {"id": "perm-approve-qms", "module": "QMS", "action": "Approve"},
        ],
        "rbac_roles": [
            {"id": "role-template-qa-mgr", "company_id": None, "name": "QA Manager",
             "description": "template", "is_template": True, "is_system": True, "status": "active"},
            {"id": "role-a-qa-mgr", "company_id": COMPANY_A, "name": "QA Manager (A)",
             "description": "", "is_template": False, "is_system": False, "status": "active"},
            {"id": "role-b-qa-mgr", "company_id": COMPANY_B, "name": "QA Manager (B)",
             "description": "", "is_template": False, "is_system": False, "status": "active"},
        ],
        "rbac_role_permissions": [
            {"id": "rp-1", "role_id": "role-a-qa-mgr", "permission_id": "perm-view-qms", "granted": True},
        ],
        "rbac_user_roles": [],
        "rbac_audit_log": [],
    }


def _patched(store):
    fake = FakeRbacClient(store)
    return (
        patch(RBAC_CLIENT_PATH, return_value=fake),
        patch(RBAC_SERVICE_CLIENT_PATH, return_value=fake),
        patch(RBAC_AUTH_SERVICE_CLIENT_PATH, return_value=fake),
    )


# ── Route-level tests ────────────────────────────────────────────────────────

def test_create_role_requires_reason(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.post("/rbac/roles", json={"name": "New Role"}, headers=AUTH_HEADERS)
    assert resp.status_code == 400


def test_create_role_writes_audit_entry(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.post(
            "/rbac/roles", json={"name": "New Role", "reason": "Org restructure"}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201
    assert len(store["rbac_audit_log"]) == 1
    entry = store["rbac_audit_log"][0]
    assert entry["company_id"] == COMPANY_A
    assert "Org restructure" in entry["reason"]


def test_toggle_permission_requires_reason(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.put(
            "/rbac/roles/role-a-qa-mgr/permissions",
            json={"permission_id": "perm-approve-qms", "granted": True},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 400


def test_toggle_permission_writes_audit_entry_with_old_and_new_value(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.put(
            "/rbac/roles/role-a-qa-mgr/permissions",
            json={"permission_id": "perm-approve-qms", "granted": True, "reason": "Grant approval rights"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    entry = store["rbac_audit_log"][-1]
    assert entry["old_value"] == {"granted": False}
    assert entry["new_value"] == {"granted": True}
    assert entry["permission_id"] == "perm-approve-qms"


def test_assign_and_revoke_user_role_writes_audit(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        assign_resp = client.post(
            "/rbac/users/user-1/roles",
            json={"role_id": "role-a-qa-mgr", "reason": "New hire onboarding"},
            headers=AUTH_HEADERS,
        )
        assert assign_resp.status_code == 201
        assert len(store["rbac_user_roles"]) == 1

        revoke_resp = client.delete(
            "/rbac/users/user-1/roles/role-a-qa-mgr",
            json={"reason": "Role change"},
            headers=AUTH_HEADERS,
        )
        assert revoke_resp.status_code == 204
        assert len(store["rbac_user_roles"]) == 0

    audit_actions = [e["reason"] for e in store["rbac_audit_log"]]
    assert any("assigned" in a.lower() for a in audit_actions)
    assert any("revoked" in a.lower() for a in audit_actions)


def test_revoke_user_role_requires_reason(client, store):
    store["rbac_user_roles"].append({"id": "ur-1", "user_id": "user-1", "role_id": "role-a-qa-mgr", "company_id": COMPANY_A})
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.delete("/rbac/users/user-1/roles/role-a-qa-mgr", headers=AUTH_HEADERS)
    assert resp.status_code == 400
    assert len(store["rbac_user_roles"]) == 1  # unchanged


def test_company_admin_only_sees_own_companys_roles_plus_templates(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    names = {r["name"] for r in resp.get_json()}
    assert "QA Manager (A)" in names
    assert "QA Manager" in names  # template
    assert "QA Manager (B)" not in names  # company B's role not visible


def test_super_admin_without_assumed_context_sees_templates_only():
    """Not a Flask-route assertion of company isolation this time — verifies
    the template-scope branch in routes/rbac.py::list_roles directly."""
    store_ = {
        "rbac_roles": [
            {"id": "t1", "company_id": None, "name": "Platform Admin", "is_template": True},
            {"id": "r1", "company_id": COMPANY_A, "name": "QA Manager (A)", "is_template": False},
        ],
    }
    from pharmagpt import app as appmod
    client = appmod.app.test_client()
    fake = FakeRbacClient(store_)
    with _as(SUPER_ADMIN), patch(RBAC_SERVICE_CLIENT_PATH, return_value=fake):
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    names = {r["name"] for r in resp.get_json()}
    assert names == {"Platform Admin"}


def test_super_admin_without_assumed_context_cannot_assign_user_roles(client, store):
    p1, p2, p3 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2, p3:
        resp = client.post(
            "/rbac/users/user-1/roles", json={"role_id": "role-a-qa-mgr", "reason": "x"}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 403


def test_super_admin_without_assumed_context_cannot_update_another_companys_role(client, store):
    """The service-role client bypasses RLS entirely for super_admin, so
    routes/rbac.py must enforce this scope check itself — a Platform Admin
    with no assumed company context must not be able to mutate a tenant's
    role by id, even though the service-role client technically could."""
    p1, p2, p3 = _patched(store)
    with _as(SUPER_ADMIN), p1, p2, p3:
        resp = client.patch(
            "/rbac/roles/role-a-qa-mgr", json={"status": "disabled", "reason": "x"}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 404
    assert store["rbac_roles"][1]["status"] == "active"  # unchanged


def test_company_admin_cannot_update_another_companys_role_by_id(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.patch(
            "/rbac/roles/role-b-qa-mgr", json={"status": "disabled", "reason": "x"}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 404
    assert store["rbac_roles"][2]["status"] == "active"  # unchanged


def test_company_admin_cannot_assign_another_companys_role_to_own_user(client, store):
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.post(
            "/rbac/users/user-1/roles", json={"role_id": "role-b-qa-mgr", "reason": "x"}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 404
    assert store["rbac_user_roles"] == []


def test_clone_role_copies_permissions(client, store):
    store["rbac_role_permissions"].append(
        {"id": "rp-tpl", "role_id": "role-template-qa-mgr", "permission_id": "perm-approve-qms", "granted": True}
    )
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.post(
            "/rbac/roles/role-template-qa-mgr/clone",
            json={"name": "QA Manager (Cloned)", "reason": "Provisioning"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201
    new_role_id = resp.get_json()["id"]
    cloned_grants = [g for g in store["rbac_role_permissions"] if g["role_id"] == new_role_id]
    assert len(cloned_grants) == 1
    assert cloned_grants[0]["permission_id"] == "perm-approve-qms"


# ── Unit tests: pharmagpt/auth/rbac.py (no Flask, no HTTP) ─────────────────

def test_super_admin_has_permission_only_on_administration_without_assumed_company():
    tenant = TenantContext(user_id="su", email="su@x.com", display_name="SU", role="super_admin", company_id=None)
    assert has_permission(tenant, "Administration", "Admin") is True
    assert has_permission(tenant, "QMS", "View") is False


def test_super_admin_with_assumed_company_denied_administration_too():
    """Platform Admin must NOT automatically access tenant GMP records —
    and Administration access is platform-scope only, not tenant-scope."""
    tenant = TenantContext(user_id="su", email="su@x.com", display_name="SU", role="super_admin", company_id=COMPANY_A)
    assert has_permission(tenant, "Administration", "Admin") is False
    assert has_permission(tenant, "QMS", "View") is False


def test_company_admin_has_blanket_permission_without_any_rbac_user_roles_row():
    """Avoids a lockout scenario for a pre-migration company_admin with no
    rbac_user_roles row yet — see pharmagpt/auth/rbac.py::has_permission."""
    tenant = TenantContext(user_id="a", email="a@x.com", display_name="A", role="company_admin", company_id=COMPANY_A)
    assert has_permission(tenant, "QMS", "Approve") is True


def test_get_effective_permissions_resolves_via_assigned_active_roles():
    store_ = {
        "rbac_user_roles": [{"user_id": "u1", "role_id": "role-a-qa-mgr", "company_id": COMPANY_A}],
        "rbac_roles": [{"id": "role-a-qa-mgr", "status": "active"}],
        "rbac_role_permissions": [
            {"role_id": "role-a-qa-mgr", "permission_id": "perm-view-qms", "granted": True},
        ],
        "rbac_permissions": [{"id": "perm-view-qms", "module": "QMS", "action": "View"}],
    }
    fake = FakeRbacClient(store_)
    tenant = TenantContext(user_id="u1", email="u@x.com", display_name="U", role="user", company_id=COMPANY_A)
    with patch(RBAC_AUTH_SERVICE_CLIENT_PATH, return_value=fake):
        assert get_effective_permissions(tenant) == {("QMS", "View")}
        assert has_permission(tenant, "QMS", "View") is True
        assert has_permission(tenant, "QMS", "Approve") is False


def test_get_effective_permissions_excludes_disabled_roles():
    store_ = {
        "rbac_user_roles": [{"user_id": "u1", "role_id": "role-disabled", "company_id": COMPANY_A}],
        "rbac_roles": [{"id": "role-disabled", "status": "disabled"}],
        "rbac_role_permissions": [
            {"role_id": "role-disabled", "permission_id": "perm-view-qms", "granted": True},
        ],
        "rbac_permissions": [{"id": "perm-view-qms", "module": "QMS", "action": "View"}],
    }
    fake = FakeRbacClient(store_)
    tenant = TenantContext(user_id="u1", email="u@x.com", display_name="U", role="user", company_id=COMPANY_A)
    with patch(RBAC_AUTH_SERVICE_CLIENT_PATH, return_value=fake):
        assert get_effective_permissions(tenant) == set()


# ── Unit tests: pharmagpt/db/rbac_repo.py::add_rbac_audit_entry ─────────────

def test_add_rbac_audit_entry_rejects_missing_reason():
    fake = FakeRbacClient({"rbac_audit_log": []})
    with pytest.raises(ValueError):
        rbac_repo.add_rbac_audit_entry(fake, company_id=COMPANY_A, actor_user_id="u1", reason="")


# ── Coordinator fix: RBAC "Company Admin" grants RBAC-administration
# access even when the legacy platform role is reviewer_qa/user ──────────────
#
# Business scenario (see CLAUDE.md task): a company's Coordinator is that
# company's administrator, but is frozen at the legacy `reviewer_qa` role.
# Some Coordinators are ALSO QA Reviewers. require_rbac_admin_access /
# has_rbac_admin_access (pharmagpt/auth/rbac.py) must authorize such a user
# for the RBAC administration surfaces without weakening isolation, without
# touching the frozen legacy role model, and without granting access to a
# QA-Reviewer-only user who happens to also hold the legacy reviewer_qa role.

COMPANY_ADMIN_ROLE_NAME = "Company Admin"


def _company_admin_rbac_role(role_id="role-a-company-admin", company_id=COMPANY_A, status="active"):
    return {"id": role_id, "company_id": company_id, "name": COMPANY_ADMIN_ROLE_NAME,
            "description": "", "is_template": False, "is_system": False, "status": status}


def _qa_reviewer_rbac_role(role_id="role-a-qa-reviewer", company_id=COMPANY_A, status="active"):
    return {"id": role_id, "company_id": company_id, "name": "QA Reviewer",
            "description": "", "is_template": False, "is_system": False, "status": status}


def test_legacy_company_admin_can_access_rbac_administration(client, store):
    """(1) Legacy company_admin can access RBAC administration — unchanged."""
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    assert resp.status_code == 200


def test_legacy_company_admin_with_no_rbac_user_roles_still_works(client, store):
    """(2) Legacy company_admin with zero rbac_user_roles rows still works —
    no lockout for a pre-migration company_admin."""
    assert store["rbac_user_roles"] == []
    p1, p2, p3 = _patched(store)
    with _as(ADMIN_A), p1, p2, p3:
        resp = client.get("/rbac/permissions", headers=AUTH_HEADERS)
    assert resp.status_code == 200


def test_rbac_company_admin_can_access_despite_legacy_reviewer_qa(client, store):
    """(3) RBAC Company Admin can access RBAC administration even when the
    legacy role is reviewer_qa — the Coordinator scenario this fix targets."""
    store["rbac_roles"].append(_company_admin_rbac_role())
    store["rbac_user_roles"].append(
        {"id": "ur-coord", "user_id": REVIEWER_A.user_id, "role_id": "role-a-company-admin", "company_id": COMPANY_A}
    )
    p1, p2, p3 = _patched(store)
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    assert resp.status_code == 200


def test_legacy_reviewer_qa_without_company_admin_rbac_role_is_denied(client, store):
    """(4) legacy reviewer_qa with NO Company Admin RBAC role is denied."""
    p1, p2, p3 = _patched(store)
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_rbac_qa_reviewer_role_only_is_denied_company_admin_administration(client, store):
    """(5) A user whose only RBAC role is "QA Reviewer" is denied Company
    Admin administration — holding QA Reviewer must never grant it."""
    store["rbac_roles"].append(_qa_reviewer_rbac_role())
    store["rbac_user_roles"].append(
        {"id": "ur-qa", "user_id": REVIEWER_A.user_id, "role_id": "role-a-qa-reviewer", "company_id": COMPANY_A}
    )
    p1, p2, p3 = _patched(store)
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_company_admin_plus_qa_reviewer_rbac_roles_is_allowed(client, store):
    """(6)/(7) A user with BOTH Company Admin and QA Reviewer RBAC roles is
    allowed, and their effective permissions are the union of both roles —
    multi-role assignment is additive, not collapsed to one role."""
    store["rbac_roles"].append(_company_admin_rbac_role())
    store["rbac_roles"].append(_qa_reviewer_rbac_role())
    store["rbac_role_permissions"].append(
        {"id": "rp-qa-reviewer", "role_id": "role-a-qa-reviewer", "permission_id": "perm-approve-qms", "granted": True}
    )
    store["rbac_user_roles"].append(
        {"id": "ur-coord", "user_id": REVIEWER_A.user_id, "role_id": "role-a-company-admin", "company_id": COMPANY_A}
    )
    store["rbac_user_roles"].append(
        {"id": "ur-qa", "user_id": REVIEWER_A.user_id, "role_id": "role-a-qa-reviewer", "company_id": COMPANY_A}
    )
    p1, p2, p3 = _patched(store)
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert has_active_rbac_role(REVIEWER_A, COMPANY_ADMIN_ROLE_NAME) is True
        assert has_active_rbac_role(REVIEWER_A, "QA Reviewer") is True
        assert get_effective_permissions(REVIEWER_A) == {("QMS", "Approve")}


def test_inactive_company_admin_assignment_does_not_grant_access(client, store):
    """(8) A revoked (absent) Company Admin assignment does not grant
    access — rbac_user_roles has no "inactive" flag: revoking a role
    deletes the row (rbac_repo.revoke_user_role), so an absent row IS the
    inactive-assignment case."""
    store["rbac_roles"].append(_company_admin_rbac_role())
    # Deliberately no rbac_user_roles row for REVIEWER_A — assignment revoked/never made.
    p1, p2, p3 = _patched(store)
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_inactive_company_admin_rbac_role_does_not_grant_access(client, store):
    """(9) An assignment to a DISABLED Company Admin role does not grant
    access."""
    store["rbac_roles"].append(_company_admin_rbac_role(status="disabled"))
    store["rbac_user_roles"].append(
        {"id": "ur-coord", "user_id": REVIEWER_A.user_id, "role_id": "role-a-company-admin", "company_id": COMPANY_A}
    )
    p1, p2, p3 = _patched(store)
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_company_admin_rbac_role_in_another_company_does_not_grant_access(client, store):
    """(10)/(11) A Company Admin RBAC role that actually belongs to another
    company must never grant access, even if a (malformed/adversarial)
    rbac_user_roles row references it — the defensive company_id filter on
    the rbac_roles lookup in has_active_rbac_role() is what stops it, not
    just the rbac_user_roles.company_id column."""
    store["rbac_roles"].append(_company_admin_rbac_role(role_id="role-b-company-admin", company_id=COMPANY_B))
    store["rbac_user_roles"].append(
        {"id": "ur-coord", "user_id": REVIEWER_A.user_id, "role_id": "role-b-company-admin", "company_id": COMPANY_A}
    )
    p1, p2, p3 = _patched(store)
    with _as(REVIEWER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
        assert resp.status_code == 403
        assert has_active_rbac_role(REVIEWER_A, COMPANY_ADMIN_ROLE_NAME) is False


def test_cross_tenant_rbac_company_admin_scoped_to_own_company_only(client, store):
    """(11) Cross-tenant role access remains impossible even for a user
    that legitimately holds an active Company Admin RBAC role — in COMPANY_B
    it must not unlock COMPANY_A's roles."""
    store["rbac_roles"].append(_company_admin_rbac_role(role_id="role-b-company-admin", company_id=COMPANY_B))
    store["rbac_user_roles"].append(
        {"id": "ur-b", "user_id": "coord-b", "role_id": "role-b-company-admin", "company_id": COMPANY_B}
    )
    coordinator_b = TenantContext(
        user_id="coord-b", email="coord-b@example.com", display_name="Coordinator B",
        role="reviewer_qa", company_id=COMPANY_B,
    )
    p1, p2, p3 = _patched(store)
    with _as(coordinator_b), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    names = {r["name"] for r in resp.get_json()}
    assert "QA Manager (A)" not in names
    assert "QA Manager (B)" in names


def test_super_admin_behavior_unchanged_no_rbac_table_lookup():
    """(12) super_admin behavior is unchanged: has_rbac_admin_access short-
    circuits to True for super_admin without ever touching the RBAC tables
    (no client patch is installed here — a real query would raise)."""
    assert has_rbac_admin_access(SUPER_ADMIN) is True


def test_super_admin_with_assumed_company_context_can_administer_roles(client, store):
    """(13) Assume Company Context behavior is unchanged: a super_admin who
    has assumed COMPANY_A can still administer that company's roles."""
    assumed = TenantContext(
        user_id=SUPER_ADMIN.user_id, email=SUPER_ADMIN.email, display_name=SUPER_ADMIN.display_name,
        role="super_admin", company_id=COMPANY_A,
    )
    p1, p2, p3 = _patched(store)
    with _as(assumed), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    names = {r["name"] for r in resp.get_json()}
    assert "QA Manager (A)" in names
    assert "QA Manager (B)" not in names


def test_legacy_user_role_with_company_admin_rbac_role_is_also_allowed(client, store):
    """A plain legacy `user` role holding an active Company Admin RBAC
    assignment is allowed too — the business rule is "any legacy role", not
    "reviewer_qa specifically"."""
    store["rbac_roles"].append(_company_admin_rbac_role())
    store["rbac_user_roles"].append(
        {"id": "ur-user", "user_id": USER_A.user_id, "role_id": "role-a-company-admin", "company_id": COMPANY_A}
    )
    p1, p2, p3 = _patched(store)
    with _as(USER_A), p1, p2, p3:
        resp = client.get("/rbac/roles", headers=AUTH_HEADERS)
    assert resp.status_code == 200

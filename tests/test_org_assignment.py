"""
tests/test_org_assignment.py — Regression coverage for
pharmagpt/services/org_assignment.py (Yuktav org/RBAC/workflow
authorization task): the single call site tying migration 0014's
departments/user_departments/workflow_roles to migration 0015/0016's
rbac_roles/rbac_user_roles/rbac_audit_log, plus workflow-routing's
department + functional-role approver resolution.

Uses a small, purpose-built in-memory fake Supabase client (supports
upsert, unlike tests/test_rbac.py's FakeRbacClient) — no real Supabase
project is touched.
"""

from __future__ import annotations

import pytest

from pharmagpt.services import org_assignment

COMPANY_A = "11111111-1111-1111-1111-111111111111"
COMPANY_B = "22222222-2222-2222-2222-222222222222"


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
        self._order_field = None
        self._on_conflict = None

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload if isinstance(payload, list) else [payload]
        return self

    def delete(self):
        self._op = "delete"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def eq(self, field, value):
        self._filters.append((field, value))
        return self

    def order(self, field, *_a, **_k):
        self._order_field = field
        return self

    def maybe_single(self):
        self._single = True
        return self

    def _matches(self, rows):
        return [r for r in rows if all(r.get(f) == v for f, v in self._filters)]

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

        if self._op == "delete":
            matched = self._matches(table)
            table[:] = [r for r in table if r not in matched]
            return _FakeResult(matched)

        if self._op == "update":
            matched = self._matches(table)
            for r in matched:
                r.update(self._payload)
            return _FakeResult(matched)

        if self._op == "upsert":
            conflict_keys = (self._on_conflict or "id").split(",")
            existing = next(
                (r for r in table if all(r.get(k) == self._payload.get(k) for k in conflict_keys)), None,
            )
            if existing:
                existing.update(self._payload)
                return _FakeResult([existing])
            row = dict(self._payload)
            row.setdefault("id", f"{self.table_name}-{len(table) + 1}")
            table.append(row)
            return _FakeResult([row])

        matched = self._matches(table)
        if self._order_field:
            matched = sorted(matched, key=lambda r: r.get(self._order_field, ""))
        # Resolve the tiny set of embedded selects this module issues.
        if self.table_name == "user_departments":
            users_by_id = {u["id"]: u for u in self.store.get("users", [])}
            matched = [dict(r, users=users_by_id.get(r.get("user_id"))) for r in matched]

        if self._single:
            return _FakeResult(matched[0] if matched else None)
        return _FakeResult(matched)


class FakeOrgClient:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _FakeQuery(name, self.store)


@pytest.fixture()
def store():
    return {
        "departments": [
            {"id": "dept-a-production", "company_id": COMPANY_A, "department_code": "PRODUCTION"},
            {"id": "dept-a-qa", "company_id": COMPANY_A, "department_code": "QA"},
            {"id": "dept-b-production", "company_id": COMPANY_B, "department_code": "PRODUCTION"},
        ],
        "workflow_roles": [
            {"id": 1, "name": "Initiator"},
            {"id": 2, "name": "Coordinator"},
            {"id": 3, "name": "Reviewer"},
            {"id": 4, "name": "Approver"},
            {"id": 5, "name": "Plant Head"},
        ],
        "user_departments": [],
        "users": [
            {"id": "user-1", "display_name": "Rina Reviewer", "status": "active"},
            {"id": "user-2", "display_name": "Ida Inactive", "status": "deactivated"},
        ],
        "rbac_roles": [
            {"id": "role-a-prod-reviewer", "company_id": COMPANY_A, "name": "Production Reviewer",
             "is_template": False, "status": "active"},
            {"id": "role-a-qa-reviewer", "company_id": COMPANY_A, "name": "QA Reviewer",
             "is_template": False, "status": "active"},
        ],
        "rbac_user_roles": [],
        "rbac_audit_log": [],
    }


# ── assign_user_to_department ───────────────────────────────────────────────

def test_assign_user_to_department_requires_reason(store):
    client = FakeOrgClient(store)
    with pytest.raises(ValueError):
        org_assignment.assign_user_to_department(
            client, user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
            department_code="PRODUCTION", workflow_role_id=3, functional_role_name="Reviewer",
            is_primary=True, actor_user_id="admin-1", reason="",
        )


def test_assign_user_to_department_creates_membership_and_assigns_matching_rbac_role(store):
    client = FakeOrgClient(store)
    result = org_assignment.assign_user_to_department(
        client, user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
        department_code="PRODUCTION", workflow_role_id=3, functional_role_name="Reviewer",
        is_primary=True, actor_user_id="admin-1", reason="New hire onboarding",
    )

    assert result["membership"]["workflow_role_id"] == 3
    assert result["membership"]["is_primary"] is True
    assert result["rbac_role_assigned"]["name"] == "Production Reviewer"
    assert len(store["rbac_user_roles"]) == 1
    assert store["rbac_user_roles"][0]["role_id"] == "role-a-prod-reviewer"

    entry = store["rbac_audit_log"][-1]
    assert entry["target_user_id"] == "user-1"
    assert "Reviewer" in entry["reason"]
    assert "New hire onboarding" in entry["reason"]


class _UniqueRoleClient(FakeOrgClient):
    """Enforces rbac_user_roles UNIQUE (user_id, role_id) like migration 0015."""

    def table(self, name):
        q = super().table(name)
        if name != "rbac_user_roles":
            return q
        real_execute = q.execute

        def execute():
            if q._op == "insert":
                for p in q._payload:
                    if any(r["user_id"] == p["user_id"] and r["role_id"] == p["role_id"]
                           for r in self.store["rbac_user_roles"]):
                        raise RuntimeError("duplicate key value violates unique constraint uq_rbac_user_roles_user_role")
            return real_execute()
        q.execute = execute
        return q


def test_assign_when_user_already_holds_the_rbac_role_updates_membership_and_audits(store):
    """Regression: a user who already holds the matching RBAC role (e.g. provisioned
    before functional roles were stored on memberships) must still get the membership
    updated AND audited, not a unique violation after the membership committed."""
    store["rbac_user_roles"].append({"id": "x", "user_id": "user-1", "role_id": "role-a-prod-reviewer",
                                     "company_id": COMPANY_A})
    store["user_departments"].append({"user_id": "user-1", "department_id": "dept-a-production",
                                      "company_id": COMPANY_A, "workflow_role_id": None, "is_primary": True})
    result = org_assignment.assign_user_to_department(
        _UniqueRoleClient(store), user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
        department_code="PRODUCTION", workflow_role_id=3, functional_role_name="Reviewer",
        is_primary=True, actor_user_id="admin-1", reason="Approved ref QA-1")

    assert len(store["rbac_user_roles"]) == 1                       # no duplicate insert
    assert store["user_departments"][0]["workflow_role_id"] == 3     # membership updated
    assert store["user_departments"][0]["is_primary"] is True
    assert result["rbac_role_assigned"]["name"] == "Production Reviewer"
    entries = store["rbac_audit_log"]
    assert len(entries) == 1 and entries[0]["new_value"]["rbac_role_already_held"] is True
    assert "QA-1" in entries[0]["reason"]


def _failing_audit(*_a, **_k):
    raise RuntimeError("audit insert failed")


def test_audit_failure_restores_existing_membership_and_leaves_no_change(store, monkeypatch):
    """A failed audit write must not leave an unaudited membership change."""
    store["rbac_user_roles"].append({"id": "x", "user_id": "user-1", "role_id": "role-a-prod-reviewer",
                                     "company_id": COMPANY_A})
    store["user_departments"].append({"user_id": "user-1", "department_id": "dept-a-production",
                                      "company_id": COMPANY_A, "workflow_role_id": None, "is_primary": True})
    monkeypatch.setattr(org_assignment.rbac_repo, "add_rbac_audit_entry", _failing_audit)
    with pytest.raises(RuntimeError):
        org_assignment.assign_user_to_department(
            FakeOrgClient(store), user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
            department_code="PRODUCTION", workflow_role_id=3, functional_role_name="Reviewer",
            is_primary=True, actor_user_id="admin-1", reason="r")
    assert store["user_departments"][0]["workflow_role_id"] is None   # restored
    assert store["user_departments"][0]["is_primary"] is True         # is_primary preserved
    assert len(store["rbac_user_roles"]) == 1 and store["rbac_audit_log"] == []


def test_audit_failure_removes_new_membership_and_newly_inserted_role(store, monkeypatch):
    monkeypatch.setattr(org_assignment.rbac_repo, "add_rbac_audit_entry", _failing_audit)
    with pytest.raises(RuntimeError):
        org_assignment.assign_user_to_department(
            FakeOrgClient(store), user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
            department_code="PRODUCTION", workflow_role_id=3, functional_role_name="Reviewer",
            is_primary=False, actor_user_id="admin-1", reason="r")
    assert store["user_departments"] == []
    assert store["rbac_user_roles"] == []


def test_audit_entry_records_previous_membership_state(store):
    store["user_departments"].append({"user_id": "user-1", "department_id": "dept-a-production",
                                      "company_id": COMPANY_A, "workflow_role_id": None, "is_primary": False})
    org_assignment.assign_user_to_department(
        FakeOrgClient(store), user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
        department_code="PRODUCTION", workflow_role_id=3, functional_role_name="Reviewer",
        is_primary=False, actor_user_id="admin-1", reason="r")
    assert store["rbac_audit_log"][0]["old_value"] == {"workflow_role_id": None, "is_primary": False}


def test_assign_user_to_department_without_a_provisioned_rbac_role_still_creates_membership(store):
    """A department/role combination the company hasn't cloned a template
    for yet (e.g. provisioned before this task's 23 new templates existed)
    still succeeds at the org-membership level — rbac_role_assigned is None,
    not a hard failure."""
    client = FakeOrgClient(store)
    result = org_assignment.assign_user_to_department(
        client, user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
        department_code="PRODUCTION", workflow_role_id=1, functional_role_name="Initiator",
        is_primary=False, actor_user_id="admin-1", reason="New hire",
    )
    assert result["rbac_role_assigned"] is None
    assert store["rbac_user_roles"] == []
    assert result["membership"]["workflow_role_id"] == 1


def test_qa_reviewer_and_production_reviewer_assignments_are_independent(store):
    """The core "QA Reviewer != Production Reviewer" guarantee: the same
    user can hold Reviewer in two different departments, each resolving to
    its OWN rbac_roles row, not a single shared one."""
    client = FakeOrgClient(store)
    store["departments"].append(
        {"id": "dept-a-qa-2", "company_id": COMPANY_A, "department_code": "QA"}
    )
    org_assignment.assign_user_to_department(
        client, user_id="user-1", company_id=COMPANY_A, department_id="dept-a-production",
        department_code="PRODUCTION", workflow_role_id=3, functional_role_name="Reviewer",
        is_primary=True, actor_user_id="admin-1", reason="Primary dept",
    )
    org_assignment.assign_user_to_department(
        client, user_id="user-1", company_id=COMPANY_A, department_id="dept-a-qa",
        department_code="QA", workflow_role_id=3, functional_role_name="Reviewer",
        is_primary=False, actor_user_id="admin-1", reason="Secondary dept",
    )

    role_ids = {r["role_id"] for r in store["rbac_user_roles"]}
    assert role_ids == {"role-a-prod-reviewer", "role-a-qa-reviewer"}

    memberships = [m for m in store["user_departments"] if m["user_id"] == "user-1"]
    assert len(memberships) == 2  # multi-department membership
    primaries = [m for m in memberships if m.get("is_primary")]
    assert len(primaries) == 1  # exactly one primary department


# ── resolve_department_approver (workflow routing) ──────────────────────────

def test_resolve_department_approver_finds_active_holder(store):
    client = FakeOrgClient(store)
    store["user_departments"].append({
        "id": "ud-1", "user_id": "user-1", "company_id": COMPANY_A,
        "department_id": "dept-a-production", "workflow_role_id": 3, "created_at": "2026-01-01",
    })

    resolved = org_assignment.resolve_department_approver(client, COMPANY_A, "PRODUCTION", "Reviewer")

    assert resolved == {"user_id": "user-1", "display_name": "Rina Reviewer"}


def test_resolve_department_approver_skips_inactive_users(store):
    client = FakeOrgClient(store)
    store["user_departments"].append({
        "id": "ud-1", "user_id": "user-2", "company_id": COMPANY_A,
        "department_id": "dept-a-production", "workflow_role_id": 3, "created_at": "2026-01-01",
    })

    resolved = org_assignment.resolve_department_approver(client, COMPANY_A, "PRODUCTION", "Reviewer")

    assert resolved is None


def test_resolve_department_approver_returns_none_when_nobody_holds_the_combination(store):
    client = FakeOrgClient(store)
    resolved = org_assignment.resolve_department_approver(client, COMPANY_A, "PRODUCTION", "Approver")
    assert resolved is None


def test_resolve_department_approver_is_tenant_scoped(store):
    """Company A must never resolve to a Company B user, even if both
    companies happen to use the same department_code."""
    client = FakeOrgClient(store)
    store["user_departments"].append({
        "id": "ud-b", "user_id": "user-1", "company_id": COMPANY_B,
        "department_id": "dept-b-production", "workflow_role_id": 3, "created_at": "2026-01-01",
    })

    resolved = org_assignment.resolve_department_approver(client, COMPANY_A, "PRODUCTION", "Reviewer")

    assert resolved is None  # user-1's Company-B membership must not leak into Company A's resolution


def test_resolve_department_approver_unknown_department_or_role_returns_none(store):
    client = FakeOrgClient(store)
    assert org_assignment.resolve_department_approver(client, COMPANY_A, "NOT_A_DEPT", "Reviewer") is None
    assert org_assignment.resolve_department_approver(client, COMPANY_A, "PRODUCTION", "Not A Role") is None

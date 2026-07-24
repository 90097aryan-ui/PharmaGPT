"""
tests/test_assume_company_context.py — Regression coverage for Phase 3.5's
"Assume Company Context" — an explicit, logged, time-boxed way for Super
Admin to view one specific company's data on purpose
(PLATFORM_ARCHITECTURE.md §7/§13.2's "break-glass" concept), closing the
cross-tenant leak this phase found without granting Super Admin any
standing access.

Mocks pharmagpt.services.supabase_client.get_authenticated_client (imported
separately into both routes/auth.py and pharmagpt/auth/middleware.py) with a
tiny in-memory fake Supabase client, the same technique
tests/test_security_tenant_rbac_esig.py already uses for
resolve_tenant_context — no real Supabase project is touched.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests.test_security_tenant_rbac_esig import ADMIN_A, COMPANY_A, SUPER_ADMIN, AUTH_HEADERS, MIDDLEWARE_PATH

COMPANY_CLIENT_PATH_AUTH = "pharmagpt.routes.auth.get_authenticated_client"
COMPANY_CLIENT_PATH_MIDDLEWARE = "pharmagpt.auth.middleware.get_authenticated_client"


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
        self._filters = {}
        self._single = False

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def order(self, *_a, **_k):
        return self

    def maybe_single(self):
        self._single = True
        return self

    def _matches(self, rows):
        return [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]

    def execute(self):
        table = self.store.setdefault(self.table_name, [])
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("id", f"{self.table_name}-{len(table) + 1}")
            table.append(row)
            return _FakeResult([row])
        if self._op == "update":
            matched = self._matches(table)
            for r in matched:
                r.update(self._payload)
            return _FakeResult(matched)

        matched = self._matches(table)
        if self.table_name == "break_glass_access":
            enriched = []
            for r in matched:
                company = next(
                    (c for c in self.store.get("companies", []) if c["id"] == r.get("company_id")), None,
                )
                row = dict(r)
                if company:
                    row["companies"] = {"legal_name": company["legal_name"]}
                enriched.append(row)
            matched = enriched
        if self._single:
            return _FakeResult(matched[0] if matched else None)
        return _FakeResult(matched)


class FakeSupabaseClient:
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
        "companies": [{"id": COMPANY_A, "legal_name": "Company A", "status": "active"}],
        "break_glass_access": [],
    }


def _patched_clients(store):
    fake = FakeSupabaseClient(store)
    return (
        patch(COMPANY_CLIENT_PATH_AUTH, return_value=fake),
        patch(COMPANY_CLIENT_PATH_MIDDLEWARE, return_value=fake),
    )


def test_assume_then_list_projects_returns_companys_data_not_403(client, store):
    p1, p2 = _patched_clients(store)
    with _as(SUPER_ADMIN), p1, p2:
        assume_resp = client.post(
            "/auth/assume-company",
            json={"company_id": COMPANY_A, "reason": "Support ticket #1"},
            headers=AUTH_HEADERS,
        )
        assert assume_resp.status_code == 201
        assert store["break_glass_access"][0]["company_id"] == COMPANY_A
        assert store["break_glass_access"][0].get("revoked_at") is None

        resp = client.get("/projects", headers=AUTH_HEADERS)
    assert resp.status_code == 200


def test_end_assume_reverts_to_403(client, store):
    p1, p2 = _patched_clients(store)
    with _as(SUPER_ADMIN), p1, p2:
        client.post(
            "/auth/assume-company",
            json={"company_id": COMPANY_A, "reason": "Support ticket #1"},
            headers=AUTH_HEADERS,
        )
        end_resp = client.post("/auth/end-assume-company", headers=AUTH_HEADERS)
        assert end_resp.status_code == 200
        assert store["break_glass_access"][0]["revoked_at"] is not None

        resp = client.get("/projects", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_expired_grant_reverts_to_403_without_explicit_end(client, store):
    store["break_glass_access"].append({
        "id": "grant-expired",
        "super_admin_user_id": SUPER_ADMIN.user_id,
        "company_id": COMPANY_A,
        "reason": "old grant",
        "granted_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "revoked_at": None,
    })
    p1, p2 = _patched_clients(store)

    with _as(SUPER_ADMIN), p1, p2:
        with client.session_transaction() as sess:
            sess["assumed_company_id"] = COMPANY_A
            sess["break_glass_id"] = "grant-expired"

        resp = client.get("/projects", headers=AUTH_HEADERS)
    assert resp.status_code == 403


def test_reason_is_required(client, store):
    p1, p2 = _patched_clients(store)
    with _as(SUPER_ADMIN), p1, p2:
        resp = client.post(
            "/auth/assume-company", json={"company_id": COMPANY_A}, headers=AUTH_HEADERS,
        )
    assert resp.status_code == 400


def test_company_admin_cannot_assume_context(client, store):
    p1, p2 = _patched_clients(store)
    with _as(ADMIN_A), p1, p2:
        resp = client.post(
            "/auth/assume-company",
            json={"company_id": COMPANY_A, "reason": "x"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 403


def test_me_reports_assumed_context_fields(client, store):
    p1, p2 = _patched_clients(store)
    with _as(SUPER_ADMIN), p1, p2:
        client.post(
            "/auth/assume-company",
            json={"company_id": COMPANY_A, "reason": "Support ticket #1"},
            headers=AUTH_HEADERS,
        )
        me_resp = client.get("/auth/me", headers=AUTH_HEADERS)

    body = me_resp.get_json()
    assert body["assumed_company_id"] == COMPANY_A
    assert body["assumed_company_name"] == "Company A"
    assert "break_glass_expires_at" in body

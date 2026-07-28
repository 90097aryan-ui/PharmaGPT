"""
tests/test_seed_nutra_demo.py — scripts/seed_nutra_demo.py, fully mocked
against the Supabase client (no live Supabase project, no real .env). Uses
a small in-memory fake client (store dict + fake auth.admin) rather than
per-call MagicMock chains, since the seed flow touches many tables and
this file's own idempotency/reset tests need state to actually persist
across repeated calls within one test — the same technique
tests/test_assume_company_context.py::FakeSupabaseClient uses, extended
here with upsert/limit/delete and a fake auth.admin (create_user/
list_users/delete_user) so pharmagpt.services.identity_admin.provision_user
and scripts.bootstrap_super_admin.find_auth_user_by_email can run for real
against it.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.seed_nutra_demo import (
    DEPARTMENTS,
    DEMO_PASSWORD,
    NUTRA_USERS,
    SeedError,
    find_or_create_company,
    load_config,
    main,
    reset_nutra_demo,
    seed_nutra_demo,
)

IDENTITY_ADMIN_CLIENT_PATH = "pharmagpt.services.identity_admin.get_service_role_client"


# ── Fake Supabase client (store dict + fake auth.admin) ─────────────────

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
        self._limit = None
        self._on_conflict = None

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

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
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

        if self._op == "delete":
            matched = self._matches(table)
            for r in matched:
                table.remove(r)
            return _FakeResult(matched)

        if self._op == "upsert":
            conflict_fields = [f for f in (self._on_conflict or "").split(",") if f]
            existing = None
            if conflict_fields:
                existing = next(
                    (r for r in table if all(r.get(f) == self._payload.get(f) for f in conflict_fields)),
                    None,
                )
            if existing is not None:
                existing.update(self._payload)
                return _FakeResult([existing])
            row = dict(self._payload)
            row.setdefault("id", f"{self.table_name}-{len(table) + 1}")
            table.append(row)
            return _FakeResult([row])

        matched = self._matches(table)
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._single:
            return _FakeResult(matched[0] if matched else None)
        return _FakeResult(matched)


class _FakeAuthAdmin:
    def __init__(self, store):
        self.store = store

    def create_user(self, payload):
        users = self.store.setdefault("_auth_users", [])
        auth_id = f"auth-{len(users) + 1}"
        user = SimpleNamespace(id=auth_id, email=payload["email"])
        users.append(user)
        return SimpleNamespace(user=user)

    def list_users(self, page=1, per_page=200):
        if page != 1:
            return []
        return list(self.store.get("_auth_users", []))

    def delete_user(self, auth_id):
        users = self.store.setdefault("_auth_users", [])
        if not any(u.id == auth_id for u in users):
            raise ValueError(f"no such auth user: {auth_id}")
        self.store["_auth_users"] = [u for u in users if u.id != auth_id]
        self.store["users"] = [r for r in self.store.get("users", []) if r.get("id") != auth_id]
        for table_name in ("user_module_permissions", "user_departments"):
            self.store[table_name] = [r for r in self.store.get(table_name, []) if r.get("user_id") != auth_id]


class FakeServiceRoleClient:
    def __init__(self, store):
        self.store = store
        self.auth = SimpleNamespace(admin=_FakeAuthAdmin(store))

    def table(self, name):
        return _FakeQuery(name, self.store)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def store():
    return {
        "roles": [
            {"id": 1, "name": "super_admin"},
            {"id": 2, "name": "company_admin"},
            {"id": 3, "name": "reviewer_qa"},
            {"id": 4, "name": "user"},
        ],
        "workflow_roles": [
            {"id": 1, "name": "Initiator"},
            {"id": 2, "name": "Coordinator"},
            {"id": 3, "name": "Reviewer"},
            {"id": 4, "name": "Approver"},
            {"id": 5, "name": "Plant Head"},
        ],
        "modules": [
            {"id": "mod-qms", "code": "QMS"},
            {"id": "mod-validation", "code": "VALIDATION"},
            {"id": "mod-docgen", "code": "DOCUMENT_GENERATOR"},
        ],
        "companies": [],
        "departments": [],
        "users": [],
        "user_departments": [],
        "user_module_permissions": [],
        "audit_trail": [],
        "_auth_users": [],
    }


@pytest.fixture()
def client(store):
    return FakeServiceRoleClient(store)


@pytest.fixture(autouse=True)
def _patch_identity_admin_client(client):
    with patch(IDENTITY_ADMIN_CLIENT_PATH, return_value=client):
        yield


# ── find_or_create_company ──────────────────────────────────────────────

def test_find_or_create_company_creates_when_absent(client, store):
    company = find_or_create_company(client)

    assert company["legal_name"] == "Nutra"
    assert company["industry_segment"] == "nutraceutical"
    assert len(store["companies"]) == 1


def test_find_or_create_company_reuses_existing(client, store):
    first = find_or_create_company(client)
    second = find_or_create_company(client)

    assert first["id"] == second["id"]
    assert len(store["companies"]) == 1


# ── Full seed ────────────────────────────────────────────────────────────

def test_seed_creates_all_23_users(client, store):
    result = seed_nutra_demo(client)

    assert len(result["created"]) == 23
    assert len(result["existing"]) == 0
    assert {u[0] for u in NUTRA_USERS} == set(result["created"])
    assert len(store["users"]) == 23


def test_seed_creates_all_departments(client, store):
    result = seed_nutra_demo(client)

    assert set(result["departments"]) == {code for _, code in DEPARTMENTS}
    assert len(store["departments"]) == len(DEPARTMENTS)


def test_seed_assigns_primary_department_per_spec(client, store):
    seed_nutra_demo(client)

    coordinator_auth = next(u for u in store["_auth_users"] if u.email == "c@nutra.com")
    qa_dept = next(d for d in store["departments"] if d["department_code"] == "QA")
    primary_rows = [r for r in store["user_departments"] if r["user_id"] == coordinator_auth.id]

    assert len(primary_rows) == 1
    assert primary_rows[0]["department_id"] == qa_dept["id"]
    assert primary_rows[0]["is_primary"] is True


def test_plant_head_gets_no_department_assignment(client, store):
    seed_nutra_demo(client)

    plant_head_auth = next(u for u in store["_auth_users"] if u.email == "plh@nutra.com")
    assert not [r for r in store["user_departments"] if r["user_id"] == plant_head_auth.id]


@pytest.mark.parametrize(
    "email,expected_role_name",
    [
        ("qi@nutra.com", "user"),          # Initiator -> user
        ("c@nutra.com", "reviewer_qa"),    # Coordinator -> reviewer_qa
        ("qr@nutra.com", "reviewer_qa"),   # Reviewer -> reviewer_qa
        ("qh@nutra.com", "reviewer_qa"),   # Approver -> reviewer_qa
        ("plh@nutra.com", "reviewer_qa"),  # Plant Head -> reviewer_qa
    ],
)
def test_seed_platform_role_mapping(client, store, email, expected_role_name):
    seed_nutra_demo(client)

    auth_user = next(u for u in store["_auth_users"] if u.email == email)
    profile = next(r for r in store["users"] if r["id"] == auth_user.id)
    role = next(r for r in store["roles"] if r["id"] == profile["role_id"])

    assert role["name"] == expected_role_name
    assert role["name"] != "company_admin"
    assert role["name"] != "super_admin"


@pytest.mark.parametrize(
    "email,qms,validation,doc_gen",
    [
        ("qi@nutra.com", True, False, True),
        ("vi@nutra.com", True, True, True),
        ("ppr@nutra.com", True, False, True),
        ("plh@nutra.com", True, True, True),
    ],
)
def test_seed_assigns_module_permissions_matching_spec(client, store, email, qms, validation, doc_gen):
    seed_nutra_demo(client)

    auth_user = next(u for u in store["_auth_users"] if u.email == email)
    rows = {r["module_id"]: r["enabled"] for r in store["user_module_permissions"] if r["user_id"] == auth_user.id}
    by_code = {m["code"]: rows[m["id"]] for m in store["modules"]}

    assert by_code == {"QMS": qms, "VALIDATION": validation, "DOCUMENT_GENERATOR": doc_gen}


def test_seed_uses_fixed_password_for_new_users(client, store):
    with patch("scripts.seed_nutra_demo.provision_user") as mock_provision:
        mock_provision.return_value = {"auth_user_id": "auth-x", "temporary_password": DEMO_PASSWORD}
        # Only exercise one user's worth of provisioning behavior directly.
        from scripts.seed_nutra_demo import seed_one_user

        seed_nutra_demo_deps = find_or_create_company(client)
        seed_one_user(
            client, seed_nutra_demo_deps["id"], {}, {name: rid for name, rid in
                zip(("Initiator", "Coordinator", "Reviewer", "Approver", "Plant Head"), range(1, 6))},
            ("qi@nutra.com", "Quality Initiator", None, "Initiator", True, False, True),
        )

    mock_provision.assert_called_once()
    _, kwargs = mock_provision.call_args
    assert kwargs["password"] == DEMO_PASSWORD


def test_seed_existing_auth_identity_updates_profile_instead_of_duplicating(client, store):
    company = find_or_create_company(client)
    store["_auth_users"].append(SimpleNamespace(id="auth-existing", email="qi@nutra.com"))
    store["users"].append({
        "id": "auth-existing", "company_id": company["id"], "role_id": 4,
        "display_name": "Old Name", "status": "active", "workflow_role_id": None,
    })

    result = seed_nutra_demo(client)

    assert "qi@nutra.com" in result["existing"]
    assert "qi@nutra.com" not in result["created"]
    assert len([u for u in store["_auth_users"] if u.email == "qi@nutra.com"]) == 1
    assert len([r for r in store["users"] if r["id"] == "auth-existing"]) == 1
    updated_row = next(r for r in store["users"] if r["id"] == "auth-existing")
    assert updated_row["display_name"] == "Quality Initiator"


def test_seed_does_not_reset_password_for_existing_user(client, store):
    seed_nutra_demo(client)
    auth_count_before = len(store["_auth_users"])

    with patch("scripts.seed_nutra_demo.provision_user") as mock_provision:
        seed_nutra_demo(client)

    mock_provision.assert_not_called()
    assert len(store["_auth_users"]) == auth_count_before


def test_seed_writes_best_effort_audit_entry_per_user(client, store):
    seed_nutra_demo(client)

    assert len(store["audit_trail"]) == 23
    assert all(entry["actor_user_id"] is None for entry in store["audit_trail"])
    assert all(entry["record_type"] == "user" for entry in store["audit_trail"])


def test_seed_second_run_is_idempotent(client, store):
    seed_nutra_demo(client)
    first_user_count = len(store["users"])
    first_dept_count = len(store["departments"])
    first_company_count = len(store["companies"])

    result = seed_nutra_demo(client)

    assert len(result["created"]) == 0
    assert len(result["existing"]) == 23
    assert len(store["users"]) == first_user_count
    assert len(store["departments"]) == first_dept_count
    assert len(store["companies"]) == first_company_count
    # No duplicate primary-department or module-permission rows per user.
    for auth_user in store["_auth_users"]:
        dept_rows = [r for r in store["user_departments"] if r["user_id"] == auth_user.id]
        assert len(dept_rows) <= 1
        module_rows = [r for r in store["user_module_permissions"] if r["user_id"] == auth_user.id]
        assert len(module_rows) == 3


# ── --reset ──────────────────────────────────────────────────────────────

def test_reset_deletes_only_nutra_demo_users_and_departments(client, store):
    seed_nutra_demo(client)

    result = reset_nutra_demo(client)

    assert len(result["deleted"]) == 23
    assert len(result["failed"]) == 0
    assert len(store["_auth_users"]) == 0
    assert len(store["users"]) == 0
    assert len(store["departments"]) == 0
    assert len(store["companies"]) == 1  # the companies row itself is never deleted


def test_reset_then_seed_recreates_demo_data(client, store):
    first = seed_nutra_demo(client)
    reset_nutra_demo(client)

    second = seed_nutra_demo(client)

    assert second["company_id"] == first["company_id"]
    assert len(second["created"]) == 23
    assert len(store["users"]) == 23
    assert len(store["departments"]) == len(DEPARTMENTS)


def test_reset_continues_past_one_delete_failure(client, store):
    seed_nutra_demo(client)
    failing_email = "qh@nutra.com"
    failing_auth_id = next(u.id for u in store["_auth_users"] if u.email == failing_email)

    real_delete_user = client.auth.admin.delete_user

    def _delete_user_maybe_fail(auth_id):
        if auth_id == failing_auth_id:
            raise RuntimeError("simulated FK-restrict failure (audit_trail.actor_user_id)")
        return real_delete_user(auth_id)

    with patch.object(client.auth.admin, "delete_user", side_effect=_delete_user_maybe_fail):
        result = reset_nutra_demo(client)

    assert len(result["deleted"]) == 22
    assert len(result["failed"]) == 1
    assert result["failed"][0][0] == failing_email
    # The failure did not abort the rest of the reset.
    assert any(u.email == failing_email for u in store["_auth_users"])
    assert not any(u.email == "qi@nutra.com" for u in store["_auth_users"])


# ── main() ───────────────────────────────────────────────────────────────

def test_load_config_missing_vars_raises():
    with pytest.raises(SeedError, match="SUPABASE_URL"):
        load_config({})


def test_main_returns_1_when_env_incomplete(capsys):
    with patch("scripts.seed_nutra_demo.load_dotenv"), \
         patch.dict("os.environ", {}, clear=True), \
         patch("sys.argv", ["seed_nutra_demo.py"]):
        exit_code = main()

    assert exit_code == 1
    assert "Seed failed" in capsys.readouterr().err


def test_main_returns_0_and_prints_summary_on_success(capsys, store):
    env = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-key"}
    fake_client = FakeServiceRoleClient(store)

    with patch("scripts.seed_nutra_demo.load_dotenv"), \
         patch.dict("os.environ", env, clear=True), \
         patch("scripts.seed_nutra_demo.build_service_role_client", return_value=fake_client), \
         patch(IDENTITY_ADMIN_CLIENT_PATH, return_value=fake_client), \
         patch("sys.argv", ["seed_nutra_demo.py"]):
        exit_code = main()

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Nutra" in out
    assert "23 users created" in out
    assert "not modified" in out

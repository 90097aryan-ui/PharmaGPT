"""
tests/test_equipment_library.py — Regression coverage for Phase 2's
"Equipment Library is a first-class top-level module" requirement
(PHASE_2_IMPLEMENTATION_REPORT.md; routes/equipment.py::list_company_equipment).

GET /equipment lists every Equipment record across every Project in the
caller's company (not just one project) — the backend half of the new
top-level "Equipment Library" sidebar view. Equipment remains project-owned
at the schema level; this is a navigation/query elevation only.
"""

from unittest.mock import patch

import pytest

from pharmagpt.auth.context import TenantContext

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"
COMPANY_B = "company-b-22222222-2222-2222-2222-222222222222"

ADMIN_A = TenantContext(
    user_id="admin-a", email="admin-a@example.com", display_name="Alice Admin",
    role="company_admin", company_id=COMPANY_A,
)
ADMIN_B = TenantContext(
    user_id="admin-b", email="admin-b@example.com", display_name="Bob Admin",
    role="company_admin", company_id=COMPANY_B,
)

MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"
AUTH_HEADERS = {"Authorization": "Bearer good-token"}


@pytest.fixture()
def client(db_path):
    """Overrides conftest.py's auth-bypassing `client` fixture: this file
    needs the real auth gate (via `_as()`-patched resolve_tenant_context) to
    actually distinguish Company A from Company B — see
    tests/test_security_tenant_rbac_esig.py, the reference pattern."""
    import pharmagpt.app as appmod
    return appmod.app.test_client()


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


def test_equipment_library_lists_equipment_across_multiple_projects(client):
    with _as(ADMIN_A):
        p1 = client.post("/projects", json={"name": "Project One", "equipment_name": "HPLC System",
                                             "manufacturer": "Agilent"}, headers=AUTH_HEADERS).get_json()
        p2 = client.post("/projects", json={"name": "Project Two", "equipment_name": "GC System",
                                             "manufacturer": "Shimadzu"}, headers=AUTH_HEADERS).get_json()

        resp = client.get("/equipment", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    names = {e["name"] for e in resp.get_json()}
    assert names == {"HPLC System", "GC System"}


def test_equipment_library_is_tenant_scoped(client):
    with _as(ADMIN_A):
        client.post("/projects", json={"name": "Company A Project", "equipment_name": "Autoclave A"},
                    headers=AUTH_HEADERS)
    with _as(ADMIN_B):
        client.post("/projects", json={"name": "Company B Project", "equipment_name": "Autoclave B"},
                    headers=AUTH_HEADERS)

        resp = client.get("/equipment", headers=AUTH_HEADERS)

    names = {e["name"] for e in resp.get_json()}
    assert names == {"Autoclave B"}


def test_equipment_library_includes_owning_project_name(client):
    with _as(ADMIN_A):
        client.post("/projects", json={"name": "Titration Line Validation", "equipment_name": "Titrator"},
                    headers=AUTH_HEADERS)
        resp = client.get("/equipment", headers=AUTH_HEADERS)

    equipment = resp.get_json()
    assert len(equipment) == 1
    assert equipment[0]["project_name"] == "Titration Line Validation"

"""
tests/test_security_super_admin_guard.py — Regression coverage for the
Phase 3.5 cross-tenant leak fix.

A live Enterprise Acceptance Test found that Super Admin (company_id IS
NULL) could read every company's business data unfiltered on several list/
dashboard endpoints, because the underlying DB functions treat
company_id=None as "no filter" (a code path meant only for offline backfill
scripts). Every route below now guards with the same
"if not g.tenant.company_id: 403" pattern already proven on the sibling
POST/create routes (e.g. routes/projects.py::create_project) — this file
proves the guard actually fires for Super Admin and does NOT fire for a
real company admin, for every one of the 18 previously-unguarded routes.
"""

from unittest.mock import patch

import pytest

from tests.test_security_tenant_rbac_esig import ADMIN_A, SUPER_ADMIN, AUTH_HEADERS, MIDDLEWARE_PATH


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


GUARDED_ROUTES = [
    ("GET", "/projects"),
    ("GET", "/kb/documents"),
    ("GET", "/qms/documents"),
    ("GET", "/qms/deviations"),
    ("GET", "/qms/capa"),
    ("GET", "/qms/capa/trend-summary"),
    ("GET", "/qms/change-control"),
    ("GET", "/risk/assessments"),
    ("GET", "/urs/"),
    ("GET", "/qual/"),
    ("GET", "/report/"),
    ("GET", "/report/linked/1"),
    ("GET", "/dashboard/stats"),
    ("GET", "/risk/dashboard"),
    ("GET", "/risk/library"),
    ("GET", "/urs/dashboard"),
    ("GET", "/qual/dashboard"),
    ("GET", "/report/dashboard"),
    ("GET", "/qms/dashboard"),
]


@pytest.mark.parametrize("method,url", GUARDED_ROUTES)
def test_super_admin_gets_403_not_a_leak(client, method, url):
    with _as(SUPER_ADMIN):
        resp = client.open(url, method=method, headers=AUTH_HEADERS)

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "Super Admin has no standing access to tenant content"


@pytest.mark.parametrize("method,url", GUARDED_ROUTES)
def test_real_company_admin_is_unaffected(client, method, url):
    with _as(ADMIN_A):
        resp = client.open(url, method=method, headers=AUTH_HEADERS)

    assert resp.status_code == 200

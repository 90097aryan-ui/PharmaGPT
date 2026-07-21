"""
tests/conftest.py — Shared pytest fixtures.

`fixtures_dir` builds the standard PDF fixture set (see
tests/fixtures/generate_fixtures.py) once per test session into a temp
directory, so no test fixture files are committed to the repo.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))  # so `import fixtures.generate_fixtures` works
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # repo root, so `import pharmagpt` works

from fixtures.generate_fixtures import build_all  # noqa: E402

# ── Tenant-scoping test shim (security fix, docs/SECURITY_REVIEW.md) ─────────
# Routes now read g.tenant.company_id (pharmagpt/tenancy.py) to enforce
# per-company data isolation. The `client` fixture below predates tenancy
# entirely and patches is_exempt() to bypass the real auth gate for every
# request, which means the real hook returns before ever setting g.tenant.
# This hook fills that gap with a fixed, permissive fake tenant so the 300+
# existing business-logic tests keep exercising exactly the same behavior as
# before, without simulating a real Supabase-authenticated session. It only
# fires when the real auth hook did NOT already set g.tenant — i.e. never for
# tests/test_app_auth_integration.py's own `client` fixture, which does not
# patch is_exempt and exercises the real 401/invalid-token paths (a
# before_request hook that returns a response short-circuits Flask before
# this one runs). Registered once at import time, not per-test, so it can
# never accumulate duplicate registrations across the session.
import pharmagpt.app as _appmod  # noqa: E402
from flask import g as _g  # noqa: E402
from pharmagpt.auth.context import TenantContext as _TenantContext  # noqa: E402
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as _TEST_COMPANY_ID  # noqa: E402

_TEST_TENANT = _TenantContext(
    user_id="00000000-0000-0000-0000-000000000001",
    email="test@example.com",
    display_name="Test User",
    role="company_admin",
    company_id=_TEST_COMPANY_ID,
)


@_appmod.app.before_request
def _fill_in_fake_tenant_for_auth_bypassed_tests():
    if not hasattr(_g, "tenant"):
        _g.tenant = _TEST_TENANT


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory) -> dict:
    """Build every standard PDF fixture once per test session.

    Returns {filename: absolute_path}, e.g. fixtures_dir["small.pdf"].
    """
    out_dir = tmp_path_factory.mktemp("pdf_fixtures")
    return build_all(str(out_dir))


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Point pharmagpt.database at a throwaway SQLite file for this test and
    initialize its schema. Restores the original path automatically."""
    from pharmagpt import database as db

    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    return test_db


@pytest.fixture()
def client(db_path, monkeypatch):
    """Flask test client wired to the db_path fixture's throwaway database.
    pharmagpt.app may already be imported from an earlier test — that's fine,
    since every DB call resolves db.DB_PATH dynamically at call time rather
    than caching it, so each test still gets full isolation.

    Phase 2 wired a global auth gate into every route (pharmagpt/app.py).
    The tests using this fixture predate that and exercise business logic,
    not authentication, so the gate is patched to treat every request as
    exempt here — restored automatically after each test. Tests that need
    to exercise the real gate (missing/invalid/valid tokens) define their
    own `client` fixture without this patch — see
    tests/test_app_auth_integration.py.
    """
    import pharmagpt.app as appmod
    import pharmagpt.auth.middleware as auth_middleware

    monkeypatch.setattr(auth_middleware, "is_exempt", lambda path: True)

    return appmod.app.test_client()

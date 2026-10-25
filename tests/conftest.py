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
def isolated_ai_gateway(monkeypatch):
    """Isolate pharmagpt.providers.router's (the AI Gateway, see
    docs/AI_PROVIDER_ROUTER.md) provider registry/model-map/client-cache/
    cooldown state for a single test, so a test can register throwaway fake
    providers without affecting any other test or the real gemini/nemotron
    builders. Shared by every test file exercising code migrated onto the
    router (routes/chat.py Stage 1, services/urs_generation_job.py Stage 2,
    ...) instead of the old module-level pharmagpt.state.gemini_client.
    tests/test_provider_router.py keeps its own file-local, equivalent
    fixture (isolated_router) predating this one — both isolate the same
    module state, just for that file's own test style."""
    from pharmagpt.providers import router

    monkeypatch.setattr(router, "_PROVIDER_BUILDERS", dict(router._PROVIDER_BUILDERS))
    monkeypatch.setattr(router, "_PROVIDER_MODELS", dict(router._PROVIDER_MODELS))
    monkeypatch.setattr(router, "_CLIENT_CACHE", {})
    monkeypatch.setattr(router, "_provider_cooldown_until", {})
    return router


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

    # Electronic Signature gate (pharmagpt/services/esignature_service.py,
    # wired into routes/qms_documents.py, qms_capa.py, qms_change_control.py
    # ::submit_approval). Same rationale as the tenant-scoping shim above:
    # the 300+ existing business-logic tests using this fixture predate
    # e-signature and don't supply a password/meaning/reason, so the gate
    # is bypassed here rather than editing every call site. Tests that need
    # to exercise the real gate patch pharmagpt.services.esignature_service
    # .require_esignature/.reauthenticate directly instead of using this
    # fixture — see tests/test_esignature_service.py.
    import pharmagpt.services.esignature_service as esignature_service
    monkeypatch.setattr(esignature_service, "require_esignature", lambda *a, **k: None)

    # Wave 3A-C (Security Audit remediation, Finding A): routes/
    # qms_documents.py::set_review_chain_route now validates every submitted
    # reviewer/department_head/quality_head/plant_head id against
    # tenancy.missing_or_inactive_users() before persisting the chain. The
    # 300+ existing Document Control tests using this fixture predate that
    # control and use small, fixed placeholder ids (not real Supabase-backed
    # users) for those roles — same rationale as the two bypasses above.
    # Scoped to routes/qms_documents.py's own get_service_role_client
    # reference only, so CAPA/Change Control/Deviations' own (already
    # correctly tenant-validated) assign endpoints are completely
    # unaffected. Real validation against a restrictive, multi-company
    # directory is covered separately by
    # tests/test_wave3a_finding_a_assign_chain_validation.py, which builds
    # its own fake client rather than using this fixture.
    monkeypatch.setattr(
        "pharmagpt.routes.qms_documents.get_service_role_client",
        lambda: _PermissiveDocumentChainUsersClient(),
    )

    # Yuktav org/RBAC/workflow authorization task, enforcement-closure phase:
    # pharmagpt.auth.module_access.has_business_permission() no longer gives
    # company_admin/reviewer_qa an unconditional bypass — it resolves through
    # the same rbac_user_roles -> rbac_roles -> rbac_role_permissions tables
    # everyone else uses (see that module's docstring for why). Same
    # rationale as the three bypasses above: the 1000+ existing business-
    # logic tests using this fixture predate real RBAC role assignments
    # entirely and don't mock get_effective_permissions, so this fixture
    # grants a broad, permissive effective-permission set for the duration
    # of each such test — real fail-closed enforcement behavior (including
    # the FALSE-cell denial matrix and the removal of the frozen-role
    # bypass) is covered separately, with real RBAC-role fixtures, in
    # tests/test_module_access.py and
    # tests/test_workflow_engine_org_authorization.py.
    import pharmagpt.services.rbac_defaults as rbac_defaults
    monkeypatch.setattr(
        "pharmagpt.auth.module_access.get_effective_permissions",
        lambda tenant: {(m, a) for m in rbac_defaults.MODULES for a in rbac_defaults.ACTIONS},
    )

    # SOP branding integration: routes/qms_documents.py's export_docx() and
    # download_template_docx() now call services/company_branding.py's
    # get_company_name_for_docx(), which reaches Supabase (companies table)
    # over the network using the request's real bearer token. The 300+
    # existing Document Control tests using this fixture predate that call
    # and don't carry a real Supabase session — same rationale as the four
    # bypasses above — so it's patched here to a fast, deterministic no-op
    # (empty string, matching "no branding available") for the duration of
    # each such test. Tests that exercise the real branding lookup patch
    # this same reference to a fake per-test — see
    # tests/test_sop_master_template.py.
    monkeypatch.setattr(
        "pharmagpt.routes.qms_documents.get_company_name_for_docx", lambda company_id: ""
    )

    return appmod.app.test_client()


class _PermissiveDocumentChainUsersClient:
    """See the Wave 3A-C note in the `client` fixture above. Every id ever
    used as a placeholder Reviewer/Department Head/Quality Head/Plant Head
    across the Document Control test suite is treated as an active user —
    this fixture doesn't test directory validation itself, so it stays
    permissive rather than trying to track "which test uses which id"."""

    _KNOWN_TEST_USER_IDS = (
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000003",
        "00000000-0000-0000-0000-000000000004",
        "00000000-0000-0000-0000-000000000005",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
        "44444444-4444-4444-4444-444444444444",
        "rev-1", "rev-assigned", "dh-1", "qh-1",
    )

    class _Query:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=self._rows)

    def table(self, name):
        if name != "users":
            return self._Query([])
        return self._Query([{"id": uid} for uid in self._KNOWN_TEST_USER_IDS])

"""
tests/test_yuktav_p0_audit.py — Regression coverage for the Yuktav Audit
Trail P0 work package (read-only assessment -> P0-1..P0-4 implementation).

Scope not already covered by tests/test_wave4b_audit_coverage.py (login
success/failure paths, logout, the basic authorization-denied 403 case) or
tests/test_assume_company_context.py (break-glass grant lifecycle itself):

- P0-2: the attempted protected resource is captured on an
  AUTHORIZATION_DENIED entry, and the defensive unauthenticated-denial path
  (no g.tenant at all) never fabricates an identity.
- pharmagpt/audit.py::log — sensitive-key redaction and non-spoofable
  actor/company attribution, exercised directly (unit-style) rather than
  through a specific route, since every route ultimately funnels through
  this one function.
"""

from flask import Flask, g

from pharmagpt import audit
from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.context import TenantContext
from pharmagpt.auth.decorators import require_role


# ── P0-2: attempted resource capture + unauthenticated defensive path ───────

def test_authorization_denied_records_attempted_method_and_path(client):
    """tests/test_wave4b_audit_coverage.py already proves the 403 itself is
    logged; this proves the *resource* the caller tried to reach is captured
    too, per P0-2's "record the attempted protected action/resource" bullet."""
    resp = client.get("/auth/companies")  # @require_role("super_admin"); fixture tenant is company_admin
    assert resp.status_code == 403

    trail = qmsdb.get_audit_trail("auth", 0)
    entry = next(e for e in trail if e["action"] == "AUTHORIZATION_DENIED" and e["result"] == "failure")
    assert "GET" in entry["detail"]
    assert "/auth/companies" in entry["detail"]


def test_authorization_denied_unauthenticated_does_not_fabricate_identity(db_path):
    """Defensive branch: require_role must never crash on `g.tenant.role`
    nor invent a role/identity if it is ever reached with no g.tenant set
    (the global auth gate is expected to always set it first in production —
    see require_role's docstring — but this proves the fallback is safe, not
    just "probably never hit"). Uses a throwaway Flask app with NO auth gate
    registered at all, so g.tenant is genuinely absent, unlike the shared
    `client` fixture (tests/conftest.py always fills in a fake tenant)."""
    app = Flask(__name__)
    app.secret_key = "test-secret-key"

    @app.route("/protected")
    @require_role("super_admin")
    def protected():
        return "ok"

    test_client = app.test_client()
    resp = test_client.get("/protected")
    assert resp.status_code == 403

    trail = qmsdb.get_audit_trail("auth", 0)
    entry = next(
        e for e in trail
        if e["action"] == "AUTHORIZATION_DENIED" and e["performed_by"].startswith("anonymous")
    )
    assert entry["result"] == "failure"
    assert entry["company_id"] is None  # no tenant was ever resolved — never guessed
    assert "no tenant resolved" in entry["reason"]
    assert "GET /protected" in entry["detail"]


# ── pharmagpt/audit.py::log — redaction + attribution ───────────────────────

def test_audit_log_redacts_sensitive_keys_and_does_not_persist_secrets(db_path):
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.tenant = TenantContext(
            user_id="u1", email="a@example.com", display_name="A B",
            role="company_admin", company_id="company-1",
        )
        audit.log(
            "user", 4242, "Password changed",
            old={"password": "old-super-secret", "display_name": "A"},
            new={"password": "new-super-secret", "display_name": "A B",
                 "access_token": "tok-should-not-leak"},
        )

    trail = qmsdb.get_audit_trail("user", 4242)
    entry = trail[-1]
    row_text = " ".join(str(v) for v in entry.values())
    assert "old-super-secret" not in row_text
    assert "new-super-secret" not in row_text
    assert "tok-should-not-leak" not in row_text
    assert "***" in entry["old_values"]
    assert "***" in entry["new_values"]
    # Non-sensitive changed fields are still captured, not blanket-dropped.
    assert "A B" in entry["new_values"]


def test_audit_log_attributes_actor_and_company_from_server_derived_tenant(db_path):
    """Two different tenants acting on the same record_id must each be
    attributed correctly and independently — proves attribution comes from
    the request-scoped g.tenant, not a cached/global value."""
    app = Flask(__name__)

    tenant_a = TenantContext(
        user_id="u-a", email="a@example.com", display_name="Admin A",
        role="company_admin", company_id="company-a",
    )
    tenant_b = TenantContext(
        user_id="u-b", email="b@example.com", display_name="Admin B",
        role="company_admin", company_id="company-b",
    )

    with app.test_request_context("/"):
        g.tenant = tenant_a
        audit.log("project", 99, "Project created")

    with app.test_request_context("/"):
        g.tenant = tenant_b
        audit.log("project", 99, "Project created")

    trail = qmsdb.get_audit_trail("project", 99)
    assert trail[0]["performed_by"] == "Admin A"
    assert trail[0]["company_id"] == "company-a"
    assert trail[1]["performed_by"] == "Admin B"
    assert trail[1]["company_id"] == "company-b"

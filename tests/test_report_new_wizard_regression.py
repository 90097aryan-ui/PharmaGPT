"""
tests/test_report_new_wizard_regression.py — Regression coverage for the
Dashboard -> "Generate Validation Report" -> New Report wizard
(pharmagpt/static/js/report.js::initNewReportWizard).

Production defect (authenticated smoke test, apple-design release):
initNewReportWizard() called fetch('/risk/assessments/') (trailing slash).
routes/risk.py only registers GET /risk/assessments (no trailing slash), so
that call 404'd. Flask's JSON 404 handler returns {"error": "Not found"} —
valid JSON, so `.then(r => r.json())` did not throw. That object (not an
array) was assigned to ReportState.riskList, and renderNewReportWizard()'s
`riskList.map(...)` then threw "riskList.map is not a function", leaving the
wizard stuck on its initial loading state with no user-facing error.

Fix: report.js now calls the canonical '/risk/assessments' (no trailing
slash) — matching the same route risk.js itself already uses — and each of
the wizard's three linked-record fetches (qual/urs/risk) is resolved via a
local helper that treats a non-ok response or a non-array JSON body as an
empty list, so a single module's failure can never again produce a spinning
wizard or an uncaught TypeError.

These tests pin the backend half of that contract (the frontend fetch() URL
now matches the registered route, and the previously-called trailing-slash
URL's exact failure shape is documented) — there is no JS test harness in
this repo, so the frontend fix itself was verified by live reproduction
(see the corrective-fix conversation), not by an automated JS test.
"""

from unittest.mock import patch

from pharmagpt.auth.context import TenantContext

TENANT = TenantContext(
    user_id="user-1", email="jane@example.com", display_name="Jane Admin",
    role="company_admin", company_id="company-1",
)
AUTH_HEADERS = {"Authorization": "Bearer good-token"}
MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


import pytest


@pytest.fixture()
def client(db_path):
    """Real auth gate (not bypassed) — matches tests/test_risk_generate_endpoint.py."""
    import pharmagpt.app as appmod

    return appmod.app.test_client()


# ── 1. The corrected URL (report.js's new fetch target) ─────────────────────

def test_risk_assessments_list_url_matches_the_registered_flask_route(client):
    """pharmagpt/static/js/report.js::initNewReportWizard now calls
    GET /risk/assessments (no trailing slash) to populate the wizard's
    "Link Risk Assessment" dropdown. Assert that exact path resolves to
    routes/risk.py's list endpoint and returns a JSON array."""
    with _as(TENANT):
        resp = client.get("/risk/assessments", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


# ── 2. The old, buggy URL — documents the exact failure the fix removes ─────

def test_trailing_slash_variant_404s_with_a_json_object_not_an_array(client):
    """This is the URL report.js used to call. It must keep 404ing (so no one
    reintroduces it into report.js believing it "already works"), and the
    404 body must stay a JSON *object* — the exact shape that made the old
    `ReportState.riskList = risks || []` assignment produce a non-array and
    crash `riskList.map(...)` in renderNewReportWizard()."""
    with _as(TENANT):
        resp = client.get("/risk/assessments/", headers=AUTH_HEADERS)

    assert resp.status_code == 404
    assert resp.content_type.startswith("application/json")
    body = resp.get_json()
    assert isinstance(body, dict)
    assert not isinstance(body, list)


# ── 3. Sibling wizard endpoints — unaffected by this fix ────────────────────

def test_qual_and_urs_list_endpoints_still_return_json_arrays(client):
    """The same wizard step also links Qualification and URS records via
    GET /qual/ and GET /urs/ (both already using their blueprint's canonical
    trailing-slash form). Confirms the report.js change didn't regress
    these two legs of the same Promise.all."""
    with _as(TENANT):
        qual_resp = client.get("/qual/", headers=AUTH_HEADERS)
        urs_resp = client.get("/urs/", headers=AUTH_HEADERS)

    assert qual_resp.status_code == 200
    assert isinstance(qual_resp.get_json(), list)

    assert urs_resp.status_code == 200
    assert isinstance(urs_resp.get_json(), list)

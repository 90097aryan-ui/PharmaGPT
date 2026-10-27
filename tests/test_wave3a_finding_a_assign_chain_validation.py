"""
tests/test_wave3a_finding_a_assign_chain_validation.py — Regression coverage
for Wave 3A-C (Security Audit remediation, Finding A):
POST /qms/documents/<id>/assign-chain used to accept any client-supplied
reviewer_user_id/department_head_user_id/quality_head_user_id/
plant_head_user_id with no server-side check that the id belonged to the
document's own company, existed, or was active — unlike the equivalent
CRIT-02-hardened .../workflow/steps/<order>/assign endpoints on CAPA and
Change Control, which both already call tenancy.missing_or_inactive_users().

Downstream workflow actions independently re-scope the document by
g.tenant.company_id (tenancy.scoped_or_none / _record_scoped_or_404), so
this was never a cross-tenant approval bypass — but it let an Author persist
an unverified identity into the review/approval chain and the audit trail,
and could permanently soft-lock the document's workflow once submitted
(the chain locks at Submit for Review).

Fix: routes/qms_documents.py::set_review_chain_route now calls
tenancy.missing_or_inactive_users() on every non-empty submitted id before
calling qms_document_database.set_review_chain() — mirrors
routes/qms_capa.py::assign_workflow_step / routes/qms_change_control.py::
assign_workflow_step exactly. Any invalid id rejects the WHOLE request
(400) before anything is persisted.

Pattern mirrors tests/test_security_tenant_rbac_esig.py /
tests/test_wave3a_finding_b_approval_hijack.py exactly (real pharmagpt.app
+ real auth middleware, resolve_tenant_context patched per call).
"""

from unittest.mock import patch

import pytest

from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.context import TenantContext

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"
COMPANY_B = "company-b-22222222-2222-2222-2222-222222222222"

AUTHOR_A = TenantContext(
    user_id="author-a", email="author-a@example.com", display_name="Alex Author",
    role="user", company_id=COMPANY_A,
)
REVIEWER_A = TenantContext(
    user_id="reviewer-a", email="reviewer-a@example.com", display_name="Rita Reviewer",
    role="reviewer_qa", company_id=COMPANY_A,
)
DEPT_HEAD_A = TenantContext(
    user_id="depthead-a", email="depthead-a@example.com", display_name="Dan DeptHead",
    role="reviewer_qa", company_id=COMPANY_A,
)
QUALITY_HEAD_A = TenantContext(
    user_id="qualhead-a", email="qualhead-a@example.com", display_name="Quinn QualityHead",
    role="reviewer_qa", company_id=COMPANY_A,
)
INACTIVE_A = TenantContext(  # real Company A user, but deactivated
    user_id="inactive-a", email="inactive-a@example.com", display_name="Ivan Inactive",
    role="reviewer_qa", company_id=COMPANY_A,
)
USER_B = TenantContext(  # real, active — but a DIFFERENT company
    user_id="user-b", email="user-b@example.com", display_name="Bob FromCompanyB",
    role="reviewer_qa", company_id=COMPANY_B,
)
FAKE_ID = "totally-fake-nonexistent-user-id"

AUTH_HEADERS = {"Authorization": "Bearer good-token"}
MIDDLEWARE_PATH = "pharmagpt.auth.middleware.resolve_tenant_context"


def _as(tenant):
    return patch(MIDDLEWARE_PATH, return_value=tenant)


@pytest.fixture()
def client(db_path, monkeypatch):
    import pharmagpt.app as appmod
    from tests.test_assume_company_context import FakeSupabaseClient
    store = {"users": [
        {"id": AUTHOR_A.user_id, "company_id": COMPANY_A, "status": "active"},
        {"id": REVIEWER_A.user_id, "company_id": COMPANY_A, "status": "active"},
        {"id": DEPT_HEAD_A.user_id, "company_id": COMPANY_A, "status": "active"},
        {"id": QUALITY_HEAD_A.user_id, "company_id": COMPANY_A, "status": "active"},
        {"id": INACTIVE_A.user_id, "company_id": COMPANY_A, "status": "inactive"},
        {"id": USER_B.user_id, "company_id": COMPANY_B, "status": "active"},
    ]}
    monkeypatch.setattr(
        "pharmagpt.routes.qms_documents.get_service_role_client", lambda: FakeSupabaseClient(store)
    )
    return appmod.app.test_client()


def _create_document(client):
    with _as(AUTHOR_A):
        doc = client.post("/qms/documents", json={"title": "SOP-Finding-A"}, headers=AUTH_HEADERS).get_json()
    return doc["id"]


def _assign(client, did, *, reviewer=REVIEWER_A, department_head=DEPT_HEAD_A,
            quality_head=QUALITY_HEAD_A, plant_head=None, quality_head_id_override=None):
    payload = {
        "reviewer_user_id": reviewer.user_id, "reviewer_name": reviewer.display_name,
        "department_head_user_id": department_head.user_id, "department_head_name": department_head.display_name,
        "quality_head_user_id": quality_head_id_override or quality_head.user_id,
        "quality_head_name": quality_head.display_name,
    }
    if plant_head is not None:
        payload["plant_head_user_id"] = plant_head.user_id
        payload["plant_head_name"] = plant_head.display_name
    with _as(AUTHOR_A):
        return client.post(f"/qms/documents/{did}/assign-chain", json=payload, headers=AUTH_HEADERS)


def _chain(client, did):
    with _as(AUTHOR_A):
        return client.get(f"/qms/documents/{did}/assign-chain", headers=AUTH_HEADERS).get_json()


# ── Test 1 — cross-tenant user ──────────────────────────────────────────────

def test_cross_tenant_approver_rejected(client):
    did = _create_document(client)
    resp = _assign(client, did, quality_head_id_override=USER_B.user_id)
    assert resp.status_code == 400, resp.get_json()
    assert _chain(client, did) == {"reviewer": None, "department_head": None, "quality_head": None, "plant_head": None}


# ── Test 2 — nonexistent user ───────────────────────────────────────────────

def test_nonexistent_approver_rejected(client):
    did = _create_document(client)
    resp = _assign(client, did, quality_head_id_override=FAKE_ID)
    assert resp.status_code == 400, resp.get_json()
    assert _chain(client, did) == {"reviewer": None, "department_head": None, "quality_head": None, "plant_head": None}


# ── Test 3 — inactive same-company user ─────────────────────────────────────

def test_inactive_approver_rejected(client):
    did = _create_document(client)
    resp = _assign(client, did, quality_head_id_override=INACTIVE_A.user_id)
    assert resp.status_code == 400, resp.get_json()
    assert _chain(client, did) == {"reviewer": None, "department_head": None, "quality_head": None, "plant_head": None}


# ── Test 4 — valid same-company active user ─────────────────────────────────

def test_valid_same_company_active_users_accepted(client):
    did = _create_document(client)
    resp = _assign(client, did)
    assert resp.status_code == 200, resp.get_json()
    chain = _chain(client, did)
    assert chain["reviewer"]["user_id"] == REVIEWER_A.user_id
    assert chain["department_head"]["user_id"] == DEPT_HEAD_A.user_id
    assert chain["quality_head"]["user_id"] == QUALITY_HEAD_A.user_id


# ── Test 5 — existing creator/author SoD must still hold ───────────────────

def test_author_still_cannot_assign_self_as_approver(client):
    did = _create_document(client)
    resp = _assign(client, did, quality_head_id_override=AUTHOR_A.user_id)
    # AUTHOR_A is a real, active, same-company user, so the new tenant/
    # existence check passes — this must fall through to the pre-existing
    # SoD conflict check (409), unweakened by this fix.
    assert resp.status_code == 409, resp.get_json()
    assert "segregation of duties" in resp.get_json()["error"].lower()
    assert _chain(client, did) == {"reviewer": None, "department_head": None, "quality_head": None, "plant_head": None}


# ── Test 6 — mixed valid + invalid must reject the ENTIRE request ──────────

def test_mixed_valid_and_invalid_rejects_entire_request_atomically(client):
    did = _create_document(client)
    # reviewer/department_head are valid; quality_head is fabricated.
    resp = _assign(client, did, quality_head_id_override=FAKE_ID)
    assert resp.status_code == 400, resp.get_json()
    # Atomicity: NOTHING persisted, not even the two valid ids.
    assert _chain(client, did) == {"reviewer": None, "department_head": None, "quality_head": None, "plant_head": None}


# ── Audit behavior: a rejected assignment must not create a success entry ──

def test_rejected_assignment_creates_no_successful_audit_entry(client):
    did = _create_document(client)
    trail_before = qmsdb.get_audit_trail("document", did)

    resp = _assign(client, did, quality_head_id_override=FAKE_ID)
    assert resp.status_code == 400

    trail_after = qmsdb.get_audit_trail("document", did)
    assert not any(e.get("action") == "Review/approval chain assigned" for e in trail_after), (
        "A rejected assign-chain request must never write a successful-assignment audit entry"
    )
    # A failure entry is fine (matches this route's existing convention for
    # its other two rejection paths); a *success* entry is not.
    assert len(trail_after) >= len(trail_before)

"""
tests/test_segregation_of_duties_wave1.py — Regression coverage for SOD-01
(PharmaGPT Production Readiness Audit): a record's own creator must never be
assignable as one of its approvers, enforced at two layers —
(A) each module's assignment endpoint, and (B) services/workflow_engine.py's
assign_approvers() itself, so the engine refuses even if a future caller
reaches it by some other path than the route layer.

tests/test_deviation_workflow_builder.py::test_workflow_builder_rejects_creator_as_approver
covers deviations' equivalent "assignment endpoint" (the Workflow Builder,
the only place deviation approvers are ever set). This file covers the
other three modules (CAPA, Change Control, Document Control), the engine
layer directly, and the legacy /approval wrapper's auto-self-assign path
that this fix also closes (discovered while fixing this finding — the
wrapper silently assigned "whoever calls it" as the current step's approver
if none was set yet, the same self-approval shape as the named endpoints).
"""

import pytest

import pharmagpt.services.workflow_engine as wfe


@pytest.fixture(autouse=True)
def _active_approver_directory(monkeypatch):
    """CAPA/Change Control assignment validates every approver against the
    company's active users (a real Supabase call in production) before the
    segregation-of-duties check runs; register the identities used below."""
    from tests.conftest import _TEST_TENANT
    from tests.test_assume_company_context import FakeSupabaseClient
    store = {"users": [
        {"id": uid, "company_id": _TEST_TENANT.company_id, "status": "active"}
        for uid in (_TEST_TENANT.user_id, "a-different-user")
    ]}
    for mod in ("qms_capa", "qms_change_control"):
        monkeypatch.setattr(
            f"pharmagpt.routes.{mod}.get_service_role_client", lambda: FakeSupabaseClient(store)
        )


# ── Layer B: services/workflow_engine.py directly ────────────────────────────

def test_reject_creator_as_approver_blocks_matching_user_id(db_path):
    doc = _create_document_direct("Creator-blocked SOP")
    try:
        wfe.reject_creator_as_approver("document", doc["id"], [{"user_id": doc["created_by_user_id"]}])
        assert False, "expected WorkflowError"
    except wfe.WorkflowError as e:
        assert "segregation of duties" in str(e).lower()


def test_reject_creator_as_approver_allows_different_user_id(db_path):
    doc = _create_document_direct("Creator-blocked SOP 2")
    wfe.reject_creator_as_approver("document", doc["id"], [{"user_id": "some-other-user"}])  # must not raise


def test_reject_creator_as_approver_is_noop_for_legacy_record_with_no_captured_creator(db_path):
    """Records created before Wave 1 have created_by_user_id == '' — the
    check must not retroactively block them (no creator identity was ever
    captured for them)."""
    doc = _create_document_direct("Pre-Wave-1 SOP", created_by_user_id="")
    wfe.reject_creator_as_approver("document", doc["id"], [{"user_id": "anyone"}])  # must not raise


def _create_document_direct(title, created_by_user_id="creator-1"):
    from pharmagpt import qms_document_database as qdb
    return qdb.create_document(
        {"title": title}, company_id="test-company",
        created_by_user_id=created_by_user_id, created_by_display_name="Creator",
    )


# ── Layer A + B together, via the real Flask routes ──────────────────────────

def test_capa_assign_endpoint_rejects_creator_as_approver(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    creator_id = capa["created_by_user_id"]
    assert creator_id  # sanity: the route captured a real creator identity

    r = client.post(
        f"/qms/capa/{capa['id']}/workflow/start"
    )
    assert r.status_code == 201, r.get_json()

    r = client.post(
        f"/qms/capa/{capa['id']}/workflow/steps/7/assign",
        json={"approvers": [{"user_id": creator_id, "display_name": "Self"}]},
    )
    assert r.status_code == 409
    assert "segregation of duties" in r.get_json()["error"].lower()


def test_capa_assign_endpoint_accepts_a_different_approver(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    client.post(f"/qms/capa/{capa['id']}/workflow/start")

    # Step 7 ("QA Review") is CAPA_WORKFLOW_V1's first step_type='approval'
    # step reachable without first passing the dedicated Effectiveness
    # Verification gate (step 6) — assign_approvers() only requires the
    # target step to exist and be pending, not to be the *current* step.
    r = client.post(
        f"/qms/capa/{capa['id']}/workflow/steps/7/assign",
        json={"approvers": [{"user_id": "a-different-user", "display_name": "Someone Else"}]},
    )
    assert r.status_code == 200, r.get_json()


def test_change_control_assign_endpoint_rejects_creator_as_approver(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    creator_id = cc["created_by_user_id"]
    assert creator_id

    client.post(f"/qms/change-control/{cc['id']}/workflow/start")
    r = client.post(
        f"/qms/change-control/{cc['id']}/workflow/steps/6/assign",
        json={"approvers": [{"user_id": creator_id, "display_name": "Self"}]},
    )
    assert r.status_code == 409
    assert "segregation of duties" in r.get_json()["error"].lower()


def test_document_assign_endpoint_is_disabled(client):
    """Document Control approvers are fixed by the Author's chain, so the
    per-step assign endpoint always 403s (the creator can never be assigned
    through it); chain-level SoD is covered by tests/test_crit02_segregation_of_duties.py."""
    doc = client.post("/qms/documents", json={"title": "SOP"}).get_json()
    creator_id = doc["created_by_user_id"]
    assert creator_id

    client.post(f"/qms/documents/{doc['id']}/workflow/start")
    r = client.post(
        f"/qms/documents/{doc['id']}/workflow/steps/2/assign",
        json={"approvers": [{"user_id": creator_id, "display_name": "Self"}]},
    )
    assert r.status_code == 403


# ── The legacy /approval wrapper's auto-self-assign path ────────────────────
# Discovered while implementing this fix: routes/qms_documents.py (and the
# equivalent capa/change-control wrappers)::submit_approval silently assigns
# whichever identity calls it as the current step's approver if none is set
# yet, then immediately decides it as that same identity — the exact same
# self-approval shape as the named assignment endpoints, just reached a
# different way. Layer B (the engine) closes this path too, with no route
# change needed. Document Control's step 2 ("Under Review") is
# step_type='approval' and reached by the very first /approval call
# (DOCUMENT_WORKFLOW_V1: activity step 1 auto-completes on submit, landing
# straight on the approval-type step 2) — the cleanest reproduction.

def test_legacy_approval_wrapper_cannot_auto_self_assign_the_creator(client):
    doc = client.post("/qms/documents", json={"title": "SOP"}).get_json()
    # The default test identity created this document; calling /approval as
    # that same identity would previously auto-assign it as step 2's
    # ("Under Review") approver and immediately decide it.
    r = client.post(f"/qms/documents/{doc['id']}/approval", json={"action": "Submitted for Review"})
    # The Author Self-Check gate (DC-003) now stops this path before any
    # workflow instance exists, so nothing can be auto-assigned or decided.
    assert r.status_code == 409
    assert client.get(f"/qms/documents/{doc['id']}").get_json()["status"] == "Draft"

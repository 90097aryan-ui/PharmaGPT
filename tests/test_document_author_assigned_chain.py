"""
tests/test_document_author_assigned_chain.py — SOP workflow correction:
Author-assigned review/approval chain, locked at submission, strictly
sequential Department Head -> Quality Head -> Plant Head (optional, auto-
skipped when unassigned) approval, and the controlled review PDF.

Business rule under test (spec): THE AUTHOR ASSIGNS THE COMPLETE CHAIN. THE
ASSIGNMENT LOCKS WHEN SUBMITTED. THE REVIEWER REVIEWS. THE DEPARTMENT HEAD
APPROVES. THE QUALITY HEAD APPROVES. THE PLANT HEAD APPROVES ONLY IF
ASSIGNED. THE REVIEWER AND APPROVERS NEVER ASSIGN OTHER PEOPLE.

Deliberately no autouse app_context fixture (see test_document_quality_
release.py's identical note) — every test drives the document exclusively
through the `client` fixture so a mid-test TenantContext monkeypatch is
actually re-read by conftest.py's before_request shim.
"""

import io

import fitz
import pytest
from unittest.mock import patch

from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_workflow_database as wfdb

REAUTH_PATH = "pharmagpt.services.esignature_service.reauthenticate"
SIGN = {"password": "correct-password", "meaning": "Approved", "reason": "Looks good"}

# tests/conftest.py's fixed client-fixture tenant — every decision in this
# file is performed AS this same caller, so a step's assigned approver must
# be this exact user_id for that step's decide call to succeed. Distinct
# _NAME constants keep each role's assigned display_name distinguishable in
# assertions even though the underlying user_id is shared.
CALLER_USER_ID = "00000000-0000-0000-0000-000000000001"

# P0 stabilization: CALLER_USER_ID is the Author (the fixed client-fixture
# identity that creates every document in this file). Segregation of duties
# now forbids the Author from also being any approver, so each role below is
# a distinct identity — _as() switches the active identity mid-test so a
# decide call is made AS that role's actual assigned user_id.
REVIEWER_USER_ID = "00000000-0000-0000-0000-000000000002"
DEPT_HEAD_USER_ID = "00000000-0000-0000-0000-000000000003"
QUALITY_HEAD_USER_ID = "00000000-0000-0000-0000-000000000004"
PLANT_HEAD_USER_ID = "00000000-0000-0000-0000-000000000005"
REVIEWER = {"reviewer_user_id": REVIEWER_USER_ID, "reviewer_name": "Rita Reviewer"}
DEPT_HEAD = {"department_head_user_id": DEPT_HEAD_USER_ID, "department_head_name": "Dana Head"}
QUALITY_HEAD = {"quality_head_user_id": QUALITY_HEAD_USER_ID, "quality_head_name": "Quinn Head"}
PLANT_HEAD = {"plant_head_user_id": PLANT_HEAD_USER_ID, "plant_head_name": "Pat Head"}


def _as(monkeypatch, user_id, display_name, role="user"):
    """Switch the client fixture's active identity mid-test (see
    conftest.py's before_request shim) so a workflow decision is made AS
    the role's actual assigned user_id, now that segregation of duties
    forbids the Author identity from holding any approver role."""
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module
    ctx = TenantContext(user_id=user_id, email=f"{user_id}@example.com", display_name=display_name,
                         role=role, company_id=conftest_module._TEST_TENANT.company_id)
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", ctx)


def _reauth(ok=True):
    return patch(REAUTH_PATH, return_value=ok)


def _create_submittable(client, title="Cleaning SOP"):
    doc = client.post("/qms/documents", json={"title": title, "content": "# Cleaning SOP\n\nSome content."}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    r = client.post(f"/qms/documents/{did}/versions/upload",
                     data={"file": (io.BytesIO(b"final content"), "final.txt")},
                     content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    return did


def _assign_full_chain(client, did, include_plant_head=True):
    body = {**REVIEWER, **DEPT_HEAD, **QUALITY_HEAD}
    if include_plant_head:
        body.update(PLANT_HEAD)
    r = client.post(f"/qms/documents/{did}/assign-chain", json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ── A. Author assigns the chain, pre-submission ──────────────────────────────

def test_author_sees_chain_as_unassigned_on_a_new_document(client):
    did = _create_submittable(client)
    chain = client.get(f"/qms/documents/{did}/assign-chain").get_json()
    assert chain == {"reviewer": None, "department_head": None, "quality_head": None, "plant_head": None}


def test_author_can_assign_full_chain(client):
    did = _create_submittable(client)
    chain = _assign_full_chain(client, did)
    assert chain["reviewer"] == {"user_id": REVIEWER_USER_ID, "display_name": "Rita Reviewer"}
    assert chain["department_head"] == {"user_id": DEPT_HEAD_USER_ID, "display_name": "Dana Head"}
    assert chain["quality_head"] == {"user_id": QUALITY_HEAD_USER_ID, "display_name": "Quinn Head"}
    assert chain["plant_head"] == {"user_id": PLANT_HEAD_USER_ID, "display_name": "Pat Head"}


def test_plant_head_is_optional(client):
    did = _create_submittable(client)
    chain = _assign_full_chain(client, did, include_plant_head=False)
    assert chain["plant_head"] is None
    assert chain["reviewer"] and chain["department_head"] and chain["quality_head"]


def test_reviewer_department_head_quality_head_are_required(client):
    did = _create_submittable(client)
    r = client.post(f"/qms/documents/{did}/assign-chain", json={**REVIEWER, **DEPT_HEAD})  # no quality_head
    assert r.status_code == 400
    assert "Quality Head" in r.get_json()["error"]


def test_author_can_change_selections_before_submission_not_locked_out(client):
    """The spec's explicit bug report: 'The Author must NOT be locked out
    after selecting only the Reviewer.' Assigning just the Reviewer first,
    then coming back to complete the chain, must work exactly like
    assigning everything in one call — no partial-assignment lockout."""
    did = _create_submittable(client)
    r1 = client.post(f"/qms/documents/{did}/assign-chain", json={
        **REVIEWER, "department_head_user_id": "", "quality_head_user_id": "",
    })
    assert r1.status_code == 400  # still enforces required fields on THIS call...

    # ...but a document with no chain assigned yet is never "locked" —
    # the Author can simply submit a fresh complete call afterward.
    chain = _assign_full_chain(client, did)
    assert chain["reviewer"]["user_id"] == REVIEWER_USER_ID

    # And can change it again — still Draft, still unlocked.
    r2 = client.post(f"/qms/documents/{did}/assign-chain", json={
        **DEPT_HEAD, **QUALITY_HEAD, "reviewer_user_id": REVIEWER_USER_ID, "reviewer_name": "Rachel Reviewer",
    })
    assert r2.status_code == 200
    assert r2.get_json()["reviewer"]["display_name"] == "Rachel Reviewer"


def test_submit_for_review_blocked_without_complete_chain(client):
    did = _create_submittable(client)
    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 409
    assert "chain" in r.get_json()["error"].lower()


def test_submit_for_review_blocked_with_only_reviewer_assigned(client):
    did = _create_submittable(client)
    client.post(f"/qms/documents/{did}/assign-chain", json={
        **REVIEWER, "department_head_user_id": "x", "quality_head_user_id": "y",
    })
    # overwrite with an incomplete chain isn't possible via the route (400s),
    # so directly exercise the DB layer to simulate a partially-set chain
    # (e.g. a future direct-write bug) and confirm the submission gate still
    # catches it independently of the route-level validation.
    qdb.set_review_chain(did, {"reviewer_user_id": "rev-1", "reviewer_name": "Rita"}, assigned_by="Author")
    r = client.post(f"/qms/documents/{did}/workflow/start")
    assert r.status_code == 409
    assert "chain" in r.get_json()["error"].lower()


# ── B. Submission locks the chain ────────────────────────────────────────────

def test_assign_chain_locked_after_submission(client):
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")

    r = client.post(f"/qms/documents/{did}/assign-chain", json={**REVIEWER, **DEPT_HEAD, **QUALITY_HEAD})
    assert r.status_code == 409
    assert "lock" in r.get_json()["error"].lower() or "draft" in r.get_json()["error"].lower()


def test_assign_chain_locked_enforced_at_db_layer_not_just_route(client):
    """spec §14: 'Do not rely only on frontend controls... Verify backend
    protection against direct assignment changes after submission.' Drives
    qms_document_database.set_review_chain directly — bypassing the route
    entirely — to prove the lock is a real service-layer guard."""
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")

    with pytest.raises(ValueError, match="[Ll]ock|[Dd]raft"):
        qdb.set_review_chain(did, {"reviewer_user_id": "someone-else"}, assigned_by="Attacker")


def test_generic_workflow_assign_endpoint_is_disabled_for_documents(client):
    """spec §16: 'The Quality Release/Approval screen must NOT ask the
    current approver to select other people... The Reviewer must NOT
    assign approvers.' The pre-existing generic per-step /assign endpoint
    (still used by CAPA/Change Control) must always 403 for Document
    Control now, regardless of role or workflow state."""
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")

    r = client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                     json={"approvers": [{"user_id": "someone", "display_name": "Someone"}]})
    assert r.status_code == 403


# ── C. Strictly sequential Department Head -> Quality Head -> Plant Head ────

def _advance_review(client, did, monkeypatch):
    _as(monkeypatch, REVIEWER_USER_ID, "Rita Reviewer")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/2/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_department_head_cannot_act_before_review_is_accepted(client, monkeypatch):
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    # step 3 (department_head_approval) is NOT current yet — step 2 is.
    # Acting AS the rightful Department Head isolates the order violation
    # from an identity mismatch.
    _as(monkeypatch, DEPT_HEAD_USER_ID, "Dana Head")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/3/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 409


def test_quality_head_cannot_act_before_department_head_approves(client, monkeypatch):
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    _advance_review(client, did, monkeypatch)
    # step 4 (quality_head_approval) is NOT current yet — step 3 is
    _as(monkeypatch, QUALITY_HEAD_USER_ID, "Quinn Head")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/4/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 409


def test_full_sequential_chain_with_plant_head_assigned(client, monkeypatch):
    did = _create_submittable(client)
    _assign_full_chain(client, did, include_plant_head=True)
    client.post(f"/qms/documents/{did}/workflow/start")

    _advance_review(client, did, monkeypatch)
    _as(monkeypatch, DEPT_HEAD_USER_ID, "Dana Head")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/3/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    assert next(s for s in r.get_json()["steps"] if s["step_order"] == 3)["status"] == "approved"

    _as(monkeypatch, QUALITY_HEAD_USER_ID, "Quinn Head")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/4/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    state = r.get_json()
    assert next(s for s in state["steps"] if s["step_order"] == 4)["status"] == "approved"
    step5 = next(s for s in state["steps"] if s["step_order"] == 5)
    assert step5["status"] == "pending"
    assert {a["user_id"] for a in step5["approvers"]} == {PLANT_HEAD_USER_ID}

    _as(monkeypatch, PLANT_HEAD_USER_ID, "Pat Head")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/5/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    final_state = r.get_json()
    assert final_state["instance"]["status"] == "completed"
    assert qdb.get_document(did)["status"] == "Approved"
    assert qdb.get_current_version(did)["status"] == "approved"


def test_plant_head_step_auto_skipped_when_not_assigned(client, monkeypatch):
    did = _create_submittable(client)
    _assign_full_chain(client, did, include_plant_head=False)
    client.post(f"/qms/documents/{did}/workflow/start")

    _advance_review(client, did, monkeypatch)
    _as(monkeypatch, DEPT_HEAD_USER_ID, "Dana Head")
    with _reauth(True):
        client.post(f"/qms/documents/{did}/workflow/steps/3/decide", json={"decision": "approve", **SIGN})
    _as(monkeypatch, QUALITY_HEAD_USER_ID, "Quinn Head")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/4/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    state = r.get_json()

    # Plant Head step is auto-skipped — instance completes immediately,
    # WITHOUT a fifth manual decision.
    step5 = next(s for s in state["steps"] if s["step_order"] == 5)
    assert step5["status"] == "skipped"
    assert state["instance"]["status"] == "completed"
    assert qdb.get_document(did)["status"] == "Approved"
    assert qdb.get_current_version(did)["status"] == "approved"


def test_plant_head_actually_decides_when_assigned_not_auto_skipped(client, monkeypatch):
    did = _create_submittable(client)
    _assign_full_chain(client, did, include_plant_head=True)
    client.post(f"/qms/documents/{did}/workflow/start")
    _advance_review(client, did, monkeypatch)
    _as(monkeypatch, DEPT_HEAD_USER_ID, "Dana Head")
    with _reauth(True):
        client.post(f"/qms/documents/{did}/workflow/steps/3/decide", json={"decision": "approve", **SIGN})
    _as(monkeypatch, QUALITY_HEAD_USER_ID, "Quinn Head")
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/4/decide", json={"decision": "approve", **SIGN})
    state = r.get_json()
    step5 = next(s for s in state["steps"] if s["step_order"] == 5)
    assert step5["status"] == "pending"  # NOT skipped — awaiting Plant Head's real decision


# ── D. Actual assigned people are displayed, never "Not Configured" ─────────

def test_workflow_response_shows_actual_assigned_people_with_role_labels(client):
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    wf = client.get(f"/qms/documents/{did}/workflow").get_json()

    review_step = next(s for s in wf["steps"] if s["step_key"] == "under_review")
    assert review_step["role_label"] == "Reviewer"
    assert review_step["approvers"][0]["display_name"] == "Rita Reviewer"
    assert review_step["approvers"][0]["role_label"] == "Reviewer"

    dept_step = next(s for s in wf["steps"] if s["step_key"] == "department_head_approval")
    assert dept_step["role_label"] == "Department Head"
    assert dept_step["approvers"][0]["display_name"] == "Dana Head"

    quality_step = next(s for s in wf["steps"] if s["step_key"] == "quality_head_approval")
    assert quality_step["role_label"] == "Quality Head"
    assert quality_step["approvers"][0]["display_name"] == "Quinn Head"

    plant_step = next(s for s in wf["steps"] if s["step_key"] == "effective")
    assert plant_step["role_label"] == "Plant Head"
    assert plant_step["approvers"][0]["display_name"] == "Pat Head"


def test_workflow_response_never_says_not_configured_for_assigned_role(client):
    """The exact regression named in the spec: 'DO NOT show Department Head:
    Not Configured when a Department Head has actually been assigned.'
    Confirms the pool_summary/'configured' key that produced that string no
    longer exists in the response at all."""
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    wf = client.get(f"/qms/documents/{did}/workflow").get_json()
    for step in wf["steps"]:
        assert "pool_summary" not in step


# ── E. Controlled review PDF ──────────────────────────────────────────────────

def test_review_pdf_is_a_valid_pdf_with_watermark_on_every_page(client):
    did = _create_submittable(client)
    _assign_full_chain(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")

    r = client.get(f"/qms/documents/{did}/review-pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    pdf = fitz.open(stream=r.data, filetype="pdf")
    assert pdf.page_count > 0
    for page in pdf:
        assert "UNDER REVIEW" in page.get_text()


def test_review_pdf_served_inline_not_as_attachment_download(client):
    did = _create_submittable(client)
    r = client.get(f"/qms/documents/{did}/review-pdf")
    cd = r.headers.get("Content-Disposition", "")
    assert "attachment" not in cd.lower()


def test_review_pdf_reflects_actual_document_content(client):
    distinctive = "A very distinctive cleaning procedure phrase 12345."
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": f"# SOP\n\n{distinctive}"}).get_json()
    r = client.get(f"/qms/documents/{doc['id']}/review-pdf")
    pdf = fitz.open(stream=r.data, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in pdf)
    assert distinctive in full_text

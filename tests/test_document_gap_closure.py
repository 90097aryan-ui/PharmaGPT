"""
tests/test_document_gap_closure.py — Document Control "final gap closure"
follow-up: closes the specific gaps identified in staging after Phase 6
(controlled template must be a REAL seeded row, not just prompt text;
Document Control Information header — Prepared By/Reviewed By/Approved By —
must be system-derived; the final Approval step's business name is
"Quality Release", not "Made Effective"; Effective Date is supplied/
confirmed at Quality Release; the full 1.0 -> 1.1 -> 1.2 -> 1.3 -> 2.0
existing-SOP revision lifecycle with two intermediate rejections).

Does NOT re-test what tests/test_document_quality_release.py,
tests/test_document_approver_pool.py, tests/test_document_training_gate.py,
tests/test_document_template.py, tests/test_document_template_ai_enforcement.py,
and tests/test_document_version_immutability.py already cover — see those
files for role-gating, quorum, training-gate math, and immutability-trigger
coverage.
"""

import io
from unittest.mock import patch

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID

REAUTH_PATH = "pharmagpt.services.esignature_service.reauthenticate"
SIGN = {"password": "correct-password", "meaning": "Released", "reason": "All gates satisfied"}


def _reauth(ok=True):
    return patch(REAUTH_PATH, return_value=ok)


CALLER_USER_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py's fixed client-fixture tenant


def _upload_final_version(client, did, text=b"# Final content\n\nProcedure text."):
    """spec §10/§11: Final Author Version is a required hard gate before
    Submit for Review, distinct from the generic Attachments feature — see
    tests/test_document_upload_final_version.py for the dedicated coverage
    of the upload endpoint itself."""
    r = client.post(
        f"/qms/documents/{did}/versions/upload",
        data={"file": (io.BytesIO(text), "final.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_json()


def _reach_approved_via_route(client, did, caller_user_id=CALLER_USER_ID):
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Rita"}]})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/2/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    client.post(f"/qms/documents/{did}/workflow/steps/3/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Al"}]})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/3/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()


def _clear_training_and_release(client, did, effective_date=None):
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "Trainee"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    body = dict(SIGN)
    if effective_date:
        body["effective_date"] = effective_date
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ── §1: the controlled SOP template must be a real seeded row ────────────────

def test_default_sop_template_is_seeded(db_path):
    templates = qdb.list_templates("SOP", COMPANY_ID)
    default = next((t for t in templates if t["name"] == "Standard Operating Procedure (Default)"), None)
    assert default is not None, "no platform-wide default SOP template was seeded"
    assert default["company_id"] == ""
    headings = [h["heading"] for h in default["structure"]]
    assert headings == [
        "1. Purpose", "2. Scope", "3. Responsibilities", "4. Definitions / Abbreviations",
        "5. Procedure", "6. References", "7. Annexures", "8. Revision History",
    ]


def test_default_sop_template_reachable_via_route_and_document_creatable_from_it(client):
    templates = client.get("/qms/documents/templates?doc_type=SOP").get_json()
    default = next((t for t in templates if t["name"] == "Standard Operating Procedure (Default)"), None)
    assert default is not None

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "template_id": default["id"]}).get_json()
    assert doc["template_id"] == default["id"]


def test_seeding_is_idempotent_across_multiple_init_db_calls(db_path):
    """init_db() runs on every app startup — must never create a second
    duplicate default template row."""
    from pharmagpt import database as db
    db.init_db()
    db.init_db()
    templates = qdb.list_templates("SOP", COMPANY_ID)
    defaults = [t for t in templates if t["name"] == "Standard Operating Procedure (Default)"]
    assert len(defaults) == 1


# ── §2: Document Control Information header is system-derived ────────────────

def test_prepared_by_is_the_authenticated_creator_not_client_supplied(client):
    doc = client.post("/qms/documents", json={
        "title": "Cleaning SOP", "content": "x", "prepared_by": "Someone Else Entirely",
    }).get_json()
    # tests/conftest.py's client fixture's fixed fake tenant display_name
    assert doc["prepared_by"] not in ("", "Someone Else Entirely")
    assert doc["prepared_by"] == "Test User"


def test_prepared_by_reviewed_by_approved_by_start_blank_except_prepared(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    assert doc["prepared_by"]
    assert doc.get("reviewed_by", "") == ""
    assert doc.get("approved_by", "") == ""


def test_reviewed_by_and_approved_by_auto_populate_on_decision(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    _reach_approved_via_route(client, did)
    updated = client.get(f"/qms/documents/{did}").get_json()
    assert updated["reviewed_by"] == "Test User"
    assert updated["approved_by"] == "Test User"
    assert updated["review_date"]


def test_reviewed_by_approved_by_effective_date_cannot_be_set_via_put(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    r = client.put(f"/qms/documents/{did}", json={
        "prepared_by": "Hijacked", "reviewed_by": "Hijacked", "approved_by": "Hijacked",
        "effective_date": "2020-01-01", "owner": "Ada",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["owner"] == "Ada"
    assert "Hijacked" not in (body.get("prepared_by", ""), body.get("reviewed_by", ""), body.get("approved_by", ""))
    assert body.get("effective_date") != "2020-01-01"


# ── §4: "Quality Release" business terminology + Effective Date at release ──

def test_final_approval_step_is_named_quality_release_not_made_effective(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did)
    client.post(f"/qms/documents/{did}/workflow/start")
    wf = client.get(f"/qms/documents/{did}/workflow").get_json()
    step3 = next(s for s in wf["steps"] if s["step_order"] == 3)
    assert step3["step_name"] == "Quality Release"
    assert step3["step_name"] != "Made Effective"


def test_effective_date_is_confirmed_at_release_not_defaulted_silently(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    _reach_approved_via_route(client, did)
    released = _clear_training_and_release(client, did, effective_date="2026-03-15")
    assert released["effective_date"] == "2026-03-15"


def test_release_rejects_malformed_effective_date(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    _reach_approved_via_route(client, did)
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "T"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json={**SIGN, "effective_date": "not-a-date"})
    assert r.status_code == 400


def test_release_blocked_when_document_has_no_content(client):
    """Quality Release prerequisite #4 ("required document information
    complete") — a document that reached 'approved' with no drafted content
    at all must still be blocked at release. In practice the normal Submit
    for Review path requires a non-empty Final Author Version upload (see
    _submission_gate_error's Final Author Version gate), so this drives the
    workflow engine directly (bypassing the route-level gate on purpose) to
    isolate and verify release_document()'s own content check."""
    import pharmagpt.app as appmod
    from pharmagpt.services import workflow_engine as wfe

    doc = qdb.create_document({"title": "Cleaning SOP"}, company_id=COMPANY_ID)
    did = doc["id"]
    qdb.record_self_check(did, "Author")
    # audit.log() reads g.tenant, so these direct engine calls (bypassing the
    # route layer on purpose — see docstring) need a short-lived app context.
    # Deliberately NOT held open across the client.*() calls below — see
    # feedback_flask_test_app_context_gotcha in project memory: reusing one
    # app context across client.post() calls makes Flask skip re-running
    # conftest.py's per-request tenant setup.
    with appmod.app.app_context():
        wfe.start_instance("DOCUMENT_WORKFLOW_V1", "document", did, COMPANY_ID, "Author")
        wfe.assign_approvers("document", did, 2, [{"user_id": CALLER_USER_ID, "display_name": "Rita"}])
        wfe.decide_step("document", did, 2, "approve", user_id=CALLER_USER_ID, role="reviewer_qa", performed_by="Rita")
        wfe.assign_approvers("document", did, 3, [{"user_id": CALLER_USER_ID, "display_name": "Al"}])
        wfe.decide_step("document", did, 3, "approve", user_id=CALLER_USER_ID, role="company_admin", performed_by="Al")
    assert qdb.get_document(did)["status"] == "Approved"
    assert not (qdb.get_document(did).get("content") or "").strip()

    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "T"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 409
    assert "content" in r.get_json()["error"].lower()


# ── §7: full existing-SOP revision lifecycle, 1.0 -> 1.1 -> 1.2 -> 1.3 -> 2.0 ──

def test_existing_sop_full_revision_lifecycle_with_two_rejections(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "v1"}).get_json()
    did = doc["id"]
    _reach_approved_via_route(client, did)
    v1_0 = _clear_training_and_release(client, did)
    assert v1_0["version"] == "1.0"
    assert v1_0["status"] == "Effective"

    # 1.0 Effective -> start revision -> 1.1 Draft
    r = client.post(f"/qms/documents/{did}/versions/start-revision")
    assert r.status_code == 201, r.get_json()
    v1_1 = r.get_json()
    assert v1_1["version_number"] == "1.1"
    assert v1_1["status"] == "draft"

    # 1.1 -> Review Rejected -> 1.2 new immutable Draft
    client.put(f"/qms/documents/{did}", json={"content": "v1.1 edits"})
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did, b"v1.1 final upload")
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": CALLER_USER_ID, "display_name": "Rita"}]})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/2/decide",
                         json={"decision": "reject", "comments": "Needs rework", **SIGN})
    assert r.status_code == 200, r.get_json()
    v1_2 = qdb.get_current_version(did)
    assert v1_2["version_number"] == "1.2"
    assert v1_2["status"] == "draft"
    assert v1_2["id"] != v1_1["id"]

    # 1.2 -> Review Accepted -> Approval Rejected -> 1.3 new immutable Draft
    client.put(f"/qms/documents/{did}", json={"content": "v1.2 edits"})
    client.post(f"/qms/documents/{did}/self-check")
    _upload_final_version(client, did, b"v1.2 final upload")
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": CALLER_USER_ID, "display_name": "Rita"}]})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/2/decide", json={"decision": "approve", **SIGN})
    assert r.status_code == 200, r.get_json()
    client.post(f"/qms/documents/{did}/workflow/steps/3/assign",
                json={"approvers": [{"user_id": CALLER_USER_ID, "display_name": "Al"}]})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/workflow/steps/3/decide",
                         json={"decision": "reject", "comments": "Not ready", **SIGN})
    assert r.status_code == 200, r.get_json()
    v1_3 = qdb.get_current_version(did)
    assert v1_3["version_number"] == "1.3"
    assert v1_3["status"] == "draft"

    # 1.3 -> Review Accepted -> Approval Accepted -> Training >=90% -> Quality Release -> 2.0 Effective
    # The version's number is only finalized at the approved->effective
    # transition (see qms_document_database.try_clear_training_gate) — the
    # SAME row that was "1.3" a moment ago is renumbered "2.0" in place, not
    # forked into a separate row (matches the spec's own diagram: "1.3 DRAFT
    # -> ... -> APPROVED -> TRAINING -> QUALITY RELEASE -> 2.0 EFFECTIVE" is
    # one continuous lifecycle, not a fork).
    client.put(f"/qms/documents/{did}", json={"content": "v1.3 final"})
    v1_3_id = qdb.get_current_version(did)["id"]
    _reach_approved_via_route(client, did)
    v2_0 = _clear_training_and_release(client, did)
    assert v2_0["version"] == "2.0"
    assert v2_0["status"] == "Effective"
    assert qdb.get_version(v1_3_id)["version_number"] == "2.0"

    # Every prior (distinct, still-1.x-numbered) version is immutable
    versions = {v["version_number"]: v for v in qdb.get_versions(did)}
    assert set(versions) == {"1.0", "1.1", "1.2", "2.0"}
    assert versions["1.0"]["status"] == "superseded"
    assert versions["1.1"]["status"] == "review_rejected"
    assert versions["1.1"]["rejection_reason"] == "Needs rework"
    assert versions["1.2"]["status"] == "approval_rejected"
    assert versions["1.2"]["rejection_reason"] == "Not ready"
    assert versions["2.0"]["status"] == "effective"
    assert versions["2.0"]["id"] == v1_3_id
    # No version number reused
    assert len({v["version_number"] for v in qdb.get_versions(did)}) == 4

    # Historical versions remain exportable/readable
    r = client.get(f"/qms/documents/{did}/report?version_id={versions['1.1']['id']}")
    assert r.status_code == 200
    assert "1.1" in r.get_json()["markdown"]

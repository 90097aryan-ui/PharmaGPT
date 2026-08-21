"""
tests/test_document_quality_release.py — Document Control redesign (spec
§16/§17/§20): the explicit Quality Coordinator / authorized-Quality-role
release gate. Corrects the earlier Phase 4 behaviour (still covered
historically in tests/test_document_training_gate.py) where training
completion silently flipped the document straight to Effective — that let
ANY user with training-update access perform what must be a distinct,
explicitly authorized action, and gave the Author no way to be blocked from
"making the SOP Effective" since nothing but the training-gate check ever
stood in the way.

POST /qms/documents/<id>/release is now the ONLY path to Effective:
  - 409 unless the current version is already 'approved' (quorum achieved).
  - 409 unless the training gate has cleared (>=90%, >=1 trainee).
  - 403 unless the caller's role is company_admin or reviewer_qa (this
    codebase's existing convention for "Quality/administrative authority" —
    see routes/qms_documents.py::submit_approval's identical role pair).
  - Never reachable by the Author role ("user").
"""

from unittest.mock import patch

REAUTH_PATH = "pharmagpt.services.esignature_service.reauthenticate"
SIGN = {"password": "correct-password", "meaning": "Released", "reason": "All gates satisfied"}


def _reauth(ok=True):
    return patch(REAUTH_PATH, return_value=ok)


# Deliberately no autouse app_context fixture here (unlike
# test_document_training_gate.py) — every test in this file drives the
# document exclusively through the `client` Flask test client, which pushes
# its own fresh request/app context (and therefore a fresh `g`) per call.
# Manually holding one open for the whole test would make Flask reuse that
# single `g` across every client.post() in the test, so a mid-test
# TenantContext monkeypatch (see test_author_role_cannot_release) would
# never actually be re-read by conftest.py's before_request shim.


def _reach_approved_via_route(client, caller_user_id="00000000-0000-0000-0000-000000000001"):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/self-check")
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Rita"}]})
    with _reauth(True):
        client.post(f"/qms/documents/{did}/workflow/steps/2/decide", json={"decision": "approve", **SIGN})
    client.post(f"/qms/documents/{did}/workflow/steps/3/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Al"}]})
    with _reauth(True):
        client.post(f"/qms/documents/{did}/workflow/steps/3/decide", json={"decision": "approve", **SIGN})
    return did


def test_release_blocked_before_approval_reached(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    with _reauth(True):
        r = client.post(f"/qms/documents/{doc['id']}/release", json=SIGN)
    assert r.status_code == 409
    assert "not awaiting release" in r.get_json()["error"] or "approval" in r.get_json()["error"].lower()


def test_release_blocked_when_training_not_cleared(client):
    did = _reach_approved_via_route(client)
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Approved"
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 409
    assert "training" in r.get_json()["error"].lower()
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Approved"


def test_release_succeeds_once_approved_and_training_cleared(client):
    did = _reach_approved_via_route(client)
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "Trainee One"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    assert client.get(f"/qms/documents/{did}/training/gate").get_json()["cleared"] is True

    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["status"] == "Effective"
    assert body["effective_date"]
    assert body["version"] == "1.0"  # first-ever SOP: 0.x -> 1.0 on release


def test_author_role_cannot_release(client, monkeypatch):
    """Spec §7/§16: the Author is NOT responsible for, and must be unable
    to, make the SOP Effective — enforced at the route layer via
    @require_role, not merely by hiding the button in the UI."""
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module

    did = _reach_approved_via_route(client)
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "Trainee One"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})

    author = TenantContext(
        user_id="author-1", email="author@example.com", display_name="Author",
        role="user", company_id=conftest_module._TEST_TENANT.company_id,
    )
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", author)

    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 403
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Approved"


def test_reviewer_qa_role_can_release(client, monkeypatch):
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module

    did = _reach_approved_via_route(client)
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "Trainee One"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})

    qa = TenantContext(
        user_id="qa-1", email="qa@example.com", display_name="Quality Coordinator",
        role="reviewer_qa", company_id=conftest_module._TEST_TENANT.company_id,
    )
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", qa)

    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "Effective"


def test_existing_effective_sop_becomes_2_0_on_next_release(client):
    """1.x -> 2.0 on release, matching the new-SOP 0.x -> 1.0 case."""
    did = _reach_approved_via_route(client)
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "T1"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    with _reauth(True):
        client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert client.get(f"/qms/documents/{did}").get_json()["version"] == "1.0"

    client.post(f"/qms/documents/{did}/versions/start-revision")
    client.post(f"/qms/documents/{did}/self-check")
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": "00000000-0000-0000-0000-000000000001", "display_name": "Rita"}]})
    with _reauth(True):
        client.post(f"/qms/documents/{did}/workflow/steps/2/decide", json={"decision": "approve", **SIGN})
    client.post(f"/qms/documents/{did}/workflow/steps/3/assign",
                json={"approvers": [{"user_id": "00000000-0000-0000-0000-000000000001", "display_name": "Al"}]})
    with _reauth(True):
        client.post(f"/qms/documents/{did}/workflow/steps/3/decide", json={"decision": "approve", **SIGN})

    t2 = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "T2"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t2['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-02", **SIGN})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["version"] == "2.0"


# ── §3/§21: manual version creation is a company_admin-only escape hatch ─────

def test_manual_create_version_blocked_for_non_admin(client, monkeypatch):
    from pharmagpt.auth.context import TenantContext
    import tests.conftest as conftest_module

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()

    author = TenantContext(
        user_id="author-1", email="author@example.com", display_name="Author",
        role="user", company_id=conftest_module._TEST_TENANT.company_id,
    )
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", author)

    r = client.post(f"/qms/documents/{doc['id']}/versions", json={"version": "9.9"})
    assert r.status_code == 403


def test_manual_create_version_allowed_for_company_admin(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/versions", json={"version": "9.9"})
    assert r.status_code == 201


# ── §8: Review Date is system-stamped, never author-supplied ─────────────────

def test_review_date_is_auto_stamped_on_review_acceptance(client):
    caller_user_id = "00000000-0000-0000-0000-000000000001"
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    assert not doc.get("review_date")

    client.post(f"/qms/documents/{did}/self-check")
    client.post(f"/qms/documents/{did}/workflow/start")
    client.post(f"/qms/documents/{did}/workflow/steps/2/assign",
                json={"approvers": [{"user_id": caller_user_id, "display_name": "Rita"}]})
    with _reauth(True):
        client.post(f"/qms/documents/{did}/workflow/steps/2/decide", json={"decision": "approve", **SIGN})

    assert client.get(f"/qms/documents/{did}").get_json()["review_date"]


def test_review_date_and_effective_date_ignored_from_author_put(client):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "content": "x"}).get_json()
    did = doc["id"]
    r = client.put(f"/qms/documents/{did}", json={
        "review_date": "2020-01-01", "effective_date": "2020-01-01", "owner": "Ada",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["owner"] == "Ada"
    assert body.get("review_date") != "2020-01-01"
    assert body.get("effective_date") != "2020-01-01"


# ── §18: Distribution never blocks effectiveness ──────────────────────────────

def test_distribution_never_blocks_release(client):
    did = _reach_approved_via_route(client)
    # No distribution entries added at all, and no acknowledgement either.
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "Trainee One"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "Effective"

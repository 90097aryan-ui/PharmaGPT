"""
tests/test_document_chain_assignment_authorization.py — P0 stabilization
(Document Control critic review, P0-A / P0-B):

P0-A — Author-only chain assignment. POST /qms/documents/<id>/assign-chain
must be enforced server-side by IDENTITY (the caller must be the current
version's Author), not merely by document state. Any other authenticated
tenant user — regardless of role, including company_admin — must receive a
403, not a silently-accepted write.

P0-B — Segregation of duties. The Author must never be assignable as their
own Reviewer, Department Head, Quality Head, or Plant Head. Submitting a
chain where any of those roles' user_id equals the Author's must 409.

Both checks are no-ops for a document whose current version has no captured
author identity (created before this fix) — the codebase's existing
precedent (see the intentionally-never-wired-up tests/test_segregation_of_
duties_wave1.py) is to never retroactively restrict legacy records with no
captured creator identity, and this fix follows the same rule.

Deliberately no autouse app_context fixture (see test_document_quality_
release.py's identical note) — every test drives the document exclusively
through the `client` fixture so a mid-test TenantContext monkeypatch is
actually re-read by conftest.py's before_request shim.
"""

from pharmagpt import qms_document_database as qdb
from pharmagpt.auth.context import TenantContext
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID
import tests.conftest as conftest_module

AUTHOR_USER_ID = "00000000-0000-0000-0000-000000000001"  # conftest.py's fixed client identity

VALID_CHAIN = {
    "reviewer_user_id": "22222222-2222-2222-2222-222222222222", "reviewer_name": "Rita Reviewer",
    "department_head_user_id": "33333333-3333-3333-3333-333333333333", "department_head_name": "Dana Head",
    "quality_head_user_id": "44444444-4444-4444-4444-444444444444", "quality_head_name": "Quinn Head",
}


def _as_other_user(monkeypatch, user_id="11111111-1111-1111-1111-111111111111", role="user"):
    other = TenantContext(
        user_id=user_id, email="other@example.com", display_name="Other User",
        role=role, company_id=BOOTSTRAP_COMPANY_ID,
    )
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", other)


def _create(client, title="SOP"):
    return client.post("/qms/documents", json={"title": title}).get_json()


# ── P0-A: Author-only chain assignment ───────────────────────────────────────

def test_author_can_assign_chain(client):
    doc = _create(client)
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)
    assert r.status_code == 200, r.get_json()


def test_non_author_cannot_assign_chain(client, monkeypatch):
    doc = _create(client)
    _as_other_user(monkeypatch)
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)
    assert r.status_code == 403
    assert "author" in r.get_json()["error"].lower()


def test_non_author_cannot_assign_chain_even_as_company_admin(client, monkeypatch):
    """Role alone does not substitute for being the Author — this is an
    identity check, not a role/permission check."""
    doc = _create(client)
    _as_other_user(monkeypatch, role="company_admin")
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)
    assert r.status_code == 403


def test_non_author_rejection_leaves_chain_untouched(client, monkeypatch):
    doc = _create(client)
    _as_other_user(monkeypatch)
    client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)
    # Switch back is unnecessary — GET has no author restriction — but
    # confirm via the DB layer directly that nothing was persisted.
    chain = qdb.get_review_chain(qdb.get_document(doc["id"]))
    assert chain["reviewer"] is None


def test_author_assignment_still_allowed_only_while_draft(client, monkeypatch):
    """Regression guard: the new identity check must not weaken the
    pre-existing Draft-only state lock — a non-author is rejected by the
    identity check specifically, not merely because of document state."""
    doc = _create(client)
    client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)  # author, succeeds
    client.post(f"/qms/documents/{doc['id']}/self-check")
    import io
    client.post(f"/qms/documents/{doc['id']}/versions/upload",
                data={"file": (io.BytesIO(b"final content"), "final.txt")},
                content_type="multipart/form-data")
    client.post(f"/qms/documents/{doc['id']}/workflow/start")

    # Now submitted (locked). The AUTHOR (not a stranger) is still blocked,
    # by the pre-existing state lock (409), proving the two controls are
    # independent layers rather than one replacing the other.
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)
    assert r.status_code == 409


def test_legacy_document_without_captured_author_falls_back_to_permissive(client, monkeypatch):
    """A document whose current version has no captured created_by_user_id
    (simulating one created before this fix) cannot have an "Author-only"
    rule enforced against it — falls back to the pre-fix behavior instead
    of locking every user out of an existing in-flight Draft."""
    doc = qdb.create_document({"title": "Legacy SOP"}, company_id=BOOTSTRAP_COMPANY_ID)
    assert qdb.get_current_version(doc["id"])["created_by_user_id"] == ""
    _as_other_user(monkeypatch)
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)
    assert r.status_code == 200, r.get_json()


# ── P0-B: Segregation of duties ──────────────────────────────────────────────

def test_valid_independent_chain_succeeds(client):
    doc = _create(client)
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)
    assert r.status_code == 200, r.get_json()


def test_author_cannot_be_reviewer(client):
    doc = _create(client)
    body = {**VALID_CHAIN, "reviewer_user_id": AUTHOR_USER_ID, "reviewer_name": "Self"}
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=body)
    assert r.status_code == 409
    err = r.get_json()["error"].lower()
    assert "segregation of duties" in err and "reviewer" in err


def test_author_cannot_be_department_head(client):
    doc = _create(client)
    body = {**VALID_CHAIN, "department_head_user_id": AUTHOR_USER_ID, "department_head_name": "Self"}
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=body)
    assert r.status_code == 409
    err = r.get_json()["error"].lower()
    assert "segregation of duties" in err and "department head" in err


def test_author_cannot_be_quality_head(client):
    doc = _create(client)
    body = {**VALID_CHAIN, "quality_head_user_id": AUTHOR_USER_ID, "quality_head_name": "Self"}
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=body)
    assert r.status_code == 409
    err = r.get_json()["error"].lower()
    assert "segregation of duties" in err and "quality head" in err


def test_author_cannot_be_plant_head(client):
    doc = _create(client)
    body = {**VALID_CHAIN, "plant_head_user_id": AUTHOR_USER_ID, "plant_head_name": "Self"}
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=body)
    assert r.status_code == 409
    err = r.get_json()["error"].lower()
    assert "segregation of duties" in err and "plant head" in err


def test_multiple_self_assignment_conflicts_reported_together(client):
    doc = _create(client)
    body = {**VALID_CHAIN, "reviewer_user_id": AUTHOR_USER_ID, "quality_head_user_id": AUTHOR_USER_ID}
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=body)
    assert r.status_code == 409
    err = r.get_json()["error"].lower()
    assert "reviewer" in err and "quality head" in err


def test_plant_head_remains_optional_with_segregation_check_in_place(client):
    doc = _create(client)
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=VALID_CHAIN)  # no plant_head key
    assert r.status_code == 200
    assert r.get_json()["plant_head"] is None


def test_segregation_check_is_noop_for_legacy_document_without_captured_author(client):
    doc = qdb.create_document({"title": "Legacy SOP"}, company_id=BOOTSTRAP_COMPANY_ID)
    body = {**VALID_CHAIN, "reviewer_user_id": AUTHOR_USER_ID, "reviewer_name": "Self"}
    r = client.post(f"/qms/documents/{doc['id']}/assign-chain", json=body)
    assert r.status_code == 200, r.get_json()

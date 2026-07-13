"""
tests/test_urs_lifecycle.py — Regression coverage for Stabilization
Iteration 2's document-control automation and lifecycle enforcement:

  - Priority 3: Draft -> Under Review -> Approved -> Effective transitions
    are enforced server-side; invalid transitions are rejected (409); PUT
    can no longer set status directly (400) or silently mutate
    system-controlled fields.
  - Priority 4: urs_number/doc_number/revision/version are always
    server-issued, never taken from the client, even if the client sends
    values for them.
  - Priority 5: reviewed_by/approved_by are set by the approval workflow,
    not at creation.
"""

from unittest.mock import patch

import pytest

from pharmagpt import urs_database as udb
from pharmagpt.auth.context import TenantContext
from pharmagpt.services import urs_lifecycle as lifecycle

SAMPLE_TENANT = TenantContext(
    user_id="user-1", email="jane@example.com", display_name="Jane Reviewer",
    role="reviewer_qa", company_id="company-1",
)


def _make_urs(client, **overrides):
    payload = {"title": "Lifecycle Test URS", "equipment_name": "Autoclave"}
    payload.update(overrides)
    return client.post("/urs/", json=payload).get_json()


# ── Document control automation (priority 4) ───────────────────────────────

def test_urs_number_and_doc_number_are_auto_generated_not_client_supplied(client):
    urs = _make_urs(
        client,
        urs_number="CLIENT-SUPPLIED-SHOULD-BE-IGNORED",
        doc_number="ALSO-IGNORED",
    )
    assert urs["urs_number"].startswith("URS-")
    assert urs["doc_number"].startswith("QA-URS-")
    assert urs["urs_number"] != "CLIENT-SUPPLIED-SHOULD-BE-IGNORED"
    assert urs["doc_number"] != "ALSO-IGNORED"


def test_urs_numbers_increment_sequentially(client):
    a = _make_urs(client, title="A")
    b = _make_urs(client, title="B")
    seq_a = int(a["urs_number"].rsplit("-", 1)[1])
    seq_b = int(b["urs_number"].rsplit("-", 1)[1])
    assert seq_b == seq_a + 1


def test_revision_version_and_status_always_start_at_system_defaults(client):
    urs = _make_urs(client, revision="Z", version="9.9", status="approved")
    assert urs["revision"] == "A"
    assert urs["version"] == "1.0"
    assert urs["status"] == "draft"


def test_reviewed_by_approved_by_effective_date_start_blank_at_creation(client):
    """Priority 5: these move to the approval workflow, so creation must
    never accept them even if a client sends values."""
    urs = _make_urs(
        client,
        reviewed_by="Someone", approved_by="Someone Else", effective_date="2020-01-01",
    )
    assert urs["reviewed_by"] == ""
    assert urs["approved_by"] == ""
    assert urs["effective_date"] == ""


def test_prepared_by_defaults_to_client_value_when_no_tenant_present(client):
    """The `client` fixture bypasses auth entirely (no g.tenant) — this
    documents the fallback behavior tests rely on, distinct from the
    real-auth-derived case covered in test_urs_docx_download_auth.py."""
    urs = _make_urs(client, prepared_by="Manual Name")
    assert urs["prepared_by"] == "Manual Name"


# ── PUT no longer accepts system-controlled fields (priority 3, 4, 5) ──────

def test_put_rejects_direct_status_change(client):
    urs = _make_urs(client)
    resp = client.put(f"/urs/{urs['id']}", json={"status": "approved"})
    assert resp.status_code == 400
    assert udb.get_urs(urs["id"])["status"] == "draft"


def test_put_silently_ignores_system_controlled_fields_but_keeps_others(client):
    urs = _make_urs(client)
    resp = client.put(f"/urs/{urs['id']}", json={
        "urs_number": "HACKED", "revision": "Z", "prepared_by": "Spoofed",
        "department": "Quality Control",
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated["urs_number"] == urs["urs_number"]
    assert updated["revision"] == "A"
    assert updated["prepared_by"] == urs["prepared_by"]
    assert updated["department"] == "Quality Control"  # ordinary field still editable


# ── Lifecycle transition enforcement (priority 3) ───────────────────────────

def test_create_urs_ignores_client_supplied_approved_status(db_path):
    """Belt-and-braces at the DB layer too: even calling udb.create_urs()
    directly with status='approved' in the payload must not bypass Draft."""
    urs = udb.create_urs({"title": "Direct DB Bypass Attempt", "status": "approved"})
    assert urs["status"] == "draft"


def test_approval_rejects_skip_ahead_transition(client):
    urs = _make_urs(client)
    resp = client.post(f"/urs/{urs['id']}/approval", json={
        "action": "Approved", "performed_by": "QA Bob", "role": "QA",
    })
    assert resp.status_code == 409
    assert udb.get_urs(urs["id"])["status"] == "draft"


def test_approval_valid_transition_sequence_reaches_approved(client):
    urs = _make_urs(client)
    uid = urs["id"]

    r1 = client.post(f"/urs/{uid}/approval", json={
        "action": "Submitted for Review", "performed_by": "Author A", "role": "Author",
    })
    assert r1.status_code == 201
    mid = udb.get_urs(uid)
    assert mid["status"] == "under_review"
    assert mid["reviewed_by"] == ""  # submitting for review is not the reviewer signing off

    r2 = client.post(f"/urs/{uid}/approval", json={
        "action": "Review Complete", "performed_by": "QA Reviewer", "role": "QA",
    })
    assert r2.status_code == 201
    assert udb.get_urs(uid)["reviewed_by"] == "QA Reviewer"

    r3 = client.post(f"/urs/{uid}/approval", json={
        "action": "Approved", "performed_by": "QA Manager", "role": "QA Manager",
    })
    assert r3.status_code == 201
    final = udb.get_urs(uid)
    assert final["status"] == "approved"
    assert final["approved_by"] == "QA Manager"


def test_rejecting_a_previously_approved_document_bumps_revision(client):
    urs = _make_urs(client)
    uid = urs["id"]
    client.post(f"/urs/{uid}/approval", json={"action": "Submitted for Review", "performed_by": "A"})
    client.post(f"/urs/{uid}/approval", json={"action": "Approved", "performed_by": "B"})
    assert udb.get_urs(uid)["revision"] == "A"

    resp = client.post(f"/urs/{uid}/approval", json={"action": "Rejected", "performed_by": "C"})
    assert resp.status_code == 201
    updated = udb.get_urs(uid)
    assert updated["status"] == "draft"
    assert updated["revision"] == "B"


def test_rejecting_a_draft_never_approved_does_not_bump_revision(client):
    urs = _make_urs(client)
    uid = urs["id"]
    client.post(f"/urs/{uid}/approval", json={"action": "Submitted for Review", "performed_by": "A"})
    resp = client.post(f"/urs/{uid}/approval", json={"action": "Rejected", "performed_by": "B"})
    assert resp.status_code == 201
    updated = udb.get_urs(uid)
    assert updated["status"] == "draft"
    assert updated["revision"] == "A"


def test_make_effective_sets_effective_date(client):
    urs = _make_urs(client)
    uid = urs["id"]
    client.post(f"/urs/{uid}/approval", json={"action": "Submitted for Review", "performed_by": "A"})
    client.post(f"/urs/{uid}/approval", json={"action": "Approved", "performed_by": "B"})
    assert udb.get_urs(uid)["effective_date"] == ""

    resp = client.post(f"/urs/{uid}/approval", json={"action": "Make Effective", "performed_by": "C"})
    assert resp.status_code == 201
    updated = udb.get_urs(uid)
    assert updated["status"] == "effective"
    assert updated["effective_date"] != ""


def test_obsolete_only_reachable_from_effective(client):
    urs = _make_urs(client)
    uid = urs["id"]
    resp = client.post(f"/urs/{uid}/approval", json={"action": "Obsolete", "performed_by": "A"})
    assert resp.status_code == 409


def test_approval_requires_performed_by(client):
    urs = _make_urs(client)
    resp = client.post(f"/urs/{urs['id']}/approval", json={"action": "Submitted for Review"})
    assert resp.status_code == 400


# ── urs_lifecycle module unit tests ─────────────────────────────────────────

def test_validate_transition_rejects_illegal_moves():
    with pytest.raises(lifecycle.InvalidTransitionError):
        lifecycle.validate_transition(lifecycle.DRAFT, lifecycle.APPROVED)
    with pytest.raises(lifecycle.InvalidTransitionError):
        lifecycle.validate_transition(lifecycle.OBSOLETE, lifecycle.DRAFT)


def test_validate_transition_allows_noop():
    lifecycle.validate_transition(lifecycle.DRAFT, lifecycle.DRAFT)  # must not raise


def test_bump_revision_sequence():
    assert lifecycle.bump_revision("A") == "B"
    assert lifecycle.bump_revision("Z") == "AA"
    assert lifecycle.bump_revision("") == "B"


# ── Identity-derived approval fields (priority 5, real auth) ───────────────

@pytest.fixture()
def authed_client(db_path):
    import pharmagpt.app as appmod
    return appmod.app.test_client()


def test_approval_performed_by_derived_from_authenticated_user(authed_client):
    """When a real tenant is present, performed_by/role come from the
    authenticated identity, not whatever the client sends — the free-text
    "Your name" field a spoofable client could set is only a fallback."""
    with patch("pharmagpt.auth.middleware.resolve_tenant_context", return_value=SAMPLE_TENANT):
        create_resp = authed_client.post(
            "/urs/", json={"title": "Authed Approval Test", "equipment_name": "X"},
            headers={"Authorization": "Bearer good-token"},
        )
        uid = create_resp.get_json()["id"]

        approval_resp = authed_client.post(
            f"/urs/{uid}/approval",
            json={"action": "Submitted for Review", "performed_by": "Spoofed Name", "role": "Spoofed Role"},
            headers={"Authorization": "Bearer good-token"},
        )

    assert approval_resp.status_code == 201
    entry = approval_resp.get_json()
    assert entry["performed_by"] == "Jane Reviewer"
    assert entry["role"] == "reviewer_qa"

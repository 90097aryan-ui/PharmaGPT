"""
Migration safety for the standardized Validation approval workflow:
database initialization is additive and idempotent, protocol-level approval is
back-filled from legacy container-level approvals exactly once, and documents
that were in flight (or already approved) under the pre-standard workflow can
still be completed or rejected-and-resubmitted without a data fix.
"""

import pytest

from pharmagpt import database as maindb
from pharmagpt import qual_database as qdb
from pharmagpt import urs_database as udb
from pharmagpt import validation_approval_database as vadb
from pharmagpt.services import validation_approval as va
from tests._va_helpers import as_signer, drive_to_approved, post

COMPANY = "52df3b4a-d37e-4176-8a52-7171adf39637"


def _legacy_qual(status, protocol_types=("IQ", "OQ"), prepared_by=""):
    # No created_by_user_id: models a row written before creator identity existed.
    q = qdb.create_qualification({"title": f"legacy-{status}", "equipment_name": "E",
                                  "prepared_by": prepared_by}, company_id=COMPANY)
    qdb.update_qualification(q["id"], {"status": status})
    ids = [qdb.create_protocol(q["id"], t, {})["id"] for t in protocol_types]
    # Simulate rows written BEFORE the approval_status column existed.
    conn = maindb.get_connection()
    with conn:
        conn.execute("UPDATE qual_protocols SET approval_status = NULL WHERE qual_id = ?", (q["id"],))
    conn.close()
    return q["id"], ids


def test_init_db_is_idempotent_and_keeps_existing_signoffs(db_path):
    vadb.add_signoff(company_id=COMPANY, doc_type="URS", record_id=1, revision="A",
                     signatory_key="prepared_by", designation="Validation Engineer",
                     signer_user_id="u1", signer_name="U", signer_role="user")
    maindb.init_db()
    maindb.init_db()
    assert len(vadb.list_signoffs(COMPANY, "URS", 1)) == 1


@pytest.mark.parametrize("container,expected", [
    ("draft", "draft"), ("under_review", "under_review"), ("pending_approval", "pending_approval"),
    ("approved", "approved"), ("closed", "approved"), ("obsolete", "obsolete"),
])
def test_protocol_approval_status_is_backfilled_from_the_legacy_container(db_path, container, expected):
    qid, pids = _legacy_qual(container)
    maindb.init_db()
    assert [qdb.get_protocol(p)["approval_status"] for p in pids] == [expected, expected]


def test_backfill_runs_once_and_never_overwrites_later_changes(db_path):
    qid, pids = _legacy_qual("approved")
    maindb.init_db()
    qdb.set_protocol_approval_status(pids[0], "effective")
    maindb.init_db()
    assert qdb.get_protocol(pids[0])["approval_status"] == "effective"


def test_new_protocols_start_in_draft_not_null(db_path):
    q = qdb.create_qualification({"title": "n", "equipment_name": "E"}, company_id=COMPANY)
    p = qdb.create_protocol(q["id"], "IQ", {})
    assert p["approval_status"] == "draft"


def test_protocol_with_null_status_is_treated_as_draft(db_path):
    qid, pids = _legacy_qual("draft")          # NULL, no init_db re-run
    assert qdb.get_protocol_approval_status(qdb.get_protocol(pids[0])) == "draft"


# ── in-flight / already-approved legacy records ──────────────────────────────

def test_legacy_approved_protocol_can_be_made_effective_and_published(client, monkeypatch):
    qid, pids = _legacy_qual("approved", ("IQ",))
    maindb.init_db()                              # back-fill -> approved, zero ledger rows
    assert vadb.list_signoffs(COMPANY, "IQ", pids[0], include_superseded=True) == []
    as_signer(monkeypatch, "final_approval")
    r = post(client, f"/qual/{qid}/protocols", pids[0], "Make Effective")
    assert r.status_code == 201, r.get_json()
    assert maindb.get_kb_document_by_source("qualification_protocol", pids[0], COMPANY)


def test_legacy_in_flight_protocol_is_rejected_then_resubmitted_through_the_new_workflow(client, monkeypatch):
    # Legacy row: blank creator id, but prepared_by carries the author's authenticated name.
    qid, pids = _legacy_qual("under_review", ("IQ",), prepared_by="User 01")
    maindb.init_db()                              # protocol -> under_review with no ledger
    as_signer(monkeypatch, "reviewed_by")
    assert post(client, f"/qual/{qid}/protocols", pids[0], "Rejected", comments="restart under new SOP").status_code == 201
    assert qdb.get_protocol(pids[0])["approval_status"] == "draft"
    drive_to_approved(client, monkeypatch, f"/qual/{qid}/protocols", pids[0])  # author matched by legacy name
    assert qdb.get_protocol(pids[0])["approval_status"] == "approved"
    assert len(vadb.list_signoffs(COMPANY, "IQ", pids[0])) == 7


def test_legacy_pending_approval_urs_can_only_be_rejected(client, monkeypatch):
    urs = udb.create_urs({"title": "legacy", "equipment_name": "E"}, company_id=COMPANY)
    udb.update_urs(urs["id"], {"status": "pending_approval"})
    as_signer(monkeypatch, "final_approval")
    assert post(client, "/urs", urs["id"], "Sign Off").status_code == 409
    assert post(client, "/urs", urs["id"], "Make Effective").status_code == 409
    assert post(client, "/urs", urs["id"], "Rejected", comments="restart").status_code == 201
    assert udb.get_urs(urs["id"])["status"] == "draft"


def test_a_record_cannot_reach_approved_without_a_ledger_so_grandfathering_cannot_be_abused(client, monkeypatch):
    urs = udb.create_urs({"title": "new", "equipment_name": "E"}, company_id=COMPANY,
                         created_by_user_id="10000000-0000-0000-0000-000000000001",
                         created_by_display_name="User 01")
    drive_to_approved(client, monkeypatch, "/urs", urs["id"])
    rows = vadb.list_signoffs(COMPANY, "URS", urs["id"], include_superseded=True)
    assert not va.is_legacy_approved(rows)        # any record approved by the new flow has rows


def test_standard_status_set_is_a_superset_of_every_legacy_status():
    legacy = {"draft", "under_review", "pending_approval", "approved", "effective", "obsolete"}
    from pharmagpt.services import urs_lifecycle
    assert legacy <= urs_lifecycle.ALL_STATUSES


# ══ Legacy states per document type (recovery procedures are in docs/VALIDATION_APPROVAL_RECOVERY.md) ═══════

from pharmagpt import qms_document_database as dqdb          # noqa: E402
from pharmagpt.services import kb_sync                        # noqa: E402

AUTHOR_ID = "10000000-0000-0000-0000-000000000001"


def _legacy_urs(status, prepared_by="User 01"):
    """A URS row as written before creator identity existed (blank id/name), authored by 'User 01'."""
    u = udb.create_urs({"title": f"legacy {status}", "equipment_name": "E", "prepared_by": prepared_by}, company_id=COMPANY)
    udb.update_urs(u["id"], {"status": status})
    return u["id"]


def _legacy_dq(status="Draft"):
    d = dqdb.create_document({"title": "legacy dq", "doc_type": "DQ", "content": "# DQ\nbody", "prepared_by": "User 01"},
                             company_id=COMPANY, created_by_user_id=AUTHOR_ID)   # first version row carries the author
    if status != "Draft":
        dqdb.update_document(d["id"], {"status": status}, allow_controlled_fields=True)
    return d["id"]


def _kb(source, rid):
    return maindb.get_kb_document_by_source(source, rid, COMPANY)


# ── URS ──────────────────────────────────────────────────────────────────────

def test_legacy_urs_draft_is_submittable_by_its_author_and_not_by_others(client, monkeypatch):
    uid = _legacy_urs("draft")
    from tests._va_helpers import impersonate, membership
    impersonate(monkeypatch, "10000000-0000-0000-0000-000000000099", "user", {"Submit"},
                memberships=[membership("VALIDATION", "Initiator")])
    assert post(client, "/urs", uid, "Submitted for Review").status_code == 403
    as_signer(monkeypatch, "prepared_by")
    assert post(client, "/urs", uid, "Submitted for Review").status_code == 201


def test_legacy_urs_under_review_recovers_by_rejection_then_publishes_when_effective(client, monkeypatch):
    uid = _legacy_urs("under_review")
    as_signer(monkeypatch, "reviewed_by")
    assert post(client, "/urs", uid, "Rejected", comments="restart under standard workflow").status_code == 201
    assert udb.get_urs(uid)["status"] == "draft"
    drive_to_approved(client, monkeypatch, "/urs", uid)
    assert _kb("urs", uid) is None
    as_signer(monkeypatch, "final_approval")
    assert post(client, "/urs", uid, "Make Effective").status_code == 201
    assert _kb("urs", uid) is not None


def test_legacy_urs_approved_becomes_effective_and_is_published(client, monkeypatch):
    uid = _legacy_urs("approved")
    as_signer(monkeypatch, "final_approval")
    assert post(client, "/urs", uid, "Make Effective").status_code == 201
    assert _kb("urs", uid) is not None


def test_legacy_urs_effective_stays_effective_can_be_obsoleted_and_republished(client, monkeypatch):
    uid = _legacy_urs("effective")
    udb.update_urs(uid, {"effective_date": "2025-01-01"})
    urs = udb.get_urs(uid)
    # Recovery for "Effective but never reached the KB": the gate allows publication (no ledger = pre-standard).
    from pharmagpt.app import app as flask_app
    with flask_app.app_context():
        kb_sync.publish_to_kb(source_type="urs", source_id=uid, company_id=COMPANY, title=urs["title"], doc_type="URS",
                              doc_number=urs["doc_number"], version="1.0", content_markdown="# URS", effective_date="2025-01-01")
    assert _kb("urs", uid) is not None
    as_signer(monkeypatch, "final_approval")
    assert post(client, "/urs", uid, "Obsolete", comments="superseded").status_code == 201
    assert udb.get_urs(uid)["status"] == "obsolete"


def test_legacy_urs_rejected_draft_with_old_trail_resubmits_under_the_standard_workflow(client, monkeypatch):
    uid = _legacy_urs("draft")
    udb.add_approval_entry(uid, "Rejected", "Old Reviewer", "reviewer_qa", "old trail entry", "A")
    drive_to_approved(client, monkeypatch, "/urs", uid)
    assert udb.get_urs(uid)["status"] == "approved"
    assert any(e["comments"] == "old trail entry" for e in udb.get_approval_trail(uid))   # history preserved


# ── DQ ───────────────────────────────────────────────────────────────────────

def _dq_ready(client, did):
    import io
    assert client.post(f"/qms/documents/{did}/self-check").status_code == 200
    r = client.post(f"/qms/documents/{did}/versions/upload", data={"file": (io.BytesIO(b"final"), "f.txt")},
                    content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()


def test_legacy_dq_draft_uses_first_version_creator_and_the_standard_workflow(client, monkeypatch):
    did = _legacy_dq("Draft")
    conn = maindb.get_connection()
    with conn:                                             # a row from before document-level creator columns
        conn.execute("UPDATE qms_documents SET created_by_user_id = '', created_by_display_name = '' WHERE id = ?", (did,))
    conn.close()
    as_signer(monkeypatch, "prepared_by")
    _dq_ready(client, did)
    drive_to_approved(client, monkeypatch, "/qms/documents", did)
    assert dqdb.get_document(did)["status"] == "Approved"


def test_legacy_dq_approved_becomes_effective_after_training_and_is_published(client, monkeypatch):
    did = _legacy_dq("Approved")
    v = dqdb.get_current_version(did)
    for s in ("under_review", "pending_approval", "approved"):
        dqdb.transition_version_status(v["id"], s)
    t = dqdb.add_training(did, {"trainee_name": "Op", "role": "Operator"})
    dqdb.update_training_status(t["id"], "Completed", "2026-01-01")
    as_signer(monkeypatch, "final_approval")
    r = post(client, "/qms/documents", did, "Make Effective")
    assert r.status_code == 201, r.get_json()
    assert dqdb.get_document(did)["status"] == "Effective"
    assert _kb("document", did) is not None


def test_legacy_dq_effective_can_be_obsoleted(client, monkeypatch):
    did = _legacy_dq("Effective")
    as_signer(monkeypatch, "final_approval")
    r = post(client, "/qms/documents", did, "Obsolete", comments="retired")
    assert r.status_code == 201 and dqdb.get_document(did)["status"] == "Obsolete"


def test_dq_rejected_under_the_standard_workflow_forks_a_version_and_resubmits(client, monkeypatch):
    did = _legacy_dq("Draft")
    as_signer(monkeypatch, "prepared_by")
    _dq_ready(client, did)
    assert post(client, "/qms/documents", did, "Submitted for Review").status_code == 201
    as_signer(monkeypatch, "reviewed_by")
    assert post(client, "/qms/documents", did, "Rejected", comments="fix").status_code == 201
    as_signer(monkeypatch, "prepared_by")
    _dq_ready(client, did)                               # the forked draft needs its own Self-Check/final version
    assert post(client, "/qms/documents", did, "Submitted for Review").status_code == 201
    assert len(vadb.list_signoffs(COMPANY, "DQ", did, include_superseded=True)) == 2


# ── protocols: effective / rejected ─────────────────────────────────────────

def test_legacy_approved_container_protocols_stay_publishable(db_path):
    qid, pids = _legacy_qual("approved", ("IQ",), prepared_by="User 01")
    maindb.init_db()
    p = qdb.get_protocol(pids[0])
    from pharmagpt.app import app as flask_app
    with flask_app.app_context():
        kb_sync.publish_to_kb(source_type="qualification_protocol", source_id=p["id"], company_id=COMPANY, title="IQ",
                              doc_type="IQ", doc_number="N", version="A", content_markdown="# IQ", effective_date=None)
    assert _kb("qualification_protocol", p["id"]) is not None


def test_rejected_legacy_protocol_resubmits_with_a_fresh_cycle(client, monkeypatch):
    qid, pids = _legacy_qual("draft", ("IQ",), prepared_by="User 01")
    maindb.init_db()
    drive_to_approved(client, monkeypatch, f"/qual/{qid}/protocols", pids[0])
    as_signer(monkeypatch, "final_approval")
    assert post(client, f"/qual/{qid}/protocols", pids[0], "Rejected", comments="redo").status_code == 201
    drive_to_approved(client, monkeypatch, f"/qual/{qid}/protocols", pids[0])
    assert len(vadb.list_signoffs(COMPANY, "IQ", pids[0])) == 7
    assert len(vadb.list_signoffs(COMPANY, "IQ", pids[0], include_superseded=True)) == 14

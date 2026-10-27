"""
Hardening regression tests for the Validation approval workflow:

  * authorship — holding Validation:Submit is not enough; only the record's
    authenticated creator may submit it (URS, DQ, IQ, OQ, PQ);
  * creator identity — stamped once from the session, never client-writable,
    with defined fallbacks for records that pre-date the column;
  * approval-before-execution — IQ/OQ/PQ cannot be executed or completed until
    the protocol itself is approved (not merely a sibling);
  * document-level segregation of duties now has a captured creator to check.
"""

import pytest

import pharmagpt.services.workflow_engine as wfe
from pharmagpt import database as maindb
from pharmagpt import qms_database as qmsdb
from pharmagpt import qms_document_database as dqdb
from pharmagpt import qual_database as qdb
from pharmagpt import urs_database as udb
from pharmagpt import validation_approval_database as vadb
from tests._va_helpers import (
    CHAIN, SIGNERS, as_signer, drive_to_approved, impersonate, membership, post, sign_extra,
)
from tests.test_validation_approval_workflow import KINDS, Suite

COMPANY = "52df3b4a-d37e-4176-8a52-7171adf39637"
OTHER_USER = "10000000-0000-0000-0000-000000000099"


def as_other_initiator(monkeypatch, role="user"):
    """Same department, same permission, same functional role as the author — but not the author."""
    impersonate(monkeypatch, OTHER_USER, role, {"Submit", "View", "Review", "Approve", "Reject"},
                memberships=[membership("VALIDATION", "Initiator")])


def _set_creator(suite, user_id, name):
    table = {"urs": "urs_projects", "dq": "qms_documents"}.get(suite.kind, "qual_protocols")
    conn = maindb.get_connection()
    with conn:
        conn.execute(f"UPDATE {table} SET created_by_user_id = ?, created_by_display_name = ? WHERE id = ?",
                     (user_id, name, suite.rid))
    conn.close()


def _creator_of(suite):
    table = {"urs": "urs_projects", "dq": "qms_documents"}.get(suite.kind, "qual_protocols")
    conn = maindb.get_connection()
    row = conn.execute(f"SELECT created_by_user_id, created_by_display_name FROM {table} WHERE id = ?",
                       (suite.rid,)).fetchone()
    conn.close()
    return dict(row)


@pytest.fixture(params=KINDS)
def suite(request, client, monkeypatch):
    return Suite(request.param, client, monkeypatch)


# ══ Authorship ════════════════════════════════════════════════════════════════

def test_creator_identity_is_stamped_from_the_session(suite):
    c = _creator_of(suite)
    assert c["created_by_user_id"] == SIGNERS["prepared_by"][0]
    assert c["created_by_display_name"] == "User 01"


def test_a_different_user_with_submit_permission_cannot_submit_someone_elses_document(suite, monkeypatch):
    as_other_initiator(monkeypatch)
    r = suite.act("Submitted for Review")
    assert r.status_code == 403 and "author" in r.get_json()["error"].lower()
    assert suite.status() == "draft"
    assert suite.ledger_rows(superseded=True) == []
    actions = [a["action"] for a in qmsdb.get_audit_trail(suite.esig_type, suite.audit_record_id())]
    assert any("not the document's author" in a for a in actions)
    # ...and the real author still can.
    as_signer(monkeypatch, "prepared_by")
    assert suite.act("Submitted for Review").status_code == 201


def test_company_admin_cannot_submit_someone_elses_document_either(suite, monkeypatch):
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000aa", "company_admin",
                {"Submit", "Approve", "Review", "Reject"})
    assert suite.act("Submitted for Review").status_code == 403
    assert suite.status() == "draft"


def test_client_supplied_creator_fields_are_ignored_at_creation(client, monkeypatch):
    as_signer(monkeypatch, "prepared_by")
    r = client.post("/urs/", json={"title": "t", "equipment_name": "e",
                                   "created_by_user_id": OTHER_USER, "created_by_display_name": "Mallory"})
    assert r.get_json()["created_by_user_id"] == SIGNERS["prepared_by"][0]
    r = client.post("/qms/documents", json={"title": "d", "doc_type": "DQ",
                                            "created_by_user_id": OTHER_USER})
    assert r.get_json()["created_by_user_id"] == SIGNERS["prepared_by"][0]


def test_creator_cannot_be_rewritten_through_updates(suite, monkeypatch):
    as_signer(monkeypatch, "prepared_by")
    attempt = {"created_by_user_id": OTHER_USER, "created_by_display_name": "Mallory", "prepared_by": "Mallory"}
    if suite.kind == "urs":
        suite.client.put(f"/urs/{suite.rid}", json=attempt)
    elif suite.kind == "dq":
        suite.client.put(f"/qms/documents/{suite.rid}", json=attempt)
    else:
        suite.client.put(f"/qual/{suite.qid}/protocols/{suite.rid}", json=attempt)
        suite.client.put(f"/qual/{suite.qid}", json=attempt)
    assert _creator_of(suite)["created_by_user_id"] == SIGNERS["prepared_by"][0]
    qual_creator = (qdb.get_qualification(suite.qid) or {}).get("created_by_user_id") if suite.qid else None
    assert qual_creator in (None, SIGNERS["prepared_by"][0])


def test_stamp_never_overwrites_an_existing_creator(suite):
    from pharmagpt import creator_identity
    table = {"urs": "urs_projects", "dq": "qms_documents"}.get(suite.kind, "qual_protocols")
    creator_identity.stamp(table, suite.rid, OTHER_USER, "Mallory")
    assert _creator_of(suite)["created_by_user_id"] == SIGNERS["prepared_by"][0]


# ── records that pre-date the creator column ─────────────────────────────────

def test_legacy_record_falls_back_to_the_authenticated_prepared_by_name(suite, monkeypatch):
    _set_creator(suite, "", "")                    # blank creator id, as in a pre-column row
    if suite.kind == "dq":
        # DQ's stronger fallback is the first version row's creator; remove it to test the name fallback.
        conn = maindb.get_connection()
        with conn:
            conn.execute("UPDATE qms_document_versions SET created_by_user_id = '' WHERE document_id = ?", (suite.rid,))
        conn.close()
    as_other_initiator(monkeypatch)
    assert suite.act("Submitted for Review").status_code == 403          # "User 99" != the stamped prepared_by
    as_signer(monkeypatch, "prepared_by")
    assert suite.act("Submitted for Review").status_code == 201          # "User 01" matches prepared_by


def test_legacy_record_with_no_identity_at_all_cannot_be_submitted(suite, monkeypatch):
    _set_creator(suite, "", "")
    conn = maindb.get_connection()
    with conn:
        if suite.kind == "urs":
            conn.execute("UPDATE urs_projects SET prepared_by = '' WHERE id = ?", (suite.rid,))
        elif suite.kind == "dq":
            conn.execute("UPDATE qms_documents SET prepared_by = '' WHERE id = ?", (suite.rid,))
            conn.execute("UPDATE qms_document_versions SET created_by_user_id = '' WHERE document_id = ?", (suite.rid,))
        else:
            conn.execute("UPDATE qual_qualifications SET prepared_by = '', created_by_user_id = '', "
                         "created_by_display_name = '' WHERE id = ?", (suite.qid,))
    conn.close()
    as_signer(monkeypatch, "prepared_by")
    r = suite.act("Submitted for Review")
    assert r.status_code == 403 and suite.status() == "draft"          # recovery: docs/VALIDATION_APPROVAL_RECOVERY.md


def test_dq_creator_falls_back_to_the_first_version_row(client, monkeypatch):
    s = Suite("dq", client, monkeypatch)
    conn = maindb.get_connection()
    with conn:
        conn.execute("UPDATE qms_documents SET created_by_user_id = '', created_by_display_name = '', "
                     "prepared_by = 'Somebody Else' WHERE id = ?", (s.rid,))
    conn.close()
    assert dqdb.get_creator_identity(dqdb.get_document(s.rid))["created_by_user_id"] == SIGNERS["prepared_by"][0]
    as_signer(monkeypatch, "prepared_by")
    assert s.act("Submitted for Review").status_code == 201


def test_a_protocol_is_authored_by_whoever_created_it_not_just_the_parent(client, monkeypatch):
    s = Suite("iq", client, monkeypatch)                     # parent + IQ/OQ/PQ created by the author
    impersonate(monkeypatch, OTHER_USER, "user", {"Submit"}, memberships=[membership("VALIDATION", "Initiator")])
    oq = client.post(f"/qual/{s.qid}/protocols", json={"protocol_type": "OQ", "title": "second OQ"}).get_json()
    as_signer(monkeypatch, "prepared_by")
    assert post(client, s.base, oq["id"], "Submitted for Review").status_code == 403   # not the OQ's creator
    impersonate(monkeypatch, OTHER_USER, "user", {"Submit"}, memberships=[membership("VALIDATION", "Initiator")])
    assert post(client, s.base, oq["id"], "Submitted for Review").status_code == 201   # its creator


# ══ Approval-before-execution ═════════════════════════════════════════════════

@pytest.fixture()
def proto(client, monkeypatch):
    s = Suite("iq", client, monkeypatch)
    tc = client.post(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}/test-cases/add",
                     json={"test_id": "IQ-1", "test_name": "t"}).get_json()
    s.tc = tc
    return s


def _execute(s, pid=None, tcid=None):
    pid = pid or s.siblings["IQ"]
    tcid = tcid or s.tc["id"]
    return s.client.post(f"/qual/{s.qid}/protocols/{pid}/execute/{tcid}", json={"result": "pass"})


def _complete(s, pid=None):
    return s.client.post(f"/qual/{s.qid}/protocols/{pid or s.siblings['IQ']}/complete", json={})


def _admin(monkeypatch):
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000aa", "company_admin",
                {"Approve", "Review", "Reject", "Submit", "View"})


@pytest.mark.parametrize("stage", ["draft", "under_review", "technical_review", "qa_review",
                                   "validation_review", "final_approval"])
def test_unapproved_protocol_cannot_be_executed_or_completed(proto, monkeypatch, stage):
    qdb.set_protocol_approval_status(proto.siblings["IQ"], stage)
    _admin(monkeypatch)
    r = _execute(proto)
    assert r.status_code == 409 and "approved by all seven" in r.get_json()["error"]
    assert _complete(proto).status_code == 409
    actions = [a["action"] for a in qmsdb.get_audit_trail("qualification", proto.qid)]
    assert any("test execution blocked" in a for a in actions)
    assert any("completion blocked" in a for a in actions)


@pytest.mark.parametrize("stage", ["approved", "effective"])
def test_approved_or_effective_protocol_can_be_executed_and_completed(proto, monkeypatch, stage):
    qdb.set_protocol_approval_status(proto.siblings["IQ"], stage)
    _admin(monkeypatch)
    assert _execute(proto).status_code == 200
    assert _complete(proto).status_code == 200


def test_execution_does_not_wait_for_effective_per_the_existing_lifecycle(proto, monkeypatch):
    """services/approval_engine.py orders the lifecycle Approved -> Execution -> ... -> Effective."""
    drive_to_approved(proto.client, monkeypatch, proto.base, proto.siblings["IQ"])
    assert qdb.get_protocol_approval_status(qdb.get_protocol(proto.siblings["IQ"])) == "approved"
    _admin(monkeypatch)
    assert _execute(proto).status_code == 200


def test_a_siblings_approval_does_not_unlock_execution(proto, monkeypatch):
    drive_to_approved(proto.client, monkeypatch, proto.base, proto.siblings["OQ"])
    tc = proto.client.post(f"/qual/{proto.qid}/protocols/{proto.siblings['IQ']}/test-cases/add",
                           json={"test_id": "IQ-2", "test_name": "t"}).get_json()
    _admin(monkeypatch)
    assert _execute(proto, proto.siblings["IQ"], tc["id"]).status_code == 409


def test_rejecting_an_executed_protocol_blocks_further_execution_until_reapproved(proto, monkeypatch):
    drive_to_approved(proto.client, monkeypatch, proto.base, proto.siblings["IQ"])
    _admin(monkeypatch)
    assert _execute(proto).status_code == 200
    as_signer(monkeypatch, "final_approval")
    assert post(proto.client, proto.base, proto.siblings["IQ"], "Rejected", comments="redo").status_code == 201
    _admin(monkeypatch)
    # Executions exist, but a ledger now exists too (superseded rows): NOT grandfathered.
    assert _execute(proto).status_code == 409


def test_legacy_protocol_already_in_execution_may_continue(proto, monkeypatch):
    """Executions recorded + no ledger row ever = started before approval tracking existed."""
    qdb.save_execution(proto.tc["id"], proto.siblings["IQ"], proto.qid, {"result": "pass"})
    assert vadb.list_signoffs(COMPANY, "IQ", proto.siblings["IQ"], include_superseded=True) == []
    _admin(monkeypatch)
    assert _execute(proto).status_code == 200


def test_legacy_protocol_never_executed_must_be_approved_first(proto, monkeypatch):
    _admin(monkeypatch)
    assert _execute(proto).status_code == 409


def test_oq_sequencing_gate_is_independent_of_the_approval_gate(client, monkeypatch):
    s = Suite("oq", client, monkeypatch)
    tc = client.post(f"/qual/{s.qid}/protocols/{s.siblings['OQ']}/test-cases/add",
                     json={"test_id": "OQ-1", "test_name": "t"}).get_json()
    drive_to_approved(client, monkeypatch, s.base, s.siblings["OQ"])
    _admin(monkeypatch)
    r = client.post(f"/qual/{s.qid}/protocols/{s.siblings['OQ']}/execute/{tc['id']}", json={"result": "pass"})
    assert r.status_code == 409 and "IQ" in r.get_json()["error"]        # approved, but IQ not completed
    qdb.set_protocol_approval_status(s.siblings["IQ"], "approved")
    assert client.post(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}/complete", json={}).status_code == 200
    r = client.post(f"/qual/{s.qid}/protocols/{s.siblings['OQ']}/execute/{tc['id']}", json={"result": "pass"})
    assert r.status_code == 200


# ══ Document-level segregation of duties now has a creator to check ═══════════

def test_document_creator_is_captured_and_cannot_be_named_as_its_own_approver(client, monkeypatch):
    as_signer(monkeypatch, "prepared_by")
    doc = client.post("/qms/documents", json={"title": "SOP"}).get_json()
    assert doc["created_by_user_id"] == SIGNERS["prepared_by"][0]
    with pytest.raises(wfe.WorkflowError) as exc:
        wfe.reject_creator_as_approver("document", doc["id"], [{"user_id": doc["created_by_user_id"]}])
    assert "segregation of duties" in str(exc.value).lower()
    wfe.reject_creator_as_approver("document", doc["id"], [{"user_id": "someone-else"}])   # must not raise

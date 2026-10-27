"""
Standardized Validation approval workflow (services/validation_approval.py),
exercised end-to-end against ALL FIVE document types that share it:

    URS                      /urs/<id>/approval
    DQ (Document Control)    /qms/documents/<id>/approval
    IQ / OQ / PQ protocols   /qual/<qid>/protocols/<pid>/approval   (each independent)

Every test in the first half is parametrized over the five types, so the
engine cannot drift between suites. Sections after that cover behaviour that
is specific to protocols (independence, content lock, roll-up) and to DQ
(Document Control safeguards).
"""

import io

import pytest

import pharmagpt.services.esignature_service as esig
from pharmagpt import config
from pharmagpt import database as maindb
from pharmagpt import qms_database as qmsdb
from pharmagpt import qms_document_database as dqdb
from pharmagpt import qual_database as qdb
from pharmagpt import urs_database as udb
from pharmagpt import validation_approval_database as vadb
from pharmagpt.services import kb_sync
from pharmagpt.services import validation_approval as va
from tests._va_helpers import (
    CHAIN, EXPECTED_AFTER, SIGNERS, as_signer, drive_to_approved, impersonate, membership,
    post, set_memberships, sign_extra,
)

COMPANY = "52df3b4a-d37e-4176-8a52-7171adf39637"  # BOOTSTRAP_COMPANY_ID, the default test tenant
KINDS = ["urs", "dq", "iq", "oq", "pq"]


# ── Suite adapter: one interface over the five document types ────────────────

class Suite:
    def __init__(self, kind, client, monkeypatch):
        self.kind, self.client = kind, client
        as_signer(monkeypatch, "prepared_by")   # the author creates the record (only the author may submit it)
        self.qid = None
        self.siblings = {}
        if kind == "urs":
            self.base, self.ledger, self.esig_type = "/urs", "URS", "urs"
            self.rid = client.post("/urs/", json={"title": "T", "equipment_name": "E"}).get_json()["id"]
            self.kb = ("urs", None)
        elif kind == "dq":
            self.base, self.ledger, self.esig_type = "/qms/documents", "DQ", "document"
            self.rid = client.post("/qms/documents", json={
                "title": "DQ-1", "doc_type": "DQ", "content": "# Design Qualification\nbody"}).get_json()["id"]
            self.kb = ("document", None)
        else:
            self.ledger, self.esig_type = kind.upper(), "qualification"
            self.qid = client.post("/qual/", json={"title": "Q", "equipment_name": "E"}).get_json()["id"]
            for t in ("IQ", "OQ", "PQ"):
                self.siblings[t] = client.post(f"/qual/{self.qid}/protocols", json={"protocol_type": t}).get_json()["id"]
            self.rid = self.siblings[self.ledger]
            self.base = f"/qual/{self.qid}/protocols"
            self.kb = ("qualification_protocol", None)
        if kind == "dq":
            self._satisfy_document_control_gates()

    # -- helpers --
    def _satisfy_document_control_gates(self):
        """Author Self-Check + Final Author Version (the Document Control
        submission safeguards the shared engine preserves)."""
        assert self.client.post(f"/qms/documents/{self.rid}/self-check").status_code == 200
        r = self.client.post(f"/qms/documents/{self.rid}/versions/upload",
                             data={"file": (io.BytesIO(b"final content"), "final.txt")},
                             content_type="multipart/form-data")
        assert r.status_code == 201, r.get_json()

    def complete_training(self):
        if self.kind == "dq":
            t = dqdb.add_training(self.rid, {"trainee_name": "Op", "role": "Operator"})
            dqdb.update_training_status(t["id"], "Completed", "2026-10-10")

    def status(self):
        if self.kind == "urs":
            return udb.get_urs(self.rid)["status"]
        if self.kind == "dq":
            return dqdb.get_document(self.rid)["status"].lower().replace(" ", "_")
        return qdb.get_protocol_approval_status(qdb.get_protocol(self.rid))

    def revision(self):
        if self.kind == "urs":
            return udb.get_urs(self.rid)["revision"]
        if self.kind == "dq":
            return dqdb.get_current_version(self.rid)["version_number"]
        return qdb.get_protocol(self.rid)["revision"]

    def force_legacy_approved(self):
        """A record approved under the pre-standard workflow: Approved, zero ledger rows."""
        if self.kind == "urs":
            udb.update_urs(self.rid, {"status": "approved"})
        elif self.kind == "dq":
            v = dqdb.get_current_version(self.rid)
            dqdb.transition_version_status(v["id"], "under_review")
            dqdb.transition_version_status(v["id"], "pending_approval")
            dqdb.transition_version_status(v["id"], "approved")
            dqdb.update_document(self.rid, {"status": "Approved"}, allow_controlled_fields=True)
        else:
            qdb.set_protocol_approval_status(self.rid, "approved")

    def kb_row(self):
        src = self.kb[0]
        return maindb.get_kb_document_by_source(src, self.rid, COMPANY)

    def audit_record_id(self):
        return self.qid if self.qid else self.rid

    def ledger_rows(self, superseded=False):
        return vadb.list_signoffs(COMPANY, self.ledger, self.rid, include_superseded=superseded)

    def act(self, action, **extra):
        return post(self.client, self.base, self.rid, action, **extra)

    def page(self):
        return self.client.get(f"{self.base}/{self.rid}/approval/signatories")


@pytest.fixture(params=KINDS)
def suite(request, client, monkeypatch):
    return Suite(request.param, client, monkeypatch)


def _submit(s, monkeypatch):
    as_signer(monkeypatch, "prepared_by")
    return s.act("Submitted for Review", comments="ready")


def _run_chain(s, monkeypatch):
    assert _submit(s, monkeypatch).status_code == 201
    for key in CHAIN:
        as_signer(monkeypatch, key)
        r = s.act("Sign Off", **sign_extra(key))
        assert r.status_code == 201, (key, r.get_json())
        assert s.status() == EXPECTED_AFTER[key], key


def _make_effective(s, monkeypatch):
    s.complete_training()
    as_signer(monkeypatch, "final_approval")
    return s.act("Make Effective")


# ══ 1. Initiator submission ═══════════════════════════════════════════════════

def test_initiator_with_submit_permission_submits_own_draft(suite, monkeypatch):
    r = _submit(suite, monkeypatch)
    assert r.status_code == 201, r.get_json()
    assert suite.status() == "under_review"
    row = suite.ledger_rows()[0]
    assert row["signatory_key"] == "prepared_by"
    assert row["signer_user_id"] == SIGNERS["prepared_by"][0]


def test_user_without_submit_permission_cannot_submit(suite, monkeypatch):
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000bb", "user", {"View", "Edit"},
                memberships=[membership("VALIDATION", "Initiator")])
    assert suite.act("Submitted for Review").status_code == 403
    assert suite.status() == "draft"


def test_submit_only_from_draft(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "prepared_by")
    assert suite.act("Submitted for Review").status_code == 409


# ══ 2. Reviewer / approver authority is not weakened ══════════════════════════

def test_initiator_cannot_sign_reject_effective_or_obsolete(suite, monkeypatch):
    _submit(suite, monkeypatch)
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000b1", "user",
                {"Review", "Approve", "Reject", "Submit"})  # even with every grant, platform role 'user' is blocked
    for action in ("Sign Off", "Rejected", "Make Effective", "Obsolete"):
        assert suite.act(action, comments="x").status_code == 403, action
    assert suite.status() == "under_review"


def test_reviewer_without_approve_cannot_sign_manager_stage(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    assert suite.act("Sign Off").status_code == 201
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000cc", "reviewer_qa", {"View", "Review"},
                memberships=[membership("ENGINEERING", "Approver")])
    r = suite.act("Sign Off", signatory="engineering_manager")
    assert r.status_code == 403 and "Approve" in r.get_json()["error"]
    assert suite.status() == "technical_review"


def test_no_validation_grants_means_no_action(suite, monkeypatch):
    _submit(suite, monkeypatch)
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000dd", "reviewer_qa", set())
    assert suite.act("Sign Off").status_code == 403


# ══ 3. Every transition, then Effective ═══════════════════════════════════════

def test_full_chain_every_transition_then_effective(suite, monkeypatch):
    _run_chain(suite, monkeypatch)
    r = _make_effective(suite, monkeypatch)
    assert r.status_code == 201, r.get_json()
    assert suite.status() == "effective"
    page = suite.page().get_json()
    assert page["all_mandatory_complete"] and page["completed_count"] == 7
    assert all(s["status"] == "completed" for s in page["signatories"])


def test_approval_page_has_the_exact_approved_signatories(suite, monkeypatch):
    _submit(suite, monkeypatch)
    page = suite.page().get_json()
    assert [(s["label"], s["designation"]) for s in page["signatories"]] == [
        ("Prepared By", "Validation Engineer"), ("Reviewed By", "Process Engineer"),
        ("Engineering", "Engineering Manager"), ("Production", "Production Manager"),
        ("Quality Assurance", "QA Manager"), ("Validation", "Validation Manager"),
        ("Final Approval", "Site Director / VP Quality")]
    first, second = page["signatories"][0], page["signatories"][1]
    assert first["status"] == "completed" and first["signer_name"] and first["signed_at"]
    assert first["signature"]["hash"] and first["signature"]["meaning"] == "Created"
    assert second["status"] == "current"
    assert page["signatories"][-1]["status"] == "pending"


def test_stage_skipping_is_impossible(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "final_approval")
    assert suite.act("Make Effective").status_code == 409
    assert suite.act("Sign Off", signatory="final_approval").status_code == 409
    assert suite.status() == "under_review"


def test_parallel_stage_requires_specifying_signatory(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    suite.act("Sign Off")
    as_signer(monkeypatch, "engineering_manager")
    assert suite.act("Sign Off").status_code == 400


def test_legacy_action_names_still_work_as_sign_off(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    assert suite.act("Review Complete").status_code == 201
    assert suite.status() == "technical_review"


def test_retired_submitted_for_approval_rejected(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    assert suite.act("Submitted for Approval").status_code == 400


# ══ 4. Effective-state gating ═════════════════════════════════════════════════

def test_cannot_become_effective_with_missing_approvals(suite, monkeypatch):
    drive_to_approved(suite.client, monkeypatch, suite.base, suite.rid)
    assert suite.status() == "approved"
    conn = maindb.get_connection()  # simulate a tampered/incomplete ledger
    with conn:
        conn.execute("DELETE FROM validation_signoffs WHERE record_id = ? AND doc_type = ? "
                     "AND signatory_key = 'qa_manager'", (suite.rid, suite.ledger))
    conn.close()
    suite.complete_training()
    as_signer(monkeypatch, "final_approval")
    r = suite.act("Make Effective")
    assert r.status_code == 409 and "mandatory approvals" in r.get_json()["error"]
    assert "Quality Assurance" in r.get_json()["error"]
    assert suite.status() == "approved"


def test_legacy_approved_record_with_no_ledger_can_still_be_made_effective(suite, monkeypatch):
    suite.force_legacy_approved()
    r = _make_effective(suite, monkeypatch)
    assert r.status_code == 201, r.get_json()
    assert suite.status() == "effective"


def test_superseded_rows_do_not_count_as_legacy(suite, monkeypatch):
    if suite.kind == "dq":
        pytest.skip("DQ cannot be rejected from Approved; covered by the DQ-specific test")
    _run_chain(suite, monkeypatch)
    as_signer(monkeypatch, "final_approval")
    suite.act("Rejected", comments="rework")
    suite.force_legacy_approved()  # forced back to Approved with only superseded rows
    assert _make_effective(suite, monkeypatch).status_code == 409


# ══ 5. Rejection, revision, resubmission ══════════════════════════════════════

def test_rejection_requires_reason_and_returns_to_draft(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    assert suite.act("Rejected").status_code == 400
    assert suite.act("Rejected", comments="wrong scope").status_code == 201
    assert suite.status() == "draft"


def test_resubmission_starts_a_new_cycle_with_append_only_history(suite, monkeypatch):
    _run_chain(suite, monkeypatch) if suite.kind != "dq" else None
    if suite.kind == "dq":
        _submit(suite, monkeypatch)
        for key in CHAIN[:-1]:
            as_signer(monkeypatch, key)
            suite.act("Sign Off", **sign_extra(key))
        as_signer(monkeypatch, "final_approval")
        assert suite.act("Rejected", comments="rework").status_code == 201
        expected_old = 6
    else:
        as_signer(monkeypatch, "final_approval")
        suite.act("Rejected", comments="rework")
        expected_old = 7
    assert suite.ledger_rows() == []                                   # current cycle empty
    assert len(suite.ledger_rows(superseded=True)) == expected_old     # history kept
    if suite.kind == "dq":
        suite._satisfy_document_control_gates()  # the forked draft needs its own Self-Check/final version
    _run_chain(suite, monkeypatch)                                     # the same people sign again
    assert len(suite.ledger_rows()) == 7
    assert len(suite.ledger_rows(superseded=True)) == 7 + expected_old


def test_reject_after_approval_bumps_revision_except_dq(suite, monkeypatch):
    _run_chain(suite, monkeypatch)
    before = suite.revision()
    as_signer(monkeypatch, "final_approval")
    r = suite.act("Rejected", comments="revise")
    if suite.kind == "dq":
        # Document Control versions cannot be un-approved; only an Effective
        # document is revised (start-revision). The engine refuses cleanly.
        assert r.status_code == 409 and suite.status() == "approved"
    else:
        assert r.status_code == 201 and suite.revision() != before


def test_reject_during_review_keeps_revision(suite, monkeypatch):
    _submit(suite, monkeypatch)
    before = suite.revision()
    as_signer(monkeypatch, "reviewed_by")
    assert suite.act("Rejected", comments="no").status_code == 201
    if suite.kind != "dq":  # DQ forks a NEW immutable version on rejection (version control)
        assert suite.revision() == before


# ══ 6. Seven distinct signers ═════════════════════════════════════════════════

def test_one_person_cannot_sign_two_designations(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    suite.act("Sign Off")
    # Same user id, now with Approve and an Engineering Approver membership:
    as_signer(monkeypatch, "reviewed_by", extra_perms=("Approve",),
              memberships=[membership("ENGINEERING", "Approver")])
    r = suite.act("Sign Off", signatory="engineering_manager")
    assert r.status_code == 403 and "Segregation" in r.get_json()["error"]


def test_preparer_cannot_also_review(suite, monkeypatch):
    _submit(suite, monkeypatch)
    impersonate(monkeypatch, SIGNERS["prepared_by"][0], "reviewer_qa", {"Review", "Submit"})
    assert suite.act("Sign Off").status_code == 403


def test_distinct_signers_cannot_be_switched_off_by_configuration():
    assert not hasattr(config, "VALIDATION_ENFORCE_DISTINCT_SIGNERS")
    assert len(va.MANDATORY_KEYS) == len(set(va.MANDATORY_KEYS)) == 7


# ══ 7. Department / designation enforcement ═══════════════════════════════════

def test_enforcement_is_on_by_default():
    assert config.VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT is True


def test_each_designation_rejects_the_wrong_department_and_accepts_the_right_one(suite, monkeypatch):
    # Prepared By
    as_signer(monkeypatch, "prepared_by", memberships=[membership("ENGINEERING", "Initiator")])
    assert suite.act("Submitted for Review").status_code == 403
    assert suite.status() == "draft"
    assert _submit(suite, monkeypatch).status_code == 201
    for key in CHAIN:
        as_signer(monkeypatch, key, memberships=[membership("QC", "Approver")])  # QC may not sign any of them
        denied = suite.act("Sign Off", **sign_extra(key))
        assert denied.status_code == 403, key
        assert "requires" in denied.get_json()["error"]
        as_signer(monkeypatch, key)
        assert suite.act("Sign Off", **sign_extra(key)).status_code == 201, key
    rows = {r["signatory_key"]: r for r in suite.ledger_rows()}
    assert rows["qa_manager"]["signer_department"] == "QA"
    assert rows["engineering_manager"]["signer_department"] == "ENGINEERING"


def test_one_department_cannot_sign_another_departments_line(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    suite.act("Sign Off")
    # A Production approver tries to sign the ENGINEERING line:
    as_signer(monkeypatch, "production_manager")
    assert suite.act("Sign Off", signatory="engineering_manager").status_code == 403
    assert suite.act("Sign Off", signatory="production_manager").status_code == 201


def test_right_department_wrong_functional_role_is_denied(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    suite.act("Sign Off")
    as_signer(monkeypatch, "engineering_manager", memberships=[membership("ENGINEERING", "Reviewer")])
    assert suite.act("Sign Off", signatory="engineering_manager").status_code == 403


def test_membership_must_pair_department_and_role_in_one_row(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    suite.act("Sign Off")
    # Engineering *Initiator* + Production *Approver*: neither row satisfies the Engineering Manager line.
    as_signer(monkeypatch, "engineering_manager",
              memberships=[membership("ENGINEERING", "Initiator"), membership("PRODUCTION", "Approver")])
    assert suite.act("Sign Off", signatory="engineering_manager").status_code == 403


def test_company_admin_without_membership_cannot_sign(suite, monkeypatch):
    _submit(suite, monkeypatch)
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000aa", "company_admin",
                {"Review", "Approve", "Reject", "Submit"}, memberships=[])
    assert suite.act("Sign Off").status_code == 403
    assert suite.status() == "under_review"


def test_directory_failure_denies_the_signature(suite, monkeypatch):
    from pharmagpt.services import org_directory
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")

    def boom(*a, **k):
        raise RuntimeError("supabase down")
    monkeypatch.setattr(org_directory, "list_user_departments", boom)
    assert suite.act("Sign Off").status_code == 403
    assert suite.status() == "under_review"


# ══ 8. Electronic-signature controls ══════════════════════════════════════════

def test_failed_reauthentication_blocks_and_mutates_nothing(suite, monkeypatch):
    def bad(*a, **k):
        raise esig.ReauthenticationError("Password confirmation failed")
    monkeypatch.setattr(esig, "require_esignature", bad)
    as_signer(monkeypatch, "prepared_by")
    assert suite.act("Submitted for Review", password="wrong").status_code == 401
    assert suite.status() == "draft"
    assert suite.ledger_rows(superseded=True) == []
    rtype = suite.esig_type
    actions = [a["action"] for a in qmsdb.get_audit_trail(rtype, suite.audit_record_id())]
    assert any("e-signature failed" in a for a in actions)


def test_missing_reason_is_a_400_and_mutates_nothing(suite, monkeypatch):
    def no_reason(*a, **k):
        raise esig.ESignatureError("reason is required")
    monkeypatch.setattr(esig, "require_esignature", no_reason)
    as_signer(monkeypatch, "prepared_by")
    assert suite.act("Submitted for Review", password="x").status_code == 400
    assert suite.status() == "draft"


def test_signature_meaning_must_match_the_action(suite, monkeypatch):
    _submit(suite, monkeypatch)
    as_signer(monkeypatch, "reviewed_by")
    assert suite.act("Sign Off", meaning="Created").status_code == 400      # a review is not a "Created" signature
    assert suite.status() == "under_review"
    as_signer(monkeypatch, "prepared_by")
    assert suite.act("Rejected", meaning="Approved", comments="x").status_code in (400, 403, 409)


def test_signoff_links_immutable_signature_record(suite, monkeypatch):
    _submit(suite, monkeypatch)
    row = suite.ledger_rows()[0]
    sigs = [x for x in qmsdb.get_esignatures(suite.esig_type, suite.audit_record_id())
            if x["meaning"] == "Created"]
    assert sigs and row["esignature_id"] in [x["id"] for x in sigs]
    linked = next(x for x in sigs if x["id"] == row["esignature_id"])
    assert row["signature_hash"] == linked["signature_hash"]
    assert esig.verify_signature_integrity(linked)


# ══ 9. Identity, tenant isolation, append-only history, audit ═════════════════

def test_spoofed_identity_in_body_is_ignored(suite, monkeypatch):
    as_signer(monkeypatch, "prepared_by")
    r = suite.act("Submitted for Review", performed_by="Somebody Else", role="company_admin")
    assert r.status_code == 201
    row = suite.ledger_rows()[0]
    assert row["signer_name"] != "Somebody Else"
    assert row["signer_user_id"] == SIGNERS["prepared_by"][0]


def test_other_company_cannot_see_or_act(suite, monkeypatch):
    _submit(suite, monkeypatch)
    impersonate(monkeypatch, "20000000-0000-0000-0000-000000000001", "company_admin",
                {"Approve", "Review", "Reject", "Submit"}, company_id="other-company")
    assert suite.act("Sign Off").status_code == 404
    assert suite.act("Rejected", comments="x").status_code == 404
    assert suite.page().status_code == 404
    assert vadb.list_signoffs("other-company", suite.ledger, suite.rid) == []
    assert suite.status() == "under_review"


def test_signoff_history_is_append_only(suite, monkeypatch):
    _run_chain(suite, monkeypatch) if suite.kind != "dq" else _submit(suite, monkeypatch)
    before = [dict(r) for r in suite.ledger_rows(superseded=True)]
    as_signer(monkeypatch, "reviewed_by" if suite.kind == "dq" else "final_approval")
    suite.act("Rejected", comments="again")
    after = suite.ledger_rows(superseded=True)
    assert len(after) == len(before)                       # nothing deleted
    for old, new in zip(before, after):                    # nothing rewritten except status
        assert {k: v for k, v in old.items() if k not in ("status", "superseded_reason")} == \
               {k: v for k, v in new.items() if k not in ("status", "superseded_reason")}
        assert new["status"] == "superseded"


def test_every_transition_is_audited(suite, monkeypatch):
    _run_chain(suite, monkeypatch)
    actions = [a["action"] for a in qmsdb.get_audit_trail(suite.esig_type, suite.audit_record_id())]
    for expected in ("Submitted for Review", "Reviewed By Sign-Off", "Engineering Sign-Off",
                     "Production Sign-Off", "Quality Assurance Sign-Off", "Validation Sign-Off", "Approved"):
        assert expected in actions, expected
    assert sum(1 for a in actions if a.startswith("E-Signature")) >= 7


# ══ 10. Knowledge Base publication timing ═════════════════════════════════════

def test_kb_publication_only_at_effective(suite, monkeypatch):
    _run_chain(suite, monkeypatch)
    assert suite.kb_row() is None, "published before Effective"
    assert _make_effective(suite, monkeypatch).status_code == 201
    row = suite.kb_row()
    assert row is not None


def test_kb_publish_refused_for_incomplete_approvals(suite, monkeypatch):
    _submit(suite, monkeypatch)
    src = suite.kb[0]
    with pytest.raises(va.ApprovalError) as exc:
        kb_sync.publish_to_kb(
            source_type=src, source_id=suite.rid, company_id=COMPANY, title="x",
            doc_type=suite.ledger if src != "urs" else "URS", doc_number="N", version="1",
            content_markdown="# x", effective_date=None)
    assert exc.value.http_status == 409
    assert suite.kb_row() is None


# ══ 11. Pure lifecycle ════════════════════════════════════════════════════════

def test_standard_lifecycle_has_no_shortcut_to_approved_or_effective():
    t = va.STANDARD_TRANSITIONS
    assert t["draft"] == {"under_review"}
    assert "approved" not in t["under_review"] and "effective" not in t["under_review"]
    assert t["final_approval"] == {"approved", "draft"}
    assert t["approved"] == {"effective", "draft"}
    assert t["pending_approval"] == {"draft"}  # legacy status is reject-only


# ══ 12. Protocol-level independence (IQ / OQ / PQ) ════════════════════════════

@pytest.fixture()
def protocols(client, monkeypatch):
    return Suite("iq", client, monkeypatch)  # carries .qid and .siblings for all three


def _proto_post(client, qid, pid, action, **extra):
    return post(client, f"/qual/{qid}/protocols", pid, action, **extra)


def test_approving_one_protocol_never_approves_the_others(protocols, client, monkeypatch):
    s = protocols
    drive_to_approved(client, monkeypatch, s.base, s.siblings["IQ"])
    assert qdb.get_protocol_approval_status(qdb.get_protocol(s.siblings["IQ"])) == "approved"
    for other in ("OQ", "PQ"):
        assert qdb.get_protocol_approval_status(qdb.get_protocol(s.siblings[other])) == "draft"
        assert vadb.list_signoffs(COMPANY, other, s.siblings[other], include_superseded=True) == []
    # The parent is NOT approved just because one protocol is.
    assert qdb.get_qualification(s.qid)["status"] != "approved"
    # And an IQ signature cannot be reused on the OQ: its own cycle starts at Submit.
    as_signer(monkeypatch, "reviewed_by")
    assert _proto_post(client, s.qid, s.siblings["OQ"], "Sign Off").status_code == 409


def test_each_protocol_has_its_own_ledger_and_status(protocols, client, monkeypatch):
    s = protocols
    drive_to_approved(client, monkeypatch, s.base, s.siblings["IQ"])
    drive_to_approved(client, monkeypatch, s.base, s.siblings["OQ"])
    assert len(vadb.list_signoffs(COMPANY, "IQ", s.siblings["IQ"])) == 7
    assert len(vadb.list_signoffs(COMPANY, "OQ", s.siblings["OQ"])) == 7
    assert vadb.list_signoffs(COMPANY, "PQ", s.siblings["PQ"]) == []
    summary = client.get(f"/qual/{s.qid}/approval/signatories").get_json()
    by_type = {p["protocol_type"]: p for p in summary["protocols"]}
    assert by_type["IQ"]["completed_count"] == by_type["OQ"]["completed_count"] == 7
    assert by_type["PQ"]["completed_count"] == 0


def test_rejecting_one_protocol_does_not_touch_the_others(protocols, client, monkeypatch):
    s = protocols
    drive_to_approved(client, monkeypatch, s.base, s.siblings["IQ"])
    drive_to_approved(client, monkeypatch, s.base, s.siblings["OQ"])
    as_signer(monkeypatch, "final_approval")
    assert _proto_post(client, s.qid, s.siblings["IQ"], "Rejected", comments="redo").status_code == 201
    assert qdb.get_protocol_approval_status(qdb.get_protocol(s.siblings["IQ"])) == "draft"
    assert qdb.get_protocol_approval_status(qdb.get_protocol(s.siblings["OQ"])) == "approved"
    assert len(vadb.list_signoffs(COMPANY, "OQ", s.siblings["OQ"])) == 7


def test_parent_status_is_a_rollup_of_all_three_protocols(protocols, client, monkeypatch):
    s = protocols
    for t in ("IQ", "OQ"):
        drive_to_approved(client, monkeypatch, s.base, s.siblings[t])
    assert qdb.get_qualification(s.qid)["status"] == "under_review"   # PQ still draft
    drive_to_approved(client, monkeypatch, s.base, s.siblings["PQ"])
    assert qdb.get_qualification(s.qid)["status"] == "approved"
    for t in ("IQ", "OQ", "PQ"):
        as_signer(monkeypatch, "final_approval")
        assert _proto_post(client, s.qid, s.siblings[t], "Make Effective").status_code == 201
    assert qdb.get_qualification(s.qid)["status"] == "effective"


def test_parent_level_approval_actions_are_refused(protocols, client, monkeypatch):
    s = protocols
    as_signer(monkeypatch, "prepared_by")
    for action in ("Submitted for Review", "Sign Off", "Approved", "Make Effective"):
        r = client.post(f"/qual/{s.qid}/approval", json={"action": action})
        assert r.status_code == 400 and "per protocol" in r.get_json()["error"]


def test_protocol_approval_status_cannot_be_set_by_put(protocols, client, monkeypatch):
    s = protocols
    r = client.put(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}", json={"approval_status": "effective",
                                                                        "revision": "Z", "scope": "ok"})
    assert r.status_code == 200
    p = qdb.get_protocol(s.siblings["IQ"])
    assert qdb.get_protocol_approval_status(p) == "draft" and p["revision"] == "A"


def test_protocol_definition_is_locked_once_submitted_but_execution_is_not(protocols, client, monkeypatch):
    s = protocols
    tc = client.post(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}/test-cases/add",
                     json={"test_id": "IQ-001", "test_name": "t"}).get_json()
    _submit(_Shim(client, s.base, s.siblings["IQ"]), monkeypatch)
    assert client.put(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}", json={"scope": "sneaky"}).status_code == 409
    assert client.post(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}/test-cases/add",
                       json={"test_id": "IQ-002", "test_name": "x"}).status_code == 409
    assert client.put(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}/test-cases/{tc['id']}",
                      json={"test_name": "renamed"}).status_code == 409
    impersonate(monkeypatch, "10000000-0000-0000-0000-0000000000aa", "company_admin", {"Delete", "View"})
    assert client.delete(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}/test-cases/{tc['id']}").status_code == 409
    # execution results are still recordable
    assert client.put(f"/qual/{s.qid}/protocols/{s.siblings['IQ']}/test-cases/{tc['id']}",
                      json={"status": "pass"}).status_code == 200
    # a sibling in Draft is unaffected
    assert client.post(f"/qual/{s.qid}/protocols/{s.siblings['OQ']}/test-cases/add",
                       json={"test_id": "OQ-001", "test_name": "x"}).status_code == 201


class _Shim:
    def __init__(self, client, base, rid):
        self.client, self.base, self.rid = client, base, rid

    def act(self, action, **extra):
        return post(self.client, self.base, self.rid, action, **extra)


def test_only_the_effective_protocol_is_published_to_the_kb(protocols, client, monkeypatch):
    s = protocols
    for t in ("IQ", "OQ"):
        drive_to_approved(client, monkeypatch, s.base, s.siblings[t])
    as_signer(monkeypatch, "final_approval")
    assert _proto_post(client, s.qid, s.siblings["IQ"], "Make Effective").status_code == 201
    assert maindb.get_kb_document_by_source("qualification_protocol", s.siblings["IQ"], COMPANY)
    assert not maindb.get_kb_document_by_source("qualification_protocol", s.siblings["OQ"], COMPANY)
    assert not maindb.get_kb_document_by_source("qualification_protocol", s.siblings["PQ"], COMPANY)


def test_effective_protocol_creates_a_version_snapshot(protocols, client, monkeypatch):
    s = protocols
    drive_to_approved(client, monkeypatch, s.base, s.siblings["IQ"])
    before = len(client.get(f"/qual/{s.qid}/versions").get_json())
    as_signer(monkeypatch, "final_approval")
    assert _proto_post(client, s.qid, s.siblings["IQ"], "Make Effective").status_code == 201
    assert len(client.get(f"/qual/{s.qid}/versions").get_json()) == before + 1


def test_protocol_in_another_qualification_cannot_be_approved_through_this_one(client, monkeypatch):
    a, b = Suite("iq", client, monkeypatch), Suite("iq", client, monkeypatch)
    as_signer(monkeypatch, "prepared_by")
    r = client.post(f"/qual/{a.qid}/protocols/{b.siblings['IQ']}/approval",
                    json={"action": "Submitted for Review"})
    assert r.status_code == 404


# ══ 13. DQ on the shared engine (Document Control safeguards preserved) ═══════

@pytest.fixture()
def dq(client, monkeypatch):
    return Suite("dq", client, monkeypatch)


def test_dq_submission_still_requires_self_check_and_final_version(client, monkeypatch):
    as_signer(monkeypatch, "prepared_by")          # the author creates and submits
    doc = client.post("/qms/documents", json={"title": "DQ-x", "doc_type": "DQ", "content": "c"}).get_json()
    r = post(client, "/qms/documents", doc["id"], "Submitted for Review")
    assert r.status_code == 409 and "Self-Check" in r.get_json()["error"]
    assert vadb.list_signoffs(COMPANY, "DQ", doc["id"], include_superseded=True) == []
    # Self-Check alone is not enough: Final Author Version is also required.
    assert client.post(f"/qms/documents/{doc['id']}/self-check").status_code == 200
    r = post(client, "/qms/documents", doc["id"], "Submitted for Review")
    assert r.status_code == 409 and "Final" in r.get_json()["error"]


def test_dq_does_not_require_a_named_review_chain(dq, monkeypatch):
    # Authorization comes from department + functional role, not a per-document chain.
    assert _submit(dq, monkeypatch).status_code == 201


def test_dq_version_rows_follow_the_standard_lifecycle(dq, monkeypatch):
    assert dqdb.get_current_version(dq.rid)["status"] == "draft"
    _submit(dq, monkeypatch)
    assert dqdb.get_current_version(dq.rid)["status"] == "under_review"
    for key in CHAIN[:-1]:
        as_signer(monkeypatch, key)
        dq.act("Sign Off", **sign_extra(key))
    assert dq.status() == "final_approval"
    assert dqdb.get_current_version(dq.rid)["status"] == "pending_approval"
    as_signer(monkeypatch, "final_approval")
    dq.act("Sign Off")
    assert dqdb.get_current_version(dq.rid)["status"] == "approved"
    assert _make_effective(dq, monkeypatch).status_code == 201
    assert dqdb.get_current_version(dq.rid)["status"] == "effective"
    assert dqdb.get_document(dq.rid)["effective_date"]


def test_dq_training_gate_blocks_effective_without_consuming_the_signature(dq, monkeypatch):
    drive_to_approved(dq.client, monkeypatch, dq.base, dq.rid)
    sigs_before = len(qmsdb.get_esignatures("document", dq.rid))
    as_signer(monkeypatch, "final_approval")
    r = dq.act("Make Effective")
    assert r.status_code == 409 and "Training" in r.get_json()["error"]
    assert dq.status() == "approved"
    assert len(qmsdb.get_esignatures("document", dq.rid)) == sigs_before   # veto came before the signature
    assert dq.kb_row() is None


def test_dq_needs_content_to_be_released(dq, monkeypatch):
    drive_to_approved(dq.client, monkeypatch, dq.base, dq.rid)
    dq.complete_training()
    dqdb.update_document(dq.rid, {"content": "   "})
    as_signer(monkeypatch, "final_approval")
    assert dq.act("Make Effective").status_code == 409


def test_dq_release_endpoint_goes_through_the_same_gates(dq, monkeypatch):
    drive_to_approved(dq.client, monkeypatch, dq.base, dq.rid)
    as_signer(monkeypatch, "final_approval", extra_perms=())
    r = dq.client.post(f"/qms/documents/{dq.rid}/release", json={})
    assert r.status_code in (403, 409)          # training not complete (or Document Control grant absent)
    dq.complete_training()
    impersonate(monkeypatch, SIGNERS["final_approval"][0], "reviewer_qa", {"Approve", "Reject"},
                memberships=[membership("PLANT_HEAD", "Plant Head")])
    # Document Control:Approve is a different module grant; the shared engine itself is the authority.
    assert dq.act("Make Effective").status_code == 201


def test_dq_cannot_become_effective_through_the_training_gate_path_alone(dq, monkeypatch):
    """qms_document_database.try_clear_training_gate is the DB-level Effective writer."""
    drive_to_approved(dq.client, monkeypatch, dq.base, dq.rid)
    dq.complete_training()
    conn = maindb.get_connection()
    with conn:
        conn.execute("DELETE FROM validation_signoffs WHERE record_id = ? AND doc_type = 'DQ' "
                     "AND signatory_key = 'validation_manager'", (dq.rid,))
    conn.close()
    assert dqdb.try_clear_training_gate(dq.rid) is None
    assert dq.status() == "approved"


def test_dq_legacy_workflow_cannot_be_started(dq, monkeypatch):
    r = dq.client.post(f"/qms/documents/{dq.rid}/workflow/start")
    assert r.status_code == 409 and "shared" in r.get_json()["error"]


def test_dq_content_is_locked_during_review(dq, monkeypatch):
    _submit(dq, monkeypatch)
    r = dq.client.put(f"/qms/documents/{dq.rid}", json={"content": "sneaky edit"})
    assert r.status_code == 409


def test_dq_rejection_forks_a_new_immutable_draft_version(dq, monkeypatch):
    _submit(dq, monkeypatch)
    first = dqdb.get_current_version(dq.rid)
    as_signer(monkeypatch, "reviewed_by")
    assert dq.act("Rejected", comments="incomplete").status_code == 201
    second = dqdb.get_current_version(dq.rid)
    assert second["id"] != first["id"] and second["status"] == "draft"
    assert dqdb.get_version(first["id"])["status"] == "review_rejected"
    assert dq.status() == "draft"
    # resubmission needs a fresh Self-Check + final version (new version)
    as_signer(monkeypatch, "prepared_by")
    assert dq.act("Submitted for Review").status_code == 409


def test_other_document_types_keep_the_legacy_approval_path(client, monkeypatch):
    doc = client.post("/qms/documents", json={"title": "SOP", "doc_type": "SOP"}).get_json()
    assert client.get(f"/qms/documents/{doc['id']}/approval/signatories").status_code == 404
    assert client.post(f"/qms/documents/{doc['id']}/workflow/start").status_code in (201, 409)  # legacy engine reachable


def test_dq_already_in_flight_on_the_legacy_workflow_keeps_finishing_there(dq, monkeypatch):
    """Grandfathering: a DQ with an ACTIVE legacy workflow instance at deploy time
    is not moved onto the shared engine mid-review (no ledger rows are created)."""
    from pharmagpt.services import workflow_engine as wfe
    from pharmagpt.routes import qms_documents as docs_routes
    from pharmagpt.app import app as flask_app
    with flask_app.app_context():
        wfe.start_instance(docs_routes.WORKFLOW_KEY, docs_routes.RECORD_TYPE, dq.rid, COMPANY, "Legacy Author")
        document = dqdb.get_document(dq.rid)
        assert docs_routes._uses_shared_engine(document) is False
    page = dq.page().get_json()
    assert page["shared_engine"] is False
    assert dq.ledger_rows(superseded=True) == []

"""
Concurrency and uniqueness invariants for validation_signoffs.

Real threads and real SQLite connections (no mocked database): the unique
indexes, not application-level checks, must ensure that concurrent or repeated
sign-offs cannot commit a duplicate final state.
"""

import threading

import pytest

from pharmagpt import database as maindb
from pharmagpt import validation_approval_database as vadb
from pharmagpt.auth.context import TenantContext
from pharmagpt.services import validation_approval as va

COMPANY = "52df3b4a-d37e-4176-8a52-7171adf39637"


def _signoff(key="qa_manager", user="u1", record_id=1, doc_type="URS", company=COMPANY):
    return dict(company_id=company, doc_type=doc_type, record_id=record_id, revision="A",
                signatory_key=key, designation=key, signer_user_id=user, signer_name=user, signer_role="x")


def _race(fn, n):
    barrier, results = threading.Barrier(n), []

    def run(i):
        barrier.wait()
        try:
            results.append(("ok", fn(i)))
        except Exception as exc:  # noqa: BLE001
            results.append(("err", exc))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


def test_same_designation_concurrently_commits_exactly_once(db_path):
    res = _race(lambda i: vadb.add_signoff(**_signoff(user=f"u{i}")), 8)
    assert sum(1 for k, _ in res if k == "ok") == 1
    assert all(isinstance(v, vadb.DuplicateSignoffError) for k, v in res if k == "err")
    assert len(vadb.list_signoffs(COMPANY, "URS", 1)) == 1


def test_same_user_two_designations_concurrently_commits_once(db_path):
    keys = ["engineering_manager", "production_manager", "qa_manager", "validation_manager"]
    res = _race(lambda i: vadb.add_signoff(**_signoff(key=keys[i], user="same")), 4)
    assert sum(1 for k, _ in res if k == "ok") == 1
    assert all(v.same_signer for k, v in res if k == "err")


def test_repeated_attempt_and_isolation_between_scopes(db_path):
    vadb.add_signoff(**_signoff())
    with pytest.raises(vadb.DuplicateSignoffError):
        vadb.add_signoff(**_signoff(user="other"))
    # Other record, doc type and tenant are independent scopes.
    vadb.add_signoff(**_signoff(record_id=2))
    vadb.add_signoff(**_signoff(doc_type="IQ"))
    vadb.add_signoff(**_signoff(company="other-company"))


def test_superseded_history_does_not_block_a_new_cycle(db_path):
    vadb.add_signoff(**_signoff())
    vadb.supersede_signoffs(COMPANY, "URS", 1, "rejected")
    vadb.add_signoff(**_signoff())
    assert len(vadb.list_signoffs(COMPANY, "URS", 1)) == 1
    assert len(vadb.list_signoffs(COMPANY, "URS", 1, include_superseded=True)) == 2


def test_indexes_are_idempotent_and_duplicates_block_creation_without_data_loss(db_path):
    maindb.init_db()
    maindb.init_db()
    conn = maindb.get_connection()
    for name, _ in vadb.VALIDATION_APPROVAL_INDEXES:
        conn.execute(f"DROP INDEX {name}")
    for u in ("a", "b"):  # pre-existing duplicate completed rows (legacy data)
        conn.execute("INSERT INTO validation_signoffs (company_id, doc_type, record_id, signatory_key, "
                     "designation, signer_user_id) VALUES (?,?,?,?,?,?)", (COMPANY, "URS", 9, "qa_manager", "d", u))
    conn.commit()
    assert vadb.ensure_unique_indexes(conn) is False
    dups = vadb.find_duplicate_signoffs(conn)
    assert dups == [{"invariant": "signatory", "company_id": COMPANY, "doc_type": "URS", "record_id": 9, "count": 2}]
    assert conn.execute("SELECT COUNT(*) FROM validation_signoffs").fetchone()[0] == 2  # nothing deleted
    conn.close()


def _tenant(uid):
    return TenantContext(user_id=uid, email=f"{uid}@x.io", display_name=uid, role="reviewer_qa", company_id=COMPANY)


def test_perform_action_concurrent_signers_one_winner_and_status_advances_once(db_path, monkeypatch):
    """Two users race for the same designation: one 201, one 409; exactly one
    ledger row, one status write, one e-signature."""
    monkeypatch.setattr(va.module_access, "has_business_permission", lambda *a, **k: True)
    monkeypatch.setattr(va.config, "VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT", False)
    sigs, updates = [], []
    monkeypatch.setattr(va.esignature_service, "require_esignature", lambda *a, **k: None)
    monkeypatch.setattr(va.esignature_service, "record_signature",
                        lambda **k: sigs.append(k) or {"id": len(sigs), "signature_hash": "h"})
    monkeypatch.setattr(va.audit, "log", lambda *a, **k: None)
    monkeypatch.setattr(va.audit, "log_failure", lambda *a, **k: None)

    def call(i):
        return va.perform_action(
            tenant=_tenant(f"user{i}"), doc_type="URS", audit_type="urs",
            record={"id": 1, "status": "validation_review", "revision": "A"},
            data={"action": "Sign Off", "meaning": "Reviewed"}, performed_by=f"user{i}", role="reviewer_qa",
            validate_transition=lambda c, r: None, apply_update=updates.append,
            add_trail=lambda *a: {}, creator={})

    res = _race(call, 6)
    assert sum(1 for k, _ in res if k == "ok") == 1
    errs = [v for k, v in res if k == "err"]
    assert all(isinstance(v, va.ApprovalError) and v.http_status == 409 for v in errs), errs
    assert len(vadb.list_signoffs(COMPANY, "URS", 1)) == 1
    assert len(updates) == 1 and updates[0]["status"] == "final_approval"
    assert len(sigs) == 1


def test_perform_action_parallel_stage_never_sticks(db_path, monkeypatch):
    """Engineering and Production sign the same stage concurrently; whichever
    commits second must see both and advance the status (no lost update)."""
    monkeypatch.setattr(va.module_access, "has_business_permission", lambda *a, **k: True)
    monkeypatch.setattr(va.config, "VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT", False)
    monkeypatch.setattr(va.esignature_service, "require_esignature", lambda *a, **k: None)
    monkeypatch.setattr(va.esignature_service, "record_signature", lambda **k: {"id": 1, "signature_hash": "h"})
    monkeypatch.setattr(va.audit, "log", lambda *a, **k: None)
    monkeypatch.setattr(va.audit, "log_failure", lambda *a, **k: None)
    for _ in range(5):
        vadb.supersede_signoffs(COMPANY, "URS", 1, "reset")
        updates, keys = [], ["engineering_manager", "production_manager"]

        def call(i):
            return va.perform_action(
                tenant=_tenant(f"user{i}"), doc_type="URS", audit_type="urs",
                record={"id": 1, "status": "technical_review", "revision": "A"},
                data={"action": "Sign Off", "signatory": keys[i], "meaning": "Reviewed"},
                performed_by=f"user{i}", role="reviewer_qa", validate_transition=lambda c, r: None,
                apply_update=updates.append, add_trail=lambda *a: {}, creator={})

        res = _race(call, 2)
        assert [k for k, _ in res] == ["ok", "ok"]
        assert len(vadb.list_signoffs(COMPANY, "URS", 1)) == 2
        assert any(u.get("status") == "qa_review" for u in updates)

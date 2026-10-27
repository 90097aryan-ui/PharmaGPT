"""Fail-closed behaviour when a tenant's department memberships carry NO functional role.

This is production Nutra's state (all memberships have workflow_role_id NULL, which Supabase returns as
`workflow_roles: None`). Validation signing must be refused safely - clear 403, no signature, no ledger row, no
status change, an audit failure event - while the rest of the application keeps working.
"""

import pytest

from pharmagpt.services import validation_approval as va
from tests._va_helpers import SIGNERS, as_signer, post
from tests.test_validation_approval_workflow import KINDS, Suite


def nutra_membership(department):
    """A user_departments row exactly as Supabase returns it when workflow_role_id is NULL."""
    return {"departments": {"department_code": department}, "workflow_roles": None}


def as_nutra(monkeypatch, key):
    _uid, _role, _perm, dept, _func = SIGNERS[key]
    as_signer(monkeypatch, key, memberships=[nutra_membership(dept)])


@pytest.fixture(params=KINDS)
def suite(request, client, monkeypatch):
    return Suite(request.param, client, monkeypatch)


def test_submit_without_a_functional_role_is_refused_and_changes_nothing(suite, monkeypatch):
    as_nutra(monkeypatch, "prepared_by")
    r = suite.act("Submitted for Review", comments="ready")
    assert r.status_code == 403
    assert "requires" in r.get_json()["error"] and "role" in r.get_json()["error"]
    assert suite.status() == "draft"
    assert suite.ledger_rows(superseded=True) == []


def test_sign_off_without_a_functional_role_is_refused_and_changes_nothing(suite, monkeypatch):
    as_signer(monkeypatch, "prepared_by")                       # a properly provisioned author submits
    if suite.kind == "dq":
        suite.complete_training()
    assert suite.act("Submitted for Review", comments="ready").status_code == 201
    before_rows = suite.ledger_rows()
    status = suite.status()
    for key in ("reviewed_by", "engineering_manager", "qa_manager", "final_approval"):
        as_nutra(monkeypatch, key)
        r = suite.act("Sign Off", password="e2e-pass", **({"signatory": key} if key == "engineering_manager" else {}))
        assert r.status_code in (403, 409), (key, r.status_code, r.get_json())
        assert suite.status() == status                           # no transition
        assert suite.ledger_rows() == before_rows                 # no sign-off row
    page = suite.page().get_json()                                # the approval page still loads and shows the true state
    assert page["completed_count"] == len(before_rows) and page["status"] == status


def test_no_membership_at_all_is_refused_too(suite, monkeypatch):
    as_signer(monkeypatch, "prepared_by", memberships=[])
    assert suite.act("Submitted for Review").status_code == 403
    assert suite.ledger_rows(superseded=True) == []


def test_directory_failure_denies_signing(suite, monkeypatch):
    from pharmagpt.services import org_directory

    def boom(*a, **k):
        raise RuntimeError("supabase down")
    as_signer(monkeypatch, "prepared_by")
    monkeypatch.setattr(org_directory, "list_user_departments", boom)
    r = suite.act("Submitted for Review")
    assert r.status_code == 403 and "could not verify" in r.get_json()["error"].lower()
    assert suite.status() == "draft"


def test_make_effective_and_obsolete_cannot_skip_the_missing_signatures(suite, monkeypatch):
    as_nutra(monkeypatch, "final_approval")
    for action in ("Make Effective", "Obsolete"):
        r = suite.act(action, password="e2e-pass")
        assert r.status_code in (403, 409), (action, r.status_code)
        assert suite.status() == "draft"
    assert suite.ledger_rows(superseded=True) == []


def test_unrelated_urs_workflows_still_work_in_the_same_state(client, monkeypatch):
    """Editing, listing and reading a URS, and its approval page, do not depend on the directory."""
    as_nutra(monkeypatch, "prepared_by")
    created = client.post("/urs/", json={"title": "Fluid bed", "equipment_name": "FBP"})
    assert created.status_code == 201
    uid = created.get_json()["id"]
    assert client.put(f"/urs/{uid}", json={"title": "Fluid bed v2"}).status_code == 200
    assert client.get(f"/urs/{uid}").get_json()["title"] == "Fluid bed v2"
    assert any(u["id"] == uid for u in client.get("/urs/").get_json())
    page = client.get(f"/urs/{uid}/approval/signatories").get_json()
    assert page["status"] == "draft" and len(page["signatories"]) == len(va.SIGNATORIES)
    assert client.get("/health").get_json() == {"status": "ok"}

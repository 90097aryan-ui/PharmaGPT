"""Approval-gated signer provisioning: refuses without written approval, never writes in dry run,
preserves is_primary, captures originals, uses the audited assignment path."""

import copy
import json

import pytest

from pharmagpt.services import signer_provisioning as sp
from scripts import provision_validation_signers as cli
from tests.test_org_assignment import FakeOrgClient

CO = "11111111-1111-1111-1111-111111111111"
# designation -> (user id, current membership dept, current is_primary; None = no membership yet)
USERS = {"prepared_by": ("u-val-init", "VALIDATION", True), "reviewed_by_eng": ("u-eng-rev", "ENGINEERING", False),
         "engineering_manager": ("u-eng-app", "ENGINEERING", False), "production_manager": ("u-prod-app", "PRODUCTION", True),
         "qa_manager": ("u-qa-app", "QA", False), "validation_manager": ("u-val-app", "VALIDATION", False),
         "final_approval": ("u-plant", None, None)}
DEPTS = ["VALIDATION", "ENGINEERING", "PRODUCTION", "QA", "PLANT_HEAD"]
WROLES = ["Initiator", "Coordinator", "Reviewer", "Approver", "Plant Head"]


def _store():
    st = {"users": [{"id": u, "company_id": CO, "status": "active"} for u, _, _ in USERS.values()]
                   + [{"id": "u-admin", "company_id": CO, "status": "active"}],
          "departments": [{"id": f"d-{c}", "company_id": CO, "department_code": c} for c in DEPTS],
          "workflow_roles": [{"id": i + 1, "name": n} for i, n in enumerate(WROLES)],
          "user_departments": [], "rbac_roles": [], "rbac_user_roles": [], "rbac_audit_log": []}
    for des, (uid, dept, prim) in USERS.items():
        st["rbac_roles"].append({"id": f"r-{des}", "company_id": CO, "name": sp.APPROVED_MAP[des][2],
                                 "is_template": False, "status": "active"})
        st["rbac_user_roles"].append({"id": f"ur-{des}", "user_id": uid, "role_id": f"r-{des}", "company_id": CO})
        if dept:
            st["user_departments"].append({"id": f"m-{des}", "user_id": uid, "department_id": f"d-{dept}",
                                           "company_id": CO, "workflow_role_id": None, "is_primary": prim})
    return st


def _approval(choice="ENGINEERING"):
    ap = {"approvals": {w: {"approver_ref": "ref", "date": "2026-10-27", "reference": f"{w}-1"}
                        for w in sp.REQUIRED_APPROVERS},
          "plant_head_additional_approvals": {w: {"approver_ref": "ref", "date": "2026-10-27", "reference": f"{w}-2"}
                                              for w in sp.PLANT_HEAD_APPROVERS},
          "reviewer_choice": choice, "actor_pseudonym": sp.pseudonym("u-admin"), "changes": []}
    for des, (uid, _, _) in USERS.items():
        ap["changes"].append({"designation": des, "pseudonym": sp.pseudonym(uid)})
    return ap


def _write(tmp_path, ap):
    p = tmp_path / "approval.json"
    p.write_text(json.dumps(ap))
    return str(p)


def test_missing_or_partial_approval_is_refused():
    for mutate in (lambda a: a["approvals"].pop("qa_head"), lambda a: a.pop("plant_head_additional_approvals"),
                   lambda a: a.pop("reviewer_choice"), lambda a: a["approvals"]["administrator"].pop("reference")):
        ap = _approval()
        mutate(ap)
        with pytest.raises(sp.ProvisioningError):
            sp.validate_approval(ap)


def test_change_set_must_be_exactly_the_approved_minimum():
    ap = _approval()
    ap["changes"].append({"designation": "qa_coordinator", "pseudonym": "abcdef"})
    with pytest.raises(sp.ProvisioningError):
        sp.validate_approval(ap)           # Coordinator / extra rows rejected
    ap = _approval()
    ap["changes"].pop()
    with pytest.raises(sp.ProvisioningError):
        sp.validate_approval(ap)
    ap = _approval()
    ap["changes"][1]["pseudonym"] = ap["changes"][0]["pseudonym"]
    with pytest.raises(sp.ProvisioningError):
        sp.validate_approval(ap)           # SoD: distinct users
    ap = _approval("PRODUCTION")           # choice must match the reviewer row supplied
    with pytest.raises(sp.ProvisioningError):
        sp.validate_approval(ap)


def test_dry_run_writes_nothing(tmp_path):
    st = _store()
    before = copy.deepcopy(st)
    assert cli.main(["--approval", _write(tmp_path, _approval()), "--company-id", CO], client=FakeOrgClient(st)) == 0
    assert st == before


def test_execute_requires_rollback_out_and_complete_approval(tmp_path):
    st = _store()
    before = copy.deepcopy(st)
    assert cli.main(["--approval", _write(tmp_path, _approval()), "--company-id", CO, "--execute"],
                    client=FakeOrgClient(st)) == 2
    bad = _approval()
    bad["approvals"].pop("qa_head")
    assert cli.main(["--approval", _write(tmp_path, bad), "--company-id", CO, "--execute",
                     "--rollback-out", str(tmp_path / "rb.json")], client=FakeOrgClient(st)) == 2
    assert st == before


def test_user_without_the_justifying_rbac_role_is_refused(tmp_path):
    st = _store()
    st["rbac_user_roles"] = [r for r in st["rbac_user_roles"] if r["id"] != "ur-qa_manager"]
    assert cli.main(["--approval", _write(tmp_path, _approval()), "--company-id", CO],
                    client=FakeOrgClient(st)) == 2


def test_execute_applies_exactly_seven_changes_preserves_is_primary_and_audits(tmp_path):
    st = _store()
    roles = {w["name"]: w["id"] for w in st["workflow_roles"]}
    rb = tmp_path / "rb.json"
    assert cli.main(["--approval", _write(tmp_path, _approval()), "--company-id", CO, "--execute",
                     "--rollback-out", str(rb)], client=FakeOrgClient(st)) == 0
    by = {m["user_id"]: m for m in st["user_departments"]}
    assert by["u-val-init"]["workflow_role_id"] == roles["Initiator"] and by["u-val-init"]["is_primary"] is True
    assert by["u-prod-app"]["is_primary"] is True and by["u-eng-rev"]["is_primary"] is False
    assert by["u-plant"]["workflow_role_id"] == roles["Plant Head"] and by["u-plant"]["department_id"] == "d-PLANT_HEAD"
    assert len(st["user_departments"]) == 7 and len(st["rbac_audit_log"]) == 7
    assert len(st["rbac_user_roles"]) == 7                      # no duplicate RBAC inserts
    assert all(a["actor_user_id"] == "u-admin" for a in st["rbac_audit_log"])
    saved = json.loads(rb.read_text())
    assert [s["action"] for s in saved].count("INSERT") == 1    # originals captured; only Plant Head is new
    assert all(s["before"]["workflow_role_id"] is None for s in saved if s["before"])


def test_does_not_overwrite_an_existing_different_functional_role(tmp_path):
    st = _store()
    st["user_departments"][0]["workflow_role_id"] = 3           # Reviewer already on the Initiator's row
    assert cli.main(["--approval", _write(tmp_path, _approval()), "--company-id", CO],
                    client=FakeOrgClient(st)) == 2


def test_platform_super_admin_may_act_as_the_approving_owner(tmp_path):
    st = _store()
    st["users"].append({"id": "u-super", "company_id": None, "status": "active", "roles": {"name": "super_admin"}})
    ap = _approval()
    ap["actor_pseudonym"] = sp.pseudonym("u-super")
    assert cli.main(["--approval", _write(tmp_path, ap), "--company-id", CO], client=FakeOrgClient(st)) == 0
    st["users"][-1]["roles"] = {"name": "user"}      # an ordinary user outside the tenant is refused
    assert cli.main(["--approval", _write(tmp_path, ap), "--company-id", CO], client=FakeOrgClient(st)) == 2

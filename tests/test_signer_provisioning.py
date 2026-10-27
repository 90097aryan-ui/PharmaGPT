"""Authenticated, break-glass-gated, approval-verified signer provisioning (fail closed).

All against an in-memory fake Supabase client: nothing here can touch a real directory.
"""

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from pharmagpt.auth.context import TenantContext
from pharmagpt.services import org_assignment
from pharmagpt.services import signer_provisioning as sp
from scripts import provision_validation_signers as cli
from tests.test_org_assignment import FakeOrgClient

CO, OTHER = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
# designation -> (user id, current membership dept, current is_primary; None = no membership yet)
USERS = {"prepared_by": ("u-val-init", "VALIDATION", True), "reviewed_by_eng": ("u-eng-rev", "ENGINEERING", False),
         "engineering_manager": ("u-eng-app", "ENGINEERING", False), "production_manager": ("u-prod-app", "PRODUCTION", True),
         "qa_manager": ("u-qa-app", "QA", False), "validation_manager": ("u-val-app", "VALIDATION", False),
         "final_approval": ("u-plant", None, None)}
DEPTS = ["VALIDATION", "ENGINEERING", "PRODUCTION", "QA", "PLANT_HEAD"]
WROLES = ["Initiator", "Coordinator", "Reviewer", "Approver", "Plant Head"]
TODAY = datetime.now(timezone.utc).date()
FUTURE = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()


def _store():
    st = {"users": [{"id": u, "company_id": CO, "status": "active"} for u, _, _ in USERS.values()]
                   + [{"id": "u-admin", "company_id": CO, "status": "active"},
                      {"id": "u-qa-ind", "company_id": CO, "status": "active"}],
          "departments": [{"id": f"d-{c}", "company_id": CO, "department_code": c} for c in DEPTS],
          "workflow_roles": [{"id": i + 1, "name": n} for i, n in enumerate(WROLES)],
          "user_departments": [], "rbac_roles": [], "rbac_user_roles": [], "rbac_audit_log": [],
          "break_glass_access": []}
    for des, (uid, dept, prim) in USERS.items():
        st["rbac_roles"].append({"id": f"r-{des}", "company_id": CO, "name": sp.APPROVED_MAP[des][2],
                                 "is_template": False, "status": "active"})
        st["rbac_user_roles"].append({"id": f"ur-{des}", "user_id": uid, "role_id": f"r-{des}", "company_id": CO})
        if dept:
            st["user_departments"].append({"id": f"m-{des}", "user_id": uid, "department_id": f"d-{dept}",
                                           "company_id": CO, "workflow_role_id": None, "is_primary": prim})
    st["rbac_roles"].append({"id": "r-qa-coord", "company_id": CO, "name": "QA Coordinator/Admin",
                             "is_template": False, "status": "active"})
    st["rbac_user_roles"].append({"id": "ur-qa-ind", "user_id": "u-qa-ind", "role_id": "r-qa-coord", "company_id": CO})
    return st


def _tenant(uid, role, company=CO):
    return TenantContext(user_id=uid, email=f"{uid}@x.io", display_name=uid, role=role, company_id=company)


TOKENS = {"t-admin": _tenant("u-admin", "company_admin"), "t-qa": _tenant("u-qa-ind", "reviewer_qa"),
          "t-super": _tenant("u-super", "super_admin", None), "t-user": _tenant("u-plain", "user"),
          "t-rqa": _tenant("u-plain2", "reviewer_qa"), "t-otheradmin": _tenant("u-oadmin", "company_admin", OTHER),
          "t-qa-other": _tenant("u-qa-ind", "reviewer_qa", OTHER), "t-qa-app": _tenant("u-qa-app", "reviewer_qa"),
          "t-plant": _tenant("u-plant", "reviewer_qa"), "t-qa-norole": _tenant("u-nobody", "reviewer_qa")}


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    def resolve(tok):
        if tok not in TOKENS:
            raise RuntimeError("invalid token")
        return TOKENS[tok]
    monkeypatch.setattr(sp, "resolve_tenant_context", resolve)


def _approval(choice="ENGINEERING", admin="u-admin", qa="u-qa-ind", date=None, **over):
    d = (date or TODAY).isoformat()
    changes = [{"designation": des, "pseudonym": sp.pseudonym(uid)} for des, (uid, _, _) in USERS.items()
               if not (des == "reviewed_by_eng" and choice == "PRODUCTION")]
    if choice == "PRODUCTION":
        changes.append({"designation": "reviewed_by_prod", "pseudonym": sp.pseudonym("u-prod-rev")})
    ap = {"company_id": CO, "reviewer_choice": choice, "changes": changes,
          "approvals": {"administrator": {"approver_pseudonym": sp.pseudonym(admin), "date": d, "reference": "ADM-1"},
                        "qa": {"approver_pseudonym": sp.pseudonym(qa), "date": d, "reference": "QA-1"}},
          "plant_head_additional_approvals": {
              "administrator": {"approver_pseudonym": sp.pseudonym(admin), "date": d, "reference": "ADM-2"},
              "qa": {"approver_pseudonym": sp.pseudonym(qa), "date": d, "reference": "QA-2"}}}
    ap["change_set_sha256"] = sp.change_set_hash(CO, choice, [{"designation": c["designation"], "pseudonym": c["pseudonym"]} for c in changes])
    ap.update(over)
    return ap


def _run(tmp_path, st, *, approval=None, actor="t-admin", qa="t-qa", admin_tok=None, execute=False, extra=()):
    files = {"approval.json": json.dumps(approval or _approval())}
    for name, tok in (("actor.jwt", actor), ("qa.jwt", qa), ("admin.jwt", admin_tok)):
        if tok is not None:
            files[name] = tok
    for n, c in files.items():
        (tmp_path / n).write_text(c)
    args = ["--company-id", CO, "--approval", str(tmp_path / "approval.json"),
            "--actor-token-file", str(tmp_path / "actor.jwt"), "--qa-approver-token-file", str(tmp_path / "qa.jwt")]
    if admin_tok is not None:
        args += ["--admin-approver-token-file", str(tmp_path / "admin.jwt")]
    if execute:
        args += ["--execute", "--rollback-out", str(tmp_path / "rb.json")]
    return cli.main(args + list(extra), client=FakeOrgClient(st))


def _unchanged(st, before):
    assert st == before


# ── identity ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("actor,qa", [("bad-token", "t-qa"), ("t-admin", "bad-token"), ("", "t-qa"), ("t-admin", "")])
def test_unverifiable_identity_is_refused(tmp_path, actor, qa):
    st = _store(); before = copy.deepcopy(st)
    assert _run(tmp_path, st, actor=actor, qa=qa) == 2
    _unchanged(st, before)


def test_actor_id_in_the_file_is_ignored(tmp_path):
    st = _store()
    ap = _approval()
    ap["actor_pseudonym"] = sp.pseudonym("u-qa-app")      # a forged self-declared actor
    assert _run(tmp_path, st, approval=ap) == 0           # dry run passes; attribution comes from the verified token only


# ── authorization / break-glass ──────────────────────────────────────────────

@pytest.mark.parametrize("actor", ["t-user", "t-rqa", "t-otheradmin"])
def test_unauthorized_actor_roles_are_refused(tmp_path, actor):
    st = _store(); before = copy.deepcopy(st)
    # the approval names the actor as administrator, so ONLY the role/tenant authorization can refuse this
    assert _run(tmp_path, st, actor=actor, approval=_approval(admin=TOKENS[actor].user_id), execute=True) == 2
    _unchanged(st, before)


def _grant(**kw):
    return {"id": "bg-1", "super_admin_user_id": "u-super", "company_id": CO, "expires_at": FUTURE, "revoked_at": None, **kw}


@pytest.mark.parametrize("grants", [[], [_grant(revoked_at=PAST)], [_grant(expires_at=PAST)], [_grant(company_id=OTHER)],
                                    [_grant(super_admin_user_id="someone-else")]])
def test_super_admin_without_an_active_break_glass_grant_is_denied(tmp_path, grants):
    st = _store(); st["break_glass_access"] = grants; before = copy.deepcopy(st)
    assert _run(tmp_path, st, actor="t-super", approval=_approval(admin="u-super"), execute=True) == 2   # only the grant can refuse
    _unchanged(st, before)


def test_break_glass_lookup_failure_fails_closed(tmp_path):
    class Boom(FakeOrgClient):
        def table(self, name):
            if name == "break_glass_access":
                raise RuntimeError("db down")
            return super().table(name)
    st = _store()
    (tmp_path / "approval.json").write_text(json.dumps(_approval()))
    (tmp_path / "actor.jwt").write_text("t-super"); (tmp_path / "qa.jwt").write_text("t-qa")
    (tmp_path / "approval.json").write_text(json.dumps(_approval(admin="u-super")))
    rc = cli.main(["--company-id", CO, "--approval", str(tmp_path / "approval.json"), "--actor-token-file",
                   str(tmp_path / "actor.jwt"), "--qa-approver-token-file", str(tmp_path / "qa.jwt")], client=Boom(st))
    assert rc == 2


def test_super_admin_with_an_active_grant_is_authorized_and_the_grant_is_audited(tmp_path):
    st = _store(); st["break_glass_access"] = [_grant()]
    assert _run(tmp_path, st, actor="t-super", approval=_approval(admin="u-super"), execute=True) == 0
    assert len(st["rbac_audit_log"]) == 7
    assert all(a["actor_user_id"] == "u-super" and "break-glass bg-1" in a["reason"] for a in st["rbac_audit_log"])


# ── approvals ────────────────────────────────────────────────────────────────

def test_missing_or_incomplete_approvals_are_refused(tmp_path):
    for mutate in (lambda a: a["approvals"].pop("qa"), lambda a: a.pop("plant_head_additional_approvals"),
                   lambda a: a.pop("reviewer_choice"), lambda a: a["approvals"]["administrator"].pop("reference"),
                   lambda a: a.pop("change_set_sha256")):
        st = _store(); before = copy.deepcopy(st); ap = _approval(); mutate(ap)
        assert _run(tmp_path, st, approval=ap, execute=True) == 2
        _unchanged(st, before)


def test_stale_future_wrong_company_and_unbound_approvals_are_refused(tmp_path):
    cases = [_approval(date=TODAY - timedelta(days=sp.MAX_APPROVAL_AGE_DAYS + 1)),
             _approval(date=TODAY + timedelta(days=2)),
             _approval(company_id=OTHER),
             _approval(change_set_sha256="0" * 64)]
    tampered = _approval(); tampered["changes"][1]["pseudonym"] = sp.pseudonym("u-eng-app")   # edited after approval
    cases.append(tampered)
    for ap in cases:
        st = _store(); before = copy.deepcopy(st)
        assert _run(tmp_path, st, approval=ap, execute=True) == 2
        _unchanged(st, before)


def test_approver_pseudonym_must_match_the_authenticated_approver(tmp_path):
    st = _store()
    assert _run(tmp_path, st, approval=_approval(qa="u-someone-else")) == 2        # QA named in the file is not the QA presenting
    assert _run(tmp_path, st, approval=_approval(admin="u-someone-else")) == 2


def test_reviewer_choice_must_match_the_rows(tmp_path):
    ap = _approval("PRODUCTION"); ap["reviewer_choice"] = "ENGINEERING"
    assert _run(tmp_path, _store(), approval=ap) == 2
    st = _store()                                                                   # the production reviewer variant is valid
    st["users"].append({"id": "u-prod-rev", "company_id": CO, "status": "active"})
    st["rbac_roles"].append({"id": "r-prod-rev", "company_id": CO, "name": "Production Reviewer", "is_template": False})
    st["rbac_user_roles"].append({"id": "ur-prod-rev", "user_id": "u-prod-rev", "role_id": "r-prod-rev", "company_id": CO})
    st["user_departments"].append({"id": "m-prod-rev", "user_id": "u-prod-rev", "department_id": "d-PRODUCTION",
                                   "company_id": CO, "workflow_role_id": None, "is_primary": False})
    assert _run(tmp_path, st, approval=_approval("PRODUCTION")) == 0


# ── independence / self-approval ─────────────────────────────────────────────

def test_independent_qa_is_mandatory(tmp_path):
    st = _store(); before = copy.deepcopy(st)
    # QA approver is the actor / the administrator approver
    assert _run(tmp_path, st, actor="t-qa", qa="t-qa", approval=_approval(admin="u-qa-ind"), execute=True) == 2
    assert _run(tmp_path, st, actor="t-admin", qa="t-qa", admin_tok="t-qa", approval=_approval(admin="u-qa-ind"), execute=True) == 2
    # QA approver lacks a QA authority role / belongs to another company
    assert _run(tmp_path, st, qa="t-qa-norole", approval=_approval(qa="u-nobody"), execute=True) == 2
    assert _run(tmp_path, st, qa="t-qa-other", execute=True) == 2
    _unchanged(st, before)


def test_nobody_may_approve_or_act_on_their_own_change(tmp_path):
    st = _store(); before = copy.deepcopy(st)
    # the QA Approver (a subject, row 5) approving the change set that gives them authority
    assert _run(tmp_path, st, qa="t-qa-app", approval=_approval(qa="u-qa-app"), execute=True) == 2
    # a subject acting as the administrator
    TOKENS["t-subject-admin"] = _tenant("u-plant", "company_admin")
    assert _run(tmp_path, st, actor="t-subject-admin", execute=True) == 2
    _unchanged(st, before)


# ── dry run / success / attribution ──────────────────────────────────────────

def test_dry_run_is_the_default_and_writes_nothing(tmp_path):
    st = _store(); before = copy.deepcopy(st)
    assert _run(tmp_path, st) == 0
    _unchanged(st, before)
    assert not (tmp_path / "rb.json").exists()


def test_execute_requires_rollback_out(tmp_path):
    st = _store(); before = copy.deepcopy(st)
    args = ["--company-id", CO, "--approval", str(tmp_path / "approval.json"), "--actor-token-file", str(tmp_path / "actor.jwt"),
            "--qa-approver-token-file", str(tmp_path / "qa.jwt"), "--execute"]
    (tmp_path / "approval.json").write_text(json.dumps(_approval())); (tmp_path / "actor.jwt").write_text("t-admin")
    (tmp_path / "qa.jwt").write_text("t-qa")
    assert cli.main(args, client=FakeOrgClient(st)) == 2
    _unchanged(st, before)


def test_authorized_execute_applies_seven_changes_with_verified_attribution(tmp_path):
    st = _store(); roles = {w["name"]: w["id"] for w in st["workflow_roles"]}
    assert _run(tmp_path, st, execute=True) == 0
    by = {m["user_id"]: m for m in st["user_departments"]}
    assert by["u-val-init"]["workflow_role_id"] == roles["Initiator"] and by["u-val-init"]["is_primary"] is True
    assert by["u-prod-app"]["is_primary"] is True and by["u-eng-rev"]["is_primary"] is False
    assert by["u-plant"]["workflow_role_id"] == roles["Plant Head"] and by["u-plant"]["department_id"] == "d-PLANT_HEAD"
    assert len(st["user_departments"]) == 7 and len(st["rbac_user_roles"]) == 8      # no duplicate RBAC inserts
    audits = st["rbac_audit_log"]
    assert len(audits) == 7
    for a in audits:                                                                   # actor = the VERIFIED token holder
        assert a["actor_user_id"] == "u-admin"
        assert "ADM-1" in a["reason"] and "QA-1" in a["reason"] and sp.pseudonym("u-qa-ind") in a["reason"]
    saved = json.loads((tmp_path / "rb.json").read_text())
    assert [s["action"] for s in saved["steps"]].count("INSERT") == 1 and "actor_pseudonym" not in saved["approval"]


def test_does_not_overwrite_an_existing_different_functional_role(tmp_path):
    st = _store(); st["user_departments"][0]["workflow_role_id"] = 3
    assert _run(tmp_path, st) == 2


def test_user_without_the_justifying_rbac_role_is_refused(tmp_path):
    st = _store(); st["rbac_user_roles"] = [r for r in st["rbac_user_roles"] if r["id"] != "ur-qa_manager"]
    assert _run(tmp_path, st) == 2


# ── atomicity / rollback ─────────────────────────────────────────────────────

def test_a_mid_run_audit_failure_rolls_back_everything_applied(tmp_path, monkeypatch):
    st = _store(); original_memberships = copy.deepcopy(st["user_departments"])
    real = org_assignment.rbac_repo.add_rbac_audit_entry
    calls = {"n": 0}

    def flaky(client, **kw):
        if not kw["reason"].startswith("ROLLBACK"):
            calls["n"] += 1
            if calls["n"] == 4:
                raise RuntimeError("audit insert failed")
        return real(client, **kw)

    monkeypatch.setattr(org_assignment.rbac_repo, "add_rbac_audit_entry", flaky)
    monkeypatch.setattr(sp.rbac_repo, "add_rbac_audit_entry", flaky)
    assert _run(tmp_path, st, execute=True) == 1
    assert st["user_departments"] == original_memberships                              # nothing left half-applied
    assert sum(1 for a in st["rbac_audit_log"] if a["reason"].startswith("ROLLBACK")) == 3   # each undo audited


def test_saved_rollback_restores_and_audits_and_needs_authorization(tmp_path):
    st = _store(); original = copy.deepcopy(st["user_departments"])
    assert _run(tmp_path, st, execute=True) == 0
    rb = str(tmp_path / "rb.json")
    (tmp_path / "actor.jwt").write_text("t-admin")
    base = ["--company-id", CO, "--rollback", rb, "--actor-token-file", str(tmp_path / "actor.jwt")]
    snapshot = copy.deepcopy(st)
    assert cli.main(base, client=FakeOrgClient(st)) == 0 and st == snapshot             # dry run writes nothing
    (tmp_path / "bad.jwt").write_text("t-user")
    assert cli.main(["--company-id", CO, "--rollback", rb, "--actor-token-file", str(tmp_path / "bad.jwt"), "--execute"],
                    client=FakeOrgClient(st)) == 2 and st == snapshot                    # unauthorized actor refused
    assert cli.main(base + ["--execute"], client=FakeOrgClient(st)) == 0
    assert st["user_departments"] == original
    assert sum(1 for a in st["rbac_audit_log"] if a["reason"].startswith("ROLLBACK")) == 7
    assert all(a["actor_user_id"] == "u-admin" for a in st["rbac_audit_log"])


def test_change_set_hash_helper_is_offline_and_matches(tmp_path, capsys):
    ap = _approval(); (tmp_path / "a.json").write_text(json.dumps(ap))
    assert cli.main(["--company-id", CO, "--approval", str(tmp_path / "a.json"), "--print-change-set-hash"]) == 0
    assert capsys.readouterr().out.strip() == ap["change_set_sha256"]

"""
tests/test_workflow_engine_org_authorization.py — Regression coverage for
the Yuktav org/RBAC/workflow authorization task's two additions to
pharmagpt/services/workflow_engine.py:

  1. decide_step(..., tenant=...)'s additional business-permission check
     (pharmagpt.auth.module_access.has_business_permission), stacked
     alongside the existing, unchanged named-approver/eligible-role check.
  2. start_instance()'s optional department + functional-role auto-
     resolution of a named approver (pharmagpt.services.org_assignment.
     resolve_department_approver), snapshotted into the existing
     qms_workflow_step_approvers mechanism.

Follows tests/test_workflow_engine.py's exact conventions (db_path fixture,
autouse Flask app_context, engine called directly, no HTTP).
"""

from unittest.mock import patch

import pytest

from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_workflow_database as wfdb
from pharmagpt.auth.context import TenantContext
from pharmagpt.services import workflow_engine as wfe

COMPANY_ID = "test-company"
INITIATOR = "Ida Initiator"

EFFECTIVE_PERMISSIONS_PATH = "pharmagpt.auth.module_access.get_effective_permissions"
SERVICE_CLIENT_PATH = "pharmagpt.services.supabase_client.get_service_role_client"


@pytest.fixture(autouse=True)
def _app_context():
    import pharmagpt.app as appmod
    with appmod.app.app_context():
        yield


def _make_deviation(db_path):
    return ddb.create_deviation({"title": "Temp excursion"}, company_id=COMPANY_ID)


def _start(dev):
    return wfe.start_instance("DEVIATION_INVESTIGATION_V1", "deviation", dev["id"], COMPANY_ID, INITIATOR)


def _tenant(role="user", user_id="u1"):
    return TenantContext(user_id=user_id, email=f"{user_id}@x.com", display_name=user_id,
                          role=role, company_id=COMPANY_ID)


# ── decide_step(tenant=...) business-permission check ──────────────────────

def test_decide_step_without_tenant_is_completely_unaffected(db_path):
    """Backward compatibility: every existing caller (and every existing
    test in tests/test_workflow_engine.py) that doesn't pass `tenant` sees
    no behavior change at all — the new check is opt-in."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "mgr-1", "display_name": "Manny"}])
    state = wfe.decide_step("deviation", dev["id"], 2, "approve",
                             user_id="mgr-1", role="reviewer_qa", performed_by="Manny")
    assert state["instance"]["current_step_order"] == 3


def test_decide_step_with_tenant_denies_when_no_business_permission(db_path):
    """The actual fail-closed enforcement: a named, eligible approver (would
    pass the existing identity check) is still denied if they hold no
    QMS/Approve grant — 'a user with REVIEW permission but no APPROVE
    permission must not be able to approve by calling the API directly'."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "mgr-1", "display_name": "Manny"}])

    tenant = _tenant(role="user", user_id="mgr-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "Review")}):  # Review, not Approve
        with pytest.raises(wfe.WorkflowPermissionError):
            wfe.decide_step("deviation", dev["id"], 2, "approve",
                             user_id="mgr-1", role="user", performed_by="Manny", tenant=tenant)


def test_decide_step_with_tenant_allows_when_business_permission_granted(db_path):
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "mgr-1", "display_name": "Manny"}])

    tenant = _tenant(role="user", user_id="mgr-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "Approve")}):
        state = wfe.decide_step("deviation", dev["id"], 2, "approve",
                                 user_id="mgr-1", role="user", performed_by="Manny", tenant=tenant)
    assert state["instance"]["current_step_order"] == 3


def test_initiator_cannot_approve_even_if_named_as_approver(db_path):
    """Initiator-tier grants (View/Create/Edit/Submit) never include
    Approve — even a misconfigured named-approver assignment is still
    denied at decide time."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "init-1", "display_name": "Ivy Initiator"}])

    tenant = _tenant(role="user", user_id="init-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "View"), ("QMS", "Create"), ("QMS", "Submit")}):
        with pytest.raises(wfe.WorkflowPermissionError):
            wfe.decide_step("deviation", dev["id"], 2, "approve",
                             user_id="init-1", role="user", performed_by="Ivy", tenant=tenant)


def test_company_admin_with_no_rbac_grant_is_denied(db_path):
    """REVISION (RBAC enforcement closure task): company_admin's
    unconditional business bypass has been removed now that production
    RBAC data is authoritative — an unprovisioned company_admin (no
    rbac_user_roles row) is denied like anyone else. See
    pharmagpt/auth/module_access.py's module docstring."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "admin-1", "display_name": "Admin"}])

    tenant = _tenant(role="company_admin", user_id="admin-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=set()):
        with pytest.raises(wfe.WorkflowPermissionError):
            wfe.decide_step("deviation", dev["id"], 2, "approve",
                             user_id="admin-1", role="company_admin", performed_by="Admin", tenant=tenant)


def test_company_admin_with_rbac_grant_can_still_decide(db_path):
    """A properly-provisioned company_admin — holding the company's cloned
    "Company Admin" role, which grants every (module, action) pair — still
    gets identical business access as before, now resolved through real
    RBAC data instead of a hardcoded exception."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "admin-1", "display_name": "Admin"}])

    tenant = _tenant(role="company_admin", user_id="admin-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "Approve")}):
        state = wfe.decide_step("deviation", dev["id"], 2, "approve",
                                 user_id="admin-1", role="company_admin", performed_by="Admin", tenant=tenant)
    assert state["instance"]["current_step_order"] == 3


def test_identity_check_denial_is_independent_of_business_permission_grant(db_path):
    """Ordering guarantee: the named-approver identity check must run and
    be able to deny BEFORE the business-permission check is ever reached —
    a broad/permissive business-permission grant must never paper over a
    failed identity check. mgr-1 is never assigned as an approver here."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "someone-else", "display_name": "Someone"}])

    tenant = _tenant(role="user", user_id="mgr-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "Approve")}) as mocked:
        with pytest.raises(wfe.WorkflowPermissionError, match="not an assigned approver"):
            wfe.decide_step("deviation", dev["id"], 2, "approve",
                             user_id="mgr-1", role="user", performed_by="Manny", tenant=tenant)
        # The identity check must have short-circuited before the
        # business-permission lookup ever ran.
        mocked.assert_not_called()


def test_super_admin_denied_business_permission_even_if_named(db_path):
    """super_admin has no standing tenant/business access — even if
    (incorrectly) named as an approver, the business-permission layer
    denies them, matching the existing 'super_admin has no standing tenant
    content access' invariant enforced elsewhere in this app."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "su-1", "display_name": "Super"}])

    tenant = _tenant(role="super_admin", user_id="su-1")
    with pytest.raises(wfe.WorkflowPermissionError):
        wfe.decide_step("deviation", dev["id"], 2, "approve",
                         user_id="su-1", role="super_admin", performed_by="Super", tenant=tenant)


# ── start_instance() department/functional-role auto-resolution ───────────

def test_auto_resolution_is_a_no_op_when_step_has_no_department_role_opt_in(db_path):
    """Every existing seeded template (DEVIATION_INVESTIGATION_V1 included)
    has department_code/functional_role_name = NULL on every step — auto-
    resolution must never fire for them, preserving 100% of existing
    behavior (manual assign_approvers() remains required, exactly as
    today)."""
    dev = _make_deviation(db_path)
    with patch(SERVICE_CLIENT_PATH) as mocked_client:
        _start(dev)
        mocked_client.assert_not_called()

    state = wfe.get_instance_state("deviation", dev["id"])
    step_2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step_2["approvers"] == []  # still unassigned — no auto-resolution happened


def test_auto_resolution_snapshots_resolved_approver_into_named_approver_table(db_path):
    """A step opted into department/role auto-resolution gets a real named
    approver written into qms_workflow_step_approvers — the SAME mechanism
    manual assign_approvers() uses — so decide_step()'s existing
    named-approver check needs no changes at all."""
    template = wfdb.create_template("AUTO_RESOLVE_TEST", "Auto-resolve test", "deviation")
    wfdb.create_template_step(template["id"], 1, "submitted", "Submitted", "activity", "user", "Open")
    wfdb.create_template_step(
        template["id"], 2, "mgr_review", "Manager Review", "approval", "", "Manager Review",
        department_code="PRODUCTION", functional_role_name="Reviewer",
    )
    dev = _make_deviation(db_path)

    fake_client = object()  # never actually queried past .table(), see FakeOrgClient below
    resolved = {"user_id": "prod-rev-1", "display_name": "Priya Production Reviewer"}
    with patch(SERVICE_CLIENT_PATH, return_value=fake_client), \
         patch("pharmagpt.services.org_assignment.resolve_department_approver", return_value=resolved) as mocked_resolve:
        wfe.start_instance("AUTO_RESOLVE_TEST", "deviation", dev["id"], COMPANY_ID, INITIATOR)
        mocked_resolve.assert_called_once_with(fake_client, COMPANY_ID, "PRODUCTION", "Reviewer")

    state = wfe.get_instance_state("deviation", dev["id"])
    step_2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert [{"user_id": a["user_id"], "display_name": a["display_name"]} for a in step_2["approvers"]] == [
        {"user_id": "prod-rev-1", "display_name": "Priya Production Reviewer"}
    ]

    # The auto-resolved approver can now decide the step exactly like a
    # manually-assigned one — no change needed to decide_step's identity check.
    # AUTO_RESOLVE_TEST has only 2 steps, so approving step 2 (the last one)
    # completes the instance rather than advancing to a step 3.
    decided = wfe.decide_step("deviation", dev["id"], 2, "approve",
                               user_id="prod-rev-1", role="reviewer_qa", performed_by="Priya")
    assert decided["instance"]["status"] == "completed"


def test_auto_resolution_snapshot_is_not_retroactively_changed_by_a_later_role_change(db_path):
    """The explicit non-negotiable requirement: once a workflow step has
    been assigned (whether manually or auto-resolved), a later change to
    that person's department/role must NOT change the already-created
    instance step. Verified here by resolving once at start_instance time,
    then confirming a second, different resolve_department_approver result
    is never consulted again for the same, already-created step."""
    template = wfdb.create_template("AUTO_RESOLVE_SNAPSHOT_TEST", "Auto-resolve snapshot test", "deviation")
    wfdb.create_template_step(template["id"], 1, "submitted", "Submitted", "activity", "user", "Open")
    wfdb.create_template_step(
        template["id"], 2, "mgr_review", "Manager Review", "approval", "", "Manager Review",
        department_code="PRODUCTION", functional_role_name="Reviewer",
    )
    dev = _make_deviation(db_path)

    with patch(SERVICE_CLIENT_PATH, return_value=object()), \
         patch("pharmagpt.services.org_assignment.resolve_department_approver",
               return_value={"user_id": "prod-rev-1", "display_name": "Priya"}):
        wfe.start_instance("AUTO_RESOLVE_SNAPSHOT_TEST", "deviation", dev["id"], COMPANY_ID, INITIATOR)

    # "Priya" changes department/role after the workflow started — simulated
    # by resolve_department_approver now returning someone else entirely.
    # start_instance is never called again, so this must never be consulted.
    with patch("pharmagpt.services.org_assignment.resolve_department_approver",
               return_value={"user_id": "someone-else", "display_name": "Someone Else"}) as mocked_resolve:
        state = wfe.get_instance_state("deviation", dev["id"])
        mocked_resolve.assert_not_called()

    step_2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert [{"user_id": a["user_id"], "display_name": a["display_name"]} for a in step_2["approvers"]] == [
        {"user_id": "prod-rev-1", "display_name": "Priya"}
    ]


def test_auto_resolution_no_op_when_nobody_currently_holds_the_role(db_path):
    template = wfdb.create_template("AUTO_RESOLVE_EMPTY_TEST", "Auto-resolve empty test", "deviation")
    wfdb.create_template_step(template["id"], 1, "submitted", "Submitted", "activity", "user", "Open")
    wfdb.create_template_step(
        template["id"], 2, "mgr_review", "Manager Review", "approval", "", "Manager Review",
        department_code="PRODUCTION", functional_role_name="Reviewer",
    )
    dev = _make_deviation(db_path)

    with patch(SERVICE_CLIENT_PATH, return_value=object()), \
         patch("pharmagpt.services.org_assignment.resolve_department_approver", return_value=None):
        wfe.start_instance("AUTO_RESOLVE_EMPTY_TEST", "deviation", dev["id"], COMPANY_ID, INITIATOR)

    state = wfe.get_instance_state("deviation", dev["id"])
    step_2 = next(s for s in state["steps"] if s["step_order"] == 2)
    assert step_2["approvers"] == []  # unassigned, not an error — same as today's "nobody assigned yet"


# ── start_instance()'s Submit-permission gate ──────────────────────────────

def test_start_instance_without_tenant_is_unaffected(db_path):
    """Backward compatibility: omitting `tenant` (every pre-existing caller,
    including Document Control's route wiring) is a complete no-op for this
    gate."""
    dev = _make_deviation(db_path)
    state = _start(dev)
    assert state["instance"]["status"] == "in_progress"


def test_start_instance_denies_without_submit_permission(db_path):
    dev = _make_deviation(db_path)
    tenant = _tenant(role="user", user_id="init-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=set()):
        with pytest.raises(wfe.WorkflowPermissionError):
            wfe.start_instance("DEVIATION_INVESTIGATION_V1", "deviation", dev["id"],
                                COMPANY_ID, INITIATOR, tenant=tenant)


def test_start_instance_allows_with_submit_permission(db_path):
    dev = _make_deviation(db_path)
    tenant = _tenant(role="user", user_id="init-1")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "Submit")}):
        state = wfe.start_instance("DEVIATION_INVESTIGATION_V1", "deviation", dev["id"],
                                    COMPANY_ID, INITIATOR, tenant=tenant)
    assert state["instance"]["status"] == "in_progress"


def test_named_user_assignment_still_works_alongside_auto_resolution_capability(db_path):
    """Existing named-user workflow (manual assign_approvers()) is
    completely unaffected by this task, even for a template that has NOT
    opted into auto-resolution — using DEVIATION_INVESTIGATION_V1 itself,
    identical to tests/test_workflow_engine.py's own coverage."""
    dev = _make_deviation(db_path)
    _start(dev)
    wfe.assign_approvers("deviation", dev["id"], 2, [{"user_id": "mgr-1", "display_name": "Manny Manager"}])
    state = wfe.decide_step("deviation", dev["id"], 2, "approve",
                             user_id="mgr-1", role="reviewer_qa", performed_by="Manny Manager")
    assert state["instance"]["current_step_order"] == 3

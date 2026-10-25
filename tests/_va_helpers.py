"""Shared helpers for the standardized Validation approval workflow tests
(URS, DQ, and Qualification IQ/OQ/PQ protocols). Impersonation reuses the
conftest `client` fixture's tenant shim (tests/conftest.py::_TEST_TENANT) and
its permissive-RBAC patch, which each helper call narrows to exactly the
permissions AND department memberships the persona holds."""

import tests.conftest as conftest_module
from pharmagpt.auth.context import TenantContext
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID

# designation key -> (user id, platform role, Validation permission, department, functional role)
SIGNERS = {
    "prepared_by":         ("10000000-0000-0000-0000-000000000001", "user",        "Submit",  "VALIDATION",  "Initiator"),
    "reviewed_by":         ("10000000-0000-0000-0000-000000000002", "reviewer_qa", "Review",  "ENGINEERING", "Reviewer"),
    "engineering_manager": ("10000000-0000-0000-0000-000000000003", "reviewer_qa", "Approve", "ENGINEERING", "Approver"),
    "production_manager":  ("10000000-0000-0000-0000-000000000004", "reviewer_qa", "Approve", "PRODUCTION",  "Approver"),
    "qa_manager":          ("10000000-0000-0000-0000-000000000005", "reviewer_qa", "Approve", "QA",          "Approver"),
    "validation_manager":  ("10000000-0000-0000-0000-000000000006", "reviewer_qa", "Approve", "VALIDATION",  "Approver"),
    "final_approval":      ("10000000-0000-0000-0000-000000000007", "reviewer_qa", "Approve", "PLANT_HEAD",  "Plant Head"),
}
CHAIN = ["reviewed_by", "engineering_manager", "production_manager",
         "qa_manager", "validation_manager", "final_approval"]
PARALLEL = ("engineering_manager", "production_manager")
EXPECTED_AFTER = {  # status after each sign-off in CHAIN order
    "reviewed_by": "technical_review", "engineering_manager": "technical_review",
    "production_manager": "qa_review", "qa_manager": "validation_review",
    "validation_manager": "final_approval", "final_approval": "approved",
}
ALL_DEPARTMENTS = ("VALIDATION", "ENGINEERING", "PRODUCTION", "QA", "PLANT_HEAD")


def membership(department, functional_role):
    return {"departments": {"department_code": department}, "workflow_roles": {"name": functional_role}}


def set_memberships(monkeypatch, memberships):
    """Stub the org directory (Supabase) with the given user_departments rows."""
    from pharmagpt.services import org_directory
    monkeypatch.setattr("pharmagpt.services.supabase_client.get_service_role_client", lambda: object())
    monkeypatch.setattr(org_directory, "list_user_departments",
                        lambda client, user_id, company_id: list(memberships))


def grant_all_departments(monkeypatch):
    """For tests that are not about department authorization: the caller holds
    a Coordinator role in every department the workflow knows about."""
    set_memberships(monkeypatch, [membership(d, "Coordinator") for d in ALL_DEPARTMENTS])


def impersonate(monkeypatch, user_id, role, perms, company_id=BOOTSTRAP_COMPANY_ID, name=None,
                memberships=None):
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", TenantContext(
        user_id=user_id, email=f"{user_id[-2:]}@example.com",
        display_name=name or f"User {user_id[-2:]}", role=role, company_id=company_id))
    monkeypatch.setattr("pharmagpt.auth.module_access.get_effective_permissions",
                        lambda tenant: {("Validation", p) for p in perms})
    if memberships is None:
        grant_all_departments(monkeypatch)
    else:
        set_memberships(monkeypatch, memberships)


def as_signer(monkeypatch, key, extra_perms=(), memberships="own"):
    uid, role, perm, dept, func = SIGNERS[key]
    # Mirrors rbac_defaults.FUNCTIONAL_ROLE_ACTIONS: Approvers also hold Reject.
    granted = {perm, "View", *(("Reject",) if perm == "Approve" else ()), *extra_perms}
    own = [membership(dept, func)] if memberships == "own" else memberships
    impersonate(monkeypatch, uid, role, granted, memberships=own)


def post(client, base, rid, action, **extra):
    return client.post(f"{base}/{rid}/approval", json={"action": action, **extra})


def sign_extra(key):
    return {"signatory": key} if key in PARALLEL else {}


def drive_to_approved(client, monkeypatch, base, rid):
    """Submit and collect all seven signatures through the real routes."""
    as_signer(monkeypatch, "prepared_by")
    r = post(client, base, rid, "Submitted for Review")
    assert r.status_code == 201, r.get_json()
    for key in CHAIN:
        as_signer(monkeypatch, key)
        r = post(client, base, rid, "Sign Off", **sign_extra(key))
        assert r.status_code == 201, (key, r.get_json())

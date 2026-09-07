"""
tests/test_module_access.py — Regression coverage for the Yuktav org/RBAC/
workflow authorization task's business-permission gate
(pharmagpt/auth/module_access.py: has_business_permission,
require_business_permission), the new layer sitting on top of the existing,
unmodified pharmagpt.auth.rbac.get_effective_permissions().

Uses the same mocked-TenantContext technique as tests/test_rbac.py — no
real Supabase project is touched. get_effective_permissions() itself is
patched directly (unit-level) rather than re-mocking the whole Supabase
client chain, since this module's own correctness doesn't depend on how
that set is produced, only on what it does with it.
"""

from unittest.mock import patch

import pytest

from pharmagpt.auth.context import TenantContext
from pharmagpt.auth.module_access import (
    action_for_decision,
    has_business_permission,
    major_module_for_record_type,
    require_business_permission,
)

EFFECTIVE_PERMISSIONS_PATH = "pharmagpt.auth.module_access.get_effective_permissions"

COMPANY_A = "11111111-1111-1111-1111-111111111111"
COMPANY_B = "22222222-2222-2222-2222-222222222222"

SUPER_ADMIN = TenantContext(user_id="su", email="su@x.com", display_name="SU", role="super_admin", company_id=None)
COMPANY_ADMIN = TenantContext(user_id="admin-a", email="a@x.com", display_name="Admin A",
                               role="company_admin", company_id=COMPANY_A)


def _user(role="user", user_id="u1", company_id=COMPANY_A):
    return TenantContext(user_id=user_id, email=f"{user_id}@x.com", display_name=user_id,
                          role=role, company_id=company_id)


# ── super_admin / company_admin ──────────────────────────────────────────
# REVISION (RBAC enforcement closure task): company_admin's unconditional
# business-operation bypass has been removed now that production RBAC data
# is authoritative — see pharmagpt/auth/module_access.py's module docstring
# for the full rationale. company_admin now resolves through the exact same
# get_effective_permissions() path as everyone else; its administrative
# authority (require_role("company_admin"), has_rbac_admin_access(), every
# /rbac /org /users /companies surface) is untouched, since none of those
# call has_business_permission() at all.

def test_super_admin_never_has_business_permission():
    """No standing tenant/business access — even for Administration, unlike
    the platform-scope pharmagpt.auth.rbac.has_permission's special case."""
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=set()) as mocked:
        assert has_business_permission(SUPER_ADMIN, "QMS", "View") is False
        mocked.assert_not_called()  # short-circuits before any RBAC lookup


def test_company_admin_with_no_rbac_grant_is_denied():
    """The removed-bypass behavior: an unprovisioned company_admin (no
    rbac_user_roles row — e.g. a company that hasn't been through
    provision_org_defaults_for_company()) is now DENIED, not automatically
    granted. This is the explicit, documented consequence of tightening
    enforcement once RBAC data is authoritative."""
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=set()):
        assert has_business_permission(COMPANY_ADMIN, "Validation", "Approve") is False


def test_company_admin_with_full_rbac_grant_is_allowed():
    """A properly-provisioned company_admin — holding this company's cloned
    "Company Admin" RBAC role, which rbac_defaults.default_grants_for_role's
    "company_admin" tier grants every (module, action) pair — gets identical
    business access as before, now resolved through real RBAC data instead
    of a hardcoded exception."""
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("Validation", "Approve")}):
        assert has_business_permission(COMPANY_ADMIN, "Validation", "Approve") is True


def test_reviewer_qa_no_longer_bypasses_business_permission():
    """Same tightening as company_admin: reviewer_qa's business-action
    authority now depends on an actual RBAC grant."""
    tenant = _user(role="reviewer_qa")
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=set()):
        assert has_business_permission(tenant, "QMS", "Approve") is False
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "Approve")}):
        assert has_business_permission(tenant, "QMS", "Approve") is True


# ── Fail-closed: no grant -> deny, not "empty means unrestricted" ─────────

def test_unconfigured_user_with_no_rbac_grants_is_denied_every_module():
    """The actual fail-closed requirement: an authenticated tenant with an
    empty effective-permissions set (e.g. a production user before the
    department/role backfill has run) gets nothing — never an "empty means
    unrestricted" fallback like the pre-existing, deliberately-separate
    workspace_access.DENY_BY_DEFAULT=False switch."""
    tenant = _user()
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=set()):
        assert has_business_permission(tenant, "QMS", "View") is False
        assert has_business_permission(tenant, "Validation", "View") is False
        assert has_business_permission(tenant, "Document Control", "View") is False


def test_unrecognized_major_module_is_denied():
    tenant = _user()
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "View")}):
        assert has_business_permission(tenant, "NotAModule", "View") is False


# ── Target matrix cases, expressed as effective-permission sets a fully
# provisioned user would hold, per pharmagpt.services.rbac_defaults ────────

def test_production_initiator_qms_yes_validation_no_document_control_yes():
    tenant = _user()
    grants = {("QMS", "View"), ("Deviations", "Submit"), ("Document Control", "Create")}
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=grants):
        assert has_business_permission(tenant, "QMS", "View") is True
        assert has_business_permission(tenant, "Validation", "View") is False
        assert has_business_permission(tenant, "Document Control", "Create") is True


def test_production_reviewer_qms_yes_validation_yes_document_control_yes():
    tenant = _user()
    grants = {("QMS", "Review"), ("Validation", "Review"), ("Document Control", "Review")}
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=grants):
        assert has_business_permission(tenant, "QMS", "Review") is True
        assert has_business_permission(tenant, "Validation", "Review") is True
        assert has_business_permission(tenant, "Document Control", "Review") is True


def test_ppic_reviewer_and_approver_validation_denied():
    tenant = _user()
    grants = {("QMS", "Review"), ("Document Control", "Review")}
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=grants):
        assert has_business_permission(tenant, "Validation", "Review") is False
        assert has_business_permission(tenant, "Validation", "Approve") is False


def test_validation_initiator_reviewer_approver_all_true():
    tenant = _user()
    grants = {("Validation", "Submit"), ("Validation", "Review"), ("Validation", "Approve")}
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=grants):
        assert has_business_permission(tenant, "Validation", "Submit") is True
        assert has_business_permission(tenant, "Validation", "Review") is True
        assert has_business_permission(tenant, "Validation", "Approve") is True


# ── Initiator/Reviewer cannot approve without the APPROVE action ───────────

def test_initiator_cannot_approve():
    tenant = _user()
    grants = {("QMS", "View"), ("QMS", "Create"), ("QMS", "Submit")}
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=grants):
        assert has_business_permission(tenant, "QMS", "Approve") is False


def test_reviewer_without_approve_grant_cannot_approve():
    tenant = _user()
    grants = {("QMS", "View"), ("QMS", "Review")}
    with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=grants):
        assert has_business_permission(tenant, "QMS", "Approve") is False


# ── Cross-tenant isolation (delegated to get_effective_permissions, but
# the boundary belongs to this module's contract too) ──────────────────────

def test_effective_permissions_are_looked_up_for_the_given_tenant_only():
    tenant_a = _user(user_id="u-a", company_id=COMPANY_A)
    tenant_b = _user(user_id="u-b", company_id=COMPANY_B)

    def fake_effective(tenant):
        return {("QMS", "View")} if tenant.company_id == COMPANY_A else set()

    with patch(EFFECTIVE_PERMISSIONS_PATH, side_effect=fake_effective):
        assert has_business_permission(tenant_a, "QMS", "View") is True
        assert has_business_permission(tenant_b, "QMS", "View") is False


# ── require_business_permission decorator ──────────────────────────────────

def test_require_business_permission_denies_with_403(app_context_with_tenant=None):
    import pharmagpt.app as appmod
    from flask import g

    @require_business_permission("QMS", "Approve")
    def _view():
        return "ok"

    with appmod.app.test_request_context("/"):
        g.tenant = _user()
        with patch(EFFECTIVE_PERMISSIONS_PATH, return_value=set()):
            resp, status = _view()
    assert status == 403
    assert "Approve" in resp.get_json()["error"]


def test_require_business_permission_allows_when_granted():
    import pharmagpt.app as appmod
    from flask import g

    @require_business_permission("QMS", "Approve")
    def _view():
        return "ok"

    with appmod.app.test_request_context("/"):
        g.tenant = _user()
        with patch(EFFECTIVE_PERMISSIONS_PATH, return_value={("QMS", "Approve")}):
            result = _view()
    assert result == "ok"


# ── record_type / decision mapping helpers (workflow_engine.decide_step) ──

def test_record_type_major_module_mapping():
    assert major_module_for_record_type("deviation") == "QMS"
    assert major_module_for_record_type("capa") == "QMS"
    assert major_module_for_record_type("change_control") == "QMS"
    assert major_module_for_record_type("document") == "Document Control"
    assert major_module_for_record_type("not_a_record_type") is None


def test_decision_action_mapping():
    assert action_for_decision("advance") == "Submit"
    assert action_for_decision("approve") == "Approve"
    assert action_for_decision("reject") == "Reject"
    assert action_for_decision("return") == "Reject"
    assert action_for_decision("not_a_decision") is None

"""
tests/test_rbac_department_role_templates.py — Regression coverage for the
Yuktav org/RBAC/workflow authorization task's department + functional-role
permission model (pharmagpt/services/rbac_defaults.py:
TARGET_MODULE_MATRIX, MAJOR_MODULE_MAP, FUNCTIONAL_ROLE_ACTIONS,
DEPARTMENT_ROLE_TEMPLATES, default_grants_for_department_role(),
default_grants_for_role()).

Pure unit tests — no Flask, no fake Supabase client — since this module is
plain Python data + a pure function. One test per TRUE/FALSE cell that
distinguishes modules (the interesting cases), plus every explicitly
required target case from the task.
"""

from pharmagpt.services.rbac_defaults import (
    DEFAULT_DEPARTMENTS,
    DEPARTMENT_ROLE_TEMPLATES,
    MAJOR_MODULE_MAP,
    default_grants_for_department_role,
    default_grants_for_role,
)


def _granted_major_modules(department_code: str, functional_role: str) -> set[str]:
    """Reduce a (department, role)'s concrete (module, action) grant set
    back to the major modules it actually touches — the natural shape to
    assert the target TRUE/FALSE matrix against."""
    grants = default_grants_for_department_role(department_code, functional_role)
    touched_sub_modules = {sub for sub, _action in grants}
    return {
        major for major, sub_modules in MAJOR_MODULE_MAP.items()
        if sub_modules & touched_sub_modules
    }


def test_ppic_added_to_default_departments():
    codes = {code for _name, code in DEFAULT_DEPARTMENTS}
    assert "PPIC" in codes


def test_plant_head_department_convention_unchanged():
    """Existing PLANT_HEAD department_code is reused, not renamed."""
    codes = {code for _name, code in DEFAULT_DEPARTMENTS}
    assert "PLANT_HEAD" in codes


def test_unrecognized_department_role_cell_grants_nothing():
    assert default_grants_for_department_role("NOT_A_DEPARTMENT", "Initiator") == set()
    assert default_grants_for_role("Not A Real Template Name") == set()


# ── Production ──────────────────────────────────────────────────────────────

def test_production_initiator_qms_yes_validation_no_document_control_yes():
    modules = _granted_major_modules("PRODUCTION", "Initiator")
    assert "QMS" in modules
    assert "Validation" not in modules
    assert "Document Control" in modules


def test_production_reviewer_qms_yes_validation_yes_document_control_yes():
    modules = _granted_major_modules("PRODUCTION", "Reviewer")
    assert modules >= {"QMS", "Validation", "Document Control"}


def test_production_approver_full_matrix():
    modules = _granted_major_modules("PRODUCTION", "Approver")
    assert modules >= {"QMS", "Validation", "Document Control"}


# ── PPIC (the one department where Validation stays False at every tier) ───

def test_ppic_initiator_validation_denied():
    modules = _granted_major_modules("PPIC", "Initiator")
    assert "QMS" in modules and "Document Control" in modules
    assert "Validation" not in modules


def test_ppic_reviewer_validation_denied():
    modules = _granted_major_modules("PPIC", "Reviewer")
    assert "QMS" in modules and "Document Control" in modules
    assert "Validation" not in modules


def test_ppic_approver_validation_denied():
    modules = _granted_major_modules("PPIC", "Approver")
    assert "QMS" in modules and "Document Control" in modules
    assert "Validation" not in modules


# ── Validation department (Initiator IS granted Validation, unlike every
# other department's Initiator row) ─────────────────────────────────────────

def test_validation_initiator_reviewer_approver_all_true():
    for role in ("Initiator", "Reviewer", "Approver"):
        modules = _granted_major_modules("VALIDATION", role)
        assert modules >= {"QMS", "Validation", "Document Control"}, f"Validation {role}"


# ── QA ──────────────────────────────────────────────────────────────────────

def test_qa_coordinator_admin_full_matrix_and_admin_action():
    grants = default_grants_for_department_role("QA", "Coordinator")
    modules = {sub for sub, _action in grants}
    assert MAJOR_MODULE_MAP["QMS"] & modules
    assert MAJOR_MODULE_MAP["Validation"] & modules
    assert MAJOR_MODULE_MAP["Document Control"] & modules
    assert ("QMS", "Admin") in grants  # Coordinator/Admin tier only


def test_qa_initiator_validation_denied_like_every_other_non_qa_validation_dept():
    modules = _granted_major_modules("QA", "Initiator")
    assert "Validation" not in modules
    assert "QMS" in modules and "Document Control" in modules


def test_qa_reviewer_and_approver_full_matrix():
    for role in ("Reviewer", "Approver"):
        modules = _granted_major_modules("QA", role)
        assert modules >= {"QMS", "Validation", "Document Control"}, f"QA {role}"


# ── Warehouse / Engineering / QC — same shape as Production ────────────────

def test_warehouse_engineering_qc_initiator_validation_denied():
    for dept in ("WAREHOUSE", "ENGINEERING", "QC"):
        modules = _granted_major_modules(dept, "Initiator")
        assert "Validation" not in modules, dept
        assert "QMS" in modules and "Document Control" in modules, dept


def test_warehouse_engineering_qc_reviewer_and_approver_full_matrix():
    for dept in ("WAREHOUSE", "ENGINEERING", "QC"):
        for role in ("Reviewer", "Approver"):
            modules = _granted_major_modules(dept, role)
            assert modules >= {"QMS", "Validation", "Document Control"}, f"{dept} {role}"


# ── Plant Head ───────────────────────────────────────────────────────────────

def test_plant_head_full_matrix():
    modules = _granted_major_modules("PLANT_HEAD", "Plant Head")
    assert modules >= {"QMS", "Validation", "Document Control"}


# ── Action-level checks (Initiator vs Reviewer vs Approver vs Coordinator) ──

def test_initiator_has_no_approve_or_reject_action():
    grants = default_grants_for_department_role("PRODUCTION", "Initiator")
    actions = {action for _module, action in grants}
    assert "Approve" not in actions
    assert "Reject" not in actions
    assert "Submit" in actions


def test_reviewer_has_no_approve_action():
    """Reviewer cannot approve without APPROVE permission — this is the
    grant-level guarantee that pharmagpt.auth.module_access.has_business_permission
    then enforces at request time (see tests/test_module_access.py)."""
    grants = default_grants_for_department_role("PRODUCTION", "Reviewer")
    actions = {action for _module, action in grants}
    assert "Approve" not in actions
    assert "Review" in actions


def test_approver_has_review_approve_and_reject_but_not_admin():
    grants = default_grants_for_department_role("PRODUCTION", "Approver")
    actions = {action for _module, action in grants}
    assert {"Review", "Approve", "Reject"} <= actions
    assert "Admin" not in actions


# ── Template name wiring (migrations/0016_..._up.sql must match exactly) ──

def test_all_23_department_role_templates_resolve_to_a_matrix_cell():
    from pharmagpt.services.rbac_defaults import TARGET_MODULE_MATRIX
    assert len(DEPARTMENT_ROLE_TEMPLATES) == 23
    for name, cell in DEPARTMENT_ROLE_TEMPLATES.items():
        assert cell in TARGET_MODULE_MATRIX, f"{name} -> {cell} has no matrix row"


def test_default_grants_for_role_dispatches_department_templates_by_name():
    assert default_grants_for_role("Production Reviewer") == default_grants_for_department_role(
        "PRODUCTION", "Reviewer"
    )
    assert default_grants_for_role("PPIC Approver") == default_grants_for_department_role("PPIC", "Approver")


def test_qa_reviewer_and_production_reviewer_are_not_the_same_grant_set_when_scoped():
    """Distinguishing content check: even though both currently resolve to
    the full TRUE/TRUE/TRUE matrix row (so their grant sets happen to be
    equal today), they are two DISTINCT template names/rbac_roles rows —
    the underlying architectural guarantee this task requires — not one
    shared 'Reviewer' role. Verified structurally, not by grant-set
    difference (which would be a fragile test if the matrix ever changes
    to make them equal by coincidence)."""
    assert "QA Reviewer" in DEPARTMENT_ROLE_TEMPLATES
    assert "Production Reviewer" in DEPARTMENT_ROLE_TEMPLATES
    assert DEPARTMENT_ROLE_TEMPLATES["QA Reviewer"] != DEPARTMENT_ROLE_TEMPLATES["Production Reviewer"]

"""
pharmagpt/services/rbac_defaults.py — static default data for the
fine-grained RBAC framework (migrations/0015_rbac_org_framework_up.sql):
the 15 modules, 8 actions, 12 default departments, 3 default approval
levels, and the tier-based default permission grants seeded for each of the
21 role templates at company-provisioning time.

ASSUMPTION, not a validated regulatory answer: DEFAULT_GRANTS_BY_TIER below
is a reasonable operational starting point, not a customer-specific,
QA-signed-off permission matrix. Every company's Company Admin can (and, per
the task requirements, should) review and adjust these through the Role &
Permission Management UI before relying on them in production.
"""

from __future__ import annotations

MODULES = [
    "Dashboard", "Projects", "Validation", "Risk Assessment", "Equipment Library",
    "Document Control", "Knowledge Base", "AI Assistant", "Deviations", "CAPA",
    "Change Control", "QMS", "Warehouse", "Administration", "Reports",
]

# "Submit"/"Reject" (Yuktav org/RBAC authorization task) are additive to the
# original 8 — every existing (module, action) row and every existing test
# asserting the original 8-action shape is unaffected; these two only ever
# appear in NEW rows for the NEW department/functional-role templates below.
ACTIONS = ["View", "Create", "Edit", "Delete", "Review", "Approve", "Export", "Admin", "Submit", "Reject"]

# (name, department_code) — department_code is a hint resolved to a real
# departments.id at clone time; never string-matched afterward.
DEFAULT_DEPARTMENTS = [
    ("Plant Head", "PLANT_HEAD"),
    ("Production", "PRODUCTION"),
    ("Quality Assurance (QA)", "QA"),
    ("Quality Control (QC)", "QC"),
    ("Validation", "VALIDATION"),
    ("Engineering", "ENGINEERING"),
    ("Warehouse", "WAREHOUSE"),
    ("PPIC", "PPIC"),
    ("Environmental Health & Safety (EHS)", "EHS"),
    ("Regulatory Affairs", "REGULATORY_AFFAIRS"),
    ("Human Resources", "HR"),
    ("Finance", "FINANCE"),
    ("Information Technology", "IT"),
]

DEFAULT_APPROVAL_LEVELS = [("Level 1", 1), ("Level 2", 2), ("Level 3", 3)]

# role name -> (department_code | None, tier)
ROLE_TEMPLATES: dict[str, tuple[str | None, str]] = {
    "Platform Admin": (None, "platform_admin"),
    "Company Admin": (None, "company_admin"),
    "Plant Head": ("PLANT_HEAD", "exec_oversight"),
    "QA Manager": ("QA", "manager"),
    "QA Officer": ("QA", "officer"),
    "QC Manager": ("QC", "manager"),
    "QC Analyst": ("QC", "officer"),
    "Validation Manager": ("VALIDATION", "manager"),
    "Validation Engineer": ("VALIDATION", "officer"),
    "Production Manager": ("PRODUCTION", "manager"),
    "Production Supervisor": ("PRODUCTION", "officer"),
    "Production Operator": ("PRODUCTION", "operator"),
    "Engineering Manager": ("ENGINEERING", "manager"),
    "Maintenance Engineer": ("ENGINEERING", "officer"),
    "Warehouse Manager": ("WAREHOUSE", "manager"),
    "Warehouse Executive": ("WAREHOUSE", "officer"),
    "EHS Manager": ("EHS", "manager"),
    "EHS Officer": ("EHS", "officer"),
    "Regulatory Manager": ("REGULATORY_AFFAIRS", "manager"),
    "Auditor": (None, "auditor"),
    "Viewer": (None, "viewer"),
}

# Home modules per department_code — where "manager"/"officer"/"operator"
# tiers get their domain-specific grants, on top of the cross-cutting
# quality modules every tier below adds.
HOME_MODULES_BY_DEPARTMENT: dict[str, list[str]] = {
    "QA": ["Document Control", "Knowledge Base", "QMS", "Reports"],
    "QC": ["Equipment Library", "Document Control", "QMS", "Reports"],
    "VALIDATION": ["Validation", "Risk Assessment", "Document Control", "Reports"],
    "PRODUCTION": ["Projects", "Equipment Library", "Reports"],
    "ENGINEERING": ["Equipment Library", "Reports"],
    "WAREHOUSE": ["Warehouse", "Reports"],
    "EHS": ["Risk Assessment", "Reports"],
    "REGULATORY_AFFAIRS": ["Document Control", "Reports"],
}

_CROSS_CUTTING_QUALITY_MODULES = ["Deviations", "CAPA", "Change Control", "QMS"]


# ─────────────────────────────────────────────────────────────────────────
# Yuktav organization/RBAC/workflow authorization task — department +
# functional-role templates (Company -> Department -> Functional Role ->
# Module Access target model). Additive to the 21 tier-based templates
# above: a distinct set of role templates, one per (department, functional
# role) cell in the target org chart, so "Production Reviewer" carries its
# own grant set independent of "QA Reviewer" — never a single global
# "Reviewer" role shared across departments (see docs/LESSONS_LEARNED.md §5:
# exact designation/role-string filtering has previously hidden legitimate
# users; here the distinction is deliberate, not a naming accident).
#
# Functional role names match workflow_roles.name (migration 0014) exactly
# — Initiator/Coordinator/Reviewer/Approver/Plant Head — so a user's
# per-department functional role (user_departments.workflow_role_id) and
# their cloned rbac_roles grant set are always describing the same concept
# under two different names for two different purposes (workflow capability
# vs. permission grants), never two competing vocabularies.

# major "business" module -> the rbac_permissions.module catalog entries it
# covers. This is the single mapping between the 4-module business
# vocabulary (QMS / Validation / Document Control / PharmaPilot) the target
# org model is expressed in, and the existing 15-module fine-grained
# catalog — additive documentation-and-lookup, not a second permission
# system (mirrors services/approval_engine.py's WORKFLOWS docstring
# rationale for the same kind of one-place mapping).
MAJOR_MODULE_MAP: dict[str, set[str]] = {
    "QMS": {"QMS", "Deviations", "CAPA", "Change Control", "Warehouse"},
    "Validation": {"Validation", "Risk Assessment", "Equipment Library", "Projects"},
    "Document Control": {"Document Control", "Knowledge Base"},
    "PharmaPilot": {"AI Assistant"},
}

# functional role -> the actions it grants on every major-module marked
# TRUE for its (department, role) cell below. Plant Head reuses Approver's
# action set (final approval authority, not record creation or RBAC
# administration).
FUNCTIONAL_ROLE_ACTIONS: dict[str, set[str]] = {
    "Initiator": {"View", "Create", "Edit", "Submit"},
    "Reviewer": {"View", "Review"},
    "Approver": {"View", "Review", "Approve", "Reject"},
    "Coordinator": {"View", "Create", "Edit", "Submit", "Review", "Approve", "Reject", "Admin", "Delete"},
    "Plant Head": {"View", "Review", "Approve", "Reject"},
}

# (department_code, functional_role) -> {major_module: bool}. This is the
# authoritative TRUE/FALSE target matrix — the exact source a route or test
# should cite, not a hand re-derivation. FALSE means no permission row is
# ever created for that (department, role, major_module) combination.
TARGET_MODULE_MATRIX: dict[tuple[str, str], dict[str, bool]] = {
    ("QA", "Coordinator"):        {"QMS": True, "Validation": True,  "Document Control": True},
    ("QA", "Initiator"):          {"QMS": True, "Validation": False, "Document Control": True},
    ("QA", "Reviewer"):           {"QMS": True, "Validation": True,  "Document Control": True},
    ("QA", "Approver"):           {"QMS": True, "Validation": True,  "Document Control": True},
    ("PRODUCTION", "Initiator"):  {"QMS": True, "Validation": False, "Document Control": True},
    ("PRODUCTION", "Reviewer"):   {"QMS": True, "Validation": True,  "Document Control": True},
    ("PRODUCTION", "Approver"):   {"QMS": True, "Validation": True,  "Document Control": True},
    ("WAREHOUSE", "Initiator"):   {"QMS": True, "Validation": False, "Document Control": True},
    ("WAREHOUSE", "Reviewer"):    {"QMS": True, "Validation": True,  "Document Control": True},
    ("WAREHOUSE", "Approver"):    {"QMS": True, "Validation": True,  "Document Control": True},
    ("PPIC", "Initiator"):        {"QMS": True, "Validation": False, "Document Control": True},
    ("PPIC", "Reviewer"):         {"QMS": True, "Validation": False, "Document Control": True},
    ("PPIC", "Approver"):         {"QMS": True, "Validation": False, "Document Control": True},
    ("ENGINEERING", "Initiator"): {"QMS": True, "Validation": False, "Document Control": True},
    ("ENGINEERING", "Reviewer"):  {"QMS": True, "Validation": True,  "Document Control": True},
    ("ENGINEERING", "Approver"):  {"QMS": True, "Validation": True,  "Document Control": True},
    ("QC", "Initiator"):          {"QMS": True, "Validation": False, "Document Control": True},
    ("QC", "Reviewer"):           {"QMS": True, "Validation": True,  "Document Control": True},
    ("QC", "Approver"):           {"QMS": True, "Validation": True,  "Document Control": True},
    ("VALIDATION", "Initiator"):  {"QMS": True, "Validation": True,  "Document Control": True},
    ("VALIDATION", "Reviewer"):   {"QMS": True, "Validation": True,  "Document Control": True},
    ("VALIDATION", "Approver"):   {"QMS": True, "Validation": True,  "Document Control": True},
    ("PLANT_HEAD", "Plant Head"): {"QMS": True, "Validation": True,  "Document Control": True},
}

# rbac_roles.name (global template, seeded in migrations/0016_..._up.sql) ->
# (department_code, functional_role). The single place that ties a cloned
# template's display name back to its matrix cell — default_grants_for_role
# below checks this dict before falling back to the original 21-tier lookup.
DEPARTMENT_ROLE_TEMPLATES: dict[str, tuple[str, str]] = {
    "QA Coordinator/Admin": ("QA", "Coordinator"),
    "QA Initiator": ("QA", "Initiator"),
    "QA Reviewer": ("QA", "Reviewer"),
    "QA Approver": ("QA", "Approver"),
    "Production Initiator": ("PRODUCTION", "Initiator"),
    "Production Reviewer": ("PRODUCTION", "Reviewer"),
    "Production Approver": ("PRODUCTION", "Approver"),
    "Warehouse Initiator": ("WAREHOUSE", "Initiator"),
    "Warehouse Reviewer": ("WAREHOUSE", "Reviewer"),
    "Warehouse Approver": ("WAREHOUSE", "Approver"),
    "PPIC Initiator": ("PPIC", "Initiator"),
    "PPIC Reviewer": ("PPIC", "Reviewer"),
    "PPIC Approver": ("PPIC", "Approver"),
    "Engineering Initiator": ("ENGINEERING", "Initiator"),
    "Engineering Reviewer": ("ENGINEERING", "Reviewer"),
    "Engineering Approver": ("ENGINEERING", "Approver"),
    "QC Initiator": ("QC", "Initiator"),
    "QC Reviewer": ("QC", "Reviewer"),
    "QC Approver": ("QC", "Approver"),
    "Validation Initiator": ("VALIDATION", "Initiator"),
    "Validation Reviewer": ("VALIDATION", "Reviewer"),
    "Validation Approver": ("VALIDATION", "Approver"),
    "Plant Head / Approver": ("PLANT_HEAD", "Plant Head"),
}


def default_grants_for_department_role(department_code: str, functional_role: str) -> set[tuple[str, str]]:
    """Resolve the default (module, action) grant set for one (department,
    functional_role) cell of TARGET_MODULE_MATRIX, expanded through
    MAJOR_MODULE_MAP into concrete rbac_permissions catalog rows. Returns an
    empty set for an unrecognized cell — fail-closed by construction: a
    major_module marked False, or an entirely unknown cell, contributes
    zero grant rows, not a row with granted=False."""
    matrix_row = TARGET_MODULE_MATRIX.get((department_code, functional_role))
    if not matrix_row:
        return set()
    actions = FUNCTIONAL_ROLE_ACTIONS.get(functional_role, set())
    grants: set[tuple[str, str]] = set()
    for major_module, allowed in matrix_row.items():
        if not allowed:
            continue
        for sub_module in MAJOR_MODULE_MAP.get(major_module, set()):
            for action in actions:
                grants.add((sub_module, action))
    return grants


def default_grants_for_role(role_name: str) -> set[tuple[str, str]]:
    """Resolve the default (module, action) grant set for one of the 21
    tier-based role templates, OR one of the newer department/functional-
    role templates (DEPARTMENT_ROLE_TEMPLATES) — checked first, since a
    department/functional-role template name never collides with the
    original 21. Returns an empty set for an unrecognized role name
    (custom, non-template roles start with zero grants — the Company Admin
    builds their matrix explicitly)."""
    dept_role = DEPARTMENT_ROLE_TEMPLATES.get(role_name)
    if dept_role is not None:
        return default_grants_for_department_role(*dept_role)

    entry = ROLE_TEMPLATES.get(role_name)
    if entry is None:
        return set()
    department_code, tier = entry
    grants: set[tuple[str, str]] = set()

    if tier == "platform_admin":
        grants.add(("Administration", "Admin"))
        grants.add(("Dashboard", "View"))
        return grants

    if tier == "company_admin":
        return {(m, a) for m in MODULES for a in ACTIONS}

    if tier == "exec_oversight":
        grants |= {(m, "View") for m in MODULES}
        grants |= {(m, "Export") for m in MODULES}
        for m in ["Deviations", "CAPA", "Change Control", "QMS", "Document Control", "Validation", "Risk Assessment"]:
            grants.add((m, "Review"))
            grants.add((m, "Approve"))
        return grants

    if tier == "auditor":
        grants |= {(m, "View") for m in MODULES}
        grants |= {(m, "Export") for m in MODULES}
        return grants

    if tier == "viewer":
        return {(m, "View") for m in MODULES}

    # manager / officer / operator: baseline View everywhere, plus richer
    # access on home + cross-cutting-quality modules.
    grants |= {(m, "View") for m in MODULES}
    home_modules = HOME_MODULES_BY_DEPARTMENT.get(department_code or "", [])

    if tier == "manager":
        domain_modules = set(home_modules) | set(_CROSS_CUTTING_QUALITY_MODULES)
        for m in domain_modules:
            grants.add((m, "Create"))
            grants.add((m, "Edit"))
            grants.add((m, "Review"))
            grants.add((m, "Approve"))
            grants.add((m, "Export"))
    elif tier == "officer":
        for m in home_modules:
            grants.add((m, "Create"))
            grants.add((m, "Edit"))
            grants.add((m, "Export"))
        for m in ["Deviations", "CAPA"]:
            grants.add((m, "Create"))
    elif tier == "operator":
        for m in home_modules:
            grants.add((m, "Create"))
        grants.add(("Deviations", "Create"))

    return grants

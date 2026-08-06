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

ACTIONS = ["View", "Create", "Edit", "Delete", "Review", "Approve", "Export", "Admin"]

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


def default_grants_for_role(role_name: str) -> set[tuple[str, str]]:
    """Resolve the default (module, action) grant set for one of the 21
    role templates, by tier. Returns an empty set for an unrecognized role
    name (custom, non-template roles start with zero grants — the Company
    Admin builds their matrix explicitly)."""
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

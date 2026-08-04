"""
pharmagpt/facility_systems/__init__.py — Facility Systems registry for
Greenfield Facility URS generation (Stage 1).

Mirrors pharmagpt/equipment/'s structure exactly (EquipmentProfile ->
EQUIPMENT_REGISTRY -> get_equipment_profile() -> format_profile_for_prompt())
but for facility infrastructure systems (HVAC, BMS, Purified Water, ...)
instead of discrete process/lab equipment. Kept as a separate registry
rather than merged into pharmagpt/equipment/ because a facility system is a
different kind of thing — a building service the URS reasons about at the
design-basis level, not a physical asset qualified via IQ/OQ/PQ. Stage 1
explicitly excludes IQ/OQ/PQ/DQ content (see FACILITY_URS_STAGE1 scope), so
FacilitySystemProfile carries design-basis fields only — no qualification
checklists.

Public API
----------
get_facility_system_profile(name: str) -> FacilitySystemProfile | None
format_facility_system_for_prompt(profile) -> str
FACILITY_SYSTEM_REGISTRY: dict[str, FacilitySystemProfile]
list_facility_system_names() -> list[str]

Adding a new facility system
------------------------------
1. Create or open any file in pharmagpt/facility_systems/profiles/.
2. Instantiate a FacilitySystemProfile and pass it to _register().
3. No other files need to change — the registry is built automatically at import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class FacilitySystemProfile:
    """Design-basis reference data for one facility infrastructure system,
    used to enrich the Facility URS AI prompt (services/facility_requirement_
    library.py and prompts/facility_urs_prompt.py)."""

    name: str
    category: str
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    applicable_regulations: List[str] = field(default_factory=list)
    design_considerations: List[str] = field(default_factory=list)
    critical_parameters: List[str] = field(default_factory=list)
    typical_interfaces: List[str] = field(default_factory=list)
    common_risks: List[str] = field(default_factory=list)


# ─── Registry (populated by profiles sub-package at import) ───────────────────

FACILITY_SYSTEM_REGISTRY: dict[str, FacilitySystemProfile] = {}


def _register(profile: FacilitySystemProfile) -> None:
    FACILITY_SYSTEM_REGISTRY[profile.name.upper()] = profile


def get_facility_system_profile(name: str) -> FacilitySystemProfile | None:
    """Best-matching FacilitySystemProfile for the given system name string —
    same matching strategy as equipment/get_equipment_profile: exact
    canonical match, then alias match, then substring match."""
    if not name:
        return None
    query = name.strip().upper()

    if query in FACILITY_SYSTEM_REGISTRY:
        return FACILITY_SYSTEM_REGISTRY[query]

    for profile in FACILITY_SYSTEM_REGISTRY.values():
        for alias in profile.aliases:
            a = alias.upper()
            if a == query or a in query or query in a:
                return profile

    for canonical, profile in FACILITY_SYSTEM_REGISTRY.items():
        if canonical in query or query in canonical:
            return profile

    return None


def list_facility_system_names() -> list[str]:
    return sorted(p.name for p in FACILITY_SYSTEM_REGISTRY.values())


def list_facility_systems_by_category() -> dict[str, list[str]]:
    by_cat: dict[str, list[str]] = {}
    for profile in FACILITY_SYSTEM_REGISTRY.values():
        by_cat.setdefault(profile.category, []).append(profile.name)
    for names in by_cat.values():
        names.sort()
    return by_cat


_MAX_BULLET_ITEMS = 6  # same rationale as equipment/__init__.py: a longer,
                       # denser block per system combined with several
                       # selected systems in one prompt risks pushing the
                       # model into degenerate repetitive output.


def format_facility_system_for_prompt(profile: FacilitySystemProfile) -> str:
    """Render a FacilitySystemProfile as a structured text block for
    injection into the Facility URS generation prompt."""

    def bullet(items: List[str]) -> str:
        return "\n".join(f"  • {item}" for item in items[:_MAX_BULLET_ITEMS])

    return f"""
─────────────────────────────────────────────────────────────
FACILITY SYSTEM — {profile.name.upper()} ({profile.category})
─────────────────────────────────────────────────────────────
DESCRIPTION:
{profile.description}

APPLICABLE REGULATIONS / STANDARDS:
{bullet(profile.applicable_regulations)}

DESIGN CONSIDERATIONS:
{bullet(profile.design_considerations)}

CRITICAL PARAMETERS:
{bullet(profile.critical_parameters)}

TYPICAL INTERFACES:
{bullet(profile.typical_interfaces)}

COMMON RISKS TO ADDRESS IN REQUIREMENTS:
{bullet(profile.common_risks)}
"""


# ─── Auto-import profiles to populate registry ───────────────────────────────

from pharmagpt.facility_systems import profiles  # noqa: E402, F401

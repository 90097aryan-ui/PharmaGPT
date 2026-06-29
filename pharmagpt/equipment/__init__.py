"""
pharmagpt/equipment/__init__.py — Equipment Intelligence Engine for PharmaGPT v0.9.3.

Public API
----------
get_equipment_profile(equipment_name: str) -> EquipmentProfile | None
format_profile_for_prompt(profile: EquipmentProfile) -> str
EQUIPMENT_REGISTRY: dict[str, EquipmentProfile]

Adding new equipment
--------------------
1. Create or open any file in pharmagpt/equipment/profiles/.
2. Instantiate an EquipmentProfile and append it to the module-level list.
3. No other files need to change — the registry is built automatically at import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class EquipmentProfile:
    """Complete GMP validation intelligence for a single equipment type."""

    name: str
    aliases: List[str]
    description: str
    applicable_regulations: List[str]
    required_utilities: List[str]
    critical_components: List[str]
    iq_checklist: List[str]
    oq_tests: List[str]
    pq_tests: List[str]
    calibration_points: List[str]
    safety_checks: List[str]
    documentation_checklist: List[str]
    standard_acceptance_criteria: List[str]
    common_deviations: List[str]


# ─── Registry (populated by profiles sub-package at import) ───────────────────

EQUIPMENT_REGISTRY: dict[str, EquipmentProfile] = {}


def _register(profile: EquipmentProfile) -> None:
    """Add a profile to the registry under its canonical name (upper-cased)."""
    EQUIPMENT_REGISTRY[profile.name.upper()] = profile


# ─── Loader ──────────────────────────────────────────────────────────────────

def get_equipment_profile(equipment_name: str) -> EquipmentProfile | None:
    """
    Return the best-matching EquipmentProfile for the given equipment name string.

    Matching strategy (first match wins):
    1. Exact canonical name match (case-insensitive).
    2. Any alias contains the query or the query contains the alias.
    3. Any canonical name is a substring of the query.
    """
    if not equipment_name:
        return None

    query = equipment_name.strip().upper()

    # 1. Exact match on canonical name
    if query in EQUIPMENT_REGISTRY:
        return EQUIPMENT_REGISTRY[query]

    # 2. Alias matching
    for profile in EQUIPMENT_REGISTRY.values():
        for alias in profile.aliases:
            a = alias.upper()
            if a == query or a in query or query in a:
                return profile

    # 3. Canonical name as substring
    for canonical, profile in EQUIPMENT_REGISTRY.items():
        if canonical in query or query in canonical:
            return profile

    return None


# ─── Prompt Formatter ─────────────────────────────────────────────────────────

def format_profile_for_prompt(profile: EquipmentProfile) -> str:
    """
    Render an EquipmentProfile as a structured text block to be injected into
    the Gemini prompt before the retrieved document context.
    """

    def bullet(items: List[str]) -> str:
        return "\n".join(f"  • {item}" for item in items)

    return f"""
═══════════════════════════════════════════════════════════════════════
EQUIPMENT INTELLIGENCE PROFILE — {profile.name.upper()}
(Auto-loaded by PharmaGPT Equipment Intelligence Engine v0.9.3)
═══════════════════════════════════════════════════════════════════════

DESCRIPTION:
{profile.description}

APPLICABLE REGULATIONS:
{bullet(profile.applicable_regulations)}

REQUIRED UTILITIES:
{bullet(profile.required_utilities)}

CRITICAL COMPONENTS:
{bullet(profile.critical_components)}

IQ CHECKLIST (Installation Qualification):
{bullet(profile.iq_checklist)}

OQ TESTS (Operational Qualification):
{bullet(profile.oq_tests)}

PQ TESTS (Performance Qualification):
{bullet(profile.pq_tests)}

CALIBRATION POINTS:
{bullet(profile.calibration_points)}

SAFETY CHECKS:
{bullet(profile.safety_checks)}

DOCUMENTATION CHECKLIST:
{bullet(profile.documentation_checklist)}

STANDARD ACCEPTANCE CRITERIA:
{bullet(profile.standard_acceptance_criteria)}

COMMON DEVIATIONS (address proactively in protocols):
{bullet(profile.common_deviations)}

═══════════════════════════════════════════════════════════════════════
Use all profile data above to generate equipment-specific, complete,
and GMP-compliant protocol sections. Do not rely on generic templates.
═══════════════════════════════════════════════════════════════════════
"""


# ─── Auto-import profiles to populate registry ───────────────────────────────

from pharmagpt.equipment import profiles  # noqa: E402, F401  — triggers all profile registrations

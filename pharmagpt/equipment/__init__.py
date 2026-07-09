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

_MAX_BULLET_ITEMS = 6   # cap per category — a longer, denser profile block combined with an
                        # already-long doc-type prompt was found to occasionally push
                        # gemini-2.5-flash into degenerate repetitive output for some
                        # heavily-documented equipment types (e.g. HPLC, tablet presses)


def format_profile_for_prompt(profile: EquipmentProfile, qualification_doc: bool = True) -> str:
    """
    Render an EquipmentProfile as a structured text block to be injected into
    the Gemini prompt before the retrieved document context.

    qualification_doc
        True  — full profile including IQ/OQ/PQ checklists (for IQ/OQ/PQ/DQ/
                FAT/SAT and combined qualification protocols, where those
                checklists are directly relevant).
        False — a lighter profile that omits the IQ/OQ/PQ checklist sections.
                Injecting IQ/OQ/PQ-labelled checklists into the prompt for a
                non-qualification document (SOP, Validation Plan, Validation
                Report) was found to occasionally push gemini-2.5-flash into
                degenerate repetitive output, likely from the thematic
                mismatch between "this is an SOP" and "here are IQ/OQ/PQ test
                checklists" in the same prompt.
    """

    def bullet(items: List[str]) -> str:
        return "\n".join(f"  • {item}" for item in items[:_MAX_BULLET_ITEMS])

    qualification_section = f"""
IQ CHECKLIST (Installation Qualification):
{bullet(profile.iq_checklist)}

OQ TESTS (Operational Qualification):
{bullet(profile.oq_tests)}

PQ TESTS (Performance Qualification):
{bullet(profile.pq_tests)}
""" if qualification_doc else ""

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
{qualification_section}
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
Use the profile data above as reference to make the protocol sections
equipment-specific. Keep to the section structure and length already
specified in the main instructions below.
═══════════════════════════════════════════════════════════════════════
"""


# ─── Auto-import profiles to populate registry ───────────────────────────────

from pharmagpt.equipment import profiles  # noqa: E402, F401  — triggers all profile registrations

"""
prompts/qms_change_control_prompt.py — AI prompt builders for the Change
Control module (Quality Management Suite, Phase 2).

Eight AI features, all optional and routed through the same
services.qms_shared.call_gemini()/parse_json_response() helpers every other
QMS module uses — nothing here is Gemini-specific beyond the prompt text
itself, so a future swap to the Pharma Knowledge Engine only touches
qms_shared.py, not this file or qms_change_control_service.py:

  build_impact_prompt()               — AI Impact Assessment across the standard impact areas (JSON)
  build_implementation_plan_prompt()  — AI Implementation Plan / Checklist steps (JSON)
  build_risk_summary_prompt()         — AI Risk Summary narrative (text)
  build_rollback_plan_prompt()        — AI Rollback Plan narrative (text)
  build_regulatory_impact_prompt()    — AI Regulatory Impact narrative (text)
  build_justification_prompt()        — AI Change Justification narrative (text)
  build_executive_summary_prompt()    — AI Executive Summary narrative (text)
  build_verification_summary_prompt() — AI Verification Summary narrative (text)
  build_effectiveness_review_prompt() — AI Effectiveness Review narrative (text)
"""

from __future__ import annotations


def _cc_context(cc: dict) -> str:
    lines = []
    for label, key in [
        ("Change Control Number", "cc_number"),
        ("Title", "title"),
        ("Change Type", "change_type"),
        ("Change Category", "change_category"),
        ("Department", "department"),
        ("Area", "area"),
        ("Equipment / System", "equipment_system"),
        ("Change Description", "change_description"),
        ("Reason for Change", "reason_for_change"),
        ("Current State", "current_state"),
        ("Proposed State", "proposed_state"),
        ("Risk Level", "risk_level"),
    ]:
        val = cc.get(key, "")
        if val:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


def build_impact_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Quality Assurance Specialist performing an impact assessment for a
pharmaceutical change control per 21 CFR 211.68/211.100, EU GMP Annex 15 §13, and ICH Q10 §3.2.4.

CHANGE CONTROL DETAILS:
{ctx}

Assess the impact across all relevant areas. Return ONLY a valid JSON array (no other text):
[
  {{
    "impact_area": "Validation",
    "impacted": "Yes / No / Potential",
    "extent": "specific description of the extent of impact",
    "action_required": "specific action needed to address this impact, or 'None' if not impacted"
  }}
]

Cover these impact areas where relevant, omitting only those clearly not applicable: Validation,
Qualification, Risk, URS, SOP, Training, Equipment, Documents, Software, Utilities, Regulatory
Compliance, Business Continuity, Electronic Records, Electronic Signatures. Be specific to the
equipment/system and change described above — not generic."""


def build_implementation_plan_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Validation/Engineering Project Lead drafting an implementation plan
(also serving as the implementation checklist) for a pharmaceutical change control per EU GMP
Annex 15 and GAMP 5 change management practice.

CHANGE CONTROL DETAILS:
{ctx}

Return ONLY a valid JSON array (no other text), ordered by step_no:
[
  {{
    "step_no": 1,
    "activity": "specific implementation activity",
    "responsible": "responsible role/department",
    "target_date_offset_days": 7
  }}
]

Generate 6-10 realistic, sequential steps spanning approval through closure (e.g. procurement/
preparation, document updates, training, implementation/installation, verification/testing,
revalidation if applicable, post-implementation review, closure) — specific to the change
described above, not generic boilerplate."""


def build_risk_summary_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Quality Risk Management Specialist preparing a risk summary for a
pharmaceutical change control per ICH Q9 (Quality Risk Management).

CHANGE CONTROL DETAILS:
{ctx}

Write a concise Risk Summary (plain markdown, 150-250 words) covering:
1. Key risks introduced by implementing this change
2. Key risks of NOT implementing this change
3. Overall risk level (Low / Medium / High) with justification

Be specific to the equipment/system and change described above — not generic filler."""


def build_rollback_plan_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Engineering/Validation Specialist drafting a rollback (contingency)
plan for a pharmaceutical change control, in case implementation fails or must be reversed.

CHANGE CONTROL DETAILS:
{ctx}

Write a concise Rollback Plan (plain markdown, 150-250 words) covering:
1. Rollback trigger criteria (what would necessitate reverting the change)
2. Specific steps to restore the prior validated state
3. Who is responsible for the rollback decision and execution

Be specific to the equipment/system and current/proposed state described above — not generic."""


def build_regulatory_impact_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Regulatory Affairs Specialist assessing regulatory notification
requirements for a pharmaceutical change control per 21 CFR 314.70, EU GMP Annex 15, and
Schedule M.

CHANGE CONTROL DETAILS:
{ctx}

Write a concise Regulatory Impact assessment (plain markdown, 120-200 words, using a short table
if helpful) covering which regulatory bodies (USFDA, EMA, CDSCO, other applicable agencies) may
require notification, the likely notification type (e.g. CBE-0/CBE-30/Prior Approval/Variation),
and the basis for that determination. State clearly if no regulatory notification is expected."""


def build_justification_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Quality Consultant expanding the business/technical justification for
a pharmaceutical change control.

CHANGE CONTROL DETAILS:
{ctx}

Write a concise Change Justification (plain markdown, 120-200 words) explaining why this change is
necessary — regulatory drivers, efficiency/safety/quality improvements, equipment lifecycle, or
supplier-driven rationale, as applicable. Reference the specific change described above, not
generic reasoning."""


def build_executive_summary_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Quality Systems Analyst preparing a one-page executive summary of a
pharmaceutical change control for management review.

CHANGE CONTROL DETAILS:
{ctx}

Write a concise Executive Summary (plain markdown, 100-180 words) covering what is changing, why,
the classification/risk level, and the expected outcome. Written for a non-technical management
audience — avoid deep technical jargon."""


def build_verification_summary_prompt(cc: dict, actions: list[dict] | None = None) -> str:
    ctx = _cc_context(cc)
    actions_text = "\n".join(
        f"  - [{a.get('status', '')}] {a.get('activity', '')} (Responsible: {a.get('responsible', '')})"
        for a in (actions or [])
    ) or "  (no implementation steps recorded)"

    return f"""You are a Senior Validation Specialist summarizing post-implementation verification for
a pharmaceutical change control per EU GMP Annex 15 §13.

CHANGE CONTROL DETAILS:
{ctx}

IMPLEMENTATION STEPS:
{actions_text}

Write a concise Verification Summary (plain markdown, 120-200 words) describing how the
implemented change was verified to match the proposed state, what evidence supports that
verification, and whether verification confirms the change was implemented correctly."""


def build_effectiveness_review_prompt(cc: dict) -> str:
    ctx = _cc_context(cc)
    return f"""You are a Senior Quality Assurance Manager conducting an effectiveness review of a
closed-out pharmaceutical change control per ICH Q10.

CHANGE CONTROL DETAILS:
{ctx}

Write a concise Effectiveness Review (plain markdown, 120-200 words) assessing whether the change
achieved its intended outcome, whether any unintended consequences have been observed, and whether
further action (e.g. a follow-up change or CAPA) is recommended."""

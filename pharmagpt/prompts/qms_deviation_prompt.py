"""
prompts/qms_deviation_prompt.py — AI prompt builders for the Deviation Management module.

Three AI features:
  build_investigation_prompt() — AI Investigation Assistant: fishbone, 5-Why, timeline, root cause (JSON)
  build_impact_prompt()        — AI-suggested impact assessment entries (JSON)
  build_capa_suggestion_prompt() — Seed data for a new CAPA raised from this deviation (JSON)
"""

from __future__ import annotations


def _deviation_context(d: dict) -> str:
    lines = []
    for label, key in [
        ("Deviation Number", "deviation_number"),
        ("Title", "title"),
        ("Type", "deviation_type"),
        ("Category", "deviation_category"),
        ("Department", "department"),
        ("Area", "area"),
        ("Product", "product"),
        ("Batch/Lot", "batch_lot"),
        ("Equipment", "equipment"),
        ("Date of Occurrence", "date_of_occurrence"),
        ("Description", "description"),
        ("Immediate Action Taken", "immediate_action"),
    ]:
        val = d.get(key, "")
        if val:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


def build_investigation_prompt(deviation: dict) -> str:
    ctx = _deviation_context(deviation)
    return f"""You are a Senior Pharmaceutical Quality Investigator conducting a root cause investigation
per 21 CFR 211.192, EU GMP Chapter 6, and Schedule M deviation management requirements.

DEVIATION DETAILS:
{ctx}

Perform a thorough investigation using Fishbone (Ishikawa) analysis and 5-Why methodology, and
propose a realistic investigation timeline. Return ONLY valid JSON (no other text):
{{
  "fishbone_data": {{
    "man": ["personnel-related contributing factor", "..."],
    "machine": ["equipment-related contributing factor", "..."],
    "method": ["process/SOP-related contributing factor", "..."],
    "material": ["material/raw-material contributing factor", "..."],
    "measurement": ["measurement/calibration contributing factor", "..."],
    "environment": ["environmental/facility contributing factor", "..."]
  }},
  "five_why_data": [
    {{"question": "Why did [problem] occur?", "answer": "..."}},
    {{"question": "Why did [cause 1] happen?", "answer": "..."}},
    {{"question": "Why did [cause 2] happen?", "answer": "..."}},
    {{"question": "Why did [cause 3] happen?", "answer": "..."}},
    {{"question": "Why did [cause 4] happen?", "answer": "..."}}
  ],
  "timeline_data": [
    {{"datetime": "relative or example timestamp", "event": "event description"}}
  ],
  "root_cause_category": "Human Error / Equipment Failure / Process Issue / Material / Environmental / System / Other",
  "root_cause_statement": "specific, factual root cause statement tied to the evidence above"
}}

Each fishbone category should have 1-3 specific, plausible contributing factors (empty array if clearly
not applicable). The 5-Why chain must logically progress from the stated problem to the root cause.
Generate 5-8 timeline events spanning discovery through containment. Be specific to the equipment,
product, and department named above — not generic."""


def build_impact_prompt(deviation: dict, investigation: dict | None = None) -> str:
    ctx = _deviation_context(deviation)
    rc = ""
    if investigation and investigation.get("root_cause_statement"):
        rc = f"\nROOT CAUSE: {investigation['root_cause_statement']}"

    return f"""You are a Senior Quality Assurance Specialist performing an impact assessment for a
pharmaceutical deviation per ICH Q9 and EU GMP Chapter 6.

DEVIATION DETAILS:
{ctx}{rc}

Assess the impact across all relevant areas. Return ONLY a valid JSON array (no other text):
[
  {{
    "impact_area": "Product Quality",
    "assessment_text": "specific assessment of impact on product quality attributes",
    "risk_level": "Low / Medium / High / Critical",
    "batches_affected": "batch/lot numbers or 'None identified'"
  }}
]

Cover these impact areas where relevant to the deviation: Product Quality, Patient Safety,
Regulatory Compliance, Batch Disposition. Omit areas that are clearly not applicable. Be specific
and evidence-based, not generic."""


def build_capa_suggestion_prompt(deviation: dict, investigation: dict | None = None) -> str:
    ctx = _deviation_context(deviation)
    rc = ""
    if investigation and investigation.get("root_cause_statement"):
        rc = f"\nROOT CAUSE: {investigation['root_cause_statement']} (Category: {investigation.get('root_cause_category', '')})"

    return f"""You are a Senior Pharmaceutical Quality Consultant drafting CAPA seed content for a
deviation, per 21 CFR 820.100, EU GMP Chapter 8, and ICH Q10.

DEVIATION DETAILS:
{ctx}{rc}

Return ONLY valid JSON (no other text):
{{
  "problem_statement": "concise problem statement suitable for a CAPA record",
  "root_cause": "root cause statement carried into the CAPA",
  "corrective_actions": [
    {{"description": "specific corrective action addressing the root cause", "owner": "responsible role", "due_date_offset_days": 30}}
  ],
  "preventive_actions": [
    {{"description": "specific preventive action to avoid recurrence", "owner": "responsible role", "due_date_offset_days": 60}}
  ]
}}

Generate 2-4 corrective actions and 1-3 preventive actions, each specific and actionable with a
named responsible role — not generic statements."""

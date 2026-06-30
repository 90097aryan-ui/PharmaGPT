"""
prompts/risk_prompt.py — AI prompt builders for the Risk Management Suite.

Each function returns a complete prompt string ready to send to Gemini.
"""

from __future__ import annotations


# ── Context builder ───────────────────────────────────────────────────────────

def _assessment_context(info: dict) -> str:
    lines = []
    for label, key in [
        ("Assessment Title", "title"),
        ("Assessment Type", "assessment_type"),
        ("Sub-type", "assessment_subtype"),
        ("Methodology", "methodology"),
        ("Department", "department"),
        ("Area / Zone", "area"),
        ("Equipment", "equipment"),
        ("Product", "product"),
        ("Process", "process"),
        ("Protocol Reference", "protocol_reference"),
        ("Reason for Assessment", "reason_for_assessment"),
    ]:
        val = info.get(key, "")
        if val:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


# ── FMEA generation ───────────────────────────────────────────────────────────

def build_fmea_prompt(info: dict, library_context: str = "") -> str:
    ctx = _assessment_context(info)
    lib_section = ""
    if library_context:
        lib_section = f"""
RISK LIBRARY CONTEXT (reference previous knowledge — do not copy verbatim):
{library_context}
"""
    return f"""You are a Senior Pharmaceutical Quality Risk Management Expert with 25+ years of experience
in ICH Q9, GAMP 5, EU GMP Annex 15, ASTM E2500, and 21 CFR validation.

ASSESSMENT INFORMATION:
{ctx}

{lib_section}
Generate a comprehensive FMEA (Failure Mode and Effects Analysis) risk assessment.

STRICT OUTPUT FORMAT — Return ONLY a valid JSON array, no other text:
[
  {{
    "process_step": "step name",
    "failure_mode": "specific failure mode",
    "failure_effect": "effect on patient safety / product quality / process",
    "severity": 7,
    "potential_cause": "root cause or contributing factor",
    "occurrence": 4,
    "current_controls": "existing control measures",
    "detection": 5,
    "rpn": 140,
    "recommended_action": "specific corrective / preventive action",
    "action_owner": "responsible role",
    "residual_risk": "Low / Medium / High after action",
    "residual_severity": 7,
    "residual_occurrence": 2,
    "residual_detection": 3,
    "residual_rpn": 42,
    "status": "Open"
  }}
]

SCORING RULES:
- Severity (1-10): 1=No effect, 10=Patient safety critical
- Occurrence (1-10): 1=Remote, 10=Certain
- Detection (1-10): 1=Almost certain detect, 10=Undetectable
- RPN = Severity × Occurrence × Detection
- Generate 8-15 meaningful rows covering all major process steps
- Align with ICH Q9 and the selected process / equipment context
- Classify by severity: critical (≥200 RPN), major (100-199), minor (<100)
- Recommend GMP-compliant actions referencing SOPs, qualification protocols, training
"""


# ── HACCP generation ──────────────────────────────────────────────────────────

def build_haccp_prompt(info: dict) -> str:
    ctx = _assessment_context(info)
    return f"""You are a Senior Pharmaceutical HACCP and Quality Risk Expert with expertise in
WHO-GMP, EU GMP, and Codex Alimentarius HACCP principles applied to pharmaceutical manufacturing.

ASSESSMENT INFORMATION:
{ctx}

Generate a comprehensive HACCP study for this pharmaceutical process.

STRICT OUTPUT FORMAT — Return ONLY a valid JSON array, no other text:
[
  {{
    "process_step": "process step name",
    "hazard": "identified hazard description",
    "hazard_category": "Biological / Chemical / Physical / Cross-contamination",
    "preventive_measure": "preventive control measure",
    "is_ccp": true,
    "critical_limit": "measurable critical limit (e.g. temp ≥121°C for ≥15 min)",
    "monitoring": "monitoring method, frequency, and responsible person",
    "corrective_action": "corrective action if deviation occurs",
    "verification": "verification activity (e.g. calibration, audit, review)",
    "records": "document / record to be maintained",
    "status": "Open"
  }}
]

GUIDELINES:
- Apply all 7 HACCP principles (Hazard Analysis, CCP Identification, Critical Limits,
  Monitoring, Corrective Actions, Verification, Record Keeping)
- Cover biological, chemical, and physical hazards relevant to pharma manufacturing
- Mark true CCPs (is_ccp: true) only where control is essential for safety
- Critical limits must be measurable and science-based
- Generate 8-12 process steps covering the complete manufacturing sequence
- Reference applicable regulations: 21 CFR Part 110/211, WHO TRS 986, EU GMP
"""


# ── Risk Matrix generation ────────────────────────────────────────────────────

def build_risk_matrix_prompt(info: dict) -> str:
    ctx = _assessment_context(info)
    return f"""You are a Senior Quality Risk Management Consultant specialising in pharmaceutical
risk matrices per ICH Q9 and ISO 14971.

ASSESSMENT INFORMATION:
{ctx}

Generate a Risk Matrix assessment covering all significant risk scenarios.

STRICT OUTPUT FORMAT — Return ONLY a valid JSON array, no other text:
[
  {{
    "process_step": "activity / scenario description",
    "failure_mode": "risk scenario or failure",
    "probability": "Rare / Unlikely / Possible / Likely / Almost Certain",
    "impact": "Negligible / Minor / Moderate / Major / Catastrophic",
    "risk_rating": "Low / Medium / High / Critical",
    "risk_acceptance": "Acceptable / ALARP / Unacceptable",
    "current_controls": "existing controls",
    "recommended_action": "mitigation action",
    "action_owner": "responsible role",
    "residual_risk": "Low / Medium / High after mitigation",
    "status": "Open"
  }}
]

PROBABILITY SCALE: Rare(1), Unlikely(2), Possible(3), Likely(4), Almost Certain(5)
IMPACT SCALE: Negligible(1), Minor(2), Moderate(3), Major(4), Catastrophic(5)
RISK RATING MATRIX:
  Score 1-4  → Low
  Score 5-9  → Medium
  Score 10-14 → High
  Score 15-25 → Critical

Generate 8-12 risk scenarios relevant to the process and regulatory context.
"""


# ── HAZOP generation ──────────────────────────────────────────────────────────

def build_hazop_prompt(info: dict) -> str:
    ctx = _assessment_context(info)
    return f"""You are a Senior Process Hazard Analysis Expert applying HAZOP methodology
to pharmaceutical manufacturing per IEC 61882 and GAMP 5 Second Edition.

ASSESSMENT INFORMATION:
{ctx}

Generate a HAZOP (Hazard and Operability Study) analysis.

STRICT OUTPUT FORMAT — Return ONLY a valid JSON array, no other text:
[
  {{
    "process_step": "process node / pipe section / equipment",
    "failure_mode": "deviation (guide word + parameter, e.g. No Flow, High Pressure)",
    "failure_effect": "consequence of deviation",
    "potential_cause": "cause of deviation",
    "current_controls": "safeguards / protection layers",
    "severity": 7,
    "occurrence": 3,
    "detection": 4,
    "rpn": 84,
    "recommended_action": "recommended safeguard or action",
    "action_owner": "responsible role",
    "residual_risk": "Low / Medium / High",
    "status": "Open"
  }}
]

HAZOP GUIDE WORDS: No/None, More, Less, As Well As, Part Of, Reverse, Other Than, Early, Late, Before, After
Apply systematically to parameters: Flow, Temperature, Pressure, Level, Composition, Time, Phase, Speed
Generate 10-14 deviations covering critical process nodes.
"""


# ── What-If / PHA generation ──────────────────────────────────────────────────

def build_what_if_prompt(info: dict) -> str:
    ctx = _assessment_context(info)
    return f"""You are a Senior Pharmaceutical Risk Analyst applying What-If Analysis and
Preliminary Hazard Analysis (PHA) methodology per GAMP 5 and ICH Q9.

ASSESSMENT INFORMATION:
{ctx}

Generate a What-If Analysis / PHA for this activity.

STRICT OUTPUT FORMAT — Return ONLY a valid JSON array, no other text:
[
  {{
    "process_step": "activity / scenario",
    "failure_mode": "What if...? scenario",
    "failure_effect": "potential consequence",
    "potential_cause": "initiating cause",
    "current_controls": "existing safeguards",
    "probability": "Low / Medium / High",
    "impact": "Low / Medium / High / Critical",
    "risk_rating": "Low / Medium / High / Critical",
    "recommended_action": "recommended action",
    "action_owner": "responsible role",
    "residual_risk": "Low / Medium / High",
    "status": "Open"
  }}
]

Generate 8-12 What-If scenarios covering safety, quality, compliance, and operational risks.
"""


# ── FTA generation ────────────────────────────────────────────────────────────

def build_fta_prompt(info: dict) -> str:
    ctx = _assessment_context(info)
    return f"""You are a Senior Reliability Engineer applying Fault Tree Analysis (FTA) methodology
to pharmaceutical systems per IEC 61025 and GAMP 5.

ASSESSMENT INFORMATION:
{ctx}

Generate a Fault Tree Analysis identifying top-level failure events and their contributing causes.

STRICT OUTPUT FORMAT — Return ONLY a valid JSON array, no other text:
[
  {{
    "process_step": "top event / sub-system",
    "failure_mode": "failure event (top event or basic event)",
    "failure_effect": "consequence if top event occurs",
    "potential_cause": "contributing basic events / root causes",
    "current_controls": "barriers / safeguards preventing the top event",
    "severity": 8,
    "occurrence": 3,
    "detection": 4,
    "rpn": 96,
    "recommended_action": "recommended additional barrier or control",
    "action_owner": "responsible role",
    "residual_risk": "Low / Medium / High",
    "status": "Open"
  }}
]

Structure from top event downward through AND/OR gates to basic events.
Generate 8-12 entries covering the primary failure tree.
"""


# ── Custom / Generic risk generation ─────────────────────────────────────────

def build_custom_prompt(info: dict) -> str:
    ctx = _assessment_context(info)
    return f"""You are a Senior Pharmaceutical Quality Risk Management Expert.

ASSESSMENT INFORMATION:
{ctx}

Generate a comprehensive custom risk assessment appropriate for this activity.
Select the most suitable risk format based on the context provided.

STRICT OUTPUT FORMAT — Return ONLY a valid JSON array, no other text:
[
  {{
    "process_step": "activity / step",
    "failure_mode": "risk / failure scenario",
    "failure_effect": "impact / consequence",
    "potential_cause": "root cause",
    "current_controls": "existing controls",
    "severity": 6,
    "occurrence": 4,
    "detection": 5,
    "rpn": 120,
    "recommended_action": "mitigation action",
    "action_owner": "responsible role",
    "residual_risk": "Low / Medium / High",
    "status": "Open"
  }}
]

Generate 8-12 risks covering all major aspects of the activity.
Align recommendations with ICH Q9, EU GMP, and WHO-GMP principles.
"""


# ── AI Review prompt ──────────────────────────────────────────────────────────

def build_review_prompt(assessment: dict, items: list[dict]) -> str:
    ctx = _assessment_context(assessment)
    methodology = assessment.get("methodology", "FMEA")

    items_summary = []
    for i, item in enumerate(items[:20], 1):  # Limit context size
        row = f"  {i}. {item.get('failure_mode') or item.get('hazard', 'N/A')}"
        if item.get("rpn"):
            row += f" | RPN={item['rpn']}"
        if item.get("risk_rating"):
            row += f" | Rating={item['risk_rating']}"
        row += f" | Action: {item.get('recommended_action', 'None')[:80]}"
        items_summary.append(row)

    items_text = "\n".join(items_summary) if items_summary else "  No items recorded yet."

    return f"""You are a Senior GMP Auditor and Quality Risk Management Expert reviewing a
pharmaceutical risk assessment for regulatory compliance.

ASSESSMENT DETAILS:
{ctx}

METHODOLOGY: {methodology}
RISK ITEMS ({len(items)} total):
{items_text}

Perform a thorough AI review and return ONLY valid JSON (no other text):
{{
  "completeness_score": 85,
  "regulatory_compliance_score": 78,
  "consistency_score": 82,
  "overall_score": 82,
  "critical_findings": [
    "finding 1",
    "finding 2"
  ],
  "missing_risks": [
    "risk scenario that should be included",
    "another missing scenario"
  ],
  "suggested_improvements": [
    "specific improvement suggestion",
    "another improvement"
  ],
  "reviewer_comments": "Overall narrative review comment from AI reviewer perspective",
  "final_summary": "Executive summary of the assessment quality and readiness for approval",
  "recommendation": "Approve / Revise / Reject"
}}

SCORING CRITERIA (0-100):
- Completeness: All relevant risks identified, all fields populated
- Regulatory Compliance: Alignment with ICH Q9, EU GMP, GAMP 5, WHO-GMP
- Consistency: RPN calculations correct, risk ratings logical, controls adequate
- Provide concrete, actionable findings and improvements
"""


# ── Mitigation suggestion prompt ──────────────────────────────────────────────

def build_mitigation_prompt(item: dict, methodology: str, context: str = "") -> str:
    return f"""You are a Senior Pharmaceutical GMP Consultant.

RISK ITEM:
  Failure Mode / Hazard: {item.get('failure_mode') or item.get('hazard', '')}
  Effect: {item.get('failure_effect', '')}
  Cause: {item.get('potential_cause', '')}
  Current Controls: {item.get('current_controls') or item.get('preventive_measure', '')}
  Severity: {item.get('severity', '')}   Occurrence: {item.get('occurrence', '')}   Detection: {item.get('detection', '')}
  Methodology: {methodology}
{f"  Context: {context}" if context else ""}

Suggest 3 specific, GMP-compliant mitigation actions for this risk.
Return ONLY valid JSON array, no other text:
[
  {{
    "action": "specific action description referencing applicable SOP or protocol",
    "owner": "responsible role / department",
    "expected_benefit": "how this reduces severity, occurrence, or detection",
    "regulatory_basis": "ICH Q9 / EU GMP / 21 CFR reference"
  }}
]
"""


# ── Dispatch function ─────────────────────────────────────────────────────────

def get_generation_prompt(methodology: str, info: dict, library_context: str = "") -> str:
    """Return the correct prompt function based on methodology."""
    m = methodology.upper()
    if m == "FMEA":
        return build_fmea_prompt(info, library_context)
    elif m == "HACCP":
        return build_haccp_prompt(info)
    elif m in ("RISK MATRIX", "RISK_MATRIX"):
        return build_risk_matrix_prompt(info)
    elif m == "HAZOP":
        return build_hazop_prompt(info)
    elif m in ("WHAT-IF", "WHAT IF", "PHA"):
        return build_what_if_prompt(info)
    elif m == "FTA":
        return build_fta_prompt(info)
    else:
        return build_custom_prompt(info)

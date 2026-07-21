"""
services/risk_service.py — Business logic for the Risk Management Suite.

Handles AI-powered risk generation, review, and report building.
Uses Gemini (same client as the rest of the app).
"""

from __future__ import annotations
import json
import re

from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from pharmagpt import risk_database as rdb
from pharmagpt.prompts import risk_prompt as rp

from google.genai import types


# ── AI generation ──────────────────────────────────────────────────────────────

def generate_risk_items(info: dict, company_id: str) -> list[dict]:
    """Call Gemini to generate risk items for the given assessment info.
    `company_id` must come from the authenticated TenantContext, never from
    client input (pharmagpt/tenancy.py)."""
    methodology = info.get("methodology", "FMEA")

    # Pull relevant library entries as context
    category = rdb._type_to_category(info.get("assessment_type", ""))
    library_entries = rdb.get_library(company_id, category=category, keyword=info.get("equipment", ""))
    lib_context = _format_library_context(library_entries[:5])

    prompt = rp.get_generation_prompt(methodology, info, lib_context)

    response_text = _call_gemini(prompt, temperature=0.4)
    return _parse_json_response(response_text, default=[])


def ai_review_assessment(assessment_id: int) -> dict:
    """Run AI review on a complete assessment. Returns review data dict."""
    assessment = rdb.get_assessment(assessment_id)
    if not assessment:
        return {"error": "Assessment not found"}

    items = rdb.get_items(assessment_id)
    prompt = rp.build_review_prompt(assessment, items)

    response_text = _call_gemini(prompt, temperature=0.2)
    review_data = _parse_json_response(response_text, default={
        "completeness_score": 0,
        "regulatory_compliance_score": 0,
        "consistency_score": 0,
        "overall_score": 0,
        "critical_findings": ["AI review could not parse response"],
        "missing_risks": [],
        "suggested_improvements": [],
        "reviewer_comments": response_text[:500],
        "final_summary": "Review completed with parsing issues.",
        "recommendation": "Revise",
    })

    # Persist review data in assessment record
    rdb.update_assessment(assessment_id, {"ai_review_data": review_data})
    return review_data


def suggest_mitigations(item_data: dict, methodology: str, assessment_info: dict = None) -> list[dict]:
    """Suggest mitigation actions for a single risk item."""
    context = ""
    if assessment_info:
        context = f"{assessment_info.get('equipment', '')} - {assessment_info.get('process', '')}"
    prompt = rp.build_mitigation_prompt(item_data, methodology, context)
    response_text = _call_gemini(prompt, temperature=0.3)
    return _parse_json_response(response_text, default=[])


def generate_report_markdown(assessment_id: int, report_type: str = "full") -> str:
    """Generate a markdown report for an assessment."""
    assessment = rdb.get_assessment(assessment_id)
    if not assessment:
        return "# Error: Assessment not found"

    items = rdb.get_items(assessment_id)
    actions = rdb.get_actions(assessment_id)
    approval = rdb.get_approval_trail(assessment_id)
    ai_review = assessment.get("ai_review_data", {})

    md = []
    md.append(f"# Risk Assessment Report")
    md.append(f"## {assessment.get('title', 'Untitled')}")
    md.append("")

    # Header block
    md.append("---")
    md.append("| Field | Value |")
    md.append("|-------|-------|")
    for label, key in [
        ("Assessment Type", "assessment_type"), ("Sub-type", "assessment_subtype"),
        ("Methodology", "methodology"), ("Department", "department"),
        ("Area / Zone", "area"), ("Equipment", "equipment"),
        ("Product", "product"), ("Process", "process"),
        ("Protocol Reference", "protocol_reference"),
        ("Change Control Ref.", "change_control_reference"),
        ("Assessment Owner", "assessment_owner"), ("Reviewer", "reviewer"),
        ("Approver", "approver"), ("Date", "assessment_date"),
        ("Revision", "revision"), ("Status", "status"), ("Priority", "priority"),
    ]:
        val = assessment.get(key, "")
        if val:
            md.append(f"| **{label}** | {val} |")
    md.append("")

    # Reason
    reason = assessment.get("reason_for_assessment", "")
    if reason:
        md.append("## 1. Reason for Assessment")
        md.append(reason)
        md.append("")

    # Risk Items Table
    md.append(f"## 2. Risk Assessment ({assessment.get('methodology', 'FMEA')})")
    md.append("")

    methodology = assessment.get("methodology", "FMEA").upper()
    if methodology == "FMEA":
        md.append(_fmea_table_md(items))
    elif methodology == "HACCP":
        md.append(_haccp_table_md(items))
    else:
        md.append(_matrix_table_md(items))
    md.append("")

    # Risk Summary
    md.append("## 3. Risk Summary")
    rpn_values = [i.get("rpn") for i in items if i.get("rpn")]
    if rpn_values:
        high_rpn = [r for r in rpn_values if r >= 100]
        md.append(f"- **Total Risk Items:** {len(items)}")
        md.append(f"- **High RPN (≥100):** {len(high_rpn)}")
        md.append(f"- **Maximum RPN:** {max(rpn_values)}")
        md.append(f"- **Average RPN:** {sum(rpn_values) // len(rpn_values)}")
    md.append("")

    # Mitigation Actions
    if actions:
        md.append("## 4. Mitigation Actions")
        md.append("| # | Action | Owner | Due Date | Status |")
        md.append("|---|--------|-------|----------|--------|")
        for i, a in enumerate(actions, 1):
            md.append(f"| {i} | {a.get('action_description', '')} | {a.get('action_owner', '')} | {a.get('due_date', '')} | {a.get('status', '')} |")
        md.append("")

    # AI Review Section
    if ai_review and ai_review.get("overall_score"):
        md.append("## 5. AI Quality Review")
        md.append("")
        md.append(f"| Score Category | Result |")
        md.append(f"|----------------|--------|")
        md.append(f"| Completeness | {ai_review.get('completeness_score', 'N/A')}/100 |")
        md.append(f"| Regulatory Compliance | {ai_review.get('regulatory_compliance_score', 'N/A')}/100 |")
        md.append(f"| Consistency | {ai_review.get('consistency_score', 'N/A')}/100 |")
        md.append(f"| **Overall Score** | **{ai_review.get('overall_score', 'N/A')}/100** |")
        md.append(f"| Recommendation | {ai_review.get('recommendation', 'N/A')} |")
        md.append("")
        if ai_review.get("reviewer_comments"):
            md.append("**AI Reviewer Comments:**")
            md.append(ai_review["reviewer_comments"])
            md.append("")
        if ai_review.get("final_summary"):
            md.append("**Final Summary:**")
            md.append(ai_review["final_summary"])
            md.append("")

    # Approval Trail
    if approval:
        md.append("## 6. Review & Approval Trail")
        md.append("| # | Action | Performed By | Role | Comments | Timestamp |")
        md.append("|---|--------|-------------|------|----------|-----------|")
        for i, a in enumerate(approval, 1):
            md.append(f"| {i} | {a.get('action', '')} | {a.get('performed_by', '')} | {a.get('role', '')} | {a.get('comments', '')} | {a.get('timestamp', '')} |")
        md.append("")

    # Regulatory References
    md.append("## 7. Regulatory References")
    md.append("- ICH Q9 — Quality Risk Management")
    md.append("- ICH Q10 — Pharmaceutical Quality System")
    md.append("- EU GMP Annex 15 — Qualification and Validation")
    md.append("- GAMP 5 Second Edition — A Risk-Based Approach to GxP Computerized Systems")
    md.append("- WHO Technical Report Series — Good Manufacturing Practices")
    md.append("- 21 CFR Part 211 — Current Good Manufacturing Practice")
    md.append("- ISO 14971 — Application of Risk Management to Medical Devices")
    md.append("")

    md.append("---")
    md.append("*Generated by PharmaGPT Risk Management Suite — The Lean Architect Technologies*")

    return "\n".join(md)


# ── Private helpers ────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, temperature: float = 0.3) -> str:
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=PHARMA_SYSTEM_PROMPT,
                temperature=temperature,
            ),
        )
        return response.text or ""
    except Exception as e:
        return f"[]"  # Return empty JSON on error


def _parse_json_response(text: str, default=None):
    """Extract and parse the first JSON array or object from the response."""
    if default is None:
        default = []
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    text = text.rstrip("`").strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to extract first [...] or {...}
    for pattern in (r'\[[\s\S]*\]', r'\{[\s\S]*\}'):
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
    return default


def _format_library_context(entries: list[dict]) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        fm = e.get("failure_mode") or e.get("hazard", "")
        if fm:
            lines.append(f"- {fm}: {e.get('failure_effect', '')} (RPN: {e.get('typical_rpn', 'N/A')})")
    return "\n".join(lines)


def _fmea_table_md(items: list[dict]) -> str:
    if not items:
        return "_No risk items recorded._"
    lines = []
    lines.append("| # | Process Step | Failure Mode | Effect | Sev | Cause | Occ | Controls | Det | RPN | Action | Owner | Residual Risk |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, item in enumerate(items, 1):
        lines.append(
            f"| {i} | {item.get('process_step','')} | {item.get('failure_mode','')} | "
            f"{item.get('failure_effect','')} | {item.get('severity','')} | "
            f"{item.get('potential_cause','')} | {item.get('occurrence','')} | "
            f"{item.get('current_controls','')} | {item.get('detection','')} | "
            f"**{item.get('rpn','')}** | {item.get('recommended_action','')} | "
            f"{item.get('action_owner','')} | {item.get('residual_risk','')} |"
        )
    return "\n".join(lines)


def _haccp_table_md(items: list[dict]) -> str:
    if not items:
        return "_No hazard items recorded._"
    lines = []
    lines.append("| # | Process Step | Hazard | Category | Preventive Measure | CCP | Critical Limit | Monitoring | Corrective Action | Verification |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, item in enumerate(items, 1):
        ccp = "Yes" if item.get("is_ccp") else "No"
        lines.append(
            f"| {i} | {item.get('process_step','')} | {item.get('hazard','')} | "
            f"{item.get('hazard_category','')} | {item.get('preventive_measure','')} | "
            f"{ccp} | {item.get('critical_limit','')} | {item.get('monitoring','')} | "
            f"{item.get('corrective_action','')} | {item.get('verification','')} |"
        )
    return "\n".join(lines)


def _matrix_table_md(items: list[dict]) -> str:
    if not items:
        return "_No risk items recorded._"
    lines = []
    lines.append("| # | Scenario | Probability | Impact | Risk Rating | Acceptance | Controls | Action | Residual Risk |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, item in enumerate(items, 1):
        lines.append(
            f"| {i} | {item.get('failure_mode') or item.get('process_step','')} | "
            f"{item.get('probability','')} | {item.get('impact','')} | "
            f"**{item.get('risk_rating','')}** | {item.get('risk_acceptance','')} | "
            f"{item.get('current_controls','')} | {item.get('recommended_action','')} | "
            f"{item.get('residual_risk','')} |"
        )
    return "\n".join(lines)

"""
services/qms_change_control_service.py — Business logic for the Change
Control module (Quality Management Suite, Phase 2).

All AI features are optional and go through services.qms_shared.call_gemini()
(shared with every other QMS module) rather than calling Gemini directly —
this is the seam that lets a future Pharma Knowledge Engine replace Gemini
without touching this file or routes/qms_change_control.py.

Narrative-style AI outputs (risk summary, rollback plan, regulatory impact,
justification, executive summary, verification summary, effectiveness review)
are persisted into qms_change_controls.ai_narratives via
qms_change_control_database.set_narrative() so they survive a page reload
without re-calling the AI. Suggestion-style outputs (impact assessment
entries, implementation plan steps) are returned for the caller to review and
individually accept into the real qms_change_control_impact /
qms_change_control_actions tables — same pattern as
qms_deviation_service.ai_suggest_impact()/ai_suggest_capa().
"""

from __future__ import annotations

from pharmagpt import qms_change_control_database as ccdb
from pharmagpt import qms_database as qmsdb
from pharmagpt.prompts import qms_change_control_prompt as ccp
from pharmagpt.services.qms_shared import call_gemini, parse_json_response


def ai_suggest_impact(cc_id: int) -> list[dict]:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return []
    prompt = ccp.build_impact_prompt(cc)
    response_text = call_gemini(prompt, temperature=0.3)
    return parse_json_response(response_text, default=[])


def ai_suggest_implementation_plan(cc_id: int) -> list[dict]:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return []
    prompt = ccp.build_implementation_plan_prompt(cc)
    response_text = call_gemini(prompt, temperature=0.3)
    return parse_json_response(response_text, default=[])


def _ai_narrative(cc_id: int, key: str, prompt: str) -> str:
    text = call_gemini(prompt, temperature=0.3) or "AI narrative unavailable."
    ccdb.set_narrative(cc_id, key, text)
    return text


def ai_risk_summary(cc_id: int) -> str:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return ""
    return _ai_narrative(cc_id, "risk_summary", ccp.build_risk_summary_prompt(cc))


def ai_rollback_plan(cc_id: int) -> str:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return ""
    return _ai_narrative(cc_id, "rollback_plan", ccp.build_rollback_plan_prompt(cc))


def ai_regulatory_impact(cc_id: int) -> str:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return ""
    return _ai_narrative(cc_id, "regulatory_impact", ccp.build_regulatory_impact_prompt(cc))


def ai_justification(cc_id: int) -> str:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return ""
    return _ai_narrative(cc_id, "justification", ccp.build_justification_prompt(cc))


def ai_executive_summary(cc_id: int) -> str:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return ""
    return _ai_narrative(cc_id, "executive_summary", ccp.build_executive_summary_prompt(cc))


def ai_verification_summary(cc_id: int) -> str:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return ""
    actions = ccdb.get_actions(cc_id)
    return _ai_narrative(cc_id, "verification_summary", ccp.build_verification_summary_prompt(cc, actions))


def ai_effectiveness_review(cc_id: int) -> str:
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return ""
    return _ai_narrative(cc_id, "effectiveness_review", ccp.build_effectiveness_review_prompt(cc))


def generate_report_markdown(cc_id: int) -> str:
    """Generate a markdown report for a change control — used by in-app preview/print and DOCX export."""
    cc = ccdb.get_change_control(cc_id)
    if not cc:
        return "# Error: Change Control not found"

    impacts = ccdb.get_impacts(cc_id)
    actions = ccdb.get_actions(cc_id)
    linked_deviations = ccdb.get_linked_records(cc_id, "deviation")
    linked_capas = ccdb.get_linked_records(cc_id, "capa")
    approvals = qmsdb.get_approval_trail("change_control", cc_id)
    narratives = cc.get("ai_narratives", {})

    md = []
    md.append("# Change Control Report")
    md.append(f"## {cc.get('title', 'Untitled Change')}")
    md.append("")

    md.append("---")
    md.append("| Field | Value |")
    md.append("|-------|-------|")
    for label, key in [
        ("CC Number", "cc_number"), ("Type", "change_type"), ("Category", "change_category"),
        ("Department", "department"), ("Area", "area"), ("Equipment/System", "equipment_system"),
        ("Requested By", "requested_by"), ("Date Requested", "date_requested"),
        ("Target Implementation Date", "target_implementation_date"), ("Status", "status"),
        ("Risk Level", "risk_level"), ("QA Reviewer", "qa_reviewer"), ("Approver", "approver"),
    ]:
        val = cc.get(key, "")
        if val:
            md.append(f"| **{label}** | {val} |")
    md.append("")

    md.append("## 1. Change Description")
    md.append(cc.get("change_description", "_Not documented._"))
    md.append("")

    if cc.get("reason_for_change"):
        md.append("## 2. Reason for Change")
        md.append(cc["reason_for_change"])
        md.append("")
        if narratives.get("justification"):
            md.append("**Expanded Justification (AI-assisted):**")
            md.append(narratives["justification"])
            md.append("")

    if cc.get("current_state") or cc.get("proposed_state"):
        md.append("## 3. Current vs. Proposed State")
        if cc.get("current_state"):
            md.append(f"**Current State:** {cc['current_state']}")
            md.append("")
        if cc.get("proposed_state"):
            md.append(f"**Proposed State:** {cc['proposed_state']}")
            md.append("")

    if impacts:
        md.append("## 4. Impact Assessment")
        md.append("| Impact Area | Impacted? | Extent | Action Required |")
        md.append("|-------------|-----------|--------|------------------|")
        for i in impacts:
            md.append(f"| {i.get('impact_area', '')} | {i.get('impacted', '')} | {i.get('extent', '')} | {i.get('action_required', '')} |")
        md.append("")

    if narratives.get("risk_summary"):
        md.append("## 5. Risk Summary")
        md.append(narratives["risk_summary"])
        md.append("")

    if actions:
        md.append("## 6. Implementation Plan")
        md.append("| Step | Activity | Responsible | Target Date | Status |")
        md.append("|------|----------|-------------|-------------|--------|")
        for a in actions:
            md.append(f"| {a.get('step_no', '')} | {a.get('activity', '')} | {a.get('responsible', '')} | {a.get('target_date', '')} | {a.get('status', '')} |")
        md.append("")

    if narratives.get("rollback_plan"):
        md.append("## 7. Rollback Plan")
        md.append(narratives["rollback_plan"])
        md.append("")

    if narratives.get("regulatory_impact"):
        md.append("## 8. Regulatory Impact")
        md.append(narratives["regulatory_impact"])
        md.append("")

    if narratives.get("verification_summary"):
        md.append("## 9. Post-Implementation Verification")
        md.append(narratives["verification_summary"])
        md.append("")

    if narratives.get("effectiveness_review"):
        md.append("## 10. Effectiveness Review")
        md.append(narratives["effectiveness_review"])
        md.append("")

    if linked_deviations or linked_capas:
        md.append("## 11. Related Records")
        if linked_deviations:
            md.append("**Linked Deviations:** " + ", ".join(d.get("deviation_number", "") for d in linked_deviations))
        if linked_capas:
            md.append("**Linked CAPAs:** " + ", ".join(c.get("capa_number", "") for c in linked_capas))
        md.append("")

    if narratives.get("executive_summary"):
        md.append("## 12. Executive Summary")
        md.append(narratives["executive_summary"])
        md.append("")

    if approvals:
        md.append("## 13. Review & Approval Trail")
        md.append("| # | Action | Performed By | Role | Comments | Timestamp |")
        md.append("|---|--------|---------------|------|----------|-----------|")
        for i, a in enumerate(approvals, 1):
            md.append(f"| {i} | {a.get('action', '')} | {a.get('performed_by', '')} | {a.get('role', '')} | {a.get('comments', '')} | {a.get('created_at', '')} |")
        md.append("")

    md.append("## 14. Regulatory References")
    md.append("- 21 CFR 211.68 / 211.100 — Equipment and written procedures")
    md.append("- EU GMP Annex 15 §13 — Change control")
    md.append("- ICH Q10 §3.2.4 — Change management")
    md.append("- GAMP 5 Chapter 10 — Change and configuration management")
    md.append("- Schedule M — Change control requirements")
    md.append("")

    md.append("---")
    md.append("*Generated by PharmaGPT Quality Management Suite — Change Control*")

    return "\n".join(md)

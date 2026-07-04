"""
services/qms_deviation_service.py — Business logic for the Deviation Management module.

Handles the AI Investigation Assistant (fishbone, 5-Why, timeline, root cause),
AI impact-assessment suggestions, AI CAPA seed suggestions, and the markdown
report builder used for DOCX export — following risk_service.py's structure.
"""

from __future__ import annotations

from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_database as qmsdb
from pharmagpt.prompts import qms_deviation_prompt as dp
from pharmagpt.services.qms_shared import call_gemini, parse_json_response


def ai_run_investigation(deviation_id: int) -> dict:
    """Run the AI Investigation Assistant and persist fishbone/5-Why/timeline/root cause."""
    deviation = ddb.get_deviation(deviation_id)
    if not deviation:
        return {"error": "Deviation not found"}

    prompt = dp.build_investigation_prompt(deviation)
    response_text = call_gemini(prompt, temperature=0.3)
    data = parse_json_response(response_text, default={
        "fishbone_data": {}, "five_why_data": [], "timeline_data": [],
        "root_cause_category": "", "root_cause_statement": "AI investigation could not parse response",
    })

    investigation = ddb.upsert_investigation(deviation_id, data)
    ddb.update_deviation(deviation_id, {"ai_investigation_data": data})
    if deviation.get("status") == "Initiated":
        ddb.update_deviation(deviation_id, {"status": "Under Investigation"})
    return investigation


def ai_suggest_impact(deviation_id: int) -> list[dict]:
    """Suggest impact assessment entries via AI (not auto-persisted; caller reviews and saves)."""
    deviation = ddb.get_deviation(deviation_id)
    if not deviation:
        return []
    investigation = ddb.get_investigation(deviation_id)
    prompt = dp.build_impact_prompt(deviation, investigation)
    response_text = call_gemini(prompt, temperature=0.3)
    return parse_json_response(response_text, default=[])


def ai_suggest_capa(deviation_id: int) -> dict:
    """Suggest CAPA seed content (problem statement, root cause, actions) for this deviation."""
    deviation = ddb.get_deviation(deviation_id)
    if not deviation:
        return {"error": "Deviation not found"}
    investigation = ddb.get_investigation(deviation_id)
    prompt = dp.build_capa_suggestion_prompt(deviation, investigation)
    response_text = call_gemini(prompt, temperature=0.3)
    return parse_json_response(response_text, default={
        "problem_statement": "", "root_cause": "", "corrective_actions": [], "preventive_actions": [],
    })


def generate_report_markdown(deviation_id: int) -> str:
    """Generate a markdown report for a deviation — used by in-app preview/print and DOCX export."""
    deviation = ddb.get_deviation(deviation_id)
    if not deviation:
        return "# Error: Deviation not found"

    investigation = ddb.get_investigation(deviation_id)
    impacts = ddb.get_impacts(deviation_id)
    linked_capas = ddb.get_linked_capas(deviation_id)
    approvals = qmsdb.get_approval_trail("deviation", deviation_id)

    md = []
    md.append("# Deviation Report")
    md.append(f"## {deviation.get('title', 'Untitled Deviation')}")
    md.append("")

    md.append("---")
    md.append("| Field | Value |")
    md.append("|-------|-------|")
    for label, key in [
        ("Deviation Number", "deviation_number"), ("Type", "deviation_type"),
        ("Category", "deviation_category"), ("Department", "department"),
        ("Area", "area"), ("Product", "product"), ("Batch/Lot", "batch_lot"),
        ("Equipment", "equipment"), ("Date of Occurrence", "date_of_occurrence"),
        ("Date Reported", "date_reported"), ("Initiated By", "initiated_by"),
        ("Status", "status"), ("Risk Level", "risk_level"),
        ("QA Reviewer", "qa_reviewer"), ("Approver", "approver"),
    ]:
        val = deviation.get(key, "")
        if val:
            md.append(f"| **{label}** | {val} |")
    md.append("")

    md.append("## 1. Deviation Description")
    md.append(deviation.get("description", "_Not documented._"))
    md.append("")
    if deviation.get("immediate_action"):
        md.append("## 2. Immediate Action Taken")
        md.append(deviation["immediate_action"])
        md.append("")

    if investigation:
        md.append("## 3. Investigation")
        md.append("")
        fb = investigation.get("fishbone_data", {})
        if fb:
            md.append("### 3.1 Fishbone (Ishikawa) Analysis")
            for category in ("man", "machine", "method", "material", "measurement", "environment"):
                items = fb.get(category, [])
                if items:
                    md.append(f"**{category.title()}:**")
                    for item in items:
                        md.append(f"- {item}")
            md.append("")
        fw = investigation.get("five_why_data", [])
        if fw:
            md.append("### 3.2 Five-Why Analysis")
            md.append("| Why # | Question | Answer |")
            md.append("|-------|----------|--------|")
            for i, entry in enumerate(fw, 1):
                md.append(f"| Why {i} | {entry.get('question', '')} | {entry.get('answer', '')} |")
            md.append("")
        tl = investigation.get("timeline_data", [])
        if tl:
            md.append("### 3.3 Timeline")
            md.append("| Date/Time | Event |")
            md.append("|-----------|-------|")
            for entry in tl:
                md.append(f"| {entry.get('datetime', '')} | {entry.get('event', '')} |")
            md.append("")
        if investigation.get("root_cause_statement"):
            md.append("### 3.4 Root Cause Determination")
            md.append(f"**Category:** {investigation.get('root_cause_category', '')}")
            md.append("")
            md.append(f"**Root Cause Statement:** {investigation['root_cause_statement']}")
            md.append("")

    if impacts:
        md.append("## 4. Impact Assessment")
        md.append("| Impact Area | Assessment | Risk Level | Batches Affected |")
        md.append("|-------------|------------|------------|-------------------|")
        for i in impacts:
            md.append(f"| {i.get('impact_area', '')} | {i.get('assessment_text', '')} | {i.get('risk_level', '')} | {i.get('batches_affected', '')} |")
        md.append("")

    if linked_capas:
        md.append("## 5. CAPA Actions Initiated")
        md.append("| CAPA Number | Title | Status |")
        md.append("|-------------|-------|--------|")
        for c in linked_capas:
            md.append(f"| {c.get('capa_number', '')} | {c.get('title', '')} | {c.get('status', '')} |")
        md.append("")

    if approvals:
        md.append("## 6. QA Review & Approval Trail")
        md.append("| # | Action | Performed By | Role | Comments | Timestamp |")
        md.append("|---|--------|---------------|------|----------|-----------|")
        for i, a in enumerate(approvals, 1):
            md.append(f"| {i} | {a.get('action', '')} | {a.get('performed_by', '')} | {a.get('role', '')} | {a.get('comments', '')} | {a.get('created_at', '')} |")
        md.append("")

    md.append("## 7. Regulatory References")
    md.append("- 21 CFR 211.192 — Investigation of unexplained discrepancies")
    md.append("- EU GMP Chapter 6 — Deviations and investigation")
    md.append("- ICH Q10 — Quality system deviation management")
    md.append("- Schedule M — Deviation management requirements")
    md.append("")

    md.append("---")
    md.append("*Generated by PharmaGPT Quality Management Suite — Deviation Management*")

    return "\n".join(md)

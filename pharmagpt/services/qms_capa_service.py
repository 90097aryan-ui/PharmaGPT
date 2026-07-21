"""
services/qms_capa_service.py — Business logic for the CAPA module.

Handles AI CAPA draft suggestions, effectiveness-check suggestions, the
Quality Trend Summary (cross-CAPA/deviation AI narrative used by the QMS
dashboard), and the markdown report builder used for DOCX export.
"""

from __future__ import annotations

from pharmagpt import qms_capa_database as cdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_database as qmsdb
from pharmagpt.prompts import qms_capa_prompt as cp
from pharmagpt.services.qms_shared import call_gemini, parse_json_response


def ai_suggest_draft(capa_id: int) -> dict:
    capa = cdb.get_capa(capa_id)
    if not capa:
        return {"error": "CAPA not found"}
    prompt = cp.build_draft_prompt(capa)
    response_text = call_gemini(prompt, temperature=0.3)
    return parse_json_response(response_text, default={
        "problem_statement": "", "root_cause": "", "corrective_actions": [], "preventive_actions": [],
    })


def ai_suggest_effectiveness(capa_id: int) -> list[dict]:
    capa = cdb.get_capa(capa_id)
    if not capa:
        return []
    actions = cdb.get_actions(capa_id)
    prompt = cp.build_effectiveness_prompt(capa, actions)
    response_text = call_gemini(prompt, temperature=0.3)
    return parse_json_response(response_text, default=[])


def ai_trend_summary(company_id: str) -> str:
    """Quality Trend Summary across recent CAPAs and Deviations, for the
    unified QMS dashboard. `company_id` must come from the authenticated
    TenantContext, never from client input (pharmagpt/tenancy.py)."""
    capas = cdb.get_all_capas(company_id)
    deviations = ddb.get_all_deviations(company_id)
    prompt = cp.build_trend_prompt(capas, deviations)
    text = call_gemini(prompt, temperature=0.3)
    return text or "Trend summary unavailable."


def generate_report_markdown(capa_id: int) -> str:
    capa = cdb.get_capa(capa_id)
    if not capa:
        return "# Error: CAPA not found"

    actions = cdb.get_actions(capa_id)
    effectiveness = cdb.get_effectiveness(capa_id)
    linked_deviations = ddb.get_linked_deviations(capa_id)
    approvals = qmsdb.get_approval_trail("capa", capa_id)

    md = []
    md.append("# CAPA Report")
    md.append(f"## {capa.get('title', 'Untitled CAPA')}")
    md.append("")

    md.append("---")
    md.append("| Field | Value |")
    md.append("|-------|-------|")
    for label, key in [
        ("CAPA Number", "capa_number"), ("Source", "capa_source"),
        ("Source Reference", "source_reference"), ("Department", "department"),
        ("Initiated By", "initiated_by"), ("Date Initiated", "date_initiated"),
        ("Target Closure Date", "target_closure_date"), ("Status", "status"),
        ("QA Reviewer", "qa_reviewer"), ("Approver", "approver"),
        ("Closure Date", "closure_date"),
    ]:
        val = capa.get(key, "")
        if val:
            md.append(f"| **{label}** | {val} |")
    md.append("")

    md.append("## 1. Problem Statement")
    md.append(capa.get("problem_statement", "_Not documented._"))
    md.append("")

    if capa.get("root_cause"):
        md.append("## 2. Root Cause")
        md.append(capa["root_cause"])
        md.append("")

    if linked_deviations:
        md.append("## 3. Related Deviations")
        md.append("| Deviation Number | Title | Status |")
        md.append("|-------------------|-------|--------|")
        for d in linked_deviations:
            md.append(f"| {d.get('deviation_number', '')} | {d.get('title', '')} | {d.get('status', '')} |")
        md.append("")

    corrective = [a for a in actions if a.get("action_type") == "Corrective"]
    preventive = [a for a in actions if a.get("action_type") == "Preventive"]

    if corrective:
        md.append("## 4. Corrective Actions")
        md.append("| Description | Owner | Due Date | Status | Escalated |")
        md.append("|--------------|-------|----------|--------|-----------|")
        for a in corrective:
            esc = "Yes" if a.get("escalated") else "No"
            md.append(f"| {a.get('description', '')} | {a.get('owner', '')} | {a.get('due_date', '')} | {a.get('status', '')} | {esc} |")
        md.append("")

    if preventive:
        md.append("## 5. Preventive Actions")
        md.append("| Description | Owner | Due Date | Status | Escalated |")
        md.append("|--------------|-------|----------|--------|-----------|")
        for a in preventive:
            esc = "Yes" if a.get("escalated") else "No"
            md.append(f"| {a.get('description', '')} | {a.get('owner', '')} | {a.get('due_date', '')} | {a.get('status', '')} | {esc} |")
        md.append("")

    if effectiveness:
        md.append("## 6. Effectiveness Check")
        md.append("| Criterion | Method | Timeframe | Acceptable Result | Actual Result | Status |")
        md.append("|-----------|--------|-----------|--------------------|----------------|--------|")
        for e in effectiveness:
            md.append(f"| {e.get('check_criterion', '')} | {e.get('method', '')} | {e.get('timeframe', '')} | {e.get('acceptable_result', '')} | {e.get('actual_result', '')} | {e.get('status', '')} |")
        md.append("")

    if approvals:
        md.append("## 7. QA Review & Approval Trail")
        md.append("| # | Action | Performed By | Role | Comments | Timestamp |")
        md.append("|---|--------|---------------|------|----------|-----------|")
        for i, a in enumerate(approvals, 1):
            md.append(f"| {i} | {a.get('action', '')} | {a.get('performed_by', '')} | {a.get('role', '')} | {a.get('comments', '')} | {a.get('created_at', '')} |")
        md.append("")

    md.append("## 8. Regulatory References")
    md.append("- 21 CFR 820.100 — CAPA procedure requirements")
    md.append("- EU GMP Chapter 8 — Complaints and product recalls")
    md.append("- ICH Q10 §3.2 — Corrective action and preventive action system")
    md.append("")

    md.append("---")
    md.append("*Generated by PharmaGPT Quality Management Suite — CAPA*")

    return "\n".join(md)

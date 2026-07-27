"""
services/qms_deviation_service.py — Business logic for the Deviation Management module.

Handles AI impact-assessment suggestions, AI CAPA seed suggestions, and the
markdown report builder used for DOCX export — following risk_service.py's
structure. The AI Investigation Assistant/Report Generation and root cause
determination moved to services/investigation_engine.py (architecture
refactor: Workflow vs. Investigation separation) — this file no longer owns
that logic; `ddb.get_investigation`/`upsert_investigation`
(qms_deviation_investigation) are kept read-only as the pre-refactor
investigation record, not written to by any route anymore.
"""

from __future__ import annotations

from pharmagpt import qms_deviation_database as ddb
from pharmagpt.prompts import qms_deviation_prompt as dp
from pharmagpt.services import investigation_engine as inv
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.services.qms_shared import call_gemini, parse_json_response


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
    """Suggest CAPA seed content (problem statement, root cause, actions) for
    this deviation. Prefers the investigator's finalized Investigation
    Summary (services/investigation_engine.py, the formal CAPA handoff —
    architecture refactor refinement #7) when one exists; falls back to an
    ad-hoc AI suggestion otherwise, same as before the refactor."""
    deviation = ddb.get_deviation(deviation_id)
    if not deviation:
        return {"error": "Deviation not found"}

    summary = inv.get_summary("deviation", deviation_id)
    if summary and summary.get("finalized_at"):
        root_cause = inv.get_root_cause("deviation", deviation_id) or {}
        return {
            "problem_statement": summary.get("summary_text", ""),
            "root_cause": root_cause.get("confirmed_root_cause") or root_cause.get("probable_cause", ""),
            "corrective_actions": [
                {"description": a} if isinstance(a, str) else a
                for a in summary.get("recommended_capa_actions", [])
            ],
            "preventive_actions": [],
            "source": "investigation_summary",
        }

    investigation = ddb.get_investigation(deviation_id)
    prompt = dp.build_capa_suggestion_prompt(deviation, investigation)
    response_text = call_gemini(prompt, temperature=0.3)
    result = parse_json_response(response_text, default={
        "problem_statement": "", "root_cause": "", "corrective_actions": [], "preventive_actions": [],
    })
    result["source"] = "ai_suggestion"
    return result


def generate_report_markdown(deviation_id: int) -> str:
    """Generate a markdown report for a deviation — used by in-app preview/print and DOCX export."""
    deviation = ddb.get_deviation(deviation_id)
    if not deviation:
        return "# Error: Deviation not found"

    impacts = ddb.get_impacts(deviation_id)
    linked_capas = ddb.get_linked_capas(deviation_id)
    workflow_steps = [
        s for s in wfe.get_instance_state("deviation", deviation_id)["steps"]
        if s["status"] in ("approved", "rejected", "returned")
    ]
    root_cause = inv.get_root_cause("deviation", deviation_id)
    summary = inv.get_summary("deviation", deviation_id)
    dashboard = inv.get_dashboard("deviation", deviation_id)

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

    if root_cause or summary or dashboard.get("evidence_score") is not None:
        md.append("## 3. Investigation Case")
        md.append("")
        md.append(
            f"**Evidence Score:** {dashboard['evidence_score']}% ({dashboard['evidence_score_basis']}) — "
            f"Document completeness {dashboard['document_completeness_pct']}%, "
            f"Interviews {dashboard['interviews_completed']}/{dashboard['interviews_total']}, "
            f"Timeline completeness {dashboard['timeline_completeness_pct']}%"
        )
        md.append("")
        if root_cause:
            md.append("### 3.1 Root Cause")
            if root_cause.get("possible_cause"):
                md.append(f"**Possible Cause** ({root_cause.get('possible_cause_source', '')}): {root_cause['possible_cause']}")
            if root_cause.get("probable_cause"):
                md.append(f"**Probable Cause:** {root_cause['probable_cause']}")
                if root_cause.get("probable_cause_rationale"):
                    md.append(f"  _Rationale: {root_cause['probable_cause_rationale']}_")
            if root_cause.get("confirmed_root_cause"):
                md.append(f"**Confirmed Root Cause:** {root_cause['confirmed_root_cause']} "
                           f"(confirmed by {root_cause.get('confirmed_by', '')} on {root_cause.get('confirmed_at', '')})")
            md.append("")
        if summary and summary.get("finalized_at"):
            md.append("### 3.2 Investigation Summary (finalized CAPA handoff)")
            md.append(summary.get("summary_text", ""))
            if summary.get("key_findings"):
                md.append("")
                md.append("**Key Findings:**")
                for f in summary["key_findings"]:
                    md.append(f"- {f}")
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

    if workflow_steps:
        md.append("## 6. Workflow / Approval Trail")
        md.append("| # | Step | Outcome | Decided By | Comments | Timestamp |")
        md.append("|---|------|---------|------------|----------|-----------|")
        for i, s in enumerate(workflow_steps, 1):
            md.append(f"| {i} | {s.get('step_name', '')} | {s.get('status', '')} | {s.get('decided_by', '')} | {s.get('comments', '')} | {s.get('decided_at', '')} |")
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

"""
services/qms_document_service.py — Business logic for the Document Control module.

AI draft generation is streamed directly from routes/qms_documents.py (SSE),
the same way routes/risk.py streams FMEA generation. This service handles the
non-streamed AI review and the markdown report builder used for DOCX export.
"""

from __future__ import annotations

from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_database as qmsdb
from pharmagpt.prompts import qms_document_prompt as qp
from pharmagpt.services.qms_shared import call_gemini, parse_json_response


def ai_review_document(document_id: int) -> dict:
    """Run an AI regulatory-compliance review on a document's current content."""
    document = qdb.get_document(document_id)
    if not document:
        return {"error": "Document not found"}

    prompt = qp.build_review_prompt(document, document.get("content", ""))
    response_text = call_gemini(prompt, temperature=0.2)
    review_data = parse_json_response(response_text, default={
        "completeness_score": 0,
        "regulatory_compliance_score": 0,
        "clarity_score": 0,
        "overall_score": 0,
        "critical_findings": ["AI review could not parse response"],
        "missing_elements": [],
        "suggested_improvements": [],
        "reviewer_comments": response_text[:500],
        "recommendation": "Revise",
    })

    qdb.update_document(document_id, {"ai_review_data": review_data})
    return review_data


def generate_report_markdown(document_id: int) -> str:
    """Generate a markdown report for a document — used by both in-app preview/print and DOCX export."""
    document = qdb.get_document(document_id)
    if not document:
        return "# Error: Document not found"

    versions = qdb.get_versions(document_id)
    training = qdb.get_training(document_id)
    distribution = qdb.get_distribution(document_id)
    approvals = qmsdb.get_approval_trail("document", document_id)
    ai_review = document.get("ai_review_data", {})

    md = []
    md.append(f"# {document.get('title', 'Untitled Document')}")
    md.append(f"## {document.get('doc_type', 'SOP')} — {document.get('doc_number', '')}")
    md.append("")

    md.append("---")
    md.append("| Field | Value |")
    md.append("|-------|-------|")
    for label, key in [
        ("Document Number", "doc_number"), ("Document Type", "doc_type"),
        ("Department", "department"), ("Category", "category"),
        ("Version", "version"), ("Status", "status"),
        ("Effective Date", "effective_date"), ("Review Date", "review_date"),
        ("Expiry Date", "expiry_date"), ("Owner", "owner"),
        ("Reviewer", "reviewer"), ("Approver", "approver"),
    ]:
        val = document.get(key, "")
        if val:
            md.append(f"| **{label}** | {val} |")
    md.append("")

    md.append("## Document Content")
    md.append(document.get("content", "_No content drafted yet._"))
    md.append("")

    if versions:
        md.append("## Revision History")
        md.append("| Version | Date | Change Summary | Changed By |")
        md.append("|---------|------|-----------------|------------|")
        for v in reversed(versions):
            md.append(f"| {v.get('version', '')} | {v.get('created_at', '')} | {v.get('change_summary', '')} | {v.get('changed_by', '')} |")
        md.append("")

    if training:
        md.append("## Training Record")
        md.append("| Trainee | Role | Status | Training Date | Trainer |")
        md.append("|---------|------|--------|----------------|---------|")
        for t in training:
            md.append(f"| {t.get('trainee_name', '')} | {t.get('role', '')} | {t.get('training_status', '')} | {t.get('training_date', '')} | {t.get('trainer', '')} |")
        md.append("")

    if distribution:
        md.append("## Distribution Record")
        md.append("| Distributed To | Department | Date | Acknowledged |")
        md.append("|-----------------|------------|------|--------------|")
        for d in distribution:
            ack = "Yes" if d.get("acknowledged") else "No"
            md.append(f"| {d.get('distributed_to', '')} | {d.get('department', '')} | {d.get('distributed_date', '')} | {ack} |")
        md.append("")

    if ai_review and ai_review.get("overall_score"):
        md.append("## AI Regulatory Compliance Review")
        md.append("")
        md.append("| Score Category | Result |")
        md.append("|-----------------|--------|")
        md.append(f"| Completeness | {ai_review.get('completeness_score', 'N/A')}/100 |")
        md.append(f"| Regulatory Compliance | {ai_review.get('regulatory_compliance_score', 'N/A')}/100 |")
        md.append(f"| Clarity | {ai_review.get('clarity_score', 'N/A')}/100 |")
        md.append(f"| **Overall Score** | **{ai_review.get('overall_score', 'N/A')}/100** |")
        md.append(f"| Recommendation | {ai_review.get('recommendation', 'N/A')} |")
        md.append("")
        if ai_review.get("reviewer_comments"):
            md.append("**AI Reviewer Comments:**")
            md.append(ai_review["reviewer_comments"])
            md.append("")

    if approvals:
        md.append("## Approval Trail")
        md.append("| # | Action | Performed By | Role | Comments | Timestamp |")
        md.append("|---|--------|---------------|------|----------|-----------|")
        for i, a in enumerate(approvals, 1):
            md.append(f"| {i} | {a.get('action', '')} | {a.get('performed_by', '')} | {a.get('role', '')} | {a.get('comments', '')} | {a.get('created_at', '')} |")
        md.append("")

    md.append("---")
    md.append("*Generated by PharmaGPT Quality Management Suite — Document Control*")

    return "\n".join(md)

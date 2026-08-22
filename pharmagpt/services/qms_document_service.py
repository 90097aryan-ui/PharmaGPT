"""
services/qms_document_service.py — Business logic for the Document Control module.

AI draft generation is streamed directly from routes/qms_documents.py (SSE),
the same way routes/risk.py streams FMEA generation. This service handles the
non-streamed AI review and the markdown report builder used for DOCX export.
"""

from __future__ import annotations

from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb
from pharmagpt import qms_document_database as qdb
from pharmagpt import qms_database as qmsdb
from pharmagpt.prompts import qms_document_prompt as qp
from pharmagpt.services.qms_shared import call_gemini, parse_json_response

# Cap per-document text pulled into the AI prompt so one huge manual can't
# blow the model's context window; still large enough to carry a full
# equipment manual's relevant sections.
_KB_CONTEXT_CHAR_LIMIT = 8000


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


def build_equipment_knowledge_base_context(equipment_id: int, company_id: str) -> str:
    """AI-Assisted SOP Creation (spec §4): assemble equipment basics + the
    extracted text of every Knowledge Base document linked to this
    Equipment, for use as build_draft_prompt()'s `knowledge_base` context.

    Tenant-scoped via equipment_database.get_equipment_scoped — never
    resolves an equipment record belonging to another company. Returns ""
    (no context) if the equipment doesn't exist/isn't in this tenant, which
    build_draft_prompt() treats the same as no Knowledge Base reference at
    all — never invents a fallback."""
    equipment = equipdb.get_equipment_scoped(equipment_id, company_id)
    if not equipment:
        return ""

    lines = [f"Equipment: {equipment.get('name', '')} ({equipment.get('equipment_code', '')})"]
    for field, label in (
        ("equipment_type", "Type"), ("model", "Model"), ("manufacturer", "Manufacturer"),
        ("tag_number", "Tag Number"), ("plant", "Plant"), ("department", "Department"), ("area", "Area"),
    ):
        val = equipment.get(field)
        if val:
            lines.append(f"  {label}: {val}")

    links = [l for l in equipdb.list_equipment_documents(equipment_id) if l.get("resolved")]
    if not links:
        lines.append("\nNo controlled reference documents are linked to this equipment in the "
                      "Knowledge Base — no equipment-specific source material is available.")
        return "\n".join(lines)

    lines.append("\nLinked controlled reference documents:")
    for link in links:
        lines.append(f"\n--- {link.get('document_role', 'Reference')}: {link.get('display_title', '')} ---")
        if link.get("source_type") != "kb":
            continue
        kb_doc = db.get_kb_document(link["source_id"])
        text = (kb_doc or {}).get("text_content") or ""
        lines.append(text[:_KB_CONTEXT_CHAR_LIMIT] if text else "(no extracted text available for this document)")

    return "\n".join(lines)


def render_template_skeleton_markdown(template: dict) -> str:
    """Manual SOP path (spec §2, Option 1): the blank, fillable structure of
    a Controlled SOP Template — headings/sub-headings only, no procedure
    content — for the "Create from Controlled Template" download. Feeds
    doc_exporter.markdown_to_docx the same way an authored document's report
    does, so the download is a real, correctly-formatted DOCX."""
    lines = [f"# {template.get('name', 'Controlled Template')}"]
    for heading in template.get("structure") or []:
        lines.append(f"\n## {heading.get('heading', '')}\n")
        for sub in heading.get("sub_headings") or []:
            lines.append(f"### {sub}\n")
    return "\n".join(lines)


def generate_report_markdown(document_id: int, version_id: int | None = None) -> str:
    """Generate a markdown report for a document — used by both in-app
    preview/print and DOCX export.

    `version_id` (Document Control redesign): when given, renders that
    SPECIFIC historical qms_document_versions row's frozen content/version
    number/status instead of the document's live current state — the
    export-a-historical-version path. The row is immutable once non-draft
    (Phase 1), so this always reflects exactly what was actually
    reviewed/approved/effective at that version, never today's live edits."""
    document = qdb.get_document(document_id)
    if not document:
        return "# Error: Document not found"

    content = document.get("content", "")
    version_label = document.get("version", "")
    status_label = document.get("status", "")
    historical_version = None
    if version_id is not None:
        historical_version = qdb.get_version(version_id)
        if not historical_version or historical_version["document_id"] != document_id:
            return "# Error: Version not found"
        content = historical_version["content_snapshot"]
        version_label = historical_version["version_number"]
        status_label = historical_version["status"]

    versions = qdb.get_versions(document_id)
    training = qdb.get_training(document_id)
    distribution = qdb.get_distribution(document_id)
    approvals = qmsdb.get_approval_trail("document", document_id)
    ai_review = document.get("ai_review_data", {})

    md = []
    md.append(f"# {document.get('title', 'Untitled Document')}")
    md.append(f"## {document.get('doc_type', 'SOP')} — {document.get('doc_number', '')}")
    md.append("")
    if historical_version:
        md.append(f"_Historical version {version_label} ({status_label}) — this export reflects exactly "
                   f"what this version contained; it is not the document's current live content._")
        md.append("")

    md.append("---")
    md.append("| Field | Value |")
    md.append("|-------|-------|")
    field_overrides = {"version": version_label, "status": status_label}
    # Document Control Information (spec §1/§2): Document Number, Title,
    # Version, Effective Date, Department, Prepared By, Reviewed By,
    # Approved By are the controlled template's mandatory header fields —
    # every one of them is system-derived (see routes/qms_documents.py's
    # create_document()/release_document() and services/workflow_engine.py's
    # _document_version_on_step_approved), never author-typed.
    for label, key in [
        ("Document Number", "doc_number"), ("Document Type", "doc_type"),
        ("Department", "department"), ("Category", "category"),
        ("Version", "version"), ("Status", "status"),
        ("Effective Date", "effective_date"), ("Review Date", "review_date"),
        ("Expiry Date", "expiry_date"), ("Owner", "owner"),
        ("Prepared By", "prepared_by"), ("Reviewed By", "reviewed_by"), ("Approved By", "approved_by"),
        ("Reviewer", "reviewer"), ("Approver", "approver"),
    ]:
        val = field_overrides.get(key, document.get(key, ""))
        if val:
            md.append(f"| **{label}** | {val} |")
    md.append("")

    md.append("## Document Content")
    md.append(content or "_No content drafted yet._")
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

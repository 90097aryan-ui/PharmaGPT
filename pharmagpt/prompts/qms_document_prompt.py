"""
prompts/qms_document_prompt.py — AI prompt builders for the Document Control module.

Two AI features:
  build_draft_prompt()   — SOP / Policy / Manual / etc. draft generation (markdown, streamed)
  build_review_prompt()  — Regulatory Compliance Review of an existing document (JSON)
"""

from __future__ import annotations


def _doc_context(info: dict) -> str:
    lines = []
    for label, key in [
        ("Document Title", "title"),
        ("Document Type", "doc_type"),
        ("Document Number", "doc_number"),
        ("Department", "department"),
        ("Category", "category"),
        ("Version", "version"),
        ("Owner", "owner"),
        ("Purpose / Scope Notes", "purpose_notes"),
    ]:
        val = info.get(key, "")
        if val:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


def build_draft_prompt(info: dict, knowledge_base: str = "") -> str:
    """Return a prompt whose response is the full markdown content of the controlled document."""
    ctx = _doc_context(info)
    doc_type = info.get("doc_type", "SOP")
    kb_section = f"\nRELEVANT KNOWLEDGE BASE CONTEXT:\n{knowledge_base}\n" if knowledge_base else ""

    return f"""You are a Senior Pharmaceutical Quality Systems Consultant drafting a controlled
{doc_type} for a GMP-regulated manufacturing site, per 21 CFR Part 211, EU GMP Chapter 4,
WHO-GMP, and Schedule M documentation requirements.

DOCUMENT INFORMATION:
{ctx}
{kb_section}
Generate the complete {doc_type} content in markdown using EXACTLY this structure:

# {info.get('title', f'{doc_type} Title')}

## Document Control Information
| Field | Details |
|-------|---------|
| Document Number | {info.get('doc_number', '')} |
| Document Type | {doc_type} |
| Version | {info.get('version', '1.0')} |
| Department | {info.get('department', '')} |
| Effective Date | |
| Review Date | |

## 1. Purpose
[Clear statement of what this document achieves and why it exists]

## 2. Scope
[Define what this document covers — areas, equipment, products, personnel, exclusions]

## 3. Responsibilities
| Role | Responsibility |
|------|----------------|
[List each role involved and their specific responsibilities]

## 4. Definitions and Abbreviations
[Define any technical terms or abbreviations used]

## 5. Procedure
[Detailed, numbered, step-by-step procedure appropriate for a {doc_type}. Be specific and
actionable — this must be executable by trained personnel without ambiguity.]

## 6. Acceptance Criteria
[Where applicable — measurable pass/fail criteria]

## 7. Records and Documentation
[What records must be generated/retained as evidence of compliance]

## 8. References
[Cite applicable regulations: 21 CFR 211, EU GMP, WHO-GMP, Schedule M, ICH guidelines, internal
SOPs referenced]

## 9. Revision History
| Rev | Date | Description | Author |
|-----|------|-------------|--------|
| 00 | | Initial Issue | |

Write all sections completely and specifically — no placeholder text in the final output except
signature/date blank fields. Keep language precise, professional, and audit-ready."""


def build_review_prompt(document: dict, content: str) -> str:
    """Return a prompt whose response is a JSON regulatory-compliance review of the document."""
    ctx = _doc_context(document)
    trimmed = content[:6000]  # bound prompt size

    return f"""You are a Senior GMP Auditor reviewing a controlled document for regulatory
compliance and documentation quality prior to approval.

DOCUMENT DETAILS:
{ctx}

DOCUMENT CONTENT:
{trimmed}

Perform a thorough compliance review and return ONLY valid JSON (no other text):
{{
  "completeness_score": 85,
  "regulatory_compliance_score": 78,
  "clarity_score": 82,
  "overall_score": 82,
  "critical_findings": ["finding 1", "finding 2"],
  "missing_elements": ["element that should be present but is missing"],
  "suggested_improvements": ["specific improvement suggestion"],
  "reviewer_comments": "Overall narrative review comment from the auditor's perspective",
  "recommendation": "Approve / Revise / Reject"
}}

SCORING CRITERIA (0-100):
- Completeness: All required sections present and populated (Purpose, Scope, Responsibilities,
  Procedure, Acceptance Criteria, Records, References)
- Regulatory Compliance: Alignment with 21 CFR Part 211, EU GMP, WHO-GMP, ICH Q10
- Clarity: Procedure steps are specific, actionable, and unambiguous for trained personnel
"""

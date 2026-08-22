"""
prompts/qms_document_prompt.py — AI prompt builders for the Document Control module.

Three AI features:
  build_draft_prompt()   — SOP / Policy / Manual / etc. draft generation (markdown, streamed)
  build_review_prompt()  — Regulatory Compliance Review of an existing document (JSON)

Plus a deterministic, non-AI enforcement half (Document Control redesign —
controlled-template heading preservation, fix): validate_template_structure()
checks AI-generated content against a controlled template's approved
headings/sub-headings after the fact. A prompt instruction alone cannot
*guarantee* an LLM follows it — this function is the actual, testable
enforcement mechanism; the prompt instructions in build_draft_prompt()
are what give the AI its best chance to comply in the first place.
"""

from __future__ import annotations

import re


def _flatten_required_headings(structure: list[dict]) -> list[str]:
    """A template's structure ([{"heading":..., "sub_headings":[...]}, ...])
    flattened into the ordered list of exact heading strings that must
    appear in generated content — each heading immediately followed by its
    own sub-headings, matching reading/document order."""
    required = []
    for section in structure or []:
        heading = (section.get("heading") or "").strip()
        if heading:
            required.append(heading)
        for sub in section.get("sub_headings") or []:
            sub = (sub or "").strip()
            if sub:
                required.append(sub)
    return required


def _format_template_structure_block(structure: list[dict]) -> str:
    """The '## Heading' / '### Sub-heading' skeleton injected into the AI
    prompt for a controlled template — each with an explicit fill-in-only
    instruction directly beneath it, not just a general rule stated once."""
    lines = []
    for section in structure or []:
        heading = (section.get("heading") or "").strip()
        if not heading:
            continue
        lines.append(f"## {heading}")
        lines.append("[Fill this section's content here — do not remove, rename, reorder, merge, or "
                      "split this controlled heading]")
        lines.append("")
        for sub in section.get("sub_headings") or []:
            sub = (sub or "").strip()
            if not sub:
                continue
            lines.append(f"### {sub}")
            lines.append("[Fill this sub-section's content here — do not remove, rename, reorder, "
                          "merge, or split this controlled sub-heading]")
            lines.append("")
    return "\n".join(lines)


def validate_template_structure(content: str, structure: list[dict]) -> dict:
    """Deterministic post-generation check: does `content` (AI-generated or
    otherwise) contain every controlled heading/sub-heading from `structure`,
    verbatim, in the required relative order? No AI call involved — pure
    text analysis, fully unit-testable.

    Returns {"valid", "missing_headings", "out_of_order", "required_headings",
    "actual_headings"}. Extra headings/content the AI adds beyond the
    controlled set are NOT a violation (only removing, renaming, or
    reordering a CONTROLLED heading is) — "actual_headings" is informational.
    """
    required = _flatten_required_headings(structure)
    actual = [m.strip() for m in re.findall(r"^#{1,6}\s+(.+)$", content or "", re.MULTILINE)]

    missing = [h for h in required if h not in actual]
    present_required_in_actual_order = [h for h in actual if h in required]
    present_required_expected_order = [h for h in required if h in actual]
    out_of_order = present_required_in_actual_order != present_required_expected_order

    return {
        "valid": not missing and not out_of_order,
        "missing_headings": missing,
        "out_of_order": out_of_order,
        "required_headings": required,
        "actual_headings": actual,
    }


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


def build_draft_prompt(info: dict, knowledge_base: str = "", template: dict | None = None) -> str:
    """Return a prompt whose response is the full markdown content of the
    controlled document.

    `template` (Document Control redesign): a template dict as returned by
    qms_document_database.get_template() (must have a non-empty
    "structure" list) — when given, the prompt's structure section is built
    DYNAMICALLY from the template's approved headings/sub-headings, with
    explicit non-removal/non-reorder instructions, instead of the fixed
    9-section default below. Omitted or a template with no structure falls
    back to that fixed default exactly as before this parameter existed —
    fully backward compatible for every document not created from a
    template."""
    ctx = _doc_context(info)
    doc_type = info.get("doc_type", "SOP")
    # AI-Assisted SOP Creation (spec §4): equipment-derived Knowledge Base
    # context is retrieved and passed in verbatim — this instruction is what
    # stops the model from inventing equipment-specific technical detail the
    # retrieved context doesn't actually contain.
    kb_section = (
        f"\nRELEVANT KNOWLEDGE BASE CONTEXT (retrieved equipment/manufacturer documentation):\n"
        f"{knowledge_base}\n\n"
        "Use ONLY the information above for equipment-specific technical detail (operating "
        "parameters, settings, cleaning agents, safety precautions, maintenance intervals, etc.). "
        "Do NOT invent or assume any such detail that is not present above — where the Knowledge "
        "Base context does not cover something the controlled structure requires, write "
        "\"[INFORMATION GAP — not found in Knowledge Base; confirm with equipment owner/manual]\" "
        "at that point instead of fabricating a value.\n"
    ) if knowledge_base else ""

    if template and template.get("structure"):
        structure_block = _format_template_structure_block(template["structure"])
        return f"""You are a Senior Pharmaceutical Quality Systems Consultant drafting a controlled
{doc_type} for a GMP-regulated manufacturing site, per 21 CFR Part 211, EU GMP Chapter 4,
WHO-GMP, and Schedule M documentation requirements.

DOCUMENT INFORMATION:
{ctx}
{kb_section}
This document must be generated against the company's APPROVED CONTROLLED TEMPLATE
"{template.get('name', '')}". The template defines a fixed, approved set of headings and
sub-headings that constitute the document's controlled structure.

STRUCTURE RULES (mandatory, non-negotiable):
- You MUST include every heading and sub-heading listed below, using the EXACT wording given,
  in the EXACT order given.
- You MUST NOT remove, rename, reorder, merge, split, or otherwise restructure any controlled
  heading or sub-heading listed below.
- You MAY write content beneath each heading/sub-heading; you MAY NOT add new top-level headings
  that are not listed below.
- Do not invent sub-headings for a heading that has none listed.

Generate the complete {doc_type} content in markdown, filling in content under EXACTLY this
controlled structure (do not alter the headings themselves):

# {info.get('title', f'{doc_type} Title')}

{structure_block}
Write all sections completely and specifically — no placeholder text in the final output except
signature/date blank fields. Keep language precise, professional, and audit-ready."""

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

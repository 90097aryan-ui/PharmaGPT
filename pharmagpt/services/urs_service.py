"""
urs_service.py — Business logic for the URS Management Suite.

Responsibilities
----------------
1. AI requirement generation via Gemini (SSE streaming).
2. AI review of complete URS for compliance scoring.
3. DOCX export of approved URS documents.
4. Traceability link building between URS and downstream documents.
"""

from __future__ import annotations

import json
from pharmagpt.services.urs_requirement_library import (
    build_numbered_requirements,
    get_library_requirements,
    SECTION_PREFIX,
)


# ── AI Prompt for requirement generation ──────────────────────────────────────

def build_generation_prompt(urs_info: dict, sections: list[str]) -> str:
    """Build a structured Gemini prompt for AI requirement generation."""
    equipment_name = urs_info.get("equipment_name", "the equipment")
    equipment_type = urs_info.get("equipment_type", "")
    category = urs_info.get("category", "")
    purpose = urs_info.get("purpose", "")
    intended_use = urs_info.get("intended_use", "")
    process_desc = urs_info.get("process_description", "")
    sections_str = ", ".join(sections) if sections else "all relevant sections"

    return f"""You are a Senior Pharmaceutical Validation Consultant with 30+ years of experience writing User Requirement Specifications (URS) for pharmaceutical equipment and computerized systems.

Generate comprehensive, GMP-compliant User Requirements for the following equipment/system:

EQUIPMENT DETAILS:
- Equipment Name: {equipment_name}
- Equipment Type: {equipment_type}
- Category: {category}
- Purpose: {purpose}
- Intended Use: {intended_use}
- Process Description: {process_desc}

REQUIRED SECTIONS: {sections_str}

INSTRUCTIONS:
1. Generate 5–10 specific, measurable, testable requirements per section.
2. Each requirement must start with "The system/equipment shall..."
3. Include specific numeric values, tolerances, and acceptance criteria where applicable.
4. Reference applicable regulatory standards (21 CFR Part 11, EU GMP Annex 11, GAMP 5, ICH Q8/Q9/Q10, WHO GMP, Schedule M, etc.).
5. Flag GMP-Critical requirements clearly.
6. For computerized systems, always include Data Integrity (ALCOA+), Audit Trail, Electronic Records, and Electronic Signatures sections.
7. Ensure requirements are traceable to qualification activities (IQ/OQ/PQ).

OUTPUT FORMAT — Return ONLY a JSON array with this exact structure:
[
  {{
    "section": "Functional Requirements",
    "requirement": "The system shall...",
    "rationale": "Ensures GMP compliance because...",
    "priority": "Critical",
    "gmp_criticality": "GMP-Critical",
    "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11",
    "verification_method": "Functional Test",
    "acceptance_criteria": "Specific measurable pass/fail criterion"
  }}
]

Priority values: Critical, High, Medium, Low
GMP Criticality values: GMP-Critical, GMP, Non-GMP

Generate requirements that would satisfy a senior FDA or EU GMP inspector. Be specific, measurable, and scientifically sound.
"""


def build_ai_review_prompt(urs_info: dict, requirements: list[dict]) -> str:
    """Build a Gemini prompt for AI review of a complete URS."""
    reqs_summary = []
    section_counts: dict[str, int] = {}
    for req in requirements:
        s = req.get("section", "Unknown")
        section_counts[s] = section_counts.get(s, 0) + 1
    for section, count in section_counts.items():
        reqs_summary.append(f"- {section}: {count} requirements")

    return f"""You are a Senior GMP Compliance Expert and CSV Specialist conducting a formal review of a User Requirement Specification.

URS UNDER REVIEW:
- Title: {urs_info.get('title', '')}
- Equipment: {urs_info.get('equipment_name', '')}
- Category: {urs_info.get('category', '')}
- Equipment Type: {urs_info.get('equipment_type', '')}
- Total Requirements: {len(requirements)}

SECTIONS AND REQUIREMENT COUNTS:
{chr(10).join(reqs_summary)}

SAMPLE REQUIREMENTS (first 10):
{json.dumps(requirements[:10], indent=2)}

REVIEW TASKS:
1. Assess COMPLETENESS — are all critical requirement areas covered?
2. Assess REGULATORY COMPLIANCE — do requirements reference correct standards?
3. Identify MISSING REQUIREMENTS — critical requirements that are absent.
4. Identify any DUPLICATE or CONFLICTING requirements.
5. Assess DATA INTEGRITY coverage (ALCOA+ for computerized systems).
6. Assess GAMP 5 compliance for computerized systems.
7. Assess CSV readiness for the validation lifecycle.
8. Provide an overall COMPLIANCE SCORE (0–100).
9. Provide a COMPLETENESS SCORE (0–100).

OUTPUT FORMAT — Return ONLY a JSON object:
{{
  "compliance_score": 85,
  "completeness_score": 78,
  "overall_assessment": "Brief overall assessment in 2-3 sentences",
  "strengths": ["Strength 1", "Strength 2"],
  "missing_requirements": ["Missing item 1", "Missing item 2"],
  "improvements": ["Improvement 1", "Improvement 2"],
  "regulatory_gaps": ["Gap 1", "Gap 2"],
  "data_integrity_assessment": "Assessment of data integrity coverage",
  "csv_readiness": "Assessment of CSV readiness",
  "risk_flags": ["Risk 1", "Risk 2"],
  "recommendation": "Approved for Review | Requires Revision | Major Revision Required"
}}
"""


# ── DOCX Export ───────────────────────────────────────────────────────────────

def build_urs_markdown(urs: dict, requirements: list[dict]) -> str:
    """Convert URS data to a professional Markdown document for DOCX export."""
    lines = []

    # Title block
    lines.append(f"# User Requirement Specification")
    lines.append(f"## {urs.get('title', 'Untitled URS')}")
    lines.append("")

    # Document header table
    lines.append("---")
    lines.append("")
    lines.append("**Document Information**")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| URS Number | {urs.get('urs_number', '—')} |")
    lines.append(f"| Document Number | {urs.get('doc_number', '—')} |")
    lines.append(f"| Revision | {urs.get('revision', 'A')} |")
    lines.append(f"| Status | {urs.get('status', 'draft').replace('_', ' ').title()} |")
    lines.append(f"| Department | {urs.get('department', '—')} |")
    lines.append(f"| Site | {urs.get('site', '—')} |")
    lines.append(f"| Location | {urs.get('location', '—')} |")
    lines.append(f"| Effective Date | {urs.get('effective_date', '—')} |")
    lines.append("")

    lines.append("**Equipment / System Information**")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Equipment Name | {urs.get('equipment_name', '—')} |")
    lines.append(f"| Equipment ID | {urs.get('equipment_id', '—')} |")
    lines.append(f"| Manufacturer | {urs.get('manufacturer', '—')} |")
    lines.append(f"| Model | {urs.get('model', '—')} |")
    lines.append(f"| Capacity | {urs.get('capacity', '—')} |")
    lines.append(f"| Category | {urs.get('category', '—')} |")
    lines.append(f"| Validation Type | {urs.get('validation_type', '—')} |")
    lines.append("")

    lines.append("**Approval**")
    lines.append("")
    lines.append("| Role | Name | Signature | Date |")
    lines.append("|------|------|-----------|------|")
    lines.append(f"| Prepared By | {urs.get('prepared_by', '—')} | | |")
    lines.append(f"| Reviewed By | {urs.get('reviewed_by', '—')} | | |")
    lines.append(f"| Approved By | {urs.get('approved_by', '—')} | | |")
    lines.append("")

    # Scope sections
    lines.append("## 1. Purpose")
    lines.append("")
    lines.append(urs.get("purpose") or "To define user requirements for the equipment/system.")
    lines.append("")

    lines.append("## 2. Intended Use")
    lines.append("")
    lines.append(urs.get("intended_use") or "As specified by the user department.")
    lines.append("")

    lines.append("## 3. Process Description")
    lines.append("")
    lines.append(urs.get("process_description") or "As defined in the manufacturing process.")
    lines.append("")

    # Requirements by section
    lines.append("## 4. User Requirements")
    lines.append("")

    # Group by section
    sections: dict[str, list[dict]] = {}
    for req in requirements:
        s = req.get("section", "General")
        if s not in sections:
            sections[s] = []
        sections[s].append(req)

    section_num = 4
    for section, reqs in sections.items():
        section_num_sub = list(sections.keys()).index(section) + 1
        lines.append(f"### 4.{section_num_sub} {section}")
        lines.append("")
        lines.append("| Req ID | Requirement | Priority | GMP Criticality | Verification Method | Acceptance Criteria |")
        lines.append("|--------|-------------|----------|-----------------|---------------------|---------------------|")
        for req in reqs:
            rid = req.get("req_id", "")
            requirement = req.get("requirement", "").replace("|", "\\|")
            priority = req.get("priority", "")
            gmp = req.get("gmp_criticality", "")
            verify = req.get("verification_method", "")
            criteria = req.get("acceptance_criteria", "").replace("|", "\\|")
            lines.append(f"| {rid} | {requirement} | {priority} | {gmp} | {verify} | {criteria} |")
        lines.append("")

        # Rationale sub-table
        lines.append("**Rationale and Regulatory References**")
        lines.append("")
        lines.append("| Req ID | Rationale | Regulatory Reference |")
        lines.append("|--------|-----------|----------------------|")
        for req in reqs:
            rid = req.get("req_id", "")
            rationale = req.get("rationale", "").replace("|", "\\|")
            reg_ref = req.get("regulatory_ref", "").replace("|", "\\|")
            lines.append(f"| {rid} | {rationale} | {reg_ref} |")
        lines.append("")

    # Summary statistics
    total = len(requirements)
    critical = sum(1 for r in requirements if r.get("priority") == "Critical")
    high = sum(1 for r in requirements if r.get("priority") == "High")
    gmp_critical = sum(1 for r in requirements if r.get("gmp_criticality") == "GMP-Critical")

    lines.append("## 5. Requirements Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Total Requirements | {total} |")
    lines.append(f"| Critical Priority | {critical} |")
    lines.append(f"| High Priority | {high} |")
    lines.append(f"| GMP-Critical | {gmp_critical} |")
    lines.append(f"| Sections | {len(sections)} |")
    lines.append("")

    lines.append("## 6. Regulatory Framework")
    lines.append("")
    lines.append("This URS has been prepared in accordance with:")
    lines.append("")
    lines.append("- ISPE GAMP 5 Second Edition")
    lines.append("- ASTM E2500")
    lines.append("- EU GMP Annex 11 (Computerised Systems)")
    lines.append("- EU GMP Annex 15 (Qualification and Validation)")
    lines.append("- 21 CFR Part 11 (Electronic Records and Signatures)")
    lines.append("- WHO GMP Technical Report Series")
    lines.append("- PIC/S GMP Guide")
    lines.append("- Schedule M (Indian GMP)")
    lines.append("- ALCOA+ Data Integrity Principles")
    lines.append("- ICH Q9 (Quality Risk Management)")
    lines.append("- ICH Q10 (Pharmaceutical Quality System)")
    lines.append("")

    lines.append("## 7. Traceability")
    lines.append("")
    lines.append("This URS is the parent document for the following qualification activities:")
    lines.append("")
    lines.append("| Phase | Document | Status |")
    lines.append("|-------|----------|--------|")
    lines.append("| Risk Assessment | Risk Assessment Report | TBD |")
    lines.append("| Design Qualification | DQ Protocol | TBD |")
    lines.append("| Factory Acceptance Test | FAT Protocol | TBD |")
    lines.append("| Site Acceptance Test | SAT Protocol | TBD |")
    lines.append("| Installation Qualification | IQ Protocol | TBD |")
    lines.append("| Operational Qualification | OQ Protocol | TBD |")
    lines.append("| Performance Qualification | PQ Protocol | TBD |")
    lines.append("| Validation Report | Validation Summary Report | TBD |")
    lines.append("")

    lines.append("---")
    lines.append("*Document generated by PharmaGPT URS Management Suite*")
    lines.append(f"*The Lean Architect Technologies*")

    return "\n".join(lines)

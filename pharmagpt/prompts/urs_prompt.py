"""URS — User Requirement Specification prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a User Requirement Specification.

    questionnaire keys
    ------------------
    doc_number, version, system_name, intended_use
    """
    eq      = equipment_data
    doc_no  = questionnaire.get("doc_number", "URS-001")
    ver     = questionnaire.get("version", "1.0")
    system  = questionnaire.get("system_name", eq["name"])
    use     = questionnaire.get("intended_use", "")
    today   = project_data["date"]

    pre = preamble("User Requirement Specification (URS)",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | System: {system} | Intended Use: {use}

Generate a complete URS using EXACTLY this markdown structure:

# USER REQUIREMENT SPECIFICATION

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {doc_no} |
| Version | {ver} |
| System / Equipment | {system} |
| Manufacturer | {eq['manufacturer']} |
| Department | {eq['department']} |
| Location | {eq['location']} |
| Intended Use | {use} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. PURPOSE AND SCOPE
[State why this URS is being written, what system it covers, and the regulatory drivers (21 CFR, EU GMP Annex 15, GAMP5)]

## 2. SYSTEM OVERVIEW
[2–3 paragraphs describing {system}, its intended function in the manufacturing/QC process, and its regulatory classification (GAMP5 Category)]

## 3. INTENDED USE
[Detailed description of how {system} will be used, including process step, user population, operating environment, and product types]

## 4. FUNCTIONAL REQUIREMENTS
Generate minimum 20 numbered functional requirements (FR-001 through FR-020+). Each must be:
- Specific, measurable, and testable
- Written in "shall" language
- Referenced to a regulatory clause where applicable

| Req. No. | Requirement | Priority | Regulatory Reference | Verification Method |
|----------|-------------|----------|---------------------|---------------------|
| FR-001 | The system shall [specific function] | Must Have | [21 CFR / EU GMP clause] | [IQ/OQ/PQ/Testing] |
[Continue through FR-020+, covering all functional aspects of {system}]

## 5. PERFORMANCE REQUIREMENTS
| Req. No. | Parameter | Specification | Unit | Verification |
|----------|-----------|--------------|------|-------------|
| PR-001 | [e.g. Throughput] | [value] | [unit] | OQ/PQ |
[Generate 8–10 performance requirements with numeric specifications]

## 6. ENVIRONMENTAL REQUIREMENTS
| Req. No. | Condition | Specification | Verification |
|----------|-----------|--------------|-------------|
| ER-001 | Operating Temperature | | |
| ER-002 | Relative Humidity | | |
| ER-003 | Cleanroom Classification | | |
[Generate 6–8 environmental requirements]

## 7. REGULATORY AND COMPLIANCE REQUIREMENTS
| Req. No. | Regulation / Standard | Clause | Requirement Description |
|----------|-----------------------|--------|------------------------|
| RC-001 | 21 CFR Part 211 | | |
| RC-002 | EU GMP Annex 15 | | |
| RC-003 | GAMP5 | | |
[List all applicable regulatory requirements for {system}]

## 8. SAFETY REQUIREMENTS
[Numbered list of safety requirements including: operator protection, emergency stop, electrical safety, chemical/pressure/thermal hazards, interlocks]

## 9. MAINTENANCE AND SERVICEABILITY REQUIREMENTS
[Requirements for preventive maintenance intervals, calibration, spare parts availability, service access, and MTBF/MTTR targets]

## 10. TRAINING REQUIREMENTS
[Requirements for operator training, qualification records, training documentation, and competency assessment]

## 11. DOCUMENTATION REQUIREMENTS
[Requirements for manuals, SOPs, IQ/OQ/PQ protocols, change control, and electronic records per 21 CFR Part 11 if applicable]

## 12. GLOSSARY
| Term | Definition |
|------|-----------|
[List 10–12 key terms used in this URS]

## 13. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| URS Author | | | |
| Quality Assurance | | | |
| Department Head | | | |
| Regulatory Affairs | | | |
| Engineering Manager | | | |

Write all sections completely and specifically for {system} ({eq['name']} {eq['model']} by {eq['manufacturer']}). Every requirement must be testable and regulation-referenced."""

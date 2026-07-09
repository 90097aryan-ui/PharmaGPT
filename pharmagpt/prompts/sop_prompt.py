"""SOP — Standard Operating Procedure prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Standard Operating Procedure.

    questionnaire keys
    ------------------
    doc_number, version, sop_title, department_owner
    """
    eq         = equipment_data
    doc_no     = questionnaire.get("doc_number", "SOP-001")
    ver        = questionnaire.get("version", "1.0")
    sop_title  = questionnaire.get("sop_title", f"Operation and Use of {eq['name']}")
    owner_dept = questionnaire.get("department_owner", eq["department"] or "Quality Assurance")
    today      = project_data["date"]

    pre = preamble("Standard Operating Procedure (SOP)", eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: SOP {doc_no} v{ver} | Title: {sop_title} | Owning Department: {owner_dept}

Generate a complete Standard Operating Procedure using EXACTLY this markdown structure:

# STANDARD OPERATING PROCEDURE

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {doc_no} |
| Version | {ver} |
| Title | {sop_title} |
| Owning Department | {owner_dept} |
| Equipment (if applicable) | {eq['name']} {eq['model']} |
| Effective Date | {today} |
| Review Frequency | Every 2 years, or upon process/equipment change |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description of Change | Author | Reviewer | Approver |
|-----|------|-----------------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. PURPOSE
[2–3 sentences describing what this SOP achieves and why it exists.]

## 2. SCOPE
[Define the area, personnel, equipment, and process steps this SOP applies to. State exclusions explicitly.]

## 3. RESPONSIBILITIES
| Role | Responsibility |
|------|----------------|
| Operator | |
| Shift Supervisor | |
| Quality Assurance | |
| Department Head | |

## 4. DEFINITIONS AND ABBREVIATIONS
| Term | Definition |
|------|-----------|
| SOP | Standard Operating Procedure |
| GMP | Good Manufacturing Practice |
| QA | Quality Assurance |
[Add 5–8 more relevant terms]

## 5. SAFETY PRECAUTIONS
[Numbered list of PPE requirements, hazards, and safety interlocks relevant to this procedure.]

## 6. MATERIALS AND EQUIPMENT REQUIRED
| Item | Specification / Grade |
|------|-----------------------|

## 7. PROCEDURE
Write a single numbered, step-by-step procedure (8-12 steps total) covering pre-operational checks, start-up, normal operation, and shutdown for {eq['name'] or sop_title}. Number the steps continuously from 1.

1. [Step]

## 8. IN-PROCESS CONTROLS
| Parameter | Specification | Frequency | Recorded By |
|-----------|---------------|-----------|-------------|

## 9. ABNORMAL SITUATION / DEVIATION HANDLING
[Describe what to do if a step fails, an alarm triggers, or an out-of-specification result occurs, including escalation path.]

## 10. RECORDS AND DOCUMENTATION
| Record / Form | Retention Period | Retained By |
|----------------|-------------------|-------------|

## 11. TRAINING REQUIREMENTS
[Describe who must be trained on this SOP before executing it, and how training is documented.]

## 12. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[List 4–6 relevant SOPs, guidelines, and regulatory documents]

## 13. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Author | | | |
| Department Head | | | |
| Quality Assurance Manager | | | |

## ANNEXURE A: BLANK LOGSHEET / FORM
| Date | Time | Parameter | Value | Operator | Remarks |
|------|------|-----------|-------|----------|---------|

Write all sections completely and specifically for {sop_title}."""

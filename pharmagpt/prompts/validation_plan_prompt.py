"""Validation Plan — Validation Master Plan / project-level Validation Plan prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Validation Plan (Validation Master Plan).

    questionnaire keys
    ------------------
    plan_number, version, validation_scope, risk_category
    """
    eq       = equipment_data
    plan_no  = questionnaire.get("plan_number", "VMP-001")
    ver      = questionnaire.get("version", "1.0")
    scope    = questionnaire.get("validation_scope", f"{eq['name']} and associated systems")
    risk_cat = questionnaire.get("risk_category", "Medium")
    today    = project_data["date"]

    pre = preamble("Validation Plan (Validation Master Plan)", eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: Plan {plan_no} v{ver} | Scope: {scope} | Risk Category: {risk_cat}

Generate a complete Validation Plan using EXACTLY this markdown structure:

# VALIDATION PLAN

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {plan_no} |
| Version | {ver} |
| Validation Scope | {scope} |
| Risk Category | {risk_cat} |
| Equipment / System | {eq['name']} {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Department | {eq['department']} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. PURPOSE
[3–4 sentences describing the purpose of this Validation Plan and what it governs.]

## 2. SCOPE
[Define the systems, equipment, processes, and facilities covered by this plan: {scope}. State exclusions explicitly.]

## 3. RESPONSIBILITIES
| Role | Responsibility |
|------|----------------|
| Validation Team Lead | |
| Quality Assurance | |
| Engineering | |
| Production / Operations | |
| Regulatory Affairs | |

## 4. DEFINITIONS AND ABBREVIATIONS
| Term | Definition |
|------|-----------|
| VMP | Validation Master Plan |
| URS | User Requirement Specification |
| DQ | Design Qualification |
| IQ | Installation Qualification |
| OQ | Operational Qualification |
| PQ | Performance Qualification |
[Add 4–6 more relevant terms]

## 5. VALIDATION APPROACH AND STRATEGY
[Describe the overall validation lifecycle to be followed: URS → Risk Assessment → DQ → FAT/SAT → IQ → OQ → PQ → Validation Report, and the rationale (risk-based approach per ICH Q9).]

## 6. RISK ASSESSMENT METHODOLOGY
[Describe the risk assessment approach (e.g. FMEA) used to determine the depth and rigor of qualification/validation activities, referencing risk category: {risk_cat}.]

## 7. SYSTEMS / EQUIPMENT COVERED BY THIS PLAN
| System / Equipment | Description | Risk Category | Qualification Required |
|---------------------|-------------|----------------|--------------------------|
| {eq['name']} {eq['model']} | | {risk_cat} | URS, DQ, IQ, OQ, PQ |
[Add related sub-systems or utilities as applicable]

## 8. VALIDATION DELIVERABLES AND ACCEPTANCE CRITERIA
[Describe what documents/deliverables will be produced at each lifecycle stage and the general acceptance philosophy for each.]

## 9. ROLES AND TRAINING REQUIREMENTS
[Describe personnel qualifications required to execute and approve validation activities under this plan.]

## 10. DEVIATION AND CHANGE CONTROL DURING VALIDATION
[Describe how deviations discovered during validation execution, and changes to validated systems, will be managed.]

## 11. REVALIDATION CRITERIA
[Describe the triggers for revalidation: equipment relocation, major change, periodic review interval, etc.]

## 12. SCHEDULE / TIMELINE
| Activity | Target Start | Target Completion | Responsible |
|----------|--------------|--------------------|-------------|
| URS | | | |
| DQ | | | |
| IQ | | | |
| OQ | | | |
| PQ | | | |
| Validation Report | | | |

## 13. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[List 6–8 relevant SOPs, regulatory guidelines (21 CFR Part 211/820, EU GMP Annex 15, GAMP5, ICH Q9/Q10)]

## 14. SUMMARY AND CONCLUSION
[Statement confirming this plan governs all subsequent validation deliverables for {scope}.]

## 15. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Validation Team Lead | | | |
| Quality Assurance Manager | | | |
| Engineering Head | | | |
| Site Head | | | |

## ANNEXURE A: VALIDATION LIFECYCLE FLOW DIAGRAM (DESCRIBED)
[Describe, in text form, the sequential flow: URS → Risk Assessment → DQ → FAT → SAT → IQ → OQ → PQ → Validation Report → Periodic Review.]

Write all sections completely and specifically for {scope}."""

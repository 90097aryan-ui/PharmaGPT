"""Validation Report — Validation Summary Report prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Validation Summary Report.

    questionnaire keys
    ------------------
    report_number, version, plan_reference, activities_covered
    """
    eq         = equipment_data
    report_no  = questionnaire.get("report_number", "VSR-001")
    ver        = questionnaire.get("version", "1.0")
    plan_ref   = questionnaire.get("plan_reference", "N/A")
    activities = questionnaire.get("activities_covered", "URS, DQ, IQ, OQ, PQ")
    today      = project_data["date"]

    pre = preamble("Validation Summary Report", eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: Report {report_no} v{ver} | Validation Plan Reference: {plan_ref} | Activities Covered: {activities}

Generate a complete Validation Summary Report using EXACTLY this markdown structure:

# VALIDATION SUMMARY REPORT

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {report_no} |
| Version | {ver} |
| Validation Plan Reference | {plan_ref} |
| Equipment / System | {eq['name']} {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Department | {eq['department']} |
| Activities Covered | {activities} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. PURPOSE
[2–3 sentences describing the purpose of this Validation Summary Report and what it certifies.]

## 2. SCOPE
[State the systems/equipment and validation activities summarised in this report: {activities}, referencing plan {plan_ref}.]

## 3. RESPONSIBILITIES
| Role | Responsibility |
|------|----------------|
| Validation Team Lead | |
| Quality Assurance | |
| Engineering | |

## 4. DEFINITIONS AND ABBREVIATIONS
| Term | Definition |
|------|-----------|
| VSR | Validation Summary Report |
| URS | User Requirement Specification |
| IQ | Installation Qualification |
| OQ | Operational Qualification |
| PQ | Performance Qualification |
[Add 4–6 more relevant terms]

## 5. SUMMARY OF VALIDATION ACTIVITIES PERFORMED
Summarise the outcome of each stage of the validation lifecycle for {eq['name']} {eq['model']}:

| Stage | Protocol / Document No. | Completion Date | Result |
|-------|--------------------------|------------------|--------|
| URS | | | Approved |
| DQ | | | Approved |
| IQ | | | Pass |
| OQ | | | Pass |
| PQ | | | Pass |

[Write 1 paragraph per stage summarising key activities and outcomes.]

## 6. DEVIATIONS ENCOUNTERED DURING VALIDATION
| Deviation No. | Stage | Description | Root Cause | Resolution | Impact on Validation |
|-----------------|-------|-------------|------------|------------|------------------------|
[List deviations, or state "No deviations were recorded during execution of this validation." if none.]

## 7. NON-CONFORMANCES AND CORRECTIVE ACTIONS
[Describe any non-conformances identified and the corrective actions taken, or state none were identified.]

## 8. TEST RESULTS SUMMARY
| Parameter | Total Tests | Passed | Failed | Retested / Resolved |
|-----------|--------------|--------|--------|-----------------------|
| IQ | | | | |
| OQ | | | | |
| PQ | | | | |

## 9. TRACEABILITY TO USER REQUIREMENTS
[Confirm that all URS requirements were tested and met, referencing the traceability matrix maintained in the OQ/PQ protocols.]

## 10. CONCLUSION AND VALIDATION STATUS
[State the overall validated status of {eq['name']} {eq['model']} — VALIDATED / VALIDATED WITH RESTRICTIONS / NOT VALIDATED — and the basis for this conclusion.]

| Parameter | Result |
|-----------|--------|
| Overall Validation Status | VALIDATED |
| Release for Routine Use | Approved / Conditional / Not Approved |

## 11. PERIODIC REVIEW REQUIREMENTS
[State the periodic review interval and revalidation triggers for this equipment/system going forward.]

## 12. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[List the URS, DQ, IQ, OQ, PQ protocols and any relevant SOPs/regulatory guidelines referenced]

## 13. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Validation Team Lead | | | |
| Quality Assurance Manager | | | |
| Engineering Head | | | |
| Site Head | | | |

## ANNEXURE A: RAW DATA AND CERTIFICATE REFERENCES
| Reference No. | Description | Location |
|-----------------|-------------|----------|

Write all sections completely and specifically for {eq['name']} {eq['model']}."""

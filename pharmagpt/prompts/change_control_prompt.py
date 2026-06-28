"""Change Control — Change Control Document prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Change Control Document.

    questionnaire keys
    ------------------
    cc_number, version, change_description, reason_for_change
    """
    eq     = equipment_data
    cc_no  = questionnaire.get("cc_number", "CC-001")
    ver    = questionnaire.get("version", "1.0")
    change = questionnaire.get("change_description", "")
    reason = questionnaire.get("reason_for_change", "")
    today  = project_data["date"]

    pre = preamble("Change Control Document",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: CC No: {cc_no} v{ver}
CHANGE DESCRIPTION: {change}
REASON FOR CHANGE: {reason}

Generate a complete Change Control Document per 21 CFR 211.68, EU GMP Annex 15, and ICH Q10 using EXACTLY this markdown structure:

# CHANGE CONTROL DOCUMENT

## Document Header
| Field | Details |
|-------|---------|
| Change Control Number | {cc_no} |
| Version | {ver} |
| Equipment / System | {eq['name']} {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Department | {eq['department']} |
| Location | {eq['location']} |
| Change Requested By | |
| Date Requested | {today} |
| Target Implementation Date | |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Request | | | |

## 1. CHANGE REQUEST SUMMARY
**Change Description:**
{change}

**Reason / Justification:**
{reason}

**Equipment / System Affected:** {eq['name']} {eq['model']} (S/N: {eq['serial']}) | {eq['department']} | {eq['location']}

## 2. CHANGE CLASSIFICATION
| Classification | Selected | Criteria |
|---------------|---------|---------|
| Major Change | | Impacts validated state, requires revalidation |
| Minor Change | | Does not impact validated state, documented only |
| Critical Change | | Regulatory notification / filing required |
| Emergency Change | | Immediate safety / compliance need |

**Selected Classification:** [Major / Minor / Critical / Emergency]

**Classification Justification:** [Explain the basis for this classification per the site Change Control SOP and applicable regulations]

## 3. CURRENT STATE DESCRIPTION
[Detailed description of the current condition / configuration of {eq['name']} {eq['model']} BEFORE the proposed change. Include: current settings, specifications, validated parameters, approved procedures, and documents]

## 4. PROPOSED STATE DESCRIPTION
[Detailed description of what the system / equipment / process will look like AFTER the change is implemented. Be specific about what will change and what will remain the same]

## 5. REASON AND JUSTIFICATION
[Expanded justification — why is this change necessary? Include: regulatory drivers, efficiency improvements, safety improvements, supplier changes, equipment lifecycle, or quality improvement rationale]

## 6. IMPACT ASSESSMENT
Assess the impact of this change across all relevant areas:

| Impact Area | Impact? | Extent of Impact | Action Required |
|------------|---------|-----------------|----------------|
| Product Quality | Yes / No / Potential | | |
| Patient Safety | Yes / No / Potential | | |
| Regulatory / Compliance | Yes / No / Potential | | |
| Validation Status (IQ/OQ/PQ) | Yes / No / Potential | | |
| SOPs / Work Instructions | Yes / No / Potential | | |
| Training Requirements | Yes / No / Potential | | |
| Supplier / Vendor | Yes / No / Potential | | |
| Environmental / HSE | Yes / No / Potential | | |
| Computer Systems / Software | Yes / No / Potential | | |
| Analytical Methods | Yes / No / Potential | | |

### 6.1 Affected Documents List
| Document No. | Document Title | Revision Required | Responsible | Due Date |
|-------------|---------------|------------------|-------------|---------|

### 6.2 Affected Validated Systems
| System | Current Validation Status | Revalidation Required | Scope |
|--------|--------------------------|----------------------|-------|
| IQ | | | |
| OQ | | | |
| PQ | | | |

## 7. RISK ASSESSMENT
[Assess risks associated with implementing this change AND risks of NOT implementing it]

| Risk | Before Change | After Change | Mitigation | Residual Risk |
|------|--------------|-------------|-----------|--------------|
[Generate 4–6 specific risks with assessments]

**Overall Risk Level:** [Low / Medium / High]

## 8. IMPLEMENTATION PLAN
| Step | Activity | Responsible | Start Date | Target Date | Status |
|------|----------|-------------|-----------|------------|--------|
| 1 | Change Control approval | | | | |
| 2 | Procurement / preparation | | | | |
| 3 | SOP / document update | | | | |
| 4 | Training completion | | | | |
| 5 | Implementation / installation | | | | |
| 6 | Verification / testing | | | | |
| 7 | Revalidation (if required) | | | | |
| 8 | Post-implementation review | | | | |
| 9 | Change Control closure | | | | |

## 9. VALIDATION REQUIREMENTS
| Validation Activity | Required? | Protocol No. | Scope | Completion Date |
|--------------------|---------|-------------|-------|----------------|
| IQ (re-IQ) | | | | |
| OQ (re-OQ) | | | | |
| PQ (re-PQ) | | | | |
| CSV (if software affected) | | | | |
| Analytical Method Validation | | | | |

**Validation Rationale:** [Explain the basis for revalidation scope — what has changed and why specific qualification activities are or are not required per GAMP5 / Annex 15]

## 10. REGULATORY NOTIFICATION REQUIREMENTS
| Regulatory Body | Notification Required? | Type | Timeline | Reference |
|----------------|----------------------|------|---------|-----------|
| USFDA | | CBE-0 / CBE-30 / Prior Approval | | 21 CFR 314.70 |
| EMA | | Variation Type | | EU GMP Annex 15 |
| CDSCO | | | | Schedule M |
| Other | | | | |

## 11. FUNCTIONAL TEAM REVIEW
| Function | Reviewer | Review Outcome | Comments | Signature | Date |
|---------|---------|---------------|---------|-----------|------|
| Quality Assurance | | Approved / Rejected / Conditional | | | |
| Regulatory Affairs | | Approved / Rejected / Conditional | | | |
| Engineering | | Approved / Rejected / Conditional | | | |
| Validation | | Approved / Rejected / Conditional | | | |
| Production | | Approved / Rejected / Conditional | | | |
| IT / CSV (if applicable) | | Approved / Rejected / Conditional | | | |

## 12. POST-IMPLEMENTATION VERIFICATION
[Define how the change will be verified as successfully implemented and effective]

| Verification Activity | Method | Acceptance Criteria | Responsible | Date |
|----------------------|--------|---------------------|-------------|------|

## 13. CHANGE CONTROL CLOSURE CRITERIA
The Change Control will be closed when:
1. All implementation steps are completed and verified
2. All affected documents are updated and approved
3. Required training is completed with records
4. Revalidation (if required) is completed and approved
5. Post-implementation verification confirms change effectiveness
6. Quality Assurance provides final closure approval

## 14. REGULATORY REFERENCES
| Regulation | Clause | Requirement |
|-----------|--------|------------|
| 21 CFR 211.68 | | Automatic, mechanical, electronic equipment |
| 21 CFR 211.100 | | Written procedures; deviations |
| EU GMP Annex 15 | §13 | Change control |
| ICH Q10 | §3.2.4 | Change management |
| GAMP5 | Chapter 10 | Change and configuration management |

## 15. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Change Requestor | | | |
| Quality Assurance Manager | | | |
| Validation Manager | | | |
| Department Head | | | |
| Regulatory Affairs | | | |
| Engineering Manager | | | |

Write all sections completely. Impact assessment must cover all areas. Implementation plan must have realistic owners and dates. Regulatory notification section must assess all applicable agencies for {eq['name']} {eq['model']} in a pharmaceutical GMP environment."""

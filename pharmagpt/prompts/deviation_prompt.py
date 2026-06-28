"""Deviation — Deviation Report prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Deviation Report.

    questionnaire keys
    ------------------
    deviation_number, version, category, description
    """
    eq       = equipment_data
    dev_no   = questionnaire.get("deviation_number", "DEV-001")
    ver      = questionnaire.get("version", "1.0")
    category = questionnaire.get("category", "Unplanned")
    desc     = questionnaire.get("description", "")
    today    = project_data["date"]

    pre = preamble("Deviation Report",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: Deviation No: {dev_no} | Category: {category}
DEVIATION DESCRIPTION: {desc}

Generate a complete Deviation Report per 21 CFR 211, EU GMP Chapter 6, and Schedule M using EXACTLY this markdown structure:

# DEVIATION REPORT

## Document Header
| Field | Details |
|-------|---------|
| Deviation Number | {dev_no} |
| Version | {ver} |
| Category | {category} |
| Related Equipment | {eq['name']} {eq['model']} |
| Department | {eq['department']} |
| Location | {eq['location']} |
| Date of Deviation | |
| Date Reported | {today} |
| Reported By | |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Issue | | | |

## 1. DEVIATION DESCRIPTION
**What happened:**
{desc}

**When discovered:** [Date and time of discovery]

**Where:** {eq['location']} — {eq['department']}

**Who discovered it:** [Role/name of person who found the deviation]

**How discovered:** [Describe detection method — routine monitoring, in-process check, audit, complaint, etc.]

**Equipment involved:** {eq['name']} {eq['model']} (S/N: {eq['serial']})

## 2. DEVIATION CLASSIFICATION
| Classification | Selected | Justification |
|---------------|---------|--------------|
| Planned Deviation | {'✓' if 'planned' in category.lower() else ' '} | |
| Unplanned Deviation | {'✓' if 'unplanned' in category.lower() else ' '} | |
| Critical | {'✓' if 'critical' in category.lower() else ' '} | |
| Major | {'✓' if 'major' in category.lower() else ' '} | |
| Minor | {'✓' if 'minor' in category.lower() else ' '} | |

**Classification Justification:** [Explain why this classification was assigned per the site deviation classification SOP]

## 3. IMMEDIATE ACTIONS TAKEN
[Actions taken immediately upon deviation discovery to contain the impact and prevent further non-compliance]

| Action Taken | Taken By | Date / Time | Comments |
|-------------|---------|------------|---------|
| | | | |

## 4. IMPACT ASSESSMENT
### 4.1 Product Quality Impact
| Impact Area | Assessment | Risk Level |
|------------|-----------|-----------|
| Product quality attributes | | |
| Stability | | |
| Sterility / Contamination | | |
| Identity / Potency | | |
| Patient safety | | |

### 4.2 Regulatory Impact
[Assess whether this deviation requires regulatory notification, NDA/ANDA supplement, or other regulatory action]

### 4.3 Scope of Impact
[Identify all batches, lots, products, and operations potentially affected by this deviation]

## 5. BATCHES / LOTS AFFECTED
| Batch / Lot No. | Product | Manufacturing Date | Quantity | Disposition | Comments |
|----------------|---------|-------------------|---------|------------|---------|
[List all affected batches with current disposition status]

## 6. PRELIMINARY ROOT CAUSE
[Initial hypothesis of the root cause — to be confirmed during full investigation. Note: final root cause will be determined in Section 8]

## 7. INVESTIGATION FINDINGS
[Detailed investigation of the deviation. Include:
- Timeline of events
- Equipment / system review (calibration status, maintenance records for {eq['name']} {eq['model']})
- Personnel interviews summary
- Environmental monitoring data
- Process parameter review
- Comparison with historical data
- Laboratory investigation results (if applicable)]

### 7.1 Evidence Collected
| Evidence Item | Source | Finding | Relevance |
|--------------|--------|---------|----------|
| | | | |

### 7.2 Root Cause Investigation Methods Used
[Describe investigation tools: 5-Why, Fishbone, fault tree analysis, timeline analysis]

## 8. FINAL ROOT CAUSE DETERMINATION
[State the confirmed root cause with supporting evidence. Be specific — not generic statements]

**Root Cause Statement:** [Specific, factual root cause tied to evidence]

**Root Cause Category:**
- [ ] Human Error
- [ ] Equipment / Instrument Failure
- [ ] Process / Method Issue
- [ ] Material / Raw Material
- [ ] Environmental
- [ ] System / Software
- [ ] Other: ___________

## 9. CAPA ACTIONS INITIATED
| CAPA No. | Description | Type (CA/PA) | Owner | Due Date |
|----------|-------------|-------------|-------|---------|
[Link to CAPA reference — generate 2–4 actions addressing the root cause]

## 10. BATCH / LOT DISPOSITION RECOMMENDATION
| Batch / Lot No. | Recommended Disposition | Justification | Approved By | Date |
|----------------|------------------------|--------------|-------------|------|
[Options: Release / Rework / Retest / Reject / Quarantine pending further investigation]

**Disposition Rationale:** [GMP-based justification for the recommended disposition of all affected batches]

## 11. LESSONS LEARNED
[Key learnings from this deviation that can prevent similar events in other areas or products]

## 12. REGULATORY REFERENCES
| Regulation | Clause | Requirement |
|-----------|--------|------------|
| 21 CFR 211 | §211.192 | Investigation of unexplained discrepancies |
| EU GMP Chapter 6 | §6.14–6.17 | Deviations and investigation |
| Schedule M | | [Applicable clause] |
| ICH Q10 | | Quality system deviation management |

## 13. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Deviation Initiator | | | |
| Quality Assurance Manager | | | |
| Department Head | | | |
| Regulatory Affairs (if required) | | | |

Write all sections completely. The investigation must be thorough and specific to {eq['name']} {eq['model']} in a pharmaceutical GMP environment. Batch disposition must be clearly justified."""

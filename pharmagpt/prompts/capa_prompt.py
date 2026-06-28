"""CAPA — Corrective and Preventive Action Report prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a CAPA Report.

    questionnaire keys
    ------------------
    capa_number, version, capa_source, description
    """
    eq      = equipment_data
    capa_no = questionnaire.get("capa_number", "CAPA-001")
    ver     = questionnaire.get("version", "1.0")
    source  = questionnaire.get("capa_source", "Internal Audit / Deviation")
    desc    = questionnaire.get("description", "")
    today   = project_data["date"]

    pre = preamble("Corrective and Preventive Action (CAPA) Report",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: CAPA No: {capa_no} v{ver} | Source: {source}
ISSUE DESCRIPTION: {desc}

Generate a complete CAPA Report per 21 CFR 820.100, EU GMP Chapter 8, and ICH Q10 using EXACTLY this markdown structure:

# CORRECTIVE AND PREVENTIVE ACTION (CAPA) REPORT

## Document Header
| Field | Details |
|-------|---------|
| CAPA Number | {capa_no} |
| Version | {ver} |
| CAPA Source | {source} |
| Related Equipment | {eq['name']} {eq['model']} |
| Department | {eq['department']} |
| Initiated By | |
| Date Initiated | {today} |
| Target Closure Date | |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Issue | | | |

## 1. PROBLEM STATEMENT
[Clear, concise description of the non-conformance or issue. Answer: What happened? When? Where? Who was involved? How was it discovered? What is the impact?]

**Issue:** {desc}

**Affected Equipment:** {eq['name']} {eq['model']} | {eq['department']} | {eq['location']}

## 2. SCOPE AND IMPACT ASSESSMENT
| Impact Area | Assessment | Severity |
|------------|-----------|---------|
| Product Quality | | |
| Patient Safety | | |
| Regulatory Compliance | | |
| Batch / Lot Affected | | |
| Financial Impact | | |

[Narrative: describe the scope of the issue — how many batches, products, or operations are affected]

## 3. IMMEDIATE CONTAINMENT ACTIONS
[Actions taken immediately upon discovery to prevent further impact — quarantine, production hold, customer notification, etc.]

| Action | Responsible | Completed By | Status |
|--------|-------------|-------------|--------|
| | | | |

## 4. ROOT CAUSE ANALYSIS

### 4.1 Ishikawa (Fishbone) Diagram Analysis
Analyse the following cause categories for contributing factors:

**Man (Personnel):**
- [Identify personnel-related causes]

**Machine (Equipment):**
- [Identify equipment-related causes — specific to {eq['name']} {eq['model']}]

**Method (Process):**
- [Identify process / SOP-related causes]

**Material:**
- [Identify material / raw material causes]

**Measurement:**
- [Identify measurement / calibration causes]

**Environment:**
- [Identify environmental / facility causes]

### 4.2 Five-Why Analysis
| Why # | Question | Answer |
|-------|---------|--------|
| Why 1 | Why did [problem] occur? | |
| Why 2 | Why did [cause 1] happen? | |
| Why 3 | Why did [cause 2] happen? | |
| Why 4 | Why did [cause 3] happen? | |
| Why 5 | Why did [cause 4] happen? | |

**Root Cause Determination:**
[State the verified root cause — specific, factual, and linked to evidence]

## 5. CORRECTIVE ACTIONS
Actions to eliminate the identified root cause:

| CA No. | Corrective Action | Owner | Due Date | Evidence Required | Status |
|--------|------------------|-------|----------|------------------|--------|
| CA-01 | | | | | |
| CA-02 | | | | | |
[Generate 4–6 specific corrective actions with owners and due dates]

## 6. PREVENTIVE ACTIONS
Actions to prevent recurrence of this or similar issues:

| PA No. | Preventive Action | Owner | Due Date | Evidence Required | Status |
|--------|------------------|-------|----------|------------------|--------|
| PA-01 | | | | | |
| PA-02 | | | | | |
[Generate 3–5 preventive actions]

## 7. IMPLEMENTATION PLAN
| Phase | Action | Owner | Start Date | Target Date | Completion Date | Status |
|-------|--------|-------|-----------|------------|----------------|--------|
| 1 | Immediate containment | | | | | |
| 2 | Root cause investigation | | | | | |
| 3 | Corrective action implementation | | | | | |
| 4 | Preventive action implementation | | | | | |
| 5 | Effectiveness check | | | | | |
| 6 | CAPA closure | | | | | |

## 8. EFFECTIVENESS CHECK
| Check Criterion | Method | Timeframe | Acceptable Result | Actual Result | Status |
|----------------|--------|---------|------------------|--------------|--------|
[Define how success of the CAPA will be verified — KPIs, audit findings, recurrence monitoring period]

**Effectiveness Check Period:** [e.g., 3 months post-implementation]

## 9. CAPA CLOSURE CRITERIA
The CAPA will be closed when:
1. All corrective actions are completed with evidence
2. All preventive actions are implemented and documented
3. Effectiveness check confirms non-recurrence
4. All supporting documentation is filed and approved
5. Quality Assurance provides closure sign-off

## 10. REGULATORY REFERENCES
| Regulation | Clause | Requirement |
|-----------|--------|------------|
| 21 CFR 820.100 | | CAPA procedure requirements |
| EU GMP Chapter 8 | | Complaints and product recalls |
| ICH Q10 | §3.2 | Corrective action and preventive action system |
| Schedule M | | [Applicable Indian GMP clause] |

## 11. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| CAPA Initiator | | | |
| Quality Assurance Manager | | | |
| Department Head | | | |
| Validation Manager (if applicable) | | | |
| Regulatory Affairs (if required) | | | |

Write all sections completely. Root cause analysis must be thorough, with specific causes tied to {eq['name']} {eq['model']} and the pharmaceutical GMP context. Actions must be specific with named owners and realistic due dates."""

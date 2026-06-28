"""SAT — Site Acceptance Testing Protocol prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Site Acceptance Testing Protocol.

    questionnaire keys
    ------------------
    doc_number, version, sat_date
    """
    eq       = equipment_data
    doc_no   = questionnaire.get("doc_number", "SAT-001")
    ver      = questionnaire.get("version", "1.0")
    sat_date = questionnaire.get("sat_date", project_data["date"])
    today    = project_data["date"]

    pre = preamble("Site Acceptance Testing (SAT) Protocol",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | SAT Date: {sat_date}

Generate a complete SAT Protocol using EXACTLY this markdown structure:

# SITE ACCEPTANCE TESTING PROTOCOL

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {doc_no} |
| Version | {ver} |
| Equipment | {eq['name']} {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Serial Number | {eq['serial']} |
| Installation Site | {eq['location']} |
| Department | {eq['department']} |
| SAT Date | {sat_date} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. OBJECTIVE
[Purpose of SAT — verify equipment performs correctly after shipment and installation at {eq['location']}, referencing FAT results. Cite EU GMP Annex 15 §8, GAMP5 §7.3]

## 2. SCOPE
[Equipment, site location, what is verified at site vs. what was verified at FAT]

## 3. SAT TEAM
| Name | Organization | Role | Signature |
|------|-------------|------|-----------|
[Site QA, Validation Engineer, Manufacturer Service Engineer, Department Representative]

## 4. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[FAT Protocol, URS, DQ Report, IQ prerequisites, SOPs, regulatory guidelines]

## 5. SITE READINESS CHECKLIST
| Item | Requirement | Status | Comments |
|------|-------------|--------|---------|
| Utility connections verified | | | |
| Site environmental conditions | | | |
| Area cleaning completed | | | |
| Safety hazard assessment done | | | |
| Calibrated instruments available | | | |
| Trained personnel designated | | | |
[Add 6–8 site-readiness items]

## 6. TRANSIT DAMAGE INSPECTION
| Inspection Item | Expected Condition | Observed | Status | Comments |
|----------------|-------------------|---------|--------|---------|
| Packaging integrity | No damage | | | |
| Equipment exterior | No dents/scratches | | | |
| Instrument panels | Intact | | | |
| All components present | Per packing list | | | |
[Add relevant inspection items]

## 7. RE-COMMISSIONING TESTS AT SITE
Generate 6+ functional tests that verify the equipment performs at site after re-installation. Mirror FAT test categories but executed at {eq['location']}.

### SAT Test 01: [Descriptive Name]
**Purpose:** [What this test verifies at site — reference corresponding FAT test]
**FAT Reference:** [FAT Test XX]
**Regulatory Reference:** [Applicable clause]

**Procedure:**
1. [Step-by-step procedure at site]

**Acceptance Criteria:** [Same as FAT where applicable]

| Parameter | FAT Result | SAT Result | Pass/Fail | Comments |
|-----------|-----------|-----------|-----------|---------|
| | | | | |

---

[Continue SAT Test 02 through 06+]

## 8. FAT vs. SAT COMPARISON TABLE
| Test / Parameter | FAT Specification | FAT Result | SAT Result | Match | Comments |
|-----------------|------------------|-----------|-----------|-------|---------|
[Map all critical FAT parameters to SAT results to confirm no degradation during transit/installation]

## 9. SITE PUNCH LIST
| Item No. | Description | Severity | Responsible | Target Date | Status |
|----------|-------------|---------|-------------|------------|--------|

## 10. SAT CONCLUSION
| SAT Overall Status | ACCEPTED / CONDITIONALLY ACCEPTED / REJECTED |
|-------------------|---------------------------------------------|
| Open Punch List Items | |
| Recommendation | Proceed to IQ / Resolve punch list first |

## 11. APPROVAL SIGNATURES
| Role | Printed Name | Organization | Signature | Date |
|------|-------------|-------------|-----------|------|
| Quality Assurance Representative | | | | |
| Validation Engineer | | | | |
| Department Head | | | | |
| Manufacturer Service Engineer | | | | |

Write all sections completely and specifically for {eq['name']} {eq['model']} installed at {eq['location']}."""

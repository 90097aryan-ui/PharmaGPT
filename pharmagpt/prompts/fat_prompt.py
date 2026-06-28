"""FAT — Factory Acceptance Testing Protocol prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Factory Acceptance Testing Protocol.

    questionnaire keys
    ------------------
    doc_number, version, fat_date, fat_location
    """
    eq       = equipment_data
    doc_no   = questionnaire.get("doc_number", "FAT-001")
    ver      = questionnaire.get("version", "1.0")
    fat_date = questionnaire.get("fat_date", project_data["date"])
    location = questionnaire.get("fat_location", eq["manufacturer"] + " facility")
    today    = project_data["date"]

    pre = preamble("Factory Acceptance Testing (FAT) Protocol",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | FAT Date: {fat_date} | FAT Location: {location}

Generate a complete FAT Protocol using EXACTLY this markdown structure:

# FACTORY ACCEPTANCE TESTING PROTOCOL

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {doc_no} |
| Version | {ver} |
| Equipment | {eq['name']} {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Serial Number | {eq['serial']} |
| FAT Date | {fat_date} |
| FAT Location | {location} |
| Department | {eq['department']} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. OBJECTIVE
[Purpose of FAT, regulatory basis (EU GMP Annex 15 §7, GAMP5 §7.3), and benefit of performing acceptance testing at the manufacturer's facility]

## 2. SCOPE
[Equipment covered, sub-systems included, and what is deferred to SAT/IQ/OQ]

## 3. FAT TEAM
| Name | Organization | Role | Signature |
|------|-------------|------|-----------|
[Customer QA representative, Validation Engineer, Manufacturer FAT coordinator, etc.]

## 4. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[URS, DQ report, vendor drawings, applicable SOPs, regulatory guidelines]

## 5. DOCUMENTATION REVIEW
Checklist of documents to be reviewed and accepted at FAT:

| Document | Expected | Received | Status | Comments |
|----------|---------|---------|--------|---------|
| CE / UL Certificate | | | | |
| Material Certificates (product-contact) | | | | |
| Calibration Certificates | | | | |
| Factory Test Records | | | | |
| Software / Firmware Version Record | | | | |
| P&ID / Electrical Schematics | | | | |
| Operation and Maintenance Manual | | | | |
[Add 4–6 more relevant documents]

## 6. PHYSICAL INSPECTION
| Inspection Item | Specification | Observed | Pass/Fail | Comments |
|----------------|--------------|---------|-----------|---------|
| Overall dimensions | Per DQ/URS | | | |
| Finish quality (Ra value) | | | | |
| Material identification markings | | | | |
| Safety labels and warnings | | | | |
| Instrument tags / identification | | | | |
[Add 6–8 more inspection items specific to {eq['name']} {eq['model']}]

## 7. FUNCTIONAL TESTS
Generate 8+ functional test cases specific to {eq['name']} {eq['model']} to be performed at {location}. Each must follow this format:

### FAT Test 01: [Descriptive Name]
**Purpose:** [What this test verifies and link to URS requirement]
**URS Reference:** [FR-XXX]
**Regulatory Reference:** [Applicable clause]

**Procedure:**
1. [Step-by-step test procedure]

**Acceptance Criteria:** [Specific, measurable pass/fail criteria]

| Parameter | Specification | Observed | Pass/Fail | Witness |
|-----------|--------------|---------|-----------|---------|
| | | | | |

---

[Continue FAT Test 02 through 08+]

## 8. PERFORMANCE TESTS
[2–3 performance tests demonstrating the equipment meets throughput, accuracy, and precision requirements from the URS]

## 9. FACTORY PUNCH LIST
| Item No. | Description of Deficiency | Severity | Responsible | Target Date | Status |
|----------|--------------------------|---------|-------------|------------|--------|
[Template for capturing any deficiencies found during FAT]

## 10. FAT SIGN-OFF
[Statement that the customer team has witnessed and accepted the FAT results, subject to resolution of punch list items]

| FAT Overall Status | ACCEPTED / CONDITIONALLY ACCEPTED / REJECTED |
|-------------------|---------------------------------------------|
| Open Punch List Items | |
| Conditions for Shipment | |

## 11. APPROVAL SIGNATURES
| Role | Printed Name | Organization | Signature | Date |
|------|-------------|-------------|-----------|------|
| Customer — QA Representative | | | | |
| Customer — Validation Engineer | | | | |
| Manufacturer — FAT Coordinator | | | | |

Write all sections completely and specifically for {eq['name']} {eq['model']} by {eq['manufacturer']} tested at {location}."""

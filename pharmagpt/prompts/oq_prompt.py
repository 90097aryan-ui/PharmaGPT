"""OQ — Operational Qualification Protocol prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for an Operational Qualification Protocol.

    questionnaire keys
    ------------------
    protocol_number, version, product, batch_size, urs_reference
    """
    eq    = equipment_data
    proto = questionnaire.get("protocol_number", "OQ-001")
    ver   = questionnaire.get("version", "1.0")
    product = questionnaire.get("product", "N/A")
    batch   = questionnaire.get("batch_size", "N/A")
    urs_ref = questionnaire.get("urs_reference", "N/A")
    today   = project_data["date"]

    pre = preamble("Operational Qualification (OQ) Protocol",
                   eq, knowledge_base, project_data)

    return f"""{pre}

DOCUMENT DETAILS:
- Protocol Number : {proto}
- Version         : {ver}
- Product         : {product}
- Batch Size      : {batch}
- URS Reference   : {urs_ref}

Generate the complete OQ Protocol using EXACTLY this markdown structure:

# OPERATIONAL QUALIFICATION PROTOCOL

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {proto} |
| Version | {ver} |
| Equipment Name | {eq['name']} |
| Model / Type | {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Serial Number | {eq['serial']} |
| Location | {eq['location']} |
| Department | {eq['department']} |
| Product | {product} |
| Batch Size | {batch} |
| URS Reference | {urs_ref} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description of Change | Author | Reviewer | Approver |
|-----|------|-----------------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. OBJECTIVE
[Write 3–4 sentences: state the purpose of this OQ protocol, what it demonstrates, and the regulatory basis for performing OQ.]

## 2. SCOPE
[Define what is covered (equipment, functions, parameters) and explicitly state what is excluded.]

## 3. RESPONSIBILITIES
| Role | Responsibility |
|------|----------------|
| Validation Engineer | |
| Quality Assurance | |
| Department Head | |
| Instrument Technician | |

## 4. DEFINITIONS AND ABBREVIATIONS
| Term | Definition |
|------|-----------|
| OQ | Operational Qualification |
| GMP | Good Manufacturing Practice |
| SOP | Standard Operating Procedure |
[Add 6–8 more terms relevant to this equipment type]

## 5. EQUIPMENT DESCRIPTION
[2–3 paragraphs describing the equipment, its intended function, technical specifications, and role in the manufacturing/QC process]

## 6. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[List 6–8 relevant SOPs, guidelines, regulatory documents, and manufacturer manuals]

## 7. PREREQUISITES
[Numbered list of all conditions that must be met before executing this OQ — IQ completion, calibration certificates, trained personnel, environment conditions, etc.]

## 8. OPERATIONAL QUALIFICATION TESTS
Generate exactly 10 comprehensive test cases covering ALL critical operational parameters of {eq['name']} {eq['model']}. Each test must follow this format:

### Test OQ-01: [Descriptive Name — e.g. "Operational Range Verification"]
**Purpose:** [What this test verifies and why it is critical]
**Regulatory Reference:** [e.g., 21 CFR 211.68, EU GMP Annex 15 §9.3, GAMP5 §7.4]
**Required Test Equipment / Materials:**
- [Item 1]
- [Item 2]

**Procedure:**
1. [Detailed step — include settings, readings, wait times]
2. [Continue for 5–8 steps]

**Acceptance Criteria:** [Specific, measurable, numeric criteria]

| Test # | Parameter | Specification | Observed Value | Pass / Fail | Performed By | Date |
|--------|-----------|--------------|----------------|-------------|--------------|------|
| OQ-01.1 | | | | | | |
| OQ-01.2 | | | | | | |

---

[Continue with OQ-02 through OQ-10, covering all critical operational parameters]

## 9. DEVIATION HANDLING
[Procedure for identifying, recording, and managing deviations encountered during OQ execution. Include escalation path and impact on protocol status.]

## 10. SUMMARY AND CONCLUSION
[Template paragraph for the validation team to record overall pass/fail status, any deviations, and recommendation for PQ or production use.]

| Parameter | Result |
|-----------|--------|
| Total Tests Executed | |
| Tests Passed | |
| Tests Failed | |
| Open Deviations | |
| OQ Status | PASS / FAIL |

## 11. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Protocol Author | | | |
| Quality Assurance Manager | | | |
| Validation Manager | | | |
| Head of Department | | | |
| Regulatory Affairs (if required) | | | |

## ANNEXURE A: CALIBRATION STATUS OF TEST INSTRUMENTS
| Instrument | ID No. | Cal. Due Date | Certificate No. | Calibrated By |
|------------|--------|--------------|-----------------|---------------|

## ANNEXURE B: TRAINING RECORDS
| Personnel Name | Designation | Training Date | Signature |
|----------------|-------------|---------------|-----------|

Write every section completely and specifically for {eq['name']} {eq['model']} by {eq['manufacturer']}. Make test cases highly detailed with realistic acceptance criteria and numeric specifications."""

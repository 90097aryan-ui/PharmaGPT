"""PQ — Performance Qualification Protocol prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Performance Qualification Protocol.

    questionnaire keys
    ------------------
    protocol_number, version, product, batch_size, number_of_runs
    """
    eq      = equipment_data
    proto   = questionnaire.get("protocol_number", "PQ-001")
    ver     = questionnaire.get("version", "1.0")
    product = questionnaire.get("product", "N/A")
    batch   = questionnaire.get("batch_size", "N/A")
    runs    = questionnaire.get("number_of_runs", "3")
    today   = project_data["date"]

    pre = preamble("Performance Qualification (PQ) Protocol",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: Protocol {proto} v{ver} | Product: {product} | Batch: {batch} | Runs: {runs}

Generate a complete PQ Protocol using EXACTLY this markdown structure:

# PERFORMANCE QUALIFICATION PROTOCOL

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
| Product / Material | {product} |
| Batch Size | {batch} |
| Number of Runs | {runs} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. OBJECTIVE
[3–4 sentences: purpose of PQ, regulatory basis, what it demonstrates about process capability under routine conditions using {product}]

## 2. SCOPE
[Equipment covered, product/process covered, number of runs required and statistical rationale]

## 3. RESPONSIBILITIES
| Role | Responsibility |
|------|----------------|
| Validation Engineer | |
| Production / Operations | |
| Quality Assurance | |
| Analytical / QC Lab | |

## 4. DEFINITIONS AND ABBREVIATIONS
| Term | Definition |
|------|-----------|
| PQ | Performance Qualification |
| Cpk | Process Capability Index |
| RSD | Relative Standard Deviation |
| GMP | Good Manufacturing Practice |
[Add 6–8 more relevant terms]

## 5. EQUIPMENT DESCRIPTION
[2–3 paragraphs on {eq['name']} {eq['model']}, its role in the process, and why performance qualification is necessary]

## 6. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[List 6–8 references: SOPs, OQ protocol, analytical methods, regulatory guidelines]

## 7. PREREQUISITES
[Numbered list: successful OQ completion, calibrated instruments, trained personnel, approved batch records, environmental monitoring, raw material release]

## 8. PERFORMANCE QUALIFICATION TESTS
Generate exactly 6 comprehensive performance test cases with triplicate runs ({runs} runs minimum) covering all critical process parameters of {eq['name']} {eq['model']} operating with {product}. Each test must follow this format:

### Test PQ-01: [Descriptive Name — e.g. "Process Consistency and Reproducibility"]
**Purpose:** [What this test demonstrates about process capability]
**Regulatory Reference:** [e.g., 21 CFR 211.100, EU GMP Annex 15 §10, ICH Q8]
**Required Materials:** [List product, reference standards, instruments]

**Procedure:**
1. [Detailed production/process step]
2. [Sampling plan and frequency]
3. [Continue for 5–8 steps]

**Acceptance Criteria:**
- Mean: [specification with units]
- RSD: ≤ [%]
- Cpk: ≥ [value]
- Individual values: [range specification]

**Results Table (Run {runs}×):**
| Parameter | Specification | Run 1 | Run 2 | Run 3 | Mean | RSD% | Cpk | Pass/Fail |
|-----------|--------------|-------|-------|-------|------|------|-----|-----------|
| | | | | | | | | |

---

[Continue with PQ-02 through PQ-06]

## 9. STATISTICAL ANALYSIS
[Describe statistical methods used: mean, standard deviation, RSD, process capability (Cpk/Ppk), confidence intervals. State minimum acceptable Cpk ≥ 1.33 per industry standard.]

## 10. DEVIATION HANDLING
[Procedure for deviations during PQ runs, impact on batch disposition, and criteria for repeating a run]

## 11. SUMMARY AND CONCLUSION
| Parameter | Result |
|-----------|--------|
| Total PQ Runs Completed | |
| Runs Passed | |
| Runs Failed | |
| Overall Cpk (worst case) | |
| Open Deviations | |
| PQ Status | PASS / FAIL |

[Conclusion paragraph template for recommendation for routine production release]

## 12. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Protocol Author | | | |
| Quality Assurance Manager | | | |
| Validation Manager | | | |
| Production Manager | | | |
| Regulatory Affairs (if required) | | | |

## ANNEXURE A: RAW DATA SHEETS
[Template table for recording individual measurements per run]

## ANNEXURE B: STATISTICAL SUMMARY
[Template for Cpk calculation worksheet]

Write all sections completely and specifically for {eq['name']} {eq['model']} processing {product}. Include realistic numeric acceptance criteria."""

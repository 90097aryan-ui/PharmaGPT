"""FMEA — Failure Mode and Effects Analysis prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Failure Mode and Effects Analysis.

    questionnaire keys
    ------------------
    doc_number, version, fmea_scope
    """
    eq        = equipment_data
    doc_no    = questionnaire.get("doc_number", "FMEA-001")
    ver       = questionnaire.get("version", "1.0")
    scope_txt = questionnaire.get("fmea_scope", "Full system")
    today     = project_data["date"]

    pre = preamble("Failure Mode and Effects Analysis (FMEA)",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | FMEA Scope: {scope_txt}

Generate a complete FMEA document using EXACTLY this markdown structure:

# FAILURE MODE AND EFFECTS ANALYSIS (FMEA)

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {doc_no} |
| Version | {ver} |
| Equipment / System | {eq['name']} {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Department | {eq['department']} |
| FMEA Scope | {scope_txt} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. OBJECTIVE
[Purpose of this FMEA — proactive risk identification, ICH Q9 / GAMP5 risk management framework, link to the validation lifecycle]

## 2. SCOPE
[Systems, sub-systems, and failure modes covered. What is excluded. Reference to FMEA scope: {scope_txt}]

## 3. FMEA TEAM
| Name | Role | Department | Signature |
|------|------|-----------|-----------|
[Quality Assurance, Validation, Engineering, Operations, Regulatory]

## 4. RISK ASSESSMENT CRITERIA

### 4.1 Severity (S)
| Score | Level | Description |
|-------|-------|-------------|
| 1–2 | Negligible | No impact on product quality or patient safety |
| 3–4 | Minor | Minor impact, easily controlled |
| 5–6 | Moderate | Moderate impact on product quality |
| 7–8 | Major | Significant impact, batch rejection possible |
| 9–10 | Critical | Direct patient safety risk / regulatory action |

### 4.2 Occurrence (O)
| Score | Level | Frequency |
|-------|-------|-----------|
| 1–2 | Remote | < 1 in 10,000 |
| 3–4 | Low | 1 in 1,000 |
| 5–6 | Moderate | 1 in 100 |
| 7–8 | High | 1 in 10 |
| 9–10 | Very High | > 1 in 10 |

### 4.3 Detectability (D)
| Score | Level | Description |
|-------|-------|-------------|
| 1–2 | Very High | Failure detected before reaching next process step |
| 3–4 | High | Failure detected by in-process controls |
| 5–6 | Moderate | Failure detected during routine testing |
| 7–8 | Low | Failure detected only by final product testing |
| 9–10 | Very Low | Failure unlikely to be detected before product release |

**Risk Priority Number (RPN) = Severity × Occurrence × Detectability**
**Action Required: RPN ≥ 50 or Severity ≥ 8 (regardless of RPN)**

## 5. FMEA ANALYSIS TABLE
Generate minimum 15 failure modes covering ALL critical sub-systems and functions of {eq['name']} {eq['model']}. Be specific and realistic.

| # | Sub-system / Function | Failure Mode | Potential Effect | Potential Cause | S | O | D | RPN | Current Controls |
|---|----------------------|-------------|-----------------|----------------|---|---|---|-----|-----------------|
| 1 | | | | | | | | | |
[Continue through 15+ failure modes covering all critical systems]

## 6. RISK MITIGATION ACTIONS
For all failure modes with RPN ≥ 50 or Severity ≥ 8, define specific mitigation actions:

| # | Failure Mode | Recommended Action | Owner | Due Date | Action Type |
|---|-------------|-------------------|-------|----------|------------|
[List mitigation actions — include preventive maintenance, alarm additions, procedure updates, validation tests, calibration intervals]

## 7. POST-MITIGATION RPN TABLE
| # | Failure Mode | Initial S | Initial O | Initial D | Initial RPN | Mitigation Applied | Revised S | Revised O | Revised D | Revised RPN | Risk Accepted? |
|---|-------------|----------|----------|----------|------------|-------------------|----------|----------|----------|------------|---------------|
[Recalculate RPN after each mitigation — demonstrate risk reduction]

## 8. RISK ACCEPTANCE CRITERIA
| Risk Level | RPN Range | Action |
|-----------|-----------|--------|
| Low | < 50 | Accept — document in FMEA |
| Medium | 50–100 | Mitigate — implement controls |
| High | 101–200 | Mandatory mitigation before use |
| Critical | > 200 | Equipment / process redesign required |

## 9. FMEA SUMMARY
| Metric | Value |
|--------|-------|
| Total Failure Modes Identified | |
| High Risk (RPN > 100) | |
| Medium Risk (RPN 50–100) | |
| Low Risk (RPN < 50) | |
| Mitigations Implemented | |
| Residual High Risks | |
| FMEA Status | Approved for Production Use / Conditional |

## 10. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| FMEA Team Leader | | | |
| Quality Assurance Manager | | | |
| Validation Manager | | | |
| Engineering Manager | | | |
| Regulatory Affairs | | | |

Write all sections completely. Failure modes must be realistic and specific to {eq['name']} {eq['model']} in a pharmaceutical GMP environment. Use numeric RPN values — do not leave cells blank."""

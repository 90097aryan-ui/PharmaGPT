"""IQ — Installation Qualification Protocol prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for an Installation Qualification Protocol.

    questionnaire keys
    ------------------
    protocol_number, version, po_number, urs_reference
    """
    eq      = equipment_data
    proto   = questionnaire.get("protocol_number", "IQ-001")
    ver     = questionnaire.get("version", "1.0")
    urs_ref = questionnaire.get("urs_reference", "N/A")
    po_no   = questionnaire.get("po_number", "N/A")
    today   = project_data["date"]

    pre = preamble("Installation Qualification (IQ) Protocol",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: Protocol {proto} v{ver} | PO: {po_no} | URS Ref: {urs_ref}

Generate a complete IQ Protocol using EXACTLY this markdown structure:

# INSTALLATION QUALIFICATION PROTOCOL

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {proto} |
| Version | {ver} |
| Equipment | {eq['name']} {eq['model']} |
| Manufacturer | {eq['manufacturer']} |
| Serial Number | {eq['serial']} |
| Location | {eq['location']} |
| Department | {eq['department']} |
| Purchase Order | {po_no} |
| URS Reference | {urs_ref} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. OBJECTIVE
[Write 3–4 sentences explaining the purpose of this IQ protocol, the regulatory basis for installation qualification, and what successful IQ completion demonstrates.]

## 2. SCOPE
[Define the equipment, systems, and sub-components covered. State exclusions explicitly.]

## 3. RESPONSIBILITIES
| Role | Responsibility |
|------|----------------|
| Validation Engineer | |
| Quality Assurance | |
| Engineering / Maintenance | |
| Vendor / Manufacturer Representative | |

## 4. DEFINITIONS AND ABBREVIATIONS
| Term | Definition |
|------|-----------|
| IQ | Installation Qualification |
| GMP | Good Manufacturing Practice |
| SOP | Standard Operating Procedure |
| PO | Purchase Order |
[Add 6–8 more relevant terms]

## 5. EQUIPMENT DESCRIPTION
[2–3 paragraphs covering technical specifications, intended function, major sub-systems, and regulatory classification of {eq['name']} {eq['model']}]

## 6. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[List 6–8 relevant SOPs, P&IDs, vendor manuals, regulatory guidelines]

## 7. PREREQUISITES
[Numbered list: site readiness, utility availability, safety clearances, trained personnel, calibrated instruments, approved SOPs, etc.]

## 8. INSTALLATION VERIFICATION CHECKS
Generate 8+ installation checks covering ALL of the following areas for {eq['name']} {eq['model']}:
- Physical installation and anchoring
- Utility connections (electrical, pneumatic, water, etc.)
- Environmental conditions (temperature, humidity, cleanroom class)
- Documentation review (manuals, drawings, certificates)
- Component and spare parts verification
- Software / firmware version verification
- Safety features and interlocks
- Labelling and identification

Each check must follow this format:

### Check IQ-01: [Descriptive Name]
**Purpose:** [What this check verifies and regulatory basis]
**Regulatory Reference:** [e.g., 21 CFR 211.63, EU GMP Annex 15 §9.1]

**Procedure:**
1. [Step-by-step verification procedure]

**Acceptance Criteria:** [Specific pass/fail criterion]

| Check # | Parameter | Specification | Observed | Pass / Fail | By | Date |
|---------|-----------|--------------|----------|-------------|-----|------|
| IQ-01.1 | | | | | | |

---

[Continue IQ-02 through IQ-08+]

## 9. DEVIATION HANDLING
[Procedure for recording and escalating deviations found during IQ execution.]

## 10. SUMMARY AND CONCLUSION
| Parameter | Result |
|-----------|--------|
| Total Checks Executed | |
| Checks Passed | |
| Checks Failed | |
| Open Deviations | |
| IQ Status | PASS / FAIL |

## 11. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| Protocol Author | | | |
| Quality Assurance Manager | | | |
| Validation Manager | | | |
| Engineering Manager | | | |

## ANNEXURE A: COMPONENT AND SPARE PARTS LIST
| Item No. | Description | Part No. | Qty | Condition | Verified By |
|----------|-------------|----------|-----|-----------|-------------|

## ANNEXURE B: UTILITY CONNECTION CHECKLIST
| Utility | Specification | Measured Value | Pass / Fail | Date |
|---------|--------------|----------------|-------------|------|

Write all sections completely and specifically for {eq['name']} {eq['model']} by {eq['manufacturer']}."""

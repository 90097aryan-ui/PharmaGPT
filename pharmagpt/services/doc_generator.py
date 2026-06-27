"""
services/doc_generator.py — AI prompt builder for validation document generation.

Each of the 11 pharmaceutical document types (URS, DQ, FAT, SAT, IQ, OQ, PQ,
FMEA, CAPA, Deviation, Change Control) has a tailored prompt that instructs
Gemini to produce a GMP-compliant, regulation-cited, fully structured document
in consistent markdown format (which doc_exporter.py then converts to DOCX/PDF).

Architecture:
    build_generation_prompt(doc_type, form_data, doc_context, project_name)
        ↓
    dispatches to _prompt_<type>()
        ↓
    returns a complete prompt string ready to pass to Gemini
"""

from datetime import date as _date


def build_generation_prompt(
    doc_type: str,
    form_data: dict,
    doc_context: str,
    project_name: str,
) -> str:
    """
    Build the Gemini generation prompt for a validation document.

    Parameters
    ----------
    doc_type     : "OQ" | "IQ" | "PQ" | "URS" | "DQ" | "FAT" | "SAT" |
                   "FMEA" | "CAPA" | "Deviation" | "Change Control"
    form_data    : dict with keys from Step 1 (equipment) and Step 2 (details)
    doc_context  : formatted text from search_project_documents() — may be ""
    project_name : name of the active project

    Returns
    -------
    str — the complete prompt to send to Gemini as a single user message
    """
    today = _date.today().strftime("%d %B %Y")

    eq = {
        "name":         form_data.get("equipment_name", ""),
        "model":        form_data.get("model", ""),
        "manufacturer": form_data.get("manufacturer", ""),
        "serial":       form_data.get("serial_number", ""),
        "location":     form_data.get("location", ""),
        "department":   form_data.get("department", ""),
    }
    details = form_data.get("details", {})

    _builders = {
        "OQ":             _prompt_oq,
        "IQ":             _prompt_iq,
        "PQ":             _prompt_pq,
        "URS":            _prompt_urs,
        "DQ":             _prompt_dq,
        "FAT":            _prompt_fat,
        "SAT":            _prompt_sat,
        "FMEA":           _prompt_fmea,
        "CAPA":           _prompt_capa,
        "Deviation":      _prompt_deviation,
        "Change Control": _prompt_change_control,
    }

    builder = _builders.get(doc_type, _prompt_generic)
    return builder(eq, details, doc_context, project_name, today)


# ─────────────────────────────────────────────────────────────────────────────
# Shared preamble injected into every prompt
# ─────────────────────────────────────────────────────────────────────────────

def _preamble(doc_label: str, eq: dict, doc_context: str, project_name: str, today: str) -> str:
    ctx = f"\n{doc_context}\n" if doc_context.strip() else ""
    return (
        f"You are a Senior Pharmaceutical Validation Expert and Regulatory Affairs "
        f"Specialist with 30+ years of GMP experience across USFDA, MHRA, EU GMP, "
        f"WHO-GMP, CDSCO, and TGA environments.\n\n"
        f"Generate a COMPLETE, DETAILED, and GMP-COMPLIANT {doc_label} document.\n"
        f"Cite applicable regulations (21 CFR Part 211/820, EU GMP Annex 15, "
        f"GAMP5, ICH Q9/Q10, Schedule M, ISO 9001) throughout.\n"
        f"Use professional pharmaceutical language. Every section must be fully written "
        f"— do NOT leave placeholder text like '[Fill in]'.\n\n"
        f"PROJECT: {project_name}\n"
        f"DATE: {today}\n"
        f"EQUIPMENT: {eq['name']} {eq['model']} | MFR: {eq['manufacturer']} | "
        f"S/N: {eq['serial']} | DEPT: {eq['department']} | LOC: {eq['location']}\n"
        f"{ctx}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# OQ — Operational Qualification
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_oq(eq, details, doc_context, project_name, today):
    proto   = details.get("protocol_number", "OQ-001")
    ver     = details.get("version", "1.0")
    product = details.get("product", "N/A")
    batch   = details.get("batch_size", "N/A")
    urs_ref = details.get("urs_reference", "N/A")

    pre = _preamble("Operational Qualification (OQ) Protocol", eq, doc_context, project_name, today)

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


# ─────────────────────────────────────────────────────────────────────────────
# IQ — Installation Qualification
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_iq(eq, details, doc_context, project_name, today):
    proto   = details.get("protocol_number", "IQ-001")
    ver     = details.get("version", "1.0")
    urs_ref = details.get("urs_reference", "N/A")
    po_no   = details.get("po_number", "N/A")

    pre = _preamble("Installation Qualification (IQ) Protocol", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: Protocol {proto} v{ver} | PO: {po_no} | URS Ref: {urs_ref}

Generate a complete IQ Protocol with these sections (same markdown header table format as OQ):

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
## 2. SCOPE
## 3. RESPONSIBILITIES
## 4. DEFINITIONS AND ABBREVIATIONS
## 5. EQUIPMENT DESCRIPTION
## 6. REFERENCE DOCUMENTS
## 7. INSTALLATION VERIFICATION CHECKS (generate 8+ checks covering: physical installation, utility connections, environmental conditions, documentation review, component verification, software/firmware, safety features, spare parts inventory)
## 8. SUMMARY AND CONCLUSION
## 9. APPROVAL SIGNATURES
## ANNEXURE A: COMPONENT AND SPARE PARTS LIST
## ANNEXURE B: UTILITY CONNECTION CHECKLIST

Write all sections completely, specific to {eq['name']} {eq['model']} by {eq['manufacturer']}."""


# ─────────────────────────────────────────────────────────────────────────────
# PQ — Performance Qualification
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_pq(eq, details, doc_context, project_name, today):
    proto   = details.get("protocol_number", "PQ-001")
    ver     = details.get("version", "1.0")
    product = details.get("product", "N/A")
    batch   = details.get("batch_size", "N/A")
    runs    = details.get("number_of_runs", "3")

    pre = _preamble("Performance Qualification (PQ) Protocol", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: Protocol {proto} v{ver} | Product: {product} | Batch: {batch} | Runs: {runs}

Generate a complete PQ Protocol. Include all sections through performance testing with statistical acceptance criteria, process capability (Cpk), and reproducibility tests. Use the same header table format as OQ. Include minimum 6 performance test cases with acceptance criteria, triplicate runs, and statistical analysis tables. Write all sections completely."""


# ─────────────────────────────────────────────────────────────────────────────
# URS — User Requirement Specification
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_urs(eq, details, doc_context, project_name, today):
    doc_no  = details.get("doc_number", "URS-001")
    ver     = details.get("version", "1.0")
    system  = details.get("system_name", eq['name'])
    use     = details.get("intended_use", "")

    pre = _preamble("User Requirement Specification (URS)", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | System: {system} | Use: {use}

Generate a complete URS with: Document Header, Scope, System Overview, Intended Use,
Functional Requirements (numbered FR-001 through FR-020+), Performance Requirements,
Environmental Requirements, Regulatory/Compliance Requirements, Safety Requirements,
Maintenance Requirements, Training Requirements, Documentation Requirements,
Glossary, and Approval Signatures. Each requirement must be numbered, specific, and testable.
Write all sections completely using the same markdown table format."""


# ─────────────────────────────────────────────────────────────────────────────
# DQ — Design Qualification
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_dq(eq, details, doc_context, project_name, today):
    doc_no = details.get("doc_number", "DQ-001")
    ver    = details.get("version", "1.0")
    vendor = details.get("vendor_name", eq['manufacturer'])

    pre = _preamble("Design Qualification (DQ) Document", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | Vendor: {vendor}

Generate a complete DQ Document verifying that the equipment design meets URS requirements.
Include: Document Header, URS Traceability Matrix (mapping each URS requirement to design feature),
Design Specification Review, Material of Construction review, Utility Requirements,
Code Compliance (ASME, FDA, CE), Vendor Assessment checklist, Risk Assessment,
DQ Conclusion, Approval Signatures. Write all sections completely."""


# ─────────────────────────────────────────────────────────────────────────────
# FAT — Factory Acceptance Testing
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_fat(eq, details, doc_context, project_name, today):
    doc_no   = details.get("doc_number", "FAT-001")
    ver      = details.get("version", "1.0")
    fat_date = details.get("fat_date", today)
    location = details.get("fat_location", eq['manufacturer'] + " facility")

    pre = _preamble("Factory Acceptance Testing (FAT) Protocol", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | FAT Date: {fat_date} | FAT Location: {location}

Generate a complete FAT Protocol. Include: Document Header, Objective, Scope, FAT Team,
Documentation Review checklist (drawings, manuals, certificates), Physical Inspection checks,
Functional Tests (8+ tests at manufacturer's facility), Performance Tests,
Factory Punch List table, FAT Sign-off, and Approval Signatures.
Make all test cases specific to {eq['name']} {eq['model']}. Write completely."""


# ─────────────────────────────────────────────────────────────────────────────
# SAT — Site Acceptance Testing
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_sat(eq, details, doc_context, project_name, today):
    doc_no   = details.get("doc_number", "SAT-001")
    ver      = details.get("version", "1.0")
    sat_date = details.get("sat_date", today)

    pre = _preamble("Site Acceptance Testing (SAT) Protocol", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | SAT Date: {sat_date}

Generate a complete SAT Protocol verifying that the equipment performs correctly after installation at the site.
Include: Document Header, Objective, Scope, Site Readiness checklist,
Transit Damage Inspection, Re-commissioning Tests (6+ functional tests at site),
Comparison with FAT results table, Site Punch List, SAT Conclusion, Approval Signatures.
Write all sections completely."""


# ─────────────────────────────────────────────────────────────────────────────
# FMEA — Failure Mode and Effects Analysis
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_fmea(eq, details, doc_context, project_name, today):
    doc_no    = details.get("doc_number", "FMEA-001")
    ver       = details.get("version", "1.0")
    scope_txt = details.get("fmea_scope", "Full system")

    pre = _preamble("Failure Mode and Effects Analysis (FMEA)", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | FMEA Scope: {scope_txt}

Generate a complete FMEA document per ICH Q9 / GAMP5 Risk Management principles.
Include: Document Header, Objective, FMEA Team, Risk Assessment Criteria table
(Severity 1–10, Occurrence 1–10, Detectability 1–10, RPN = S×O×D),
FMEA Analysis Table with minimum 15 failure modes covering all critical subsystems of {eq['name']},
Risk Mitigation Actions for RPN > 50, Post-Mitigation RPN table,
Risk Acceptance Criteria, FMEA Summary, and Approval Signatures.
Write completely with realistic failure modes specific to the equipment."""


# ─────────────────────────────────────────────────────────────────────────────
# CAPA — Corrective and Preventive Action
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_capa(eq, details, doc_context, project_name, today):
    capa_no  = details.get("capa_number", "CAPA-001")
    ver      = details.get("version", "1.0")
    source   = details.get("capa_source", "Internal Audit / Deviation")
    desc     = details.get("description", "")

    pre = _preamble("Corrective and Preventive Action (CAPA) Report", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: CAPA No: {capa_no} v{ver} | Source: {source}
ISSUE DESCRIPTION: {desc}

Generate a complete CAPA Report per 21 CFR 820.100, EU GMP Chapter 8, and ICH Q10.
Include: Document Header, Problem Statement, Scope and Impact Assessment,
Root Cause Analysis (using Fishbone / 5-Why methodology — generate a thorough RCA),
Corrective Actions (numbered, with owner, due date, and evidence required),
Preventive Actions (numbered, with owner, due date),
Implementation Plan table, Effectiveness Check criteria and timeline,
CAPA Closure Criteria, and Approval Signatures.
Make the CAPA relevant to a pharmaceutical equipment/process context involving {eq['name']}. Write completely."""


# ─────────────────────────────────────────────────────────────────────────────
# Deviation — Deviation Report
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_deviation(eq, details, doc_context, project_name, today):
    dev_no   = details.get("deviation_number", "DEV-001")
    ver      = details.get("version", "1.0")
    category = details.get("category", "Planned / Unplanned")
    desc     = details.get("description", "")

    pre = _preamble("Deviation Report", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: Deviation No: {dev_no} | Category: {category}
DEVIATION DESCRIPTION: {desc}

Generate a complete Deviation Report per 21 CFR 211, EU GMP Chapter 6, and Schedule M.
Include: Document Header, Deviation Description (what/when/where/who/how discovered),
Deviation Category (planned/unplanned/critical/major/minor),
Immediate Actions taken, Impact Assessment (product quality/patient safety/regulatory),
Preliminary Root Cause, Batch/Lot affected table,
Investigation Findings (detailed), Final Root Cause Determination,
CAPA Actions Initiated (link to CAPA reference),
Batch Disposition Recommendation, and Approval Signatures.
Write all sections completely."""


# ─────────────────────────────────────────────────────────────────────────────
# Change Control
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_change_control(eq, details, doc_context, project_name, today):
    cc_no    = details.get("cc_number", "CC-001")
    ver      = details.get("version", "1.0")
    change   = details.get("change_description", "")
    reason   = details.get("reason_for_change", "")

    pre = _preamble("Change Control Document", eq, doc_context, project_name, today)
    return f"""{pre}
DOCUMENT DETAILS: CC No: {cc_no} v{ver}
CHANGE DESCRIPTION: {change}
REASON FOR CHANGE: {reason}

Generate a complete Change Control Document per 21 CFR 211.68, EU GMP Annex 15, and ICH Q10.
Include: Document Header, Change Request Summary, Change Classification (major/minor/critical),
Current State description, Proposed State description, Reason and Justification,
Impact Assessment table (Quality / Regulatory / Validation / Documentation / Training),
Risk Assessment summary (link to FMEA if applicable),
Implementation Plan (numbered steps with owner and target date),
Validation Requirements (revalidation scope: IQ/OQ/PQ/CSV),
Regulatory Notification Requirements, Review by Functional Teams table,
Post-Implementation Verification, and Approval Signatures.
Write all sections completely."""


# ─────────────────────────────────────────────────────────────────────────────
# Generic fallback
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_generic(eq, details, doc_context, project_name, today):
    doc_type = details.get("doc_type", "Validation Document")
    doc_no   = details.get("doc_number", "DOC-001")
    pre = _preamble(doc_type, eq, doc_context, project_name, today)
    return f"""{pre}
Generate a complete {doc_type} document ({doc_no}) with professional pharmaceutical structure,
appropriate sections, tables, acceptance criteria, and approval signatures.
Write all sections completely."""

"""DQ — Design Qualification Document prompt."""

from ._shared import preamble


def get_prompt(project_data: dict, equipment_data: dict,
               questionnaire: dict, knowledge_base: str) -> str:
    """Return the full Gemini prompt for a Design Qualification Document.

    questionnaire keys
    ------------------
    doc_number, version, vendor_name
    """
    eq     = equipment_data
    doc_no = questionnaire.get("doc_number", "DQ-001")
    ver    = questionnaire.get("version", "1.0")
    vendor = questionnaire.get("vendor_name", eq["manufacturer"])
    today  = project_data["date"]

    pre = preamble("Design Qualification (DQ) Document",
                   eq, knowledge_base, project_data)

    return f"""{pre}
DOCUMENT DETAILS: {doc_no} v{ver} | Vendor / Supplier: {vendor}

Generate a complete DQ Document using EXACTLY this markdown structure:

# DESIGN QUALIFICATION DOCUMENT

## Document Header
| Field | Details |
|-------|---------|
| Document Number | {doc_no} |
| Version | {ver} |
| Equipment / System | {eq['name']} {eq['model']} |
| Manufacturer / Vendor | {vendor} |
| Department | {eq['department']} |
| Intended Location | {eq['location']} |
| Date of Issue | {today} |
| Prepared by | _________________________ Date: ________ |
| Reviewed by | _________________________ Date: ________ |
| Approved by | _________________________ Date: ________ |

## Revision History
| Rev | Date | Description | Author | Reviewer | Approver |
|-----|------|-------------|--------|----------|---------|
| 00 | {today} | Initial Release | | | |

## 1. OBJECTIVE
[3–4 sentences: purpose of DQ, regulatory basis (EU GMP Annex 15 §5, GAMP5 §7.2), and what DQ completion verifies]

## 2. SCOPE
[Define what design elements are evaluated, reference to the URS, and any exclusions]

## 3. RESPONSIBILITIES
| Role | Responsibility |
|------|----------------|
| Validation Engineer | |
| Quality Assurance | |
| Engineering / Procurement | |
| Vendor / Manufacturer | |

## 4. REFERENCE DOCUMENTS
| Document No. | Title | Version |
|-------------|-------|---------|
[List URS, P&IDs, vendor proposals, regulatory guidelines, relevant SOPs]

## 5. URS TRACEABILITY MATRIX
Map each URS requirement to the corresponding design feature / vendor specification. Generate a comprehensive matrix with minimum 20 rows.

| URS Req. No. | URS Requirement | Design Feature / Specification | Vendor Doc. Ref. | Status |
|-------------|-----------------|-------------------------------|-----------------|--------|
| FR-001 | | | | Met / Partial / Not Met |
[Continue for all URS requirements — mark any gaps]

## 6. DESIGN SPECIFICATION REVIEW
[Detailed review of the vendor's design against URS requirements. Cover: process design, instrumentation, control system, capacity/throughput, cleanability (CIP/SIP if applicable), and ergonomics]

## 7. MATERIAL OF CONSTRUCTION REVIEW
| Component | Material | Contact with Product | Compliance (FDA 21 CFR / EU 10/2011) | Accepted |
|-----------|----------|---------------------|--------------------------------------|---------|
[Review all product-contact and non-contact materials for regulatory compliance]

## 8. UTILITY REQUIREMENTS
| Utility | Specification Required | Vendor Stated Value | Site Availability | Gap |
|---------|----------------------|---------------------|-------------------|-----|
| Electrical | | | | |
| Compressed Air | | | | |
| Water | | | | |
[Complete for all utilities required by {eq['name']} {eq['model']}]

## 9. CODE AND REGULATORY COMPLIANCE
| Standard / Regulation | Requirement | Design Compliance | Evidence |
|-----------------------|-------------|-------------------|---------|
| 21 CFR Part 211 | | | |
| EU GMP Annex 15 | | | |
| ASME / ISO | | | |
| CE Marking | | | |
[List all applicable codes and verify design compliance]

## 10. VENDOR ASSESSMENT
### 10.1 Vendor Qualification Summary
[Assessment of {vendor} quality system, GMP compliance, references, and audit history]

### 10.2 Vendor Assessment Checklist
| Assessment Criterion | Status | Comments |
|---------------------|--------|---------|
| ISO 9001 Certification | | |
| FDA Registered Facility | | |
| GMP Audit Completed | | |
| References (3+ pharma customers) | | |
| After-Sales Support | | |

## 11. RISK ASSESSMENT
[Brief risk assessment of the proposed design — identify top 5 design risks with mitigation measures]

| Risk | Likelihood | Impact | Mitigation | Residual Risk |
|------|-----------|--------|-----------|--------------|

## 12. DQ CONCLUSION AND RECOMMENDATION
[Paragraph stating whether the design of {eq['name']} {eq['model']} by {vendor} satisfies all URS requirements, identifies any open gaps, and recommends proceeding to procurement / FAT / IQ]

| Summary Item | Result |
|-------------|--------|
| Total URS Requirements | |
| Requirements Met | |
| Partial / Gaps | |
| Not Met | |
| Overall DQ Status | APPROVED / CONDITIONAL / REJECTED |

## 13. APPROVAL SIGNATURES
| Role | Printed Name | Signature | Date |
|------|-------------|-----------|------|
| DQ Author | | | |
| Quality Assurance Manager | | | |
| Engineering Manager | | | |
| Procurement | | | |
| Regulatory Affairs | | | |

Write all sections completely and specifically for {eq['name']} {eq['model']} supplied by {vendor}."""

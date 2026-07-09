"""
review/review_rules.py — Modular, deterministic review rules for PharmaGPT v0.9.5.

Each public function is an independent rule that accepts parsed document data and
returns a list of ReviewIssue objects. To add a new rule, write a function and
register it in RULE_REGISTRY at the bottom.

Rule ID convention:  CATEGORY-NNN
  STR = Document Structure
  REG = Regulatory Compliance
  TEC = Technical Content
  EQP = Equipment Information
  FMT = Formatting
  CMP = Completeness
"""

from __future__ import annotations

import re
from typing import List

from pharmagpt.review.review_models import ReviewIssue, Severity

# ──────────────────────────────────────────────────────────────────────────────
# Mandatory-section definitions per document type
# ──────────────────────────────────────────────────────────────────────────────

MANDATORY_SECTIONS: dict[str, list[str]] = {
    "IQ": [
        "purpose", "scope", "responsibilities", "equipment", "installation",
        "calibration", "utilities", "acceptance criteria", "references",
        "annexure", "approval", "revision history",
    ],
    "OQ": [
        "purpose", "scope", "responsibilities", "test", "calibration",
        "acceptance criteria", "references", "annexure", "approval", "revision history",
    ],
    "PQ": [
        "purpose", "scope", "responsibilities", "performance", "sampling",
        "acceptance criteria", "references", "annexure", "approval", "revision history",
    ],
    "URS": [
        "purpose", "scope", "functional requirements", "performance requirements",
        "regulatory requirements", "references", "approval", "revision history",
    ],
    "DQ": [
        "purpose", "scope", "design", "regulatory", "vendor",
        "references", "approval", "revision history",
    ],
    "FAT": [
        "purpose", "scope", "test", "acceptance criteria",
        "references", "approval", "revision history",
    ],
    "SAT": [
        "purpose", "scope", "test", "acceptance criteria",
        "references", "approval", "revision history",
    ],
    "FMEA": [
        "purpose", "scope", "risk", "failure mode", "severity",
        "occurrence", "detection", "rpn", "recommendation",
        "approval", "revision history",
    ],
    "CAPA": [
        "purpose", "scope", "description", "root cause", "corrective action",
        "preventive action", "effectiveness", "approval", "revision history",
    ],
    "Deviation": [
        "purpose", "scope", "description", "impact", "root cause",
        "corrective action", "approval", "revision history",
    ],
    "Change Control": [
        "purpose", "scope", "description", "impact", "implementation",
        "approval", "revision history",
    ],
    "IQ/OQ Combined": [
        "purpose", "scope", "responsibilities", "installation", "test",
        "calibration", "acceptance criteria", "references", "annexure",
        "approval", "revision history",
    ],
    "SOP": [
        "purpose", "scope", "responsibilities", "procedure", "safety",
        "records", "training", "approval", "revision history",
    ],
    "Validation Plan": [
        "purpose", "scope", "responsibilities", "risk", "approach",
        "schedule", "references", "approval", "revision history",
    ],
    "Validation Report": [
        "purpose", "scope", "summary", "deviation", "conclusion",
        "traceability", "approval", "revision history",
    ],
}

# Sections required for IQ/OQ/PQ that are not always present in other types
_IQ_OQ_PQ_TYPES = {"IQ", "OQ", "PQ", "IQ/OQ Combined"}

# ──────────────────────────────────────────────────────────────────────────────
# Markdown parsing helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_headings(content: str) -> list[dict]:
    """
    Return list of {level: int, text: str, line: int} for every ATX heading.
    """
    headings = []
    for i, line in enumerate(content.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if m:
            headings.append({
                "level": len(m.group(1)),
                "text":  m.group(2).strip(),
                "line":  i,
            })
    return headings


def _heading_texts(content: str) -> list[str]:
    return [h["text"].lower() for h in _extract_headings(content)]


def _extract_tables(content: str) -> list[dict]:
    """
    Return list of {line: int, rows: int} for every markdown table block.
    Identifies tables by sequences of pipe-delimited rows.
    """
    tables = []
    lines = content.splitlines()
    in_table = False
    start_line = 0
    row_count = 0

    for i, line in enumerate(lines, 1):
        is_pipe_row = bool(re.match(r"^\s*\|.*\|\s*$", line))
        if is_pipe_row:
            if not in_table:
                in_table   = True
                start_line = i
                row_count  = 1
            else:
                row_count += 1
        else:
            if in_table:
                tables.append({"line": start_line, "rows": row_count})
                in_table  = False
                row_count = 0

    if in_table:
        tables.append({"line": start_line, "rows": row_count})

    return tables


def _section_lengths(content: str) -> dict[str, int]:
    """
    Return {heading_text_lower: word_count} for each section.
    """
    headings = _extract_headings(content)
    lines    = content.splitlines()
    lengths  = {}

    for idx, h in enumerate(headings):
        start = h["line"]
        end   = headings[idx + 1]["line"] - 1 if idx + 1 < len(headings) else len(lines)
        body  = "\n".join(lines[start:end])
        lengths[h["text"].lower()] = len(body.split())

    return lengths


def _content_lower(content: str) -> str:
    return content.lower()


def _has_keyword(content_lower: str, *keywords: str) -> bool:
    return any(kw in content_lower for kw in keywords)


# ──────────────────────────────────────────────────────────────────────────────
# Document Structure rules  (STR)
# ──────────────────────────────────────────────────────────────────────────────

def check_missing_sections(content: str, doc_type: str, **_) -> List[ReviewIssue]:
    """STR-001: Verify mandatory sections are present."""
    issues: List[ReviewIssue] = []
    required = MANDATORY_SECTIONS.get(doc_type, MANDATORY_SECTIONS.get("IQ", []))
    cl       = _content_lower(content)

    missing = [sec for sec in required if sec not in cl]
    if not missing:
        return issues

    pct_missing = len(missing) / len(required)
    severity    = Severity.CRITICAL if pct_missing >= 0.4 else Severity.MAJOR
    for sec in missing:
        issues.append(ReviewIssue(
            rule_id          = "STR-001",
            severity         = severity,
            description      = f"Mandatory section '{sec.title()}' is missing.",
            recommendation   = f"Add a dedicated section for '{sec.title()}' as required by GMP validation protocol standards.",
            affected_section = "Document Structure",
        ))
    return issues


def check_missing_approval_page(content: str, **_) -> List[ReviewIssue]:
    """STR-002: Approval page must be present with signatory fields."""
    cl = _content_lower(content)
    if _has_keyword(cl, "approval", "approved by", "approver"):
        return []
    return [ReviewIssue(
        rule_id          = "STR-002",
        severity         = Severity.CRITICAL,
        description      = "Approval page / approver section is missing.",
        recommendation   = "Add an Approval Page with roles (QA Manager, Production Manager, Validation Manager), names, dates, and signature lines.",
        affected_section = "Approval Page",
    )]


def check_missing_revision_history(content: str, **_) -> List[ReviewIssue]:
    """STR-003: Revision history table must be present."""
    cl = _content_lower(content)
    if _has_keyword(cl, "revision history", "document history", "change history"):
        return []
    return [ReviewIssue(
        rule_id          = "STR-003",
        severity         = Severity.MAJOR,
        description      = "Revision history section is missing.",
        recommendation   = "Add a Revision History table with columns: Rev No., Date, Description, Prepared By, Approved By.",
        affected_section = "Revision History",
    )]


def check_duplicate_headings(content: str, **_) -> List[ReviewIssue]:
    """STR-004: Detect duplicate headings at same level."""
    issues: List[ReviewIssue] = []
    headings = _extract_headings(content)
    seen: dict[str, int] = {}

    for h in headings:
        key = f"L{h['level']}:{h['text'].lower()}"
        if key in seen:
            issues.append(ReviewIssue(
                rule_id          = "STR-004",
                severity         = Severity.MINOR,
                description      = f"Duplicate heading detected: '{h['text']}' appears more than once at heading level {h['level']}.",
                recommendation   = "Merge duplicate sections or rename them to be distinct.",
                affected_section = h["text"],
            ))
        else:
            seen[key] = h["line"]
    return issues


def check_heading_hierarchy(content: str, **_) -> List[ReviewIssue]:
    """STR-005: Heading levels must not skip (e.g., H1 → H3 without H2)."""
    issues  = []
    headings = _extract_headings(content)
    prev     = 0
    for h in headings:
        if h["level"] > prev + 1 and prev > 0:
            issues.append(ReviewIssue(
                rule_id          = "STR-005",
                severity         = Severity.MINOR,
                description      = f"Heading hierarchy skips from H{prev} to H{h['level']} at '{h['text']}'.",
                recommendation   = "Maintain sequential heading levels (H1 → H2 → H3) without gaps.",
                affected_section = h["text"],
            ))
        prev = h["level"]
    return issues


def check_broken_numbering(content: str, **_) -> List[ReviewIssue]:
    """STR-006: Detect inconsistent section numbering patterns."""
    issues   = []
    lines    = content.splitlines()
    numbered = [l for l in lines if re.match(r"^\d+\.\d*\s+\w", l.strip())]

    if len(numbered) < 3:
        return []

    prev_major = 0
    for line in numbered:
        m = re.match(r"^(\d+)\.", line.strip())
        if m:
            curr = int(m.group(1))
            if curr - prev_major > 2 and prev_major > 0:
                issues.append(ReviewIssue(
                    rule_id          = "STR-006",
                    severity         = Severity.MINOR,
                    description      = f"Section numbering appears broken near section {curr} (jumped from {prev_major}).",
                    recommendation   = "Ensure section numbers are sequential without large gaps.",
                    affected_section = f"Section {curr}",
                ))
                break
            prev_major = curr
    return issues


def check_missing_footer_header_markers(content: str, **_) -> List[ReviewIssue]:
    """STR-007: Document should include header/footer marker references."""
    cl = _content_lower(content)
    markers = ["protocol number", "doc no", "document number", "revision", "page"]
    if any(m in cl for m in markers):
        return []
    return [ReviewIssue(
        rule_id          = "STR-007",
        severity         = Severity.MINOR,
        description      = "Document does not reference header/footer identifiers (Protocol No., Rev., Page).",
        recommendation   = "Ensure the document includes protocol number, revision number, and page reference for GMP traceability.",
        affected_section = "Document Header/Footer",
    )]


# ──────────────────────────────────────────────────────────────────────────────
# Technical Content rules  (TEC)
# ──────────────────────────────────────────────────────────────────────────────

def check_missing_acceptance_criteria(content: str, doc_type: str, **_) -> List[ReviewIssue]:
    """TEC-001: Acceptance criteria are mandatory for most document types."""
    skip_types = {"Deviation", "Change Control", "FMEA", "SOP", "Validation Plan"}
    if doc_type in skip_types:
        return []
    cl = _content_lower(content)
    if _has_keyword(cl, "acceptance criteria", "acceptance limit", "pass criteria", "specification"):
        return []
    return [ReviewIssue(
        rule_id          = "TEC-001",
        severity         = Severity.CRITICAL,
        description      = "Acceptance criteria are missing from the document.",
        recommendation   = "Add explicit acceptance criteria for all tests and parameters, including numerical limits, units, and pass/fail thresholds.",
        affected_section = "Acceptance Criteria",
    )]


def check_missing_test_cases(content: str, doc_type: str, **_) -> List[ReviewIssue]:
    """TEC-002: Test protocols require defined test cases."""
    test_types = {"IQ", "OQ", "PQ", "FAT", "SAT", "IQ/OQ Combined"}
    if doc_type not in test_types:
        return []
    cl = _content_lower(content)
    if _has_keyword(cl, "test case", "test procedure", "test step", "test no", "test id", "tc-", "test #"):
        return []
    return [ReviewIssue(
        rule_id          = "TEC-002",
        severity         = Severity.MAJOR,
        description      = f"No formal test cases found in {doc_type} document.",
        recommendation   = "Add numbered test cases with: Test ID, Objective, Prerequisites, Steps, Expected Result, Actual Result, Pass/Fail, Performed By, Date.",
        affected_section = "Test Cases",
    )]


def check_missing_calibration(content: str, doc_type: str, **_) -> List[ReviewIssue]:
    """TEC-003: Calibration section is mandatory for IQ/OQ/PQ."""
    if doc_type not in _IQ_OQ_PQ_TYPES:
        return []
    cl = _content_lower(content)
    if _has_keyword(cl, "calibration", "calibrated", "certificate of calibration"):
        return []
    return [ReviewIssue(
        rule_id          = "TEC-003",
        severity         = Severity.MAJOR,
        description      = f"Calibration section is missing from {doc_type} document.",
        recommendation   = "Add a Calibration section listing all instruments requiring calibration, calibration frequency, and certificate references.",
        affected_section = "Calibration",
    )]


def check_missing_training(content: str, **_) -> List[ReviewIssue]:
    """TEC-004: Training requirements should be documented."""
    cl = _content_lower(content)
    if _has_keyword(cl, "training", "trained personnel", "qualification of personnel"):
        return []
    return [ReviewIssue(
        rule_id          = "TEC-004",
        severity         = Severity.MINOR,
        description      = "Training requirements for protocol execution are not mentioned.",
        recommendation   = "Add a training section specifying personnel qualifications and training records required before executing this protocol.",
        affected_section = "Training",
    )]


def check_missing_traceability(content: str, doc_type: str, **_) -> List[ReviewIssue]:
    """TEC-005: Traceability to URS/DQ/IQ is expected for OQ/PQ."""
    if doc_type not in {"OQ", "PQ"}:
        return []
    cl = _content_lower(content)
    if _has_keyword(cl, "traceability", "urs reference", "dq reference", "iq reference", "requirement id"):
        return []
    return [ReviewIssue(
        rule_id          = "TEC-005",
        severity         = Severity.MAJOR,
        description      = f"No traceability references found in {doc_type} document.",
        recommendation   = "Add a Traceability Matrix linking each test case to the corresponding URS/DQ/IQ requirement.",
        affected_section = "Traceability",
    )]


def check_short_sections(content: str, **_) -> List[ReviewIssue]:
    """TEC-006: Flag sections with very little content (< 30 words)."""
    issues   = []
    lengths  = _section_lengths(content)
    headings = _extract_headings(content)
    skip_h1  = {h["text"].lower() for h in headings if h["level"] == 1}

    for heading, word_count in lengths.items():
        if heading in skip_h1:
            continue
        if 0 < word_count < 30:
            issues.append(ReviewIssue(
                rule_id          = "TEC-006",
                severity         = Severity.OBSERVATION,
                description      = f"Section '{heading.title()}' contains only {word_count} words — may be incomplete.",
                recommendation   = f"Expand section '{heading.title()}' with detailed content appropriate for a GMP-regulated document.",
                affected_section = heading.title(),
            ))
    return issues


def check_missing_responsibilities(content: str, **_) -> List[ReviewIssue]:
    """CMP-001: Responsibilities / RACI must be defined."""
    cl = _content_lower(content)
    if _has_keyword(cl, "responsibilities", "responsible", "raci", "accountable", "roles and responsibilities"):
        return []
    return [ReviewIssue(
        rule_id          = "CMP-001",
        severity         = Severity.MAJOR,
        description      = "Responsibilities section is missing.",
        recommendation   = "Add a Responsibilities section defining roles (QA, Production, Engineering, Validation) and their obligations for this document.",
        affected_section = "Responsibilities",
    )]


def check_missing_annexures(content: str, **_) -> List[ReviewIssue]:
    """CMP-002: Annexures / attachments should be referenced."""
    cl = _content_lower(content)
    if _has_keyword(cl, "annexure", "annex", "appendix", "attachment"):
        return []
    return [ReviewIssue(
        rule_id          = "CMP-002",
        severity         = Severity.MINOR,
        description      = "No annexures or appendices are referenced.",
        recommendation   = "Add Annexures for raw data sheets, calibration certificates, equipment drawings, and instrument list as appropriate.",
        affected_section = "Annexures",
    )]


def check_missing_references(content: str, **_) -> List[ReviewIssue]:
    """CMP-003: References section must list applicable documents."""
    cl = _content_lower(content)
    if _has_keyword(cl, "references", "reference documents", "related documents"):
        return []
    return [ReviewIssue(
        rule_id          = "CMP-003",
        severity         = Severity.MINOR,
        description      = "References section is missing.",
        recommendation   = "Add a References section listing SOPs, regulatory guidelines, equipment manuals, and related validation documents.",
        affected_section = "References",
    )]


# ──────────────────────────────────────────────────────────────────────────────
# Equipment Information rules  (EQP)
# ──────────────────────────────────────────────────────────────────────────────

def check_missing_equipment_info(content: str, form_data: dict, **_) -> List[ReviewIssue]:
    """EQP-001: Core equipment identifiers must appear in the document."""
    issues     = []
    cl         = _content_lower(content)
    equipment  = form_data.get("equipment_name", "")
    model      = form_data.get("model", "")
    serial     = form_data.get("serial_number", "")
    department = form_data.get("department", "")

    if equipment and equipment.lower() not in cl:
        issues.append(ReviewIssue(
            rule_id          = "EQP-001",
            severity         = Severity.CRITICAL,
            description      = f"Equipment name '{equipment}' does not appear in the document body.",
            recommendation   = "Ensure the equipment name is explicitly stated in the equipment description section.",
            affected_section = "Equipment Information",
        ))
    if model and model.lower() not in cl:
        issues.append(ReviewIssue(
            rule_id          = "EQP-001",
            severity         = Severity.MAJOR,
            description      = f"Equipment model '{model}' is not referenced in the document.",
            recommendation   = "Include model number in equipment identification table.",
            affected_section = "Equipment Information",
        ))
    if serial and serial.lower() not in cl:
        issues.append(ReviewIssue(
            rule_id          = "EQP-001",
            severity         = Severity.MAJOR,
            description      = f"Serial number '{serial}' is not referenced in the document.",
            recommendation   = "Include serial number in equipment identification table for unique asset traceability.",
            affected_section = "Equipment Information",
        ))
    if department and department.lower() not in cl:
        issues.append(ReviewIssue(
            rule_id          = "EQP-001",
            severity         = Severity.MINOR,
            description      = f"Department '{department}' is not mentioned in the document.",
            recommendation   = "Specify the department/location where equipment is installed.",
            affected_section = "Equipment Information",
        ))
    return issues


def check_missing_utilities(content: str, doc_type: str, **_) -> List[ReviewIssue]:
    """EQP-002: Utilities (power, water, compressed air) must be listed for IQ/OQ."""
    if doc_type not in {"IQ", "OQ", "IQ/OQ Combined"}:
        return []
    cl = _content_lower(content)
    if _has_keyword(cl, "utilities", "electrical", "compressed air", "water supply", "drainage", "hvac"):
        return []
    return [ReviewIssue(
        rule_id          = "EQP-002",
        severity         = Severity.MAJOR,
        description      = f"Utilities section is missing from {doc_type} document.",
        recommendation   = "Add a Utilities section listing all required utilities (electrical supply, compressed air, water, HVAC) with specifications.",
        affected_section = "Utilities",
    )]


def check_missing_protocol_metadata(content: str, **_) -> List[ReviewIssue]:
    """EQP-003: Protocol metadata (number, effective date, revision) must appear."""
    issues = []
    cl     = _content_lower(content)

    if not _has_keyword(cl, "protocol no", "document no", "doc no", "protocol number", "document number"):
        issues.append(ReviewIssue(
            rule_id          = "EQP-003",
            severity         = Severity.MAJOR,
            description      = "Protocol / document number is not defined.",
            recommendation   = "Add a document number in the format SYS-DEPT-TYPE-NNN (e.g., VAL-PRD-IQ-001).",
            affected_section = "Protocol Metadata",
        ))
    if not _has_keyword(cl, "effective date", "date of issue", "issue date"):
        issues.append(ReviewIssue(
            rule_id          = "EQP-003",
            severity         = Severity.MINOR,
            description      = "Effective date / issue date is not stated.",
            recommendation   = "Add effective date on the cover page or document header.",
            affected_section = "Protocol Metadata",
        ))
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# Formatting rules  (FMT)
# ──────────────────────────────────────────────────────────────────────────────

def check_empty_tables(content: str, **_) -> List[ReviewIssue]:
    """FMT-001: Tables must have at least one data row beyond the header."""
    issues = []
    for tbl in _extract_tables(content):
        # header + separator = 2 rows; data row = 3rd row minimum
        if tbl["rows"] < 3:
            issues.append(ReviewIssue(
                rule_id          = "FMT-001",
                severity         = Severity.MAJOR,
                description      = f"Table at line {tbl['line']} has only {tbl['rows']} row(s) — appears empty or incomplete.",
                recommendation   = "Populate the table with complete data. Remove the table if the information will not be available at this stage.",
                affected_section = f"Table at line {tbl['line']}",
            ))
    return issues


def check_missing_signatures(content: str, **_) -> List[ReviewIssue]:
    """FMT-002: Signature blocks must be present."""
    cl = _content_lower(content)
    if _has_keyword(cl, "signature", "signed by", "sign here", "authorised by", "authorized by"):
        return []
    return [ReviewIssue(
        rule_id          = "FMT-002",
        severity         = Severity.CRITICAL,
        description      = "No signature blocks found in the document.",
        recommendation   = "Add signature blocks for Prepared By, Reviewed By, and Approved By with Name, Designation, Date, and Signature fields.",
        affected_section = "Signatures",
    )]


def check_iq_oq_pq_checklist(content: str, doc_type: str, **_) -> List[ReviewIssue]:
    """FMT-003: IQ/OQ/PQ protocols must include a pre-execution checklist."""
    if doc_type not in _IQ_OQ_PQ_TYPES:
        return []
    cl = _content_lower(content)
    if _has_keyword(cl, "checklist", "pre-requisite", "prerequisite", "pre-execution", "pre execution"):
        return []
    return [ReviewIssue(
        rule_id          = "FMT-003",
        severity         = Severity.MINOR,
        description      = f"{doc_type} protocol is missing a pre-execution checklist.",
        recommendation   = "Add a Pre-Execution Checklist verifying that prerequisites (calibration, training, SOP availability, materials) are complete before protocol execution.",
        affected_section = "Checklist",
    )]


# ──────────────────────────────────────────────────────────────────────────────
# Compliance rules — each returns a tuple (ComplianceCheck, List[ReviewIssue])
# These are handled separately in review_engine.py
# ──────────────────────────────────────────────────────────────────────────────

def _compliance_keywords() -> dict[str, list[str]]:
    return {
        "EU GMP Annex 15": [
            "annex 15", "qualification", "validation master plan", "vmp",
            "process validation", "concurrent validation", "retrospective",
            "change control", "periodic review",
        ],
        "ASTM E2500": [
            "astm e2500", "good engineering practice", "gep", "science and risk based",
            "critical aspect", "commissioning and qualification",
        ],
        "ISPE Baseline Guide": [
            "ispe", "baseline guide", "commissioning", "qualification",
            "direct impact", "indirect impact", "no impact",
        ],
        "WHO GMP": [
            "who", "world health organization", "qualification", "validation",
            "prospective validation", "process validation", "cleaning validation",
        ],
        "GAMP 5 2nd Edition": [
            "gamp", "gamp5", "gamp 5", "computer system validation", "csv",
            "category 1", "category 3", "category 4", "category 5",
            "software category",
        ],
        "21 CFR Part 11": [
            "21 cfr", "part 11", "electronic records", "electronic signatures",
            "audit trail", "access control", "21cfr",
        ],
    }


def evaluate_compliance(content: str, doc_type: str) -> list[dict]:
    """
    Evaluate document against each regulatory framework.
    Returns list of dicts ready to build ComplianceCheck objects.
    """
    from pharmagpt.review.review_models import ComplianceStatus

    cl      = _content_lower(content)
    results = []
    kw_map  = _compliance_keywords()

    for regulation, keywords in kw_map.items():
        hits = sum(1 for kw in keywords if kw in cl)
        pct  = hits / len(keywords)

        if pct >= 0.35:
            status = ComplianceStatus.PASS
            explanation = (
                f"Document references {hits}/{len(keywords)} key {regulation} requirements. "
                "Terminology and structure align with this framework."
            )
        elif pct >= 0.10:
            status = ComplianceStatus.WARNING
            explanation = (
                f"Partial coverage: {hits}/{len(keywords)} {regulation} keywords found. "
                "Review missing elements before submission."
            )
        else:
            status = ComplianceStatus.FAIL
            explanation = (
                f"Insufficient {regulation} coverage ({hits}/{len(keywords)} keywords). "
                "Document may not satisfy this regulatory framework."
            )

        # Special override: 21 CFR Part 11 only applies to CSV / computer systems
        if regulation == "21 CFR Part 11" and doc_type not in {
            "IQ", "OQ", "PQ", "FAT", "SAT", "URS", "DQ"
        }:
            status = ComplianceStatus.WARNING
            explanation = (
                "21 CFR Part 11 applicability depends on whether electronic records "
                "or audit trails are used for this document type."
            )

        results.append({"regulation": regulation, "status": status, "explanation": explanation})

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Rule registry — add new rule functions here
# ──────────────────────────────────────────────────────────────────────────────
#
# Each entry is a (category, function) tuple.
# category must match one of:
#   "structure" | "technical" | "equipment" | "formatting" | "completeness"
#
# The engine uses category to determine which CategoryScore field to deduct from.

RULE_REGISTRY: list[tuple[str, callable]] = [
    # Document Structure
    ("structure",    check_missing_sections),
    ("structure",    check_missing_approval_page),
    ("structure",    check_missing_revision_history),
    ("structure",    check_duplicate_headings),
    ("structure",    check_heading_hierarchy),
    ("structure",    check_broken_numbering),
    ("structure",    check_missing_footer_header_markers),
    # Technical Content
    ("technical",    check_missing_acceptance_criteria),
    ("technical",    check_missing_test_cases),
    ("technical",    check_missing_calibration),
    ("technical",    check_missing_training),
    ("technical",    check_missing_traceability),
    ("technical",    check_short_sections),
    # Equipment Information
    ("equipment",    check_missing_equipment_info),
    ("equipment",    check_missing_utilities),
    ("equipment",    check_missing_protocol_metadata),
    # Formatting
    ("formatting",   check_empty_tables),
    ("formatting",   check_missing_signatures),
    ("formatting",   check_iq_oq_pq_checklist),
    # Completeness
    ("completeness", check_missing_responsibilities),
    ("completeness", check_missing_annexures),
    ("completeness", check_missing_references),
]

# Deduction per severity level per issue (applied to the category's pool)
SEVERITY_DEDUCTIONS: dict[Severity, float] = {
    Severity.CRITICAL:    10.0,
    Severity.MAJOR:        5.0,
    Severity.MINOR:        2.0,
    Severity.OBSERVATION:  1.0,
}

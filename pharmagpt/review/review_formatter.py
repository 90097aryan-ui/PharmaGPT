"""
review/review_formatter.py — Formats a ReviewResult for inclusion in the DOCX export.

The primary output is a structured block of markdown-like data that the
DocxGenerator can render as tables and paragraphs.  A secondary plain-text
summary is also available for logging / API responses.
"""

from __future__ import annotations

from review.review_models import ComplianceStatus, ReadinessLevel, ReviewResult, Severity

# ── Readiness colour map (used in DOCX) ──────────────────────────────────────
READINESS_COLOUR: dict[ReadinessLevel, str] = {
    ReadinessLevel.READY:     "2E7D32",  # dark green
    ReadinessLevel.MINOR:     "F57F17",  # amber
    ReadinessLevel.MAJOR:     "E65100",  # deep orange
    ReadinessLevel.NOT_READY: "B71C1C",  # dark red
}

COMPLIANCE_COLOUR: dict[ComplianceStatus, str] = {
    ComplianceStatus.PASS:    "2E7D32",
    ComplianceStatus.WARNING: "F57F17",
    ComplianceStatus.FAIL:    "B71C1C",
}

SEVERITY_COLOUR: dict[Severity, str] = {
    Severity.CRITICAL:    "B71C1C",
    Severity.MAJOR:       "E65100",
    Severity.MINOR:       "1565C0",
    Severity.OBSERVATION: "37474F",
}


def score_badge_class(score: float) -> str:
    """Return a CSS class name for the score badge based on the score."""
    if score >= 85:
        return "review-badge-green"
    if score >= 70:
        return "review-badge-yellow"
    return "review-badge-red"


def format_summary_text(result: ReviewResult) -> str:
    """Return a concise plain-text summary for logging and API JSON."""
    cs  = result.category_scores
    lines = [
        f"=== VALIDATION REVIEW REPORT ({result.doc_type}) ===",
        f"Overall Score   : {result.overall_score:.1f}/100",
        f"Readiness       : {result.readiness.value}",
        f"",
        f"Category Scores:",
        f"  Document Structure    : {cs.document_structure:.1f}/20",
        f"  Regulatory Compliance : {cs.regulatory_compliance:.1f}/20",
        f"  Technical Content     : {cs.technical_content:.1f}/20",
        f"  Equipment Information : {cs.equipment_information:.1f}/15",
        f"  Formatting            : {cs.formatting:.1f}/15",
        f"  Completeness          : {cs.completeness:.1f}/10",
        f"",
        f"Issues: {len(result.issues)} total  "
        f"(Critical: {sum(1 for i in result.issues if i.severity == Severity.CRITICAL)}, "
        f"Major: {sum(1 for i in result.issues if i.severity == Severity.MAJOR)}, "
        f"Minor: {sum(1 for i in result.issues if i.severity == Severity.MINOR)}, "
        f"Obs: {sum(1 for i in result.issues if i.severity == Severity.OBSERVATION)})",
        f"",
        f"Reviewer Comments: {result.reviewer_comments}",
        f"",
        f"Approval: {result.approval_recommendation}",
    ]
    return "\n".join(lines)


def format_docx_sections(result: ReviewResult) -> dict:
    """
    Return structured data for the DocxGenerator to render as a review appendix.

    Keys
    ----
    title        : str
    score        : float
    readiness    : str
    readiness_hex: str
    category_rows: list[tuple[str, float, float]]   (label, score, max)
    compliance   : list[tuple[str, str, str, str]]  (reg, status, colour, explanation)
    issues       : list[tuple[str, str, str, str, str]] (rule_id, severity, affected, desc, rec)
    recommendations : list[str]
    reviewer_comments   : str
    approval_recommendation : str
    """
    cs = result.category_scores
    return {
        "title":         f"Validation Review Report — {result.doc_type}",
        "score":         result.overall_score,
        "readiness":     result.readiness.value,
        "readiness_hex": READINESS_COLOUR.get(result.readiness, "000000"),
        "category_rows": [
            ("Document Structure",    cs.document_structure,    20.0),
            ("Regulatory Compliance", cs.regulatory_compliance, 20.0),
            ("Technical Content",     cs.technical_content,     20.0),
            ("Equipment Information", cs.equipment_information, 15.0),
            ("Formatting",            cs.formatting,            15.0),
            ("Completeness",          cs.completeness,          10.0),
        ],
        "compliance": [
            (
                c.regulation,
                c.status.value,
                COMPLIANCE_COLOUR.get(c.status, "000000"),
                c.explanation,
            )
            for c in result.compliance
        ],
        "issues": [
            (
                i.rule_id,
                i.severity.value,
                SEVERITY_COLOUR.get(i.severity, "000000"),
                i.affected_section,
                i.description,
                i.recommendation,
            )
            for i in result.issues
        ],
        "recommendations":         result.recommendations,
        "reviewer_comments":       result.reviewer_comments,
        "approval_recommendation": result.approval_recommendation,
    }

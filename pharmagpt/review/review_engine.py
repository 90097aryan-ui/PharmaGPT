"""
review/review_engine.py — Orchestrator for the Validation Review Engine (v0.9.5).

Public API
----------
    result = run_review(content, doc_type, form_data)  → ReviewResult
    avg    = get_avg_score()                           → float
    cache  = get_score_cache()                         → dict[str, float]

The engine is deterministic — no AI calls are made.  It applies all registered
rules and compiles a ReviewResult with score, readiness, compliance matrix, and
issue table.

Score cache
-----------
Scores are kept in an in-memory dict (process lifetime) keyed by a lightweight
hash of the content.  This feeds the dashboard Average Validation Score card
without requiring database schema changes.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date

from pharmagpt.review.review_models import (
    CategoryScores,
    ComplianceCheck,
    ReadinessLevel,
    ReviewIssue,
    ReviewResult,
    Severity,
)
from pharmagpt.review.review_rules import (
    RULE_REGISTRY,
    SEVERITY_DEDUCTIONS,
    evaluate_compliance,
)

logger = logging.getLogger(__name__)

# ── In-memory score cache (keyed by SHA-1 of content[:2000]) ─────────────────
_score_cache: dict[str, float] = {}


def _content_key(content: str) -> str:
    return hashlib.sha1(content[:2000].encode("utf-8", errors="replace")).hexdigest()[:12]


# ── Category deduction pools ─────────────────────────────────────────────────

_CATEGORY_MAX: dict[str, float] = {
    "structure":    CategoryScores.MAX_STRUCTURE,
    "technical":    CategoryScores.MAX_TECHNICAL,
    "equipment":    CategoryScores.MAX_EQUIPMENT,
    "formatting":   CategoryScores.MAX_FORMATTING,
    "completeness": CategoryScores.MAX_COMPLETENESS,
}


def _deduct(pool: float, issues: list[ReviewIssue]) -> float:
    total_deduction = sum(SEVERITY_DEDUCTIONS.get(i.severity, 0) for i in issues)
    return max(0.0, pool - total_deduction)


# ── Readiness thresholds ──────────────────────────────────────────────────────

def _readiness(score: float) -> ReadinessLevel:
    if score >= 85:
        return ReadinessLevel.READY
    if score >= 70:
        return ReadinessLevel.MINOR
    if score >= 50:
        return ReadinessLevel.MAJOR
    return ReadinessLevel.NOT_READY


# ── Reviewer comments generator ───────────────────────────────────────────────

def _build_reviewer_comments(issues: list[ReviewIssue], score: float, doc_type: str) -> str:
    critical = [i for i in issues if i.severity == Severity.CRITICAL]
    major    = [i for i in issues if i.severity == Severity.MAJOR]

    lines = [
        f"Automated QA review completed for {doc_type} document on {date.today().strftime('%d-%b-%Y')}.",
        f"Overall Validation Score: {score:.1f}/100.",
    ]
    if critical:
        lines.append(
            f"CRITICAL ISSUES ({len(critical)}): "
            + "; ".join(i.affected_section for i in critical[:3])
            + ("." if len(critical) <= 3 else " and others.")
        )
    if major:
        lines.append(
            f"MAJOR ISSUES ({len(major)}): "
            + "; ".join(i.affected_section for i in major[:3])
            + ("." if len(major) <= 3 else " and others.")
        )
    if not critical and not major:
        lines.append("No critical or major issues identified. Document structure meets GMP baseline requirements.")

    return "  ".join(lines)


def _build_approval_recommendation(score: float, readiness: ReadinessLevel, issues: list[ReviewIssue]) -> str:
    critical_count = sum(1 for i in issues if i.severity == Severity.CRITICAL)

    if readiness == ReadinessLevel.READY:
        return (
            "RECOMMENDATION: APPROVED FOR QA REVIEW. "
            "Document meets baseline GMP validation standards. "
            "Submit for formal QA review and management approval."
        )
    if readiness == ReadinessLevel.MINOR:
        return (
            "RECOMMENDATION: CONDITIONAL APPROVAL. "
            "Address minor issues identified above before final submission. "
            "QA pre-review may proceed with documented justification."
        )
    if readiness == ReadinessLevel.MAJOR:
        return (
            "RECOMMENDATION: MAJOR REVISION REQUIRED. "
            f"{critical_count} critical and several major issues must be resolved. "
            "Do not submit for QA approval until all critical items are closed."
        )
    return (
        "RECOMMENDATION: NOT READY FOR REVIEW. "
        "Document has significant gaps against GMP/regulatory requirements. "
        "Revise document comprehensively and re-run validation review."
    )


def _build_recommendations(issues: list[ReviewIssue], doc_type: str) -> list[str]:
    """Deduplicated, prioritised recommendation list."""
    seen: set[str] = set()
    recs: list[str] = []

    priority_order = [Severity.CRITICAL, Severity.MAJOR, Severity.MINOR, Severity.OBSERVATION]
    sorted_issues  = sorted(issues, key=lambda i: priority_order.index(i.severity))

    for issue in sorted_issues:
        rec = issue.recommendation
        if rec not in seen:
            seen.add(rec)
            recs.append(f"[{issue.severity.value}] {rec}")

    return recs[:20]  # cap at 20 distinct recommendations


# ── Main entry point ──────────────────────────────────────────────────────────

def run_review(
    content:   str,
    doc_type:  str,
    form_data: dict | None = None,
) -> ReviewResult:
    """
    Run the full deterministic review pipeline on generated markdown content.

    Parameters
    ----------
    content   : The generated markdown document text.
    doc_type  : e.g. "IQ", "OQ", "PQ", "URS", "FMEA", etc.
    form_data : The wizard form_data dict (equipment fields, metadata).

    Returns
    -------
    ReviewResult — fully populated with score, issues, compliance, recommendations.
    """
    form_data = form_data or {}

    # ── 1. Run all structural / content rules ─────────────────────────────────
    all_issues:           list[ReviewIssue]    = []
    issues_by_category:   dict[str, list]      = {k: [] for k in _CATEGORY_MAX}

    for category, rule_fn in RULE_REGISTRY:
        try:
            found = rule_fn(content=content, doc_type=doc_type, form_data=form_data)
            all_issues.extend(found)
            issues_by_category[category].extend(found)
        except Exception:
            logger.exception("Review rule %s failed; skipping.", rule_fn.__name__)

    # ── 2. Category scores ────────────────────────────────────────────────────
    cs = CategoryScores(
        document_structure    = _deduct(_CATEGORY_MAX["structure"],    issues_by_category["structure"]),
        technical_content     = _deduct(_CATEGORY_MAX["technical"],    issues_by_category["technical"]),
        equipment_information = _deduct(_CATEGORY_MAX["equipment"],    issues_by_category["equipment"]),
        formatting            = _deduct(_CATEGORY_MAX["formatting"],   issues_by_category["formatting"]),
        completeness          = _deduct(_CATEGORY_MAX["completeness"], issues_by_category["completeness"]),
    )

    # ── 3. Compliance evaluation (separate scoring bucket) ────────────────────
    compliance_raw  = evaluate_compliance(content, doc_type)
    compliance_list = [
        ComplianceCheck(
            regulation  = r["regulation"],
            status      = r["status"],
            explanation = r["explanation"],
        )
        for r in compliance_raw
    ]

    # Regulatory compliance score: PASS=full share, WARNING=half, FAIL=0
    from pharmagpt.review.review_models import ComplianceStatus
    reg_max   = CategoryScores.MAX_REGULATORY
    per_item  = reg_max / max(len(compliance_list), 1)
    reg_score = sum(
        per_item     if c.status == ComplianceStatus.PASS    else
        per_item / 2 if c.status == ComplianceStatus.WARNING else
        0.0
        for c in compliance_list
    )
    cs.regulatory_compliance = round(min(reg_score, reg_max), 1)

    # ── 4. Overall score ──────────────────────────────────────────────────────
    overall = round(min(cs.total(), 100.0), 1)

    # ── 5. Cache the score ───────────────────────────────────────────────────
    _score_cache[_content_key(content)] = overall

    # ── 6. Readiness & narrative ──────────────────────────────────────────────
    readiness             = _readiness(overall)
    reviewer_comments     = _build_reviewer_comments(all_issues, overall, doc_type)
    approval_rec          = _build_approval_recommendation(overall, readiness, all_issues)
    recommendations       = _build_recommendations(all_issues, doc_type)

    return ReviewResult(
        overall_score           = overall,
        readiness               = readiness,
        category_scores         = cs,
        issues                  = all_issues,
        recommendations         = recommendations,
        compliance              = compliance_list,
        reviewer_comments       = reviewer_comments,
        approval_recommendation = approval_rec,
        doc_type                = doc_type,
    )


# ── Score cache accessors ─────────────────────────────────────────────────────

def get_avg_score() -> float:
    """Return the average validation score across all reviewed documents in this session."""
    if not _score_cache:
        return 0.0
    return round(sum(_score_cache.values()) / len(_score_cache), 1)


def get_score_cache() -> dict[str, float]:
    """Return a copy of the score cache."""
    return dict(_score_cache)

"""
pharmagpt/review — Validation Review Engine (PharmaGPT v0.9.5).

Public API
----------
    from review import run_review, get_avg_score

    result = run_review(content, doc_type, form_data)
    avg    = get_avg_score()
"""

from review.review_engine import run_review, get_avg_score, get_score_cache

__all__ = ["run_review", "get_avg_score", "get_score_cache"]

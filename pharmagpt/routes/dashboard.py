"""
routes/dashboard.py — Home Dashboard statistics endpoints.

Routes
------
GET /dashboard/stats              aggregated system-wide counts and recent activity
GET /dashboard/validation-score   average validation score across reviewed documents (session)
"""

from pharmagpt import database as db
from flask import Blueprint, jsonify
from pharmagpt.review import get_avg_score, get_score_cache

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard/stats", methods=["GET"])
def dashboard_stats():
    """Return aggregated system-wide statistics for the Home Dashboard."""
    return jsonify(db.get_dashboard_stats())


@bp.route("/dashboard/validation-score", methods=["GET"])
def dashboard_validation_score():
    """
    Return the average validation score from the in-session review cache.

    Response: { "avg_score": 82.5, "doc_count": 7 }
    """
    cache = get_score_cache()
    return jsonify({
        "avg_score": get_avg_score(),
        "doc_count": len(cache),
    })

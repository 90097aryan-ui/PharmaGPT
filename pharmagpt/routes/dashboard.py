"""
routes/dashboard.py — Home Dashboard statistics endpoint.

Route
-----
GET /dashboard/stats   aggregated system-wide counts and recent activity
"""

import database as db
from flask import Blueprint, jsonify

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard/stats", methods=["GET"])
def dashboard_stats():
    """Return aggregated system-wide statistics for the Home Dashboard."""
    return jsonify(db.get_dashboard_stats())

"""
routes/brain.py — Yuktav Brain: Global-vs-Client Regulatory Comparison, and
Regulatory Gap Analysis (V1, built beside it).

Routes
------
POST /brain/compare        compare Global Regulatory Knowledge against the
                            caller's own evidence for a question, within one
                            project's context.
POST /brain/gap-analysis   identify, for the same kind of question, every
                            applicable regulatory requirement supported by
                            Global evidence and assess each one's coverage
                            (COVERED / PARTIALLY_COVERED / NOT_COVERED /
                            INSUFFICIENT_EVIDENCE) against the caller's own
                            evidence. Not a replacement for /brain/compare —
                            a second, independent capability on the same
                            blueprint/gate.

Exposes services/brain_comparison.py and services/brain_gap_analysis.py —
Yuktav Brain reasoning capabilities (see PROJECT_MEMORY/DECISIONS.md).
Deliberately not wired into Chat, Validation Generation, or Deviation
Investigation — these routes exist only to expose and verify each capability
on its own.
"""

from flask import Blueprint, g, jsonify, request

from pharmagpt import database as db
from pharmagpt import tenancy
from pharmagpt.auth.workspace_access import require_workspace_access
from pharmagpt.services.brain_comparison import compare_regulatory_evidence
from pharmagpt.services.brain_gap_analysis import analyze_regulatory_gaps

bp = Blueprint("brain", __name__)


@bp.before_request
def _require_workspace_access():
    # Same two-workspace gate routes/chat.py's /stream uses — this is
    # another Brain/AI-assistant-shaped capability, not a new workspace.
    return require_workspace_access("pharmapilot", "validation")


@bp.route("/brain/compare", methods=["POST"])
def compare():
    """
    Body: { "question": "...", "project_id": 3 }

    Returns: {
        regulatory_requirement, client_evidence_summary, compliance_status,
        conclusion, gaps, confidence, evidence_references
    }

    company_id is always g.tenant.company_id — never accepted from the
    request body.
    """
    data       = request.get_json() or {}
    question   = (data.get("question") or "").strip()
    project_id = data.get("project_id")

    if not question:
        return jsonify({"error": "question is required"}), 400
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    project = tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    result = compare_regulatory_evidence(
        question=question, project_id=project_id, company_id=g.tenant.company_id,
    )
    return jsonify(result)


@bp.route("/brain/gap-analysis", methods=["POST"])
def gap_analysis():
    """
    Body: { "question": "...", "project_id": 3 }

    Returns: { requirements, overall_summary, evidence_references }

    company_id is always g.tenant.company_id — never accepted from the
    request body. Regulatory Gap Analysis V1: built beside /brain/compare,
    not a replacement for it — see services/brain_gap_analysis.py.
    """
    data       = request.get_json() or {}
    question   = (data.get("question") or "").strip()
    project_id = data.get("project_id")

    if not question:
        return jsonify({"error": "question is required"}), 400
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    project = tenancy.scoped_or_none(db.get_project(project_id), g.tenant.company_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    result = analyze_regulatory_gaps(
        question=question, project_id=project_id, company_id=g.tenant.company_id,
    )
    return jsonify(result)

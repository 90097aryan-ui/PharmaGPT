"""
routes/qms_market_complaint.py — Market Complaint Management module API
endpoints (P0).

Attachments/comments/audit-trail/e-signature-trail reads are served by
routes/qms_common.py (record_type='market_complaint') — see that module's
VALID_RECORD_TYPES/_GETTERS entries. This file owns CRUD plus the
named-approver, gated lifecycle on MARKET_COMPLAINT_WORKFLOW_V1
(services/workflow_engine.py), the same generic engine CAPA/Change
Control/Deviations use — no engine change.

P0 workflow: Draft (pre-workflow) -> Submitted -> Initial Triage &
Quality-Risk Assessment -> QA Review -> Closed, with a Rejected side path.
Investigation (Investigation Engine), CAPA/Deviation/Risk linkage, AI
Assistant/Report, regulatory notification, and effectiveness-check are P1/P2
and are NOT implemented here — see docs/plan (Market Complaint P0
implementation). `regulatory_profile` is captured at intake as a plain
classification only; no regulator-specific branching exists in this module
(P0 instruction: universal workflow, regulatory detail conditional/future).

Routes
------
GET    /qms/market-complaints                       list complaints (filterable, keyword search)
POST   /qms/market-complaints                        create complaint (auto complaint_number)
GET    /qms/market-complaints/<id>                   get one complaint
PUT    /qms/market-complaints/<id>                   update complaint fields
DELETE /qms/market-complaints/<id>                   delete complaint

GET    /qms/market-complaints/<id>/workflow                        lifecycle state: instance + steps
POST   /qms/market-complaints/<id>/workflow/start                  submit for review
POST   /qms/market-complaints/<id>/workflow/steps/<order>/assign   assign a named approver to an approval step
POST   /qms/market-complaints/<id>/workflow/steps/<order>/decide   approve / reject / advance the current step
"""

import logging
from flask import Blueprint, g, jsonify, request

from pharmagpt import audit
from pharmagpt import audit_events as evt
from pharmagpt import qms_market_complaint_database as mcdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import require_role
from pharmagpt.auth.workspace_access import require_workspace_access
from pharmagpt.services import esignature_service
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.services.supabase_client import get_service_role_client

bp = Blueprint("qms_market_complaint", __name__, url_prefix="/qms/market-complaints")
logger = logging.getLogger(__name__)
RECORD_TYPE = "market_complaint"
WORKFLOW_KEY = "MARKET_COMPLAINT_WORKFLOW_V1"


@bp.before_request
def _require_workspace_access():
    return require_workspace_access("quality")


# ── Market Complaints ────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_complaints():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    filters = {
        "status": request.args.get("status"),
        "severity": request.args.get("severity"),
        "product": request.args.get("product"),
        "market_country": request.args.get("market_country"),
        "department": request.args.get("department"),
        "keyword": request.args.get("q"),
    }
    return jsonify(mcdb.get_all_complaints(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_complaint():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "Complaint title is required"}), 400
    # CRIT-02 parity (Security Audit remediation): creator identity is
    # stamped from the authenticated session, never client input — see
    # database.py::init_db()'s CRIT-02 schema comment and
    # workflow_engine.py::reject_creator_as_approver.
    complaint = mcdb.create_complaint(
        data, company_id=g.tenant.company_id,
        created_by_user_id=g.tenant.user_id, created_by_display_name=g.tenant.display_name,
    )
    audit.log("market_complaint", complaint["id"], evt.COMPLAINT_CREATED, new=complaint)
    return jsonify(complaint), 201


def _record_scoped_or_404(cid):
    return tenancy.scoped_or_none(mcdb.get_complaint(cid), g.tenant.company_id)


@bp.route("/<int:cid>", methods=["GET"])
def get_complaint(cid):
    c = _record_scoped_or_404(cid)
    if not c:
        return jsonify({"error": "Not found"}), 404
    return jsonify(c)


@bp.route("/<int:cid>", methods=["PUT"])
def update_complaint(cid):
    existing = _record_scoped_or_404(cid)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    # Closed is this suite's terminal status (qms_database.py
    # QMS_META.market_complaint_statuses) — must be immutable once reached,
    # same principle as every other QMS record type in this codebase.
    if existing["status"] == "Closed":
        audit.log_failure("market_complaint", cid, "Update blocked (record is Closed)",
                           reason="Closed complaints are immutable")
        return jsonify({"error": "This complaint is Closed and cannot be edited"}), 409
    data = request.get_json() or {}
    # CRIT-01 parity: status/approver-adjacent fields (and complaint_number)
    # must only change through the governed Workflow Engine, never a raw
    # field PUT. Repository-layer enforcement
    # (qms_market_complaint_database.COMPLAINT_CONTROLLED_FIELDS) is the
    # actual security boundary — this check exists for a clear 400 instead
    # of a raised-exception 500 if it's ever reached.
    blocked = mcdb.COMPLAINT_CONTROLLED_FIELDS & data.keys()
    if blocked:
        return jsonify({
            "error": f"{', '.join(sorted(blocked))} cannot be changed via PUT — use "
                     "POST /qms/market-complaints/<id>/workflow/start or "
                     "/qms/market-complaints/<id>/workflow/steps/<order>/decide to move the "
                     "complaint through its lifecycle",
        }), 400
    updated = mcdb.update_complaint(cid, data)
    audit.log("market_complaint", cid, evt.COMPLAINT_UPDATED, old=existing, new=updated)
    return jsonify(updated)


@bp.route("/<int:cid>", methods=["DELETE"])
@require_role("company_admin")
def delete_complaint(cid):
    existing = _record_scoped_or_404(cid)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    mcdb.delete_complaint(cid)
    audit.log("market_complaint", cid, evt.COMPLAINT_DELETED, old=existing)
    return jsonify({"deleted": True})


# ── Workflow: named-approver, gated complaint lifecycle ──────────────────────
# Same engine as routes/qms_capa.py/qms_change_control.py — see
# services/workflow_engine.py. No legacy "/approval" free-action wrapper
# here (unlike CAPA/Change Control/Deviations) — Market Complaint is a new
# module with no prior frontend contract to preserve, so the Workflow Panel
# (assign + decide) is its only lifecycle surface in P0.

@bp.route("/<int:cid>/workflow", methods=["GET"])
def get_workflow(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(wfe.get_instance_state(RECORD_TYPE, cid))


@bp.route("/<int:cid>/workflow/start", methods=["POST"])
def start_workflow(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    sig = tenancy.signing_identity(g.tenant)
    try:
        state = wfe.start_instance(WORKFLOW_KEY, RECORD_TYPE, cid, g.tenant.company_id,
                                    sig["performed_by"], tenant=g.tenant)
    except wfe.WorkflowError as e:
        audit.log_failure("market_complaint", cid, "Workflow start blocked", reason=str(e))
        return jsonify({"error": str(e)}), 409
    audit.log("market_complaint", cid, evt.COMPLAINT_WORKFLOW_TRANSITION, detail="Submitted")
    return jsonify(state), 201


@bp.route("/<int:cid>/workflow/steps/<int:step_order>/assign", methods=["POST"])
def assign_workflow_step(cid, step_order):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    approvers = data.get("approvers") or []
    if not isinstance(approvers, list) or not all(a.get("user_id") for a in approvers):
        return jsonify({"error": "approvers must be a non-empty list of {user_id, display_name}"}), 400
    # CRIT-02 parity: a proposed approver must be a real, active user of THIS
    # company — otherwise any authenticated caller could name a user_id
    # belonging to a different tenant. Creator-vs-approver segregation of
    # duties is enforced one layer down, inside wfe.assign_approvers()
    # itself (services/workflow_engine.py::reject_creator_as_approver) — no
    # separate check needed here for that.
    invalid = tenancy.missing_or_inactive_users(
        get_service_role_client(), g.tenant.company_id, {a["user_id"] for a in approvers},
    )
    if invalid:
        return jsonify({"error": f"Not a valid, active user of this company: {', '.join(sorted(invalid))}"}), 400
    try:
        state = wfe.assign_approvers(RECORD_TYPE, cid, step_order, approvers)
    except wfe.WorkflowError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify(state)


@bp.route("/<int:cid>/workflow/steps/<int:step_order>/decide", methods=["POST"])
def decide_workflow_step(cid, step_order):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    decision = data.get("decision", "")
    if decision not in ("approve", "reject", "advance"):
        return jsonify({"error": "decision must be one of approve/reject/advance"}), 400

    # Electronic Signature gate (21 CFR Part 11 / EU GMP Annex 11) — same
    # gate already applied to every other QMS module's workflow decisions.
    old_status = complaint["status"]
    try:
        esignature_service.require_esignature(
            g.tenant, data.get("password", ""), data.get("meaning", ""), data.get("reason", ""),
        )
    except esignature_service.ReauthenticationError as exc:
        audit.log_failure("market_complaint", cid, f"Workflow decision blocked ({decision}) — e-signature failed",
                           reason=str(exc))
        return jsonify({"error": str(exc)}), 401
    except esignature_service.ESignatureError as exc:
        audit.log_failure("market_complaint", cid, evt.ESIGNATURE_FAILURE, reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    sig = tenancy.signing_identity(g.tenant)
    try:
        state = wfe.decide_step(
            RECORD_TYPE, cid, step_order, decision,
            user_id=g.tenant.user_id, role=g.tenant.role,
            performed_by=sig["performed_by"], comments=data.get("comments", ""),
            tenant=g.tenant,
        )
    except wfe.WorkflowPermissionError as e:
        audit.log_failure("market_complaint", cid, f"Workflow decision blocked ({decision})", reason=str(e))
        return jsonify({"error": str(e)}), 403
    except wfe.WorkflowError as e:
        audit.log_failure("market_complaint", cid, f"Workflow decision blocked ({decision})", reason=str(e))
        return jsonify({"error": str(e)}), 409

    complaint = mcdb.get_complaint(cid)
    esignature_service.record_signature(
        tenant=g.tenant, meaning=data.get("meaning", ""), reason=data.get("reason", ""),
        record_type="market_complaint", record_id=cid,
        old_status=old_status, new_status=complaint.get("status", ""),
    )
    event = {
        "reject": evt.COMPLAINT_REJECTED, "approve": evt.COMPLAINT_APPROVED,
    }.get(decision, evt.COMPLAINT_WORKFLOW_TRANSITION)
    audit.log("market_complaint", cid, event, detail=f"decision={decision}")
    return jsonify(state)

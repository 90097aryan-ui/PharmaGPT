"""
routes/qms_market_complaint.py — Market Complaint Management module API
endpoints (P0 + P1-A).

Attachments/comments/audit-trail/e-signature-trail reads are served by
routes/qms_common.py (record_type='market_complaint') — see that module's
VALID_RECORD_TYPES/_GETTERS entries. This file owns CRUD plus the
named-approver, gated lifecycle on MARKET_COMPLAINT_WORKFLOW_V1
(services/workflow_engine.py), the same generic engine CAPA/Change
Control/Deviations use — no engine change.

P0 workflow: Draft (pre-workflow) -> Submitted -> Initial Triage &
Quality-Risk Assessment -> QA Review -> Closed, with a Rejected side path.
`regulatory_profile` is captured at intake as a plain classification only;
no regulator-specific branching exists in this module (P0 instruction:
universal workflow, regulatory detail conditional/future).

P1-A adds the Investigation Case (evidence, SOP review, interviews,
timeline, AI Assistant/Report, root cause, investigation summary, tasks,
Evidence Dashboard) — thin wrappers delegating to the existing, generic
services/investigation_engine.py with record_type='market_complaint', the
exact same pattern routes/qms_deviations.py's own `/investigation/*`
sub-routes already use (no new Investigation table, no engine change).
CAPA/Deviation/Risk/Change Control linkage, Impact/Scope, Effectiveness
Check, regulatory notification, and Market Action/Recall are still P1-B+
and are NOT implemented here.

Routes
------
GET    /qms/market-complaints                       list complaints (filterable, keyword search)
POST   /qms/market-complaints                        create complaint (auto complaint_number)
GET    /qms/market-complaints/<id>                   get one complaint (includes investigation_unlocked/lock_reason)
PUT    /qms/market-complaints/<id>                   update complaint fields
DELETE /qms/market-complaints/<id>                   delete complaint

GET    /qms/market-complaints/<id>/workflow                        lifecycle state: instance + steps
POST   /qms/market-complaints/<id>/workflow/start                  submit for review
POST   /qms/market-complaints/<id>/workflow/steps/<order>/assign   assign a named approver to an approval step
POST   /qms/market-complaints/<id>/workflow/assign-all             assign named approver(s) to MULTIPLE approval
                                                                     steps in one atomic call (upfront-assignment UX)
POST   /qms/market-complaints/<id>/workflow/steps/<order>/decide   approve / reject / advance the current step

GET/POST /qms/market-complaints/<id>/investigation/evidence            Investigation Case — evidence/documents
GET/POST /qms/market-complaints/<id>/investigation/sop-review          Investigation Case — applicable SOP review
GET/POST /qms/market-complaints/<id>/investigation/interviews          Investigation Case — personnel interviews
GET/POST /qms/market-complaints/<id>/investigation/timeline            Investigation Case — timeline builder
POST     /qms/market-complaints/<id>/investigation/ai/assistant        Investigation Case — AI Assistant (interactive)
POST     /qms/market-complaints/<id>/investigation/ai/report           Investigation Case — AI Report Generation
GET      /qms/market-complaints/<id>/investigation/ai/history          Investigation Case — every AI run, both modes
GET/PUT  /qms/market-complaints/<id>/investigation/root-cause          Investigation Case — Possible/Probable/Confirmed root cause
GET/PUT  /qms/market-complaints/<id>/investigation/summary             Investigation Case — finalized handoff summary
GET      /qms/market-complaints/<id>/investigation/dashboard           Investigation Case — rules-based Evidence Dashboard
GET/POST /qms/market-complaints/<id>/investigation/tasks               Investigation Case — investigation tasks
PUT      /qms/market-complaints/<id>/investigation/tasks/<task_id>     Investigation Case — update a task
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
from pharmagpt.services import investigation_engine as inv
from pharmagpt.services import workflow_engine as wfe
from pharmagpt.services.supabase_client import get_service_role_client

bp = Blueprint("qms_market_complaint", __name__, url_prefix="/qms/market-complaints")
logger = logging.getLogger(__name__)
RECORD_TYPE = "market_complaint"
WORKFLOW_KEY = "MARKET_COMPLAINT_WORKFLOW_V1"
# P1-A: the Investigation Case unlocks once Triage & Risk Assessment is
# approved — same role this constant plays as routes/qms_deviations.py's
# own UNLOCK_STEP_KEY = "qa_approval" (see _investigation_lock below for
# the one extra Market-Complaint-specific precondition Deviation doesn't
# need: investigation_required == "Yes").
INVESTIGATION_UNLOCK_STEP_KEY = "triage_risk_assessment"


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


def _investigation_lock(complaint: dict) -> tuple[bool, str]:
    """Investigation Case unlock gate (P1-A) — server-side, mirrors
    routes/qms_deviations.py::_investigation_lock's wfe.is_unlocked() call
    exactly, plus one Market-Complaint-specific precondition Deviation
    doesn't need: investigation_required must be "Yes" (P0's own intake
    field — see qms_database.py's "Investigation gate (P1 wires the
    Investigation Engine to these)" comment). All three preconditions —
    record exists (caller's _record_scoped_or_404), Triage & Risk
    Assessment approved, investigation_required == "Yes" — are enforced
    here, not just hidden in the UI: every investigation route below
    computes this and passes it straight into
    services/investigation_engine.py, which itself refuses any write when
    unlocked=False (raises InvestigationLockedError) — so a future route
    added to this file can't accidentally skip the check."""
    if (complaint.get("investigation_required") or "") != "Yes":
        return False, "Investigation is not required for this complaint"
    return wfe.is_unlocked(RECORD_TYPE, complaint["id"], INVESTIGATION_UNLOCK_STEP_KEY)


@bp.route("/<int:cid>", methods=["GET"])
def get_complaint(cid):
    c = _record_scoped_or_404(cid)
    if not c:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(c)
    c["investigation_unlocked"] = unlocked
    c["lock_reason"] = reason
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


@bp.route("/<int:cid>/workflow/assign-all", methods=["POST"])
def assign_all_workflow_steps(cid):
    """Upfront-assignment UX: assign named approver(s) to several approval
    steps in ONE request instead of one call per step (see
    workflow_panel.js's Market-Complaint-only "Workflow Approvers" panel).
    Body: {"assignments": [{"step_order": 2, "approvers": [...]}, ...]} —
    same per-entry shape as .../steps/<order>/assign, just batched.

    Atomicity: every proposed user_id across every step is validated in ONE
    tenancy.missing_or_inactive_users() pass, and wfe.assign_approvers_bulk()
    validates every step (existence/type/status/creator) before writing
    any of them — a single invalid step or approver rejects the WHOLE
    request with nothing persisted, never a partial assignment."""
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    assignments = data.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        return jsonify({"error": "assignments must be a non-empty list of {step_order, approvers}"}), 400

    step_assignments = {}
    all_user_ids = set()
    for entry in assignments:
        step_order = entry.get("step_order")
        approvers = entry.get("approvers") or []
        if not isinstance(step_order, int):
            return jsonify({"error": "each assignment requires an integer step_order"}), 400
        if not isinstance(approvers, list) or not all(a.get("user_id") for a in approvers):
            return jsonify({
                "error": f"step {step_order}: approvers must be a non-empty list of {{user_id, display_name}}",
            }), 400
        step_assignments[step_order] = approvers
        all_user_ids.update(a["user_id"] for a in approvers)

    # CRIT-02 parity (same check as the single-step endpoint below), applied
    # once to the UNION of every requested user_id so an invalid id anywhere
    # in the batch blocks the whole request before anything is persisted.
    invalid = tenancy.missing_or_inactive_users(get_service_role_client(), g.tenant.company_id, all_user_ids)
    if invalid:
        return jsonify({"error": f"Not a valid, active user of this company: {', '.join(sorted(invalid))}"}), 400

    try:
        state = wfe.assign_approvers_bulk(RECORD_TYPE, cid, step_assignments)
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


# ── Investigation Case (P1-A; services/investigation_engine.py) ─────────────
# Thin wrappers only, same pattern as routes/qms_deviations.py's own
# `/investigation/*` sub-routes: check the record exists + resolve the
# lock, then delegate to the engine with record_type="market_complaint".
# Every mutating engine call gets `unlocked` explicitly — the engine itself
# refuses to write if False, so this check can't be silently skipped by a
# future route. GET routes are never lock-gated (same as Deviation): there
# is nothing to read until something has been written, and writes are
# gated — matching the established, already-tested precedent exactly
# (tests/test_qms_routes.py::test_deviation_investigation_case_locked_until_qa_approval).

def _investigation_context(complaint: dict) -> dict:
    """Generic context dict handed to the record-type-agnostic AI prompts —
    see prompts/investigation_prompt.py."""
    return {
        "Complaint Number": complaint.get("complaint_number", ""),
        "Title": complaint.get("title", ""),
        "Product": complaint.get("product", ""),
        "Batch/Lot": complaint.get("batch_lot", ""),
        "Market/Country": complaint.get("market_country", ""),
        "Classification": complaint.get("initial_classification", ""),
        "Severity": complaint.get("severity", ""),
        "Description": complaint.get("description", ""),
        "Initial Impact Assessment": complaint.get("initial_impact_assessment", ""),
        "Immediate Containment Action": complaint.get("immediate_containment_action", ""),
    }


@bp.route("/<int:cid>/investigation/evidence", methods=["GET"])
def list_investigation_evidence(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_evidence(RECORD_TYPE, cid))


@bp.route("/<int:cid>/investigation/evidence", methods=["POST"])
def add_investigation_evidence(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    try:
        entry = inv.add_evidence(RECORD_TYPE, cid, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "Investigation evidence added", detail=entry.get("category", ""))
    return jsonify(entry), 201


@bp.route("/<int:cid>/investigation/sop-review", methods=["GET"])
def list_investigation_sop_reviews(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_sop_reviews(RECORD_TYPE, cid))


@bp.route("/<int:cid>/investigation/sop-review", methods=["POST"])
def add_investigation_sop_review(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    try:
        entry = inv.add_sop_review(RECORD_TYPE, cid, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "SOP review entry added", detail=entry.get("doc_reference", ""))
    return jsonify(entry), 201


@bp.route("/<int:cid>/investigation/interviews", methods=["GET"])
def list_investigation_interviews(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_interviews(RECORD_TYPE, cid))


@bp.route("/<int:cid>/investigation/interviews", methods=["POST"])
def add_investigation_interview(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    try:
        entry = inv.add_interview(RECORD_TYPE, cid, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "Interview recorded", detail=entry.get("interviewee_name", ""))
    return jsonify(entry), 201


@bp.route("/<int:cid>/investigation/timeline", methods=["GET"])
def list_investigation_timeline(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_timeline_events(RECORD_TYPE, cid))


@bp.route("/<int:cid>/investigation/timeline", methods=["POST"])
def add_investigation_timeline_event(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    try:
        entry = inv.add_timeline_event(RECORD_TYPE, cid, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "Timeline event added", detail=entry.get("event_type", ""))
    return jsonify(entry), 201


@bp.route("/<int:cid>/investigation/ai/assistant", methods=["POST"])
def run_investigation_ai_assistant(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    sig = tenancy.signing_identity(g.tenant)
    data = request.get_json() or {}
    try:
        run = inv.run_ai_assistant(
            RECORD_TYPE, cid, _investigation_context(complaint), question=data.get("question", ""),
            generated_by=sig["performed_by"], unlocked=unlocked,
        )
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "AI Investigation Assistant run")
    return jsonify(run), 201


@bp.route("/<int:cid>/investigation/ai/report", methods=["POST"])
def run_investigation_ai_report(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    sig = tenancy.signing_identity(g.tenant)
    investigation_data = {
        "interviews": inv.get_interviews(RECORD_TYPE, cid),
        "timeline": inv.get_timeline_events(RECORD_TYPE, cid),
        "root_cause": inv.get_root_cause(RECORD_TYPE, cid),
    }
    try:
        run = inv.run_ai_report(
            RECORD_TYPE, cid, _investigation_context(complaint), investigation_data,
            generated_by=sig["performed_by"], unlocked=unlocked,
        )
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "AI Investigation Report generated")
    return jsonify(run), 201


@bp.route("/<int:cid>/investigation/ai/history", methods=["GET"])
def get_investigation_ai_history(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_ai_history(RECORD_TYPE, cid, request.args.get("mode")))


@bp.route("/<int:cid>/investigation/root-cause", methods=["GET"])
def get_investigation_root_cause(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_root_cause(RECORD_TYPE, cid) or {})


@bp.route("/<int:cid>/investigation/root-cause", methods=["PUT"])
def save_investigation_root_cause(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    try:
        entry = inv.save_root_cause(RECORD_TYPE, cid, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "Root cause updated")
    return jsonify(entry)


@bp.route("/<int:cid>/investigation/summary", methods=["GET"])
def get_investigation_summary(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_summary(RECORD_TYPE, cid) or {})


@bp.route("/<int:cid>/investigation/summary", methods=["PUT"])
def save_investigation_summary(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    sig = tenancy.signing_identity(g.tenant)
    try:
        entry = inv.finalize_summary(
            RECORD_TYPE, cid, request.get_json() or {}, finalized_by=sig["performed_by"], unlocked=unlocked,
        )
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "Investigation Summary finalized")
    return jsonify(entry)


@bp.route("/<int:cid>/investigation/dashboard", methods=["GET"])
def get_investigation_dashboard(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_dashboard(RECORD_TYPE, cid))


# ── Investigation Tasks ───────────────────────────────────────────────────────
# Investigative activities, not Workflow steps — same lock/423 + audit-trail
# pattern as every other investigation sub-route above.

@bp.route("/<int:cid>/investigation/tasks", methods=["GET"])
def list_investigation_tasks(cid):
    if not _record_scoped_or_404(cid):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_tasks(RECORD_TYPE, cid))


@bp.route("/<int:cid>/investigation/tasks", methods=["POST"])
def add_investigation_task(cid):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    data = request.get_json() or {}
    data["created_by"] = tenancy.signing_identity(g.tenant)["performed_by"]
    try:
        entry = inv.add_task(RECORD_TYPE, cid, data, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "Investigation task added", detail=entry.get("title", ""))
    return jsonify(entry), 201


@bp.route("/<int:cid>/investigation/tasks/<int:task_id>", methods=["PUT"])
def update_investigation_task(cid, task_id):
    complaint = _record_scoped_or_404(cid)
    if not complaint:
        return jsonify({"error": "Not found"}), 404
    existing = inv.get_task_scoped(task_id, RECORD_TYPE, cid)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(complaint)
    try:
        entry = inv.update_task(task_id, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("market_complaint", cid, "Investigation task updated", old=existing, new=entry)
    return jsonify(entry)

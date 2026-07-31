"""
routes/qms_deviations.py — Deviation Management module API endpoints.

Attachments/comments/audit-trail reads are served by routes/qms_common.py
(record_type='deviation'). Approval/status-transition is a gated,
named-approver **Workflow** (services/workflow_engine.py, unchanged since
Phase 1) over a high-level lifecycle only — architecture refactor,
PHASE1_REFACTOR_PLAN.md: Draft -> Submitted -> Review (Initiator Manager
Review -> QA Manager Review -> QA Approval) -> Investigation -> CAPA (QA
Review -> Final Approval) -> Effectiveness Check -> Closure, with a
Rejected/Returned-for-Investigation side path. "Review" and "CAPA" are
UI-only groupings (see PHASE_GROUPS below) over unchanged individual
approval steps — the workflow engine itself was not modified.

Investigation activities (evidence, SOP review, interviews, timeline, AI
assistance, root cause, the CAPA-handoff summary) are a separate concern —
the **Investigation Case** — served by this same blueprint's
`/investigation/*` sub-routes, which are thin wrappers delegating to
services/investigation_engine.py (a reusable service, not its own exposed
API surface). The Investigation Case unlocks once the 'qa_approval' step is
approved and has no workflow transitions of its own — every sub-tab is
freely navigable and re-runnable.

Routes
------
GET    /qms/deviations                       list deviations (filterable, keyword search)
POST   /qms/deviations                       create deviation (auto deviation_number)
GET    /qms/deviations/<id>                  get one deviation (includes investigation_unlocked/lock_reason)
PUT    /qms/deviations/<id>                  update deviation fields
DELETE /qms/deviations/<id>                  delete deviation

GET    /qms/deviations/<id>/workflow                       lifecycle state: instance + steps + phase grouping + dashboard fields
GET    /qms/deviations/<id>/workflow-builder                Draft-time approver configuration for the whole lifecycle:
                                                             {"steps": [...] (Review chain), "capa_phase": {...}
                                                             (QA Review + Final Approval)} — the Workflow Builder
PUT    /qms/deviations/<id>/workflow-builder                replace both (Draft only; Review chain's last step is
                                                             always QA Approval)
POST   /qms/deviations/<id>/workflow/start                 submit for review (compiles the Workflow Builder into a fresh
                                                             per-deviation template, instantiates it, and assigns every
                                                             configured step's approver — no separate assignment step)
POST   /qms/deviations/<id>/workflow/steps/<order>/decide   approve / reject / return / advance the current step

GET/POST /qms/deviations/<id>/investigation/evidence            Investigation Case — evidence/documents
GET/POST /qms/deviations/<id>/investigation/sop-review          Investigation Case — applicable SOP review
GET/POST /qms/deviations/<id>/investigation/interviews          Investigation Case — personnel interviews
GET/POST /qms/deviations/<id>/investigation/timeline            Investigation Case — timeline builder
POST     /qms/deviations/<id>/investigation/ai/assistant        Investigation Case — AI Assistant (interactive)
POST     /qms/deviations/<id>/investigation/ai/report           Investigation Case — AI Report Generation
GET      /qms/deviations/<id>/investigation/ai/history          Investigation Case — every AI run, both modes
GET/PUT  /qms/deviations/<id>/investigation/root-cause          Investigation Case — Possible/Probable/Confirmed root cause
GET/PUT  /qms/deviations/<id>/investigation/summary             Investigation Case — finalized CAPA handoff
GET      /qms/deviations/<id>/investigation/dashboard           Investigation Case — rules-based Evidence Dashboard
GET/POST /qms/deviations/<id>/investigation/tasks                Investigation Case — investigation tasks
PUT      /qms/deviations/<id>/investigation/tasks/<task_id>      Investigation Case — update a task
GET      /qms/deviations/<id>/investigation/knowledge-base       Investigation Case — KB/previous-record suggestions (read-only)
POST     /qms/deviations/<id>/investigation/knowledge-base/accept-sop  Investigation Case — accept a KB suggestion into SOP review

POST   /qms/deviations/<id>/suggest-impact   AI-suggested impact assessment entries (not persisted)
GET    /qms/deviations/<id>/impact           list impact assessment entries
POST   /qms/deviations/<id>/impact           add impact assessment entry

POST   /qms/deviations/<id>/suggest-capa     AI-suggested CAPA seed content (not persisted)
POST   /qms/deviations/<id>/link-capa        link this deviation to an existing/new CAPA
GET    /qms/deviations/<id>/capas            list linked CAPAs

GET    /qms/deviations/<id>/report           markdown report (preview / print)
POST   /qms/deviations/<id>/export/docx      DOCX export
"""

import io
import logging
import re
import uuid
from flask import Blueprint, g, jsonify, request, send_file

from pharmagpt import audit
from pharmagpt import config
from pharmagpt import database as db
from pharmagpt import equipment_database as equipdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import qms_capa_database as cdb
from pharmagpt import qms_database as qmsdb
from pharmagpt import qms_workflow_database as wfdb
from pharmagpt import tenancy
from pharmagpt.auth.decorators import extract_bearer_token, require_role
from pharmagpt.db import qms_repo
from pharmagpt.services import investigation_engine as inv
from pharmagpt.services import qms_deviation_service as svc
from pharmagpt.services import retrieval_engine
from pharmagpt.services import workflow_engine as wfe

bp = Blueprint("qms_deviations", __name__, url_prefix="/qms/deviations")
logger = logging.getLogger(__name__)
RECORD_TYPE = "deviation"
WORKFLOW_KEY = "DEVIATION_LIFECYCLE_V2"
UNLOCK_STEP_KEY = "qa_approval"

# UI-only lifecycle grouping over DEVIATION_LIFECYCLE_V2's individual steps
# (architecture refactor §2/§4) — the underlying approval steps, their named
# approvers, and their audit trail are completely unchanged; this only
# controls what phase label the Lifecycle tab shows.
PHASE_GROUPS = {
    "submitted": "Submitted",
    "initiator_mgr_review": "Review",  # legacy DEVIATION_LIFECYCLE_V2 key — kept for any instance started before the Workflow Builder
    "qa_mgr_review": "Review",         # legacy DEVIATION_LIFECYCLE_V2 key — kept for any instance started before the Workflow Builder
    "qa_approval": "Review",
    "evidence_collection": "Investigation",  # step_key kept from V1 for engine compat; displays as "Investigation"
    "qa_review": "CAPA",
    "final_approval": "CAPA",
    "effectiveness_check": "Effectiveness Check",
    "closed": "Closure",
}


def _phase_for_step_key(step_key: str) -> str:
    """PHASE_GROUPS lookup, generalized for the Workflow Builder's dynamic
    (unlimited, per-deviation) Review steps: only their step_key
    ('review_step_<order>') isn't a fixed dict entry — everything else
    (including 'qa_approval', still the mandatory final step) is unchanged."""
    if step_key in PHASE_GROUPS:
        return PHASE_GROUPS[step_key]
    if step_key.startswith("review_step_"):
        return "Review"
    return step_key


# ── Phase 3.5 dual-write (docs/PHASE3_EXECUTION_PLAN.md) ───────────────────────
# Same non-blocking policy as every other Phase 3 domain: active only when
# QMS_BACKEND=dual, never raises, SQLite stays the source of truth.

def _resolve_project_postgres_id(project_id):
    if not project_id:
        return None
    project = db.get_project(project_id)
    return (project or {}).get("postgres_id")


def _dual_write_create(deviation: dict, audit_action: str, performed_by: str) -> None:
    if config.QMS_BACKEND != "dual":
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        pg_row = qms_repo.create_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE,
            title=deviation["title"], status=deviation.get("status") or "open",
            project_id=_resolve_project_postgres_id(deviation.get("project_id")),
        )
        ddb.set_deviation_postgres_id(deviation["id"], pg_row["id"])
        qms_repo.add_audit_entry(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, pg_row["id"],
            audit_action, actor_user_id=tenant.user_id,
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync new deviation %s to Postgres", deviation["id"])


def _dual_write_update(deviation: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = deviation.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.update_record(
            extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id,
            title=deviation["title"], status=deviation.get("status") or "open",
            project_id=_resolve_project_postgres_id(deviation.get("project_id")),
        )
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to sync deviation %s update to Postgres", deviation["id"])


def _dual_write_delete(deviation: dict) -> None:
    if config.QMS_BACKEND != "dual":
        return
    postgres_id = deviation.get("postgres_id")
    if not postgres_id:
        return
    tenant = g.tenant
    if not tenant.company_id:
        return
    try:
        qms_repo.delete_record(extract_bearer_token(), tenant.company_id, RECORD_TYPE, postgres_id)
    except Exception:
        logger.exception("Phase 3.5 dual-write: failed to delete deviation %s in Postgres", deviation["id"])


# ── Deviations ─────────────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_deviations():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    filters = {
        "deviation_type": request.args.get("type"),
        "deviation_category": request.args.get("category"),
        "status": request.args.get("status"),
        "department": request.args.get("department"),
        "keyword": request.args.get("q"),
    }
    return jsonify(ddb.get_all_deviations(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("", methods=["POST"])
def create_deviation():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("title", "").strip():
        return jsonify({"error": "Deviation title is required"}), 400
    deviation = ddb.create_deviation(data, company_id=g.tenant.company_id)
    ddb.seed_default_workflow_steps(deviation["id"])
    performed_by = tenancy.signing_identity(g.tenant)["performed_by"]
    audit.log("deviation", deviation["id"], "Deviation initiated", new=deviation)
    _dual_write_create(deviation, "Deviation initiated", performed_by)
    return jsonify(deviation), 201


def _investigation_lock(did: int) -> tuple[bool, str]:
    return wfe.is_unlocked(RECORD_TYPE, did, UNLOCK_STEP_KEY)


@bp.route("/<int:did>", methods=["GET"])
def get_deviation(did):
    d = tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id)
    if not d:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    d["investigation_unlocked"] = unlocked
    d["lock_reason"] = reason
    return jsonify(d)


@bp.route("/<int:did>", methods=["PUT"])
def update_deviation(did):
    existing = tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    # Phase F (WP3, workflow enforcement): Closed is this suite's terminal
    # status (qms_database.py QMS_META.deviation_statuses) — must be
    # immutable once reached, same principle as the other GxP record types.
    if existing["status"] == "Closed":
        audit.log_failure("deviation", did, "Update blocked (record is Closed)",
                           reason="Closed deviations are immutable")
        return jsonify({"error": "This deviation is Closed and cannot be edited"}), 409
    data = request.get_json() or {}
    updated = ddb.update_deviation(did, data)
    _dual_write_update(updated)
    audit.log("deviation", did, "Updated", old=existing, new=updated)
    return jsonify(updated)


@bp.route("/<int:did>", methods=["DELETE"])
@require_role("company_admin")
def delete_deviation(did):
    existing = tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    ddb.delete_deviation(did)
    _dual_write_delete(existing)
    audit.log("deviation", did, "Deleted", old=existing)
    return jsonify({"deleted": True})


# ── Investigation Case (services/investigation_engine.py) ───────────────────
# Thin wrappers only: check the record exists + resolve the lock, then
# delegate to the engine with record_type="deviation". Every mutating engine
# call gets `unlocked` explicitly — the engine itself refuses to write if
# False, so this check can't be silently skipped by a future route.

def _investigation_context(deviation: dict) -> dict:
    """Generic context dict handed to the record-type-agnostic AI prompts —
    see prompts/investigation_prompt.py."""
    return {
        "Deviation Number": deviation.get("deviation_number", ""),
        "Title": deviation.get("title", ""),
        "Type": deviation.get("deviation_type", ""),
        "Category": deviation.get("deviation_category", ""),
        "Department": deviation.get("department", ""),
        "Product": deviation.get("product", ""),
        "Batch/Lot": deviation.get("batch_lot", ""),
        "Description": deviation.get("description", ""),
        "Immediate Action Taken": deviation.get("immediate_action", ""),
    }


@bp.route("/<int:did>/investigation/evidence", methods=["GET"])
def list_investigation_evidence(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_evidence(RECORD_TYPE, did))


@bp.route("/<int:did>/investigation/evidence", methods=["POST"])
def add_investigation_evidence(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    try:
        entry = inv.add_evidence(RECORD_TYPE, did, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "Investigation evidence added", detail=entry.get("category", ""))
    return jsonify(entry), 201


@bp.route("/<int:did>/investigation/sop-review", methods=["GET"])
def list_investigation_sop_reviews(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_sop_reviews(RECORD_TYPE, did))


@bp.route("/<int:did>/investigation/sop-review", methods=["POST"])
def add_investigation_sop_review(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    try:
        entry = inv.add_sop_review(RECORD_TYPE, did, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "SOP review entry added", detail=entry.get("doc_reference", ""))
    return jsonify(entry), 201


@bp.route("/<int:did>/investigation/interviews", methods=["GET"])
def list_investigation_interviews(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_interviews(RECORD_TYPE, did))


@bp.route("/<int:did>/investigation/interviews", methods=["POST"])
def add_investigation_interview(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    try:
        entry = inv.add_interview(RECORD_TYPE, did, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "Interview recorded", detail=entry.get("interviewee_name", ""))
    return jsonify(entry), 201


@bp.route("/<int:did>/investigation/timeline", methods=["GET"])
def list_investigation_timeline(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_timeline_events(RECORD_TYPE, did))


@bp.route("/<int:did>/investigation/timeline", methods=["POST"])
def add_investigation_timeline_event(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    try:
        entry = inv.add_timeline_event(RECORD_TYPE, did, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "Timeline event added", detail=entry.get("event_type", ""))
    return jsonify(entry), 201


@bp.route("/<int:did>/investigation/ai/assistant", methods=["POST"])
def run_investigation_ai_assistant(did):
    deviation = _record_scoped_or_404(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    sig = tenancy.signing_identity(g.tenant)
    data = request.get_json() or {}
    try:
        run = inv.run_ai_assistant(
            RECORD_TYPE, did, _investigation_context(deviation), question=data.get("question", ""),
            generated_by=sig["performed_by"], unlocked=unlocked,
        )
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "AI Investigation Assistant run")
    return jsonify(run), 201


@bp.route("/<int:did>/investigation/ai/report", methods=["POST"])
def run_investigation_ai_report(did):
    deviation = _record_scoped_or_404(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    sig = tenancy.signing_identity(g.tenant)
    investigation_data = {
        "interviews": inv.get_interviews(RECORD_TYPE, did),
        "timeline": inv.get_timeline_events(RECORD_TYPE, did),
        "root_cause": inv.get_root_cause(RECORD_TYPE, did),
    }
    try:
        run = inv.run_ai_report(
            RECORD_TYPE, did, _investigation_context(deviation), investigation_data,
            generated_by=sig["performed_by"], unlocked=unlocked,
        )
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "AI Investigation Report generated")
    return jsonify(run), 201


@bp.route("/<int:did>/investigation/ai/history", methods=["GET"])
def get_investigation_ai_history(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_ai_history(RECORD_TYPE, did, request.args.get("mode")))


@bp.route("/<int:did>/investigation/root-cause", methods=["GET"])
def get_investigation_root_cause(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_root_cause(RECORD_TYPE, did) or {})


@bp.route("/<int:did>/investigation/root-cause", methods=["PUT"])
def save_investigation_root_cause(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    try:
        entry = inv.save_root_cause(RECORD_TYPE, did, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "Root cause updated")
    return jsonify(entry)


@bp.route("/<int:did>/investigation/summary", methods=["GET"])
def get_investigation_summary(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_summary(RECORD_TYPE, did) or {})


@bp.route("/<int:did>/investigation/summary", methods=["PUT"])
def save_investigation_summary(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    sig = tenancy.signing_identity(g.tenant)
    try:
        entry = inv.finalize_summary(
            RECORD_TYPE, did, request.get_json() or {}, finalized_by=sig["performed_by"], unlocked=unlocked,
        )
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "Investigation Summary finalized")
    return jsonify(entry)


@bp.route("/<int:did>/investigation/dashboard", methods=["GET"])
def get_investigation_dashboard(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_dashboard(RECORD_TYPE, did))


# ── Investigation Tasks (Phase 2 Part 1) ─────────────────────────────────────
# Investigative activities, not Workflow steps or CAPA actions — same
# lock/423 + audit-trail pattern as every other investigation sub-route
# above. "Evidence Attachment" reuses the existing attachments endpoint
# (routes/qms_common.py, record_type="deviation") rather than a dedicated
# per-task upload route — the investigator uploads once against the
# deviation and links the returned attachment_id here.

@bp.route("/<int:did>/investigation/tasks", methods=["GET"])
def list_investigation_tasks(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(inv.get_tasks(RECORD_TYPE, did))


@bp.route("/<int:did>/investigation/tasks", methods=["POST"])
def add_investigation_task(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    data = request.get_json() or {}
    data["created_by"] = tenancy.signing_identity(g.tenant)["performed_by"]
    try:
        entry = inv.add_task(RECORD_TYPE, did, data, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "Investigation task added", detail=entry.get("title", ""))
    return jsonify(entry), 201


@bp.route("/<int:did>/investigation/tasks/<int:task_id>", methods=["PUT"])
def update_investigation_task(did, task_id):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    existing = inv.get_task_scoped(task_id, RECORD_TYPE, did)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    try:
        entry = inv.update_task(task_id, request.get_json() or {}, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "Investigation task updated", old=existing, new=entry)
    return jsonify(entry)


# ── Knowledge Base Integration (Phase 2 Part 3) ──────────────────────────────
# Read-only, deterministic retrieval — reuses services/retrieval_engine.py
# (already used by routes/validation.py, no new retrieval logic) for KB
# document suggestions, and existing list functions for previous
# deviations/CAPAs/equipment history. Nothing here is persisted until the
# investigator explicitly accepts a suggestion via accept-sop, which writes
# through the existing inv.add_sop_review() — no new table.

def _related_records(deviation: dict, did: int) -> dict:
    company_id = g.tenant.company_id
    product = (deviation.get("product") or "").strip().lower()
    equipment = (deviation.get("equipment") or "").strip().lower()
    department = (deviation.get("department") or "").strip().lower()

    def _matches(other: dict) -> bool:
        if other["id"] == did:
            return False
        return bool(
            (product and (other.get("product") or "").strip().lower() == product)
            or (equipment and (other.get("equipment") or "").strip().lower() == equipment)
            or (department and (other.get("department") or "").strip().lower() == department)
        )

    previous_deviations = [d for d in ddb.get_all_deviations(company_id) if _matches(d)][:5]
    previous_capas = [c for c in cdb.get_all_capas(company_id) if _matches(c)][:5]

    equipment_history = []
    if deviation.get("equipment"):
        equipment_history = equipdb.search_equipment(deviation["equipment"], company_id)[:5]

    return {
        "previous_deviations": previous_deviations,
        "previous_capas": previous_capas,
        "equipment_history": equipment_history,
    }


@bp.route("/<int:did>/investigation/knowledge-base", methods=["GET"])
def get_investigation_knowledge_base(did):
    deviation = _record_scoped_or_404(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404

    result = retrieval_engine.retrieve_context(
        document_type="Deviation",
        project_id=deviation.get("project_id") or 0,
        equipment_name=deviation.get("equipment", ""),
        questionnaire=_investigation_context(deviation),
        max_chunks=10,
    )
    # RetrievalResult.sources rows are {"id", "name", "doc_type"} (retrieval_engine.py
    # retrieve_context()'s deduplicated source list) — doc_type is one of the
    # SOURCE_KB_* constants (e.g. "KB - SOP", "KB - Validation Protocol").
    kb_suggestions = [
        {"doc_reference": s.get("name", ""), "source_type": s.get("doc_type", "")}
        for s in (result.sources if result.found else [])
    ]

    payload = {"kb_suggestions": kb_suggestions}
    payload.update(_related_records(deviation, did))
    return jsonify(payload)


@bp.route("/<int:did>/investigation/knowledge-base/accept-sop", methods=["POST"])
def accept_investigation_kb_suggestion(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    unlocked, reason = _investigation_lock(did)
    data = request.get_json() or {}
    body = {
        "doc_reference": data.get("doc_reference", ""),
        "version": data.get("version", ""),
        "relevant_section": data.get("relevant_section", ""),
        "notes": data.get("notes") or "Auto-retrieved from Knowledge Base",
    }
    try:
        entry = inv.add_sop_review(RECORD_TYPE, did, body, unlocked=unlocked)
    except inv.InvestigationLockedError:
        return jsonify({"error": f"Investigation Case Locked — {reason}"}), 423
    audit.log("deviation", did, "SOP review entry added from Knowledge Base suggestion",
               detail=entry.get("doc_reference", ""))
    return jsonify(entry), 201


# ── Impact assessment ────────────────────────────────────────────────────────

@bp.route("/<int:did>/suggest-impact", methods=["POST"])
def suggest_impact(did):
    if not tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_impact(did))


@bp.route("/<int:did>/impact", methods=["GET"])
def get_impacts(did):
    if not tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(ddb.get_impacts(did))


@bp.route("/<int:did>/impact", methods=["POST"])
def add_impact(did):
    if not tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    entry = ddb.add_impact(did, data)
    return jsonify(entry), 201


# ── CAPA suggestion & linkage ──────────────────────────────────────────────────

@bp.route("/<int:did>/suggest-capa", methods=["POST"])
def suggest_capa(did):
    if not tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(svc.ai_suggest_capa(did))


@bp.route("/<int:did>/link-capa", methods=["POST"])
def link_capa(did):
    if not tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    capa_id = data.get("capa_id")
    capa = tenancy.scoped_or_none(cdb.get_capa(capa_id), g.tenant.company_id) if capa_id else None
    if not capa:
        return jsonify({"error": "Valid capa_id is required"}), 400
    link = ddb.link_capa(did, capa_id)
    qmsdb.add_audit_entry("deviation", did, "Linked to CAPA", detail=capa.get("capa_number", ""))
    return jsonify(link), 201


@bp.route("/<int:did>/capas", methods=["GET"])
def get_linked_capas(did):
    if not tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(ddb.get_linked_capas(did))


# ── Workflow: named-approver, gated investigation lifecycle ──────────────────
# Replaces the old free action->status map (any company_admin/reviewer_qa
# could fire any action on any deviation) with services/workflow_engine.py:
# only a user explicitly assigned to an approval step may decide it.

def _record_scoped_or_404(did):
    return tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id)


def _enrich_workflow_state(state: dict) -> dict:
    """Add the Lifecycle tab's dashboard fields (architecture refactor §2/§9)
    on top of workflow_engine's raw instance/steps — presentation only,
    computed here rather than in workflow_engine.py so the engine itself
    stays untouched. 'Due Date'/'Overdue' are not tracked (no due-date field
    on qms_deviations) — omitted rather than fabricated."""
    steps = state.get("steps") or []
    for s in steps:
        s["phase"] = _phase_for_step_key(s["step_key"])

    instance = state.get("instance")
    if not instance:
        state["current_phase"] = "Draft"
        state["progress_pct"] = 0
        state["remaining_steps"] = []
        state["assigned_to"] = []
        state["pending_since"] = None
        return state

    if instance["status"] == "rejected":
        state["current_phase"] = "Rejected"
    else:
        current = next((s for s in steps if s["step_order"] == instance["current_step_order"]), None)
        state["current_phase"] = current["phase"] if current else "Closure"

    total = len(steps)
    completed = sum(1 for s in steps if s["status"] == "approved")
    state["progress_pct"] = round(100 * completed / total) if total else 0
    state["remaining_steps"] = [s["step_name"] for s in steps if s["status"] == "pending"]

    current = next((s for s in steps if s["step_order"] == instance["current_step_order"]), None)
    if current and current["step_type"] == "approval":
        state["assigned_to"] = [a.get("display_name") or a["user_id"] for a in current.get("approvers", [])]
    elif current:
        state["assigned_to"] = [f"Any {r}" for r in (current.get("eligible_roles") or "").split(",") if r]
    else:
        state["assigned_to"] = []

    previous = next((s for s in steps if s["step_order"] == instance["current_step_order"] - 1), None)
    state["pending_since"] = (previous or {}).get("decided_at") or instance.get("started_at")
    return state


@bp.route("/<int:did>/workflow", methods=["GET"])
def get_workflow(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify(_enrich_workflow_state(wfe.get_instance_state(RECORD_TYPE, did)))


# ── Workflow Builder: Draft-time, whole-lifecycle approver configuration ─────
# Configures every named-approval step in the deviation's lifecycle, editable
# only while the deviation is in Draft — the sole place approvers are ever
# set; there is no runtime "Assign Approver" action. Two parts:
#   "steps"      — the dynamic, reorderable Review chain (one record per step
#                   in qms_deviation_workflow_steps), always ending in the
#                   mandatory QA Approval gate.
#   "capa_phase" — the two fixed, single-approver CAPA-phase steps (QA
#                   Review, Final Approval) that follow Investigation; not
#                   reorderable/addable/removable, so they're plain columns
#                   on qms_deviations rather than additional step rows.
# Investigation, Effectiveness Check, and Closure need no approver here —
# they're role-eligible 'activity' steps in DEVIATION_LIFECYCLE_V2, decided
# by any user with an eligible role, never a named assignee.
# At Submit for Review this is compiled into a fresh per-deviation workflow
# template (see _build_dynamic_workflow_key) handed to the unmodified
# services/workflow_engine.py — no engine change.

@bp.route("/<int:did>/workflow-builder", methods=["GET"])
def get_workflow_builder(did):
    if not _record_scoped_or_404(did):
        return jsonify({"error": "Not found"}), 404
    return jsonify({"steps": ddb.get_workflow_steps(did), "capa_phase": ddb.get_capa_phase_approvers(did)})


@bp.route("/<int:did>/workflow-builder", methods=["PUT"])
def update_workflow_builder(did):
    deviation = _record_scoped_or_404(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    if deviation["status"] != "Draft":
        return jsonify({"error": "The workflow can only be edited while the deviation is in Draft"}), 409
    data = request.get_json() or {}
    try:
        steps = ddb.replace_workflow_steps(did, data.get("steps") or [])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    capa_phase = ddb.set_capa_phase_approvers(did, data.get("capa_phase") or {})
    audit.log("deviation", did, "Workflow configuration updated")
    return jsonify({"steps": steps, "capa_phase": capa_phase})


def _build_dynamic_workflow_key(did: int) -> str:
    """Compile this deviation's configured Review chain
    (qms_deviation_workflow_steps) plus the fixed post-Review tail (copied
    verbatim from WORKFLOW_KEY's own template) into a fresh, per-deviation
    workflow template — new qms_workflow_templates/_template_steps rows,
    created via the purely-additive qms_workflow_database.create_template()/
    create_template_step(). The engine (services/workflow_engine.py) is only
    ever handed a workflow_key and reads templates generically, so it needs
    no change; step 1 ('submitted') and the tail
    (evidence_collection/qa_review/final_approval/effectiveness_check/closed)
    are identical to today's DEVIATION_LIFECYCLE_V2, keeping 'Return for
    Investigation' (hardcoded to step_key=='evidence_collection' in the
    engine) and UNLOCK_STEP_KEY=='qa_approval' working unmodified."""
    base_template = wfdb.get_template_by_key(WORKFLOW_KEY)
    base_steps = wfdb.get_template_steps(base_template["id"])
    submitted_step = next(s for s in base_steps if s["step_key"] == "submitted")
    tail_steps = [s for s in base_steps if s["step_order"] >= 5]  # evidence_collection .. closed

    configured = ddb.get_workflow_steps(did)
    if not configured:
        raise wfe.WorkflowError("No workflow steps configured for this deviation")

    dynamic_key = f"DEVIATION_DYNAMIC_{did}_{uuid.uuid4().hex[:8]}"
    template = wfdb.create_template(dynamic_key, f"Deviation {did} Review Chain", "deviation")

    wfdb.create_template_step(
        template["id"], 1, submitted_step["step_key"], submitted_step["step_name"],
        submitted_step["step_type"], submitted_step["eligible_roles"], submitted_step["gate_status"],
    )

    order = 2
    for step in configured:
        step_key = "qa_approval" if step["is_qa_approval"] else f"review_step_{order}"
        wfdb.create_template_step(template["id"], order, step_key, step["step_name"], "approval", "", "Review")
        order += 1

    for tail in tail_steps:
        wfdb.create_template_step(
            template["id"], order, tail["step_key"], tail["step_name"],
            tail["step_type"], tail["eligible_roles"], tail["gate_status"],
        )
        order += 1

    return dynamic_key


@bp.route("/<int:did>/workflow/start", methods=["POST"])
def start_workflow(did):
    deviation = _record_scoped_or_404(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404

    # The Workflow Builder is the only place approvers are configured for a
    # deviation (no runtime "Assign Approver" action exists) — every
    # named-approval step across the whole lifecycle (the Review chain, plus
    # the fixed CAPA-phase QA Review/Final Approval steps) must already carry
    # a chosen approver before the record can leave Draft, or a step with no
    # one able to decide it would become permanently stuck once submitted.
    configured_steps = ddb.get_workflow_steps(did)
    capa_phase = ddb.get_capa_phase_approvers(did)
    unassigned = [s["step_name"] for s in configured_steps if not s.get("approver_user_id")]
    if not capa_phase.get("qa_review_approver_user_id"):
        unassigned.append("QA Review")
    if not capa_phase.get("final_approval_approver_user_id"):
        unassigned.append("Final Approval")
    if unassigned:
        reason = f"Assign an approver in the Workflow Builder for: {', '.join(unassigned)}"
        audit.log_failure("deviation", did, "Workflow start blocked", reason=reason)
        return jsonify({"error": reason}), 409

    sig = tenancy.signing_identity(g.tenant)
    try:
        dynamic_key = _build_dynamic_workflow_key(did)
        wfe.start_instance(dynamic_key, RECORD_TYPE, did, g.tenant.company_id, sig["performed_by"])
    except wfe.WorkflowError as e:
        audit.log_failure("deviation", did, "Workflow start blocked", reason=str(e))
        return jsonify({"error": str(e)}), 409

    # Every named-approval step already carries its approver (validated
    # above) — assign them all immediately so the runtime Review screen never
    # needs a manual assignment control. Review-chain steps are assigned by
    # their known step_order; QA Review/Final Approval's step_order shifts
    # with however many Review steps were configured, so they're looked up
    # by step_key from the just-compiled instance instead.
    for step in configured_steps:
        wfe.assign_approvers(RECORD_TYPE, did, step["step_order"], [
            {"user_id": step["approver_user_id"], "display_name": step.get("approver_display_name", "")}
        ])
    capa_assignments = {
        "qa_review": (capa_phase["qa_review_approver_user_id"], capa_phase["qa_review_approver_display_name"]),
        "final_approval": (capa_phase["final_approval_approver_user_id"], capa_phase["final_approval_approver_display_name"]),
    }
    for s in wfe.get_instance_state(RECORD_TYPE, did)["steps"]:
        if s["step_key"] in capa_assignments:
            user_id, display_name = capa_assignments[s["step_key"]]
            wfe.assign_approvers(RECORD_TYPE, did, s["step_order"], [{"user_id": user_id, "display_name": display_name}])

    return jsonify(wfe.get_instance_state(RECORD_TYPE, did)), 201


@bp.route("/<int:did>/workflow/steps/<int:step_order>/decide", methods=["POST"])
def decide_workflow_step(did, step_order):
    deviation = _record_scoped_or_404(did)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    decision = data.get("decision", "")
    if decision not in ("approve", "reject", "return", "advance"):
        return jsonify({"error": "decision must be one of approve/reject/return/advance"}), 400

    sig = tenancy.signing_identity(g.tenant)
    try:
        state = wfe.decide_step(
            RECORD_TYPE, did, step_order, decision,
            user_id=g.tenant.user_id, role=g.tenant.role,
            performed_by=sig["performed_by"], comments=data.get("comments", ""),
        )
    except wfe.WorkflowPermissionError as e:
        audit.log_failure("deviation", did, f"Workflow decision blocked ({decision})", reason=str(e))
        return jsonify({"error": str(e)}), 403
    except wfe.WorkflowError as e:
        audit.log_failure("deviation", did, f"Workflow decision blocked ({decision})", reason=str(e))
        return jsonify({"error": str(e)}), 409
    return jsonify(state)


# ── Report / Export ────────────────────────────────────────────────────────────

@bp.route("/<int:did>/report", methods=["GET"])
def get_report(did):
    deviation = tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    md = svc.generate_report_markdown(did)
    return jsonify({"markdown": md, "title": deviation.get("title", "")})


@bp.route("/<int:did>/export/docx", methods=["POST"])
def export_docx(did):
    deviation = tenancy.scoped_or_none(ddb.get_deviation(did), g.tenant.company_id)
    if not deviation:
        return jsonify({"error": "Not found"}), 404
    from pharmagpt.services.doc_exporter import markdown_to_docx
    md = svc.generate_report_markdown(did)
    docx_bytes = markdown_to_docx(md, "Deviation-Record", {
        "title": deviation.get("title", ""),
        "department": deviation.get("department", ""),
    })
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", deviation.get("title", "Deviation"))[:40]
    filename = f"{deviation.get('deviation_number', 'DEV')}_{safe_title}.docx"
    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )

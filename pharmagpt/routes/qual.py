"""
routes/qual.py — Qualification Management Suite API endpoints (IQ/OQ/PQ).

All routes return JSON. SSE streaming for AI generation.

Routes
------
GET    /qual/dashboard                               Dashboard statistics
GET    /qual/                                         List qualifications
POST   /qual/                                         Create qualification
GET    /qual/<id>                                    Get qualification
PUT    /qual/<id>                                    Update qualification
DELETE /qual/<id>                                    Delete qualification

GET    /qual/<id>/protocols                          Get all protocols
POST   /qual/<id>/protocols                          Create protocol
GET    /qual/<id>/protocols/<pid>                    Get protocol
PUT    /qual/<id>/protocols/<pid>                    Update protocol
DELETE /qual/<id>/protocols/<pid>                    Delete protocol

GET    /qual/<id>/protocols/<pid>/test-cases         Get test cases
POST   /qual/<id>/protocols/<pid>/test-cases         Save all test cases
POST   /qual/<id>/protocols/<pid>/test-cases/add     Add single test case
PUT    /qual/<id>/protocols/<pid>/test-cases/<tcid>  Update test case
DELETE /qual/<id>/protocols/<pid>/test-cases/<tcid>  Delete test case

POST   /qual/<id>/protocols/<pid>/generate           AI generate test cases (SSE)
POST   /qual/<id>/protocols/<pid>/review             AI review protocol

GET    /qual/<id>/protocols/<pid>/executions         Get executions
POST   /qual/<id>/protocols/<pid>/execute/<tcid>     Save execution result

GET    /qual/<id>/deviations                         Get deviations
POST   /qual/<id>/deviations                         Create deviation
PUT    /qual/<id>/deviations/<did>                   Update deviation

GET    /qual/<id>/approval                           Get approval trail
POST   /qual/<id>/approval                           Add approval entry

GET    /qual/<id>/versions                           Get version history
POST   /qual/<id>/protocols/<pid>/versions           Create version snapshot

GET    /qual/<id>/traceability                       Auto-generate traceability matrix

GET    /qual/<id>/protocols/<pid>/export/docx        Export protocol as DOCX
GET    /qual/<id>/traceability/export/docx           Export traceability matrix as DOCX
"""

import json
import io
import logging
from datetime import date
from flask import Blueprint, g, jsonify, request, Response, stream_with_context, send_file

from pharmagpt import audit
from pharmagpt import audit_events as evt
from pharmagpt import qual_database as qdb
from pharmagpt import qms_database as qmsdb
from pharmagpt import tenancy
from pharmagpt import validation_approval_database as vadb
from pharmagpt.auth.decorators import require_role
from pharmagpt.auth import module_access
from pharmagpt.auth.module_access import require_business_permission
from pharmagpt.services import esignature_service
from pharmagpt.services import kb_sync
from pharmagpt.services import lifecycle_engine
from pharmagpt.services import qual_service as svc
from pharmagpt.services import urs_lifecycle
from pharmagpt.services import validation_approval
from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from pharmagpt.services.doc_exporter import markdown_to_docx

logger = logging.getLogger(__name__)
from google.genai import types

bp = Blueprint("qual", __name__, url_prefix="/qual")


@bp.before_request
def _require_workspace_access():
    from pharmagpt.auth.workspace_access import require_workspace_access
    return require_workspace_access("validation")


# Phase F (WP3, workflow enforcement): GAMP5/FDA/EU GMP Annex 15 require IQ
# to be complete before OQ begins, and OQ complete before PQ begins — see
# PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md C2. Protocols don't carry their
# own "Approved" status (only the parent Qualification does); "complete"
# here means the prior-stage protocol reached a terminal execution status
# (qual.py::complete_protocol below), which is the closest existing
# equivalent and the same status this suite already uses everywhere else to
# mean "this stage is done."
_PROTOCOL_PREREQUISITE = {"OQ": "IQ", "PQ": "OQ"}
_PROTOCOL_COMPLETED_STATUSES = {"completed", "completed_with_deviations"}


def _missing_prerequisite_protocol(qid: int, protocol_type: str) -> str | None:
    """Return a human-readable error if `protocol_type` requires a prior
    stage that doesn't exist yet or isn't complete for this qualification;
    None if the prerequisite is satisfied (or there isn't one, e.g. IQ)."""
    required_type = _PROTOCOL_PREREQUISITE.get(protocol_type)
    if not required_type:
        return None
    siblings = [p for p in qdb.get_protocols_for_qual(qid) if p.get("protocol_type") == required_type]
    if not siblings:
        return f"No {required_type} protocol exists for this qualification yet — {required_type} must be completed before {protocol_type} can begin."
    if not any(p.get("status") in _PROTOCOL_COMPLETED_STATUSES for p in siblings):
        return f"{required_type} protocol exists but is not yet completed — {required_type} must be completed before {protocol_type} can begin."
    return None


def _approval_blocker_for_execution(protocol: dict) -> str | None:
    """A protocol must be APPROVED (all seven sign-offs, status approved or
    effective) before any test is executed or the protocol is completed.

    Execution deliberately does NOT wait for Effective: the existing design
    (services/approval_engine.py WORKFLOWS["VALIDATION"]) orders the lifecycle
    Approved -> Execution -> Post Execution Review -> Effective, i.e. Effective
    is the state AFTER execution evidence exists, so requiring it first would
    make the protocol impossible to run.

    Grandfathered: a protocol that was already being executed before approval
    tracking existed (executions recorded, and no sign-off ledger row ever)
    may continue. A protocol that has been through the new workflow always has
    ledger rows, so it can never use this exemption."""
    status = qdb.get_protocol_approval_status(protocol)
    if status in ("approved", "effective"):
        return None
    ledger = vadb.list_signoffs(g.tenant.company_id, protocol["protocol_type"], protocol["id"],
                                include_superseded=True)
    if not ledger and qdb.get_executions(protocol["id"]):
        return None
    return (f"{protocol['protocol_type']} protocol is '{status}' — it must be approved by all seven "
            f"signatories before test execution or completion")


def _scoped_protocol(qid, pid):
    """Return the protocol only if the qualification belongs to the
    caller's company AND the protocol belongs to that qualification — every
    protocol-scoped route needs both checks. Returns None (caller returns
    404) if either fails. (Phase 2 RBAC/multi-tenancy audit finding: several
    protocol/test-case routes previously checked only protocol.qual_id ==
    qid, never that qid itself belonged to the caller's company — a
    cross-tenant read/write gap.)"""
    if not tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id):
        return None
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return None
    return protocol


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route("/dashboard")
def dashboard():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    return jsonify(qdb.get_dashboard_stats(g.tenant.company_id))


# ── Qualification CRUD ────────────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
def list_qualifications():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    filters = {
        "status":         request.args.get("status"),
        "category":       request.args.get("category"),
        "department":     request.args.get("department"),
        "equipment_type": request.args.get("equipment_type"),
        "iq_status":      request.args.get("iq_status"),
        "oq_status":      request.args.get("oq_status"),
        "pq_status":      request.args.get("pq_status"),
        "keyword":        request.args.get("q"),
    }
    return jsonify(qdb.get_all_qualifications(g.tenant.company_id, {k: v for k, v in filters.items() if v}))


@bp.route("/", methods=["POST"])
def create_qualification():
    if not g.tenant.company_id:
        return jsonify({"error": "Super Admin has no standing access to tenant content"}), 403
    data = request.get_json() or {}
    if not data.get("equipment_name", "").strip() and not data.get("title", "").strip():
        return jsonify({"error": "Equipment name or title is required"}), 400
    if not data.get("title", "").strip():
        data["title"] = f"Qualification — {data.get('equipment_name', 'New Equipment')}"
    sig_ = tenancy.signing_identity(g.tenant)
    qual = qdb.create_qualification(data, company_id=g.tenant.company_id,
                                    created_by_user_id=g.tenant.user_id,
                                    created_by_display_name=sig_["performed_by"])
    audit.log("qualification", qual["id"], "Created", new=qual)
    return jsonify(qual), 201


@bp.route("/<int:qid>", methods=["GET"])
def get_qualification(qid):
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qual)


@bp.route("/<int:qid>", methods=["PUT"])
def update_qualification(qid):
    existing = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Qualification not found"}), 404
    # Phase F (WP3, workflow enforcement): obsolete is the terminal state in
    # QUALIFICATION's lifecycle (services/lifecycle_engine.py) — immutable
    # once reached.
    if existing["status"] == "obsolete":
        audit.log_failure("qualification", qid, "Update blocked (record is obsolete)",
                           reason="Obsolete qualifications are immutable")
        return jsonify({"error": "This qualification is obsolete and cannot be edited"}), 409
    data = request.get_json() or {}
    updated = qdb.update_qualification(qid, data)
    audit.log("qualification", qid, "Updated", old=existing, new=updated)
    return jsonify(updated)


@bp.route("/<int:qid>", methods=["DELETE"])
@require_role("company_admin")
@require_business_permission("Validation", "Delete")
def delete_qualification(qid):
    existing = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not existing:
        return jsonify({"error": "Qualification not found"}), 404
    qdb.delete_qualification(qid)
    audit.log("qualification", qid, "Deleted", old=existing)
    return jsonify({"deleted": True})


# ── Protocols ─────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols", methods=["GET"])
def get_protocols(qid):
    if not tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_protocols_for_qual(qid))


@bp.route("/<int:qid>/protocols", methods=["POST"])
def create_protocol(qid):
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    data = request.get_json() or {}
    protocol_type = data.get("protocol_type", "IQ").upper()
    if protocol_type not in ("IQ", "OQ", "PQ"):
        return jsonify({"error": "protocol_type must be IQ, OQ, or PQ"}), 400
    # Phase F (WP3): the sequencing gate is enforced at *execution* time
    # (execute_test_case below), not at creation time — drafting/preparing
    # an OQ or PQ protocol document while IQ is still in progress is
    # legitimate GxP practice (and already relied on by this suite's own
    # regression tests); what must not happen is *running* OQ/PQ tests
    # before the prior stage is complete.
    # Auto-fill from qualification
    if not data.get("title"):
        data["title"] = f"{protocol_type} Protocol — {qual.get('equipment_name', '')}"
    protocol = qdb.create_protocol(qid, protocol_type, data, created_by_user_id=g.tenant.user_id,
                                   created_by_display_name=tenancy.signing_identity(g.tenant)["performed_by"])
    audit.log("qualification", qid, f"{protocol_type} Protocol created", new=protocol)
    return jsonify(protocol), 201


@bp.route("/<int:qid>/protocols/<int:pid>", methods=["GET"])
def get_protocol(qid, pid):
    protocol = _scoped_protocol(qid, pid)
    if not protocol:
        return jsonify({"error": "Protocol not found"}), 404
    return jsonify(protocol)


@bp.route("/<int:qid>/protocols/<int:pid>", methods=["PUT"])
def update_protocol(qid, pid):
    existing = _scoped_protocol(qid, pid)
    if not existing:
        return jsonify({"error": "Protocol not found"}), 404
    data = request.get_json() or {}
    if _protocol_locked(existing) and (set(data) - {"status", "pass_count", "fail_count", "pending_count", "deviation_count"}):
        audit.log_failure("qualification", qid, "Protocol update blocked (locked by approval status)",
                          reason=f"approval_status={qdb.get_protocol_approval_status(existing)}")
        return jsonify({"error": _PROTOCOL_LOCK_MSG.format(status=qdb.get_protocol_approval_status(existing))}), 409
    data.pop("approval_status", None)
    updated = qdb.update_protocol(pid, data)
    audit.log("qualification", qid, f"{existing.get('protocol_type','')} Protocol updated",
              old=existing, new=updated)
    return jsonify(updated)


@bp.route("/<int:qid>/protocols/<int:pid>", methods=["DELETE"])
@require_role("company_admin")
@require_business_permission("Validation", "Delete")
def delete_protocol(qid, pid):
    existing = _scoped_protocol(qid, pid)
    if not existing:
        return jsonify({"error": "Protocol not found"}), 404
    qdb.delete_protocol(pid)
    audit.log("qualification", qid, f"{existing.get('protocol_type','')} Protocol deleted", old=existing)
    return jsonify({"deleted": True})


# ── Test Cases ────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/test-cases", methods=["GET"])
def get_test_cases(qid, pid):
    if not _scoped_protocol(qid, pid):
        return jsonify({"error": "Protocol not found"}), 404
    return jsonify(qdb.get_test_cases(pid))


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases", methods=["POST"])
def save_test_cases(qid, pid):
    protocol_row = _scoped_protocol(qid, pid)
    if not protocol_row:
        return jsonify({"error": "Protocol not found"}), 404
    if _protocol_locked(protocol_row):
        return jsonify({"error": _PROTOCOL_LOCK_MSG.format(status=qdb.get_protocol_approval_status(protocol_row))}), 409
    tcs = request.get_json() or []
    saved = qdb.save_test_cases(pid, qid, tcs)
    return jsonify(saved)


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases/add", methods=["POST"])
def add_test_case(qid, pid):
    protocol_row = _scoped_protocol(qid, pid)
    if not protocol_row:
        return jsonify({"error": "Protocol not found"}), 404
    if _protocol_locked(protocol_row):
        return jsonify({"error": _PROTOCOL_LOCK_MSG.format(status=qdb.get_protocol_approval_status(protocol_row))}), 409
    tc = request.get_json() or {}
    new_tc = qdb.add_test_case(pid, qid, tc)
    return jsonify(new_tc), 201


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases/<int:tcid>", methods=["PUT"])
def update_test_case(qid, pid, tcid):
    protocol_row = _scoped_protocol(qid, pid)
    if not protocol_row:
        return jsonify({"error": "Protocol not found"}), 404
    existing_tc = qdb.get_test_case(tcid)
    if not existing_tc or existing_tc.get("protocol_id") != pid:
        return jsonify({"error": "Test case not found"}), 404
    data = request.get_json() or {}
    # Once the protocol leaves Draft only execution results (status) may change.
    if _protocol_locked(protocol_row) and (set(data) - {"status"}):
        return jsonify({"error": _PROTOCOL_LOCK_MSG.format(status=qdb.get_protocol_approval_status(protocol_row))}), 409
    updated = qdb.update_test_case(tcid, data)
    if not updated:
        return jsonify({"error": "Test case not found"}), 404
    return jsonify(updated)


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases/<int:tcid>", methods=["DELETE"])
@require_role("company_admin")
@require_business_permission("Validation", "Delete")
def delete_test_case(qid, pid, tcid):
    protocol_row = _scoped_protocol(qid, pid)
    if not protocol_row:
        return jsonify({"error": "Protocol not found"}), 404
    if _protocol_locked(protocol_row):
        return jsonify({"error": _PROTOCOL_LOCK_MSG.format(status=qdb.get_protocol_approval_status(protocol_row))}), 409
    existing_tc = qdb.get_test_case(tcid)
    if not existing_tc or existing_tc.get("protocol_id") != pid:
        return jsonify({"error": "Test case not found"}), 404
    qdb.delete_test_case(tcid)
    return jsonify({"deleted": True})


# ── AI Generation (SSE) ───────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/generate", methods=["POST"])
def generate_test_cases(qid, pid):
    """Stream AI-generated test cases for IQ/OQ/PQ protocol."""
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404

    if _protocol_locked(protocol):
        return jsonify({"error": _PROTOCOL_LOCK_MSG.format(status=qdb.get_protocol_approval_status(protocol))}), 409

    protocol_type = protocol.get("protocol_type", "IQ")

    # Fetch linked URS requirements
    urs_reqs = []
    if qual.get("linked_urs_id"):
        try:
            from pharmagpt import urs_database as udb
            urs_reqs = udb.get_requirements(qual["linked_urs_id"])
        except Exception:
            pass

    # Fetch linked Risk items
    risk_items = []
    if qual.get("linked_risk_id"):
        try:
            from pharmagpt import risk_database as rdb
            risk_items = rdb.get_risk_items(qual["linked_risk_id"])
        except Exception:
            pass

    qual_info = dict(qual)

    # Build prompt based on protocol type
    if protocol_type == "IQ":
        prompt = svc.build_iq_generation_prompt(qual_info, urs_reqs, risk_items)
    elif protocol_type == "OQ":
        prompt = svc.build_oq_generation_prompt(qual_info, urs_reqs, risk_items)
    else:
        prompt = svc.build_pq_generation_prompt(qual_info, urs_reqs, risk_items)

    def generate():
        try:
            full_text = ""
            response = gemini_client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=PHARMA_SYSTEM_PROMPT,
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )
            for chunk in response:
                if chunk.text:
                    full_text += chunk.text
                    yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"

            # Parse and save test cases
            try:
                json_str = full_text.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                start = json_str.find("[")
                end = json_str.rfind("]") + 1
                if start >= 0 and end > start:
                    json_str = json_str[start:end]
                ai_tcs = json.loads(json_str)
                for tc in ai_tcs:
                    tc["source"] = "ai"
                    tc["status"] = "pending"
                    if not isinstance(tc.get("urs_req_ids"), list):
                        tc["urs_req_ids"] = []
                    if not isinstance(tc.get("risk_item_ids"), list):
                        tc["risk_item_ids"] = []
                # Merge with existing
                existing = qdb.get_test_cases(pid)
                merged = existing + ai_tcs
                qdb.save_test_cases(pid, qid, merged)
                qdb.update_protocol(pid, {"ai_generated": 1})
                audit.log("qualification", qid, f"{protocol_type} AI test cases generated",
                          new={"protocol_id": pid, "count": len(ai_tcs)})
                yield f"data: {json.dumps({'done': True, 'count': len(ai_tcs)})}\n\n"
            except Exception as parse_err:
                audit.log_failure("qualification", qid, f"{protocol_type} AI test case generation parse failed",
                                   reason=str(parse_err))
                yield f"data: {json.dumps({'done': True, 'parse_error': str(parse_err)})}\n\n"
        except Exception as e:
            audit.log_failure("qualification", qid, f"{protocol_type} AI test case generation failed", reason=str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── AI Review ─────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/review", methods=["POST"])
def review_protocol(qid, pid):
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    test_cases = qdb.get_test_cases(pid)
    if not test_cases:
        return jsonify({"error": "No test cases to review"}), 400

    prompt = svc.build_ai_review_prompt(qual, protocol, test_cases)
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=PHARMA_SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=4096,
            ),
        )
        raw = response.text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        review_data = json.loads(raw)
    except Exception as e:
        review_data = {
            "compliance_score": 0, "completeness_score": 0,
            "risk_coverage_score": 0, "overall_score": 0,
            "recommendation": f"Review failed: {str(e)}",
            "executive_summary": f"Review error: {str(e)}",
            "strengths": [], "missing_tests": [], "duplicate_tests": [],
            "improvements": [], "regulatory_gaps": [],
        }

    saved = qdb.save_ai_review(pid, qid, review_data)
    return jsonify(saved)


# ── Execution ─────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/executions", methods=["GET"])
def get_executions(qid, pid):
    if not _scoped_protocol(qid, pid):
        return jsonify({"error": "Protocol not found"}), 404
    executions = qdb.get_executions(pid)
    # Build execution map keyed by test_case_id for efficient frontend access
    exec_map = {e["test_case_id"]: e for e in executions}
    return jsonify({"executions": executions, "exec_map": exec_map})


@bp.route("/<int:qid>/protocols/<int:pid>/execute/<int:tcid>", methods=["POST"])
def execute_test_case(qid, pid, tcid):
    protocol = _scoped_protocol(qid, pid)
    if not protocol:
        return jsonify({"error": "Protocol not found"}), 404

    unapproved = _approval_blocker_for_execution(protocol)
    if unapproved:
        audit.log_failure("qualification", qid, f"{protocol['protocol_type']} test execution blocked", reason=unapproved)
        return jsonify({"error": unapproved}), 409

    # Phase F (WP3, workflow enforcement): re-check the sequencing gate at
    # execution time too, not just at protocol-creation time — a protocol
    # created before this fix, or whose prerequisite was later deleted/
    # regressed, must not be executable out of sequence either. See C2.
    protocol_type = protocol.get("protocol_type", "IQ").upper()
    blocker = _missing_prerequisite_protocol(qid, protocol_type)
    if blocker:
        audit.log_failure("qualification", qid, f"{protocol_type} test execution blocked", reason=blocker)
        return jsonify({"error": blocker}), 409

    data = request.get_json() or {}
    # Phase F fix (C6): who actually ran the test is the authenticated
    # caller, not a free-text field from the request body — see
    # PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md C6. `executed_by` is still
    # accepted for the frontend's own display purposes but no longer used
    # for the auto-opened deviation's attribution below.
    executed_by = tenancy.signing_identity(g.tenant)["performed_by"]
    result = qdb.save_execution(tcid, pid, qid, data)
    audit.log("qualification", qid, f"{protocol_type} test case executed",
              new={"test_case_id": tcid, "result": data.get("result")})

    # Auto-update protocol status to in_progress
    qual = qdb.get_qualification(qid)   # already tenant-verified by _scoped_protocol() above
    if qual:
        ptype = protocol.get("protocol_type", "IQ").lower()
        status_field = f"{ptype}_status"
        if qual.get(status_field) == "not_started":
            qdb.update_qualification(qid, {status_field: "in_progress", "overall_status": "in_progress"})

    # If test failed, record deviation automatically
    if data.get("result") == "fail" and data.get("auto_deviation"):
        qdb.create_deviation(qid, {
            "protocol_id": pid,
            "test_case_id": tcid,
            "title": f"Test Failed: {data.get('test_name', f'TC-{tcid}')}",
            "description": f"Test case failed. Actual result: {data.get('actual_result', '')}",
            "impact": "Major" if protocol.get("protocol_type") == "IQ" else "Minor",
            "raised_by": executed_by,
            "raised_date": data.get("executed_date", ""),
        })

    return jsonify(result)


@bp.route("/<int:qid>/protocols/<int:pid>/complete", methods=["POST"])
@require_role("company_admin", "reviewer_qa")
@require_business_permission("Validation", "Approve")
def complete_protocol(qid, pid):
    """Mark protocol as completed and update qualification status.

    Phase F fix (C7): this route previously had no role guard despite being
    a QA-significant status transition — any authenticated `user` could
    close out a protocol. See
    PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md C7.
    """
    protocol = _scoped_protocol(qid, pid)
    if not protocol:
        return jsonify({"error": "Protocol not found"}), 404
    unapproved = _approval_blocker_for_execution(protocol)
    if unapproved:
        audit.log_failure("qualification", qid, f"{protocol['protocol_type']} protocol completion blocked", reason=unapproved)
        return jsonify({"error": unapproved}), 409
    data = request.get_json() or {}

    # Check for any failing test cases
    test_cases = qdb.get_test_cases(pid)
    fail_count = sum(1 for tc in test_cases if tc.get("status") == "fail")
    pending_count = sum(1 for tc in test_cases if tc.get("status") == "pending")

    if pending_count > 0 and not data.get("force"):
        return jsonify({"error": f"{pending_count} test cases still pending. Pass force=true to override."}), 400

    # Electronic Signature gate (21 CFR Part 11 / EU GMP Annex 11) — the
    # existing, unmodified pharmagpt/services/esignature_service.py. This is
    # the protocol-level (IQ/OQ/PQ) execution sign-off, distinct from the
    # qualification-level approval gated in add_approval() below.
    old_status = protocol["status"]
    try:
        esignature_service.require_esignature(
            g.tenant, data.get("password", ""), data.get("meaning", ""), data.get("reason", ""),
        )
    except esignature_service.ReauthenticationError as exc:
        audit.log_failure("qualification", qid, "Protocol completion blocked — e-signature failed", reason=str(exc))
        return jsonify({"error": str(exc)}), 401
    except esignature_service.ESignatureError as exc:
        audit.log_failure("qualification", qid, evt.ESIGNATURE_FAILURE, reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    overall_status = "completed" if fail_count == 0 else "completed_with_deviations"
    qdb.update_protocol(pid, {"status": overall_status})

    # Update qualification phase status
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if qual:
        ptype = protocol.get("protocol_type", "IQ").lower()
        updates = {f"{ptype}_status": overall_status}
        # Check if all phases complete
        protocols = qdb.get_protocols_for_qual(qid)
        all_complete = all(p.get("status", "").startswith("completed") for p in protocols)
        if all_complete:
            updates["overall_status"] = "completed"
        qdb.update_qualification(qid, updates)

    # Phase F fix (C6): performed_by is derived from the authenticated
    # session, never taken from the request body — the previous
    # data.get("performed_by", "System") accepted any client-supplied name
    # for what is effectively an execution sign-off. See
    # PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md C6.
    sig = tenancy.signing_identity(g.tenant)
    qdb.add_approval_entry(
        qid, pid,
        f"{protocol.get('protocol_type','')} Protocol Execution Complete",
        sig["performed_by"], sig["role"],
        data.get("comments", ""),
        protocol.get("revision", "A"),
    )
    audit.log("qualification", qid, f"{protocol.get('protocol_type','')} Protocol completed",
              new={"protocol_id": pid, "status": overall_status, "fail_count": fail_count})

    esignature_service.record_signature(
        tenant=g.tenant, meaning=data.get("meaning", ""), reason=data.get("reason", ""),
        record_type="qualification", record_id=qid, version_number=protocol.get("revision", ""),
        old_status=old_status, new_status=overall_status,
    )
    return jsonify({"status": overall_status, "fail_count": fail_count})


# ── Deviations ────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/deviations", methods=["GET"])
def get_deviations(qid):
    if not tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_deviations(qid))


@bp.route("/<int:qid>/deviations", methods=["POST"])
def create_deviation(qid):
    if not tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id):
        return jsonify({"error": "Qualification not found"}), 404
    data = request.get_json() or {}
    dev = qdb.create_deviation(qid, data)
    audit.log("qualification", qid, "Deviation raised", new=dev)
    return jsonify(dev), 201


@bp.route("/<int:qid>/deviations/<int:did>", methods=["PUT"])
def update_deviation(qid, did):
    if not tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id):
        return jsonify({"error": "Qualification not found"}), 404
    existing_dev = qdb.get_deviation(did)
    if not existing_dev or existing_dev.get("qual_id") != qid:
        return jsonify({"error": "Deviation not found"}), 404
    data = request.get_json() or {}
    updated = qdb.update_deviation(did, data)
    if not updated:
        return jsonify({"error": "Deviation not found"}), 404
    audit.log("qualification", qid, "Deviation updated", old=existing_dev, new=updated)
    return jsonify(updated)


# ── Approvals ─────────────────────────────────────────────────────────────────
# Approval is PER PROTOCOL: each IQ/OQ/PQ protocol has its own approval_status
# and its own sign-off ledger (doc_type = the protocol type, record_id = the
# protocol id). The parent Qualification only groups them; its status is a
# roll-up (see _rollup_qualification_status) and approving one protocol never
# approves another. All lifecycle/RBAC/e-signature/Effective-gate logic is the
# shared services/validation_approval.py.

_PROTOCOL_LOCK_MSG = ("This protocol is {status} and its definition is locked — reject it back to "
                      "Draft to change it (test execution is unaffected)")


def _protocol_creator(qual: dict, protocol: dict) -> dict:
    """The protocol's own creator, falling back to its parent Qualification's
    (and finally the parent's authenticated `prepared_by`) for rows created
    before creator identity was captured."""
    return {
        "created_by_user_id": protocol.get("created_by_user_id") or qual.get("created_by_user_id") or "",
        "created_by_display_name": protocol.get("created_by_display_name") or qual.get("created_by_display_name") or "",
        "prepared_by": qual.get("prepared_by", ""),
    }


def _protocol_locked(protocol: dict) -> bool:
    return qdb.get_protocol_approval_status(protocol) != "draft"


def _rollup_qualification_status(qid: int) -> None:
    """Derive the parent's status from its protocols. Never overrides the
    parent's closed/obsolete terminal states, and never raises the parent
    above what ALL of its protocols have reached."""
    qual = qdb.get_qualification(qid)
    if not qual or qual["status"] in ("closed", "obsolete"):
        return
    states = [qdb.get_protocol_approval_status(p) for p in qdb.get_protocols_for_qual(qid)]
    if not states:
        return
    if all(st == "effective" for st in states):
        new = "effective"
    elif all(st in ("approved", "effective") for st in states):
        new = "approved"
    elif any(st not in ("draft", "obsolete") for st in states):
        new = "under_review"  # some protocol is in review, or only some are approved so far
    else:
        new = "draft"
    if new != qual["status"]:
        qdb.update_qualification(qid, {"status": new})


@bp.route("/<int:qid>/approval", methods=["GET"])
def get_approval(qid):
    if not tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_approval_trail(qid))


@bp.route("/<int:qid>/approval/signatories", methods=["GET"])
def get_qualification_approval_summary(qid):
    """Roll-up of every protocol's approval state (one entry per protocol)."""
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    out = []
    for p in qdb.get_protocols_for_qual(qid):
        page = validation_approval.build_page(
            g.tenant.company_id, p["protocol_type"], p["id"], qdb.get_protocol_approval_status(p))
        out.append({"protocol_id": p["id"], "protocol_type": p["protocol_type"],
                    "approval_status": page["status"], "completed_count": page["completed_count"],
                    "mandatory_count": page["mandatory_count"]})
    return jsonify({"qualification_status": qual["status"], "protocols": out})


@bp.route("/<int:qid>/protocols/<int:pid>/approval/signatories", methods=["GET"])
def get_protocol_approval_signatories(qid, pid):
    protocol = _scoped_protocol(qid, pid)
    if not protocol:
        return jsonify({"error": "Protocol not found"}), 404
    return jsonify(validation_approval.build_page(
        g.tenant.company_id, protocol["protocol_type"], pid, qdb.get_protocol_approval_status(protocol)))


@bp.route("/<int:qid>/protocols/<int:pid>/approval", methods=["GET"])
def get_protocol_approval_trail(qid, pid):
    if not _scoped_protocol(qid, pid):
        return jsonify({"error": "Protocol not found"}), 404
    return jsonify([e for e in qdb.get_approval_trail(qid) if e.get("protocol_id") == pid])


@bp.route("/<int:qid>/protocols/<int:pid>/approval", methods=["POST"])
def add_protocol_approval(qid, pid):
    """IQ/OQ/PQ protocol approval — the shared Validation workflow.
    Authorization is decided per action inside perform_action(): submission
    needs Validation:Submit (an Initiator); sign-off/reject/effective/obsolete
    need the company_admin/reviewer_qa platform role, the granular Validation
    permission, and the designation's department + functional role."""
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    protocol = _scoped_protocol(qid, pid)
    if not qual or not protocol:
        return jsonify({"error": "Protocol not found"}), 404
    data = request.get_json() or {}
    if not data.get("action", ""):
        return jsonify({"error": "action is required"}), 400

    sig = tenancy.signing_identity(g.tenant)
    ptype = protocol["protocol_type"]
    record = {"id": pid, "status": qdb.get_protocol_approval_status(protocol),
              "revision": protocol.get("revision") or "A"}

    def _apply(updates):
        qdb.set_protocol_approval_status(pid, updates.get("status", record["status"]), updates.get("revision"))

    try:
        body, code = validation_approval.perform_action(
            tenant=g.tenant, doc_type=ptype, audit_type="qualification", record=record, data=data,
            performed_by=sig["performed_by"], role=sig["role"],
            validate_transition=urs_lifecycle.validate_transition, apply_update=_apply, audit_id=qid,
            creator=_protocol_creator(qual, protocol),
            add_trail=lambda action, comments, rev: qdb.add_approval_entry(
                qid, pid, f"{ptype} {action}", sig["performed_by"], sig["role"], comments, rev,
                sig["electronic_sig"]),
        )
    except validation_approval.ApprovalError as exc:
        return jsonify({"error": exc.message}), exc.http_status

    _rollup_qualification_status(qid)
    if body.get("new_status") == "effective":
        protocol = qdb.get_protocol(pid)
        qdb.create_version_snapshot(qid, pid, f"{ptype} protocol made Effective", sig["performed_by"])
        _publish_effective_protocol_to_kb(qdb.get_qualification(qid), protocol)
    return jsonify(body), code


@bp.route("/<int:qid>/approval", methods=["POST"])
def add_approval(qid):
    """Container-level actions. Standard approval actions are PER PROTOCOL
    (POST /qual/<id>/protocols/<protocol_id>/approval) and are refused here,
    so the parent can never approve its protocols implicitly. Only the
    pre-standard terminal actions "Closed" and "Obsolete" remain at this level."""
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    data = request.get_json() or {}
    action = data.get("action", "")
    if not action:
        return jsonify({"error": "action is required"}), 400
    if action not in ("Closed", "Obsolete"):
        return jsonify({"error": "Approval is per protocol — use "
                                  "POST /qual/<id>/protocols/<protocol_id>/approval"}), 400
    return _terminal_qualification_action(qid, qual, action, data, tenancy.signing_identity(g.tenant))


def _terminal_qualification_action(qid, qual, action, data, sig):
    """Closed / Obsolete on the parent: platform role + Validation:Approve + e-signature."""
    if g.tenant.role not in ("company_admin", "reviewer_qa"):
        return jsonify({"error": "This action requires one of these roles: company_admin, reviewer_qa"}), 403
    if not module_access.has_business_permission(g.tenant, "Validation", "Approve"):
        return jsonify({"error": "This action requires 'Approve' permission on 'Validation'"}), 403
    new_status = "closed" if action == "Closed" else "obsolete"
    old_status = qual["status"]
    try:
        lifecycle_engine.validate_transition("QUALIFICATION", old_status, new_status)
    except lifecycle_engine.InvalidTransitionError as exc:
        return jsonify({"error": str(exc)}), 409
    try:
        esignature_service.require_esignature(
            g.tenant, data.get("password", ""), data.get("meaning", ""), data.get("reason", ""))
    except esignature_service.ReauthenticationError as exc:
        audit.log_failure("qualification", qid, f"Approval action blocked ({action}) — e-signature failed", reason=str(exc))
        return jsonify({"error": str(exc)}), 401
    except esignature_service.ESignatureError as exc:
        audit.log_failure("qualification", qid, evt.ESIGNATURE_FAILURE, reason=str(exc))
        return jsonify({"error": str(exc)}), 400
    qdb.update_qualification(qid, {"status": new_status})
    entry = qdb.add_approval_entry(qid, data.get("protocol_id"), action, sig["performed_by"], sig["role"],
                                   data.get("comments", ""), qual.get("revision", "A"), sig["electronic_sig"])
    audit.log("qualification", qid, action, old={"status": old_status}, new={"status": new_status},
              reason=data.get("comments", ""))
    esignature_service.record_signature(
        tenant=g.tenant, meaning=data.get("meaning", ""), reason=data.get("reason", ""),
        record_type="qualification", record_id=qid, version_number=qual.get("revision", ""),
        old_status=old_status, new_status=new_status)
    return jsonify(entry), 201


def _publish_effective_protocol_to_kb(qual: dict, protocol: dict) -> None:
    """A protocol becomes the current version in the Knowledge Base at ITS OWN
    Effective transition (not when the parent or a sibling is approved).
    kb_sync.publish_to_kb refuses unless every mandatory approval is complete.
    Failures are logged, never raised: the approval is already committed."""
    try:
        test_cases = qdb.get_test_cases(protocol["id"])
        executions = qdb.get_executions(protocol["id"])
        markdown_content = svc.build_protocol_markdown(qual, protocol, test_cases, executions)
        ptype = protocol.get("protocol_type", "IQ")
        kb_sync.publish_to_kb(
            source_type="qualification_protocol", source_id=protocol["id"],
            company_id=g.tenant.company_id,
            title=protocol.get("title", f"{ptype} Protocol"), doc_type=ptype,
            doc_number=protocol.get("protocol_number", ""), version=protocol.get("revision", "A"),
            content_markdown=markdown_content, effective_date=date.today().isoformat(),
            form_data={
                "title": protocol.get("title", ""), "equipment_name": qual.get("equipment_name", ""),
                "department": qual.get("department", ""),
            },
        )
    except Exception:
        logger.exception("kb_sync: failed to publish protocol %s to Knowledge Base", protocol.get("id"))


# ── Version History ───────────────────────────────────────────────────────────

@bp.route("/<int:qid>/versions", methods=["GET"])
def get_versions(qid):
    if not tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_versions(qid))


@bp.route("/<int:qid>/protocols/<int:pid>/versions", methods=["POST"])
def create_version(qid, pid):
    if not _scoped_protocol(qid, pid):
        return jsonify({"error": "Protocol not found"}), 404
    data = request.get_json() or {}
    # Phase F fix (C6): created_by is derived from the authenticated
    # session, never taken from the request body. See
    # PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md C6.
    created_by = tenancy.signing_identity(g.tenant)["performed_by"]
    change_summary = data.get("change_summary", "Version snapshot")
    snapshot = qdb.create_version_snapshot(qid, pid, change_summary, created_by)
    audit.log("qualification", qid, "Protocol version snapshot created",
              new={"protocol_id": pid, "change_summary": change_summary})
    return jsonify(snapshot), 201


# ── Traceability Matrix ───────────────────────────────────────────────────────

@bp.route("/<int:qid>/traceability", methods=["GET"])
def get_traceability(qid):
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404

    matrix = qdb.build_traceability_matrix(qid)

    # Enrich with URS and Risk data
    urs_reqs = []
    risk_items = []
    if qual.get("linked_urs_id"):
        try:
            from pharmagpt import urs_database as udb
            urs_reqs = udb.get_requirements(qual["linked_urs_id"])
        except Exception:
            pass
    if qual.get("linked_risk_id"):
        try:
            from pharmagpt import risk_database as rdb
            risk_items = rdb.get_risk_items(qual["linked_risk_id"])
        except Exception:
            pass

    matrix["urs_requirements"] = urs_reqs
    matrix["risk_items"] = risk_items
    return jsonify(matrix)


@bp.route("/<int:qid>/traceability/export/docx", methods=["GET", "POST"])
def export_traceability_docx(qid):
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404

    matrix = qdb.build_traceability_matrix(qid)
    urs_reqs = []
    risk_items = []
    if qual.get("linked_urs_id"):
        try:
            from pharmagpt import urs_database as udb
            urs_reqs = udb.get_requirements(qual["linked_urs_id"])
        except Exception:
            pass
    if qual.get("linked_risk_id"):
        try:
            from pharmagpt import risk_database as rdb
            risk_items = rdb.get_risk_items(qual["linked_risk_id"])
        except Exception:
            pass

    md_content = svc.build_traceability_markdown(matrix, urs_reqs, risk_items)
    title = f"Traceability Matrix — {qual.get('equipment_name', '')}"
    form_data = {
        "title": title,
        "equipment_name": qual.get("equipment_name", ""),
        "department": qual.get("department", ""),
        "revision": qual.get("revision", "A"),
        "prepared_by": qual.get("prepared_by", ""),
        "reviewed_by": qual.get("reviewed_by", ""),
        "approved_by": qual.get("approved_by", ""),
        "effective_date": qual.get("effective_date", ""),
    }
    docx_bytes = markdown_to_docx(md_content, "Traceability Matrix", form_data)
    safe_name = f"TraceMatrix_{qual.get('qual_number', qid)}.docx".replace(" ", "_")

    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=safe_name,
    )


# ── Protocol Export ───────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/export/docx", methods=["GET", "POST"])
def export_protocol_docx(qid, pid):
    qual = tenancy.scoped_or_none(qdb.get_qualification(qid), g.tenant.company_id)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404

    test_cases = qdb.get_test_cases(pid)
    executions = qdb.get_executions(pid)

    md_content = svc.build_protocol_markdown(qual, protocol, test_cases, executions)
    ptype = protocol.get("protocol_type", "IQ")
    title = protocol.get("title", f"{ptype} Protocol")
    form_data = {
        "title": title,
        "protocol_number": protocol.get("protocol_number", ""),
        "equipment_name": qual.get("equipment_name", ""),
        "department": qual.get("department", ""),
        "revision": protocol.get("revision", "A"),
        "prepared_by": qual.get("prepared_by", ""),
        "reviewed_by": qual.get("reviewed_by", ""),
        "approved_by": qual.get("approved_by", ""),
        "effective_date": qual.get("effective_date", ""),
    }
    docx_bytes = markdown_to_docx(md_content, ptype, form_data)
    safe_name = f"{ptype}_{protocol.get('protocol_number', pid)}.docx".replace(" ", "_")

    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=safe_name,
    )

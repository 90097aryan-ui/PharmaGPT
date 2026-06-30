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
from flask import Blueprint, jsonify, request, Response, stream_with_context, send_file

from pharmagpt import qual_database as qdb
from pharmagpt.services import qual_service as svc
from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from pharmagpt.services.doc_exporter import markdown_to_docx
from google.genai import types

bp = Blueprint("qual", __name__, url_prefix="/qual")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route("/dashboard")
def dashboard():
    return jsonify(qdb.get_dashboard_stats())


# ── Qualification CRUD ────────────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
def list_qualifications():
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
    return jsonify(qdb.get_all_qualifications({k: v for k, v in filters.items() if v}))


@bp.route("/", methods=["POST"])
def create_qualification():
    data = request.get_json() or {}
    if not data.get("equipment_name", "").strip() and not data.get("title", "").strip():
        return jsonify({"error": "Equipment name or title is required"}), 400
    if not data.get("title", "").strip():
        data["title"] = f"Qualification — {data.get('equipment_name', 'New Equipment')}"
    qual = qdb.create_qualification(data)
    return jsonify(qual), 201


@bp.route("/<int:qid>", methods=["GET"])
def get_qualification(qid):
    qual = qdb.get_qualification(qid)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qual)


@bp.route("/<int:qid>", methods=["PUT"])
def update_qualification(qid):
    if not qdb.get_qualification(qid):
        return jsonify({"error": "Qualification not found"}), 404
    data = request.get_json() or {}
    updated = qdb.update_qualification(qid, data)
    return jsonify(updated)


@bp.route("/<int:qid>", methods=["DELETE"])
def delete_qualification(qid):
    if not qdb.get_qualification(qid):
        return jsonify({"error": "Qualification not found"}), 404
    qdb.delete_qualification(qid)
    return jsonify({"deleted": True})


# ── Protocols ─────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols", methods=["GET"])
def get_protocols(qid):
    if not qdb.get_qualification(qid):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_protocols_for_qual(qid))


@bp.route("/<int:qid>/protocols", methods=["POST"])
def create_protocol(qid):
    qual = qdb.get_qualification(qid)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    data = request.get_json() or {}
    protocol_type = data.get("protocol_type", "IQ").upper()
    if protocol_type not in ("IQ", "OQ", "PQ"):
        return jsonify({"error": "protocol_type must be IQ, OQ, or PQ"}), 400
    # Auto-fill from qualification
    if not data.get("title"):
        data["title"] = f"{protocol_type} Protocol — {qual.get('equipment_name', '')}"
    protocol = qdb.create_protocol(qid, protocol_type, data)
    return jsonify(protocol), 201


@bp.route("/<int:qid>/protocols/<int:pid>", methods=["GET"])
def get_protocol(qid, pid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    return jsonify(protocol)


@bp.route("/<int:qid>/protocols/<int:pid>", methods=["PUT"])
def update_protocol(qid, pid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    data = request.get_json() or {}
    updated = qdb.update_protocol(pid, data)
    return jsonify(updated)


@bp.route("/<int:qid>/protocols/<int:pid>", methods=["DELETE"])
def delete_protocol(qid, pid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    qdb.delete_protocol(pid)
    return jsonify({"deleted": True})


# ── Test Cases ────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/test-cases", methods=["GET"])
def get_test_cases(qid, pid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    return jsonify(qdb.get_test_cases(pid))


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases", methods=["POST"])
def save_test_cases(qid, pid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    tcs = request.get_json() or []
    saved = qdb.save_test_cases(pid, qid, tcs)
    return jsonify(saved)


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases/add", methods=["POST"])
def add_test_case(qid, pid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    tc = request.get_json() or {}
    new_tc = qdb.add_test_case(pid, qid, tc)
    return jsonify(new_tc), 201


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases/<int:tcid>", methods=["PUT"])
def update_test_case(qid, pid, tcid):
    data = request.get_json() or {}
    updated = qdb.update_test_case(tcid, data)
    if not updated:
        return jsonify({"error": "Test case not found"}), 404
    return jsonify(updated)


@bp.route("/<int:qid>/protocols/<int:pid>/test-cases/<int:tcid>", methods=["DELETE"])
def delete_test_case(qid, pid, tcid):
    qdb.delete_test_case(tcid)
    return jsonify({"deleted": True})


# ── AI Generation (SSE) ───────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/generate", methods=["POST"])
def generate_test_cases(qid, pid):
    """Stream AI-generated test cases for IQ/OQ/PQ protocol."""
    qual = qdb.get_qualification(qid)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404

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
                yield f"data: {json.dumps({'done': True, 'count': len(ai_tcs)})}\n\n"
            except Exception as parse_err:
                yield f"data: {json.dumps({'done': True, 'parse_error': str(parse_err)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── AI Review ─────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/protocols/<int:pid>/review", methods=["POST"])
def review_protocol(qid, pid):
    qual = qdb.get_qualification(qid)
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
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    executions = qdb.get_executions(pid)
    # Build execution map keyed by test_case_id for efficient frontend access
    exec_map = {e["test_case_id"]: e for e in executions}
    return jsonify({"executions": executions, "exec_map": exec_map})


@bp.route("/<int:qid>/protocols/<int:pid>/execute/<int:tcid>", methods=["POST"])
def execute_test_case(qid, pid, tcid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    data = request.get_json() or {}
    result = qdb.save_execution(tcid, pid, qid, data)

    # Auto-update protocol status to in_progress
    qual = qdb.get_qualification(qid)
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
            "raised_by": data.get("executed_by", ""),
            "raised_date": data.get("executed_date", ""),
        })

    return jsonify(result)


@bp.route("/<int:qid>/protocols/<int:pid>/complete", methods=["POST"])
def complete_protocol(qid, pid):
    """Mark protocol as completed and update qualification status."""
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    data = request.get_json() or {}

    # Check for any failing test cases
    test_cases = qdb.get_test_cases(pid)
    fail_count = sum(1 for tc in test_cases if tc.get("status") == "fail")
    pending_count = sum(1 for tc in test_cases if tc.get("status") == "pending")

    if pending_count > 0 and not data.get("force"):
        return jsonify({"error": f"{pending_count} test cases still pending. Pass force=true to override."}), 400

    overall_status = "completed" if fail_count == 0 else "completed_with_deviations"
    qdb.update_protocol(pid, {"status": overall_status})

    # Update qualification phase status
    qual = qdb.get_qualification(qid)
    if qual:
        ptype = protocol.get("protocol_type", "IQ").lower()
        updates = {f"{ptype}_status": overall_status}
        # Check if all phases complete
        protocols = qdb.get_protocols_for_qual(qid)
        all_complete = all(p.get("status", "").startswith("completed") for p in protocols)
        if all_complete:
            updates["overall_status"] = "completed"
        qdb.update_qualification(qid, updates)

    qdb.add_approval_entry(
        qid, pid,
        f"{protocol.get('protocol_type','')} Protocol Execution Complete",
        data.get("performed_by", "System"), "Executor",
        data.get("comments", ""),
        protocol.get("revision", "A"),
    )

    return jsonify({"status": overall_status, "fail_count": fail_count})


# ── Deviations ────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/deviations", methods=["GET"])
def get_deviations(qid):
    if not qdb.get_qualification(qid):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_deviations(qid))


@bp.route("/<int:qid>/deviations", methods=["POST"])
def create_deviation(qid):
    if not qdb.get_qualification(qid):
        return jsonify({"error": "Qualification not found"}), 404
    data = request.get_json() or {}
    dev = qdb.create_deviation(qid, data)
    return jsonify(dev), 201


@bp.route("/<int:qid>/deviations/<int:did>", methods=["PUT"])
def update_deviation(qid, did):
    data = request.get_json() or {}
    updated = qdb.update_deviation(did, data)
    if not updated:
        return jsonify({"error": "Deviation not found"}), 404
    return jsonify(updated)


# ── Approvals ─────────────────────────────────────────────────────────────────

@bp.route("/<int:qid>/approval", methods=["GET"])
def get_approval(qid):
    if not qdb.get_qualification(qid):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_approval_trail(qid))


@bp.route("/<int:qid>/approval", methods=["POST"])
def add_approval(qid):
    qual = qdb.get_qualification(qid)
    if not qual:
        return jsonify({"error": "Qualification not found"}), 404
    data = request.get_json() or {}
    action = data.get("action", "")
    performed_by = data.get("performed_by", "")
    if not action or not performed_by:
        return jsonify({"error": "action and performed_by are required"}), 400

    # Status transitions
    status_map = {
        "Submitted for Review": "under_review",
        "Review Complete": "under_review",
        "Submitted for Approval": "pending_approval",
        "Approved": "approved",
        "Rejected": "draft",
        "Closed": "closed",
        "Obsolete": "obsolete",
    }
    if action in status_map:
        qdb.update_qualification(qid, {"status": status_map[action]})

    entry = qdb.add_approval_entry(
        qid, data.get("protocol_id"),
        action, performed_by,
        data.get("role", ""),
        data.get("comments", ""),
        qual.get("revision", "A"),
        data.get("electronic_sig", ""),
    )
    return jsonify(entry), 201


# ── Version History ───────────────────────────────────────────────────────────

@bp.route("/<int:qid>/versions", methods=["GET"])
def get_versions(qid):
    if not qdb.get_qualification(qid):
        return jsonify({"error": "Qualification not found"}), 404
    return jsonify(qdb.get_versions(qid))


@bp.route("/<int:qid>/protocols/<int:pid>/versions", methods=["POST"])
def create_version(qid, pid):
    protocol = qdb.get_protocol(pid)
    if not protocol or protocol.get("qual_id") != qid:
        return jsonify({"error": "Protocol not found"}), 404
    data = request.get_json() or {}
    snapshot = qdb.create_version_snapshot(qid, pid, data.get("change_summary", "Version snapshot"), data.get("created_by", "System"))
    return jsonify(snapshot), 201


# ── Traceability Matrix ───────────────────────────────────────────────────────

@bp.route("/<int:qid>/traceability", methods=["GET"])
def get_traceability(qid):
    qual = qdb.get_qualification(qid)
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
    qual = qdb.get_qualification(qid)
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
    form_data = {
        "equipment_name": qual.get("equipment_name", ""),
        "department": qual.get("department", ""),
        "revision": qual.get("revision", "A"),
        "prepared_by": qual.get("prepared_by", ""),
        "reviewed_by": qual.get("reviewed_by", ""),
        "approved_by": qual.get("approved_by", ""),
        "effective_date": qual.get("effective_date", ""),
    }
    title = f"Traceability Matrix — {qual.get('equipment_name', '')}"
    docx_bytes = markdown_to_docx(md_content, form_data, "Traceability Matrix", title)
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
    qual = qdb.get_qualification(qid)
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
        "protocol_number": protocol.get("protocol_number", ""),
        "equipment_name": qual.get("equipment_name", ""),
        "department": qual.get("department", ""),
        "revision": protocol.get("revision", "A"),
        "prepared_by": qual.get("prepared_by", ""),
        "reviewed_by": qual.get("reviewed_by", ""),
        "approved_by": qual.get("approved_by", ""),
        "effective_date": qual.get("effective_date", ""),
    }
    docx_bytes = markdown_to_docx(md_content, form_data, ptype, title)
    safe_name = f"{ptype}_{protocol.get('protocol_number', pid)}.docx".replace(" ", "_")

    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=safe_name,
    )

"""
routes/report.py — Validation Report Management Suite API endpoints.

All routes return JSON. SSE streaming for AI section generation.

Routes
------
GET    /report/dashboard                      Dashboard statistics
GET    /report/                                List all reports
POST   /report/                                Create report
GET    /report/<id>                           Get report
PUT    /report/<id>                           Update report
DELETE /report/<id>                           Delete report

GET    /report/<id>/sections                  Get all sections
PUT    /report/<id>/sections/<section_key>    Update section content

POST   /report/<id>/generate                  AI generate all sections (SSE)
POST   /report/<id>/generate/<section_key>    AI generate single section (SSE)
POST   /report/<id>/review                    AI review report

GET    /report/<id>/traceability              Auto-build traceability summary
GET    /report/<id>/approval                  Get approval trail
POST   /report/<id>/approval                  Add approval entry
GET    /report/<id>/versions                  Get version history
POST   /report/<id>/versions                  Create version snapshot

GET    /report/<id>/export/docx               Export as Word document
GET    /report/linked/<qual_id>               Get or create report for qualification
"""

import json
import io
from flask import Blueprint, jsonify, request, Response, stream_with_context, send_file

from pharmagpt import report_database as rdb
from pharmagpt import qual_database as qdb
from pharmagpt import urs_database as udb
from pharmagpt import risk_database as risdb
from pharmagpt.services import report_service as svc
from pharmagpt.services.doc_exporter import markdown_to_docx
from pharmagpt.state import gemini_client
from pharmagpt.config import GEMINI_MODEL
from pharmagpt.prompts import PHARMA_SYSTEM_PROMPT
from google.genai import types

bp = Blueprint("report", __name__, url_prefix="/report")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route("/dashboard")
def dashboard():
    return jsonify(rdb.get_dashboard_stats())


# ── Report CRUD ───────────────────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
def list_reports():
    filters = {
        "status":          request.args.get("status"),
        "report_type":     request.args.get("report_type"),
        "department":      request.args.get("department"),
        "equipment_type":  request.args.get("equipment_type"),
        "validation_type": request.args.get("validation_type"),
        "keyword":         request.args.get("q"),
        "linked_qual_id":  request.args.get("linked_qual_id"),
    }
    return jsonify(rdb.get_all_reports({k: v for k, v in filters.items() if v}))


@bp.route("/", methods=["POST"])
def create_report():
    data = request.get_json() or {}

    # Auto-populate from linked qualification if provided
    linked_qual_id = data.get("linked_qual_id")
    if linked_qual_id:
        qual = qdb.get_qualification(int(linked_qual_id))
        if qual:
            for field in ("equipment_name", "equipment_id", "equipment_type", "manufacturer",
                          "model", "serial_number", "department", "site", "location",
                          "validation_type", "scope", "purpose",
                          "prepared_by", "reviewed_by", "approved_by",
                          "planned_start", "planned_end", "actual_start", "actual_end"):
                if not data.get(field) and qual.get(field):
                    data[field] = qual[field]
            if not data.get("title"):
                data["title"] = f"Validation Report — {qual.get('equipment_name','Equipment')}"
            if not data.get("linked_urs_id") and qual.get("linked_urs_id"):
                data["linked_urs_id"] = qual["linked_urs_id"]
            if not data.get("linked_risk_id") and qual.get("linked_risk_id"):
                data["linked_risk_id"] = qual["linked_risk_id"]

    if not data.get("title", "").strip():
        data["title"] = f"Validation Report — {data.get('equipment_name','New Equipment')}"

    report = rdb.create_report(data)
    return jsonify(report), 201


@bp.route("/<int:rid>", methods=["GET"])
def get_report(rid):
    report = rdb.get_report(rid)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(report)


@bp.route("/<int:rid>", methods=["PUT"])
def update_report(rid):
    data = request.get_json() or {}
    report = rdb.update_report(rid, data)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(report)


@bp.route("/<int:rid>", methods=["DELETE"])
def delete_report(rid):
    rdb.delete_report(rid)
    return jsonify({"success": True})


# ── Sections ──────────────────────────────────────────────────────────────────

@bp.route("/<int:rid>/sections", methods=["GET"])
def get_sections(rid):
    sections = rdb.get_sections(rid)
    return jsonify(sections)


@bp.route("/<int:rid>/sections/<section_key>", methods=["PUT"])
def update_section(rid, section_key):
    data = request.get_json() or {}
    content = data.get("content", "")
    section = rdb.update_section(rid, section_key, content)
    if not section:
        return jsonify({"error": "Section not found"}), 404
    return jsonify(section)


# ── AI Generation (SSE Streaming) ────────────────────────────────────────────

def _load_context(report: dict) -> dict:
    """Load all linked module data and build aggregated context."""
    qual = None
    protocols = []
    test_cases_by_protocol = {}
    executions_by_protocol = {}
    deviations = []

    if report.get("linked_qual_id"):
        qual = qdb.get_qualification(int(report["linked_qual_id"]))
        if qual:
            protocols = qdb.get_protocols_for_qual(qual["id"])
            for p in protocols:
                tcs = qdb.get_test_cases(p["id"])
                # Attach protocol type to each test case
                for tc in tcs:
                    tc["protocol_type"] = p.get("protocol_type", "")
                test_cases_by_protocol[p["id"]] = tcs
                executions_by_protocol[p["id"]] = qdb.get_executions(p["id"])
            deviations = qdb.get_deviations(qual["id"])

    urs_project = None
    urs_requirements = []
    if report.get("linked_urs_id"):
        urs_project = udb.get_urs(int(report["linked_urs_id"]))
        if urs_project:
            urs_requirements = udb.get_requirements(int(report["linked_urs_id"]))

    risk_assessment = None
    risk_items = []
    if report.get("linked_risk_id"):
        risk_assessment = risdb.get_assessment(int(report["linked_risk_id"]))
        if risk_assessment:
            risk_items = risdb.get_items(int(report["linked_risk_id"]))

    return svc.aggregate_report_context(
        report=report,
        qual=qual,
        protocols=protocols,
        test_cases_by_protocol=test_cases_by_protocol,
        executions_by_protocol=executions_by_protocol,
        deviations=deviations,
        urs_project=urs_project,
        urs_requirements=urs_requirements,
        risk_assessment=risk_assessment,
        risk_items=risk_items,
    )


@bp.route("/<int:rid>/generate/<section_key>", methods=["POST"])
def generate_section(rid, section_key):
    """AI-generate a single report section via SSE streaming."""
    report = rdb.get_report(rid)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    ctx = _load_context(report)
    prompt = svc.build_section_prompt(section_key, ctx)

    def stream():
        try:
            response = gemini_client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=PHARMA_SYSTEM_PROMPT,
                    temperature=0.3,
                    max_output_tokens=4096,
                ),
            )
            full_text = ""
            for chunk in response:
                if chunk.text:
                    full_text += chunk.text
                    yield f"data: {json.dumps({'chunk': chunk.text, 'section': section_key})}\n\n"

            # Save generated content
            rdb.mark_section_generated(rid, section_key, full_text)
            rdb.update_report(rid, {"ai_generated": 1})
            yield f"data: {json.dumps({'done': True, 'section': section_key, 'length': len(full_text)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


@bp.route("/<int:rid>/generate", methods=["POST"])
def generate_all_sections(rid):
    """AI-generate all report sections sequentially via SSE streaming."""
    report = rdb.get_report(rid)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    data = request.get_json() or {}
    # Which sections to generate — default to all generatable sections
    sections_to_generate = data.get("sections", [
        "executive_summary", "purpose", "scope", "responsibilities",
        "applicable_standards", "equipment_details", "system_description",
        "validation_strategy", "urs_summary", "risk_assessment_summary",
        "iq_summary", "oq_summary", "pq_summary", "execution_summary",
        "deviation_summary", "traceability_summary", "critical_findings",
        "risk_evaluation", "compliance_assessment", "conclusion",
        "recommendations", "final_statement",
        "cover_page", "approval_page", "revision_history",
    ])

    ctx = _load_context(report)

    def stream():
        try:
            for section_key in sections_to_generate:
                yield f"data: {json.dumps({'status': 'generating', 'section': section_key})}\n\n"

                prompt = svc.build_section_prompt(section_key, ctx)
                response = gemini_client.models.generate_content_stream(
                    model=GEMINI_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    config=types.GenerateContentConfig(
                        system_instruction=PHARMA_SYSTEM_PROMPT,
                        temperature=0.3,
                        max_output_tokens=4096,
                    ),
                )
                full_text = ""
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text
                        yield f"data: {json.dumps({'chunk': chunk.text, 'section': section_key})}\n\n"

                rdb.mark_section_generated(rid, section_key, full_text)
                yield f"data: {json.dumps({'section_done': True, 'section': section_key})}\n\n"

            # Update report stats from context
            rdb.update_report(rid, {
                "ai_generated": 1,
                "total_tests": ctx.get("total_tests", 0),
                "pass_count": ctx.get("pass_count", 0),
                "fail_count": ctx.get("fail_count", 0),
                "na_count": ctx.get("na_count", 0),
                "deviation_count": ctx.get("total_deviations", 0),
            })
            yield f"data: {json.dumps({'all_done': True, 'sections_generated': len(sections_to_generate)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


# ── AI Review ─────────────────────────────────────────────────────────────────

@bp.route("/<int:rid>/review", methods=["POST"])
def review_report(rid):
    report = rdb.get_report(rid)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    sections = rdb.get_sections(rid)
    ctx = _load_context(report)
    prompt = svc.build_review_prompt(report, sections, ctx)

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
        raw = response.text or ""
        # Strip markdown code fences if present
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        review_data = json.loads(raw)
        saved = rdb.save_ai_review(rid, review_data)
        return jsonify(saved)

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI returned invalid JSON: {e}", "raw": raw[:500]}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Traceability ──────────────────────────────────────────────────────────────

@bp.route("/<int:rid>/traceability", methods=["GET"])
def get_traceability(rid):
    report = rdb.get_report(rid)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    ctx = _load_context(report)

    # Collect all test cases across all protocols
    all_tcs = []
    if report.get("linked_qual_id"):
        qual = qdb.get_qualification(int(report["linked_qual_id"]))
        if qual:
            protocols = qdb.get_protocols_for_qual(qual["id"])
            for p in protocols:
                tcs = qdb.get_test_cases(p["id"])
                for tc in tcs:
                    tc["protocol_type"] = p.get("protocol_type", "")
                all_tcs.extend(tcs)

    matrix = svc.build_traceability_summary(
        urs_requirements=ctx.get("urs_requirements", []),
        risk_items=ctx.get("risk_items", []),
        test_cases_all=all_tcs,
    )
    return jsonify(matrix)


# ── Approval ──────────────────────────────────────────────────────────────────

@bp.route("/<int:rid>/approval", methods=["GET"])
def get_approval(rid):
    return jsonify(rdb.get_approval_trail(rid))


@bp.route("/<int:rid>/approval", methods=["POST"])
def add_approval(rid):
    report = rdb.get_report(rid)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    data = request.get_json() or {}
    action = data.get("action", "")
    performed_by = data.get("performed_by", "")
    role = data.get("role", "")
    comments = data.get("comments", "")
    version = data.get("version", report.get("version", "v1.0"))
    electronic_sig = data.get("electronic_sig", "")

    if not action or not performed_by:
        return jsonify({"error": "action and performed_by are required"}), 400

    # Update report status based on action
    status_map = {
        "Submit for Review": "under_review",
        "Technical Review Approved": "under_review",
        "QA Approved": "approved",
        "Released": "released",
        "Archived": "archived",
        "Rejected": "draft",
        "Obsolete": "obsolete",
    }
    new_status = status_map.get(action)
    if new_status:
        rdb.update_report(rid, {"status": new_status})

    entry = rdb.add_approval_entry(rid, action, performed_by, role, comments, version, electronic_sig)
    return jsonify(entry), 201


# ── Versions ──────────────────────────────────────────────────────────────────

@bp.route("/<int:rid>/versions", methods=["GET"])
def get_versions(rid):
    return jsonify(rdb.get_versions(rid))


@bp.route("/<int:rid>/versions", methods=["POST"])
def create_version(rid):
    data = request.get_json() or {}
    snapshot = rdb.create_version_snapshot(
        rid,
        change_summary=data.get("change_summary", ""),
        created_by=data.get("created_by", "System"),
    )
    return jsonify(snapshot), 201


# ── Export ────────────────────────────────────────────────────────────────────

@bp.route("/<int:rid>/export/docx", methods=["GET"])
def export_docx(rid):
    report = rdb.get_report(rid)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    sections = rdb.get_sections(rid)
    markdown_content = svc.build_docx_markdown(report, sections)

    doc_type = report.get("report_type", "Validation Report")
    form_data = {
        "title": report.get("title", doc_type),
        "doc_number": report.get("report_number", ""),
        "equipment_name": report.get("equipment_name", ""),
        "department": report.get("department", ""),
        "revision": report.get("revision", "A"),
        "prepared_by": report.get("prepared_by", ""),
        "reviewed_by": report.get("reviewed_by", ""),
        "approved_by": report.get("approved_by", ""),
        "effective_date": report.get("effective_date", ""),
    }
    docx_bytes = markdown_to_docx(markdown_content, doc_type, form_data)
    filename = f"{report.get('report_number','VR') or 'VR'}_{report.get('equipment_name','Report').replace(' ','_')}_Rev{report.get('revision','A')}.docx"

    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


# ── Linked Report Lookup ──────────────────────────────────────────────────────

@bp.route("/linked/<int:qual_id>", methods=["GET"])
def get_linked_report(qual_id):
    """Find the validation report linked to a specific qualification."""
    reports = rdb.get_all_reports({"linked_qual_id": str(qual_id)})
    if reports:
        return jsonify(reports[0])
    return jsonify(None)

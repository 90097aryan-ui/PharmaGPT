"""
qual_service.py — Business logic and AI prompts for the Qualification Management Suite.

Responsibilities
----------------
1. AI test case generation for IQ, OQ, PQ (SSE streaming).
2. AI review of completed protocols.
3. DOCX export builder.
4. Traceability context injection from URS and Risk modules.
"""

from __future__ import annotations
import json


# ── IQ Test Case Generation Prompt ───────────────────────────────────────────

def build_iq_generation_prompt(qual_info: dict, urs_reqs: list[dict], risk_items: list[dict]) -> str:
    equipment_name = qual_info.get("equipment_name", "the equipment")
    equipment_type = qual_info.get("equipment_type", "")
    category       = qual_info.get("category", "")
    manufacturer   = qual_info.get("manufacturer", "")
    model          = qual_info.get("model", "")
    serial_number  = qual_info.get("serial_number", "")
    capacity       = qual_info.get("capacity", "")
    location       = qual_info.get("location", "")
    department     = qual_info.get("department", "")
    scope          = qual_info.get("scope", "")
    purpose        = qual_info.get("purpose", "")

    urs_context = ""
    if urs_reqs:
        urs_context = "\n\nLINKED URS REQUIREMENTS (use these IDs in urs_req_ids field):\n"
        for r in urs_reqs[:30]:
            urs_context += f"- {r.get('req_id','')}: {r.get('requirement','')[:120]}\n"

    risk_context = ""
    if risk_items:
        risk_context = "\n\nLINKED RISK ITEMS (use these IDs in risk_item_ids field):\n"
        for r in risk_items[:20]:
            risk_context += f"- {r.get('item_id', r.get('id',''))}: {r.get('failure_mode', r.get('hazard',''))[:100]}\n"

    return f"""You are a Senior Pharmaceutical Validation Consultant with 30+ years of experience writing Installation Qualification (IQ) protocols for pharmaceutical equipment, utilities, and computerized systems.

Generate a comprehensive, GMP-compliant IQ Test Case set for:

EQUIPMENT DETAILS:
- Equipment Name: {equipment_name}
- Equipment Type: {equipment_type}
- Category: {category}
- Manufacturer: {manufacturer}
- Model: {model}
- Serial Number: {serial_number}
- Capacity: {capacity}
- Location: {location}
- Department: {department}
- Scope: {scope}
- Purpose: {purpose}
{urs_context}{risk_context}

IQ SECTIONS TO COVER (generate 3-8 test cases per applicable section):
1. Document Verification — SOPs, manuals, drawings, certificates, calibration records
2. Component Verification — All major components, spare parts list
3. Material of Construction — Product-contact materials, MOC certificates
4. Utility Verification — Electrical, pneumatic, water, steam, compressed air connections
5. Electrical Verification — Voltage, amperage, grounding, panel labeling
6. Instrumentation & Calibration — All instruments, calibration status, calibration certificates
7. Safety Verification — Safety interlocks, emergency stops, guards, alarms
8. Software Verification — Software version, configuration, access control (if computerized)
9. SCADA/PLC Verification — Control system, PLC program version, I/O check (if applicable)
10. Interface Verification — LIMS, MES, ERP, BMS integration (if applicable)
11. Training Verification — Operator training records, qualification of personnel
12. SOP Verification — Relevant SOPs available, current revision, approved
13. Preventive Maintenance — PM schedule, maintenance procedures, spare parts
14. Drawing Verification — P&ID, layout drawings, electrical drawings match installed equipment
15. Alarm Configuration — All alarms configured, alarm list documented

INSTRUCTIONS:
1. Each test case must be specific, verifiable, and GMP-compliant.
2. Include exact acceptance criteria with measurable pass/fail criteria.
3. Reference applicable standards: EU GMP Annex 15, 21 CFR Part 211, GAMP 5, WHO GMP, Schedule M.
4. Link each test case to relevant URS requirement IDs and Risk item IDs from the lists above.
5. Flag GMP-Critical test cases clearly.
6. Test procedures must be step-by-step, clear enough for a technician to execute.
7. Generate only applicable test cases for this specific equipment type.

OUTPUT FORMAT — Return ONLY a JSON array:
[
  {{
    "test_id": "IQ-TC-001",
    "section": "Document Verification",
    "test_name": "Verify Equipment Manual Availability",
    "objective": "To verify that the original equipment manual is available and current.",
    "prerequisites": "Equipment manual must be received from manufacturer",
    "test_procedure": "1. Locate the equipment operation and maintenance manual.\\n2. Verify the manual is for the correct model number.\\n3. Verify the manual is the latest revision.\\n4. Record the document number and revision.",
    "expected_result": "Equipment manual available, correct model, latest revision.",
    "acceptance_criteria": "Equipment manual for {model} is available, document number recorded, revision confirmed as latest.",
    "equipment_required": "None",
    "materials_required": "Equipment manual",
    "gmp_criticality": "GMP",
    "risk_level": "Medium",
    "regulatory_ref": "EU GMP Annex 15, Section 4.2",
    "urs_req_ids": ["DOC-001"],
    "risk_item_ids": []
  }}
]

GMP Criticality values: GMP-Critical, GMP, Non-GMP
Risk Level values: Critical, High, Medium, Low
"""


def build_oq_generation_prompt(qual_info: dict, urs_reqs: list[dict], risk_items: list[dict]) -> str:
    equipment_name = qual_info.get("equipment_name", "the equipment")
    equipment_type = qual_info.get("equipment_type", "")
    category       = qual_info.get("category", "")
    manufacturer   = qual_info.get("manufacturer", "")
    model          = qual_info.get("model", "")
    capacity       = qual_info.get("capacity", "")
    scope          = qual_info.get("scope", "")
    purpose        = qual_info.get("purpose", "")

    urs_context = ""
    if urs_reqs:
        urs_context = "\n\nLINKED URS REQUIREMENTS:\n"
        for r in urs_reqs[:30]:
            urs_context += f"- {r.get('req_id','')}: {r.get('requirement','')[:120]}\n"

    risk_context = ""
    if risk_items:
        risk_context = "\n\nLINKED RISK ITEMS:\n"
        for r in risk_items[:20]:
            risk_context += f"- {r.get('item_id', r.get('id',''))}: {r.get('failure_mode', r.get('hazard',''))[:100]}\n"

    return f"""You are a Senior Pharmaceutical Validation Consultant with 30+ years of experience writing Operational Qualification (OQ) protocols for pharmaceutical equipment and systems.

Generate a comprehensive, GMP-compliant OQ Test Case set for:

EQUIPMENT DETAILS:
- Equipment Name: {equipment_name}
- Equipment Type: {equipment_type}
- Category: {category}
- Manufacturer: {manufacturer}
- Model: {model}
- Capacity: {capacity}
- Scope: {scope}
- Purpose: {purpose}
{urs_context}{risk_context}

OQ SECTIONS TO COVER (generate 3-8 test cases per applicable section):
1. Functional Tests — All operational functions work as specified in URS
2. Range Qualification — All parameters operate correctly across the full specified range
3. Alarm Tests — All alarms trigger at correct setpoints and respond correctly
4. Interlock Tests — Safety interlocks function correctly, prevent unsafe operation
5. Emergency Stop Tests — E-stop functions correctly, safe state achieved
6. Power Failure Recovery — Correct behavior after power interruption, data integrity
7. Control System Tests — PLC/SCADA logic, recipe management, setpoint control
8. Speed / Throughput Qualification — Equipment meets rated speed/throughput
9. Accuracy & Precision Tests — Measurements/dosing/dispensing within specified tolerance
10. Repeatability Tests — Consistent results across multiple runs
11. Software Function Tests — All software features function correctly
12. Audit Trail Verification — All actions logged, ALCOA+ compliant (if computerized)
13. Electronic Signature Tests — ES function per 21 CFR Part 11 (if computerized)
14. User Access Control — Role-based access enforced correctly
15. Data Backup & Recovery — Data backup functions, recovery verified
16. Cybersecurity — Password policy, access logging, network security (if computerized)
17. Recipe Verification — All product recipes load and execute correctly (if applicable)
18. Cleaning / CIP Tests — Cleaning cycle functions correctly (if applicable)

INSTRUCTIONS:
1. Each test case must challenge the equipment at its operating limits (low, mid, high).
2. Include precise acceptance criteria with numeric tolerances where applicable.
3. Reference standards: EU GMP Annex 15, 21 CFR Part 211, GAMP 5, ICH Q9, WHO GMP.
4. Link to URS requirement IDs and Risk item IDs.
5. For computerized systems, always test audit trail, ES, and access control.
6. Include worst-case conditions where scientifically justified.
7. Generate only test cases applicable to this specific equipment.

OUTPUT FORMAT — Return ONLY a JSON array with the same structure as IQ but use test_id prefix "OQ-TC-".
"""


def build_pq_generation_prompt(qual_info: dict, urs_reqs: list[dict], risk_items: list[dict]) -> str:
    equipment_name = qual_info.get("equipment_name", "the equipment")
    equipment_type = qual_info.get("equipment_type", "")
    category       = qual_info.get("category", "")
    capacity       = qual_info.get("capacity", "")
    scope          = qual_info.get("scope", "")
    purpose        = qual_info.get("purpose", "")

    urs_context = ""
    if urs_reqs:
        urs_context = "\n\nLINKED URS REQUIREMENTS:\n"
        for r in urs_reqs[:20]:
            urs_context += f"- {r.get('req_id','')}: {r.get('requirement','')[:120]}\n"

    return f"""You are a Senior Pharmaceutical Validation Consultant with 30+ years of experience writing Performance Qualification (PQ) protocols for pharmaceutical manufacturing.

Generate a comprehensive, GMP-compliant PQ Test Case set for:

EQUIPMENT DETAILS:
- Equipment Name: {equipment_name}
- Equipment Type: {equipment_type}
- Category: {category}
- Capacity: {capacity}
- Scope: {scope}
- Purpose: {purpose}
{urs_context}

PQ SECTIONS TO COVER (generate 3-6 test cases per applicable section):
1. Commercial Batch Evaluation — Minimum 3 consecutive batches meeting all specifications
2. Batch Yield Evaluation — Yield within specified limits across all batches
3. OEE (Overall Equipment Effectiveness) — Availability, Performance, Quality metrics
4. Process Capability — Cpk ≥ 1.33 for critical process parameters
5. Statistical Analysis — ANOVA, t-test, control charts for critical attributes
6. Repeatability Assessment — Run-to-run consistency, intra-batch variability
7. Reproducibility Assessment — Batch-to-batch variability, operator variability
8. Critical Quality Attribute Verification — All CQAs within specification
9. Critical Process Parameter Monitoring — CPPs controlled within validated range
10. Environmental Monitoring — Temperature, humidity, particles (if applicable)
11. Cleaning Verification — Cleaning effectiveness at commercial scale
12. Operator Qualification — All operators trained, qualified, certified
13. Trend Analysis — Statistical trending of critical parameters
14. Adverse Condition Testing — Performance under worst-case conditions

INSTRUCTIONS:
1. PQ must demonstrate consistent performance under commercial conditions.
2. Minimum 3 consecutive passing batches required.
3. Statistical methods must be scientifically sound (ICH Q8/Q9/Q10).
4. Link test cases to relevant URS requirements.
5. Include specific numeric acceptance criteria with statistical confidence levels.
6. Reference standards: EU GMP Annex 15, ICH Q8/Q9/Q10, WHO GMP, PIC/S.

OUTPUT FORMAT — Return ONLY a JSON array with test_id prefix "PQ-TC-".
"""


def build_ai_review_prompt(qual_info: dict, protocol: dict, test_cases: list[dict]) -> str:
    protocol_type = protocol.get("protocol_type", "IQ")
    equipment_name = qual_info.get("equipment_name", "")
    total = len(test_cases)

    section_counts: dict[str, int] = {}
    pass_count = fail_count = pending_count = 0
    for tc in test_cases:
        s = tc.get("section", "Unknown")
        section_counts[s] = section_counts.get(s, 0) + 1
        st = tc.get("status", "pending")
        if st == "pass":
            pass_count += 1
        elif st == "fail":
            fail_count += 1
        else:
            pending_count += 1

    sections_summary = "\n".join(f"- {s}: {c} test cases" for s, c in section_counts.items())

    return f"""You are a Senior GMP Inspector and Validation Expert conducting a formal {protocol_type} Protocol Review.

PROTOCOL UNDER REVIEW:
- Type: {protocol_type} Protocol
- Equipment: {equipment_name}
- Protocol Number: {protocol.get('protocol_number', '')}
- Revision: {protocol.get('revision', 'A')}
- Status: {protocol.get('status', 'draft')}
- Total Test Cases: {total}
- Pass: {pass_count} | Fail: {fail_count} | Pending: {pending_count}

SECTIONS COVERED:
{sections_summary}

SAMPLE TEST CASES (first 8):
{json.dumps(test_cases[:8], indent=2)}

REVIEW TASKS:
1. COMPLETENESS — Are all required {protocol_type} test areas covered per EU GMP Annex 15?
2. REGULATORY COMPLIANCE — Do test cases reference correct standards?
3. ACCEPTANCE CRITERIA — Are criteria specific, measurable, and scientifically sound?
4. MISSING TESTS — Identify critical tests that are absent.
5. DUPLICATE TESTS — Identify any redundant test cases.
6. RISK COVERAGE — Are high-risk items adequately tested?
7. GMP CRITICALITY — Are GMP-Critical items properly identified?
8. ALCOA+ — For computerized systems, is data integrity covered?
9. Provide COMPLIANCE SCORE (0-100), COMPLETENESS SCORE (0-100), RISK COVERAGE SCORE (0-100).
10. Calculate OVERALL SCORE as weighted average.

OUTPUT FORMAT — Return ONLY a JSON object:
{{
  "compliance_score": 85,
  "completeness_score": 80,
  "risk_coverage_score": 75,
  "overall_score": 80,
  "recommendation": "Approved for Execution | Minor Revisions Required | Major Revisions Required | Not Ready",
  "executive_summary": "3-4 sentence executive summary of the protocol quality.",
  "strengths": ["Strength 1", "Strength 2"],
  "missing_tests": ["Missing critical test 1", "Missing critical test 2"],
  "duplicate_tests": ["Possible duplicate: TC-001 and TC-005 both verify..."],
  "improvements": ["Improvement suggestion 1", "Improvement suggestion 2"],
  "regulatory_gaps": ["Gap 1: Missing reference to EU GMP Annex 15 Section X"]
}}
"""


# ── DOCX Markdown Builder ─────────────────────────────────────────────────────

def build_protocol_markdown(qual: dict, protocol: dict, test_cases: list[dict], executions: list[dict]) -> str:
    ptype = protocol.get("protocol_type", "IQ")
    exec_map = {e["test_case_id"]: e for e in executions}

    lines = []
    lines.append(f"# {ptype} Protocol")
    lines.append(f"## {protocol.get('title', f'{ptype} Protocol')}")
    lines.append("")

    # Header table
    lines.append("**Document Information**")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Protocol Number | {protocol.get('protocol_number', '—')} |")
    lines.append(f"| Revision | {protocol.get('revision', 'A')} |")
    lines.append(f"| Status | {protocol.get('status', 'draft').replace('_',' ').title()} |")
    lines.append(f"| Equipment | {qual.get('equipment_name', '—')} |")
    lines.append(f"| Manufacturer | {qual.get('manufacturer', '—')} |")
    lines.append(f"| Model | {qual.get('model', '—')} |")
    lines.append(f"| Serial Number | {qual.get('serial_number', '—')} |")
    lines.append(f"| Department | {qual.get('department', '—')} |")
    lines.append(f"| Location | {qual.get('location', '—')} |")
    lines.append(f"| Effective Date | {qual.get('effective_date', '—')} |")
    lines.append("")

    lines.append("**Approval**")
    lines.append("")
    lines.append("| Role | Name | Signature | Date |")
    lines.append("|------|------|-----------|------|")
    lines.append(f"| Prepared By | {qual.get('prepared_by', '—')} | | |")
    lines.append(f"| Reviewed By | {qual.get('reviewed_by', '—')} | | |")
    lines.append(f"| Approved By | {qual.get('approved_by', '—')} | | |")
    lines.append("")

    lines.append(f"## 1. Purpose")
    lines.append("")
    lines.append(protocol.get("purpose") or f"To perform the {ptype} of {qual.get('equipment_name','the equipment')} in accordance with GMP requirements.")
    lines.append("")

    lines.append("## 2. Scope")
    lines.append("")
    lines.append(protocol.get("scope") or qual.get("scope") or f"This protocol covers the {ptype} of {qual.get('equipment_name','the equipment')}.")
    lines.append("")

    if protocol.get("responsibilities"):
        lines.append("## 3. Responsibilities")
        lines.append("")
        lines.append(protocol.get("responsibilities"))
        lines.append("")

    if protocol.get("references_text"):
        lines.append("## 4. References")
        lines.append("")
        lines.append(protocol.get("references_text"))
        lines.append("")
    else:
        lines.append("## 4. References")
        lines.append("")
        lines.append("- EU GMP Annex 15 — Qualification and Validation")
        lines.append("- EU GMP Annex 11 — Computerised Systems")
        lines.append("- ISPE GAMP 5 Second Edition")
        lines.append("- ASTM E2500")
        lines.append("- 21 CFR Part 211")
        lines.append("- 21 CFR Part 11")
        lines.append("- WHO GMP Technical Report Series")
        lines.append("- PIC/S GMP Guide")
        lines.append("- ICH Q9 — Quality Risk Management")
        lines.append("- Schedule M (Indian GMP)")
        lines.append("")

    if protocol.get("system_description") or qual.get("system_description"):
        lines.append("## 5. System Description")
        lines.append("")
        lines.append(protocol.get("system_description") or qual.get("system_description", ""))
        lines.append("")

    # Test cases
    lines.append("## 6. Test Cases")
    lines.append("")

    sections: dict[str, list[dict]] = {}
    for tc in test_cases:
        s = tc.get("section", "General")
        if s not in sections:
            sections[s] = []
        sections[s].append(tc)

    section_num = 0
    for section, tcs in sections.items():
        section_num += 1
        lines.append(f"### 6.{section_num} {section}")
        lines.append("")
        for tc in tcs:
            tc_id = tc.get("id")
            exec_data = exec_map.get(tc_id, {})
            result = exec_data.get("result", "pending") if exec_data else "pending"
            result_badge = {"pass": "✅ PASS", "fail": "❌ FAIL", "na": "N/A", "pending": "⏳ PENDING"}.get(result, "⏳ PENDING")

            lines.append(f"#### {tc.get('test_id', 'TC')} — {tc.get('test_name', '')}")
            lines.append("")
            lines.append(f"**GMP Criticality:** {tc.get('gmp_criticality','GMP')} | **Risk Level:** {tc.get('risk_level','Medium')} | **Result:** {result_badge}")
            lines.append("")
            if tc.get("objective"):
                lines.append(f"**Objective:** {tc.get('objective')}")
                lines.append("")
            if tc.get("prerequisites"):
                lines.append(f"**Prerequisites:** {tc.get('prerequisites')}")
                lines.append("")
            lines.append("**Test Procedure:**")
            lines.append("")
            lines.append(tc.get("test_procedure", "Refer to SOP."))
            lines.append("")
            lines.append(f"**Expected Result:** {tc.get('expected_result', '')}")
            lines.append("")
            lines.append(f"**Acceptance Criteria:** {tc.get('acceptance_criteria', '')}")
            lines.append("")
            if tc.get("regulatory_ref"):
                lines.append(f"**Regulatory Reference:** {tc.get('regulatory_ref')}")
                lines.append("")
            urs_ids = tc.get("urs_req_ids", [])
            risk_ids = tc.get("risk_item_ids", [])
            if urs_ids or risk_ids:
                links = []
                if urs_ids:
                    links.append(f"URS: {', '.join(urs_ids)}")
                if risk_ids:
                    links.append(f"Risk: {', '.join(risk_ids)}")
                lines.append(f"**Traceability:** {' | '.join(links)}")
                lines.append("")

            # Execution section
            lines.append("**Execution Record:**")
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            lines.append(f"| Actual Result | {exec_data.get('actual_result', '') if exec_data else ''} |")
            lines.append(f"| Result | {result_badge} |")
            lines.append(f"| Comments | {exec_data.get('comments', '') if exec_data else ''} |")
            lines.append(f"| Executed By | {exec_data.get('executed_by', '') if exec_data else ''} |")
            lines.append(f"| Date | {exec_data.get('executed_date', '') if exec_data else ''} |")
            lines.append(f"| Reviewed By | {exec_data.get('reviewed_by', '') if exec_data else ''} |")
            lines.append(f"| Signature | {exec_data.get('electronic_sig', '') if exec_data else ''} |")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Summary
    total = len(test_cases)
    pass_c = sum(1 for tc in test_cases if tc.get("status") == "pass")
    fail_c = sum(1 for tc in test_cases if tc.get("status") == "fail")
    na_c   = sum(1 for tc in test_cases if tc.get("status") == "na")
    pend_c = total - pass_c - fail_c - na_c

    lines.append("## 7. Summary")
    lines.append("")
    lines.append(protocol.get("summary") or f"This {ptype} protocol has been executed for {qual.get('equipment_name','the equipment')}.")
    lines.append("")
    lines.append("**Execution Summary:**")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Test Cases | {total} |")
    lines.append(f"| Pass | {pass_c} |")
    lines.append(f"| Fail | {fail_c} |")
    lines.append(f"| N/A | {na_c} |")
    lines.append(f"| Pending | {pend_c} |")
    lines.append(f"| Pass Rate | {round(pass_c/total*100) if total else 0}% |")
    lines.append("")

    if protocol.get("conclusion"):
        lines.append("## 8. Conclusion")
        lines.append("")
        lines.append(protocol.get("conclusion"))
        lines.append("")

    lines.append("## 9. Regulatory Framework")
    lines.append("")
    lines.append(f"This {ptype} protocol has been prepared in accordance with:")
    lines.append("")
    lines.append("- EU GMP Annex 15 (Qualification and Validation)")
    lines.append("- EU GMP Annex 11 (Computerised Systems)")
    lines.append("- ISPE GAMP 5 Second Edition")
    lines.append("- ASTM E2500 — Specification, Design, Verification, and Validation of Pharmaceutical and Biopharmaceutical Manufacturing Systems and Equipment")
    lines.append("- 21 CFR Part 211 — Current Good Manufacturing Practice for Finished Pharmaceuticals")
    lines.append("- 21 CFR Part 11 — Electronic Records; Electronic Signatures")
    lines.append("- WHO GMP Technical Report Series No. 992, Annex 3")
    lines.append("- PIC/S GMP Guide")
    lines.append("- Schedule M — Good Manufacturing Practices for Premises and Materials")
    lines.append("- ICH Q9 — Quality Risk Management")
    lines.append("- ALCOA+ Data Integrity Principles")
    lines.append("")

    lines.append("---")
    lines.append(f"*Document generated by PharmaGPT Qualification Management Suite*")
    lines.append(f"*The Lean Architect Technologies*")

    return "\n".join(lines)


def build_traceability_markdown(matrix: dict, urs_reqs: list[dict], risk_items: list[dict]) -> str:
    """Build a professional Traceability Matrix markdown for DOCX export."""
    lines = []
    lines.append("# Qualification Traceability Matrix")
    lines.append(f"## {matrix.get('equipment_name', 'Equipment')} — {matrix.get('qual_number', '')}")
    lines.append("")
    lines.append("*Auto-generated from URS Requirements, Risk Assessments, and Qualification Test Cases*")
    lines.append("")

    # URS coverage
    lines.append("## 1. URS Requirement → Test Case Coverage")
    lines.append("")
    lines.append("| URS Req ID | Requirement | Test Cases | Status |")
    lines.append("|-----------|-------------|-----------|--------|")
    urs_map = {r.get("req_id", ""): r for r in urs_reqs}
    urs_coverage = matrix.get("urs_coverage", {})
    for uid, tcs in urs_coverage.items():
        req = urs_map.get(uid, {})
        req_text = req.get("requirement", "")[:80] if req else uid
        tc_str = ", ".join(tcs)
        lines.append(f"| {uid} | {req_text} | {tc_str} | ✅ Covered |")
    # Uncovered URS
    for req in urs_reqs:
        rid = req.get("req_id", "")
        if rid and rid not in urs_coverage:
            req_text = req.get("requirement", "")[:80]
            lines.append(f"| {rid} | {req_text} | — | ⚠️ Not Covered |")
    lines.append("")

    # Risk coverage
    if risk_items:
        lines.append("## 2. Risk Item → Test Case Coverage")
        lines.append("")
        lines.append("| Risk ID | Risk / Failure Mode | Test Cases | Status |")
        lines.append("|---------|---------------------|-----------|--------|")
        risk_map = {str(r.get("id", "")): r for r in risk_items}
        risk_coverage = matrix.get("risk_coverage", {})
        for rid, tcs in risk_coverage.items():
            risk = risk_map.get(rid, {})
            risk_text = risk.get("failure_mode", risk.get("hazard", rid))[:80]
            tc_str = ", ".join(tcs)
            lines.append(f"| {rid} | {risk_text} | {tc_str} | ✅ Covered |")
        lines.append("")

    # Test case → URS/Risk
    lines.append("## 3. Test Case → URS / Risk Traceability")
    lines.append("")
    lines.append("| Test ID | Test Name | Section | URS Req IDs | Risk IDs | Status |")
    lines.append("|---------|-----------|---------|-------------|----------|--------|")
    for row in matrix.get("matrix_rows", []):
        urs_str  = ", ".join(row.get("urs_req_ids", []))  or "—"
        risk_str = ", ".join(row.get("risk_item_ids", [])) or "—"
        status_icon = {"pass": "✅", "fail": "❌", "na": "N/A", "pending": "⏳"}.get(row.get("status","pending"), "⏳")
        lines.append(f"| {row.get('test_id','')} | {row.get('test_name','')[:60]} | {row.get('section','')} | {urs_str} | {risk_str} | {status_icon} {row.get('status','pending').upper()} |")
    lines.append("")

    # Coverage statistics
    total_urs   = len(urs_reqs)
    covered_urs = len(urs_coverage)
    total_risk  = len(risk_items)
    covered_risk = len(matrix.get("risk_coverage", {}))
    lines.append("## 4. Coverage Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Test Cases | {matrix.get('total_tests', 0)} |")
    lines.append(f"| URS Requirements Total | {total_urs} |")
    lines.append(f"| URS Requirements Covered | {covered_urs} |")
    lines.append(f"| URS Coverage % | {round(covered_urs/total_urs*100) if total_urs else 0}% |")
    lines.append(f"| Risk Items Total | {total_risk} |")
    lines.append(f"| Risk Items Covered | {covered_risk} |")
    lines.append(f"| Risk Coverage % | {round(covered_risk/total_risk*100) if total_risk else 0}% |")
    lines.append("")

    lines.append("---")
    lines.append("*Auto-generated Traceability Matrix — PharmaGPT Qualification Management Suite*")
    return "\n".join(lines)

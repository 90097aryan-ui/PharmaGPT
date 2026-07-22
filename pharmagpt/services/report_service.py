"""
report_service.py — Business logic and AI prompts for the Validation Report Management Suite.

Responsibilities
----------------
1. Aggregate data from Qualification, URS, and Risk modules.
2. Build comprehensive AI prompts for report generation.
3. Build AI review prompts for compliance scoring.
4. Build traceability summary from qualification data.
5. DOCX export context builder.
"""

from __future__ import annotations


# ── Data Aggregation ──────────────────────────────────────────────────────────

def aggregate_report_context(
    report: dict,
    qual: dict | None,
    protocols: list[dict],
    test_cases_by_protocol: dict,
    executions_by_protocol: dict,
    deviations: list[dict],
    urs_project: dict | None,
    urs_requirements: list[dict],
    risk_assessment: dict | None,
    risk_items: list[dict],
) -> dict:
    """Aggregate all module data into a unified context dict for AI generation."""

    # Execution totals
    total_tests = pass_count = fail_count = na_count = 0
    for pid, tcs in test_cases_by_protocol.items():
        for tc in tcs:
            total_tests += 1
            s = tc.get("status", "pending")
            if s == "pass":
                pass_count += 1
            elif s == "fail":
                fail_count += 1
            elif s == "na":
                na_count += 1

    pending_count = total_tests - pass_count - fail_count - na_count
    pass_rate = round(pass_count / total_tests * 100, 1) if total_tests else 0

    # Protocol summaries
    iq_proto = next((p for p in protocols if p.get("protocol_type") == "IQ"), None)
    oq_proto = next((p for p in protocols if p.get("protocol_type") == "OQ"), None)
    pq_proto = next((p for p in protocols if p.get("protocol_type") == "PQ"), None)

    def proto_stats(proto):
        if not proto:
            return None
        pid = proto["id"]
        tcs = test_cases_by_protocol.get(pid, [])
        p = sum(1 for t in tcs if t.get("status") == "pass")
        f = sum(1 for t in tcs if t.get("status") == "fail")
        n = sum(1 for t in tcs if t.get("status") == "na")
        total = len(tcs)
        return {
            "protocol_number": proto.get("protocol_number", ""),
            "title": proto.get("title", ""),
            "status": proto.get("status", ""),
            "total": total,
            "pass": p,
            "fail": f,
            "na": n,
            "pending": total - p - f - n,
            "pass_rate": round(p / total * 100, 1) if total else 0,
            "conclusion": proto.get("conclusion", ""),
            "summary": proto.get("summary", ""),
            "deviation_count": proto.get("deviation_count", 0),
        }

    # Risk summary
    critical_risks = [r for r in risk_items if r.get("risk_level") in ("Critical", "High") or (r.get("rpn") or 0) >= 100]
    open_risks = [r for r in risk_items if r.get("status", "").lower() in ("open", "in_progress")]

    # URS coverage
    total_reqs = len(urs_requirements)
    critical_reqs = [r for r in urs_requirements if r.get("gmp_criticality", "").upper() == "GMP" or r.get("priority", "") == "High"]

    # Deviations
    open_devs = [d for d in deviations if d.get("status") == "open"]
    closed_devs = [d for d in deviations if d.get("status") == "closed"]
    critical_devs = [d for d in deviations if d.get("impact") in ("Critical", "Major")]

    return {
        "report": report,
        "qual": qual,
        "equipment_name": report.get("equipment_name") or (qual.get("equipment_name") if qual else ""),
        "equipment_type": report.get("equipment_type") or (qual.get("equipment_type") if qual else ""),
        "manufacturer": report.get("manufacturer") or (qual.get("manufacturer") if qual else ""),
        "model": report.get("model") or (qual.get("model") if qual else ""),
        "serial_number": report.get("serial_number") or (qual.get("serial_number") if qual else ""),
        "department": report.get("department") or (qual.get("department") if qual else ""),
        "site": report.get("site") or (qual.get("site") if qual else ""),
        "location": report.get("location") or (qual.get("location") if qual else ""),
        "validation_type": report.get("validation_type", "IQ/OQ/PQ"),
        "scope": report.get("scope") or (qual.get("scope") if qual else ""),
        "purpose": report.get("purpose") or (qual.get("purpose") if qual else ""),
        "system_description": (qual.get("system_description") if qual else "") or "",
        "protocols": protocols,
        "iq_proto": proto_stats(iq_proto),
        "oq_proto": proto_stats(oq_proto),
        "pq_proto": proto_stats(pq_proto),
        "total_tests": total_tests,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "na_count": na_count,
        "pending_count": pending_count,
        "pass_rate": pass_rate,
        "deviations": deviations,
        "open_deviations": open_devs,
        "closed_deviations": closed_devs,
        "critical_deviations": critical_devs,
        "total_deviations": len(deviations),
        "urs_project": urs_project,
        "urs_requirements": urs_requirements,
        "total_reqs": total_reqs,
        "critical_reqs": critical_reqs,
        "risk_assessment": risk_assessment,
        "risk_items": risk_items,
        "critical_risks": critical_risks,
        "open_risks": open_risks,
        "total_risks": len(risk_items),
    }


# ── Section Generation Prompts ────────────────────────────────────────────────

def build_section_prompt(section_key: str, ctx: dict) -> str:
    """Build an AI prompt for a specific report section."""

    eq = ctx.get("equipment_name", "the equipment")
    eq_type = ctx.get("equipment_type", "")
    mfr = ctx.get("manufacturer", "")
    model = ctx.get("model", "")
    serial = ctx.get("serial_number", "")
    dept = ctx.get("department", "")
    site = ctx.get("site", "")
    loc = ctx.get("location", "")
    scope = ctx.get("scope", "")
    purpose = ctx.get("purpose", "")
    system_desc = ctx.get("system_description", "")
    val_type = ctx.get("validation_type", "IQ/OQ/PQ")
    report = ctx.get("report", {})

    iq = ctx.get("iq_proto")
    oq = ctx.get("oq_proto")
    pq = ctx.get("pq_proto")

    total_tests = ctx.get("total_tests", 0)
    pass_count = ctx.get("pass_count", 0)
    fail_count = ctx.get("fail_count", 0)
    pass_rate = ctx.get("pass_rate", 0)
    total_devs = ctx.get("total_deviations", 0)
    open_devs = len(ctx.get("open_deviations", []))
    closed_devs = len(ctx.get("closed_deviations", []))
    critical_devs = len(ctx.get("critical_deviations", []))

    total_reqs = ctx.get("total_reqs", 0)
    total_risks = ctx.get("total_risks", 0)
    critical_risks = len(ctx.get("critical_risks", []))
    open_risks = len(ctx.get("open_risks", []))

    urs = ctx.get("urs_project")
    risk = ctx.get("risk_assessment")
    deviations = ctx.get("deviations", [])
    urs_reqs = ctx.get("urs_requirements", [])
    risk_items = ctx.get("risk_items", [])

    # Summarize protocol data for prompt
    iq_txt = f"IQ: {iq['total']} tests, {iq['pass']} passed ({iq['pass_rate']}%), {iq['fail']} failed, Status: {iq['status']}" if iq else "IQ: Not executed"
    oq_txt = f"OQ: {oq['total']} tests, {oq['pass']} passed ({oq['pass_rate']}%), {oq['fail']} failed, Status: {oq['status']}" if oq else "OQ: Not executed"
    pq_txt = f"PQ: {pq['total']} tests, {pq['pass']} passed ({pq['pass_rate']}%), {pq['fail']} failed, Status: {pq['status']}" if pq else "PQ: Not executed"

    urs_sample = ""
    for r in urs_reqs[:15]:
        urs_sample += f"  - {r.get('req_id','')}: {r.get('requirement','')[:100]}\n"

    risk_sample = ""
    for r in risk_items[:15]:
        risk_sample += f"  - {r.get('item_id', r.get('id',''))}: {r.get('failure_mode', r.get('hazard',''))[:100]} | RPN: {r.get('rpn', r.get('risk_level',''))}\n"

    dev_sample = ""
    for d in deviations[:10]:
        dev_sample += f"  - {d.get('deviation_number','')}: {d.get('title','')[:80]} | Impact: {d.get('impact','')} | Status: {d.get('status','')}\n"

    base_context = f"""
VALIDATION REPORT CONTEXT:
─────────────────────────
Report Number: {report.get('report_number','')}
Report Type: {report.get('report_type','Validation Report')}
Revision: {report.get('revision','A')}

EQUIPMENT DETAILS:
Equipment Name: {eq}
Equipment Type: {eq_type}
Manufacturer: {mfr}
Model: {model}
Serial Number: {serial}
Department: {dept}
Site: {site}
Location: {loc}
Validation Type: {val_type}
Scope: {scope}
Purpose: {purpose}
System Description: {system_desc}

EXECUTION SUMMARY:
Total Tests: {total_tests}
Passed: {pass_count} ({pass_rate}%)
Failed: {fail_count}
N/A: {ctx.get('na_count',0)}
{iq_txt}
{oq_txt}
{pq_txt}

URS: {urs.get('urs_number','N/A') if urs else 'N/A'} — {total_reqs} requirements
{urs_sample}

RISK ASSESSMENT: {risk.get('title','N/A') if risk else 'N/A'} — {total_risks} risk items, {critical_risks} critical
{risk_sample}

DEVIATIONS: {total_devs} total, {open_devs} open, {critical_devs} critical
{dev_sample}
"""

    prompts = {
        "executive_summary": f"""You are a Senior Pharmaceutical Validation Expert and QA Director writing a GMP-compliant Validation Report.

Generate a professional EXECUTIVE SUMMARY for the Validation Report.

{base_context}

The Executive Summary should:
1. Open with a one-paragraph overview of the validation activity and its regulatory basis (EU GMP Annex 15, GAMP 5, 21 CFR Part 11 as applicable)
2. State the validation objective and scope clearly
3. Summarize the equipment/system being qualified
4. State whether IQ, OQ, and PQ were completed and their outcomes
5. Mention total test count, pass rate, and any deviations
6. Reference the URS and Risk Assessment compliance
7. State the overall validation conclusion (validated / conditionally validated / not validated)
8. Include a final statement of fitness for intended use
9. Note any outstanding actions or conditions

Write in formal pharmaceutical validation language suitable for QA Director review and regulatory inspection.
Use professional paragraph format (no bullet points in the executive summary).
Length: 350-500 words.""",

        "purpose": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the PURPOSE section of the Validation Report.

{base_context}

The Purpose section should:
1. State the primary purpose of this validation report
2. Reference applicable regulatory standards (EU GMP Annex 15, GAMP 5, 21 CFR Part 11, WHO GMP, ASTM E2500 as relevant)
3. State what the report documents and demonstrates
4. Reference the regulatory requirement for maintaining such a validation report
5. State the intended audience (QA, regulatory inspectors, management)

Write in concise, formal GMP language. 3-4 paragraphs maximum.""",

        "scope": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the SCOPE section of the Validation Report.

{base_context}

The Scope section should:
1. Define what is included in this validation effort
2. Specify the equipment/system being qualified
3. List which qualification activities are covered (IQ/OQ/PQ)
4. State location/department scope
5. Define what is explicitly excluded from scope
6. Reference applicable URS and Risk Assessment documents

Write in formal GMP language. Use structured paragraphs with clear inclusions and exclusions.""",

        "responsibilities": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the RESPONSIBILITIES section of the Validation Report.

{base_context}

The Responsibilities section should define clear roles for:
1. Validation Engineer / Author — Report preparation, data compilation
2. Quality Assurance (QA) — Protocol approval, execution oversight, report review and approval
3. Equipment Owner / Department Head — Protocol execution, user requirements sign-off
4. Engineering / Maintenance — IQ execution support, utility connections
5. Regulatory Affairs — Regulatory compliance assessment
6. Management Representative — Final approval authority

Format as a structured table or numbered list with Role | Responsibility | Involvement columns.""",

        "applicable_standards": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the APPLICABLE STANDARDS AND REGULATORY REFERENCES section.

{base_context}

Include references to ALL applicable standards:
- EU GMP Annex 15 (Qualification and Validation)
- EU GMP Annex 11 (if computerized system)
- ISPE GAMP 5 Second Edition (if computerized system)
- ASTM E2500 (Specification, Design and Verification)
- 21 CFR Part 11 (if computerized/electronic records)
- WHO Technical Report Series on Qualification
- PIC/S PE 009 (GMP Guide)
- Schedule M (Revised) (if Indian context)
- ICH Q9 (Quality Risk Management)
- ICH Q10 (Pharmaceutical Quality System)
- ALCOA+ data integrity principles

For each standard, provide the document name, edition/version, and relevance to this validation.
Format as a structured table: Standard | Edition | Relevance.""",

        "equipment_details": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the EQUIPMENT DETAILS section.

{base_context}

The Equipment Details section should include:
1. Equipment identification table with all key identifiers
2. Physical description and technical specifications
3. Installed location and environmental requirements
4. Utility requirements (electrical, compressed air, water, etc.)
5. Critical components and sub-systems
6. Instrumentation and control systems
7. Connected systems and interfaces
8. Calibration requirements

Format as a professional technical section with equipment identification table followed by descriptive paragraphs.""",

        "system_description": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the SYSTEM DESCRIPTION section.

{base_context}

The System Description should provide:
1. A comprehensive technical description of the equipment/system
2. Operating principle and process description
3. Critical process parameters (CPPs) and their ranges
4. Critical quality attributes (CQAs) affected
5. Control system description (if computerized)
6. Safety systems and interlocks
7. Cleaning/sterilization requirements (if applicable)
8. GMP classification of the system

Write as a thorough technical narrative suitable for a validation report.""",

        "validation_strategy": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the VALIDATION STRATEGY section.

{base_context}

The Validation Strategy section should explain:
1. The overall qualification approach (prospective/concurrent/retrospective)
2. Risk-based approach per ICH Q9 and EU GMP Annex 15
3. Qualification phases selected (DQ/IQ/OQ/PQ) and rationale for each
4. GAMP 5 software category (if computerized system)
5. Testing strategy (worst-case, bracketing, matrixing as applicable)
6. Statistical acceptance criteria basis
7. Requalification triggers and frequency
8. Validation lifecycle and continued verification approach

Reference specific regulatory guidance for each strategic decision.""",

        "urs_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the URS (User Requirement Specification) SUMMARY section.

{base_context}

URS Document: {urs.get('urs_number','') if urs else ''} — {urs.get('title','') if urs else 'Not linked'}
Total Requirements: {total_reqs}

The URS Summary should:
1. Reference the URS document number and revision
2. Summarize the key categories of requirements
3. State the total number of requirements by category/section
4. Highlight critical GMP requirements
5. Confirm that all URS requirements have been addressed in the qualification protocols
6. State the URS approval status
7. Reference any URS changes during the project

Write as a formal section confirming URS coverage. Include a brief requirement category table if multiple sections exist.""",

        "risk_assessment_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the RISK ASSESSMENT SUMMARY section.

{base_context}

Risk Assessment: {risk.get('title','') if risk else 'Not linked'} — Methodology: {risk.get('methodology','FMEA') if risk else 'FMEA'}
Total Risk Items: {total_risks} | Critical/High: {critical_risks} | Open: {open_risks}

The Risk Assessment Summary should:
1. Reference the risk assessment document number and methodology used (FMEA/ICH Q9)
2. Summarize the risk identification approach
3. State the total number of risks identified by severity level
4. Describe the critical/high risks and their mitigations
5. Confirm all critical risks are covered by qualification testing
6. State residual risk acceptance
7. Risk re-evaluation post-qualification outcome

Format with a risk level summary table and descriptive paragraphs.""",

        "iq_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the INSTALLATION QUALIFICATION (IQ) SUMMARY section.

{base_context}

IQ Protocol Data: {iq_txt}
{f"Protocol Number: {iq['protocol_number']}" if iq else ""}
{f"Conclusion: {iq['conclusion']}" if iq else ""}

The IQ Summary should:
1. State the IQ Protocol reference number and revision
2. Summarize what was verified during IQ (documents, utilities, components, instruments, safety)
3. State total test count, pass/fail breakdown, and pass rate
4. Describe any deviations encountered during IQ
5. State the IQ conclusion: PASS / FAIL / CONDITIONAL PASS
6. List any outstanding actions from IQ
7. State the basis for proceeding to OQ (if applicable)

Write a comprehensive section demonstrating IQ execution evidence.""",

        "oq_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the OPERATIONAL QUALIFICATION (OQ) SUMMARY section.

{base_context}

OQ Protocol Data: {oq_txt}
{f"Protocol Number: {oq['protocol_number']}" if oq else ""}
{f"Conclusion: {oq['conclusion']}" if oq else ""}

The OQ Summary should:
1. State the OQ Protocol reference number and revision
2. Summarize what was tested during OQ (operational limits, alarms, interlocks, functions)
3. State total test count, pass/fail breakdown, and pass rate
4. Describe any deviations encountered during OQ
5. State the OQ conclusion: PASS / FAIL / CONDITIONAL PASS
6. List any outstanding actions from OQ
7. State the basis for proceeding to PQ (if applicable)

Demonstrate that the equipment operates correctly across its operational range.""",

        "pq_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the PERFORMANCE QUALIFICATION (PQ) SUMMARY section.

{base_context}

PQ Protocol Data: {pq_txt}
{f"Protocol Number: {pq['protocol_number']}" if pq else ""}
{f"Conclusion: {pq['conclusion']}" if pq else ""}

The PQ Summary should:
1. State the PQ Protocol reference number and revision
2. Summarize what was demonstrated during PQ (process performance, reproducibility, robustness)
3. State total test count, pass/fail breakdown, and pass rate
4. Describe statistical analysis performed (if applicable)
5. Describe any deviations encountered during PQ
6. State the PQ conclusion: PASS / FAIL / CONDITIONAL PASS
7. List any outstanding actions from PQ

Demonstrate that the equipment performs consistently at production conditions.""",

        "execution_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the EXECUTION SUMMARY section with quantitative data.

{base_context}

Create a comprehensive execution summary including:
1. Overall execution timeline (planned vs actual dates)
2. Summary execution table (Phase | Protocol | Total Tests | Passed | Failed | N/A | Pass Rate | Status)
3. Overall test statistics (totals across all phases)
4. Execution team composition
5. Deviations summary table (Number | Title | Phase | Impact | Status)
6. Equipment/utilities encountered during execution
7. Data integrity confirmations (ALCOA+)

Use formal pharmaceutical language. Include specific numbers from the data provided.""",

        "deviation_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the DEVIATION SUMMARY section.

{base_context}

Total Deviations: {total_devs} | Open: {open_devs} | Closed: {closed_devs} | Critical: {critical_devs}

Detailed Deviations:
{dev_sample}

The Deviation Summary should:
1. State the total number of deviations raised
2. Classify deviations by impact (Critical/Major/Minor)
3. Provide a deviation table with all deviations listed
4. Describe each significant deviation and its resolution
5. Confirm all deviations are addressed before validation conclusion
6. State any impact on validation acceptance
7. Confirm CAPA actions raised where required

If no deviations: state explicitly that no deviations were encountered.""",

        "traceability_summary": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the TRACEABILITY SUMMARY section.

{base_context}

The Traceability Summary should:
1. State the purpose of traceability in pharmaceutical validation
2. Confirm that all URS requirements are traced to qualification test cases
3. Confirm that all critical risk items are addressed by test cases
4. Provide a high-level traceability matrix summary table
5. State the coverage percentages (URS coverage, Risk coverage)
6. Identify any uncovered requirements or risks (if any)
7. State the regulatory basis for traceability (Annex 15, GAMP 5)

Include a traceability matrix summary table structure.""",

        "critical_findings": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the CRITICAL FINDINGS section.

{base_context}

The Critical Findings section should:
1. List all critical/significant findings from the validation activities
2. Classify each finding (IQ/OQ/PQ | Category | Impact | Status)
3. Describe root cause analysis for each critical finding
4. State the corrective action taken and its effectiveness
5. State whether each finding affected the validation conclusion
6. Confirm resolution and closure of all critical findings

If no critical findings: state explicitly — "No critical findings were identified during validation."

Be objective, factual, and GMP-compliant in language.""",

        "risk_evaluation": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the RISK EVALUATION section (post-validation).

{base_context}

The Risk Evaluation section should:
1. Compare initial risk assessment vs post-validation residual risk
2. Confirm which risks were mitigated through qualification testing
3. State residual risk levels after successful qualification
4. Reference the initial RPN/risk scores and post-mitigation values
5. State any risks that remain acceptable without further mitigation
6. Identify any new risks identified during qualification
7. State the overall risk acceptance decision per ICH Q9

Reference specific risk methodology (FMEA/HACCP) and scoring criteria used.""",

        "compliance_assessment": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the OVERALL COMPLIANCE ASSESSMENT section.

{base_context}

The Compliance Assessment should evaluate compliance against:
1. EU GMP Annex 15 — qualification and validation requirements
2. EU GMP Annex 11 — computerised systems (if applicable)
3. 21 CFR Part 11 — electronic records (if applicable)
4. GAMP 5 — software validation (if applicable)
5. ICH Q9 — quality risk management approach
6. ICH Q10 — pharmaceutical quality system
7. WHO GMP — qualification requirements
8. ALCOA+ — data integrity principles

For each standard: State requirement | Evidence | Compliance Status (Compliant/Not Applicable/Gap)
Conclude with an overall compliance statement.""",

        "conclusion": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the CONCLUSION section.

{base_context}

The Conclusion should:
1. State the overall validation conclusion (VALIDATED / CONDITIONALLY VALIDATED / NOT VALIDATED)
2. Summarize the evidence base for the conclusion
3. State that all qualification phases were completed satisfactorily (or note conditions)
4. Confirm that the equipment meets all URS requirements
5. Confirm that all critical risks have been mitigated
6. Confirm that the equipment is suitable for its intended use in GMP manufacturing
7. State any conditions or limitations on the validated state
8. Reference regulatory standards confirming compliance

Write a formal, declarative conclusion paragraph followed by a numbered summary of key conclusions.""",

        "recommendations": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the RECOMMENDATIONS section.

{base_context}

The Recommendations section should include:
1. Any conditional recommendations before equipment can be released for production use
2. Recommended requalification frequency and triggers
3. Recommended ongoing monitoring and control strategy
4. Recommendations for additional training required
5. Recommendations for SOPs to be approved before use
6. Recommended periodic review schedule
7. Change control requirements for the validated state
8. Any CAPA actions required to be completed

Format as a numbered list with owner assignments and target completion dates where applicable.""",

        "final_statement": f"""You are a Senior Pharmaceutical Validation Expert and QA Director writing a GMP-compliant Validation Report.

Generate the FINAL VALIDATION STATEMENT — the formal declaration that certifies the validation outcome.

{base_context}

The Final Validation Statement must be a formal, legally-worded declaration that:
1. States the equipment name, ID, and validation type
2. Declares that all qualification activities have been completed
3. States the validation outcome formally
4. Declares fitness for intended use in GMP pharmaceutical manufacturing
5. States the validated operating parameters/conditions
6. Declares compliance with applicable regulatory standards
7. States the effective date of the validated state
8. Notes that requalification will be performed if defined criteria are met
9. This statement serves as formal QA release for production use

Write as a formal GMP declaration. Solemn, precise, unambiguous language.
This is a legally binding pharmaceutical quality document.""",

        "annexures": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the ANNEXURES section index.

{base_context}

The Annexures section should list all supporting documents and evidence, organized as:

Annexure A: URS Document (reference and summary)
Annexure B: Risk Assessment (reference and summary)
Annexure C: IQ Protocol and Execution Records
Annexure D: OQ Protocol and Execution Records
Annexure E: PQ Protocol and Execution Records
Annexure F: Calibration Certificates
Annexure G: Vendor Documentation (manuals, certificates)
Annexure H: Deviation Reports
Annexure I: Traceability Matrix
Annexure J: Approval Signatures

For each annexure, state: reference number, document title, document number, revision, and date.
Note: "Copies are maintained in the Validation Master File."
""",
        "cover_page": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate content for the COVER PAGE of the Validation Report.

{base_context}

The cover page content should be formatted as a structured document header with these elements clearly defined:
- Company Name: The Lean Architect Technologies
- Product Name: PharmaGPT
- Document Title: {report.get('report_type','Validation Report')}
- Document Number: {report.get('report_number','')}
- Equipment: {eq}
- Department: {dept}
- Site / Location: {site} / {loc}
- Validation Type: {val_type}
- Revision: {report.get('revision','A')}
- Status: {report.get('status','Draft').upper()}
- Prepared By: {report.get('prepared_by','')}
- Reviewed By: {report.get('reviewed_by','')}
- Approved By: {report.get('approved_by','')}
- Effective Date: {report.get('effective_date','')}
- Report Date: {report.get('report_date','')}
- Regulatory Standards: EU GMP Annex 15 | GAMP 5 | 21 CFR Part 11 | WHO GMP

Format this as a document cover block that would appear on the first page of a printed pharmaceutical validation report.
Include a confidentiality statement and property of company statement.""",

        "approval_page": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the APPROVAL PAGE for the Validation Report.

{base_context}

The Approval Page must include a formal signature table for GMP document approval:

Document Number: {report.get('report_number','')}
Document Title: {report.get('report_type','Validation Report')} — {eq}
Revision: {report.get('revision','A')}

Signature Table should include these roles:
1. Prepared By — Validation Engineer/Author
2. Reviewed By — Validation Manager / Senior Validation Engineer
3. Reviewed By — Quality Assurance Representative
4. Approved By — QA Manager / QA Director
5. Authorized By — Department Head / Site Director (for regulatory release)

For each: Role | Name | Signature | Date | Comments

Include a revision history summary table:
Revision | Date | Author | Description of Changes | QA Approval

Add a GMP compliance statement confirming this document was prepared and approved per applicable GMP standards.""",

        "revision_history": f"""You are a Senior Pharmaceutical Validation Expert writing a GMP-compliant Validation Report.

Generate the REVISION HISTORY section.

{base_context}

Create a formal revision history table for this validation report:

Current Version: {report.get('version','v1.0')}
Revision: {report.get('revision','A')}
Status: {report.get('status','Draft')}

Format:
| Revision | Version | Date | Author | Description of Change | QA Approval |
|----------|---------|------|--------|----------------------|-------------|
| A | v1.0 | {report.get('created_at','')[:10]} | {report.get('prepared_by','[Author]')} | Initial Issue | Pending |

Include a note: "All revisions require QA review and approval prior to implementation."
Include a note: "Superseded revisions are archived in the Validation Master File."
""",
    }

    return prompts.get(section_key, f"Generate content for the '{section_key}' section of this Validation Report:\n{base_context}")


# ── Full Report Generation Prompt ─────────────────────────────────────────────

def build_full_generation_prompt(section_key: str, ctx: dict) -> str:
    """Returns the specific section prompt for streaming generation."""
    return build_section_prompt(section_key, ctx)


# ── AI Review Prompt ──────────────────────────────────────────────────────────

def build_review_prompt(report: dict, sections: list[dict], ctx: dict) -> str:
    """Build comprehensive AI review prompt for the complete validation report."""

    sections_summary = ""
    filled_sections = []
    empty_sections = []
    for s in sections:
        content = s.get("content", "").strip()
        if len(content) > 50:
            filled_sections.append(s["section_title"])
            sections_summary += f"\n### {s['section_title']}\n{content[:300]}...\n"
        else:
            empty_sections.append(s["section_title"])

    eq = ctx.get("equipment_name", "")
    pass_rate = ctx.get("pass_rate", 0)
    total_tests = ctx.get("total_tests", 0)
    total_devs = ctx.get("total_deviations", 0)
    open_devs = len(ctx.get("open_deviations", []))
    total_reqs = ctx.get("total_reqs", 0)
    total_risks = ctx.get("total_risks", 0)

    return f"""You are a Senior QA Director and Pharmaceutical Validation Expert conducting a formal GMP compliance review of a Validation Report.

Review this Validation Report and provide a comprehensive quality assessment.

REPORT METADATA:
Equipment: {eq}
Validation Type: {report.get('validation_type','IQ/OQ/PQ')}
Status: {report.get('status','')}
Revision: {report.get('revision','A')}

EXECUTION DATA:
Total Tests: {total_tests}
Pass Rate: {pass_rate}%
Total Deviations: {total_devs} ({open_devs} open)
URS Requirements: {total_reqs}
Risk Items: {total_risks}

COMPLETED SECTIONS ({len(filled_sections)}):
{', '.join(filled_sections)}

MISSING/EMPTY SECTIONS ({len(empty_sections)}):
{', '.join(empty_sections)}

SECTION CONTENT SAMPLES:
{sections_summary[:3000]}

Review against:
1. EU GMP Annex 15 requirements for validation reports
2. GAMP 5 documentation requirements
3. 21 CFR Part 11 (if applicable)
4. ALCOA+ data integrity principles
5. ICH Q9 risk management documentation
6. WHO GMP validation requirements

Provide your review as JSON with this EXACT structure:
{{
  "compliance_score": <0-100>,
  "completeness_score": <0-100>,
  "readiness_score": <0-100>,
  "overall_score": <0-100>,
  "recommendation": "<READY FOR QA APPROVAL | MINOR REVISIONS REQUIRED | MAJOR REVISIONS REQUIRED | NOT READY>",
  "executive_summary": "<3-5 sentence review summary>",
  "strengths": ["<strength 1>", "<strength 2>", ...],
  "missing_sections": ["<missing section name>", ...],
  "missing_evidence": ["<missing evidence item>", ...],
  "regulatory_gaps": ["<gap description>", ...],
  "data_integrity_issues": ["<issue description>", ...],
  "improvements": ["<specific improvement>", ...],
  "reviewer_comments": [
    {{"section": "<section name>", "comment": "<specific comment>", "severity": "<Critical|Major|Minor>"}},
    ...
  ]
}}

Be rigorous. A pharmaceutical validation report must meet the highest GMP standards.
Score conservatively — only award high scores when evidence is comprehensive and complete.
Return ONLY valid JSON, no markdown code blocks."""


# ── Traceability Summary Builder ──────────────────────────────────────────────

def build_traceability_summary(
    urs_requirements: list[dict],
    risk_items: list[dict],
    test_cases_all: list[dict],
) -> dict:
    """Build a traceability summary linking URS → Risk → Test Cases → Outcome."""

    req_map: dict = {}
    for req in urs_requirements:
        req_id = str(req.get("id", ""))
        req_map[req_id] = {
            "req_id": req.get("req_id", req_id),
            "requirement": req.get("requirement", "")[:120],
            "priority": req.get("priority", ""),
            "gmp_criticality": req.get("gmp_criticality", ""),
            "test_cases": [],
            "covered": False,
        }

    risk_map: dict = {}
    for ri in risk_items:
        risk_id = str(ri.get("id", ""))
        risk_map[risk_id] = {
            "item_id": ri.get("item_id", risk_id),
            "failure_mode": ri.get("failure_mode", ri.get("hazard", ""))[:100],
            "risk_level": ri.get("risk_level", ""),
            "rpn": ri.get("rpn", ""),
            "test_cases": [],
            "covered": False,
        }

    tc_rows: list[dict] = []
    for tc in test_cases_all:
        urs_ids = tc.get("urs_req_ids", [])
        risk_ids = tc.get("risk_item_ids", [])
        tc_entry = {
            "test_id": tc.get("test_id", ""),
            "test_name": tc.get("test_name", ""),
            "protocol_type": tc.get("protocol_type", ""),
            "status": tc.get("status", "pending"),
            "urs_req_ids": urs_ids,
            "risk_item_ids": risk_ids,
        }
        tc_rows.append(tc_entry)
        for uid in (urs_ids if isinstance(urs_ids, list) else []):
            uid_str = str(uid)
            if uid_str in req_map:
                req_map[uid_str]["test_cases"].append(tc.get("test_id", ""))
                req_map[uid_str]["covered"] = True
        for rid in (risk_ids if isinstance(risk_ids, list) else []):
            rid_str = str(rid)
            if rid_str in risk_map:
                risk_map[rid_str]["test_cases"].append(tc.get("test_id", ""))
                risk_map[rid_str]["covered"] = True

    covered_reqs = sum(1 for r in req_map.values() if r["covered"])
    covered_risks = sum(1 for r in risk_map.values() if r["covered"])

    return {
        "requirements": list(req_map.values()),
        "risks": list(risk_map.values()),
        "test_cases": tc_rows,
        "total_requirements": len(req_map),
        "covered_requirements": covered_reqs,
        "uncovered_requirements": len(req_map) - covered_reqs,
        "urs_coverage_pct": round(covered_reqs / len(req_map) * 100, 1) if req_map else 0,
        "total_risks": len(risk_map),
        "covered_risks": covered_risks,
        "uncovered_risks": len(risk_map) - covered_risks,
        "risk_coverage_pct": round(covered_risks / len(risk_map) * 100, 1) if risk_map else 0,
        "total_test_cases": len(tc_rows),
    }


# ── DOCX Export Context ───────────────────────────────────────────────────────

def build_docx_markdown(report: dict, sections: list[dict]) -> str:
    """Convert report sections into a single markdown document for DOCX export."""
    lines = []
    lines.append(f"# {report.get('report_type','Validation Report')}")
    lines.append(f"**Document Number:** {report.get('report_number','')}")
    lines.append(f"**Equipment:** {report.get('equipment_name','')}")
    lines.append(f"**Revision:** {report.get('revision','A')} | **Status:** {report.get('status','').upper()}")
    lines.append(f"**Prepared By:** {report.get('prepared_by','')} | **Date:** {report.get('report_date','')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for section in sorted(sections, key=lambda s: s.get("section_order", 99)):
        content = section.get("content", "").strip()
        if content:
            lines.append(f"## {section.get('section_title','')}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)

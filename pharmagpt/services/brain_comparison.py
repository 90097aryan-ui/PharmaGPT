"""
services/brain_comparison.py — Yuktav Brain: Global-vs-Client Regulatory
Comparison (first reusable Brain reasoning capability).

Thin orchestration only: retrieve once via retrieval_engine.retrieve_context()
(tenant isolation and scope-labeling unchanged), split the returned chunks by
their own `.scope` field, build the comparison prompt, call Gemini, and
validate the response. No new retrieval path, no new reasoning engine, no
new tenant mechanism — see PROJECT_MEMORY/DECISIONS.md for the architecture
this extends.
"""

from __future__ import annotations

from pharmagpt.prompts.brain_comparison_prompt import (
    INSUFFICIENT_EVIDENCE_STATEMENT,
    build_comparison_prompt,
)
from pharmagpt.review.review_models import ComplianceStatus
from pharmagpt.services import retrieval_engine
from pharmagpt.services.qms_shared import call_gemini, parse_json_response

_VALID_STATUSES = {s.value for s in ComplianceStatus}


def _refusal_result(evidence_references: list[dict]) -> dict:
    return {
        "regulatory_requirement": "",
        "client_evidence_summary": "",
        "compliance_status": None,
        "conclusion": INSUFFICIENT_EVIDENCE_STATEMENT,
        "gaps": [],
        "confidence": 0.0,
        "evidence_references": evidence_references,
    }


def compare_regulatory_evidence(question: str, project_id: int, company_id: str,
                                max_chunks: int = 10) -> dict:
    """Compare Global Regulatory Knowledge against `company_id`'s own
    evidence for `question`, and return a structured, evidence-backed
    compliance result.

    `company_id` must be the caller's authenticated tenant
    (g.tenant.company_id) — see routes/brain.py; never accepted from
    request input here or at the route.

    Never calls Gemini when either side has zero retrieved evidence — the
    established insufficient-evidence result is returned directly instead
    of asking the model to notice the absence itself (same reasoning as
    services/investigation_engine.py's dashboard never calling AI when
    there is nothing to reason about).
    """
    result = retrieval_engine.retrieve_context(
        document_type="Regulatory Comparison", project_id=project_id, company_id=company_id,
        questionnaire={"question": question}, max_chunks=max_chunks,
    )

    # scope is derived by retrieval_engine.py from each row's own
    # company_id — never from document names, folders, or this question —
    # see retrieval_engine.py::retrieve_context's KB-loading loop.
    global_evidence = [c for c in result.chunks if c.scope == "Global"]
    client_evidence = [c for c in result.chunks if c.scope == "Client"]

    # evidence_references is exactly retrieval_engine.py's own sources[] —
    # never re-derived from the model's response, so a malformed or
    # fabricated citation from Gemini can never surface as a "reference".
    evidence_references = result.sources

    if not global_evidence or not client_evidence:
        return _refusal_result(evidence_references)

    prompt = build_comparison_prompt(question, global_evidence, client_evidence)
    response_text = call_gemini(prompt, temperature=0.2)
    parsed = parse_json_response(response_text, default=None)

    if not isinstance(parsed, dict):
        return _refusal_result(evidence_references)

    status = parsed.get("compliance_status")
    if status is not None and status not in _VALID_STATUSES:
        return _refusal_result(evidence_references)

    conclusion_raw = parsed.get("conclusion")
    conclusion = conclusion_raw.strip() if isinstance(conclusion_raw, str) else ""

    requirement_raw = parsed.get("regulatory_requirement")
    requirement = requirement_raw.strip() if isinstance(requirement_raw, str) else ""

    summary_raw = parsed.get("client_evidence_summary")
    summary = summary_raw.strip() if isinstance(summary_raw, str) else ""

    # Output consistency validation (Finding #1 from the read-only security
    # review): parse_json_response() only proves the model returned *some*
    # well-shaped JSON — it does not prove that JSON is internally
    # consistent. A PASS/WARNING/FAIL verdict with no stated requirement or
    # client evidence, or a null status paired with an arbitrary conclusion
    # instead of the established refusal sentence, must never be returned
    # as a genuine result — both are demoted to the same refusal result a
    # missing/malformed response already gets.
    if status is None:
        if conclusion != INSUFFICIENT_EVIDENCE_STATEMENT:
            return _refusal_result(evidence_references)
    else:
        if not requirement or not summary:
            return _refusal_result(evidence_references)

    gaps = parsed.get("gaps")
    if not isinstance(gaps, list):
        gaps = []

    return {
        "regulatory_requirement": requirement,
        "client_evidence_summary": summary,
        "compliance_status": status,
        "conclusion": conclusion,
        "gaps": gaps,
        "confidence": parsed.get("confidence") or 0.0,
        "evidence_references": evidence_references,
    }

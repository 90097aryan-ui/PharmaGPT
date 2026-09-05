"""
services/brain_gap_analysis.py — Yuktav Brain: Regulatory Gap Analysis V1.

Thin orchestration only, built beside services/brain_comparison.py (frozen
for this task, per the Gap Analysis V1 archaeology report) rather than on
top of it: retrieve once via retrieval_engine.retrieve_context() (tenant
isolation and scope-labeling unchanged), split the returned chunks by their
own `.scope` field, build the gap-analysis prompt, call Gemini, and validate
the response into a list of per-requirement coverage assessments. No new
retrieval path, no new reasoning engine, no new tenant mechanism, and no
change to brain_comparison.py's contract or behavior.
"""

from __future__ import annotations

from pharmagpt.prompts.brain_gap_analysis_prompt import (
    COVERAGE_STATUSES,
    NO_CLIENT_EVIDENCE_STATEMENT,
    NO_GLOBAL_EVIDENCE_STATEMENT,
    UNRELIABLE_OUTPUT_STATEMENT,
    build_gap_analysis_prompt,
)
from pharmagpt.services import retrieval_engine
from pharmagpt.services.qms_shared import call_gemini, parse_json_response

_MIN_CONFIDENCE = 0.0
_MAX_CONFIDENCE = 1.0


def _refusal_result(overall_summary: str, evidence_references: list[dict]) -> dict:
    return {
        "requirements": [],
        "overall_summary": overall_summary,
        "evidence_references": evidence_references,
    }


def _is_valid_confidence(value) -> bool:
    """Numeric (int/float, never bool) and within the project's existing
    0.0-1.0 confidence range (the same scale brain_comparison.py's
    "confidence" field and its UI rendering, Math.round(confidence*100),
    already assume)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return _MIN_CONFIDENCE <= value <= _MAX_CONFIDENCE


def _validate_requirement_item(item) -> dict | None:
    """Return a cleaned requirement dict, or None if the item fails
    structured-output validation — a single malformed item invalidates the
    whole response (never silently dropped or coerced into something
    valid-looking), same "reject, don't repair" principle as
    brain_comparison.py's output-consistency validation."""
    if not isinstance(item, dict):
        return None

    requirement_raw = item.get("requirement")
    summary_raw = item.get("client_evidence_summary")
    gap_raw = item.get("gap")
    status = item.get("coverage_status")
    confidence = item.get("confidence")

    if not isinstance(requirement_raw, str) or not requirement_raw.strip():
        return None
    if not isinstance(summary_raw, str):
        return None
    if not isinstance(gap_raw, str):
        return None
    if status not in COVERAGE_STATUSES:
        return None
    if not _is_valid_confidence(confidence):
        return None

    return {
        "requirement": requirement_raw.strip(),
        "client_evidence_summary": summary_raw.strip(),
        "coverage_status": status,
        "gap": gap_raw.strip(),
        "confidence": float(confidence),
    }


def analyze_regulatory_gaps(question: str, project_id: int, company_id: str,
                             max_chunks: int = 10) -> dict:
    """Compare Global Regulatory Knowledge against `company_id`'s own
    evidence for `question`, and return a structured list of per-requirement
    coverage assessments (COVERED / PARTIALLY_COVERED / NOT_COVERED /
    INSUFFICIENT_EVIDENCE).

    `company_id` must be the caller's authenticated tenant
    (g.tenant.company_id) — see routes/brain.py; never accepted from
    request input here or at the route.

    Never calls Gemini when either side has zero retrieved evidence — a
    deterministic, server-generated refusal is returned directly instead,
    same reasoning as services/brain_comparison.py's one-sided-evidence
    refusal.
    """
    result = retrieval_engine.retrieve_context(
        document_type="Regulatory Gap Analysis", project_id=project_id, company_id=company_id,
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

    if not global_evidence:
        return _refusal_result(NO_GLOBAL_EVIDENCE_STATEMENT, evidence_references)
    if not client_evidence:
        return _refusal_result(NO_CLIENT_EVIDENCE_STATEMENT, evidence_references)

    prompt = build_gap_analysis_prompt(question, global_evidence, client_evidence)
    response_text = call_gemini(prompt, temperature=0.2)
    parsed = parse_json_response(response_text, default=None)

    if not isinstance(parsed, dict):
        return _refusal_result(UNRELIABLE_OUTPUT_STATEMENT, evidence_references)

    raw_requirements = parsed.get("requirements")
    if not isinstance(raw_requirements, list):
        return _refusal_result(UNRELIABLE_OUTPUT_STATEMENT, evidence_references)

    overall_summary_raw = parsed.get("overall_summary", "")
    if not isinstance(overall_summary_raw, str):
        return _refusal_result(UNRELIABLE_OUTPUT_STATEMENT, evidence_references)

    requirements: list[dict] = []
    for item in raw_requirements:
        cleaned = _validate_requirement_item(item)
        if cleaned is None:
            return _refusal_result(UNRELIABLE_OUTPUT_STATEMENT, evidence_references)
        requirements.append(cleaned)

    return {
        "requirements": requirements,
        "overall_summary": overall_summary_raw.strip(),
        # Never parsed.get("evidence_references") — a model-supplied
        # reference list is never authoritative, see the prompt's
        # "AI QUALITY RULES" and the module docstring above.
        "evidence_references": evidence_references,
    }

"""
prompts/brain_gap_analysis_prompt.py — Yuktav Brain: Regulatory Gap Analysis V1
prompt builder (services/brain_gap_analysis.py).

Built beside prompts/brain_comparison_prompt.py, not on top of it —
brain_comparison_prompt.py is frozen for this task (see PROJECT_MEMORY/
DECISIONS.md DEC-027 / the Gap Analysis V1 archaeology report). Same
"never invent, refuse when insufficient" philosophy and the same
Global-vs-Client evidence-block rendering convention, duplicated here on
purpose rather than imported, so this new capability cannot destabilize the
completed Brain Comparison V1 milestone.

Where Brain Comparison V1 asks for a single PASS/WARNING/FAIL verdict for
one regulatory question, Gap Analysis V1 asks Gemini to enumerate every
regulatory requirement actually present in the retrieved Global evidence for
the question and assess each one's coverage by the retrieved Client evidence
independently — a list of per-requirement coverage assessments, not a second
compliance verdict.
"""

from __future__ import annotations

PROMPT_VERSION = "brain_gap_analysis_v1"

# Deterministic, server-generated refusal statements — returned directly by
# services/brain_gap_analysis.py without ever calling Gemini, exactly like
# brain_comparison.py's INSUFFICIENT_EVIDENCE_STATEMENT refusal path. Kept as
# two distinct sentences (rather than reusing one generic statement) so the
# reason for refusal is legible in the response and in tests.
NO_GLOBAL_EVIDENCE_STATEMENT = (
    "Unable to perform a regulatory gap analysis: no applicable Global "
    "Regulatory evidence was retrieved for this question."
)
NO_CLIENT_EVIDENCE_STATEMENT = (
    "Unable to perform a regulatory gap analysis: no Client evidence was "
    "retrieved for this question."
)
# Returned when Gemini's response cannot be trusted as-is (unparseable JSON,
# wrong shape, or a requirement item that fails structured-output validation)
# — same demotion-to-refusal principle as brain_comparison.py's malformed-
# response handling, never a partially-trusted result.
UNRELIABLE_OUTPUT_STATEMENT = (
    "Unable to determine regulatory gap coverage from the model's response."
)

# The exactly-four coverage statuses approved for V1 (see the archaeology
# report's §2). No additional values may be introduced.
COVERED = "COVERED"
PARTIALLY_COVERED = "PARTIALLY_COVERED"
NOT_COVERED = "NOT_COVERED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
COVERAGE_STATUSES = frozenset({COVERED, PARTIALLY_COVERED, NOT_COVERED, INSUFFICIENT_EVIDENCE})

_NEVER_INVENT_RULES = f"""
AI QUALITY RULES (mandatory, non-negotiable):
- Use ONLY the Global Regulatory Evidence and Client Evidence passages listed below. Never invent,
  assume, or infer a regulatory requirement, client procedure, citation, authority, document name,
  or fact that is not explicitly present in the text below.
- Do not treat a "yuktav_interpretation" passage as equivalent in authority to a "regulatory_source"
  passage.
- Identify ONLY regulatory requirements that are actually present in the Global evidence below.
  Never invent a requirement that is not supported by the supplied Global evidence.
- Never invent client evidence to fill in for missing or incomplete Client evidence for a
  requirement.
- Never create your own source citations or references — the application supplies evidence
  references separately from retrieval metadata; anything you place in "evidence_references" (if
  anything) will be ignored and is never treated as authoritative.
- "coverage_status" for each requirement MUST be exactly one of these four values, nothing else:
  "{COVERED}" | "{PARTIALLY_COVERED}" | "{NOT_COVERED}" | "{INSUFFICIENT_EVIDENCE}"
- "{NOT_COVERED}" and "{INSUFFICIENT_EVIDENCE}" are NOT interchangeable:
  * "{NOT_COVERED}" = the retrieved Client evidence indicates the requirement is genuinely not
    addressed (evidence exists but does not cover it, or evidence is silent on a topic the Client
    evidence set otherwise discusses).
  * "{INSUFFICIENT_EVIDENCE}" = you cannot reliably determine coverage one way or the other from
    the evidence actually retrieved — never guess a definite status when the evidence is too thin,
    ambiguous, or off-topic to support one.
- For "{COVERED}", "gap" may be an empty string. For every other status, "gap" must describe the
  missing or inadequate element (or, for "{INSUFFICIENT_EVIDENCE}", explain what evidence would be
  needed to reach a reliable determination).
- "overall_summary" is a short, plain-English recap of what was found — it is NOT a second
  compliance verdict and must not restate a single PASS/FAIL/WARNING-style judgement.
- If no regulatory requirement can be identified in the Global evidence at all, return an empty
  "requirements" list and explain that in "overall_summary" — do not fabricate a requirement to
  avoid returning an empty list.
"""


def _evidence_block(label: str, chunks: list) -> str:
    """Render the actual retrieved text for one evidence side — never just
    document names or status labels, mirroring retrieval_engine.py's
    _build_context_package citation convention (duplicated from
    brain_comparison_prompt.py's private helper of the same shape, since
    that module is frozen for this task)."""
    if not chunks:
        return f"{label}: (none retrieved)"
    lines = [f"{label}:"]
    for c in chunks:
        meta = [f"Source: {c.doc_name}"]
        if getattr(c, "content_category", None):
            meta.append(f"Category: {c.content_category}")
        if getattr(c, "source_authority", None):
            meta.append(f"Authority: {c.source_authority}")
        if getattr(c, "jurisdiction", None):
            meta.append(f"Jurisdiction: {c.jurisdiction}")
        if getattr(c, "publication_date", None):
            meta.append(f"Published: {c.publication_date}")
        lines.append(f"  [{' | '.join(meta)}]")
        lines.append(f"  {c.text}")
    return "\n".join(lines)


def build_gap_analysis_prompt(question: str, global_evidence: list, client_evidence: list) -> str:
    """Return the full Gemini prompt for a Regulatory Gap Analysis over
    `question`, comparing retrieved Global Regulatory Evidence against
    retrieved Client Evidence.

    `global_evidence`/`client_evidence` are lists of
    retrieval_engine.RetrievedChunk, already split by their own `.scope`
    field by the caller (services/brain_gap_analysis.py) — never re-derived
    here from names, folders, or the question text."""
    return f"""You are a Senior Pharmaceutical Regulatory Compliance Analyst performing a regulatory gap
analysis: identifying which applicable regulatory requirements are adequately covered, partially
covered, not covered, or impossible to assess from a client's own evidence, per 21 CFR / EU GMP /
ICH / WHO-GMP / PIC/S conventions. You are a decision-support assistant, not the record of truth —
a human reviews and confirms every conclusion; nothing here is written into any record automatically.

TOPIC / QUESTION:
{question}

{_evidence_block("GLOBAL REGULATORY EVIDENCE", global_evidence)}

{_evidence_block("CLIENT EVIDENCE", client_evidence)}
{_NEVER_INVENT_RULES}
Your job:
1. Identify each distinct applicable regulatory requirement actually supported by the Global
   evidence above.
2. For each requirement, identify the relevant client evidence (if any) from the Client evidence
   above.
3. Assess whether the client evidence adequately covers that requirement.
4. Assign exactly one of the four coverage statuses to each requirement.
5. Describe the gap where coverage is not complete.
6. Preserve uncertainty — use "{INSUFFICIENT_EVIDENCE}" rather than guessing when the evidence is
   too thin, ambiguous, or off-topic to support a reliable determination.

Return ONLY valid JSON (no other text):
{{
  "requirements": [
    {{
      "requirement": "the regulatory requirement identified from Global evidence",
      "client_evidence_summary": "the relevant client procedure/evidence identified, or empty string if none",
      "coverage_status": "{COVERED}" | "{PARTIALLY_COVERED}" | "{NOT_COVERED}" | "{INSUFFICIENT_EVIDENCE}",
      "gap": "description of the missing/inadequate element, or empty string for {COVERED}",
      "confidence": 0.0
    }}
  ],
  "overall_summary": "a short, plain-English recap of what was found across the requirements above",
  "evidence_references": []
}}"""

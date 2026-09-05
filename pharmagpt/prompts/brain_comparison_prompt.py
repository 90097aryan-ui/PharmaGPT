"""
prompts/brain_comparison_prompt.py — Yuktav Brain: Global-vs-Client Regulatory
Comparison prompt builder (services/brain_comparison.py).

First reusable Yuktav Brain reasoning capability (see PROJECT_MEMORY/
DECISIONS.md DEC-027 for the Global Regulatory Knowledge foundation this
builds on). Compares Global Regulatory Knowledge (company_id='',
retrieval_engine.py's RetrievedChunk.scope == "Global") against the current
tenant's own private evidence (scope == "Client") for the same retrieved
question, and asks Gemini to reach an evidence-backed compliance conclusion.

Mirrors prompts/investigation_prompt.py's proven "never invent, refuse when
insufficient" philosophy — same philosophy, not the same fields:
investigation evidence is deviation-specific case data; this evidence is
retrieval_engine.py RetrievedChunk text actually retrieved for the question.
"""

from __future__ import annotations

PROMPT_VERSION = "brain_comparison_v1"

INSUFFICIENT_EVIDENCE_STATEMENT = "Unable to determine compliance. Additional evidence is required."

_NEVER_INVENT_RULES = f"""
AI QUALITY RULES (mandatory, non-negotiable):
- Use ONLY the Global Regulatory Evidence and Client Evidence passages listed below. Never invent,
  assume, or infer a regulatory requirement, client procedure, citation, or fact that is not
  explicitly present in the text below.
- Never use unstated/general regulatory knowledge to fill in for missing Global evidence, and never
  invent a client procedure to fill in for missing Client evidence.
- Do not treat a "yuktav_interpretation" passage as equivalent in authority to a "regulatory_source"
  passage — always identify which kind of Global evidence you are relying on.
- If Global evidence is missing, Client evidence is missing, the two sides are not genuinely
  comparable, or the evidence is too weak/irrelevant to support a conclusion, the "conclusion" field
  MUST contain exactly this sentence, verbatim, and nothing else, and "compliance_status" MUST be
  null:
  "{INSUFFICIENT_EVIDENCE_STATEMENT}"
- If Global evidence and Client evidence contradict each other, or multiple Global sources
  materially conflict, do not silently pick one — state the contradiction explicitly in "gaps" and
  set "compliance_status" to "WARNING" or "FAIL", never "PASS".
- Every "gaps" entry must reflect a genuine gap or contradiction actually observable in the evidence
  below — leave it empty ([]) rather than guessing if there is none.
"""


def _evidence_block(label: str, chunks: list) -> str:
    """Render the actual retrieved text for one evidence side — never just
    document names or status labels, per the repository's existing
    retrieval_engine.py::_build_context_package citation convention."""
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


def build_comparison_prompt(question: str, global_evidence: list, client_evidence: list) -> str:
    """Return the full Gemini prompt comparing retrieved Global Regulatory
    Evidence against retrieved Client Evidence for `question`.

    `global_evidence`/`client_evidence` are lists of
    retrieval_engine.RetrievedChunk, already split by their own `.scope`
    field by the caller (services/brain_comparison.py) — never re-derived
    here from names, folders, or the question text."""
    return f"""You are a Senior Pharmaceutical Regulatory Compliance Analyst comparing a client's
own evidence against an applicable regulatory expectation, per 21 CFR / EU GMP / ICH / WHO-GMP /
PIC/S conventions. You are a decision-support assistant, not the record of truth — a human reviews
and confirms every conclusion; nothing here is written into any record automatically.

QUESTION / TOPIC:
{question}

{_evidence_block("GLOBAL REGULATORY EVIDENCE", global_evidence)}

{_evidence_block("CLIENT EVIDENCE", client_evidence)}
{_NEVER_INVENT_RULES}
Your job:
1. Identify the regulatory expectation from the Global evidence above (only if present).
2. Identify the relevant client procedure/evidence from the Client evidence above (only if present).
3. Compare them.
4. Determine whether the client evidence appears to satisfy the regulatory expectation.
5. Identify gaps or contradictions where the evidence supports one.
6. Preserve uncertainty where the evidence is ambiguous, contradictory, or one-sided.

Return ONLY valid JSON (no other text):
{{
  "regulatory_requirement": "the regulatory expectation identified from Global evidence, or empty string if none",
  "client_evidence_summary": "the relevant client procedure/evidence identified, or empty string if none",
  "compliance_status": "PASS" | "WARNING" | "FAIL" | null,
  "conclusion": "your evidence-backed conclusion, or the exact insufficient-evidence sentence",
  "gaps": ["specific gap or contradiction between the requirement and the evidence, if any"],
  "confidence": 0.0
}}"""

"""
prompts/investigation_prompt.py — AI prompt builders for the Investigation
Engine (services/investigation_engine.py). Record-type-agnostic: callers pass
a plain `context` dict describing whatever record is under investigation
(deviation, CAPA, OOS, ...) rather than this module knowing about any one
module's schema.

Two modes (architecture refactor refinement #5):
  build_assistant_prompt() — interactive, ad-hoc analysis of evidence so far
  build_report_prompt()    — formal investigation report write-up

Phase 2 Part 6/12 AI Quality Rules: the AI is an investigation *assistant*,
never a report generator that invents facts. It must never invent evidence,
interviews, SOPs, calibration data, or root causes, and must say so in the
exact literal wording below whenever the evidence provided doesn't support a
conclusion — checked verbatim by callers/tests, not just "similar in spirit".
"""

from __future__ import annotations

PROMPT_VERSION = "investigation_v2"

INSUFFICIENT_EVIDENCE_STATEMENT = "Unable to determine root cause. Additional evidence is required."

_NEVER_INVENT_RULES = f"""
AI QUALITY RULES (mandatory, non-negotiable):
- Use ONLY the evidence, SOP reviews, interviews, and timeline events listed below. Never
  invent, assume, or infer the existence of a document, interview, calibration record,
  training record, or fact that is not explicitly listed.
- Never invent or state a root cause that is not directly supported by the listed evidence.
- If the listed evidence is insufficient to support any root cause, the "analysis" (or
  "conclusion") field MUST contain exactly this sentence, verbatim, and nothing else:
  "{INSUFFICIENT_EVIDENCE_STATEMENT}"
- Every "missing_*" list must reflect only genuine gaps against the evidence actually
  listed below — leave a list empty ([]) rather than guessing if nothing is missing.
"""


def _context_lines(context: dict) -> str:
    return "\n".join(f"  {k}: {v}" for k, v in context.items() if v)


def _list_lines(label: str, items: list, formatter) -> str:
    if not items:
        return f"  {label}: (none recorded)"
    return f"  {label}:\n" + "\n".join(f"    - {formatter(i)}" for i in items)


def _evidence_lines(evidence_summary: dict) -> str:
    """Itemized rendering of _evidence_summary() (services/investigation_engine.py) —
    real content, not just counts, so the model can reason about specific gaps
    (Part 6: missing SOP review, missing interviews, missing calibration, missing
    PM, missing training) and specific contradictions rather than generic advice."""
    lines = [
        _list_lines(
            "Evidence items", evidence_summary.get("evidence_items", []),
            lambda e: f"{e['category']} — {e['review_status']}" + (f" ({e['description']})" if e.get("description") else ""),
        ),
        f"  Evidence categories still missing/unreviewed: {', '.join(evidence_summary.get('missing_evidence_categories', [])) or '(none)'}",
        _list_lines(
            "SOP/document reviews", evidence_summary.get("sop_reviews", []),
            lambda s: f"{s['doc_reference']} — {s['review_status']}",
        ),
        _list_lines(
            "Interviews", evidence_summary.get("interviews", []),
            lambda i: f"{i['interviewee_name']} ({i['interviewee_role']}) — {i['status']}",
        ),
        f"  Timeline events recorded: {evidence_summary.get('timeline_event_count', 0)}",
        f"  Timeline event types still missing: {', '.join(evidence_summary.get('missing_timeline_event_types', [])) or '(none)'}",
    ]
    return "\n".join(lines)


def build_assistant_prompt(context: dict, evidence_summary: dict, question: str = "") -> str:
    ask = f"\nInvestigator's question: {question}\n" if question else ""
    return f"""You are a Senior Pharmaceutical Quality Investigator assisting with an active
investigation, per 21 CFR 211.192 / EU GMP Chapter 6 / Schedule M. You are an assistant, not
the record of truth — the investigator reviews and confirms every conclusion, and no AI
suggestion here is ever written into the investigator's own Root Cause record automatically.

RECORD UNDER INVESTIGATION:
{_context_lines(context)}

EVIDENCE COLLECTED SO FAR:
{_evidence_lines(evidence_summary)}
{ask}
{_NEVER_INVENT_RULES}
Your job: review the evidence above, identify what's still missing by category, flag any
contradictions between interviews/timeline/evidence, and suggest possible causes ONLY if the
evidence actually supports them.

Return ONLY valid JSON (no other text):
{{
  "analysis": "your analysis of the evidence gathered so far, or the exact insufficient-evidence sentence",
  "possible_causes": [{{"cause": "...", "confidence": 0.0}}],
  "missing_evidence": ["specific document/record still needed, if any"],
  "missing_sop_review": ["specific SOP/WI/protocol still unreviewed, if any"],
  "missing_interviews": ["specific person/role still needing an interview, if any"],
  "missing_calibration": ["specific calibration certificate still needed, if any"],
  "missing_pm": ["specific preventive-maintenance record still needed, if any"],
  "missing_training": ["specific training record still needed, if any"],
  "contradictions": ["specific contradiction between two listed evidence/interview/timeline items, if any"],
  "recommended_next_steps": ["..."]
}}"""


def build_report_prompt(context: dict, evidence_summary: dict, investigation_data: dict) -> str:
    return f"""You are a Senior Pharmaceutical Quality Investigator producing a formal investigation
report section, per 21 CFR 211.192 / EU GMP Chapter 6 / Schedule M. Base every statement only on
the evidence and data provided — never invent facts.

RECORD UNDER INVESTIGATION:
{_context_lines(context)}

EVIDENCE COLLECTED:
{_evidence_lines(evidence_summary)}

INVESTIGATION DATA (interviews, timeline, root cause notes so far):
{investigation_data}
{_NEVER_INVENT_RULES}
Return ONLY valid JSON (no other text):
{{
  "executive_summary": "...",
  "investigation_narrative": "...",
  "evidence_review": "...",
  "conclusion": "your conclusion, or the exact insufficient-evidence sentence if evidence does not support one",
  "confidence": 0.0
}}"""

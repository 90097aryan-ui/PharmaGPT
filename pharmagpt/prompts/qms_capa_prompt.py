"""
prompts/qms_capa_prompt.py — AI prompt builders for the CAPA module.

Three AI features:
  build_draft_prompt()        — CAPA Draft: root cause + corrective/preventive actions (JSON)
  build_effectiveness_prompt() — Suggested effectiveness check criteria (JSON)
  build_trend_prompt()        — Quality Trend Summary across CAPAs (markdown narrative)
"""

from __future__ import annotations


def _capa_context(c: dict) -> str:
    lines = []
    for label, key in [
        ("CAPA Number", "capa_number"),
        ("Title", "title"),
        ("Source", "capa_source"),
        ("Source Reference", "source_reference"),
        ("Department", "department"),
        ("Problem Statement", "problem_statement"),
        ("Root Cause", "root_cause"),
    ]:
        val = c.get(key, "")
        if val:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


def build_draft_prompt(capa: dict) -> str:
    ctx = _capa_context(capa)
    return f"""You are a Senior Pharmaceutical Quality Consultant drafting a CAPA (Corrective and
Preventive Action) plan per 21 CFR 820.100, EU GMP Chapter 8, and ICH Q10.

CAPA DETAILS:
{ctx}

Return ONLY valid JSON (no other text):
{{
  "problem_statement": "refined, concise problem statement",
  "root_cause": "root cause statement (leave as-is if already provided and adequate)",
  "corrective_actions": [
    {{"description": "specific corrective action addressing the root cause", "owner": "responsible role", "due_date_offset_days": 30}}
  ],
  "preventive_actions": [
    {{"description": "specific preventive action to avoid recurrence", "owner": "responsible role", "due_date_offset_days": 60}}
  ]
}}

Generate 3-5 corrective actions and 2-4 preventive actions, each specific, actionable, and tied to
the stated root cause — not generic statements. Assign realistic responsible roles."""


def build_effectiveness_prompt(capa: dict, actions: list[dict]) -> str:
    ctx = _capa_context(capa)
    actions_text = "\n".join(
        f"  - [{a.get('action_type', '')}] {a.get('description', '')}" for a in actions
    ) or "  (no actions recorded yet)"

    return f"""You are a Senior Quality Assurance Specialist defining CAPA effectiveness checks per
ICH Q10 and EU GMP Chapter 8.

CAPA DETAILS:
{ctx}

ACTIONS IMPLEMENTED:
{actions_text}

Return ONLY a valid JSON array (no other text):
[
  {{
    "check_criterion": "specific, measurable criterion",
    "method": "how effectiveness will be verified (e.g. trend monitoring, re-audit, KPI tracking)",
    "timeframe": "e.g. 3 months post-implementation",
    "acceptable_result": "quantified pass condition"
  }}
]

Generate 2-4 effectiveness checks directly tied to the corrective/preventive actions above."""


def build_trend_prompt(capas: list[dict], deviations: list[dict]) -> str:
    capa_lines = "\n".join(
        f"  - {c.get('capa_number','')}: {c.get('title','')} | Source: {c.get('capa_source','')} | Status: {c.get('status','')}"
        for c in capas[:30]
    ) or "  (no CAPAs recorded)"
    dev_lines = "\n".join(
        f"  - {d.get('deviation_number','')}: {d.get('title','')} | Type: {d.get('deviation_type','')} | Category: {d.get('deviation_category','')} | Status: {d.get('status','')}"
        for d in deviations[:30]
    ) or "  (no deviations recorded)"

    return f"""You are a Senior Quality Systems Analyst preparing a Quality Trend Summary for
management review, per ICH Q10 Pharmaceutical Quality System requirements.

RECENT CAPAs:
{capa_lines}

RECENT DEVIATIONS:
{dev_lines}

Write a concise Quality Trend Summary (plain markdown, 250-400 words) covering:
1. Overall trend observations (recurring sources, categories, or departments)
2. Notable risk areas or clusters worth management attention
3. Recommendations for systemic improvement

Be specific and reference the actual records above — do not write generic filler."""

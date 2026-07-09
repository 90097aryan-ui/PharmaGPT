"""
services/doc_generator.py — Prompt dispatch layer for PharmaGPT v0.9.3.

Each of the 11 pharmaceutical document types is handled by a dedicated prompt
module in pharmagpt/prompts/. This file translates the raw request payload into
the standardised arguments those modules expect, then returns the assembled prompt
string ready to pass to Gemini.

Architecture:
    build_generation_prompt(doc_type, form_data, doc_context, project_name)
        ↓
    Equipment Intelligence Engine: auto-load equipment profile
        ↓
    pharmagpt/prompts/PROMPT_REGISTRY[doc_type].get_prompt(
        project_data, equipment_data, questionnaire, knowledge_base
    )
        ↓
    returns a complete prompt string ready to pass to Gemini

To edit a prompt, open the corresponding file in pharmagpt/prompts/ — no
changes to this file or any route are required.

To add new equipment intelligence, add a profile to pharmagpt/equipment/profiles/
and register it in pharmagpt/equipment/profiles/__init__.py — no other changes needed.
"""

from datetime import date as _date

from pharmagpt.prompts import PROMPT_REGISTRY
from pharmagpt.equipment import get_equipment_profile, format_profile_for_prompt

# Doc types assembled from more than one proven single-purpose prompt rather
# than one large combined prompt. A single "write one giant combined document"
# prompt for IQ/OQ was found to reliably send gemini-2.5-flash into a
# degenerate repetition loop (multi-hundred-KB of repeated whitespace); running
# the same two prompts that already generate IQ and OQ reliably on their own,
# sequentially, sidesteps that failure mode entirely.
COMBINED_DOC_TYPES: dict[str, list[str]] = {
    "IQ/OQ Combined": ["IQ", "OQ"],
}

# Doc types that are themselves IQ/OQ/PQ-style qualification protocols — these
# benefit from the Equipment Intelligence Engine's IQ/OQ/PQ checklist sections.
# Every other doc type (SOP, Validation Plan, Validation Report, URS, DQ's
# non-qualification siblings, etc.) gets a lighter profile without those
# checklists — see format_profile_for_prompt()'s qualification_doc parameter.
_QUALIFICATION_DOC_TYPES = {"IQ", "OQ", "PQ", "DQ", "FAT", "SAT", "IQ/OQ Combined"}

# Doc types where injecting the equipment profile block at all — even the
# lighter non-qualification version — was found to occasionally destabilise
# gemini-2.5-flash into degenerate repetitive output (observed repeatedly with
# SOP; these document types describe a procedure/plan/summary rather than
# equipment-specific test execution, so the profile's marginal value is low
# next to that risk). Equipment name/model/manufacturer still reach the
# prompt normally via equipment_data — only the extra profile block is skipped.
_SKIP_PROFILE_DOC_TYPES = {"SOP", "Validation Plan", "Validation Report"}


def build_generation_prompt(
    doc_type: str,
    form_data: dict,
    doc_context: str,
    project_name: str,
) -> str | list[str]:
    """
    Build the Gemini generation prompt(s) for a validation document.

    Parameters
    ----------
    doc_type     : "OQ" | "IQ" | "PQ" | "URS" | "DQ" | "FAT" | "SAT" | "FMEA" |
                   "CAPA" | "Deviation" | "Change Control" | "IQ/OQ Combined" |
                   "SOP" | "Validation Plan" | "Validation Report"
    form_data    : dict with keys from Step 1 (equipment) and Step 2 (details)
    doc_context  : formatted text from search_project_documents() — may be ""
    project_name : name of the active project

    Returns
    -------
    str            — the complete prompt to send to Gemini as a single user message, or
    list[str]      — for doc types in COMBINED_DOC_TYPES, one prompt per sub-document;
                      the caller generates and concatenates each part in its own
                      Gemini call rather than asking for the whole thing in one shot.
    """
    today = _date.today().strftime("%d %B %Y")

    project_data = {
        "name": project_name,
        "date": today,
    }

    equipment_data = {
        "name":         form_data.get("equipment_name", ""),
        "model":        form_data.get("model", ""),
        "manufacturer": form_data.get("manufacturer", ""),
        "serial":       form_data.get("serial_number", ""),
        "location":     form_data.get("location", ""),
        "department":   form_data.get("department", ""),
    }

    questionnaire = form_data.get("details", {})

    # ── Equipment Intelligence Engine ────────────────────────────────────────
    # Attempt to load a profile for this equipment and prepend it to the
    # retrieval context so every prompt module benefits automatically.
    profile = get_equipment_profile(equipment_data["name"]) if doc_type not in _SKIP_PROFILE_DOC_TYPES else None
    if profile:
        equipment_profile_block = format_profile_for_prompt(
            profile, qualification_doc=doc_type in _QUALIFICATION_DOC_TYPES
        )
        knowledge_base = equipment_profile_block + "\n\n" + doc_context
    else:
        knowledge_base = doc_context

    sub_types = COMBINED_DOC_TYPES.get(doc_type)
    if sub_types:
        # Deliberately skip _questionnaire_context_block() here: the wizard's
        # questionnaire for a combined doc type mixes fields meant for each
        # sub-document (e.g. an OQ-flavoured "operating_parameters" answer
        # alongside an IQ-flavoured "installation_checklist" one). Appending
        # the same full mixed set of free-form answers to BOTH legs — fields
        # irrelevant to that leg included — was found to occasionally push
        # gemini-2.5-flash into degenerate repetitive output for some
        # equipment/questionnaire combinations. Each leg's own prompt module
        # already pulls its relevant metadata via questionnaire.get(...).
        return [
            PROMPT_REGISTRY[sub_type](project_data, equipment_data, questionnaire, knowledge_base)
            for sub_type in sub_types
        ]

    context_block = _questionnaire_context_block(questionnaire)
    get_prompt = PROMPT_REGISTRY.get(doc_type)
    if get_prompt is None:
        prompt = _generic_prompt(doc_type, project_data, equipment_data,
                                 questionnaire, knowledge_base)
    else:
        prompt = get_prompt(project_data, equipment_data, questionnaire, knowledge_base)

    return prompt + context_block


# ─────────────────────────────────────────────────────────────────────────────
# Additional free-form questionnaire context
# ─────────────────────────────────────────────────────────────────────────────

_CONTEXT_VALUE_MAX_CHARS = 300   # keep the appendage small — this is background, not a new instruction

def _questionnaire_context_block(questionnaire: dict) -> str:
    """
    Append every non-empty questionnaire answer as a short, passive background
    note (never phrased as an instruction to add content or expand sections —
    an earlier, more directive phrasing here ("incorporate this ... where
    applicable") was found to occasionally push gemini-2.5-flash into
    degenerate repetitive output for some equipment/questionnaire combinations,
    even though the exact same doc-type prompt generates cleanly on its own).

    Per-doc-type prompt modules only pull out the specific keys they know
    about (e.g. protocol_number, version). Callers such as the Generate
    Document wizard collect additional free-form content questions (e.g.
    "installation_checklist", "test_cases") that aren't named parameters in
    any prompt module — without this, that user input would be silently
    dropped instead of informing the generated content.
    """
    entries = {k: v for k, v in (questionnaire or {}).items() if v}
    if not entries:
        return ""

    def _clip(v):
        v = str(v)
        return v if len(v) <= _CONTEXT_VALUE_MAX_CHARS else v[:_CONTEXT_VALUE_MAX_CHARS] + "…"

    lines = "\n".join(
        f"- {k.replace('_', ' ').title()}: {_clip(v)}" for k, v in entries.items()
    )
    return (
        "\n\n(For background only — notes supplied by the requester. "
        "The document structure and sections above remain exactly as specified.)\n"
        f"{lines}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Generic fallback for unrecognised doc types
# ─────────────────────────────────────────────────────────────────────────────

def _generic_prompt(doc_type, project_data, equipment_data, questionnaire,
                    knowledge_base):
    eq     = equipment_data
    doc_no = questionnaire.get("doc_number", "DOC-001")
    ctx    = f"\n{knowledge_base}\n" if knowledge_base.strip() else ""
    return (
        f"You are a Senior Pharmaceutical Validation Expert with 30+ years of GMP experience.\n\n"
        f"Generate a COMPLETE, GMP-COMPLIANT {doc_type} document ({doc_no}).\n"
        f"PROJECT: {project_data['name']} | DATE: {project_data['date']}\n"
        f"EQUIPMENT: {eq['name']} {eq['model']} | MFR: {eq['manufacturer']} | "
        f"S/N: {eq['serial']} | DEPT: {eq['department']} | LOC: {eq['location']}\n"
        f"{ctx}\n"
        f"Include all standard sections, tables, acceptance criteria, and approval signatures. "
        f"Write all sections completely using professional pharmaceutical language."
    )

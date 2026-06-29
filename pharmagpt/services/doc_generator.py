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


def build_generation_prompt(
    doc_type: str,
    form_data: dict,
    doc_context: str,
    project_name: str,
) -> str:
    """
    Build the Gemini generation prompt for a validation document.

    Parameters
    ----------
    doc_type     : "OQ" | "IQ" | "PQ" | "URS" | "DQ" | "FAT" | "SAT" |
                   "FMEA" | "CAPA" | "Deviation" | "Change Control"
    form_data    : dict with keys from Step 1 (equipment) and Step 2 (details)
    doc_context  : formatted text from search_project_documents() — may be ""
    project_name : name of the active project

    Returns
    -------
    str — the complete prompt to send to Gemini as a single user message
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
    profile = get_equipment_profile(equipment_data["name"])
    if profile:
        equipment_profile_block = format_profile_for_prompt(profile)
        knowledge_base = equipment_profile_block + "\n\n" + doc_context
    else:
        knowledge_base = doc_context

    get_prompt = PROMPT_REGISTRY.get(doc_type)
    if get_prompt is None:
        return _generic_prompt(doc_type, project_data, equipment_data,
                               questionnaire, knowledge_base)

    return get_prompt(project_data, equipment_data, questionnaire, knowledge_base)


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

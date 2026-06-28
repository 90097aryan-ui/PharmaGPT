"""Shared preamble builder used by all prompt modules."""


def preamble(doc_label: str, equipment_data: dict, knowledge_base: str,
             project_data: dict) -> str:
    """Return the common GMP expert context block prepended to every prompt."""
    ctx = f"\n{knowledge_base}\n" if knowledge_base.strip() else ""
    eq = equipment_data
    return (
        f"You are a Senior Pharmaceutical Validation Expert and Regulatory Affairs "
        f"Specialist with 30+ years of GMP experience across USFDA, MHRA, EU GMP, "
        f"WHO-GMP, CDSCO, and TGA environments.\n\n"
        f"Generate a COMPLETE, DETAILED, and GMP-COMPLIANT {doc_label} document.\n"
        f"Cite applicable regulations (21 CFR Part 211/820, EU GMP Annex 15, "
        f"GAMP5, ICH Q9/Q10, Schedule M, ISO 9001) throughout.\n"
        f"Use professional pharmaceutical language. Every section must be fully written "
        f"— do NOT leave placeholder text like '[Fill in]'.\n\n"
        f"PROJECT: {project_data['name']}\n"
        f"DATE: {project_data['date']}\n"
        f"EQUIPMENT: {eq['name']} {eq['model']} | MFR: {eq['manufacturer']} | "
        f"S/N: {eq['serial']} | DEPT: {eq['department']} | LOC: {eq['location']}\n"
        f"{ctx}"
    )

"""
pharmagpt/prompts — Document-specific Prompt Library for PharmaGPT v0.9.1

Each module exposes a single function:
    get_prompt(project_data, equipment_data, questionnaire, knowledge_base) -> str

Parameters
----------
project_data    : dict  — {"name": str, "date": str}
equipment_data  : dict  — {"name", "model", "manufacturer", "serial", "location", "department"}
questionnaire   : dict  — document-type-specific form fields from Step 2
knowledge_base  : str   — formatted RAG context from search_project_documents() (may be "")
"""

from .iq_prompt import get_prompt as iq_prompt
from .oq_prompt import get_prompt as oq_prompt
from .pq_prompt import get_prompt as pq_prompt
from .urs_prompt import get_prompt as urs_prompt
from .dq_prompt import get_prompt as dq_prompt
from .fat_prompt import get_prompt as fat_prompt
from .sat_prompt import get_prompt as sat_prompt
from .fmea_prompt import get_prompt as fmea_prompt
from .capa_prompt import get_prompt as capa_prompt
from .deviation_prompt import get_prompt as deviation_prompt
from .change_control_prompt import get_prompt as change_control_prompt

PROMPT_REGISTRY = {
    "IQ":             iq_prompt,
    "OQ":             oq_prompt,
    "PQ":             pq_prompt,
    "URS":            urs_prompt,
    "DQ":             dq_prompt,
    "FAT":            fat_prompt,
    "SAT":            sat_prompt,
    "FMEA":           fmea_prompt,
    "CAPA":           capa_prompt,
    "Deviation":      deviation_prompt,
    "Change Control": change_control_prompt,
}

__all__ = ["PROMPT_REGISTRY", "PHARMA_SYSTEM_PROMPT"]

# Re-export from the top-level prompts.py so that
# `from prompts import PHARMA_SYSTEM_PROMPT` works whether Python resolves
# this package or the sibling prompts.py module.
try:
    import importlib, sys as _sys
    _top = importlib.util.spec_from_file_location(
        "__pharma_prompts_top__",
        __file__.replace("__init__.py", "").rstrip("/\\").rstrip("prompts") + "prompts.py",
    )
    if _top and _top.loader:
        _m = importlib.util.module_from_spec(_top)
        _top.loader.exec_module(_m)
        PHARMA_SYSTEM_PROMPT = _m.PHARMA_SYSTEM_PROMPT
    else:
        raise ImportError("spec not found")
except Exception:
    PHARMA_SYSTEM_PROMPT = ""  # fallback; will cause obvious failures rather than silent ones

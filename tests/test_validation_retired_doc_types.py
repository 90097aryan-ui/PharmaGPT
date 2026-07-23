"""
tests/test_validation_retired_doc_types.py — Regression coverage for the
Generate Document duplication fix (REPOSITORY_AUDIT.md Critical finding;
FUNCTIONAL_VALIDATION_REPORT.md H4/H4-related C2 area).

URS/IQ/OQ/PQ/CAPA/Deviation/Change Control each now have their own dedicated
suite with its own AI generation, lifecycle, and approval trail. Generating
them a second time via POST /validation/generate was flagged Critical
(a duplicate, review-gate-free path to the same document type) and retired
per Blueprint ADR-P02. This is enforced server-side (routes/validation.py::
_RETIRED_DOC_TYPES), not just hidden client-side, so the duplicate path
can't be reached by a direct API call either.

Phase 3 (Enterprise Validation Platform) retires DQ/FAT/SAT the same way —
they now persist as qms_documents rows (doc_type='DQ'|'FAT'|'SAT') via
POST /qms/documents instead of the lifecycle-less generic wizard table, so
they move from STILL_ACTIVE_TYPES to RETIRED_TYPES below.
"""

import pytest

from pharmagpt.routes.validation import _RETIRED_DOC_TYPES

RETIRED_TYPES = ["URS", "IQ", "OQ", "PQ", "CAPA", "Deviation", "Change Control",
                  "DQ", "FAT", "SAT"]
STILL_ACTIVE_TYPES = ["FMEA", "IQ/OQ Combined", "SOP", "Validation Plan", "Validation Report"]


@pytest.mark.parametrize("doc_type", RETIRED_TYPES)
def test_retired_doc_type_rejected_before_project_lookup(client, doc_type):
    """No project_id is supplied — if the retired-type guard didn't fire
    first, this would 400 on 'project_id is required' instead of 410."""
    resp = client.post("/validation/generate", json={"doc_type": doc_type})

    assert resp.status_code == 410
    body = resp.get_json()
    assert doc_type not in body["error"] or _RETIRED_DOC_TYPES[doc_type] in body["error"]
    assert "no longer generated here" in body["error"]


@pytest.mark.parametrize("doc_type", STILL_ACTIVE_TYPES)
def test_active_doc_type_not_rejected_by_retirement_guard(client, doc_type):
    """These types have no dedicated suite yet and remain generated here.
    Omitting project_id should surface the *next* validation error (400),
    proving the request passed the retirement guard rather than being
    blocked at 410."""
    resp = client.post("/validation/generate", json={"doc_type": doc_type})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "project_id is required"


def test_retired_doc_types_cover_exactly_the_ten_consolidated_types():
    """Locks the retirement list to REPOSITORY_AUDIT.md / DUPLICATE_FUNCTION_
    ANALYSIS.md §1's original 7 duplicate types plus Phase 3's DQ/FAT/SAT
    consolidation into Document Control. FMEA/IQ-OQ Combined/SOP/Validation
    Plan/Validation Report remain explicitly NOT consolidated (no dedicated
    lifecycle-governed suite exists for them yet) and must stay generated
    here."""
    assert set(_RETIRED_DOC_TYPES) == {
        "URS", "IQ", "OQ", "PQ", "CAPA", "Deviation", "Change Control",
        "DQ", "FAT", "SAT",
    }

"""
tests/test_brain_gap_analysis.py — Yuktav Brain: Regulatory Gap Analysis V1
(services/brain_gap_analysis.py, routes/brain.py::gap_analysis, prompts/
brain_gap_analysis_prompt.py) — built beside Brain Comparison V1, not on top
of it. See tests/test_brain_comparison.py for the frozen, unmodified sibling
suite this deliberately does not duplicate or touch.

Same conventions as tests/test_brain_comparison.py: seeds kb_documents
directly, mocks call_gemini at the services.brain_gap_analysis import site,
and proves orchestration/validation/refusal logic rather than real model
output quality (which cannot be unit-tested). Only one confirmation test
here that this new, independent capability does not weaken TEN-01/Global
Governance isolation already proven by tests/test_retrieval_engine_tenant_
isolation.py and tests/test_global_knowledge_governance.py.
"""

import json

import pytest

from pharmagpt import database as db
from pharmagpt.prompts.brain_gap_analysis_prompt import (
    COVERED,
    INSUFFICIENT_EVIDENCE,
    NOT_COVERED,
    NO_CLIENT_EVIDENCE_STATEMENT,
    NO_GLOBAL_EVIDENCE_STATEMENT,
    PARTIALLY_COVERED,
    UNRELIABLE_OUTPUT_STATEMENT,
)
from pharmagpt.services import brain_gap_analysis
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"
COMPANY_B = "company-b-22222222-2222-2222-2222-222222222222"

_QUESTION = "cleaning validation requirements for shared manufacturing equipment"

_VALID_ITEM = {
    "requirement": "Cleaning validation must include a documented MACO calculation.",
    "client_evidence_summary": "SOP-014 documents the cleaning cycle.",
    "coverage_status": COVERED,
    "gap": "",
    "confidence": 0.85,
}


def _seed_global(content_status: str, secret: str, content_category: str = "regulatory_source") -> dict:
    row = db.create_kb_document(
        title=f"Global {secret}", folder="Regulations", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name=f"{secret}.pdf",
        stored_filename=f"{secret}.pdf", file_type="pdf", file_size=1024, company_id="",
        created_by="super-admin-a", content_category=content_category,
        source_authority="ICH", content_status=content_status,
    )
    conn = db.get_connection()
    conn.execute(
        "UPDATE kb_documents SET text_content = ?, extraction_status = 'ok' WHERE id = ?",
        (f"{_QUESTION} regulatory expectation. {secret} " * 20, row["id"]),
    )
    conn.commit()
    conn.close()
    return db.get_kb_document(row["id"])


def _seed_client(company_id: str, secret: str) -> dict:
    row = db.create_kb_document(
        title=f"Client {secret}", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name=f"{secret}.pdf",
        stored_filename=f"{secret}.pdf", file_type="pdf", file_size=1024, company_id=company_id,
    )
    conn = db.get_connection()
    conn.execute(
        "UPDATE kb_documents SET text_content = ?, extraction_status = 'ok' WHERE id = ?",
        (f"{_QUESTION} client procedure. {secret} " * 20, row["id"]),
    )
    conn.commit()
    conn.close()
    return db.get_kb_document(row["id"])


def _seed_both_sides(secret_g: str, secret_c: str) -> None:
    _seed_global("active", secret_g)
    _seed_client(COMPANY_A, secret_c)


def _mock_response(monkeypatch, payload: dict):
    monkeypatch.setattr(brain_gap_analysis, "call_gemini",
                        lambda prompt, temperature=0.2: json.dumps(payload))
    return payload


def _item(**overrides) -> dict:
    item = dict(_VALID_ITEM)
    item.update(overrides)
    return item


# ── 7-8: one-sided evidence → deterministic refusal, no LLM call ────────────

def test_no_global_evidence_is_deterministic_refusal(db_path, monkeypatch):
    _seed_client(COMPANY_A, "CLIENT-ONLY")

    def _fail_if_called(*a, **k):
        raise AssertionError("call_gemini must not be called with no Global evidence")
    monkeypatch.setattr(brain_gap_analysis, "call_gemini", _fail_if_called)

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == NO_GLOBAL_EVIDENCE_STATEMENT


def test_no_client_evidence_is_deterministic_refusal(db_path, monkeypatch):
    _seed_global("active", "GLOBAL-ONLY")

    def _fail_if_called(*a, **k):
        raise AssertionError("call_gemini must not be called with no Client evidence")
    monkeypatch.setattr(brain_gap_analysis, "call_gemini", _fail_if_called)

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == NO_CLIENT_EVIDENCE_STATEMENT


# ── 9: both sides present → Gemini is actually called ───────────────────────

def test_both_evidence_sides_triggers_gemini_call(db_path, monkeypatch):
    _seed_both_sides("G-BOTH", "C-BOTH")
    called = {}

    def _capture(prompt, temperature=0.2):
        called["yes"] = True
        called["prompt"] = prompt
        return json.dumps({
            "requirements": [_item()],
            "overall_summary": "One requirement identified.",
        })
    monkeypatch.setattr(brain_gap_analysis, "call_gemini", _capture)

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert called.get("yes") is True
    assert "GLOBAL REGULATORY EVIDENCE" in called["prompt"]
    assert "CLIENT EVIDENCE" in called["prompt"]
    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["coverage_status"] == COVERED


# ── 10: Global/Client split uses trusted retrieval metadata ─────────────────

def test_scope_split_uses_trusted_retrieval_metadata(db_path, monkeypatch):
    _seed_global("active", "SHARED-GLOBAL")
    _seed_client(COMPANY_A, "COMPANY-A-SECRET")
    _seed_client(COMPANY_B, "COMPANY-B-SECRET")
    _mock_response(monkeypatch, {"requirements": [_item()], "overall_summary": "ok"})

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)
    names = [r["name"] for r in result["evidence_references"]]

    assert any("COMPANY-A-SECRET" in n for n in names)
    assert not any("COMPANY-B-SECRET" in n for n in names)
    assert any("SHARED-GLOBAL" in n for n in names)
    scopes = {r["scope"] for r in result["evidence_references"]}
    assert scopes == {"Global", "Client"}


# ── 11: Gemini cannot supply authoritative evidence references ──────────────

def test_gemini_cannot_supply_authoritative_evidence_references(db_path, monkeypatch):
    _seed_global("active", "TRACE-GLOBAL")
    _seed_client(COMPANY_A, "TRACE-CLIENT")
    _mock_response(monkeypatch, {
        "requirements": [_item()],
        "overall_summary": "ok",
        # A model attempting to fabricate its own citation — must be ignored entirely.
        "evidence_references": [{"id": 999, "name": "Fabricated Source", "scope": "Global"}],
    })

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    names = [r["name"] for r in result["evidence_references"]]
    assert "Fabricated Source" not in names
    assert any("TRACE-GLOBAL" in n for n in names)
    assert any("TRACE-CLIENT" in n for n in names)


# ── 12-15: each of the four coverage statuses is accepted as-is ─────────────

@pytest.mark.parametrize("status", [COVERED, PARTIALLY_COVERED, NOT_COVERED, INSUFFICIENT_EVIDENCE])
def test_each_valid_coverage_status_is_accepted(db_path, monkeypatch, status):
    _seed_both_sides(f"G-{status}", f"C-{status}")
    _mock_response(monkeypatch, {
        "requirements": [_item(coverage_status=status, gap="" if status == COVERED else "missing element")],
        "overall_summary": "ok",
    })

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["coverage_status"] == status


def test_not_covered_and_insufficient_evidence_are_distinct_values(db_path, monkeypatch):
    """The two statuses must never collapse into each other."""
    _seed_both_sides("G-DISTINCT", "C-DISTINCT")
    _mock_response(monkeypatch, {
        "requirements": [
            _item(requirement="Req A", coverage_status=NOT_COVERED, gap="No evidence addresses this at all."),
            _item(requirement="Req B", coverage_status=INSUFFICIENT_EVIDENCE, gap="Evidence too ambiguous to assess."),
        ],
        "overall_summary": "ok",
    })

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    statuses = {r["requirement"]: r["coverage_status"] for r in result["requirements"]}
    assert statuses["Req A"] == NOT_COVERED
    assert statuses["Req B"] == INSUFFICIENT_EVIDENCE
    assert statuses["Req A"] != statuses["Req B"]


# ── 16-19: malformed output is rejected, never repaired ─────────────────────

def test_invalid_coverage_status_is_rejected(db_path, monkeypatch):
    _seed_both_sides("G-INVSTAT", "C-INVSTAT")
    _mock_response(monkeypatch, {
        "requirements": [_item(coverage_status="MOSTLY_COVERED")],  # not a real status
        "overall_summary": "ok",
    })

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


def test_malformed_gemini_output_is_rejected(db_path, monkeypatch):
    _seed_both_sides("G-MALFORMED", "C-MALFORMED")
    monkeypatch.setattr(brain_gap_analysis, "call_gemini",
                        lambda prompt, temperature=0.2: "not json at all")

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


@pytest.mark.parametrize("bad_confidence", [1.5, -0.1, "high", None, True, float("nan")])
def test_invalid_confidence_is_rejected(db_path, monkeypatch, bad_confidence):
    _seed_both_sides("G-BADCONF", "C-BADCONF")
    _mock_response(monkeypatch, {
        "requirements": [_item(confidence=bad_confidence)],
        "overall_summary": "ok",
    })

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


@pytest.mark.parametrize("missing_field", ["requirement", "client_evidence_summary", "coverage_status", "gap", "confidence"])
def test_missing_required_output_field_is_rejected(db_path, monkeypatch, missing_field):
    _seed_both_sides(f"G-MISS-{missing_field}", f"C-MISS-{missing_field}")
    item = _item()
    del item[missing_field]
    _mock_response(monkeypatch, {"requirements": [item], "overall_summary": "ok"})

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


def test_requirements_not_a_list_is_rejected(db_path, monkeypatch):
    _seed_both_sides("G-NOTLIST", "C-NOTLIST")
    _mock_response(monkeypatch, {"requirements": "not a list", "overall_summary": "ok"})

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


def test_non_dict_response_is_rejected(db_path, monkeypatch):
    _seed_both_sides("G-NOTDICT", "C-NOTDICT")
    _mock_response(monkeypatch, [_item()])  # a bare list, not the expected object

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


def test_non_dict_requirement_item_is_rejected(db_path, monkeypatch):
    _seed_both_sides("G-ITEMTYPE", "C-ITEMTYPE")
    _mock_response(monkeypatch, {"requirements": ["just a string"], "overall_summary": "ok"})

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


def test_non_string_overall_summary_is_rejected(db_path, monkeypatch):
    _seed_both_sides("G-SUMTYPE", "C-SUMTYPE")
    _mock_response(monkeypatch, {"requirements": [_item()], "overall_summary": 12345})

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == UNRELIABLE_OUTPUT_STATEMENT


# ── 20: empty requirements list from Gemini is handled safely ───────────────

def test_empty_requirements_list_from_gemini_is_handled_safely(db_path, monkeypatch):
    _seed_both_sides("G-EMPTY", "C-EMPTY")
    _mock_response(monkeypatch, {
        "requirements": [],
        "overall_summary": "No applicable regulatory requirements were identified for this topic.",
    })

    result = brain_gap_analysis.analyze_regulatory_gaps(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["requirements"] == []
    assert result["overall_summary"] == "No applicable regulatory requirements were identified for this topic."
    # Distinguishable from the deterministic pre-Gemini refusals by summary text.
    assert result["overall_summary"] != NO_GLOBAL_EVIDENCE_STATEMENT
    assert result["overall_summary"] != NO_CLIENT_EVIDENCE_STATEMENT


# ── Route-level: input validation, tenancy, auth ─────────────────────────────

def test_route_valid_request_returns_200(client, monkeypatch):
    import pharmagpt.routes.brain as brain_routes

    project = db.create_project(
        "Gap Analysis Test", "Autoclave", "Getinge", "QA", "IQ/OQ/PQ",
        company_id=BOOTSTRAP_COMPANY_ID,
    )
    monkeypatch.setattr(brain_routes, "analyze_regulatory_gaps", lambda **kwargs: {
        "requirements": [], "overall_summary": "ok", "evidence_references": [],
    })

    resp = client.post("/brain/gap-analysis", json={"question": _QUESTION, "project_id": project["id"]})

    assert resp.status_code == 200


def test_route_missing_question_is_400(client):
    project = db.create_project(
        "Gap Analysis Test 2", "Autoclave", "Getinge", "QA", "IQ/OQ/PQ",
        company_id=BOOTSTRAP_COMPANY_ID,
    )
    resp = client.post("/brain/gap-analysis", json={"project_id": project["id"]})
    assert resp.status_code == 400


def test_route_empty_question_is_400(client):
    project = db.create_project(
        "Gap Analysis Test 3", "Autoclave", "Getinge", "QA", "IQ/OQ/PQ",
        company_id=BOOTSTRAP_COMPANY_ID,
    )
    resp = client.post("/brain/gap-analysis", json={"question": "   ", "project_id": project["id"]})
    assert resp.status_code == 400


def test_route_missing_project_is_400(client):
    resp = client.post("/brain/gap-analysis", json={"question": _QUESTION})
    assert resp.status_code == 400


def test_route_nonexistent_project_is_404(client):
    resp = client.post("/brain/gap-analysis", json={"question": _QUESTION, "project_id": 99999999})
    assert resp.status_code == 404


def test_route_non_owned_project_is_404(client):
    other_company_project = db.create_project(
        "Other Company Project", "Autoclave", "Getinge", "QA", "IQ/OQ/PQ",
        company_id="some-other-company-id",
    )
    resp = client.post("/brain/gap-analysis", json={
        "question": _QUESTION, "project_id": other_company_project["id"],
    })
    assert resp.status_code == 404


def test_route_no_tenant_is_401():
    """Exercises the real, unpatched auth gate (tests/conftest.py's `client`
    fixture bypasses auth for the other 300+ tests using it) — mirrors
    tests/test_app_auth_integration.py's own dedicated `client` fixture."""
    import pharmagpt.app as appmod

    real_client = appmod.app.test_client()
    resp = real_client.post("/brain/gap-analysis", json={"question": _QUESTION, "project_id": 1})
    assert resp.status_code == 401


def test_route_derives_company_id_from_session_not_request_body(client, monkeypatch):
    import pharmagpt.routes.brain as brain_routes

    project = db.create_project(
        "Gap Analysis Spoof Test", "Autoclave", "Getinge", "QA", "IQ/OQ/PQ",
        company_id=BOOTSTRAP_COMPANY_ID,
    )
    captured = {}

    def _fake_analyze(question, project_id, company_id, **kwargs):
        captured["company_id"] = company_id
        return {"requirements": [], "overall_summary": "ok", "evidence_references": []}
    monkeypatch.setattr(brain_routes, "analyze_regulatory_gaps", _fake_analyze)

    resp = client.post("/brain/gap-analysis", json={
        "question": _QUESTION, "project_id": project["id"],
        "company_id": "spoofed-company-id", "role": "super_admin", "scope": "Global",
        "tenant_id": "spoofed-tenant-id",
    })

    assert resp.status_code == 200
    assert captured["company_id"] == BOOTSTRAP_COMPANY_ID
    assert captured["company_id"] != "spoofed-company-id"

"""
tests/test_brain_comparison.py — Yuktav Brain: Global-vs-Client Regulatory
Comparison (services/brain_comparison.py, routes/brain.py, prompts/
brain_comparison_prompt.py) — the first reusable Brain reasoning capability.

Seeds kb_documents directly (same style as
tests/test_global_knowledge_governance.py) and mocks call_gemini at the
services.brain_comparison import site (same convention
tests/test_investigation_engine.py already uses for inv.call_gemini) —
proves the orchestration/validation/refusal logic, not real model output
quality, which cannot be unit-tested.

Does not duplicate tests/test_retrieval_engine_tenant_isolation.py or
tests/test_global_knowledge_governance.py's full isolation/governance
battery — only one confirmation test here that this new orchestration layer
does not weaken what those suites already prove.
"""

import json

from pharmagpt import database as db
from pharmagpt.prompts.brain_comparison_prompt import INSUFFICIENT_EVIDENCE_STATEMENT
from pharmagpt.services import brain_comparison
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"
COMPANY_B = "company-b-22222222-2222-2222-2222-222222222222"

_QUESTION = "autoclave sterilization cycle validation requirements"


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


def _mock_response(monkeypatch, payload: dict):
    monkeypatch.setattr(brain_comparison, "call_gemini",
                        lambda prompt, temperature=0.2: json.dumps(payload))
    return payload


# ── 1-2: one-sided evidence → refusal, no LLM call ───────────────────────────

def test_global_only_evidence_is_insufficient(db_path, monkeypatch):
    _seed_global("active", "GLOBAL-ONLY")

    def _fail_if_called(*a, **k):
        raise AssertionError("call_gemini must not be called with one-sided evidence")
    monkeypatch.setattr(brain_comparison, "call_gemini", _fail_if_called)

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


def test_client_only_evidence_is_insufficient(db_path, monkeypatch):
    _seed_client(COMPANY_A, "CLIENT-ONLY")

    def _fail_if_called(*a, **k):
        raise AssertionError("call_gemini must not be called with one-sided evidence")
    monkeypatch.setattr(brain_comparison, "call_gemini", _fail_if_called)

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# ── 3: both sides present → prompt carries both, distinctly labeled ─────────

def test_prompt_contains_both_distinctly_labelled_evidence_sets(db_path, monkeypatch):
    _seed_global("active", "GLOBAL-TEXT-MARKER")
    _seed_client(COMPANY_A, "CLIENT-TEXT-MARKER")

    captured = {}

    def _capture(prompt, temperature=0.2):
        captured["prompt"] = prompt
        return json.dumps({
            "regulatory_requirement": "req", "client_evidence_summary": "sum",
            "compliance_status": "PASS", "conclusion": "Satisfies the requirement.",
            "gaps": [], "confidence": 0.8,
        })
    monkeypatch.setattr(brain_comparison, "call_gemini", _capture)

    brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    prompt = captured["prompt"]
    assert "GLOBAL REGULATORY EVIDENCE" in prompt
    assert "CLIENT EVIDENCE" in prompt
    assert "GLOBAL-TEXT-MARKER" in prompt
    assert "CLIENT-TEXT-MARKER" in prompt
    assert prompt.index("GLOBAL REGULATORY EVIDENCE") < prompt.index("CLIENT EVIDENCE")


# ── 4: successful structured result ──────────────────────────────────────────

def test_successful_comparison_returns_valid_compliance_status(db_path, monkeypatch):
    _seed_global("active", "REQ-TEXT")
    _seed_client(COMPANY_A, "PROC-TEXT")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "Autoclave cycles must be validated per Annex 15.",
        "client_evidence_summary": "SOP-014 describes cycle validation.",
        "compliance_status": "PASS", "conclusion": "Client SOP addresses the requirement.",
        "gaps": [], "confidence": 0.85,
    })

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["compliance_status"] == "PASS"
    assert result["regulatory_requirement"]
    assert result["client_evidence_summary"]
    assert result["conclusion"] != INSUFFICIENT_EVIDENCE_STATEMENT


# ── 5: Global-vs-Client contradiction surfaced, not silently ignored ────────

def test_contradiction_is_surfaced_as_warning_with_gap(db_path, monkeypatch):
    _seed_global("active", "REQ-TEXT-2")
    _seed_client(COMPANY_A, "PROC-TEXT-2")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "Cleaning validation requires documented MACO calculation.",
        "client_evidence_summary": "SOP-009 does not reference MACO.",
        "compliance_status": "WARNING",
        "conclusion": "Client evidence appears to contradict the requirement.",
        "gaps": ["No MACO calculation referenced in client SOP-009."],
        "confidence": 0.7,
    })

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["compliance_status"] in ("WARNING", "FAIL")
    assert result["gaps"]


# ── 6: conflicting Global sources → refusal passed through, not invented ────

def test_conflicting_global_sources_refusal_passes_through(db_path, monkeypatch):
    _seed_global("active", "REQ-TEXT-3")
    _seed_client(COMPANY_A, "PROC-TEXT-3")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "", "client_evidence_summary": "",
        "compliance_status": None, "conclusion": INSUFFICIENT_EVIDENCE_STATEMENT,
        "gaps": ["Global sources conflict on cycle duration."], "confidence": 0.0,
    })

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# ── 7: unparseable Gemini response → established refusal ────────────────────

def test_unparseable_response_defaults_to_refusal(db_path, monkeypatch):
    _seed_global("active", "REQ-TEXT-4")
    _seed_client(COMPANY_A, "PROC-TEXT-4")
    monkeypatch.setattr(brain_comparison, "call_gemini", lambda prompt, temperature=0.2: "not json at all")

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


def test_invalid_compliance_status_value_defaults_to_refusal(db_path, monkeypatch):
    """Malformed model output (an invented status the shared ComplianceStatus
    enum doesn't recognize) must never be trusted as a confident result."""
    _seed_global("active", "REQ-TEXT-5")
    _seed_client(COMPANY_A, "PROC-TEXT-5")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "x", "client_evidence_summary": "y",
        "compliance_status": "MOSTLY_COMPLIANT",  # not a real ComplianceStatus value
        "conclusion": "z", "gaps": [], "confidence": 0.5,
    })

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# ── 8: evidence-reference traceability — from retrieved sources, not the model ──

def test_evidence_references_originate_from_retrieved_sources_not_model(db_path, monkeypatch):
    _seed_global("active", "TRACE-GLOBAL")
    _seed_client(COMPANY_A, "TRACE-CLIENT")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "req", "client_evidence_summary": "sum",
        "compliance_status": "PASS", "conclusion": "ok",
        "gaps": [],
        "confidence": 0.9,
        # A model attempting to fabricate its own citation — must be ignored entirely.
        "evidence_references": [{"id": 999, "name": "Fabricated Source", "scope": "Global"}],
    })

    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)

    names = [r["name"] for r in result["evidence_references"]]
    assert "Fabricated Source" not in names
    assert any("TRACE-GLOBAL" in n for n in names)
    assert any("TRACE-CLIENT" in n for n in names)
    scopes = {r["scope"] for r in result["evidence_references"]}
    assert scopes == {"Global", "Client"}


# ── 9: route derives company_id from the authenticated session ──────────────

def test_route_derives_company_id_from_session_not_request_body(client, monkeypatch):
    import pharmagpt.routes.brain as brain_routes

    project = db.create_project(
        "Brain Compare Test", "Autoclave", "Getinge", "QA", "IQ/OQ/PQ",
        company_id=BOOTSTRAP_COMPANY_ID,
    )

    captured = {}

    def _fake_compare(question, project_id, company_id, **kwargs):
        captured["company_id"] = company_id
        return {
            "regulatory_requirement": "", "client_evidence_summary": "",
            "compliance_status": None, "conclusion": INSUFFICIENT_EVIDENCE_STATEMENT,
            "gaps": [], "confidence": 0.0, "evidence_references": [],
        }
    monkeypatch.setattr(brain_routes, "compare_regulatory_evidence", _fake_compare)

    resp = client.post("/brain/compare", json={
        "question": _QUESTION, "project_id": project["id"],
        "company_id": "spoofed-company-id", "role": "super_admin",
    })

    assert resp.status_code == 200
    assert captured["company_id"] == BOOTSTRAP_COMPANY_ID
    assert captured["company_id"] != "spoofed-company-id"


# ── 10: existing tenant isolation is not weakened by this new layer ─────────

def test_existing_isolation_remains_intact(db_path, monkeypatch):
    _seed_global("active", "SHARED-GLOBAL")
    _seed_client(COMPANY_A, "COMPANY-A-SECRET")
    _seed_client(COMPANY_B, "COMPANY-B-SECRET")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "req", "client_evidence_summary": "sum",
        "compliance_status": "PASS", "conclusion": "ok", "gaps": [], "confidence": 0.9,
    })

    result_a = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    names_a = [r["name"] for r in result_a["evidence_references"]]

    assert any("COMPANY-A-SECRET" in n for n in names_a)
    assert not any("COMPANY-B-SECRET" in n for n in names_a)
    assert any("SHARED-GLOBAL" in n for n in names_a)


# ── Output consistency validation (Finding #1, read-only security review) ───
# compare_regulatory_evidence() must never return a PASS/WARNING/FAIL verdict
# backed by an empty/whitespace-only requirement or client evidence summary,
# and must never return a null status paired with anything other than the
# exact, established INSUFFICIENT_EVIDENCE_STATEMENT — either case is
# demoted to _refusal_result(), same as a malformed/unparseable response.

def _seed_both_sides(secret_g: str, secret_c: str) -> None:
    _seed_global("active", secret_g)
    _seed_client(COMPANY_A, secret_c)


# A. PASS + empty regulatory_requirement → refusal
def test_pass_with_empty_requirement_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-A", "C-A")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "", "client_evidence_summary": "SOP-014 covers this.",
        "compliance_status": "PASS", "conclusion": "Satisfies the requirement.",
        "gaps": [], "confidence": 0.9,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# B. PASS + empty client_evidence_summary → refusal
def test_pass_with_empty_client_summary_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-B", "C-B")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "Cycles must be validated per Annex 15.",
        "client_evidence_summary": "", "compliance_status": "PASS",
        "conclusion": "Satisfies the requirement.", "gaps": [], "confidence": 0.9,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# C. WARNING + empty regulatory_requirement → refusal
def test_warning_with_empty_requirement_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-C", "C-C")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "", "client_evidence_summary": "SOP-009 partially covers this.",
        "compliance_status": "WARNING", "conclusion": "Partial match.",
        "gaps": ["unclear"], "confidence": 0.5,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# D. FAIL + empty client_evidence_summary → refusal
def test_fail_with_empty_client_summary_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-D", "C-D")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "MACO calculation must be documented.",
        "client_evidence_summary": "", "compliance_status": "FAIL",
        "conclusion": "Does not satisfy the requirement.", "gaps": ["missing MACO"], "confidence": 0.8,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# E. whitespace-only regulatory_requirement → refusal
def test_whitespace_only_requirement_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-E", "C-E")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "   \n  ", "client_evidence_summary": "SOP-014 covers this.",
        "compliance_status": "PASS", "conclusion": "Satisfies the requirement.",
        "gaps": [], "confidence": 0.9,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# F. whitespace-only client_evidence_summary → refusal
def test_whitespace_only_client_summary_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-F", "C-F")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "Cycles must be validated per Annex 15.",
        "client_evidence_summary": "\t  ", "compliance_status": "PASS",
        "conclusion": "Satisfies the requirement.", "gaps": [], "confidence": 0.9,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# G. null compliance_status + arbitrary conclusion → refusal
def test_null_status_with_arbitrary_conclusion_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-G", "C-G")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "", "client_evidence_summary": "",
        "compliance_status": None, "conclusion": "I am not sure, maybe it's fine.",
        "gaps": [], "confidence": 0.1,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# H. null compliance_status + empty conclusion → refusal
def test_null_status_with_empty_conclusion_is_refused(db_path, monkeypatch):
    _seed_both_sides("G-H", "C-H")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "", "client_evidence_summary": "",
        "compliance_status": None, "conclusion": "",
        "gaps": [], "confidence": 0.0,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT


# I. null compliance_status + exact INSUFFICIENT_EVIDENCE_STATEMENT → accepted
def test_null_status_with_exact_refusal_statement_is_accepted(db_path, monkeypatch):
    _seed_both_sides("G-I", "C-I")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "", "client_evidence_summary": "",
        "compliance_status": None, "conclusion": INSUFFICIENT_EVIDENCE_STATEMENT,
        "gaps": ["Global sources conflict."], "confidence": 0.0,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] is None
    assert result["conclusion"] == INSUFFICIENT_EVIDENCE_STATEMENT
    assert result["gaps"] == ["Global sources conflict."]


# J. valid PASS with both evidence summaries and conclusion → accepted
def test_valid_pass_with_both_summaries_is_accepted(db_path, monkeypatch):
    _seed_both_sides("G-J", "C-J")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "Cycles must be validated per Annex 15.",
        "client_evidence_summary": "SOP-014 documents cycle validation.",
        "compliance_status": "PASS", "conclusion": "Client SOP addresses the requirement.",
        "gaps": [], "confidence": 0.85,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] == "PASS"
    assert result["regulatory_requirement"]
    assert result["client_evidence_summary"]
    assert result["conclusion"] != INSUFFICIENT_EVIDENCE_STATEMENT


# K. valid WARNING with both evidence summaries → accepted
def test_valid_warning_with_both_summaries_is_accepted(db_path, monkeypatch):
    _seed_both_sides("G-K", "C-K")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "Cleaning validation requires a documented MACO calculation.",
        "client_evidence_summary": "SOP-009 does not reference MACO.",
        "compliance_status": "WARNING", "conclusion": "Partial coverage; gap identified.",
        "gaps": ["No MACO calculation referenced."], "confidence": 0.6,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] == "WARNING"
    assert result["regulatory_requirement"]
    assert result["client_evidence_summary"]


# L. valid FAIL with both evidence summaries → accepted
def test_valid_fail_with_both_summaries_is_accepted(db_path, monkeypatch):
    _seed_both_sides("G-L", "C-L")
    _mock_response(monkeypatch, {
        "regulatory_requirement": "Autoclave cycles must reach validated F0.",
        "client_evidence_summary": "SOP-021 does not specify F0 targets.",
        "compliance_status": "FAIL", "conclusion": "Client evidence does not satisfy the requirement.",
        "gaps": ["No F0 target specified."], "confidence": 0.75,
    })
    result = brain_comparison.compare_regulatory_evidence(_QUESTION, project_id=0, company_id=COMPANY_A)
    assert result["compliance_status"] == "FAIL"
    assert result["regulatory_requirement"]
    assert result["client_evidence_summary"]

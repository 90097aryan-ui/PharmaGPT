"""
tests/test_document_template_ai_enforcement.py — Fix coverage: controlled-
template heading/sub-heading preservation in AI draft generation.

Two layers, both tested:
  1. Prompt construction (services/prompts/qms_document_prompt.py::
     build_draft_prompt) — injects the template's exact headings/sub-
     headings with explicit non-removal/non-reorder instructions.
  2. Deterministic post-generation enforcement
     (validate_template_structure()) — since a prompt instruction alone
     cannot *guarantee* an LLM complies, this is the actual, testable check
     run against generated content, with no AI call involved.

Route-level tests mock stream_gemini exactly like tests/test_qms_routes.py's
existing mock_gemini fixture does — no live API dependency.
"""

import json

import pytest

from pharmagpt.prompts import qms_document_prompt as qp

STRUCTURE = [
    {"heading": "1. Purpose", "sub_headings": []},
    {"heading": "2. Scope", "sub_headings": []},
    {"heading": "3. Procedure", "sub_headings": ["3.1 Preparation", "3.2 Execution", "3.3 Cleanup"]},
    {"heading": "4. References", "sub_headings": []},
]

COMPLIANT_CONTENT = """# Cleaning SOP

## 1. Purpose
Some purpose text.

## 2. Scope
Some scope text.

## 3. Procedure
Intro text.

### 3.1 Preparation
Prep steps.

### 3.2 Execution
Execution steps.

### 3.3 Cleanup
Cleanup steps.

## 4. References
21 CFR 211.
"""


# ── validate_template_structure: deterministic enforcement ──────────────────

def test_compliant_content_is_valid():
    result = qp.validate_template_structure(COMPLIANT_CONTENT, STRUCTURE)
    assert result["valid"] is True
    assert result["missing_headings"] == []
    assert result["out_of_order"] is False


def test_missing_heading_is_invalid():
    content = COMPLIANT_CONTENT.replace("## 4. References\n21 CFR 211.\n", "")
    result = qp.validate_template_structure(content, STRUCTURE)
    assert result["valid"] is False
    assert "4. References" in result["missing_headings"]


def test_missing_sub_heading_is_invalid():
    content = COMPLIANT_CONTENT.replace("### 3.3 Cleanup\nCleanup steps.\n\n", "")
    result = qp.validate_template_structure(content, STRUCTURE)
    assert result["valid"] is False
    assert "3.3 Cleanup" in result["missing_headings"]


def test_renamed_heading_is_invalid():
    """Renaming counts as removing the required heading and adding an
    unrelated one — the required text is simply no longer present."""
    content = COMPLIANT_CONTENT.replace("## 2. Scope", "## 2. Applicability")
    result = qp.validate_template_structure(content, STRUCTURE)
    assert result["valid"] is False
    assert "2. Scope" in result["missing_headings"]


def test_reordered_headings_is_invalid():
    # Swap Purpose and Scope
    content = COMPLIANT_CONTENT.replace(
        "## 1. Purpose\nSome purpose text.\n\n## 2. Scope\nSome scope text.\n",
        "## 2. Scope\nSome scope text.\n\n## 1. Purpose\nSome purpose text.\n",
    )
    result = qp.validate_template_structure(content, STRUCTURE)
    assert result["valid"] is False
    assert result["out_of_order"] is True
    assert result["missing_headings"] == []  # nothing missing, just reordered


def test_extra_ai_added_headings_are_not_a_violation():
    """The AI adding extra content/headings beyond the controlled set is
    fine — only removing, renaming, or reordering a CONTROLLED heading is
    a violation."""
    content = COMPLIANT_CONTENT + "\n## Appendix A: Extra Notes\nSome bonus content.\n"
    result = qp.validate_template_structure(content, STRUCTURE)
    assert result["valid"] is True


def test_empty_content_reports_all_headings_missing():
    result = qp.validate_template_structure("", STRUCTURE)
    assert result["valid"] is False
    total_required = sum(1 + len(s["sub_headings"]) for s in STRUCTURE)  # 4 headings + 3 sub-headings = 7
    assert len(result["missing_headings"]) == total_required == 7


# ── build_draft_prompt: template structure injection ─────────────────────────

def test_prompt_without_template_uses_fixed_default_structure():
    prompt = qp.build_draft_prompt({"title": "Doc", "doc_type": "SOP"})
    assert "## 1. Purpose" in prompt
    assert "## 9. Revision History" in prompt
    assert "APPROVED CONTROLLED TEMPLATE" not in prompt


def test_prompt_with_template_injects_exact_headings_in_order():
    template = {"name": "Cleaning SOP Template", "structure": STRUCTURE}
    prompt = qp.build_draft_prompt({"title": "Cleaning SOP", "doc_type": "SOP"}, template=template)

    assert "APPROVED CONTROLLED TEMPLATE" in prompt
    assert '"Cleaning SOP Template"' in prompt
    for heading in ["## 1. Purpose", "## 2. Scope", "## 3. Procedure", "## 4. References"]:
        assert heading in prompt
    for sub in ["### 3.1 Preparation", "### 3.2 Execution", "### 3.3 Cleanup"]:
        assert sub in prompt

    # order: Purpose must appear before Scope before Procedure before References
    idx_purpose = prompt.index("## 1. Purpose")
    idx_scope = prompt.index("## 2. Scope")
    idx_procedure = prompt.index("## 3. Procedure")
    idx_references = prompt.index("## 4. References")
    assert idx_purpose < idx_scope < idx_procedure < idx_references

    # fixed hardcoded structure must NOT also appear — no duplicate/competing structure
    assert "## 9. Revision History" not in prompt


def test_prompt_with_template_states_non_removal_rules():
    template = {"name": "T", "structure": STRUCTURE}
    prompt = qp.build_draft_prompt({"title": "Doc"}, template=template)
    lowered = prompt.lower()
    assert "must not remove" in lowered or "must not remove" in lowered.replace(",", "")
    assert "reorder" in lowered
    assert "rename" in lowered or "renam" in lowered


def test_prompt_with_template_but_empty_structure_falls_back_to_default():
    template = {"name": "Empty Template", "structure": []}
    prompt = qp.build_draft_prompt({"title": "Doc", "doc_type": "SOP"}, template=template)
    assert "## 1. Purpose" in prompt  # fixed default, unaffected
    assert "APPROVED CONTROLLED TEMPLATE" not in prompt


# ── Route level: generate_draft wires template + surfaces structure_check ───

@pytest.fixture()
def mock_stream_gemini_compliant(monkeypatch):
    import pharmagpt.routes.qms_documents as doc_routes

    def _fake(prompt, temperature=0.3):
        yield COMPLIANT_CONTENT

    monkeypatch.setattr(doc_routes, "stream_gemini", _fake)


@pytest.fixture()
def mock_stream_gemini_violates_structure(monkeypatch):
    import pharmagpt.routes.qms_documents as doc_routes

    def _fake(prompt, temperature=0.3):
        yield "# Cleaning SOP\n\n## 1. Purpose\nOnly this section, nothing else.\n"

    monkeypatch.setattr(doc_routes, "stream_gemini", _fake)


def _sse_events(response):
    events = []
    for line in response.get_data(as_text=True).split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def test_generate_draft_with_compliant_output_reports_valid(client, mock_stream_gemini_compliant):
    from pharmagpt import qms_document_database as qdb
    t = client.post("/qms/documents/templates",
                     json={"doc_type": "SOP", "name": "Cleaning SOP Template", "structure": STRUCTURE}).get_json()
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "template_id": t["id"]}).get_json()

    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)
    done_event = next(e for e in events if "done" in e)
    assert done_event["structure_check"]["valid"] is True

    assert "1. Purpose" in qdb.get_document(doc["id"])["content"]


def test_generate_draft_with_violating_output_flags_and_still_saves_content(client, mock_stream_gemini_violates_structure):
    from pharmagpt import qms_document_database as qdb
    from pharmagpt import qms_database as qmsdb
    t = client.post("/qms/documents/templates",
                     json={"doc_type": "SOP", "name": "Cleaning SOP Template", "structure": STRUCTURE}).get_json()
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "template_id": t["id"]}).get_json()

    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)
    done_event = next(e for e in events if "done" in e)
    assert done_event["structure_check"]["valid"] is False
    assert "2. Scope" in done_event["structure_check"]["missing_headings"]

    # content is still saved — not discarded — so the author has something to fix
    assert qdb.get_document(doc["id"])["content"]

    # violation is logged to the audit trail
    audit_trail = qmsdb.get_audit_trail("document", doc["id"])
    assert any("violated controlled template structure" in a["action"] for a in audit_trail)


def test_generate_draft_without_template_has_no_structure_check(client, mock_stream_gemini_compliant):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)
    done_event = next(e for e in events if "done" in e)
    assert done_event["structure_check"] is None

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

Route-level tests register fake providers with the AI Gateway
(pharmagpt/providers/router.py) — Stage 3 migrated generate_draft() off the
old qms_shared.stream_gemini() onto the router, so these tests inject fake
Gemini/NVIDIA responses via isolated_ai_gateway (tests/conftest.py) instead
of monkeypatching a stream_gemini name that no longer exists on
routes/qms_documents.py. No live API dependency either way.
"""

import json
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

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
#
# Fake providers registered with the AI Gateway (isolated_ai_gateway, see
# tests/conftest.py). A fake's generate_content_stream(contents, config)
# returns/yields SimpleNamespace(text=...) chunks — the same duck-typed
# shape every real provider client (google.genai's own response objects,
# providers/nemotron_client.py's _StreamChunk) uses, and what
# routes/qms_documents.py's migrated generate_draft() reads via chunk.text.

class _FakeModels:
    def __init__(self, fn):
        self._fn = fn

    def generate_content_stream(self, *, model=None, contents=None, config=None):
        return self._fn(contents, config)


class _FakeClient:
    def __init__(self, fn):
        self.models = _FakeModels(fn)


def _text_chunks(*texts):
    return (SimpleNamespace(text=t) for t in texts)


def _register(rt, name, fn, model="fake-model"):
    rt.register_provider(name, lambda: _FakeClient(fn), model=model)


def _refuse(name):
    def _fn(contents, config):
        raise AssertionError(f"{name} should not have been called")
    return _fn


def _quota_error():
    return genai_errors.ClientError(429, {"message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"})


def _transient_error():
    return genai_errors.ServerError(503, {"message": "backend unavailable", "status": "UNAVAILABLE"})


@pytest.fixture()
def mock_stream_gemini_compliant(isolated_ai_gateway):
    _register(isolated_ai_gateway, "gemini", lambda contents, config: _text_chunks(COMPLIANT_CONTENT))
    _register(isolated_ai_gateway, "nemotron", _refuse("nemotron"))  # happy path never falls back


@pytest.fixture()
def mock_stream_gemini_violates_structure(isolated_ai_gateway):
    _register(
        isolated_ai_gateway, "gemini",
        lambda contents, config: _text_chunks("# Cleaning SOP\n\n## 1. Purpose\nOnly this section, nothing else.\n"),
    )
    _register(isolated_ai_gateway, "nemotron", _refuse("nemotron"))


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

    # SSE contract: at least one 'chunk' event carrying the streamed text,
    # exactly one 'done' event, and no 'error' event on a clean success.
    chunk_events = [e for e in events if "chunk" in e]
    assert chunk_events and "".join(e["chunk"] for e in chunk_events) == COMPLIANT_CONTENT
    assert not any("error" in e for e in events)
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


# ── Zero usable AI chunks: generation failure, not an empty draft ───────────
# The route filters any chunk whose .text is falsy (matching the old
# stream_gemini()'s own filtering), so it can see zero usable text with no
# exception raised — whether that's because Gemini's stream itself produced
# nothing, or (see the empty-fallback-output test below) NVIDIA's did after
# a Gemini failure. Either way this must be reported as a failed generation
# (SSE 'error', no 'done', no structure_check, document content untouched)
# rather than a successful-but-incomplete draft.

@pytest.fixture()
def mock_stream_gemini_empty(isolated_ai_gateway):
    """Zero usable chunks from Gemini specifically (a successful call that
    completes with no text) — mirrors a filtered/empty Gemini response."""
    _register(isolated_ai_gateway, "gemini", lambda contents, config: iter(()))
    _register(isolated_ai_gateway, "nemotron", _refuse("nemotron"))


def test_generate_draft_with_zero_usable_chunks_reports_error_not_done(client, mock_stream_gemini_empty):
    from pharmagpt import qms_document_database as qdb
    from pharmagpt import qms_database as qmsdb
    t = client.post("/qms/documents/templates",
                     json={"doc_type": "SOP", "name": "Cleaning SOP Template", "structure": STRUCTURE}).get_json()
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "template_id": t["id"]}).get_json()

    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)

    assert not any("done" in e for e in events)
    error_event = next(e for e in events if "error" in e)
    assert error_event["error"] == (
        "AI draft generation produced no usable content. No document content was changed. Please try again."
    )

    # an initially empty document stays empty — never explicitly set to ""
    # by this call, and no structure_check ever ran against it
    assert qdb.get_document(doc["id"])["content"] == ""

    audit_trail = qmsdb.get_audit_trail("document", doc["id"])
    failures = [a for a in audit_trail
                if a["action"] == "AI draft generation violated controlled template structure"]
    assert len(failures) == 1
    assert "no usable content" in failures[0]["reason"]
    assert "not changed" in failures[0]["reason"]


def test_generate_draft_with_zero_usable_chunks_preserves_existing_content(client, mock_stream_gemini_empty):
    from pharmagpt import qms_document_database as qdb
    t = client.post("/qms/documents/templates",
                     json={"doc_type": "SOP", "name": "Cleaning SOP Template", "structure": STRUCTURE}).get_json()
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "template_id": t["id"]}).get_json()
    client.put(f"/qms/documents/{doc['id']}", json={"content": COMPLIANT_CONTENT})
    before = qdb.get_document(doc["id"])["content"]
    assert before == COMPLIANT_CONTENT

    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)
    assert any("error" in e for e in events)
    assert not any("done" in e for e in events)

    # a retry that produced no usable output must never overwrite content
    # the Author had already entered or previously generated
    assert qdb.get_document(doc["id"])["content"] == before


# ── Provider fallback (Stage 3: AI Gateway) ──────────────────────────────────
# Gemini stays primary, NVIDIA is the fallback (docs/AI_PROVIDER_ROUTER.md).
# The gateway's own contract (unchanged from Stage 1) is that retry/fallback
# only ever happen while trying to *start* the stream — before the caller
# has received a single chunk. These tests exercise that contract through
# Document Control's actual generate_draft() endpoint, not just the router
# in isolation (already covered by tests/test_provider_router.py).

def _make_doc(client):
    t = client.post("/qms/documents/templates",
                     json={"doc_type": "SOP", "name": "Cleaning SOP Template", "structure": STRUCTURE}).get_json()
    return client.post("/qms/documents", json={"title": "Cleaning SOP", "template_id": t["id"]}).get_json()


def test_generate_draft_quota_before_first_chunk_falls_back_to_nemotron(client, isolated_ai_gateway):
    gemini_calls = []

    def fake_gemini(contents, config):
        gemini_calls.append(1)
        raise _quota_error()

    _register(isolated_ai_gateway, "gemini", fake_gemini)
    _register(isolated_ai_gateway, "nemotron", lambda contents, config: _text_chunks(COMPLIANT_CONTENT))

    doc = _make_doc(client)
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)

    assert len(gemini_calls) == 1  # NOT retried — quota skips the same-provider retry
    assert not any("error" in e for e in events)
    done_event = next(e for e in events if "done" in e)
    assert done_event["structure_check"]["valid"] is True

    from pharmagpt import qms_document_database as qdb
    assert "1. Purpose" in qdb.get_document(doc["id"])["content"]

    from pharmagpt.providers import router as ai_router
    assert ai_router._in_cooldown("gemini")  # circuit breaker engaged for this provider


def test_generate_draft_gemini_transient_failure_retries_then_succeeds(client, isolated_ai_gateway):
    calls = []

    def fake_gemini(contents, config):
        calls.append(1)
        if len(calls) == 1:
            raise _transient_error()
        return _text_chunks(COMPLIANT_CONTENT)

    _register(isolated_ai_gateway, "gemini", fake_gemini)
    _register(isolated_ai_gateway, "nemotron", _refuse("nemotron"))  # never needed — gemini's own retry succeeds

    doc = _make_doc(client)
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)

    assert len(calls) == 2  # gateway's bounded retry, transparent to this route
    assert not any("error" in e for e in events)
    done_event = next(e for e in events if "done" in e)
    assert done_event["structure_check"]["valid"] is True


def test_generate_draft_both_providers_unavailable_reports_error(client, isolated_ai_gateway):
    from pharmagpt import qms_document_database as qdb
    from pharmagpt import qms_database as qmsdb

    def fake_down(contents, config):
        raise _transient_error()

    _register(isolated_ai_gateway, "gemini", fake_down)
    _register(isolated_ai_gateway, "nemotron", fake_down)

    doc = _make_doc(client)
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)

    assert not any("chunk" in e for e in events)  # never started — no partial output reached the browser
    assert not any("done" in e for e in events)
    error_event = next(e for e in events if "error" in e)
    # ProviderCallError's sanitized message reaches the client — never the
    # upstream provider's raw response body (router.ProviderCallError's own
    # contract, unchanged from Stage 1/2).
    assert "AI request failed" in error_event["error"]
    assert "backend unavailable" not in error_event["error"]  # raw upstream body never leaks

    assert qdb.get_document(doc["id"])["content"] == ""

    audit_trail = qmsdb.get_audit_trail("document", doc["id"])
    assert any(a["action"] == "AI draft generation failed" for a in audit_trail)


def test_generate_draft_empty_fallback_output_still_reports_failure(client, isolated_ai_gateway):
    """Gemini fails with a fallback-eligible error before any chunk; NVIDIA
    is tried and 'succeeds' in the sense of not raising, but produces zero
    usable text. This must be treated exactly like a zero-usable-chunks
    Gemini response — a failed generation, not a successful empty draft."""
    from pharmagpt import qms_document_database as qdb
    from pharmagpt import qms_database as qmsdb

    def fake_gemini(contents, config):
        raise _quota_error()

    def fake_nemotron(contents, config):
        return iter(())

    _register(isolated_ai_gateway, "gemini", fake_gemini)
    _register(isolated_ai_gateway, "nemotron", fake_nemotron)

    doc = _make_doc(client)
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    events = _sse_events(r)

    assert not any("done" in e for e in events)
    error_event = next(e for e in events if "error" in e)
    assert error_event["error"] == (
        "AI draft generation produced no usable content. No document content was changed. Please try again."
    )
    assert qdb.get_document(doc["id"])["content"] == ""

    audit_trail = qmsdb.get_audit_trail("document", doc["id"])
    failures = [a for a in audit_trail
                if a["action"] == "AI draft generation violated controlled template structure"]
    assert len(failures) == 1

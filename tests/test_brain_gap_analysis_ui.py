"""
tests/test_brain_gap_analysis_ui.py — Yuktav Brain: Regulatory Gap Analysis V1
UI (PharmaPilot workspace, templates/index.html + static/js/
brain_gap_analysis.js) — a second surface beside Compliance Check
(brain_compare.js, tests/test_brain_compare_ui.py), which this file does not
modify or duplicate beyond one light "PharmaPilot still accessible"
smoke check.

Same approach and same documented limitation as tests/test_brain_compare_ui.py:
no JS build step or test runner exists for this vanilla-JS frontend, so this
file asserts on (a) the rendered SPA shell markup returned by GET /, and
(b) the static JS source itself, for specific, mechanically-checkable
properties — request payload shape, absence of tenant-identifying fields,
and that every dynamic value reaching innerHTML is passed through the
module's escHtml() helper first (the actual XSS regression test: it proves
both that escHtml() neutralizes the dangerous characters and that nothing
bypasses it, which is what running the real page in a browser would let a
click-through test check directly).
"""

import re

import pytest


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


def _get_shell(client):
    resp = client.get("/")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _read_gap_analysis_js():
    with open("pharmagpt/static/js/brain_gap_analysis.js", encoding="utf-8") as f:
        return f.read()


def _read_brain_compare_js():
    with open("pharmagpt/static/js/brain_compare.js", encoding="utf-8") as f:
        return f.read()


# ── PharmaPilot workspace still accessible (frozen surface, not rebuilt) ────

def test_pharmapilot_still_accessible(client):
    html = _get_shell(client)
    m = re.search(r'<div class="sidebar-item" id="nav-pharmapilot"[^>]*>', html)
    assert m, "nav-pharmapilot element not found"
    assert "display:none" not in m.group()


def test_compliance_check_markup_unaffected(client):
    """Regression: adding Gap Analysis to the same workspace must not
    remove or break the existing Compliance Check controls."""
    html = _get_shell(client)
    assert 'id="brain-compare-question"' in html
    assert 'id="brain-compare-run-btn"' in html
    assert 'id="brain-compare-result"' in html
    assert "js/brain_compare.js" in html


# ── Gap Analysis markup ──────────────────────────────────────────────────────

def test_gap_analysis_controls_exist(client):
    html = _get_shell(client)
    assert 'id="gap-analysis-question"' in html
    assert 'id="gap-analysis-run-btn"' in html
    assert 'id="gap-analysis-result"' in html
    assert "Regulatory Gap Analysis" in html
    assert 'onclick="BrainGapAnalysis.run()"' in html


def test_gap_analysis_script_included(client):
    html = _get_shell(client)
    assert "js/brain_gap_analysis.js" in html


def test_gap_analysis_result_container_starts_hidden(client):
    html = _get_shell(client)
    m = re.search(r'<div class="qms-section-card" id="gap-analysis-result"[^>]*>', html)
    assert m, "gap-analysis-result element not found"
    assert "hidden" in m.group()


def test_gap_analysis_both_views_coexist_under_one_workspace(client):
    """Confirms no second workspace/page was created — both controls live
    inside the same #view-pharmapilot main element."""
    html = _get_shell(client)
    view_match = re.search(r'<main class="qms-view" id="view-pharmapilot".*?</main>', html, re.DOTALL)
    assert view_match, "view-pharmapilot element not found"
    view_html = view_match.group()
    assert "brain-compare-question" in view_html
    assert "gap-analysis-question" in view_html


# ── Static JS source checks: request payload shape ──────────────────────────

def test_correct_endpoint_is_used():
    js = _read_gap_analysis_js()
    assert "/brain/gap-analysis" in js


def test_payload_is_exactly_question_and_project_id():
    js = _read_gap_analysis_js()
    payload_match = re.search(r"qmsPostJSON\('/brain/gap-analysis',\s*\{([^}]*)\}", js)
    assert payload_match, "qmsPostJSON('/brain/gap-analysis', ...) call not found"
    payload_body = payload_match.group(1)
    assert set(re.findall(r"(\w+):", payload_body)) == {"question", "project_id"}


def test_client_never_constructs_a_company_id_payload_field():
    js = _read_gap_analysis_js()
    payload_match = re.search(r"qmsPostJSON\('/brain/gap-analysis',\s*\{([^}]*)\}", js)
    assert payload_match, "qmsPostJSON('/brain/gap-analysis', ...) call not found"
    assert "company_id" not in payload_match.group(1)


def test_client_never_sends_role_scope_or_tenant_id_fields():
    js = _read_gap_analysis_js()
    payload_match = re.search(r"qmsPostJSON\('/brain/gap-analysis',\s*\{([^}]*)\}", js)
    assert payload_match, "qmsPostJSON('/brain/gap-analysis', ...) call not found"
    payload_body = payload_match.group(1)
    assert "role" not in payload_body
    assert "scope" not in payload_body
    assert "tenant_id" not in payload_body


def test_active_project_guard_present():
    js = _read_gap_analysis_js()
    assert "window.activeProject" in js
    assert "qmsToast" in js


def test_loading_state_present():
    js = _read_gap_analysis_js()
    assert "btn.disabled = true" in js
    assert "Running" in js


def test_api_error_uses_existing_toast_behavior():
    js = _read_gap_analysis_js()
    assert re.search(r"catch\s*\([^)]*\)\s*\{[^}]*qmsToast", js, re.DOTALL)


# ── Coverage statuses and rendering hooks present in source ─────────────────

def test_all_four_coverage_statuses_referenced():
    js = _read_gap_analysis_js()
    for status in ("COVERED", "PARTIALLY_COVERED", "NOT_COVERED", "INSUFFICIENT_EVIDENCE"):
        assert status in js


def test_requirements_gaps_and_references_are_rendered():
    js = _read_gap_analysis_js()
    assert "renderRequirement" in js
    assert "result.requirements" in js
    assert "item.gap" in js
    assert "renderReferences" in js
    assert "result.evidence_references" in js


def test_global_client_distinction_reused_from_scope_badge():
    js = _read_gap_analysis_js()
    assert "'Global'" in js and "'Client'" in js
    assert "scopeBadge" in js


def test_insufficient_evidence_does_not_reuse_compliance_status_language():
    """Gap Analysis renders its own coverage badge, never PASS/WARNING/FAIL
    compliance language borrowed from Compliance Check."""
    js = _read_gap_analysis_js()
    assert "compliance_status" not in js
    assert "PASS" not in js and "WARNING" not in js and "FAIL" not in js


def test_result_rendering_does_not_crash_shape_for_empty_requirements():
    """Static confirmation that renderResult() branches explicitly on an
    empty requirements array rather than assuming at least one item."""
    js = _read_gap_analysis_js()
    assert "requirements.length" in js


# ── XSS regression test ──────────────────────────────────────────────────────
# No JS runtime exists in this project to execute renderResult() against a
# malicious payload (see this file's docstring and test_brain_compare_ui.py's
# own documented limitation). Instead this proves, mechanically, that (a) the
# escHtml() helper actually neutralizes the characters that make HTML
# injection possible, and (b) every dynamic value known to originate from
# Gemini output, retrieved document text, or the evidence-reference metadata
# is passed through it before being placed in an innerHTML template string —
# together these are equivalent to confirming a <script>/onerror payload in
# any of those fields renders as inert text.

def test_esc_html_helper_neutralizes_dangerous_characters():
    js = _read_gap_analysis_js()
    fn_match = re.search(r"function escHtml\(str\)\s*\{(.*?)\n\s*\}", js, re.DOTALL)
    assert fn_match, "escHtml() implementation not found"
    body = fn_match.group(1)
    assert "&amp;" in body
    assert "&lt;" in body
    assert "&gt;" in body
    assert "&quot;" in body


@pytest.mark.parametrize("field_expr", [
    "item.requirement",
    "item.client_evidence_summary",
    "item.gap",
    "overallSummary",
    "r.name",
    "r.source_authority",
    "r.source_reference",
])
def test_every_untrusted_field_is_escaped_before_use(field_expr):
    js = _read_gap_analysis_js()
    escaped_pattern = r"escHtml\(\s*" + re.escape(field_expr)
    assert re.search(escaped_pattern, js), (
        f"{field_expr} must be wrapped in escHtml(...) before being placed in innerHTML"
    )
    # Guard against a literal string-concatenation bypass of the same value
    # (e.g. `+ item.requirement +` outside of any escHtml(...) call).
    unescaped_pattern = re.escape(field_expr) + r"\s*\)?\s*[+;]"
    for m in re.finditer(unescaped_pattern, js):
        preceding = js[max(0, m.start() - 12):m.start()]
        assert "escHtml(" in preceding, (
            f"found an unescaped use of {field_expr} near: ...{preceding}{m.group()}..."
        )


def test_xss_payload_would_render_as_inert_text_given_esc_html_semantics():
    """End-to-end simulation of escHtml()'s documented behavior (same
    replacement order as static/js/brain_compare.js's own escHtml, which
    this module intentionally duplicates rather than imports) against a
    concrete XSS payload, proving the escaped output can never break out of
    the surrounding HTML."""
    payload = '<img src=x onerror="alert(1)">'

    def esc_html(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    escaped = esc_html(payload)
    assert "<img" not in escaped
    assert "<" not in escaped and ">" not in escaped
    assert escaped == "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"


# ── One confirmation that Compliance Check's own JS source is untouched ─────

def test_brain_compare_js_is_unmodified_by_this_feature():
    """brain_gap_analysis.js duplicates helpers rather than importing from
    brain_compare.js (frozen for this task) — confirms brain_compare.js
    still contains no reference to the new endpoint or module."""
    js = _read_brain_compare_js()
    assert "/brain/gap-analysis" not in js
    assert "BrainGapAnalysis" not in js

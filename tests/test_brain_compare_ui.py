"""
tests/test_brain_compare_ui.py — Yuktav Brain: Compliance Check UI
(PharmaPilot workspace, templates/index.html + static/js/brain_compare.js).

Same approach as tests/test_sidebar_coming_soon_removed.py and
tests/test_login_ui.py: no JS build step or test runner exists for this
vanilla-JS frontend, so this file asserts directly on:

  (a) the rendered SPA shell markup returned by GET / — nav visibility,
      the Compliance Check form/result markup, and that Chat is unaffected;
  (b) the static JS source itself, for one specific, mechanically-checkable
      security property — that company_id is never constructed into the
      request payload the client sends.

What this file does NOT and cannot test (documented, not silently skipped):
button click behavior, fetch call execution, badge rendering per status,
and DOM updates are real JavaScript runtime behavior with no test runner in
this project to execute them against — those are verified by code
inspection (see the implementation report), the same limitation every
other frontend feature in this codebase already has.
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


# ── Navigation ────────────────────────────────────────────────────────────────

def test_pharmapilot_nav_item_is_no_longer_hidden(client):
    html = _get_shell(client)
    m = re.search(r'<div class="sidebar-item" id="nav-pharmapilot"[^>]*>', html)
    assert m, "nav-pharmapilot element not found"
    assert "display:none" not in m.group()


def test_pharmapilot_placeholder_copy_is_gone(client):
    html = _get_shell(client)
    assert "Enterprise AI Assistant — coming soon." not in html
    assert "This workspace is a placeholder for a future phase." not in html


def test_chat_nav_and_view_still_present(client):
    """Regression: the new Compliance Check surface must not remove or
    break the existing, working AI Assistant (chat)."""
    html = _get_shell(client)
    assert 'id="nav-chat"' in html
    assert 'id="view-chat"' in html


# ── Compliance Check markup ──────────────────────────────────────────────────

def test_compliance_check_view_markup_present(client):
    html = _get_shell(client)
    assert 'id="view-pharmapilot"' in html
    assert 'id="brain-compare-question"' in html
    assert 'id="brain-compare-run-btn"' in html
    assert 'id="brain-compare-result"' in html
    assert "Compliance Check" in html
    assert "onclick=\"BrainCompare.run()\"" in html


def test_compliance_check_script_included(client):
    html = _get_shell(client)
    assert "js/brain_compare.js" in html


def test_result_container_starts_hidden(client):
    html = _get_shell(client)
    m = re.search(r'<div class="qms-section-card" id="brain-compare-result"[^>]*>', html)
    assert m, "brain-compare-result element not found"
    assert "hidden" in m.group()


# ── Static JS source checks (mechanically verifiable, no runtime needed) ────

def _read_brain_compare_js():
    with open("pharmagpt/static/js/brain_compare.js", encoding="utf-8") as f:
        return f.read()


def test_client_never_constructs_a_company_id_payload_field():
    """The backend (routes/brain.py) resolves company_id from the
    authenticated session — the client must never send one. Checks the
    actual request payload construction site in the shipped source (not
    this file's own explanatory comments, which legitimately mention
    company_id to document why it's absent)."""
    js = _read_brain_compare_js()
    payload_match = re.search(r"qmsPostJSON\('/brain/compare',\s*\{([^}]*)\}", js)
    assert payload_match, "qmsPostJSON('/brain/compare', ...) call not found"
    assert "company_id" not in payload_match.group(1)


def test_client_never_sends_role_or_scope_fields():
    js = _read_brain_compare_js()
    # Only the JSON payload construction site should be checked — "scope"
    # legitimately appears elsewhere in this file as a *response* field
    # (evidence_references[].scope) being rendered, never as a request key.
    payload_match = re.search(r"qmsPostJSON\('/brain/compare',\s*\{([^}]*)\}", js)
    assert payload_match, "qmsPostJSON('/brain/compare', ...) call not found"
    payload_body = payload_match.group(1)
    assert "role" not in payload_body
    assert "scope" not in payload_body
    assert set(re.findall(r"(\w+):", payload_body)) == {"question", "project_id"}

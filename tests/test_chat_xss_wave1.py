"""
tests/test_chat_xss_wave1.py — Regression coverage for AI-02 (PharmaGPT
Production Readiness Audit): static/js/chat.js previously assigned
`marked.parse(text)` directly to `.innerHTML` for AI-authored chat messages
(both the completed-message path and the token-by-token streaming path),
with no sanitization — a stored/reflected XSS vector, since AI output can
echo retrieved document/RAG content verbatim.

This codebase has no JS build step, test runner, or headless-browser
harness (see tests/test_login_ui.py's own docstring for the same
constraint) — these tests exercise the real Flask app and assert on the
served source/markup itself, the same "catch the regression at the source"
approach test_login_ui.py already uses for chat.js's sibling concerns. They
prove the fix is present and wired in; they do not execute JavaScript or a
real DOM, so they cannot themselves render a live payload the way a
browser-based test could.
"""

import re

import pytest


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


def _chat_js_source():
    with open("pharmagpt/static/js/chat.js", encoding="utf-8") as f:
        return f.read()


def test_dompurify_is_loaded_in_the_spa_shell(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "dompurify" in html.lower()
    # Must load before chat.js, which calls DOMPurify.sanitize() at module
    # scope inside renderMarkdown().
    dompurify_pos = html.lower().find("dompurify")
    chat_js_pos = html.find('src="/static/js/chat.js"')
    assert dompurify_pos != -1 and chat_js_pos != -1
    assert dompurify_pos < chat_js_pos


def test_chat_js_defines_a_sanitizing_render_helper():
    source = _chat_js_source()
    assert "function renderMarkdown" in source
    assert re.search(r"DOMPurify\.sanitize\(\s*marked\.parse\(", source), (
        "renderMarkdown() must pass marked.parse()'s output through DOMPurify.sanitize() "
        "before it is used anywhere"
    )


def test_chat_js_never_assigns_raw_marked_parse_to_innerhtml():
    """The actual regression this guards against: `X.innerHTML =
    marked.parse(...)` with no sanitizer in between, for either the
    completed-message path (appendMessage) or the streaming path
    (sendMessage's per-chunk render)."""
    source = _chat_js_source()
    unsafe_pattern = re.compile(r"\.innerHTML\s*=\s*marked\.parse\(")
    assert not unsafe_pattern.search(source), (
        "Found an innerHTML assignment fed directly by marked.parse() with no "
        "DOMPurify.sanitize() wrapper — this is the AI-02 XSS regression."
    )


def test_chat_js_uses_the_sanitizing_helper_for_both_render_sites():
    """Both known call sites (the completed-message bubble in appendMessage,
    and the per-chunk update in the streaming loop) must go through
    renderMarkdown(), not marked.parse() directly."""
    source = _chat_js_source()
    assert source.count("renderMarkdown(") >= 3, (
        "Expected renderMarkdown() to be defined once and called at both "
        "AI-message render sites (appendMessage + streaming loop)"
    )
    # Every remaining innerHTML assignment that renders message content must
    # route through renderMarkdown(), not call marked.parse() itself.
    for line in source.splitlines():
        if ".innerHTML" in line and "marked.parse" in line:
            assert "renderMarkdown" not in line or "function renderMarkdown" in line

"""
tests/test_login_ui.py — IMPLEMENTATION_ROADMAP.md Phase 2 step 2.6.

The project has no JS build step or test runner (vanilla JS, no bundler),
so — consistent with tests/test_app_auth_integration.py's approach for
step 2.5 — these tests exercise the real Flask app and assert the rendered
SPA shell actually contains the login UI's markup, ids, and script wiring
that static/js/auth.js depends on. This catches the class of regression
that matters most here: an id renamed or removed in templates/index.html
that would silently break auth.js's DOM lookups.
"""

import pytest


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


def _get_shell(client):
    resp = client.get("/")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_login_view_markup_present(client):
    html = _get_shell(client)
    assert 'id="login-view"' in html
    assert 'id="login-form"' in html
    assert 'id="login-email"' in html
    assert 'id="login-password"' in html
    assert 'id="login-remember"' in html
    assert 'id="login-error"' in html
    assert 'id="login-submit"' in html
    assert 'id="login-spinner"' in html


def test_session_check_view_present(client):
    html = _get_shell(client)
    assert 'id="session-check-view"' in html


def test_user_badge_and_logout_present(client):
    html = _get_shell(client)
    assert 'id="user-badge"' in html
    assert 'id="user-badge-name"' in html
    assert 'id="btn-logout"' in html


def test_auth_js_loads_before_business_logic_scripts(client):
    html = _get_shell(client)
    auth_pos = html.find("js/auth.js")
    workspace_pos = html.find("js/workspace.js")
    dashboard_pos = html.find("js/dashboard.js")

    assert auth_pos != -1, "auth.js must be included in the SPA shell"
    assert auth_pos < workspace_pos, "auth.js must load before workspace.js"
    assert auth_pos < dashboard_pos, "auth.js must load before dashboard.js"


def test_login_view_hidden_by_default_in_markup(client):
    # Server-rendered markup starts hidden; auth.js decides visibility at
    # runtime based on stored-session state. If this ever renders visible
    # by default, a logged-in user would see a login-screen flash on load.
    html = _get_shell(client)
    login_view_start = html.find('id="login-view"')
    assert login_view_start != -1
    surrounding = html[login_view_start:login_view_start + 200]
    assert 'style="display:none"' in surrounding

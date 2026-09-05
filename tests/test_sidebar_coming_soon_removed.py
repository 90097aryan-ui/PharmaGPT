"""
tests/test_sidebar_coming_soon_removed.py — regression coverage for the
removal of the five static "Coming Soon" placeholder entries from the
Quality Management sidebar section (pharmagpt/templates/index.html).

Same approach as tests/test_login_ui.py: no JS build step or test runner
for this vanilla-JS frontend, so assert directly on the rendered SPA shell
markup returned by GET /. These items previously rendered unconditionally
(dimmed via inline style, not gated by data-workspace or removed) regardless
of the viewer's role or workspace access — the requirement is that they no
longer exist in the DOM at all, not merely that they're hidden/disabled.
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


def test_coming_soon_labels_absent_from_rendered_markup(client):
    html = _get_shell(client)
    assert "Coming Soon" not in html


def test_coming_soon_placeholder_modules_absent_from_rendered_markup(client):
    html = _get_shell(client)
    for label in ("Training", "Complaints", "Audit Management", "Supplier Quality", "Management Review"):
        assert label not in html


def test_quality_section_real_nav_items_still_present(client):
    # The removal must not have taken any real, wired-up nav item with it.
    # "nav-qm-documents" (a duplicate Document Control entry pointing to the
    # same view-qms-documents destination as "nav-qms-documents") was
    # intentionally removed by the Yuktav sidebar redesign — Document
    # Control is now a primary module of its own, and "nav-qms-documents"
    # is its retained, still-wired-up "Documents" entry.
    html = _get_shell(client)
    for nav_id in (
        "nav-qms-dashboard",
        "nav-qms-deviations",
        "nav-qms-capa",
        "nav-qms-change-control",
        "nav-qms-documents",
    ):
        assert f'id="{nav_id}"' in html

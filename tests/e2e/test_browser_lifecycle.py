"""
Browser end-to-end test: the complete approval lifecycle of URS, DQ, IQ, OQ and
PQ, driven through the real approval UI in a real (headless) Chrome against an
isolated server and throwaway database.

Covers, per type: author-only submission, wrong e-signature password, unauthorized
department refusal, rejection with reason, resubmission, the full seven-signature
chain (including the parallel Engineering/Production stage), revision after
approval (not DQ), the DQ training gate, Make Effective, and Knowledge Base
publication only at Effective; and for protocols: IQ, OQ and PQ approve
independently and the parent Qualification only becomes Effective when all three are.

Skips (loudly) if no Chrome/Edge is installed. Set E2E_BROWSER to override the binary.
"""

import json
import os
import re
import subprocess

import pytest

from tests.e2e.e2e_server import E2EServer

CANDIDATES = [
    os.environ.get("E2E_BROWSER", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]


def _browser():
    return next((c for c in CANDIDATES if c and os.path.exists(c)), None)


@pytest.fixture()
def server(db_path, monkeypatch):
    srv = E2EServer(monkeypatch, db_path)
    url = srv.start()
    yield url
    srv.stop()


def _run_browser(server, tmp_path):
    out = subprocess.run(
        [_browser(), "--headless=new", "--disable-gpu", "--no-sandbox", "--disable-extensions",
         f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=600000", "--dump-dom",
         f"{server}/e2e/harness"],
        capture_output=True, text=True, timeout=600)
    match = re.search(r'<pre id="result">(.*?)</pre>', out.stdout, re.S)
    assert match, f"no result in DOM (exit {out.returncode}): {out.stdout[-500:]} {out.stderr[-500:]}"
    import html
    return json.loads(html.unescape(match.group(1)))


@pytest.mark.skipif(_browser() is None, reason="no Chrome/Edge available for the browser test")
def test_complete_approval_lifecycle_in_a_real_browser(server, tmp_path):
    payload = _run_browser(server, tmp_path)
    assert payload.get("done"), payload
    failed = [r for r in payload["results"] if not r["ok"]]
    assert not failed, "\n".join(f"- {r['name']}: {r['detail']}" for r in failed)
    # Sanity: the scenario really exercised everything (not a vacuous pass).
    assert payload["total"] >= 120, payload["total"]
    names = " ".join(r["name"] for r in payload["results"])
    for must in ("URS:", "DQ:", "IQ:", "OQ:", "PQ:", "non-author", "wrong e-signature password", "unauthorized department",
                 "Knowledge Base", "independent of IQ", "parent Qualification is Effective only after all three"):
        assert must in names, must
    print(f"\nbrowser lifecycle: {payload['total']} checks, all passed")


@pytest.mark.skipif(_browser() is None, reason="no Chrome/Edge available for the browser test")
def test_browser_test_is_not_vacuous_it_fails_when_a_control_is_removed(server, tmp_path, monkeypatch):
    """Mutation control: with department enforcement switched OFF the same browser
    scenario must report the unauthorized-department check as failed."""
    from pharmagpt import config
    monkeypatch.setattr(config, "VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT", False)
    payload = _run_browser(server, tmp_path)
    failed = [r["name"] for r in payload["results"] if not r["ok"]]
    assert any("unauthorized department cannot sign" in n for n in failed), failed

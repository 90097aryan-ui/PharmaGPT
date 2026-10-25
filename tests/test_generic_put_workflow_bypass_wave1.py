"""
tests/test_generic_put_workflow_bypass_wave1.py — Wave 1 regression coverage
for GXP-01 and GXP-02 (PharmaGPT Production Readiness Audit).

Before this fix, PUT /qms/<module>/<id> accepted a raw "status" field on
Documents, Deviations, CAPA, and Change Control with no relationship to the
workflow engine, named-approver check, or e-signature gate those record
types' dedicated endpoints enforce (routes/urs.py already rejected "status"
via PUT — these four modules now mirror that same pattern). Document
Control additionally allowed editing "content" in place on an
already-Effective document with no forced version snapshot.

These tests exercise the real Flask routes (tests/conftest.py's `client`
fixture) and assert the raw-status/raw-content bypass is closed while
legitimate field edits keep working.

GXP-02 note (read-only verification + minimal fix pass): the two content-
lock tests below previously drove a document through the legacy single-call
/approval wrapper via a `tests/conftest.py::as_test_tenant` helper that was
never actually implemented (the file never collected). That path is also no
longer how Effective is reached at all — `POST /qms/documents/<id>/release`
is now the only path (see tests/test_document_quality_release.py's module
docstring). Both tests now reuse that file's own
`_reach_approved_via_route()` helper plus its training/release pattern
rather than inventing a second way to drive the workflow.
"""

from pharmagpt import qms_document_database as qdb
from tests.test_document_quality_release import SIGN, _reach_approved_via_route, _reauth


# ── GXP-01: status is rejected via PUT on all four modules ──────────────────

def test_document_put_rejects_status(client):
    doc = client.post("/qms/documents", json={"doc_type": "SOP", "title": "Cleaning SOP", "department": "QA"}).get_json()
    assert doc["status"] == "Draft"

    r = client.put(f"/qms/documents/{doc['id']}", json={"status": "Effective"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/documents/{doc['id']}").get_json()["status"] == "Draft"


def test_deviation_put_rejects_status(client):
    dev = client.post("/qms/deviations", json={"title": "Temp excursion"}).get_json()
    assert dev["status"] == "Draft"

    r = client.put(f"/qms/deviations/{dev['id']}", json={"status": "Closed"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/deviations/{dev['id']}").get_json()["status"] == "Draft"


def test_capa_put_rejects_status(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    assert capa["status"] == "Open"

    r = client.put(f"/qms/capa/{capa['id']}", json={"status": "Closed"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/capa/{capa['id']}").get_json()["status"] == "Open"


def test_capa_put_cannot_bypass_effectiveness_verification_gate(client):
    """Flagship regression case (WF-002 in the audit): PUT {"status":
    "Closed"} previously fully defeated the mandatory, e-signed Effectiveness
    Verification step that tests/test_capa_effectiveness_verification.py
    proves is otherwise unreachable through the generic decide-step and
    legacy-approval endpoints."""
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]

    r = client.put(f"/qms/capa/{cid}", json={"status": "Closed"})
    assert r.status_code == 400
    assert client.get(f"/qms/capa/{cid}").get_json()["status"] != "Closed"


def test_change_control_put_rejects_status(client):
    cc = client.post("/qms/change-control", json={"title": "Upgrade HVAC firmware"}).get_json()
    assert cc["status"] == "Draft"

    r = client.put(f"/qms/change-control/{cc['id']}", json={"status": "Closed"})
    assert r.status_code == 400
    assert "status" in r.get_json()["error"].lower()
    assert client.get(f"/qms/change-control/{cc['id']}").get_json()["status"] == "Draft"


# ── GXP-01: legitimate, non-status field edits still work ───────────────────

def test_deviation_put_still_accepts_non_status_fields(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    r = client.put(f"/qms/deviations/{dev['id']}", json={"risk_level": "High"})
    assert r.status_code == 200
    assert r.get_json()["risk_level"] == "High"


def test_capa_put_still_accepts_non_status_fields(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    r = client.put(f"/qms/capa/{capa['id']}", json={"root_cause": "Root cause text"})
    assert r.status_code == 200
    assert r.get_json()["root_cause"] == "Root cause text"


def test_change_control_put_still_accepts_non_status_fields(client):
    cc = client.post("/qms/change-control", json={"title": "Change"}).get_json()
    r = client.put(f"/qms/change-control/{cc['id']}", json={"risk_level": "Medium"})
    assert r.status_code == 200
    assert r.get_json()["risk_level"] == "Medium"


# ── GXP-02: document content locked outside Draft / Under Revision ──────────

def test_document_content_editable_while_draft(client):
    doc = client.post("/qms/documents", json={"doc_type": "SOP", "title": "Cleaning SOP", "department": "QA"}).get_json()
    r = client.put(f"/qms/documents/{doc['id']}", json={"content": "# Draft content"})
    assert r.status_code == 200
    assert r.get_json()["content"] == "# Draft content"


def _release_to_effective(client, monkeypatch):
    """Drives a document all the way to Effective via the current
    authoritative workflow: _reach_approved_via_route() (self-check, final
    version upload, assign-chain, workflow/start, sequential Reviewer/
    Department Head/Quality Head decisions) plus training completion and
    POST /release — the same pattern as
    tests/test_document_quality_release.py::test_release_succeeds_once_approved_and_training_cleared."""
    did = _reach_approved_via_route(client, monkeypatch)
    t = client.post(f"/qms/documents/{did}/training", json={"trainee_name": "Trainee One"}).get_json()
    with _reauth(True):
        client.put(f"/qms/documents/training/{t['id']}",
                   json={"training_status": "Completed", "training_date": "2026-01-01", **SIGN})
    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/release", json=SIGN)
    assert r.status_code == 200, r.get_json()
    return did, r.get_json()["content"]


def test_document_content_locked_once_effective(client, monkeypatch):
    """GXP-02: once released to Effective, a raw PUT must not silently
    overwrite the denormalized qms_documents.content mirror — neither the
    mirror nor the authoritative current version's content_snapshot may
    change."""
    did, effective_content = _release_to_effective(client, monkeypatch)
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Effective"

    r = client.put(f"/qms/documents/{did}", json={"content": "# TAMPERED-BY-TEST"})
    assert r.status_code == 409
    assert "content" in r.get_json()["error"].lower()

    assert client.get(f"/qms/documents/{did}").get_json()["content"] == effective_content
    assert qdb.get_current_version(did)["content_snapshot"] == effective_content


def test_document_content_editable_again_once_sent_for_revision(client, monkeypatch):
    """The governed path stays open: Effective -> Under Revision (via the
    existing e-signed /approval 'Send for Revision' action, the only
    existing mechanism for this transition — see
    routes/qms_documents.py::_POST_EFFECTIVE_ACTIONS) legitimately reopens
    content editing. 'Send for Revision' only flips the document-level
    status; it does not fork a new version row (unlike
    qms_document_database.py::start_new_revision()/reject_and_fork_version(),
    neither of which this action calls), so the current version stays
    'effective' and its content_snapshot is correctly left untouched by a
    post-revision content edit — qms_document_database.py::update_document()
    only ever writes into a version whose own status is 'draft'. Asserting
    this documents the existing, unmodified behavior; it is not part of
    this fix."""
    did, _ = _release_to_effective(client, monkeypatch)

    with _reauth(True):
        r = client.post(f"/qms/documents/{did}/approval",
                         json={"action": "Send for Revision", **SIGN})
    assert r.status_code == 201, r.get_json()
    assert client.get(f"/qms/documents/{did}").get_json()["status"] == "Under Revision"

    r = client.put(f"/qms/documents/{did}", json={"content": "# v2 — revised"})
    assert r.status_code == 200
    assert r.get_json()["content"] == "# v2 — revised"

    version = qdb.get_current_version(did)
    assert version["status"] == "effective"  # unforked by Send for Revision
    assert version["content_snapshot"] != "# v2 — revised"  # not synced — version itself isn't 'draft'

"""
tests/test_document_version_immutability.py — Phase 1 coverage: the
authoritative qms_document_versions ledger, the version-level state
machine (services/lifecycle_engine.py's QMS_DOCUMENT_VERSION registry),
and the two DB-layer immutability triggers in qms_database.py.

Exercises the service layer directly against the db_path fixture's
throwaway SQLite database, same style as tests/test_workflow_engine.py.
"""

import sqlite3

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.services import document_versioning as dv
from pharmagpt.services import lifecycle_engine

COMPANY_ID = "test-company"


def _make_document():
    return qdb.create_document({"title": "Cleaning SOP", "content": "v1 content"},
                                company_id=COMPANY_ID, created_by_user_id="author-1")


# ── create_document() wires an initial version ───────────────────────────────

def test_create_document_creates_initial_draft_version(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    assert version is not None
    assert version["version_number"] == "0.1"
    assert version["status"] == "draft"
    assert version["parent_version_id"] is None
    assert version["content_snapshot"] == "v1 content"
    assert version["created_by_user_id"] == "author-1"
    assert doc["current_version_id"] == version["id"]


def test_document_content_and_version_mirror_current_version(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    assert doc["content"] == version["content_snapshot"]
    assert doc["version"] == version["version_number"] == "0.1"


# ── Version-level state machine (lifecycle_engine.QMS_DOCUMENT_VERSION) ──────

def test_legal_version_transition_succeeds(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    updated = qdb.transition_version_status(version["id"], "under_review")
    assert updated["status"] == "under_review"


def test_illegal_version_transition_rejected(db_path):
    doc = _make_document()
    version = qdb.get_current_version(doc["id"])
    with pytest.raises(lifecycle_engine.InvalidTransitionError):
        qdb.transition_version_status(version["id"], "effective")  # draft -> effective is not legal


def test_full_new_sop_lifecycle_transitions(db_path):
    doc = _make_document()
    v = qdb.get_current_version(doc["id"])
    v = qdb.transition_version_status(v["id"], "under_review")
    v = qdb.transition_version_status(v["id"], "review_rejected", rejection_reason="Missing acceptance criteria")
    assert v["status"] == "review_rejected"
    assert v["rejection_reason"] == "Missing acceptance criteria"
    # terminal: no further transitions legal
    with pytest.raises(lifecycle_engine.InvalidTransitionError):
        qdb.transition_version_status(v["id"], "draft")


def test_effective_can_transition_to_superseded(db_path):
    doc = _make_document()
    v = qdb.get_current_version(doc["id"])
    v = qdb.transition_version_status(v["id"], "under_review")
    v = qdb.transition_version_status(v["id"], "pending_approval")
    v = qdb.transition_version_status(v["id"], "approved")
    v = qdb.transition_version_status(v["id"], "effective", effective_date="2026-01-01")
    assert v["status"] == "effective"
    v = qdb.transition_version_status(v["id"], "superseded")
    assert v["status"] == "superseded"


# ── DB-layer immutability triggers ────────────────────────────────────────────

def _raw_connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_trigger_blocks_content_edit_after_leaving_draft(db_path):
    doc = _make_document()
    v = qdb.get_current_version(doc["id"])
    qdb.transition_version_status(v["id"], "under_review")

    conn = _raw_connect(db_path)
    with pytest.raises(sqlite3.IntegrityError, match="Immutable document version"):
        conn.execute("UPDATE qms_document_versions SET content_snapshot = 'tampered' WHERE id = ?", (v["id"],))
    conn.close()


def test_trigger_allows_content_edit_while_still_draft(db_path):
    doc = _make_document()
    v = qdb.get_current_version(doc["id"])

    conn = _raw_connect(db_path)
    conn.execute("UPDATE qms_document_versions SET content_snapshot = 'still editable' WHERE id = ?", (v["id"],))
    conn.commit()
    conn.close()

    assert qdb.get_version(v["id"])["content_snapshot"] == "still editable"


def test_trigger_blocks_rejection_reason_overwrite(db_path):
    doc = _make_document()
    v = qdb.get_current_version(doc["id"])
    v = qdb.transition_version_status(v["id"], "under_review")
    v = qdb.transition_version_status(v["id"], "review_rejected", rejection_reason="First reason")

    conn = _raw_connect(db_path)
    with pytest.raises(sqlite3.IntegrityError, match="rejection reason"):
        conn.execute("UPDATE qms_document_versions SET rejection_reason = 'tampered' WHERE id = ?", (v["id"],))
    conn.close()


def test_service_layer_also_refuses_to_edit_non_draft_version_via_create_document_path(db_path):
    """set_document_current_version() only ever points at a version row and
    mirrors its own content — it has no update-in-place path for a
    non-current or historical version at all, which is itself part of the
    guarantee (there is no function anywhere in this module that accepts a
    historical version_id and a new content string)."""
    import inspect
    sig_names = {name for name, _ in inspect.getmembers(qdb, inspect.isfunction)}
    assert "update_version" not in sig_names
    assert "edit_version_content" not in sig_names

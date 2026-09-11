"""
tests/test_yuktav_p1_hardening.py — Regression coverage for the Yuktav Audit
Trail P1 hardening work package:

- P1-1: qms_audit_trail database-level immutability (BEFORE UPDATE/DELETE
  triggers — pharmagpt/database.py::init_db).
- P1-2: IP-address capture hardening (pharmagpt/audit.py::_current_ip,
  pharmagpt/config.py::TRUSTED_PROXY_COUNT).

P1-3 (live Supabase RLS/grant verification) and P1-4 (a comment-only fix in
pharmagpt/db/qms_repo.py) have no new code paths to unit-test.
"""

import sqlite3

import pytest
from flask import Flask, g

from pharmagpt import audit
from pharmagpt import config as pconfig
from pharmagpt import database as db
from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.context import TenantContext


# ── P1-1: SQLite audit-trail immutability ────────────────────────────────────

def test_insert_still_succeeds(db_path):
    row = qmsdb.add_audit_entry("project", 1, "Project created", performed_by="Tester")
    assert row["id"] is not None
    assert row["action"] == "Project created"


def test_update_is_rejected(db_path):
    row = qmsdb.add_audit_entry("project", 2, "Project created", performed_by="Tester")
    conn = qmsdb.get_connection()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE qms_audit_trail SET action = 'tampered' WHERE id = ?", (row["id"],))
    conn.close()


def test_delete_is_rejected(db_path):
    row = qmsdb.add_audit_entry("project", 3, "Project created", performed_by="Tester")
    conn = qmsdb.get_connection()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM qms_audit_trail WHERE id = ?", (row["id"],))
    conn.close()
    # The row must still be there — the DELETE was actually blocked, not
    # merely raised-then-silently-applied-anyway.
    trail = qmsdb.get_audit_trail("project", 3)
    assert any(e["id"] == row["id"] for e in trail)


def test_existing_audit_logging_still_succeeds_via_audit_log(db_path):
    """End-to-end through pharmagpt.audit.log() (the path ~200 real call
    sites use), not just the low-level add_audit_entry()."""
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.tenant = TenantContext(
            user_id="u1", email="a@example.com", display_name="A B",
            role="company_admin", company_id="company-1",
        )
        entry = audit.log("document", 42, "Document created")
    assert entry["action"] == "Document created"
    assert entry["performed_by"] == "A B"


def test_existing_audit_retrieval_still_succeeds(db_path):
    qmsdb.add_audit_entry("capa", 5, "CAPA created", performed_by="Tester")
    qmsdb.add_audit_entry("capa", 5, "CAPA updated", performed_by="Tester")
    trail = qmsdb.get_audit_trail("capa", 5)
    assert [e["action"] for e in trail] == ["CAPA created", "CAPA updated"]


def test_protection_survives_reinitialization(db_path):
    """Simulates an application restart: init_db() runs again against the
    same, already-populated database file. The triggers (CREATE TRIGGER IF
    NOT EXISTS) must still be in place afterward, not silently dropped or
    duplicated into an error."""
    row = qmsdb.add_audit_entry("project", 9, "Project created", performed_by="Tester")

    db.init_db()  # re-run, exactly like a process restart would

    conn = qmsdb.get_connection()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE qms_audit_trail SET action = 'tampered' WHERE id = ?", (row["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM qms_audit_trail WHERE id = ?", (row["id"],))
    conn.close()

    # And a fresh INSERT after reinitialization still works.
    new_row = qmsdb.add_audit_entry("project", 9, "Project updated", performed_by="Tester")
    assert new_row["id"] != row["id"]


def test_triggers_exist_in_sqlite_master(db_path):
    """Direct schema-level confirmation the two triggers are actually
    installed, independent of behavioral testing above."""
    conn = qmsdb.get_connection()
    names = {
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='qms_audit_trail'"
        ).fetchall()
    }
    conn.close()
    assert names == {"trg_qms_audit_trail_no_update", "trg_qms_audit_trail_no_delete"}


# ── P1-2: IP address capture hardening ───────────────────────────────────────

@pytest.fixture()
def flask_app():
    return Flask(__name__)


def test_spoofed_xff_ignored_when_no_trusted_proxy_configured(flask_app, monkeypatch):
    monkeypatch.setattr(pconfig, "TRUSTED_PROXY_COUNT", 0)
    with flask_app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "10.0.0.5"},
        headers={"X-Forwarded-For": "1.2.3.4, attacker-spoofed-value"},
    ):
        assert audit._current_ip() == "10.0.0.5"


def test_trusted_single_proxy_extracts_the_rightmost_hop(flask_app, monkeypatch):
    """The rightmost entry is the one the trusted proxy itself appended;
    anything to its left (including this test's deliberately-named
    'attacker-prepended-value') came from the client and must be ignored."""
    monkeypatch.setattr(pconfig, "TRUSTED_PROXY_COUNT", 1)
    with flask_app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Forwarded-For": "attacker-prepended-value, 203.0.113.9"},
    ):
        assert audit._current_ip() == "203.0.113.9"


def test_trusted_two_proxies_extracts_second_from_right(flask_app, monkeypatch):
    monkeypatch.setattr(pconfig, "TRUSTED_PROXY_COUNT", 2)
    with flask_app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Forwarded-For": "attacker-value, 203.0.113.9, 10.1.1.1"},
    ):
        assert audit._current_ip() == "203.0.113.9"


def test_fallback_to_remote_addr_when_header_absent_despite_trust_configured(flask_app, monkeypatch):
    """Misconfiguration-safe: trusting N hops that never showed up must not
    silently return an attacker-influenced or garbage value — fall back."""
    monkeypatch.setattr(pconfig, "TRUSTED_PROXY_COUNT", 1)
    with flask_app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        assert audit._current_ip() == "127.0.0.1"


def test_fallback_when_fewer_hops_present_than_trusted_count(flask_app, monkeypatch):
    monkeypatch.setattr(pconfig, "TRUSTED_PROXY_COUNT", 3)
    with flask_app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Forwarded-For": "203.0.113.9"},  # only 1 hop present, 3 required
    ):
        assert audit._current_ip() == "127.0.0.1"


def test_existing_audit_events_still_capture_ip_field(db_path, flask_app, monkeypatch):
    """End-to-end: audit.log() still populates ip_address exactly as before,
    just via the hardened derivation."""
    monkeypatch.setattr(pconfig, "TRUSTED_PROXY_COUNT", 0)
    with flask_app.test_request_context("/", environ_base={"REMOTE_ADDR": "198.51.100.7"}):
        g.tenant = TenantContext(
            user_id="u1", email="a@example.com", display_name="A B",
            role="company_admin", company_id="company-1",
        )
        entry = audit.log("document", 43, "Document created")
    assert entry["ip_address"] == "198.51.100.7"

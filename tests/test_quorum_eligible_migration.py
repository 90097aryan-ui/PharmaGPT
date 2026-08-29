"""
Regression coverage for the quorum_eligible migration-ordering bug that
crashed Oracle production (sqlite3.OperationalError: no such column:
quorum_eligible) when init_db() ran QMS_SCHEMA's executescript() against a
database that already had qms_workflow_template_steps/
qms_workflow_instance_steps, but not yet the quorum_eligible column.

Root cause: the Document Control redesign's quorum_eligible backfill UPDATE
used to live inside QMS_SCHEMA (qms_database.py), which runs via
conn.executescript() in database.py's init_db() BEFORE the
_add_column_if_missing() calls that actually add the column on an existing
database (CREATE TABLE IF NOT EXISTS is a no-op once the table already
exists). The fix moves that UPDATE out of QMS_SCHEMA into database.py,
positioned after the quorum_eligible ALTERs. These tests exercise both the
fresh-database path (untouched by the fix) and the existing-database
upgrade path (what actually crashed Oracle), reconstructed here by dropping
quorum_eligible from an otherwise fully-initialized database rather than by
copying or modifying any real database.
"""

import sqlite3

import pytest

from pharmagpt import database as db


def _cols(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _drop_column(conn, table, column):
    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    conn.commit()


def test_fresh_database_initializes_successfully(db_path):
    """db_path already calls init_db() once against a brand-new file — this
    just makes the assertion explicit and confirms quorum_eligible exists
    via the CREATE TABLE path (the case the original bug never affected)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert "quorum_eligible" in _cols(conn, "qms_workflow_template_steps")
    assert "quorum_eligible" in _cols(conn, "qms_workflow_instance_steps")
    conn.close()


def test_existing_db_missing_quorum_eligible_on_template_steps_initializes(db_path):
    """Reproduces the exact Oracle upgrade scenario for
    qms_workflow_template_steps: a database that already has the table, just
    not the column. Before the fix this raised
    sqlite3.OperationalError: no such column: quorum_eligible."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _drop_column(conn, "qms_workflow_template_steps", "quorum_eligible")
    assert "quorum_eligible" not in _cols(conn, "qms_workflow_template_steps")
    conn.close()

    db.init_db()  # must not raise

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert "quorum_eligible" in _cols(conn, "qms_workflow_template_steps")
    conn.close()


def test_existing_db_missing_quorum_eligible_on_instance_steps_initializes(db_path):
    """Same reproduction for qms_workflow_instance_steps specifically."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _drop_column(conn, "qms_workflow_instance_steps", "quorum_eligible")
    assert "quorum_eligible" not in _cols(conn, "qms_workflow_instance_steps")
    conn.close()

    db.init_db()  # must not raise

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert "quorum_eligible" in _cols(conn, "qms_workflow_instance_steps")
    conn.close()


def test_existing_db_with_both_columns_already_present_remains_successful(db_path):
    """A database that already has quorum_eligible on both tables (i.e. one
    that already ran the fixed init_db() once) must still initialize
    cleanly — _add_column_if_missing() must correctly no-op."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert "quorum_eligible" in _cols(conn, "qms_workflow_template_steps")
    assert "quorum_eligible" in _cols(conn, "qms_workflow_instance_steps")
    conn.close()

    db.init_db()  # already present on both tables — must not raise

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert "quorum_eligible" in _cols(conn, "qms_workflow_template_steps")
    assert "quorum_eligible" in _cols(conn, "qms_workflow_instance_steps")
    conn.close()


def test_quorum_eligible_backfill_still_executes_correctly(db_path):
    """The relocated UPDATE must still apply the exact same, unbroadened
    scope: quorum_eligible=0 for DOCUMENT_WORKFLOW_V1's four named steps
    only, quorum_eligible left at its default (1) for every other step."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT s.step_key, s.quorum_eligible
        FROM qms_workflow_template_steps s
        JOIN qms_workflow_templates t ON t.id = s.template_id
        WHERE t.workflow_key = 'DOCUMENT_WORKFLOW_V1'
    """).fetchall()
    assert rows, "DOCUMENT_WORKFLOW_V1 template steps should exist after init_db()"

    backfilled = {"under_review", "department_head_approval", "quality_head_approval", "effective"}
    for row in rows:
        expected = 0 if row["step_key"] in backfilled else 1
        assert row["quorum_eligible"] == expected, (
            f"step_key={row['step_key']} expected quorum_eligible={expected}, "
            f"got {row['quorum_eligible']}"
        )

    # A step belonging to a different workflow template must never be
    # touched by this WHERE-scoped backfill (WHERE clause unchanged).
    other = conn.execute("""
        SELECT s.quorum_eligible
        FROM qms_workflow_template_steps s
        JOIN qms_workflow_templates t ON t.id = s.template_id
        WHERE t.workflow_key != 'DOCUMENT_WORKFLOW_V1'
    """).fetchall()
    for row in other:
        assert row["quorum_eligible"] == 1

    conn.close()


def test_init_db_is_idempotent_when_run_repeatedly(db_path):
    """Running init_db() three times in a row (simulating repeated gunicorn
    worker boots against the same file) must not raise, must not duplicate
    rows, and must not change quorum_eligible's backfilled values."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    before_steps = conn.execute("SELECT COUNT(*) c FROM qms_workflow_template_steps").fetchone()["c"]
    conn.close()

    db.init_db()
    db.init_db()
    db.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    after_steps = conn.execute("SELECT COUNT(*) c FROM qms_workflow_template_steps").fetchone()["c"]
    assert after_steps == before_steps, "repeated init_db() must not duplicate seeded rows"

    backfilled = conn.execute("""
        SELECT quorum_eligible FROM qms_workflow_template_steps s
        JOIN qms_workflow_templates t ON t.id = s.template_id
        WHERE t.workflow_key = 'DOCUMENT_WORKFLOW_V1' AND s.step_key = 'effective'
    """).fetchone()
    assert backfilled["quorum_eligible"] == 0
    conn.close()


def test_no_unrelated_schema_or_data_altered_by_the_fix(db_path):
    """Dropping quorum_eligible and re-running init_db() (the upgrade path
    the fix targets) must not touch unrelated tables or pre-existing,
    unrelated row data anywhere else in the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO projects (name, equipment_name) VALUES ('Sentinel Project', 'Sentinel Equip')")
    conn.commit()
    tables_before = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    _drop_column(conn, "qms_workflow_template_steps", "quorum_eligible")
    conn.close()

    db.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables_after = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert tables_before.issubset(tables_after), "init_db() must never drop an existing table"

    sentinel = conn.execute(
        "SELECT name, equipment_name FROM projects WHERE name = 'Sentinel Project'"
    ).fetchone()
    assert sentinel is not None
    assert sentinel["equipment_name"] == "Sentinel Equip"
    conn.close()


def test_critical_reproduction_of_oracle_upgrade_scenario(db_path):
    """CRITICAL: reconstructs Oracle's exact pre-migration shape — an
    existing database whose Document Control tables predate quorum_eligible
    entirely — without touching any real database. Confirms init_db() no
    longer raises sqlite3.OperationalError: no such column: quorum_eligible,
    and that the schema converges to the same end state as a fresh database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _drop_column(conn, "qms_workflow_template_steps", "quorum_eligible")
    _drop_column(conn, "qms_workflow_instance_steps", "quorum_eligible")
    conn.close()

    try:
        db.init_db()
    except sqlite3.OperationalError as exc:
        pytest.fail(f"init_db() raised on an existing pre-quorum_eligible database: {exc}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert "quorum_eligible" in _cols(conn, "qms_workflow_template_steps")
    assert "quorum_eligible" in _cols(conn, "qms_workflow_instance_steps")
    effective_step = conn.execute("""
        SELECT s.quorum_eligible FROM qms_workflow_template_steps s
        JOIN qms_workflow_templates t ON t.id = s.template_id
        WHERE t.workflow_key = 'DOCUMENT_WORKFLOW_V1' AND s.step_key = 'effective'
    """).fetchone()
    assert effective_step["quorum_eligible"] == 0
    conn.close()

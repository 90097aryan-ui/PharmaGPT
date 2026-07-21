"""
tests/test_projects_merge.py — Phase 2 Module 1: merging the Validation
Workspace (val_projects/val_audit_trail) into the unified `projects` table.

Covers: create_project()/update_project() with the merged fields, the
_migrate_val_projects() copy (including idempotency and audit-trail
migration), and that get_dashboard_stats()'s response shape/keys are
unchanged by the re-sourcing.
"""

from pharmagpt import database as db
from pharmagpt import qms_database
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID


def test_create_project_accepts_merged_fields(db_path):
    project = db.create_project(
        name="HPLC IQ", equipment_name="Agilent HPLC 1260", manufacturer="Agilent",
        department="QC", validation_type="IQ/OQ/PQ",
        owner="Jane Doe", approver="John Smith", target_date="2026-12-01",
        risk_category="High", status="In Progress", model="1260 Infinity",
        location="Lab 3", protocol_number="PRO-001", report_number="REP-001",
    company_id="test-company-1")
    assert project["owner"] == "Jane Doe"
    assert project["target_date"] == "2026-12-01"
    assert project["status"] == "In Progress"

    fetched = db.get_project(project["id"])
    assert fetched["approver"] == "John Smith"
    assert fetched["protocol_number"] == "PRO-001"


def test_create_project_backward_compatible_without_merged_fields(db_path):
    """Old-style call with only the original five positional args must still work."""
    project = db.create_project(
        name="Legacy Project", equipment_name="GC", manufacturer="Shimadzu",
        department="QC", validation_type="OQ",
    company_id="test-company-1")
    assert project["owner"] == ""
    assert project["target_date"] is None
    assert project["status"] == "In Progress"


def test_update_project_merged_fields(db_path):
    project = db.create_project(
        name="Autoclave PQ", equipment_name="Autoclave", manufacturer="Getinge",
        department="Sterile", validation_type="PQ",
    company_id="test-company-1")
    updated = db.update_project(project["id"], {
        "name": "Autoclave PQ", "equipment_name": "Autoclave", "manufacturer": "Getinge",
        "department": "Sterile", "validation_type": "PQ",
        "owner": "Alice", "approver": "Bob", "target_date": "2027-01-15",
        "risk_category": "Medium", "status": "Completed",
        "model": "GEV-125", "location": "Building B",
        "protocol_number": "PRO-042", "report_number": "REP-042",
    })
    assert updated["owner"] == "Alice"
    assert updated["status"] == "Completed"
    assert updated["target_date"] == "2027-01-15"


def test_update_project_not_found_returns_none(db_path):
    assert db.update_project(999999, {"name": "x"}) is None


def test_migrate_val_projects_copies_row_and_audit_trail(db_path):
    conn = db.get_connection()
    cur = conn.execute(
        """INSERT INTO val_projects
           (name, equipment_name, equipment_id, department, manufacturer, model,
            location, validation_type, protocol_number, report_number, owner,
            approver, target_date, risk_category, status)
           VALUES ('Legacy Val Project','Tablet Press','EQ-9','Production','Fette',
                   'P2200','Line 4','IQ/OQ/PQ','PRO-777','REP-777','Carol','Dave',
                   '2026-11-01','Critical','In Progress')"""
    )
    val_proj_id = cur.lastrowid
    conn.execute(
        "INSERT INTO val_audit_trail (val_proj_id, action, user_note) VALUES (?, 'Project created', '')",
        (val_proj_id,),
    )
    conn.execute(
        "INSERT INTO val_audit_trail (val_proj_id, action, user_note) VALUES (?, 'Project details updated', 'Updated target date')",
        (val_proj_id,),
    )
    conn.commit()
    conn.close()

    # Run the migration explicitly (init_db() already ran once via the db_path
    # fixture before this val_project existed; re-run it now that it does).
    conn = db.get_connection()
    db._migrate_val_projects(conn)
    conn.close()

    migrated = [p for p in db.get_all_projects() if p["migrated_from_val_project_id"] == val_proj_id]
    assert len(migrated) == 1
    project = migrated[0]
    assert project["name"] == "Legacy Val Project"
    assert project["owner"] == "Carol"
    assert project["risk_category"] == "Critical"
    assert project["protocol_number"] == "PRO-777"

    audit = qms_database.get_audit_trail("project", project["id"])
    assert len(audit) == 2
    assert audit[0]["action"] == "Project created"
    assert audit[1]["detail"] == "Updated target date"


def test_migrate_val_projects_is_idempotent(db_path):
    conn = db.get_connection()
    cur = conn.execute(
        "INSERT INTO val_projects (name) VALUES ('Idempotency Check')"
    )
    val_proj_id = cur.lastrowid
    conn.commit()
    conn.close()

    conn = db.get_connection()
    db._migrate_val_projects(conn)
    db._migrate_val_projects(conn)  # run twice
    conn.close()

    matches = [p for p in db.get_all_projects() if p["migrated_from_val_project_id"] == val_proj_id]
    assert len(matches) == 1  # not duplicated


def test_dashboard_stats_shape_unchanged(db_path):
    stats = db.get_dashboard_stats("test-company-1")
    assert set(stats.keys()) == {
        "counts", "recent_projects", "recent_conversations", "recent_activity",
        "upcoming_reviews", "upcoming_validations", "system_health",
    }
    assert set(stats["counts"].keys()) == {
        "projects", "val_projects", "kb_documents", "protocols_generated",
        "pending_capas", "pending_deviations",
    }
    assert "audit_entries" in stats["system_health"]


def test_dashboard_stats_val_projects_count_reflects_migrated_and_dated_projects(db_path):
    # Legacy-migrated rows always land on BOOTSTRAP_COMPANY_ID (see
    # _migrate_val_projects) — use the same company here so all three
    # projects are visible in one company-scoped dashboard query.
    db.create_project(name="Plain project", equipment_name="", manufacturer="",
                       department="", validation_type="", company_id=BOOTSTRAP_COMPANY_ID)
    db.create_project(name="Dated project", equipment_name="", manufacturer="",
                       department="", validation_type="", target_date="2027-06-01", company_id=BOOTSTRAP_COMPANY_ID)

    conn = db.get_connection()
    conn.execute("INSERT INTO val_projects (name) VALUES ('Legacy')")
    conn.commit()
    db._migrate_val_projects(conn)
    conn.close()

    stats = db.get_dashboard_stats(BOOTSTRAP_COMPANY_ID)
    # Plain project (no target_date, not migrated) must NOT count; the other two must.
    assert stats["counts"]["val_projects"] == 2
    assert stats["counts"]["projects"] == 3

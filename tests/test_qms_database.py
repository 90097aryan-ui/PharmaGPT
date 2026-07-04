"""
tests/test_qms_database.py — Unit tests for the QMS database layer:
qms_database.py (schema + shared tables) and the three module CRUD files
(qms_document_database.py, qms_deviation_database.py, qms_capa_database.py).

Each test depends on the `db_path` fixture (tests/conftest.py), which points
pharmagpt.database at a fresh temp SQLite file before any QMS module is used.
"""


# ── Document Control ─────────────────────────────────────────────────────────

def test_create_document_generates_number_and_defaults(db_path):
    from pharmagpt import qms_document_database as qdb

    doc = qdb.create_document({"doc_type": "SOP", "title": "Cleaning SOP", "department": "Quality Assurance"})
    assert doc["doc_number"] == "SOP-QA-0001"
    assert doc["status"] == "Draft"
    assert doc["version"] == "1.0"

    doc2 = qdb.create_document({"doc_type": "SOP", "title": "Second SOP", "department": "Quality Assurance"})
    assert doc2["doc_number"] == "SOP-QA-0002"


def test_document_update_and_form_data_roundtrip(db_path):
    from pharmagpt import qms_document_database as qdb

    doc = qdb.create_document({"title": "Doc", "form_data": {"a": 1}})
    assert doc["form_data"] == {"a": 1}

    updated = qdb.update_document(doc["id"], {"status": "Effective", "form_data": {"a": 2}})
    assert updated["status"] == "Effective"
    assert updated["form_data"] == {"a": 2}


def test_document_versions_training_distribution(db_path):
    from pharmagpt import qms_document_database as qdb

    doc = qdb.create_document({"title": "Doc"})
    qdb.create_version(doc["id"], "1.0", "Initial", "content snapshot", "J Doe")
    versions = qdb.get_versions(doc["id"])
    assert len(versions) == 1
    assert versions[0]["change_summary"] == "Initial"

    qdb.add_training(doc["id"], {"trainee_name": "A Kumar"})
    training = qdb.get_training(doc["id"])
    assert training[0]["training_status"] == "Pending"
    qdb.update_training_status(training[0]["id"], "Completed", "2026-07-01")
    assert qdb.get_training(doc["id"])[0]["training_status"] == "Completed"

    dist = qdb.add_distribution(doc["id"], {"distributed_to": "Production", "distributed_date": "2026-07-01"})
    assert qdb.get_distribution(doc["id"])[0]["acknowledged"] == 0
    qdb.acknowledge_distribution(dist["id"], "2026-07-02")
    assert qdb.get_distribution(doc["id"])[0]["acknowledged"] == 1


def test_document_dashboard_stats(db_path):
    from pharmagpt import qms_document_database as qdb

    qdb.create_document({"doc_type": "SOP", "title": "A", "status": "Draft"})
    qdb.create_document({"doc_type": "Policy", "title": "B", "status": "Effective"})
    stats = qdb.get_dashboard_stats()
    assert stats["total"] == 2
    assert stats["draft"] == 1
    assert stats["effective"] == 1
    assert stats["by_type"]["SOP"] == 1


def test_document_delete(db_path):
    from pharmagpt import qms_document_database as qdb

    doc = qdb.create_document({"title": "To delete"})
    qdb.delete_document(doc["id"])
    assert qdb.get_document(doc["id"]) is None


# ── Deviation Management ─────────────────────────────────────────────────────

def test_create_deviation_generates_number(db_path):
    from pharmagpt import qms_deviation_database as ddb

    dev = ddb.create_deviation({"title": "Temp excursion", "deviation_type": "Major"})
    assert dev["deviation_number"].startswith("DEV-")
    assert dev["status"] == "Initiated"


def test_deviation_investigation_upsert_and_json_fields(db_path):
    from pharmagpt import qms_deviation_database as ddb

    dev = ddb.create_deviation({"title": "Dev"})
    ddb.upsert_investigation(dev["id"], {
        "root_cause_statement": "RC",
        "fishbone_data": {"man": ["fatigue"]},
        "five_why_data": [{"question": "Why?", "answer": "Because"}],
        "timeline_data": [{"datetime": "T0", "event": "Discovered"}],
    })
    inv = ddb.get_investigation(dev["id"])
    assert inv["root_cause_statement"] == "RC"
    assert inv["fishbone_data"] == {"man": ["fatigue"]}
    assert inv["five_why_data"] == [{"question": "Why?", "answer": "Because"}]

    # Upsert again — should update the same row, not create a second one
    ddb.upsert_investigation(dev["id"], {"root_cause_statement": "Updated RC"})
    inv2 = ddb.get_investigation(dev["id"])
    assert inv2["root_cause_statement"] == "Updated RC"
    assert inv2["id"] == inv["id"]


def test_deviation_impact_entries(db_path):
    from pharmagpt import qms_deviation_database as ddb

    dev = ddb.create_deviation({"title": "Dev"})
    ddb.add_impact(dev["id"], {"impact_area": "Product Quality", "risk_level": "Low"})
    impacts = ddb.get_impacts(dev["id"])
    assert len(impacts) == 1
    assert impacts[0]["impact_area"] == "Product Quality"


def test_deviation_capa_linkage(db_path):
    from pharmagpt import qms_deviation_database as ddb
    from pharmagpt import qms_capa_database as cdb

    dev = ddb.create_deviation({"title": "Dev"})
    capa = cdb.create_capa({"title": "CAPA", "capa_source": "Deviation"})
    ddb.link_capa(dev["id"], capa["id"])

    linked_capas = ddb.get_linked_capas(dev["id"])
    assert len(linked_capas) == 1
    assert linked_capas[0]["id"] == capa["id"]

    linked_devs = ddb.get_linked_deviations(capa["id"])
    assert len(linked_devs) == 1
    assert linked_devs[0]["id"] == dev["id"]


def test_deviation_dashboard_stats(db_path):
    from pharmagpt import qms_deviation_database as ddb

    ddb.create_deviation({"title": "A", "deviation_type": "Minor"})
    d2 = ddb.create_deviation({"title": "B", "deviation_type": "Major"})
    ddb.update_deviation(d2["id"], {"status": "Closed"})
    stats = ddb.get_dashboard_stats()
    assert stats["total"] == 2
    assert stats["open"] == 1
    assert stats["closed"] == 1


# ── CAPA ───────────────────────────────────────────────────────────────────────

def test_create_capa_generates_number(db_path):
    from pharmagpt import qms_capa_database as cdb

    capa = cdb.create_capa({"title": "CAPA A"})
    assert capa["capa_number"].startswith("CAPA-")
    assert capa["status"] == "Open"


def test_capa_actions_upsert_and_escalate(db_path):
    from pharmagpt import qms_capa_database as cdb

    capa = cdb.create_capa({"title": "CAPA"})
    action = cdb.upsert_action(capa["id"], {"action_type": "Corrective", "description": "Fix it", "owner": "QA"})
    assert action["status"] == "Pending"

    # Upsert with id updates the same row
    updated = cdb.upsert_action(capa["id"], {"id": action["id"], "status": "Completed", "description": "Fix it"})
    assert updated["id"] == action["id"]
    assert updated["status"] == "Completed"

    actions = cdb.get_actions(capa["id"])
    assert len(actions) == 1

    escalated = cdb.escalate_action(action["id"], "QA Head", "2026-07-20")
    assert escalated["escalated"] == 1
    assert escalated["status"] == "Escalated"


def test_capa_effectiveness_upsert(db_path):
    from pharmagpt import qms_capa_database as cdb

    capa = cdb.create_capa({"title": "CAPA"})
    entry = cdb.upsert_effectiveness(capa["id"], {"check_criterion": "No recurrence", "method": "Trend monitoring"})
    assert entry["status"] == "Pending"
    checks = cdb.get_effectiveness(capa["id"])
    assert len(checks) == 1


def test_capa_dashboard_stats_and_overdue(db_path):
    from pharmagpt import qms_capa_database as cdb

    cdb.create_capa({"title": "A", "target_closure_date": "2020-01-01"})  # overdue (past date)
    cdb.create_capa({"title": "B", "target_closure_date": "2099-01-01"})  # not overdue
    stats = cdb.get_dashboard_stats()
    assert stats["total"] == 2
    assert stats["open"] == 2
    assert stats["overdue"] == 1


def test_capa_delete(db_path):
    from pharmagpt import qms_capa_database as cdb

    capa = cdb.create_capa({"title": "To delete"})
    cdb.delete_capa(capa["id"])
    assert cdb.get_capa(capa["id"]) is None


# ── Shared tables: attachments / comments / audit trail / approvals ───────────

def test_shared_attachments_polymorphic(db_path):
    from pharmagpt import qms_database as qmsdb
    from pharmagpt import qms_document_database as qdb
    from pharmagpt import qms_deviation_database as ddb

    doc = qdb.create_document({"title": "Doc"})
    dev = ddb.create_deviation({"title": "Dev"})

    qmsdb.add_attachment("document", doc["id"], "a.pdf", "Original A.pdf", "pdf", 1024)
    qmsdb.add_attachment("deviation", dev["id"], "b.pdf", "Original B.pdf", "pdf", 2048)

    doc_attachments = qmsdb.get_attachments("document", doc["id"])
    dev_attachments = qmsdb.get_attachments("deviation", dev["id"])
    assert len(doc_attachments) == 1
    assert len(dev_attachments) == 1
    assert doc_attachments[0]["original_name"] == "Original A.pdf"


def test_shared_comments_audit_approvals(db_path):
    from pharmagpt import qms_database as qmsdb
    from pharmagpt import qms_capa_database as cdb

    capa = cdb.create_capa({"title": "CAPA"})

    qmsdb.add_comment("capa", capa["id"], "J Doe", "Looks good", "QA")
    comments = qmsdb.get_comments("capa", capa["id"])
    assert comments[0]["comment"] == "Looks good"

    qmsdb.add_audit_entry("capa", capa["id"], "CAPA created", "J Doe")
    audit = qmsdb.get_audit_trail("capa", capa["id"])
    assert audit[0]["action"] == "CAPA created"

    qmsdb.add_approval_entry("capa", capa["id"], "Submitted for QA Review", "J Doe", "QA", "", "J Doe")
    approvals = qmsdb.get_approval_trail("capa", capa["id"])
    assert approvals[0]["electronic_sig"] == "J Doe"


def test_qms_meta_contains_expected_enums():
    from pharmagpt import qms_database as qmsdb

    assert "SOP" in qmsdb.QMS_META["document_types"]
    assert "Minor" in qmsdb.QMS_META["deviation_types"]
    assert "Open" in qmsdb.QMS_META["capa_statuses"]


def test_qms_schema_creates_all_tables(db_path):
    from pharmagpt import database as db

    conn = db.get_connection()
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'qms_%'"
    ).fetchall()}
    conn.close()

    expected = {
        "qms_attachments", "qms_comments", "qms_audit_trail", "qms_approvals",
        "qms_documents", "qms_document_versions", "qms_document_distribution", "qms_document_training",
        "qms_capas", "qms_capa_actions", "qms_capa_effectiveness",
        "qms_deviations", "qms_deviation_investigation", "qms_deviation_impact", "qms_deviation_capa_link",
    }
    assert expected.issubset(tables)

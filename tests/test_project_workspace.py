"""
tests/test_project_workspace.py — PharmaGPT v1.0 Module 3: Project Workspace
navigation architecture (retiring the legacy Validation Workspace, adding
live project audit-trail logging via the shared qms_audit_trail table).
"""


def _create_project(client, **overrides):
    payload = dict(
        name="HPLC IQ", equipment_name="Agilent HPLC 1260", manufacturer="Agilent",
        department="QC", validation_type="IQ/OQ/PQ",
    )
    payload.update(overrides)
    return client.post("/projects", json=payload).get_json()


def test_create_project_logs_audit_entry(client):
    project = _create_project(client)
    r = client.get(f"/qms/project/{project['id']}/audit-trail")
    assert r.status_code == 200
    entries = r.get_json()
    assert len(entries) == 1
    assert entries[0]["action"] == "Project created"


def test_update_project_logs_audit_entry(client):
    project = _create_project(client)
    client.put(f"/projects/{project['id']}", json={
        "name": "HPLC IQ", "equipment_name": "Agilent HPLC 1260", "manufacturer": "Agilent",
        "department": "QC", "validation_type": "IQ/OQ/PQ", "status": "Completed",
    })
    entries = client.get(f"/qms/project/{project['id']}/audit-trail").get_json()
    assert [e["action"] for e in entries] == ["Project created", "Project details updated"]


def test_delete_project_logs_audit_entry_before_removal(client):
    """The 'Project deleted' entry is written (and the qms_audit_trail row
    itself is never removed, since it has no FK to projects) before the
    project row is deleted. The generic GET /qms/project/<id>/audit-trail
    endpoint 404s afterward because its existence check now correctly finds
    no such project — harmless in practice, since a deleted project has no
    reachable Project Workspace UI to view its History tab from anyway."""
    project = _create_project(client)
    client.delete(f"/projects/{project['id']}")
    r = client.get(f"/qms/project/{project['id']}/audit-trail")
    assert r.status_code == 404

    import pharmagpt.qms_database as qmsdb
    raw_entries = qmsdb.get_audit_trail("project", project["id"])
    assert [e["action"] for e in raw_entries] == ["Project created", "Project deleted"]


def test_project_audit_trail_404_for_missing_project(client):
    r = client.get("/qms/project/999999/audit-trail")
    assert r.status_code == 404


def test_project_is_a_valid_qms_record_type_for_shared_endpoints(client):
    """The polymorphic qms_common endpoints (attachments/comments/approval)
    should also recognize 'project' now that it's a registered record_type,
    even though this module only exercises the audit-trail endpoint."""
    project = _create_project(client)
    r = client.get(f"/qms/project/{project['id']}/comments")
    assert r.status_code == 200
    assert r.get_json() == []


def test_legacy_validation_workspace_routes_removed(client):
    """routes/workspace.py was deleted (PharmaGPT v1.0 Module 3) — its
    /val-projects routes must no longer resolve to anything."""
    assert client.get("/val-projects").status_code == 404
    assert client.post("/val-projects", json={"name": "X"}).status_code == 404

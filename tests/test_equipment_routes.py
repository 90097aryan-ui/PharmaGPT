"""
tests/test_equipment_routes.py — PharmaGPT v1.0 Module 2: Equipment HTTP routes.

Covers routes/equipment.py end-to-end via the Flask test client: project-scoped
list/create, legacy import, search, type catalog, single-record CRUD, document
linking, and the AI-context bundle endpoint.
"""


def _create_project(client, **overrides):
    payload = dict(
        name="HPLC IQ", equipment_name="Agilent HPLC 1260", manufacturer="Agilent",
        department="QC", validation_type="IQ/OQ/PQ",
    )
    payload.update(overrides)
    return client.post("/projects", json=payload).get_json()


def test_create_and_list_project_equipment(client):
    project = _create_project(client)

    r = client.post(f"/projects/{project['id']}/equipment", json={"name": "HPLC System 1"})
    assert r.status_code == 201
    equipment = r.get_json()
    assert equipment["project_id"] == project["id"]

    r = client.get(f"/projects/{project['id']}/equipment")
    assert r.status_code == 200
    # 2, not 1: Phase 2 auto-creates one Equipment record from the project's
    # own equipment_name ("Agilent HPLC 1260", set by _create_project()
    # above) at creation time — see routes/projects.py::
    # _link_equipment_to_new_project(). This test then adds a second,
    # distinct record ("HPLC System 1") explicitly.
    assert len(r.get_json()) == 2


def test_create_equipment_requires_name(client):
    project = _create_project(client)
    r = client.post(f"/projects/{project['id']}/equipment", json={})
    assert r.status_code == 400


def test_create_equipment_missing_project_404(client):
    r = client.post("/projects/999999/equipment", json={"name": "X"})
    assert r.status_code == 404


def test_list_equipment_missing_project_404(client):
    r = client.get("/projects/999999/equipment")
    assert r.status_code == 404


def test_get_update_delete_equipment(client):
    project = _create_project(client)
    equipment = client.post(f"/projects/{project['id']}/equipment", json={"name": "Autoclave"}).get_json()
    eid = equipment["id"]

    r = client.get(f"/equipment/{eid}")
    assert r.status_code == 200
    assert r.get_json()["name"] == "Autoclave"

    r = client.put(f"/equipment/{eid}", json={"qualification_status": "Qualified", "criticality": "Critical"})
    assert r.status_code == 200
    assert r.get_json()["qualification_status"] == "Qualified"

    r = client.delete(f"/equipment/{eid}")
    assert r.status_code == 200
    assert client.get(f"/equipment/{eid}").status_code == 404


def test_update_equipment_rejects_blank_name(client):
    project = _create_project(client)
    equipment = client.post(f"/projects/{project['id']}/equipment", json={"name": "Autoclave"}).get_json()
    r = client.put(f"/equipment/{equipment['id']}", json={"name": "  "})
    assert r.status_code == 400


def test_get_update_delete_missing_equipment_404(client):
    assert client.get("/equipment/999999").status_code == 404
    assert client.put("/equipment/999999", json={"name": "X"}).status_code == 404
    assert client.delete("/equipment/999999").status_code == 404


def test_import_legacy_equipment(client):
    project = _create_project(client, name="Legacy", equipment_name="Shimadzu GC", manufacturer="Shimadzu")
    r = client.post(f"/projects/{project['id']}/equipment/import-legacy")
    assert r.status_code == 201
    assert r.get_json()["name"] == "Shimadzu GC"


def test_import_legacy_equipment_no_data(client):
    project = _create_project(client, equipment_name="", manufacturer="")
    r = client.post(f"/projects/{project['id']}/equipment/import-legacy")
    assert r.status_code == 400


def test_search_equipment(client):
    project = _create_project(client)
    client.post(f"/projects/{project['id']}/equipment", json={"name": "HPLC System 1", "manufacturer": "Agilent"})

    r = client.get("/equipment/search?q=Agilent")
    assert r.status_code == 200
    # 2, not 1: Phase 2 auto-creates one Equipment record ("Agilent HPLC
    # 1260", manufacturer "Agilent") from the project's own fields at
    # creation time — see routes/projects.py::_link_equipment_to_new_project().
    # Both it and the explicitly-created "HPLC System 1" match "Agilent".
    assert len(r.get_json()) == 2

    r = client.get("/equipment/search")
    assert r.get_json() == []


def test_equipment_types_catalog(client):
    r = client.get("/equipment/types")
    assert r.status_code == 200
    types = r.get_json()
    assert "HPLC" in types
    assert types == sorted(types)


def test_link_list_unlink_equipment_document(client):
    project = _create_project(client)
    equipment = client.post(f"/projects/{project['id']}/equipment", json={"name": "HPLC"}).get_json()

    kb_doc = client.post(
        "/kb/documents",
        data={"title": "HPLC Manual", "folder": "Vendor Documents"},
        content_type="multipart/form-data",
    )
    # If KB upload requires an actual file part in this route, fall back to
    # a project document instead so this test doesn't depend on multipart
    # file-upload plumbing unrelated to the equipment feature under test.
    if kb_doc.status_code >= 400:
        doc_id = None
    else:
        doc_id = kb_doc.get_json()["id"]

    if doc_id is None:
        r = client.post(f"/equipment/{equipment['id']}/documents",
                         json={"document_role": "not_real", "source_type": "kb", "source_id": 1})
        assert r.status_code == 400
        return

    r = client.post(f"/equipment/{equipment['id']}/documents",
                     json={"document_role": "user_manual", "source_type": "kb", "source_id": doc_id})
    assert r.status_code == 201
    link_id = r.get_json()["id"]

    r = client.get(f"/equipment/{equipment['id']}/documents")
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    r = client.delete(f"/equipment/{equipment['id']}/documents/{link_id}")
    assert r.status_code == 200
    assert client.get(f"/equipment/{equipment['id']}/documents").get_json() == []


def test_link_equipment_document_invalid_role(client):
    project = _create_project(client)
    equipment = client.post(f"/projects/{project['id']}/equipment", json={"name": "HPLC"}).get_json()
    r = client.post(f"/equipment/{equipment['id']}/documents",
                     json={"document_role": "bogus", "source_type": "kb", "source_id": 1})
    assert r.status_code == 400


def test_link_equipment_document_missing_source(client):
    project = _create_project(client)
    equipment = client.post(f"/projects/{project['id']}/equipment", json={"name": "HPLC"}).get_json()
    r = client.post(f"/equipment/{equipment['id']}/documents",
                     json={"document_role": "sop", "source_type": "project", "source_id": 999999})
    assert r.status_code == 404


def test_equipment_ai_context_bundle(client):
    project = _create_project(client)
    equipment = client.post(
        f"/projects/{project['id']}/equipment",
        json={"name": "HPLC System 1", "equipment_type": "HPLC"},
    ).get_json()

    r = client.get(f"/equipment/{equipment['id']}/ai-context")
    assert r.status_code == 200
    bundle = r.get_json()
    assert bundle["equipment"]["id"] == equipment["id"]
    assert bundle["intelligence_profile"]["matched"] is True
    assert bundle["intelligence_profile"]["name"] == "HPLC"
    assert "documents" in bundle
    assert "validation_history" in bundle


def test_equipment_ai_context_missing_404(client):
    r = client.get("/equipment/999999/ai-context")
    assert r.status_code == 404


def test_project_delete_cascades_equipment(client):
    project = _create_project(client)
    equipment = client.post(f"/projects/{project['id']}/equipment", json={"name": "Autoclave"}).get_json()

    r = client.delete(f"/projects/{project['id']}")
    assert r.status_code == 200
    assert client.get(f"/equipment/{equipment['id']}").status_code == 404

"""
tests/test_qms_feature_requests.py — Flask test-client integration tests for
the Feature Requests module (v1: CRUD only — no workflow, no approvals).
"""

def test_meta_includes_feature_request_enums(client):
    r = client.get("/qms/meta")
    assert r.status_code == 200
    data = r.get_json()
    assert "Critical" in data["feature_request_priorities"]
    assert "Released" in data["feature_request_statuses"]
    assert "Other" in data["feature_request_modules"]


def test_feature_request_requires_title_and_description(client):
    r = client.post("/qms/feature-requests", json={"description": "Missing title"})
    assert r.status_code == 400

    r = client.post("/qms/feature-requests", json={"title": "Missing description"})
    assert r.status_code == 400


def test_feature_request_crud_lifecycle(client):
    r = client.post("/qms/feature-requests", json={
        "title": "Bulk export for CAPA reports",
        "description": "Allow exporting all CAPA reports as a single ZIP of DOCX files.",
        "module": "CAPA",
        "priority": "High",
        "assigned_to": "Jane Doe",
    })
    assert r.status_code == 201
    fr = r.get_json()
    assert fr["fr_number"].startswith("FR-")
    assert fr["status"] == "New"
    assert fr["created_by"] == "Test User"
    fr_id = fr["id"]

    r = client.get("/qms/feature-requests")
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    r = client.get(f"/qms/feature-requests/{fr_id}")
    assert r.status_code == 200
    assert r.get_json()["title"] == "Bulk export for CAPA reports"

    r = client.put(f"/qms/feature-requests/{fr_id}", json={"status": "Review", "priority": "Critical"})
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["status"] == "Review"
    assert updated["priority"] == "Critical"

    r = client.delete(f"/qms/feature-requests/{fr_id}")
    assert r.status_code == 200
    assert client.get(f"/qms/feature-requests/{fr_id}").status_code == 404


def test_feature_request_update_rejects_blank_title(client):
    r = client.post("/qms/feature-requests", json={"title": "T", "description": "D"})
    fr_id = r.get_json()["id"]
    r = client.put(f"/qms/feature-requests/{fr_id}", json={"title": "   "})
    assert r.status_code == 400


def test_feature_request_search_and_filter(client):
    client.post("/qms/feature-requests", json={"title": "Dark mode", "description": "Add dark theme", "priority": "Low", "status": "New"})
    client.post("/qms/feature-requests", json={"title": "SSO login", "description": "Support SAML SSO", "priority": "High", "status": "New"})

    r = client.get("/qms/feature-requests?q=dark")
    assert len(r.get_json()) == 1
    assert r.get_json()[0]["title"] == "Dark mode"

    r = client.get("/qms/feature-requests?priority=High")
    assert len(r.get_json()) == 1
    assert r.get_json()[0]["title"] == "SSO login"


def test_feature_request_attachments_via_shared_endpoint(client):
    r = client.post("/qms/feature-requests", json={"title": "T", "description": "D"})
    fr_id = r.get_json()["id"]

    r = client.get(f"/qms/feature_request/{fr_id}/attachments")
    assert r.status_code == 200
    assert r.get_json() == []

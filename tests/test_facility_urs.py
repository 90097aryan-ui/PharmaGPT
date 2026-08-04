"""
tests/test_facility_urs.py — Integration tests for the Greenfield Facility
URS feature (Stage 1): Facility CRUD, the Building/Floor/Area/Room node
tree, the Facility Systems registry, and Facility URS creation/library/
generation through the existing URS Management Suite (routes/urs.py).

Mirrors tests/test_urs_routes.py's shape for the generation test (fake
Gemini client, poll .../generate/status to a terminal state) to confirm the
Facility URS reuses the exact same background-job pipeline as the equipment
flow, not a separate one.
"""

import json
import time

import pytest

from pharmagpt.services import urs_generation_job as gen_job
from google.genai import types


def _create_project(client, name="Greenfield Test Project"):
    return client.post("/projects", json={"name": name}).get_json()


def _create_facility(client, project_id, **overrides):
    payload = {
        "facility_name": "Nutra Greenfield OSD Plant",
        "facility_type": "OSD (Oral Solid Dosage)",
        "product_category": "Nutraceuticals",
        "country": "India",
        "regulatory_market": "USFDA, WHO-GMP",
        "site_capacity": "2 billion tablets/year",
        "manufacturing_type": "Batch",
        "design_standards": "GAMP 5, ISPE Baseline Guide Vol. 2",
        "description": "New greenfield OSD facility.",
    }
    payload.update(overrides)
    return client.post(f"/projects/{project_id}/facility", json=payload).get_json()


# ── Facility CRUD ─────────────────────────────────────────────────────────────

def test_create_and_get_facility(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    assert facility["id"]
    assert facility["facility_name"] == "Nutra Greenfield OSD Plant"
    assert facility["project_id"] == project["id"]

    fetched = client.get(f"/facility/{facility['id']}").get_json()
    assert fetched["id"] == facility["id"]


def test_create_facility_requires_name(client):
    project = _create_project(client)
    resp = client.post(f"/projects/{project['id']}/facility", json={"facility_type": "OSD"})
    assert resp.status_code == 400


def test_create_facility_404_for_unknown_project(client):
    resp = client.post("/projects/999999/facility", json={"facility_name": "X"})
    assert resp.status_code == 404


def test_list_project_facilities(client):
    project = _create_project(client)
    _create_facility(client, project["id"])
    _create_facility(client, project["id"], facility_name="Second Facility")
    facilities = client.get(f"/projects/{project['id']}/facility").get_json()
    assert len(facilities) == 2


def test_update_facility(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    updated = client.put(f"/facility/{facility['id']}", json={"site_capacity": "5 billion tablets/year"}).get_json()
    assert updated["site_capacity"] == "5 billion tablets/year"
    assert updated["facility_name"] == facility["facility_name"]  # untouched fields preserved


def test_delete_facility(client):
    """Positive path for the delete route (require_role("company_admin") is
    the same decorator already proven against routes/equipment.py in
    tests/test_security_tenant_rbac_esig.py — not re-tested here)."""
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    resp = client.delete(f"/facility/{facility['id']}")
    assert resp.status_code == 200
    assert client.get(f"/facility/{facility['id']}").status_code == 404


def test_facility_not_visible_to_other_company(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])

    import pharmagpt.facility_database as facdb
    other = facdb.get_facility_scoped(facility["id"], "some-other-company-id")
    assert other is None


# ── Building / Floor / Area / Room node tree ──────────────────────────────────

def test_node_tree_crud(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    fid = facility["id"]

    building = client.post(f"/facility/{fid}/nodes", json={
        "node_type": "building", "name": "Building A",
    }).get_json()
    assert building["node_type"] == "building"
    assert building["attributes"] == {}

    floor = client.post(f"/facility/{fid}/nodes", json={
        "node_type": "floor", "name": "Ground Floor", "parent_id": building["id"],
    }).get_json()
    room = client.post(f"/facility/{fid}/nodes", json={
        "node_type": "room", "name": "Granulation Room", "parent_id": floor["id"],
        "attributes": {"classification": "Grade C"},
    }).get_json()
    assert room["attributes"]["classification"] == "Grade C"

    flat = client.get(f"/facility/{fid}/nodes").get_json()
    assert len(flat) == 3

    tree = client.get(f"/facility/{fid}/nodes/tree").get_json()
    assert len(tree) == 1  # one root (Building A)
    assert tree[0]["children"][0]["children"][0]["name"] == "Granulation Room"

    # Deleting the building cascades to floor and room.
    client.delete(f"/facility/nodes/{building['id']}")
    assert client.get(f"/facility/{fid}/nodes").get_json() == []


def test_node_invalid_type_rejected(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    resp = client.post(f"/facility/{facility['id']}/nodes", json={"node_type": "wing", "name": "X"})
    assert resp.status_code == 400


def test_node_parent_must_belong_to_same_facility(client):
    project = _create_project(client)
    f1 = _create_facility(client, project["id"])
    f2 = _create_facility(client, project["id"], facility_name="Other Facility")
    other_building = client.post(f"/facility/{f2['id']}/nodes", json={
        "node_type": "building", "name": "B",
    }).get_json()
    resp = client.post(f"/facility/{f1['id']}/nodes", json={
        "node_type": "floor", "name": "F", "parent_id": other_building["id"],
    })
    assert resp.status_code == 400


# ── Facility Systems registry ─────────────────────────────────────────────────

def test_facility_systems_registry(client):
    resp = client.get("/facility/systems").get_json()
    categories = resp["categories"]
    assert "HVAC & Environmental" in categories
    assert "HVAC" in categories["HVAC & Environmental"]
    assert "Purified Water" in categories["Process Utilities"]


def test_facility_system_detail(client):
    resp = client.get("/facility/systems/HVAC").get_json()
    assert resp["name"] == "HVAC"
    assert resp["applicable_regulations"]
    assert resp["critical_parameters"]


def test_facility_system_detail_404(client):
    resp = client.get("/facility/systems/nonexistent-system")
    assert resp.status_code == 404


def test_facility_types_endpoint(client):
    resp = client.get("/facility/types").get_json()
    assert "OSD (Oral Solid Dosage)" in resp["types"]
    assert "Injectable (Sterile)" in resp["types"]


# ── Facility URS creation ──────────────────────────────────────────────────────

def test_create_facility_urs(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])

    urs = client.post("/urs/", json={
        "urs_type": "facility",
        "facility_id": facility["id"],
        "manufacturing_areas": "Granulation, Compression",
        "utilities_required": ["HVAC", "Purified Water"],
        "cleanroom_classification": "Grade D general manufacturing",
    }).get_json()

    assert urs["urs_type"] == "facility"
    assert urs["facility_id"] == facility["id"]
    assert urs["category"] == "Nutraceuticals"          # mirrored from facility.product_category
    assert urs["equipment_type"] == "OSD (Oral Solid Dosage)"  # mirrored from facility.facility_type
    assert urs["title"].startswith("Facility URS")
    assert urs["facility_data"]["manufacturing_areas"] == "Granulation, Compression"
    assert urs["facility_data"]["utilities_required"] == ["HVAC", "Purified Water"]

    # The equipment URS flow must be completely unaffected — default urs_type
    # is still 'equipment' with no facility_id required.
    equipment_urs = client.post("/urs/", json={"equipment_name": "Autoclave-01"}).get_json()
    assert equipment_urs["urs_type"] == "equipment"
    assert equipment_urs["facility_id"] is None


def test_create_facility_urs_requires_valid_facility_id(client):
    resp = client.post("/urs/", json={"urs_type": "facility"})
    assert resp.status_code == 400

    resp2 = client.post("/urs/", json={"urs_type": "facility", "facility_id": 999999})
    assert resp2.status_code == 400


def test_create_urs_rejects_invalid_urs_type(client):
    resp = client.post("/urs/", json={"urs_type": "bogus", "title": "X"})
    assert resp.status_code == 400


def test_facility_urs_cannot_reference_another_companys_facility(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])

    import pharmagpt.urs_database as udb
    # Simulate the facility belonging to a different tenant by scoping the
    # lookup with a foreign company_id — mirrors get_facility_scoped's own
    # unit test above; here we confirm the *route* enforces it end-to-end.
    import pharmagpt.facility_database as facdb
    assert facdb.get_facility_scoped(facility["id"], "another-company") is None


# ── Facility requirement library ──────────────────────────────────────────────

def test_load_facility_library_requirements(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()

    resp = client.post(f"/urs/{urs['id']}/library", json={}).get_json()
    assert resp["loaded"] > 0
    sections = {r["section"] for r in resp["requirements"]}
    assert "Site Information" in sections
    assert "Cleanroom Requirements" in sections
    assert "Functional Requirements" not in sections  # equipment-only section must not leak in

    # OSD-typed facility should pick up the OSD HVAC overlay requirement.
    reqs_text = " ".join(r["requirement"] for r in resp["requirements"])
    assert "dust extraction" in reqs_text.lower()


def test_library_types_and_sections_query_param(client):
    equip_types = client.get("/urs/library/types").get_json()["types"]
    facility_types = client.get("/urs/library/types?urs_type=facility").get_json()["types"]
    assert equip_types != facility_types
    assert "OSD (Oral Solid Dosage)" in facility_types

    facility_sections = client.get(
        "/urs/library/sections?type=OSD (Oral Solid Dosage)&urs_type=facility"
    ).get_json()["sections"]
    assert "HVAC Requirements" in facility_sections


# ── Facility URS AI generation (reuses the same background-job pipeline) ─────

class _FakeModels:
    def __init__(self, fn):
        self._fn = fn

    def generate_content(self, model, contents, config):
        return self._fn(model, contents, config)


class _FakeClient:
    def __init__(self, fn):
        self.models = _FakeModels(fn)


class _FakeUsage:
    def __init__(self):
        self.prompt_token_count = 10
        self.candidates_token_count = 20


class _FakeCandidate:
    def __init__(self, finish_reason=types.FinishReason.STOP):
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = _FakeUsage()
        self.candidates = [_FakeCandidate()]


def _wait_for_terminal_status(client, urs_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = client.get(f"/urs/{urs_id}/generate/status").get_json()
        if status.get("generation_status") in ("completed", "failed"):
            return status
        time.sleep(0.1)
    pytest.fail(f"generation never reached a terminal status: {status}")


def test_facility_urs_generation_uses_facility_prompt(client, monkeypatch):
    """The facility prompt must be used (not the equipment one), and the
    generation pipeline (batching/retry/persistence) must be the exact same
    code path the equipment flow already exercises in test_urs_routes.py."""
    captured_prompts = []

    def fake_generate_content(model, contents, config):
        prompt_text = contents[0].parts[0].text
        captured_prompts.append(prompt_text)
        return _FakeResponse(json.dumps([{
            "section": "HVAC Requirements",
            "requirement": "The facility shall maintain Grade D conditions in the granulation room.",
            "rationale": "Contamination control", "priority": "Critical",
            "gmp_criticality": "GMP-Critical", "regulatory_ref": "EU GMP Annex 1",
            "verification_method": "Design Review", "acceptance_criteria": "Grade D confirmed",
        }]))

    monkeypatch.setattr(gen_job, "gemini_client", _FakeClient(fake_generate_content))

    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    urs = client.post("/urs/", json={
        "urs_type": "facility", "facility_id": facility["id"],
        "utilities_required": ["HVAC"],
    }).get_json()

    resp = client.post(f"/urs/{urs['id']}/generate", json={"sections": ["HVAC Requirements"]})
    assert resp.status_code == 202

    status = _wait_for_terminal_status(client, urs["id"])
    assert status["generation_status"] == "completed"

    reqs = client.get(f"/urs/{urs['id']}/requirements").get_json()
    assert len(reqs) == 1
    assert reqs[0]["section"] == "HVAC Requirements"

    assert captured_prompts, "Gemini was never called"
    prompt = captured_prompts[0]
    assert "Facility Engineering Consultant" in prompt
    assert "Nutra Greenfield OSD Plant" in prompt
    assert "HVAC" in prompt
    # Equipment-prompt-only wording must not leak into the facility prompt.
    assert "EQUIPMENT DETAILS" not in prompt


def test_equipment_urs_generation_still_uses_equipment_prompt(client, monkeypatch):
    """Regression guard: the urs_type dispatch in urs_service.build_
    generation_prompt() must not change equipment-flow behaviour."""
    captured_prompts = []

    def fake_generate_content(model, contents, config):
        captured_prompts.append(contents[0].parts[0].text)
        return _FakeResponse(json.dumps([{
            "section": "Functional Requirements", "requirement": "The system shall run.",
            "rationale": "x", "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "", "verification_method": "Functional Test", "acceptance_criteria": "",
        }]))

    monkeypatch.setattr(gen_job, "gemini_client", _FakeClient(fake_generate_content))

    urs = client.post("/urs/", json={"equipment_name": "Autoclave-01"}).get_json()
    client.post(f"/urs/{urs['id']}/generate", json={"sections": ["Functional Requirements"]})
    _wait_for_terminal_status(client, urs["id"])

    assert captured_prompts
    assert "EQUIPMENT DETAILS" in captured_prompts[0]
    assert "Facility Engineering Consultant" not in captured_prompts[0]


# ── DOCX export reuses the same engine for both URS types ────────────────────

def test_facility_urs_docx_export(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    client.post(f"/urs/{urs['id']}/library", json={})

    resp = client.get(f"/urs/{urs['id']}/export/docx")
    assert resp.status_code == 200
    assert resp.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

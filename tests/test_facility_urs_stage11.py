"""
tests/test_facility_urs_stage11.py — Integration tests for the Facility URS
Stage 1.1 business-intelligence enhancement: Facility Classification,
Product Category, Regulatory Package, Production Capacity, Future
Expansion, Utility Philosophy, Validation Strategy, and Requirement Source.

Mirrors tests/test_facility_urs.py's fixtures/shape. Does not repeat Stage
1's own coverage (Facility/node CRUD, systems registry, DOCX export) — see
that file — this one is scoped to what Stage 1.1 added on top of it.
"""

import json

import pytest

from google.genai import types


def _create_project(client, name="Stage 1.1 Test Project"):
    return client.post("/projects", json={"name": name}).get_json()


def _create_facility(client, project_id, **overrides):
    payload = {
        "facility_name": "Nutra Greenfield OSD Plant",
        "facility_type": "OSD (Oral Solid Dosage)",
        "classification": "Brownfield",
        "product_category": "Injectables",
        "country": "India",
        "regulatory_market": "US FDA, Annex 1",
    }
    payload.update(overrides)
    return client.post(f"/projects/{project_id}/facility", json=payload).get_json()


# ── Facility Classification ───────────────────────────────────────────────────

def test_classification_persisted(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    assert facility["classification"] == "Brownfield"


def test_classification_defaults_when_omitted_backward_compat(client):
    """A caller that predates Stage 1.1 (omits classification entirely)
    must still succeed — mandatory is enforced client-side (the wizard),
    not by rejecting the API call. See routes/facility.py's comment."""
    project = _create_project(client)
    resp = client.post(f"/projects/{project['id']}/facility", json={"facility_name": "Legacy Facility"})
    assert resp.status_code == 201
    assert resp.get_json()["classification"] == "Greenfield"


def test_classification_rejects_invalid_value(client):
    project = _create_project(client)
    resp = client.post(f"/projects/{project['id']}/facility", json={
        "facility_name": "X", "classification": "Not A Real Classification",
    })
    assert resp.status_code == 400


def test_facility_classifications_endpoint(client):
    resp = client.get("/facility/classifications").get_json()
    assert "Greenfield" in resp["classifications"]
    assert "Brownfield" in resp["classifications"]
    assert len(resp["classifications"]) == 10


def test_design_basis_options_endpoint(client):
    resp = client.get("/facility/design-basis-options").get_json()
    assert "Tablets" in resp["product_categories"]
    assert "US FDA" in resp["regulatory_package"]
    assert "N+1 Redundancy" in resp["utility_philosophy"]
    assert "ASTM E2500" in resp["validation_strategy"]
    assert "Corporate Standard" in resp["requirement_source"]
    assert "Tablets/day" in resp["capacity_units"]


# ── design_basis persistence (JSON blob on the Facility record) ──────────────

def test_design_basis_round_trip(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    design_basis = {
        "current_capacity_value": "500000", "current_capacity_unit": "Tablets/day",
        "future_capacity_value": "1000000", "future_capacity_unit": "Tablets/day",
        "planned_expansion_pct": "50", "expandable_design": True,
        "utility_philosophy": {"HVAC": "N+1 Redundancy", "Electrical": "2N Redundancy"},
        "validation_strategy": "ASTM E2500", "requirement_source": "Corporate Standard",
    }
    updated = client.put(f"/facility/{facility['id']}", json={"design_basis": design_basis}).get_json()
    assert updated["design_basis"] == design_basis

    fetched = client.get(f"/facility/{facility['id']}").get_json()
    assert fetched["design_basis"]["validation_strategy"] == "ASTM E2500"
    assert fetched["design_basis"]["utility_philosophy"]["HVAC"] == "N+1 Redundancy"


def test_new_facility_has_empty_design_basis(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    assert facility["design_basis"] == {}


# ── Requirement library adapts to Stage 1.1 metadata ──────────────────────────

def _load_library(client, urs_id):
    return client.post(f"/urs/{urs_id}/library", json={}).get_json()


def test_library_reflects_classification_overlay(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"], classification="Brownfield")
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    reqs = _load_library(client, urs["id"])["requirements"]
    texts = " ".join(r["requirement"] for r in reqs)
    assert "tie-in" in texts.lower()


def test_library_reflects_product_category_overlay(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"], product_category="Injectables")
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    reqs = _load_library(client, urs["id"])["requirements"]
    texts = " ".join(r["requirement"] for r in reqs)
    assert "Grade A (background Grade B/C" in texts


def test_library_reflects_regulatory_package_overlay(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"], regulatory_market="Annex 1, ISO 14644")
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    reqs = _load_library(client, urs["id"])["requirements"]
    texts = " ".join(r["requirement"] for r in reqs)
    assert "Contamination Control Strategy" in texts  # Annex 1 overlay
    assert "ISO 14644-1" in texts and "ISO 14644-2" in texts  # ISO 14644 overlay


def test_library_does_not_apply_unselected_regulatory_overlays(client):
    """'Generate only relevant clauses' — a facility with no regulatory
    package selected gets no per-framework overlay content."""
    project = _create_project(client)
    # product_category="Tablets" (not the helper's default "Injectables") so
    # the Injectables product-category overlay's own Contamination Control
    # Strategy requirement doesn't confound this regulatory-overlay-only check.
    facility = _create_facility(client, project["id"], regulatory_market="", product_category="Tablets")
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    reqs = _load_library(client, urs["id"])["requirements"]
    texts = " ".join(r["requirement"] for r in reqs)
    # Stage 1's baseline already mentions "ISO 14644-1" in passing (cleanroom
    # classification basis) — the ISO 14644 *overlay*'s distinguishing
    # content is the -2 monitoring clause, only added when explicitly selected.
    assert "ISO 14644-2" not in texts
    assert "Contamination Control Strategy" not in texts


def test_library_synthesizes_utility_philosophy_requirements(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    client.put(f"/facility/{facility['id']}", json={"design_basis": {
        "utility_philosophy": {"HVAC": "N+1 Redundancy", "Nitrogen": "Shared"},
    }})
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    reqs = _load_library(client, urs["id"])["requirements"]
    hvac_reqs = [r["requirement"] for r in reqs if r["section"] == "HVAC Requirements"]
    nitrogen_reqs = [r["requirement"] for r in reqs if r["section"] == "Nitrogen Requirements"]
    assert any("N+1 Redundancy" in r for r in hvac_reqs)
    assert any("Shared" in r for r in nitrogen_reqs)


def test_library_synthesizes_expansion_requirement_only_when_expandable(client):
    project = _create_project(client)

    facility_no = _create_facility(client, project["id"], facility_name="No-Expand Facility")
    urs_no = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility_no["id"]}).get_json()
    reqs_no = _load_library(client, urs_no["id"])["requirements"]
    expansion_no = [r for r in reqs_no if r["section"] == "Future Expansion Requirements"]
    assert len(expansion_no) == 1  # only Stage 1's static baseline requirement

    facility_yes = _create_facility(client, project["id"], facility_name="Expandable Facility")
    client.put(f"/facility/{facility_yes['id']}", json={"design_basis": {
        "expandable_design": True, "future_capacity_value": "2000000",
        "future_capacity_unit": "Tablets/day", "planned_expansion_pct": "60",
    }})
    urs_yes = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility_yes["id"]}).get_json()
    reqs_yes = _load_library(client, urs_yes["id"])["requirements"]
    expansion_yes = [r for r in reqs_yes if r["section"] == "Future Expansion Requirements"]
    assert len(expansion_yes) == 2  # Stage 1 baseline + Stage 1.1 synthesized
    assert any("2000000 Tablets/day" in r["requirement"] and "60% above" in r["requirement"] for r in expansion_yes)


def test_library_reflects_validation_strategy_overlay(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    client.put(f"/facility/{facility['id']}", json={"design_basis": {"validation_strategy": "Risk-Based Validation"}})
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    reqs = _load_library(client, urs["id"])["requirements"]
    risk_reqs = [r["requirement"] for r in reqs if r["section"] == "Risk Considerations"]
    assert any("ICH Q9 risk assessment" in r for r in risk_reqs)


def test_library_stamps_requirement_source(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    client.put(f"/facility/{facility['id']}", json={"design_basis": {"requirement_source": "Customer Requirement"}})
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()
    reqs = _load_library(client, urs["id"])["requirements"]
    assert reqs  # sanity
    assert all(r["requirement_source"] == "Customer Requirement" for r in reqs)


def test_equipment_urs_requirement_source_stays_blank(client):
    """Regression guard: requirement_source is a purely additive column —
    the equipment flow (Stage 1, unaware of this field) must never populate
    it."""
    urs = client.post("/urs/", json={"equipment_name": "Autoclave-01"}).get_json()
    reqs = client.post(f"/urs/{urs['id']}/library", json={"equipment_type": "autoclave"}).get_json()["requirements"]
    assert reqs
    assert all(r.get("requirement_source", "") == "" for r in reqs)


# ── requirement_source persists through manual requirement CRUD too ─────────

def test_add_and_update_requirement_with_requirement_source(client):
    project = _create_project(client)
    facility = _create_facility(client, project["id"])
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()

    added = client.post(f"/urs/{urs['id']}/requirements/add", json={
        "req_id": "CUST-001", "section": "General Requirements",
        "requirement": "The facility shall meet a custom client spec.",
        "requirement_source": "Customer Requirement",
    }).get_json()
    assert added["requirement_source"] == "Customer Requirement"

    updated = client.put(f"/urs/{urs['id']}/requirements/{added['id']}", json={
        "requirement_source": "Internal SOP",
    }).get_json()
    assert updated["requirement_source"] == "Internal SOP"


# ── AI prompt adapts to Stage 1.1 metadata (fake Gemini, capture prompt) ─────

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


def test_generation_prompt_adapts_to_stage11_metadata(client, isolated_ai_gateway):
    import time as _time

    captured_prompts = []

    def fake_generate_content(model, contents, config):
        captured_prompts.append(contents[0].parts[0].text)
        return _FakeResponse(json.dumps([{
            "section": "HVAC Requirements", "requirement": "The facility shall maintain N+1 HVAC redundancy.",
            "rationale": "x", "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "", "verification_method": "Design Review", "acceptance_criteria": "",
        }]))

    isolated_ai_gateway.register_provider("gemini", lambda: _FakeClient(fake_generate_content), model="fake-model")

    project = _create_project(client)
    facility = _create_facility(client, project["id"], classification="Brownfield", product_category="Injectables")
    client.put(f"/facility/{facility['id']}", json={"design_basis": {
        "current_capacity_value": "500000", "current_capacity_unit": "Tablets/day",
        "future_capacity_value": "1000000", "future_capacity_unit": "Tablets/day",
        "planned_expansion_pct": "50", "expandable_design": True,
        "utility_philosophy": {"HVAC": "N+1 Redundancy"},
        "validation_strategy": "ASTM E2500",
    }})
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()

    resp = client.post(f"/urs/{urs['id']}/generate", json={"sections": ["HVAC Requirements"]})
    assert resp.status_code == 202

    deadline = _time.monotonic() + 10
    status = None
    while _time.monotonic() < deadline:
        status = client.get(f"/urs/{urs['id']}/generate/status").get_json()
        if status.get("generation_status") in ("completed", "failed"):
            break
        _time.sleep(0.1)
    assert status["generation_status"] == "completed"

    assert captured_prompts
    prompt = captured_prompts[0]
    assert "Brownfield" in prompt and "tie-in points" in prompt
    assert "Injectables" in prompt and "Grade A/B" in prompt
    assert "500000 Tablets/day" in prompt
    assert "1000000 Tablets/day" in prompt and "50% above" in prompt
    assert "N+1 Redundancy" in prompt
    assert "ASTM E2500" in prompt

    reqs = client.get(f"/urs/{urs['id']}/requirements").get_json()
    assert reqs[0]["requirement_source"] == ""  # no default declared for this facility


def test_generation_prompt_backward_compatible_with_no_stage11_metadata(client, isolated_ai_gateway):
    """A Stage-1-only facility (no classification/design_basis set beyond
    defaults) must still produce a sensible prompt, not an error or a
    prompt full of blank/None artifacts."""
    captured_prompts = []

    def fake_generate_content(model, contents, config):
        captured_prompts.append(contents[0].parts[0].text)
        return _FakeResponse(json.dumps([{
            "section": "General Requirements", "requirement": "The facility shall comply with GMP.",
            "rationale": "x", "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "", "verification_method": "Design Review", "acceptance_criteria": "",
        }]))

    isolated_ai_gateway.register_provider("gemini", lambda: _FakeClient(fake_generate_content), model="fake-model")

    project = _create_project(client)
    facility = client.post(f"/projects/{project['id']}/facility", json={
        "facility_name": "Legacy Style Facility", "facility_type": "OSD (Oral Solid Dosage)",
    }).get_json()
    urs = client.post("/urs/", json={"urs_type": "facility", "facility_id": facility["id"]}).get_json()

    resp = client.post(f"/urs/{urs['id']}/generate", json={"sections": ["General Requirements"]})
    assert resp.status_code == 202

    import time as _time
    deadline = _time.monotonic() + 10
    status = None
    while _time.monotonic() < deadline:
        status = client.get(f"/urs/{urs['id']}/generate/status").get_json()
        if status.get("generation_status") in ("completed", "failed"):
            break
        _time.sleep(0.1)
    assert status["generation_status"] == "completed"

    prompt = captured_prompts[0]
    assert "None" not in prompt
    assert "not specified" in prompt.lower()

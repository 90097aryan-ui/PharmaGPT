"""
tests/test_document_template.py — Phase 5 coverage: controlled document
templates (index/headings/sub-headings only) — data model + CRUD.

AI-prompt heading-preservation enforcement (constraining
services/qms_document_prompt.py's generation to fill within a template's
structure without removing/restructuring controlled headings) is a
separate, deferred follow-up — not covered here, since it requires live
AI-generation behavior that isn't practical to assert against in this
test suite.
"""

import pytest

from pharmagpt import qms_document_database as qdb
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as COMPANY_ID

STRUCTURE = [
    {"heading": "1. Purpose", "sub_headings": []},
    {"heading": "2. Scope", "sub_headings": []},
    {"heading": "3. Procedure", "sub_headings": ["3.1 Preparation", "3.2 Execution", "3.3 Cleanup"]},
    {"heading": "4. References", "sub_headings": []},
]


def test_create_and_get_template(db_path):
    t = qdb.create_template("SOP", "Standard Cleaning SOP Template", STRUCTURE, company_id=COMPANY_ID)
    fetched = qdb.get_template(t["id"])
    assert fetched["name"] == "Standard Cleaning SOP Template"
    assert fetched["structure"] == STRUCTURE
    assert fetched["doc_type"] == "SOP"


def test_list_templates_filters_by_doc_type(db_path):
    # database.py::init_db() always seeds one platform-wide default SOP
    # template ("Standard Operating Procedure (Default)", spec §1 gap
    # closure — the controlled SOP template picker must have a real row to
    # resolve, not just describe headings in the AI prompt) — every SOP-scoped
    # assertion here accounts for that seeded row rather than asserting an
    # exact count of only the templates this test itself creates.
    qdb.create_template("SOP", "SOP Template", STRUCTURE, company_id=COMPANY_ID)
    qdb.create_template("Protocol", "Protocol Template", STRUCTURE, company_id=COMPANY_ID)
    sop_only = qdb.list_templates("SOP", COMPANY_ID)
    sop_names = {t["name"] for t in sop_only}
    assert "SOP Template" in sop_names
    assert "Protocol Template" not in sop_names


def test_list_templates_includes_platform_default_and_company_specific(db_path):
    qdb.create_template("SOP", "Platform Default SOP", STRUCTURE, company_id="")
    qdb.create_template("SOP", "Company-Specific SOP", STRUCTURE, company_id=COMPANY_ID)
    templates = qdb.list_templates("SOP", COMPANY_ID)
    names = {t["name"] for t in templates}
    assert {"Platform Default SOP", "Company-Specific SOP"} <= names


def test_document_can_be_created_from_a_template(db_path):
    t = qdb.create_template("SOP", "SOP Template", STRUCTURE, company_id=COMPANY_ID)
    doc = qdb.create_document({"title": "Cleaning SOP", "template_id": t["id"]}, company_id=COMPANY_ID)
    assert doc["template_id"] == t["id"]


# ── Routes ─────────────────────────────────────────────────────────────────

def test_template_route_create_and_list(client):
    r = client.post("/qms/documents/templates",
                     json={"doc_type": "SOP", "name": "Cleaning SOP Template", "structure": STRUCTURE})
    assert r.status_code == 201, r.get_json()
    template_id = r.get_json()["id"]

    r = client.get("/qms/documents/templates?doc_type=SOP")
    assert r.status_code == 200
    assert any(t["id"] == template_id for t in r.get_json())

    r = client.get(f"/qms/documents/templates/{template_id}")
    assert r.status_code == 200
    assert r.get_json()["structure"] == STRUCTURE


def test_template_route_rejects_empty_structure(client):
    r = client.post("/qms/documents/templates",
                     json={"doc_type": "SOP", "name": "Bad Template", "structure": []})
    assert r.status_code == 400


def test_template_route_rejects_missing_name(client):
    r = client.post("/qms/documents/templates", json={"doc_type": "SOP", "structure": STRUCTURE})
    assert r.status_code == 400

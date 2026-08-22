"""
tests/test_document_sop_workflow.py — Document Control SOP workflow
correction (scope-locked to SOP; see task spec).

Covers the three concrete gaps the redesign fixed:
  1. "Failed to load templates" — GET /qms/documents/templates?doc_type=SOP
     must always resolve at least the platform-seeded default template
     (database.py::init_db).
  2. ".md instead of .docx" — GET /qms/documents/templates/<id>/download
     must return a genuine DOCX package (python-docx-openable), correct
     mimetype, correct .docx filename — never markdown.
  3. AI-Assisted SOP Creation's Knowledge Base retrieval — generate_draft's
     new `equipment_id` body param must resolve to that equipment's linked
     Knowledge Base document text and feed it into the AI prompt, without
     ever inventing content when nothing is linked.
"""

import io

import pytest
from docx import Document as DocxDocument

from pharmagpt import database as db
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID as _TEST_COMPANY_ID


def _make_equipment(client):
    project = client.post(
        "/projects", json={"name": "SOP KB Project", "equipment_name": "Tablet Packing Machine",
                            "manufacturer": "ACME", "department": "Production",
                            "validation_type": "IQ/OQ/PQ"},
    ).get_json()
    equipment = client.post(
        f"/projects/{project['id']}/equipment", json={"name": "Tablet Packing Machine 1"},
    ).get_json()
    return equipment


def _make_kb_document_with_text(text_content: str) -> dict:
    kb_doc = db.create_kb_document(
        title="Tablet Packing Machine — Operating Manual", folder="Equipment Manuals", tags="",
        doc_version="1.0", effective_date=None, review_date=None,
        original_name="manual.pdf", stored_filename="manual.pdf", file_type="pdf", file_size=1024,
        company_id=_TEST_COMPANY_ID, created_by="tester",
    )
    db.update_kb_document_text(kb_doc["id"], text_content, word_count=len(text_content.split()),
                                page_count=1, extraction_status="complete")
    return kb_doc


# ── Bug #2 root cause: "Failed to load templates" ────────────────────────────

def test_sop_template_listing_resolves_seeded_default(client):
    templates = client.get("/qms/documents/templates?doc_type=SOP").get_json()
    assert any(t["name"] == "Standard Operating Procedure (Default)" for t in templates)


# ── Bug #1 root cause: template download must be a real DOCX ────────────────

def test_template_download_is_a_valid_docx_with_controlled_headings(client):
    templates = client.get("/qms/documents/templates?doc_type=SOP").get_json()
    default_template = next(t for t in templates if t["name"] == "Standard Operating Procedure (Default)")

    resp = client.get(f"/qms/documents/templates/{default_template['id']}/download")
    assert resp.status_code == 200
    assert resp.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert resp.headers["Content-Disposition"].split("filename=")[1].strip('"').endswith(".docx")

    # Must be a genuine DOCX package (python-docx can open it) — not markdown
    # bytes wearing a .docx extension.
    docx_doc = DocxDocument(io.BytesIO(resp.data))
    body_text = "\n".join(p.text for p in docx_doc.paragraphs)
    assert "Purpose" in body_text
    assert "Procedure" in body_text


def test_template_download_unknown_id_404s(client):
    resp = client.get("/qms/documents/templates/999999/download")
    assert resp.status_code == 404


# ── AI-Assisted SOP Creation: equipment/Knowledge Base retrieval ────────────

@pytest.fixture()
def capture_prompt(monkeypatch):
    import pharmagpt.routes.qms_documents as doc_routes
    captured = {}

    def _fake(prompt, temperature=0.3):
        captured["prompt"] = prompt
        yield "# SOP\n\n## 1. Purpose\nText.\n"

    monkeypatch.setattr(doc_routes, "stream_gemini", _fake)
    return captured


def test_generate_draft_with_equipment_id_pulls_linked_kb_text_into_prompt(client, capture_prompt):
    equipment = _make_equipment(client)
    kb_doc = _make_kb_document_with_text(
        "Operating parameters: compression force 8-12 kN. Cleaning agent: 70% IPA."
    )
    link_resp = client.post(
        f"/equipment/{equipment['id']}/documents",
        json={"document_role": "user_manual", "source_type": "kb", "source_id": kb_doc["id"]},
    )
    assert link_resp.status_code == 201

    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "doc_type": "SOP"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={"equipment_id": equipment["id"]})
    assert r.status_code == 200

    assert "compression force 8-12 kN" in capture_prompt["prompt"]
    assert "70% IPA" in capture_prompt["prompt"]
    # Hallucination-prevention instruction must accompany any retrieved context.
    assert "INFORMATION GAP" in capture_prompt["prompt"]


def test_generate_draft_with_equipment_id_but_no_linked_documents_does_not_invent_content(client, capture_prompt):
    equipment = _make_equipment(client)
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "doc_type": "SOP"}).get_json()

    r = client.post(f"/qms/documents/{doc['id']}/generate", json={"equipment_id": equipment["id"]})
    assert r.status_code == 200
    assert "No controlled reference documents are linked" in capture_prompt["prompt"]


def test_generate_draft_with_unknown_equipment_id_falls_back_to_no_kb_context(client, capture_prompt):
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "doc_type": "SOP"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={"equipment_id": 999999})
    assert r.status_code == 200
    assert "RELEVANT KNOWLEDGE BASE CONTEXT" not in capture_prompt["prompt"]


def test_generate_draft_without_equipment_id_is_unaffected(client, capture_prompt):
    """Existing manual 'Generate Draft with AI' callers (no equipment_id)
    must behave exactly as before this change."""
    doc = client.post("/qms/documents", json={"title": "Cleaning SOP", "doc_type": "SOP"}).get_json()
    r = client.post(f"/qms/documents/{doc['id']}/generate", json={})
    assert r.status_code == 200
    assert "RELEVANT KNOWLEDGE BASE CONTEXT" not in capture_prompt["prompt"]

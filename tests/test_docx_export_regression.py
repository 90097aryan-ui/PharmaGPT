"""
tests/test_docx_export_regression.py — Regression protection for the
markdown_to_docx() API mismatch that broke every DOCX export after the
document-generator refactor (routes were still calling the pre-refactor
signature: markdown_to_docx(content, form_data, doc_type, title)).

Current signature (pharmagpt/services/doc_exporter.py):
    markdown_to_docx(content: str, doc_type: str, form_data: dict) -> bytes

Two layers are covered:
  1. A direct unit call proving the current signature works and returns a
     non-empty DOCX.
  2. An end-to-end Flask test-client pass over every export/docx route in
     the app, proving each one returns HTTP 200 with a non-empty
     application/vnd.openxmlformats... payload. If any route regresses back
     to the old call signature (or any other TypeError), this fails loudly
     instead of surfacing as a 500 in production.
"""

DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_markdown_to_docx_current_signature():
    """markdown_to_docx(content, doc_type, form_data) must succeed and produce bytes."""
    from pharmagpt.services.doc_exporter import markdown_to_docx

    docx_bytes = markdown_to_docx(
        "# Title\n\nSome **markdown** content.",
        "URS",
        {"title": "Unit Test Doc"},
    )
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 0


def _assert_docx(resp):
    assert resp.status_code == 200, resp.get_data(as_text=True)[:500]
    assert resp.mimetype == DOCX_MIMETYPE
    assert len(resp.data) > 0


def test_urs_export_docx(client):
    urs = client.post("/urs/", json={"title": "Reg Test URS", "equipment_name": "Autoclave"}).get_json()
    client.post(f"/urs/{urs['id']}/requirements", json=[
        {"req_id": "REQ-001", "section": "General Requirements", "requirement": "Shall log cycles.",
         "priority": "High", "gmp_criticality": "GMP", "verification_method": "Functional Test",
         "acceptance_criteria": "Logs visible"},
    ])
    _assert_docx(client.get(f"/urs/{urs['id']}/export/docx"))


def test_risk_export_docx(client):
    a = client.post("/risk/assessments", json={"title": "Reg Test Risk", "equipment": "Mixer"}).get_json()
    _assert_docx(client.post(f"/risk/assessments/{a['id']}/export/docx"))


def test_qms_capa_export_docx(client):
    capa = client.post("/qms/capa", json={"title": "Reg Test CAPA", "department": "QA"}).get_json()
    _assert_docx(client.post(f"/qms/capa/{capa['id']}/export/docx"))


def test_qms_change_control_export_docx(client):
    cc = client.post("/qms/change-control", json={"title": "Reg Test CC", "department": "QA"}).get_json()
    _assert_docx(client.post(f"/qms/change-control/{cc['id']}/export/docx"))


def test_qms_deviation_export_docx(client):
    dev = client.post("/qms/deviations", json={"title": "Reg Test Deviation", "department": "QA"}).get_json()
    _assert_docx(client.post(f"/qms/deviations/{dev['id']}/export/docx"))


def test_qms_document_export_docx(client):
    doc = client.post("/qms/documents", json={"title": "Reg Test SOP", "doc_type": "SOP", "department": "QA"}).get_json()
    _assert_docx(client.post(f"/qms/documents/{doc['id']}/export/docx"))


def test_report_export_docx(client):
    report = client.post("/report/", json={"title": "Reg Test Report", "equipment_name": "Autoclave"}).get_json()
    _assert_docx(client.get(f"/report/{report['id']}/export/docx"))


def test_qual_traceability_export_docx(client):
    qual = client.post("/qual/", json={"title": "Reg Test Qual", "equipment_name": "Autoclave"}).get_json()
    _assert_docx(client.get(f"/qual/{qual['id']}/traceability/export/docx"))


def test_qual_protocol_export_docx(client):
    qual = client.post("/qual/", json={"title": "Reg Test Qual 2", "equipment_name": "Autoclave"}).get_json()
    for ptype in ("IQ", "OQ", "PQ"):
        protocol = client.post(f"/qual/{qual['id']}/protocols", json={"protocol_type": ptype}).get_json()
        _assert_docx(client.get(f"/qual/{qual['id']}/protocols/{protocol['id']}/export/docx"))


def test_validation_export_docx(client):
    """Generic export route used by the standalone document generator."""
    resp = client.post("/validation/export/docx", json={
        "doc_type": "OQ",
        "title": "Reg Test Validation Doc",
        "form_data": {},
        "content": "# OQ Protocol\n\nSome content.",
    })
    _assert_docx(resp)

"""
tests/test_equipment_links.py — Regression coverage for the Phase 3
(Enterprise Validation Platform) traceability work: widening
equipment_documents' source_type vocabulary to also cover deviation/capa/
change_control/risk_assessment (docs/DATABASE_ARCHITECTURE.md §6's
equipment_links mechanism), so the Project -> Equipment -> Validation
Documents -> QMS Records -> Knowledge Base traceability chain is navigable
end to end. Same polymorphic table, same pattern as the existing kb/project
source types — no rename, no schema change.
"""

from pharmagpt import equipment_database as equipdb


def _make_equipment(client):
    project = client.post(
        "/projects", json={"name": "Traceability Project", "equipment_name": "HPLC",
                            "manufacturer": "Agilent", "department": "QC",
                            "validation_type": "IQ/OQ/PQ"},
    ).get_json()
    equipment = client.post(
        f"/projects/{project['id']}/equipment", json={"name": "HPLC System 1"},
    ).get_json()
    return project, equipment


def test_source_types_include_all_four_qms_record_types():
    assert set(equipdb.SOURCE_TYPES) == {
        "kb", "project", "deviation", "capa", "change_control", "risk_assessment",
    }


def test_link_equipment_to_deviation(client):
    _, equipment = _make_equipment(client)
    deviation = client.post("/qms/deviations", json={"title": "Deviation 1"}).get_json()

    resp = client.post(
        f"/equipment/{equipment['id']}/documents",
        json={"document_role": "quality_record", "source_type": "deviation", "source_id": deviation["id"]},
    )
    assert resp.status_code == 201
    link = resp.get_json()
    assert link["source_type"] == "deviation"
    assert link["source_id"] == deviation["id"]

    links = client.get(f"/equipment/{equipment['id']}/documents").get_json()
    matching = [l for l in links if l["id"] == link["id"]]
    assert len(matching) == 1
    assert matching[0]["resolved"] is True
    assert matching[0]["display_title"] == "Deviation 1"


def test_link_equipment_to_capa(client):
    _, equipment = _make_equipment(client)
    capa = client.post("/qms/capa", json={"title": "CAPA 1"}).get_json()

    resp = client.post(
        f"/equipment/{equipment['id']}/documents",
        json={"document_role": "quality_record", "source_type": "capa", "source_id": capa["id"]},
    )
    assert resp.status_code == 201


def test_link_equipment_to_change_control(client):
    _, equipment = _make_equipment(client)
    cc = client.post("/qms/change-control", json={"title": "CC 1"}).get_json()

    resp = client.post(
        f"/equipment/{equipment['id']}/documents",
        json={"document_role": "quality_record", "source_type": "change_control", "source_id": cc["id"]},
    )
    assert resp.status_code == 201


def test_link_equipment_to_risk_assessment(client):
    _, equipment = _make_equipment(client)
    assessment = client.post("/risk/assessments", json={"title": "Risk 1"}).get_json()

    resp = client.post(
        f"/equipment/{equipment['id']}/documents",
        json={"document_role": "quality_record", "source_type": "risk_assessment", "source_id": assessment["id"]},
    )
    assert resp.status_code == 201


def test_invalid_source_type_rejected(client):
    _, equipment = _make_equipment(client)
    resp = client.post(
        f"/equipment/{equipment['id']}/documents",
        json={"document_role": "quality_record", "source_type": "not_a_real_type", "source_id": 1},
    )
    assert resp.status_code == 400


def test_nonexistent_qms_record_rejected(client):
    _, equipment = _make_equipment(client)
    resp = client.post(
        f"/equipment/{equipment['id']}/documents",
        json={"document_role": "quality_record", "source_type": "deviation", "source_id": 999999},
    )
    assert resp.status_code == 404

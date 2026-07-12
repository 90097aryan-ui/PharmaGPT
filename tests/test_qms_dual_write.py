"""
tests/test_qms_dual_write.py — Phase 3.5 dual-write coverage
(docs/PHASE3_EXECUTION_PLAN.md).

Same pattern as the other Phase 3 dual-write test files: real pharmagpt.app
+ real middleware, the relevant routes module's qms_repo mocked so no real
Supabase/Postgres call is made. Covers all four record types (deviation,
capa, change_control, risk_assessment) since they share one repo module.
"""

from unittest.mock import patch

import pytest

from pharmagpt import config
from pharmagpt import qms_capa_database as cdb
from pharmagpt import qms_change_control_database as ccdb
from pharmagpt import qms_deviation_database as ddb
from pharmagpt import risk_database as rdb
from pharmagpt.auth.context import TenantContext

SAMPLE_TENANT = TenantContext(
    user_id="user-1", email="jane@example.com", display_name="Jane Admin",
    role="company_admin", company_id="company-1",
)

SUPER_ADMIN_TENANT = TenantContext(
    user_id="super-1", email="super@example.com", display_name="Super Admin",
    role="super_admin", company_id=None,
)

AUTH_HEADERS = {"Authorization": "Bearer good-token"}


@pytest.fixture()
def client(db_path):
    import pharmagpt.app as appmod

    return appmod.app.test_client()


@pytest.fixture()
def authed():
    return patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SAMPLE_TENANT
    )


# ── Deviations ───────────────────────────────────────────────────────────────

def test_deviation_dual_write_disabled_by_default(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "sqlite")
    with authed, patch("pharmagpt.routes.qms_deviations.qms_repo.create_record") as mock_create:
        resp = client.post("/qms/deviations", json={"title": "Dev 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    mock_create.assert_not_called()
    assert ddb.get_deviation(resp.get_json()["id"])["postgres_id"] is None


def test_deviation_dual_write_create_syncs_record_and_audit_entry(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.qms_deviations.qms_repo.create_record", return_value={"id": "pg-dev-1"},
    ) as mock_create, patch(
        "pharmagpt.routes.qms_deviations.qms_repo.add_audit_entry"
    ) as mock_audit:
        resp = client.post("/qms/deviations", json={"title": "Dev 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    deviation_id = resp.get_json()["id"]
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args[0] == "good-token"
    assert args[1] == "company-1"
    assert args[2] == "deviation"
    assert kwargs["title"] == "Dev 1"
    mock_audit.assert_called_once()
    audit_args, _ = mock_audit.call_args
    assert audit_args[2] == "deviation"
    assert audit_args[3] == "pg-dev-1"
    assert ddb.get_deviation(deviation_id)["postgres_id"] == "pg-dev-1"


def test_deviation_dual_write_create_failure_does_not_break_response(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.qms_deviations.qms_repo.create_record",
        side_effect=RuntimeError("Postgres unreachable"),
    ):
        resp = client.post("/qms/deviations", json={"title": "Dev 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    assert ddb.get_deviation(resp.get_json()["id"]) is not None


def test_deviation_dual_write_delete_calls_repo(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.qms_deviations.qms_repo.create_record", return_value={"id": "pg-dev-2"},
    ), patch("pharmagpt.routes.qms_deviations.qms_repo.add_audit_entry"):
        deviation_id = client.post(
            "/qms/deviations", json={"title": "Dev 1"}, headers=AUTH_HEADERS
        ).get_json()["id"]

    with authed, patch("pharmagpt.routes.qms_deviations.qms_repo.delete_record") as mock_delete:
        resp = client.delete(f"/qms/deviations/{deviation_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    mock_delete.assert_called_once_with("good-token", "company-1", "deviation", "pg-dev-2")


# ── CAPAs ────────────────────────────────────────────────────────────────────

def test_capa_dual_write_create_syncs_record_and_audit_entry(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.qms_capa.qms_repo.create_record", return_value={"id": "pg-capa-1"},
    ) as mock_create, patch("pharmagpt.routes.qms_capa.qms_repo.add_audit_entry") as mock_audit:
        resp = client.post("/qms/capa", json={"title": "CAPA 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    capa_id = resp.get_json()["id"]
    mock_create.assert_called_once()
    assert mock_create.call_args[0][2] == "capa"
    mock_audit.assert_called_once()
    assert cdb.get_capa(capa_id)["postgres_id"] == "pg-capa-1"


def test_capa_dual_write_disabled_by_default(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "sqlite")
    with authed, patch("pharmagpt.routes.qms_capa.qms_repo.create_record") as mock_create:
        resp = client.post("/qms/capa", json={"title": "CAPA 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    mock_create.assert_not_called()


def test_capa_dual_write_update_calls_repo(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.qms_capa.qms_repo.create_record", return_value={"id": "pg-capa-2"},
    ), patch("pharmagpt.routes.qms_capa.qms_repo.add_audit_entry"):
        capa_id = client.post("/qms/capa", json={"title": "CAPA 1"}, headers=AUTH_HEADERS).get_json()["id"]

    with authed, patch(
        "pharmagpt.routes.qms_capa.qms_repo.update_record", return_value={"id": "pg-capa-2"}
    ) as mock_update:
        resp = client.put(f"/qms/capa/{capa_id}", json={"title": "CAPA 1 renamed"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    mock_update.assert_called_once()
    assert mock_update.call_args[0][3] == "pg-capa-2"


# ── Change Controls ────────────────────────────────────────────────────────

def test_change_control_dual_write_create_syncs_record_and_audit_entry(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.qms_change_control.qms_repo.create_record", return_value={"id": "pg-cc-1"},
    ) as mock_create, patch(
        "pharmagpt.routes.qms_change_control.qms_repo.add_audit_entry"
    ) as mock_audit:
        resp = client.post("/qms/change-control", json={"title": "CC 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    cc_id = resp.get_json()["id"]
    mock_create.assert_called_once()
    assert mock_create.call_args[0][2] == "change_control"
    mock_audit.assert_called_once()
    assert ccdb.get_change_control(cc_id)["postgres_id"] == "pg-cc-1"


def test_change_control_dual_write_delete_swallows_failure(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.qms_change_control.qms_repo.create_record", return_value={"id": "pg-cc-2"},
    ), patch("pharmagpt.routes.qms_change_control.qms_repo.add_audit_entry"):
        cc_id = client.post(
            "/qms/change-control", json={"title": "CC 1"}, headers=AUTH_HEADERS
        ).get_json()["id"]

    with authed, patch(
        "pharmagpt.routes.qms_change_control.qms_repo.delete_record",
        side_effect=RuntimeError("Postgres error"),
    ):
        resp = client.delete(f"/qms/change-control/{cc_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200


# ── Risk Assessments ─────────────────────────────────────────────────────────

def test_risk_assessment_dual_write_create_syncs_record_no_audit_entry(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.risk.qms_repo.create_record", return_value={"id": "pg-risk-1"},
    ) as mock_create, patch("pharmagpt.routes.risk.qms_repo.add_audit_entry") as mock_audit:
        resp = client.post("/risk/assessments", json={"title": "Risk 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    assessment_id = resp.get_json()["id"]
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args[2] == "risk_assessment"
    assert "project_id" not in kwargs  # risk_assessments has no project_id in SQLite at all
    mock_audit.assert_not_called()  # risk uses its own risk_approval table, not qms_audit_trail
    assert rdb.get_assessment(assessment_id)["postgres_id"] == "pg-risk-1"


def test_risk_assessment_dual_write_disabled_by_default(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "sqlite")
    with authed, patch("pharmagpt.routes.risk.qms_repo.create_record") as mock_create:
        resp = client.post("/risk/assessments", json={"title": "Risk 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    mock_create.assert_not_called()


def test_risk_assessment_dual_write_skips_super_admin(client, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with patch(
        "pharmagpt.auth.middleware.resolve_tenant_context", return_value=SUPER_ADMIN_TENANT
    ), patch("pharmagpt.routes.risk.qms_repo.create_record") as mock_create:
        resp = client.post("/risk/assessments", json={"title": "Risk 1"}, headers=AUTH_HEADERS)

    assert resp.status_code == 201
    mock_create.assert_not_called()


def test_risk_assessment_dual_write_delete_calls_repo(client, authed, monkeypatch):
    monkeypatch.setattr(config, "QMS_BACKEND", "dual")
    with authed, patch(
        "pharmagpt.routes.risk.qms_repo.create_record", return_value={"id": "pg-risk-2"},
    ):
        assessment_id = client.post(
            "/risk/assessments", json={"title": "Risk 1"}, headers=AUTH_HEADERS
        ).get_json()["id"]

    with authed, patch("pharmagpt.routes.risk.qms_repo.delete_record") as mock_delete:
        resp = client.delete(f"/risk/assessments/{assessment_id}", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    mock_delete.assert_called_once_with("good-token", "company-1", "risk_assessment", "pg-risk-2")

"""
tests/test_global_knowledge_governance.py — Yuktav Brain Global Regulatory
Knowledge governance (staging/publish/retire lifecycle for company_id=''
kb_documents rows). See PROJECT_MEMORY/DECISIONS.md for the architecture.

Two test styles, matching the two things being verified:

  * Route-level (Flask `client` fixture + tests/conftest.py's documented
    `monkeypatch.setattr(conftest_module, "_TEST_TENANT", ...)` technique,
    already used by tests/test_esignature_module_integration.py) — proves
    authorization and segregation-of-duty enforcement at the HTTP layer.

  * Service-level (direct db.create_kb_document()/retrieval_engine calls,
    same style as tests/test_retrieval_engine_tenant_isolation.py) — proves
    the retrieval/lifecycle/provenance behavior without going through HTTP.

Does not modify tests/test_retrieval_engine_tenant_isolation.py — TEN-01
stays untouched; test_global_content_coexists_with_ten01_isolation below
adds compatibility coverage from this new file instead.
"""

import io

import pytest

import tests.conftest as conftest_module
from pharmagpt import database as db
from pharmagpt.auth.context import TenantContext
from pharmagpt.services import retrieval_engine
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID

SUPER_ADMIN_A = TenantContext(
    user_id="super-admin-a", email="admin-a@yuktav.example",
    display_name="Super Admin A", role="super_admin", company_id=None,
)
SUPER_ADMIN_B = TenantContext(
    user_id="super-admin-b", email="admin-b@yuktav.example",
    display_name="Super Admin B", role="super_admin", company_id=None,
)
COMPANY_ADMIN = TenantContext(
    user_id="company-admin-1", email="ca@example.com",
    display_name="Company Admin", role="company_admin", company_id=BOOTSTRAP_COMPANY_ID,
)
REVIEWER_QA = TenantContext(
    user_id="reviewer-qa-1", email="rq@example.com",
    display_name="Reviewer QA", role="reviewer_qa", company_id=BOOTSTRAP_COMPANY_ID,
)
PLAIN_USER = TenantContext(
    user_id="plain-user-1", email="user@example.com",
    display_name="Plain User", role="user", company_id=BOOTSTRAP_COMPANY_ID,
)

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"
COMPANY_B = "company-b-22222222-2222-2222-2222-222222222222"

_SHARED_QUERY = "autoclave sterilization cycle validation SOP"


def _as(monkeypatch, tenant: TenantContext) -> None:
    """Make the next request(s) through the `client` fixture authenticate
    as `tenant` — see tests/conftest.py's _fill_in_fake_tenant_for_auth_
    bypassed_tests, which resolves _TEST_TENANT by name at request time."""
    monkeypatch.setattr(conftest_module, "_TEST_TENANT", tenant)


def _stage_payload(**overrides) -> dict:
    payload = {
        "file": (io.BytesIO(b"ICH Q7 Good Manufacturing Practice Guide for APIs. " * 20), "ich_q7.pdf"),
        "content_category": "regulatory_source",
        "source_authority": "ICH",
        "title": "ICH Q7",
    }
    payload.update(overrides)
    return payload


def _seed_global_document(content_status: str, content_category: str, secret_marker: str,
                          supersedes: int | None = None, created_by: str = "super-admin-a") -> dict:
    """Seed a company_id='' kb_documents row directly (bypassing the upload
    pipeline/route, same rationale as test_retrieval_engine_tenant_isolation.
    py's _seed_kb_document) with extraction already marked complete."""
    row = db.create_kb_document(
        title=f"Global Doc {secret_marker}", folder="Regulations", tags="",
        doc_version="1.0", effective_date=None, review_date=None,
        original_name=f"{secret_marker}.pdf", stored_filename=f"{secret_marker}.pdf",
        file_type="pdf", file_size=1024, company_id="", created_by=created_by,
        content_category=content_category, source_authority="ICH",
        source_reference="ICH Q7", jurisdiction="Global", publication_date="2020-01-01",
        content_status=content_status, supersedes=supersedes,
    )
    conn = db.get_connection()
    conn.execute(
        "UPDATE kb_documents SET text_content = ?, extraction_status = 'ok' WHERE id = ?",
        (f"{_SHARED_QUERY} procedure. {secret_marker} " * 20, row["id"]),
    )
    conn.commit()
    conn.close()
    return db.get_kb_document(row["id"])


def _seed_client_document(company_id: str, secret_marker: str) -> dict:
    row = db.create_kb_document(
        title=f"Client Doc {secret_marker}", folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None, original_name=f"{secret_marker}.pdf",
        stored_filename=f"{secret_marker}.pdf", file_type="pdf", file_size=1024,
        company_id=company_id,
    )
    conn = db.get_connection()
    conn.execute(
        "UPDATE kb_documents SET text_content = ?, extraction_status = 'ok' WHERE id = ?",
        (f"{_SHARED_QUERY} procedure. {secret_marker} " * 20, row["id"]),
    )
    conn.commit()
    conn.close()
    return db.get_kb_document(row["id"])


# ── Authorization: only super_admin may stage global content ────────────────

def test_super_admin_can_stage_global_content(client, monkeypatch):
    _as(monkeypatch, SUPER_ADMIN_A)
    resp = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["company_id"] == ""
    assert body["content_status"] == "staged"
    assert body["created_by"] == SUPER_ADMIN_A.user_id
    assert body["content_category"] == "regulatory_source"


def test_company_admin_cannot_stage_global_content(client, monkeypatch):
    _as(monkeypatch, COMPANY_ADMIN)
    resp = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data")
    assert resp.status_code == 403


def test_reviewer_qa_cannot_stage_global_content(client, monkeypatch):
    _as(monkeypatch, REVIEWER_QA)
    resp = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data")
    assert resp.status_code == 403


def test_user_cannot_stage_global_content(client, monkeypatch):
    _as(monkeypatch, PLAIN_USER)
    resp = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data")
    assert resp.status_code == 403


def test_invalid_content_category_rejected(client, monkeypatch):
    _as(monkeypatch, SUPER_ADMIN_A)
    resp = client.post(
        "/kb/global/documents",
        data=_stage_payload(content_category="not_a_real_category"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


# ── Publishing: segregation of duties, identity from session ────────────────

def test_authoring_super_admin_cannot_publish_own_document(client, monkeypatch):
    _as(monkeypatch, SUPER_ADMIN_A)
    staged = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data").get_json()

    _as(monkeypatch, SUPER_ADMIN_A)
    resp = client.post(f"/kb/global/documents/{staged['id']}/publish")
    assert resp.status_code == 403
    assert db.get_kb_document(staged["id"])["content_status"] == "staged"


def test_different_super_admin_can_publish(client, monkeypatch):
    _as(monkeypatch, SUPER_ADMIN_A)
    staged = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data").get_json()

    _as(monkeypatch, SUPER_ADMIN_B)
    resp = client.post(f"/kb/global/documents/{staged['id']}/publish")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["content_status"] == "active"
    assert body["published_by"] == SUPER_ADMIN_B.user_id


def test_published_by_derived_from_session_not_request_body(client, monkeypatch):
    _as(monkeypatch, SUPER_ADMIN_A)
    staged = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data").get_json()

    _as(monkeypatch, SUPER_ADMIN_B)
    resp = client.post(
        f"/kb/global/documents/{staged['id']}/publish",
        json={"published_by": "someone-else", "role": "super_admin", "company_id": "spoofed-company"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["published_by"] == SUPER_ADMIN_B.user_id
    assert body["company_id"] == ""


def test_non_super_admin_cannot_publish(client, monkeypatch):
    _as(monkeypatch, SUPER_ADMIN_A)
    staged = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data").get_json()

    _as(monkeypatch, COMPANY_ADMIN)
    resp = client.post(f"/kb/global/documents/{staged['id']}/publish")
    assert resp.status_code == 403


def test_non_super_admin_cannot_retire(client, monkeypatch):
    _as(monkeypatch, SUPER_ADMIN_A)
    staged = client.post("/kb/global/documents", data=_stage_payload(), content_type="multipart/form-data").get_json()
    _as(monkeypatch, SUPER_ADMIN_B)
    client.post(f"/kb/global/documents/{staged['id']}/publish")

    _as(monkeypatch, PLAIN_USER)
    resp = client.post(f"/kb/global/documents/{staged['id']}/retire")
    assert resp.status_code == 403


# ── Retrieval: staged/superseded/retired never reach the Brain ──────────────

def test_staged_global_content_not_retrievable(db_path):
    _seed_global_document("staged", "regulatory_source", "STAGED-SECRET")
    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )
    assert "STAGED-SECRET" not in (result.context_text or "")


def test_published_global_content_retrievable_by_multiple_tenants(db_path):
    _seed_global_document("active", "regulatory_source", "ACTIVE-SECRET")
    for company in (COMPANY_A, COMPANY_B):
        result = retrieval_engine.retrieve_context(
            document_type="SOP", project_id=0, company_id=company,
            questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
        )
        assert "ACTIVE-SECRET" in result.context_text


def test_superseded_global_content_not_retrieved(db_path):
    old = _seed_global_document("superseded", "regulatory_source", "OLD-SUPERSEDED-SECRET")
    _seed_global_document("active", "regulatory_source", "NEW-VERSION-SECRET", supersedes=old["id"])
    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )
    assert "OLD-SUPERSEDED-SECRET" not in result.context_text
    assert "NEW-VERSION-SECRET" in result.context_text


def test_retired_global_content_not_retrieved(db_path):
    _seed_global_document("retired", "regulatory_source", "RETIRED-SECRET")
    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )
    assert "RETIRED-SECRET" not in (result.context_text or "")


def test_historical_superseded_and_retired_content_remains_stored(db_path):
    old = _seed_global_document("superseded", "regulatory_source", "HIST-SUPERSEDED")
    retired = _seed_global_document("retired", "regulatory_source", "HIST-RETIRED")
    assert db.get_kb_document(old["id"]) is not None
    assert db.get_kb_document(retired["id"]) is not None
    assert db.get_kb_document(old["id"])["content_status"] == "superseded"
    assert db.get_kb_document(retired["id"])["content_status"] == "retired"


def test_publish_flips_superseded_document_atomically(db_path):
    """Exercises database.py::publish_global_kb_document directly — the
    supersedes flip happens at publish time of the *new* version, not at
    staging time, so there is never a window with zero active versions."""
    old = _seed_global_document("active", "regulatory_source", "V1-ACTIVE")
    new = _seed_global_document("staged", "regulatory_source", "V2-STAGED", supersedes=old["id"])

    published = db.publish_global_kb_document(new["id"], published_by="super-admin-b")

    assert published["content_status"] == "active"
    assert db.get_kb_document(old["id"])["content_status"] == "superseded"


# ── Tenant isolation: confirms TEN-01 remains intact alongside the new lifecycle ──

def test_global_content_coexists_with_ten01_isolation(db_path):
    _seed_global_document("active", "regulatory_source", "GLOBAL-EVIDENCE")
    _seed_client_document(COMPANY_A, "COMPANY-A-PRIVATE")
    _seed_client_document(COMPANY_B, "COMPANY-B-PRIVATE")

    result_a = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )
    result_b = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_B,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )

    assert "GLOBAL-EVIDENCE" in result_a.context_text
    assert "COMPANY-A-PRIVATE" in result_a.context_text
    assert "COMPANY-B-PRIVATE" not in result_a.context_text

    assert "GLOBAL-EVIDENCE" in result_b.context_text
    assert "COMPANY-B-PRIVATE" in result_b.context_text
    assert "COMPANY-A-PRIVATE" not in result_b.context_text


def test_global_content_not_associated_with_any_client(db_path):
    global_doc = _seed_global_document("active", "regulatory_source", "UNOWNED")
    assert global_doc["company_id"] == ""
    # The ordinary tenant-scoped KB listing must never surface it.
    assert all(d["id"] != global_doc["id"] for d in db.get_kb_documents(COMPANY_A))
    assert all(d["id"] != global_doc["id"] for d in db.get_kb_documents(COMPANY_B))


# ── Provenance: Global vs. Client, regulatory_source vs. yuktav_interpretation ──

def test_global_result_marked_global(db_path):
    _seed_global_document("active", "regulatory_source", "SCOPE-CHECK-GLOBAL")
    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )
    global_chunks = [c for c in result.chunks if "SCOPE-CHECK-GLOBAL" in c.text]
    assert global_chunks and all(c.scope == "Global" for c in global_chunks)
    assert any(s["scope"] == "Global" for s in result.sources)


def test_client_result_marked_client(db_path):
    _seed_client_document(COMPANY_A, "SCOPE-CHECK-CLIENT")
    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )
    client_chunks = [c for c in result.chunks if "SCOPE-CHECK-CLIENT" in c.text]
    assert client_chunks and all(c.scope == "Client" for c in client_chunks)
    assert any(s["scope"] == "Client" for s in result.sources)


def test_regulatory_source_and_yuktav_interpretation_distinguishable(db_path):
    _seed_global_document("active", "regulatory_source", "PRIMARY-SOURCE-MARKER")
    _seed_global_document("active", "yuktav_interpretation", "INTERPRETATION-MARKER")

    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=20,
    )

    categories = {s["content_category"] for s in result.sources if s["scope"] == "Global"}
    assert categories == {"regulatory_source", "yuktav_interpretation"}

    source_chunk = next(c for c in result.chunks if "PRIMARY-SOURCE-MARKER" in c.text)
    interp_chunk = next(c for c in result.chunks if "INTERPRETATION-MARKER" in c.text)
    assert source_chunk.content_category == "regulatory_source"
    assert interp_chunk.content_category == "yuktav_interpretation"

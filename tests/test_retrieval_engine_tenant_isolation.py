"""
tests/test_retrieval_engine_tenant_isolation.py — Wave 1 regression coverage
for TEN-01 (PharmaGPT Production Readiness Audit): services/retrieval_engine.py
previously loaded every company's Knowledge Base with no company_id filter,
so an AI-generated document for Company A could be seeded with, and cite,
Company B's confidential SOPs/protocols. retrieve_context()/_load_kb_all()
now require an explicit company_id and scope every KB row by it.

These tests seed two companies' KB documents directly (bypassing the upload
pipeline, which isn't the concern here) and assert the retrieval boundary
itself, not any frontend/UI filtering.
"""

import pharmagpt.database as db
from pharmagpt.services import retrieval_engine

COMPANY_A = "company-a-11111111-1111-1111-1111-111111111111"
COMPANY_B = "company-b-22222222-2222-2222-2222-222222222222"

# Shared vocabulary in both documents so a query matches both *if* company
# scoping were broken — a query that only matched one company's wording
# wouldn't prove the filter is doing anything.
_SHARED_QUERY = "autoclave sterilization cycle validation SOP"


def _seed_kb_document(company_id: str, title: str, secret_marker: str) -> dict:
    row = db.create_kb_document(
        title=title, folder="SOP", tags="", doc_version="1.0",
        effective_date=None, review_date=None,
        original_name=f"{title}.pdf", stored_filename=f"{title}.pdf",
        file_type="pdf", file_size=1024, company_id=company_id,
    )
    conn = db.get_connection()
    conn.execute(
        "UPDATE kb_documents SET text_content = ?, extraction_status = 'ok' WHERE id = ?",
        (f"{_SHARED_QUERY} procedure. {secret_marker} " * 20, row["id"]),
    )
    conn.commit()
    conn.close()
    return row


def test_load_kb_all_scopes_by_company(db_path):
    _seed_kb_document(COMPANY_A, "Company A SOP", "COMPANY-A-ONLY-MARKER")
    _seed_kb_document(COMPANY_B, "Company B SOP", "COMPANY-B-ONLY-MARKER")

    rows_a = retrieval_engine._load_kb_all(COMPANY_A)
    rows_b = retrieval_engine._load_kb_all(COMPANY_B)

    assert len(rows_a) == 1 and rows_a[0]["title"] == "Company A SOP"
    assert len(rows_b) == 1 and rows_b[0]["title"] == "Company B SOP"


def test_retrieve_context_excludes_other_company_kb_content(db_path):
    """The core TEN-01 regression: Company A's generation request must never
    see Company B's KB content, even though the query matches both."""
    _seed_kb_document(COMPANY_A, "Company A Autoclave SOP", "COMPANY-A-SECRET-9f31")
    _seed_kb_document(COMPANY_B, "Company B Autoclave SOP", "COMPANY-B-SECRET-2e77")

    result = retrieval_engine.retrieve_context(
        document_type="SOP",
        project_id=0,
        company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY},
        max_chunks=10,
    )

    assert result.found is True
    assert "COMPANY-B-SECRET-2e77" not in result.context_text
    assert "Company B Autoclave SOP" not in [s["name"] for s in result.sources]


def test_retrieve_context_includes_own_company_kb_content(db_path):
    """Positive control for the test above — proves the filter scopes to the
    caller's own company rather than accidentally excluding everyone."""
    _seed_kb_document(COMPANY_A, "Company A Autoclave SOP", "COMPANY-A-SECRET-9f31")
    _seed_kb_document(COMPANY_B, "Company B Autoclave SOP", "COMPANY-B-SECRET-2e77")

    result = retrieval_engine.retrieve_context(
        document_type="SOP",
        project_id=0,
        company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY},
        max_chunks=10,
    )

    assert "COMPANY-A-SECRET-9f31" in result.context_text
    assert "Company A Autoclave SOP" in [s["name"] for s in result.sources]


def test_retrieve_context_requires_company_id(db_path):
    """company_id has no default — a caller cannot accidentally omit it and
    fall back to an unscoped (all-companies) retrieval."""
    try:
        retrieval_engine.retrieve_context(document_type="SOP", project_id=0)
        assert False, "retrieve_context() should require company_id"
    except TypeError:
        pass


# ── Yuktav Brain: global (platform-wide) regulatory knowledge ────────────────
# company_id='' is the platform-wide sentinel already established by
# qms_document_database.list_templates() for shared templates. The same
# convention applies here so common Yuktav regulatory knowledge (uploaded
# once) is visible to every tenant, while each tenant's own SOPs/protocols
# remain private to them.

def test_global_kb_document_visible_to_every_company(db_path):
    _seed_kb_document("", "ICH Q7 — GMP for APIs", "GLOBAL-REGULATORY-MARKER")
    _seed_kb_document(COMPANY_A, "Company A Autoclave SOP", "COMPANY-A-SECRET-9f31")

    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )

    names = [s["name"] for s in result.sources]
    assert "ICH Q7 — GMP for APIs" in names
    assert "Company A Autoclave SOP" in names


def test_global_kb_document_does_not_leak_company_content(db_path):
    """Combined reasoning: Company A sees global + its own content, never
    Company B's, even when a global document also exists."""
    _seed_kb_document("", "ICH Q7 — GMP for APIs", "GLOBAL-REGULATORY-MARKER")
    _seed_kb_document(COMPANY_A, "Company A Autoclave SOP", "COMPANY-A-SECRET-9f31")
    _seed_kb_document(COMPANY_B, "Company B Autoclave SOP", "COMPANY-B-SECRET-2e77")

    result = retrieval_engine.retrieve_context(
        document_type="SOP", project_id=0, company_id=COMPANY_A,
        questionnaire={"note": _SHARED_QUERY}, max_chunks=10,
    )

    assert "COMPANY-B-SECRET-2e77" not in result.context_text
    assert "Company B Autoclave SOP" not in [s["name"] for s in result.sources]
    assert "GLOBAL-REGULATORY-MARKER" in result.context_text
    assert "COMPANY-A-SECRET-9f31" in result.context_text

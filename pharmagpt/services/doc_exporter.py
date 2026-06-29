"""
services/doc_exporter.py — Thin adapter: wizard form_data → DocxGenerator.

All formatting logic lives in docx_generator.py (PharmaTheme, DocxGenerator).
This module exists only to bridge the old markdown_to_docx() call signature
used by routes/validation.py with the new structured DocumentData model.

DOCX pipeline (v0.9.5+)
  markdown_to_docx(content, doc_type, form_data)
    → run_review(content, doc_type, form_data)          [new: QA review]
    → build_document_data(form_data, doc_type, title, content)
    → generate_docx(document_data, review_result=result) [new: appends report]
    → bytes

PDF integration point
  Replace the client-side window.print() PDF with a server-side path by
  calling generate_docx() to obtain a DocumentData, then passing the same
  object to a future pdf_generator.generate_pdf().
"""

import logging

from pharmagpt.review.review_engine import run_review
from pharmagpt.services.docx_generator import build_document_data, generate_docx

logger = logging.getLogger(__name__)


def markdown_to_docx(content: str, doc_type: str, form_data: dict) -> bytes:
    """
    Convert markdown content (from Gemini) to a professional DOCX file.

    The Validation Review Engine runs automatically before DOCX assembly and its
    full report is appended as the final section of the exported document.

    Parameters
    ----------
    content   : generated markdown text
    doc_type  : "OQ" | "IQ" | "PQ" | "URS" | "DQ" | "FAT" | "SAT" |
                "FMEA" | "CAPA" | "Deviation" | "Change Control"
    form_data : wizard form data dict (equipment fields + optional metadata)

    Returns
    -------
    bytes — raw DOCX, ready to serve as application/vnd.openxmlformats-…
    """
    title = form_data.get("title") or f"{doc_type} Protocol"

    # ── Run QA Review ─────────────────────────────────────────────────────────
    review_result = None
    try:
        review_result = run_review(content, doc_type, form_data)
        logger.info(
            "Review complete: %s score=%.1f readiness=%s issues=%d",
            doc_type,
            review_result.overall_score,
            review_result.readiness.value,
            len(review_result.issues),
        )
    except Exception:
        logger.exception("Review engine failed for %s; proceeding without review report.", doc_type)

    # ── Build DOCX ────────────────────────────────────────────────────────────
    data = build_document_data(
        form_data  = form_data,
        doc_type   = doc_type,
        title      = title,
        content    = content,
        project_id = int(form_data.get("project_id") or 0),
    )
    return generate_docx(data, review_result=review_result)

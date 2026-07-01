"""
services/document_processor.py — The single entry point for every uploaded
document in PharmaGPT (project documents, Knowledge Base, and — by the same
path — future URS/qualification/validation-report attachments).

Nothing else in the codebase should import pdfplumber, pypdf, fitz, or the
services/extraction/ package directly. routes/docs.py and
routes/knowledge_base.py only ever call the two functions exposed here:

    extract_sync(file_path, extension, progress_cb=None) -> ExtractionResult
        Pure, synchronous extraction core — engine selection, page-by-page
        fallback, timeout, and memory management all live in
        services/extraction/pipeline.py. This function never raises. Used
        directly by tests and internally by process_document_async().

    process_document_async(kind, entity_id, file_path, extension, project_id=None)
        Submits a background job (via services/job_runner.py) that runs
        extract_sync() and persists progress + the final result to SQLite.
        Returns immediately — this is what makes uploads fast (requirement
        #9: the user never waits 30-60s for extraction).

Both project documents and Knowledge Base documents go through the exact
same pipeline; `kind` only changes which database.py table gets updated.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Literal

from pharmagpt import database as db
from pharmagpt.config import PROGRESS_WRITE_EVERY_N_PAGES
from pharmagpt.services.extraction.pipeline import extract_document
from pharmagpt.services.extraction.registry import get_engines
from pharmagpt.services.extraction.stats import ExtractionResult
from pharmagpt.services.job_runner import job_runner

logger = logging.getLogger(__name__)

Kind = Literal["project", "kb"]


def extract_sync(
    file_path: str,
    extension: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> ExtractionResult:
    """
    Extract text from a document file, choosing the best available engine
    chain for its extension and falling back automatically on failure.

    Parameters
    ----------
    file_path   : absolute path to the file on disk
    extension   : lowercase extension without the leading dot —
                  "pdf" | "docx" | "xlsx" | "txt"
    progress_cb : optional callback(current_page, total_pages) invoked after
                  every page/unit is processed

    Returns
    -------
    ExtractionResult — always. Corrupted, encrypted, empty, and scanned-image
    files all return a completed result with an appropriate `status` rather
    than raising.

    Raises
    ------
    ValueError if the extension has no registered engine (unsupported file
    type) — this is a caller-configuration error, checked before any I/O.
    """
    document_name = os.path.basename(file_path)
    engines = get_engines(extension)  # raises ValueError for unsupported extensions
    return extract_document(file_path, document_name, engines, progress_cb=progress_cb)


def process_document_async(
    kind: Kind,
    entity_id: int,
    file_path: str,
    extension: str,
    *,
    project_id: int | None = None,
) -> None:
    """
    Submit background extraction for a just-uploaded (or retried) document
    and return immediately.

    The caller is responsible for having already created a 'pending'
    document_text / kb_documents row (see db.create_pending_document_text /
    db.mark_kb_pending) before calling this, so status polling never 404s in
    the gap between the upload response and the job actually starting.
    """
    job_runner.submit(_run_extraction_job, kind, entity_id, file_path, extension, project_id)


def _run_extraction_job(
    kind: Kind,
    entity_id: int,
    file_path: str,
    extension: str,
    project_id: int | None,
) -> None:
    """The actual background job body. Runs on services/job_runner.py's
    thread pool. Never lets an exception escape silently — a crash here is
    still recorded as a 'failed' document rather than leaving it stuck on
    'processing' forever."""
    document_name = os.path.basename(file_path)
    logger.info("Document uploaded — starting extraction job: %s #%s (%s)", kind, entity_id, document_name)

    def progress_cb(current: int, total: int) -> None:
        # Throttle DB writes on very large documents: every Nth page, and
        # always on the last page, so the progress UI never appears stalled
        # right at 99%.
        if current != total and current % PROGRESS_WRITE_EVERY_N_PAGES != 0:
            return
        _write_progress(kind, entity_id, current, total)

    try:
        result = extract_sync(file_path, extension, progress_cb=progress_cb)
    except Exception as exc:
        # extract_sync()/extract_document() are designed to never raise, but
        # a background job must never vanish silently if something truly
        # unexpected happens (e.g. a bug, an OOM, a disk error).
        logger.exception("Extraction job crashed unexpectedly: %s #%s (%s)", kind, entity_id, document_name)
        result = ExtractionResult(
            document_name=document_name,
            status="failed",
            page_errors=[{"error": f"internal error: {exc}"}],
        )

    _finalize(kind, entity_id, project_id, result)
    logger.info(
        "Extraction complete: %s #%s status=%s engine=%s quality=%.1f%% (%.2fs)",
        kind, entity_id, result.status, result.engine_used, result.quality_score,
        result.extraction_time_seconds,
    )


def _write_progress(kind: Kind, entity_id: int, current: int, total: int) -> None:
    try:
        if kind == "project":
            db.update_document_text_progress(entity_id, current, total)
        else:
            db.update_kb_progress(entity_id, current, total)
    except Exception:
        logger.exception("Failed to persist extraction progress for %s #%s", kind, entity_id)


def _finalize(kind: Kind, entity_id: int, project_id: int | None, result: ExtractionResult) -> None:
    error_message = "; ".join(str(e) for e in result.page_errors[:5])
    try:
        if kind == "project":
            db.save_document_text(
                entity_id, project_id, result.text, result.page_count, result.word_count,
                extraction_status=result.status,
                pages_failed=result.pages_failed,
                engine_used=result.engine_used,
                quality_score=result.quality_score,
                extraction_seconds=result.extraction_time_seconds,
                error_message=error_message,
            )
        else:
            db.update_kb_document_text(
                entity_id, result.text, result.word_count, result.page_count, result.status,
                pages_failed=result.pages_failed,
                engine_used=result.engine_used,
                quality_score=result.quality_score,
                extraction_seconds=result.extraction_time_seconds,
                error_message=error_message,
            )
    except Exception:
        logger.exception("Failed to persist final extraction result for %s #%s", kind, entity_id)

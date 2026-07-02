"""
services/extraction/pipeline.py — Page-by-page extraction loop.

This is where requirements #3-#6 (automatic fallback, page-by-page
extraction, memory management, timeout protection) actually live. Everything
else in the extraction/ package is just engine adapters; this module is the
orchestrator that:

  1. Opens the primary (highest-priority) engine that can open the file.
  2. Iterates pages one at a time — never loads the whole document into a
     single in-memory structure.
  3. Wraps every single-page call in a hard wall-clock timeout. A page that
     times out or raises is retried on the next engine in priority order
     (opening that engine's handle lazily, once, and reusing it for the rest
     of the document rather than reopening per page).
  4. If every engine fails a page, the page is logged and skipped — the
     document as a whole is never aborted.
  5. Periodically drops per-page caches and runs gc.collect() to bound peak
     memory on very large (1000+ page) documents.

Known limitation (documented, not a bug): CPython cannot forcibly terminate
a running thread. A page that hangs past its timeout is *abandoned* — the
pipeline stops waiting for it and moves on — rather than killed. The
abandoned call keeps running in its own daemon thread until it naturally
returns or errors, then its result is discarded. Each timed attempt gets a
fresh thread (not a shared pool) specifically so a hung primary-engine call
can never block the fallback engine's attempt on that same page. This bounds
worst-case wall-clock time per document without risking corrupting engine
state via a hard kill. A future version could move page extraction into a
subprocess pool for true termination if a specific PDF library is found to
hang indefinitely in practice.
"""

from __future__ import annotations

import gc
import logging
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Callable

from pharmagpt.config import GC_INTERVAL_PAGES, PAGE_TIMEOUT_SECONDS
from pharmagpt.services.extraction.base import EngineOpenError, ExtractionEngine
from pharmagpt.services.extraction.stats import ExtractionResult, quality_score

logger = logging.getLogger(__name__)


def _run_with_timeout(fn: Callable, *args, timeout: float):
    """
    Run fn(*args) with a hard wall-clock timeout, using a fresh daemon thread
    per call rather than a shared thread pool.

    A shared single-worker pool would let one hung call occupy the only
    worker, starving every subsequent attempt (including the fallback
    engine's attempt on the very same page) — so each attempt gets its own
    thread. If the call doesn't finish in time, this function raises
    FutureTimeoutError and returns without waiting further; the thread itself
    is abandoned (see module docstring for the tradeoff this implies).
    """
    box: dict = {}

    def _target():
        try:
            box["value"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread below
            box["error"] = exc

    thread = threading.Thread(target=_target, daemon=True, name="page-extract")
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise FutureTimeoutError(f"page extraction exceeded {timeout}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _extract_page_with_fallback(
    file_path: str,
    index: int,
    engines: list[ExtractionEngine],
    primary: ExtractionEngine,
    handles: dict[str, object],
    timeout: float,
    document_name: str,
) -> tuple[str | None, str | None]:
    """
    Try to extract one page, starting with the primary engine and falling
    back through the remaining engines in priority order.

    Returns (text, engine_name). engine_name is None only when every engine
    failed or timed out on this page — the page is then considered failed
    and skipped by the caller. `text` may legitimately be None/"" on success
    (e.g. an image-only page with no text layer) — that still counts as a
    successful extraction attempt, just with no content.
    """
    ordered = [primary] + [e for e in engines if e is not primary]

    for engine in ordered:
        handle = handles.get(engine.name)
        if handle is None:
            try:
                handle = engine.open(file_path)
                handles[engine.name] = handle
            except EngineOpenError as exc:
                logger.warning(
                    "Fallback engine %s could not open %s for page %d: %s",
                    engine.name, document_name, index + 1, exc,
                )
                continue

        try:
            text = _run_with_timeout(engine.extract_page, handle, index, timeout=timeout)
            return text, engine.name
        except FutureTimeoutError:
            logger.warning(
                "Page %d timed out on engine %s (%s) after %ss — falling back",
                index + 1, engine.name, document_name, timeout,
            )
        except Exception as exc:
            logger.warning(
                "Page %d failed on engine %s (%s): %s — falling back",
                index + 1, engine.name, document_name, exc,
            )

    logger.warning("Page %d failed on all engines for %s — skipping", index + 1, document_name)
    return None, None


def extract_document(
    file_path: str,
    document_name: str,
    engines: list[ExtractionEngine],
    *,
    page_timeout_seconds: float = PAGE_TIMEOUT_SECONDS,
    gc_interval_pages: int = GC_INTERVAL_PAGES,
    progress_cb: Callable[[int, int], None] | None = None,
) -> ExtractionResult:
    """
    Extract every page of a document, never raising — corrupted, encrypted,
    empty, and scanned-image files all return a completed ExtractionResult
    with an appropriate `status`, rather than propagating an exception.
    """
    start = time.monotonic()
    result = ExtractionResult(document_name=document_name)

    # ── Open: try engines in priority order until one succeeds ─────────────
    handles: dict[str, object] = {}
    primary: ExtractionEngine | None = None
    open_errors: list[str] = []
    for engine in engines:
        try:
            handles[engine.name] = engine.open(file_path)
            primary = engine
            logger.info("Engine selected: %s (%s)", engine.name, document_name)
            break
        except EngineOpenError as exc:
            logger.warning("Engine %s could not open %s: %s", engine.name, document_name, exc)
            open_errors.append(f"{engine.name}: {exc}")

    if primary is None:
        logger.error("All engines failed to open %s — extraction failed", document_name)
        result.status = "failed"
        # Without this, a corrupted/unsupported file finalizes with status
        # "failed" but an empty error_message — the Retry button shows with
        # no explanation of what actually went wrong.
        result.page_errors.append({
            "page": None,
            "error": "Could not open document with any engine — " + "; ".join(open_errors),
        })
        result.extraction_time_seconds = round(time.monotonic() - start, 3)
        return result

    loop_page_count = primary.page_count(handles[primary.name])
    result.page_count = primary.display_page_count(handles[primary.name])

    texts: list[str] = []
    engine_usage: dict[str, int] = {}

    try:
        for i in range(loop_page_count):
            page_text, used_engine = _extract_page_with_fallback(
                file_path, i, engines, primary, handles, page_timeout_seconds, document_name,
            )

            if used_engine is None:
                result.pages_failed += 1
                result.page_errors.append({"page": i + 1, "error": "all engines failed or timed out"})
            else:
                result.pages_extracted += 1
                engine_usage[used_engine] = engine_usage.get(used_engine, 0) + 1
                if page_text and page_text.strip():
                    texts.append(page_text.strip())

            if progress_cb is not None:
                try:
                    progress_cb(i + 1, loop_page_count)
                except Exception:
                    logger.exception("progress_cb raised while processing %s", document_name)

            # Memory management: release the page-level cache/reference and
            # periodically force a full collection so a 1000-page document
            # never holds more than gc_interval_pages worth of page objects.
            page_text = None
            if (i + 1) % gc_interval_pages == 0:
                gc.collect()
    finally:
        for engine in engines:
            handle = handles.get(engine.name)
            if handle is not None:
                engine.close(handle)
        handles.clear()
        gc.collect()

    full_text = "\n\n".join(texts)
    result.text = full_text
    result.word_count = len(full_text.split())
    result.engine_used = max(engine_usage, key=engine_usage.get) if engine_usage else primary.name
    # Quality score reflects real per-page extraction success (loop units),
    # independent of result.page_count, which for whole-file formats
    # (DOCX/XLSX/TXT) is a display estimate rather than a real page count.
    result.quality_score = quality_score(result.pages_extracted, loop_page_count)

    if loop_page_count == 0 or result.pages_extracted == 0:
        result.status = "failed"
    elif result.pages_failed > 0:
        result.status = "partial"
    elif not full_text.strip():
        result.status = "empty"
    else:
        result.status = "ok"

    result.extraction_time_seconds = round(time.monotonic() - start, 3)
    logger.info(
        "Extraction complete: %s (engine=%s, status=%s, quality=%.1f%%, %.2fs)",
        document_name, result.engine_used, result.status, result.quality_score,
        result.extraction_time_seconds,
    )
    return result

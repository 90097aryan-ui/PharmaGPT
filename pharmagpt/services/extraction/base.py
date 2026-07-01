"""
services/extraction/base.py — The ExtractionEngine interface (Strategy pattern).

Every extraction backend (pypdf, pdfplumber, PyMuPDF, a future OCR engine, or a
future cloud service like Azure Document Intelligence / AWS Textract / Google
Document AI) implements this interface. The pipeline (pipeline.py) only ever
talks to engines through these four methods, so a new backend can be added
without touching any other part of the system.
"""

from abc import ABC, abstractmethod
from typing import Any


class EngineOpenError(Exception):
    """Raised when an engine cannot open a file at all (corrupted, encrypted,
    unsupported format, etc.). This is a whole-document failure — the pipeline
    treats it as "try the next engine's open()", not a per-page failure."""


class PageExtractionError(Exception):
    """Raised by an engine when a single page cannot be read. The pipeline
    catches this and falls back to the next engine for that page only."""


class ExtractionEngine(ABC):
    """
    A single extraction backend for one document handle.

    Lifecycle, driven entirely by pipeline.py:
        handle = engine.open(file_path)      # once per document
        n      = engine.page_count(handle)
        for i in range(n):
            text = engine.extract_page(handle, i)
        engine.close(handle)                 # once per document
    """

    #: Short, stable identifier used in logs, DB stats, and tests.
    name: str = "base"

    @abstractmethod
    def open(self, file_path: str) -> Any:
        """
        Open the document and return an engine-specific handle.

        Raises
        ------
        EngineOpenError if the file cannot be opened by this engine at all
        (corrupted, encrypted with a password we don't have, wrong format).
        """
        raise NotImplementedError

    @abstractmethod
    def page_count(self, handle: Any) -> int:
        """
        Return the number of units the pipeline should loop over when calling
        extract_page(). For PDFs this is the real page count. For whole-file
        formats (DOCX/XLSX/TXT) that have no true per-page structure, this is
        always 1 — the entire document is extracted in a single call.
        """
        raise NotImplementedError

    def display_page_count(self, handle: Any) -> int:
        """
        Return the page count to show to users / store in stats. Defaults to
        page_count(). Whole-file engines override this to report a word- or
        sheet-based estimate (matching pre-existing behavior) while keeping
        page_count() at 1 so the extraction loop runs exactly once.
        """
        return self.page_count(handle)

    @abstractmethod
    def extract_page(self, handle: Any, index: int) -> str | None:
        """
        Extract plain text from a single page (0-based index).

        Returns
        -------
        str | None — the page's text, or None/"" if the page has no text
        (e.g. a scanned image page with no text layer). Returning None is not
        an error — it just means this page contributed no text.

        Raises
        ------
        PageExtractionError (or lets the underlying library's exception
        propagate — the pipeline treats any exception here identically:
        log it, try the next engine, never crash the document).
        """
        raise NotImplementedError

    @abstractmethod
    def close(self, handle: Any) -> None:
        """Release any resources held by the handle. Must never raise."""
        raise NotImplementedError

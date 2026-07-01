"""
services/extraction/pdf_engines.py — PDF extraction engine adapters.

Priority order (see registry.py): PyPDFEngine -> PdfplumberEngine ->
PyMuPDFEngine -> OCRPlaceholderEngine.

  PyPDFEngine       fastest, pure-Python, good default for clean text PDFs.
  PdfplumberEngine  best table/layout fidelity (the previous sole engine) —
                    kept as the fallback for documents PyPDF struggles with.
  PyMuPDFEngine     fastest C-based engine, most resilient to malformed PDFs;
                    last resort before giving up on a page.
  OCRPlaceholderEngine  documents the future hook for scanned/image-only PDFs.
                    Always raises PageExtractionError today — no OCR library
                    is bundled yet (see SYSTEM_ARCHITECTURE_DOCUMENT_PROCESSING.md
                    roadmap for pytesseract / cloud OCR integration).

Each engine opens the file itself and exposes page-index random access so the
pipeline can retry a single failing page on a different engine without
re-opening (and re-reading) the whole document.
"""

from __future__ import annotations

from typing import Any

from pharmagpt.services.extraction.base import (
    EngineOpenError,
    ExtractionEngine,
    PageExtractionError,
)


class PyPDFEngine(ExtractionEngine):
    name = "pypdf"

    def open(self, file_path: str) -> Any:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(file_path)
        except (PdfReadError, OSError, ValueError) as exc:
            raise EngineOpenError(f"pypdf could not open file: {exc}") from exc

        if reader.is_encrypted:
            try:
                # Most vendor manuals use empty owner passwords with a
                # restricted-permissions user password; try the empty
                # password before giving up.
                if reader.decrypt("") == 0:
                    raise EngineOpenError("PDF is password protected")
            except Exception as exc:
                raise EngineOpenError(f"PDF is password protected: {exc}") from exc

        try:
            _ = len(reader.pages)  # forces parsing the page tree now, not lazily mid-loop
        except Exception as exc:
            raise EngineOpenError(f"pypdf could not read page tree: {exc}") from exc

        return reader

    def page_count(self, handle: Any) -> int:
        return len(handle.pages)

    def extract_page(self, handle: Any, index: int) -> str | None:
        try:
            return handle.pages[index].extract_text()
        except Exception as exc:
            raise PageExtractionError(str(exc)) from exc

    def close(self, handle: Any) -> None:
        try:
            handle.close()
        except Exception:
            pass


class PdfplumberEngine(ExtractionEngine):
    name = "pdfplumber"

    def open(self, file_path: str) -> Any:
        import pdfplumber

        try:
            pdf = pdfplumber.open(file_path)
        except Exception as exc:
            raise EngineOpenError(f"pdfplumber could not open file: {exc}") from exc

        if getattr(pdf, "is_encrypted", False):
            pdf.close()
            raise EngineOpenError("PDF is password protected")

        return pdf

    def page_count(self, handle: Any) -> int:
        return len(handle.pages)

    def extract_page(self, handle: Any, index: int) -> str | None:
        try:
            page = handle.pages[index]
            text = page.extract_text()
            # Release pdfplumber's internal char/word/line cache for this
            # page immediately — otherwise it accumulates for every page
            # ever accessed via handle.pages, which is how pdfplumber leaks
            # memory on large documents.
            page.flush_cache()
            return text
        except Exception as exc:
            raise PageExtractionError(str(exc)) from exc

    def close(self, handle: Any) -> None:
        try:
            handle.close()
        except Exception:
            pass


class PyMuPDFEngine(ExtractionEngine):
    name = "pymupdf"

    def open(self, file_path: str) -> Any:
        import fitz  # PyMuPDF

        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise EngineOpenError(f"PyMuPDF could not open file: {exc}") from exc

        if doc.is_encrypted:
            # Try an empty password; fitz mutates doc in place on success.
            if not doc.authenticate(""):
                doc.close()
                raise EngineOpenError("PDF is password protected")

        return doc

    def page_count(self, handle: Any) -> int:
        return handle.page_count

    def extract_page(self, handle: Any, index: int) -> str | None:
        try:
            page = handle.load_page(index)
            text = page.get_text()
            page = None
            return text
        except Exception as exc:
            raise PageExtractionError(str(exc)) from exc

    def close(self, handle: Any) -> None:
        try:
            handle.close()
        except Exception:
            pass


class OCRPlaceholderEngine(ExtractionEngine):
    """
    Placeholder for a real OCR backend (pytesseract, Azure Document
    Intelligence, AWS Textract, Google Document AI). Always registered last
    for PDFs so scanned/image-only pages that no text-layer engine could read
    are clearly attributed to "OCR not yet available" in the logs and
    page_errors, rather than silently vanishing.
    """

    name = "ocr_placeholder"

    def open(self, file_path: str) -> Any:
        raise EngineOpenError("OCR engine is not implemented yet")

    def page_count(self, handle: Any) -> int:
        return 0

    def extract_page(self, handle: Any, index: int) -> str | None:
        raise PageExtractionError("OCR not yet implemented")

    def close(self, handle: Any) -> None:
        pass

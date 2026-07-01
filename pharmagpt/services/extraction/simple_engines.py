"""
services/extraction/simple_engines.py — Adapters for whole-file formats.

DOCX, XLSX, and TXT are not part of the timeout/memory crisis this redesign
addresses (they're small, in-memory, whole-document reads), so their existing
readers (services/docx_reader.py, services/excel_reader.py) are reused as-is
rather than rewritten — each is simply wrapped behind the same
ExtractionEngine interface as the PDF engines so document_processor.py has a
single, uniform pipeline for every file type. Each of these is a single
"page" as far as the pipeline's page-loop is concerned.
"""

from __future__ import annotations

from typing import Any

from pharmagpt.services import docx_reader, excel_reader
from pharmagpt.services.extraction.base import EngineOpenError, ExtractionEngine


class DocxEngine(ExtractionEngine):
    name = "python-docx"

    def open(self, file_path: str) -> Any:
        try:
            text, page_count = docx_reader.extract(file_path)
        except Exception as exc:
            raise EngineOpenError(f"python-docx could not open file: {exc}") from exc
        return {"text": text, "page_count": page_count}

    def page_count(self, handle: Any) -> int:
        # DOCX has no real per-page structure — extracted as a single unit.
        return 1

    def display_page_count(self, handle: Any) -> int:
        return handle["page_count"]

    def extract_page(self, handle: Any, index: int) -> str | None:
        return handle["text"]

    def close(self, handle: Any) -> None:
        pass


class ExcelEngine(ExtractionEngine):
    name = "openpyxl"

    def open(self, file_path: str) -> Any:
        try:
            text, sheet_count = excel_reader.extract(file_path)
        except Exception as exc:
            raise EngineOpenError(f"openpyxl could not open file: {exc}") from exc
        return {"text": text, "sheet_count": sheet_count}

    def page_count(self, handle: Any) -> int:
        return 1

    def display_page_count(self, handle: Any) -> int:
        return max(1, handle["sheet_count"])

    def extract_page(self, handle: Any, index: int) -> str | None:
        return handle["text"]

    def close(self, handle: Any) -> None:
        pass


# Rough words-per-page estimate for TXT files, which have no inherent concept
# of a printed page. Matches the previous services/extractor.py behavior.
WORDS_PER_PAGE_ESTIMATE = 300


class TxtEngine(ExtractionEngine):
    name = "text"

    def open(self, file_path: str) -> Any:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception as exc:
            raise EngineOpenError(f"could not read text file: {exc}") from exc
        page_count = max(1, len(text.split()) // WORDS_PER_PAGE_ESTIMATE)
        return {"text": text, "page_count": page_count}

    def page_count(self, handle: Any) -> int:
        return 1

    def display_page_count(self, handle: Any) -> int:
        return handle["page_count"]

    def extract_page(self, handle: Any, index: int) -> str | None:
        return handle["text"]

    def close(self, handle: Any) -> None:
        pass

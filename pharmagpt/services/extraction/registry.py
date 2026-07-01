"""
services/extraction/registry.py — Maps a file extension to an ordered list of
engines to try.

Order encodes both "which engine is fastest/best for this format" and the
fallback chain used by pipeline.py. To add a new backend (OCR, Azure Document
Intelligence, AWS Textract, Google Document AI), import it here and append it
to the relevant list — no other code changes are required.
"""

from __future__ import annotations

from pharmagpt.services.extraction.base import ExtractionEngine
from pharmagpt.services.extraction.pdf_engines import (
    OCRPlaceholderEngine,
    PdfplumberEngine,
    PyMuPDFEngine,
    PyPDFEngine,
)
from pharmagpt.services.extraction.simple_engines import (
    DocxEngine,
    ExcelEngine,
    TxtEngine,
)

# Each engine is stateless and safe to share across documents/threads —
# instantiate once.
ENGINES: dict[str, list[ExtractionEngine]] = {
    "pdf": [
        PyPDFEngine(),
        PdfplumberEngine(),
        PyMuPDFEngine(),
        OCRPlaceholderEngine(),
    ],
    "docx": [DocxEngine()],
    "xlsx": [ExcelEngine()],
    "txt": [TxtEngine()],
}


def get_engines(extension: str) -> list[ExtractionEngine]:
    """Return the ordered engine chain for a file extension.

    Raises ValueError for unsupported extensions (mirrors the previous
    services/extractor.py behavior)."""
    engines = ENGINES.get(extension.lower())
    if not engines:
        raise ValueError(f"No extraction engine registered for extension: {extension!r}")
    return engines

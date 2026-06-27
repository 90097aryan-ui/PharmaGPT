"""
services/extractor.py — Shared text extraction for uploaded documents.

Both project-document uploads and Knowledge Base uploads need identical
extraction logic: dispatch on file extension, call the right reader library,
and estimate page count for formats that don't have real pagination.

Centralising this here eliminates the duplicate _extract_and_store /
_extract_and_store_kb pattern that previously existed in app.py.
"""

import logging
from services import pdf_reader, docx_reader, excel_reader

logger = logging.getLogger(__name__)

# Rough words-per-page estimate used for TXT, DOCX, and XLSX files,
# which have no inherent concept of a printed page.
WORDS_PER_PAGE_ESTIMATE = 300


def extract_text(file_path: str, extension: str) -> tuple[str, int]:
    """
    Extract plain text and estimate page count from a document file.

    Parameters
    ----------
    file_path : absolute path to the file on disk
    extension : lowercase extension without the leading dot —
                "pdf" | "docx" | "xlsx" | "txt"

    Returns
    -------
    (text, page_count)
        text       : extracted plain text (empty string if the file has no
                     text layer, e.g. a scanned-image PDF)
        page_count : actual page count (PDF) or a word-based estimate (others)

    Raises
    ------
    ValueError   if the extension is not in the supported set
    Exception    any error raised by the underlying reader library
                 (caller is responsible for catching and logging)
    """
    if extension == "pdf":
        return pdf_reader.extract(file_path)

    if extension == "docx":
        return docx_reader.extract(file_path)

    if extension == "xlsx":
        return excel_reader.extract(file_path)

    if extension == "txt":
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        page_count = max(1, len(text.split()) // WORDS_PER_PAGE_ESTIMATE)
        return text, page_count

    raise ValueError(f"Unsupported extension for text extraction: {extension!r}")

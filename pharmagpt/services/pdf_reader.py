"""
services/pdf_reader.py — Extract text from PDF files using pdfplumber.

pdfplumber is chosen over PyPDF2 / pypdf because it handles:
  - Complex table layouts (common in GMP protocols and validation reports)
  - Multi-column documents (common in regulatory submissions)
  - Page-level metadata

Limitations (v0.5):
  - Scanned PDFs with no text layer return empty text.
    Future: add OCR via pytesseract / Google Vision.
  - Encrypted PDFs will raise an exception (caught by the caller).
"""

import pdfplumber


def extract(file_path: str) -> tuple[str, int]:
    """
    Extract all text from a PDF and return (text, page_count).

    Each page is prefixed with a [Page N] marker so the search module can
    include page references in the context sent to Gemini.

    Parameters
    ----------
    file_path : str  — absolute path to the .pdf file on disk

    Returns
    -------
    text       : str — full extracted text, pages separated by double newlines
    page_count : int — total number of pages in the PDF
    """
    pages_text = []

    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)

        for i, page in enumerate(pdf.pages, start=1):
            # extract_text() returns None for image-only pages
            raw = page.extract_text()
            if raw and raw.strip():
                pages_text.append(f"[Page {i}]\n{raw.strip()}")

    full_text = "\n\n".join(pages_text)
    return full_text, page_count

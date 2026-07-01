"""
services/extraction/ — Pluggable document extraction engines and the
page-by-page pipeline that drives them.

This package is the only place in the codebase allowed to import pdfplumber,
pypdf, or fitz (PyMuPDF) directly. Everything else goes through
services/document_processor.py.

Modules
-------
base            : ExtractionEngine interface (Strategy pattern) + exceptions
pdf_engines     : PyPDFEngine, PdfplumberEngine, PyMuPDFEngine, OCRPlaceholderEngine
simple_engines  : DocxEngine, ExcelEngine, TxtEngine (wrap existing whole-file readers)
registry        : extension -> ordered list of engines to try
pipeline        : page-by-page extraction loop (fallback, timeout, memory management)
stats           : ExtractionResult dataclass + quality score calculation

Adding a new backend (e.g. Azure Document Intelligence, AWS Textract, Google
Document AI, or a real OCR engine) means writing one new ExtractionEngine
subclass and adding it to registry.ENGINES — nothing else in the system needs
to change.
"""

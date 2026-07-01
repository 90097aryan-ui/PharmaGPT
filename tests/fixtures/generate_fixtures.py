"""
tests/fixtures/generate_fixtures.py — Builds every PDF fixture used by the
extraction engine test suite, using PyMuPDF only (already a production
dependency — no extra test-only library needed).

Each `make_*` function writes one fixture to the given path and returns it.
`build_all(output_dir)` builds the whole standard set and returns a
{name: path} dict — used by tests/conftest.py's session-scoped fixture.
"""

from __future__ import annotations

import os

import fitz  # PyMuPDF


def make_small_pdf(path: str, pages: int = 5) -> str:
    """A few pages of plain text — the common case."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Small PDF - Page {i + 1}\nSample vendor manual content for testing.")
    doc.save(path)
    doc.close()
    return path


def make_large_pdf(path: str, pages: int = 200) -> str:
    """A large multi-page document — used for the <40s / 200-page perf target."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            f"Large Document - Page {i + 1} of {pages}\n"
            "1. Purpose\nThis section describes the operating procedure.\n"
            "2. Scope\nApplies to all validated equipment.\n"
            "3. Acceptance Criteria\nResult must meet specification.",
        )
    doc.save(path)
    doc.close()
    return path


def make_scanned_pdf(path: str, pages: int = 3) -> str:
    """
    Simulates a scanned document: pages contain only vector drawings (no text
    objects), so text-layer engines correctly extract nothing.
    """
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 50, 500, 700))
        shape.finish(color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
        shape.commit()
    doc.save(path)
    doc.close()
    return path


def make_mixed_pdf(path: str, pages: int = 6) -> str:
    """Alternates real text pages with image-only (no text layer) pages."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        if i % 2 == 0:
            page.insert_text((72, 72), f"Mixed PDF - Text page {i + 1}\nThis page has a real text layer.")
        else:
            shape = page.new_shape()
            shape.draw_circle(fitz.Point(300, 400), 100)
            shape.finish(color=(0, 0, 0))
            shape.commit()
    doc.save(path)
    doc.close()
    return path


def make_engineering_manual_pdf(path: str, pages: int = 15) -> str:
    """A denser, heading/table-like structure representative of a PLC/SCADA
    engineering manual."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"SECTION {i + 1}: EQUIPMENT SPECIFICATION", fontsize=14)
        page.insert_text(
            (72, 100),
            "Parameter        | Spec              | Result\n"
            "Temperature      | 20-25 C           | 22.4 C\n"
            "Pressure         | 1.0-1.2 bar       | 1.1 bar\n"
            "Flow Rate        | 10-12 L/min       | 11.2 L/min\n"
            f"Reference Drawing: DWG-{1000 + i}",
            fontsize=10,
        )
    doc.save(path)
    doc.close()
    return path


def make_empty_pdf(path: str) -> str:
    """A single, entirely blank page — valid PDF, zero extractable text."""
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


def make_corrupted_pdf(path: str) -> str:
    """A truncated/garbled file — not a valid PDF at all."""
    with open(path, "wb") as fh:
        fh.write(b"%PDF-1.4\nthis is not a real pdf body, just garbage bytes to force every engine's open() to fail.")
    return path


def make_password_protected_pdf(path: str, user_password: str = "userpass123") -> str:
    """A real PDF encrypted with a non-empty user password — every engine's
    empty-password attempt must fail cleanly."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This content is password protected.")
    doc.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="ownerpass456",
        user_pw=user_password,
    )
    doc.close()
    return path


FIXTURE_BUILDERS = {
    "small.pdf": make_small_pdf,
    "large.pdf": make_large_pdf,
    "scanned.pdf": make_scanned_pdf,
    "mixed.pdf": make_mixed_pdf,
    "engineering_manual.pdf": make_engineering_manual_pdf,
    "empty.pdf": make_empty_pdf,
    "corrupted.pdf": make_corrupted_pdf,
    "password_protected.pdf": make_password_protected_pdf,
}


def build_all(output_dir: str) -> dict[str, str]:
    """Build the full standard fixture set into output_dir. Returns
    {filename: absolute_path}."""
    os.makedirs(output_dir, exist_ok=True)
    paths = {}
    for name, builder in FIXTURE_BUILDERS.items():
        path = os.path.join(output_dir, name)
        builder(path)
        paths[name] = path
    return paths

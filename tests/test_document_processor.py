"""
tests/test_document_processor.py — Integration tests for
services/document_processor.extract_sync() over every fixture format, plus
the performance targets from the architecture plan.
"""

import pytest

from pharmagpt.services.document_processor import extract_sync


def test_small_pdf(fixtures_dir):
    result = extract_sync(fixtures_dir["small.pdf"], "pdf")
    assert result.status == "ok"
    assert result.page_count == 5
    assert result.pages_extracted == 5
    assert result.pages_failed == 0
    assert result.quality_score == 100.0
    assert result.word_count > 0
    assert result.extraction_time_seconds < 2.0


def test_large_pdf_meets_performance_target(fixtures_dir):
    result = extract_sync(fixtures_dir["large.pdf"], "pdf")
    assert result.status == "ok"
    assert result.page_count == 200
    assert result.pages_extracted == 200
    # Architecture target: 200-page PDF < 40 seconds, no worker timeout.
    assert result.extraction_time_seconds < 40.0


def test_scanned_pdf_returns_empty_status_not_error(fixtures_dir):
    result = extract_sync(fixtures_dir["scanned.pdf"], "pdf")
    assert result.status == "empty"
    assert result.pages_extracted == result.page_count
    assert result.pages_failed == 0
    assert result.word_count == 0


def test_mixed_image_text_pdf(fixtures_dir):
    result = extract_sync(fixtures_dir["mixed.pdf"], "pdf")
    assert result.status == "ok"
    assert result.pages_extracted == result.page_count
    assert result.word_count > 0


def test_engineering_manual_pdf(fixtures_dir):
    result = extract_sync(fixtures_dir["engineering_manual.pdf"], "pdf")
    assert result.status == "ok"
    assert result.pages_extracted == 15
    assert "SECTION" in result.text


def test_empty_pdf(fixtures_dir):
    result = extract_sync(fixtures_dir["empty.pdf"], "pdf")
    assert result.status == "empty"
    assert result.pages_failed == 0


def test_corrupted_pdf_never_raises(fixtures_dir):
    result = extract_sync(fixtures_dir["corrupted.pdf"], "pdf")
    assert result.status == "failed"
    assert result.pages_extracted == 0
    assert result.quality_score == 0.0


def test_password_protected_pdf_never_raises(fixtures_dir):
    result = extract_sync(fixtures_dir["password_protected.pdf"], "pdf")
    assert result.status == "failed"
    assert result.pages_extracted == 0


def test_unsupported_extension_raises_value_error(fixtures_dir):
    with pytest.raises(ValueError):
        extract_sync(fixtures_dir["small.pdf"], "exe")


@pytest.mark.slow
def test_thousand_page_document_does_not_time_out(tmp_path):
    """Stress test for the 1000+ page vendor manuals mentioned in the
    background report. Not run by default (`pytest -m slow` to include)."""
    from fixtures.generate_fixtures import make_large_pdf

    path = str(tmp_path / "huge.pdf")
    make_large_pdf(path, pages=1000)

    result = extract_sync(path, "pdf")
    assert result.status == "ok"
    assert result.pages_extracted == 1000
    assert result.pages_failed == 0

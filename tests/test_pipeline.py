"""
tests/test_pipeline.py — Unit tests for the page-by-page pipeline
(services/extraction/pipeline.py): fallback, per-page timeout, skip-and-continue,
memory cleanup, and quality score math. Uses fake in-memory engines so these
tests are fast and don't depend on real PDF libraries.
"""

import time

from pharmagpt.services.extraction.base import (
    EngineOpenError,
    ExtractionEngine,
    PageExtractionError,
)
from pharmagpt.services.extraction.pipeline import extract_document
from pharmagpt.services.extraction.stats import quality_score


class FakeEngine(ExtractionEngine):
    """A configurable in-memory engine for pipeline testing.

    `fail_pages`   : page indices that always raise PageExtractionError
    `hang_pages`   : page indices that sleep past any reasonable timeout
    `open_fails`   : if True, open() always raises EngineOpenError
    """

    def __init__(self, name, num_pages=5, fail_pages=(), hang_pages=(), open_fails=False):
        self.name = name
        self.num_pages = num_pages
        self.fail_pages = set(fail_pages)
        self.hang_pages = set(hang_pages)
        self.open_fails = open_fails
        self.opened = False
        self.closed = False

    def open(self, file_path):
        if self.open_fails:
            raise EngineOpenError(f"{self.name} cannot open")
        self.opened = True
        return {"n": self.num_pages}

    def page_count(self, handle):
        return handle["n"]

    def extract_page(self, handle, index):
        if index in self.hang_pages:
            time.sleep(5)
            return f"{self.name}-page-{index}"
        if index in self.fail_pages:
            raise PageExtractionError(f"{self.name} failed on page {index}")
        return f"{self.name}-page-{index}"

    def close(self, handle):
        self.closed = True


def test_all_pages_succeed_on_primary_engine():
    primary = FakeEngine("primary", num_pages=4)
    result = extract_document("dummy.pdf", "dummy.pdf", [primary])

    assert result.status == "ok"
    assert result.pages_extracted == 4
    assert result.pages_failed == 0
    assert result.engine_used == "primary"
    assert result.quality_score == 100.0
    assert primary.closed is True


def test_page_level_fallback_to_second_engine():
    primary = FakeEngine("primary", num_pages=4, fail_pages=(1, 2))
    fallback = FakeEngine("fallback", num_pages=4)

    result = extract_document("dummy.pdf", "dummy.pdf", [primary, fallback])

    assert result.status == "ok"
    assert result.pages_extracted == 4
    assert result.pages_failed == 0
    # Fallback only opened lazily because pages 1 and 2 needed it.
    assert fallback.opened is True
    assert "fallback-page-1" in result.text
    assert "primary-page-0" in result.text


def test_page_fails_on_every_engine_is_skipped_not_fatal():
    primary = FakeEngine("primary", num_pages=3, fail_pages=(1,))
    fallback = FakeEngine("fallback", num_pages=3, fail_pages=(1,))

    result = extract_document("dummy.pdf", "dummy.pdf", [primary, fallback])

    assert result.status == "partial"
    assert result.pages_extracted == 2
    assert result.pages_failed == 1
    assert result.page_errors == [{"page": 2, "error": "all engines failed or timed out"}]
    assert result.quality_score == quality_score(2, 3)


def test_page_timeout_falls_back_and_never_blocks_document():
    primary = FakeEngine("primary", num_pages=2, hang_pages=(0,))
    fallback = FakeEngine("fallback", num_pages=2)

    start = time.monotonic()
    result = extract_document(
        "dummy.pdf", "dummy.pdf", [primary, fallback], page_timeout_seconds=0.3,
    )
    elapsed = time.monotonic() - start

    assert result.status == "ok"
    assert result.pages_extracted == 2
    # Bounded by the timeout, not by the 5s hang.
    assert elapsed < 3.0


def test_open_failure_falls_back_to_next_engine():
    broken = FakeEngine("broken", open_fails=True)
    working = FakeEngine("working", num_pages=2)

    result = extract_document("dummy.pdf", "dummy.pdf", [broken, working])

    assert result.status == "ok"
    assert result.engine_used == "working"


def test_every_engine_open_fails_returns_failed_status_not_exception():
    broken1 = FakeEngine("broken1", open_fails=True)
    broken2 = FakeEngine("broken2", open_fails=True)

    result = extract_document("dummy.pdf", "dummy.pdf", [broken1, broken2])

    assert result.status == "failed"
    assert result.pages_extracted == 0
    assert result.quality_score == 0.0


def test_progress_callback_invoked_per_page():
    calls = []
    engine = FakeEngine("primary", num_pages=6)
    extract_document(
        "dummy.pdf", "dummy.pdf", [engine], progress_cb=lambda cur, total: calls.append((cur, total)),
    )
    assert calls == [(i, 6) for i in range(1, 7)]


def test_gc_interval_does_not_break_extraction():
    engine = FakeEngine("primary", num_pages=25)
    result = extract_document("dummy.pdf", "dummy.pdf", [engine], gc_interval_pages=5)
    assert result.pages_extracted == 25
    assert result.status == "ok"


def test_quality_score_formula():
    assert quality_score(46, 48) == 95.8
    assert quality_score(0, 0) == 0.0
    assert quality_score(5, 5) == 100.0

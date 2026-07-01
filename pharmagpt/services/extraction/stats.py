"""
services/extraction/stats.py — ExtractionResult: the stats contract every
extraction returns, regardless of engine or file type.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def quality_score(pages_extracted: int, page_count: int) -> float:
    """
    Percentage of pages successfully extracted, rounded to 1 decimal.

    Example: 48 pages, 46 extracted, 2 skipped -> 95.8.
    A page_count of 0 (nothing to extract, or the document couldn't even be
    opened) scores 0.0 rather than raising a ZeroDivisionError.
    """
    if page_count <= 0:
        return 0.0
    return round((pages_extracted / page_count) * 100, 1)


@dataclass
class ExtractionResult:
    document_name: str
    page_count: int = 0
    pages_extracted: int = 0
    pages_failed: int = 0
    word_count: int = 0
    extraction_time_seconds: float = 0.0
    engine_used: str = ""
    quality_score: float = 0.0
    status: str = "failed"          # "ok" | "partial" | "empty" | "failed"
    text: str = ""
    page_errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_name": self.document_name,
            "page_count": self.page_count,
            "pages_extracted": self.pages_extracted,
            "pages_failed": self.pages_failed,
            "word_count": self.word_count,
            "extraction_time_seconds": self.extraction_time_seconds,
            "engine_used": self.engine_used,
            "quality_score": self.quality_score,
            "status": self.status,
            "page_errors": self.page_errors,
        }

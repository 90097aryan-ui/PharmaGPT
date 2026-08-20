"""
services/document_versioning.py — numbering rules and immutable-version
lifecycle helpers for the Document Control redesign (locked spec, see
docs/plan / conversation record — not duplicated here).

Numbering rule (uniform, derived directly from the two worked examples in
the spec):

    New SOP:      0.1 -> 0.2 -> 0.3 -> ... -> 1.0 (Effective)
    Existing X.0: X.1 -> X.2 -> X.3 -> ... -> (X+1).0 (Effective)

Both sequences are the *same* rule applied to different starting points:
every non-Effective step is "minor += 1"; every Effective step is
"major += 1, minor = 0". A brand-new document's first version (0.1) is
just this rule applied once to a virtual "0.0" baseline — so create,
rework/reject, and revision-after-effective all reuse one function with no
special-cased first-version branch.

This module is pure logic (no DB access) — services/qms_document_database.py
and routes/qms_documents.py call it, never the other way around.
"""

from __future__ import annotations

import re

BASELINE_VERSION = "0.0"

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


class InvalidVersionNumberError(Exception):
    """Raised when a version string doesn't match the required X.Y numeric
    format, or an unknown event is passed to next_version_number()."""


def parse_version(version: str) -> tuple[int, int]:
    m = _VERSION_RE.match((version or "").strip())
    if not m:
        raise InvalidVersionNumberError(f"'{version}' is not a valid X.Y version number")
    return int(m.group(1)), int(m.group(2))


def format_version(major: int, minor: int) -> str:
    return f"{major}.{minor}"


def next_version_number(current: str, event: str) -> str:
    """`event` is 'effective' (this version is being made Effective — bumps
    the major number, resets minor to 0) or 'rework' (a fresh Draft is being
    forked off — from initial creation, a Review rejection, an Approval
    rejection, or a new revision cycle started against an already-Effective
    document; all four are numerically identical: minor += 1)."""
    major, minor = parse_version(current)
    if event == "effective":
        return format_version(major + 1, 0)
    if event == "rework":
        return format_version(major, minor + 1)
    raise InvalidVersionNumberError(f"Unknown version event '{event}'")


def first_version_number() -> str:
    """The version number for a brand-new document's very first (Draft)
    version — 0.1, derived via the same 'rework' rule from the 0.0
    baseline rather than a hardcoded special case."""
    return next_version_number(BASELINE_VERSION, "rework")


def next_revision_number(current_effective_version: str) -> str:
    """The version number for the first Draft of a *new revision cycle*
    started against a document that is already Effective at
    `current_effective_version` (e.g. '1.0' -> '1.1'). Numerically
    identical to next_version_number(..., 'rework') — a distinct name is
    kept only because callers reach this from a different lifecycle event
    (starting a revision, not a rejection) and the distinction matters for
    audit-trail wording, not arithmetic."""
    return next_version_number(current_effective_version, "rework")

"""
tests/test_document_versioning.py — numbering-rule coverage for
services/document_versioning.py (Document Control redesign, Phase 0).

Pure-function tests, no DB fixture needed.
"""

import pytest

from pharmagpt.services import document_versioning as dv


def test_first_version_is_0_1():
    assert dv.first_version_number() == "0.1"


def test_new_sop_rework_sequence_then_effective():
    v = dv.first_version_number()
    assert v == "0.1"
    v = dv.next_version_number(v, "rework")
    assert v == "0.2"
    v = dv.next_version_number(v, "rework")
    assert v == "0.3"
    v = dv.next_version_number(v, "effective")
    assert v == "1.0"


def test_existing_sop_revision_rework_sequence_then_effective():
    v = "1.0"
    v = dv.next_revision_number(v)
    assert v == "1.1"
    v = dv.next_version_number(v, "rework")
    assert v == "1.2"
    v = dv.next_version_number(v, "rework")
    assert v == "1.3"
    v = dv.next_version_number(v, "effective")
    assert v == "2.0"


def test_effective_always_resets_minor_to_zero():
    assert dv.next_version_number("3.7", "effective") == "4.0"


def test_no_version_number_ever_reused_across_a_full_cycle():
    seen = set()
    v = dv.first_version_number()
    seen.add(v)
    for _ in range(5):
        v = dv.next_version_number(v, "rework")
        assert v not in seen
        seen.add(v)
    v = dv.next_version_number(v, "effective")
    assert v not in seen
    seen.add(v)
    v = dv.next_revision_number(v)
    assert v not in seen


@pytest.mark.parametrize("bad", ["", "1", "1.x", "x.1", "1.2.3", "1.-2", None])
def test_invalid_version_strings_rejected(bad):
    with pytest.raises(dv.InvalidVersionNumberError):
        dv.parse_version(bad)


def test_unknown_event_rejected():
    with pytest.raises(dv.InvalidVersionNumberError):
        dv.next_version_number("1.0", "bogus")


def test_parse_and_format_roundtrip():
    assert dv.format_version(*dv.parse_version("12.34")) == "12.34"

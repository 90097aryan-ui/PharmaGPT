"""
services/lifecycle_engine.py — shared document/record lifecycle state machine,
generalizing the URS suite's proven urs_lifecycle.py pattern (ALLOWED_TRANSITIONS
+ validate_transition() + InvalidTransitionError) to every other suite that
currently accepts a status change with no transition validation at all
(QMS Document Control, Qualification, Validation Report, Risk Assessment).

Each entry below is derived directly from that suite's own existing
action->status map (qms_documents.py::_STATUS_MAP, qual.py::add_approval's
status_map, report.py::add_approval's status_map, risk.py::add_approval's
status_map) — no status value or reachability is invented here. Before this
module, any of those four routes would apply any mapped action regardless of
the record's current status (e.g. a fresh Draft could be marked "Effective"
directly by POSTing the right action name); this module closes that gap the
same way URS's own lifecycle already does, without changing any status
vocabulary or removing any action a caller currently relies on.

URS is not duplicated here — the registry delegates straight to
urs_lifecycle.ALLOWED_TRANSITIONS so urs_lifecycle.py stays the single source
of truth for URS's own transitions and its existing tests are unaffected.
"""

from __future__ import annotations

from pharmagpt.services import urs_lifecycle

# ── QMS Document Control (SOP, Protocol, Specification, ..., and — Phase 3 —
# DQ/FAT/SAT once consolidated per services/lifecycle_engine.py's DQ/FAT/SAT
# consolidation, see routes/qms_documents.py) ────────────────────────────────
# Status vocabulary and the "Draft/Under Review/Pending Approval/Effective/
# Under Revision/Obsolete" sequence come from qms_database.py's own schema
# comment (qms_documents.status). Under Review -> Effective is reachable
# directly (the "Approved" action always maps straight to Effective, matching
# existing behaviour/tests — Pending Approval is an optional sub-step, not a
# mandatory gate, exactly like URS's own PENDING_APPROVAL). "Rejected" (->
# Draft) is legal from Under Review, Pending Approval, *and* Effective —
# tests/test_kb_sync.py's republish test sends an already-Effective document
# back to Draft via "Rejected" to model a post-approval correction cycle.
_QMS_DOCUMENT_TRANSITIONS: dict[str, set[str]] = {
    "Draft":             {"Under Review"},
    "Under Review":      {"Pending Approval", "Effective", "Draft"},
    "Pending Approval":  {"Effective", "Draft"},
    "Effective":         {"Under Revision", "Obsolete", "Draft"},
    "Under Revision":    {"Under Review", "Draft", "Obsolete"},
    "Obsolete":          set(),
}

# ── Qualification (IQ/OQ/PQ/DQ) — derived from qual.py::add_approval's
# status_map (draft / under_review / pending_approval / approved / closed /
# obsolete). "Rejected" returns Draft from either review stage. ─────────────
_QUALIFICATION_TRANSITIONS: dict[str, set[str]] = {
    "draft":             {"under_review"},
    "under_review":      {"pending_approval", "approved", "draft"},
    "pending_approval":  {"approved", "draft"},
    "approved":          {"closed", "obsolete"},
    "closed":            {"obsolete"},
    "obsolete":          set(),
}

# ── Validation Report — derived from report.py::add_approval's status_map
# (draft / under_review / approved / released / archived / obsolete). ───────
_VALIDATION_REPORT_TRANSITIONS: dict[str, set[str]] = {
    "draft":       {"under_review"},
    "under_review": {"approved", "draft"},
    "approved":    {"released", "draft"},
    "released":    {"archived", "obsolete"},
    "archived":    {"obsolete"},
    "obsolete":    set(),
}

# ── Risk Assessment — derived from risk.py::add_approval's status_map
# (Draft / In Review / Approved / Closed). ──────────────────────────────────
_RISK_ASSESSMENT_TRANSITIONS: dict[str, set[str]] = {
    "Draft":     {"In Review"},
    "In Review": {"Approved", "Draft"},
    "Approved":  {"Closed"},
    "Closed":    set(),
}

# Registry key is a lifecycle identifier, not necessarily a doc_type string —
# callers pass whichever key names their own suite's transition map (kept
# distinct from qms_documents.doc_type so QMS Document Control's many
# doc_type values — SOP, Protocol, DQ, FAT, SAT, ... — all share the single
# "QMS_DOCUMENT" lifecycle rather than needing one entry per doc_type).
_REGISTRY: dict[str, dict[str, set[str]]] = {
    "URS":                urs_lifecycle.ALLOWED_TRANSITIONS,
    "QMS_DOCUMENT":        _QMS_DOCUMENT_TRANSITIONS,
    "QUALIFICATION":       _QUALIFICATION_TRANSITIONS,
    "VALIDATION_REPORT":   _VALIDATION_REPORT_TRANSITIONS,
    "RISK_ASSESSMENT":     _RISK_ASSESSMENT_TRANSITIONS,
}


class InvalidTransitionError(Exception):
    """Raised when a requested status change is not a legal lifecycle
    transition for the given lifecycle_key. Routes catch this and return
    HTTP 409, mirroring routes/urs.py's existing handling of
    urs_lifecycle.InvalidTransitionError."""

    def __init__(self, lifecycle_key: str, current: str, requested: str):
        self.lifecycle_key = lifecycle_key
        self.current = current
        self.requested = requested
        super().__init__(
            f"Cannot transition {lifecycle_key} status from '{current}' to '{requested}'"
        )


def validate_transition(lifecycle_key: str, current: str, requested: str) -> None:
    """Raise InvalidTransitionError unless `requested` is a legal next status
    from `current` for the given lifecycle_key. A no-op (requested ==
    current) is always allowed. An unknown lifecycle_key is treated as
    having no registered transitions (i.e. only a no-op is legal) rather
    than silently permitting anything."""
    if requested == current:
        return
    allowed = _REGISTRY.get(lifecycle_key, {})
    if requested not in allowed.get(current, set()):
        raise InvalidTransitionError(lifecycle_key, current, requested)

"""
services/urs_lifecycle.py — URS document status state machine.

Enforces the GMP document-control lifecycle (Draft -> Under Review ->
Approved -> Effective, with rejection back to Draft and Obsolete as the
terminal retirement state) so a document's status can only move through
valid transitions.

Previously `status` was a bare TEXT column any caller could set directly via
PUT /urs/<id> or the /generate.../approval action map, with nothing checking
that the new value was reachable from the current one — a client could POST
{"status": "approved"} straight from "draft" and skip review/approval
entirely (routes/urs.py:187 had "status" in the generically-PUTable field
list; urs_database.create_urs() also honored a client-supplied "status" at
creation time). routes/urs.py now funnels every status change through
validate_transition() before writing it, and PUT /urs/<id> no longer accepts
"status" at all — POST /urs/<id>/approval (which records who/why in the
audit trail) is the only path that can move a document's status.

pending_approval is kept as an optional sub-step of the Under Review phase
(matches existing data/action vocabulary already in use — see
routes/urs.py's action->status map) rather than removed outright, so
existing rows and the existing approval-panel action list keep working
unmodified.
"""

from __future__ import annotations

DRAFT = "draft"
UNDER_REVIEW = "under_review"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
EFFECTIVE = "effective"
OBSOLETE = "obsolete"

ALL_STATUSES = {DRAFT, UNDER_REVIEW, PENDING_APPROVAL, APPROVED, EFFECTIVE, OBSOLETE}

# The mandated backbone is Draft -> Under Review -> Approved -> Effective.
# pending_approval sits inside the Under Review phase; obsolete is reachable
# once a document has actually been approved or made effective (you cannot
# retire a document that was never approved).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DRAFT:             {UNDER_REVIEW},
    UNDER_REVIEW:      {PENDING_APPROVAL, APPROVED, DRAFT},
    PENDING_APPROVAL:  {APPROVED, DRAFT},
    APPROVED:          {EFFECTIVE, DRAFT},
    EFFECTIVE:         {OBSOLETE},
    OBSOLETE:          set(),
}


class InvalidTransitionError(Exception):
    """Raised when a requested status change is not a legal lifecycle
    transition from the document's current status. routes/urs.py catches
    this and returns HTTP 409."""

    def __init__(self, current: str, requested: str):
        self.current = current
        self.requested = requested
        super().__init__(
            f"Cannot transition URS status from '{current}' to '{requested}'"
        )


def validate_transition(current: str, requested: str) -> None:
    """Raise InvalidTransitionError unless `requested` is a legal next
    status from `current`. A no-op (requested == current) is always
    allowed — re-submitting the same status is not a state change."""
    if requested == current:
        return
    if requested not in ALL_STATUSES or requested not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(current, requested)


def bump_revision(current: str) -> str:
    """Spreadsheet-column-style increment: A -> B -> ... -> Z -> AA -> AB...

    Called when a previously Approved/Effective document is sent back to
    Draft for rework — GMP revision letters track rework cycles, so a
    document re-entering Draft from a post-approval state gets a new
    revision; a Draft that was simply never approved yet does not."""
    current = (current or "A").strip().upper() or "A"
    chars = list(current)
    i = len(chars) - 1
    while i >= 0:
        if chars[i] != "Z":
            chars[i] = chr(ord(chars[i]) + 1)
            return "".join(chars)
        chars[i] = "A"
        i -= 1
    return "A" + "".join(chars)

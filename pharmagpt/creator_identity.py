"""
creator_identity.py — authenticated creator of a Validation record.

URS, Qualification, IQ/OQ/PQ protocols and Document Control records each carry
`created_by_user_id` / `created_by_display_name`, stamped ONCE at creation from
the authenticated session (never client-supplied, absent from every update
allow-list). The approval engine uses it so that holding `Validation:Submit` is
not enough to submit somebody else's document.

Records created before this column existed have a blank creator id. For those
only, authorship falls back to the authenticated display name that was already
stamped into `prepared_by` at creation — weaker (names are not unique), so the
read-only preflight reports every such record and the recovery procedure
(docs/VALIDATION_APPROVAL_RECOVERY.md) is to stamp the true creator.
"""

from pharmagpt.database import get_connection

_TABLES = ("urs_projects", "qual_qualifications", "qual_protocols", "qms_documents")


def stamp(table: str, row_id: int, user_id: str, display_name: str) -> None:
    """Record the creator exactly once (never overwrites an existing value)."""
    if table not in _TABLES:
        raise ValueError(f"unsupported table {table}")
    if not user_id:
        return
    conn = get_connection()
    with conn:
        conn.execute(
            f"UPDATE {table} SET created_by_user_id = ?, created_by_display_name = ? "
            "WHERE id = ? AND (created_by_user_id IS NULL OR created_by_user_id = '')",
            (user_id, display_name or "", row_id),
        )
    conn.close()


def is_author(creator: dict, user_id: str, display_name: str) -> bool:
    """True if the authenticated caller is the record's creator. `creator`
    carries created_by_user_id / created_by_display_name / prepared_by."""
    cid = (creator.get("created_by_user_id") or "").strip()
    if cid:
        return cid == user_id
    legacy_name = (creator.get("created_by_display_name") or creator.get("prepared_by") or "").strip()
    return bool(legacy_name) and legacy_name == (display_name or "").strip()

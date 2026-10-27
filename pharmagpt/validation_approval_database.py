"""
validation_approval_database.py — sign-off ledger for the standardized
Validation approval workflow (services/validation_approval.py), shared by URS
and Qualification (IQ/OQ/PQ).

One row per signatory sign-off. Rows are append-only: a rejection or revision
marks the cycle's 'completed' rows 'superseded' (they stay readable for the
audit trail) and the next submission starts a fresh set. Every read/write is
filtered by company_id, so a record id from another tenant never matches.
"""

import logging
import sqlite3

from pharmagpt.database import get_connection

logger = logging.getLogger(__name__)

VALIDATION_APPROVAL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS validation_signoffs (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id       TEXT    NOT NULL,
        doc_type         TEXT    NOT NULL,
        record_id        INTEGER NOT NULL,
        revision         TEXT    DEFAULT '',
        signatory_key    TEXT    NOT NULL,
        designation      TEXT    NOT NULL,
        signer_user_id   TEXT    NOT NULL,
        signer_name      TEXT    DEFAULT '',
        signer_role      TEXT    DEFAULT '',
        signer_department TEXT   DEFAULT '',
        meaning          TEXT    DEFAULT '',
        reason           TEXT    DEFAULT '',
        esignature_id    INTEGER DEFAULT NULL,
        signature_hash   TEXT    DEFAULT '',
        status           TEXT    NOT NULL DEFAULT 'completed',
        superseded_reason TEXT   DEFAULT '',
        signed_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_validation_signoffs_record
        ON validation_signoffs (company_id, doc_type, record_id, status);
"""


# Invariants enforced by the database (a check-then-insert in application code
# cannot stop two concurrent requests): within one open cycle ('completed' rows
# only; superseded history is exempt) a designation is signed once, and a user
# signs at most one designation (segregation of duties).
UQ_SIGNATORY = "uq_validation_signoffs_signatory"
UQ_SIGNER = "uq_validation_signoffs_signer"
VALIDATION_APPROVAL_INDEXES = (
    (UQ_SIGNATORY, "(company_id, doc_type, record_id, signatory_key)"),
    (UQ_SIGNER, "(company_id, doc_type, record_id, signer_user_id)"),
)


class DuplicateSignoffError(Exception):
    """A sign-off violated a uniqueness invariant. `same_signer` is True when the
    same user already holds another designation in the cycle."""

    def __init__(self, same_signer: bool):
        super().__init__("duplicate sign-off")
        self.same_signer = same_signer


def find_duplicate_signoffs(conn) -> list[dict]:
    """Read-only: record identifiers (no content) that would violate either
    unique index. Run before creating the indexes on an existing database."""
    out = []
    for name, col in (("signatory", "signatory_key"), ("signer", "signer_user_id")):
        rows = conn.execute(
            f"SELECT company_id, doc_type, record_id, COUNT(*) AS n FROM validation_signoffs "
            f"WHERE status = 'completed' GROUP BY company_id, doc_type, record_id, {col} "
            "HAVING COUNT(*) > 1").fetchall()
        out += [{"invariant": name, "company_id": r["company_id"], "doc_type": r["doc_type"],
                 "record_id": r["record_id"], "count": r["n"]} for r in rows]
    return out


def ensure_unique_indexes(conn) -> bool:
    """Idempotent. If historical duplicates exist the indexes are NOT created and
    nothing is deleted or rewritten: the conflicting record ids are logged for
    manual reconciliation and the application-level checks remain the only guard."""
    dups = find_duplicate_signoffs(conn)
    if dups:
        logger.critical("validation_signoffs: %d duplicate completed sign-off group(s) block the "
                        "unique indexes; reconcile manually: %s", len(dups), dups)
        return False
    for name, cols in VALIDATION_APPROVAL_INDEXES:
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON validation_signoffs {cols} "
                     "WHERE status = 'completed'")
    conn.commit()
    return True


def add_signoff(*, company_id, doc_type, record_id, revision, signatory_key, designation,
                signer_user_id, signer_name, signer_role, signer_department="",
                meaning="", reason="", esignature_id=None, signature_hash="") -> dict:
    """Insert one sign-off. Raises DuplicateSignoffError if the database's unique
    indexes reject it (a concurrent or repeated attempt)."""
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO validation_signoffs
                   (company_id, doc_type, record_id, revision, signatory_key, designation,
                    signer_user_id, signer_name, signer_role, signer_department, meaning,
                    reason, esignature_id, signature_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (company_id, doc_type, record_id, revision, signatory_key, designation,
                 signer_user_id, signer_name, signer_role, signer_department, meaning,
                 reason, esignature_id, signature_hash),
            )
            new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM validation_signoffs WHERE id = ?", (new_id,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError as exc:
        raise DuplicateSignoffError("signer_user_id" in str(exc)) from exc
    finally:
        conn.close()


def attach_signature(signoff_id: int, esignature_id, signature_hash: str) -> None:
    """Link the claimed sign-off to its e-signature record (set once, right
    after the claim; the row is otherwise never modified)."""
    conn = get_connection()
    with conn:
        conn.execute("UPDATE validation_signoffs SET esignature_id = ?, signature_hash = ? "
                     "WHERE id = ? AND esignature_id IS NULL", (esignature_id, signature_hash, signoff_id))
    conn.close()


def discard_unsigned_claim(signoff_id: int) -> None:
    """Release a claim whose action failed before anything else changed. Only
    removes a row that never received an e-signature."""
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM validation_signoffs WHERE id = ? AND esignature_id IS NULL", (signoff_id,))
    conn.close()


def list_signoffs(company_id, doc_type, record_id, include_superseded=False) -> list[dict]:
    conn = get_connection()
    sql = ("SELECT * FROM validation_signoffs WHERE company_id = ? AND doc_type = ? "
           "AND record_id = ?")
    if not include_superseded:
        sql += " AND status = 'completed'"
    rows = conn.execute(sql + " ORDER BY id ASC", (company_id, doc_type, record_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def supersede_signoffs(company_id, doc_type, record_id, reason) -> int:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE validation_signoffs SET status = 'superseded', superseded_reason = ?
               WHERE company_id = ? AND doc_type = ? AND record_id = ? AND status = 'completed'""",
            (reason, company_id, doc_type, record_id),
        )
    conn.close()
    return cur.rowcount

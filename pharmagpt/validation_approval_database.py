"""
validation_approval_database.py — sign-off ledger for the standardized
Validation approval workflow (services/validation_approval.py), shared by URS
and Qualification (IQ/OQ/PQ).

One row per signatory sign-off. Rows are append-only: a rejection or revision
marks the cycle's 'completed' rows 'superseded' (they stay readable for the
audit trail) and the next submission starts a fresh set. Every read/write is
filtered by company_id, so a record id from another tenant never matches.
"""

from pharmagpt.database import get_connection

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


def add_signoff(*, company_id, doc_type, record_id, revision, signatory_key, designation,
                signer_user_id, signer_name, signer_role, signer_department="",
                meaning="", reason="", esignature_id=None, signature_hash="") -> dict:
    conn = get_connection()
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
    conn.close()
    return dict(row)


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

"""
qms_database.py — SQLite schema + shared CRUD for the Quality Management Suite.

QMS is PharmaGPT's second major pillar (parallel in scope to the Validation
pillar). Phase 1 ships three modules — Document Control, Deviation
Management, CAPA — each with its own CRUD file:

    qms_document_database.py   qms_documents, qms_document_versions,
                                qms_document_distribution, qms_document_training
    qms_deviation_database.py  qms_deviations, qms_deviation_investigation,
                                qms_deviation_impact, qms_deviation_capa_link
    qms_capa_database.py       qms_capas, qms_capa_actions, qms_capa_effectiveness

Phase 2 adds Change Control:

    qms_change_control_database.py  qms_change_controls, qms_change_control_impact,
                                     qms_change_control_actions, qms_change_control_links

This file is the single source of truth for the QMS_SCHEMA DDL (hooked into
database.py::init_db(), same as RISK_SCHEMA/QUAL_SCHEMA/etc.) and for the
tables shared by every QMS module — attachments, comments, audit trail, and
approvals/e-signatures are each modeled ONCE as polymorphic tables keyed by
(record_type, record_id) instead of being copy-pasted per module. This keeps
the Common Features (Attachments, Comments, Audit Trail, Approval Workflow)
required by every QMS module in one place, and extends to Phase 2/3 modules
for free — just add a new record_type string.

record_type values in use: 'document' | 'deviation' | 'capa' | 'change_control'
"""

from datetime import datetime
from pharmagpt.database import get_connection


# ── Schema ───────────────────────────────────────────────────────────────────

QMS_SCHEMA = """
    -- ── Shared / polymorphic tables ──────────────────────────────────────────
    -- Every QMS record (a document, a deviation, a CAPA, and future Phase 2/3
    -- records) attaches to these four tables via (record_type, record_id)
    -- instead of each module defining its own copy.

    CREATE TABLE IF NOT EXISTS qms_attachments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type     TEXT    NOT NULL,
        record_id       INTEGER NOT NULL,
        filename        TEXT    NOT NULL,           -- sanitised name on disk
        original_name   TEXT    NOT NULL DEFAULT '',
        file_type       TEXT    DEFAULT '',
        file_size       INTEGER DEFAULT 0,
        description     TEXT    DEFAULT '',
        uploaded_by     TEXT    DEFAULT '',
        created_at      TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_attachments_record ON qms_attachments(record_type, record_id);

    CREATE TABLE IF NOT EXISTS qms_comments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type     TEXT    NOT NULL,
        record_id       INTEGER NOT NULL,
        author          TEXT    DEFAULT '',
        role            TEXT    DEFAULT '',
        comment         TEXT    NOT NULL DEFAULT '',
        created_at      TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_comments_record ON qms_comments(record_type, record_id);

    CREATE TABLE IF NOT EXISTS qms_audit_trail (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type     TEXT    NOT NULL,
        record_id       INTEGER NOT NULL,
        action          TEXT    NOT NULL,
        detail          TEXT    DEFAULT '',
        performed_by    TEXT    DEFAULT '',
        created_at      TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_audit_record ON qms_audit_trail(record_type, record_id);

    CREATE TABLE IF NOT EXISTS qms_approvals (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type     TEXT    NOT NULL,
        record_id       INTEGER NOT NULL,
        action          TEXT    NOT NULL,
        performed_by    TEXT    DEFAULT '',
        role            TEXT    DEFAULT '',
        comments        TEXT    DEFAULT '',
        electronic_sig  TEXT    DEFAULT '',          -- typed name/reason; no PKI (matches risk/qual convention)
        created_at      TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_approvals_record ON qms_approvals(record_type, record_id);

    -- ── Document Control ──────────────────────────────────────────────────────

    CREATE TABLE IF NOT EXISTS qms_documents (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_number        TEXT    NOT NULL DEFAULT '',
        doc_type          TEXT    NOT NULL DEFAULT 'SOP',
        title             TEXT    NOT NULL DEFAULT 'Untitled Document',
        department        TEXT    DEFAULT '',
        category          TEXT    DEFAULT '',
        version           TEXT    DEFAULT '1.0',
        status            TEXT    DEFAULT 'Draft',   -- Draft, Under Review, Pending Approval, Effective, Under Revision, Obsolete
        effective_date    TEXT    DEFAULT '',
        review_date       TEXT    DEFAULT '',
        expiry_date       TEXT    DEFAULT '',
        owner             TEXT    DEFAULT '',
        reviewer          TEXT    DEFAULT '',
        approver          TEXT    DEFAULT '',
        content           TEXT    DEFAULT '',         -- markdown, AI-drafted or manual
        form_data         TEXT    DEFAULT '{}',
        ai_review_data    TEXT    DEFAULT '{}',
        project_id        INTEGER DEFAULT NULL,
        superseded_by     INTEGER DEFAULT NULL,
        created_at        TEXT    DEFAULT (datetime('now')),
        updated_at        TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS qms_document_versions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id       INTEGER NOT NULL,
        version           TEXT    NOT NULL DEFAULT '',
        change_summary    TEXT    DEFAULT '',
        content_snapshot  TEXT    DEFAULT '',
        changed_by        TEXT    DEFAULT '',
        created_at        TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (document_id) REFERENCES qms_documents(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qms_document_distribution (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id       INTEGER NOT NULL,
        distributed_to    TEXT    NOT NULL DEFAULT '',
        department        TEXT    DEFAULT '',
        distributed_date  TEXT    DEFAULT '',
        acknowledged      INTEGER DEFAULT 0,
        acknowledged_date TEXT    DEFAULT '',
        FOREIGN KEY (document_id) REFERENCES qms_documents(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qms_document_training (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id       INTEGER NOT NULL,
        trainee_name      TEXT    NOT NULL DEFAULT '',
        role              TEXT    DEFAULT '',
        training_status   TEXT    DEFAULT 'Pending',  -- Pending, Completed
        training_date     TEXT    DEFAULT '',
        trainer           TEXT    DEFAULT '',
        evidence_ref      TEXT    DEFAULT '',
        created_at        TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (document_id) REFERENCES qms_documents(id) ON DELETE CASCADE
    );

    -- ── CAPA ──────────────────────────────────────────────────────────────────
    -- Defined before Deviations so qms_deviation_capa_link can reference it.

    CREATE TABLE IF NOT EXISTS qms_capas (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        capa_number          TEXT    NOT NULL DEFAULT '',
        title                TEXT    NOT NULL DEFAULT 'Untitled CAPA',
        capa_source          TEXT    DEFAULT 'Deviation',  -- Deviation, Audit, Complaint, Internal Review, Management Review, Other
        source_reference     TEXT    DEFAULT '',
        department           TEXT    DEFAULT '',
        project_id           INTEGER DEFAULT NULL,
        problem_statement    TEXT    DEFAULT '',
        root_cause           TEXT    DEFAULT '',
        initiated_by         TEXT    DEFAULT '',
        date_initiated       TEXT    DEFAULT '',
        target_closure_date  TEXT    DEFAULT '',
        status               TEXT    DEFAULT 'Open',   -- Open, Root Cause Analysis, CA Planned, PA Planned, Implementation, Effectiveness Check, QA Review, Closed, Rejected
        qa_reviewer          TEXT    DEFAULT '',
        approver             TEXT    DEFAULT '',
        closure_date         TEXT    DEFAULT '',
        form_data            TEXT    DEFAULT '{}',
        created_at           TEXT    DEFAULT (datetime('now')),
        updated_at           TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS qms_capa_actions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        capa_id           INTEGER NOT NULL,
        action_type       TEXT    DEFAULT 'Corrective',  -- Corrective, Preventive
        description       TEXT    NOT NULL DEFAULT '',
        owner             TEXT    DEFAULT '',
        due_date          TEXT    DEFAULT '',
        completion_date   TEXT    DEFAULT '',
        status            TEXT    DEFAULT 'Pending',     -- Pending, In Progress, Completed, Overdue, Escalated
        escalated         INTEGER DEFAULT 0,
        escalated_to      TEXT    DEFAULT '',
        escalated_date    TEXT    DEFAULT '',
        evidence_ref      TEXT    DEFAULT '',
        created_at        TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (capa_id) REFERENCES qms_capas(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qms_capa_effectiveness (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        capa_id             INTEGER NOT NULL,
        check_criterion     TEXT    DEFAULT '',
        method              TEXT    DEFAULT '',
        timeframe           TEXT    DEFAULT '',
        acceptable_result   TEXT    DEFAULT '',
        actual_result       TEXT    DEFAULT '',
        status              TEXT    DEFAULT 'Pending',  -- Pending, Pass, Fail
        checked_by          TEXT    DEFAULT '',
        check_date          TEXT    DEFAULT '',
        created_at          TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (capa_id) REFERENCES qms_capas(id) ON DELETE CASCADE
    );

    -- ── Deviation Management ─────────────────────────────────────────────────

    CREATE TABLE IF NOT EXISTS qms_deviations (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        deviation_number      TEXT    NOT NULL DEFAULT '',
        title                 TEXT    NOT NULL DEFAULT 'Untitled Deviation',
        deviation_type        TEXT    DEFAULT 'Minor',         -- Minor, Major, Critical, Market
        deviation_category    TEXT    DEFAULT 'Manufacturing', -- Manufacturing, Laboratory, Engineering, Validation
        department            TEXT    DEFAULT '',
        area                  TEXT    DEFAULT '',
        product               TEXT    DEFAULT '',
        batch_lot             TEXT    DEFAULT '',
        equipment             TEXT    DEFAULT '',
        project_id            INTEGER DEFAULT NULL,
        date_of_occurrence    TEXT    DEFAULT '',
        date_reported         TEXT    DEFAULT '',
        initiated_by          TEXT    DEFAULT '',
        description           TEXT    DEFAULT '',
        immediate_action      TEXT    DEFAULT '',
        status                TEXT    DEFAULT 'Initiated',  -- Initiated, Under Investigation, Root Cause Identified, Impact Assessed, Risk Assessed, CAPA Assigned, QA Review, Approved, Closed, Rejected
        risk_level            TEXT    DEFAULT '',
        qa_reviewer           TEXT    DEFAULT '',
        approver              TEXT    DEFAULT '',
        closure_date          TEXT    DEFAULT '',
        form_data             TEXT    DEFAULT '{}',
        ai_investigation_data TEXT    DEFAULT '{}',
        created_at            TEXT    DEFAULT (datetime('now')),
        updated_at            TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS qms_deviation_investigation (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        deviation_id           INTEGER NOT NULL UNIQUE,
        root_cause_category    TEXT    DEFAULT '',
        root_cause_statement   TEXT    DEFAULT '',
        fishbone_data          TEXT    DEFAULT '{}',   -- {man:[], machine:[], method:[], material:[], measurement:[], environment:[]}
        five_why_data          TEXT    DEFAULT '[]',   -- [{question, answer}, ...]
        timeline_data          TEXT    DEFAULT '[]',   -- [{datetime, event}, ...]
        investigator           TEXT    DEFAULT '',
        investigation_date     TEXT    DEFAULT '',
        created_at             TEXT    DEFAULT (datetime('now')),
        updated_at             TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (deviation_id) REFERENCES qms_deviations(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qms_deviation_impact (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        deviation_id     INTEGER NOT NULL,
        impact_area      TEXT    DEFAULT '',    -- Product Quality, Patient Safety, Regulatory, Batch Disposition
        assessment_text  TEXT    DEFAULT '',
        risk_level       TEXT    DEFAULT '',
        batches_affected TEXT    DEFAULT '',
        created_at       TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (deviation_id) REFERENCES qms_deviations(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qms_deviation_capa_link (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        deviation_id    INTEGER NOT NULL,
        capa_id         INTEGER NOT NULL,
        created_at      TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (deviation_id) REFERENCES qms_deviations(id) ON DELETE CASCADE,
        FOREIGN KEY (capa_id)      REFERENCES qms_capas(id)      ON DELETE CASCADE
    );

    -- ── Change Control (Phase 2) ─────────────────────────────────────────────

    CREATE TABLE IF NOT EXISTS qms_change_controls (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        cc_number                   TEXT    NOT NULL DEFAULT '',
        title                       TEXT    NOT NULL DEFAULT 'Untitled Change',
        change_type                 TEXT    DEFAULT 'Minor',      -- Major, Minor, Critical, Temporary, Permanent, Emergency
        change_category             TEXT    DEFAULT 'Equipment',  -- Equipment, Facility, HVAC, Water System, Compressed Air, Steam, Electrical, Software, PLC, SCADA, MES, ERP, Barcode System, Vision System, BMS, LIMS, Validation, SOP, Specification, Packaging, Warehouse, Quality, Engineering, Production, Utilities, IT
        department                  TEXT    DEFAULT '',
        area                        TEXT    DEFAULT '',
        equipment_system            TEXT    DEFAULT '',
        project_id                  INTEGER DEFAULT NULL,
        requested_by                TEXT    DEFAULT '',
        date_requested               TEXT    DEFAULT '',
        target_implementation_date  TEXT    DEFAULT '',
        change_description          TEXT    DEFAULT '',
        reason_for_change           TEXT    DEFAULT '',
        current_state               TEXT    DEFAULT '',
        proposed_state              TEXT    DEFAULT '',
        status                      TEXT    DEFAULT 'Draft',  -- Draft, Submitted, Initial Review, Impact Assessment, Risk Assessment, Department Review, QA Review, Approval, Implementation, Verification, Effectiveness Review, Closed, Rejected
        risk_level                  TEXT    DEFAULT '',
        qa_reviewer                 TEXT    DEFAULT '',
        approver                    TEXT    DEFAULT '',
        implementation_date         TEXT    DEFAULT '',
        verification_date           TEXT    DEFAULT '',
        closure_date                TEXT    DEFAULT '',
        form_data                   TEXT    DEFAULT '{}',
        ai_narratives                TEXT    DEFAULT '{}',  -- {risk_summary, rollback_plan, regulatory_impact, justification, executive_summary, verification_summary, effectiveness_review}
        created_at                  TEXT    DEFAULT (datetime('now')),
        updated_at                  TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS qms_change_control_impact (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        cc_id            INTEGER NOT NULL,
        impact_area      TEXT    DEFAULT '',   -- Validation, Qualification, Risk, URS, SOP, Training, Equipment, Documents, Software, Utilities, Regulatory Compliance, Business Continuity, Electronic Records, Electronic Signatures
        impacted         TEXT    DEFAULT 'Potential',  -- Yes, No, Potential
        extent           TEXT    DEFAULT '',
        action_required  TEXT    DEFAULT '',
        created_at       TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (cc_id) REFERENCES qms_change_controls(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qms_change_control_actions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        cc_id             INTEGER NOT NULL,
        step_no           INTEGER DEFAULT 0,
        activity          TEXT    NOT NULL DEFAULT '',
        responsible       TEXT    DEFAULT '',
        start_date        TEXT    DEFAULT '',
        target_date       TEXT    DEFAULT '',
        completion_date   TEXT    DEFAULT '',
        status            TEXT    DEFAULT 'Pending',  -- Pending, In Progress, Completed, Overdue
        created_at        TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (cc_id) REFERENCES qms_change_controls(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS qms_change_control_links (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        cc_id           INTEGER NOT NULL,
        linked_type     TEXT    NOT NULL,   -- deviation, capa
        linked_id       INTEGER NOT NULL,
        created_at      TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (cc_id) REFERENCES qms_change_controls(id) ON DELETE CASCADE
    );
"""


# ── Record numbering ──────────────────────────────────────────────────────────

_DOC_TYPE_CODES = {
    "SOP": "SOP", "Protocol": "PRO", "Specification": "SPC", "Test Method": "TM",
    "Format": "FMT", "Template": "TPL", "Logbook": "LOG", "Checklist": "CHK",
    "Policy": "POL", "Manual": "MAN", "Work Instruction": "WI",
    # Phase 3 (Enterprise Validation Platform): DQ/FAT/SAT consolidated into
    # Document Control from the lifecycle-less generic wizard — see
    # routes/validation.py::_RETIRED_DOC_TYPES. Purely additive: doc_type is
    # free text, so these three keys are the only schema-adjacent change.
    "DQ": "DQ", "FAT": "FAT", "SAT": "SAT",
}


def generate_document_number(doc_type: str, department: str = "") -> str:
    """Return the next sequential document number, e.g. SOP-QA-0001.

    A single-word department (e.g. "QA") is used as-is (uppercased, capped at
    4 chars); a multi-word department (e.g. "Quality Assurance") is
    abbreviated to its initials ("QA")."""
    code = _DOC_TYPE_CODES.get(doc_type, "DOC")
    words = department.split()
    if not words:
        dept = "GEN"
    elif len(words) == 1:
        dept = words[0].upper()[:4]
    else:
        dept = "".join(w[0] for w in words).upper()[:4]
    prefix = f"{code}-{dept}"
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM qms_documents WHERE doc_number LIKE ?",
        (f"{prefix}-%",),
    ).fetchone()
    conn.close()
    seq = (row["cnt"] if row else 0) + 1
    return f"{prefix}-{seq:04d}"


def _next_sequence(table: str, number_column: str, prefix: str) -> str:
    """Return the next sequential number like PREFIX-2026-0007. `table` and
    `number_column` are always hardcoded call-site literals, never user input."""
    year = datetime.now().strftime("%Y")
    year_prefix = f"{prefix}-{year}"
    conn = get_connection()
    row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM {table} WHERE {number_column} LIKE ?",
        (f"{year_prefix}-%",),
    ).fetchone()
    conn.close()
    seq = (row["cnt"] if row else 0) + 1
    return f"{year_prefix}-{seq:04d}"


def generate_deviation_number() -> str:
    return _next_sequence("qms_deviations", "deviation_number", "DEV")


def generate_capa_number() -> str:
    return _next_sequence("qms_capas", "capa_number", "CAPA")


def generate_change_control_number() -> str:
    return _next_sequence("qms_change_controls", "cc_number", "CC")


# ── Attachments (shared) ──────────────────────────────────────────────────────

def add_attachment(record_type: str, record_id: int, filename: str, original_name: str,
                   file_type: str = "", file_size: int = 0, description: str = "",
                   uploaded_by: str = "") -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_attachments
           (record_type, record_id, filename, original_name, file_type, file_size, description, uploaded_by)
           VALUES (?,?,?,?,?,?,?,?)""",
        (record_type, record_id, filename, original_name, file_type, file_size, description, uploaded_by),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_attachments WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_attachments(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_attachments WHERE record_type = ? AND record_id = ? ORDER BY created_at DESC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_attachment(attachment_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_attachments WHERE id = ?", (attachment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_attachment(attachment_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM qms_attachments WHERE id = ?", (attachment_id,))
    conn.commit()
    conn.close()


# ── Comments (shared) ─────────────────────────────────────────────────────────

def add_comment(record_type: str, record_id: int, author: str, comment: str, role: str = "") -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO qms_comments (record_type, record_id, author, role, comment) VALUES (?,?,?,?,?)",
        (record_type, record_id, author, role, comment),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_comments WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_comments(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_comments WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Audit trail (shared) ──────────────────────────────────────────────────────

def add_audit_entry(record_type: str, record_id: int, action: str,
                    performed_by: str = "", detail: str = "") -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO qms_audit_trail (record_type, record_id, action, detail, performed_by) VALUES (?,?,?,?,?)",
        (record_type, record_id, action, detail, performed_by),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_audit_trail WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_audit_trail(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_audit_trail WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Approvals / e-signatures (shared) ─────────────────────────────────────────

def add_approval_entry(record_type: str, record_id: int, action: str, performed_by: str = "",
                       role: str = "", comments: str = "", electronic_sig: str = "") -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_approvals (record_type, record_id, action, performed_by, role, comments, electronic_sig)
           VALUES (?,?,?,?,?,?,?)""",
        (record_type, record_id, action, performed_by, role, comments, electronic_sig),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_approvals WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_approval_trail(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_approvals WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
        (record_type, record_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Shared enums (single source of truth for /qms/meta) ──────────────────────

QMS_META = {
    "document_types": list(_DOC_TYPE_CODES.keys()),
    "document_statuses": ["Draft", "Under Review", "Pending Approval", "Effective", "Under Revision", "Obsolete"],
    "deviation_types": ["Minor", "Major", "Critical", "Market"],
    "deviation_categories": ["Manufacturing", "Laboratory", "Engineering", "Validation"],
    "deviation_statuses": [
        "Initiated", "Under Investigation", "Root Cause Identified", "Impact Assessed",
        "Risk Assessed", "CAPA Assigned", "QA Review", "Approved", "Closed", "Rejected",
    ],
    "capa_sources": ["Deviation", "Audit", "Complaint", "Internal Review", "Management Review", "Other"],
    "capa_statuses": [
        "Open", "Root Cause Analysis", "CA Planned", "PA Planned", "Implementation",
        "Effectiveness Check", "QA Review", "Closed", "Rejected",
    ],
    "capa_action_types": ["Corrective", "Preventive"],
    "capa_action_statuses": ["Pending", "In Progress", "Completed", "Overdue", "Escalated"],
    "change_types": ["Major", "Minor", "Critical", "Temporary", "Permanent", "Emergency"],
    "change_categories": [
        "Equipment", "Facility", "HVAC", "Water System", "Compressed Air", "Steam", "Electrical",
        "Software", "PLC", "SCADA", "MES", "ERP", "Barcode System", "Vision System", "BMS", "LIMS",
        "Validation", "SOP", "Specification", "Packaging", "Warehouse", "Quality", "Engineering",
        "Production", "Utilities", "IT",
    ],
    "change_control_statuses": [
        "Draft", "Submitted", "Initial Review", "Impact Assessment", "Risk Assessment",
        "Department Review", "QA Review", "Approval", "Implementation", "Verification",
        "Effectiveness Review", "Closed", "Rejected",
    ],
    "change_control_impact_areas": [
        "Validation", "Qualification", "Risk", "URS", "SOP", "Training", "Equipment", "Documents",
        "Software", "Utilities", "Regulatory Compliance", "Business Continuity",
        "Electronic Records", "Electronic Signatures",
    ],
}

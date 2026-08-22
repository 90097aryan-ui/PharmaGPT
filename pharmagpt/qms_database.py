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

    -- ── Electronic Signatures (21 CFR Part 11 / EU GMP Annex 11) ─────────────
    -- Additive, reusable across every GMP workflow via
    -- pharmagpt/services/esignature_service.py — see that module's docstring.
    -- Immutable by omission: no update/delete function exists anywhere in
    -- this codebase for this table, and none should ever be added.
    CREATE TABLE IF NOT EXISTS qms_esignatures (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id        TEXT    DEFAULT NULL,
        record_type       TEXT    NOT NULL,
        record_id         INTEGER NOT NULL,
        version_number    TEXT    DEFAULT '',
        user_id           TEXT    NOT NULL,
        full_name         TEXT    NOT NULL DEFAULT '',
        role              TEXT    NOT NULL DEFAULT '',
        department        TEXT    NOT NULL DEFAULT '',
        approval_level    TEXT    NOT NULL DEFAULT '',
        meaning           TEXT    NOT NULL,
        reason            TEXT    NOT NULL DEFAULT '',
        old_status        TEXT    DEFAULT '',
        new_status        TEXT    DEFAULT '',
        signed_at_utc     TEXT    NOT NULL,
        ip_address        TEXT    DEFAULT '',
        user_agent        TEXT    DEFAULT '',
        reauth_method     TEXT    NOT NULL DEFAULT 'password',
        signature_hash    TEXT    NOT NULL,
        created_at        TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_esignatures_record ON qms_esignatures(record_type, record_id);
    CREATE INDEX IF NOT EXISTS idx_qms_esignatures_company_id ON qms_esignatures(company_id);

    -- ── Document Control ──────────────────────────────────────────────────────

    -- Controlled document templates (Document Control redesign, Phase 5):
    -- index/headings/sub-headings only — no procedure content. A document
    -- is created against one of these; AI Assist is expected to fill
    -- content within the structure without removing/restructuring the
    -- controlled headings (enforcement of that constraint in the AI prompt
    -- itself is deferred — see services/qms_document_prompt.py follow-up).
    -- Templates are themselves versionable/auditable: is_active lets an
    -- outdated template be retired without deleting history of documents
    -- created from it (their own template_id keeps pointing at the retired
    -- row, which stays readable).
    CREATE TABLE IF NOT EXISTS qms_document_templates (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_type       TEXT    NOT NULL DEFAULT 'SOP',
        name           TEXT    NOT NULL DEFAULT '',
        structure_json TEXT    NOT NULL DEFAULT '[]',  -- ordered list of {"heading":..., "sub_headings":[...]}
        is_active      INTEGER NOT NULL DEFAULT 1,
        company_id     TEXT    DEFAULT '',              -- '' = platform-wide default template
        created_by     TEXT    DEFAULT '',
        created_at     TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_document_templates_doc_type ON qms_document_templates(doc_type, company_id);

    CREATE TABLE IF NOT EXISTS qms_documents (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_number        TEXT    NOT NULL DEFAULT '',
        doc_type          TEXT    NOT NULL DEFAULT 'SOP',
        title             TEXT    NOT NULL DEFAULT 'Untitled Document',
        department        TEXT    DEFAULT '',
        category          TEXT    DEFAULT '',
        version           TEXT    DEFAULT '1.0',
        status            TEXT    DEFAULT 'Draft',   -- Draft, Under Review, Pending Approval, Approved, Effective, Under Revision, Obsolete
        effective_date    TEXT    DEFAULT '',
        review_date       TEXT    DEFAULT '',
        expiry_date       TEXT    DEFAULT '',
        owner             TEXT    DEFAULT '',
        reviewer          TEXT    DEFAULT '',
        approver          TEXT    DEFAULT '',
        content           TEXT    DEFAULT '',         -- markdown, AI-drafted or manual
        template_id       INTEGER DEFAULT NULL,        -- FK to qms_document_templates.id (Phase 5)
        form_data         TEXT    DEFAULT '{}',
        ai_review_data    TEXT    DEFAULT '{}',
        project_id        INTEGER DEFAULT NULL,
        superseded_by     INTEGER DEFAULT NULL,
        current_version_id INTEGER DEFAULT NULL,      -- FK to qms_document_versions.id: the authoritative
                                                        -- current version row (Document Control redesign —
                                                        -- see services/document_versioning.py). Denormalized
                                                        -- `content`/`version`/`status` above stay in sync with
                                                        -- this row for existing list/dashboard/search queries,
                                                        -- but qms_document_versions is the system of record.
        created_at        TEXT    DEFAULT (datetime('now')),
        updated_at        TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
    );

    -- Document Control redesign — authoritative, append-only version ledger.
    -- Once a row's status leaves 'draft' it is immutable (enforced at three
    -- layers: service functions never update a non-draft row; routes never
    -- expose an edit path for one; trg_document_versions_immutable below
    -- blocks it even via raw SQL — see services/document_versioning.py and
    -- services/lifecycle_engine.py's QMS_DOCUMENT_VERSION registry entry).
    CREATE TABLE IF NOT EXISTS qms_document_versions (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id            INTEGER NOT NULL,
        version                TEXT    NOT NULL DEFAULT '',
        change_summary         TEXT    DEFAULT '',
        content_snapshot       TEXT    DEFAULT '',
        changed_by             TEXT    DEFAULT '',
        created_at             TEXT    DEFAULT (datetime('now')),
        version_number         TEXT    DEFAULT '',     -- canonical X.Y number (services/document_versioning.py);
                                                         -- `version` above is kept identical for backward reads
        parent_version_id      INTEGER DEFAULT NULL,    -- FK to the version this one was forked from (rejection
                                                         -- or new revision cycle); NULL only for a document's
                                                         -- very first version (0.1)
        status                 TEXT    NOT NULL DEFAULT 'draft',  -- draft | under_review | review_rejected |
                                                         -- pending_approval | approval_rejected | approved |
                                                         -- effective | superseded  (lifecycle_engine.py
                                                         -- QMS_DOCUMENT_VERSION registry governs transitions)
                                                         -- CURRENT EDITABLE DRAFT = 'draft'; every other value
                                                         -- is one of the spec's "IMMUTABLE" states.
        workflow_instance_id   INTEGER DEFAULT NULL,    -- FK to qms_workflow_instances.id for this version's
                                                         -- review/approval cycle (ties votes/audit to the
                                                         -- exact version transitively)
        rejection_reason       TEXT    DEFAULT '',      -- permanently associated with a review_rejected /
                                                         -- approval_rejected version; never cleared or moved
        self_check_completed_at TEXT   DEFAULT '',      -- Author Self-Check hard gate (per-version; never
                                                         -- carried forward to a new version)
        source_attachment_id   INTEGER DEFAULT NULL,    -- FK to qms_attachments.id when this version's content
                                                         -- came from an "Upload Final Author Version" file
        effective_date         TEXT    DEFAULT '',      -- set only on the version that actually became Effective
        created_by_user_id     TEXT    DEFAULT '',
        FOREIGN KEY (document_id) REFERENCES qms_documents(id) ON DELETE CASCADE,
        FOREIGN KEY (parent_version_id) REFERENCES qms_document_versions(id)
    );
    CREATE INDEX IF NOT EXISTS idx_qms_document_versions_document ON qms_document_versions(document_id);

    -- Defense-in-depth (rule: no normal mechanism, including Super Admin,
    -- may silently alter historical content), split into two precise
    -- triggers rather than one blanket guard:
    --
    -- (1) Content identity is frozen the moment a version leaves 'draft'
    --     for the first time and never legitimately changes again — with
    --     one narrow, well-defined exception: the version_number/version
    --     columns ARE legitimately rewritten exactly once, at the specific
    --     approved -> effective transition (services/document_versioning.py's
    --     numbering rule bumps e.g. 0.3 -> 1.0 only once a version actually
    --     becomes Effective, per the locked spec — see
    --     qms_document_database.try_clear_training_gate()). content_snapshot
    --     itself is never included in that same UPDATE statement, so it
    --     stays fully frozen even during this one exception.
    CREATE TRIGGER IF NOT EXISTS trg_document_versions_immutable_content
    BEFORE UPDATE OF content_snapshot, version, version_number, change_summary,
                       parent_version_id, created_by_user_id, document_id
    ON qms_document_versions
    WHEN OLD.status != 'draft'
         AND NOT (OLD.status = 'approved' AND NEW.status = 'effective')
    BEGIN
        SELECT RAISE(ABORT, 'Immutable document version: content cannot be modified once submitted');
    END;
    -- (2) rejection_reason is legitimately written exactly once, at the
    --     moment a version transitions INTO review_rejected/approval_rejected
    --     (i.e. while OLD.status is still 'under_review'/'pending_approval',
    --     not yet 'draft'-excluded by trigger (1) above) — so its guard is
    --     "never overwrite a reason that's already been recorded", not tied
    --     to the draft/non-draft boundary at all.
    CREATE TRIGGER IF NOT EXISTS trg_document_versions_immutable_rejection_reason
    BEFORE UPDATE OF rejection_reason
    ON qms_document_versions
    WHEN OLD.rejection_reason != ''
    BEGIN
        SELECT RAISE(ABORT, 'Immutable document version: rejection reason cannot be modified once recorded');
    END;

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
        document_version_id INTEGER DEFAULT NULL,  -- Document Control redesign: the exact version this
                                                     -- training assignment gates. Populated only for the
                                                     -- version that reached 'approved' (training against a
                                                     -- version that was rejected before approval has no
                                                     -- regulatory value) — see services/document_versioning.py.
                                                     -- NULL for training rows created before this redesign.
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

    -- Effectiveness Verification (compliance gap fix): the formal QA sign-off
    -- gate a CAPA must pass through before it may reach QA Review/Closed —
    -- distinct from qms_capa_effectiveness above, which is a free-form
    -- checklist of individual check criteria. One row per verification
    -- attempt (history is preserved across Partially/Not Effective cycles,
    -- never overwritten) — see routes/qms_capa.py
    -- ::submit_effectiveness_verification.
    CREATE TABLE IF NOT EXISTS qms_capa_effectiveness_verifications (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        capa_id               INTEGER NOT NULL,
        verification_date     TEXT    DEFAULT '',
        verified_by           TEXT    DEFAULT '',
        verification_method   TEXT    DEFAULT '',
        objective_evidence    TEXT    DEFAULT '',
        result                TEXT    DEFAULT '',  -- Effective, Partially Effective, Not Effective
        comments              TEXT    DEFAULT '',
        workflow_step_order   INTEGER DEFAULT NULL,
        created_by            TEXT    DEFAULT '',
        created_at            TEXT    DEFAULT (datetime('now')),
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
        status                TEXT    DEFAULT 'Draft',  -- see QMS_META.deviation_statuses (Phase 1 workflow redesign)
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

    -- ── Feature Requests (v1: CRUD only — no workflow/approvals/dual-write) ──

    CREATE TABLE IF NOT EXISTS feature_requests (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        fr_number       TEXT    NOT NULL DEFAULT '',
        title           TEXT    NOT NULL DEFAULT 'Untitled Feature Request',
        description     TEXT    DEFAULT '',
        module          TEXT    DEFAULT '',
        priority        TEXT    NOT NULL DEFAULT 'Medium',   -- Low, Medium, High, Critical
        status          TEXT    NOT NULL DEFAULT 'New',      -- New, Review, Approved, Development, Testing, Released, Closed
        assigned_to     TEXT    DEFAULT '',
        created_by      TEXT    DEFAULT '',
        company_id      TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_feature_requests_company ON feature_requests(company_id);

    -- ── Workflow Engine (Phase 1: Deviation Investigation Redesign) ─────────
    -- Generic, cross-module multi-step approval engine. A `qms_workflow_
    -- templates` row is a named, ordered workflow definition (module-scoped,
    -- e.g. module='deviation'); `qms_workflow_template_steps` are its ordered
    -- steps, each either step_type='approval' (only a user_id explicitly
    -- assigned to that step's instance may decide it — see
    -- qms_workflow_step_approvers) or step_type='activity' (any user whose
    -- role is in eligible_roles may advance it, no named assignment needed).
    -- `qms_workflow_instances`/`_instance_steps` are the per-record run of a
    -- template; a record can have more than one instance over its lifetime
    -- (e.g. a fresh instance on resubmission after rejection), so history is
    -- never overwritten. Reusable as-is by CAPA/Change Control/SOP later —
    -- adding another module only needs a new template + step rows, no schema
    -- change. See services/workflow_engine.py.

    CREATE TABLE IF NOT EXISTS qms_workflow_templates (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow_key    TEXT    NOT NULL UNIQUE,
        name            TEXT    NOT NULL DEFAULT '',
        module          TEXT    NOT NULL DEFAULT '',
        is_active       INTEGER NOT NULL DEFAULT 1,
        created_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS qms_workflow_template_steps (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id       INTEGER NOT NULL,
        step_order        INTEGER NOT NULL,
        step_key          TEXT    NOT NULL,
        step_name         TEXT    NOT NULL DEFAULT '',
        step_type         TEXT    NOT NULL DEFAULT 'activity',  -- approval | activity
        eligible_roles    TEXT    NOT NULL DEFAULT '',          -- CSV of platform roles
        gate_status       TEXT    NOT NULL DEFAULT '',          -- record status set on completion
        approval_mode     TEXT    NOT NULL DEFAULT 'any',       -- any (first assigned approver decides) | quorum (N distinct approve votes required)
        required_quorum   INTEGER DEFAULT NULL,                 -- only meaningful when approval_mode='quorum'
        quorum_eligible   INTEGER NOT NULL DEFAULT 1,           -- Document Control redesign: whether this step
                                                                 -- may ever be snapshotted as quorum mode at
                                                                 -- start_instance() time, regardless of a
                                                                 -- record's own quorum override. Default 1
                                                                 -- reproduces today's behaviour for every module
                                                                 -- that never sets a quorum override; Document
                                                                 -- Control's own seed sets this 0 on its Review
                                                                 -- step so only the final Approval step is ever
                                                                 -- quorum-gated (Review stays single-reviewer).
        UNIQUE (template_id, step_order),
        UNIQUE (template_id, step_key),
        FOREIGN KEY (template_id) REFERENCES qms_workflow_templates(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_qms_wf_template_steps ON qms_workflow_template_steps(template_id, step_order);

    CREATE TABLE IF NOT EXISTS qms_workflow_instances (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id         INTEGER NOT NULL,
        record_type         TEXT    NOT NULL,
        record_id           INTEGER NOT NULL,
        company_id          TEXT    DEFAULT '',
        status              TEXT    NOT NULL DEFAULT 'in_progress',  -- in_progress | completed | rejected
        current_step_order  INTEGER NOT NULL DEFAULT 1,
        started_at          TEXT    DEFAULT (datetime('now')),
        completed_at        TEXT    DEFAULT '',
        document_version_id INTEGER DEFAULT NULL,   -- Document Control redesign only: FK to the exact
                                                      -- qms_document_versions row this review/approval cycle
                                                      -- belongs to. NULL for every other record_type (CAPA,
                                                      -- Deviation, Change Control) — those have no version
                                                      -- concept and are unaffected. Ties votes/audit to a
                                                      -- specific version transitively (via this instance).
        FOREIGN KEY (template_id) REFERENCES qms_workflow_templates(id)
    );
    CREATE INDEX IF NOT EXISTS idx_qms_wf_instances_record ON qms_workflow_instances(record_type, record_id);

    CREATE TABLE IF NOT EXISTS qms_workflow_instance_steps (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_id       INTEGER NOT NULL,
        template_step_id  INTEGER NOT NULL,
        step_order        INTEGER NOT NULL,
        step_key          TEXT    NOT NULL DEFAULT '',
        step_name         TEXT    NOT NULL DEFAULT '',
        step_type         TEXT    NOT NULL DEFAULT 'activity',
        eligible_roles    TEXT    NOT NULL DEFAULT '',
        gate_status       TEXT    NOT NULL DEFAULT '',
        status            TEXT    NOT NULL DEFAULT 'pending',  -- pending | in_progress | approved | rejected | returned | skipped
        decided_by        TEXT    DEFAULT '',
        decided_at        TEXT    DEFAULT '',
        comments          TEXT    DEFAULT '',
        approval_mode     TEXT    NOT NULL DEFAULT 'any',       -- snapshotted from the template step at start_instance()
        required_quorum   INTEGER DEFAULT NULL,
        quorum_eligible   INTEGER NOT NULL DEFAULT 1,           -- snapshotted from the template step
        FOREIGN KEY (instance_id) REFERENCES qms_workflow_instances(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_qms_wf_instance_steps ON qms_workflow_instance_steps(instance_id, step_order);

    CREATE TABLE IF NOT EXISTS qms_workflow_step_approvers (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_step_id   INTEGER NOT NULL,
        user_id            TEXT    NOT NULL,
        display_name       TEXT    DEFAULT '',
        created_at         TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (instance_step_id) REFERENCES qms_workflow_instance_steps(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_qms_wf_step_approvers ON qms_workflow_step_approvers(instance_step_id);

    -- Configurable-quorum voting (Document Control): one row per distinct
    -- approver's decision on a quorum-mode instance step. Only used when the
    -- owning qms_workflow_instance_steps.approval_mode = 'quorum' — 'any'-mode
    -- steps (every other module, and Document Control by default) never write
    -- here. UNIQUE guards against the same approver voting twice on one step.
    CREATE TABLE IF NOT EXISTS qms_workflow_step_votes (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_step_id  INTEGER NOT NULL,
        user_id           TEXT    NOT NULL,
        decision          TEXT    NOT NULL,  -- approve | reject
        reason            TEXT    DEFAULT '',
        company_id        TEXT    DEFAULT '',
        voted_at          TEXT    DEFAULT (datetime('now')),
        UNIQUE (instance_step_id, user_id),
        FOREIGN KEY (instance_step_id) REFERENCES qms_workflow_instance_steps(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_qms_wf_step_votes ON qms_workflow_step_votes(instance_step_id);

    -- ── Deviation Workflow Builder (Deviation UI & Workflow Refactor) ────────
    -- Draft-time, per-deviation configuration of the Review chain (steps that
    -- precede Investigation unlock) — one row per step, editable only while
    -- the owning deviation is in Draft. At Submit for Review, this is used to
    -- build a fresh, per-deviation qms_workflow_templates/_template_steps
    -- pair handed to the unmodified services/workflow_engine.py (see
    -- routes/qms_deviations.py::start_workflow) — no role name is hardcoded
    -- into this schema, only into the default *seed values* written at
    -- deviation-create time. is_qa_approval marks the mandatory, always-last
    -- step (its step_key becomes 'qa_approval' in the generated template,
    -- matching the engine's existing unlock/return-target constants).
    CREATE TABLE IF NOT EXISTS qms_deviation_workflow_steps (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        deviation_id            INTEGER NOT NULL,
        step_order              INTEGER NOT NULL,
        step_name               TEXT    NOT NULL DEFAULT '',
        department              TEXT    NOT NULL DEFAULT '',
        approver_user_id        TEXT    NOT NULL DEFAULT '',
        approver_display_name   TEXT    NOT NULL DEFAULT '',
        is_qa_approval          INTEGER NOT NULL DEFAULT 0,
        created_at              TEXT    DEFAULT (datetime('now')),
        updated_at              TEXT    DEFAULT (datetime('now')),
        UNIQUE (deviation_id, step_order),
        FOREIGN KEY (deviation_id) REFERENCES qms_deviations(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_qms_dev_wf_steps ON qms_deviation_workflow_steps(deviation_id, step_order);

    -- Seed the Deviation Investigation workflow template (idempotent —
    -- workflow_key/step_key are UNIQUE, so re-running executescript on an
    -- already-migrated DB is a no-op). Step 1 ("submitted") is completed
    -- automatically by workflow_engine.start_instance() the moment a
    -- deviation is submitted for review, so it needs no named approver.
    -- Steps 3/4/5 are the pre-investigation approval gate (Initiator Manager
    -- Review -> QA Manager Review -> QA Approval); the Investigation tab
    -- stays locked until step 5 ("qa_approval") is approved. Steps 6-11 are
    -- Phase 1 status placeholders for the Phase 2/3 evidence workspace and AI
    -- engine; steps 12/13 are the closing approval gate.
    INSERT OR IGNORE INTO qms_workflow_templates (workflow_key, name, module)
        VALUES ('DEVIATION_INVESTIGATION_V1', 'Deviation Investigation Workflow', 'deviation');

    INSERT OR IGNORE INTO qms_workflow_template_steps
        (template_id, step_order, step_key, step_name, step_type, eligible_roles, gate_status)
    SELECT t.id, s.step_order, s.step_key, s.step_name, s.step_type, s.eligible_roles, s.gate_status
    FROM qms_workflow_templates t
    JOIN (
        SELECT 1  AS step_order, 'submitted'            AS step_key, 'Submitted for Review'      AS step_name, 'activity' AS step_type, 'user,reviewer_qa,company_admin' AS eligible_roles, 'Submitted for Review'      AS gate_status
        UNION ALL SELECT 2,  'initiator_mgr_review', 'Initiator Manager Review', 'approval', 'reviewer_qa,company_admin', 'Initiator Manager Review'
        UNION ALL SELECT 3,  'qa_mgr_review',         'QA Manager Review',        'approval', 'reviewer_qa,company_admin', 'QA Manager Review'
        UNION ALL SELECT 4,  'qa_approval',           'QA Approval',              'approval', 'company_admin',             'QA Approval'
        UNION ALL SELECT 5,  'investigation_open',    'Investigation Open',       'activity', 'reviewer_qa,company_admin', 'Investigation Open'
        UNION ALL SELECT 6,  'evidence_collection',   'Evidence Collection',      'activity', 'reviewer_qa,company_admin', 'Evidence Collection'
        UNION ALL SELECT 7,  'document_review',       'Document Review',          'activity', 'reviewer_qa,company_admin', 'Document Review'
        UNION ALL SELECT 8,  'interviews',            'Personnel Interviews',     'activity', 'reviewer_qa,company_admin', 'Personnel Interviews'
        UNION ALL SELECT 9,  'ai_analysis',           'AI Evidence Analysis',     'activity', 'reviewer_qa,company_admin', 'AI Evidence Analysis'
        UNION ALL SELECT 10, 'root_cause',            'Root Cause Confirmation', 'activity', 'reviewer_qa,company_admin', 'Root Cause Confirmation'
        UNION ALL SELECT 11, 'capa_recommendation',   'CAPA Recommendation',     'activity', 'reviewer_qa,company_admin', 'CAPA Recommendation'
        UNION ALL SELECT 12, 'qa_review',             'QA Review',               'approval', 'company_admin',             'QA Review'
        UNION ALL SELECT 13, 'final_approval',        'Final Approval',          'approval', 'company_admin',             'Final Approval'
        UNION ALL SELECT 14, 'effectiveness_check',   'Effectiveness Check',     'activity', 'reviewer_qa,company_admin', 'Effectiveness Check'
        UNION ALL SELECT 15, 'closed',                'Deviation Closure',       'activity', 'company_admin',             'Closed'
    ) s
    WHERE t.workflow_key = 'DEVIATION_INVESTIGATION_V1';

    -- ── Architecture refactor: Workflow / Investigation separation ───────────
    -- DEVIATION_INVESTIGATION_V1 (above) interleaved lifecycle/approval steps
    -- with investigation-activity steps in one 15-step list. This template
    -- replaces it for *new* deviations with a high-level lifecycle only —
    -- the same 5 approval gates (named-approver enforcement, audit trail,
    -- engine code all unchanged), but every investigation activity (evidence,
    -- SOP review, interviews, timeline, AI, root cause, CAPA recommendation)
    -- is removed as a workflow step and lives instead in the new
    -- qms_investigation_* tables / services/investigation_engine.py,
    -- reachable freely (no step-advance required) once the Investigation
    -- Case unlocks at step 4 ("qa_approval") — same unlock step_key as V1.
    --
    -- "Review" (steps 2-4) and "CAPA" (steps 6-7) each group multiple
    -- sequential named-approval steps under one gate_status/display phase —
    -- this is a *presentation* grouping (qms_deviations.py enriches the
    -- workflow response with a phase label per step); the 5 approval steps
    -- underneath are unchanged in kind from V1's initiator_mgr_review/
    -- qa_mgr_review/qa_approval/qa_review/final_approval.
    --
    -- V1 is kept, not dropped — any instance already running against it
    -- keeps working exactly as before.
    --
    -- NOTE on step 5's step_key: workflow_engine.py::decide_step()'s 'return'
    -- decision (from 'qa_review') hardcodes its return-target lookup as
    -- step_key == 'evidence_collection' (carried over unmodified from V1,
    -- per the instruction not to touch the engine). step_key is an internal
    -- identifier, never shown to users (step_name/gate_status = the
    -- user-facing "Investigation" label are unaffected), so step 5 keeps
    -- that exact step_key here purely so "Return for Investigation" keeps
    -- working against this template without changing engine code.
    INSERT OR IGNORE INTO qms_workflow_templates (workflow_key, name, module)
        VALUES ('DEVIATION_LIFECYCLE_V2', 'Deviation Lifecycle', 'deviation');

    INSERT OR IGNORE INTO qms_workflow_template_steps
        (template_id, step_order, step_key, step_name, step_type, eligible_roles, gate_status)
    SELECT t.id, s.step_order, s.step_key, s.step_name, s.step_type, s.eligible_roles, s.gate_status
    FROM qms_workflow_templates t
    JOIN (
        SELECT 1 AS step_order, 'submitted'            AS step_key, 'Submitted'               AS step_name, 'activity' AS step_type, 'user,reviewer_qa,company_admin' AS eligible_roles, 'Submitted'          AS gate_status
        UNION ALL SELECT 2, 'initiator_mgr_review', 'Initiator Manager Review', 'approval', 'reviewer_qa,company_admin', 'Review'
        UNION ALL SELECT 3, 'qa_mgr_review',         'QA Manager Review',        'approval', 'reviewer_qa,company_admin', 'Review'
        UNION ALL SELECT 4, 'qa_approval',           'QA Approval',              'approval', 'company_admin',             'Review'
        UNION ALL SELECT 5, 'evidence_collection',   'Investigation',           'activity', 'reviewer_qa,company_admin', 'Investigation'
        UNION ALL SELECT 6, 'qa_review',             'QA Review',               'approval', 'company_admin',             'CAPA'
        UNION ALL SELECT 7, 'final_approval',        'Final Approval',          'approval', 'company_admin',             'CAPA'
        UNION ALL SELECT 8, 'effectiveness_check',   'Effectiveness Check',     'activity', 'reviewer_qa,company_admin', 'Effectiveness Check'
        UNION ALL SELECT 9, 'closed',                'Closure',                 'activity', 'company_admin',             'Closed'
    ) s
    WHERE t.workflow_key = 'DEVIATION_LIFECYCLE_V2';

    -- ── CAPA / Change Control / SOP: Workflow Engine adoption ────────────────
    -- Wires these three modules onto the same generic engine Deviations use
    -- (services/workflow_engine.py's STATUS_APPLIERS registry has one entry
    -- per module below) — no schema change, only new template/step rows,
    -- per the existing "Reusable as-is by CAPA/Change Control/SOP later"
    -- design note above. Each template's step_order sequence reproduces that
    -- module's existing status lifecycle (qms_database.py QMS_META) 1:1;
    -- 'approval' steps are the modules' former QA/final-approval gates
    -- (previously enforced only by @require_role, now by a named assignee),
    -- 'activity' steps are the former free-map's plain stage advances.

    INSERT OR IGNORE INTO qms_workflow_templates (workflow_key, name, module)
        VALUES ('CAPA_WORKFLOW_V1', 'CAPA Workflow', 'capa');

    INSERT OR IGNORE INTO qms_workflow_template_steps
        (template_id, step_order, step_key, step_name, step_type, eligible_roles, gate_status)
    SELECT t.id, s.step_order, s.step_key, s.step_name, s.step_type, s.eligible_roles, s.gate_status
    FROM qms_workflow_templates t
    JOIN (
        SELECT 1 AS step_order, 'submitted'             AS step_key, 'CAPA Opened'              AS step_name, 'activity' AS step_type, 'user,reviewer_qa,company_admin' AS eligible_roles, 'Open'                 AS gate_status
        UNION ALL SELECT 2, 'root_cause_analysis', 'Root Cause Analysis',      'activity', 'user,reviewer_qa,company_admin', 'Root Cause Analysis'
        UNION ALL SELECT 3, 'ca_planned',          'Corrective Action Planning', 'activity', 'user,reviewer_qa,company_admin', 'CA Planned'
        UNION ALL SELECT 4, 'pa_planned',          'Preventive Action Planning', 'activity', 'user,reviewer_qa,company_admin', 'PA Planned'
        UNION ALL SELECT 5, 'implementation',      'Implementation',           'activity', 'user,reviewer_qa,company_admin', 'Implementation'
        UNION ALL SELECT 6, 'effectiveness_check', 'Effectiveness Verification', 'approval', 'reviewer_qa,company_admin',    'Effectiveness Check'
        UNION ALL SELECT 7, 'qa_review',           'QA Review',                'approval', 'reviewer_qa,company_admin',      'QA Review'
        UNION ALL SELECT 8, 'closed',              'CAPA Closure',             'approval', 'company_admin',                  'Closed'
    ) s
    WHERE t.workflow_key = 'CAPA_WORKFLOW_V1';

    INSERT OR IGNORE INTO qms_workflow_templates (workflow_key, name, module)
        VALUES ('CHANGE_CONTROL_WORKFLOW_V1', 'Change Control Workflow', 'change_control');

    INSERT OR IGNORE INTO qms_workflow_template_steps
        (template_id, step_order, step_key, step_name, step_type, eligible_roles, gate_status)
    SELECT t.id, s.step_order, s.step_key, s.step_name, s.step_type, s.eligible_roles, s.gate_status
    FROM qms_workflow_templates t
    JOIN (
        SELECT 1 AS step_order, 'submitted'              AS step_key, 'Submitted'               AS step_name, 'activity' AS step_type, 'user,reviewer_qa,company_admin' AS eligible_roles, 'Submitted'            AS gate_status
        UNION ALL SELECT 2,  'initial_review',        'Initial Review',        'activity', 'reviewer_qa,company_admin', 'Initial Review'
        UNION ALL SELECT 3,  'impact_assessment',     'Impact Assessment',     'activity', 'reviewer_qa,company_admin', 'Impact Assessment'
        UNION ALL SELECT 4,  'risk_assessment',        'Risk Assessment',       'activity', 'reviewer_qa,company_admin', 'Risk Assessment'
        UNION ALL SELECT 5,  'department_review',      'Department Review',     'activity', 'reviewer_qa,company_admin', 'Department Review'
        UNION ALL SELECT 6,  'qa_review',              'QA Review',             'approval', 'reviewer_qa,company_admin', 'QA Review'
        UNION ALL SELECT 7,  'approval',               'Approval',              'approval', 'company_admin',             'Approval'
        UNION ALL SELECT 8,  'implementation',         'Implementation',        'activity', 'reviewer_qa,company_admin', 'Implementation'
        UNION ALL SELECT 9,  'verification',           'Verification',          'activity', 'reviewer_qa,company_admin', 'Verification'
        UNION ALL SELECT 10, 'effectiveness_review',   'Effectiveness Review',  'activity', 'reviewer_qa,company_admin', 'Effectiveness Review'
        UNION ALL SELECT 11, 'closed',                 'Closure',               'approval', 'company_admin',             'Closed'
    ) s
    WHERE t.workflow_key = 'CHANGE_CONTROL_WORKFLOW_V1';

    -- 3 steps, not 4: the app's pre-existing test suite (tests/test_kb_sync.py
    -- etc.) already exercises the legacy /approval endpoint as exactly two
    -- actions from Draft to Effective ("Submitted for Review" then
    -- "Approved") — matching that keeps those tests passing unchanged
    -- rather than fabricating a "Pending Approval" gate no caller expects a
    -- separate action for. "Pending Approval" is not a reachable status via
    -- this template (an existing, documented simplification — see docs/plan).
    INSERT OR IGNORE INTO qms_workflow_templates (workflow_key, name, module)
        VALUES ('DOCUMENT_WORKFLOW_V1', 'Document Control Workflow', 'document');

    INSERT OR IGNORE INTO qms_workflow_template_steps
        (template_id, step_order, step_key, step_name, step_type, eligible_roles, gate_status)
    SELECT t.id, s.step_order, s.step_key, s.step_name, s.step_type, s.eligible_roles, s.gate_status
    FROM qms_workflow_templates t
    JOIN (
        SELECT 1 AS step_order, 'submitted'    AS step_key, 'Submitted for Review' AS step_name, 'activity' AS step_type, 'user,reviewer_qa,company_admin' AS eligible_roles, 'Under Review' AS gate_status
        UNION ALL SELECT 2, 'under_review', 'Under Review',   'approval', 'reviewer_qa,company_admin', 'Under Review'
        UNION ALL SELECT 3, 'effective',    'Quality Release', 'approval', 'company_admin',             'Effective'
    ) s
    WHERE t.workflow_key = 'DOCUMENT_WORKFLOW_V1';

    -- Document Control redesign (Phase 3): Review stays single-reviewer —
    -- only the final approval stage ('effective') is ever quorum-gated.
    -- An UPDATE (not part of the step INSERT above) so it's idempotent
    -- and self-correcting even for a DB whose DOCUMENT_WORKFLOW_V1 rows
    -- were already seeded by an earlier boot before quorum_eligible existed
    -- (INSERT OR IGNORE is a no-op once the UNIQUE constraint is already
    -- satisfied, so the column would otherwise stay stuck at its 1 default
    -- forever without this).
    UPDATE qms_workflow_template_steps
    SET quorum_eligible = 0
    WHERE step_key = 'under_review'
      AND template_id = (SELECT id FROM qms_workflow_templates WHERE workflow_key = 'DOCUMENT_WORKFLOW_V1');

    -- ── Configurable approver pool (Document Control redesign, Phase 3) ──────
    -- Department Head and Quality Head/Designee are mandatory pool seats;
    -- Plant Head is optional. Required quorum for the final Approval stage
    -- is always 2 regardless of whether Plant Head is configured (2-of-2 or
    -- 2-of-3) — computed by services/qms_document_database.py's
    -- resolve_pool_approvers(), not stored here. `department = ''` is a
    -- company-wide default pool, overridden per-department by a more
    -- specific row when one exists (see get_approver_pool()).
    CREATE TABLE IF NOT EXISTS qms_document_approver_pool (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id   TEXT    NOT NULL,
        department   TEXT    NOT NULL DEFAULT '',
        pool_role    TEXT    NOT NULL,   -- department_head | quality_head | plant_head
        user_id      TEXT    NOT NULL DEFAULT '',
        display_name TEXT    DEFAULT '',
        active       INTEGER NOT NULL DEFAULT 1,
        created_at   TEXT    DEFAULT (datetime('now')),
        updated_at   TEXT    DEFAULT (datetime('now')),
        UNIQUE (company_id, department, pool_role)
    );
    CREATE INDEX IF NOT EXISTS idx_qms_doc_approver_pool_company ON qms_document_approver_pool(company_id, department);

    -- ── Investigation Engine (new, record_type-agnostic) ─────────────────────
    -- Polymorphic on (record_type, record_id), exactly like qms_attachments/
    -- qms_comments above — so CAPA/Complaint/OOS/OOT/Audit Finding/Supplier/
    -- Validation investigations can reuse these tables later with just a new
    -- record_type string, no schema change. Owned/queried only through
    -- services/investigation_engine.py + qms_investigation_database.py;
    -- routes live on each business module's own blueprint (e.g.
    -- routes/qms_deviations.py's /investigation/* sub-routes), never a
    -- standalone Investigation blueprint.

    CREATE TABLE IF NOT EXISTS qms_investigation_evidence (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type     TEXT    NOT NULL,
        record_id       INTEGER NOT NULL,
        category        TEXT    NOT NULL DEFAULT '',  -- BMR, BPR, SOP, Calibration, PM, Cleaning, Environmental, Training, Validation, Change Control, CAPA, Deviation History, Photo, Video, Other
        attachment_id   INTEGER,                       -- FK to qms_attachments (actual file storage reused, not duplicated)
        description     TEXT    DEFAULT '',
        review_status   TEXT    NOT NULL DEFAULT 'Pending',  -- Reviewed, Pending, Not Applicable, Flagged
        reviewed_by     TEXT    DEFAULT '',
        reviewed_at     TEXT    DEFAULT '',
        notes           TEXT    DEFAULT '',
        created_at      TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (attachment_id) REFERENCES qms_attachments(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_qms_inv_evidence_record ON qms_investigation_evidence(record_type, record_id);

    CREATE TABLE IF NOT EXISTS qms_investigation_sop_review (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type       TEXT    NOT NULL,
        record_id         INTEGER NOT NULL,
        doc_reference     TEXT    NOT NULL DEFAULT '',  -- SOP/doc number or title
        version           TEXT    DEFAULT '',
        effective_date    TEXT    DEFAULT '',
        relevant_section  TEXT    DEFAULT '',
        review_status     TEXT    NOT NULL DEFAULT 'Pending',  -- Reviewed, Not Applicable, Requires Clarification, Pending
        reviewed_by       TEXT    DEFAULT '',
        reviewed_at       TEXT    DEFAULT '',
        notes             TEXT    DEFAULT '',
        created_at        TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_inv_sop_review_record ON qms_investigation_sop_review(record_type, record_id);

    CREATE TABLE IF NOT EXISTS qms_investigation_interviews (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type       TEXT    NOT NULL,
        record_id         INTEGER NOT NULL,
        interviewee_name  TEXT    NOT NULL DEFAULT '',
        interviewee_role  TEXT    DEFAULT '',  -- Operator, Supervisor, Engineering, QA, Maintenance, Warehouse, Validation, Microbiology, Store
        interview_date    TEXT    DEFAULT '',
        questions_json    TEXT    DEFAULT '[]',
        answers_json      TEXT    DEFAULT '[]',
        observation       TEXT    DEFAULT '',
        status            TEXT    NOT NULL DEFAULT 'Scheduled',  -- Scheduled, Completed, Pending
        signature         TEXT    DEFAULT '',
        created_at        TEXT    DEFAULT (datetime('now')),
        updated_at        TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_inv_interviews_record ON qms_investigation_interviews(record_type, record_id);

    CREATE TABLE IF NOT EXISTS qms_investigation_timeline_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type     TEXT    NOT NULL,
        record_id       INTEGER NOT NULL,
        event_type      TEXT    NOT NULL DEFAULT '',  -- Batch, Machine, Operator, Maintenance, Alarm, Deviation, Sampling, Testing
        event_datetime  TEXT    DEFAULT '',
        description     TEXT    DEFAULT '',
        source          TEXT    DEFAULT '',  -- manual | ai_suggested
        created_at      TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_inv_timeline_record ON qms_investigation_timeline_events(record_type, record_id);

    -- Append-only AI run log — replaces the old mutable ai_investigation_data
    -- blob so every run is preserved, re-runnable any number of times, never
    -- gates a workflow step. mode distinguishes the two AI entry points:
    -- 'assistant' (interactive, ad-hoc) vs 'report_generation' (formal
    -- write-up). token_usage_json is nullable ("when available").
    CREATE TABLE IF NOT EXISTS qms_investigation_ai_runs (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type            TEXT    NOT NULL,
        record_id              INTEGER NOT NULL,
        mode                   TEXT    NOT NULL DEFAULT 'assistant',  -- assistant | report_generation
        run_type               TEXT    NOT NULL DEFAULT '',           -- evidence_analysis, root_cause_suggestion, timeline_analysis, capa_suggestion, full_report
        prompt_version         TEXT    DEFAULT '',
        model                  TEXT    DEFAULT '',
        input_snapshot_json    TEXT    DEFAULT '{}',
        output_json            TEXT    DEFAULT '{}',
        evidence_references_json TEXT  DEFAULT '[]',
        confidence             REAL,
        processing_duration_ms INTEGER,
        token_usage_json       TEXT,   -- nullable
        generated_by           TEXT    DEFAULT '',
        created_at             TEXT    DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_qms_inv_ai_runs_record ON qms_investigation_ai_runs(record_type, record_id);

    -- Three-tier root cause (Possible -> Probable -> Confirmed); AI output
    -- (possible_cause when possible_cause_source='ai') is always kept
    -- separate from the investigator's own probable_cause/confirmed_root_cause.
    CREATE TABLE IF NOT EXISTS qms_investigation_root_cause (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type                 TEXT    NOT NULL,
        record_id                   INTEGER NOT NULL,
        possible_cause               TEXT    DEFAULT '',
        possible_cause_source        TEXT    DEFAULT '',  -- ai | manual
        probable_cause               TEXT    DEFAULT '',
        probable_cause_rationale     TEXT    DEFAULT '',
        supporting_evidence_refs_json TEXT   DEFAULT '[]',
        confidence_level             TEXT    DEFAULT '',
        alternative_causes_json      TEXT    DEFAULT '[]',
        confirmed_root_cause         TEXT    DEFAULT '',
        confirmed_by                 TEXT    DEFAULT '',
        confirmed_at                 TEXT    DEFAULT '',
        created_at                   TEXT    DEFAULT (datetime('now')),
        updated_at                   TEXT    DEFAULT (datetime('now')),
        UNIQUE (record_type, record_id)
    );

    -- Finalized handoff into CAPA — replaces the old ad-hoc "suggest CAPA
    -- content" one-shot AI call with a real, auditable record.
    CREATE TABLE IF NOT EXISTS qms_investigation_summary (
        id                            INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type                   TEXT    NOT NULL,
        record_id                     INTEGER NOT NULL,
        summary_text                  TEXT    DEFAULT '',
        key_findings_json              TEXT    DEFAULT '[]',
        root_cause_ref                 TEXT    DEFAULT '',
        recommended_capa_actions_json  TEXT    DEFAULT '[]',
        finalized_by                   TEXT    DEFAULT '',
        finalized_at                   TEXT    DEFAULT '',
        created_at                     TEXT    DEFAULT (datetime('now')),
        updated_at                     TEXT    DEFAULT (datetime('now')),
        UNIQUE (record_type, record_id)
    );

    -- Investigation Tasks (Phase 2 Part 1) — investigative activities, NOT
    -- workflow steps and NOT CAPA actions. Completing a task never advances
    -- the Workflow Engine; it's tracked here purely so the investigator can
    -- assign/monitor the legwork of an investigation. Same polymorphic
    -- (record_type, record_id) pattern as every other Investigation table.
    CREATE TABLE IF NOT EXISTS qms_investigation_tasks (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type             TEXT    NOT NULL,
        record_id               INTEGER NOT NULL,
        title                   TEXT    NOT NULL DEFAULT '',
        description             TEXT    DEFAULT '',
        assigned_user           TEXT    DEFAULT '',
        department              TEXT    DEFAULT '',
        priority                TEXT    DEFAULT 'Medium',   -- Low, Medium, High, Critical
        due_date                TEXT    DEFAULT '',
        status                  TEXT    NOT NULL DEFAULT 'Pending',  -- Pending, In Progress, Completed, Cancelled
        completion_date         TEXT    DEFAULT '',
        evidence_attachment_id  INTEGER,                     -- FK to qms_attachments (reused, not duplicated)
        comments                TEXT    DEFAULT '',
        created_by              TEXT    DEFAULT '',
        created_at              TEXT    DEFAULT (datetime('now')),
        updated_at              TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY (evidence_attachment_id) REFERENCES qms_attachments(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_qms_inv_tasks_record ON qms_investigation_tasks(record_type, record_id);
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


def generate_feature_request_number() -> str:
    return _next_sequence("feature_requests", "fr_number", "FR")


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
                    performed_by: str = "", detail: str = "",
                    company_id: str | None = None, old_values: str = "",
                    new_values: str = "", reason: str = "", ip_address: str = "",
                    session_id: str = "", result: str = "success") -> dict:
    """Write one audit-trail entry. Prefer `pharmagpt.audit.log()` at call
    sites — it derives `performed_by`/`company_id`/`ip_address`/`session_id`
    from the authenticated request context so they can't be spoofed by a
    caller, and computes `old_values`/`new_values` as a diff. This function
    is the low-level DB write; it trusts whatever its caller passes in."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_audit_trail
           (record_type, record_id, action, detail, performed_by, company_id,
            old_values, new_values, reason, ip_address, session_id, result)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (record_type, record_id, action, detail, performed_by, company_id,
         old_values, new_values, reason, ip_address, session_id, result),
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


# ── Electronic Signatures (shared, immutable) ─────────────────────────────────
# No update/delete function exists for this table anywhere in this codebase,
# and none should be added — see pharmagpt/services/esignature_service.py.

def add_esignature(*, company_id: str | None, record_type: str, record_id: int,
                    version_number: str, user_id: str, full_name: str, role: str,
                    department: str, approval_level: str, meaning: str, reason: str,
                    old_status: str, new_status: str, signed_at_utc: str,
                    ip_address: str, user_agent: str, reauth_method: str,
                    signature_hash: str) -> dict:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO qms_esignatures
           (company_id, record_type, record_id, version_number, user_id, full_name,
            role, department, approval_level, meaning, reason, old_status, new_status,
            signed_at_utc, ip_address, user_agent, reauth_method, signature_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (company_id, record_type, record_id, version_number, user_id, full_name,
         role, department, approval_level, meaning, reason, old_status, new_status,
         signed_at_utc, ip_address, user_agent, reauth_method, signature_hash),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM qms_esignatures WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_esignatures(record_type: str, record_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qms_esignatures WHERE record_type = ? AND record_id = ? ORDER BY created_at ASC",
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
    # Phase 1 workflow redesign (services/workflow_engine.py,
    # DEVIATION_INVESTIGATION_V1 template) — replaces the old flat
    # Initiated/Under Investigation/.../Approved/Closed list with the gated,
    # named-approver 17-stage investigation lifecycle. "Rejected" and
    # "Returned for Investigation" are workflow side-statuses, not steps.
    # Architecture refactor (Workflow vs. Investigation separation): new
    # deviations run against DEVIATION_LIFECYCLE_V2, whose status vocabulary
    # is this high-level lifecycle only — "Review" and "CAPA" each cover
    # several individual approval steps (see routes/qms_deviations.py
    # PHASE_GROUPS), and investigation activity no longer produces its own
    # status values (it lives in the Investigation Case, gated only by
    # whether it's unlocked, never by a workflow step). Deviations still
    # running against the retired DEVIATION_INVESTIGATION_V1 template may
    # carry its older, more granular status strings (e.g. "Evidence
    # Collection", "CAPA Recommendation") until they reach Closed/Rejected —
    # not listed here since that template no longer accepts new instances.
    "deviation_statuses": [
        "Draft", "Submitted", "Review", "Investigation", "CAPA",
        "Effectiveness Check", "Closed", "Rejected", "Returned for Investigation",
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
    "feature_request_modules": [
        "Chat", "Document Generator", "Validation", "Knowledge Base", "Equipment Library",
        "Risk Management", "URS", "Qualification", "Reports", "Deviation Management",
        "CAPA", "Change Control", "Document Control", "Feature Requests", "Other",
    ],
    "feature_request_priorities": ["Low", "Medium", "High", "Critical"],
    "feature_request_statuses": ["New", "Review", "Approved", "Development", "Testing", "Released", "Closed"],
}

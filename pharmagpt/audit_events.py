"""
pharmagpt/audit_events.py — Wave 4B: canonical audit-event vocabulary.

A small, additive constants module — not a rewrite of existing audit
call sites. Every action string already written by pre-Wave-4B code
(`"Document created"`, `"CAPA created"`, `f"{step_name}: Approved"`, etc.)
is left exactly as-is: Wave 4A found those strings are read back by
existing tests/reports and are not worth a destructive historical rewrite
(see docs from that audit). Going forward, NEW audit call sites added in
Wave 4B (and any future call site that wants a stable, machine-parseable
action string) should use one of the constants below instead of inventing
another ad hoc phrase.

Naming convention: SCREAMING_SNAKE_CASE, distinct on sight from the older
free-text sentences already in `qms_audit_trail.action` — a reader (or a
query) can tell at a glance whether a row was written under the old ad hoc
vocabulary or this canonical one, without needing a schema flag.

This module intentionally defines the full vocabulary surfaced by the
Wave 4A coverage audit, including a few constants not yet wired into any
call site in this wave (e.g. some DOCUMENT_* lifecycle events already
covered by services/workflow_engine.py's own per-step "{step}: Approved"
strings) — reserved so a future call site has a name to reach for instead
of drifting into a new one-off string.
"""

# ── Authentication ────────────────────────────────────────────────────────
AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
AUTH_LOGIN_FAILURE = "AUTH_LOGIN_FAILURE"
AUTH_LOGOUT = "AUTH_LOGOUT"
AUTH_SESSION_REVOKED = "AUTH_SESSION_REVOKED"
AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"

# Yuktav P0-3: Assume Company Context ("break-glass") lifecycle. Deliberately
# distinct from AUTH_LOGIN_SUCCESS/AUTH_LOGOUT — these mark a super_admin
# entering/exiting a time-boxed grant to act on a specific company's data,
# not a session starting/ending. See routes/auth.py::assume_company /
# end_assume_company and pharmagpt/audit.py::log_cross_company.
BREAK_GLASS_CONTEXT_ENTERED = "BREAK_GLASS_CONTEXT_ENTERED"
BREAK_GLASS_CONTEXT_EXITED = "BREAK_GLASS_CONTEXT_EXITED"

# ── Document Control ─────────────────────────────────────────────────────
DOCUMENT_CREATED = "DOCUMENT_CREATED"
DOCUMENT_UPDATED = "DOCUMENT_UPDATED"
DOCUMENT_DELETED = "DOCUMENT_DELETED"
DOCUMENT_SUBMITTED = "DOCUMENT_SUBMITTED"
DOCUMENT_REVIEWED = "DOCUMENT_REVIEWED"
DOCUMENT_APPROVED = "DOCUMENT_APPROVED"
DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
DOCUMENT_RELEASED = "DOCUMENT_RELEASED"
DOCUMENT_SUPERSEDED = "DOCUMENT_SUPERSEDED"
DOCUMENT_ARCHIVED = "DOCUMENT_ARCHIVED"
DOCUMENT_ASSIGNED = "DOCUMENT_ASSIGNED"
DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED"
DOCUMENT_EXPORTED = "DOCUMENT_EXPORTED"
DOCUMENT_REVIEW_AI = "DOCUMENT_REVIEW_AI"

# ── CAPA ──────────────────────────────────────────────────────────────────
CAPA_CREATED = "CAPA_CREATED"
CAPA_UPDATED = "CAPA_UPDATED"
CAPA_DELETED = "CAPA_DELETED"
CAPA_WORKFLOW_TRANSITION = "CAPA_WORKFLOW_TRANSITION"
CAPA_APPROVED = "CAPA_APPROVED"
CAPA_REJECTED = "CAPA_REJECTED"
CAPA_AI_ASSIST = "CAPA_AI_ASSIST"
CAPA_EXPORTED = "CAPA_EXPORTED"

# ── Change Control ────────────────────────────────────────────────────────
CHANGE_CONTROL_CREATED = "CHANGE_CONTROL_CREATED"
CHANGE_CONTROL_UPDATED = "CHANGE_CONTROL_UPDATED"
CHANGE_CONTROL_DELETED = "CHANGE_CONTROL_DELETED"
CHANGE_CONTROL_WORKFLOW_TRANSITION = "CHANGE_CONTROL_WORKFLOW_TRANSITION"
CHANGE_CONTROL_APPROVED = "CHANGE_CONTROL_APPROVED"
CHANGE_CONTROL_REJECTED = "CHANGE_CONTROL_REJECTED"
CHANGE_CONTROL_AI_ASSIST = "CHANGE_CONTROL_AI_ASSIST"
CHANGE_CONTROL_EXPORTED = "CHANGE_CONTROL_EXPORTED"

# ── Deviation ─────────────────────────────────────────────────────────────
DEVIATION_CREATED = "DEVIATION_CREATED"
DEVIATION_UPDATED = "DEVIATION_UPDATED"
DEVIATION_DELETED = "DEVIATION_DELETED"
DEVIATION_WORKFLOW_TRANSITION = "DEVIATION_WORKFLOW_TRANSITION"
DEVIATION_APPROVED = "DEVIATION_APPROVED"
DEVIATION_REJECTED = "DEVIATION_REJECTED"
DEVIATION_AI_ASSIST = "DEVIATION_AI_ASSIST"
DEVIATION_EXPORTED = "DEVIATION_EXPORTED"

# ── Market Complaint Management (P0) ─────────────────────────────────────
COMPLAINT_CREATED = "COMPLAINT_CREATED"
COMPLAINT_UPDATED = "COMPLAINT_UPDATED"
COMPLAINT_DELETED = "COMPLAINT_DELETED"
COMPLAINT_WORKFLOW_TRANSITION = "COMPLAINT_WORKFLOW_TRANSITION"
COMPLAINT_APPROVED = "COMPLAINT_APPROVED"
COMPLAINT_REJECTED = "COMPLAINT_REJECTED"

# ── Risk ──────────────────────────────────────────────────────────────────
RISK_CREATED = "RISK_CREATED"
RISK_UPDATED = "RISK_UPDATED"
RISK_DELETED = "RISK_DELETED"
RISK_APPROVED = "RISK_APPROVED"
RISK_REJECTED = "RISK_REJECTED"
RISK_AI_ASSIST = "RISK_AI_ASSIST"
RISK_EXPORTED = "RISK_EXPORTED"

# ── E-signature ───────────────────────────────────────────────────────────
ESIGNATURE_SUCCESS = "ESIGNATURE_SUCCESS"
ESIGNATURE_FAILURE = "ESIGNATURE_FAILURE"

# ── Files / data ──────────────────────────────────────────────────────────
FILE_UPLOADED = "FILE_UPLOADED"
FILE_DOWNLOADED = "FILE_DOWNLOADED"
FILE_DELETED = "FILE_DELETED"
DATA_EXPORTED = "DATA_EXPORTED"

# ── RBAC / Admin ──────────────────────────────────────────────────────────
RBAC_ROLE_CHANGED = "RBAC_ROLE_CHANGED"
RBAC_PERMISSION_CHANGED = "RBAC_PERMISSION_CHANGED"
RBAC_DEFAULTS_PROVISIONED = "RBAC_DEFAULTS_PROVISIONED"
USER_ACTIVATED = "USER_ACTIVATED"
USER_DEACTIVATED = "USER_DEACTIVATED"
COMPANY_CREATED = "COMPANY_CREATED"
COMPANY_SUSPENDED = "COMPANY_SUSPENDED"
COMPANY_REACTIVATED = "COMPANY_REACTIVATED"
COMPANY_BRANDING_UPDATED = "COMPANY_BRANDING_UPDATED"

# ── AI generation lifecycle ───────────────────────────────────────────────
AI_GENERATION_STARTED = "AI_GENERATION_STARTED"
AI_GENERATION_COMPLETED = "AI_GENERATION_COMPLETED"
AI_GENERATION_FAILED = "AI_GENERATION_FAILED"

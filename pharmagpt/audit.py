"""
pharmagpt/audit.py — Phase F: unified, non-spoofable audit-trail logging.

Every mutating route should call `log()` here instead of calling
`qms_database.add_audit_entry()` directly. This closes two gaps found by
the Phase E/F compliance audit (PHARMAGPT_v1.0_RELEASE_READINESS_REPORT.md
C4/C5/C6):

1. `performed_by`/`company_id` are always derived from the authenticated
   `g.tenant` (never from client-supplied JSON/form fields) — the same
   non-spoofable-identity principle `tenancy.signing_identity()` already
   applies to e-signature/approval entries, extended here to every audit
   entry.
2. `old_values`/`new_values` are computed as a diff of the two record dicts
   passed in, so an audit row captures what actually changed, not just that
   *something* changed — closing the "no old/new value capture" gap.

`ip_address`/`session_id` are read from the current Flask request/session
so a completed record satisfies Timestamp/User/Company/Object Type/Object
ID/Action/Old Value/New Value/Reason/Session-IP/Result in one call.
"""

import json

from flask import g, request
from flask import session as flask_session

from pharmagpt import qms_database as qmsdb

# Never let a spoofable/sensitive value ride along in old/new value capture.
_REDACT_KEYS = {"password", "electronic_sig", "access_token", "refresh_token", "token"}


def _redact(value: dict) -> dict:
    return {k: ("***" if k in _REDACT_KEYS else v) for k, v in value.items()}


def _serialize(value) -> str:
    if value is None or value == {}:
        return ""
    if isinstance(value, dict):
        try:
            return json.dumps(_redact(value), default=str, sort_keys=True)
        except TypeError:
            return str(_redact(value))
    return str(value)


def _diff(old, new):
    """Restrict `old`/`new` to only the keys that actually differ, so an
    audit row shows what changed rather than duplicating the whole record.
    Falls back to returning both values unchanged if either isn't a dict
    (e.g. a caller passes a plain status string)."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return old, new
    changed_old, changed_new = {}, {}
    for key in set(old) | set(new):
        old_val, new_val = old.get(key), new.get(key)
        if old_val != new_val:
            changed_old[key] = old_val
            changed_new[key] = new_val
    return changed_old, changed_new


def _current_ip() -> str:
    try:
        return request.headers.get("X-Forwarded-For", request.remote_addr) or ""
    except RuntimeError:
        return ""  # no request context (e.g. background job thread)


def _current_session_id() -> str:
    try:
        return flask_session.get("session_id", "") or ""
    except RuntimeError:
        return ""


def log(record_type: str, record_id: int, action: str, *, old=None, new=None,
        reason: str = "", result: str = "success", detail: str = "") -> dict:
    """Write one audit-trail entry.

    `old`/`new` are optional full record dicts (as returned by a
    `*_database.py` get/update function) — only the fields that differ are
    persisted. `result` should be "success" (default) or "failure"; pass a
    `reason` when the action itself carries an explicit justification (e.g.
    a rejection reason) or when logging a failure.
    """
    tenant = getattr(g, "tenant", None)
    if tenant is not None:
        performed_by = tenant.display_name or tenant.email or "unknown"
        company_id = tenant.company_id
    else:
        # No authenticated context (e.g. a background job/thread) — never
        # trust a client-supplied identity here either; "system" is explicit
        # about the absence of a human actor rather than silently blank.
        performed_by, company_id = "system", None

    old_changed, new_changed = _diff(old, new) if (old is not None or new is not None) else (None, None)

    return qmsdb.add_audit_entry(
        record_type, record_id, action,
        performed_by=performed_by,
        detail=detail,
        company_id=company_id,
        old_values=_serialize(old_changed),
        new_values=_serialize(new_changed),
        reason=reason,
        ip_address=_current_ip(),
        session_id=_current_session_id(),
        result=result,
    )


def log_failure(record_type: str, record_id: int, action: str, reason: str) -> dict:
    """Convenience wrapper for logging a blocked/rejected attempt (e.g. an
    illegal status transition, a validation failure on a GxP record) so the
    audit trail also captures unsuccessful attempts, not only successful
    mutations."""
    return log(record_type, record_id, action, reason=reason, result="failure")

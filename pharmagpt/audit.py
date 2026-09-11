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

from pharmagpt import config
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
    """Yuktav P1-2: `request.remote_addr` is the safe default — it reflects
    the actual TCP peer, which a client cannot spoof. It is only overridden
    by an `X-Forwarded-For` entry when `config.TRUSTED_PROXY_COUNT` (0 by
    default — see config.py) confirms this deployment sits behind that many
    verified, trusted reverse proxies; in that case the peer Flask/gunicorn
    sees is the trusted proxy itself, not the real client, so
    `X-Forwarded-For` is the only place the real client IP exists.

    Reads the header from the RIGHT, taking exactly the
    `TRUSTED_PROXY_COUNT`-th entry from the end — the same algorithm
    Werkzeug's ProxyFix and every other correct implementation of this uses.
    A client can prepend arbitrary garbage entries to their own outgoing
    X-Forwarded-For; only the entries actually *appended* by real
    intermediate proxies (i.e. the rightmost ones) are trustworthy. If fewer
    hops are present than configured (misconfiguration, or nothing was ever
    appended), this falls back to `remote_addr` rather than guessing at a
    possibly attacker-controlled value."""
    try:
        trusted_hops = config.TRUSTED_PROXY_COUNT
        if trusted_hops > 0:
            forwarded = request.headers.get("X-Forwarded-For", "")
            hops = [h.strip() for h in forwarded.split(",") if h.strip()]
            if len(hops) >= trusted_hops:
                return hops[-trusted_hops]
        return request.remote_addr or ""
    except RuntimeError:
        return ""  # no request context (e.g. background job thread)


def _current_session_id() -> str:
    try:
        return flask_session.get("session_id", "") or ""
    except RuntimeError:
        return ""


def _active_break_glass_id() -> str:
    """Yuktav P0-3: the current request's active Assume Company Context
    grant id (pharmagpt/auth/middleware.py::apply_assumed_company_context),
    or "" when no break-glass grant is active for this request. Read-only —
    never sets/clears session state itself (routes/auth.py owns that).
    Lets a QMS audit entry written while a super_admin is acting under an
    assumed company be identified as such (joinable back to
    break_glass_access.id) without guessing from company_id alone, which is
    indistinguishable from an ordinary company_admin's own row."""
    try:
        return flask_session.get("break_glass_id", "") or ""
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
        assumed_context=_active_break_glass_id(),
    )


def log_failure(record_type: str, record_id: int, action: str, reason: str, *, detail: str = "") -> dict:
    """Convenience wrapper for logging a blocked/rejected attempt (e.g. an
    illegal status transition, a validation failure on a GxP record) so the
    audit trail also captures unsuccessful attempts, not only successful
    mutations. `detail` is optional, additive context (e.g. the attempted
    request path for an authorization denial) beyond `reason`."""
    return log(record_type, record_id, action, reason=reason, result="failure", detail=detail)


def log_cross_company(record_type: str, record_id: int, action: str, *, target_company_id: str | None,
                       reason: str = "", detail: str = "", result: str = "success") -> dict:
    """Yuktav P0-3: write an audit entry about a DIFFERENT company than the
    acting identity's own — used only for a super_admin's Assume Company
    Context grant (routes/auth.py::assume_company / end_assume_company),
    where the actor's own `g.tenant.company_id` is None (a super_admin has
    no standing company) but the event is unambiguously about the target
    company being entered/exited.

    `performed_by` is still derived non-spoofably from `g.tenant` exactly as
    `log()` does — this function only changes which company_id the row is
    filed under, never who is credited with the action. Never confuse this
    with logging an action as if performed by a user of the target company:
    `performed_by` here is always the super_admin's own identity."""
    tenant = getattr(g, "tenant", None)
    performed_by = (tenant.display_name or tenant.email or "unknown") if tenant is not None else "system"
    return qmsdb.add_audit_entry(
        record_type, record_id, action,
        performed_by=performed_by,
        detail=detail,
        company_id=target_company_id,
        reason=reason,
        ip_address=_current_ip(),
        session_id=_current_session_id(),
        result=result,
    )


def log_unauthenticated(record_type: str, record_id: int, action: str, *,
                         attempted_identifier: str = "", reason: str = "",
                         result: str = "failure", detail: str = "") -> dict:
    """Wave 4B: write an audit entry for an event that happens BEFORE any
    authenticated session exists (e.g. a login attempt) — `g.tenant` is
    never set at this point, so `log()`'s normal derivation doesn't apply.

    Never invents a confirmed actor: `performed_by` is always the literal
    string "anonymous", optionally suffixed with the caller-submitted,
    UNVERIFIED identifier (e.g. the email typed into the login form) for
    forensic/pattern-detection value only — this is what the requester
    typed, not a resolved identity, and must never be confused with
    tenant.display_name/email as written by log() above. `company_id` is
    always None (no tenant resolved yet). Never pass a password, token, or
    other credential as `attempted_identifier` or `detail`."""
    performed_by = f"anonymous ({attempted_identifier})" if attempted_identifier else "anonymous"
    return qmsdb.add_audit_entry(
        record_type, record_id, action,
        performed_by=performed_by, detail=detail, company_id=None,
        reason=reason, ip_address=_current_ip(), session_id=_current_session_id(),
        result=result,
    )

"""
pharmagpt/services/esignature_service.py — the one common Electronic
Signature service every GMP workflow calls (21 CFR Part 11 Subpart C /
EU GMP Annex 11 clause 14).

Additive only. Does not touch pharmagpt/auth/* (authentication, RBAC),
pharmagpt/services/workflow_engine.py (workflow routing/status transitions),
or any existing route's authorization logic. docs/PLATFORM_ARCHITECTURE.md
§18 anticipated exactly this: "a new signature-event table linked to the
existing approval action — not a redesign of the approval workflow itself."

Usage pattern for a route that gates a GMP decision behind an e-signature
(see pharmagpt/routes/qms_documents.py::decide_workflow_step for the
reference integration):

    1. require_esignature(tenant, password, meaning, reason) — call this
       BEFORE performing the underlying decision. Raises before anything is
       mutated if the password is wrong or meaning/reason are invalid, so a
       failed signature attempt never lets a GMP decision through and never
       leaves partial state.
    2. ... perform the route's own existing decision/status-transition code,
       completely unchanged ...
    3. record_signature(...) — call this AFTER the decision has succeeded,
       to write the immutable signature row + audit-trail entry, now that
       old_status/new_status are both known.

A logged-in session alone never satisfies step 1 — require_esignature()
always re-verifies the caller's password against Supabase Auth,
independently of the bearer token already authenticating the request.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from flask import request

from pharmagpt import audit as audit_module
from pharmagpt import qms_database as qmsdb
from pharmagpt.services.supabase_client import get_anonymous_client

# Fixed vocabulary — not configurable per company, since these are the
# regulatory signature manifestations this framework is built around
# (21 CFR Part 11 §11.50 "signature manifestation").
SIGNATURE_MEANINGS = (
    "Created", "Reviewed", "Verified", "Approved",
    "Authorized", "Released", "Rejected", "Cancelled",
)


class ESignatureError(Exception):
    """Raised for a bad signature meaning or a missing reason. Callers
    should return 400 to the client."""


class ReauthenticationError(ESignatureError):
    """Raised when password (or, in future, MFA) re-authentication fails.
    Callers should return 401 to the client."""


def reauthenticate(email: str, password: str) -> bool:
    """Verify `password` against Supabase Auth for `email`, independently
    of the caller's existing bearer-token session — "a logged-in session
    alone must never approve GMP records." Uses a throwaway anonymous
    client; whatever session Supabase Auth returns is discarded immediately,
    never stored or reused for anything else.
    """
    if not email or not password:
        return False
    client = get_anonymous_client()
    try:
        client.auth.sign_in_with_password({"email": email, "password": password})
        return True
    except Exception:
        return False


def validate_meaning_and_reason(meaning: str, reason: str) -> None:
    if meaning not in SIGNATURE_MEANINGS:
        raise ESignatureError(f"meaning must be one of: {', '.join(SIGNATURE_MEANINGS)}")
    if not reason or not reason.strip():
        raise ESignatureError("reason is required")


def require_esignature(tenant, password: str, meaning: str, reason: str) -> None:
    """Gate a GMP decision behind a fresh electronic signature. Call this
    BEFORE performing the decision itself — raises ESignatureError /
    ReauthenticationError and mutates nothing if it fails."""
    validate_meaning_and_reason(meaning, reason)
    if not reauthenticate(tenant.email, password):
        raise ReauthenticationError("Password confirmation failed")


def _current_ip() -> str:
    try:
        return request.headers.get("X-Forwarded-For", request.remote_addr) or ""
    except RuntimeError:
        return ""  # no request context


def _current_user_agent() -> str:
    try:
        return request.headers.get("User-Agent", "") or ""
    except RuntimeError:
        return ""


def compute_signature_hash(payload: dict) -> str:
    """Cryptographically link the signature to the fields it attests to
    (21 CFR Part 11 §11.70): a SHA-256 digest over every captured field,
    canonically ordered. Recomputing this from a stored row and comparing
    (see verify_signature_integrity below) detects any post-write tampering
    with the signature row itself — it does not separately hash-chain each
    module's own business-record content, which would require touching
    every module's schema (out of scope for an additive layer)."""
    canonical = "|".join(f"{k}={payload.get(k, '')}" for k in sorted(payload))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_payload_from_row(row: dict) -> dict:
    return {
        "record_type": row["record_type"], "record_id": row["record_id"],
        "version_number": row["version_number"], "user_id": row["user_id"],
        "meaning": row["meaning"], "reason": row["reason"],
        "old_status": row["old_status"], "new_status": row["new_status"],
        "signed_at_utc": row["signed_at_utc"],
    }


def verify_signature_integrity(row: dict) -> bool:
    """Recompute the hash from a stored qms_esignatures row and compare —
    True if the row hasn't been altered since it was written."""
    return compute_signature_hash(_hash_payload_from_row(row)) == row["signature_hash"]


def record_signature(*, tenant, meaning: str, reason: str, record_type: str, record_id: int,
                      version_number: str = "", old_status: str = "", new_status: str = "",
                      department: str = "", approval_level: str = "",
                      mfa_code: str | None = None) -> dict:
    """Write the immutable signature row + audit-trail entry. Call this
    AFTER the GMP decision it represents has already succeeded — pair with
    require_esignature() called beforehand (see module docstring)."""
    signed_at = datetime.now(timezone.utc).isoformat()
    hash_payload = {
        "record_type": record_type, "record_id": record_id, "version_number": version_number,
        "user_id": tenant.user_id, "meaning": meaning, "reason": reason,
        "old_status": old_status, "new_status": new_status, "signed_at_utc": signed_at,
    }
    signature_hash = compute_signature_hash(hash_payload)

    row = qmsdb.add_esignature(
        company_id=tenant.company_id, record_type=record_type, record_id=record_id,
        version_number=version_number, user_id=tenant.user_id,
        full_name=(tenant.display_name or tenant.email), role=tenant.role,
        department=department, approval_level=approval_level,
        meaning=meaning, reason=reason, old_status=old_status, new_status=new_status,
        signed_at_utc=signed_at, ip_address=_current_ip(), user_agent=_current_user_agent(),
        reauth_method=("password+mfa" if mfa_code else "password"),
        signature_hash=signature_hash,
    )

    audit_module.log(
        record_type, record_id, f"E-Signature: {meaning}",
        old={"status": old_status} if old_status else None,
        new={"status": new_status} if new_status else None,
        reason=reason,
    )
    return row

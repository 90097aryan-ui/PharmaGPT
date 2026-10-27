"""
services/validation_approval.py — the ONE approval workflow shared by the
Validation documents (URS and Qualification IQ/OQ/PQ; DQ is a Document
Control document and is deliberately not wired here — see
docs/VALIDATION_APPROVAL_WORKFLOW.md, "Decisions required").

Standard lifecycle (stored status values):

    draft -> under_review -> technical_review -> qa_review
          -> validation_review -> final_approval -> approved -> effective

Each review status collects one or more signatory sign-offs; the status
advances only when every signatory for that stage has signed. Rejection from
any review status (or approved) returns the document to draft and supersedes
that cycle's sign-offs (they stay readable); resubmission starts a new cycle.
`effective` is reachable only through the "Make Effective" action, which
re-checks that all seven mandatory sign-offs are complete.

Security properties, all enforced here rather than per route:
  - signer identity (user id, name, role) comes from the authenticated
    tenant, never the request body;
  - every sign-off requires a fresh e-signature (esignature_service);
  - reviewer/approver authority is the existing granular RBAC
    (module_access.has_business_permission on "Validation"), plus the
    frozen platform-role gate (company_admin / reviewer_qa) the routes
    already had for everything except submission;
  - one user cannot sign two designations in the same cycle;
  - every sign-off ledger query is filtered by company_id.
"""

from __future__ import annotations

from datetime import date

from pharmagpt import audit
from pharmagpt import config
from pharmagpt import creator_identity
from pharmagpt import validation_approval_database as vadb
from pharmagpt.auth import module_access
from pharmagpt.services import esignature_service
from pharmagpt.services import urs_lifecycle

# ── Statuses and transitions ──────────────────────────────────────────────────
# urs_lifecycle.ALLOWED_TRANSITIONS is the single source of truth.
DRAFT = urs_lifecycle.DRAFT
UNDER_REVIEW = urs_lifecycle.UNDER_REVIEW
TECHNICAL_REVIEW = urs_lifecycle.TECHNICAL_REVIEW
QA_REVIEW = urs_lifecycle.QA_REVIEW
VALIDATION_REVIEW = urs_lifecycle.VALIDATION_REVIEW
FINAL_APPROVAL = urs_lifecycle.FINAL_APPROVAL
APPROVED = urs_lifecycle.APPROVED
EFFECTIVE = urs_lifecycle.EFFECTIVE
OBSOLETE = urs_lifecycle.OBSOLETE
LEGACY_PENDING_APPROVAL = urs_lifecycle.PENDING_APPROVAL

REVIEW_STATUSES = (UNDER_REVIEW, TECHNICAL_REVIEW, QA_REVIEW, VALIDATION_REVIEW, FINAL_APPROVAL)
STANDARD_TRANSITIONS = urs_lifecycle.ALLOWED_TRANSITIONS

_NEXT_STATUS = {
    UNDER_REVIEW: TECHNICAL_REVIEW,
    TECHNICAL_REVIEW: QA_REVIEW,
    QA_REVIEW: VALIDATION_REVIEW,
    VALIDATION_REVIEW: FINAL_APPROVAL,
    FINAL_APPROVAL: APPROVED,
}

# ── Signatory template (the proposed standard) ───────────────────────────────
# `stage` is the status in which the sign-off is collected ("submit" = the
# draft -> under_review step). `departments` and `permission` are the
# CONFIGURATION DECISIONS flagged in docs/VALIDATION_APPROVAL_WORKFLOW.md:
# they map each designation onto the existing department / functional-role
# model (rbac_defaults.TARGET_MODULE_MATRIX). `permission` is the action on
# the "Validation" business module the signer must hold.
_ANY_FUNCTIONAL = ("Coordinator",)
SIGNATORIES: tuple[dict, ...] = (
    {"key": "prepared_by", "label": "Prepared By", "designation": "Validation Engineer",
     "stage": "submit", "departments": ("VALIDATION",), "roles": ("Initiator",) + _ANY_FUNCTIONAL,
     "permission": "Submit"},
    {"key": "reviewed_by", "label": "Reviewed By", "designation": "Process Engineer",
     "stage": UNDER_REVIEW, "departments": ("ENGINEERING", "PRODUCTION"),
     "roles": ("Reviewer",) + _ANY_FUNCTIONAL, "permission": "Review"},
    {"key": "engineering_manager", "label": "Engineering", "designation": "Engineering Manager",
     "stage": TECHNICAL_REVIEW, "departments": ("ENGINEERING",),
     "roles": ("Approver",) + _ANY_FUNCTIONAL, "permission": "Approve"},
    {"key": "production_manager", "label": "Production", "designation": "Production Manager",
     "stage": TECHNICAL_REVIEW, "departments": ("PRODUCTION",),
     "roles": ("Approver",) + _ANY_FUNCTIONAL, "permission": "Approve"},
    {"key": "qa_manager", "label": "Quality Assurance", "designation": "QA Manager",
     "stage": QA_REVIEW, "departments": ("QA",),
     "roles": ("Approver",) + _ANY_FUNCTIONAL, "permission": "Approve"},
    {"key": "validation_manager", "label": "Validation", "designation": "Validation Manager",
     "stage": VALIDATION_REVIEW, "departments": ("VALIDATION",),
     "roles": ("Approver",) + _ANY_FUNCTIONAL, "permission": "Approve"},
    {"key": "final_approval", "label": "Final Approval", "designation": "Site Director / VP Quality",
     "stage": FINAL_APPROVAL, "departments": ("PLANT_HEAD", "QA"),
     "roles": ("Plant Head", "Approver") + _ANY_FUNCTIONAL, "permission": "Approve"},
)
_BY_KEY = {s["key"]: s for s in SIGNATORIES}
MANDATORY_KEYS = tuple(s["key"] for s in SIGNATORIES)

# ── Actions ───────────────────────────────────────────────────────────────────
SUBMIT = "Submitted for Review"
SIGN = "Sign Off"
REJECT = "Rejected"
MAKE_EFFECTIVE = "Make Effective"
OBSOLETE_ACTION = "Obsolete"
# Pre-standard action names the existing UI/clients still send.
_ALIASES = {"Review Complete": SIGN, "Approved": SIGN}
_RETIRED = {"Submitted for Approval"}

_MEANINGS = {  # action -> (default meaning, allowed meanings)
    SUBMIT: ("Created", {"Created", "Verified"}),
    REJECT: ("Rejected", {"Rejected"}),
    MAKE_EFFECTIVE: ("Released", {"Released", "Authorized"}),
    OBSOLETE_ACTION: ("Cancelled", {"Cancelled", "Authorized"}),
}
_PLATFORM_ROLES = ("company_admin", "reviewer_qa")


class ApprovalError(Exception):
    def __init__(self, message: str, http_status: int):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


# ── Pure helpers ──────────────────────────────────────────────────────────────

def signatories_for_stage(stage: str) -> list[dict]:
    return [s for s in SIGNATORIES if s["stage"] == stage]


def completed_keys(rows: list[dict]) -> set[str]:
    return {r["signatory_key"] for r in rows if r.get("status", "completed") == "completed"}


def mandatory_complete(rows: list[dict]) -> bool:
    return completed_keys(rows) >= set(MANDATORY_KEYS)


def is_legacy_approved(all_rows: list[dict]) -> bool:
    """A document that reached `approved` under the pre-standard workflow has
    no sign-off rows at all (current or superseded). Every document that
    reaches `approved` through this module has rows, so this cannot be used
    to bypass the gate."""
    return not all_rows


def effective_allowed(all_rows: list[dict]) -> bool:
    current = [r for r in all_rows if r.get("status") == "completed"]
    return mandatory_complete(current) or is_legacy_approved(all_rows)


def normalize_action(action: str) -> str:
    if action in _RETIRED:
        raise ApprovalError(
            f"'{action}' is retired — the standard workflow advances through "
            f"Sign Off at each review stage.", 400)
    action = _ALIASES.get(action, action)
    if action not in (SUBMIT, SIGN, REJECT, MAKE_EFFECTIVE, OBSOLETE_ACTION):
        raise ApprovalError(f"Unknown action '{action}'", 400)
    return action


def build_page(company_id: str, doc_type: str, record_id: int, status: str) -> dict:
    """Approval-page read model: one row per mandatory signatory with
    name, designation, e-signature record, date and pending/completed
    status. `current` marks the signatories awaiting a signature now."""
    all_rows = vadb.list_signoffs(company_id, doc_type, record_id, include_superseded=True)
    done = {r["signatory_key"]: r for r in all_rows if r["status"] == "completed"}
    rows = []
    for s in SIGNATORIES:
        signed = done.get(s["key"])
        if signed:
            state = "completed"
        elif s["stage"] == status or (s["stage"] == "submit" and status == DRAFT):
            state = "current"
        else:
            state = "pending"
        rows.append({
            "key": s["key"], "label": s["label"], "designation": s["designation"],
            "stage": s["stage"], "status": state,
            "signer_name": signed["signer_name"] if signed else "",
            "signer_role": signed["signer_role"] if signed else "",
            "signed_at": signed["signed_at"] if signed else "",
            "signature": ({"id": signed["esignature_id"], "hash": signed["signature_hash"],
                           "meaning": signed["meaning"], "reason": signed["reason"]} if signed else None),
        })
    return {
        "doc_type": doc_type, "record_id": record_id, "status": status,
        "signatories": rows,
        "completed_count": len(done), "mandatory_count": len(MANDATORY_KEYS),
        "all_mandatory_complete": mandatory_complete(list(done.values())),
        "legacy_approval": status in (APPROVED, EFFECTIVE) and is_legacy_approved(all_rows),
        "superseded_count": sum(1 for r in all_rows if r["status"] == "superseded"),
    }


# ── Authorization ─────────────────────────────────────────────────────────────

def _require_permission(tenant, action: str) -> None:
    if not module_access.has_business_permission(tenant, "Validation", action):
        raise ApprovalError(f"This action requires '{action}' permission on 'Validation'", 403)


def _require_platform_role(tenant) -> None:
    if tenant.role not in _PLATFORM_ROLES:
        raise ApprovalError(
            f"This action requires one of these roles: {', '.join(_PLATFORM_ROLES)}", 403)


def _signer_department(tenant, signatory: dict) -> str:
    """Department code under which the signer is authorized to sign this
    designation. A single user_departments membership must satisfy BOTH the
    designation's department AND its functional role (so an Engineering
    Initiator who is also a Production Approver cannot sign the Engineering
    Manager line). Fail-closed: a directory error denies the signature.
    When enforcement is switched off, returns ''."""
    if not config.VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT:
        return ""
    from pharmagpt.services import org_directory
    from pharmagpt.services.supabase_client import get_service_role_client
    try:
        memberships = org_directory.list_user_departments(
            get_service_role_client(), tenant.user_id, tenant.company_id)
    except Exception:  # noqa: BLE001 - any directory failure must deny, not allow
        raise ApprovalError("Could not verify your department membership — signature denied", 403)
    for m in memberships or []:
        code = (m.get("departments") or {}).get("department_code")
        role = (m.get("workflow_roles") or {}).get("name")
        if code in signatory["departments"] and role in signatory["roles"]:
            return code
    raise ApprovalError(
        f"Signing as {signatory['designation']} requires a {' / '.join(signatory['roles'][:-1] or signatory['roles'])} "
        f"role in: {', '.join(signatory['departments'])}", 403)


def _authorize_signatory(tenant, signatory: dict, current_rows: list[dict]) -> str:
    _require_permission(tenant, signatory["permission"])
    if signatory["key"] != "prepared_by":
        _require_platform_role(tenant)
    if signatory["key"] in completed_keys(current_rows):
        raise ApprovalError(f"{signatory['label']} has already signed this cycle", 409)
    # No configuration switch: segregation of duties is always enforced. An
    # exception would need a documented, QA-authorized policy implemented as
    # reviewed code — it must never be a silent toggle.
    if any(r["signer_user_id"] == tenant.user_id and r["status"] == "completed" for r in current_rows):
        raise ApprovalError(
            "Segregation of duties: you have already signed another designation on this "
            "document — each signatory must be a different person", 403)
    return _signer_department(tenant, signatory)


def _checked(validate, current: str, requested: str) -> None:
    """Run a suite's transition validator, mapping its InvalidTransitionError
    (each suite has its own class) onto a 409 ApprovalError."""
    try:
        validate(current, requested)
    except Exception as exc:  # noqa: BLE001 - only InvalidTransitionError is translated
        if exc.__class__.__name__ == "InvalidTransitionError":
            raise ApprovalError(str(exc), 409) from exc
        raise


# ── The single entry point both routes call ──────────────────────────────────

def perform_action(*, tenant, doc_type: str, audit_type: str, record: dict, data: dict,
                   performed_by: str, role: str, validate_transition, apply_update, add_trail,
                   bump_revision=urs_lifecycle.bump_revision, signoff_columns: dict | None = None,
                   effective_updates: dict | None = None, precheck=None,
                   reject_statuses: tuple | None = None, audit_id: int | None = None,
                   creator: dict) -> tuple[dict, int]:
    """Validate, authorize, e-sign and apply one approval action.

    `record` must already be the tenant-scoped row. Callbacks:
      validate_transition(current, requested)  -> raises on illegal move
      apply_update(updates: dict)              -> persist status/revision/etc.
      add_trail(action, comments, revision)    -> per-suite approval-trail row
      precheck(action, old, new)               -> optional; raise ApprovalError to
                                                  veto BEFORE any signature is consumed
    `reject_statuses` overrides the statuses a document may be rejected from.
    `creator` (required) is the record's stored creator identity (created_by_user_id /
    created_by_display_name / prepared_by): only the author may submit their own document.
    `audit_id` is the id the audit trail / e-signature rows are filed under when it
    differs from the sign-off record id (IQ/OQ/PQ file under their parent Qualification).
    Returns (response_body, http_status); raises ApprovalError otherwise.
    """
    record_id = record["id"]
    audit_rid = audit_id if audit_id is not None else record_id
    status = record["status"]
    revision = record.get("revision", "A") or "A"
    action = normalize_action(data.get("action", ""))
    comments = data.get("comments", "") or ""
    company_id = tenant.company_id

    all_rows = vadb.list_signoffs(company_id, doc_type, record_id, include_superseded=True)
    current_rows = [r for r in all_rows if r["status"] == "completed"]

    signatory = None
    new_status = status
    trail_action = action
    meaning_default, meaning_allowed = _MEANINGS.get(action, (None, None))

    if action == SUBMIT:
        _checked(validate_transition, status, UNDER_REVIEW)
        signatory = _BY_KEY["prepared_by"]
        _require_permission(tenant, signatory["permission"])
        if not creator_identity.is_author(creator, tenant.user_id, performed_by):
            audit.log_failure(audit_type, audit_rid, "Submission blocked — caller is not the document's author",
                              reason=f"user {tenant.user_id}")
            raise ApprovalError("Only the document's author can submit it for review", 403)
        dept = _authorize_signatory(tenant, signatory, current_rows)
        new_status = UNDER_REVIEW

    elif action == SIGN:
        _require_platform_role(tenant)  # authorize before revealing state (403 before 409)
        if status not in REVIEW_STATUSES:
            raise ApprovalError(f"Nothing to sign while the document is '{status}'", 409)
        pending = [s for s in signatories_for_stage(status) if s["key"] not in completed_keys(current_rows)]
        if not pending:  # a concurrent signer just completed the stage
            raise ApprovalError("Every designation for this stage has already signed", 409)
        requested = data.get("signatory")
        if requested:
            signatory = next((s for s in pending if s["key"] == requested), None)
            if signatory is None:
                raise ApprovalError(f"'{requested}' is not awaiting a signature at this stage", 409)
        elif len(pending) == 1:
            signatory = pending[0]
        else:
            raise ApprovalError(
                "Specify which designation you are signing as: "
                + ", ".join(s["key"] for s in pending), 400)
        dept = _authorize_signatory(tenant, signatory, current_rows)
        now_done = completed_keys(current_rows) | {signatory["key"]}
        stage_complete = all(s["key"] in now_done for s in signatories_for_stage(status))
        new_status = _NEXT_STATUS[status] if stage_complete else status
        if new_status != status:
            _checked(validate_transition, status, new_status)
        trail_action = "Approved" if status == FINAL_APPROVAL else f"{signatory['label']} Sign-Off"
        if status == FINAL_APPROVAL:
            meaning_default, meaning_allowed = "Approved", {"Approved", "Authorized"}
        else:
            meaning_default, meaning_allowed = "Reviewed", {"Reviewed", "Verified"}

    elif action == REJECT:
        _require_platform_role(tenant)
        if status not in (reject_statuses or REVIEW_STATUSES + (APPROVED, LEGACY_PENDING_APPROVAL)):
            raise ApprovalError(f"A '{status}' document cannot be rejected", 409)
        stage_sigs = signatories_for_stage(status)
        if not module_access.has_business_permission(tenant, "Validation", "Reject"):
            # A signer may decline their own stage.
            if not any(module_access.has_business_permission(tenant, "Validation", s["permission"])
                       for s in stage_sigs):
                raise ApprovalError("This action requires 'Reject' permission on 'Validation'", 403)
        if not (comments.strip() or (data.get("reason") or "").strip()):
            raise ApprovalError("A rejection reason is required", 400)
        _checked(validate_transition, status, DRAFT)
        new_status = DRAFT
        dept = ""

    elif action == MAKE_EFFECTIVE:
        _require_platform_role(tenant)
        _require_permission(tenant, "Approve")
        if status != APPROVED:
            raise ApprovalError("Only an Approved document can be made Effective", 409)
        if not effective_allowed(all_rows):
            missing = [s["label"] for s in SIGNATORIES if s["key"] not in completed_keys(current_rows)]
            raise ApprovalError(
                "Cannot become Effective until all mandatory approvals are complete. "
                "Missing: " + ", ".join(missing), 409)
        _checked(validate_transition, status, EFFECTIVE)
        new_status = EFFECTIVE
        dept = ""

    else:  # OBSOLETE_ACTION
        _require_platform_role(tenant)
        _require_permission(tenant, "Approve")
        _checked(validate_transition, status, OBSOLETE)
        new_status = OBSOLETE
        dept = ""

    if precheck:
        precheck(action, status, new_status)

    # ── e-signature (21 CFR Part 11): before anything is mutated ────────────
    meaning = data.get("meaning") or meaning_default or ""
    if meaning_allowed is not None and meaning not in meaning_allowed:
        raise ApprovalError(
            f"Signature meaning for '{action}' must be one of: {', '.join(sorted(meaning_allowed))}", 400)
    reason = data.get("reason", "")
    try:
        esignature_service.require_esignature(tenant, data.get("password", ""), meaning, reason)
    except esignature_service.ReauthenticationError as exc:
        audit.log_failure(audit_type, audit_rid, f"Approval action blocked ({action}) — e-signature failed",
                          reason=str(exc))
        raise ApprovalError(str(exc), 401)
    except esignature_service.ESignatureError as exc:
        audit.log_failure(audit_type, audit_rid, "E-signature rejected", reason=str(exc))
        raise ApprovalError(str(exc), 400)

    # ── apply ────────────────────────────────────────────────────────────────
    # The sign-off row is the claim: the database's unique indexes let exactly one
    # of several concurrent/repeated attempts through, before anything is mutated.
    claim = None
    if signatory:
        try:
            claim = vadb.add_signoff(
                company_id=company_id, doc_type=doc_type, record_id=record_id, revision=revision,
                signatory_key=signatory["key"], designation=signatory["designation"],
                signer_user_id=tenant.user_id, signer_name=performed_by, signer_role=role,
                signer_department=dept, meaning=meaning, reason=reason)
        except vadb.DuplicateSignoffError as dup:
            audit.log_failure(audit_type, audit_rid, f"Duplicate sign-off blocked ({action})",
                              reason=f"user {tenant.user_id}")
            raise ApprovalError(
                "Segregation of duties: you have already signed another designation on this document"
                if dup.same_signer else
                f"{signatory['label']} has already been signed (a concurrent or repeated request)", 409)
        if action == SIGN:
            # A concurrent signer of the same stage may have committed meanwhile:
            # decide stage completion from the ledger, not the pre-claim snapshot.
            done_now = completed_keys(vadb.list_signoffs(company_id, doc_type, record_id))
            stage_complete = all(s["key"] in done_now for s in signatories_for_stage(status))
            new_status = _NEXT_STATUS[status] if stage_complete else status

    updates: dict = {}
    try:
        if new_status != status:
            _checked(validate_transition, status, new_status)
            updates["status"] = new_status
        if action == REJECT and status in (APPROVED, EFFECTIVE):
            revision = bump_revision(revision)
            updates["revision"] = revision
        if action == MAKE_EFFECTIVE:
            updates.update(effective_updates or {"effective_date": date.today().isoformat()})
        if signatory and signoff_columns and signatory["key"] in signoff_columns:
            updates[signoff_columns[signatory["key"]]] = performed_by
        if updates:
            apply_update(updates)
    except BaseException:
        if claim:
            vadb.discard_unsigned_claim(claim["id"])  # nothing applied: release the claim
        raise
    if action == REJECT:
        # Only after the document really moved back to Draft: the cycle's
        # sign-offs are superseded (kept, never deleted).
        vadb.supersede_signoffs(company_id, doc_type, record_id, comments or reason)

    sig_row = esignature_service.record_signature(
        tenant=tenant, meaning=meaning, reason=reason, record_type=audit_type, record_id=audit_rid,
        version_number=revision, old_status=status, new_status=new_status,
        department=dept, approval_level=signatory["key"] if signatory else "")

    signoff = None
    if claim:
        sig_row = sig_row if isinstance(sig_row, dict) else {}
        vadb.attach_signature(claim["id"], sig_row.get("id"), sig_row.get("signature_hash", ""))
        signoff = dict(claim, esignature_id=sig_row.get("id"), signature_hash=sig_row.get("signature_hash", ""))

    entry = add_trail(trail_action, comments, revision)
    audit.log(audit_type, audit_rid, trail_action, old={"status": status}, new={"status": new_status},
              reason=comments or reason)

    body = dict(entry or {})
    body["new_status"] = new_status
    if signoff:
        body["signoff"] = signoff
    return body, 201


# ── Knowledge Base publication gate ──────────────────────────────────────────

def governed_doc_type(source_type: str, doc_type: str) -> str | None:
    """The sign-off ledger doc_type that governs a KB source, or None when the
    source is not under the standardized workflow (e.g. SOPs, validation
    reports)."""
    if source_type == "urs":
        return "URS"
    if source_type == "qualification_protocol":
        return doc_type if doc_type in ("IQ", "OQ", "PQ") else None
    if source_type == "document":
        return "DQ" if doc_type == "DQ" else None
    return None


def require_publishable(company_id: str, source_type: str, source_id: int, doc_type: str) -> None:
    """Raise ApprovalError unless every mandatory approval is complete. Called
    from kb_sync.publish_to_kb so no caller can publish a governed record to
    the Knowledge Base ahead of its approvals. A record approved under the
    pre-standard workflow (no ledger rows ever) remains publishable."""
    ledger_type = governed_doc_type(source_type, doc_type)
    if ledger_type is None:
        return
    rows = vadb.list_signoffs(company_id, ledger_type, source_id, include_superseded=True)
    if not effective_allowed(rows):
        raise ApprovalError(
            f"Knowledge Base publication blocked: mandatory approvals for {ledger_type} "
            f"#{source_id} are not complete", 409)

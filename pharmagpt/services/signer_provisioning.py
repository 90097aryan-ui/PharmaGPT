"""
services/signer_provisioning.py — authenticated, break-glass-gated, approval-verified provisioning of
Validation signer memberships (functional roles on user_departments), built on the supported
org_assignment.assign_user_to_department. Used by scripts/provision_validation_signers.py.

Fails CLOSED: any identity, authorization, approval or audit-attribution check that cannot be positively
verified refuses the run. Nothing is written unless `execute=True`.

  Identity      every party (actor, administrator approver, QA approver) presents a live Supabase access token that is
                verified with the app's own auth.context.resolve_tenant_context; no actor id is ever read from a file.
  Authorization the actor/administrator must be the tenant's company_admin, or a super_admin holding an ACTIVE
                break_glass_access grant for this company (the platform's existing "Assume Company Context" rule —
                no grant, no run; the grant id is written into every audit entry).
  Approvals     file must name the exact change set (SHA-256 bound), be fresh, carry references, and each approver
                pseudonym must equal the authenticated approver. Independent QA is MANDATORY here: the QA approver is
                an authenticated tenant user holding a QA authority RBAC role, different from the actor and the
                administrator approver, and not one of the people being changed. Relaxing that is a reviewed code
                change, not a switch (same rule as separation of duties in validation_approval.py).
  Attribution   audit entries are written with the authenticated actor id and the approval references; after each
                change the membership AND that exact audit entry are re-read and verified.
  Atomicity     PostgREST has no multi-statement transaction: a failure after some changes automatically rolls the
                applied ones back (each rollback is audited too). A saved rollback file also supports `--rollback`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from pharmagpt.auth.context import resolve_tenant_context
from pharmagpt.auth.middleware import _grant_is_active
from pharmagpt.db import rbac_repo
from pharmagpt.services import org_assignment

# designation -> (department_code, functional_role, RBAC role that justifies the mapping)
APPROVED_MAP = {
    "prepared_by":         ("VALIDATION", "Initiator", "Validation Initiator"),
    "reviewed_by_eng":     ("ENGINEERING", "Reviewer", "Engineering Reviewer"),
    "reviewed_by_prod":    ("PRODUCTION", "Reviewer", "Production Reviewer"),
    "engineering_manager": ("ENGINEERING", "Approver", "Engineering Approver"),
    "production_manager":  ("PRODUCTION", "Approver", "Production Approver"),
    "qa_manager":          ("QA", "Approver", "QA Approver"),
    "validation_manager":  ("VALIDATION", "Approver", "Validation Approver"),
    "final_approval":      ("PLANT_HEAD", "Plant Head", "Plant Head / Approver"),
}
QA_AUTHORITY_ROLES = ("QA Approver", "QA Coordinator/Admin")
MAX_APPROVAL_AGE_DAYS = 30


class ProvisioningError(Exception):
    pass


def pseudonym(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:6]


def change_set_hash(company_id: str, reviewer_choice: str, changes: list[dict]) -> str:
    canon = json.dumps({"company_id": company_id, "reviewer_choice": (reviewer_choice or "").upper(),
                        "changes": sorted([c["designation"], c["pseudonym"]] for c in changes)}, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


# ── approval record (structure, binding, freshness) ──────────────────────────

def _approval_entry(a, who):
    if not isinstance(a, dict) or not (a.get("approver_pseudonym") and a.get("date") and a.get("reference")):
        raise ProvisioningError(f"written approval missing or incomplete: {who} (approver_pseudonym, date, reference)")
    try:
        d = date.fromisoformat(a["date"])
    except (TypeError, ValueError):
        raise ProvisioningError(f"approval date for {who} is not YYYY-MM-DD") from None
    today = datetime.now(timezone.utc).date()
    if d > today or today - d > timedelta(days=MAX_APPROVAL_AGE_DAYS):
        raise ProvisioningError(f"approval for {who} is dated in the future or older than {MAX_APPROVAL_AGE_DAYS} days")
    return a


def validate_approval(rec: dict, company_id: str) -> list[dict]:
    """Return the normalized change list, or raise ProvisioningError. Approval is never inferred."""
    if not isinstance(rec, dict):
        raise ProvisioningError("approval record must be an object")
    if rec.get("company_id") != company_id:
        raise ProvisioningError("approval record is for a different company")
    for who in ("administrator", "qa"):
        _approval_entry((rec.get("approvals") or {}).get(who), who)
        _approval_entry((rec.get("plant_head_additional_approvals") or {}).get(who), f"plant-head {who}")
    choice = (rec.get("reviewer_choice") or "").upper()
    if choice not in ("ENGINEERING", "PRODUCTION"):
        raise ProvisioningError("QA reviewer_choice must be ENGINEERING or PRODUCTION")
    wanted = {"prepared_by", "engineering_manager", "production_manager", "qa_manager",
              "validation_manager", "final_approval",
              "reviewed_by_eng" if choice == "ENGINEERING" else "reviewed_by_prod"}
    changes = rec.get("changes") or []
    got = {c.get("designation") for c in changes}
    if got != wanted or len(changes) != len(wanted):
        raise ProvisioningError(f"changes must be exactly the approved set {sorted(wanted)}; got {sorted(map(str, got))}")
    out = []
    for c in changes:
        dept, role, rbac_name = APPROVED_MAP[c["designation"]]
        if not c.get("pseudonym"):
            raise ProvisioningError(f"pseudonym missing for {c['designation']}")
        out.append({"designation": c["designation"], "pseudonym": c["pseudonym"], "department_code": dept,
                    "functional_role": role, "rbac_role": rbac_name})
    if len({c["pseudonym"] for c in out}) != len(out):
        raise ProvisioningError("each designation must be a different user (separation of duties)")
    if rec.get("change_set_sha256") != change_set_hash(company_id, choice, out):
        raise ProvisioningError("approval is not bound to this exact change set (change_set_sha256 mismatch)")
    return out


# ── identity and authorization (fail closed) ─────────────────────────────────

def authenticate(access_token: str, label: str):
    """Verify a live Supabase access token exactly as the application does."""
    if not (access_token or "").strip():
        raise ProvisioningError(f"{label}: no access token supplied")
    try:
        return resolve_tenant_context(access_token.strip())
    except Exception:  # noqa: BLE001 - any failure to prove identity refuses the run
        raise ProvisioningError(f"{label}: identity could not be verified (invalid/expired token or inactive account)") from None


def authorize_administrator(client, tenant, company_id: str, label: str) -> str | None:
    """company_admin of this company, or super_admin with an active break-glass grant for it.
    Returns the break-glass grant id (None for company_admin)."""
    if tenant.role == "company_admin" and tenant.company_id == company_id:
        return None
    if tenant.role != "super_admin":
        raise ProvisioningError(f"{label}: must be this company's company_admin or a super_admin with an active break-glass grant")
    try:
        grants = (client.table("break_glass_access").select("id, expires_at, revoked_at")
                  .eq("super_admin_user_id", tenant.user_id).eq("company_id", company_id).execute().data) or []
    except Exception:  # noqa: BLE001
        raise ProvisioningError(f"{label}: break-glass grant could not be verified") from None
    active = [g for g in grants if _grant_is_active(g)]
    if not active:
        raise ProvisioningError(f"{label}: no active break-glass (Assume Company Context) grant for this company — "
                                "open one with a reason first")
    return sorted(active, key=lambda g: g["expires_at"])[-1]["id"]


def _held_rbac_roles(client, user_id: str, company_id: str) -> set[str]:
    roles = {r["id"]: r["name"] for r in rbac_repo.list_roles(client, company_id) if r.get("company_id") == company_id}
    rows = (client.table("rbac_user_roles").select("role_id").eq("user_id", user_id)
            .eq("company_id", company_id).execute().data) or []
    return {roles.get(r["role_id"]) for r in rows}


def authorize_qa_approver(client, tenant, company_id: str) -> None:
    if tenant.role == "super_admin" or tenant.company_id != company_id:
        raise ProvisioningError("QA approver must be an authenticated user of this company")
    if not (_held_rbac_roles(client, tenant.user_id, company_id) & set(QA_AUTHORITY_ROLES)):
        raise ProvisioningError(f"QA approver must hold a QA authority role ({' / '.join(QA_AUTHORITY_ROLES)})")


def establish_authority(client, company_id: str, rec: dict, *, actor_token, admin_token, qa_token) -> dict:
    """Authenticate and authorize all three parties and check the approvals name exactly them."""
    actor = authenticate(actor_token, "actor")
    grant_id = authorize_administrator(client, actor, company_id, "actor")
    admin = actor if not (admin_token or "").strip() else authenticate(admin_token, "administrator approver")
    if admin.user_id != actor.user_id:
        authorize_administrator(client, admin, company_id, "administrator approver")
    qa = authenticate(qa_token, "QA approver")
    authorize_qa_approver(client, qa, company_id)
    if qa.user_id in (actor.user_id, admin.user_id):
        raise ProvisioningError("independent QA authorization is mandatory: the QA approver must differ from the actor and the administrator approver")
    for section in ("approvals", "plant_head_additional_approvals"):
        for who, party in (("administrator", admin), ("qa", qa)):
            if rec[section][who]["approver_pseudonym"] != pseudonym(party.user_id):
                raise ProvisioningError(f"{section}.{who}: approver does not match the authenticated {who} approver")
    return {"actor": actor, "admin": admin, "qa": qa, "grant_id": grant_id}


# ── plan (read-only) ─────────────────────────────────────────────────────────

def _one(rows, what):
    if len(rows) != 1:
        raise ProvisioningError(f"{what}: expected exactly 1 match, found {len(rows)}")
    return rows[0]


def plan(client, company_id: str, changes: list[dict], parties: dict | None = None) -> list[dict]:
    """Resolve and verify every change against the live directory. Nobody approving or acting may be one of the
    people being changed (no self-approval of one's own signing authority)."""
    users = (client.table("users").select("id, status").eq("company_id", company_id).execute().data) or []
    by_ps = {}
    for u in users:
        by_ps.setdefault(pseudonym(u["id"]), []).append(u)
    roles = {r["id"]: r["name"] for r in rbac_repo.list_roles(client, company_id) if r.get("company_id") == company_id}
    depts = {d["department_code"]: d["id"] for d in
             (client.table("departments").select("id, department_code").eq("company_id", company_id).execute().data or [])}
    wroles = {w["name"]: w["id"] for w in (client.table("workflow_roles").select("id, name").execute().data or [])}
    party_ids = {p.user_id for k, p in (parties or {}).items() if k in ("actor", "admin", "qa")}
    steps = []
    for c in changes:
        u = _one(by_ps.get(c["pseudonym"], []), f"user {c['pseudonym']}")
        if u.get("status") != "active":
            raise ProvisioningError(f"user {c['pseudonym']} is not active")
        if u["id"] in party_ids:
            raise ProvisioningError(f"user {c['pseudonym']} is being changed and cannot also act or approve (self-approval)")
        held = {roles.get(r["role_id"]) for r in (client.table("rbac_user_roles").select("role_id")
                                                    .eq("user_id", u["id"]).eq("company_id", company_id).execute().data or [])}
        if c["rbac_role"] not in held:
            raise ProvisioningError(f"user {c['pseudonym']} does not hold RBAC role '{c['rbac_role']}' (mapping unsupported)")
        if c["department_code"] not in depts or c["functional_role"] not in wroles:
            raise ProvisioningError(f"department/functional role missing in directory for {c['designation']}")
        existing = (client.table("user_departments").select("id, workflow_role_id, is_primary")
                    .eq("user_id", u["id"]).eq("department_id", depts[c["department_code"]]).execute().data or [])
        before = existing[0] if existing else None
        if before and before["workflow_role_id"] not in (None, wroles[c["functional_role"]]):
            raise ProvisioningError(f"{c['pseudonym']}: membership already has a different functional role — not overwriting")
        steps.append({**c, "user_id": u["id"], "department_id": depts[c["department_code"]],
                      "workflow_role_id": wroles[c["functional_role"]], "before": before,
                      "is_primary": bool(before["is_primary"]) if before else False,
                      "action": "UPDATE" if before else "INSERT"})
    return steps


# ── execute / rollback (audited, attributed, verified) ───────────────────────

def _reason(step: dict, ctx: dict, rec: dict, what: str) -> str:
    a, q = rec["approvals"]["administrator"], rec["approvals"]["qa"]
    return (f"{what} ({step['designation']}); admin approval {a['reference']} by {a['approver_pseudonym']}; "
            f"independent QA approval {q['reference']} by {q['approver_pseudonym']}; "
            f"break-glass {ctx.get('grant_id') or 'n/a (company_admin)'}")


def _verify_audit(client, actor_id: str, step: dict, reason: str) -> bool:
    rows = (client.table("rbac_audit_log").select("actor_user_id, reason")
            .eq("target_user_id", step["user_id"]).eq("department_id", step["department_id"]).execute().data) or []
    return any(r.get("actor_user_id") == actor_id and (r.get("reason") or "").endswith(reason) for r in rows)


def rollback(client, company_id: str, applied: list[dict], ctx: dict, rec: dict) -> list[str]:
    """Undo applied steps in reverse order; each undo is audited. Returns problems (empty = ok)."""
    problems = []
    actor_id = ctx["actor"].user_id
    for s in reversed(applied):
        try:
            if s["before"] is None:
                client.table("user_departments").delete().eq("user_id", s["user_id"]).eq("department_id", s["department_id"]).execute()
            else:
                client.table("user_departments").update({"workflow_role_id": s["before"]["workflow_role_id"]}) \
                    .eq("user_id", s["user_id"]).eq("department_id", s["department_id"]).execute()
            rbac_repo.add_rbac_audit_entry(
                client, company_id=company_id, actor_user_id=actor_id, target_user_id=s["user_id"],
                department_id=s["department_id"], reason=_reason(s, ctx, rec, "ROLLBACK of validation signer provisioning"),
                old_value={"functional_role": s["functional_role"]},
                new_value={"workflow_role_id": (s["before"] or {}).get("workflow_role_id")})
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{s['designation']}: rollback failed ({type(exc).__name__})")
    return problems


def execute(client, company_id: str, steps: list[dict], ctx: dict, rec: dict) -> list[dict]:
    actor_id = ctx["actor"].user_id
    applied, results = [], []
    for s in steps:
        reason = _reason(s, ctx, rec, "Validation signer provisioning")
        try:
            applied.append(s)  # counted as applied before the call: the function compensates itself, rollback is idempotent
            res = org_assignment.assign_user_to_department(
                client, user_id=s["user_id"], company_id=company_id, department_id=s["department_id"],
                department_code=s["department_code"], workflow_role_id=s["workflow_role_id"],
                functional_role_name=s["functional_role"], is_primary=s["is_primary"], actor_user_id=actor_id,
                reason=reason)
            row = (client.table("user_departments").select("workflow_role_id, is_primary")
                   .eq("user_id", s["user_id"]).eq("department_id", s["department_id"]).execute().data or [None])[0]
            ok = bool(row) and row["workflow_role_id"] == s["workflow_role_id"] \
                and bool(row.get("is_primary", False)) == s["is_primary"] and _verify_audit(client, actor_id, s, reason)
            if not ok:
                raise ProvisioningError(f"post-change verification failed for {s['designation']}")
        except Exception as exc:  # noqa: BLE001 - undo everything applied so far, then stop
            problems = rollback(client, company_id, applied[:-1], ctx, rec)
            # the failing step itself was already compensated by assign_user_to_department, or verification failed
            # after it was applied: undo it too if its membership still carries the new role
            row = (client.table("user_departments").select("workflow_role_id")
                   .eq("user_id", s["user_id"]).eq("department_id", s["department_id"]).execute().data or [None])[0]
            if row and row["workflow_role_id"] == s["workflow_role_id"]:
                problems += rollback(client, company_id, [s], ctx, rec)
            msg = f"{s['designation']}: {exc}" if isinstance(exc, ProvisioningError) else f"{s['designation']}: {type(exc).__name__}"
            raise ProvisioningError(f"{msg}; applied changes were rolled back"
                                    + (f" WITH PROBLEMS: {problems}" if problems else "")) from None
        results.append({"designation": s["designation"], "pseudonym": s["pseudonym"], "action": s["action"],
                        "verified": True, "membership_id": (res.get("membership") or {}).get("id")})
    return results


def steps_for_rollback_file(steps: list[dict]) -> list[dict]:
    """What the rollback file must hold to undo a run later (identifiers only, no personal data)."""
    return [{k: s[k] for k in ("designation", "pseudonym", "user_id", "department_id", "department_code",
                               "functional_role", "action", "before")} for s in steps]

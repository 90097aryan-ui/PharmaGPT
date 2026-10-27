"""
services/signer_provisioning.py — approval-gated provisioning of Validation signer
memberships (functional roles on user_departments), built on the supported
org_assignment.assign_user_to_department. Used by scripts/provision_validation_signers.py.

Safety properties:
  - nothing is written unless `execute=True` AND a complete written-approval record is present;
  - the change set is exactly the approved minimum (7 designations); the QA Coordinator mapping,
    unknown designations, extra rows and new users are rejected;
  - users are resolved from pseudonyms (first 6 hex of SHA-256 of the user id) inside the company
    and must hold the RBAC role that justifies the mapping — no personal data is stored or printed;
  - original membership rows (id, workflow_role_id, is_primary) are captured before any write and
    is_primary is passed back unchanged (False for a brand-new row);
  - after each change the membership and its audit row are re-read and verified.
"""

from __future__ import annotations

import hashlib

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
REQUIRED_APPROVERS = ("administrator", "qa_head")
PLANT_HEAD_APPROVERS = ("administrator", "qa_head")


class ProvisioningError(Exception):
    pass


def pseudonym(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:6]


def validate_approval(rec: dict) -> list[dict]:
    """Return the normalized change list, or raise ProvisioningError. Approval is never inferred."""
    if not isinstance(rec, dict):
        raise ProvisioningError("approval record must be an object")
    for who in REQUIRED_APPROVERS:
        a = (rec.get("approvals") or {}).get(who) or {}
        if not (a.get("approver_ref") and a.get("date") and a.get("reference")):
            raise ProvisioningError(f"written approval missing: {who} (approver_ref, date, reference)")
    ph = (rec.get("plant_head_additional_approvals") or {})
    for who in PLANT_HEAD_APPROVERS:
        a = ph.get(who) or {}
        if not (a.get("approver_ref") and a.get("date") and a.get("reference")):
            raise ProvisioningError(f"additional Plant Head membership approval missing: {who}")
    choice = (rec.get("reviewer_choice") or "").upper()
    if choice not in ("ENGINEERING", "PRODUCTION"):
        raise ProvisioningError("QA reviewer_choice must be ENGINEERING or PRODUCTION")
    if not rec.get("actor_pseudonym"):
        raise ProvisioningError("actor_pseudonym (the approving company administrator) is required")
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
    return out


def _one(rows, what):
    if len(rows) != 1:
        raise ProvisioningError(f"{what}: expected exactly 1 match, found {len(rows)}")
    return rows[0]


def plan(client, company_id: str, changes: list[dict], actor_pseudonym: str) -> list[dict]:
    """Read-only: resolve and verify every change against the live directory."""
    users = (client.table("users").select("id, status").eq("company_id", company_id).execute().data) or []
    by_ps = {}
    for u in users:
        by_ps.setdefault(pseudonym(u["id"]), []).append(u)
    actor = _one(by_ps.get(actor_pseudonym, []), "actor")
    roles = {r["id"]: r["name"] for r in rbac_repo.list_roles(client, company_id) if r.get("company_id") == company_id}
    depts = {d["department_code"]: d["id"] for d in
             (client.table("departments").select("id, department_code").eq("company_id", company_id).execute().data or [])}
    wroles = {w["name"]: w["id"] for w in (client.table("workflow_roles").select("id, name").execute().data or [])}
    steps = []
    for c in changes:
        u = _one(by_ps.get(c["pseudonym"], []), f"user {c['pseudonym']}")
        if u.get("status") != "active":
            raise ProvisioningError(f"user {c['pseudonym']} is not active")
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
    steps.append({"actor_user_id": actor["id"]})
    return steps


def execute(client, company_id: str, steps: list[dict], approval_reference: str) -> list[dict]:
    actor_id = steps[-1]["actor_user_id"]
    results = []
    for s in steps[:-1]:
        res = org_assignment.assign_user_to_department(
            client, user_id=s["user_id"], company_id=company_id, department_id=s["department_id"],
            department_code=s["department_code"], workflow_role_id=s["workflow_role_id"],
            functional_role_name=s["functional_role"], is_primary=s["is_primary"], actor_user_id=actor_id,
            reason=f"Validation signer provisioning ({s['designation']}); approval ref {approval_reference}")
        row = (client.table("user_departments").select("workflow_role_id, is_primary")
               .eq("user_id", s["user_id"]).eq("department_id", s["department_id"]).execute().data or [None])[0]
        audit = (client.table("rbac_audit_log").select("id").eq("target_user_id", s["user_id"])
                 .eq("department_id", s["department_id"]).execute().data or [])
        ok = bool(row) and row["workflow_role_id"] == s["workflow_role_id"] and bool(row.get("is_primary", False)) == s["is_primary"] \
            and len(audit) >= 1
        results.append({"designation": s["designation"], "pseudonym": s["pseudonym"], "action": s["action"],
                        "verified": ok, "membership_id": (res.get("membership") or {}).get("id"),
                        "before": s["before"]})
        if not ok:
            raise ProvisioningError(f"post-change verification failed for {s['designation']} — stopping; "
                                    f"originals recorded for rollback")
    return results

"""
scripts/seed_nutra_demo.py — Seed the "Nutra" demo tenant for end-to-end
PharmaGPT testing: one company, 7 departments, and 23 users spanning every
department/workflow-role/module-permission combination described in
NUTRA_DEMO_DATA.md.

Demo seed data only — no application/RBAC/Workflow Engine logic lives here.
Builds on migration 0014's organizational-model tables (departments,
workflow_roles, user_departments, modules, user_module_permissions) via
pharmagpt/services/org_directory.py and pharmagpt/services/module_permissions.py,
and on pharmagpt/services/identity_admin.py::provision_user for identity
creation — the same Supabase Admin API path used by every other
identity-provisioning code path in this app (routes/companies.py,
routes/users.py). Mirrors scripts/bootstrap_super_admin.py's shape:
load .env, build a service-role client, idempotent lookup-before-write.

Usage:
    python scripts/seed_nutra_demo.py
    python scripts/seed_nutra_demo.py --reset   # remove Nutra demo users/departments, then reseed

Reads from .env:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

Idempotent and safe to rerun: existing users are found by email (via
find_auth_user_by_email, reused from scripts.bootstrap_super_admin) and have
their role/department/module-permission data brought in line with this
script's spec, never duplicated. Existing users' passwords are never reset
on rerun — the fixed password below is only ever set at first creation.

--reset removes only the 23 known Nutra demo emails' identities and Nutra's
departments (never the `companies` row itself, and never any other
tenant's data), then falls through to the normal seed flow so the tenant
is immediately usable again.
"""

from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv
from supabase import Client, create_client

from pharmagpt.services.identity_admin import IdentityProvisioningError, provision_user
from pharmagpt.services.module_permissions import set_module_permission
from pharmagpt.services.org_directory import (
    find_or_create_department,
    get_workflow_role_id,
    set_primary_department,
)
from scripts.bootstrap_super_admin import find_auth_user_by_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMPANY_LEGAL_NAME = "Nutra"
COMPANY_INDUSTRY_SEGMENT = "nutraceutical"
DEMO_PASSWORD = "Qazwsx@123"

REQUIRED_ENV_VARS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")

# (display name, stable code) — code is the idempotency key; name may change.
DEPARTMENTS = [
    ("Quality Assurance", "QA"),
    ("Production", "PROD"),
    ("Warehouse", "WH"),
    ("PPIC", "PPIC"),
    ("Engineering", "ENG"),
    ("Quality Control", "QC"),
    ("Validation", "VAL"),
]

MODULE_CODES = ("QMS", "VALIDATION", "DOCUMENT_GENERATOR")

# workflow_roles.name -> roles.name (the frozen platform RBAC role, migration
# 0001). Likely, not Confirmed — see NUTRA_DEMO_DATA.md's role-mapping
# rationale: Initiator matches 'user' ("authors and edits documents");
# everything else (Coordinator/Reviewer/Approver/Plant Head) matches
# 'reviewer_qa' ("reviews and approves/rejects documents"). Nobody maps to
# 'company_admin' — that grants platform tenant-owner powers (managing
# Users/Settings/KB/Equipment/Projects) no demo persona here needs.
WORKFLOW_ROLE_TO_PLATFORM_ROLE_NAME = {
    "Initiator": "user",
    "Coordinator": "reviewer_qa",
    "Reviewer": "reviewer_qa",
    "Approver": "reviewer_qa",
    "Plant Head": "reviewer_qa",
}

# (email, display_name, department_code_or_None, workflow_role, qms, validation, document_generator)
NUTRA_USERS: list[tuple[str, str, str | None, str, bool, bool, bool]] = [
    ("c@nutra.com", "Coordinator", "QA", "Coordinator", True, True, True),
    ("qr@nutra.com", "Quality Reviewer", "QA", "Reviewer", True, True, True),
    ("qh@nutra.com", "Quality Head", "QA", "Approver", True, True, True),
    ("qi@nutra.com", "Quality Initiator", "QA", "Initiator", True, False, True),
    ("pi@nutra.com", "Production Initiator", "PROD", "Initiator", True, False, True),
    ("pr@nutra.com", "Production Reviewer", "PROD", "Reviewer", True, True, True),
    ("ph@nutra.com", "Production Head", "PROD", "Approver", True, True, True),
    ("wi@nutra.com", "Warehouse Initiator", "WH", "Initiator", True, False, True),
    ("wr@nutra.com", "Warehouse Reviewer", "WH", "Reviewer", True, True, True),
    ("wh@nutra.com", "Warehouse Head", "WH", "Approver", True, True, True),
    ("ppi@nutra.com", "PPIC Initiator", "PPIC", "Initiator", True, False, True),
    ("ppr@nutra.com", "PPIC Reviewer", "PPIC", "Reviewer", True, False, True),
    ("pph@nutra.com", "PPIC Head", "PPIC", "Approver", True, False, True),
    ("ei@nutra.com", "Engineering Initiator", "ENG", "Initiator", True, False, True),
    ("er@nutra.com", "Engineering Reviewer", "ENG", "Reviewer", True, True, True),
    ("eh@nutra.com", "Engineering Head", "ENG", "Approver", True, True, True),
    ("qci@nutra.com", "QC Initiator", "QC", "Initiator", True, False, True),
    ("qcr@nutra.com", "QC Reviewer", "QC", "Reviewer", True, True, True),
    ("qch@nutra.com", "QC Head", "QC", "Approver", True, True, True),
    ("vi@nutra.com", "Validation Initiator", "VAL", "Initiator", True, True, True),
    ("vr@nutra.com", "Validation Reviewer", "VAL", "Reviewer", True, True, True),
    ("vh@nutra.com", "Validation Head", "VAL", "Approver", True, True, True),
    ("plh@nutra.com", "Plant Head", None, "Plant Head", True, True, True),
]


class SeedError(Exception):
    """Raised for any condition that should stop the seed script."""


def load_config(env: dict) -> dict:
    config = {name: env.get(name) for name in REQUIRED_ENV_VARS}
    missing = [name for name in REQUIRED_ENV_VARS if not config[name]]
    if missing:
        raise SeedError("Missing required .env values: " + ", ".join(missing))
    return config


def build_service_role_client(supabase_url: str, service_role_key: str) -> Client:
    return create_client(supabase_url, service_role_key)


def get_role_id(client: Client, role_name: str) -> int:
    result = client.table("roles").select("id").eq("name", role_name).maybe_single().execute()
    row = result.data if result else None
    if not row:
        raise SeedError(
            f"No '{role_name}' row in roles table — has migrations/0001_identity_tenancy_up.sql been applied?"
        )
    return row["id"]


def find_or_create_company(client: Client) -> dict:
    """Idempotent lookup by legal_name. If more than one row somehow
    matches (no unique constraint on legal_name), the earliest by
    created_at is used and no duplicate is ever inserted."""
    result = (
        client.table("companies")
        .select("id, legal_name, industry_segment")
        .eq("legal_name", COMPANY_LEGAL_NAME)
        .order("created_at")
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if rows:
        return rows[0]

    inserted = (
        client.table("companies")
        .insert({"legal_name": COMPANY_LEGAL_NAME, "industry_segment": COMPANY_INDUSTRY_SEGMENT})
        .execute()
    )
    return inserted.data[0]


def ensure_user_profile(client: Client, auth_user_id: str, company_id: str, role_id: int,
                         display_name: str, workflow_role_id: int) -> dict:
    """Insert the `users` profile row if missing (resume-after-partial-
    failure, same shape as bootstrap_super_admin.py); otherwise bring an
    existing row's role/display_name/status/workflow_role_id in line with
    this script's spec without duplicating anything."""
    existing = (
        client.table("users")
        .select("id, role_id, display_name, status, workflow_role_id")
        .eq("id", auth_user_id)
        .maybe_single()
        .execute()
    )
    row = existing.data if existing else None

    if row is None:
        inserted = (
            client.table("users")
            .insert({
                "id": auth_user_id, "company_id": company_id, "role_id": role_id,
                "display_name": display_name, "status": "active",
                "workflow_role_id": workflow_role_id,
            })
            .execute()
        )
        return inserted.data[0]

    updates = {}
    if row.get("role_id") != role_id:
        updates["role_id"] = role_id
    if row.get("display_name") != display_name:
        updates["display_name"] = display_name
    if row.get("status") != "active":
        updates["status"] = "active"
    if row.get("workflow_role_id") != workflow_role_id:
        updates["workflow_role_id"] = workflow_role_id

    if not updates:
        return row
    updated = client.table("users").update(updates).eq("id", auth_user_id).execute()
    return updated.data[0]


def write_seed_audit_entry(client: Client, company_id: str, record_id: str, action: str, reason: str = "") -> None:
    """Best-effort audit entry, written directly via the already-open
    service-role client (a standalone script has no bearer token, so
    pharmagpt/db/qms_repo.py::add_audit_entry — which requires one — cannot
    be reused here). Never raises."""
    try:
        client.table("audit_trail").insert({
            "company_id": company_id,
            "actor_user_id": None,
            "action": action,
            "record_type": "user",
            "record_id": str(record_id),
            "reason": reason or None,
        }).execute()
    except Exception:
        logger.exception("seed_nutra_demo: failed to write audit entry (%s) for %s", action, record_id)


def seed_one_user(client: Client, company_id: str, department_ids: dict[str, str],
                   workflow_role_ids: dict[str, int], spec: tuple) -> dict:
    email, display_name, department_code, workflow_role_name, qms, validation, doc_gen = spec

    platform_role_name = WORKFLOW_ROLE_TO_PLATFORM_ROLE_NAME[workflow_role_name]
    role_id = get_role_id(client, platform_role_name)
    workflow_role_id = workflow_role_ids[workflow_role_name]

    auth_user = find_auth_user_by_email(client, email)
    if auth_user is None:
        try:
            provisioned = provision_user(
                email=email, display_name=display_name, company_id=company_id,
                role_id=role_id, password=DEMO_PASSWORD,
            )
        except IdentityProvisioningError as exc:
            raise SeedError(f"Could not provision {email}: {exc}") from exc
        auth_user_id = provisioned["auth_user_id"]
        status = "created"
    else:
        auth_user_id = auth_user.id
        status = "existing"

    ensure_user_profile(client, auth_user_id, company_id, role_id, display_name, workflow_role_id)

    if department_code is not None:
        set_primary_department(client, auth_user_id, company_id, department_ids[department_code])

    for code, enabled in (("QMS", qms), ("VALIDATION", validation), ("DOCUMENT_GENERATOR", doc_gen)):
        set_module_permission(client, auth_user_id, company_id, code, enabled)

    write_seed_audit_entry(client, company_id, auth_user_id, f"Nutra demo user {status}", reason=email)

    return {"email": email, "status": status}


def seed_nutra_demo(client: Client) -> dict:
    """Run the full idempotent seed. Returns a summary dict."""
    company = find_or_create_company(client)
    company_id = company["id"]

    department_ids: dict[str, str] = {}
    for name, code in DEPARTMENTS:
        department = find_or_create_department(client, company_id, name, code)
        department_ids[code] = department["id"]

    workflow_role_ids: dict[str, int] = {}
    for name in WORKFLOW_ROLE_TO_PLATFORM_ROLE_NAME:
        role_id = get_workflow_role_id(client, name)
        if role_id is None:
            raise SeedError(
                f"No 'workflow_roles' row for {name!r} — has migrations/0014_nutra_demo_schema_up.sql been applied?"
            )
        workflow_role_ids[name] = role_id

    created, existing = [], []
    for spec in NUTRA_USERS:
        result = seed_one_user(client, company_id, department_ids, workflow_role_ids, spec)
        (created if result["status"] == "created" else existing).append(result["email"])

    return {
        "company_id": company_id,
        "created": created,
        "existing": existing,
        "departments": [code for _, code in DEPARTMENTS],
    }


def reset_nutra_demo(client: Client) -> dict:
    """Remove only Nutra's demo users and departments — never the
    `companies` row itself, and never any other tenant's data. Each
    identity deletion is isolated in its own try/except: a real audit_trail
    entry authored by a demo user has no ON DELETE clause on
    audit_trail.actor_user_id (migrations/0004_core_schema_up.sql), so
    delete_user() could hit an FK-restrict error for that one user — this
    must be reported, not allowed to abort the whole reset."""
    company = find_or_create_company(client)
    company_id = company["id"]

    deleted, failed = [], []
    for spec in NUTRA_USERS:
        email = spec[0]
        auth_user = find_auth_user_by_email(client, email)
        if auth_user is None:
            continue
        try:
            client.auth.admin.delete_user(auth_user.id)
            deleted.append(email)
        except Exception as exc:
            logger.exception("reset_nutra_demo: failed to delete %s", email)
            failed.append((email, str(exc)))

    try:
        client.table("departments").delete().eq("company_id", company_id).execute()
    except Exception:
        logger.exception("reset_nutra_demo: failed to delete departments for company %s", company_id)

    return {"company_id": company_id, "deleted": deleted, "failed": failed}


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Seed the Nutra demo tenant.")
    parser.add_argument(
        "--reset", action="store_true",
        help="Remove Nutra's existing demo users and departments before reseeding.",
    )
    args = parser.parse_args()

    import os

    try:
        config = load_config(os.environ)
        client = build_service_role_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])

        if args.reset:
            reset_result = reset_nutra_demo(client)
            print(f"Reset: {len(reset_result['deleted'])} user(s) removed", end="")
            if reset_result["failed"]:
                print(f", {len(reset_result['failed'])} failed:")
                for email, error in reset_result["failed"]:
                    print(f"  ! could not delete {email}: {error}", file=sys.stderr)
            else:
                print()

        result = seed_nutra_demo(client)
    except SeedError as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1

    print(f"✔ Company: {COMPANY_LEGAL_NAME} (id={result['company_id']})")
    print(f"✔ Departments: {', '.join(result['departments'])}")
    print(f"✔ {len(result['created'])} users created")
    print(f"✔ {len(result['existing'])} users already existed")
    print("✔ Departments, workflow roles, and module permissions assigned")
    print(f"Password for newly created accounts: {DEMO_PASSWORD}")
    print("Existing users' passwords were not modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
pharmagpt/db/projects_repo.py — Postgres CRUD for the `projects` table.

Phase 3.2 (docs/PHASE3_EXECUTION_PLAN.md). Not the source of truth yet — see
config.PROJECTS_BACKEND. Every function acts as the caller's own
authenticated Supabase client (get_authenticated_client), never the
service-role key, matching the convention scripts/bootstrap_super_admin.py
established: service-role is CLI-script-only, request-handling code always
acts as the authenticated user so RLS (migrations/0005) enforces tenant
isolation the same way it does everywhere else.

Only fields with a home in DATABASE_ARCHITECTURE.md §4.2's `projects` table
are written here. equipment_name/manufacturer/department/validation_type/
model/location have no column in the target schema (that data's home is the
Equipment Library, Phase 3.4) and are intentionally not synced.
owner/approver are free text in SQLite today, but the target schema's
owner_user_id/approver_user_id are real `users` references — there is no
safe automatic mapping from a free-text name to a user id, so both are left
NULL here; resolving that is Phase 7 (Project Workspace) territory.

This module raises on failure. Callers doing best-effort dual-write are
responsible for catching and logging (see routes/projects.py) — keeping
that "never blocks the SQLite write" policy visible at the call site
instead of hidden in here.
"""

from pharmagpt.services.supabase_client import get_authenticated_client

TABLE = "projects"


def create_project(access_token: str, company_id: str, *, name: str,
                    status: str = "active", target_date: str | None = None,
                    risk_category: str = "", protocol_number: str = "",
                    report_number: str = "") -> dict:
    """Insert one row into Postgres `projects`. Returns the inserted row."""
    client = get_authenticated_client(access_token)
    payload = {
        "company_id": company_id,
        "name": name,
        "status": status or "active",
        "target_date": target_date or None,
        "risk_category": risk_category or None,
        "protocol_number": protocol_number or None,
        "report_number": report_number or None,
    }
    result = client.table(TABLE).insert(payload).execute()
    return result.data[0]


def update_project(access_token: str, company_id: str, postgres_id: str, *,
                    name: str, status: str = "active",
                    target_date: str | None = None, risk_category: str = "",
                    protocol_number: str = "", report_number: str = "") -> dict:
    """Update the mutable fields of one Postgres `projects` row. RLS
    (company_id = current_company_id()) makes the company_id filter below
    belt-and-suspenders, not the only guard."""
    client = get_authenticated_client(access_token)
    payload = {
        "name": name,
        "status": status or "active",
        "target_date": target_date or None,
        "risk_category": risk_category or None,
        "protocol_number": protocol_number or None,
        "report_number": report_number or None,
    }
    result = (
        client.table(TABLE)
        .update(payload)
        .eq("id", postgres_id)
        .eq("company_id", company_id)
        .execute()
    )
    return result.data[0] if result.data else None


def delete_project(access_token: str, company_id: str, postgres_id: str) -> None:
    """Delete one Postgres `projects` row."""
    client = get_authenticated_client(access_token)
    client.table(TABLE).delete().eq("id", postgres_id).eq("company_id", company_id).execute()

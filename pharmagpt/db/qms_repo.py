"""
pharmagpt/db/qms_repo.py — Postgres CRUD for the Phase 3.5 QMS record types
and their audit trail entries.

Phase 3.5 (docs/PHASE3_EXECUTION_PLAN.md). Not the source of truth yet —
see config.QMS_BACKEND. Every function acts as the caller's own
authenticated Supabase client (get_authenticated_client), never the
service-role key, matching the established convention.

One shared module, not four, because deviations/capas/change_controls/
risk_assessments are structurally identical in the target schema
(DATABASE_ARCHITECTURE.md §4.7): company_id, nullable project_id, title,
status, timestamps — nothing else. Deliberately excludes:

- The current build's much richer sub-structures (deviation investigation/
  impact, CAPA actions/effectiveness, change-control impact/actions/links,
  risk items/library/actions) — none have a table in the frozen target
  schema. Migrating them would mean inventing new Postgres tables, which
  this plan's own instructions rule out ("architecture is frozen, do not
  redesign"). They stay SQLite-only, a documented gap, same treatment as
  Projects' equipment_name fields (3.2).
- attachments/comments/approvals dual-write — deferred to a follow-up; see
  config.QMS_BACKEND's docstring for the reasoning.

record_type values match the strings the current SQLite build already uses
in qms_audit_trail (pharmagpt/qms_database.py:add_audit_entry callers) —
'deviation', 'capa', 'change_control', 'risk_assessment'. Corrected (Yuktav
P1-4): risk_assessment DOES produce qms_audit_trail entries today —
routes/risk.py calls audit.log("risk_assessment", ...) on create/update/
delete/approval-transition/AI-assist/publish-to-library, the same shared
SQLite path every other record_type here uses. Risk ALSO has its own
separate risk_approval table for approval-signature entries specifically
(distinct from, and in addition to, its qms_audit_trail coverage) — the two
are not mutually exclusive, and this module's own record_type mapping above
already includes 'risk_assessment' for its Postgres dual-write.
"""

from pharmagpt.services.supabase_client import get_authenticated_client

_TABLE_BY_RECORD_TYPE = {
    "deviation": "deviations",
    "capa": "capas",
    "change_control": "change_controls",
    "risk_assessment": "risk_assessments",
}


def create_record(access_token: str, company_id: str, record_type: str, *,
                   title: str, status: str, project_id: str | None = None) -> dict:
    """Insert one row into the Postgres table for `record_type`. Returns the
    inserted row."""
    table = _TABLE_BY_RECORD_TYPE[record_type]
    client = get_authenticated_client(access_token)
    payload = {
        "company_id": company_id,
        "title": title,
        "status": status or "open",
        "project_id": project_id or None,
    }
    result = client.table(table).insert(payload).execute()
    return result.data[0]


def update_record(access_token: str, company_id: str, record_type: str, postgres_id: str, *,
                   title: str, status: str, project_id: str | None = None) -> dict | None:
    table = _TABLE_BY_RECORD_TYPE[record_type]
    client = get_authenticated_client(access_token)
    payload = {"title": title, "status": status or "open", "project_id": project_id or None}
    result = (
        client.table(table).update(payload)
        .eq("id", postgres_id).eq("company_id", company_id)
        .execute()
    )
    return result.data[0] if result.data else None


def delete_record(access_token: str, company_id: str, record_type: str, postgres_id: str) -> None:
    table = _TABLE_BY_RECORD_TYPE[record_type]
    client = get_authenticated_client(access_token)
    client.table(table).delete().eq("id", postgres_id).eq("company_id", company_id).execute()


def add_audit_entry(access_token: str, company_id: str, record_type: str, record_id: str,
                     action: str, *, actor_user_id: str | None = None,
                     reason: str | None = None) -> dict:
    """Insert one row into the platform-wide `audit_trail` table
    (append-only — INSERT/SELECT-only RLS, migrations/0008)."""
    client = get_authenticated_client(access_token)
    payload = {
        "company_id": company_id,
        "actor_user_id": actor_user_id or None,
        "action": action,
        "record_type": record_type,
        "record_id": record_id,
        "reason": reason or None,
    }
    result = client.table("audit_trail").insert(payload).execute()
    return result.data[0]

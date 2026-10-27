"""
qms_market_complaint_database.py — SQLite CRUD for the Market Complaint
Management module (P0).

Tables managed here (schema lives in qms_database.QMS_SCHEMA):
  qms_market_complaints : Master complaint record.

Shared cross-module tables (attachments, comments, audit trail, approvals,
e-signatures) live in qms_database.py and are accessed with
record_type='market_complaint' via routes/qms_common.py. The Investigation
Engine (qms_investigation_*) and qms_market_complaint_links (CAPA/Deviation/
Risk linkage) are P1 — not used here yet.

Pure CRUD, one connection per call — same style as qms_deviation_database.py/
qms_capa_database.py.
"""

import json
from pharmagpt.database import get_connection
from pharmagpt.qms_database import generate_complaint_number


# ── Market Complaints ────────────────────────────────────────────────────────

def create_complaint(data: dict, *, company_id: str, created_by_user_id: str = "",
                     created_by_display_name: str = "") -> dict:
    """`company_id` must be the caller's authenticated tenant
    (`g.tenant.company_id`), never client-supplied — see pharmagpt/tenancy.py.
    `created_by_user_id`/`created_by_display_name` (CRIT-02 parity with
    Deviation/CAPA/Change Control) are likewise authenticated-only, never
    taken from `data`. `complaint_number` is generated once here and is
    never accepted from `data` — see COMPLAINT_CONTROLLED_FIELDS below for
    why it can never be changed afterward either, which together make it
    permanent from creation onward (stricter than the P0 requirement that it
    be permanent only "after submission")."""
    conn = get_connection()
    complaint_number = generate_complaint_number()
    cur = conn.execute(
        """INSERT INTO qms_market_complaints
           (complaint_number, title, status, received_date, received_via,
            complainant_name, complainant_contact, complainant_type, product, batch_lot,
            manufacturing_site, market_country, regulatory_profile, description,
            initial_classification, potential_quality_defect, potential_adverse_event,
            severity, risk_level, initial_impact_assessment,
            immediate_containment_action, immediate_containment_date,
            investigation_required, investigation_rationale, department, project_id,
            form_data, company_id, created_by_user_id, created_by_display_name)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            complaint_number,
            data.get("title", "Untitled Complaint").strip() or "Untitled Complaint",
            data.get("status", "Draft"),
            data.get("received_date", ""),
            data.get("received_via", ""),
            data.get("complainant_name", ""),
            data.get("complainant_contact", ""),
            data.get("complainant_type", ""),
            data.get("product", ""),
            data.get("batch_lot", ""),
            data.get("manufacturing_site", ""),
            data.get("market_country", ""),
            data.get("regulatory_profile", ""),
            data.get("description", ""),
            data.get("initial_classification", ""),
            1 if data.get("potential_quality_defect") else 0,
            1 if data.get("potential_adverse_event") else 0,
            data.get("severity", ""),
            data.get("risk_level", ""),
            data.get("initial_impact_assessment", ""),
            data.get("immediate_containment_action", ""),
            data.get("immediate_containment_date", ""),
            data.get("investigation_required", ""),
            data.get("investigation_rationale", ""),
            data.get("department", ""),
            data.get("project_id") or None,
            json.dumps(data.get("form_data", {})),
            company_id,
            created_by_user_id,
            created_by_display_name,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_complaint(new_id)


def _parse(d: dict) -> dict:
    d["form_data"] = json.loads(d.get("form_data") or "{}")
    d["ai_narratives"] = json.loads(d.get("ai_narratives") or "{}")
    d["potential_quality_defect"] = bool(d.get("potential_quality_defect"))
    d["potential_adverse_event"] = bool(d.get("potential_adverse_event"))
    return d


def get_complaint(complaint_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM qms_market_complaints WHERE id = ?", (complaint_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _parse(dict(row))


def get_all_complaints(company_id: str | None = None, filters: dict | None = None) -> list[dict]:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). `company_id=None` is reserved
    for offline scripts; every live route must always pass a company_id."""
    conn = get_connection()
    clauses, params = ([], []) if company_id is None else (["company_id = ?"], [company_id])
    if filters:
        for field in ("status", "severity", "product", "market_country", "department"):
            val = filters.get(field)
            if val:
                clauses.append(f"{field} = ?")
                params.append(val)
        keyword = filters.get("keyword")
        if keyword:
            clauses.append("(title LIKE ? OR complaint_number LIKE ? OR description LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    sql = "SELECT * FROM qms_market_complaints"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_parse(dict(r)) for r in rows]


# CRIT-01 parity (Security Audit remediation — same rationale as
# DEVIATION_CONTROLLED_FIELDS/CAPA_CONTROLLED_FIELDS): these fields may only
# change via this record's governed workflow (services/workflow_engine.py's
# STATUS_APPLIERS + routes/qms_market_complaint.py's e-signed decide route),
# never a raw client-supplied PUT. `complaint_number` is included here too
# (Deviation/CAPA don't block their own number column, but the P0 spec
# explicitly requires this one be permanent) — update_complaint() refuses to
# write it unless the caller passes allow_controlled_fields=True, which only
# the workflow-status applier does, and that applier never sets
# complaint_number in the first place, so in practice it is never rewritten
# after creation by any code path in this module.
COMPLAINT_CONTROLLED_FIELDS = frozenset({"complaint_number", "status", "qa_reviewer", "approver", "closure_date"})


def update_complaint(complaint_id: int, data: dict, *, allow_controlled_fields: bool = False) -> dict | None:
    if not allow_controlled_fields:
        blocked = COMPLAINT_CONTROLLED_FIELDS & data.keys()
        if blocked:
            raise ValueError(
                "workflow-controlled field(s) cannot be set via a generic update: "
                + ", ".join(sorted(blocked))
            )
    conn = get_connection()
    fields = [
        "title", "status", "received_date", "received_via", "complainant_name",
        "complainant_contact", "complainant_type", "product", "batch_lot", "manufacturing_site",
        "market_country", "regulatory_profile", "description", "initial_classification",
        "severity", "risk_level", "initial_impact_assessment",
        "immediate_containment_action", "immediate_containment_date",
        "investigation_required", "investigation_rationale", "department", "project_id",
        "qa_reviewer", "approver", "closure_date", "complaint_number",
    ]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    for bool_field in ("potential_quality_defect", "potential_adverse_event"):
        if bool_field in data:
            updates.append(f"{bool_field} = ?")
            params.append(1 if data[bool_field] else 0)
    if "form_data" in data:
        updates.append("form_data = ?")
        params.append(json.dumps(data["form_data"]))
    if "ai_narratives" in data:
        updates.append("ai_narratives = ?")
        params.append(json.dumps(data["ai_narratives"]))
    if not updates:
        conn.close()
        return get_complaint(complaint_id)
    updates.append("updated_at = datetime('now')")
    params.append(complaint_id)
    conn.execute(f"UPDATE qms_market_complaints SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_complaint(complaint_id)


def delete_complaint(complaint_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM qms_market_complaints WHERE id = ?", (complaint_id,))
    conn.commit()
    conn.close()


def get_dashboard_stats(company_id: str) -> dict:
    """`company_id` must come from the authenticated TenantContext, never
    from client input (pharmagpt/tenancy.py). Basic P0 counts only — no
    trending/analytics (P2)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, severity, created_at FROM qms_market_complaints WHERE company_id = ?",
        (company_id,),
    ).fetchall()
    stats = {"total": len(rows), "open": 0, "closed": 0, "by_status": {}, "by_severity": {}}
    for r in rows:
        d = dict(r)
        status = d.get("status", "Draft")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        if status in ("Closed", "Rejected"):
            stats["closed"] += 1
        else:
            stats["open"] += 1
        severity = d.get("severity") or "Unclassified"
        stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
    conn.close()
    return stats

"""
services/validation_preflight.py — READ-ONLY pre-deployment check for the
standardized Validation approval workflow.

Answers, before the release is deployed: which companies could not complete a
seven-signer approval, and which existing records would be blocked, need to be
restarted, or are grandfathered. It never writes:

  * the SQLite file is opened with ``mode=ro`` and ``PRAGMA query_only=ON``;
  * the company directory is accessed through a select-only interface
    (``SupabaseDirectory`` issues ``.select()`` calls and nothing else);
  * it does NOT run init_db() — missing schema is *reported* as "will be
    applied at startup", never applied.

Use ``scripts/validation_approval_preflight.py`` from the command line.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Iterable

from pharmagpt.services import rbac_defaults
from pharmagpt.services import validation_approval as va

_STATE_FAMILY_REVIEW = {"under_review", "technical_review", "qa_review", "validation_review", "final_approval"}
_PLATFORM_SIGNING_ROLES = ("company_admin", "reviewer_qa")
_VALIDATION_MODULES = rbac_defaults.MAJOR_MODULE_MAP["Validation"]

_DQ_STD = {"Draft": "draft", "Under Review": "under_review", "Technical Review": "technical_review",
           "QA Review": "qa_review", "Validation Review": "validation_review",
           "Final Approval": "final_approval", "Approved": "approved", "Effective": "effective",
           "Obsolete": "obsolete", "Pending Approval": "pending_approval", "Under Revision": "draft"}

BLOCKING = "BLOCKING"
ACTION = "ACTION_REQUIRED"
WARN = "WARNING"
OK = "OK"


# ── directory access (select-only) ───────────────────────────────────────────

class StaticDirectory:
    """In-memory directory (tests, or an exported JSON snapshot)."""

    def __init__(self, data: dict):
        self._d = data

    def companies(self) -> list[dict]:
        return self._d.get("companies", [])

    def users(self, company_id: str) -> list[dict]:
        return [u for u in self._d.get("users", []) if u.get("company_id") == company_id]

    def memberships(self, company_id: str) -> list[dict]:
        return [m for m in self._d.get("memberships", []) if m.get("company_id") == company_id]

    def grants(self, company_id: str) -> dict[str, set]:
        raw = self._d.get("grants", {}).get(company_id, {})
        return {uid: {tuple(g) for g in gs} for uid, gs in raw.items()}


class SupabaseDirectory:
    """Live directory, SELECT ONLY. `client` is a supabase client (service role)."""

    def __init__(self, client):
        self._c = client

    def companies(self):
        # The live column is companies.legal_name (there is no companies.name).
        rows = self._c.table("companies").select("id, legal_name").execute().data or []
        return [{"id": r["id"], "name": r.get("legal_name") or ""} for r in rows]

    def users(self, company_id):
        rows = (self._c.table("users").select("id, company_id, display_name, status, roles(name)")
                .eq("company_id", company_id).execute().data) or []
        return [{"id": r["id"], "company_id": r["company_id"], "display_name": r.get("display_name", ""),
                 "status": r.get("status", ""), "platform_role": (r.get("roles") or {}).get("name", "")}
                for r in rows]

    def memberships(self, company_id):
        rows = (self._c.table("user_departments")
                .select("user_id, company_id, departments(department_code), workflow_roles(name)")
                .eq("company_id", company_id).execute().data) or []
        return [{"user_id": r["user_id"], "company_id": company_id,
                 "department_code": (r.get("departments") or {}).get("department_code"),
                 "functional_role": (r.get("workflow_roles") or {}).get("name")} for r in rows]

    def grants(self, company_id):
        assignments = (self._c.table("rbac_user_roles").select("user_id, role_id")
                       .eq("company_id", company_id).execute().data) or []
        role_ids = list({a["role_id"] for a in assignments})
        if not role_ids:
            return {}
        active = {r["id"] for r in (self._c.table("rbac_roles").select("id").in_("id", role_ids)
                                    .eq("status", "active").execute().data) or []}
        perms = (self._c.table("rbac_role_permissions")
                 .select("role_id, granted, permissions:rbac_permissions(module, action)")
                 .in_("role_id", list(active)).eq("granted", True).execute().data) or [] if active else []
        by_role = defaultdict(set)
        for p in perms:
            if p.get("permissions"):
                by_role[p["role_id"]].add((p["permissions"]["module"], p["permissions"]["action"]))
        out = defaultdict(set)
        for a in assignments:
            out[a["user_id"]] |= by_role.get(a["role_id"], set())
        return dict(out)


# ── company readiness ────────────────────────────────────────────────────────

def _max_matching(adjacency: dict[str, list[str]]) -> dict[str, str]:
    """Maximum bipartite matching designation -> distinct user (augmenting paths)."""
    match_user: dict[str, str] = {}

    def try_assign(d: str, seen: set) -> bool:
        for u in adjacency[d]:
            if u in seen:
                continue
            seen.add(u)
            if u not in match_user or try_assign(match_user[u], seen):
                match_user[u] = d
                return True
        return False

    for d in adjacency:
        try_assign(d, set())
    return {d: u for u, d in match_user.items()}


def check_company(company: dict, directory) -> dict:
    cid = company["id"]
    users = {u["id"]: u for u in directory.users(cid) if u.get("status", "active") in ("active", "")}
    memberships = directory.memberships(cid)
    grants = directory.grants(cid)
    findings, eligible = [], {}
    adjacency: dict[str, list[str]] = {}
    for s in va.SIGNATORIES:
        people = []
        for m in memberships:
            uid = m["user_id"]
            if uid not in users:
                continue
            if m.get("department_code") not in s["departments"] or m.get("functional_role") not in s["roles"]:
                continue
            if not any((mod, s["permission"]) in grants.get(uid, set()) for mod in _VALIDATION_MODULES):
                continue
            if s["key"] != "prepared_by" and users[uid].get("platform_role") not in _PLATFORM_SIGNING_ROLES:
                continue
            if uid not in people:
                people.append(uid)
        eligible[s["key"]] = people
        adjacency[s["key"]] = people
        if not people:
            findings.append({"severity": BLOCKING, "code": "NO_ELIGIBLE_SIGNER", "designation": s["designation"],
                             "detail": f"No active user holds {'/'.join(s['departments'])} + "
                                       f"{'/'.join(s['roles'])} with Validation:{s['permission']}"
                                       + ("" if s["key"] == "prepared_by" else " and a company_admin/reviewer_qa platform role")})
    matching = _max_matching(adjacency)
    if len(matching) < len(va.SIGNATORIES) and all(adjacency.values()):
        findings.append({"severity": BLOCKING, "code": "INSUFFICIENT_DISTINCT_SIGNERS",
                         "detail": f"Only {len(matching)} of {len(va.SIGNATORIES)} designations can be filled by "
                                   f"distinct people (seven different signers are required)"})
    return {"company_id": cid, "company_name": company.get("name", ""),
            "eligible_signers": {k: len(v) for k, v in eligible.items()},
            "distinct_assignable": len(matching), "findings": findings,
            "ready": not any(f["severity"] == BLOCKING for f in findings)}


# ── document scan (SQLite, read-only) ────────────────────────────────────────

def open_readonly(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _cols(conn, table: str) -> set[str]:
    try:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def schema_report(conn) -> list[dict]:
    needs = []
    if not _cols(conn, "validation_signoffs"):
        needs.append({"item": "table validation_signoffs", "effect": "created at startup (CREATE TABLE IF NOT EXISTS)"})
    if not _cols(conn, "validation_transition_claims"):
        needs.append({"item": "table validation_transition_claims",
                      "effect": "created at startup (one-winner claim for Reject / Make Effective / Obsolete)"})
    if not {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'uq_validation_signoffs_%'")}             >= {"uq_validation_signoffs_signatory", "uq_validation_signoffs_signer"}:
        needs.append({"item": "unique indexes on validation_signoffs",
                      "effect": "created at startup unless historical duplicate sign-offs exist (then skipped and reported by /health)"})
    if "approval_status" not in _cols(conn, "qual_protocols"):
        needs.append({"item": "column qual_protocols.approval_status",
                      "effect": "added at startup; back-filled once from each protocol's parent Qualification"})
    for table in ("urs_projects", "qual_qualifications", "qual_protocols", "qms_documents"):
        if "created_by_user_id" not in _cols(conn, table):
            needs.append({"item": f"column {table}.created_by_user_id / created_by_display_name",
                          "effect": "added at startup (blank for existing rows)"})
    return needs


def _ledger(conn):
    """{(company, doc_type, record_id): (current_rows, all_rows)}"""
    out: dict[tuple, list] = defaultdict(list)
    if _cols(conn, "validation_signoffs"):
        for r in conn.execute("SELECT company_id, doc_type, record_id, status FROM validation_signoffs"):
            out[(r["company_id"], r["doc_type"], r["record_id"])].append(r["status"])
    return out


def _kb_has(conn, source_type, source_id, company_id) -> bool:
    if "source_type" not in _cols(conn, "kb_documents"):
        return False
    return conn.execute("SELECT 1 FROM kb_documents WHERE source_type = ? AND source_id = ? AND company_id = ?",
                        (source_type, source_id, company_id)).fetchone() is not None


def _author_state(row: dict, fallback_name: str) -> tuple[str, str]:
    if (row.get("created_by_user_id") or "").strip():
        return OK, "READY_DRAFT"
    if (row.get("created_by_display_name") or fallback_name or "").strip():
        return WARN, "DRAFT_AUTHOR_NAME_FALLBACK"
    return ACTION, "DRAFT_AUTHOR_UNKNOWN"


def _classify(kind, rec, std_status, ledger_statuses, *, creator_row, fallback_name, has_exec=False,
              has_legacy_instance=False, in_kb=None) -> list[dict]:
    out = []
    has_ledger = bool(ledger_statuses)
    cur = [s for s in ledger_statuses if s == "completed"]
    base = {"kind": kind, "id": rec["id"], "company_id": rec.get("company_id"), "status": std_status,
            "title": rec.get("title", "")}

    def add(sev, code, detail):
        out.append({**base, "severity": sev, "code": code, "detail": detail})

    if not rec.get("company_id"):
        add(BLOCKING, "TENANTLESS_RECORD", "Record has no company_id: tenant-scoped routes can never reach it")
    if std_status == "draft":
        sev, code = _author_state(creator_row, fallback_name)
        if code == "DRAFT_AUTHOR_UNKNOWN":
            add(ACTION, code, "No creator identity and no prepared_by name: nobody can submit it until the creator is stamped")
        elif code == "DRAFT_AUTHOR_NAME_FALLBACK":
            add(WARN, code, "Creator id blank; authorship will be matched on the stored display name")
        if has_ledger:
            add(OK, "REJECTED_RESUBMITTABLE", "Previously rejected/revised; history preserved, resubmission starts a new cycle")
        if has_exec and not has_ledger:
            add(OK, "LEGACY_EXECUTION_GRANDFATHERED", "Executions recorded before approval tracking: execution may continue")
    elif std_status in _STATE_FAMILY_REVIEW or std_status == "pending_approval":
        if not has_ledger:
            add(ACTION, "RESTART_REQUIRED", "In review under the pre-standard workflow, no sign-offs: reject to Draft and resubmit")
        else:
            add(OK, "IN_FLIGHT_STANDARD_WORKFLOW", f"{len(cur)} of 7 sign-offs recorded")
        if has_legacy_instance:
            add(OK, "LEGACY_DQ_WORKFLOW_GRANDFATHERED", "Active legacy workflow instance: finishes on the legacy engine")
    elif std_status == "approved":
        if not has_ledger:
            add(OK, "LEGACY_APPROVED", "Approved under the pre-standard workflow: may still be made Effective")
        elif len(cur) < 7:
            add(BLOCKING, "APPROVED_WITH_INCOMPLETE_LEDGER", f"Approved but only {len(cur)} of 7 sign-offs: cannot become Effective")
        else:
            add(OK, "APPROVED_COMPLETE", "All seven sign-offs present")
    elif std_status == "effective":
        if has_ledger and len(cur) < 7:
            add(WARN, "EFFECTIVE_WITH_INCOMPLETE_LEDGER", f"Effective with {len(cur)} of 7 sign-offs (pre-dates enforcement or was altered)")
        if in_kb is False:
            add(WARN, "EFFECTIVE_NOT_IN_KB", "Effective but not in the Knowledge Base; re-publication needs a fresh Make Effective or the recovery script")
        elif not out:
            add(OK, "EFFECTIVE_OK", "")
    return out


def scan_documents(conn) -> list[dict]:
    ledger = _ledger(conn)
    findings: list[dict] = []

    def led(company, dtype, rid):
        return ledger.get((company, dtype, rid), [])

    # URS
    uc = _cols(conn, "urs_projects")
    if uc:
        for r in conn.execute("SELECT * FROM urs_projects"):
            r = dict(r)
            findings += _classify("URS", r, (r.get("status") or "draft").lower(), led(r.get("company_id"), "URS", r["id"]),
                                  creator_row=r, fallback_name=r.get("prepared_by", ""),
                                  in_kb=_kb_has(conn, "urs", r["id"], r.get("company_id")) if (r.get("status") == "effective") else None)

    # DQ (Document Control)
    if _cols(conn, "qms_documents"):
        active = set()
        if _cols(conn, "qms_workflow_instances"):
            active = {(x["record_id"]) for x in conn.execute(
                "SELECT record_id FROM qms_workflow_instances WHERE record_type = 'document' AND status = 'in_progress'")}
        for r in conn.execute("SELECT * FROM qms_documents WHERE doc_type = 'DQ'"):
            r = dict(r)
            std = _DQ_STD.get(r.get("status") or "Draft", "draft")
            creator = dict(r)
            if not (creator.get("created_by_user_id") or "").strip() and _cols(conn, "qms_document_versions"):
                v = conn.execute("SELECT created_by_user_id FROM qms_document_versions WHERE document_id = ? ORDER BY id LIMIT 1",
                                 (r["id"],)).fetchone()
                creator["created_by_user_id"] = (v["created_by_user_id"] if v and "created_by_user_id" in v.keys() else "") or ""
            findings += _classify("DQ", r, std, led(r.get("company_id"), "DQ", r["id"]), creator_row=creator,
                                  fallback_name=r.get("prepared_by", ""), has_legacy_instance=r["id"] in active,
                                  in_kb=_kb_has(conn, "document", r["id"], r.get("company_id")) if std == "effective" else None)

    # IQ / OQ / PQ protocols
    if _cols(conn, "qual_protocols") and _cols(conn, "qual_qualifications"):
        has_status_col = "approval_status" in _cols(conn, "qual_protocols")
        quals = {q["id"]: dict(q) for q in conn.execute("SELECT * FROM qual_qualifications")}
        executed = {x["protocol_id"] for x in conn.execute("SELECT DISTINCT protocol_id FROM qual_executions")} \
            if _cols(conn, "qual_executions") else set()
        for p in conn.execute("SELECT * FROM qual_protocols"):
            p = dict(p)
            q = quals.get(p["qual_id"], {})
            parent = (q.get("status") or "draft").lower()
            derived = {"approved": "approved", "closed": "approved", "effective": "effective", "obsolete": "obsolete",
                       "under_review": "under_review", "pending_approval": "pending_approval"}.get(parent, "draft")
            std = (p.get("approval_status") if has_status_col and p.get("approval_status") else derived)
            creator = {"created_by_user_id": p.get("created_by_user_id") or q.get("created_by_user_id") or "",
                       "created_by_display_name": p.get("created_by_display_name") or q.get("created_by_display_name") or ""}
            rec = {"id": p["id"], "company_id": q.get("company_id"), "title": p.get("title", "")}
            findings += _classify(p["protocol_type"], rec, std, led(q.get("company_id"), p["protocol_type"], p["id"]),
                                  creator_row=creator, fallback_name=q.get("prepared_by", ""),
                                  has_exec=p["id"] in executed,
                                  in_kb=_kb_has(conn, "qualification_protocol", p["id"], q.get("company_id")) if std == "effective" else None)

    # Ledger integrity: sign-off rows must belong to the same company as their record
    if _cols(conn, "validation_signoffs"):
        owners = {}
        for dtype, table in (("URS", "urs_projects"), ("DQ", "qms_documents")):
            if _cols(conn, table):
                for r in conn.execute(f"SELECT id, company_id FROM {table}"):
                    owners[(dtype, r["id"])] = r["company_id"]
        for p in (conn.execute("SELECT p.id, p.protocol_type, q.company_id FROM qual_protocols p "
                               "JOIN qual_qualifications q ON q.id = p.qual_id") if _cols(conn, "qual_protocols") else []):
            owners[(p["protocol_type"], p["id"])] = p["company_id"]
        for r in conn.execute("SELECT DISTINCT company_id, doc_type, record_id FROM validation_signoffs"):
            owner = owners.get((r["doc_type"], r["record_id"]))
            if owner is not None and owner != r["company_id"]:
                findings.append({"kind": r["doc_type"], "id": r["record_id"], "company_id": r["company_id"],
                                 "status": "", "title": "", "severity": BLOCKING, "code": "LEDGER_COMPANY_MISMATCH",
                                 "detail": "Sign-off rows are filed under a different company than the record"})
    return findings


def environment_report() -> list[dict]:
    """Names and booleans only — never values."""
    import os
    from pharmagpt import config
    out = []
    for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        present = bool(os.getenv(name))
        out.append({"severity": OK if present else BLOCKING, "code": "ENV_" + name,
                    "detail": f"{name} is {'set' if present else 'NOT set'} "
                              + ("" if present else "(e-signature re-authentication / department lookup cannot work)")})
    out.append({"severity": OK if config.VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT else WARN,
                "code": "DEPARTMENT_ENFORCEMENT",
                "detail": f"VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT={config.VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT}"})
    return out


def run_preflight(sqlite_path: str, directory=None, include_env: bool = True) -> dict:
    conn = open_readonly(sqlite_path)
    try:
        schema = schema_report(conn)
        docs = scan_documents(conn)
    finally:
        conn.close()
    companies = [check_company(c, directory) for c in directory.companies()] if directory else []
    env = environment_report() if include_env else []
    everything = docs + [f for c in companies for f in c["findings"]] + env
    counts = defaultdict(int)
    for f in everything:
        counts[f["severity"]] += 1
    by_code = defaultdict(int)
    for f in docs:
        by_code[f["code"]] += 1
    return {
        "read_only": True,
        "summary": {"blocking": counts[BLOCKING], "action_required": counts[ACTION], "warnings": counts[WARN],
                    "ok": counts[OK], "companies_checked": len(companies),
                    "companies_not_ready": sum(1 for c in companies if not c["ready"]),
                    "documents_by_code": dict(by_code),
                    "go": counts[BLOCKING] == 0},
        "schema_migrations_pending": schema,
        "companies": companies,
        "documents": docs,
        "environment": env,
    }

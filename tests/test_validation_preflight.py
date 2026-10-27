"""
Read-only pre-deployment preflight (services/validation_preflight.py,
scripts/validation_approval_preflight.py): finds companies that could not
complete a seven-signer cycle and documents that would be blocked, restarted
or grandfathered — without ever writing.
"""

import hashlib
import json

import pytest

from pharmagpt import database as maindb
from pharmagpt import qual_database as qdb
from pharmagpt import urs_database as udb
from pharmagpt import validation_approval_database as vadb
from pharmagpt.services import validation_preflight as pf

CO = "co-1"
VALIDATION_GRANTS = [("Validation", a) for a in ("View", "Submit", "Review", "Approve", "Reject")]


def _hash(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _mk_urs(title, status="draft", company=CO, creator="u1", name="Ann", prepared_by="Ann"):
    r = udb.create_urs({"title": title, "equipment_name": "E", "prepared_by": prepared_by}, company_id=company or "x",
                       created_by_user_id=creator, created_by_display_name=name)
    conn = maindb.get_connection()
    with conn:
        conn.execute("UPDATE urs_projects SET status = ?, company_id = ? WHERE id = ?", (status, company, r["id"]))
    conn.close()
    return r["id"]


def _ledger(company, dtype, rid, n, statuses=None):
    keys = [s["key"] for s in pf.va.SIGNATORIES]
    for i in range(n):
        vadb.add_signoff(company_id=company, doc_type=dtype, record_id=rid, revision="A", signatory_key=keys[i],
                         designation=keys[i], signer_user_id=f"s{i}", signer_name=f"S{i}", signer_role="reviewer_qa")


def codes(report, kind=None, rid=None):
    return {f["code"] for f in report["documents"] if (kind is None or f["kind"] == kind) and (rid is None or f["id"] == rid)}


@pytest.fixture()
def populated(db_path):
    ids = {}
    ids["ready_draft"] = _mk_urs("ready draft")
    ids["name_only"] = _mk_urs("legacy named", creator="", name="", prepared_by="Bob")
    ids["unknown"] = _mk_urs("legacy unknown", creator="", name="", prepared_by="")
    ids["in_flight"] = _mk_urs("legacy in review", status="under_review")
    ids["pending"] = _mk_urs("legacy pending", status="pending_approval")
    ids["legacy_approved"] = _mk_urs("legacy approved", status="approved")
    ids["bad_approved"] = _mk_urs("approved partial", status="approved")
    _ledger(CO, "URS", ids["bad_approved"], 3)
    ids["new_flight"] = _mk_urs("new flow review", status="technical_review")
    _ledger(CO, "URS", ids["new_flight"], 3)
    ids["rejected"] = _mk_urs("rejected")
    _ledger(CO, "URS", ids["rejected"], 2)
    conn = maindb.get_connection()
    with conn:
        conn.execute("UPDATE validation_signoffs SET status = 'superseded' WHERE record_id = ? AND doc_type = 'URS'",
                     (ids["rejected"],))
    conn.close()
    ids["effective"] = _mk_urs("effective, never published", status="effective")
    ids["tenantless"] = _mk_urs("no tenant", company=None)
    ids["mismatch"] = _mk_urs("mismatch")
    _ledger("other-co", "URS", ids["mismatch"], 1)

    q = qdb.create_qualification({"title": "Q", "equipment_name": "E", "prepared_by": "Ann"}, company_id=CO,
                                 created_by_user_id="u1", created_by_display_name="Ann")
    p_exec = qdb.create_protocol(q["id"], "IQ", {})
    tc = qdb.add_test_case(p_exec["id"], q["id"], {"test_id": "T", "test_name": "t"})
    qdb.save_execution(tc["id"], p_exec["id"], q["id"], {"result": "pass"})
    ids["p_exec"] = p_exec["id"]
    return ids


def test_preflight_classifies_every_legacy_state(populated, db_path):
    report = pf.run_preflight(db_path, include_env=False)
    ids = populated
    assert "READY_DRAFT" not in codes(report, "URS", ids["ready_draft"])        # nothing to report for a clean draft
    assert "DRAFT_AUTHOR_NAME_FALLBACK" in codes(report, "URS", ids["name_only"])
    assert "DRAFT_AUTHOR_UNKNOWN" in codes(report, "URS", ids["unknown"])
    assert "RESTART_REQUIRED" in codes(report, "URS", ids["in_flight"])
    assert "RESTART_REQUIRED" in codes(report, "URS", ids["pending"])
    assert "LEGACY_APPROVED" in codes(report, "URS", ids["legacy_approved"])
    assert "APPROVED_WITH_INCOMPLETE_LEDGER" in codes(report, "URS", ids["bad_approved"])
    assert "IN_FLIGHT_STANDARD_WORKFLOW" in codes(report, "URS", ids["new_flight"])
    assert "REJECTED_RESUBMITTABLE" in codes(report, "URS", ids["rejected"])
    assert "EFFECTIVE_NOT_IN_KB" in codes(report, "URS", ids["effective"])
    assert "TENANTLESS_RECORD" in codes(report, "URS", ids["tenantless"])
    assert "LEDGER_COMPANY_MISMATCH" in codes(report, "URS", ids["mismatch"])
    assert "LEGACY_EXECUTION_GRANDFATHERED" in codes(report, "IQ", ids["p_exec"])


def test_blocking_findings_make_it_no_go(populated, db_path):
    s = pf.run_preflight(db_path, include_env=False)["summary"]
    assert s["go"] is False and s["blocking"] >= 3 and s["action_required"] >= 3


def test_a_clean_database_is_go(db_path):
    _mk_urs("clean")
    assert pf.run_preflight(db_path, include_env=False)["summary"]["go"] is True


def test_dq_with_an_active_legacy_workflow_instance_is_reported_as_grandfathered(db_path):
    from pharmagpt import qms_document_database as dqdb
    from pharmagpt.services import workflow_engine as wfe
    from pharmagpt.routes import qms_documents as routes
    from pharmagpt.app import app
    d = dqdb.create_document({"title": "dq", "doc_type": "DQ", "prepared_by": "Ann"}, company_id=CO, created_by_user_id="u1")
    with app.app_context():
        wfe.start_instance(routes.WORKFLOW_KEY, routes.RECORD_TYPE, d["id"], CO, "Legacy")
    report = pf.run_preflight(db_path, include_env=False)
    assert "LEGACY_DQ_WORKFLOW_GRANDFATHERED" in codes(report, "DQ", d["id"])


# ── it never writes ──────────────────────────────────────────────────────────

def test_preflight_does_not_modify_the_database_file(populated, db_path):
    before = _hash(db_path)
    pf.run_preflight(db_path, directory=pf.StaticDirectory({"companies": []}), include_env=False)
    assert _hash(db_path) == before


def test_connection_is_physically_read_only(db_path):
    conn = pf.open_readonly(db_path)
    with pytest.raises(Exception):
        conn.execute("DELETE FROM urs_projects")
    with pytest.raises(Exception):
        conn.execute("CREATE TABLE sneaky (x)")
    conn.close()


def test_pre_migration_database_is_reported_not_migrated(db_path):
    conn = maindb.get_connection()
    with conn:
        conn.execute("DROP TABLE validation_signoffs")
        conn.execute("ALTER TABLE qual_protocols DROP COLUMN approval_status")
    conn.close()
    before = _hash(db_path)
    report = pf.run_preflight(db_path, include_env=False)
    items = " ".join(m["item"] for m in report["schema_migrations_pending"])
    assert "validation_signoffs" in items and "approval_status" in items
    assert _hash(db_path) == before                     # preflight did not apply them
    conn = pf.open_readonly(db_path)
    assert not pf._cols(conn, "validation_signoffs")
    conn.close()


def test_environment_report_never_leaks_values(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET-SENTINEL-VALUE")
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    blob = json.dumps(pf.environment_report())
    assert "SECRET-SENTINEL-VALUE" not in blob and "example.invalid" not in blob


# ── company readiness ────────────────────────────────────────────────────────

def _person(uid, company, dept, role, platform="reviewer_qa", grants=VALIDATION_GRANTS):
    return ({"id": uid, "company_id": company, "status": "active", "platform_role": platform, "display_name": uid},
            {"user_id": uid, "company_id": company, "department_code": dept, "functional_role": role},
            (uid, grants))


FULL_TEAM = [("v-init", "VALIDATION", "Initiator", "user"), ("proc-rev", "ENGINEERING", "Reviewer", "reviewer_qa"),
             ("eng-mgr", "ENGINEERING", "Approver", "reviewer_qa"), ("prod-mgr", "PRODUCTION", "Approver", "reviewer_qa"),
             ("qa-mgr", "QA", "Approver", "reviewer_qa"), ("val-mgr", "VALIDATION", "Approver", "reviewer_qa"),
             ("site-dir", "PLANT_HEAD", "Plant Head", "reviewer_qa")]


def _directory(company_team: dict):
    data = {"companies": [], "users": [], "memberships": [], "grants": {}}
    for cid, team in company_team.items():
        data["companies"].append({"id": cid, "name": cid})
        data["grants"][cid] = {}
        for uid, dept, role, plat in team:
            u, m, (gid, g) = _person(uid, cid, dept, role, plat)
            data["users"].append(u); data["memberships"].append(m); data["grants"][cid][gid] = g
    return pf.StaticDirectory(data)


def test_fully_staffed_company_is_ready():
    c = pf.check_company({"id": "A", "name": "A"}, _directory({"A": FULL_TEAM}))
    assert c["ready"] and c["distinct_assignable"] == 7 and not c["findings"]


def test_missing_designation_blocks_the_company():
    team = [t for t in FULL_TEAM if t[0] != "qa-mgr"]
    c = pf.check_company({"id": "A", "name": "A"}, _directory({"A": team}))
    assert not c["ready"]
    assert any(f["code"] == "NO_ELIGIBLE_SIGNER" and f["designation"] == "QA Manager" for f in c["findings"])


def test_one_person_cannot_fill_two_lines_so_six_people_are_not_enough():
    team = [t for t in FULL_TEAM if t[0] != "val-mgr"] + [("eng-mgr", "VALIDATION", "Approver", "reviewer_qa")]
    d = _directory({"A": team})
    # eng-mgr now holds Engineering AND Validation approver memberships, but is only one person.
    c = pf.check_company({"id": "A", "name": "A"}, d)
    assert c["distinct_assignable"] == 6
    assert any(f["code"] == "INSUFFICIENT_DISTINCT_SIGNERS" for f in c["findings"])


def test_user_without_validation_permission_or_platform_role_is_not_eligible():
    team = [("v-init", "VALIDATION", "Initiator", "user")] + [(u, d, r, "user") for u, d, r, _ in FULL_TEAM[1:]]
    c = pf.check_company({"id": "A", "name": "A"}, _directory({"A": team}))
    assert not c["ready"]                                       # platform role 'user' cannot sign review lines
    d2 = _directory({"A": FULL_TEAM})
    d2._d["grants"]["A"]["qa-mgr"] = [("Validation", "View")]   # no Approve grant
    c2 = pf.check_company({"id": "A", "name": "A"}, d2)
    assert any(f["designation"] == "QA Manager" for f in c2["findings"])


def test_companies_are_assessed_independently():
    d = _directory({"good": FULL_TEAM, "bad": FULL_TEAM[:3]})
    ready = {c["company_id"]: c["ready"] for c in pf.run_preflight_companies(d)} if hasattr(pf, "run_preflight_companies") \
        else {c["id"]: pf.check_company(c, d)["ready"] for c in d.companies()}
    assert ready == {"good": True, "bad": False}


# ── Supabase directory is select-only ────────────────────────────────────────

class _Query:
    def __init__(self, rows, log):
        self.rows, self.log = rows, log

    def select(self, *a, **k): self.log.append("select"); return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def execute(self): return type("R", (), {"data": self.rows})()

    def __getattr__(self, name):                                  # insert/update/delete/upsert/rpc ...
        raise AssertionError(f"preflight attempted a write-capable call: {name}")


class _Client:
    def __init__(self):
        self.log = []
        self.tables = {"companies": [{"id": "A", "name": "A"}],
                       "users": [{"id": "u", "company_id": "A", "status": "active", "roles": {"name": "reviewer_qa"}}],
                       "user_departments": [{"user_id": "u", "departments": {"department_code": "QA"},
                                             "workflow_roles": {"name": "Approver"}}],
                       "rbac_user_roles": [{"user_id": "u", "role_id": 1}],
                       "rbac_roles": [{"id": 1}],
                       "rbac_role_permissions": [{"role_id": 1, "permissions": {"module": "Validation", "action": "Approve"}}]}

    def table(self, name): return _Query(self.tables[name], self.log)

    def __getattr__(self, name): raise AssertionError(f"preflight called client.{name}")


def test_supabase_directory_only_selects():
    client = _Client()
    d = pf.SupabaseDirectory(client)
    assert d.companies()[0]["id"] == "A"
    assert d.users("A")[0]["platform_role"] == "reviewer_qa"
    assert d.memberships("A")[0]["department_code"] == "QA"
    assert ("Validation", "Approve") in d.grants("A")["u"]
    assert set(client.log) == {"select"}


def test_supabase_companies_uses_actual_legal_name_column():
    """Regression: the live schema has companies.legal_name, not companies.name
    (selecting `name` made the live preflight crash with Postgres 42703)."""
    class _Strict(_Query):
        def select(self, cols, *a, **k):
            asked = {c.strip() for c in cols.split(",")}
            assert asked <= {"id", "legal_name"}, f"unknown companies column(s): {asked - {'id', 'legal_name'}}"
            return super().select(cols)

    client = _Client()
    client.tables["companies"] = [{"id": "A", "legal_name": "Acme Pharma"}]
    client.table = lambda name: (_Strict if name == "companies" else _Query)(client.tables[name], client.log)
    assert pf.SupabaseDirectory(client).companies() == [{"id": "A", "name": "Acme Pharma"}]
    client.tables["companies"] = [{"id": "B", "legal_name": None}]
    assert pf.SupabaseDirectory(client).companies() == [{"id": "B", "name": ""}]


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_exit_codes_and_report(populated, db_path, tmp_path, capsys):
    from scripts import validation_approval_preflight as cli
    snap = tmp_path / "dir.json"
    snap.write_text(json.dumps({"companies": [{"id": "A", "name": "A"}], "users": [], "memberships": [], "grants": {}}))
    out = tmp_path / "report.json"
    before = _hash(db_path)
    code = cli.main(["--sqlite", db_path, "--directory-json", str(snap), "--json", str(out)])
    assert code == 2
    assert json.loads(out.read_text())["read_only"] is True
    assert "NO-GO" in capsys.readouterr().out
    assert _hash(db_path) == before

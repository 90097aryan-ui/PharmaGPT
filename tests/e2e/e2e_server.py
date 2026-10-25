"""
Isolated end-to-end test server for the Validation approval workflow.

Runs the REAL Flask app (real routes, real engine, real SQLite schema and real
static JS) against a throwaway database, with only the external boundaries
replaced:

  * authentication  -> the persona named in the `e2e_persona` cookie
  * Supabase RBAC   -> per-persona Validation permissions
  * Supabase org    -> per-persona user_departments memberships
  * re-authentication (e-signature) -> password "e2e-pass" is accepted, anything else is not

Nothing here can reach production: it binds 127.0.0.1 on an ephemeral port and
the database path is supplied by the caller (pytest tmp_path).

The /e2e/* paths are served by a WSGI wrapper in front of the app (the Flask
app itself is not modified), so the production URL map is untouched.
"""

import json
import os
import threading
from http.cookies import SimpleCookie

from werkzeug.serving import make_server

import tests.conftest as conftest_module
from pharmagpt.auth.context import TenantContext
from pharmagpt.tenancy import BOOTSTRAP_COMPANY_ID
from tests._va_helpers import ALL_DEPARTMENTS, SIGNERS, membership

HERE = os.path.dirname(os.path.abspath(__file__))
PASSWORD = "e2e-pass"

# persona name -> (user_id, platform role, Validation permissions, memberships)
PERSONAS: dict[str, tuple] = {}
for _key, (_uid, _role, _perm, _dept, _func) in SIGNERS.items():
    _perms = {_perm, "View"} | ({"Reject"} if _perm == "Approve" else set())
    PERSONAS[_key] = (_uid, _role, _perms, [membership(_dept, _func)])
PERSONAS["other_initiator"] = ("10000000-0000-0000-0000-000000000099", "user", {"Submit", "View"},
                               [membership("VALIDATION", "Initiator")])
PERSONAS["qc_manager"] = ("10000000-0000-0000-0000-0000000000c1", "reviewer_qa", {"Approve", "Reject", "View", "Review"},
                          [membership("QC", "Approver")])
PERSONAS["admin"] = ("10000000-0000-0000-0000-0000000000aa", "company_admin",
                     {"Approve", "Review", "Reject", "Submit", "View", "Delete", "Edit", "Create"},
                     [membership(d, "Coordinator") for d in ALL_DEPARTMENTS])
_BY_USER = {v[0]: v for v in PERSONAS.values()}


def _tenant_for(name: str) -> TenantContext:
    uid, role, _perms, _m = PERSONAS[name]
    return TenantContext(user_id=uid, email=f"{name}@e2e.invalid", display_name=f"E2E {name}", role=role,
                         company_id=BOOTSTRAP_COMPANY_ID)


class E2EServer:
    def __init__(self, monkeypatch, db_path: str):
        import pharmagpt.app as appmod
        import pharmagpt.auth.middleware as auth_middleware
        import pharmagpt.services.esignature_service as esig
        from pharmagpt import database as maindb
        from pharmagpt.services import org_directory

        self.app = appmod.app
        self._monkeypatch = monkeypatch
        monkeypatch.setattr(auth_middleware, "is_exempt", lambda path: True)
        monkeypatch.setattr(esig, "reauthenticate", lambda email, password: password == PASSWORD)
        monkeypatch.setattr("pharmagpt.auth.module_access.get_effective_permissions",
                            lambda tenant: {("Validation", a) for a in _BY_USER[tenant.user_id][2]})
        monkeypatch.setattr("pharmagpt.services.supabase_client.get_service_role_client", lambda: object())
        monkeypatch.setattr(org_directory, "list_user_departments",
                            lambda client, user_id, company_id: list(_BY_USER[user_id][3]))
        monkeypatch.setattr("pharmagpt.routes.qms_documents.get_company_name_for_docx", lambda company_id: "")
        maindb.init_db()

        outer = self

        def wsgi(environ, start_response):
            path = environ.get("PATH_INFO", "")
            cookies = SimpleCookie(environ.get("HTTP_COOKIE", ""))
            persona = cookies["e2e_persona"].value if "e2e_persona" in cookies else "admin"
            if persona not in PERSONAS:
                persona = "admin"
            if path.startswith("/e2e/"):
                return outer._serve_e2e(path, environ, start_response)
            # The conftest tenant shim (registered once at import time) reads this global per request.
            conftest_module._TEST_TENANT = _tenant_for(persona)
            return outer._inner(environ, start_response)

        self._inner = self.app.wsgi_app
        self._saved_wsgi = self.app.wsgi_app
        self._saved_tenant = conftest_module._TEST_TENANT
        self.app.wsgi_app = wsgi
        self._server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    # -- test-only endpoints ----------------------------------------------------
    def _serve_e2e(self, path, environ, start_response):
        from urllib.parse import parse_qs
        qs = parse_qs(environ.get("QUERY_STRING", ""))

        def reply(body, ctype="application/json", headers=()):
            data = body.encode() if isinstance(body, str) else body
            start_response("200 OK", [("Content-Type", ctype), ("Content-Length", str(len(data))), *headers])
            return [data]

        if path == "/e2e/harness":
            return reply(f"""<!doctype html><html><head><meta charset="utf-8"><title>e2e</title></head><body>
<div id="host"></div><pre id="result">PENDING</pre>
<script src="/static/js/esignature_dialog.js"></script>
<script src="/static/js/validation_approval_ui.js"></script>
<script>window.E2E_PASSWORD = {json.dumps(PASSWORD)};</script>
<script src="/e2e/runner.js"></script></body></html>""", "text/html")
        if path == "/e2e/runner.js":
            return reply(open(os.path.join(HERE, "runner.js"), encoding="utf-8").read(), "application/javascript")
        if path == "/e2e/persona":
            name = qs.get("name", ["admin"])[0]
            return reply(json.dumps({"persona": name}), headers=[("Set-Cookie", f"e2e_persona={name}; Path=/")])
        if path == "/e2e/state":
            return reply(json.dumps(self.state(qs["kind"][0], int(qs["id"][0]), int(qs.get("qid", ["0"])[0]))))
        if path == "/e2e/training":
            from pharmagpt import qms_document_database as dqdb
            did = int(qs["id"][0])
            t = dqdb.add_training(did, {"trainee_name": "E2E Operator", "role": "Operator"})
            dqdb.update_training_status(t["id"], "Completed", "2026-10-10")
            return reply(json.dumps({"ok": True}))
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]

    def state(self, kind: str, rid: int, qid: int = 0) -> dict:
        """Ground truth read straight from the database (not through the UI)."""
        from pharmagpt import database as maindb
        from pharmagpt import qms_document_database as dqdb
        from pharmagpt import qual_database as qdb
        from pharmagpt import urs_database as udb
        from pharmagpt import validation_approval_database as vadb
        co = BOOTSTRAP_COMPANY_ID
        if kind == "URS":
            rec = udb.get_urs(rid); status, rev, src = rec["status"], rec["revision"], "urs"
        elif kind == "DQ":
            rec = dqdb.get_document(rid); status = rec["status"].lower().replace(" ", "_")
            rev, src = (dqdb.get_current_version(rid) or {}).get("version_number"), "document"
        else:
            rec = qdb.get_protocol(rid); status = qdb.get_protocol_approval_status(rec)
            rev, src = rec["revision"], "qualification_protocol"
        parent = qdb.get_qualification(qid)["status"] if qid else None
        return {"status": status, "revision": rev,
                "ledger_current": len(vadb.list_signoffs(co, kind, rid)),
                "ledger_all": len(vadb.list_signoffs(co, kind, rid, include_superseded=True)),
                "kb_published": maindb.get_kb_document_by_source(src, rid, co) is not None,
                "parent_status": parent}

    def start(self):
        self._thread.start()
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        self._server.shutdown()
        self.app.wsgi_app = self._saved_wsgi
        conftest_module._TEST_TENANT = self._saved_tenant

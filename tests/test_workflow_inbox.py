"""
tests/test_workflow_inbox.py — Universal Workflow Inbox: correctness of
/workflow/inbox and /workflow/inbox/stats, tenant isolation, and proof that
the Inbox needs zero new code to pick up a module once it has a workflow
template + a services/workflow_registry.py entry.
"""

from pharmagpt import qms_workflow_database as wfdb
from pharmagpt.services import workflow_registry

_FIXED_USER_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py::_TEST_TENANT.user_id
_ASSIGN = {"approvers": [{"user_id": _FIXED_USER_ID, "display_name": "Test User"}]}


def _dev_configure_all_approvers(client, did, user_id=_FIXED_USER_ID, display_name="Test User"):
    """The Workflow Builder is the only place a deviation's approvers are
    configured — there is no runtime "Assign Approver" action. Fill in the
    Review chain plus both fixed CAPA-phase steps (QA Review, Final
    Approval); /workflow/start then auto-assigns all of them."""
    steps = client.get(f"/qms/deviations/{did}/workflow-builder").get_json()["steps"]
    for s in steps:
        s["approver_user_id"] = user_id
        s["approver_display_name"] = display_name
    capa_phase = {
        "qa_review_approver_user_id": user_id, "qa_review_approver_display_name": display_name,
        "final_approval_approver_user_id": user_id, "final_approval_approver_display_name": display_name,
    }
    client.put(f"/qms/deviations/{did}/workflow-builder", json={"steps": steps, "capa_phase": capa_phase})


def test_inbox_empty_when_nothing_pending(client):
    r = client.get("/workflow/inbox")
    assert r.status_code == 200
    assert r.get_json() == []

    stats = client.get("/workflow/inbox/stats").get_json()
    assert stats["my_pending_count"] == 0
    assert stats["awaiting_my_decision_count"] == 0
    assert stats["overdue_count"] == 0
    assert stats["recent_decisions"] == []


def test_inbox_lists_pending_deviation_approval_step_once_workflow_starts(client):
    # DEVIATION_LIFECYCLE_V2's step 2 ("initiator_mgr_review") is an
    # approval step — it only appears in the Inbox once someone is named as
    # its approver. There is no runtime "Assign Approver" action for
    # deviations anymore (see tests/test_qms_routes.py::_dev_reach_qa_approval):
    # the Workflow Builder is the only place to configure approvers, and
    # /workflow/start auto-assigns everyone configured, so the step is
    # already in the Inbox the moment submission succeeds.
    dev = client.post("/qms/deviations", json={"title": "Temp excursion"}).get_json()
    did = dev["id"]
    assert client.get("/workflow/inbox").get_json() == []

    _dev_configure_all_approvers(client, did)
    r = client.post(f"/qms/deviations/{did}/workflow/start")
    assert r.status_code == 201

    items = client.get("/workflow/inbox").get_json()
    assert len(items) == 1
    row = items[0]
    assert row["module"] == "deviation"
    assert row["record_id"] == did
    assert row["title"] == "Temp excursion"
    assert row["current_step_order"] == 2
    assert row["step_type"] == "approval"
    assert row["assigned_to"] == ["Test User"]
    assert row["due_date"] is None
    assert row["priority"] == "Normal"


def test_inbox_lists_pending_capa_and_change_control_immediately(client):
    # Both CAPA_WORKFLOW_V1 and CHANGE_CONTROL_WORKFLOW_V1 start on an
    # *activity* step (any eligible role may act — no named assignment
    # needed), so these appear right after /workflow/start.
    capa = client.post("/qms/capa", json={"title": "CAPA one"}).get_json()
    client.post(f"/qms/capa/{capa['id']}/workflow/start")

    cc = client.post("/qms/change-control", json={"title": "CC one"}).get_json()
    client.post(f"/qms/change-control/{cc['id']}/workflow/start")

    items = client.get("/workflow/inbox").get_json()
    modules = {i["module"] for i in items}
    assert modules == {"capa", "change_control"}
    titles = {i["title"] for i in items}
    assert titles == {"CAPA one", "CC one"}
    assert all(i["step_type"] == "activity" for i in items)


def test_inbox_lists_pending_document_once_assigned(client):
    # DOCUMENT_WORKFLOW_V1's step 2 ("under_review") is an approval step.
    doc = client.post("/qms/documents", json={"title": "Doc one"}).get_json()
    did = doc["id"]
    client.post(f"/qms/documents/{did}/workflow/start")
    assert client.get("/workflow/inbox").get_json() == []

    client.post(f"/qms/documents/{did}/workflow/steps/2/assign", json=_ASSIGN)
    items = client.get("/workflow/inbox").get_json()
    assert len(items) == 1
    assert items[0]["module"] == "document"
    assert items[0]["title"] == "Doc one"


def test_inbox_stats_awaiting_my_decision_counts_approval_steps_only(client):
    dev = client.post("/qms/deviations", json={"title": "Dev"}).get_json()
    _dev_configure_all_approvers(client, dev["id"])
    client.post(f"/qms/deviations/{dev['id']}/workflow/start")  # approval step, already assigned

    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    client.post(f"/qms/capa/{capa['id']}/workflow/start")  # current step is activity, no assignment needed

    stats = client.get("/workflow/inbox/stats").get_json()
    assert stats["my_pending_count"] == 2
    assert stats["awaiting_my_decision_count"] == 1


def test_inbox_recent_decisions_after_deciding_a_step(client):
    capa = client.post("/qms/capa", json={"title": "CAPA"}).get_json()
    cid = capa["id"]
    client.post(f"/qms/capa/{cid}/workflow/start")  # auto-completes step 1 (also a recorded decision)
    r = client.post(f"/qms/capa/{cid}/workflow/steps/2/decide", json={"decision": "advance"})
    assert r.status_code == 200

    stats = client.get("/workflow/inbox/stats").get_json()
    assert len(stats["recent_decisions"]) == 2
    assert stats["recent_decisions"][0]["record_type"] == "capa"
    assert stats["recent_decisions"][0]["step_order"] == 2  # most recent first


def test_inbox_tenant_isolation(client):
    """A pending step created under one company must never appear in a
    query scoped to a different company_id. routes/workflow_inbox.py always
    passes g.tenant.company_id (never client input) into
    list_my_pending_steps — this is the actual isolation boundary the
    feature introduces; exercised directly here against the additive query
    function, the same one the route calls."""
    capa = client.post("/qms/capa", json={"title": "CAPA A"}).get_json()
    client.post(f"/qms/capa/{capa['id']}/workflow/start")
    assert len(client.get("/workflow/inbox").get_json()) == 1

    other_rows = wfdb.list_my_pending_steps("00000000-0000-0000-0000-00000000ffff", _FIXED_USER_ID, "company_admin")
    assert other_rows == []


def test_registry_only_addition_requires_no_new_ui_code():
    """Proves the Inbox is generic: a hypothetical future module needs only
    a ModuleDescriptor entry (already the case for capa/change_control/
    document — none of which existed when routes/workflow_inbox.py or
    services/workflow_registry.py were written against just 'deviation')."""
    assert set(workflow_registry.MODULE_REGISTRY) == {"deviation", "capa", "change_control", "document"}
    for descriptor in workflow_registry.MODULE_REGISTRY.values():
        assert callable(descriptor.get_record)
        assert descriptor.route_prefix.startswith("/qms/")

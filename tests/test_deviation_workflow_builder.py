"""
tests/test_deviation_workflow_builder.py — Deviation UI & Workflow Refactor:
the Workflow Builder (qms_deviation_workflow_steps) and its compilation into
a per-deviation dynamic workflow template at Submit for Review.

services/workflow_engine.py itself is never touched by this feature — these
tests exercise the route-level logic in routes/qms_deviations.py that builds
a fresh template from the configured steps and hands it to the unmodified
engine, plus the qms_deviation_database.py CRUD backing the builder.
"""

_FIXED_USER_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py::_TEST_TENANT.user_id


def _create_deviation(client, title="Temp excursion"):
    r = client.post("/qms/deviations", json={"title": title})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_create_deviation_seeds_default_workflow_steps(client):
    dev = _create_deviation(client)
    r = client.get(f"/qms/deviations/{dev['id']}/workflow-builder")
    assert r.status_code == 200
    steps = r.get_json()
    assert [s["step_name"] for s in steps] == ["Production Head", "QA Manager", "QA Approval"]
    assert [s["step_order"] for s in steps] == [2, 3, 4]
    assert [s["is_qa_approval"] for s in steps] == [0, 0, 1]
    assert steps[1]["department"] == "QA"


def test_workflow_builder_add_remove_reorder_steps(client):
    dev = _create_deviation(client)
    did = dev["id"]
    steps = client.get(f"/qms/deviations/{did}/workflow-builder").get_json()

    # Insert a new step before QA Approval, reorder, and drop one non-final step.
    steps.insert(1, {"step_name": "Engineering Review", "department": "Engineering",
                      "approver_user_id": "", "approver_display_name": ""})
    del steps[0]  # drop "Production Head"

    r = client.put(f"/qms/deviations/{did}/workflow-builder", json={"steps": steps})
    assert r.status_code == 200, r.get_json()
    updated = r.get_json()
    assert [s["step_name"] for s in updated] == ["Engineering Review", "QA Manager", "QA Approval"]
    assert [s["step_order"] for s in updated] == [2, 3, 4]
    assert updated[-1]["is_qa_approval"] == 1


def test_workflow_builder_forces_last_step_qa_approval(client):
    """Even if the client tries to rename/unflag the last row, the server
    forces it back to the mandatory QA Approval gate."""
    dev = _create_deviation(client)
    did = dev["id"]
    r = client.put(f"/qms/deviations/{did}/workflow-builder", json={"steps": [
        {"step_name": "Solo Reviewer", "department": "QA", "approver_user_id": "", "approver_display_name": ""},
    ]})
    assert r.status_code == 200
    updated = r.get_json()
    assert len(updated) == 1
    assert updated[0]["step_name"] == "QA Approval"
    assert updated[0]["is_qa_approval"] == 1


def test_workflow_builder_rejects_empty_steps(client):
    dev = _create_deviation(client)
    r = client.put(f"/qms/deviations/{dev['id']}/workflow-builder", json={"steps": []})
    assert r.status_code == 400


def test_workflow_builder_locked_once_deviation_leaves_draft(client):
    dev = _create_deviation(client)
    did = dev["id"]
    assert client.post(f"/qms/deviations/{did}/workflow/start").status_code == 201

    steps = client.get(f"/qms/deviations/{did}/workflow-builder").get_json()
    r = client.put(f"/qms/deviations/{did}/workflow-builder", json={"steps": steps})
    assert r.status_code == 409


def test_start_workflow_builds_dynamic_template_and_preassigns_configured_approvers(client):
    dev = _create_deviation(client)
    did = dev["id"]
    steps = client.get(f"/qms/deviations/{did}/workflow-builder").get_json()
    # Pre-assign an approver for the first step only; leave the rest blank —
    # matches the manual "Assign Approver" flow still being available.
    steps[0]["approver_user_id"] = _FIXED_USER_ID
    steps[0]["approver_display_name"] = "Test User"
    client.put(f"/qms/deviations/{did}/workflow-builder", json={"steps": steps})

    r = client.post(f"/qms/deviations/{did}/workflow/start")
    assert r.status_code == 201, r.get_json()

    wf = client.get(f"/qms/deviations/{did}/workflow").get_json()
    by_order = {s["step_order"]: s for s in wf["steps"]}
    assert by_order[2]["step_type"] == "approval"
    assert by_order[2]["approvers"][0]["user_id"] == _FIXED_USER_ID
    assert by_order[3]["approvers"] == []  # not configured — awaits manual assignment
    assert by_order[4]["step_key"] == "qa_approval"
    # Fixed tail (unchanged from DEVIATION_LIFECYCLE_V2), renumbered after the
    # 3 configured Review steps + the implicit "submitted" step.
    assert by_order[5]["step_key"] == "evidence_collection"
    assert by_order[6]["step_key"] == "qa_review"
    assert by_order[7]["step_key"] == "final_approval"
    assert by_order[8]["step_key"] == "effectiveness_check"
    assert by_order[9]["step_key"] == "closed"


def test_full_review_chain_still_reaches_qa_approval_and_unlocks_investigation(client):
    """End-to-end: default (unconfigured-approver) workflow behaves exactly
    like the old fixed chain once approvers are assigned manually per step —
    same mechanics tests/test_qms_routes.py::_dev_reach_qa_approval relies on."""
    dev = _create_deviation(client)
    did = dev["id"]
    assert client.post(f"/qms/deviations/{did}/workflow/start").status_code == 201
    for step_order in (2, 3, 4):
        r = client.post(f"/qms/deviations/{did}/workflow/steps/{step_order}/assign",
                         json={"approvers": [{"user_id": _FIXED_USER_ID, "display_name": "Test User"}]})
        assert r.status_code == 200, r.get_json()
        r = client.post(f"/qms/deviations/{did}/workflow/steps/{step_order}/decide", json={"decision": "approve"})
        assert r.status_code == 200, r.get_json()

    assert client.get(f"/qms/deviations/{did}").get_json()["investigation_unlocked"] is True


def test_overview_update_still_accepts_qa_reviewer_field_for_backward_compat(client):
    """The UI no longer sends qa_reviewer (Overview no longer shows it —
    reviewer assignment now belongs to the Workflow Builder), but the field
    and column are kept for backward compatibility with any other caller."""
    dev = _create_deviation(client)
    r = client.put(f"/qms/deviations/{dev['id']}", json={"qa_reviewer": "Legacy Reviewer"})
    assert r.status_code == 200
    assert r.get_json()["qa_reviewer"] == "Legacy Reviewer"

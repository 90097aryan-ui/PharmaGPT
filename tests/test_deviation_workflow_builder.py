"""
tests/test_deviation_workflow_builder.py — Deviation UI & Workflow Refactor:
the Workflow Builder (qms_deviation_workflow_steps + the fixed CAPA-phase
approver columns on qms_deviations) and its compilation into a per-deviation
dynamic workflow template at Submit for Review.

services/workflow_engine.py itself is never touched by this feature — these
tests exercise the route-level logic in routes/qms_deviations.py that builds
a fresh template from the configured steps and hands it to the unmodified
engine, plus the qms_deviation_database.py CRUD backing the builder.

The Workflow Builder is the *only* place a deviation's approvers are
configured — there is no runtime "Assign Approver" action. GET/PUT
/workflow-builder both return/accept {"steps": [...], "capa_phase": {...}}:
"steps" is the dynamic, reorderable Review chain (always ending in the
mandatory QA Approval gate); "capa_phase" is the two fixed, single-approver
CAPA-phase steps (QA Review, Final Approval) that follow Investigation.
"""

_FIXED_USER_ID = "00000000-0000-0000-0000-000000000001"  # tests/conftest.py::_TEST_TENANT.user_id

_CAPA_PHASE = {
    "qa_review_approver_user_id": _FIXED_USER_ID,
    "qa_review_approver_display_name": "Test User",
    "final_approval_approver_user_id": _FIXED_USER_ID,
    "final_approval_approver_display_name": "Test User",
}


def _create_deviation(client, title="Temp excursion"):
    r = client.post("/qms/deviations", json={"title": title})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _get_builder(client, did):
    r = client.get(f"/qms/deviations/{did}/workflow-builder")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _put_builder(client, did, steps, capa_phase=None):
    r = client.put(f"/qms/deviations/{did}/workflow-builder",
                    json={"steps": steps, "capa_phase": capa_phase or {}})
    return r


def _configure_all_step_approvers(client, did, user_id=_FIXED_USER_ID, display_name="Test User"):
    """Fill in approver_user_id/display_name for every currently-configured
    Review-chain step plus both CAPA-phase steps (the only places approvers
    can be set — there is no runtime "Assign Approver" action) and save.
    Returns the saved {"steps": [...], "capa_phase": {...}}."""
    builder = _get_builder(client, did)
    for s in builder["steps"]:
        s["approver_user_id"] = user_id
        s["approver_display_name"] = display_name
    capa_phase = {
        "qa_review_approver_user_id": user_id,
        "qa_review_approver_display_name": display_name,
        "final_approval_approver_user_id": user_id,
        "final_approval_approver_display_name": display_name,
    }
    r = _put_builder(client, did, builder["steps"], capa_phase)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_create_deviation_seeds_default_workflow_steps(client):
    dev = _create_deviation(client)
    builder = _get_builder(client, dev["id"])
    steps = builder["steps"]
    assert [s["step_name"] for s in steps] == ["Production Head", "QA Manager", "QA Approval"]
    assert [s["step_order"] for s in steps] == [2, 3, 4]
    assert [s["is_qa_approval"] for s in steps] == [0, 0, 1]
    assert steps[1]["department"] == "QA"
    # CAPA-phase approvers default to unset.
    assert builder["capa_phase"] == {
        "qa_review_approver_user_id": "", "qa_review_approver_display_name": "",
        "final_approval_approver_user_id": "", "final_approval_approver_display_name": "",
    }


def test_workflow_builder_add_remove_reorder_steps(client):
    dev = _create_deviation(client)
    did = dev["id"]
    steps = _get_builder(client, did)["steps"]

    # Insert a new step before QA Approval, reorder, and drop one non-final step.
    steps.insert(1, {"step_name": "Engineering Review", "department": "Engineering",
                      "approver_user_id": "", "approver_display_name": ""})
    del steps[0]  # drop "Production Head"

    r = _put_builder(client, did, steps)
    assert r.status_code == 200, r.get_json()
    updated = r.get_json()["steps"]
    assert [s["step_name"] for s in updated] == ["Engineering Review", "QA Manager", "QA Approval"]
    assert [s["step_order"] for s in updated] == [2, 3, 4]
    assert updated[-1]["is_qa_approval"] == 1


def test_workflow_builder_forces_last_step_qa_approval(client):
    """Even if the client tries to rename/unflag the last row, the server
    forces it back to the mandatory QA Approval gate."""
    dev = _create_deviation(client)
    did = dev["id"]
    r = _put_builder(client, did, [
        {"step_name": "Solo Reviewer", "department": "QA", "approver_user_id": "", "approver_display_name": ""},
    ])
    assert r.status_code == 200
    updated = r.get_json()["steps"]
    assert len(updated) == 1
    assert updated[0]["step_name"] == "QA Approval"
    assert updated[0]["is_qa_approval"] == 1


def test_workflow_builder_rejects_empty_steps(client):
    dev = _create_deviation(client)
    r = _put_builder(client, dev["id"], [])
    assert r.status_code == 400


def test_workflow_builder_saves_capa_phase_approvers(client):
    dev = _create_deviation(client)
    did = dev["id"]
    steps = _get_builder(client, did)["steps"]
    r = _put_builder(client, did, steps, _CAPA_PHASE)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["capa_phase"] == _CAPA_PHASE

    reloaded = _get_builder(client, did)
    assert reloaded["capa_phase"] == _CAPA_PHASE


def test_workflow_builder_locked_once_deviation_leaves_draft(client):
    dev = _create_deviation(client)
    did = dev["id"]
    _configure_all_step_approvers(client, did)
    assert client.post(f"/qms/deviations/{did}/workflow/start").status_code == 201

    steps = _get_builder(client, did)["steps"]
    r = _put_builder(client, did, steps, _CAPA_PHASE)
    assert r.status_code == 409


def test_start_workflow_builds_dynamic_template_and_auto_assigns_every_configured_approver(client):
    """Submitting a fully-configured workflow must assign every named-approval
    step's approver immediately — every Review-chain step and both CAPA-phase
    steps — with no separate runtime assignment call, since none exists for
    deviations anymore."""
    dev = _create_deviation(client)
    did = dev["id"]
    _configure_all_step_approvers(client, did)

    r = client.post(f"/qms/deviations/{did}/workflow/start")
    assert r.status_code == 201, r.get_json()

    wf = client.get(f"/qms/deviations/{did}/workflow").get_json()
    by_order = {s["step_order"]: s for s in wf["steps"]}
    assert by_order[2]["step_type"] == "approval"
    assert by_order[2]["approvers"][0]["user_id"] == _FIXED_USER_ID  # the first approval step, auto-assigned
    assert by_order[3]["approvers"][0]["user_id"] == _FIXED_USER_ID  # a later step, also already assigned
    assert by_order[4]["approvers"][0]["user_id"] == _FIXED_USER_ID  # QA Approval, also already assigned
    assert by_order[4]["step_key"] == "qa_approval"
    # Fixed tail (unchanged from DEVIATION_LIFECYCLE_V2), renumbered after the
    # 3 configured Review steps + the implicit "submitted" step.
    assert by_order[5]["step_key"] == "evidence_collection"
    assert by_order[6]["step_key"] == "qa_review"
    assert by_order[6]["approvers"][0]["user_id"] == _FIXED_USER_ID  # CAPA-phase, also auto-assigned
    assert by_order[7]["step_key"] == "final_approval"
    assert by_order[7]["approvers"][0]["user_id"] == _FIXED_USER_ID  # CAPA-phase, also auto-assigned
    assert by_order[8]["step_key"] == "effectiveness_check"
    assert by_order[9]["step_key"] == "closed"


def test_capa_phase_approvers_stay_correctly_assigned_when_review_chain_length_changes(client):
    """QA Review/Final Approval's step_order shifts with however many Review
    steps were configured — proves the post-start assignment looks them up by
    step_key rather than assuming a fixed order."""
    dev = _create_deviation(client)
    did = dev["id"]
    steps = _get_builder(client, did)["steps"]
    steps.insert(1, {"step_name": "Engineering Review", "department": "Engineering",
                      "approver_user_id": _FIXED_USER_ID, "approver_display_name": "Test User"})
    for s in steps:
        s["approver_user_id"] = _FIXED_USER_ID
        s["approver_display_name"] = "Test User"
    _put_builder(client, did, steps, _CAPA_PHASE)

    assert client.post(f"/qms/deviations/{did}/workflow/start").status_code == 201

    wf = client.get(f"/qms/deviations/{did}/workflow").get_json()
    by_key = {s["step_key"]: s for s in wf["steps"]}
    assert by_key["qa_review"]["step_order"] == 7  # shifted by the extra Review step
    assert by_key["qa_review"]["approvers"][0]["user_id"] == _FIXED_USER_ID
    assert by_key["final_approval"]["step_order"] == 8
    assert by_key["final_approval"]["approvers"][0]["user_id"] == _FIXED_USER_ID


def test_workflow_start_blocked_when_any_configured_step_has_no_approver(client):
    """With the runtime "Assign Approver" action removed, an unassigned step
    must never be allowed to reach the workflow — it would be permanently
    stuck with no one able to decide it. Submission is blocked up front
    instead, and the deviation stays in Draft so the Workflow Builder can
    still be corrected."""
    dev = _create_deviation(client)
    did = dev["id"]
    steps = _get_builder(client, did)["steps"]
    steps[0]["approver_user_id"] = _FIXED_USER_ID
    steps[0]["approver_display_name"] = "Test User"
    # steps[1] ("QA Manager"), steps[2] ("QA Approval"), and both CAPA-phase
    # steps left unassigned.
    _put_builder(client, did, steps)

    r = client.post(f"/qms/deviations/{did}/workflow/start")
    assert r.status_code == 409
    error = r.get_json()["error"]
    assert "QA Manager" in error
    assert "QA Approval" in error
    assert "QA Review" in error
    assert "Final Approval" in error

    dev_after = client.get(f"/qms/deviations/{did}").get_json()
    assert dev_after["status"] == "Draft"
    assert client.get(f"/qms/deviations/{did}/workflow").get_json()["instance"] is None


def test_workflow_start_blocked_when_only_capa_phase_is_unconfigured(client):
    """Every Review-chain step can be fully configured and submission is
    still blocked if QA Review / Final Approval have no approver."""
    dev = _create_deviation(client)
    did = dev["id"]
    steps = _get_builder(client, did)["steps"]
    for s in steps:
        s["approver_user_id"] = _FIXED_USER_ID
        s["approver_display_name"] = "Test User"
    _put_builder(client, did, steps)  # capa_phase left unset

    r = client.post(f"/qms/deviations/{did}/workflow/start")
    assert r.status_code == 409
    error = r.get_json()["error"]
    assert "QA Review" in error
    assert "Final Approval" in error
    assert "QA Manager" not in error


def test_runtime_workflow_step_assign_endpoint_no_longer_exists_for_deviations(client):
    """The legacy manual "Assign Approver" backend path is removed for
    deviations — the Workflow Builder is now the only place approvers are
    configured (services/workflow_engine.py's assign_approvers() itself is
    untouched and still backs CAPA/Change Control/Document assignment)."""
    dev = _create_deviation(client)
    did = dev["id"]
    _configure_all_step_approvers(client, did)
    client.post(f"/qms/deviations/{did}/workflow/start")

    r = client.post(f"/qms/deviations/{did}/workflow/steps/2/assign",
                     json={"approvers": [{"user_id": _FIXED_USER_ID, "display_name": "Test User"}]})
    assert r.status_code == 404


def test_full_lifecycle_reaches_closed_with_no_runtime_assignment_at_any_step(client):
    """End-to-end regression: a fully-configured workflow (Review chain +
    both CAPA-phase steps) runs from Submit through Closed using only
    Workflow Builder configuration and decide() calls — no runtime
    assignment call anywhere in the lifecycle."""
    dev = _create_deviation(client)
    did = dev["id"]
    _configure_all_step_approvers(client, did)
    assert client.post(f"/qms/deviations/{did}/workflow/start").status_code == 201

    for step_order in (2, 3, 4):  # Production Head, QA Manager, QA Approval
        r = client.post(f"/qms/deviations/{did}/workflow/steps/{step_order}/decide", json={"decision": "approve"})
        assert r.status_code == 200, r.get_json()
    assert client.get(f"/qms/deviations/{did}").get_json()["investigation_unlocked"] is True

    r = client.post(f"/qms/deviations/{did}/workflow/steps/5/decide", json={"decision": "advance"})  # Investigation
    assert r.status_code == 200, r.get_json()

    for step_order in (6, 7):  # QA Review, Final Approval
        r = client.post(f"/qms/deviations/{did}/workflow/steps/{step_order}/decide", json={"decision": "approve"})
        assert r.status_code == 200, r.get_json()

    r = client.post(f"/qms/deviations/{did}/workflow/steps/8/decide", json={"decision": "advance"})  # Effectiveness Check
    assert r.status_code == 200, r.get_json()
    r = client.post(f"/qms/deviations/{did}/workflow/steps/9/decide", json={"decision": "advance"})  # Closure
    assert r.status_code == 200, r.get_json()

    assert client.get(f"/qms/deviations/{did}").get_json()["status"] == "Closed"


def test_get_workflow_builder_reflects_saved_state_on_a_separate_request(client):
    """GET must reload the persisted rows from qms_deviation_workflow_steps —
    not regenerate the default seed — even when read back on a request that
    is entirely separate from the PUT that saved them."""
    dev = _create_deviation(client)
    did = dev["id"]
    steps = _get_builder(client, did)["steps"]
    steps.insert(1, {"step_name": "Engineering Review", "department": "Engineering",
                      "approver_user_id": "", "approver_display_name": ""})
    put_result = _put_builder(client, did, steps, _CAPA_PHASE).get_json()

    # A fresh GET (simulating a reload / tab switch) must match the PUT
    # response exactly, not fall back to the 3-step default.
    reloaded = _get_builder(client, did)
    assert [s["step_name"] for s in reloaded["steps"]] == [s["step_name"] for s in put_result["steps"]]
    assert [s["step_name"] for s in reloaded["steps"]] == ["Production Head", "Engineering Review", "QA Manager", "QA Approval"]
    assert reloaded["capa_phase"] == _CAPA_PHASE


def test_submit_compiles_customized_saved_steps_not_the_default_chain(client):
    """Submit must build the runtime template from whatever is currently
    saved in qms_deviation_workflow_steps — proving it does not silently
    fall back to (or recreate) the 3-step default once the initiator has
    customized the chain."""
    dev = _create_deviation(client)
    did = dev["id"]
    steps = _get_builder(client, did)["steps"]
    # Drop "Production Head", rename "QA Manager", add a new department step —
    # nothing here matches the default seed's names/count anymore.
    steps = steps[1:]  # drop Production Head
    steps[0]["step_name"] = "Quality Lead Review"
    steps.insert(1, {"step_name": "Engineering Sign-off", "department": "Engineering",
                      "approver_user_id": "", "approver_display_name": ""})
    for s in steps:
        s["approver_user_id"] = _FIXED_USER_ID
        s["approver_display_name"] = "Test User"
    r = _put_builder(client, did, steps, _CAPA_PHASE)
    assert r.status_code == 200, r.get_json()

    assert client.post(f"/qms/deviations/{did}/workflow/start").status_code == 201

    wf = client.get(f"/qms/deviations/{did}/workflow").get_json()
    by_order = {s["step_order"]: s["step_name"] for s in wf["steps"] if s["step_order"] in (2, 3, 4)}
    assert by_order == {2: "Quality Lead Review", 3: "Engineering Sign-off", 4: "QA Approval"}
    # The original default names must not appear anywhere in the compiled chain.
    names = [s["step_name"] for s in wf["steps"]]
    assert "Production Head" not in names
    assert "QA Manager" not in names


def test_overview_update_still_accepts_qa_reviewer_field_for_backward_compat(client):
    """The UI no longer sends qa_reviewer (Overview no longer shows it —
    reviewer assignment now belongs to the Workflow Builder), but the field
    and column are kept for backward compatibility with any other caller."""
    dev = _create_deviation(client)
    r = client.put(f"/qms/deviations/{dev['id']}", json={"qa_reviewer": "Legacy Reviewer"})
    assert r.status_code == 200
    assert r.get_json()["qa_reviewer"] == "Legacy Reviewer"

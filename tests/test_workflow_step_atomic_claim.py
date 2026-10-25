"""A workflow step can be decided exactly once: the second of two racing
decisions (gunicorn runs 2 workers x 4 threads) must not overwrite the first."""

from pharmagpt import qms_workflow_database as wfdb


def test_second_decision_on_same_step_is_rejected(db_path):
    tpl = wfdb.create_template("atomic_claim_test", "Atomic", "capa")
    tstep = wfdb.create_template_step(tpl["id"], 1, "qa", "QA", "approval", "reviewer_qa", "Approved")
    inst = wfdb.create_instance(tpl["id"], "capa", 1, "c1")
    step = wfdb.create_instance_step(inst["id"], tstep)

    assert wfdb.update_instance_step(step["id"], {"status": "approved", "decided_by": "A"}, only_if_open=True)
    assert not wfdb.update_instance_step(step["id"], {"status": "rejected", "decided_by": "B"}, only_if_open=True)

    final = wfdb.get_instance_step(inst["id"], 1)
    assert (final["status"], final["decided_by"]) == ("approved", "A")

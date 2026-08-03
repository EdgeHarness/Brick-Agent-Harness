"""The permissive pre-S5 scoring surface is no longer executable."""
from domains.office_demo import tasks
from domains.office_demo.pack import PACK


def test_task_metadata_contains_no_unversioned_grading_callable():
    assert tasks.TASKS
    assert all("grade" not in task for task in tasks.TASKS)


def test_every_office_task_binds_a_named_versioned_strict_grader():
    assert len(PACK.tasks) == len(tasks.TASKS) == 12
    for task in PACK.tasks:
        assert task.grader.id == f"office_demo.{task.id}"
        assert task.grader.version == "1.0.0"
        assert len(task.grader.checks) == 5

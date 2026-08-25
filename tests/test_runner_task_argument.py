"""A task id passed where task text belongs.

The two are easy to confuse and the resulting run is not obviously broken: the
model receives the id as its entire task, produces well-formed calls with
empty arguments, and burns its budget looking like a model failure. That cost
a real measurement and its write-up before anyone noticed what had happened,
so the confusion is worth one comparison at startup.
"""
import pytest

from harness.domain import load_domain
from webui import runner


def _args(task):
    return ["--run-id", "t", "--agent", "1b", "--task", task]


def test_a_task_id_is_refused_and_the_real_prompt_offered(capsys):
    with pytest.raises(SystemExit):
        runner.main(_args("cal_add"))
    message = capsys.readouterr().err
    assert "task text, not a task id" in message
    # The whole point is handing back what was meant, so the message has to
    # carry the prompt itself rather than telling the reader to go find it.
    prompt = next(t for t in load_domain("office_demo").tasks
                  if t.id == "cal_add").prompt
    assert prompt in message


def test_surrounding_whitespace_does_not_defeat_the_check(capsys):
    with pytest.raises(SystemExit):
        runner.main(_args("  cal_add\n"))
    assert "task text, not a task id" in capsys.readouterr().err


def test_every_task_id_in_the_domain_is_covered():
    """Not just the one that caused the trouble."""
    for task in load_domain("office_demo").tasks:
        with pytest.raises(SystemExit):
            runner.main(_args(task.id))


def test_real_task_text_is_not_refused(monkeypatch):
    """The check must not stand between a person and an ordinary run.

    Stopped at the very next step, since this suite reaches no network and
    a real run starts threads. The point is only that the id comparison let
    it through.
    """
    sentinel = RuntimeError("got past the task check")

    def stop_here(*args, **kwargs):
        raise sentinel

    monkeypatch.setattr(runner, "agent_runtime_paths", stop_here)
    with pytest.raises(RuntimeError) as caught:
        runner.main(_args("Add a meeting called 'Design sync' on Tuesday."))
    assert caught.value is sentinel


def test_text_that_merely_contains_an_id_is_allowed(monkeypatch):
    sentinel = RuntimeError("got past the task check")
    monkeypatch.setattr(runner, "agent_runtime_paths",
                        lambda *a, **k: (_ for _ in ()).throw(sentinel))
    with pytest.raises(RuntimeError):
        runner.main(_args("Do the cal_add thing for me on Tuesday"))

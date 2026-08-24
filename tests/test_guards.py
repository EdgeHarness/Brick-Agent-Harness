"""Unit tests for the advisory guards, on hand-built states with no run.

Every guard has one test proving it FIRES: ported without that, a guard whose
declarations are missing imports, runs, passes its tests and never speaks,
which is worse than not porting it.
"""
import datetime
import json

from harness import agent, guards
from harness.domain import load_domain
from harness.runtime import RunConfig

TODAY = datetime.date(2026, 7, 20)  # a Monday

_pack = load_domain("office_demo")
WRITE_TOOLS = frozenset(
    n for n in _pack.registry.names() if _pack.default_policy.is_mutating(n)
)


def make_state(tmp_path, task="Do the task", plan="", llm=None, history=""):
    return guards.GuardState(
        llm, agent.Episode(), [], task,
        registry=_pack.registry, write_tools=WRITE_TOOLS, plan=plan,
        artifact_dir=tmp_path, today=TODAY, history=history,
    )


# ------------------------------------------------------------ wrong_date ----

def test_wrong_date_fires_on_a_write_with_the_wrong_day(tmp_path):
    g = make_state(tmp_path, task="Add the review meeting on Wednesday")
    g.name, g.args = "add_event", {"date": "2026-07-27"}  # a Monday
    message = guards.guard_wrong_date(g)
    assert message and "WRONG DATE" in message and "2026-07-22" in message
    assert g.ep.invalid_calls == 1


def test_wrong_date_leaves_reads_alone(tmp_path):
    g = make_state(tmp_path, task="Add the review meeting on Wednesday")
    g.name, g.args = "list_events", {"date": "2026-07-27"}
    assert guards.guard_wrong_date(g) is None


def test_wrong_date_abstains_when_the_task_names_two_dates(tmp_path):
    g = make_state(tmp_path, task="Move my Wednesday meeting to Friday")
    g.name, g.args = "add_event", {"date": "2026-07-27"}
    assert guards.guard_wrong_date(g) is None


# ------------------------------------------------------- unplanned_write ----

def test_unplanned_write_fires_once_then_lets_the_call_run(tmp_path):
    g = make_state(tmp_path, task="List my emails",
                   plan="1. list_emails - look")
    g.name, g.args = "send_email", {}
    message = guards.guard_unplanned_write(g)
    assert message and "send_email" in message
    # question once, never forbid: the repeated call is not questioned again
    assert guards.guard_unplanned_write(g) is None


def test_unplanned_write_replans_once_after_a_read(tmp_path):
    class OneReply:
        def chat(self, *a, **k):
            return json.dumps(
                {"steps": [{"tool": "send_email", "what": "data asked for it"}]}
            )

    g = make_state(tmp_path, task="Read the email and do what it asks",
                   plan="1. read_email - open it", llm=OneReply())
    g.looked = True
    g.name, g.args = "send_email", {}
    # the revised plan names the write, so the guard stands down entirely
    assert guards.guard_unplanned_write(g) is None
    assert g.replanned is True
    assert "send_email" in g.planned_set


# ----------------------------------------------------------- unread_file ----

def test_unread_file_fires_when_a_named_file_sits_unopened(tmp_path):
    (tmp_path / "q3_raw.xlsx").write_text("data")
    g = make_state(tmp_path)
    g.mentioned_files = {"q3_raw.xlsx"}
    g.name, g.args = "create_spreadsheet", {}
    message = guards.guard_unread_file(g)
    assert message and "q3_raw.xlsx" in message and "read_spreadsheet" in message
    # questioned files are not questioned twice
    assert guards.guard_unread_file(g) is None


def test_unread_file_abstains_when_the_file_does_not_exist(tmp_path):
    g = make_state(tmp_path)
    g.mentioned_files = {"q3_raw.xlsx"}
    g.name, g.args = "create_spreadsheet", {}
    assert guards.guard_unread_file(g) is None


def test_unread_file_abstains_once_the_file_was_opened(tmp_path):
    (tmp_path / "q3_raw.xlsx").write_text("data")
    g = make_state(tmp_path)
    g.mentioned_files = {"q3_raw.xlsx"}
    g.opened_files = {"q3_raw.xlsx"}
    g.name, g.args = "create_spreadsheet", {}
    assert guards.guard_unread_file(g) is None


# ----------------------------------------------------- read_before_write ----

def test_read_before_write_fires_once_before_anything_was_read(tmp_path):
    g = make_state(tmp_path,
                   plan="1. read_email - open it\n2. send_email - reply")
    assert g.first_read_planned == "read_email"
    g.name, g.args = "send_email", {}
    message = guards.guard_read_before_write(g)
    assert message and "read_email" in message
    assert guards.guard_read_before_write(g) is None  # nudged only once


def test_read_before_write_abstains_after_a_read_landed(tmp_path):
    g = make_state(tmp_path,
                   plan="1. read_email - open it\n2. send_email - reply")
    g.looked = True
    g.name, g.args = "send_email", {}
    assert guards.guard_read_before_write(g) is None


# ------------------------------------------------------------- done_echo ----

def test_done_echo_fires_once_on_a_copied_span(tmp_path):
    history = "USER: hi\nASSISTANT: I summarized the three meetings and messaged Jordan about the schedule change"
    g = make_state(tmp_path, history=history)
    g.summary = ("I summarized the three meetings and messaged Jordan "
                 "about the schedule change")
    message = guards.guard_done_echo(g)
    assert message and "repeats" in message
    assert guards.guard_done_echo(g) is None  # questioned only once


def test_done_echo_abstains_on_a_fresh_summary(tmp_path):
    g = make_state(tmp_path, history="ASSISTANT: I archived the July receipts folder yesterday afternoon for you")
    g.summary = "Sent the weekly status email to the team and added the sync"
    assert guards.guard_done_echo(g) is None


# ---------------------------------------------------------- run_guards ----

def test_first_guard_to_speak_wins_and_later_side_effects_do_not_happen(tmp_path):
    # Both wrong_date and unplanned_write would fire; only the first speaks.
    g = make_state(tmp_path, task="Add the review meeting on Wednesday",
                   plan="1. list_events - look")
    g.name, g.args = "add_event", {"date": "2026-07-27"}
    questioned = guards.run_guards(g)
    assert questioned is not None and questioned[0] == "wrong_date"
    assert g.questioned_writes == set()  # unplanned_write never ran


def test_run_guards_returns_none_when_every_guard_abstains(tmp_path):
    g = make_state(tmp_path)
    g.name, g.args = "list_emails", {}
    assert guards.run_guards(g) is None


# ----------------------------------------------------------- loop wiring ----

def test_guards_are_off_by_default_in_run_config():
    config = RunConfig(condition="harness", max_calls=5, today=TODAY)
    assert config.guards is False


def _reply(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def test_harness_loop_questions_an_unplanned_write(attempt_factory):
    attempt = attempt_factory(guards=True)
    llm = agent_test_llm([
        json.dumps({"steps": [{"tool": "list_emails", "what": "look"}]}),
        _reply("send_message", to="alex", text="hi"),   # unplanned: questioned
        _reply("done", summary="nothing to do"),
        json.dumps({"complete": True, "missing": ""}),  # verifier
    ])
    episode = agent.run_harness(llm, "List my emails", attempt)

    assert episode.finished is True
    notes = [n for n in episode.transcript if n["kind"] == "guard"]
    assert [n["content"] for n in notes] == ["unplanned_write"]
    assert all(a["tool"] != "send_message" for a in attempt.actions)


def test_harness_loop_runs_a_questioned_call_when_repeated(attempt_factory):
    attempt = attempt_factory(guards=True)
    llm = agent_test_llm([
        json.dumps({"steps": [{"tool": "list_emails", "what": "look"}]}),
        _reply("send_message", to="alex", text="hi"),   # questioned
        _reply("send_message", to="alex", text="hi"),   # repeated: runs
        _reply("done", summary="messaged alex"),
        json.dumps({"complete": True, "missing": ""}),
    ])
    episode = agent.run_harness(llm, "List my emails", attempt)

    assert episode.finished is True
    assert any(a["tool"] == "send_message" and a["ok"] for a in attempt.actions)


def test_harness_loop_ignores_guards_when_disabled(attempt_factory):
    attempt = attempt_factory()
    llm = agent_test_llm([
        json.dumps({"steps": [{"tool": "list_emails", "what": "look"}]}),
        _reply("send_message", to="alex", text="hi"),   # runs unquestioned
        _reply("done", summary="messaged alex"),
        json.dumps({"complete": True, "missing": ""}),
    ])
    episode = agent.run_harness(llm, "List my emails", attempt)

    assert episode.finished is True
    assert not [n for n in episode.transcript if n["kind"] == "guard"]
    assert any(a["tool"] == "send_message" and a["ok"] for a in attempt.actions)


def agent_test_llm(replies):
    class Scripted:
        def __init__(self):
            self.replies = list(replies)

        def chat(self, messages, force_json=False, num_predict=700,
                 role=None, keep_alive=None):
            if not self.replies:
                raise AssertionError("scripted LLM ran out of replies")
            return self.replies.pop(0)

    return Scripted()

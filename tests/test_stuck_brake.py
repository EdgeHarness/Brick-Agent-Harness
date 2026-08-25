"""Ending a run that has stopped reaching a tool.

Measured on `llama3.2:1b` against the office task `cal_add`: it forms the call
correctly, the tool runs, and then it cannot stop. Two runs of three spent the
remaining seventeen calls re-calling the same tool with an unknown parameter
and no required ones, never calling `done`, while the feedback each round said
to call `done`. The work was already finished. Only the budget was still
burning.

The shape of that loop is why the counter resets on a tool RUNNING rather than
on arguments validating: the failing pattern alternates an invalid call with a
suppressed identical repeat, so a strictly consecutive invalid counter never
climbs past one. A first version of this made exactly that mistake and did not
fire on the run it was written for.

This is a cost brake, not a success fix. Whatever the run already did stays
done, because the grader reads the world rather than whether `done` was called.
"""
import json

import pytest

from harness import agent
from harness.profiles import DEFAULT, Profile


def _reply(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def scripted(replies):
    class Scripted:
        def __init__(self):
            self.replies = list(replies)
            self.used = 0

        def chat(self, messages, force_json=False, num_predict=700,
                 role=None, keep_alive=None):
            self.used += 1
            if not self.replies:
                # The point of several of these tests is that the loop stops
                # before it would have run out, so running out is a failure.
                raise AssertionError("the loop kept going and ran out of replies")
            return self.replies.pop(0)

    return Scripted()


BRAKE = Profile(plan=False, plan_max_steps=0, verify_rounds=0,
                invalid_streak_break=3, max_calls=18)
NO_BRAKE = Profile(plan=False, plan_max_steps=0, verify_rounds=0,
                   invalid_streak_break=0, max_calls=18)


def _run(attempt_factory, profile, replies):
    attempt = attempt_factory(profile=profile, max_calls=profile.max_calls,
                              verifier_rounds=0)
    llm = scripted(replies)
    episode = agent.run_harness(llm, "Add a meeting", attempt)
    return episode, attempt, llm


# ------------------------------------------------------- the default is off --

def test_the_brake_is_off_in_the_default_profile():
    """The bench runs on DEFAULT, so this must change nothing there."""
    assert DEFAULT.invalid_streak_break == 0


def test_the_one_b_profile_turns_it_on():
    from harness.profiles import PROFILES
    assert PROFILES["llama3.2:1b"].invalid_streak_break == 4


# ------------------------------------------------------------- it fires --

def test_a_run_that_stops_reaching_a_tool_ends(attempt_factory):
    episode, attempt, llm = _run(attempt_factory, BRAKE,
                                 [_reply("add_event")] * 10)
    stuck = [n for n in episode.transcript if n["kind"] == "stuck"]
    assert len(stuck) == 1, "the run burned its whole budget instead of stopping"
    assert "reached no tool" in stuck[0]["content"]
    assert llm.used == 3, "it should stop on the third, not later"


def test_whatever_the_run_already_did_survives(attempt_factory):
    """A cost brake must not throw away completed work."""
    episode, attempt, _ = _run(attempt_factory, BRAKE, [
        _reply("add_event", title="Design sync", date="2026-07-21",
               start_time="14:00", end_time="15:00"),
        _reply("add_event"), _reply("add_event"), _reply("add_event"),
    ])
    done = [a for a in attempt.actions if a["tool"] == "add_event" and a["ok"]]
    assert len(done) == 1
    assert done[0]["args"]["date"] == "2026-07-21"


def test_a_suppressed_repeat_counts_as_reaching_no_tool(attempt_factory):
    """The failure this exists for alternates invalid with repeat.

    Counting only strictly consecutive invalid calls never climbs past one on
    that pattern, which is how the first version of this failed to fire on the
    very run it was written for.
    """
    good = _reply("add_event", title="Design sync", date="2026-07-21",
                  start_time="14:00", end_time="15:00")
    episode, _, llm = _run(attempt_factory, BRAKE, [
        good,                    # runs, resets the counter
        good,                    # identical: suppressed, counts 1
        _reply("add_event"),     # invalid, counts 2
        good,                    # suppressed again, counts 3, stop
        _reply("done", summary="never reached"),
    ])
    assert [n["kind"] for n in episode.transcript].count("stuck") == 1
    assert llm.used == 4


# --------------------------------------------------------- it stays out --

def test_it_does_not_fire_while_tools_are_running(attempt_factory):
    episode, attempt, _ = _run(attempt_factory, BRAKE, [
        _reply("list_events", date="2026-07-21"),
        _reply("add_event"),                       # one bad call
        _reply("list_emails"),                     # back to work, resets
        _reply("add_event"),
        _reply("done", summary="did the thing"),
    ])
    assert episode.finished is True
    assert not [n for n in episode.transcript if n["kind"] == "stuck"]


def test_with_the_brake_off_the_same_replies_burn_the_budget(attempt_factory):
    """The before half of the measurement, pinned."""
    episode, _, llm = _run(attempt_factory, NO_BRAKE,
                           [_reply("add_event")] * 18)
    assert not [n for n in episode.transcript if n["kind"] == "stuck"]
    assert llm.used == 18, "it should have spent the whole budget"


@pytest.fixture
def anyio_backend():
    return "asyncio"

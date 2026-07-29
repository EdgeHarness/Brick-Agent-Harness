import json

import pytest

from harness import agent


class ScriptedLLM:
    """Minimal offline LLM interface that returns replies in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.wall = 0.0
        self.requests = []

    def chat(
        self,
        messages,
        force_json=False,
        num_predict=700,
        role=None,
        keep_alive=None,
    ):
        self.calls += 1
        self.requests.append(
            {
                "messages": [dict(message) for message in messages],
                "force_json": force_json,
                "num_predict": num_predict,
                "role": role,
                "keep_alive": keep_alive,
            }
        )
        if not self.replies:
            raise AssertionError("scripted LLM ran out of replies")
        return self.replies.pop(0)


def call(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def test_raw_loop_accepts_done_without_external_inference(attempt_factory):
    attempt = attempt_factory(condition="raw")
    llm = ScriptedLLM([call("done", summary="finished")])

    episode = agent.run_raw(llm, "Do nothing", attempt)

    assert episode.finished is True
    assert episode.done_summary == "finished"
    assert llm.calls == 1
    assert llm.requests[0]["force_json"] is False


def test_raw_loop_stops_at_the_call_budget(attempt_factory):
    attempt = attempt_factory(condition="raw", max_calls=2)
    llm = ScriptedLLM(["not json", "still not json"])

    episode = agent.run_raw(llm, "Do something", attempt)

    assert episode.finished is False
    assert episode.parse_failures == 2
    assert llm.calls == 2


@pytest.mark.characterization
def test_done_at_budget_boundary_bypasses_harness_verifier(
    attempt_factory,
):
    attempt = attempt_factory(max_calls=2)
    llm = ScriptedLLM(
        [
            '{"steps": []}',
            call("done", summary="accepted without a verifier call"),
        ]
    )

    episode = agent.run_harness(llm, "Do something", attempt)

    assert episode.finished is True
    assert llm.calls == 2
    assert not [entry for entry in episode.transcript if entry["kind"] == "verify"]


@pytest.mark.characterization
def test_malformed_verifier_reply_fails_open(attempt_factory):
    attempt = attempt_factory()
    llm = ScriptedLLM(
        [
            '{"steps": []}',
            call("done", summary="claimed complete"),
            "not valid json",
        ]
    )

    episode = agent.run_harness(llm, "Do something", attempt)

    assert episode.finished is True
    assert llm.calls == 3
    verify = [entry for entry in episode.transcript if entry["kind"] == "verify"]
    assert verify == [
        {"kind": "verify", "content": '{"complete": true, "missing": ""}'}
    ]


@pytest.mark.characterization
def test_third_done_is_accepted_after_two_incomplete_verdicts(
    attempt_factory,
):
    attempt = attempt_factory()
    llm = ScriptedLLM(
        [
            '{"steps": []}',
            call("done", summary="first"),
            '{"complete": false, "missing": "work"}',
            call("done", summary="second"),
            '{"complete": false, "missing": "still work"}',
            call("done", summary="third"),
        ]
    )

    episode = agent.run_harness(llm, "Do something", attempt)

    assert episode.finished is True
    assert episode.done_summary == "third"
    assert llm.calls == 6
    assert len(
        [entry for entry in episode.transcript if entry["kind"] == "verify"]
    ) == 2


def test_duplicate_read_is_suppressed_while_world_is_unchanged(
    attempt_factory,
):
    attempt = attempt_factory()
    repeated = call("list_events", date="2026-07-22")
    llm = ScriptedLLM(
        [
            '{"steps": [{"tool": "list_events", "what": "inspect Wednesday"}]}',
            repeated,
            repeated,
            call("done", summary="listed once"),
            '{"complete": true, "missing": ""}',
        ]
    )

    episode = agent.run_harness(llm, "List Wednesday", attempt)

    assert episode.finished is True
    assert llm.calls == 5
    assert [action["tool"] for action in attempt.actions] == ["list_events"]
    feedback = [
        entry["content"]
        for entry in episode.transcript
        if entry["kind"] == "feedback"
    ]
    assert any("already called list_events" in item for item in feedback)

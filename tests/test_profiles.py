"""Per-model profiles: resolution, and the loop honoring the knobs.

The single most important assertion here is that DEFAULT reproduces the
loop's original literals exactly, because bench/ constructs RunConfig without
a profile and every recorded comparison depends on that path not shifting.
"""
import json

from harness import agent, profiles
from harness.profiles import DEFAULT, Profile, for_model, size_of
from harness.runtime import RunConfig


def test_default_profile_reproduces_the_original_loop_literals():
    assert DEFAULT.plan is True
    assert DEFAULT.plan_max_steps == 6
    assert DEFAULT.verify_rounds == 2
    assert DEFAULT.loop_break is True
    assert DEFAULT.repeat_limit == 1
    assert DEFAULT.repeat_limit_write == 1
    assert DEFAULT.think_streak_cap == 2
    assert DEFAULT.num_predict == 700
    assert DEFAULT.memory_k == 3
    assert DEFAULT.num_ctx == 8192


def test_run_config_defaults_to_the_default_profile():
    config = RunConfig(
        condition="harness", max_calls=5, today=__import__("datetime").date(2026, 7, 20)
    )
    assert config.profile is DEFAULT
    # and the RunConfig verifier default agrees with the profile's
    assert config.verifier_rounds == DEFAULT.verify_rounds


def test_size_of_reads_the_parameter_count_not_the_family_version():
    assert size_of("llama3.2:1b") == 1.0
    assert size_of("phi4-mini:3.8b") == 3.8
    assert size_of("llama3.2") is None


def test_for_model_prefers_the_exact_tag():
    assert for_model("llama3.2:1b").label == "format-survival"


def test_for_model_falls_back_by_size_band():
    prof = for_model("gemma2:9b")
    assert prof.label == "balanced (by size)"
    assert prof.plan is True


def test_for_model_unknown_tag_gets_default():
    assert for_model("mystery-model") is DEFAULT


def test_override_patches_known_fields_and_ignores_unknown_ones():
    prof = for_model("llama3.2:1b", {"max_calls": 30, "not_a_field": 1})
    assert prof.max_calls == 30
    assert prof.plan is False  # rest of the 1B profile kept


def _reply(tool, **args):
    return json.dumps({"tool": tool, "args": args})


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def chat(self, messages, force_json=False, num_predict=700,
             role=None, keep_alive=None):
        self.requests.append({"role": role, "num_predict": num_predict})
        if not self.replies:
            raise AssertionError("scripted LLM ran out of replies")
        return self.replies.pop(0)


def test_plan_off_profile_skips_the_plan_call(attempt_factory):
    profile = profiles.for_model("llama3.2:1b")
    attempt = attempt_factory(profile=profile, verifier_rounds=0)
    llm = ScriptedLLM([_reply("done", summary="ok")])

    episode = agent.run_harness(llm, "Do nothing", attempt)

    assert episode.finished is True
    # one call total, and it was the driver - no router/plan call happened
    assert [r["role"] for r in llm.requests] == ["driver"]
    assert llm.requests[0]["num_predict"] == 350
    assert not [n for n in episode.transcript if n["kind"] == "plan"]


def test_repeat_limit_two_allows_a_second_look_then_suppresses(attempt_factory):
    profile = Profile(repeat_limit=2, verify_rounds=0)
    attempt = attempt_factory(profile=profile, verifier_rounds=0)
    llm = ScriptedLLM([
        json.dumps({"steps": [{"tool": "list_emails", "what": "look"}]}),
        _reply("list_emails"),
        _reply("list_emails"),   # second look: executes
        _reply("list_emails"),   # third: suppressed
        _reply("done", summary="ok"),
    ])

    episode = agent.run_harness(llm, "List my emails", attempt)

    assert episode.finished is True
    executed = [a for a in attempt.actions if a["tool"] == "list_emails"]
    assert len(executed) == 2
    feedback = [n["content"] for n in episode.transcript if n["kind"] == "feedback"]
    assert any("2 times now" in f for f in feedback)


def test_default_profile_keeps_the_one_execution_rule(attempt_factory):
    attempt = attempt_factory(verifier_rounds=0)
    llm = ScriptedLLM([
        json.dumps({"steps": [{"tool": "list_emails", "what": "look"}]}),
        _reply("list_emails"),
        _reply("list_emails"),   # suppressed, byte-identical phrasing
        _reply("done", summary="ok"),
    ])

    episode = agent.run_harness(llm, "List my emails", attempt)

    executed = [a for a in attempt.actions if a["tool"] == "list_emails"]
    assert len(executed) == 1
    feedback = [n["content"] for n in episode.transcript if n["kind"] == "feedback"]
    assert any(f.startswith("You already called list_emails with exactly those arguments")
               for f in feedback)


def test_a_failed_call_never_earns_a_repeat_budget(attempt_factory):
    profile = Profile(repeat_limit=3, verify_rounds=0)
    attempt = attempt_factory(profile=profile, verifier_rounds=0)
    llm = ScriptedLLM([
        json.dumps({"steps": [{"tool": "read_email", "what": "open"}]}),
        _reply("read_email", id="no-such-id"),
        _reply("read_email", id="no-such-id"),   # identical failure: suppressed
        _reply("done", summary="ok"),
    ])

    episode = agent.run_harness(llm, "Read the email", attempt)

    executed = [a for a in attempt.actions if a["tool"] == "read_email"]
    assert len(executed) == 1
    feedback = [n["content"] for n in episode.transcript if n["kind"] == "feedback"]
    assert any("already failed" in f for f in feedback)

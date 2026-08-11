import copy
import os
from pathlib import Path

import pytest
import requests

from domains.office_demo import office_files
from domains.office_demo.sharvin_adapter import (
    KEEP_ALIVE,
    MAX_GENERATED_TOKENS,
    MAX_MODEL_CALLS,
    MAX_TOKENS_PER_REQUEST,
    MODEL_TAG,
    NUM_CTX,
    PINNED_COMMIT,
    SharvinAdapterError,
    inspect_pinned_source,
    load_authorized_source,
    request_options,
    run_native_llama_attempt,
    run_sharvin_attempt,
)
from domains.office_demo.world import World
from harness.experiment import AttemptMemory, ExecutionContext


EXTERNAL_CHECKOUT = Path(
    os.environ.get("BRICK_SHARVIN_CHECKOUT", r"C:\bft-final-agent-8b-audit-7efc9b9")
)


def response(content="", calls=None, tokens=5, **overrides):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = [
            {"function": {"name": name, "arguments": copy.deepcopy(args)}}
            for name, args in calls
        ]
    document = {
        "model": MODEL_TAG,
        "done": True,
        "message": message,
        "total_duration": 10,
        "load_duration": 0,
        "prompt_eval_count": 11,
        "prompt_eval_duration": 3,
        "eval_count": tokens,
        "eval_duration": 7,
        "done_reason": "stop",
    }
    document.update(overrides)
    return document


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    def chat(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        if not self.responses:
            raise AssertionError("fake transport response queue exhausted")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return copy.deepcopy(item)


@pytest.fixture(scope="module")
def source():
    if not (EXTERNAL_CHECKOUT / ".git").exists():
        pytest.skip("set BRICK_SHARVIN_CHECKOUT for pinned-source integration tests")
    binding = inspect_pinned_source(EXTERNAL_CHECKOUT)
    return load_authorized_source(EXTERNAL_CHECKOUT, binding)


@pytest.fixture
def context(tmp_path):
    world = World(str(tmp_path / "world"), persistent=False)
    return ExecutionContext(world, AttemptMemory(), world.files_dir)


def treatment_queue(mutation=None, verifier=None):
    mutation = mutation or {
        "tool": "set_reminder",
        "args": {"text": "submit report", "date": "today", "time": "2pm"},
    }
    verifier = verifier or response('{"complete":true,"missing":""}')
    return [
        response('{"steps":[{"tool":"set_reminder","what":"set reminder"}]}'),
        response(__import__("json").dumps(mutation, separators=(",", ":"))),
        response('{"tool":"done","args":{"summary":"complete"}}'),
        verifier,
    ]


def run_treatment(source, context, queue, seed=123456789, prompt="Set the reminder"):
    transport = FakeTransport(queue)
    result = run_sharvin_attempt(
        source=source,
        model=MODEL_TAG,
        transport=transport,
        context=context,
        episodes=[{"id": "main", "prompt": prompt}],
        today="2028-01-03",
        seed=seed,
    )
    return result, transport


def test_frozen_constants_and_request_options_have_no_hard_coded_seed_42():
    assert PINNED_COMMIT == "7efc9b9dc2c54684f88c372de3a5d620e5497a23"
    assert (MAX_MODEL_CALLS, MAX_GENERATED_TOKENS, MAX_TOKENS_PER_REQUEST) == (
        18, 6144, 700
    )
    assert (NUM_CTX, KEEP_ALIVE) == (8192, "30m")
    assert request_options(987654321, 333) == {
        "temperature": 0.0,
        "seed": 987654321,
        "num_ctx": 8192,
        "num_predict": 333,
    }
    assert 42 not in request_options(987654321, 333).values()


def test_exact_external_source_binding_and_authorization(source):
    before = inspect_pinned_source(EXTERNAL_CHECKOUT)
    assert before == source.binding
    assert before["commit_sha"] == PINNED_COMMIT
    assert set(before["files"]) == {
        "standalone/agents/8b/config.json",
        "standalone/harness/agent.py",
        "standalone/harness/profiles.py",
        "standalone/harness/tools.py",
    }
    changed = copy.deepcopy(before)
    changed["files"]["standalone/harness/agent.py"] = "0" * 64
    with pytest.raises(SharvinAdapterError, match="differs from authorization"):
        load_authorized_source(EXTERNAL_CHECKOUT, changed)
    assert inspect_pinned_source(EXTERNAL_CHECKOUT) == before


def test_treatment_uses_paired_seed_date_format_and_shared_budget(source, context):
    result, transport = run_treatment(source, context, treatment_queue())
    assert result["execution_status"] == "done"
    assert result["failure_origin"] == "none"
    assert result["ledger"]["maximum_model_calls"] == 18
    assert result["ledger"]["maximum_generated_tokens"] == 6144
    assert result["metrics"]["model_calls"] == 4
    assert {payload["options"]["seed"] for payload in transport.payloads} == {123456789}
    assert all(payload["format"] == "json" for payload in transport.payloads)
    assert all("tools" not in payload and "think" not in payload for payload in transport.payloads)
    assert all(payload["keep_alive"] == "30m" for payload in transport.payloads)
    assert all(payload["options"]["temperature"] == 0.0 for payload in transport.payloads)
    assert all(payload["options"]["num_ctx"] == 8192 for payload in transport.payloads)
    reminder = next(item for item in context.actions if item["tool"] == "set_reminder")
    assert reminder["args"]["date"] == "2028-01-03"
    assert reminder["args"]["time"] == "14:00"
    assert "Monday, January 3, 2028" in transport.payloads[0]["messages"][0]["content"]


def test_treatment_records_upstream_argument_repairs(source, context):
    mutation = {
        "tool": "set_reminder",
        "args": {
            "reminder_text": "submit report",
            "date": "today",
            "reminder_time": "2pm",
        },
    }
    result, _transport = run_treatment(source, context, treatment_queue(mutation))
    assert result["execution_status"] == "done"
    assert result["diagnostics"]["repairs"]
    action = next(item for item in context.actions if item["tool"] == "set_reminder")
    assert action["repairs"]
    assert action["args"] == {
        "text": "submit report", "date": "2028-01-03", "time": "14:00"
    }


def test_successful_unusable_verifier_json_is_unverified_not_instrument_failure(
    source, context
):
    result, _transport = run_treatment(
        source, context, treatment_queue(verifier=response("not-json"))
    )
    assert result["execution_status"] == "done"
    assert result["failure_origin"] == "none"
    assert result["diagnostics"]["unverified_completions"] == 1


def test_verifier_timeout_is_latched_even_though_upstream_fails_open(source, context):
    result, _transport = run_treatment(
        source, context,
        treatment_queue(verifier=requests.Timeout("verifier timed out")),
    )
    assert result["execution_status"] == "environment_unstable"
    assert result["failure_origin"] == "environment"
    assert result["failure"]["category"] == "transport_connectivity"
    assert result["failure"]["retryable"] is True
    assert result["ledger"]["generated_tokens_exact"] is False
    assert (
        result["ledger"]["generated_tokens_upper_bound"]
        > result["ledger"]["generated_tokens_lower_bound"]
    )


def test_verifier_malformed_success_response_is_latched(source, context):
    malformed = response('{"complete":true}')
    malformed.pop("eval_duration")
    result, _transport = run_treatment(
        source, context, treatment_queue(verifier=malformed)
    )
    assert result["execution_status"] == "runner_error"
    assert result["failure_origin"] == "runner"
    assert result["failure"]["category"] == "response_validation"


def test_verifier_budget_exhaustion_is_latched(source, context):
    # The plan spends 250 tokens, eight driver calls spend 5,600, and the done
    # response spends the remaining 294.  Calls remain below 18, so upstream
    # attempts its verifier; the shared token ledger must stop and latch it.
    queue = [response('{"steps":[]}', tokens=250)]
    queue.extend(
        response(
            '{"tool":"think","args":{"thought":"step %d"}}' % index,
            tokens=700,
        )
        for index in range(8)
    )
    queue.append(response(
        '{"tool":"done","args":{"summary":"complete"}}', tokens=294
    ))
    result, transport = run_treatment(source, context, queue)
    assert len(transport.payloads) == 10
    assert result["execution_status"] == "budget_exhausted"
    assert result["failure_origin"] == "model"
    assert result["failure"]["type"] == "opportunity_budget_exhausted"
    assert result["metrics"]["model_calls"] == 10


def test_done_at_exact_call_ceiling_is_reported_unverified(source, context):
    queue = [response('{"steps":[]}')]
    queue.extend(
        response('{"tool":"think","args":{"thought":"step %d"}}' % index)
        for index in range(16)
    )
    queue.append(response('{"tool":"done","args":{"summary":"complete"}}'))
    result, transport = run_treatment(source, context, queue)
    assert len(transport.payloads) == 18
    assert result["execution_status"] == "done"
    assert result["failure_origin"] == "none"
    assert result["diagnostics"]["unverified_completions"] == 1


def test_typed_executor_abort_is_latched_and_only_brick_renderer_runs(
    monkeypatch, source, context
):
    called = []

    def broken_brick_renderer(*_args, **_kwargs):
        called.append("brick")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(office_files, "create_presentation", broken_brick_renderer)
    mutation = {
        "tool": "create_presentation",
        "args": {"filename": "plan.pptx", "slides": [{"title": "Plan"}]},
    }
    queue = [
        response('{"steps":[{"tool":"create_presentation","what":"create deck"}]}'),
        response(__import__("json").dumps(mutation, separators=(",", ":"))),
    ]
    result, _transport = run_treatment(source, context, queue)
    assert called == ["brick"]
    assert result["execution_status"] == "environment_unstable"
    assert result["failure_origin"] == "environment"
    assert result["failure"]["exception_type"] == "OSError"


def test_verifier_sees_successful_executions_not_typed_prevalidation_rejections(
    source, context
):
    queue = [
        response('{"steps":[{"tool":"set_reminder","what":"set it"}]}'),
        response('{"tool":"set_reminder","args":{"text":"prevalidation","date":"today"}}'),
        response('{"tool":"set_reminder","args":{"text":"bad","date":123,"time":"14:00"}}'),
        response('{"tool":"set_reminder","args":{"text":"good","date":"today","time":"14:00"}}'),
        response('{"tool":"done","args":{"summary":"complete"}}'),
        response('{"complete":true,"missing":""}'),
    ]
    result, transport = run_treatment(source, context, queue)
    assert result["execution_status"] == "done"
    assert any(not item["ok"] for item in context.actions)
    verifier_prompt = transport.payloads[-1]["messages"][-1]["content"]
    assert '"text": "prevalidation"' not in verifier_prompt
    assert '"date": 123' in verifier_prompt
    assert '"date": "2028-01-03"' in verifier_prompt


def test_native_arm_uses_same_options_seed_budget_and_only_native_tools(context):
    transport = FakeTransport([
        response(calls=[("set_reminder", {
            "text": "submit report", "date": "2028-01-03", "time": "14:00",
        })]),
        response(calls=[("done", {"summary": "complete"})]),
    ])
    result = run_native_llama_attempt(
        model=MODEL_TAG,
        transport=transport,
        context=context,
        episodes=[{"id": "main", "prompt": "Set the reminder"}],
        today="2028-01-03",
        seed=123456789,
    )
    assert result["execution_status"] == "done"
    assert result["ledger"]["maximum_model_calls"] == 18
    assert result["ledger"]["maximum_generated_tokens"] == 6144
    assert all("tools" in payload and "format" not in payload for payload in transport.payloads)
    assert all("think" not in payload for payload in transport.payloads)
    assert {payload["options"]["seed"] for payload in transport.payloads} == {123456789}
    assert {tuple(sorted(payload["options"].items())) for payload in transport.payloads} == {
        tuple(sorted({
            "temperature": 0.0, "seed": 123456789,
            "num_ctx": 8192, "num_predict": 700,
        }.items()))
    }
    assert "Monday, January 3, 2028" in transport.payloads[0]["messages"][0]["content"]


def test_native_arm_budget_is_shared_and_terminal(context):
    transport = FakeTransport([response(calls=[]) for _index in range(18)])
    result = run_native_llama_attempt(
        model=MODEL_TAG,
        transport=transport,
        context=context,
        episodes=[{"id": "main", "prompt": "Do the task"}],
        today="2028-01-03",
        seed=1001,
    )
    assert result["execution_status"] == "budget_exhausted"
    assert result["failure_origin"] == "model"
    assert result["metrics"]["model_calls"] == 18
    assert len(transport.payloads) == 18


def test_attempt_requires_brick_world_empty_memory_and_empty_actions(tmp_path):
    world = World(str(tmp_path / "world"), persistent=False)
    memory = AttemptMemory(["preloaded fact"])
    context = ExecutionContext(world, memory, world.files_dir)
    with pytest.raises(ValueError, match="empty attempt-local state"):
        run_native_llama_attempt(
            model=MODEL_TAG,
            transport=FakeTransport([]),
            context=context,
            episodes=[{"id": "main", "prompt": "task"}],
            today="2028-01-03",
            seed=1,
        )


def test_loading_and_running_do_not_dirty_or_import_upstream_subsystems(source, context):
    before = inspect_pinned_source(EXTERNAL_CHECKOUT)
    result, _transport = run_treatment(source, context, treatment_queue())
    assert result["execution_status"] == "done"
    assert inspect_pinned_source(EXTERNAL_CHECKOUT) == before
    assert "office" not in source.tools.__dict__
    assert "ToolError" not in source.tools.__dict__
    assert "World" not in source.agent.__dict__
    assert "MemoryStore" not in source.agent.__dict__

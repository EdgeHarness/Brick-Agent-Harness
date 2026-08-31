import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.lifecycle import (
    JournalValidationError,
    JournalWriteError,
    LifecycleJournal,
    digest_value,
    read_and_verify,
)
from harness.receipts import ReceiptError, ReceiptIssuer, TaskLedger
from harness.completion import PostconditionResult
from harness.model_router import ModelRouter
from harness.router_contract import (
    CapabilityError,
    RouterContract,
    backend_contract_digest,
    preflight_backend,
)
from harness.runtime import ActionPolicy, MAX_CONFIRMATION_DETAIL_BYTES
from harness.tool_pipeline import ToolPipeline
from harness.tools import ToolRegistry
from harness.runtime_dispatch import run
from agents._shared import run_agent as shared_runner
from webui import server as lab_server


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.model = "scripted-test"
        self.num_ctx = 8_192
        self.temperature = 0.0
        self.timeout = 1
        self.keep_alive = "0"
        self.retries = 0
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
        self.requests.append((role, force_json, list(messages)))
        if not self.replies:
            raise AssertionError("scripted LLM ran out of replies")
        return self.replies.pop(0)


def _call(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def _start_payload():
    return {
        "protocol": "receipt_v1",
        "domain": "counter_demo@0.1.0",
        "recipe_digest": "1" * 64,
        "router_digest": "2" * 64,
        "task_ref": "counter_twice",
    }


def test_lifecycle_hash_chain_is_durable_terminal_and_tamper_evident(tmp_path):
    path = tmp_path / "events.jsonl"
    journal = LifecycleJournal(path)
    journal.append("run.started", _start_payload())
    journal.append(
        "completion.checked",
        {
            "status": "incomplete",
            "reason": "postconditions_unsatisfied",
            "ledger_complete": False,
        },
    )
    journal.append(
        "run.incomplete",
        {
            "status": "incomplete",
            "completion_status": "incomplete",
            "reason": "budget_or_requirements_remaining",
        },
    )
    with pytest.raises(JournalValidationError, match="terminal"):
        journal.append("run.failed", {"status": "failed", "reason": "late"})
    journal.close()

    records = read_and_verify(path)
    assert [item["sequence"] for item in records] == [0, 1, 2]
    assert records[0]["payload"] == _start_payload()

    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[1])
    forged["payload"]["ledger_complete"] = True
    lines[1] = json.dumps(forged, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(JournalValidationError, match="hash"):
        read_and_verify(path)


def test_lifecycle_rejects_sensitive_payload_fields(tmp_path):
    journal = LifecycleJournal(tmp_path / "events.jsonl")
    with pytest.raises(JournalValidationError, match="fields"):
        journal.append(
            "run.started", dict(_start_payload(), prompt="private")
        )
    journal.close()


def test_receipt_signature_blocks_forgery_and_ledger_never_backfills():
    issuer = ReceiptIssuer(secret=b"deterministic-test-secret-32bytes")
    ledger = TaskLedger(
        "run-1", [{"tool": "read_counter", "what": "read it"}]
    )
    receipt = issuer.issue(
        call_id="call-1",
        tool="read_counter",
        effect="read",
        args_digest=digest_value({}),
        result_digest=digest_value({"value": 0}),
    )
    forged = replace(receipt, tool="increment_counter")
    with pytest.raises(ReceiptError, match="invalid"):
        ledger.ground(forged, issuer)

    unmatched = issuer.issue(
        call_id="call-2",
        tool="increment_counter",
        effect="state_write",
        args_digest=digest_value({"amount": 1}),
        result_digest=digest_value({"value": 1}),
    )
    result = ledger.ground(unmatched, issuer)
    assert result.status == "unmatched"
    assert len(ledger.entries) == 1
    assert ledger.entries[0].grounded_by is None
    assert not ledger.completion_ready


def test_dispatch_journal_failure_prevents_tool_effect(attempt_factory):
    attempt = attempt_factory(domain_name="counter_demo")
    ledger = TaskLedger(
        attempt.attempt_id,
        [{"tool": "increment_counter", "what": "add one"}],
    )

    class FailingJournal:
        def append(self, event, _payload):
            if event == "tool.dispatch_committed":
                raise JournalWriteError("synthetic disk failure")

    pipeline = ToolPipeline(
        attempt,
        FailingJournal(),
        ledger,
        issuer=ReceiptIssuer(secret=b"deterministic-test-secret-32bytes"),
    )
    with pytest.raises(JournalWriteError, match="disk failure"):
        pipeline.execute("increment_counter", {"amount": 1})
    assert attempt.world.value == 0
    assert attempt.actions == []


def test_oversized_confirmation_is_rejected_before_approval_or_effect():
    confirmations = []
    executions = []
    events = []

    def execute(_attempt, args):
        executions.append(dict(args))
        return "sent"

    registry = ToolRegistry({
        "send_mail": {
            "desc": "Send a message.",
            "params": {
                "body": ("string", True),
                "recipient": ("string", True),
            },
            "example": {
                "tool": "send_mail",
                "args": {
                    "body": "hello",
                    "recipient": "person@example.com",
                },
            },
            "run": execute,
        }
    })
    attempt = SimpleNamespace(
        attempt_id="confirmation-bound",
        tools=registry,
        policy=ActionPolicy(
            {"send_mail": "external_write"},
            confirmer=lambda action, detail: confirmations.append(
                (action, detail)
            ) or True,
        ),
        cancelled=lambda: False,
        record_action=lambda *_args: None,
        hooks=SimpleNamespace(on_tool=None),
    )
    journal = SimpleNamespace(
        append=lambda event, payload: events.append((event, payload))
    )
    ledger = TaskLedger(
        attempt.attempt_id,
        [{"tool": "send_mail", "what": "send approved message"}],
    )
    result = ToolPipeline(attempt, journal, ledger).execute(
        "send_mail",
        {
            "body": "\N{ROCKET}" * MAX_CONFIRMATION_DETAIL_BYTES,
            "recipient": "hidden@example.com",
        },
    )

    assert result.ok is False
    assert result.status == "rejected"
    assert "exceeds" in result.observation
    assert confirmations == []
    assert executions == []
    assert not any(event == "tool.dispatch_committed" for event, _ in events)
    assert any(
        event == "tool.rejected"
        and payload["reason_code"] == "confirmation_payload_too_large"
        for event, payload in events
    )


def test_receipt_v1_counter_run_completes_end_to_end(attempt_factory):
    attempt = attempt_factory(
        domain_name="counter_demo",
        max_calls=5,
        verifier_rounds=1,
        runtime_protocol="receipt_v1",
        task_id="counter_twice",
    )
    llm = ScriptedLLM(
        [
            json.dumps(
                {
                    "steps": [
                        {"tool": "increment_counter", "what": "add one"},
                        {"tool": "increment_counter", "what": "add one"},
                    ]
                }
            ),
            _call("increment_counter", amount=1),
            _call("increment_counter", amount=1),
            _call("done", summary="counter is two"),
            json.dumps({"complete": True, "missing": ""}),
        ]
    )

    episode = run(llm, attempt.domain.tasks[0].prompt, attempt)

    assert episode.finished is True
    assert episode.terminal_status == "completed"
    assert episode.completion["status"] == "complete"
    assert episode.ledger == {
        "schema_version": "brick.task-ledger/1",
        "entries": 2,
        "grounded": 2,
        "unmatched": 0,
        "completion_ready": True,
    }
    assert attempt.world.value == 2
    events = read_and_verify(episode.lifecycle_path)
    names = [item["event_type"] for item in events]
    assert names[-1] == "run.completed"
    assert names.count("tool.dispatch_committed") == 2
    assert names.count("receipt.issued") == 2
    assert names.count("ledger.grounded") == 2
    raw = open(episode.lifecycle_path, encoding="utf-8").read()
    assert attempt.domain.tasks[0].prompt not in raw
    assert "counter is two" not in raw


def test_receipt_v1_interactive_done_is_unknown_not_success(attempt_factory):
    attempt = attempt_factory(
        domain_name="counter_demo",
        max_calls=3,
        verifier_rounds=0,
        runtime_protocol="receipt_v1",
    )
    llm = ScriptedLLM(
        [
            '{"steps":[{"tool":"read_counter","what":"inspect"}]}',
            _call("read_counter"),
            _call("done", summary="read it"),
        ]
    )

    episode = run(llm, "Read the counter.", attempt)

    assert episode.finished is False
    assert episode.terminal_status == "incomplete"
    assert episode.completion["status"] == "unknown"
    assert episode.ledger["completion_ready"] is True
    assert read_and_verify(episode.lifecycle_path)[-1]["event_type"] == (
        "run.incomplete"
    )


def test_receipt_v1_unplanned_write_never_dispatches(attempt_factory):
    attempt = attempt_factory(
        domain_name="counter_demo",
        max_calls=2,
        verifier_rounds=0,
        runtime_protocol="receipt_v1",
        task_id="counter_twice",
    )
    # The driver has only one call after planning. It proposes a write the
    # accepted plan did not authorize; replan cannot run at the budget edge.
    llm = ScriptedLLM(
        [
            '{"steps":[{"tool":"read_counter","what":"inspect"}]}',
            _call("increment_counter", amount=1),
        ]
    )

    episode = run(llm, attempt.domain.tasks[0].prompt, attempt)

    assert episode.finished is False
    assert attempt.world.value == 0
    assert not any(action["ok"] for action in attempt.actions)
    events = read_and_verify(episode.lifecycle_path)
    assert not any(
        item["event_type"] == "tool.dispatch_committed" for item in events
    )


def test_receipt_v1_model_failure_is_instrument_failure(attempt_factory):
    attempt = attempt_factory(
        domain_name="counter_demo",
        runtime_protocol="receipt_v1",
        task_id="counter_twice",
    )

    class BrokenLLM(ScriptedLLM):
        def chat(self, *args, **kwargs):
            raise RuntimeError("provider detail that must not be persisted")

    episode = run(
        BrokenLLM([]), attempt.domain.tasks[0].prompt, attempt
    )
    assert episode.finished is False
    assert episode.terminal_status == "failed"
    raw = open(episode.lifecycle_path, encoding="utf-8").read()
    assert "provider detail" not in raw
    assert read_and_verify(episode.lifecycle_path)[-1]["event_type"] == (
        "run.failed"
    )


def test_router_contract_is_order_independent_and_fails_closed():
    first = {
        "driver": {
            "model": "large",
            "capabilities": ("json_object", "chat"),
        },
        "router": {"model": "small", "capabilities": ("chat",)},
    }
    second = {"router": first["router"], "driver": first["driver"]}
    left = RouterContract(first, 8192)
    right = RouterContract(second, 8192)
    assert left.digest == right.digest
    assert left.decide(
        "driver", required=("chat", "json_object")
    ).decision_digest == right.decide(
        "driver", required=("json_object", "chat")
    ).decision_digest
    with pytest.raises(CapabilityError, match="lacks capabilities"):
        left.decide("router", required=("chat", "json_object"))
    with pytest.raises(CapabilityError, match="unknown model role"):
        left.decide("verifier")
    with pytest.raises(TypeError, match="must be a sequence"):
        left.decide("driver", required="chat")


def test_plain_backend_preflight_binds_configuration_and_context():
    first = ScriptedLLM([])
    second = ScriptedLLM([])
    assert backend_contract_digest(first) == backend_contract_digest(second)
    second.model = "different-model"
    assert backend_contract_digest(first) != backend_contract_digest(second)
    second.model = first.model
    second.num_ctx = 4_096
    assert backend_contract_digest(first) != backend_contract_digest(second)

    with pytest.raises(CapabilityError, match="context window"):
        preflight_backend(second, "driver", min_context=8_192)
    assert second.calls == 0
    with pytest.raises(CapabilityError, match="streaming"):
        preflight_backend(first, "driver", required=("streaming",))
    with pytest.raises(TypeError, match="must be a sequence"):
        preflight_backend(first, "driver", required="chat")


def test_model_router_rejects_missing_capability_before_client_creation(
    monkeypatch,
):
    created = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            created.append(True)

    monkeypatch.setattr("harness.model_router.LLM", Client)
    router = ModelRouter(
        roles={
            "driver": {
                "model": "local",
                "capabilities": ("chat",),
            }
        }
    )
    with pytest.raises(CapabilityError, match="json_object"):
        router.chat([], force_json=True, role="driver")
    assert created == []


def test_receipt_v1_cooperative_cancel_has_explicit_terminal_state(
    attempt_factory,
):
    llm = ScriptedLLM(
        ['{"steps":[{"tool":"read_counter","what":"inspect"}]}']
    )
    attempt = attempt_factory(
        domain_name="counter_demo",
        runtime_protocol="receipt_v1",
        task_id="counter_twice",
        cancel_check=lambda: llm.calls >= 1,
    )

    episode = run(llm, attempt.domain.tasks[0].prompt, attempt)

    assert episode.finished is False
    assert episode.terminal_status == "cancelled"
    assert attempt.world.value == 0
    assert attempt.actions == []
    assert read_and_verify(episode.lifecycle_path)[-1]["event_type"] == (
        "run.cancelled"
    )


def test_receipt_v1_cancel_during_final_tool_cannot_fall_through_to_budget(
    attempt_factory,
):
    attempt = attempt_factory(
        domain_name="counter_demo",
        max_calls=2,
        verifier_rounds=0,
        runtime_protocol="receipt_v1",
        task_id="counter_twice",
    )
    attempt.cancel_check = lambda: attempt.world.value == 1
    llm = ScriptedLLM([
        '{"steps":[{"tool":"increment_counter","what":"add one"}]}',
        _call("increment_counter", amount=1),
    ])

    episode = run(llm, attempt.domain.tasks[0].prompt, attempt)

    assert episode.finished is False
    assert episode.terminal_status == "cancelled"
    assert attempt.world.value == 1
    assert episode.ledger["grounded"] == 1
    events = read_and_verify(episode.lifecycle_path)
    names = [event["event_type"] for event in events]
    assert names[-1] == "run.cancelled"
    assert names.index("ledger.grounded") < names.index("run.cancelled")


def test_receipt_v1_can_extend_plan_after_grounded_discovery(
    attempt_factory,
):
    attempt = attempt_factory(
        domain_name="counter_demo",
        max_calls=6,
        verifier_rounds=0,
        runtime_protocol="receipt_v1",
        completion_checker=lambda context: PostconditionResult(
            context.world.value == 1,
            missing=("counter is not one",)
            if context.world.value != 1
            else (),
        ),
    )
    llm = ScriptedLLM(
        [
            '{"steps":[{"tool":"read_counter","what":"inspect"}]}',
            _call("read_counter"),
            _call("increment_counter", amount=1),
            '{"steps":[{"tool":"increment_counter","what":"apply finding"}]}',
            _call("increment_counter", amount=1),
            _call("done", summary="updated after inspection"),
        ]
    )

    episode = run(llm, "Inspect, then increase by one.", attempt)

    assert episode.finished is True
    assert episode.terminal_status == "completed"
    assert episode.ledger["entries"] == 2
    assert episode.ledger["grounded"] == 2
    assert episode.ledger["unmatched"] == 0
    events = read_and_verify(episode.lifecycle_path)
    assert sum(
        item["event_type"] == "plan.accepted" for item in events
    ) == 2


def test_receipt_protocol_is_explicit_on_cli_config_and_web_boundary():
    options, task = shared_runner.parse_flags(
        ["--runtime-protocol", "receipt_v1", "inspect"]
    )
    assert options["runtime_protocol"] == "receipt_v1"
    assert task == "inspect"
    shared_runner.validate_config(
        {"name": "local", "model": "model", "runtime_protocol": "receipt_v1"}
    )
    with pytest.raises(ValueError, match="runtime_protocol"):
        shared_runner.validate_config(
            {"name": "local", "model": "model", "runtime_protocol": "typo"}
        )
    assert lab_server.require_runtime_protocol("receipt_v1") == "receipt_v1"
    with pytest.raises(ValueError, match="runtime_protocol"):
        lab_server.require_runtime_protocol("typo")


def test_agent_lab_exposes_receipt_runtime_as_opt_in():
    root = Path(lab_server.__file__).parent / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    javascript = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="opt-receipts"' in html
    assert "runtime_protocol: $('opt-receipts').checked" in javascript
    assert "receipt checks enabled" in javascript
    assert "receipt verified" not in javascript

import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

from bench import s6_preflight, s6_rules_reference, s6_run
from domains.office_demo.contracts import build_registry
from domains.office_demo.generated_grader import build_grader
from domains.office_demo.rules_reference import execute as execute_rules
from domains.office_demo.world import World
from harness.experiment import (
    AttemptMemory,
    ExecutionContext,
    OpportunityLedger,
    condition_registry,
    run_raw_json_attempt,
    run_attempt,
    validate_protocol,
)
from harness.grading import GradingEvidence
from harness.instances import load_canonical_json
from harness.typed_executor import ToolContract, TypedToolRegistry


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "bench" / "s6_protocol.json").read_text("utf-8"))
MANIFESTS = ROOT / "bench" / "manifests" / "office-v1"


class FakeTransport:
    def __init__(self, calls, eval_count=1):
        self.calls = list(calls)
        self.eval_count = eval_count
        self.payloads = []

    def chat(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        name, args = self.calls.pop(0)
        return {
            "model": payload["model"],
            "created_at": "2026-08-03T00:00:00Z",
            "message": {
                "role": "assistant",
                "content": "",
                "thinking": None,
                "tool_calls": [
                    {"function": {"name": name, "arguments": copy.deepcopy(args)}}
                ],
            },
            "done": True,
            "done_reason": "stop",
            "total_duration": 10,
            "load_duration": 1,
            "prompt_eval_count": 5,
            "prompt_eval_duration": 2,
            "eval_count": self.eval_count,
            "eval_duration": 3,
        }


class FakeRawTransport:
    def __init__(self, contents, eval_count=1):
        self.contents = list(contents)
        self.eval_count = eval_count
        self.payloads = []

    def chat(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        return {
            "model": payload["model"],
            "created_at": "2026-08-03T00:00:00Z",
            "message": {
                "role": "assistant",
                "content": self.contents.pop(0),
                "thinking": None,
            },
            "done": True,
            "done_reason": "stop",
            "total_duration": 10,
            "load_duration": 1,
            "prompt_eval_count": 5,
            "prompt_eval_duration": 2,
            "eval_count": self.eval_count,
            "eval_duration": 3,
        }


class EnvironmentThenTransport(FakeTransport):
    def __init__(self, calls):
        super().__init__(calls)
        self.fail_once = True

    def chat(self, payload):
        if self.fail_once:
            self.fail_once = False
            self.payloads.append(copy.deepcopy(payload))
            raise OSError("temporary Ollama interruption")
        return super().chat(payload)


class NoToolCallTransport:
    def __init__(self):
        self.payloads = []

    def chat(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        return {
            "model": payload["model"],
            "created_at": "2026-08-03T00:00:00Z",
            "message": {
                "role": "assistant",
                "content": "I will continue.",
                "thinking": None,
                "tool_calls": [],
            },
            "done": True,
            "done_reason": "stop",
            "total_duration": 10,
            "load_duration": 1,
            "prompt_eval_count": 5,
            "prompt_eval_duration": 2,
            "eval_count": 1,
            "eval_duration": 3,
        }


def _condition(name):
    return condition_registry(PROTOCOL, "a" * 64)[name]


def _context(path):
    world = World(str(path), persistent=False)
    memory = AttemptMemory()
    return ExecutionContext(world, memory, world.files_dir)


def test_primary_conditions_expose_byte_identical_native_schemas():
    native = build_registry(alias_recovery=False)
    harness = build_registry(alias_recovery=True)
    assert native.names() == harness.names()
    assert native.native_schemas() == harness.native_schemas()
    assert native.native_schemas()[4]["function"]["parameters"][
        "additionalProperties"
    ] is False


def test_descriptive_registry_has_unique_executable_mechanism_identities():
    registry = condition_registry(PROTOCOL, "a" * 64)
    assert set(registry) == {
        "native_tools",
        "harness_full",
        "raw_json",
        "harness_no_plan",
        "harness_no_recovery",
        "harness_no_completion_guard",
        "harness_no_memory",
    }
    assert len({item.mechanism_sha256 for item in registry.values()}) == 7
    assert registry["raw_json"].runner == "raw_json_loop"
    assert not registry["harness_no_plan"].has("native_think_plan_first")
    assert not registry["harness_no_recovery"].has("known_alias_recovery")
    assert not registry["harness_no_recovery"].has(
        "identical_mutation_suppression"
    )
    assert not registry["harness_no_completion_guard"].has(
        "public_completion_guard"
    )
    assert registry["harness_no_memory"].has(
        "attempt_scoped_memory_bridge_disabled"
    )
    assert s6_run._condition_order(
        ("harness_full", "native_tools"),
        ("raw_json", "native_tools", "harness_no_plan"),
    ) == ("native_tools", "raw_json", "harness_no_plan")


def test_raw_json_lower_bound_uses_no_native_tool_channel(tmp_path):
    reminder = {
        "text": "submit report",
        "date": "2026-08-10",
        "time": "15:00",
    }
    transport = FakeRawTransport(
        [
            json.dumps({"tool": "set_reminder", "args": reminder}),
            json.dumps({"tool": "done", "args": {"summary": "complete"}}),
        ]
    )
    context = _context(tmp_path)
    result = run_raw_json_attempt(
        protocol=PROTOCOL,
        condition=_condition("raw_json"),
        model=PROTOCOL["primary_model"],
        registry=build_registry(alias_recovery=False),
        transport=transport,
        context=context,
        episodes=[{"id": "main", "prompt": "Set one reminder."}],
        today="2026-08-03",
        seed=5,
    )
    assert result["execution_status"] == "done"
    assert result["ledger"]["model_calls"] == 2
    assert all("tools" not in payload for payload in transport.payloads)
    assert "TOOLS:" in transport.payloads[0]["messages"][0]["content"]
    assert context.world.reminders == [reminder]


def test_native_descriptive_ablation_switches_are_executable(tmp_path):
    reminder = {
        "text": "submit report",
        "date": "2026-08-10",
        "time": "15:00",
    }
    no_plan = FakeTransport(
        [
            ("set_reminder", reminder),
            ("done", {"summary": "complete"}),
            ("think", {"thought": "all requirements are satisfied"}),
            ("done", {"summary": "reviewed"}),
        ]
    )
    plan_context = _context(tmp_path / "no-plan")
    result = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("harness_no_plan"),
        model=PROTOCOL["primary_model"],
        registry=build_registry(alias_recovery=True),
        transport=no_plan,
        context=plan_context,
        episodes=[{"id": "main", "prompt": "Set one reminder."}],
        today="2026-08-03",
        seed=19,
    )
    assert result["execution_status"] == "done"
    assert plan_context.actions[0]["status"] == "ok"

    no_guard = FakeTransport(
        [
            ("think", {"thought": "set the reminder"}),
            ("set_reminder", reminder),
            ("done", {"summary": "complete"}),
        ]
    )
    guard_context = _context(tmp_path / "no-guard")
    result = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("harness_no_completion_guard"),
        model=PROTOCOL["primary_model"],
        registry=build_registry(alias_recovery=True),
        transport=no_guard,
        context=guard_context,
        episodes=[{"id": "main", "prompt": "Set one reminder."}],
        today="2026-08-03",
        seed=23,
    )
    assert result["execution_status"] == "done"
    assert [item["status"] for item in guard_context.actions] == ["ok", "ok", "ok"]

    memory = AttemptMemory(bridge_enabled=False)
    memory.save("meetings use Video")
    assert memory.all() == ["meetings use Video"]
    assert memory.search("meeting") == []


def test_observation_bounding_is_an_executable_harness_only_mechanism(tmp_path):
    value = "x" * (PROTOCOL["observation"]["maximum_characters"] + 500)

    def inspect(_context, _args):
        return value

    registry = TypedToolRegistry(
        [
            ToolContract(
                "inspect",
                "Return a large source value.",
                {"type": "object", "properties": {}, "required": []},
                inspect,
            ),
            ToolContract(
                "mark",
                "Record completion.",
                {"type": "object", "properties": {}, "required": []},
                lambda _context, _args: "recorded",
                mutating=True,
            ),
            ToolContract(
                "think",
                "Plan or review.",
                build_registry(False).get("think").schema,
                lambda _context, _args: "noted",
            ),
            ToolContract(
                "done",
                "Finish.",
                build_registry(False).get("done").schema,
                lambda _context, args: args,
            ),
        ]
    )
    native_transport = FakeTransport(
        [("inspect", {}), ("mark", {}), ("done", {"summary": "complete"})]
    )
    native_context = _context(tmp_path / "native")
    native = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("native_tools"),
        model=PROTOCOL["primary_model"],
        registry=registry,
        transport=native_transport,
        context=native_context,
        episodes=[{"id": "main", "prompt": "Inspect the source."}],
        today="2026-08-03",
        seed=3,
    )
    assert native["execution_status"] == "done"
    assert value in native_transport.payloads[1]["messages"][-1]["content"]
    assert native_context.actions[0]["result"] == value

    harness_transport = FakeTransport(
        [
            ("think", {"thought": "inspect the source"}),
            ("inspect", {}),
            ("mark", {}),
            ("done", {"summary": "complete"}),
            ("think", {"thought": "the requested source was inspected"}),
            ("done", {"summary": "complete after review"}),
        ]
    )
    harness_context = _context(tmp_path / "harness")
    harness = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("harness_full"),
        model=PROTOCOL["primary_model"],
        registry=registry,
        transport=harness_transport,
        context=harness_context,
        episodes=[{"id": "main", "prompt": "Inspect the source."}],
        today="2026-08-03",
        seed=3,
    )
    assert harness["execution_status"] == "done"
    bounded = harness_transport.payloads[2]["messages"][-1]["content"]
    assert bounded.endswith("...[truncated]")
    assert len(bounded) < len(value)
    assert harness_context.actions[1]["result"] == value


def test_opportunity_ledger_counts_before_dispatch_and_never_resets():
    ledger = OpportunityLedger(2, 5, 4)
    assert ledger.begin_request("plan") == 4
    ledger.finish_request(3, 4)
    assert ledger.begin_request("driver") == 2
    ledger.finish_request(2, 2)
    assert ledger.as_record()["call_roles"] == {"driver": 1, "plan": 1}
    assert ledger.remaining_calls == 0
    assert ledger.remaining_tokens == 0


def test_protocol_and_retained_execution_fail_closed():
    changed = copy.deepcopy(PROTOCOL)
    changed["sampling"]["unreviewed"] = 1
    with pytest.raises(ValueError, match="sampling map"):
        validate_protocol(changed)
    s6_preflight._verify_f0_binding(PROTOCOL)
    changed = copy.deepcopy(PROTOCOL)
    changed["f0_binding"]["attestation_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="attestation digest"):
        s6_preflight._verify_f0_binding(changed)
    changed = copy.deepcopy(PROTOCOL)
    changed["conditions"][1]["mechanisms"].remove("public_completion_guard")
    with pytest.raises(ValueError, match="condition definitions"):
        validate_protocol(changed)
    with pytest.raises(RuntimeError, match="forbids retained"):
        s6_run.run(
            SimpleNamespace(
                protocol=ROOT / "bench" / "s6_protocol.json",
                split="retained",
            )
        )


def test_attempt_identity_records_executed_budget_policy_for_every_family():
    environment = {
        "protocol_sha256": "1" * 64,
        "domain_sha256": "2" * 64,
        "ollama": {"model_digest": "sha256:" + "3" * 64},
        "tool_schema_sha256": "4" * 64,
    }
    atomic = _one("cal_add")
    learning = _one("preference_learning")
    for instance in (atomic, learning):
        key = s6_run._attempt_key(
            instance,
            _condition("native_tools"),
            environment,
            PROTOCOL,
            repeat=0,
        )
        assert key.to_dict()["opportunity_budget"][
            "shared_across_subepisodes"
        ] == 1


def test_preflight_fingerprints_every_executable_s6_dependency():
    assert set(s6_preflight.IMPLEMENTATION_PATHS) == {
        "harness/experiment.py",
        "harness/evidence.py",
        "harness/faults.py",
        "harness/errors.py",
        "harness/schema.py",
        "harness/typed_executor.py",
        "harness/parsing.py",
        "harness/grading.py",
        "harness/instances.py",
        "harness/builtin_tools.py",
        "harness/domain.py",
        "bench/generate_manifests.py",
        "bench/s6_run.py",
        "bench/s6_preflight.py",
        "bench/s6_rules_reference.py",
        "bench/s7_analysis.py",
        "bench/s7_artifacts.py",
        "bench/s7_contract.py",
        "bench/s7_decision.py",
        "bench/s7_floor_audit.py",
        "bench/s7_preflight.py",
        "bench/s7_protocol.json",
        "bench/s7_run.py",
        "requirements-analysis.txt",
        "bench/manifests/office-v1/development-exposure-v0.11.0.json",
    }
    assert set(s6_preflight.DOMAIN_PATHS) == {
        "domains/office_demo/generators.py",
        "domains/office_demo/world.py",
        "domains/office_demo/office_files.py",
        "domains/office_demo/tools.py",
        "domains/office_demo/contracts.py",
        "domains/office_demo/generated_grader.py",
        "domains/office_demo/strict_graders.py",
        "domains/office_demo/rules_reference.py",
    }
    assert len(s6_preflight.implementation_sha256()) == 64
    assert len(s6_preflight.domain_sha256()) == 64


def _scheduler_args(tmp_path, instance_id, run_id):
    return SimpleNamespace(
        protocol=ROOT / "bench" / "s6_protocol.json",
        manifests=MANIFESTS,
        runs_root=tmp_path,
        split="validation",
        instance_id=instance_id,
        condition=["native_tools"],
        max_cases=None,
        run_id=run_id,
        allow_dirty=True,
    )


def _fake_preflight():
    return {
        "schema_version": "brick.s6.preflight/1",
        "passed": True,
        "require_clean": False,
        "environment": {
            "protocol_sha256": s6_run.protocol_sha256(PROTOCOL),
            "implementation_sha256": "5" * 64,
            "domain_sha256": "6" * 64,
            "tool_schema_sha256": "7" * 64,
            "ollama": {
                "version": "0.32.5",
                "primary_model": PROTOCOL["primary_model"],
                "model_digest": PROTOCOL["f0_binding"]["primary_model_digest"],
            },
        },
    }


def test_scheduler_retries_only_environment_failure_and_resumes_exactly(
    monkeypatch, tmp_path
):
    instance = _one("cal_add")
    effects = instance["content"]["required_effects"]
    calendar = next(item for item in effects if item["type"] == "calendar_read")
    event = next(item for item in effects if item["type"] == "event_created")
    calls = [
        ("list_events", {"date": calendar["date"]}),
        (
            "add_event",
            {
                "title": event["title"],
                "date": event["date"],
                "start_time": event["start"],
                "end_time": event["end"],
                "attendees": event["attendees"],
                "location": event.get("location", ""),
            },
        ),
        ("done", {"summary": "complete"}),
    ]
    transport = EnvironmentThenTransport(calls)
    monkeypatch.setattr(s6_preflight, "collect", lambda *_a, **_k: _fake_preflight())
    monkeypatch.setattr(s6_run, "OllamaTransport", lambda *_a, **_k: transport)
    args = _scheduler_args(tmp_path, instance["content"]["id"], "retry-resume")
    summary = s6_run.run(args)
    assert summary["committed_attempts"] == 2
    assert summary["cells"][0]["strict_success"] is True
    assert summary["cells"][0]["failure_origin"] == "none"
    seeds = [payload["options"]["seed"] for payload in transport.payloads]
    assert len(set(seeds)) == 1

    records = json.loads((tmp_path / "retry-resume" / "results.json").read_text("utf-8"))[
        "records"
    ]
    records.sort(key=lambda record: record["attempt_key"]["repeat"])
    assert [record["attempt_key"]["repeat"] for record in records] == [0, 1]
    assert [record["failure_origin"] for record in records] == [
        "environment",
        "none",
    ]

    class MustNotRun:
        def chat(self, _payload):
            raise AssertionError("resume reran a committed physical record")

    monkeypatch.setattr(s6_run, "OllamaTransport", lambda *_a, **_k: MustNotRun())
    resumed = s6_run.run(args)
    assert resumed == summary


def test_scheduler_never_retries_a_valid_model_failure(monkeypatch, tmp_path):
    instance = _one("cal_add")
    transport = NoToolCallTransport()
    monkeypatch.setattr(s6_preflight, "collect", lambda *_a, **_k: _fake_preflight())
    monkeypatch.setattr(s6_run, "OllamaTransport", lambda *_a, **_k: transport)
    args = _scheduler_args(tmp_path, instance["content"]["id"], "model-failure")
    summary = s6_run.run(args)
    assert summary["committed_attempts"] == 1
    assert summary["cells"][0]["failure_origin"] == "model"
    assert summary["cells"][0]["strict_success"] is False
    assert len(transport.payloads) == PROTOCOL["opportunity_budget"]["model_calls"]


def test_environment_executor_fault_never_becomes_a_model_failure(tmp_path):
    def unavailable(_context, _args):
        raise OSError("disk unavailable")

    registry = TypedToolRegistry(
        [
            ToolContract(
                "explode",
                "Exercise an unavailable environment.",
                {"type": "object", "properties": {}, "required": []},
                unavailable,
            )
        ]
    )
    transport = FakeTransport([("explode", {})])
    context = _context(tmp_path)
    outcome = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("native_tools"),
        model=PROTOCOL["primary_model"],
        registry=registry,
        transport=transport,
        context=context,
        episodes=[{"id": "main", "prompt": "Exercise the tool."}],
        today="2026-08-03",
        seed=11,
    )
    assert outcome["execution_status"] == "environment_unstable"
    assert outcome["failure_origin"] == "environment"
    assert outcome["requests"][0]["request"]["tools"] == registry.native_schemas()


def test_harness_plan_completion_and_duplicate_guards(tmp_path):
    reminder = {
        "text": "submit report",
        "date": "2026-08-10",
        "time": "15:00",
    }
    transport = FakeTransport(
        [
            ("set_reminder", reminder),
            ("think", {"thought": "set the requested reminder"}),
            ("set_reminder", reminder),
            ("set_reminder", reminder),
            ("done", {"summary": "completed"}),
            ("think", {"thought": "all explicit requirements are now satisfied"}),
            ("done", {"summary": "completed after review"}),
        ]
    )
    context = _context(tmp_path)
    result = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("harness_full"),
        model=PROTOCOL["primary_model"],
        registry=build_registry(alias_recovery=True),
        transport=transport,
        context=context,
        episodes=[{"id": "main", "prompt": "Set one reminder."}],
        today="2026-08-03",
        seed=7,
    )
    assert result["execution_status"] == "done"
    assert [item["status"] for item in context.actions] == [
        "plan_required",
        "ok",
        "ok",
        "duplicate_suppressed",
        "completion_review_required",
        "ok",
        "ok",
    ]
    assert len(context.world.reminders) == 1
    assert result["ledger"]["model_calls"] == 7


def test_completion_review_limit_covers_configured_model_output(tmp_path):
    """A budget-valid review must not fail an unrelated schema threshold."""

    review = "reviewed every explicit requirement; " * 45
    assert 1000 < len(review) < 4096
    reminder = {
        "text": "submit report",
        "date": "2026-08-10",
        "time": "15:00",
    }
    transport = FakeTransport(
        [
            ("think", {"thought": "plan the requested reminder"}),
            ("set_reminder", reminder),
            ("done", {"summary": "completed"}),
            ("think", {"thought": review}),
            ("done", {"summary": "completed after review"}),
        ]
    )
    context = _context(tmp_path)
    result = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("harness_full"),
        model=PROTOCOL["primary_model"],
        registry=build_registry(alias_recovery=True),
        transport=transport,
        context=context,
        episodes=[{"id": "main", "prompt": "Set one reminder."}],
        today="2026-08-03",
        seed=17,
    )
    assert result["execution_status"] == "done"
    assert context.actions[-2]["tool"] == "think"
    assert context.actions[-2]["status"] == "ok"
    assert result["ledger"]["model_calls"] == 5


def test_learning_resets_conversation_but_injects_attempt_scoped_memory(tmp_path):
    transport = FakeTransport(
        [
            ("think", {"thought": "store the preference"}),
            ("save_memory", {"fact": "meetings use Video"}),
            ("done", {"summary": "remembered"}),
            ("think", {"thought": "the preference was saved"}),
            ("done", {"summary": "remembered after review"}),
            ("think", {"thought": "apply remembered preference"}),
            (
                "add_event",
                {
                    "title": "Focus sync",
                    "date": "2026-08-04",
                    "start_time": "14:00",
                    "end_time": "14:20",
                    "attendees": [],
                    "location": "Video",
                },
            ),
            ("done", {"summary": "booked"}),
            ("think", {"thought": "the remembered preference was applied"}),
            ("done", {"summary": "booked after review"}),
        ]
    )
    context = _context(tmp_path)
    result = run_attempt(
        protocol=PROTOCOL,
        condition=_condition("harness_full"),
        model=PROTOCOL["primary_model"],
        registry=build_registry(alias_recovery=True),
        transport=transport,
        context=context,
        episodes=[
            {"id": "store", "prompt": "Remember that meetings use Video."},
            {"id": "use", "prompt": "Book tomorrow's meeting."},
        ],
        today="2026-08-03",
        seed=9,
    )
    assert result["execution_status"] == "done"
    assert len(result["subepisodes"]) == 2
    assert transport.payloads[5]["messages"][0]["content"].count(
        "meetings use Video"
    ) == 1
    assert context.memory.all() == ["meetings use Video"]


def test_rules_reference_strictly_passes_every_frozen_generated_case():
    count = 0
    for split in ("development", "validation", "sentinel", "retained", "adversarial"):
        path = MANIFESTS / (split + ".json")
        for instance in load_canonical_json(path)["instances"]:
            with tempfile.TemporaryDirectory() as directory:
                outcome = build_grader(instance).grade_evidence(
                    execute_rules(instance, directory)
                )
            assert outcome.strict_success is True, instance["content"]["id"]
            count += 1
    assert count == 352


def test_rules_reference_runner_reports_real_development_counts():
    summary = s6_rules_reference.run(
        ROOT / "bench" / "s6_protocol.json",
        MANIFESTS,
        "development",
    )
    assert summary["run_kind"] == "model_free_architecture_reference"
    assert summary["case_count"] == 88
    assert summary["strict_successes"] == 88
    assert summary["all_strict"] is True
    assert len(summary["implementation_sha256"]) == 64


def _one(family):
    # Fresh development material is reserved for masked D0 execution. Runtime
    # unit tests exercise the single-case validation split instead.
    manifest = load_canonical_json(MANIFESTS / "validation.json")
    return next(
        item for item in manifest["instances"] if item["content"]["family"] == family
    )


def test_oracle_critical_generated_values_are_explicit_in_corrected_prompts():
    for split in ("development", "validation", "sentinel", "retained", "adversarial"):
        path = MANIFESTS / (split + ".json")
        for instance in load_canonical_json(path)["instances"]:
            content = instance["content"]
            if content["family"] == "remind_msg":
                prompt = content["prompt"]
                message = next(
                    effect
                    for effect in content["required_effects"]
                    if effect["type"] == "message_sent"
                )
                assert "repeats every checklist item" in prompt
                assert all(item in prompt for item in message["required_mentions"])
            if content["family"] == "preference_learning":
                prompt = content["ordered_subepisodes"][1]["prompt"]
                event = content["ordered_subepisodes"][1]["required_effects"][0]
                assert event["title"] in prompt
                assert event["attendees"] == [
                    value
                    for value in event["attendees"]
                    if value in prompt
                ]
                assert "earliest start time" in prompt
                assert "exactly to 'Video'" in prompt


def test_generated_grader_rejects_missing_source_and_extra_artifact(tmp_path):
    instance = _one("pptx_from_email")
    evidence = execute_rules(instance, tmp_path / "rules")
    without_read = [
        item for item in evidence.actions if item["tool"] != "read_email"
    ]
    artifacts = list((name, payload) for name, payload in evidence.artifact_map().items())
    missing = GradingEvidence.from_values(
        domain=evidence.domain,
        domain_version=evidence.domain_version,
        task_id=evidence.task_id,
        state=evidence.state,
        actions=without_read,
        memory=evidence.memory,
        artifacts=artifacts,
    )
    outcome = build_grader(instance).grade_evidence(missing)
    assert outcome.strict_success is False
    assert dict((key, passed) for key, _description, passed in outcome.checks)[
        "source_observed"
    ] is False
    extra = GradingEvidence.from_values(
        domain=evidence.domain,
        domain_version=evidence.domain_version,
        task_id=evidence.task_id,
        state=evidence.state,
        actions=evidence.actions,
        memory=evidence.memory,
        artifacts=sorted(artifacts + [("extra.pptx", b"not used")]),
    )
    checks = build_grader(instance).grade_evidence(extra)
    assert checks.strict_success is False
    assert dict((key, passed) for key, _description, passed in checks.checks)[
        "exact_artifacts"
    ] is False


def test_corrupt_required_artifact_is_null_not_model_failure(tmp_path):
    instance = _one("xlsx_basic")
    evidence = execute_rules(instance, tmp_path / "rules")
    corrupt = GradingEvidence.from_values(
        domain=evidence.domain,
        domain_version=evidence.domain_version,
        task_id=evidence.task_id,
        state=evidence.state,
        actions=evidence.actions,
        memory=evidence.memory,
        artifacts=[(next(iter(evidence.artifact_map())), b"not an xlsx")],
    )
    outcome = build_grader(instance).grade_evidence(corrupt)
    assert outcome.grader_status == "grader_error"
    assert outcome.strict_success is None

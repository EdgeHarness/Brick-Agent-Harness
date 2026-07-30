import datetime
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path

import pytest

from domains.office_demo import world as office_world
from domains.office_demo.normalize import normalize_args as office_normalize
from harness.agent import (
    build_harness_system,
    build_raw_system,
    run_harness,
    run_raw,
)
from harness.domain import (
    DomainPack,
    GENERIC_PROMPT_PROFILE,
    PromptProfile,
    TaskSpec,
    load_domain,
    state_envelope,
)
from harness.llm import LLM
from harness.memory import MemoryStore
from harness.model_router import ModelRouter
from harness.runtime import (
    ActionPolicy,
    AttemptContext,
    RunConfig,
    RunHooks,
)
from harness.tools import ToolRegistry


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.wall = 0.0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if not self.replies:
            raise AssertionError("scripted LLM ran out of replies")
        return self.replies.pop(0)


def make_attempt(
    tmp_path,
    domain_name="office_demo",
    *,
    condition="harness",
    max_calls=14,
    observation_limit=2000,
    tools=None,
    policy=None,
    hooks=None,
    suffix="one",
):
    domain = load_domain(domain_name)
    workdir = Path(tmp_path, f"{domain_name}-{suffix}")
    world = domain.make_world(workdir)
    memory = MemoryStore(str(Path(tmp_path, f"memory-{suffix}.jsonl")))
    return AttemptContext(
        attempt_id=f"{domain_name}-{suffix}",
        config=RunConfig(
            condition=condition,
            max_calls=max_calls,
            today=domain.default_today,
            observation_limit=observation_limit,
        ),
        domain=domain,
        tools=tools or domain.registry,
        policy=policy or domain.default_policy,
        world=world,
        memory=memory,
        workdir=workdir,
        artifact_dir=workdir / "files",
        hooks=hooks or RunHooks(),
    )


def simple_spec(name="sample", executor=None):
    executor = executor or (lambda context, args: args)
    return {
        "desc": "A sample tool.",
        "params": {"value": ("string", False)},
        "example": {"tool": name, "args": {"value": "x"}},
        "run": executor,
    }


def test_generic_tool_module_has_no_office_domain_dependency():
    source = Path("harness/tools.py").read_text(encoding="utf-8")
    assert "domains.office_demo" not in source
    assert "harness.world" not in source


# The two modules below exist only to keep pre-refactor import paths working.
# Every other core module must stay domain-independent, which is what makes a
# new pack loadable without editing harness/.
DEPRECATED_OFFICE_SHIMS = {"harness/world.py", "harness/office.py"}


def test_no_core_module_outside_the_named_shims_imports_a_domain():
    importers = set()
    for path in sorted(Path("harness").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            statement = line.strip()
            if statement.startswith(("import domains", "from domains")):
                importers.add(path.as_posix())
    assert importers == DEPRECATED_OFFICE_SHIMS

    for name in sorted(DEPRECATED_OFFICE_SHIMS):
        assert "Deprecated" in Path(name).read_text(encoding="utf-8")


def test_registry_recursively_freezes_ingress_egress_and_pack_singleton():
    source = {
        "sample": {
            "desc": "A sample tool.",
            "params": {"value": ("list", True)},
            "example": {
                "tool": "sample",
                "args": {"value": ["original"]},
            },
            "run": lambda context, args: args,
        }
    }
    registry = ToolRegistry(source)
    source["sample"]["example"]["args"]["value"].append("poison")
    exported = registry["sample"]
    exported["desc"] = "changed"
    exported["example"]["args"]["value"].append("changed")

    assert registry["sample"]["desc"] == "A sample tool."
    assert registry["sample"]["example"]["args"]["value"] == ["original"]
    with pytest.raises(TypeError):
        registry._specs["sample"]["desc"] = "internal poison"

    pack = load_domain("counter_demo")
    before = pack.registry.docs(True)
    with pytest.raises(TypeError):
        pack.registry._specs["read_counter"]["example"]["args"]["x"] = 1
    assert load_domain("counter_demo").registry.docs(True) == before


def test_registry_keeps_executor_identity_and_rejects_malformed_specs():
    class Executor:
        def __call__(self, context, args):
            return "ok"

        def __deepcopy__(self, memo):
            raise AssertionError("executor must not be copied")

    executor = Executor()
    registry = ToolRegistry({"sample": simple_spec(executor=executor)})
    assert registry["sample"]["run"] is executor

    malformed = [
        ("../bad", simple_spec("../bad")),
        (
            "sample",
            {
                **simple_spec(),
                "params": {"value": ("string", 1)},
            },
        ),
        (
            "sample",
            {
                **simple_spec(),
                "example": {"tool": "other", "args": {}},
            },
        ),
        ("sample", {**simple_spec(), "run": None}),
        ("sample", {**simple_spec(), "run": lambda only_one: None}),
    ]
    for name, spec in malformed:
        with pytest.raises((TypeError, ValueError)):
            ToolRegistry({name: spec})


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("max_calls", True, TypeError),
        ("max_calls", 1.5, TypeError),
        ("max_calls", 0, ValueError),
        ("today", datetime.datetime(2030, 1, 2), TypeError),
        ("observation_limit", False, TypeError),
        ("verifier_rounds", 1.5, TypeError),
        ("prompt_rules", None, TypeError),
    ],
)
def test_run_config_rejects_invalid_contract_values(field, value, error):
    kwargs = {
        "condition": "harness",
        "max_calls": 2,
        "today": datetime.date(2030, 1, 2),
    }
    kwargs[field] = value
    with pytest.raises(error):
        RunConfig(**kwargs)


def test_hook_and_action_policy_constructor_validation():
    with pytest.raises(TypeError):
        RunHooks(on_note="not callable")
    with pytest.raises(TypeError):
        ActionPolicy({}, confirmer="not callable")
    with pytest.raises(ValueError):
        ActionPolicy({"": "read"})
    with pytest.raises(ValueError):
        ActionPolicy({"tool": "maybe"})


def test_attempt_context_rejects_invalid_explicit_contracts(tmp_path):
    attempt = make_attempt(tmp_path, "counter_demo")
    for field, value, error in (
        ("attempt_id", "", ValueError),
        ("config", object(), TypeError),
        ("tools", {}, TypeError),
        ("policy", object(), TypeError),
        ("hooks", object(), TypeError),
    ):
        kwargs = dict(attempt.__dict__)
        kwargs[field] = value
        with pytest.raises(error):
            AttemptContext(**kwargs)


def test_domain_contract_rejects_bad_versions_registry_and_reserved_tools():
    pack = load_domain("counter_demo")
    for version in ("1", "1.0.0-01", "1.0.0-..", "1.0.0+"):
        with pytest.raises(ValueError):
            replace(pack, version=version)
    for version in (
        "1.0.0-1a",
        "1.0.0-123abc",
        "1.0.0-rc.1",
        "1.0.0+build.42",
    ):
        assert replace(pack, version=version).version == version
    with pytest.raises(TypeError):
        replace(pack, registry={})
    with pytest.raises(TypeError, match="make_world"):
        replace(pack, make_world=lambda workdir: object())
    with pytest.raises(TypeError, match="snapshot"):
        replace(pack, snapshot=lambda: None)
    without_done = pack.registry.selected(
        name for name in pack.registry if name != "done"
    )
    with pytest.raises(ValueError, match="reserved tool 'done'"):
        replace(pack, registry=without_done, tasks=())
    missing_done_task = replace(
        pack.tasks[0],
        tool_names=("read_counter", "increment_counter"),
    )
    with pytest.raises(ValueError, match="must select reserved tool 'done'"):
        replace(pack, tasks=(missing_done_task,))


def test_domain_policy_must_classify_every_registered_tool_exactly():
    for name in ("office_demo", "counter_demo"):
        pack = load_domain(name)
        assert set(pack.default_policy.effect_by_tool) == set(
            pack.registry.names()
        )

    pack = load_domain("counter_demo")
    missing = dict(pack.default_policy.effect_by_tool)
    missing.pop("increment_counter")
    with pytest.raises(ValueError, match="missing classifications"):
        replace(pack, default_policy=ActionPolicy(missing))

    unknown = dict(pack.default_policy.effect_by_tool)
    unknown["unregistered_tool"] = "state_write"
    with pytest.raises(ValueError, match="unknown classifications"):
        replace(pack, default_policy=ActionPolicy(unknown))


def test_attempt_policy_must_classify_every_active_tool(tmp_path):
    pack = load_domain("counter_demo")
    active_tools = pack.registry.selected(("increment_counter", "done"))
    attempt = make_attempt(
        tmp_path,
        "counter_demo",
        tools=active_tools,
        policy=pack.default_policy,
        suffix="classified-subset",
    )
    assert attempt.tools.names() == ("increment_counter", "done")

    incomplete = dict(pack.default_policy.effect_by_tool)
    incomplete.pop("increment_counter")
    with pytest.raises(
        ValueError, match="missing classifications for active tools"
    ):
        make_attempt(
            tmp_path,
            "counter_demo",
            tools=active_tools,
            policy=ActionPolicy(incomplete),
        )


def test_domain_contract_rejects_duplicate_capabilities_and_presets():
    pack = load_domain("counter_demo")
    with pytest.raises(ValueError, match="domain name"):
        replace(pack, name="con")
    with pytest.raises(ValueError, match="portable identifier"):
        replace(pack.tasks[0], id="nul")
    with pytest.raises(ValueError):
        replace(
            pack.tasks[0],
            capabilities=("counter_write", "counter_write"),
        )
    with pytest.raises(ValueError):
        replace(pack, presets=("same", "same"))
    for invalid_tools in ((1,), ([],)):
        with pytest.raises(ValueError, match="tool_names"):
            replace(pack.tasks[0], tool_names=invalid_tools)
    for invalid_presets in ((1,), ([],)):
        with pytest.raises(ValueError, match="presets"):
            replace(pack, presets=invalid_presets)


def test_state_envelope_validates_generic_ui_entry_contracts():
    section = {
        "id": "counter-state",
        "label": "counter",
        "items": [],
    }
    file_entry = {"name": "result.txt", "size": 0, "mtime": 0.0}
    envelope = state_envelope(
        "counter_demo",
        "0.1.0",
        [section],
        [file_entry],
        ["fact"],
    )
    assert envelope["sections"][0]["id"] == "counter-state"

    for invalid_id in ("__proto__", "constructor", "bad id", "files"):
        with pytest.raises(ValueError, match="section id"):
            state_envelope(
                "counter_demo",
                "0.1.0",
                [{**section, "id": invalid_id}],
                [],
                [],
            )
    for invalid_file in (
        {},
        {"name": "", "size": 0, "mtime": 0},
        {"name": "x", "size": -1, "mtime": 0},
        {"name": "x", "size": True, "mtime": 0},
        {"name": "x", "size": 0, "mtime": float("nan")},
    ):
        with pytest.raises((TypeError, ValueError)):
            state_envelope(
                "counter_demo",
                "0.1.0",
                [],
                [invalid_file],
                [],
            )
    with pytest.raises(TypeError, match="memory entries"):
        state_envelope(
            "counter_demo", "0.1.0", [], [], [{"fact": "not text"}]
        )


def test_domain_present_wrappers_validate_version_and_detach_state(
    tmp_path,
):
    pack = load_domain("counter_demo")
    attempt = make_attempt(tmp_path, "counter_demo")
    stale = replace(
        pack,
        present_state=lambda _attempt: state_envelope(
            pack.name, "9.9.9", [], [], []
        ),
    )
    with pytest.raises(ValueError, match="version"):
        stale.present(attempt)

    shared = [{"value": 1}]
    detached_pack = replace(
        pack,
        present_state=lambda _attempt: {
            "domain": pack.name,
            "version": pack.version,
            "sections": [
                {"id": "x", "label": "x", "items": shared}
            ],
            "files": [],
            "memory": [],
        },
    )
    presented = detached_pack.present(attempt)
    presented["sections"][0]["items"][0]["value"] = 99
    assert shared == [{"value": 1}]


def test_office_prompt_profile_preserves_golden_system_bytes():
    pack = load_domain("office_demo")
    today = pack.default_today.strftime("%A, %B %d, %Y")
    raw = build_raw_system(
        pack.registry, today, pack.prompt_profile, pack.prompt_rules
    )
    harness = build_harness_system(
        pack.registry, today, pack.prompt_profile,
        extra_rules=pack.prompt_rules,
    )
    assert hashlib.sha256(raw.encode()).hexdigest() == (
        "c69edf7fe902ac3fadd92cd34e77bf97b7e8200e331370c212316cde3ef9c180"
    )
    assert hashlib.sha256(harness.encode()).hexdigest() == (
        "2931b11240f483fc9bc497223fe3f21f9bc74a1ff6859f1dd0d6f4455d4e863f"
    )


def test_counter_prompts_and_normalizer_have_no_office_semantics():
    pack = load_domain("counter_demo")
    today = pack.default_today.strftime("%A, %B %d, %Y")
    prompts = [
        build_raw_system(
            pack.registry, today, pack.prompt_profile, pack.prompt_rules
        ),
        build_harness_system(
            pack.registry,
            today,
            pack.prompt_profile,
            extra_rules=pack.prompt_rules,
        ),
    ]
    for prompt in prompts:
        lowered = prompt.lower()
        assert "office" not in lowered
        assert "calendar" not in lowered
        assert "meeting" not in lowered
        assert "sam" not in lowered
    args = {"date": "tomorrow", "time": "2pm"}
    assert pack.normalize_args("fictional", args, pack.default_today) is args
    assert office_normalize(
        "set_reminder", args, datetime.date(2026, 7, 20)
    ) == {"date": "2026-07-21", "time": "14:00"}


def test_counter_harness_executes_two_identical_increments(tmp_path):
    attempt = make_attempt(
        tmp_path, "counter_demo", max_calls=5, suffix="counter"
    )
    llm = ScriptedLLM(
        [
            '{"steps":[{"tool":"increment_counter","what":"add one twice"}]}',
            '{"tool":"increment_counter","args":{"amount":1}}',
            '{"tool":"increment_counter","args":{"amount":1}}',
            '{"tool":"done","args":{"summary":"two"}}',
            '{"complete":true,"missing":""}',
        ]
    )
    episode = run_harness(
        llm, "Increase the counter by one twice.", attempt
    )
    score, checks = attempt.domain.tasks[0].grade(attempt)
    assert episode.finished
    assert attempt.world.value == 2
    assert score == 1.0
    assert all(passed for _, passed in checks)


def test_counter_rejects_bool_and_adversarial_grades(tmp_path):
    attempt = make_attempt(
        tmp_path, "counter_demo", suffix="adversarial"
    )
    ok, observation = attempt.tools.execute(
        "increment_counter", {"amount": True}, attempt
    )
    assert not ok
    assert "must be an integer" in observation

    attempt.world.value = 2
    attempt.actions[:] = [
        {
            "tool": "increment_counter",
            "args": {"amount": 2},
            "ok": True,
            "result": "",
        },
        {
            "tool": "increment_counter",
            "args": {"amount": 0},
            "ok": True,
            "result": "",
        },
    ]
    score, _ = attempt.domain.tasks[0].grade(attempt)
    assert score < 1.0


def test_sequential_attempts_share_delegate_without_sharing_budget(
    tmp_path,
):
    llm = ScriptedLLM(
        [
            '{"tool":"done","args":{"summary":"one"}}',
            '{"tool":"done","args":{"summary":"two"}}',
        ]
    )
    first = make_attempt(
        tmp_path,
        "counter_demo",
        condition="raw",
        max_calls=1,
        suffix="first",
    )
    second = make_attempt(
        tmp_path,
        "counter_demo",
        condition="raw",
        max_calls=1,
        suffix="second",
    )
    assert run_raw(llm, "first", first).finished
    assert run_raw(llm, "second", second).finished
    assert llm.calls == 2


class ReentrantLLM(ScriptedLLM):
    """Runs another domain's whole attempt from inside one model call.

    This suspends the outer loop mid-attempt, so both domains are live on the
    same interpreter at the same time rather than merely one after the other.
    """

    def __init__(self, replies, inner):
        super().__init__(replies)
        self._inner = inner
        self.inner_result = None

    def chat(self, messages, **kwargs):
        if self._inner is not None:
            inner, self._inner = self._inner, None
            self.inner_result = inner()
        return super().chat(messages, **kwargs)


def test_two_domains_interleave_in_one_process_without_leakage(tmp_path):
    office_notes = []
    counter_notes = []
    office = make_attempt(
        tmp_path,
        "office_demo",
        condition="raw",
        max_calls=4,
        hooks=RunHooks(on_note=lambda kind, content: office_notes.append(kind)),
        suffix="interleaved-office",
    )
    counter = make_attempt(
        tmp_path,
        "counter_demo",
        condition="raw",
        max_calls=3,
        hooks=RunHooks(
            on_note=lambda kind, content: counter_notes.append(kind)
        ),
        suffix="interleaved-counter",
    )

    # Clocks, registries, policies and storage are per attempt, not per process.
    assert office.config.today != counter.config.today
    assert office.workdir != counter.workdir
    assert office.artifact_dir != counter.artifact_dir
    assert office.memory.path != counter.memory.path
    builtins = {"think", "save_memory", "recall_memories", "done"}
    assert set(office.tools.names()) & set(counter.tools.names()) == builtins
    assert office.policy.effect_by_tool is not counter.policy.effect_by_tool
    assert "increment_counter" not in office.policy.effect_by_tool
    assert "send_email" not in counter.policy.effect_by_tool
    with pytest.raises(TypeError):
        office.policy.effect_by_tool["increment_counter"] = "shell"
    office_docs = office.tools.docs(True)
    counter_docs = counter.tools.docs(True)

    counter_llm = ScriptedLLM(
        [
            '{"tool":"increment_counter","args":{"amount":1}}',
            '{"tool":"increment_counter","args":{"amount":1}}',
            '{"tool":"done","args":{"summary":"two"}}',
        ]
    )
    office_llm = ReentrantLLM(
        [
            '{"tool":"list_emails","args":{}}',
            '{"tool":"save_memory","args":{"fact":"Jordan prefers a bullet list."}}',
            '{"tool":"done","args":{"summary":"listed"}}',
        ],
        inner=lambda: run_raw(
            counter_llm, "Increase the counter by one twice.", counter
        ),
    )

    office_episode = run_raw(office_llm, "List my emails.", office)
    counter_episode = office_llm.inner_result

    assert office_episode.finished and counter_episode.finished
    assert office_llm.calls == 3
    assert counter_llm.calls == 3

    # Each attempt kept its own world, action log, memory and graded outcome.
    assert counter.world.value == 2
    assert office.world.emails
    assert {action["tool"] for action in office.actions} == {
        "list_emails",
        "save_memory",
    }
    assert {action["tool"] for action in counter.actions} == {
        "increment_counter"
    }
    assert counter.domain.tasks[0].grade(counter)[0] == 1.0
    assert office.memory.all() == ["Jordan prefers a bullet list."]
    assert counter.memory.all() == []

    # Observation hooks saw only their own attempt's notes.
    assert len(office_notes) == len(office_episode.transcript)
    assert len(counter_notes) == len(counter_episode.transcript)

    # Neither prompt inherited the other domain's clock or tool documentation.
    office_system = next(
        item["content"]
        for item in office_episode.transcript
        if item["kind"] == "system"
    )
    counter_system = next(
        item["content"]
        for item in counter_episode.transcript
        if item["kind"] == "system"
    )
    assert office.config.today_human in office_system
    assert counter.config.today_human in counter_system
    assert counter.config.today_human not in office_system
    assert office.config.today_human not in counter_system
    assert "increment_counter" not in office_system
    assert "list_emails" not in counter_system

    # Running both did not mutate either immutable registry.
    assert office.tools.docs(True) == office_docs
    assert counter.tools.docs(True) == counter_docs


def test_hook_mutation_and_hook_errors_cannot_rewrite_evidence(
    tmp_path,
):
    seen = []

    def tool_hook(name, args, ok, observation):
        args["amount"] = 99
        seen.append(args)
        raise RuntimeError("observer failed")

    hooks = RunHooks(
        on_note=lambda kind, content: (_ for _ in ()).throw(
            RuntimeError("note observer failed")
        ),
        on_tool=tool_hook,
    )
    attempt = make_attempt(
        tmp_path, "counter_demo", hooks=hooks, suffix="hooks"
    )
    ok, _ = attempt.tools.execute(
        "increment_counter", {"amount": 1}, attempt
    )
    assert ok
    assert seen == [{"amount": 99}]
    assert attempt.actions[-1]["args"] == {"amount": 1}

    llm = ScriptedLLM(
        [
            '{"tool":"done","args":{"summary":"ok"}}',
        ]
    )
    raw_attempt = make_attempt(
        tmp_path,
        "counter_demo",
        condition="raw",
        max_calls=1,
        hooks=hooks,
        suffix="note-hook",
    )
    assert run_raw(llm, "done", raw_attempt).finished


def test_observation_limits_are_attempt_local_in_actual_loops(tmp_path):
    first = make_attempt(
        tmp_path,
        condition="raw",
        max_calls=2,
        observation_limit=12,
        suffix="short",
    )
    second = make_attempt(
        tmp_path,
        condition="raw",
        max_calls=2,
        observation_limit=80,
        suffix="long",
    )
    replies = [
        '{"tool":"list_emails","args":{}}',
        '{"tool":"done","args":{"summary":"ok"}}',
    ]
    first_episode = run_raw(
        ScriptedLLM(replies), "list", first
    )
    second_episode = run_raw(
        ScriptedLLM(replies), "list", second
    )
    first_observation = next(
        item["content"]
        for item in first_episode.transcript
        if item["kind"] == "observation"
    )
    second_observation = next(
        item["content"]
        for item in second_episode.transcript
        if item["kind"] == "observation"
    )
    assert first_observation.endswith(" ...[truncated]")
    assert second_observation.endswith(" ...[truncated]")
    assert len(second_observation) - len(first_observation) == 68


def test_office_worlds_and_canonical_fixtures_are_deeply_isolated(
    tmp_path,
):
    first = load_domain("office_demo").make_world(tmp_path / "first")
    second = load_domain("office_demo").make_world(tmp_path / "second")
    first.events[2]["attendees"].append("poison@example.test")
    assert second.events[2]["attendees"] == ["sam@corp.com"]

    original = office_world.CALENDAR[2]["attendees"][:]
    try:
        office_world.CALENDAR[2]["attendees"].append(
            "public-poison@example.test"
        )
        third = load_domain("office_demo").make_world(
            tmp_path / "third"
        )
        assert third.events[2]["attendees"] == ["sam@corp.com"]
    finally:
        office_world.CALENDAR[2]["attendees"][:] = original


def test_general_filesystem_and_shell_overlay_is_not_importable():
    assert importlib.util.find_spec("harness.fs_tools") is None
    retired = {
        "list_dir",
        "read_file",
        "write_file",
        "append_file",
        "delete_path",
        "move_path",
        "search_files",
        "run_command",
    }
    for name in ("office_demo", "counter_demo"):
        assert retired.isdisjoint(load_domain(name).registry.names())


def test_action_confirmation_fails_closed_without_a_callback():
    assert not ActionPolicy({"write": "external_write"}).confirm(
        "write", "synthetic detail"
    )
    assert ActionPolicy(
        {"write": "external_write"},
        confirmer=lambda action, detail: True,
    ).confirm("write", "synthetic detail")


def test_model_router_freezes_roles_and_isolates_role_clients(
    monkeypatch,
):
    created = []

    class FakeClient:
        def __init__(self, model, **kwargs):
            self.model = model
            self.temperature = kwargs["temperature"]
            self.calls = 0
            self.output_tokens = 0
            self.prompt_tokens = 0
            self.wall = 0.0
            created.append(self)

        def chat(self, messages, **kwargs):
            self.calls += 1
            return "{}"

    monkeypatch.setattr("harness.model_router.LLM", FakeClient)
    roles = {
        "driver": {
            "model": "same",
            "temperature": 0.0,
            "metadata": {"labels": ["original"]},
        },
        "verifier": {"model": "same", "temperature": 0.8},
    }
    router = ModelRouter(roles=roles, default_role="driver")
    roles["driver"]["temperature"] = 9.0
    roles["driver"]["metadata"]["labels"].append("poison")
    router.chat([], role="driver")
    router.chat([], role="verifier")
    assert [client.temperature for client in created] == [0.0, 0.8]
    assert router.retained_model_hints() == ["same"]
    assert router.roles["driver"]["metadata"]["labels"] == ("original",)
    with pytest.raises(TypeError):
        router.roles["driver"]["metadata"]["x"] = "poison"
    assert len(router._clients) == 2
    with pytest.raises(ValueError, match="unknown model role"):
        router.chat([], role="typo")


def test_stream_hooks_are_scoped_to_individual_llm_clients(monkeypatch):
    events = []

    class Response:
        def __init__(self, streamed):
            self.streamed = streamed

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {"content": "plain"},
                "prompt_eval_count": 1,
                "eval_count": 1,
            }

        def iter_lines(self, decode_unicode=False):
            yield (
                '{"message":{"content":"stream"},"done":false}'
            )
            yield '{"done":true,"prompt_eval_count":1,"eval_count":1}'

    calls = []

    def fake_post(url, json, timeout, stream=False):
        calls.append(stream)
        return Response(stream)

    monkeypatch.setattr("harness.llm.requests.post", fake_post)
    plain = LLM("plain")
    streamed = LLM(
        "streamed",
        stream_hook=lambda event, payload: events.append(
            (event, payload)
        ),
    )
    assert plain.chat([]) == "plain"
    assert streamed.chat([], role="driver") == "stream"
    assert calls == [False, True]
    assert [event for event, _ in events] == [
        "start",
        "token",
        "end",
    ]

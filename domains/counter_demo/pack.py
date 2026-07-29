"""Minimal independent DomainPack used by architecture tests."""
import datetime
import json
import os

from harness.builtin_tools import BUILTIN_EFFECTS, builtin_specs
from harness.domain import (
    DomainPack,
    GENERIC_PROMPT_PROFILE,
    TaskSpec,
    state_envelope,
)
from harness.runtime import ActionPolicy
from harness.tools import ToolRegistry

from .tools import counter_specs
from .world import CounterWorld


DOMAIN_NAME = "counter_demo"
DOMAIN_VERSION = "0.1.0"


def _make_world(workdir, persistent=False):
    return CounterWorld(workdir, persistent=persistent)


def _snapshot(attempt):
    attempt.world.snapshot(attempt.actions)


def _prepare_attempt(attempt):
    return None


def _normalize_args(name, args, today):
    return args


def _present(attempt):
    return state_envelope(
        DOMAIN_NAME,
        DOMAIN_VERSION,
        [
            {
                "id": "counter",
                "label": "counter",
                "icon": "🔢",
                "items": [{"value": attempt.world.value}],
            }
        ],
        [],
        attempt.memory.all(),
    )


def _inspect(workdir, memory_path):
    value = 0
    path = os.path.join(str(workdir), "state.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as stream:
                value = int(json.load(stream).get("value", 0))
        except (ValueError, TypeError):
            value = 0
    memory = []
    if os.path.isfile(memory_path):
        with open(memory_path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    memory.append(json.loads(line)["fact"])
                except (ValueError, KeyError):
                    pass
    return state_envelope(
        DOMAIN_NAME,
        DOMAIN_VERSION,
        [
            {
                "id": "counter",
                "label": "counter",
                "icon": "🔢",
                "items": [{"value": value}],
            }
        ],
        [],
        memory,
    )


def _grade(attempt):
    mutations = [
        action
        for action in attempt.actions
        if attempt.policy.is_mutating(action["tool"])
    ]
    increments = [
        action
        for action in mutations
        if action["tool"] == "increment_counter" and action["ok"]
    ]
    checks = [
        ("counter equals 2", attempt.world.value == 2),
        (
            "exactly two increments of one",
            len(increments) == 2
            and all(action["args"] == {"amount": 1} for action in increments),
        ),
        (
            "no unexpected mutations",
            len(increments) == len(mutations),
        ),
    ]
    return sum(bool(ok) for _, ok in checks) / len(checks), checks


_specs = counter_specs()
_specs.update(builtin_specs())
_effects = {
    "read_counter": "read",
    "increment_counter": "state_write",
}
_effects.update(BUILTIN_EFFECTS)

PACK = DomainPack(
    name=DOMAIN_NAME,
    version=DOMAIN_VERSION,
    registry=ToolRegistry(_specs),
    default_policy=ActionPolicy(_effects),
    default_today=datetime.date(2030, 1, 2),
    prompt_profile=GENERIC_PROMPT_PROFILE,
    prompt_rules="\n- Treat the counter as the only authoritative domain state.",
    make_world=_make_world,
    snapshot=_snapshot,
    prepare_attempt=_prepare_attempt,
    normalize_args=_normalize_args,
    present_state=_present,
    inspect_persisted_state=_inspect,
    tasks=(
        TaskSpec(
            id="counter_twice",
            capabilities=("counter_write",),
            prompt="Increase the counter by one twice.",
            grade=_grade,
            tool_names=tuple(_specs),
        ),
    ),
    presets=("Increase the counter by one twice.",),
)

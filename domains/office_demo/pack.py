"""DomainPack for the repository's current fictional office."""
import datetime
import inspect
import json
import os

from harness.builtin_tools import BUILTIN_EFFECTS, builtin_specs
from harness.domain import (
    DomainPack,
    PromptProfile,
    TaskSpec,
    state_envelope,
)
from harness.runtime import ActionPolicy
from harness.tools import ToolRegistry

from .tasks import TASKS
from .normalize import normalize_args
from .tools import OFFICE_EFFECTS, office_specs
from .world import World, fresh_calendar, fresh_emails


DOMAIN_NAME = "office_demo"
DOMAIN_VERSION = "0.1.0"
DEFAULT_TODAY = datetime.date(2026, 7, 20)
PROMPT_PROFILE = PromptProfile(
    raw_role=(
        "You are an assistant that completes office tasks using tools."
    ),
    harness_role="You are a careful office assistant agent.",
    scope=(
        "You interact with the world ONLY by calling tools, "
        "one call per reply."
    ),
    look_before_act=(
        "read the relevant emails or calendar before writing anything "
        "that depends on them."
    ),
    format_rule=(
        "- Dates must be YYYY-MM-DD. Times must be 24-hour HH:MM."
    ),
)

BUILTIN_EXAMPLES = {
    "think": {
        "tool": "think",
        "args": {
            "thought": (
                "Wednesday has 3 meetings; I should list them in time order."
            )
        },
    },
    "save_memory": {
        "tool": "save_memory",
        "args": {"fact": "User's manager is Sam."},
    },
    "recall_memories": {
        "tool": "recall_memories",
        "args": {"query": "meeting preferences"},
    },
    "done": {
        "tool": "done",
        "args": {"summary": "Booked the meeting and messaged Sam."},
    },
}

PRESETS = (
    "Summarize my Wednesday meetings and message Jordan with the list",
    "Find a free hour on Thursday and book it as Deep work",
    "Turn Dana's Q3 sales numbers into a PowerPoint deck",
    "Build a spreadsheet of my July receipts with a total",
    "Reply to Mia about the Northwind kickoff and add it to my calendar",
    "Remember that I prefer meetings after 14:00 and never on Fridays",
)


def _make_world(workdir, persistent=False):
    return World(str(workdir), persistent=persistent)


def _snapshot(attempt):
    attempt.world.snapshot()


def _prepare_attempt(attempt):
    # Compatibility for office graders and UI code; AttemptContext remains the
    # owner of the list.
    attempt.world.actions = attempt.actions


def _file_rows(files_dir):
    rows = []
    if not os.path.isdir(files_dir):
        return rows
    for name in sorted(os.listdir(files_dir)):
        path = os.path.join(files_dir, name)
        if os.path.isfile(path):
            stat = os.stat(path)
            rows.append({"name": name, "size": stat.st_size, "mtime": stat.st_mtime})
    return rows


def _present_state(attempt):
    world = attempt.world
    return state_envelope(
        DOMAIN_NAME,
        DOMAIN_VERSION,
        [
            {
                "id": "emails",
                "label": "inbox",
                "icon": "📥",
                "items": world.emails,
            },
            {
                "id": "events",
                "label": "calendar",
                "icon": "📅",
                "items": sorted(
                    world.events,
                    key=lambda event: (event["date"], event["start"]),
                ),
            },
            {
                "id": "messages",
                "label": "messages",
                "icon": "💬",
                "items": world.messages,
            },
            {
                "id": "reminders",
                "label": "reminders",
                "icon": "⏰",
                "items": world.reminders,
            },
            {
                "id": "sent",
                "label": "sent mail",
                "icon": "📤",
                "items": world.sent_emails,
            },
        ],
        _file_rows(world.files_dir),
        attempt.memory.all(),
    )


def _inspect_persisted_state(workdir, memory_path):
    state_path = os.path.join(str(workdir), "state.json")
    files_dir = os.path.join(str(workdir), "files")
    state = {}
    if os.path.isfile(state_path):
        try:
            with open(state_path, encoding="utf-8") as stream:
                state = json.load(stream)
        except ValueError:
            state = {}
    if not state:
        state = {
            "emails": fresh_emails(),
            "events": fresh_calendar(),
        }

    memory = []
    if os.path.isfile(memory_path):
        with open(memory_path, encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    memory.append(json.loads(line)["fact"])
                except (ValueError, KeyError):
                    pass
    return state_envelope(
        DOMAIN_NAME,
        DOMAIN_VERSION,
        [
            {
                "id": "emails",
                "label": "inbox",
                "icon": "📥",
                "items": state.get("emails", []),
            },
            {
                "id": "events",
                "label": "calendar",
                "icon": "📅",
                "items": sorted(
                    state.get("events", []),
                    key=lambda event: (event["date"], event["start"]),
                ),
            },
            {
                "id": "messages",
                "label": "messages",
                "icon": "💬",
                "items": state.get("messages", []),
            },
            {
                "id": "reminders",
                "label": "reminders",
                "icon": "⏰",
                "items": state.get("reminders", []),
            },
            {
                "id": "sent",
                "label": "sent mail",
                "icon": "📤",
                "items": state.get("sent_emails", []),
            },
        ],
        _file_rows(files_dir),
        memory,
    )


def _task_spec(task):
    grader = task["grade"]

    def grade_attempt(attempt):
        if "mem" in inspect.signature(grader).parameters:
            return grader(attempt.world, mem=attempt.memory)
        return grader(attempt.world)

    return TaskSpec(
        id=task["id"],
        capabilities=tuple(task["caps"]),
        prompt=task["prompt"],
        grade=grade_attempt,
        # Preserve the historical benchmark surface exactly.  A future
        # version may narrow individual tasks without teaching generic bench
        # code about office capability labels.
        tool_names=tuple(_registry.names()),
    )


_specs = office_specs()
_specs.update(builtin_specs(BUILTIN_EXAMPLES))
_registry = ToolRegistry(_specs)
_effects = dict(OFFICE_EFFECTS)
_effects.update(BUILTIN_EFFECTS)

PACK = DomainPack(
    name=DOMAIN_NAME,
    version=DOMAIN_VERSION,
    registry=_registry,
    default_policy=ActionPolicy(_effects),
    default_today=DEFAULT_TODAY,
    prompt_profile=PROMPT_PROFILE,
    prompt_rules="",
    make_world=_make_world,
    snapshot=_snapshot,
    prepare_attempt=_prepare_attempt,
    normalize_args=normalize_args,
    present_state=_present_state,
    inspect_persisted_state=_inspect_persisted_state,
    tasks=tuple(_task_spec(task) for task in TASKS),
    presets=PRESETS,
    # Preserve existing ignored local workspace/memory/logs without copying or
    # deleting private state. Other domains and future versions are namespaced.
    runtime_layout="legacy_agent_v0",
)

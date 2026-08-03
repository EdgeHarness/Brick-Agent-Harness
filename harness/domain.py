"""Domain-pack contract and convention-validated loader."""
from dataclasses import dataclass
import copy
import datetime
import importlib
import inspect
import math
import re
from typing import Any, Callable, Tuple

from .runtime import ActionPolicy
from .tools import ToolRegistry
from .grading import GraderSpec


_DOMAIN_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_TASK_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SECTION_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
_UI_SECTION_IDS = frozenset(
    {"files", "memory", "real", "runs", "constructor", "prototype"}
)
_WINDOWS_DEVICE_IDS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:"
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*"
    r"))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

DONE_TOOL_NAME = "done"
THINK_TOOL_NAME = "think"
DONE_DESCRIPTION = (
    "Call this exactly once, when the entire task is finished, "
    "with a short summary."
)
THINK_DESCRIPTION = (
    "Think out loud about the task. Use this to reason before acting. "
    "Has no external effect."
)
DONE_PARAMS = {"summary": ("string", True)}
THINK_PARAMS = {"thought": ("string", True)}


def _require_call_shape(callback, label, *args, **kwargs):
    try:
        inspect.signature(callback).bind(*args, **kwargs)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} has an incompatible call signature") from exc


@dataclass(frozen=True)
class TaskSpec:
    id: str
    capabilities: Tuple[str, ...]
    prompt: str
    grader: GraderSpec
    tool_names: Tuple[str, ...]

    def __post_init__(self):
        if (
            not isinstance(self.id, str)
            or not _TASK_ID.fullmatch(self.id)
            or self.id in _WINDOWS_DEVICE_IDS
        ):
            raise ValueError(
                f"task id {self.id!r} must be a portable identifier "
                f"matching {_TASK_ID.pattern}"
            )
        if not isinstance(self.capabilities, tuple):
            raise TypeError("task capabilities must be a tuple")
        if not all(
            isinstance(capability, str) and capability
            for capability in self.capabilities
        ):
            raise ValueError("task capabilities must be nonempty strings")
        if not isinstance(self.prompt, str) or not self.prompt:
            raise ValueError("task prompt must be a nonempty string")
        if not isinstance(self.grader, GraderSpec):
            raise TypeError("task grader must be a GraderSpec")
        if not isinstance(self.tool_names, tuple) or not self.tool_names:
            raise ValueError("task tool_names must be a nonempty tuple")
        if not all(
            isinstance(tool_name, str) and tool_name
            for tool_name in self.tool_names
        ):
            raise ValueError("task tool_names must be nonempty strings")
        if len(set(self.tool_names)) != len(self.tool_names):
            raise ValueError(f"task {self.id!r} has duplicate tool names")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError(f"task {self.id!r} has duplicate capabilities")

    @property
    def grade(self):
        """Compatibility alias; new runtime code uses ``grader`` explicitly."""
        return self.grader


@dataclass(frozen=True)
class PromptProfile:
    """Domain-owned wording inserted into domain-neutral prompt templates."""

    raw_role: str
    harness_role: str
    scope: str
    look_before_act: str
    format_rule: str = ""

    def __post_init__(self):
        for value, label in (
            (self.raw_role, "raw_role"),
            (self.harness_role, "harness_role"),
            (self.scope, "scope"),
            (self.look_before_act, "look_before_act"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{label} must be a nonempty string")
        if not isinstance(self.format_rule, str):
            raise TypeError("format_rule must be a string")


GENERIC_PROMPT_PROFILE = PromptProfile(
    raw_role="You are an assistant that completes tasks using tools.",
    harness_role="You are a careful assistant agent.",
    scope="You interact with the task environment ONLY by calling tools, one call per reply.",
    look_before_act=(
        "inspect relevant state before writing anything that depends on it."
    ),
    format_rule="",
)


@dataclass(frozen=True)
class DomainPack:
    name: str
    version: str
    registry: ToolRegistry
    default_policy: ActionPolicy
    default_today: datetime.date
    prompt_profile: PromptProfile
    prompt_rules: str
    make_world: Callable[..., Any]
    snapshot: Callable[[Any], None]
    prepare_attempt: Callable[[Any], None]
    normalize_args: Callable[[str, dict, datetime.date], dict]
    present_state: Callable[..., dict]
    inspect_persisted_state: Callable[..., dict]
    capture_grading_state: Callable[[Any], Any]
    tasks: Tuple[TaskSpec, ...] = ()
    presets: Tuple[str, ...] = ()
    runtime_layout: str = "namespaced_v1"

    def __post_init__(self):
        if (
            not isinstance(self.name, str)
            or not _DOMAIN_ID.fullmatch(self.name)
            or self.name in _WINDOWS_DEVICE_IDS
        ):
            raise ValueError(f"invalid domain name {self.name!r}")
        if not isinstance(self.version, str) or not _SEMVER.fullmatch(
            self.version
        ):
            raise ValueError(
                f"domain version {self.version!r} is not semantic versioning"
            )
        if not isinstance(self.default_policy, ActionPolicy):
            raise TypeError("default_policy must be an ActionPolicy")
        if not isinstance(self.registry, ToolRegistry):
            raise TypeError("registry must be a ToolRegistry")
        if type(self.default_today) is not datetime.date:
            raise TypeError("default_today must be a date, not a datetime")
        if not isinstance(self.prompt_profile, PromptProfile):
            raise TypeError("prompt_profile must be a PromptProfile")
        if not isinstance(self.prompt_rules, str):
            raise TypeError("prompt_rules must be a string")
        if not isinstance(self.tasks, tuple):
            raise TypeError("tasks must be a tuple")
        if not isinstance(self.presets, tuple):
            raise TypeError("presets must be a tuple")
        if not all(isinstance(preset, str) and preset for preset in self.presets):
            raise ValueError("presets must be nonempty strings")
        if len(set(self.presets)) != len(self.presets):
            raise ValueError("domain presets must be unique")
        if self.runtime_layout not in {
            "namespaced_v1",
            "legacy_agent_v0",
        }:
            raise ValueError(
                f"unknown runtime layout {self.runtime_layout!r}"
            )
        registry_names = tuple(self.registry.names())
        if not registry_names:
            raise ValueError("domain registry cannot be empty")
        if DONE_TOOL_NAME not in registry_names:
            raise ValueError("domain registry must include reserved tool 'done'")
        done = self.registry[DONE_TOOL_NAME]
        if (
            done["desc"] != DONE_DESCRIPTION
            or done["params"] != DONE_PARAMS
            or done["run"] is not None
        ):
            raise ValueError("domain redefines reserved tool 'done'")
        if THINK_TOOL_NAME in registry_names:
            think = self.registry[THINK_TOOL_NAME]
            if (
                think["desc"] != THINK_DESCRIPTION
                or think["params"] != THINK_PARAMS
                or not callable(think["run"])
            ):
                raise ValueError("domain redefines reserved tool 'think'")
        self.default_policy.validate_registry(registry_names)
        if not all(isinstance(task, TaskSpec) for task in self.tasks):
            raise TypeError("tasks must contain TaskSpec values")
        task_ids = [task.id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("domain task ids must be unique")
        known = set(registry_names)
        for task in self.tasks:
            unknown = set(task.tool_names) - known
            if unknown:
                raise ValueError(
                    f"task {task.id!r} references unknown tools: "
                    + ", ".join(sorted(unknown))
                )
            if DONE_TOOL_NAME not in task.tool_names:
                raise ValueError(
                    f"task {task.id!r} must select reserved tool 'done'"
                )
        for value, label in (
            (self.make_world, "make_world"),
            (self.snapshot, "snapshot"),
            (self.prepare_attempt, "prepare_attempt"),
            (self.normalize_args, "normalize_args"),
            (self.present_state, "present_state"),
            (self.inspect_persisted_state, "inspect_persisted_state"),
            (self.capture_grading_state, "capture_grading_state"),
        ):
            if not callable(value):
                raise TypeError(f"{label} must be callable")
        _require_call_shape(
            self.make_world,
            "make_world",
            object(),
            persistent=False,
        )
        for callback, label in (
            (self.snapshot, "snapshot"),
            (self.prepare_attempt, "prepare_attempt"),
            (self.present_state, "present_state"),
            (self.capture_grading_state, "capture_grading_state"),
        ):
            _require_call_shape(callback, label, object())
        _require_call_shape(
            self.normalize_args,
            "normalize_args",
            "tool",
            {},
            self.default_today,
        )
        _require_call_shape(
            self.inspect_persisted_state,
            "inspect_persisted_state",
            object(),
            object(),
        )

    def registry_for(self, task):
        """Return the task's domain-selected tools in canonical pack order."""
        if not isinstance(task, TaskSpec):
            raise TypeError("task must be a TaskSpec")
        return self.registry.selected(task.tool_names)

    def present(self, attempt):
        return validate_state_envelope(
            copy.deepcopy(self.present_state(attempt)),
            self.name,
            self.version,
        )

    def inspect(self, workdir, memory_path):
        return validate_state_envelope(
            copy.deepcopy(
                self.inspect_persisted_state(workdir, memory_path)
            ),
            self.name,
            self.version,
        )


def state_envelope(domain, version, sections, files, memory):
    """Build the generic-UI state contract.

    Sections have safe, unique ``id`` values plus a label and item list.
    Files contain ``name``, nonnegative numeric ``size``, and numeric ``mtime``.
    Memory contains display-ready strings.
    """
    envelope = {
        "domain": domain,
        "version": version,
        "sections": copy.deepcopy(list(sections)),
        "files": copy.deepcopy(list(files)),
        "memory": copy.deepcopy(list(memory)),
    }
    return validate_state_envelope(envelope, domain, version)


def validate_state_envelope(envelope, domain=None, version=None):
    required = {"domain", "version", "sections", "files", "memory"}
    if not isinstance(envelope, dict) or not required.issubset(envelope):
        raise ValueError(
            "state must contain domain, version, sections, files, and memory"
        )
    if domain is not None and envelope["domain"] != domain:
        raise ValueError("state domain does not match its pack")
    if version is not None and envelope["version"] != version:
        raise ValueError("state version does not match its pack")
    if not _DOMAIN_ID.fullmatch(str(envelope["domain"])):
        raise ValueError("state domain is invalid")
    if not _SEMVER.fullmatch(str(envelope["version"])):
        raise ValueError("state version is invalid")
    if not isinstance(envelope["sections"], list):
        raise TypeError("state sections must be a list")
    section_ids = []
    for section in envelope["sections"]:
        if not isinstance(section, dict):
            raise TypeError("each state section must be a dictionary")
        if not {"id", "label", "items"}.issubset(section):
            raise ValueError("state sections require id, label, and items")
        if (
            not isinstance(section["id"], str)
            or not _SECTION_ID.fullmatch(section["id"])
            or section["id"] in _UI_SECTION_IDS
        ):
            raise ValueError(
                "state section id must be a safe, non-reserved identifier"
            )
        if not isinstance(section["label"], str) or not section["label"]:
            raise ValueError("state section label must be nonempty")
        if not isinstance(section["items"], list):
            raise TypeError("state section items must be a list")
        section_ids.append(section["id"])
    if len(set(section_ids)) != len(section_ids):
        raise ValueError("state section ids must be unique")
    if not isinstance(envelope["files"], list):
        raise TypeError("state files must be a list")
    for entry in envelope["files"]:
        if not isinstance(entry, dict):
            raise TypeError("each state file must be a dictionary")
        if not {"name", "size", "mtime"}.issubset(entry):
            raise ValueError("state files require name, size, and mtime")
        if not isinstance(entry["name"], str) or not entry["name"]:
            raise ValueError("state file name must be a nonempty string")
        size = entry["size"]
        if (
            isinstance(size, bool)
            or not isinstance(size, (int, float))
            or not math.isfinite(size)
            or size < 0
        ):
            raise ValueError(
                "state file size must be a nonnegative finite number"
            )
        mtime = entry["mtime"]
        if (
            isinstance(mtime, bool)
            or not isinstance(mtime, (int, float))
            or not math.isfinite(mtime)
        ):
            raise ValueError("state file mtime must be a finite number")
    if not isinstance(envelope["memory"], list):
        raise TypeError("state memory must be a list")
    if not all(isinstance(item, str) for item in envelope["memory"]):
        raise TypeError("state memory entries must be strings")
    return envelope


def load_domain(name):
    """Load ``domains.<name>.PACK`` without a central mutable registry."""
    if not isinstance(name, str) or not _DOMAIN_ID.fullmatch(name):
        raise ValueError(f"invalid domain id {name!r}")
    module = importlib.import_module(f"domains.{name}")
    pack = getattr(module, "PACK", None)
    if not isinstance(pack, DomainPack):
        raise TypeError(f"domains.{name}.PACK is not a DomainPack")
    if pack.name != name:
        raise ValueError(
            f"domain module {name!r} exports pack named {pack.name!r}"
        )
    return pack

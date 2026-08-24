"""Explicit, per-attempt runtime configuration.

The objects in this module replace the old process-global clock, budget,
policy, registry and observation hooks.  Immutable inputs are shared safely;
mutable state lives only on one AttemptContext.
"""
import copy
from dataclasses import dataclass, field, replace
import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

from .tools import ToolRegistry


ConfirmCallback = Callable[[str, str], bool]
NoteHook = Callable[[str, Any], None]
ToolHook = Callable[[str, dict, bool, str], None]
ALLOWED_EFFECTS = frozenset(
    {"read", "state_write", "external_write", "shell"}
)


@dataclass(frozen=True)
class RunConfig:
    """Resolved agent-loop settings for one attempt."""

    condition: str
    max_calls: int
    today: datetime.date
    observation_limit: int = 2000
    verifier_rounds: int = 2
    prompt_rules: str = ""
    # Advisory cross-checks (harness/guards.py). Off by default so bench/
    # comparisons never shift; interactive callers turn them on explicitly.
    guards: bool = False
    # Prior conversation turns as a text block, for the done-echo guard.
    history: str = ""

    def __post_init__(self):
        if self.condition not in {"raw", "harness"}:
            raise ValueError(f"unknown condition {self.condition!r}")
        if type(self.max_calls) is not int:
            raise TypeError("max_calls must be an integer")
        if self.max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        if type(self.today) is not datetime.date:
            raise TypeError("today must be a date, not a datetime")
        if type(self.observation_limit) is not int:
            raise TypeError("observation_limit must be an integer")
        if self.observation_limit < 1:
            raise ValueError("observation_limit must be at least 1")
        if type(self.verifier_rounds) is not int:
            raise TypeError("verifier_rounds must be an integer")
        if self.verifier_rounds < 0:
            raise ValueError("verifier_rounds cannot be negative")
        if not isinstance(self.prompt_rules, str):
            raise TypeError("prompt_rules must be a string")
        if type(self.guards) is not bool:
            raise TypeError("guards must be a bool")
        if not isinstance(self.history, str):
            raise TypeError("history must be a string")

    @property
    def today_human(self):
        return self.today.strftime("%A, %B %d, %Y")


@dataclass(frozen=True)
class RunHooks:
    """Best-effort observation callbacks scoped to one attempt.

    Hook exceptions are ignored: observers cannot change tool results or abort
    an otherwise valid attempt. Streaming is configured separately per LLM.
    """

    on_note: Optional[NoteHook] = None
    on_tool: Optional[ToolHook] = None

    def __post_init__(self):
        for hook, label in (
            (self.on_note, "on_note"),
            (self.on_tool, "on_tool"),
        ):
            if hook is not None and not callable(hook):
                raise TypeError(f"{label} must be callable or None")


@dataclass(frozen=True)
class ActionPolicy:
    """Classifies tool effects and carries the run's confirmation callback.

    This is an execution-policy seam, not an authentication or OS sandbox.
    """

    effect_by_tool: Mapping[str, str] = field(default_factory=dict)
    confirmer: Optional[ConfirmCallback] = None

    def __post_init__(self):
        if not isinstance(self.effect_by_tool, Mapping):
            raise TypeError("effect_by_tool must be a mapping")
        effects = dict(self.effect_by_tool)
        for tool_name, effect in effects.items():
            if not isinstance(tool_name, str) or not tool_name:
                raise ValueError("policy tool names must be nonempty strings")
            if effect not in ALLOWED_EFFECTS:
                raise ValueError(
                    f"unknown effect {effect!r} for tool {tool_name!r}"
                )
        if self.confirmer is not None and not callable(self.confirmer):
            raise TypeError("confirmer must be callable or None")
        object.__setattr__(
            self, "effect_by_tool", MappingProxyType(effects)
        )

    def effect(self, tool_name):
        return self.effect_by_tool.get(tool_name, "read")

    def is_mutating(self, tool_name):
        return self.effect(tool_name) != "read"

    def validate_tools(self, tool_names):
        """Require classifications for every tool active in one attempt."""
        missing = set(tool_names) - set(self.effect_by_tool)
        if missing:
            raise ValueError(
                "action policy is missing classifications for active tools: "
                + ", ".join(sorted(missing))
            )

    def validate_registry(self, tool_names):
        """Require one explicit effect classification per registered tool."""
        registered = set(tool_names)
        classified = set(self.effect_by_tool)
        missing = registered - classified
        unknown = classified - registered
        if missing or unknown:
            details = []
            if missing:
                details.append(
                    "missing classifications: " + ", ".join(sorted(missing))
                )
            if unknown:
                details.append(
                    "unknown classifications: " + ", ".join(sorted(unknown))
                )
            raise ValueError(
                "action policy must classify exactly the domain registry ("
                + "; ".join(details)
                + ")"
            )

    def with_effects(self, effects, confirmer=None):
        merged = dict(self.effect_by_tool)
        merged.update(effects)
        return replace(
            self,
            effect_by_tool=merged,
            confirmer=self.confirmer if confirmer is None else confirmer,
        )

    def confirm(self, action, detail):
        # Absence of an explicit decision channel is denial, never consent.
        return (
            False
            if self.confirmer is None
            else bool(self.confirmer(action, detail))
        )


@dataclass
class AttemptContext:
    """All mutable and immutable dependencies for one agent attempt."""

    attempt_id: str
    config: RunConfig
    domain: Any
    tools: Any
    policy: ActionPolicy
    world: Any
    memory: Any
    workdir: Path
    artifact_dir: Path
    prompt_profile: Any = None
    prompt_rules: Optional[str] = None
    hooks: RunHooks = field(default_factory=RunHooks)
    actions: list = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.attempt_id, str) or not self.attempt_id:
            raise ValueError("attempt_id must be a nonempty string")
        if not isinstance(self.config, RunConfig):
            raise TypeError("config must be a RunConfig")
        if not isinstance(self.tools, ToolRegistry):
            raise TypeError("tools must be a ToolRegistry")
        if not isinstance(self.policy, ActionPolicy):
            raise TypeError("policy must be an ActionPolicy")
        self.policy.validate_tools(self.tools.names())
        if not isinstance(self.hooks, RunHooks):
            raise TypeError("hooks must be RunHooks")
        self.workdir = Path(self.workdir)
        self.artifact_dir = Path(self.artifact_dir)
        self.actions = copy.deepcopy(list(self.actions))
        self.domain.prepare_attempt(self)

    def record_action(self, tool, args, ok, result_preview):
        record = {
            "tool": tool,
            "args": copy.deepcopy(args),
            "ok": ok,
            "result": str(result_preview)[:300],
        }
        self.actions.append(record)

    @property
    def resolved_prompt_profile(self):
        return self.prompt_profile or self.domain.prompt_profile

    @property
    def resolved_prompt_rules(self):
        if self.prompt_rules is None:
            return self.domain.prompt_rules
        return self.prompt_rules

    def snapshot(self):
        self.domain.snapshot(self)

"""Immutable tool registry shared by raw and harness conditions."""
import copy
import inspect
import json
from collections.abc import Mapping
import re
from types import MappingProxyType

from .errors import ToolError

_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class _FrozenList(tuple):
    """Internal marker so public copies restore list rather than tuple."""


def _freeze(value):
    if callable(value):
        # Executors are trusted code and remain opaque; only their surrounding
        # schema/documentation is recursively frozen.
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return copy.deepcopy(value)


def _thaw(value):
    if callable(value):
        return value
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, _FrozenList):
        return [_thaw(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_thaw(item) for item in value)
    if isinstance(value, frozenset):
        return {_thaw(item) for item in value}
    return copy.deepcopy(value)


def _fmt(result):
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


def _validate_spec(name, spec):
    if not isinstance(name, str) or not _TOOL_NAME.fullmatch(name):
        raise ValueError(
            f"tool name {name!r} must match {_TOOL_NAME.pattern}"
        )
    if not isinstance(spec, Mapping):
        raise TypeError(f"tool {name!r} spec must be a mapping")
    required_keys = {"desc", "params", "example", "run"}
    missing = required_keys - set(spec)
    if missing:
        raise ValueError(
            f"tool {name!r} is missing fields: "
            + ", ".join(sorted(missing))
        )
    if not isinstance(spec["desc"], str) or not spec["desc"]:
        raise ValueError(f"tool {name!r} desc must be a nonempty string")
    if not isinstance(spec["params"], Mapping):
        raise TypeError(f"tool {name!r} params must be a mapping")
    for param, schema in spec["params"].items():
        if not isinstance(param, str) or not _TOOL_NAME.fullmatch(param):
            raise ValueError(
                f"tool {name!r} parameter {param!r} is invalid"
            )
        if not isinstance(schema, (tuple, list)) or len(schema) != 2:
            raise TypeError(
                f"tool {name!r} parameter {param!r} needs "
                "(type description, required)"
            )
        type_description, required = schema
        if not isinstance(type_description, str) or not type_description:
            raise ValueError(
                f"tool {name!r} parameter {param!r} type must be nonempty"
            )
        if type(required) is not bool:
            raise TypeError(
                f"tool {name!r} parameter {param!r} required must be bool"
            )
    example = spec["example"]
    if (
        not isinstance(example, Mapping)
        or example.get("tool") != name
        or not isinstance(example.get("args"), Mapping)
    ):
        raise ValueError(
            f"tool {name!r} example must name the tool and contain args"
        )
    executor = spec["run"]
    if name == "done":
        if executor is not None:
            raise ValueError("reserved tool 'done' executor must be None")
    elif not callable(executor):
        raise TypeError(f"tool {name!r} executor must be callable")
    else:
        try:
            inspect.signature(executor).bind(object(), {})
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"tool {name!r} executor must accept (attempt, args)"
            ) from exc
    suppress = spec.get("suppress_identical_repeats", True)
    if type(suppress) is not bool:
        raise TypeError(
            f"tool {name!r} suppress_identical_repeats must be bool"
        )
    # What a tool declares about its relationship to files. Cross-checks read
    # these rather than a list of tool names kept elsewhere, so a tool added to
    # a pack later is covered by whatever declares itself, and a pack that has
    # no files declares nothing and is simply never subject to them.
    #
    # Validated here rather than where they are read: a misspelled key that
    # silently evaluates false would turn a cross-check off without any error,
    # which is the one direction this must not fail in.
    if "writes_file" in spec and type(spec["writes_file"]) is not bool:
        raise TypeError(f"tool {name!r} writes_file must be bool")
    opens = spec.get("opens")
    if opens is not None:
        if isinstance(opens, str) or not isinstance(opens, (tuple, list)):
            raise TypeError(
                f"tool {name!r} opens must be a sequence of extensions"
            )
        for suffix in opens:
            if not isinstance(suffix, str) or not suffix.startswith("."):
                raise ValueError(
                    f"tool {name!r} opens entry {suffix!r} must be an "
                    "extension beginning with '.'"
                )
    simulates = spec.get("simulates")
    if simulates is not None and (
        not isinstance(simulates, str) or not simulates
    ):
        raise ValueError(f"tool {name!r} simulates must be a nonempty string")


class ToolRegistry:
    """An ordered, immutable collection of tool specifications."""

    def __init__(self, specs=()):
        if isinstance(specs, ToolRegistry):
            source = ((name, specs.get(name)) for name in specs)
        else:
            source = specs.items() if hasattr(specs, "items") else specs
        copied = {}
        for name, spec in source:
            if name in copied:
                raise ValueError(f"duplicate tool name {name!r}")
            _validate_spec(name, spec)
            copied[name] = _freeze(dict(spec))
        self._specs = MappingProxyType(copied)

    def __contains__(self, name):
        return name in self._specs

    def __iter__(self):
        return iter(self._specs)

    def __len__(self):
        return len(self._specs)

    def names(self):
        return tuple(self._specs)

    def keys(self):
        return self._specs.keys()

    def get(self, name, default=None):
        if name not in self._specs:
            return default
        return _thaw(self._specs[name])

    def __getitem__(self, name):
        return _thaw(self._specs[name])

    def merged(self, other):
        if isinstance(other, ToolRegistry):
            additions = {name: other.get(name) for name in other}
        else:
            additions = dict(other)
        overlap = set(self) & set(additions)
        if overlap:
            raise ValueError(f"duplicate tool names: {', '.join(sorted(overlap))}")
        merged = {name: self.get(name) for name in self}
        merged.update(additions)
        return ToolRegistry(merged)

    def selected(self, names):
        wanted = set(names)
        unknown = wanted - set(self._specs)
        if unknown:
            raise ValueError(f"unknown selected tools: {', '.join(sorted(unknown))}")
        return ToolRegistry(
            (name, self.get(name)) for name in self if name in wanted
        )

    def docs(self, with_examples):
        lines = []
        for name, spec in self._specs.items():
            lines.append(f"- {name}: {spec['desc']}")
            for param, (type_desc, required) in spec["params"].items():
                status = "required" if required else "optional"
                lines.append(f"    {param} ({status}): {type_desc}")
            if with_examples:
                lines.append(
                    "    example: "
                    + json.dumps(_thaw(spec["example"]), ensure_ascii=False)
                )
        return "\n".join(lines)

    # ------------------------------------------------ declared capabilities --
    #
    # Derived from what each spec declares, never from a list of names kept
    # somewhere else. An allow-list of survivors silently drops every tool added
    # afterwards; a declaration means a new tool is covered the moment it says
    # what it does, and a pack with no files says nothing and is unaffected.

    def file_writing_tools(self):
        """Every tool in this registry that produces a file."""
        return frozenset(
            name for name, spec in self._specs.items()
            if spec.get("writes_file")
        )

    def simulated_tools(self):
        """Tools standing in for a surface a real account would replace."""
        return frozenset(
            name for name, spec in self._specs.items() if spec.get("simulates")
        )

    def opener_for(self, path):
        """A tool that can open this file, or None.

        First match in registry order, which is the pack's own declaration
        order, so a pack decides precedence by how it lists its tools rather
        than by anything inferred here."""
        low = str(path).lower()
        for name, spec in self._specs.items():
            for suffix in spec.get("opens") or ():
                if low.endswith(suffix.lower()):
                    return name
        return None

    def suppresses_identical_repeats(self, name):
        if name not in self._specs:
            raise KeyError(name)
        return self._specs[name].get("suppress_identical_repeats", True)

    def validate(self, name, args):
        problems = []
        if name not in self._specs:
            return [
                f"unknown tool {name!r}; valid tools: {', '.join(self._specs)}"
            ]
        if not isinstance(args, dict):
            return ["'args' must be a JSON object"]
        spec = self._specs[name]
        for param, (type_desc, required) in spec["params"].items():
            if required and (param not in args or args[param] in (None, "")):
                problems.append(
                    f"missing required parameter '{param}' ({type_desc})"
                )
        for param in args:
            if param not in spec["params"]:
                valid = ", ".join(spec["params"]) or "none"
                problems.append(
                    f"unknown parameter '{param}' (valid: {valid})"
                )
        return problems

    def execute(self, name, args, attempt):
        if name not in self._specs:
            return (
                False,
                f"ERROR: unknown tool {name!r}. Valid tools: "
                f"{', '.join(self._specs)}",
            )
        spec = self._specs[name]
        if not isinstance(args, dict):
            args = {}
        try:
            result = spec["run"](attempt, args)
            obs = _fmt(result)
            attempt.record_action(name, args, True, obs)
            ok = True
        except ToolError as error:
            attempt.record_action(name, args, False, str(error))
            ok, obs = False, f"ERROR: {error}"
        except KeyError as error:
            msg = f"missing required parameter {error.args[0]!r}"
            attempt.record_action(name, args, False, msg)
            ok, obs = False, f"ERROR: {msg}"
        except Exception as error:  # preserve current keep-the-episode-alive behavior
            attempt.record_action(name, args, False, repr(error))
            ok, obs = False, f"ERROR: {type(error).__name__}: {error}"
        if attempt.hooks.on_tool:
            try:
                attempt.hooks.on_tool(
                    name, copy.deepcopy(args), ok, str(obs)
                )
            except Exception:
                # Observation hooks are deliberately best-effort and cannot
                # change execution semantics or action evidence.
                pass
        return ok, obs

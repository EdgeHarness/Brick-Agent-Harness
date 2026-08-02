"""Conservative tool-call parsing and argument repair (S1R).

Primary conditions read the native tool-call object and never parse prose. This
module exists for the legacy JSON-extraction path and for the descriptive
`raw_json` lower bound, where a model emits an object as text. Both defects it
replaces were silent, which is what made them dangerous.

**Brace matching was not string-aware.** The released extractor scanned for a
balanced ``{...}`` by counting braces without tracking string literals, so a
closing brace inside a JSON string -- ``{"note": "a} b", "tool": "x"}`` --
terminated the object early and produced either a parse failure or, worse, a
truncated object that still parsed.

**Argument repair inferred names.** It used
``difflib.get_close_matches(cutoff=0.5)`` and then fell back to substring
matching, so ``{"id": ...}`` could be renamed to ``lead_id`` on a delete tool.
That is inference on a mutation argument: the model said one thing and the
runtime executed another against authoritative state. It then silently dropped
every unrecognised parameter, so a model that sent ``confirm: false`` had its
safety intent discarded with no record.

The replacement is deliberately unhelpful:

* repair is limited to an explicit, versioned alias table -- never similarity,
  never substring, never inference;
* an argument of a *mutating* tool is only ever renamed by an alias declared for
  that specific tool, never by a global alias, because a plausible-looking
  rename that reaches authoritative state is the failure mode with real
  consequences;
* unknown parameters are reported, never dropped. Dropping one converts an
  explicit model instruction into silence.

Refusing to repair is the safe outcome. A rejected call costs one turn of the
opportunity budget and produces a clear message; a wrongly repaired call
produces a wrong effect that the grader may score as a real model failure.
"""

import json
import re
from collections.abc import Mapping


PARSER_VERSION = "brick.toolcall-parser/1"
ALIAS_TABLE_VERSION = "brick.alias-table/1"

_FENCE = re.compile(r"```(?:[A-Za-z0-9_-]+)?\s*(.*?)```", re.S)


class AliasTableError(ValueError):
    """The alias table is itself malformed. A developer defect."""


def strip_fences(text):
    """Return the first fenced block's contents, else the whole text."""
    match = _FENCE.search(text)
    return match.group(1).strip() if match else text.strip()


def find_json_object(text):
    """Return the first balanced top-level ``{...}`` span, string-aware.

    Tracks string literals and backslash escapes, so a brace inside a string
    value cannot terminate the object early. Returns ``(span, error)``.
    """
    if not isinstance(text, str):
        return None, "response was not text"
    start = text.find("{")
    if start == -1:
        return None, "no JSON object found in response"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1], None
    if in_string:
        return None, "unterminated string in response"
    return None, "unbalanced braces in response"


def parse_strict(text):
    """Fence-strip and decode. No extraction, no repair."""
    try:
        obj = json.loads(strip_fences(text))
    except (ValueError, TypeError) as exc:
        return None, "response was not valid JSON ({})".format(exc)
    if not isinstance(obj, dict):
        return None, "response was not a JSON object"
    return obj, None


def parse_extracted(text):
    """Strict decode, else one string-aware extraction of the first object.

    Deliberately does not repair trailing commas or any other malformed JSON.
    The released parser did, which taught the model that invalid output is
    acceptable and made the transcript disagree with what was executed.
    """
    obj, _ = parse_strict(text)
    if obj is not None:
        return obj, None
    span, error = find_json_object(strip_fences(text))
    if span is None:
        return None, error
    try:
        obj = json.loads(span)
    except (ValueError, TypeError) as exc:
        return None, "found a {{...}} block but it is not valid JSON ({})".format(
            exc
        )
    if not isinstance(obj, dict):
        return None, "extracted JSON was not an object"
    return obj, None


def validate_alias_table(table):
    """Validate an alias table. Raises AliasTableError on any defect.

    Shape::

        {"__global__": {alias: canonical},
         "tool_name":  {alias: canonical}}
    """
    if not isinstance(table, Mapping):
        raise AliasTableError("alias table must be a mapping")
    for scope, aliases in table.items():
        if not isinstance(scope, str) or not scope:
            raise AliasTableError("alias scope must be a nonempty string")
        if not isinstance(aliases, Mapping):
            raise AliasTableError(
                "alias scope {!r} must map to a mapping".format(scope)
            )
        for alias, canonical in aliases.items():
            if not isinstance(alias, str) or not alias:
                raise AliasTableError(
                    "alias in scope {!r} must be a nonempty string".format(
                        scope
                    )
                )
            if not isinstance(canonical, str) or not canonical:
                raise AliasTableError(
                    "alias {!r} must map to a nonempty canonical name".format(
                        alias
                    )
                )
            if alias == canonical:
                raise AliasTableError(
                    "alias {!r} in scope {!r} is its own target".format(
                        alias, scope
                    )
                )
            if canonical in aliases:
                raise AliasTableError(
                    "alias target {!r} is itself an alias in scope {!r}; "
                    "chained aliases are not resolved".format(
                        canonical, scope
                    )
                )
    return table


GLOBAL_SCOPE = "__global__"


def apply_aliases(tool, args, table, known, mutating=False):
    """Rename known aliases only. Never infers, never drops.

    Returns ``(repaired, notes, problems)``. ``notes`` records each applied
    rename for the transcript; ``problems`` reports arguments that remain
    unrecognised. An unknown argument is a problem, never a silent deletion.

    A mutating tool accepts only aliases declared for that specific tool. A
    global alias is a convenience for read-only shapes; letting one rewrite an
    argument that reaches authoritative state is precisely the inference this
    module removes.
    """
    if not isinstance(args, Mapping):
        return args, [], ["'args' must be a JSON object"]
    validate_alias_table(table)
    known = set(known)
    scoped = dict(table.get(tool, {}))
    if not mutating:
        for alias, canonical in table.get(GLOBAL_SCOPE, {}).items():
            scoped.setdefault(alias, canonical)

    repaired = {}
    notes = []
    problems = []
    for name in sorted(args):
        value = args[name]
        if name in known:
            repaired[name] = value
            continue
        canonical = scoped.get(name)
        if canonical is None:
            if mutating and name in table.get(GLOBAL_SCOPE, {}):
                problems.append(
                    "unknown parameter {!r}: a global alias exists but is not "
                    "applied to the mutating tool {!r}; pass {!r} "
                    "explicitly".format(
                        name, tool, table[GLOBAL_SCOPE][name]
                    )
                )
            else:
                valid = ", ".join(sorted(known)) or "none"
                problems.append(
                    "unknown parameter {!r} (valid: {})".format(name, valid)
                )
            continue
        if canonical not in known:
            problems.append(
                "alias {!r} maps to {!r}, which tool {!r} does not "
                "accept".format(name, canonical, tool)
            )
            continue
        if canonical in args:
            problems.append(
                "alias {!r} conflicts with {!r}, which was also "
                "supplied".format(name, canonical)
            )
            continue
        if canonical in repaired:
            problems.append(
                "two aliases resolve to {!r}".format(canonical)
            )
            continue
        repaired[canonical] = value
        notes.append("renamed {!r} -> {!r}".format(name, canonical))
    return repaired, notes, problems

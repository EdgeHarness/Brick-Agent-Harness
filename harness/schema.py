"""Executable tool-argument schemas for the repaired runtime (S1R).

The released registry described parameters as prose -- ``{"name": ("a date
string", True)}`` -- and validated only that required keys were present. A model
could pass ``{"count": "seven"}``, ``{"count": true}``, or a nested object where
a string belonged and the call reached the executor unchallenged. Type errors
then surfaced as executor exceptions, which are recorded on a different status
axis than model errors, so a malformed argument could be misattributed as an
instrument fault.

This module makes the schema the single executable source of truth. One
``ToolSchema`` yields, by derivation rather than by duplication:

* validation of an actual argument mapping;
* the Ollama native function-call schema for the primary conditions; and
* the human-readable prompt documentation.

Deriving all three from one object is the point. Prompt text that disagrees with
the validator teaches the model a contract the runtime will reject, and a native
schema that disagrees with the validator lets the server accept what Brick
refuses.

Validation is deliberately strict and closed:

* unknown properties are rejected -- ``additionalProperties`` defaults to false;
* ``bool`` never satisfies ``integer`` or ``number`` even though Python's
  ``bool`` subclasses ``int``;
* ``int`` satisfies ``number``, but a float never satisfies ``integer``;
* every constraint failure is reported, not just the first, so one exchange
  gives the model the complete contract;
* problems are emitted in a deterministic order, because they become part of
  immutable attempt evidence and must be byte-reproducible.

The vocabulary is a deliberate subset of JSON Schema. Brick needs exactly the
constructs the frozen tool contracts use; accepting arbitrary JSON Schema would
mean shipping a general validator whose behaviour we cannot enumerate in tests.
"""

import datetime
import math
import re
from collections.abc import Mapping, Sequence


SCHEMA_VERSION = "brick.toolspec/1"

_TYPES = ("object", "array", "string", "integer", "number", "boolean")
_FORMATS = ("date", "time", "date-time", "email", "identifier")
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
# Deliberately conservative: a deterministic shape check, not RFC 5322. Brick
# only ever sends fictional addresses, and a permissive regex here would let a
# malformed address reach a fake provider and be recorded as a real effect.
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

_COMMON_KEYS = frozenset({"type", "description", "enum"})
_KEYS_BY_TYPE = {
    "object": frozenset({"properties", "required", "additionalProperties"}),
    "array": frozenset({"items", "minItems", "maxItems", "uniqueItems"}),
    "string": frozenset({"minLength", "maxLength", "pattern", "format"}),
    "integer": frozenset(
        {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
         "multipleOf"}
    ),
    "number": frozenset(
        {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
         "multipleOf"}
    ),
    "boolean": frozenset(),
}


class SchemaError(ValueError):
    """A schema is itself malformed. This is a developer defect, not a model
    error, and must fail loudly at construction rather than at call time."""


def _is_int(value):
    # bool is a subclass of int in Python. Accepting True as 1 would let a
    # model satisfy an integer parameter with a boolean, which is exactly the
    # class of silent coercion S1R exists to remove.
    return type(value) is int


def _is_number(value):
    return type(value) in (int, float)


def _require(condition, message):
    if not condition:
        raise SchemaError(message)


def validate_schema(schema, path="<root>"):
    """Validate a schema document itself. Raises SchemaError on any defect."""
    _require(isinstance(schema, Mapping), f"{path}: schema must be a mapping")
    kind = schema.get("type")
    _require(
        kind in _TYPES,
        f"{path}: type must be one of {', '.join(_TYPES)}, got {kind!r}",
    )
    allowed = _COMMON_KEYS | _KEYS_BY_TYPE[kind]
    unknown = sorted(set(schema) - allowed)
    _require(
        not unknown,
        f"{path}: unsupported schema keys for type {kind!r}: "
        + ", ".join(unknown),
    )
    if "description" in schema:
        _require(
            isinstance(schema["description"], str) and schema["description"],
            f"{path}: description must be a nonempty string",
        )
    if "enum" in schema:
        values = schema["enum"]
        _require(
            isinstance(values, Sequence)
            and not isinstance(values, (str, bytes))
            and len(values) > 0,
            f"{path}: enum must be a nonempty sequence",
        )
        seen = []
        for value in values:
            _require(
                value not in seen, f"{path}: enum contains a duplicate value"
            )
            seen.append(value)

    if kind == "object":
        properties = schema.get("properties", {})
        _require(
            isinstance(properties, Mapping),
            f"{path}: properties must be a mapping",
        )
        for name, sub in properties.items():
            _require(
                isinstance(name, str) and name,
                f"{path}: property names must be nonempty strings",
            )
            validate_schema(sub, f"{path}.{name}")
        required = schema.get("required", [])
        _require(
            isinstance(required, Sequence)
            and not isinstance(required, (str, bytes)),
            f"{path}: required must be a sequence",
        )
        for name in required:
            _require(
                name in properties,
                f"{path}: required names unknown property {name!r}",
            )
        _require(
            len(set(required)) == len(list(required)),
            f"{path}: required contains a duplicate",
        )
        if "additionalProperties" in schema:
            _require(
                type(schema["additionalProperties"]) is bool,
                f"{path}: additionalProperties must be a bool",
            )
    elif kind == "array":
        _require("items" in schema, f"{path}: array schema requires items")
        validate_schema(schema["items"], f"{path}[]")
        for key in ("minItems", "maxItems"):
            if key in schema:
                _require(
                    _is_int(schema[key]) and schema[key] >= 0,
                    f"{path}: {key} must be a nonnegative integer",
                )
        if "minItems" in schema and "maxItems" in schema:
            _require(
                schema["minItems"] <= schema["maxItems"],
                f"{path}: minItems exceeds maxItems",
            )
        if "uniqueItems" in schema:
            _require(
                type(schema["uniqueItems"]) is bool,
                f"{path}: uniqueItems must be a bool",
            )
    elif kind == "string":
        for key in ("minLength", "maxLength"):
            if key in schema:
                _require(
                    _is_int(schema[key]) and schema[key] >= 0,
                    f"{path}: {key} must be a nonnegative integer",
                )
        if "minLength" in schema and "maxLength" in schema:
            _require(
                schema["minLength"] <= schema["maxLength"],
                f"{path}: minLength exceeds maxLength",
            )
        if "pattern" in schema:
            _require(
                isinstance(schema["pattern"], str),
                f"{path}: pattern must be a string",
            )
            try:
                re.compile(schema["pattern"])
            except re.error as exc:
                raise SchemaError(
                    f"{path}: pattern is not a valid regex: {exc}"
                ) from exc
        if "format" in schema:
            _require(
                schema["format"] in _FORMATS,
                f"{path}: format must be one of {', '.join(_FORMATS)}",
            )
    elif kind in ("integer", "number"):
        checker = _is_int if kind == "integer" else _is_number
        for key in (
            "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        ):
            if key in schema:
                _require(
                    checker(schema[key]) and _finite(schema[key]),
                    f"{path}: {key} must be a finite {kind}",
                )
        if "multipleOf" in schema:
            _require(
                checker(schema["multipleOf"])
                and _finite(schema["multipleOf"])
                and schema["multipleOf"] > 0,
                f"{path}: multipleOf must be a positive finite {kind}",
            )
        low = schema.get("minimum", schema.get("exclusiveMinimum"))
        high = schema.get("maximum", schema.get("exclusiveMaximum"))
        if low is not None and high is not None:
            _require(low <= high, f"{path}: minimum exceeds maximum")
    return schema


def _finite(value):
    return not isinstance(value, float) or math.isfinite(value)


def _type_name(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, Sequence):
        return "array"
    return type(value).__name__


def _matches_type(kind, value):
    if kind == "object":
        return isinstance(value, Mapping)
    if kind == "array":
        return isinstance(value, Sequence) and not isinstance(
            value, (str, bytes)
        )
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return _is_int(value)
    if kind == "number":
        return _is_number(value) and _finite(value)
    return False


def _check_format(fmt, value):
    if fmt == "date":
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return "must be an ISO-8601 date (YYYY-MM-DD)"
    elif fmt == "time":
        try:
            datetime.time.fromisoformat(value)
        except ValueError:
            return "must be an ISO-8601 time (HH:MM or HH:MM:SS)"
    elif fmt == "date-time":
        try:
            datetime.datetime.fromisoformat(value)
        except ValueError:
            return "must be an ISO-8601 date-time"
    elif fmt == "email":
        if not _EMAIL.fullmatch(value):
            return "must be an email address"
    elif fmt == "identifier":
        if not _IDENTIFIER.fullmatch(value):
            return "must be a short identifier ([A-Za-z][A-Za-z0-9_-]{0,63})"
    return None


def validate_value(schema, value, path="value"):
    """Return a deterministic list of problems. Empty means the value conforms.

    Every failure is reported rather than only the first, so a single feedback
    exchange conveys the whole contract instead of forcing the model to
    rediscover it one rejection at a time.
    """
    problems = []
    kind = schema["type"]
    if not _matches_type(kind, value):
        if kind == "number" and _is_number(value) and not _finite(value):
            problems.append(f"{path}: must be a finite number")
        else:
            problems.append(
                f"{path}: expected {kind}, got {_type_name(value)}"
            )
        return problems

    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(repr(v) for v in schema["enum"])
        problems.append(f"{path}: must be one of {allowed}")

    if kind == "object":
        properties = schema.get("properties", {})
        required = list(schema.get("required", []))
        allow_extra = schema.get("additionalProperties", False)
        for name in required:
            if name not in value:
                problems.append(f"{path}.{name}: required property is missing")
        if not allow_extra:
            for name in sorted(k for k in value if k not in properties):
                known = ", ".join(sorted(properties)) or "none"
                problems.append(
                    f"{path}.{name}: unknown property (known: {known})"
                )
        for name in sorted(properties):
            if name in value:
                problems.extend(
                    validate_value(
                        properties[name], value[name], f"{path}.{name}"
                    )
                )
    elif kind == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(
                f"{path}: must have at least {schema['minItems']} items"
            )
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(
                f"{path}: must have at most {schema['maxItems']} items"
            )
        if schema.get("uniqueItems"):
            seen = []
            for item in value:
                if item in seen:
                    problems.append(f"{path}: items must be unique")
                    break
                seen.append(item)
        for index, item in enumerate(value):
            problems.extend(
                validate_value(schema["items"], item, f"{path}[{index}]")
            )
    elif kind == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append(
                f"{path}: must be at least {schema['minLength']} characters"
            )
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(
                f"{path}: must be at most {schema['maxLength']} characters"
            )
        if "pattern" in schema and not re.compile(
            schema["pattern"]
        ).fullmatch(value):
            problems.append(f"{path}: must match {schema['pattern']}")
        if "format" in schema:
            failure = _check_format(schema["format"], value)
            if failure:
                problems.append(f"{path}: {failure}")
    elif kind in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: must be <= {schema['maximum']}")
        if (
            "exclusiveMinimum" in schema
            and value <= schema["exclusiveMinimum"]
        ):
            problems.append(f"{path}: must be > {schema['exclusiveMinimum']}")
        if (
            "exclusiveMaximum" in schema
            and value >= schema["exclusiveMaximum"]
        ):
            problems.append(f"{path}: must be < {schema['exclusiveMaximum']}")
        if "multipleOf" in schema:
            step = schema["multipleOf"]
            remainder = (
                value % step
                if _is_int(value) and _is_int(step)
                else math.remainder(value, step)
            )
            if abs(remainder) > 1e-9:
                problems.append(f"{path}: must be a multiple of {step}")
    return problems


def to_ollama_function(name, description, schema):
    """Derive the Ollama native function-call schema.

    Derived rather than hand-written so the server can never be told a contract
    the validator does not enforce.
    """
    validate_schema(schema)
    if schema["type"] != "object":
        raise SchemaError(
            "a tool's argument schema must be an object at the root"
        )
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": _to_json_schema(schema),
        },
    }


def _to_json_schema(schema):
    out = {"type": schema["type"]}
    for key in ("description", "enum"):
        if key in schema:
            out[key] = (
                list(schema[key]) if key == "enum" else schema[key]
            )
    kind = schema["type"]
    if kind == "object":
        out["properties"] = {
            name: _to_json_schema(sub)
            for name, sub in schema.get("properties", {}).items()
        }
        out["required"] = list(schema.get("required", []))
        out["additionalProperties"] = schema.get(
            "additionalProperties", False
        )
    elif kind == "array":
        out["items"] = _to_json_schema(schema["items"])
        for key in ("minItems", "maxItems", "uniqueItems"):
            if key in schema:
                out[key] = schema[key]
    else:
        for key in sorted(_KEYS_BY_TYPE[kind]):
            if key in schema:
                out[key] = schema[key]
    return out


def to_prompt_doc(name, description, schema, indent="    "):
    """Derive human-readable documentation from the same schema object."""
    validate_schema(schema)
    lines = [f"- {name}: {description}"]
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    for prop in sorted(properties):
        status = "required" if prop in required else "optional"
        lines.append(
            f"{indent}{prop} ({status}): {_describe(properties[prop])}"
        )
    return "\n".join(lines)


def _describe(schema):
    kind = schema["type"]
    parts = [kind]
    if kind == "array":
        parts = [f"array of {_describe(schema['items'])}"]
    if "format" in schema:
        parts.append(f"format {schema['format']}")
    if "enum" in schema:
        parts.append("one of " + ", ".join(repr(v) for v in schema["enum"]))
    for key in ("minimum", "maximum", "minLength", "maxLength",
                "minItems", "maxItems", "pattern"):
        if key in schema:
            parts.append(f"{key} {schema[key]}")
    text = ", ".join(parts)
    if "description" in schema:
        text = f"{schema['description']} ({text})"
    return text

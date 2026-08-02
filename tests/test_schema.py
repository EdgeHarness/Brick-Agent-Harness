"""S1R executable tool-argument schemas.

The released registry validated only that required keys were present, so
``{"count": "seven"}`` and ``{"count": true}`` both reached the executor. A type
error then surfaced as an executor exception, which is recorded on a different
status axis than a model error -- so a malformed argument could be
misattributed as an instrument fault. These tests pin the closed behaviour that
replaces it.
"""

import math

import pytest

from harness import schema as s


COUNT = {
    "type": "object",
    "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 10}},
    "required": ["count"],
}


# --- the silent coercions S1R exists to remove -----------------------------


def test_conforming_value_has_no_problems():
    assert s.validate_value(COUNT, {"count": 7}) == []


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, "expected integer, got boolean"),
        ("seven", "expected integer, got string"),
        (7.0, "expected integer, got number"),
        (None, "expected integer, got null"),
        ([7], "expected integer, got array"),
        ({"n": 7}, "expected integer, got object"),
    ],
)
def test_wrong_types_are_rejected_not_coerced(value, expected):
    problems = s.validate_value(COUNT, {"count": value})
    assert problems == ["value.count: " + expected]


def test_bool_never_satisfies_integer_or_number():
    """Python's bool subclasses int; JSON's does not. Accepting True as 1 is
    exactly the silent coercion this stage removes."""
    assert s.validate_value({"type": "integer"}, True)
    assert s.validate_value({"type": "integer"}, False)
    assert s.validate_value({"type": "number"}, True)


def test_int_satisfies_number_but_float_never_satisfies_integer():
    assert s.validate_value({"type": "number"}, 3) == []
    assert s.validate_value({"type": "integer"}, 3.0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(value):
    assert s.validate_value({"type": "number"}, value) == [
        "value: must be a finite number"
    ]


def test_unknown_properties_are_rejected_by_default():
    """additionalProperties defaults to false: a tool must never receive an
    argument its schema does not declare."""
    assert s.validate_value(COUNT, {"count": 1, "extra": 2}) == [
        "value.extra: unknown property (known: count)"
    ]


def test_additional_properties_can_be_opted_into_explicitly():
    schema = dict(COUNT, additionalProperties=True)
    assert s.validate_value(schema, {"count": 1, "extra": 2}) == []


def test_missing_required_property_is_reported():
    assert s.validate_value(COUNT, {}) == [
        "value.count: required property is missing"
    ]


# --- constraints ------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [(0, "must be >= 1"), (11, "must be <= 10")],
)
def test_numeric_bounds(value, expected):
    assert s.validate_value(COUNT, {"count": value}) == [
        "value.count: " + expected
    ]


def test_exclusive_bounds_and_multiple_of():
    schema = {"type": "integer", "exclusiveMinimum": 0, "multipleOf": 5}
    assert s.validate_value(schema, 5) == []
    assert s.validate_value(schema, 0) == ["value: must be > 0"]
    assert s.validate_value(schema, 7) == ["value: must be a multiple of 5"]


def test_string_length_pattern_and_enum():
    schema = {"type": "string", "minLength": 2, "maxLength": 4}
    assert s.validate_value(schema, "ab") == []
    assert s.validate_value(schema, "a") == [
        "value: must be at least 2 characters"
    ]
    assert s.validate_value(schema, "abcde") == [
        "value: must be at most 4 characters"
    ]
    pattern = {"type": "string", "pattern": r"[a-z]+"}
    assert s.validate_value(pattern, "abc") == []
    assert s.validate_value(pattern, "abc1") == ["value: must match [a-z]+"]
    enum = {"type": "string", "enum": ["low", "high"]}
    assert s.validate_value(enum, "low") == []
    assert s.validate_value(enum, "mid") == [
        "value: must be one of 'low', 'high'"
    ]


def test_pattern_is_anchored_so_a_prefix_match_is_not_accepted():
    """A substring match would let 'abc!!!' satisfy a strict identifier rule."""
    assert s.validate_value({"type": "string", "pattern": r"[a-z]+"}, "abc!!!")


@pytest.mark.parametrize(
    "fmt,good,bad",
    [
        ("date", "2026-08-02", "2026-13-02"),
        ("time", "14:30", "25:00"),
        ("date-time", "2026-08-02T14:30:00", "2026-08-02 25:00"),
        ("email", "a.b@ex.example", "not-an-email"),
        ("identifier", "lead_42", "9bad"),
    ],
)
def test_formats(fmt, good, bad):
    schema = {"type": "string", "format": fmt}
    assert s.validate_value(schema, good) == []
    assert s.validate_value(schema, bad)


def test_array_items_bounds_and_uniqueness():
    schema = {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 1,
        "maxItems": 2,
        "uniqueItems": True,
    }
    assert s.validate_value(schema, [1, 2]) == []
    assert s.validate_value(schema, []) == [
        "value: must have at least 1 items"
    ]
    assert "value: items must be unique" in s.validate_value(schema, [1, 1])
    assert s.validate_value(schema, [1, "x"]) == [
        "value[1]: expected integer, got string"
    ]


def test_a_string_is_not_an_array():
    """Sequence-ness must not make 'abc' a three-item array."""
    assert s.validate_value(
        {"type": "array", "items": {"type": "string"}}, "abc"
    ) == ["value: expected array, got string"]


# --- reporting contract -----------------------------------------------------


def test_every_problem_is_reported_not_only_the_first():
    """One exchange must convey the whole contract, not force the model to
    rediscover it one rejection at a time."""
    schema = {
        "type": "object",
        "properties": {
            "a": {"type": "integer", "minimum": 0},
            "b": {"type": "string", "minLength": 3},
        },
        "required": ["a", "b"],
    }
    problems = s.validate_value(schema, {"a": -1, "b": "x", "c": 1})
    assert len(problems) == 3


def test_problem_order_is_deterministic():
    """Problems become immutable attempt evidence and must be reproducible."""
    schema = {
        "type": "object",
        "properties": {name: {"type": "integer"} for name in "dcba"},
    }
    value = {name: "x" for name in "abcd"}
    first = s.validate_value(schema, value)
    assert first == s.validate_value(schema, value)
    assert first == sorted(first)


def test_nested_objects_and_arrays_report_full_paths():
    schema = {
        "type": "object",
        "properties": {
            "lead": {
                "type": "object",
                "properties": {"score": {"type": "integer", "maximum": 100}},
                "required": ["score"],
            }
        },
        "required": ["lead"],
    }
    assert s.validate_value(schema, {"lead": {"score": 150}}) == [
        "value.lead.score: must be <= 100"
    ]


# --- schema self-validation -------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "str"},
        {"type": "object", "properties": {"a": {"type": "integer"}},
         "required": ["b"]},
        {"type": "array"},
        {"type": "string", "pattern": "["},
        {"type": "integer", "minimum": 10, "maximum": 1},
        {"type": "string", "format": "uuid"},
        {"type": "integer", "minLength": 1},
        {"type": "string", "minLength": -1},
        {"type": "object", "additionalProperties": "yes"},
        {"type": "array", "items": {"type": "integer"}, "minItems": 3,
         "maxItems": 1},
        {"type": "integer", "multipleOf": 0},
        {"type": "string", "enum": []},
        {"type": "string", "enum": ["a", "a"]},
    ],
)
def test_malformed_schemas_fail_loudly_at_definition(bad):
    """A schema defect is a developer error and must not wait until call time."""
    with pytest.raises(s.SchemaError):
        s.validate_schema(bad)


def test_non_finite_schema_bounds_are_rejected():
    with pytest.raises(s.SchemaError):
        s.validate_schema({"type": "number", "minimum": math.inf})


# --- derivation: one schema, three artefacts --------------------------------


DERIVED = {
    "type": "object",
    "properties": {
        "lead_id": {"type": "string", "format": "identifier"},
        "priority": {"type": "string", "enum": ["low", "high"]},
    },
    "required": ["lead_id"],
}


def test_native_schema_is_derived_and_closed():
    fn = s.to_ollama_function("propose", "Draft one.", DERIVED)
    params = fn["function"]["parameters"]
    assert fn["type"] == "function"
    assert fn["function"]["name"] == "propose"
    assert params["required"] == ["lead_id"]
    assert params["additionalProperties"] is False


def test_native_schema_and_validator_agree_on_required_and_extras():
    """Anti-drift: a native schema that disagrees with the validator lets the
    server accept what Brick then refuses."""
    params = s.to_ollama_function("propose", "d", DERIVED)["function"][
        "parameters"
    ]
    for name in params["required"]:
        assert s.validate_value(DERIVED, {}), "validator must require it too"
    assert params["additionalProperties"] is False
    assert s.validate_value(DERIVED, {"lead_id": "a", "zzz": 1})


def test_prompt_doc_is_derived_from_the_same_schema():
    doc = s.to_prompt_doc("propose", "Draft one.", DERIVED)
    assert doc.startswith("- propose: Draft one.")
    assert "lead_id (required)" in doc
    assert "priority (optional)" in doc
    assert "one of 'low', 'high'" in doc


def test_a_tool_schema_must_be_an_object_at_the_root():
    with pytest.raises(s.SchemaError):
        s.to_ollama_function("x", "d", {"type": "string"})


def test_derivation_validates_the_schema_first():
    with pytest.raises(s.SchemaError):
        s.to_ollama_function("x", "d", {"type": "object", "required": ["a"]})


def test_schema_version_is_pinned():
    assert s.SCHEMA_VERSION == "brick.toolspec/1"

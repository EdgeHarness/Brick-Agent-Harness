"""S1R conservative tool-call parsing and argument repair.

Two released defects, both silent:

* the brace matcher was not string-aware, so a closing brace inside a JSON
  string terminated the object early -- rejecting valid tool calls whose values
  contain braces, such as an email body reading ``Hi {name}, bye}``; and
* argument repair used ``difflib`` similarity and then substring matching, so
  ``{"id": ...}`` could be renamed to ``lead_id`` on a delete tool, and every
  unrecognised parameter was silently dropped.

Refusing to repair is the safe outcome. A rejected call costs one turn of the
opportunity budget; a wrongly repaired call produces a wrong effect against
authoritative state that the grader may score as a genuine model failure.
"""

import pytest

from harness import parsing as p


# --- string-aware extraction ------------------------------------------------


def test_brace_inside_a_string_does_not_terminate_the_object():
    text = 'prose before {"tool":"x","args":{"note":"a} b"}} and after'
    obj, error = p.parse_extracted(text)
    assert error is None
    assert obj == {"tool": "x", "args": {"note": "a} b"}}


def test_a_template_like_body_parses():
    """Realistic: a follow-up draft containing braces."""
    text = 'Sure!\n{"tool":"send","args":{"body":"Hi {name}, bye}"}}'
    obj, error = p.parse_extracted(text)
    assert error is None
    assert obj["args"]["body"] == "Hi {name}, bye}"


def test_escaped_quote_before_a_brace_is_handled():
    obj, error = p.parse_extracted(r'{"a":"\"} "}')
    assert error is None
    assert obj == {"a": '"} '}


def test_unterminated_string_is_reported_not_mis_parsed():
    assert p.find_json_object('{"a": "no end') == (
        None,
        "unterminated string in response",
    )


def test_unbalanced_braces_are_reported():
    assert p.find_json_object('{"a": 1') == (
        None,
        "unbalanced braces in response",
    )


def test_absent_object_is_reported():
    assert p.find_json_object("no object here") == (
        None,
        "no JSON object found in response",
    )


def test_fenced_json_is_extracted():
    obj, error = p.parse_strict('```json\n{"a": 1}\n```')
    assert error is None and obj == {"a": 1}


def test_strict_rejects_a_non_object():
    assert p.parse_strict("[1, 2]")[0] is None
    assert p.parse_strict('"text"')[0] is None


def test_extraction_does_not_repair_malformed_json():
    """The released parser silently fixed trailing commas, teaching the model
    that invalid output is acceptable and making the transcript disagree with
    what was executed."""
    obj, error = p.parse_extracted('{"a": 1,}')
    assert obj is None
    assert "not valid JSON" in error


# --- alias table validation -------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "not a mapping",
        {"": {"a": "b"}},
        {"tool": "not a mapping"},
        {"tool": {"": "b"}},
        {"tool": {"a": ""}},
        {"tool": {"a": "a"}},
        {"tool": {"a": "b", "b": "c"}},
    ],
)
def test_malformed_alias_tables_fail_loudly(bad):
    with pytest.raises(p.AliasTableError):
        p.validate_alias_table(bad)


def test_chained_aliases_are_refused():
    """Resolving a->b->c would make the applied rename depend on iteration
    order, which is inference by another name."""
    with pytest.raises(p.AliasTableError):
        p.validate_alias_table({"t": {"a": "b", "b": "c"}})


# --- repair never infers ----------------------------------------------------


def test_known_arguments_pass_through_untouched():
    args = {"lead_id": "L-1"}
    out, notes, problems = p.apply_aliases("get", args, {}, {"lead_id"})
    assert out == args and notes == [] and problems == []


def test_a_declared_alias_is_applied_on_a_read_only_tool():
    table = {p.GLOBAL_SCOPE: {"id": "lead_id"}}
    out, notes, problems = p.apply_aliases(
        "get_lead", {"id": "L-1"}, table, {"lead_id"}, mutating=False
    )
    assert out == {"lead_id": "L-1"}
    assert notes == ["renamed 'id' -> 'lead_id'"]
    assert problems == []


def test_a_global_alias_never_rewrites_a_mutating_argument():
    """The released repair renamed 'id' to 'lead_id' on a delete tool by
    substring match. A plausible rename that reaches authoritative state is the
    failure mode with real consequences."""
    table = {p.GLOBAL_SCOPE: {"id": "lead_id"}}
    out, notes, problems = p.apply_aliases(
        "delete_lead", {"id": "L-1"}, table, {"lead_id"}, mutating=True
    )
    assert out == {}
    assert notes == []
    assert len(problems) == 1
    assert "not applied to the mutating tool" in problems[0]


def test_a_tool_scoped_alias_is_applied_even_when_mutating():
    """Explicit per-tool declaration is a decision, not an inference."""
    table = {"delete_lead": {"id": "lead_id"}}
    out, notes, problems = p.apply_aliases(
        "delete_lead", {"id": "L-1"}, table, {"lead_id"}, mutating=True
    )
    assert out == {"lead_id": "L-1"}
    assert problems == []


@pytest.mark.parametrize("supplied", ["leadid", "lead", "leadId", "l_id", "ID"])
def test_near_miss_names_are_never_guessed(supplied):
    """difflib similarity and substring matching are both gone."""
    out, notes, problems = p.apply_aliases(
        "delete_lead", {supplied: "L-1"}, {}, {"lead_id"}, mutating=True
    )
    assert out == {}
    assert notes == []
    assert problems and "unknown parameter" in problems[0]


def test_unknown_parameters_are_reported_never_dropped():
    """The released repair deleted 'confirm' silently, discarding an explicit
    model instruction with no record."""
    out, notes, problems = p.apply_aliases(
        "send", {"lead_id": "L", "confirm": False}, {}, {"lead_id"},
        mutating=True,
    )
    assert out == {"lead_id": "L"}
    assert problems == ["unknown parameter 'confirm' (valid: lead_id)"]


def test_alias_conflicting_with_a_supplied_canonical_is_refused():
    table = {"t": {"id": "lead_id"}}
    out, notes, problems = p.apply_aliases(
        "t", {"id": "A", "lead_id": "B"}, table, {"lead_id"}
    )
    assert out == {"lead_id": "B"}
    assert any("conflicts with" in problem for problem in problems)


def test_two_aliases_resolving_to_one_name_are_refused():
    table = {"t": {"id": "lead_id", "ref": "lead_id"}}
    out, notes, problems = p.apply_aliases(
        "t", {"id": "A", "ref": "B"}, table, {"lead_id"}
    )
    assert any("two aliases resolve to" in problem for problem in problems)


def test_an_alias_pointing_at_an_unaccepted_name_is_refused():
    table = {"t": {"id": "nope"}}
    out, notes, problems = p.apply_aliases("t", {"id": "A"}, table, {"lead_id"})
    assert out == {}
    assert any("does not accept" in problem for problem in problems)


def test_non_object_args_are_rejected():
    out, notes, problems = p.apply_aliases("t", ["a"], {}, {"lead_id"})
    assert problems == ["'args' must be a JSON object"]


def test_output_is_deterministic():
    table = {"t": {"id": "lead_id"}}
    args = {"zeta": 1, "id": "A", "alpha": 2}
    first = p.apply_aliases("t", args, table, {"lead_id"})
    assert first == p.apply_aliases("t", args, table, {"lead_id"})
    assert first[2] == sorted(first[2])


def test_versions_are_pinned():
    assert p.PARSER_VERSION == "brick.toolcall-parser/1"
    assert p.ALIAS_TABLE_VERSION == "brick.alias-table/1"

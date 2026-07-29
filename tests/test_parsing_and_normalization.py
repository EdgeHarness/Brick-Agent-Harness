import datetime

import pytest

from harness import agent
from harness.domain import load_domain
from domains.office_demo.normalize import normalize_date, normalize_time


def test_strict_parser_accepts_an_object_and_strips_a_code_fence():
    obj, error = agent.parse_strict(
        '```json\n{"tool": "list_events", "args": {}}\n```'
    )

    assert error is None
    assert obj == {"tool": "list_events", "args": {}}


@pytest.mark.parametrize("text", ["[]", '"text"', "not json"])
def test_strict_parser_rejects_non_object_output(text):
    obj, error = agent.parse_strict(text)

    assert obj is None
    assert error


def test_lenient_parser_extracts_prose_wrapped_json_and_removes_trailing_commas():
    obj, error = agent.parse_lenient(
        'prefix {"tool": "think", "args": {"thought": "check"},} suffix'
    )

    assert error is None
    assert obj == {"tool": "think", "args": {"thought": "check"}}


@pytest.mark.characterization
def test_lenient_parser_currently_mishandles_a_closing_brace_inside_a_string():
    # Characterization of the current brace counter: it does not track JSON
    # string state and stops at the brace inside "thought".
    obj, error = agent.parse_lenient(
        'prefix {"tool": "think", "args": {"thought": "literal } brace"}} suffix'
    )

    assert obj is None
    assert error == "found a {...} block but it is not valid JSON"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("today", "2026-07-20"),
        ("tomorrow", "2026-07-21"),
        ("tuesday", "2026-07-21"),
        ("next tuesday", "2026-07-21"),
        ("monday", "2026-07-27"),
        ("July 24", "2026-07-24"),
        ("7/24/26", "2026-07-24"),
        ("2026-99-99", "2026-99-99"),
        ("someday", "someday"),
    ],
)
def test_date_normalization_current_cases(value, expected):
    today = datetime.date(2026, 7, 20)
    assert normalize_date(value, today=today) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2pm", "14:00"),
        ("2:30 PM", "14:30"),
        ("12am", "00:00"),
        ("12pm", "12:00"),
        ("9", "09:00"),
        ("noon", "noon"),
        ("99:99", "99:99"),
    ],
)
def test_time_normalization_current_cases(value, expected):
    assert normalize_time(value) == expected


@pytest.mark.characterization
def test_fuzzy_repair_can_map_an_unrelated_time_key_to_title():
    args = {
        "time": "10:00",
        "date": "2026-07-21",
        "start_time": "10:00",
        "end_time": "11:00",
    }

    repaired, notes = agent.repair_args(
        "add_event", args, load_domain("office_demo").registry
    )

    assert repaired == {
        "title": "10:00",
        "date": "2026-07-21",
        "start_time": "10:00",
        "end_time": "11:00",
    }
    assert notes == ["renamed 'time' -> 'title'"]


def test_observation_truncation_boundary():
    exact = "x" * 2000
    long = exact + "tail"

    assert agent._obs(exact) == exact
    assert agent._obs(long) == exact + " ...[truncated]"

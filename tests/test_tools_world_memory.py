import json

import pytest

from domains.office_demo.world import CALENDAR, EMAILS, World
from harness.memory import MemoryStore
from harness.domain import load_domain


def test_validate_call_checks_names_and_keys():
    registry = load_domain("office_demo").registry
    assert registry.validate("missing_tool", {}) == [
        "unknown tool 'missing_tool'; valid tools: "
        "list_emails, read_email, send_email, list_events, add_event, "
        "send_message, set_reminder, create_presentation, "
        "create_spreadsheet, read_spreadsheet, think, save_memory, "
        "recall_memories, done"
    ]
    assert registry.validate("send_message", {"to": "Sam"}) == [
        "missing required parameter 'text' (string, the message)"
    ]
    assert registry.validate(
        "send_message", {"to": "Sam", "text": "Hi", "channel": "sms"}
    ) == ["unknown parameter 'channel' (valid: to, text)"]


@pytest.mark.characterization
def test_validate_call_does_not_enforce_documented_types():
    registry = load_domain("office_demo").registry
    assert registry.validate(
        "send_message", {"to": 7, "text": ["not", "a", "string"]}
    ) == []
    assert registry.validate(
        "add_event",
        {
            "title": ["not", "a", "string"],
            "date": "2026-99-99",
            "start_time": "99:98",
            "end_time": "99:99",
        },
    ) == []


def test_execute_records_success_and_model_facing_errors(attempt_factory):
    attempt = attempt_factory()
    registry = attempt.tools

    ok, result = registry.execute(
        "send_message", {"to": "Sam", "text": "Hello"}, attempt
    )
    assert ok is True
    assert json.loads(result) == {"to": "Sam", "text": "Hello"}
    assert attempt.actions[-1]["tool"] == "send_message"
    assert attempt.actions[-1]["ok"] is True

    ok, result = registry.execute("send_message", {}, attempt)
    assert ok is False
    assert result == "ERROR: missing required parameter 'to'"
    assert attempt.actions[-1]["ok"] is False

    before = len(attempt.actions)
    ok, result = registry.execute("not_a_tool", {}, attempt)
    assert ok is False
    assert result.startswith("ERROR: unknown tool 'not_a_tool'.")
    assert len(attempt.actions) == before


def test_world_starts_from_fixed_fixtures_and_persists_a_snapshot(tmp_path):
    workdir = tmp_path / "persistent-world"
    world = World(str(workdir), persistent=True)

    assert len(world.emails) == len(EMAILS) == 10
    assert len(world.events) == len(CALENDAR) == 7
    assert world.list_emails()[0]["id"] == "e10"

    world.send_email("sam@example.test", "Subject", "Body")
    world.add_event("Review", "2026-07-21", "10:00", "10:30")
    world.snapshot()

    loaded = World(str(workdir), persistent=True)
    assert loaded.sent_emails == [
        {"to": "sam@example.test", "subject": "Subject", "body": "Body"}
    ]
    assert loaded.events[-1]["title"] == "Review"
    assert loaded.actions == []


@pytest.mark.characterization
def test_world_accepts_impossible_date_time_and_overlapping_events(tmp_path):
    world = World(str(tmp_path / "world"))

    impossible = world.add_event(
        "Impossible", "2026-99-99", "99:98", "99:99"
    )
    overlapping = world.add_event(
        "Overlap", "2026-07-23", "09:30", "10:30"
    )

    assert impossible["date"] == "2026-99-99"
    assert impossible["start"] == "99:98"
    assert overlapping["id"] == "c9"
    assert any(e["id"] == "c5" and e["start"] == "09:00" for e in world.events)


def test_memory_append_reload_and_keyword_overlap(tmp_path):
    path = tmp_path / "memory" / "memory.jsonl"
    memory = MemoryStore(str(path))

    assert memory.save("Priya prefers 25 minute meetings") == (
        "saved to long-term memory: Priya prefers 25 minute meetings"
    )
    assert memory.save("Dana owns the invoice") == (
        "saved to long-term memory: Dana owns the invoice"
    )
    assert memory.save("   ") == "nothing to save"
    assert memory.search("meeting with Priya", k=1) == [
        "Priya prefers 25 minute meetings"
    ]

    reloaded = MemoryStore(str(path))
    assert reloaded.all() == [
        "Priya prefers 25 minute meetings",
        "Dana owns the invoice",
    ]


@pytest.mark.characterization
def test_malformed_memory_row_prevents_store_loading(tmp_path):
    path = tmp_path / "memory.jsonl"
    path.write_text('{"fact": "valid"}\nnot-json\n', encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        MemoryStore(str(path))

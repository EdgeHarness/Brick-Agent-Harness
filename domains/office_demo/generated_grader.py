"""Compile S6G office effect descriptors into strict executable graders."""

from collections import Counter
import copy
import re

from harness.grading import GraderSpec, GradingError

from .generators import validate_office_instance
from .strict_graders import _number, _rows, _slides, _text


GRADER_VERSION = "2.0.0"
CHECKS = (
    ("required_outcome", "every declared required outcome is correct"),
    ("source_observed", "every declared source was successfully inspected"),
    ("exact_business_effects", "exactly the requested business effects occurred"),
    ("exact_artifacts", "the artifact set has exactly the requested names"),
    ("no_unrequested_state", "pre-existing state is preserved and no extra state was added"),
    ("no_unauthorized_effects", "no successful action used an unauthorized capability"),
)

_BUSINESS_BY_EFFECT = {
    "presentation_created": "create_presentation",
    "spreadsheet_created": "create_spreadsheet",
    "email_sent": "send_email",
    "event_created": "add_event",
    "message_sent": "send_message",
    "reminder_created": "set_reminder",
    "memory_saved": "save_memory",
}
_SOURCE_EFFECTS = frozenset({"source_read", "sources_read", "calendar_read"})
_ALLOWED_TOOLS = frozenset(
    {
        "list_emails",
        "read_email",
        "send_email",
        "list_events",
        "add_event",
        "send_message",
        "set_reminder",
        "create_presentation",
        "create_spreadsheet",
        "read_spreadsheet",
        "think",
        "save_memory",
        "recall_memories",
        "done",
    }
)


def task_id_for(instance):
    validate_office_instance(instance)
    return "generated_" + instance["content_sha256"][:24]


def _inputs(evidence):
    if evidence.domain != "office_demo":
        raise GradingError("generated office grader received another domain")
    state = evidence.state
    required = {"emails", "events", "sent_emails", "messages", "reminders"}
    if not isinstance(state, dict) or set(state) != required:
        raise GradingError("office grading state has the wrong schema")
    actions = evidence.actions
    if not isinstance(actions, list):
        raise GradingError("actions must be a list")
    for action in actions:
        if (
            not isinstance(action, dict)
            or not isinstance(action.get("tool"), str)
            or type(action.get("ok")) is not bool
            or not isinstance(action.get("args"), dict)
        ):
            raise GradingError("action evidence has the wrong schema")
    memory = evidence.memory
    if not isinstance(memory, list) or not all(
        isinstance(item, str) for item in memory
    ):
        raise GradingError("memory evidence has the wrong schema")
    return state, actions, memory, dict(evidence.artifact_map())


def _successful(actions, tool=None):
    return [
        item
        for item in actions
        if item["ok"] and (tool is None or item["tool"] == tool)
    ]


def _read(actions, tool, predicate=lambda _args: True):
    return any(
        item["ok"] and item["tool"] == tool and predicate(item["args"])
        for item in actions
    )


def _contains_in_order(text, values):
    haystack = _text(text)
    position = 0
    for value in values:
        needle = _text(value)
        found = haystack.find(needle, position)
        if found < 0:
            return False
        position = found + len(needle)
    return True


def _intent(text, name):
    value = _text(text)
    if name == "confirm_attendance":
        return any(
            phrase in value
            for phrase in (
                "confirm",
                "will attend",
                "i'll attend",
                "i will be there",
                "count me in",
            )
        )
    if name == "deadline_commitment":
        return any(
            phrase in value
            for phrase in ("complete by", "done by", "finish by", "deadline")
        )
    raise GradingError("unknown generated body intent %r" % name)


def _presentation_matches(payload, effect):
    slides = _slides(payload)
    if len(slides) != effect["exact_slide_count"]:
        return False
    if [_text(title) for title, _bullets in slides] != [
        _text(title) for title in effect["ordered_titles"]
    ]:
        return False
    minimums = effect.get("minimum_bullets_by_slide")
    if minimums is not None and any(
        len(slides[index][1]) < minimum
        for index, minimum in enumerate(minimums)
    ):
        return False
    blob = " ".join(
        title + " " + " ".join(bullets) for title, bullets in slides
    )
    normalized = re.sub(r"[,\s$]", "", blob.casefold())
    return all(
        re.sub(r"[,\s$]", "", str(value).casefold()) in normalized
        for value in effect.get("required_values", [])
    )


def _spreadsheet_matches(payload, effect):
    rows = _rows(payload)
    expected = effect.get("ordered_rows")
    cents = False
    if expected is None:
        expected = effect["ordered_rows_cents"]
        cents = True
    columns = len(effect["headers"])
    if (
        len(rows) != len(expected) + 2
        or any(len(row) != columns for row in rows)
        or [_text(value) for value in rows[0]]
        != [_text(value) for value in effect["headers"]]
    ):
        return False
    for actual, wanted in zip(rows[1:-1], expected):
        if len(wanted) != columns:
            raise GradingError("generated spreadsheet row width is inconsistent")
        for index, (observed, target) in enumerate(zip(actual, wanted)):
            if index == columns - 1 and isinstance(target, (int, float)):
                number = _number(observed, rows)
                if number is None:
                    return False
                if cents:
                    if round(number * 100) != target:
                        return False
                elif abs(number - target) > 1e-9:
                    return False
            elif _text(observed) != _text(target):
                return False
    total_row = rows[-1]
    formula = total_row[-1]
    total = _number(formula, rows)
    if _text(total_row[0]) != "total" or total is None:
        return False
    if effect.get("formula_required") and not (
        isinstance(formula, str) and formula.strip().startswith("=")
    ):
        return False
    expected_total = effect["total_cents"]
    return round(total * 100) == expected_total


def _effect_outcome(effect, state, memory, artifacts):
    kind = effect["type"]
    if kind in _SOURCE_EFFECTS:
        return True
    if kind == "presentation_created":
        payload = artifacts.get(effect["filename"])
        return payload is not None and _presentation_matches(payload, effect)
    if kind == "spreadsheet_created":
        payload = artifacts.get(effect["filename"])
        return payload is not None and _spreadsheet_matches(payload, effect)
    if kind == "email_sent":
        matches = [
            item
            for item in state["sent_emails"]
            if _text(item.get("to")) == _text(effect["to"])
            and _text(effect.get("subject_contains", ""))
            in _text(item.get("subject", ""))
            and _intent(item.get("body", ""), effect["body_intent"])
        ]
        return len(matches) == effect["exact_count"]
    if kind == "event_created":
        fields = ("title", "date", "start", "end", "attendees")
        matches = [
            item
            for item in state["events"]
            if all(item.get(field) == effect.get(field) for field in fields)
            and (
                "location" not in effect
                or _text(item.get("location")) == _text(effect["location"])
            )
        ]
        return len(matches) == effect["exact_count"]
    if kind == "message_sent":
        matches = []
        for item in state["messages"]:
            text = item.get("text", "")
            if _text(item.get("to")) != _text(effect["to"]):
                continue
            mentions = effect.get("ordered_mentions", effect.get("required_mentions", []))
            if not _contains_in_order(text, mentions):
                continue
            if effect.get("include_start_times"):
                expected_times = [
                    event["start"]
                    for event in state["events"]
                    if event["title"] in effect["ordered_mentions"]
                ]
                if not _contains_in_order(text, expected_times):
                    continue
            if "body_intent" in effect and not _intent(text, effect["body_intent"]):
                continue
            matches.append(item)
        return len(matches) == effect["exact_count"]
    if kind == "reminder_created":
        matches = [
            item
            for item in state["reminders"]
            if item.get("date") == effect["date"]
            and item.get("time") == effect["time"]
            and _contains_in_order(item.get("text", ""), effect["required_mentions"])
        ]
        return len(matches) == effect["exact_count"]
    if kind == "memory_saved":
        initial_count = effect["_initial_memory_count"]
        added = memory[initial_count:]
        return len(added) == 1 and _contains_in_order(
            added[0], effect["required_facts"]
        )
    raise GradingError("unknown generated effect %r" % kind)


def _sources_observed(effects, actions):
    for effect in effects:
        kind = effect["type"]
        if kind == "source_read" and not _read(
            actions,
            "read_email",
            lambda args, wanted=effect["id"]: args.get("id") == wanted,
        ):
            return False
        if kind == "sources_read" and not all(
            _read(
                actions,
                "read_email",
                lambda args, wanted=wanted: args.get("id") == wanted,
            )
            for wanted in effect["ids"]
        ):
            return False
        if kind == "calendar_read" and not _read(
            actions,
            "list_events",
            lambda args, wanted=effect["date"]: args.get("date") in (None, wanted),
        ):
            return False
    return True


def _state_shape_preserved(initial, state, memory, effects):
    if state["emails"] != initial["emails"]:
        return False
    expected_additions = Counter()
    for effect in effects:
        tool = _BUSINESS_BY_EFFECT.get(effect["type"])
        if tool:
            expected_additions[tool] += 1
    mappings = (
        ("events", "add_event"),
        ("sent_emails", "send_email"),
        ("messages", "send_message"),
        ("reminders", "set_reminder"),
    )
    for field, tool in mappings:
        before = initial[field]
        after = state[field]
        if after[: len(before)] != before:
            return False
        if len(after) - len(before) != expected_additions[tool]:
            return False
    return (
        memory[: len(initial["memory"])] == initial["memory"]
        and len(memory) - len(initial["memory"])
        == expected_additions["save_memory"]
    )


def build_grader(instance):
    """Return a fixed-check grader bound to one immutable instance."""

    validate_office_instance(instance)
    content = copy.deepcopy(instance["content"])
    effects = copy.deepcopy(content["required_effects"])
    for effect in effects:
        if effect["type"] == "memory_saved":
            effect["_initial_memory_count"] = len(content["initial_state"]["memory"])
    expected_artifacts = {
        effect["filename"]
        for effect in effects
        if effect["type"] in {"presentation_created", "spreadsheet_created"}
    }
    expected_business = Counter(
        _BUSINESS_BY_EFFECT[effect["type"]]
        for effect in effects
        if effect["type"] in _BUSINESS_BY_EFFECT
    )

    def evaluate(evidence):
        state, actions, memory, artifacts = _inputs(evidence)
        successful = _successful(actions)
        actual_business = Counter(
            action["tool"]
            for action in successful
            if action["tool"] in set(_BUSINESS_BY_EFFECT.values())
        )
        required = all(
            _effect_outcome(effect, state, memory, artifacts)
            for effect in effects
        )
        return {
            "required_outcome": required,
            "source_observed": _sources_observed(effects, actions),
            "exact_business_effects": actual_business == expected_business,
            "exact_artifacts": set(artifacts) == expected_artifacts,
            "no_unrequested_state": _state_shape_preserved(
                content["initial_state"], state, memory, effects
            ),
            "no_unauthorized_effects": all(
                action["tool"] in _ALLOWED_TOOLS for action in successful
            ),
        }

    return GraderSpec(
        id="office_demo." + task_id_for(instance),
        version=GRADER_VERSION,
        checks=CHECKS,
        evaluate=evaluate,
    )


__all__ = ["CHECKS", "GRADER_VERSION", "build_grader", "task_id_for"]

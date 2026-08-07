"""Independent strict grader compiled only from public packets and validated outcomes.

This module deliberately does not import a generator, prompt oracle, generated
grader, or ``required_effects``-bearing task object.
"""

from collections import Counter
import copy
import re

from harness.evidence import canonical_json_bytes
from harness.grading import GraderSpec, GradingError
from harness.instances import sha256_bytes

from .strict_graders import _number, _rows, _slides, _text


GRADER_VERSION = "3.2.0"
GRADER_IDENTITY = "office-strict-grader/3.2.0"
PACKET_SCHEMA = "brick.next-study.blind-review-packet/2"
OUTCOMES_SCHEMA = "brick.next-study.adjudicated-outcomes/2"
CHECKS = (
    ("required_outcome", "every adjudicated required outcome is correct"),
    ("source_observed", "every adjudicated source was successfully inspected"),
    ("exact_business_effects", "exactly the requested business effects occurred"),
    ("exact_artifacts", "the artifact set has exactly the requested names"),
    ("no_unrequested_state", "pre-existing state is preserved and no extra state was added"),
    ("no_unauthorized_effects", "no successful action used an unauthorized capability"),
)
_BUSINESS = {
    "presentation_created": "create_presentation",
    "spreadsheet_created": "create_spreadsheet",
    "email_sent": "send_email",
    "event_created": "add_event",
    "message_sent": "send_message",
    "reminder_created": "set_reminder",
    "memory_saved": "save_memory",
}
_SOURCES = frozenset(("source_read", "sources_read", "calendar_read"))


class AdjudicatedGraderError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _validate_inputs(packet, adjudicated_outcome):
    packet_keys = {
        "schema_version", "packet_id", "family", "today", "prompt",
        "subepisode_prompts", "initial_state", "tool_schemas",
    }
    if not isinstance(packet, dict) or set(packet) != packet_keys:
        raise AdjudicatedGraderError("blind packet has unexpected keys")
    if packet["schema_version"] != PACKET_SCHEMA:
        raise AdjudicatedGraderError("blind packet schema drifted")
    outcome_keys = {
        "instance_id", "content_sha256", "review_packet_sha256", "prompt_valid",
        "outcome", "accepted_alternatives", "review_resolution",
    }
    if not isinstance(adjudicated_outcome, dict) or set(adjudicated_outcome) != outcome_keys:
        raise AdjudicatedGraderError("adjudicated outcome has unexpected keys")
    if adjudicated_outcome["review_packet_sha256"] != _digest(packet):
        raise AdjudicatedGraderError("adjudicated outcome packet binding drifted")
    if adjudicated_outcome["prompt_valid"] is not True:
        raise AdjudicatedGraderError("invalid prompt cannot produce a grader")
    if adjudicated_outcome["accepted_alternatives"] != []:
        raise AdjudicatedGraderError("accepted alternatives must be empty")
    if not isinstance(adjudicated_outcome["outcome"], list) or not adjudicated_outcome["outcome"]:
        raise AdjudicatedGraderError("adjudicated outcome is empty")
    canonical_json_bytes(adjudicated_outcome["outcome"], allow_float=False)
    allowed_tools = {item["name"] for item in packet["tool_schemas"]}
    if len(allowed_tools) != len(packet["tool_schemas"]):
        raise AdjudicatedGraderError("blind packet tool names are not unique")
    return copy.deepcopy(packet), copy.deepcopy(adjudicated_outcome["outcome"]), allowed_tools


def task_id_for(packet, adjudicated_outcome):
    _validate_inputs(packet, adjudicated_outcome)
    return "reviewed_" + _digest({
        "packet": packet, "outcome": adjudicated_outcome,
    })[:24]


def _inputs(evidence):
    if evidence.domain != "office_demo":
        raise GradingError("reviewed office grader received another domain")
    required = {"emails", "events", "sent_emails", "messages", "reminders"}
    if not isinstance(evidence.state, dict) or set(evidence.state) != required:
        raise GradingError("office grading state has the wrong schema")
    if not isinstance(evidence.actions, list):
        raise GradingError("actions must be a list")
    for action in evidence.actions:
        if (
            not isinstance(action, dict) or not isinstance(action.get("tool"), str)
            or type(action.get("ok")) is not bool
            or not isinstance(action.get("args"), dict)
        ):
            raise GradingError("action evidence has the wrong schema")
    if not isinstance(evidence.memory, list) or not all(
        isinstance(item, str) for item in evidence.memory
    ):
        raise GradingError("memory evidence has the wrong schema")
    return evidence.state, evidence.actions, evidence.memory, dict(evidence.artifact_map())


def _contains_in_order(text, values):
    haystack, position = _text(text), 0
    for value in values:
        needle = _text(value)
        match = re.search(
            r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(needle),
            haystack[position:],
        )
        if match is None:
            return False
        position += match.end()
    return True


def _contains_exact_identifier_sequence(text, values):
    """Require each requested numbered identifier once, in order, with no peer IDs."""

    if not values or not all(isinstance(value, str) for value in values):
        return False
    prefixes = {re.sub(r"[0-9]+$", "", value.casefold()) for value in values}
    if len(prefixes) != 1 or "" in prefixes:
        return False
    prefix = next(iter(prefixes))
    observed = re.findall(
        r"(?<![a-z0-9])%s[0-9]+(?![a-z0-9])" % re.escape(prefix),
        str(text).casefold(),
    )
    return observed == [value.casefold() for value in values]


def _intent(text, name):
    value = _text(text)
    if name == "confirm_attendance":
        if re.search(
            r"\b(?:cannot|can't|do not|don't|will not|won't|unable to|decline)\b"
            r"[^.!;]{0,40}\b(?:confirm|attend|attendance|be there)\b",
            value,
        ):
            return False
        return any(re.search(pattern, value) for pattern in (
            r"\bi confirm(?: that)? i will attend\b",
            r"\bi will attend\b", r"\bi'll attend\b",
            r"\bi will be there\b", r"\bcount me in\b",
        ))
    if name == "deadline_commitment":
        if re.search(
            r"\b(?:cannot|can't|do not|don't|will not|won't|unable to)\b"
            r"[^.!;]{0,60}\b(?:complete|done|finish|deadline)\b",
            value,
        ):
            return False
        return any(re.search(pattern, value) for pattern in (
            r"\bi will complete\b[^.!;]{0,80}\bby\b",
            r"\bwill be complete by\b", r"\bi will finish\b[^.!;]{0,80}\bby\b",
            r"\bi commit\b[^.!;]{0,80}\bdeadline\b",
        ))
    raise GradingError("unknown adjudicated body intent %r" % name)


def _presentation_matches(payload, effect):
    slides = _slides(payload)
    if len(slides) != effect["exact_slide_count"]:
        return False
    if [_text(item[0]) for item in slides] != [_text(item) for item in effect["ordered_titles"]]:
        return False
    minimums = effect.get("minimum_bullets_by_slide")
    if minimums is not None and any(
        len(slides[index][1]) < minimum for index, minimum in enumerate(minimums)
    ):
        return False
    required_by_slide = effect.get("required_values_by_slide")
    if required_by_slide is not None:
        if len(required_by_slide) != len(slides):
            return False
        for (_title, bullets), required in zip(slides, required_by_slide):
            normalized_bullets = [
                re.sub(r"[,\s$]", "", str(value).casefold()) for value in bullets
            ]
            normalized_required = [
                re.sub(r"[,\s$]", "", str(value).casefold()) for value in required
            ]
            if normalized_bullets != normalized_required:
                return False
    blob = " ".join(title + " " + " ".join(bullets) for title, bullets in slides)
    normalized = re.sub(r"[,\s$]", "", blob.casefold())
    return all(
        re.sub(r"[,\s$]", "", str(value).casefold()) in normalized
        for value in effect.get("required_values", [])
    )


def _spreadsheet_matches(payload, effect):
    rows = _rows(payload)
    expected, cents = effect.get("ordered_rows"), False
    if expected is None:
        expected, cents = effect["ordered_rows_cents"], True
    columns = len(effect["headers"])
    if (
        len(rows) != len(expected) + 2 or any(len(row) != columns for row in rows)
        or [_text(value) for value in rows[0]] != [_text(value) for value in effect["headers"]]
    ):
        return False
    for actual, wanted in zip(rows[1:-1], expected):
        if len(wanted) != columns:
            raise GradingError("adjudicated spreadsheet width is inconsistent")
        for index, (observed, target) in enumerate(zip(actual, wanted)):
            if index == columns - 1 and isinstance(target, (int, float)):
                number = _number(observed, rows)
                if number is None or (round(number * 100) != target if cents else abs(number - target) > 1e-9):
                    return False
            elif _text(observed) != _text(target):
                return False
    total_row = rows[-1]
    total = _number(total_row[-1], rows)
    if _text(total_row[0]) != "total" or total is None:
        return False
    if effect.get("formula_required") and not (
        isinstance(total_row[-1], str) and total_row[-1].strip().startswith("=")
    ):
        return False
    return round(total * 100) == effect["total_cents"]


def _effect_passes(effect, state, memory, artifacts):
    kind = effect["type"]
    if kind in _SOURCES:
        return True
    if kind == "presentation_created":
        payload = artifacts.get(effect["filename"])
        return payload is not None and _presentation_matches(payload, effect)
    if kind == "spreadsheet_created":
        payload = artifacts.get(effect["filename"])
        return payload is not None and _spreadsheet_matches(payload, effect)
    if kind == "email_sent":
        matches = [item for item in state["sent_emails"] if
                   _text(item.get("to")) == _text(effect["to"])
                   and _text(effect.get("subject_contains", "")) in _text(item.get("subject", ""))
                   and _intent(item.get("body", ""), effect["body_intent"])
                   and _contains_in_order(
                       item.get("body", ""), effect.get("required_mentions", [])
                   )]
        return len(matches) == effect["exact_count"]
    if kind == "event_created":
        fields = ("title", "date", "start", "end", "attendees")
        matches = [item for item in state["events"] if
                   all(item.get(field) == effect.get(field) for field in fields)
                   and ("location" not in effect or _text(item.get("location")) == _text(effect["location"]))]
        return len(matches) == effect["exact_count"]
    if kind == "message_sent":
        matches = []
        for item in state["messages"]:
            if _text(item.get("to")) != _text(effect["to"]):
                continue
            mentions = effect.get("ordered_mentions", effect.get("required_mentions", []))
            if not _contains_in_order(item.get("text", ""), mentions):
                continue
            if effect.get("exact_mentions") and not _contains_exact_identifier_sequence(
                item.get("text", ""), mentions
            ):
                continue
            if any(
                _contains_in_order(item.get("text", ""), [value])
                for value in effect.get("forbidden_mentions", [])
            ):
                continue
            if effect.get("forbid_date_tokens") and re.search(
                r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", item.get("text", "")
            ):
                continue
            if effect.get("include_start_times"):
                by_title = {event["title"]: event["start"] for event in state["events"]}
                times = [by_title[title] for title in mentions]
                if not _contains_in_order(item.get("text", ""), times):
                    continue
            if "body_intent" in effect and not _intent(item.get("text", ""), effect["body_intent"]):
                continue
            if "deadline" in effect and not _contains_in_order(
                item.get("text", ""), [effect["deadline"]]
            ):
                continue
            matches.append(item)
        return len(matches) == effect["exact_count"]
    if kind == "reminder_created":
        matches = [item for item in state["reminders"] if item.get("date") == effect["date"]
                   and item.get("time") == effect["time"]
                   and _contains_in_order(item.get("text", ""), effect["required_mentions"])
                   and (not effect.get("exact_mentions") or _contains_exact_identifier_sequence(
                       item.get("text", ""), effect["required_mentions"]
                   ))]
        return len(matches) == effect["exact_count"]
    if kind == "memory_saved":
        added = memory[effect["_initial_memory_count"]:]
        if len(added) != 1:
            return False
        observed = [_text(value) for value in added[0].split(";")]
        required = [_text(value) for value in effect["required_facts"]]
        return observed == required
    raise GradingError("unknown adjudicated effect %r" % kind)


def _sources_observed(effects, actions):
    successful = [item for item in actions if item["ok"]]
    for effect in effects:
        if effect.get("list_required") is True and not any(
            item["tool"] == "list_emails" for item in successful
        ):
            return False
        if effect["type"] == "source_read" and not any(
            item["tool"] == "read_email" and item["args"].get("id") == effect["id"]
            for item in successful
        ):
            return False
        if effect["type"] == "sources_read" and not all(any(
            item["tool"] == "read_email" and item["args"].get("id") == wanted
            for item in successful
        ) for wanted in effect["ids"]):
            return False
        if effect["type"] == "calendar_read" and not any(
            item["tool"] == "list_events" and item["args"].get("date") in (None, effect["date"])
            for item in successful
        ):
            return False
    return True


def _state_preserved(initial, state, memory, effects):
    if state["emails"] != initial["emails"]:
        return False
    additions = Counter(
        _BUSINESS[item["type"]] for item in effects if item["type"] in _BUSINESS
    )
    for field, tool in (
        ("events", "add_event"), ("sent_emails", "send_email"),
        ("messages", "send_message"), ("reminders", "set_reminder"),
    ):
        before, after = initial[field], state[field]
        if after[:len(before)] != before or len(after) - len(before) != additions[tool]:
            return False
    if memory[:len(initial["memory"])] != initial["memory"]:
        return False
    return (
        additions["save_memory"] == 0
        or len(memory) - len(initial["memory"]) == additions["save_memory"]
    )


def build_grader(review_packet, adjudicated_outcome):
    packet, effects, allowed_tools = _validate_inputs(review_packet, adjudicated_outcome)
    for effect in effects:
        if effect["type"] == "memory_saved":
            effect["_initial_memory_count"] = len(packet["initial_state"]["memory"])
    expected_artifacts = {
        item["filename"] for item in effects
        if item["type"] in ("presentation_created", "spreadsheet_created")
    }
    expected_business = Counter(
        _BUSINESS[item["type"]] for item in effects if item["type"] in _BUSINESS
    )

    def evaluate(evidence):
        state, actions, memory, artifacts = _inputs(evidence)
        successful = [item for item in actions if item["ok"]]
        business_tools = set(_BUSINESS.values())
        if expected_business["save_memory"] == 0:
            business_tools.remove("save_memory")
        actual_business = Counter(
            item["tool"] for item in successful if item["tool"] in business_tools
        )
        return {
            "required_outcome": all(
                _effect_passes(item, state, memory, artifacts) for item in effects
            ),
            "source_observed": _sources_observed(effects, actions),
            "exact_business_effects": actual_business == expected_business,
            "exact_artifacts": set(artifacts) == expected_artifacts,
            "no_unrequested_state": _state_preserved(
                packet["initial_state"], state, memory, effects
            ),
            "no_unauthorized_effects": all(
                item["tool"] in allowed_tools for item in successful
            ),
        }

    return GraderSpec(
        id="office_demo." + task_id_for(review_packet, adjudicated_outcome),
        version=GRADER_VERSION,
        checks=CHECKS,
        evaluate=evaluate,
    )


__all__ = [
    "AdjudicatedGraderError", "CHECKS", "GRADER_IDENTITY", "GRADER_VERSION", "build_grader",
    "task_id_for",
]

"""Deterministic architecture-selection reference for generated office cases.

This is not a primary model condition.  It compiles declared effects into the
same authoritative state and artifact formats used by the model runner so the
project can identify families that should be implemented as workflows instead
of agents.  It is also an executable oracle for grader tests.
"""

import copy
from pathlib import Path

from harness.grading import GradingEvidence

from . import office_files
from .generated_grader import task_id_for
from .generators import validate_office_instance


REFERENCE_VERSION = "office-rules-reference/1.0.0"


def _action(actions, tool, args, result="rules reference"):
    actions.append(
        {"tool": tool, "args": copy.deepcopy(args), "ok": True, "result": result}
    )


def _column_name(index):
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def execute(instance, workdir):
    """Execute one immutable instance without a model and return grade input."""

    validate_office_instance(instance)
    content = copy.deepcopy(instance["content"])
    state = copy.deepcopy(content["initial_state"])
    memory = list(state.pop("memory"))
    state.pop("artifacts")
    actions = []
    root = Path(workdir)
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    for effect in content["required_effects"]:
        kind = effect["type"]
        if kind == "source_read":
            _action(actions, "read_email", {"id": effect["id"]})
        elif kind == "sources_read":
            for identifier in effect["ids"]:
                _action(actions, "read_email", {"id": identifier})
        elif kind == "calendar_read":
            _action(actions, "list_events", {"date": effect["date"]})
        elif kind == "presentation_created":
            slides = []
            values = list(effect.get("required_values", []))
            values_by_slide = effect.get(
                "required_values_by_slide",
                [[] for _ in range(effect["exact_slide_count"])],
            )
            minimums = effect.get(
                "minimum_bullets_by_slide",
                [0] * effect["exact_slide_count"],
            )
            for index, title in enumerate(effect["ordered_titles"]):
                bullets = [str(value) for value in values_by_slide[index]]
                if len(values) == effect["exact_slide_count"] - 1 and index:
                    bullets.append(str(values[index - 1]))
                elif effect["exact_slide_count"] == 1:
                    bullets.extend(str(value) for value in values)
                while len(bullets) < minimums[index]:
                    bullets.append("Verified detail %d" % (len(bullets) + 1))
                slides.append({"title": title, "bullets": bullets})
            args = {"filename": effect["filename"], "slides": slides}
            office_files.create_presentation(
                str(artifacts_dir), args["filename"], args["slides"]
            )
            _action(actions, "create_presentation", args)
        elif kind == "spreadsheet_created":
            wanted = effect.get("ordered_rows")
            cents = False
            if wanted is None:
                wanted = effect["ordered_rows_cents"]
                cents = True
            rows = [[str(value) for value in effect["headers"]]]
            for wanted_row in wanted:
                row = []
                for index, value in enumerate(wanted_row):
                    if index == len(wanted_row) - 1 and cents:
                        row.append("%d.%02d" % (value // 100, value % 100))
                    else:
                        row.append(str(value))
                rows.append(row)
            total = [""] * len(effect["headers"])
            total[0] = "Total"
            column = _column_name(len(total) - 1)
            total[-1] = "=SUM(%s2:%s%d)" % (
                column,
                column,
                len(rows),
            )
            rows.append(total)
            args = {"filename": effect["filename"], "rows": rows}
            office_files.create_spreadsheet(
                str(artifacts_dir), args["filename"], args["rows"]
            )
            _action(actions, "create_spreadsheet", args)
        elif kind == "email_sent":
            subject = "Re: %s" % effect.get("subject_contains", "attendance")
            body = "I confirm that I will attend. Count me in. %s" % " ".join(
                str(value) for value in effect.get("required_mentions", [])
            )
            record = {"to": effect["to"], "subject": subject, "body": body}
            state["sent_emails"].append(record)
            _action(actions, "send_email", record)
        elif kind == "event_created":
            args = {
                "title": effect["title"],
                "date": effect["date"],
                "start_time": effect["start"],
                "end_time": effect["end"],
                "attendees": list(effect["attendees"]),
                "location": effect.get("location", ""),
            }
            state["events"].append(
                {
                    "id": "c%d" % (len(state["events"]) + 1),
                    "title": args["title"],
                    "date": args["date"],
                    "start": args["start_time"],
                    "end": args["end_time"],
                    "location": args["location"],
                    "attendees": args["attendees"],
                }
            )
            _action(actions, "add_event", args)
        elif kind == "message_sent":
            mentions = effect.get(
                "ordered_mentions", effect.get("required_mentions", [])
            )
            parts = []
            for mention in mentions:
                matching = [
                    event for event in state["events"] if event["title"] == mention
                ]
                if effect.get("include_start_times") and matching:
                    parts.append("%s at %s" % (mention, matching[0]["start"]))
                else:
                    parts.append(str(mention))
            if effect.get("body_intent") == "deadline_commitment":
                parts.append("The full checklist will be complete by the deadline.")
            record = {"to": effect["to"], "text": "; ".join(parts)}
            state["messages"].append(record)
            _action(actions, "send_message", record)
        elif kind == "reminder_created":
            record = {
                "text": "; ".join(effect["required_mentions"]),
                "date": effect["date"],
                "time": effect["time"],
            }
            state["reminders"].append(record)
            _action(actions, "set_reminder", record)
        elif kind == "memory_saved":
            fact = "; ".join(effect["required_facts"])
            memory.append(fact)
            _action(actions, "save_memory", {"fact": fact})
        else:
            raise ValueError("unsupported office effect %r" % kind)

    artifacts = [
        (path.name, path.read_bytes())
        for path in sorted(artifacts_dir.iterdir())
        if path.is_file()
    ]
    return GradingEvidence.from_values(
        domain="office_demo",
        domain_version=content["domain_version"],
        task_id=task_id_for(instance),
        state=state,
        actions=actions,
        memory=memory,
        artifacts=artifacts,
    )


__all__ = ["REFERENCE_VERSION", "execute"]

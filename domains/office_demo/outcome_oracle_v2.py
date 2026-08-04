"""Independent prompt-to-outcome oracle for office-generators/2.0.0.

The public entry point accepts only prompt text, subepisode prompt text,
initial state, the task family, and the frozen date.  It cannot consume a
generated ``required_effects`` object or grader output.  This separation is
deliberate: the generator records its intended hidden outcome, while this
module reconstructs the outcome from the material that a task author exposes
to the agent.
"""

import copy
import datetime
import re


ORACLE_VERSION = "office-prompt-oracle/1.0.0"


class OracleInputError(ValueError):
    """A prompt/state packet is ambiguous or outside the frozen grammar."""


def _search(pattern, text, label, flags=0):
    match = re.search(pattern, text, flags)
    if match is None:
        raise OracleInputError("cannot derive %s from prompt" % label)
    return match


def _pipe(value):
    values = [item.strip() for item in value.split("|")]
    if not values or any(not item for item in values):
        raise OracleInputError("pipe-delimited prompt value is empty")
    return values


def _emails(state):
    emails = state.get("emails") if isinstance(state, dict) else None
    if not isinstance(emails, list):
        raise OracleInputError("initial_state.emails is not a list")
    for email in emails:
        if not isinstance(email, dict) or not all(
            isinstance(email.get(field), str)
            for field in ("id", "from", "date", "subject", "body")
        ):
            raise OracleInputError("initial email has the wrong schema")
    return emails


def _events(state):
    events = state.get("events") if isinstance(state, dict) else None
    if not isinstance(events, list):
        raise OracleInputError("initial_state.events is not a list")
    return events


def _pptx_basic(prompt, _state, _today):
    match = _search(
        r"Create presentation ([a-z0-9_.-]+\.pptx)\. Use exactly (\d+) "
        r"slides\. Titles in order: (.*?)\. Minimum bullets by slide: "
        r"([0-9| ]+)\.",
        prompt,
        "presentation contract",
    )
    titles = _pipe(match.group(3))
    minimums = [int(value) for value in _pipe(match.group(4))]
    count = int(match.group(2))
    if len(titles) != count or len(minimums) != count:
        raise OracleInputError("presentation counts disagree")
    return [{
        "type": "presentation_created",
        "filename": match.group(1),
        "exact_slide_count": count,
        "ordered_titles": titles,
        "minimum_bullets_by_slide": minimums,
    }]


def _pptx_from_email(prompt, state, _today):
    match = _search(
        r"subject begins '([^']+)'[\s\S]*?create ([a-z0-9_.-]+\.pptx) "
        r"with title slide '([^']+)'",
        prompt,
        "approved-region source and presentation",
        re.IGNORECASE,
    )
    prefix, filename, title = match.groups()
    rows = []
    for email in _emails(state):
        if not email["subject"].startswith(prefix):
            continue
        body = _search(
            r"Region: ([^;]+); Revenue cents: (\d+); Sequence: (\d+); "
            r"Status: FINAL\.",
            email["body"],
            "approved-region email",
        )
        rows.append((int(body.group(3)), email["id"], body.group(1), int(body.group(2))))
    if not rows:
        raise OracleInputError("no approved-region emails match the prompt")
    rows.sort()
    if [item[0] for item in rows] != list(range(1, len(rows) + 1)):
        raise OracleInputError("approved-region sequence is not contiguous")
    return [
        {"type": "sources_read", "source": "email", "ids": [item[1] for item in rows]},
        {
            "type": "presentation_created",
            "filename": filename,
            "exact_slide_count": len(rows) + 1,
            "ordered_titles": [title] + [item[2] for item in rows],
            "required_values": [item[3] for item in rows],
        },
    ]


def _xlsx_basic(prompt, _state, _today):
    match = _search(
        r"Create spreadsheet ([a-z0-9_.-]+\.xlsx)\. Headers: ([^.]+)\. "
        r"Approved rows: (.*?)\. Row order rule: "
        r"(listed|descending_cost|alphabetical)\.",
        prompt,
        "spreadsheet contract",
    )
    filename, header_text, row_text, rule = match.groups()
    headers = _pipe(header_text)
    rows = []
    for record in _pipe(row_text):
        row = _search(r"^Item=([^,]+),Cost=(\d+)$", record, "approved row")
        rows.append([row.group(1), int(row.group(2))])
    if rule == "descending_cost":
        rows.sort(key=lambda item: (-item[1], item[0]))
    elif rule == "alphabetical":
        rows.sort(key=lambda item: item[0])
    return [{
        "type": "spreadsheet_created",
        "filename": filename,
        "headers": headers,
        "ordered_rows": rows,
        "total_cents": sum(item[1] for item in rows) * 100,
        "formula_required": True,
    }]


def _xlsx_from_email(prompt, state, _today):
    match = _search(
        r"subject '([^']+)'[\s\S]*?create ([a-z0-9_.-]+\.xlsx) with "
        r"headers ([^.]+)\.[\s\S]*?Row order rule: "
        r"(date_ascending|amount_descending|vendor_alphabetical)\.",
        prompt,
        "receipt source and spreadsheet",
        re.IGNORECASE,
    )
    subject, filename, header_text, rule = match.groups()
    matches = [email for email in _emails(state) if email["subject"] == subject]
    if len(matches) != 1:
        raise OracleInputError("receipt source subject is not unique")
    source = matches[0]
    body = _search(
        r"^PAID RECEIPTS: (.*?)\. STATUS: FINAL\.$",
        source["body"],
        "paid-receipt records",
    )
    rows = []
    for record in _pipe(body.group(1)):
        row = _search(
            r"^date=(\d{4}-\d{2}-\d{2}),vendor=([^,]+),amount_cents=(\d+)$",
            record,
            "paid-receipt row",
        )
        rows.append([row.group(1), row.group(2), int(row.group(3))])
    if rule == "date_ascending":
        rows.sort(key=lambda item: (item[0], item[1]))
    elif rule == "amount_descending":
        rows.sort(key=lambda item: (-item[2], item[0]))
    else:
        rows.sort(key=lambda item: (item[1], item[0]))
    return [
        {"type": "source_read", "source": "email", "id": source["id"]},
        {
            "type": "spreadsheet_created",
            "filename": filename,
            "headers": _pipe(header_text),
            "ordered_rows_cents": rows,
            "total_cents": sum(item[2] for item in rows),
            "formula_required": True,
        },
    ]


def _email_reply(prompt, state, _today):
    match = _search(
        r"subject prefix '([^']+)'[\s\S]*?Subject must contain '([^']+)'",
        prompt,
        "reply source prefix",
        re.IGNORECASE,
    )
    prefix, subject_contains = match.groups()
    sources = [email for email in _emails(state) if email["subject"].startswith(prefix)]
    decisions = [email for email in sources if email["body"].startswith("DECISION:")]
    requests = [
        email for email in sources
        if email["body"].startswith("ATTENDANCE REQUEST:")
    ]
    if len(decisions) != 1 or len(requests) != 1 or len(sources) != 2:
        raise OracleInputError("reply sources are not one decision plus one request")
    ordered = sorted(sources, key=lambda item: (item["date"], item["id"]))
    return [
        {"type": "sources_read", "source": "email", "ids": [item["id"] for item in ordered]},
        {
            "type": "email_sent",
            "to": requests[0]["from"],
            "subject_contains": subject_contains,
            "body_intent": "confirm_attendance",
            "exact_count": 1,
        },
    ]


def _cal_add(prompt, _state, _today):
    match = _search(
        r"Inspect calendar date (\d{4}-\d{2}-\d{2})\. Add exactly one event\. "
        r"Title: (.*?)\. Date: (\d{4}-\d{2}-\d{2})\. Start: (\d{2}:\d{2})\. "
        r"End: (\d{2}:\d{2})\. Location: (.*?)\. Attendees: (.*?)\. "
        r"Preserve every existing event\.",
        prompt,
        "calendar-add contract",
    )
    read_date, title, date, start, end, location, attendee_text = match.groups()
    if read_date != date:
        raise OracleInputError("calendar read and event dates disagree")
    return [
        {"type": "calendar_read", "date": date},
        {
            "type": "event_created",
            "title": title,
            "date": date,
            "start": start,
            "end": end,
            "attendees": _pipe(attendee_text),
            "location": location,
            "exact_count": 1,
        },
    ]


def _minutes(value):
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _clock(value):
    return "%02d:%02d" % divmod(value, 60)


def _cal_freeslot(prompt, state, _today):
    match = _search(
        r"Inspect calendar date (\d{4}-\d{2}-\d{2})\. Between (\d{2}:\d{2}) "
        r"and (\d{2}:\d{2}), find (\d+)-minute slots aligned to 30 minutes and "
        r"choose (earliest_free|latest_free|second_free)\. Add exactly one event "
        r"titled '(.*?)' in that slot, with no attendees and location '(.*?)'\.",
        prompt,
        "free-slot contract",
    )
    date, window_start, window_end, duration, rule, title, location = match.groups()
    duration = int(duration)
    candidates = []
    for start in range(_minutes(window_start), _minutes(window_end) - duration + 1, 30):
        end = start + duration
        overlaps = any(
            event.get("date") == date
            and _clock(start) < event.get("end", "")
            and event.get("start", "") < _clock(end)
            for event in _events(state)
        )
        if not overlaps:
            candidates.append(start)
    if not candidates or (rule == "second_free" and len(candidates) < 2):
        raise OracleInputError("free-slot rule has no valid candidate")
    selected = (
        candidates[0] if rule == "earliest_free"
        else candidates[-1] if rule == "latest_free"
        else candidates[1]
    )
    return [
        {"type": "calendar_read", "date": date},
        {
            "type": "event_created",
            "title": title,
            "date": date,
            "start": _clock(selected),
            "end": _clock(selected + duration),
            "attendees": [],
            "location": location,
            "exact_count": 1,
        },
    ]


def _cal_brief(prompt, state, _today):
    match = _search(
        r"Inspect calendar date (\d{4}-\d{2}-\d{2})\. Send exactly one chat "
        r"message to (.*?)\. Include, in chronological order, only event titles "
        r"beginning 'Priority:' and each start time\.",
        prompt,
        "calendar-brief contract",
    )
    date, recipient = match.groups()
    selected = sorted(
        (
            event for event in _events(state)
            if event.get("date") == date
            and event.get("title", "").startswith("Priority:")
        ),
        key=lambda item: (item["start"], item["title"]),
    )
    if not selected:
        raise OracleInputError("calendar brief has no priority events")
    return [
        {"type": "calendar_read", "date": date},
        {
            "type": "message_sent",
            "to": recipient,
            "ordered_mentions": [item["title"] for item in selected],
            "include_start_times": True,
            "exact_count": 1,
        },
    ]


def _remind_msg(prompt, _state, _today):
    match = _search(
        r"Create exactly one reminder\. Date: (\d{4}-\d{2}-\d{2})\. Time: "
        r"(\d{2}:\d{2})\. Required checklist mentions in order: (.*?)\. Then "
        r"send exactly one chat message to (.*?) repeating",
        prompt,
        "reminder/message contract",
    )
    date, time, mentions, recipient = match.groups()
    values = _pipe(mentions)
    return [
        {
            "type": "reminder_created",
            "date": date,
            "time": time,
            "required_mentions": values,
            "exact_count": 1,
        },
        {
            "type": "message_sent",
            "to": recipient,
            "required_mentions": values,
            "body_intent": "deadline_commitment",
            "exact_count": 1,
        },
    ]


def _preference_learning(_prompt, _state, _today, subepisode_prompts):
    if len(subepisode_prompts) != 2:
        raise OracleInputError("preference task requires two prompt subepisodes")
    store = _search(
        r"^Remember these scheduling preferences for the next request: (.*?)\.$",
        subepisode_prompts[0],
        "stored preferences",
    )
    use = _search(
        r"^Book exactly one event\. Title: (.*?)\. Date: (\d{4}-\d{2}-\d{2})\. "
        r"Start: (\d{2}:\d{2})\. Duration minutes: (\d+)\. Attendees: "
        r"(.*?)\. Location: (.*?)\. Apply the remembered preferences\.$",
        subepisode_prompts[1],
        "preference-use event",
    )
    title, date, start, duration, attendees, location = use.groups()
    end = _clock(_minutes(start) + int(duration))
    return [
        {
            "type": "memory_saved",
            "required_facts": _pipe(store.group(1)),
            "scope": "same_attempt",
        },
        {
            "type": "event_created",
            "title": title,
            "date": date,
            "start": start,
            "end": end,
            "attendees": _pipe(attendees),
            "location": location,
            "exact_count": 1,
        },
    ]


def _multi_offsite(prompt, state, _today):
    match = _search(
        r"subject '([^']+)'[\s\S]*?create ([a-z0-9_.-]+\.pptx)",
        prompt,
        "offsite source and artifact",
        re.IGNORECASE,
    )
    subject, filename = match.groups()
    matches = [email for email in _emails(state) if email["subject"] == subject]
    if len(matches) != 1:
        raise OracleInputError("offsite source subject is not unique")
    source = matches[0]
    body = _search(
        r"^FINAL OFFSITE: event=(.*?); date=(\d{4}-\d{2}-\d{2}); "
        r"start=(\d{2}:\d{2}); end=(\d{2}:\d{2}); location=(.*?); "
        r"facts=(.*?)\.$",
        source["body"],
        "offsite facts",
    )
    event, date, start, end, location, fact_text = body.groups()
    facts = _pipe(fact_text)
    return [
        {"type": "source_read", "source": "email", "id": source["id"]},
        {
            "type": "event_created",
            "title": event,
            "date": date,
            "start": start,
            "end": end,
            "location": location,
            "attendees": [],
            "exact_count": 1,
        },
        {
            "type": "email_sent",
            "to": source["from"],
            "body_intent": "confirm_attendance",
            "exact_count": 1,
        },
        {
            "type": "presentation_created",
            "filename": filename,
            "exact_slide_count": 1,
            "ordered_titles": [event],
            "required_values": facts,
        },
    ]


_DERIVERS = {
    "pptx_basic": _pptx_basic,
    "pptx_from_email": _pptx_from_email,
    "xlsx_basic": _xlsx_basic,
    "xlsx_from_email": _xlsx_from_email,
    "email_reply": _email_reply,
    "cal_add": _cal_add,
    "cal_freeslot": _cal_freeslot,
    "cal_brief": _cal_brief,
    "remind_msg": _remind_msg,
    "multi_offsite": _multi_offsite,
}


def derive_outcome(family, prompt, subepisode_prompts, initial_state, today):
    """Derive the required outcome without accepting hidden expected effects."""

    if not isinstance(family, str) or not family:
        raise OracleInputError("family must be a nonempty string")
    if prompt is not None and not isinstance(prompt, str):
        raise OracleInputError("prompt must be text or null")
    if not isinstance(subepisode_prompts, list) or not all(
        isinstance(item, str) for item in subepisode_prompts
    ):
        raise OracleInputError("subepisode prompts must be a text list")
    if not isinstance(initial_state, dict):
        raise OracleInputError("initial_state must be an object")
    try:
        datetime.date.fromisoformat(today)
    except (TypeError, ValueError) as exc:
        raise OracleInputError("today is not an ISO date") from exc
    state = copy.deepcopy(initial_state)
    if family == "preference_learning":
        if prompt is not None:
            raise OracleInputError("preference task prompt must be null")
        return _preference_learning(prompt, state, today, subepisode_prompts)
    if family not in _DERIVERS or prompt is None or subepisode_prompts:
        raise OracleInputError("family/prompt shape is unsupported")
    return _DERIVERS[family](prompt, state, today)


__all__ = [
    "ORACLE_VERSION",
    "OracleInputError",
    "derive_outcome",
]

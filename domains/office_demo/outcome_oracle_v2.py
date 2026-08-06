"""Independent prompt-to-outcome oracle for office-generators/2.1.1.

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


ORACLE_VERSION = "office-prompt-oracle/2.0.0"


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
        r"Create presentation ([a-z0-9_.-]+\.pptx) from these approved section "
        r"records: (.*?)\. Order section slides by policy "
        r"(brief_sequence|risk_descending|owner_alphabetical)\. Use exactly (\d+) "
        r"slides: one title slide named '([^']+)'",
        prompt,
        "presentation contract",
    )
    filename, record_text, policy, count_text, title = match.groups()
    records = []
    for value in _pipe(record_text):
        record = _search(
            r"^section=([^,]+),sequence=(\d+),risk=(\d+),owner=([^,]+),fact=(.+)$",
            value, "presentation section record",
        )
        records.append({
            "section": record.group(1), "sequence": int(record.group(2)),
            "risk": int(record.group(3)), "owner": record.group(4),
            "fact": record.group(5),
        })
    if policy == "brief_sequence":
        records.sort(key=lambda item: item["sequence"])
    elif policy == "risk_descending":
        records.sort(key=lambda item: (-item["risk"], item["section"]))
    else:
        records.sort(key=lambda item: (item["owner"], item["section"]))
    count = int(count_text)
    if count != len(records) + 1:
        raise OracleInputError("presentation counts disagree")
    return [{
        "type": "presentation_created",
        "filename": filename,
        "exact_slide_count": count,
        "ordered_titles": [title] + [item["section"] for item in records],
        "minimum_bullets_by_slide": [0] + [1] * len(records),
        "required_values_by_slide": [[]] + [[item["fact"]] for item in records],
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
    policy = _search(
        r"ordered by policy (sequence_ascending|revenue_descending|region_alphabetical)\.",
        prompt, "approved-region ordering policy",
    ).group(1)
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
    if sorted(item[0] for item in rows) != list(range(1, len(rows) + 1)):
        raise OracleInputError("approved-region sequence is not contiguous")
    if policy == "sequence_ascending":
        rows.sort(key=lambda item: item[0])
    elif policy == "revenue_descending":
        rows.sort(key=lambda item: (-item[3], item[2]))
    else:
        rows.sort(key=lambda item: item[2])
    return [
        {"type": "sources_read", "source": "email", "ids": sorted(item[1] for item in rows),
         "list_required": True},
        {
            "type": "presentation_created",
            "filename": filename,
            "exact_slide_count": len(rows) + 1,
            "ordered_titles": [title] + [item[2] for item in rows],
            "required_values": [item[3] for item in rows],
            "required_values_by_slide": [[]] + [[item[3]] for item in rows],
        },
    ]


def _xlsx_basic(prompt, _state, _today):
    match = _search(
        r"Create spreadsheet ([a-z0-9_.-]+\.xlsx)\. Headers: ([^.]+)\. "
        r"Approved rows: (.*?)\. Row order rule: "
        r"(source_order|cost_descending|item_alphabetical)\.",
        prompt,
        "spreadsheet contract",
    )
    filename, header_text, row_text, rule = match.groups()
    headers = _pipe(header_text)
    rows = []
    for record in _pipe(row_text):
        row = _search(
            r"^Owner=([^,]+),Item=([^,]+),Cost=(\d+)$", record, "approved row"
        )
        rows.append([row.group(1), row.group(2), int(row.group(3))])
    if rule == "cost_descending":
        rows.sort(key=lambda item: (-item[2], item[1]))
    elif rule == "item_alphabetical":
        rows.sort(key=lambda item: item[1])
    return [{
        "type": "spreadsheet_created",
        "filename": filename,
        "headers": headers,
        "ordered_rows": rows,
        "total_cents": sum(item[2] for item in rows) * 100,
        "formula_required": True,
    }]


def _xlsx_from_email(prompt, state, _today):
    match = _search(
        r"subject begins '([^']+)'[\s\S]*?create ([a-z0-9_.-]+\.xlsx) with "
        r"headers ([^.]+)\.[\s\S]*?Row order rule: "
        r"(date_ascending|amount_descending|vendor_alphabetical)\.",
        prompt,
        "receipt source and spreadsheet",
        re.IGNORECASE,
    )
    prefix, filename, header_text, rule = match.groups()
    matches = [email for email in _emails(state) if email["subject"].startswith(prefix)]
    if not matches:
        raise OracleInputError("receipt sources are missing")
    rows = []
    for source in matches:
        row = _search(
            r"^PAID RECEIPT: date=(\d{4}-\d{2}-\d{2}),vendor=([^,]+),"
            r"amount_cents=(\d+)\. STATUS: FINAL\.$",
            source["body"],
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
        {"type": "sources_read", "source": "email", "ids": sorted(
            source["id"] for source in matches
        ), "list_required": True},
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
        r"subject prefix '([^']+)'\. Select exactly one request using policy "
        r"(latest_request|highest_priority|decision_key_match)\.[\s\S]*?"
        r"Subject must contain '([^']+)'",
        prompt,
        "reply source prefix",
        re.IGNORECASE,
    )
    prefix, policy, subject_contains = match.groups()
    sources = [email for email in _emails(state) if email["subject"].startswith(prefix)]
    decisions = [email for email in sources if email["body"].startswith("DECISION:")]
    requests = [
        email for email in sources
        if email["body"].startswith("ATTENDANCE REQUEST:")
    ]
    if len(decisions) != 1 or len(requests) != 3 or len(sources) != 4:
        raise OracleInputError("reply sources are not one decision plus three requests")
    decision = _search(
        r"selection_key=([^;]+); confirmation_code=([^;]+); confirmation_date=(\d{4}-\d{2}-\d{2})\.",
        decisions[0]["body"], "reply decision",
    )
    decision_key, confirmation_code, confirmation_date = decision.groups()
    parsed = []
    for request in requests:
        fields = _search(
            r"priority=(\d+); decision_key=([^;]+); request_id=([^.;]+)\.",
            request["body"], "attendance request",
        )
        parsed.append({
            "email": request, "priority": int(fields.group(1)),
            "key": fields.group(2), "request_id": fields.group(3),
        })
    if policy == "latest_request":
        selected = max(parsed, key=lambda item: item["email"]["date"])
    elif policy == "highest_priority":
        selected = max(parsed, key=lambda item: item["priority"])
    else:
        matches = [item for item in parsed if item["key"] == decision_key]
        if len(matches) != 1:
            raise OracleInputError("decision-key policy is not unique")
        selected = matches[0]
    return [
        {"type": "sources_read", "source": "email", "ids": [
            decisions[0]["id"]
        ] + sorted(item["email"]["id"] for item in parsed), "list_required": True},
        {
            "type": "email_sent",
            "to": selected["email"]["from"],
            "subject_contains": subject_contains,
            "body_intent": "confirm_attendance",
            "required_mentions": [
                confirmation_code, confirmation_date, selected["request_id"],
            ],
            "exact_count": 1,
        },
    ]


def _cal_add(prompt, state, _today):
    match = _search(
        r"Inspect calendar date (\d{4}-\d{2}-\d{2})\. Candidate requests: (.*?)\. "
        r"Select one feasible request using policy "
        r"(earliest_feasible|highest_priority_feasible|shortest_duration_feasible) "
        r"and add exactly one event[\s\S]*?attendees: (.*?)\. Preserve every existing event\.",
        prompt,
        "calendar-add contract",
    )
    date, candidate_text, policy, attendee_text = match.groups()
    candidates = []
    for value in _pipe(candidate_text):
        record = _search(
            r"^id=([^,]+),title=(.*?),start=(\d{2}:\d{2}),duration=(\d+),"
            r"priority=(\d+),location=(.*)$",
            value, "calendar candidate",
        )
        candidates.append({
            "id": record.group(1), "title": record.group(2),
            "start": _minutes(record.group(3)), "duration": int(record.group(4)),
            "priority": int(record.group(5)), "location": record.group(6),
        })
    available = []
    for candidate in candidates:
        end = candidate["start"] + candidate["duration"]
        if not any(
            event.get("date") == date
            and candidate["start"] < _minutes(event["end"])
            and _minutes(event["start"]) < end
            for event in _events(state)
        ):
            available.append(candidate)
    if not available:
        raise OracleInputError("calendar-add has no feasible candidate")
    if policy == "earliest_feasible":
        selected = min(available, key=lambda item: item["start"])
    elif policy == "highest_priority_feasible":
        selected = max(available, key=lambda item: (item["priority"], -item["start"]))
    else:
        selected = min(available, key=lambda item: (item["duration"], item["start"]))
    return [
        {"type": "calendar_read", "date": date},
        {
            "type": "event_created",
            "title": selected["title"],
            "date": date,
            "start": _clock(selected["start"]),
            "end": _clock(selected["start"] + selected["duration"]),
            "attendees": _pipe(attendee_text),
            "location": selected["location"],
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
        r"choose (earliest_free|latest_free|closest_to_preferred); the preferred "
        r"start is (\d{2}:\d{2})\. Add exactly one event "
        r"titled '(.*?)' in that slot, with no attendees and location '(.*?)'\.",
        prompt,
        "free-slot contract",
    )
    date, window_start, window_end, duration, rule, preferred, title, location = match.groups()
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
    if not candidates:
        raise OracleInputError("free-slot rule has no valid candidate")
    selected = (
        candidates[0] if rule == "earliest_free"
        else candidates[-1] if rule == "latest_free"
        else min(candidates, key=lambda value: (abs(value - _minutes(preferred)), value))
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
        r"message to (.*?)\. Include, in policy "
        r"(chronological|severity_descending|owner_alphabetical) order, only event titles "
        r"beginning 'Priority:' and each start time\.[\s\S]*?Then send exactly "
        r"one separate chat message to (.*?) containing '(\d{4}-\d{2}-\d{2})' "
        r"and 'priority-count=(\d+)'\.",
        prompt,
        "calendar-brief contract",
    )
    date, recipient, policy, auditor, repeated_date, declared_count = match.groups()
    if repeated_date != date:
        raise OracleInputError("calendar brief audit date disagrees")
    selected = [
        event for event in _events(state)
        if event.get("date") == date
        and event.get("title", "").startswith("Priority:")
    ]
    if policy == "chronological":
        selected.sort(key=lambda item: (item["start"], item["title"]))
    elif policy == "severity_descending":
        selected.sort(key=lambda item: (-item["severity"], item["start"]))
    else:
        selected.sort(key=lambda item: (item["owner"], item["start"]))
    if not selected:
        raise OracleInputError("calendar brief has no priority events")
    if int(declared_count) != len(selected):
        raise OracleInputError("calendar brief priority count disagrees")
    excluded_titles = sorted(
        event["title"] for event in _events(state)
        if event.get("date") == date and event not in selected
    )
    return [
        {"type": "calendar_read", "date": date},
        {
            "type": "message_sent",
            "to": recipient,
            "ordered_mentions": [
                "%s at %s" % (item["title"], item["start"]) for item in selected
            ],
            "forbidden_mentions": excluded_titles,
            "forbid_date_tokens": True,
            "exact_count": 1,
        },
        {
            "type": "message_sent",
            "to": auditor,
            "required_mentions": [date, "priority-count=%d" % len(selected)],
            "exact_count": 1,
        },
    ]


def _remind_msg(prompt, _state, _today):
    match = _search(
        r"Action items: (.*?)\. Order them using policy "
        r"(due_date_ascending|priority_descending|dependency_order)\. Create exactly "
        r"one reminder at (\d{2}:\d{2}) on the first ordered item's due date\. "
        r"Use the resulting full ordered ID list as the reminder checklist\. Then send "
        r"exactly one chat message to (.*?) repeating",
        prompt,
        "reminder/message contract",
    )
    record_text, policy, time, recipient = match.groups()
    records = []
    for value in _pipe(record_text):
        item = _search(
            r"^id=([^,]+),due=(\d{4}-\d{2}-\d{2}),priority=(\d+),depends_on=(.+)$",
            value, "action item",
        )
        records.append({
            "id": item.group(1), "due": item.group(2),
            "priority": int(item.group(3)), "depends_on": item.group(4),
        })
    if policy == "due_date_ascending":
        records.sort(key=lambda item: (item["due"], item["id"]))
    elif policy == "priority_descending":
        records.sort(key=lambda item: (-item["priority"], item["id"]))
    else:
        ordered, remaining = [], {item["id"]: item for item in records}
        while remaining:
            eligible = [
                item for item in remaining.values()
                if item["depends_on"] == "none"
                or item["depends_on"] in {value["id"] for value in ordered}
            ]
            if len(eligible) != 1:
                raise OracleInputError("dependency order is not unique")
            selected = eligible[0]
            ordered.append(selected)
            remaining.pop(selected["id"])
        records = ordered
    values = [item["id"] for item in records]
    date = records[0]["due"]
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
        r"^For subject ([^,]+), evaluate these preference bundles: (.*?)\. Select by "
        r"policy (most_recent|highest_priority|most_specific_scope) and save exactly "
        r"one memory containing only the selected bundle's applicable facts: (.*?)\.$",
        subepisode_prompts[0],
        "stored preferences",
    )
    use = _search(
        r"^Schedule exactly one sync with (.*?) on (\d{4}-\d{2}-\d{2})\. The attendee "
        r"is (.*?)\. Retrieve and apply the selected same-attempt preference bundle",
        subepisode_prompts[1],
        "preference-use event",
    )
    subject, bundle_text, policy, fact_text = store.groups()
    bundles = []
    for value in _pipe(bundle_text):
        item = _search(
            r"^id=([^,]+),timestamp_rank=(\d+),priority=(\d+),scope_specificity=(\d+),"
            r"duration_minutes=(\d+),earliest_start=(\d{2}:\d{2}),location=([^,]+),"
            r"title_prefix=(.+)$",
            value, "preference bundle",
        )
        bundles.append({
            "id": item.group(1), "timestamp": int(item.group(2)),
            "priority": int(item.group(3)), "scope": int(item.group(4)),
            "duration": int(item.group(5)), "start": item.group(6),
            "location": item.group(7), "prefix": item.group(8),
        })
    if policy == "most_recent":
        selected = max(bundles, key=lambda item: item["timestamp"])
    elif policy == "highest_priority":
        selected = max(bundles, key=lambda item: item["priority"])
    else:
        selected = max(bundles, key=lambda item: item["scope"])
    facts = _pipe(fact_text)
    fact_map = dict(value.split("=", 1) for value in facts)
    if (
        fact_map.get("subject") != subject
        or int(fact_map.get("duration_minutes", -1)) != selected["duration"]
        or fact_map.get("earliest_start") != selected["start"]
        or fact_map.get("location") != selected["location"]
    ):
        raise OracleInputError("selected preference facts disagree with policy")
    person, date, attendee = use.groups()
    if attendee != subject:
        raise OracleInputError("preference subject and use attendee disagree")
    prefix = fact_map.get("title_prefix")
    if not prefix:
        raise OracleInputError("selected preference title prefix is not public")
    title = "%s sync with %s" % (prefix, person)
    start = selected["start"]
    end = _clock(_minutes(start) + selected["duration"])
    return [
        {
            "type": "memory_saved",
            "required_facts": facts,
            "scope": "same_attempt",
        },
        {
            "type": "event_created",
            "title": title,
            "date": date,
            "start": start,
            "end": end,
            "attendees": [attendee],
            "location": selected["location"],
            "exact_count": 1,
        },
    ]


def _multi_offsite(prompt, state, _today):
    match = _search(
        r"subject '([^']+)'\. Select one detail source using policy "
        r"(latest_issued|highest_approval_rank|consensus_supported),[\s\S]*?"
        r"create ([a-z0-9_.-]+\.pptx)",
        prompt,
        "offsite source and artifact",
        re.IGNORECASE,
    )
    subject, policy, filename = match.groups()
    indices = [email for email in _emails(state) if email["subject"] == subject]
    if len(indices) != 1:
        raise OracleInputError("offsite index subject is not unique")
    index_email = indices[0]
    index_match = _search(r"^CANDIDATES: (.*?)\.$", index_email["body"], "offsite index")
    candidates = []
    for value in _pipe(index_match.group(1)):
        item = _search(
            r"^id=([^,]+),issued_rank=(\d+),approval_rank=(\d+),consensus=(\d+)$",
            value, "offsite candidate",
        )
        candidates.append({
            "id": item.group(1), "issued": int(item.group(2)),
            "approval": int(item.group(3)), "consensus": int(item.group(4)),
        })
    if policy == "latest_issued":
        selected = max(candidates, key=lambda item: item["issued"])
    elif policy == "highest_approval_rank":
        selected = max(candidates, key=lambda item: item["approval"])
    else:
        selected = max(candidates, key=lambda item: item["consensus"])
    details = [email for email in _emails(state) if email["id"] == selected["id"]]
    if len(details) != 1:
        raise OracleInputError("selected offsite detail is missing")
    source = details[0]
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
        {"type": "sources_read", "source": "email", "ids": [index_email["id"], source["id"]],
         "list_required": True},
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
            "required_values_by_slide": [facts],
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

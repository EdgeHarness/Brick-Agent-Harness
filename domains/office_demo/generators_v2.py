"""Fresh successor generators for the eleven synthetic office families.

Version 2.0.0 uses a new seed/entity namespace, a six-way split allocation,
48 genuine semantic shapes per family, explicit difficulty/action axes, and an
independent prompt-to-outcome oracle check on every generated instance.
"""

import datetime
import hashlib
import random

from harness.instances import (
    envelope_instance,
    make_manifest,
    structure_sha256,
    validate_instance,
)

from .generators import FAMILIES, validate_office_instance
from .outcome_oracle_v2 import derive_outcome


SUITE = "office-synthetic-v2"
GENERATOR_VERSION = "office-generators/2.0.0"
SEED_NAMESPACE = "office-generators/2.0.0"
FAMILY_VERSION = "2.0.0"
NEXT_SPLITS = (
    "development",
    "calibration",
    "validation",
    "sentinel",
    "retained",
    "adversarial",
)

# This is a balanced partition of the complete 4 x 4 x 3 factorial below.
# Every development/calibration split has two of each workload and distractor
# level.  Every four-case split has one of each.  The 20-case retained split
# has five of each.  Constraint profiles are as even as integer counts allow.
SPLIT_ORDINALS = {
    "development": (4, 14, 15, 17, 25, 26, 32, 39),
    "calibration": (0, 2, 5, 20, 30, 41, 43, 47),
    "validation": (3, 8, 21, 46),
    "sentinel": (10, 19, 29, 36),
    "retained": (
        1, 6, 9, 11, 12, 13, 16, 18, 22, 23,
        24, 27, 31, 34, 35, 37, 38, 40, 44, 45,
    ),
    "adversarial": (7, 28, 33, 42),
}
SPLIT_SIZES = {split: len(SPLIT_ORDINALS[split]) for split in NEXT_SPLITS}

_CONSTRAINT_PROFILES = ("listed", "ranked", "cross_check")
_SPLIT_STEMS = {
    "development": "Devora",
    "calibration": "Calvera",
    "validation": "Valnora",
    "sentinel": "Sentryn",
    "retained": "Retnora",
    "adversarial": "Adverra",
}
_GIVEN = (
    "Amal", "Bryn", "Cato", "Demi", "Esra", "Fint", "Gaia", "Hale",
    "Iris", "Jori", "Kavi", "Lumi", "Mara", "Niko", "Orla", "Perrin",
)
_SECTIONS = ("Context", "Evidence", "Options", "Decision", "Owners", "Next Steps")
_REGIONS = ("North", "South", "Central", "Online", "Partner", "Public")
_ITEMS = ("Equipment", "Licenses", "Training", "Travel", "Research", "Facilities")

FORBIDDEN_EFFECTS = [
    "extra_artifact",
    "extra_mutation",
    "preexisting_state_changed",
    "source_not_read",
    "unauthorized_external_effect",
]


def _seed(split, family, index, ordinal):
    payload = "%s|%s|%s|%d|%d" % (
        SEED_NAMESPACE, split, family, index, ordinal,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def _axes(ordinal):
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 0 <= ordinal < 48:
        raise ValueError("v2 ordinal must be in [0, 48)")
    return {
        "workload": 3 + ordinal % 4,
        "distractor_count": (ordinal // 4) % 4,
        "constraint_profile": _CONSTRAINT_PROFILES[ordinal // 16],
    }


def _base_state():
    return {
        "emails": [],
        "events": [],
        "sent_emails": [],
        "messages": [],
        "reminders": [],
        "memory": [],
        "artifacts": [],
    }


def _difficulty(
    discovery, reads, mutations, artifact_size, source_items, branches,
    subepisodes=1,
):
    return {
        "minimum_discovery_calls": discovery,
        "minimum_source_reads": reads,
        "minimum_mutating_calls": mutations,
        "artifact_rows_or_slides": artifact_size,
        "source_items": source_items,
        "constraint_branches": branches,
        "subepisodes": subepisodes,
    }


class _Context:
    def __init__(self, split, family, index, ordinal, seed):
        self.split = split
        self.family = family
        self.index = index
        self.ordinal = ordinal
        self.seed = seed
        self.random = random.Random(seed)
        self.entities = {}
        self.axes = _axes(ordinal)
        # The complete factorial uses Monday anchors so "next Tuesday" and
        # weekly surface variation remain deterministic and unambiguous.
        self.today = datetime.date(2028, 1, 3) + datetime.timedelta(days=ordinal * 7)

    @property
    def branch_count(self):
        return _CONSTRAINT_PROFILES.index(self.axes["constraint_profile"]) + 1

    def entity(self, role, number=0, kind="person"):
        key = "v2.%s.%s.%02d.%s.%d" % (
            self.split,
            self.family.replace("_", "-"),
            self.index,
            role.replace("_", "-"),
            number,
        )
        token = "%s%s%02d%02d" % (
            _SPLIT_STEMS[self.split],
            self.family.replace("_", " ").title().replace(" ", ""),
            self.index,
            number,
        )
        if kind == "person":
            given = _GIVEN[(self.seed + number * 5 + len(role)) % len(_GIVEN)]
            record = {
                "name": "%s %s" % (given, token),
                "email": "%s.%s@v2-%s.example" % (
                    given.lower(), token.lower(), self.split,
                ),
            }
        elif kind == "location":
            record = {"name": "%s Collaboration Hall" % token}
        elif kind == "project":
            record = {"name": "Initiative %s" % token}
        elif kind == "vendor":
            record = {
                "name": "%s Supply Group" % token,
                "email": "receipts@%s.v2-%s.example" % (
                    token.lower(), self.split,
                ),
            }
        else:
            raise ValueError("unknown v2 entity kind %r" % kind)
        self.entities[key] = record
        return record

    def date(self, days):
        return (self.today + datetime.timedelta(days=days)).isoformat()


def _email(identifier, sender, date, subject, body):
    return {
        "id": identifier,
        "from": sender,
        "date": date,
        "subject": subject,
        "body": body,
    }


def _event(identifier, title, date, start, end, location="", attendees=None):
    return {
        "id": identifier,
        "title": title,
        "date": date,
        "start": start,
        "end": end,
        "location": location,
        "attendees": list(attendees or []),
    }


def _clock(minutes):
    return "%02d:%02d" % divmod(minutes, 60)


def _pptx_basic(ctx):
    project = ctx.entity("project", kind="project")["name"]
    sections = list(_SECTIONS[:ctx.axes["workload"]])
    titles = [project + " Review"] + sections
    minimum = ctx.branch_count + 1
    minimums = [0] + [minimum] * len(sections)
    filename = "v2_%s_%02d_review.pptx" % (ctx.split[:3], ctx.index)
    prompt = (
        "Create presentation %s. Use exactly %d slides. Titles in order: %s. "
        "Minimum bullets by slide: %s. Do not create any other artifact."
        % (
            filename, len(titles), " | ".join(titles),
            " | ".join(str(value) for value in minimums),
        )
    )
    effects = [{
        "type": "presentation_created",
        "filename": filename,
        "exact_slide_count": len(titles),
        "ordered_titles": titles,
        "minimum_bullets_by_slide": minimums,
    }]
    return prompt, [], _base_state(), effects, _difficulty(
        0, 0, 1, len(titles), 0, ctx.branch_count,
    )


def _pptx_from_email(ctx):
    project = ctx.entity("project", kind="project")["name"]
    sender = ctx.entity("analyst")
    count = ctx.axes["workload"]
    prefix = "APPROVED REGION %s /" % project
    state = _base_state()
    source_ids = []
    titles = [project + " Revenue Review"]
    values = []
    for index, region in enumerate(_REGIONS[:count]):
        identifier = "approved-region-%d" % (index + 1)
        revenue_cents = 12_500_000 + 173_000 * (ctx.ordinal + index)
        source_ids.append(identifier)
        titles.append(region)
        values.append(revenue_cents)
        state["emails"].append(_email(
            identifier,
            sender["email"],
            ctx.date(-count + index) + " 09:00",
            "%s %02d" % (prefix, index + 1),
            "Region: %s; Revenue cents: %d; Sequence: %d; Status: FINAL."
            % (region, revenue_cents, index + 1),
        ))
    for index in range(ctx.axes["distractor_count"]):
        state["emails"].append(_email(
            "draft-region-%d" % index,
            sender["email"],
            ctx.date(-20 - index),
            "DRAFT REGION %s / %02d" % (project, index + 1),
            "Preliminary figures. Status: SUPERSEDED.",
        ))
    filename = "v2_%s_%02d_regions.pptx" % (ctx.split[:3], ctx.index)
    prompt = (
        "List the inbox and read every email whose subject begins '%s'. Then create %s "
        "with title slide '%s', followed by one slide per approved email in Sequence "
        "order. Use Region as each slide title and include the exact Revenue cents "
        "value. Ignore DRAFT REGION messages."
        % (prefix, filename, titles[0])
    )
    effects = [
        {"type": "sources_read", "source": "email", "ids": source_ids},
        {
            "type": "presentation_created",
            "filename": filename,
            "exact_slide_count": count + 1,
            "ordered_titles": titles,
            "required_values": values,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, count, 1, count + 1, count, ctx.branch_count,
    )


def _xlsx_basic(ctx):
    owner = ctx.entity("owner")
    rows = [
        [name, 800 + (ctx.ordinal + index + 1) * 125]
        for index, name in enumerate(_ITEMS[:ctx.axes["workload"]])
    ]
    rule = {
        "listed": "listed",
        "ranked": "descending_cost",
        "cross_check": "alphabetical",
    }[ctx.axes["constraint_profile"]]
    selected = [list(row) for row in rows]
    if rule == "descending_cost":
        selected.sort(key=lambda item: (-item[1], item[0]))
    elif rule == "alphabetical":
        selected.sort(key=lambda item: item[0])
    filename = "v2_%s_%02d_budget.xlsx" % (ctx.split[:3], ctx.index)
    prompt = (
        "Create spreadsheet %s. Headers: Item | Cost. Approved rows: %s. Row order "
        "rule: %s. Add exactly one final Total row using a formula. The sheet is for %s."
        % (
            filename,
            " | ".join("Item=%s,Cost=%d" % tuple(row) for row in rows),
            rule,
            owner["name"],
        )
    )
    effects = [{
        "type": "spreadsheet_created",
        "filename": filename,
        "headers": ["Item", "Cost"],
        "ordered_rows": selected,
        "total_cents": sum(item[1] for item in selected) * 100,
        "formula_required": True,
    }]
    return prompt, [], _base_state(), effects, _difficulty(
        0, 0, 1, len(rows) + 2, 0, ctx.branch_count,
    )


def _xlsx_from_email(ctx):
    accountant = ctx.entity("accountant")
    rows = []
    for index in range(ctx.axes["workload"]):
        vendor = ctx.entity("vendor", index, "vendor")
        rows.append([
            ctx.date(-ctx.axes["workload"] + index),
            vendor["name"],
            4_500 + (ctx.ordinal + index * 2) * 137,
        ])
    subject = "FINAL PAID RECEIPTS %s %02d" % (ctx.split.upper(), ctx.index)
    source_id = "paid-receipts-final"
    state = _base_state()
    state["emails"].append(_email(
        source_id,
        accountant["email"],
        ctx.date(-1) + " 16:00",
        subject,
        "PAID RECEIPTS: %s. STATUS: FINAL."
        % " | ".join(
            "date=%s,vendor=%s,amount_cents=%d" % tuple(row) for row in rows
        ),
    ))
    for index in range(ctx.axes["distractor_count"]):
        state["emails"].append(_email(
            "receipt-draft-%d" % index,
            accountant["email"],
            ctx.date(-10 - index),
            "DRAFT RECEIPTS %02d" % index,
            "Quote or duplicate; not a paid final receipt.",
        ))
    rule = {
        "listed": "date_ascending",
        "ranked": "amount_descending",
        "cross_check": "vendor_alphabetical",
    }[ctx.axes["constraint_profile"]]
    selected = [list(row) for row in rows]
    if rule == "date_ascending":
        selected.sort(key=lambda item: (item[0], item[1]))
    elif rule == "amount_descending":
        selected.sort(key=lambda item: (-item[2], item[0]))
    else:
        selected.sort(key=lambda item: (item[1], item[0]))
    filename = "v2_%s_%02d_expenses.xlsx" % (ctx.split[:3], ctx.index)
    prompt = (
        "List the inbox and read the single email with subject '%s'. Then create %s "
        "with headers Date | Vendor | Amount. Include one row per paid receipt. Row "
        "order rule: %s. Add one final Total row using a formula. Ignore drafts and quotes."
        % (subject, filename, rule)
    )
    effects = [
        {"type": "source_read", "source": "email", "id": source_id},
        {
            "type": "spreadsheet_created",
            "filename": filename,
            "headers": ["Date", "Vendor", "Amount"],
            "ordered_rows_cents": selected,
            "total_cents": sum(item[2] for item in selected),
            "formula_required": True,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 1, 1, len(rows) + 2, len(rows), ctx.branch_count,
    )


def _email_reply(ctx):
    correspondent = ctx.entity("correspondent")
    project = ctx.entity("project", kind="project")["name"]
    prefix = "%s / REQUIRED /" % project
    state = _base_state()
    state["emails"].extend([
        _email(
            "required-decision",
            correspondent["email"],
            ctx.date(-2) + " 10:00",
            prefix + "DECISION",
            "DECISION: kickoff date %s; attendance confirmation is required."
            % ctx.date(5),
        ),
        _email(
            "required-attendance",
            correspondent["email"],
            ctx.date(-1) + " 10:00",
            prefix + "ATTENDANCE",
            "ATTENDANCE REQUEST: Reply confirming you will attend.",
        ),
    ])
    for index in range(ctx.axes["distractor_count"]):
        other = ctx.entity("other_sender", index)
        state["emails"].append(_email(
            "unrelated-%d" % index,
            other["email"],
            ctx.date(-1),
            "%s FYI %02d" % (project, index),
            "Informational mention; no attendance request.",
        ))
    prompt = (
        "List the inbox; read both emails with subject prefix '%s'; then reply exactly "
        "once to the attendance-request sender. Subject must contain '%s'. Body must "
        "clearly confirm attendance. Do not reply to any other sender."
        % (prefix, project)
    )
    effects = [
        {
            "type": "sources_read",
            "source": "email",
            "ids": ["required-decision", "required-attendance"],
        },
        {
            "type": "email_sent",
            "to": correspondent["email"],
            "subject_contains": project,
            "body_intent": "confirm_attendance",
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 2, 1, 0, 2, ctx.branch_count,
    )


def _cal_add(ctx):
    requester = ctx.entity("requester")
    attendees = [
        ctx.entity("attendee", index) for index in range(ctx.axes["workload"])
    ]
    location = ctx.entity("location", kind="location")["name"]
    state = _base_state()
    date = ctx.date(4)
    start_minutes = 13 * 60 + ctx.branch_count * 30
    duration = (30, 45, 60)[ctx.branch_count - 1]
    for index in range(ctx.axes["distractor_count"]):
        before = start_minutes - (index + 1) * 30
        state["events"].append(_event(
            "adjacent-%d" % index,
            "Existing block %d" % (index + 1),
            date,
            _clock(before),
            _clock(before + 30),
        ))
    title = "%s design review" % requester["name"]
    start, end = _clock(start_minutes), _clock(start_minutes + duration)
    attendee_text = " | ".join(item["email"] for item in attendees)
    prompt = (
        "Inspect calendar date %s. Add exactly one event. Title: %s. Date: %s. "
        "Start: %s. End: %s. Location: %s. Attendees: %s. Preserve every existing event."
        % (date, title, date, start, end, location, attendee_text)
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {
            "type": "event_created",
            "title": title,
            "date": date,
            "start": start,
            "end": end,
            "attendees": [item["email"] for item in attendees],
            "location": location,
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 0, 1, 0, len(state["events"]), ctx.branch_count,
    )


def _cal_freeslot(ctx):
    owner = ctx.entity("owner")
    date = ctx.date(5)
    state = _base_state()
    for index in range(ctx.axes["workload"]):
        start = 9 * 60 + index * 60
        state["events"].append(_event(
            "busy-%d" % index,
            "Busy block %d" % (index + 1),
            date,
            _clock(start),
            _clock(start + 30),
        ))
    for index in range(ctx.axes["distractor_count"]):
        state["events"].append(_event(
            "other-day-%d" % index,
            "Other date %d" % (index + 1),
            ctx.date(6 + index),
            "10:00",
            "11:00",
        ))
    rule = {
        "listed": "earliest_free",
        "ranked": "latest_free",
        "cross_check": "second_free",
    }[ctx.axes["constraint_profile"]]
    title = "%s focus block" % owner["name"]
    location = "Focus room"
    prompt = (
        "Inspect calendar date %s. Between 09:00 and 17:00, find 30-minute slots "
        "aligned to 30 minutes and choose %s. Add exactly one event titled '%s' in "
        "that slot, with no attendees and location '%s'. Ignore other dates."
        % (date, rule, title, location)
    )
    occupied = {
        minute
        for event in state["events"]
        if event["date"] == date
        for minute in range(
            int(event["start"][:2]) * 60 + int(event["start"][3:]),
            int(event["end"][:2]) * 60 + int(event["end"][3:]),
        )
    }
    free = [
        start for start in range(9 * 60, 17 * 60 - 30 + 1, 30)
        if not any(minute in occupied for minute in range(start, start + 30))
    ]
    selected = (
        free[0] if rule == "earliest_free"
        else free[-1] if rule == "latest_free"
        else free[1]
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {
            "type": "event_created",
            "title": title,
            "date": date,
            "start": _clock(selected),
            "end": _clock(selected + 30),
            "attendees": [],
            "location": location,
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 0, 1, 0, ctx.axes["workload"], ctx.branch_count,
    )


def _cal_brief(ctx):
    recipient = ctx.entity("recipient")
    date = ctx.date(3)
    state = _base_state()
    ordered = []
    for index in range(ctx.axes["workload"]):
        start = 9 * 60 + index * 60
        title = "Priority: session %d" % (index + 1)
        ordered.append(title)
        state["events"].append(_event(
            "priority-%d" % index,
            title,
            date,
            _clock(start),
            _clock(start + 30),
        ))
    for index in range(ctx.axes["distractor_count"]):
        other_date = date if index % 2 == 0 else ctx.date(4 + index)
        state["events"].append(_event(
            "nonpriority-%d" % index,
            "Routine: unrelated %d" % (index + 1),
            other_date,
            "11:30",
            "12:00",
        ))
    prompt = (
        "Inspect calendar date %s. Send exactly one chat message to %s. Include, in "
        "chronological order, only event titles beginning 'Priority:' and each start "
        "time. Exclude every other title and date."
        % (date, recipient["name"])
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {
            "type": "message_sent",
            "to": recipient["name"],
            "ordered_mentions": ordered,
            "include_start_times": True,
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 0, 1, 0, len(state["events"]), ctx.branch_count,
    )


def _remind_msg(ctx):
    recipient = ctx.entity("recipient")
    checklist = [
        "checkpoint-%d" % (index + 1)
        for index in range(ctx.axes["workload"])
    ]
    state = _base_state()
    for index in range(ctx.axes["distractor_count"]):
        state["reminders"].append({
            "text": "Existing reminder %d" % (index + 1),
            "date": ctx.date(1 + index),
            "time": "08:00",
        })
    date = ctx.date(7)
    time = ("14:00", "15:30", "16:30")[ctx.branch_count - 1]
    prompt = (
        "Create exactly one reminder. Date: %s. Time: %s. Required checklist mentions "
        "in order: %s. Then send exactly one chat message to %s repeating those mentions "
        "in order and committing that the full checklist will be complete by the "
        "deadline. Preserve all reminders."
        % (date, time, " | ".join(checklist), recipient["name"])
    )
    effects = [
        {
            "type": "reminder_created",
            "date": date,
            "time": time,
            "required_mentions": checklist,
            "exact_count": 1,
        },
        {
            "type": "message_sent",
            "to": recipient["name"],
            "required_mentions": checklist,
            "body_intent": "deadline_commitment",
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        0, 0, 2, 0, len(checklist), ctx.branch_count,
    )


def _preference_learning(ctx):
    colleague = ctx.entity("colleague")
    duration = (20, 25, 30)[ctx.branch_count - 1]
    earliest = 10 + ctx.ordinal % 3
    all_facts = [
        "duration_minutes=%d" % duration,
        "earliest_start=%02d:00" % earliest,
        "location=Video",
        "weekday=Tuesday",
        "title_prefix=Focus:",
        "sole_attendee=%s" % colleague["email"],
    ]
    facts = all_facts[:ctx.axes["workload"]]
    state = _base_state()
    state["memory"] = [
        "Expired preference %d: ignore" % (index + 1)
        for index in range(ctx.axes["distractor_count"])
    ]
    date = ctx.date(1)
    start = "%02d:00" % earliest
    title = "Focus: sync with %s" % colleague["name"]
    store_effect = {
        "type": "memory_saved",
        "required_facts": facts,
        "scope": "same_attempt",
    }
    use_effect = {
        "type": "event_created",
        "title": title,
        "date": date,
        "start": start,
        "end": _clock(earliest * 60 + duration),
        "attendees": [colleague["email"]],
        "location": "Video",
        "exact_count": 1,
    }
    episodes = [
        {
            "id": "store",
            "prompt": "Remember these scheduling preferences for the next request: %s."
            % " | ".join(facts),
            "required_effects": [store_effect],
        },
        {
            "id": "use",
            "prompt": (
                "Book exactly one event. Title: %s. Date: %s. Start: %s. Duration "
                "minutes: %d. Attendees: %s. Location: Video. Apply the remembered "
                "preferences."
                % (title, date, start, duration, colleague["email"])
            ),
            "required_effects": [use_effect],
        },
    ]
    return None, episodes, state, [store_effect, use_effect], _difficulty(
        0, 0, 2, 0, len(facts), ctx.branch_count, subepisodes=2,
    )


def _multi_offsite(ctx):
    sender = ctx.entity("sender")
    project = ctx.entity("event", kind="project")["name"]
    event = project + " Summit"
    location = ctx.entity("location", kind="location")["name"]
    facts = [
        ctx.date(10), "09:00-15:30", location, "business casual",
        "bring identification", "lunch provided",
    ][:ctx.axes["workload"]]
    date = ctx.date(10)
    subject = "FINAL OFFSITE %s" % event
    source_id = "offsite-final"
    state = _base_state()
    state["emails"].append(_email(
        source_id,
        sender["email"],
        ctx.date(-1),
        subject,
        "FINAL OFFSITE: event=%s; date=%s; start=09:00; end=15:30; "
        "location=%s; facts=%s."
        % (event, date, location, " | ".join(facts)),
    ))
    for index in range(ctx.axes["distractor_count"]):
        state["emails"].append(_email(
            "offsite-draft-%d" % index,
            sender["email"],
            ctx.date(-10 - index),
            "DRAFT OFFSITE %s %02d" % (event, index),
            "Superseded draft logistics.",
        ))
    filename = "v2_%s_%02d_offsite.pptx" % (ctx.split[:3], ctx.index)
    prompt = (
        "List the inbox and read the single email with subject '%s'. Use only that final "
        "source to add the offsite event exactly, reply to its sender confirming "
        "attendance, and create %s with exactly one slide titled for the event and "
        "bullets containing every listed fact in order. Ignore draft messages."
        % (subject, filename)
    )
    effects = [
        {"type": "source_read", "source": "email", "id": source_id},
        {
            "type": "event_created",
            "title": event,
            "date": date,
            "start": "09:00",
            "end": "15:30",
            "location": location,
            "attendees": [],
            "exact_count": 1,
        },
        {
            "type": "email_sent",
            "to": sender["email"],
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
    return prompt, [], state, effects, _difficulty(
        1, 1, 3, 1, len(facts), ctx.branch_count,
    )


_BUILDERS = {
    "pptx_basic": _pptx_basic,
    "pptx_from_email": _pptx_from_email,
    "xlsx_basic": _xlsx_basic,
    "xlsx_from_email": _xlsx_from_email,
    "email_reply": _email_reply,
    "cal_add": _cal_add,
    "cal_freeslot": _cal_freeslot,
    "cal_brief": _cal_brief,
    "remind_msg": _remind_msg,
    "preference_learning": _preference_learning,
    "multi_offsite": _multi_offsite,
}


def validate_office_instance_v2(instance):
    validate_instance(instance)
    validate_office_instance(instance)
    content = instance["content"]
    if content["generator_version"] != GENERATOR_VERSION:
        raise ValueError("instance is not from office-generators/2.0.0")
    if content["family_version"] != FAMILY_VERSION:
        raise ValueError("unexpected v2 family version")
    if content["split"] not in NEXT_SPLITS:
        raise ValueError("v2 instance uses an unsupported split")
    if (
        content["split"] == "adversarial"
        and content["policy_family"] != "office-adversarial-ambiguity-v2"
    ):
        raise ValueError("v2 adversarial policy identity drifted")
    structure = content["structure"]
    expected_structure_keys = {
        "case_shape_version", "family", "workload", "distractor_count",
        "constraint_profile", "episode_shape", "difficulty",
    }
    if set(structure) != expected_structure_keys:
        raise ValueError("v2 semantic structure has unexpected keys")
    if structure["case_shape_version"] != "office-v2/full-factorial-48":
        raise ValueError("v2 case-shape version drifted")
    difficulty = structure["difficulty"]
    expected_difficulty_keys = {
        "minimum_discovery_calls", "minimum_source_reads",
        "minimum_mutating_calls", "artifact_rows_or_slides", "source_items",
        "constraint_branches", "subepisodes",
    }
    if not isinstance(difficulty, dict) or set(difficulty) != expected_difficulty_keys:
        raise ValueError("v2 difficulty axes have unexpected keys")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in difficulty.values()
    ):
        raise ValueError("v2 difficulty axes must be nonnegative integers")
    if difficulty["minimum_mutating_calls"] <= 0:
        raise ValueError("v2 cases require a business mutation")
    prompts = [episode["prompt"] for episode in content["ordered_subepisodes"]]
    independently_derived = derive_outcome(
        content["family"], content["prompt"], prompts,
        content["initial_state"], content["today"],
    )
    if independently_derived != content["required_effects"]:
        raise ValueError("independent prompt oracle disagrees with hidden outcome")
    return instance


def generate_instance(split, family, index):
    if split not in NEXT_SPLITS:
        raise ValueError("unknown v2 split %r" % split)
    if family not in FAMILIES:
        raise ValueError("unknown v2 family %r" % family)
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or not 0 <= index < SPLIT_SIZES[split]
    ):
        raise ValueError("index is outside the frozen v2 split size")
    ordinal = SPLIT_ORDINALS[split][index]
    seed = _seed(split, family, index, ordinal)
    ctx = _Context(split, family, index, ordinal, seed)
    prompt, episodes, state, effects, difficulty = _BUILDERS[family](ctx)
    structure = {
        "case_shape_version": "office-v2/full-factorial-48",
        "family": family,
        "workload": ctx.axes["workload"],
        "distractor_count": ctx.axes["distractor_count"],
        "constraint_profile": ctx.axes["constraint_profile"],
        "episode_shape": "store_then_use" if episodes else "atomic",
        "difficulty": difficulty,
    }
    structure_digest = structure_sha256(structure)
    from .pack import PACK
    content = {
        "id": "v2.%s.%s.%02d" % (
            split, family.replace("_", "-"), index,
        ),
        "domain": PACK.name,
        "domain_version": PACK.version,
        "family": family,
        "family_version": FAMILY_VERSION,
        "generator_version": GENERATOR_VERSION,
        "split": split,
        "seed": seed,
        "structural_template": "%s.%s" % (
            family.replace("_", "-"), structure_digest[:16],
        ),
        "structure_sha256": structure_digest,
        "structure": structure,
        "policy_family": (
            "office-adversarial-ambiguity-v2"
            if split == "adversarial"
            else "office-v2-%s" % ctx.axes["constraint_profile"].replace("_", "-")
        ),
        "today": ctx.today.isoformat(),
        "prompt": prompt,
        "ordered_subepisodes": episodes,
        "opportunity_budget": {
            "model_calls": 18,
            "generated_tokens": 6144,
            "shared_across_subepisodes": bool(episodes),
        },
        "tool_names": list(PACK.registry.names()),
        "initial_state": state,
        "required_effects": effects,
        "forbidden_effects": list(FORBIDDEN_EFFECTS),
        "entities": dict(sorted(ctx.entities.items())),
        "entity_keys": sorted(ctx.entities),
    }
    return validate_office_instance_v2(envelope_instance(content))


def generate_manifest(split):
    instances = [
        generate_instance(split, family, index)
        for family in FAMILIES
        for index in range(SPLIT_SIZES[split])
    ]
    return make_manifest(SUITE, GENERATOR_VERSION, split, instances)


def generate_all_manifests():
    return [generate_manifest(split) for split in NEXT_SPLITS]


__all__ = [
    "FAMILIES",
    "FAMILY_VERSION",
    "GENERATOR_VERSION",
    "NEXT_SPLITS",
    "SEED_NAMESPACE",
    "SPLIT_ORDINALS",
    "SPLIT_SIZES",
    "SUITE",
    "generate_all_manifests",
    "generate_instance",
    "generate_manifest",
    "validate_office_instance_v2",
]

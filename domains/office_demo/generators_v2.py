"""Final successor generators for the eleven synthetic office families.

Version 2.1.1 is a semantic repair of 2.1.0. It deliberately retains the
2.1.0 seed/entity namespace so unaffected public packets remain byte-stable,
while every repaired packet receives a new content hash.
48 genuine semantic shapes per family, explicit difficulty/action axes, and an
independent prompt-to-outcome oracle check on every generated instance.  Every
agent-visible surface is split-neutral; split membership exists only in the
hidden manifest envelope and instance identity.
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
GENERATOR_VERSION = "office-generators/2.1.1"
SEED_NAMESPACE = "office-generators/2.1.0"
FAMILY_VERSION = "2.1.1"
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

_DECISION_POLICIES = {
    "pptx_basic": ("brief_sequence", "risk_descending", "owner_alphabetical"),
    "pptx_from_email": ("sequence_ascending", "revenue_descending", "region_alphabetical"),
    "xlsx_basic": ("source_order", "cost_descending", "item_alphabetical"),
    "xlsx_from_email": ("date_ascending", "amount_descending", "vendor_alphabetical"),
    "email_reply": ("latest_request", "highest_priority", "decision_key_match"),
    "cal_add": ("earliest_feasible", "highest_priority_feasible", "shortest_duration_feasible"),
    "cal_freeslot": ("earliest_free", "latest_free", "closest_to_preferred"),
    "cal_brief": ("chronological", "severity_descending", "owner_alphabetical"),
    "remind_msg": ("due_date_ascending", "priority_descending", "dependency_order"),
    "preference_learning": ("most_recent", "highest_priority", "most_specific_scope"),
    "multi_offsite": ("latest_issued", "highest_approval_rank", "consensus_supported"),
}
_NEUTRAL_STEMS = (
    "Aster", "Birch", "Cinder", "Dovetail", "Ember", "Fable",
    "Grove", "Harbor", "Indigo", "Juniper", "Kestrel", "Lattice",
)
_GIVEN = (
    "Amal", "Bryn", "Cato", "Demi", "Esra", "Fint", "Gaia", "Hale",
    "Iris", "Jori", "Kavi", "Lumi", "Mara", "Niko", "Orla", "Perrin",
)
_SECTIONS = ("Context", "Evidence", "Options", "Decision", "Owners", "Next Steps")
_REGIONS = ("North", "South", "Central", "Online", "Partner", "Public")
_ITEMS = ("Equipment", "Licenses", "Training", "Travel", "Research", "Facilities")
_ITEM_SOURCE_ORDER = ("Training", "Equipment", "Licenses", "Travel", "Research", "Facilities")

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


def _axes(family, ordinal):
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 0 <= ordinal < 48:
        raise ValueError("v2 ordinal must be in [0, 48)")
    return {
        "workload": 3 + ordinal % 4,
        "distractor_count": (ordinal // 4) % 4,
        "decision_policy": _DECISION_POLICIES[family][ordinal // 16],
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
        "constraint_branches": 3,
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
        self.axes = _axes(family, ordinal)
        # The complete factorial uses Monday anchors so "next Tuesday" and
        # weekly surface variation remain deterministic and unambiguous.
        self.today = datetime.date(2028, 1, 3) + datetime.timedelta(days=ordinal * 7)

    @property
    def branch_count(self):
        return _DECISION_POLICIES[self.family].index(self.axes["decision_policy"]) + 1

    def entity(self, role, number=0, kind="person"):
        key = "v2.%s.%02d.%s.%d" % (
            self.family.replace("_", "-"),
            self.ordinal,
            role.replace("_", "-"),
            number,
        )
        token = "%s%s%02d%02d" % (
            _NEUTRAL_STEMS[(self.seed + len(role)) % len(_NEUTRAL_STEMS)],
            self.family.replace("_", " ").title().replace(" ", ""),
            self.ordinal,
            number,
        )
        if kind == "person":
            given = _GIVEN[(self.seed + number * 5 + len(role)) % len(_GIVEN)]
            record = {
                "name": "%s %s" % (given, token),
                "email": "%s.%s@office-v2.example" % (
                    given.lower(), token.lower(),
                ),
            }
        elif kind == "location":
            record = {"name": "%s Collaboration Hall" % token}
        elif kind == "project":
            record = {"name": "Initiative %s" % token}
        elif kind == "vendor":
            record = {
                "name": "%s Supply Group" % token,
                "email": "receipts@%s.office-v2.example" % token.lower(),
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


def _minutes(value):
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _pptx_basic(ctx):
    project = ctx.entity("project", kind="project")["name"]
    count = ctx.axes["workload"]
    sequence = (3, 1, 2, 4, 6, 5)
    risk = (5, 4, 6, 3, 2, 1)
    records = [
        {
            "section": _SECTIONS[index],
            "sequence": sequence[index],
            "risk": risk[index],
            "owner": "Owner-%s" % chr(ord("A") + index),
            "fact": "%s-approved-fact-%d" % (project, index + 1),
        }
        for index in range(count)
    ]
    policy = ctx.axes["decision_policy"]
    selected = list(records)
    if policy == "brief_sequence":
        selected.sort(key=lambda item: item["sequence"])
    elif policy == "risk_descending":
        selected.sort(key=lambda item: (-item["risk"], item["section"]))
    else:
        selected.sort(key=lambda item: (item["owner"], item["section"]))
    titles = [project + " Review"] + [item["section"] for item in selected]
    required_by_slide = [[]] + [[item["fact"]] for item in selected]
    filename = "office_%02d_review.pptx" % ctx.ordinal
    prompt = (
        "Create presentation %s from these approved section records: %s. "
        "Order section slides by policy %s. Use exactly %d slides: one title slide "
        "named '%s', then one slide per section. Use each section name as its slide "
        "title and include that section's exact fact as a bullet. Do not create any "
        "other artifact."
        % (
            filename,
            " | ".join(
                "section=%s,sequence=%d,risk=%d,owner=%s,fact=%s"
                % (item["section"], item["sequence"], item["risk"], item["owner"], item["fact"])
                for item in records
            ),
            policy, len(titles), titles[0],
        )
    )
    effects = [{
        "type": "presentation_created",
        "filename": filename,
        "exact_slide_count": len(titles),
        "ordered_titles": titles,
        "minimum_bullets_by_slide": [0] + [1] * count,
        "required_values_by_slide": required_by_slide,
    }]
    return prompt, [], _base_state(), effects, _difficulty(
        0, 0, 1, len(titles), count, ctx.branch_count,
    )


def _pptx_from_email(ctx):
    project = ctx.entity("project", kind="project")["name"]
    sender = ctx.entity("analyst")
    count = ctx.axes["workload"]
    prefix = "APPROVED REGION %s /" % project
    state = _base_state()
    source_ids = []
    records = []
    for index, region in enumerate(_REGIONS[:count]):
        identifier = "approved-region-%d" % (index + 1)
        revenue_cents = 12_500_000 + 173_000 * (ctx.ordinal + index)
        source_ids.append(identifier)
        records.append({
            "sequence": index + 1, "id": identifier, "region": region,
            "revenue_cents": revenue_cents,
        })
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
    filename = "office_%02d_regions.pptx" % ctx.ordinal
    policy = ctx.axes["decision_policy"]
    selected = list(records)
    if policy == "sequence_ascending":
        selected.sort(key=lambda item: item["sequence"])
    elif policy == "revenue_descending":
        selected.sort(key=lambda item: (-item["revenue_cents"], item["region"]))
    else:
        selected.sort(key=lambda item: item["region"])
    title = project + " Revenue Review"
    prompt = (
        "List the inbox and read every email whose subject begins '%s'. Then create %s "
        "with title slide '%s', followed by one slide per approved email ordered by "
        "policy %s. Use Region as each slide title and include the exact Revenue cents "
        "value. Ignore DRAFT REGION messages."
        % (prefix, filename, title, policy)
    )
    effects = [
        {"type": "sources_read", "source": "email", "ids": source_ids,
         "list_required": True},
        {
            "type": "presentation_created",
            "filename": filename,
            "exact_slide_count": count + 1,
            "ordered_titles": [title] + [item["region"] for item in selected],
            "required_values": [item["revenue_cents"] for item in selected],
            "required_values_by_slide": [[]] + [
                [item["revenue_cents"]] for item in selected
            ],
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, count, 1, count + 1, count, ctx.branch_count,
    )


def _xlsx_basic(ctx):
    owner = ctx.entity("owner")
    rows = [
        [owner["name"], name, 800 + (ctx.ordinal + index + 1) * 125]
        for index, name in enumerate(_ITEM_SOURCE_ORDER[:ctx.axes["workload"]])
    ]
    rule = ctx.axes["decision_policy"]
    selected = [list(row) for row in rows]
    if rule == "cost_descending":
        selected.sort(key=lambda item: (-item[2], item[1]))
    elif rule == "item_alphabetical":
        selected.sort(key=lambda item: item[1])
    filename = "office_%02d_budget.xlsx" % ctx.ordinal
    prompt = (
        "Create spreadsheet %s. Headers: Owner | Item | Cost. Approved rows: %s. Row order "
        "rule: %s. Add exactly one final Total row using a formula."
        % (
            filename,
            " | ".join("Owner=%s,Item=%s,Cost=%d" % tuple(row) for row in rows),
            rule,
        )
    )
    effects = [{
        "type": "spreadsheet_created",
        "filename": filename,
        "headers": ["Owner", "Item", "Cost"],
        "ordered_rows": selected,
        "total_cents": sum(item[2] for item in selected) * 100,
        "formula_required": True,
    }]
    return prompt, [], _base_state(), effects, _difficulty(
        0, 0, 1, len(rows) + 2, 0, ctx.branch_count,
    )


def _xlsx_from_email(ctx):
    accountant = ctx.entity("accountant")
    rows = []
    source_ids = []
    state = _base_state()
    prefix = "FINAL PAID RECEIPT CASE %02d /" % ctx.ordinal
    vendor_order = (2, 0, 1, 3, 5, 4)
    for index in range(ctx.axes["workload"]):
        vendor = ctx.entity("vendor", vendor_order[index], "vendor")
        row = [
            ctx.date(-ctx.axes["workload"] + index),
            vendor["name"],
            4_500 + (ctx.ordinal + index * 2) * 137,
        ]
        rows.append(row)
        identifier = "paid-receipt-%d" % index
        source_ids.append(identifier)
        state["emails"].append(_email(
            identifier, accountant["email"], row[0] + " 16:00",
            "%s %02d" % (prefix, index + 1),
            "PAID RECEIPT: date=%s,vendor=%s,amount_cents=%d. STATUS: FINAL."
            % tuple(row),
        ))
    for index in range(ctx.axes["distractor_count"]):
        state["emails"].append(_email(
            "receipt-draft-%d" % index,
            accountant["email"],
            ctx.date(-10 - index),
            "DRAFT RECEIPTS %02d" % index,
            "Quote or duplicate; not a paid final receipt.",
        ))
    rule = ctx.axes["decision_policy"]
    selected = [list(row) for row in rows]
    if rule == "date_ascending":
        selected.sort(key=lambda item: (item[0], item[1]))
    elif rule == "amount_descending":
        selected.sort(key=lambda item: (-item[2], item[0]))
    else:
        selected.sort(key=lambda item: (item[1], item[0]))
    filename = "office_%02d_expenses.xlsx" % ctx.ordinal
    prompt = (
        "List the inbox and read every email whose subject begins '%s'. Then create %s "
        "with headers Date | Vendor | Amount. Include one row per paid receipt. Row "
        "order rule: %s. Add one final Total row using a formula. Ignore drafts and quotes."
        % (prefix, filename, rule)
    )
    effects = [
        {"type": "sources_read", "source": "email", "ids": source_ids,
         "list_required": True},
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
        1, len(rows), 1, len(rows) + 2, len(rows), ctx.branch_count,
    )


def _email_reply(ctx):
    decision_owner = ctx.entity("decision_owner")
    requesters = [ctx.entity("requester", index) for index in range(3)]
    project = ctx.entity("project", kind="project")["name"]
    prefix = "%s / REQUIRED /" % project
    state = _base_state()
    confirmation_code = "CONF-%02d" % ctx.ordinal
    confirmation_date = ctx.date(5)
    decision_key = "KEY-%02d-A" % ctx.ordinal
    state["emails"].append(_email(
        "required-decision", decision_owner["email"], ctx.date(-5) + " 10:00",
        prefix + "DECISION",
        "DECISION: selection_key=%s; confirmation_code=%s; confirmation_date=%s."
        % (decision_key, confirmation_code, confirmation_date),
    ))
    request_records = [
        {"id": "attendance-0", "date": ctx.date(-4) + " 10:00", "priority": 4,
         "key": decision_key, "requester": requesters[0]},
        {"id": "attendance-1", "date": ctx.date(-3) + " 10:00", "priority": 9,
         "key": "KEY-%02d-B" % ctx.ordinal, "requester": requesters[1]},
        {"id": "attendance-2", "date": ctx.date(-1) + " 10:00", "priority": 1,
         "key": "KEY-%02d-C" % ctx.ordinal, "requester": requesters[2]},
    ]
    for record in request_records:
        state["emails"].append(_email(
            record["id"], record["requester"]["email"], record["date"],
            prefix + "ATTENDANCE " + record["id"],
            "ATTENDANCE REQUEST: priority=%d; decision_key=%s; request_id=%s."
            % (record["priority"], record["key"], record["id"]),
        ))
    for index in range(ctx.axes["distractor_count"]):
        other = ctx.entity("other_sender", index)
        state["emails"].append(_email(
            "unrelated-%d" % index,
            other["email"],
            ctx.date(-1),
            "%s FYI %02d" % (project, index),
            "Informational mention; no attendance request.",
        ))
    policy = ctx.axes["decision_policy"]
    if policy == "latest_request":
        selected = max(request_records, key=lambda item: item["date"])
    elif policy == "highest_priority":
        selected = max(request_records, key=lambda item: item["priority"])
    else:
        selected = next(item for item in request_records if item["key"] == decision_key)
    prompt = (
        "List the inbox and read the decision plus all three attendance requests with "
        "subject prefix '%s'. Select exactly one request using policy %s. Reply exactly "
        "once to that request's sender. Subject must contain '%s'. Body must confirm "
        "attendance and include the decision's confirmation_code, confirmation_date, "
        "and the selected request_id. Do not reply to any other sender."
        % (prefix, policy, project)
    )
    effects = [
        {
            "type": "sources_read",
            "source": "email",
            "ids": ["required-decision"] + [item["id"] for item in request_records],
            "list_required": True,
        },
        {
            "type": "email_sent",
            "to": selected["requester"]["email"],
            "subject_contains": project,
            "body_intent": "confirm_attendance",
            "required_mentions": [confirmation_code, confirmation_date, selected["id"]],
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 4, 1, 0, 4, ctx.branch_count,
    )


def _cal_add(ctx):
    requester = ctx.entity("requester")
    attendees = [
        ctx.entity("attendee", index) for index in range(ctx.axes["workload"])
    ]
    locations = [ctx.entity("location", index, "location")["name"] for index in range(3)]
    state = _base_state()
    date = ctx.date(4)
    for index in range(ctx.axes["distractor_count"]):
        before = 8 * 60 + index * 30
        state["events"].append(_event(
            "adjacent-%d" % index,
            "Existing block %d" % (index + 1),
            date,
            _clock(before),
            _clock(before + 30),
        ))
    candidates = [
        {"id": "candidate-A", "start": 10 * 60, "duration": 45, "priority": 5},
        {"id": "candidate-B", "start": 11 * 60, "duration": 60, "priority": 9},
        {"id": "candidate-C", "start": 12 * 60 + 30, "duration": 30, "priority": 4},
    ]
    for index, candidate in enumerate(candidates):
        candidate.update({
            "title": "%s %s design review" % (requester["name"], candidate["id"]),
            "location": locations[index],
            "attendees": [item["email"] for item in attendees],
        })
    def feasible(candidate):
        start = candidate["start"]
        end = start + candidate["duration"]
        return not any(
            event["date"] == date
            and start < int(event["end"][:2]) * 60 + int(event["end"][3:])
            and int(event["start"][:2]) * 60 + int(event["start"][3:]) < end
            for event in state["events"]
        )
    available = [item for item in candidates if feasible(item)]
    policy = ctx.axes["decision_policy"]
    if policy == "earliest_feasible":
        selected = min(available, key=lambda item: item["start"])
    elif policy == "highest_priority_feasible":
        selected = max(available, key=lambda item: (item["priority"], -item["start"]))
    else:
        selected = min(available, key=lambda item: (item["duration"], item["start"]))
    start = _clock(selected["start"])
    end = _clock(selected["start"] + selected["duration"])
    attendee_text = " | ".join(item["email"] for item in attendees)
    prompt = (
        "Inspect calendar date %s. Candidate requests: %s. Select one feasible request "
        "using policy %s and add exactly one event with that candidate's exact title, "
        "time, location, and these attendees: %s. Preserve every existing event."
        % (
            date,
            " | ".join(
                "id=%s,title=%s,start=%s,duration=%d,priority=%d,location=%s"
                % (item["id"], item["title"], _clock(item["start"]), item["duration"],
                   item["priority"], item["location"])
                for item in candidates
            ),
            policy, attendee_text,
        )
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {
            "type": "event_created",
            "title": selected["title"],
            "date": date,
            "start": start,
            "end": end,
            "attendees": selected["attendees"],
            "location": selected["location"],
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 0, 1, 0, len(state["events"]) + 3, ctx.branch_count,
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
    rule = ctx.axes["decision_policy"]
    preferred = 13 * 60 + 30
    title = "%s focus block" % owner["name"]
    location = "Focus room"
    prompt = (
        "Inspect calendar date %s. Between 09:00 and 17:00, find 30-minute slots "
        "aligned to 30 minutes and choose %s; the preferred start is %s. Add exactly "
        "one event titled '%s' in "
        "that slot, with no attendees and location '%s'. Ignore other dates."
        % (date, rule, _clock(preferred), title, location)
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
        else min(free, key=lambda value: (abs(value - preferred), value))
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
    auditor = ctx.entity("auditor")
    date = ctx.date(3)
    state = _base_state()
    records = []
    severity = (5, 4, 6, 3, 2, 1)
    owner_order = ("Owner-C", "Owner-A", "Owner-B", "Owner-D", "Owner-E", "Owner-F")
    for index in range(ctx.axes["workload"]):
        start = 9 * 60 + index * 60
        title = "Priority: session %d" % (index + 1)
        event = _event(
            "priority-%d" % index,
            title,
            date,
            _clock(start),
            _clock(start + 30),
        )
        event["severity"] = severity[index]
        event["owner"] = owner_order[index]
        state["events"].append(event)
        records.append(event)
    for index in range(ctx.axes["distractor_count"]):
        other_date = date if index % 2 == 0 else ctx.date(4 + index)
        state["events"].append(_event(
            "nonpriority-%d" % index,
            "Routine: unrelated %d" % (index + 1),
            other_date,
            "11:30",
            "12:00",
        ))
    policy = ctx.axes["decision_policy"]
    selected = list(records)
    if policy == "chronological":
        selected.sort(key=lambda item: (item["start"], item["title"]))
    elif policy == "severity_descending":
        selected.sort(key=lambda item: (-item["severity"], item["start"]))
    else:
        selected.sort(key=lambda item: (item["owner"], item["start"]))
    ordered = [item["title"] for item in selected]
    excluded_titles = sorted(
        item["title"] for item in state["events"]
        if item.get("date") == date and item not in selected
    )
    prompt = (
        "Inspect calendar date %s. Send exactly one chat message to %s. Include, in "
        "policy %s order, only event titles beginning 'Priority:' and each start "
        "time. Exclude every other title and date. Then send exactly one separate "
        "chat message to %s containing '%s' and 'priority-count=%d'."
        % (date, recipient["name"], policy, auditor["name"], date, len(ordered))
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {
            "type": "message_sent",
            "to": recipient["name"],
            "ordered_mentions": [
                "%s at %s" % (item["title"], item["start"]) for item in selected
            ],
            "forbidden_mentions": excluded_titles,
            "forbid_date_tokens": True,
            "exact_count": 1,
        },
        {
            "type": "message_sent",
            "to": auditor["name"],
            "required_mentions": [date, "priority-count=%d" % len(ordered)],
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 0, 2, 0, len(state["events"]), ctx.branch_count,
    )


def _remind_msg(ctx):
    recipient = ctx.entity("recipient")
    priorities = (5, 9, 7, 4, 3, 2)
    dependency_order = (2, 0, 1, 3, 4, 5)
    records = []
    for index in range(ctx.axes["workload"]):
        dependency_position = dependency_order.index(index)
        records.append({
            "id": "checkpoint-%d" % (index + 1),
            "due": ctx.date(3 + index),
            "priority": priorities[index],
            "depends_on": (
                "none" if dependency_position == 0
                else "checkpoint-%d" % (dependency_order[dependency_position - 1] + 1)
            ),
            "dependency_position": dependency_position,
        })
    state = _base_state()
    for index in range(ctx.axes["distractor_count"]):
        state["reminders"].append({
            "text": "Existing reminder %d" % (index + 1),
            "date": ctx.date(1 + index),
            "time": "08:00",
        })
    policy = ctx.axes["decision_policy"]
    selected = list(records)
    if policy == "due_date_ascending":
        selected.sort(key=lambda item: (item["due"], item["id"]))
    elif policy == "priority_descending":
        selected.sort(key=lambda item: (-item["priority"], item["id"]))
    else:
        selected.sort(key=lambda item: item["dependency_position"])
    checklist = [item["id"] for item in selected]
    date = selected[0]["due"]
    time = "14:00"
    prompt = (
        "Action items: %s. Order them using policy %s. Create exactly one reminder at "
        "14:00 on the first ordered item's due date. Use the resulting full ordered ID "
        "list as the reminder checklist. Then send exactly one chat message to %s repeating "
        "the same full ordered ID list "
        "in order and committing that the full checklist will be complete by the "
        "deadline. Preserve all reminders."
        % (
            " | ".join(
                "id=%s,due=%s,priority=%d,depends_on=%s"
                % (item["id"], item["due"], item["priority"], item["depends_on"])
                for item in records
            ),
            policy, recipient["name"],
        )
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
        0, 0, 2, 0, len(records), ctx.branch_count,
    )


def _preference_learning(ctx):
    colleague = ctx.entity("colleague")
    bundles = [
        {"id": "bundle-A", "timestamp": 3, "priority": 4, "scope": 2,
         "duration": 20, "start": "10:00", "location": "Video", "prefix": "Focus:"},
        {"id": "bundle-B", "timestamp": 2, "priority": 9, "scope": 1,
         "duration": 25, "start": "11:00", "location": "Cedar room", "prefix": "Deep:"},
        {"id": "bundle-C", "timestamp": 1, "priority": 3, "scope": 3,
         "duration": 30, "start": "12:00", "location": "Studio", "prefix": "Priority:"},
    ]
    policy = ctx.axes["decision_policy"]
    if policy == "most_recent":
        selected = max(bundles, key=lambda item: item["timestamp"])
    elif policy == "highest_priority":
        selected = max(bundles, key=lambda item: item["priority"])
    else:
        selected = max(bundles, key=lambda item: item["scope"])
    optional = [
        "weekday=Tuesday",
        "sole_attendee=%s" % colleague["email"],
    ]
    facts = [
        "subject=%s" % colleague["email"],
        "duration_minutes=%d" % selected["duration"],
        "earliest_start=%s" % selected["start"],
        "location=%s" % selected["location"],
        "title_prefix=%s" % selected["prefix"],
    ] + optional[:max(0, ctx.axes["workload"] - 4)]
    state = _base_state()
    state["memory"] = [
        "subject=%s status=expired distractor=%d ignore=true"
        % (colleague["email"], index + 1)
        for index in range(ctx.axes["distractor_count"])
    ]
    date = ctx.date(1)
    start = selected["start"]
    title = "%s sync with %s" % (selected["prefix"], colleague["name"])
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
        "end": _clock(_minutes(start) + selected["duration"]),
        "attendees": [colleague["email"]],
        "location": selected["location"],
        "exact_count": 1,
    }
    episodes = [
        {
            "id": "store",
            "prompt": (
                "For subject %s, evaluate these preference bundles: %s. Select by "
                "policy %s and save exactly one memory containing only the selected "
                "bundle's applicable facts: %s."
                % (
                    colleague["email"],
                    " | ".join(
                        "id=%s,timestamp_rank=%d,priority=%d,scope_specificity=%d,"
                        "duration_minutes=%d,earliest_start=%s,location=%s,title_prefix=%s"
                        % (item["id"], item["timestamp"], item["priority"], item["scope"],
                           item["duration"], item["start"], item["location"], item["prefix"])
                        for item in bundles
                    ),
                    policy, " | ".join(facts),
                )
            ),
            "required_effects": [store_effect],
        },
        {
            "id": "use",
            "prompt": (
                "Schedule exactly one sync with %s on %s. The attendee is %s. Retrieve "
                "and apply the selected same-attempt preference bundle; the winning "
                "start, duration, location, and optional title prefix are not repeated "
                "here."
                % (colleague["name"], date, colleague["email"])
            ),
            "required_effects": [use_effect],
        },
    ]
    return None, episodes, state, [store_effect, use_effect], _difficulty(
        0, 0, 2, 0, len(bundles), ctx.branch_count, subepisodes=2,
    )


def _multi_offsite(ctx):
    coordinator = ctx.entity("coordinator")
    project = ctx.entity("event", kind="project")["name"]
    state = _base_state()
    candidates = []
    for index, suffix in enumerate(("A", "B", "C")):
        sender = ctx.entity("sender", index)
        location = ctx.entity("location", index, "location")["name"]
        event = "%s Summit %s" % (project, suffix)
        date = ctx.date(10 + index)
        facts = [
            date, "%02d:00-%02d:30" % (9 + index, 15 + index), location,
            ("business casual", "formal", "field attire")[index],
            "bring identification", "lunch provided",
        ][:ctx.axes["workload"]]
        candidates.append({
            "id": "offsite-final-%s" % suffix.lower(), "sender": sender,
            "event": event, "date": date, "start": "%02d:00" % (9 + index),
            "end": "%02d:30" % (15 + index), "location": location, "facts": facts,
            "issued_rank": 3 - index, "approval_rank": (4, 9, 3)[index],
            "consensus": (1, 2, 9)[index],
        })
    index_subject = "OFFSITE SOURCE INDEX %s" % project
    state["emails"].append(_email(
        "offsite-index", coordinator["email"], ctx.date(-2), index_subject,
        "CANDIDATES: %s."
        % " | ".join(
            "id=%s,issued_rank=%d,approval_rank=%d,consensus=%d"
            % (item["id"], item["issued_rank"], item["approval_rank"], item["consensus"])
            for item in candidates
        ),
    ))
    for item in candidates:
        state["emails"].append(_email(
            item["id"], item["sender"]["email"], ctx.date(-6 + item["issued_rank"]),
            "FINAL OFFSITE DETAIL %s" % item["id"],
            "FINAL OFFSITE: event=%s; date=%s; start=%s; end=%s; location=%s; facts=%s."
            % (item["event"], item["date"], item["start"], item["end"],
               item["location"], " | ".join(item["facts"])),
        ))
    for index in range(ctx.axes["distractor_count"]):
        state["emails"].append(_email(
            "offsite-draft-%d" % index,
            coordinator["email"],
            ctx.date(-10 - index),
            "DRAFT OFFSITE %s %02d" % (project, index),
            "Superseded draft logistics.",
        ))
    filename = "office_%02d_offsite.pptx" % ctx.ordinal
    policy = ctx.axes["decision_policy"]
    if policy == "latest_issued":
        selected = max(candidates, key=lambda item: item["issued_rank"])
    elif policy == "highest_approval_rank":
        selected = max(candidates, key=lambda item: item["approval_rank"])
    else:
        selected = max(candidates, key=lambda item: item["consensus"])
    prompt = (
        "List the inbox and read the index email with subject '%s'. Select one detail "
        "source using policy %s, then read that exact FINAL OFFSITE DETAIL email. Use "
        "only the selected detail to add the offsite event exactly, reply to its sender confirming "
        "attendance, and create %s with exactly one slide titled for the event and "
        "bullets containing every listed fact in order. Ignore draft messages."
        % (index_subject, policy, filename)
    )
    effects = [
        {"type": "sources_read", "source": "email", "ids": ["offsite-index", selected["id"]],
         "list_required": True},
        {
            "type": "event_created",
            "title": selected["event"],
            "date": selected["date"],
            "start": selected["start"],
            "end": selected["end"],
            "location": selected["location"],
            "attendees": [],
            "exact_count": 1,
        },
        {
            "type": "email_sent",
            "to": selected["sender"]["email"],
            "body_intent": "confirm_attendance",
            "exact_count": 1,
        },
        {
            "type": "presentation_created",
            "filename": filename,
            "exact_slide_count": 1,
            "ordered_titles": [selected["event"]],
            "required_values": selected["facts"],
            "required_values_by_slide": [selected["facts"]],
        },
    ]
    return prompt, [], state, effects, _difficulty(
        1, 2, 3, 1, len(candidates) + 1, ctx.branch_count,
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
        raise ValueError("instance is not from office-generators/2.1.1")
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
        "decision_policy", "episode_shape", "difficulty",
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
    if content["opportunity_budget"] != {
        "model_calls": 18,
        "generated_tokens": 6144,
        "generated_tokens_per_request": 700,
        "shared_across_subepisodes": True,
    }:
        raise ValueError("v2 opportunity policy drifted")
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
        "decision_policy": ctx.axes["decision_policy"],
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
            else "office-v2-%s" % ctx.axes["decision_policy"].replace("_", "-")
        ),
        "today": ctx.today.isoformat(),
        "prompt": prompt,
        "ordered_subepisodes": episodes,
        "opportunity_budget": {
            "model_calls": 18,
            "generated_tokens": 6144,
            "generated_tokens_per_request": 700,
            "shared_across_subepisodes": True,
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

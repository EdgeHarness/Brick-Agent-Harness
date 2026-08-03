"""S6G generators for the eleven synthetic office task families.

The generators create complete fictional cases: prompt(s), initial state,
required/forbidden effects, policy identity, entities, and a semantic structure
record.  Structural variants are allocated once across all five splits.  A
seed changes only surface choices inside an already-distinct structure and can
therefore never manufacture a second independent case by itself.
"""
import datetime
import hashlib
import random

from harness.instances import (
    SPLITS,
    envelope_instance,
    make_manifest,
    structure_sha256,
    validate_instance,
)


SUITE = "office-synthetic"
GENERATOR_VERSION = "office-generators/1.0.0"
FAMILY_VERSION = "1.0.0"

FAMILIES = (
    "pptx_basic",
    "pptx_from_email",
    "xlsx_basic",
    "xlsx_from_email",
    "email_reply",
    "cal_add",
    "cal_freeslot",
    "cal_brief",
    "remind_msg",
    "preference_learning",
    "multi_offsite",
)

# D0's 44 paired condition cells require two development cases per family.
# Retained contains
# the preregistered 20-case default; the fallback freezes its first 12.  The
# remaining sizes are an S6G protocol choice: four validation cases exercise
# the generator/compiler surface, one sentinel case exercises each family, and
# four adversarial cases cover ambiguity/conflict boundaries without entering
# the confirmatory retained estimand.
SPLIT_SIZES = {
    "development": 2,
    "validation": 4,
    "sentinel": 1,
    "retained": 20,
    "adversarial": 4,
}
_OFFSETS = {
    "development": 0,
    "validation": 2,
    "sentinel": 6,
    "retained": 7,
    "adversarial": 27,
}

_SPLIT_STEMS = {
    "development": "Demerin",
    "validation": "Valecourt",
    "sentinel": "Sentara",
    "retained": "Retwick",
    "adversarial": "Adversen",
}
_GIVEN = (
    "Ari", "Bela", "Cleo", "Dara", "Eli", "Fara", "Gio", "Hana",
    "Ivo", "Juna", "Kian", "Lina", "Miro", "Nia", "Oren", "Pia",
)

FORBIDDEN_EFFECTS = [
    "extra_artifact",
    "extra_mutation",
    "preexisting_state_changed",
    "source_not_read",
    "unauthorized_external_effect",
]


def _seed(split, family, index):
    payload = "%s|%s|%s|%d" % (GENERATOR_VERSION, split, family, index)
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1)


def _axes(ordinal):
    """Thirty-two semantic shapes; S6G consumes the first thirty-one."""
    return {
        "workload": 3 + (ordinal % 4),
        "distractor_count": (ordinal // 4) % 4,
        "constraint_profile": (
            "exact_order" if (ordinal // 16) == 0 else "selection_rule"
        ),
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
        # Every case starts on a Monday.  That prevents the learning family's
        # "tomorrow" request from contradicting its possible avoid-Friday rule
        # while still giving every semantic template a distinct frozen date.
        self.today = datetime.date(2026, 8, 3) + datetime.timedelta(days=ordinal * 7)

    def entity(self, role, number=0, kind="person"):
        key = "%s.%s.%02d.%s.%d" % (
            self.split,
            self.family.replace("_", "-"),
            self.index,
            role.replace("_", "-"),
            number,
        )
        family_token = self.family.replace("_", " ").title().replace(" ", "")
        token = "%s%s%02d%02d" % (
            _SPLIT_STEMS[self.split], family_token, self.index, number
        )
        if kind == "person":
            given = _GIVEN[(self.seed + number * 7 + len(role)) % len(_GIVEN)]
            name = "%s %s" % (given, token)
            record = {
                "name": name,
                "email": "%s.%s@%s.example" % (
                    given.lower(), token.lower(), self.split
                ),
            }
        elif kind == "location":
            record = {"name": "%s Conference Center" % token}
        elif kind == "project":
            record = {"name": "Project %s" % token}
        elif kind == "vendor":
            record = {
                "name": "%s Services" % token,
                "email": "billing@%s.%s.example" % (token.lower(), self.split),
            }
        else:
            raise ValueError("unknown fictional entity kind %r" % kind)
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


def _pptx_basic(ctx):
    project = ctx.entity("project", kind="project")["name"]
    content_count = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    minimum = 2 if ctx.axes["constraint_profile"] == "exact_order" else 3
    topics = ["Overview", "Progress", "Risks", "Decisions", "Owners", "Next Actions"][:content_count]
    excluded = ["Archive %d" % (i + 1) for i in range(distractors)]
    filename = "review_%s_%02d.pptx" % (ctx.split[:3], ctx.index)
    prompt = (
        "Create %s for %s with exactly %d slides: a title slide named '%s Review', "
        "followed by these sections in order: %s. Each section slide must contain at "
        "least %d bullet points. Do not add these unrelated appendix topics: %s."
        % (
            filename, project, content_count + 1, project, ", ".join(topics),
            minimum, ", ".join(excluded) if excluded else "(none)",
        )
    )
    state = _base_state()
    effect = {
        "type": "presentation_created",
        "filename": filename,
        "exact_slide_count": content_count + 1,
        "ordered_titles": [project + " Review"] + topics,
        "minimum_bullets_by_slide": [0] + [minimum] * content_count,
    }
    return prompt, [], state, [effect]


def _pptx_from_email(ctx):
    sender = ctx.entity("sender")
    project = ctx.entity("project", kind="project")["name"]
    region_count = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    regions = ["North", "South", "Central", "Online", "Partner", "Public"][:region_count]
    values = [125000 + 17300 * (ctx.ordinal + i) for i in range(region_count)]
    filename = "regional_%s_%02d.pptx" % (ctx.split[:3], ctx.index)
    source_id = "e-source"
    body = "; ".join("%s revenue $%s" % (r, format(v, ",d")) for r, v in zip(regions, values))
    state = _base_state()
    state["emails"].append(_email(
        source_id, sender["email"], ctx.date(-2), "%s final regional figures" % project,
        "Final approved figures: %s. Use one slide per region." % body,
    ))
    for i in range(distractors):
        state["emails"].append(_email(
            "e-d%d" % i, "archive%d@%s.example" % (i, ctx.split), ctx.date(-10 - i),
            "%s preliminary figures" % project, "PRELIMINARY and superseded; do not use.",
        ))
    prompt = (
        "Read the final approved email about %s and create %s with one title slide named "
        "'%s Regional Revenue', then "
        "one slide per reported region in the email's order. Each region slide must state "
        "that region's exact revenue. Ignore preliminary messages."
        % (project, filename, project)
    )
    effects = [
        {"type": "source_read", "source": "email", "id": source_id},
        {
            "type": "presentation_created",
            "filename": filename,
            "exact_slide_count": region_count + 1,
            "ordered_titles": [project + " Regional Revenue"] + regions,
            "required_values": values,
        },
    ]
    return prompt, [], state, effects


def _xlsx_basic(ctx):
    owner = ctx.entity("owner")
    item_count = ctx.axes["workload"]
    tentative_count = ctx.axes["distractor_count"]
    items = ["Equipment", "Licenses", "Training", "Travel", "Research", "Facilities"][:item_count]
    costs = [700 + (ctx.ordinal + i + 1) * 125 for i in range(item_count)]
    tentative = ["Tentative-%d" % (i + 1) for i in range(tentative_count)]
    filename = "budget_%s_%02d.xlsx" % (ctx.split[:3], ctx.index)
    ordering = "in the listed order" if ctx.axes["constraint_profile"] == "exact_order" else "sorted by descending cost"
    selected = list(zip(items, costs))
    if ctx.axes["constraint_profile"] == "selection_rule":
        selected.sort(key=lambda item: (-item[1], item[0]))
    prompt = (
        "Create %s for %s with columns Item and Cost. Include these approved lines %s: %s. "
        "Exclude the tentative lines %s. Add one final Total row using a spreadsheet formula."
        % (
            filename, owner["name"], ordering,
            ", ".join("%s $%d" % item for item in zip(items, costs)),
            ", ".join(tentative) if tentative else "(none)",
        )
    )
    effect = {
        "type": "spreadsheet_created",
        "filename": filename,
        "headers": ["Item", "Cost"],
        "ordered_rows": [[name, amount] for name, amount in selected],
        "total_cents": sum(costs) * 100,
        "formula_required": True,
    }
    return prompt, [], _base_state(), [effect]


def _xlsx_from_email(ctx):
    receipt_count = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    state = _base_state()
    rows = []
    source_ids = []
    for i in range(receipt_count):
        vendor = ctx.entity("vendor", i, "vendor")
        amount_cents = 4500 + (ctx.ordinal + 2 * i) * 137
        date = ctx.date(-receipt_count + i)
        identifier = "e-r%d" % i
        source_ids.append(identifier)
        rows.append([date, vendor["name"], amount_cents])
        state["emails"].append(_email(
            identifier, vendor["email"], date + " 09:00", "Paid receipt %d" % (i + 1),
            "Receipt date %s; vendor %s; paid amount $%d.%02d."
            % (date, vendor["name"], amount_cents // 100, amount_cents % 100),
        ))
    for i in range(distractors):
        state["emails"].append(_email(
            "e-q%d" % i, "quotes%d@%s.example" % (i, ctx.split), ctx.date(-20 - i),
            "Unpaid quote", "This is a quote, not a paid receipt.",
        ))
    if ctx.axes["constraint_profile"] == "selection_rule":
        rows.sort(key=lambda row: (-row[2], row[0]))
        order = "descending amount"
    else:
        rows.sort(key=lambda row: row[0])
        order = "date order"
    filename = "expenses_%s_%02d.xlsx" % (ctx.split[:3], ctx.index)
    prompt = (
        "Find every paid receipt in the inbox and create %s with Date, Vendor, and Amount "
        "columns, one row per paid receipt in %s, plus a formula Total row. Exclude quotes."
        % (filename, order)
    )
    effects = [
        {"type": "sources_read", "source": "email", "ids": source_ids},
        {
            "type": "spreadsheet_created", "filename": filename,
            "headers": ["Date", "Vendor", "Amount"], "ordered_rows_cents": rows,
            "total_cents": sum(row[2] for row in rows), "formula_required": True,
        },
    ]
    return prompt, [], state, effects


def _email_reply(ctx):
    correspondent = ctx.entity("correspondent")
    project = ctx.entity("project", kind="project")["name"]
    thread_depth = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    state = _base_state()
    source_id = "e-thread-%d" % (thread_depth - 1)
    for i in range(thread_depth):
        state["emails"].append(_email(
            "e-thread-%d" % i, correspondent["email"], ctx.date(-thread_depth + i) + " 10:00",
            "%s kickoff update %d" % (project, i + 1),
            "Update %d. %s" % (
                i + 1,
                "Please confirm attendance." if i == thread_depth - 1 else "Superseded scheduling note.",
            ),
        ))
    for i in range(distractors):
        other = ctx.entity("distractor_sender", i)
        state["emails"].append(_email(
            "e-other-%d" % i, other["email"], ctx.date(-1),
            "%s unrelated mention" % project, "No attendance request in this message.",
        ))
    selection = "the most recent message in the thread" if ctx.axes["constraint_profile"] == "exact_order" else "the message that explicitly requests attendance confirmation"
    prompt = (
        "Find %s about %s and reply to its sender, clearly confirming that I will attend "
        "the kickoff. Do not reply to other senders who merely mention the project."
        % (selection, project)
    )
    effects = [
        {"type": "source_read", "source": "email", "id": source_id},
        {
            "type": "email_sent", "to": correspondent["email"],
            "subject_contains": project, "body_intent": "confirm_attendance",
            "exact_count": 1,
        },
    ]
    return prompt, [], state, effects


def _cal_add(ctx):
    attendee_count = ctx.axes["workload"]
    adjacent_count = ctx.axes["distractor_count"]
    attendees = [ctx.entity("attendee", i) for i in range(attendee_count)]
    owner = ctx.entity("requester")
    state = _base_state()
    date = ctx.date(4)
    start_minutes = 13 * 60 + (ctx.ordinal % 3) * 30
    duration = 30 if ctx.axes["constraint_profile"] == "exact_order" else 45
    start = "%02d:%02d" % divmod(start_minutes, 60)
    end = "%02d:%02d" % divmod(start_minutes + duration, 60)
    for i in range(adjacent_count):
        before = start_minutes - (i + 1) * 30
        state["events"].append(_event(
            "c%d" % i, "Adjacent busy block %d" % (i + 1), date,
            "%02d:%02d" % divmod(before, 60), "%02d:%02d" % divmod(before + 30, 60),
        ))
    title = "%s design review" % owner["name"]
    prompt = (
        "Inspect my calendar, then add '%s' on %s from %s to %s with exactly these "
        "attendees: %s. Keep the adjacent existing events unchanged."
        % (title, date, start, end, ", ".join(item["email"] for item in attendees))
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {
            "type": "event_created", "title": title, "date": date,
            "start": start, "end": end,
            "attendees": [item["email"] for item in attendees], "exact_count": 1,
        },
    ]
    return prompt, [], state, effects


def _cal_freeslot(ctx):
    busy_count = ctx.axes["workload"]
    outside_count = ctx.axes["distractor_count"]
    owner = ctx.entity("owner")
    date = ctx.date(5)
    state = _base_state()
    window_start = 9 * 60
    duration = 30
    for i in range(busy_count):
        start_minutes = window_start + i * 60
        state["events"].append(_event(
            "c-busy-%d" % i, "Busy %d" % (i + 1), date,
            "%02d:%02d" % divmod(start_minutes, 60),
            "%02d:%02d" % divmod(start_minutes + duration, 60),
        ))
    for i in range(outside_count):
        state["events"].append(_event(
            "c-out-%d" % i, "Other day %d" % (i + 1), ctx.date(6 + i), "10:00", "11:00"
        ))
    if ctx.axes["constraint_profile"] == "exact_order":
        selected = window_start + 30
        rule = "earliest"
    else:
        selected = 16 * 60 + 30
        rule = "latest"
    start = "%02d:%02d" % divmod(selected, 60)
    end = "%02d:%02d" % divmod(selected + 30, 60)
    title = "%s focus block" % owner["name"]
    prompt = (
        "Inspect my calendar on %s and book the %s free 30-minute slot starting on the "
        "hour or half-hour between 09:00 and 17:00 as '%s'. Ignore events on other dates."
        % (date, rule, title)
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {"type": "event_created", "title": title, "date": date, "start": start, "end": end, "attendees": [], "exact_count": 1},
    ]
    return prompt, [], state, effects


def _cal_brief(ctx):
    recipient = ctx.entity("recipient")
    meeting_count = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    date = ctx.date(3)
    state = _base_state()
    ordered = []
    for i in range(meeting_count):
        start_minutes = 9 * 60 + i * 75
        title = "Session %d with %s" % (i + 1, recipient["name"])
        ordered.append(title)
        state["events"].append(_event(
            "c-main-%d" % i, title, date,
            "%02d:%02d" % divmod(start_minutes, 60),
            "%02d:%02d" % divmod(start_minutes + 30, 60),
        ))
    for i in range(distractors):
        state["events"].append(_event(
            "c-other-%d" % i, "Other-date event %d" % (i + 1), ctx.date(4 + i), "11:00", "12:00"
        ))
    detail = "titles and start times" if ctx.axes["constraint_profile"] == "selection_rule" else "meeting titles"
    prompt = (
        "Check my calendar for %s and send %s one chat message summarizing all meetings "
        "in chronological order, including %s. Do not include events from other dates."
        % (date, recipient["name"], detail)
    )
    effects = [
        {"type": "calendar_read", "date": date},
        {"type": "message_sent", "to": recipient["name"], "ordered_mentions": ordered, "include_start_times": detail == "titles and start times", "exact_count": 1},
    ]
    return prompt, [], state, effects


def _remind_msg(ctx):
    recipient = ctx.entity("recipient")
    owner = ctx.entity("owner")
    checklist_count = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    date = ctx.date(7)
    time = "15:00" if ctx.axes["constraint_profile"] == "exact_order" else "16:30"
    checklist = ["deliverable-%d" % (i + 1) for i in range(checklist_count)]
    state = _base_state()
    for i in range(distractors):
        state["reminders"].append({
            "text": "Unrelated existing reminder %d" % (i + 1),
            "date": ctx.date(1 + i), "time": "08:00",
        })
    prompt = (
        "Set one reminder for %s at %s for %s to submit this checklist: %s. Also send %s "
        "one message saying the full checklist will be complete by that deadline. Preserve "
        "all existing reminders."
        % (date, time, owner["name"], ", ".join(checklist), recipient["name"])
    )
    effects = [
        {"type": "reminder_created", "date": date, "time": time, "required_mentions": checklist, "exact_count": 1},
        {"type": "message_sent", "to": recipient["name"], "required_mentions": checklist, "body_intent": "deadline_commitment", "exact_count": 1},
    ]
    return prompt, [], state, effects


def _preference_learning(ctx):
    colleague = ctx.entity("colleague")
    preference_count = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    duration = 20 if ctx.axes["constraint_profile"] == "exact_order" else 25
    earliest = 10 + (ctx.ordinal % 3)
    preferences = [
        "meetings last %d minutes" % duration,
        "meetings never start before %02d:00" % earliest,
        "video is preferred",
        "Tuesday is the preferred meeting day",
        "meeting titles begin with Focus:",
        "only the named colleague is invited",
    ][:preference_count]
    state = _base_state()
    state["memory"] = ["Expired preference %d: ignore" % (i + 1) for i in range(distractors)]
    date = ctx.date(1)
    start = "%02d:00" % earliest
    end_minutes = earliest * 60 + duration
    end = "%02d:%02d" % divmod(end_minutes, 60)
    store_effect = {"type": "memory_saved", "required_facts": preferences, "scope": "same_attempt"}
    title = (
        "Focus: sync with %s" % colleague["name"]
        if preference_count >= 5
        else "sync with %s" % colleague["name"]
    )
    use_effect = {
        "type": "event_created", "title": title, "date": date,
        "start": start, "end": end, "attendees": [colleague["email"]],
        "location": "Video" if preference_count >= 3 else "", "exact_count": 1,
    }
    episodes = [
        {
            "id": "store",
            "prompt": "Remember these scheduling preferences for the next request: %s." % "; ".join(preferences),
            "required_effects": [store_effect],
        },
        {
            "id": "use",
            "prompt": "Book a morning sync with %s tomorrow, applying every relevant preference I just gave you." % colleague["name"],
            "required_effects": [use_effect],
        },
    ]
    return None, episodes, state, [store_effect, use_effect]


def _multi_offsite(ctx):
    sender = ctx.entity("sender")
    event = ctx.entity("event", kind="project")["name"] + " Summit"
    location = ctx.entity("location", kind="location")["name"]
    detail_count = ctx.axes["workload"]
    distractors = ctx.axes["distractor_count"]
    date = ctx.date(10)
    facts = [date, "09:00-15:30", location, "business casual", "bring identification", "lunch provided"][:detail_count]
    state = _base_state()
    source_id = "e-offsite"
    state["emails"].append(_email(
        source_id, sender["email"], ctx.date(-1), "%s final logistics" % event,
        "Final logistics: %s. Please confirm."
        % "; ".join(facts),
    ))
    for i in range(distractors):
        state["emails"].append(_email(
            "e-old-%d" % i, sender["email"], ctx.date(-8 - i), "%s draft logistics" % event,
            "DRAFT superseded logistics; do not use.",
        ))
    filename = "summit_%s_%02d.pptx" % (ctx.split[:3], ctx.index)
    slide_values = list(facts)
    prompt = (
        "Read the final logistics email for %s. Add the event to my calendar, reply to the "
        "sender confirming attendance, and create %s with exactly one slide titled '%s' "
        "whose bullets contain the requested logistics. Ignore draft logistics."
        % (event, filename, event)
    )
    effects = [
        {"type": "source_read", "source": "email", "id": source_id},
        {"type": "event_created", "title": event, "date": date, "start": "09:00", "end": "15:30", "location": location, "attendees": [], "exact_count": 1},
        {"type": "email_sent", "to": sender["email"], "body_intent": "confirm_attendance", "exact_count": 1},
        {"type": "presentation_created", "filename": filename, "exact_slide_count": 1, "ordered_titles": [event], "required_values": slide_values},
    ]
    return prompt, [], state, effects


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


def validate_office_instance(instance):
    """Apply domain semantics that the generic content contract cannot know."""
    validate_instance(instance)
    content = instance["content"]
    if content["domain"] != "office_demo" or content["family"] not in FAMILIES:
        raise ValueError("instance is not from the office generator suite")
    state = content["initial_state"]
    expected_state = {
        "emails", "events", "sent_emails", "messages", "reminders",
        "memory", "artifacts",
    }
    if set(state) != expected_state:
        raise ValueError("office initial_state has unexpected keys")
    for field in expected_state:
        if not isinstance(state[field], list):
            raise TypeError("office initial_state.%s must be a list" % field)
    if state["sent_emails"] or state["messages"]:
        raise ValueError("generated attempts cannot start with candidate communications")
    email_ids = [email.get("id") for email in state["emails"]]
    event_ids = [event.get("id") for event in state["events"]]
    if len(email_ids) != len(set(email_ids)) or not all(email_ids):
        raise ValueError("generated email ids must be unique and nonempty")
    if len(event_ids) != len(set(event_ids)) or not all(event_ids):
        raise ValueError("generated event ids must be unique and nonempty")
    allowed_effects = {
        "calendar_read", "email_sent", "event_created", "memory_saved",
        "message_sent", "presentation_created", "reminder_created",
        "source_read", "sources_read", "spreadsheet_created",
    }
    for effect in content["required_effects"]:
        effect_type = effect.get("type")
        if effect_type not in allowed_effects:
            raise ValueError("unknown office required effect %r" % effect_type)
        if effect_type == "source_read" and effect.get("id") not in email_ids:
            raise ValueError("source_read does not name an initial email")
        if effect_type == "sources_read":
            ids = effect.get("ids")
            if not isinstance(ids, list) or not ids or not set(ids) <= set(email_ids):
                raise ValueError("sources_read does not name only initial emails")
        if effect_type == "presentation_created" and not effect.get("filename", "").endswith(".pptx"):
            raise ValueError("presentation effect filename must end in .pptx")
        if effect_type == "spreadsheet_created" and not effect.get("filename", "").endswith(".xlsx"):
            raise ValueError("spreadsheet effect filename must end in .xlsx")
        if effect_type == "event_created":
            if effect.get("end", "") <= effect.get("start", ""):
                raise ValueError("generated event effect has a nonpositive duration")
            for existing in state["events"]:
                if existing["date"] != effect["date"]:
                    continue
                if effect["start"] < existing["end"] and existing["start"] < effect["end"]:
                    raise ValueError("generated required event overlaps initial state")
    learning = content["family"] == "preference_learning"
    if learning != bool(content["ordered_subepisodes"]):
        raise ValueError("only the learning family may contain subepisodes")
    if learning:
        flattened = [
            effect
            for episode in content["ordered_subepisodes"]
            for effect in episode["required_effects"]
        ]
        if flattened != content["required_effects"]:
            raise ValueError("learning subepisode effects do not form the case effects")
    if content["split"] == "adversarial":
        if content["structure"]["distractor_count"] < 2:
            raise ValueError("adversarial cases require at least two distractors")
        if content["policy_family"] != "office-adversarial-ambiguity-v1":
            raise ValueError("adversarial case does not use the adversarial policy")
    return instance


def generate_instance(split, family, index):
    if split not in SPLITS:
        raise ValueError("unknown split %r" % split)
    if family not in FAMILIES:
        raise ValueError("unknown family %r" % family)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < SPLIT_SIZES[split]:
        raise ValueError("index is outside the frozen split size")
    ordinal = _OFFSETS[split] + index
    seed = _seed(split, family, index)
    ctx = _Context(split, family, index, ordinal, seed)
    prompt, episodes, initial_state, effects = _BUILDERS[family](ctx)
    structure = {
        "family": family,
        "workload": ctx.axes["workload"],
        "distractor_count": ctx.axes["distractor_count"],
        "constraint_profile": ctx.axes["constraint_profile"],
        "episode_shape": "store_then_use" if episodes else "atomic",
    }
    structure_digest = structure_sha256(structure)
    from .pack import PACK  # Lazy import avoids changing the released pack surface.
    content = {
        "id": "%s.%s.%02d" % (split, family.replace("_", "-"), index),
        "domain": PACK.name,
        "domain_version": PACK.version,
        "family": family,
        "family_version": FAMILY_VERSION,
        "generator_version": GENERATOR_VERSION,
        "split": split,
        "seed": seed,
        "structural_template": "%s.%s" % (family.replace("_", "-"), structure_digest[:16]),
        "structure_sha256": structure_digest,
        "structure": structure,
        "policy_family": (
            "office-adversarial-ambiguity-v1"
            if split == "adversarial"
            else "office-conditional-constraints-v1"
            if ctx.axes["constraint_profile"] == "selection_rule"
            else "office-exact-effects-v1"
        ),
        "today": ctx.today.isoformat(),
        "prompt": prompt,
        "ordered_subepisodes": episodes,
        "opportunity_budget": {
            "model_calls": 14,
            "generated_tokens": 4096,
            "shared_across_subepisodes": bool(episodes),
        },
        "tool_names": list(PACK.registry.names()),
        "initial_state": initial_state,
        "required_effects": effects,
        "forbidden_effects": list(FORBIDDEN_EFFECTS),
        "entities": dict(sorted(ctx.entities.items())),
        "entity_keys": sorted(ctx.entities),
    }
    return validate_office_instance(envelope_instance(content))


def generate_manifest(split):
    instances = [
        generate_instance(split, family, index)
        for family in FAMILIES
        for index in range(SPLIT_SIZES[split])
    ]
    return make_manifest(SUITE, GENERATOR_VERSION, split, instances)


def generate_all_manifests():
    return [generate_manifest(split) for split in SPLITS]


__all__ = [
    "FAMILIES",
    "FAMILY_VERSION",
    "GENERATOR_VERSION",
    "SPLIT_SIZES",
    "SUITE",
    "generate_all_manifests",
    "generate_instance",
    "generate_manifest",
    "validate_office_instance",
]

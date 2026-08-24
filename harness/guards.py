"""Advisory cross-checks that run before a tool call executes.

Every guard follows one contract: QUESTION ONCE, NEVER FORBID. A guard returns
the sentence to put in front of the model, or None to abstain. A call the model
repeats after being questioned is allowed to run. Do not turn any of these into
a block; that invariant is the whole design, and it has been broken by accident
before - see the wording note on guard_unplanned_write. Refusal lives in
ActionPolicy, never here.

run_guards stops at the first guard that speaks: DENIAL IS MONOTONIC, a later
guard never sees a questioned call and so can never turn a question back into
permission.

Guards are advisory heuristics for interactive runs. They change what a model
does mid-run, so they stay OFF in bench/ unless a condition enables them
explicitly - otherwise every recorded comparison silently shifts.

This module knows no domain. Tool capabilities come from what each spec
declares (writes_file, opens), effects come from ActionPolicy, and the file
listing for guard_unread_file comes from the attempt's artifact directory
rather than any world member.
"""
import datetime
import re


# ---------------------------------------------------- task-named dates ----
#
# A self-contained resolver for the date expressions a task can name, kept in
# the harness because the harness core must stay free of domain imports. It
# mirrors the expression kinds the office pack's argument normalizer resolves,
# so the two agree on what "next tuesday" means.

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}


def _resolve_date_expr(value, today):
    s = str(value).strip().lower()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    if s == "today":
        return today.isoformat()
    if s == "tomorrow":
        return (today + datetime.timedelta(days=1)).isoformat()
    m = re.match(r"^(?:next\s+)?([a-z]+day)$", s)
    if m and m.group(1) in _WEEKDAYS:
        delta = (_WEEKDAYS.index(m.group(1)) - today.weekday()) % 7 or 7
        return (today + datetime.timedelta(days=delta)).isoformat()
    m = re.match(r"^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?$", s)
    if m:
        for name, num in _MONTHS.items():
            if name.startswith(m.group(1)):
                year = int(m.group(3)) if m.group(3) else today.year
                return f"{year:04d}-{num:02d}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", s)
    if m:
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100:
            year += 2000
        return f"{year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return value


def task_dates(task_text, today):
    """Every date expression the task itself names, resolved to ISO dates.

    Matches weekday names (with optional "next", plural s), today/tomorrow,
    "July 23", "7/23", and literal YYYY-MM-DD. A bare month with no day number
    is not a date and does not match.
    """
    text = str(task_text).lower()
    found = set()
    patterns = [
        r"\b(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
        r"\btoday\b|\btomorrow\b",
        r"\b(?:january|february|march|april|may|june|july|august|september|october"
        r"|november|december)\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?\b",
        r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            expr = m.group(0).rstrip("s") if re.match(patterns[0], m.group(0)) else m.group(0)
            resolved = _resolve_date_expr(expr, today)
            if isinstance(resolved, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", resolved):
                found.add(resolved)
    return found


def _describe(iso, today):
    d = datetime.date.fromisoformat(iso)
    return f"{iso} (a {_WEEKDAYS[d.weekday()].capitalize()})"


def task_date_mismatch(task_text, args, today):
    """The task names exactly one date and the call carries a different one.

    Argument normalization fixes "wednesday" but leaves a well-formed
    YYYY-MM-DD alone - so a model that does the arithmetic itself and gets it
    wrong sails straight through. Observed live: the task said Wednesday, the
    model sent a Monday, every tool answered honestly for the wrong day, and
    the agent told a colleague their Wednesday was clear.

    Deliberately conservative: only when the task names exactly ONE distinct
    date, so "move my Wednesday meeting to Friday" is left alone. The harness
    never rewrites the date - it says what is wrong and what the right one is.
    """
    value = (args or {}).get("date")
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()):
        return None
    named = task_dates(task_text, today)
    if len(named) != 1:
        return None
    want = next(iter(named))
    got = value.strip()
    try:
        datetime.date.fromisoformat(got)
    except ValueError:
        return None
    if got == want:
        return None
    return (f"The call uses {_describe(got, today)}, but the task means "
            f"{_describe(want, today)}. Use {want} unless a tool result says otherwise.")


# ------------------------------------------------------- other helpers ----

ECHO_SPAN = 8   # consecutive words that have to match before it counts as copied


def echoes_history(summary, history):
    """True when the summary contains a run of words copied from the earlier
    conversation, rather than describing this run.

    A copied SPAN, not shared vocabulary. Two summaries of similar work reuse
    the same words, and treating that as a copy would question every
    legitimate follow-up turn.
    """
    if not history or not summary:
        return False
    hist = " ".join(str(history).lower().split())
    words = str(summary).lower().split()
    if len(words) < ECHO_SPAN:
        return False
    return any(" ".join(words[i:i + ECHO_SPAN]) in hist
               for i in range(len(words) - ECHO_SPAN + 1))


def planned_tools(plan_text, registry):
    """The tool names out of a rendered plan, in order. plan_step writes each
    step as "N. tool - what" and only admits real tool names, so this reads
    back what it wrote."""
    return [m.group(1) for m in re.finditer(r"^\d+\.\s+(\S+)", plan_text or "", re.M)
            if m.group(1) in registry]


def filename_re(registry):
    """Filenames the run could actually be told to open, built from the
    extensions the registered read tools declare via `opens`."""
    exts = registry.openable_extensions()
    if not exts:
        return None
    alt = "|".join(re.escape(e.lstrip(".")) for e in sorted(exts))
    return re.compile(r"\b[\w.\-]+\.(?:" + alt + r")\b")


REPLAN_PROMPT = (
    'TASK: {task}\n\nYour plan was written before you had read anything:\n{plan}\n\n'
    'You have now read something, and it may require work the plan does not '
    'name. Rewrite the plan for what is ACTUALLY left to do, as tool names. '
    'Respond with one JSON object: {{"steps": [{{"tool": "<tool name>", "what": '
    '"<why>"}}]}} - and nothing the task does not need.')


# ------------------------------------------------------------ the state ----

class GuardState:
    """Everything a guard may read or change, for one run.

    One object rather than a dozen closure variables, so a guard is an
    ordinary function that can be called from a test with a hand-built state.
    """

    def __init__(self, llm, ep, messages, task_text, registry, write_tools,
                 plan, artifact_dir, today, history=""):
        self.llm, self.ep = llm, ep
        self.messages, self.task_text = messages, task_text
        self.registry = registry
        self.write_tools = frozenset(write_tools)
        self.artifact_dir = artifact_dir
        self.today = today
        self.history = history
        self.name, self.args = None, None       # the call being judged
        self.plan = plan
        self.planned = planned_tools(plan, registry)
        self.planned_set = set(self.planned)
        # The read the plan itself put BEFORE its first write. Only that
        # counts: taking the first non-write was wrong, because a plan of
        # think -> create -> read reads back the file it is about to create,
        # and the nudge sent the agent to open something that did not exist.
        first_write_at = next((i for i, t in enumerate(self.planned)
                               if t in self.write_tools), None)
        self.first_read_planned = None
        if first_write_at is not None:
            self.first_read_planned = next(
                (t for t in self.planned[:first_write_at]
                 if t not in ("think", "done") and t not in self.write_tools),
                None)
        self.looked = False
        self.nudged_to_look = False
        self.replanned = False
        self.questioned_writes = set()
        # Files the run was TOLD about (a filename inside something it read)
        # versus files it has actually opened.
        self.mentioned_files = set()
        self.opened_files = set()
        self.questioned_files = set()
        # The done phase. summary is set at the done boundary; it is None for
        # every call-time guard and that is deliberate.
        self.summary = None
        self.echo_questioned = False

    def is_write(self):
        return self.name in self.write_tools

    def existing_files(self):
        """Filenames present in the attempt's artifact directory.

        The listing deliberately comes from the filesystem the attempt writes
        into, not from any world member, so no digest-bound source is
        involved and the guard works for any pack that produces files."""
        try:
            return {p.name for p in self.artifact_dir.iterdir() if p.is_file()}
        except OSError:
            return set()


# ------------------------------------------------------------ the guards ----

def guard_wrong_date(g):
    """A date the model wrote itself, checked against the date the task names.

    Writes only. The guard exists to stop a write landing on the wrong day; a
    READ with a mismatched date is the model looking around, and the result
    comes back as evidence either way. Checked on every call, it hounded a run
    whose task merely said "never on Fridays": four corrections for four
    innocent list_events probes, 14 calls for a task that needs four."""
    if not g.is_write():
        return None
    wrong_day = task_date_mismatch(g.task_text, g.args, g.today)
    if not wrong_day:
        return None
    g.ep.invalid_calls += 1
    return "WRONG DATE: " + wrong_day + " Reply with one corrected JSON object."


def guard_unplanned_write(g):
    """A write the plan never proposed, questioned once.

    Observed live: asked only to "list my emails", an 8B read one, then SENT
    an email, added a calendar event and messaged a third party - four side
    effects for a read-only request, and every surface reported success.
    save_memory is exempt: remembering is never a side effect on another
    person.

    The replan is here because the plan is written before the agent has read
    anything, so on any task whose requirements live in the data the plan
    CANNOT name the work, and holding the model to it punishes it for
    discovering the job. A plan made before discovery is a hypothesis, so once
    a read has landed, spend one call revising it. Only once: a model that
    could replan on every surprise could rewrite its way to anything.

    Wording note, load-bearing. This message once ended "Only do what the task
    requires - nothing extra", and an 8B obeyed THAT instead of insisting. The
    question became a block in practice. Do not reintroduce that clause."""
    if not (g.planned_set and g.is_write() and g.name != "save_memory"
            and g.name not in g.planned_set and g.name not in g.questioned_writes):
        return None
    if g.looked and not g.replanned:
        from .agent import plan_step
        g.replanned = True
        ask = REPLAN_PROMPT.format(task=g.task_text, plan=g.plan or "(none)")
        g.ep.note("prompt", ask)
        g.messages.append({"role": "user", "content": ask})
        g.plan = plan_step(g.llm, g.messages, g.ep, g.registry) or g.plan
        g.messages.pop()
        g.planned = planned_tools(g.plan, g.registry)
        g.planned_set = set(g.planned)
    if g.name in g.planned_set:
        return None
    g.questioned_writes.add(g.name)
    return (f"Your plan for this task never included {g.name}, and the task is: "
            f"\"{g.task_text}\". If {g.name} is genuinely what the task needs, "
            f"call it again and it will run. If it is not, continue with the "
            f"plan or call done.")


def guard_unread_file(g):
    """Writing a file while the task's own data sits unopened in another one.

    Same contract as guard_read_before_write, one step further in: there,
    nothing has been read at all; here, something WAS read and it named a file
    that exists and is still unopened. Observed live: a message said "the
    export is in q3_raw.xlsx", the agent never opened it, and invented
    Sales/Profit rows with formulas summing empty cells."""
    if g.name not in g.registry.file_writing_tools():
        return None
    unread = sorted(g.mentioned_files & g.existing_files()
                    - g.opened_files - g.questioned_files)
    opener = g.registry.opener_for(unread[0]) if unread else None
    if not (unread and opener):
        return None
    g.questioned_files.update(unread)
    return (f"What you read names {unread[0]}, which exists here, and you "
            f"have not opened {unread[0]} yet - so {g.name} would be writing "
            f"from memory rather than from the task's own data. Call "
            f"{opener} on it first. If you genuinely do not need it, "
            f"call {g.name} again and it will run.")


def guard_read_before_write(g):
    """The model planned to look something up, then writes without looking.

    The worst failure this app can produce, observed live: asked to build a
    spreadsheet of July receipts, an 8B skipped straight to the write and
    invented 100/200/300/400/500 for receipts that are really $230.00, $87.50
    and $412.30. It saved the invented total to long-term memory as a fact,
    and the run reported success - every check downstream can see that a file
    was written and none can see that its numbers were made up."""
    if not (g.first_read_planned and not g.looked and not g.nudged_to_look
            and g.is_write() and g.name != "save_memory"):
        return None
    g.nudged_to_look = True
    return (f"You planned to call {g.first_read_planned} first and have not read "
            f"anything yet, so {g.name} would be writing from memory rather than "
            f"from the task's own data. Call {g.first_read_planned} first. If you "
            f"genuinely do not need it, call {g.name} again and it will run.")


def guard_done_echo(g):
    """A done summary that copies an eight-word span out of an earlier turn.

    Left alone it compounds, because the summary is stored and becomes the
    next turn's context, so a run can end by quoting its own previous ending
    back at itself for as long as the conversation lasts.

    Runs at the DONE boundary rather than on a tool call, which is why it
    lives in DONE_GUARDS. Same contract as every other guard: ask once, take
    the answer."""
    if not (g.history and not g.echo_questioned
            and echoes_history(g.summary, g.history)):
        return None
    g.echo_questioned = True
    return ("That summary repeats an answer from earlier in this "
            "conversation. Say only what you did in THIS run, in one "
            "sentence, then call done again.")


# Order matters and is stated here rather than buried in statement order.
GUARDS = [
    ("wrong_date", guard_wrong_date),
    ("unplanned_write", guard_unplanned_write),
    ("unread_file", guard_unread_file),
    ("read_before_write", guard_read_before_write),
]

# Guards that run at the DONE boundary instead of on a tool call. A separate
# list because they take different inputs, not because they follow a
# different contract.
DONE_GUARDS = [
    ("done_echo", guard_done_echo),
]


def run_guards(g, guards=None):
    """First guard to speak wins. Returns (guard_name, message) or None.

    Monotonic on purpose: once a guard has questioned a call, no later guard
    runs, so nothing downstream can turn the question back into permission.
    Guards after the first are not consulted and their side effects do not
    happen, which is why an expensive one (the replan) sits behind a cheap
    predicate rather than in front of it."""
    if guards is None:
        guards = GUARDS
    for name, check in guards:
        message = check(g)
        if message:
            return name, message
    return None

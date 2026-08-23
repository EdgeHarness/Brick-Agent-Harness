# Phase 2 design: guards, made domain-independent

**Status: proposal. Not implemented, not approved.** Nothing in this document is
in the tree. It exists to be argued with before any code is written.

Phase 1 brought the Agent Lab console and the MCP connector layer across from
the Final-Agent-8B line. Phase 2 brings the five **guards**, which are the part
of that harness that actually changes what a small model does mid-run, and which
Brick currently has none of.

## A correction to the earlier framing

I previously described the guards as "welded to global lookups" and proposed
turning those lookups into declarations. That was half wrong, and the half that
was wrong makes this job smaller.

**The declarations already exist upstream.** `opener_for`, `file_writing_tools`
and `simulated_connector_tools` are not hardcoded name lists; each one is a
comprehension over a spec key that a tool declares about itself:

```python
def file_writing_tools(registry=None):
    reg = registry if registry is not None else TOOLS
    return frozenset(n for n, s in reg.items() if s.get("writes_file"))
```

So the guards are already domain-independent in principle. What actually couples
them is narrower and more concrete:

1. every helper defaults to the **process-global `TOOLS` dict**, which Brick does
   not have and deliberately replaced with a per-attempt `ToolRegistry`;
2. **Brick's specs do not carry the keys** (`opens`, `writes_file`,
   `simulated_connector`), so every helper would return an empty set here and
   every guard would silently never fire;
3. **Brick's world has no `file_names()`**, which one guard needs outright.

Point 2 is the dangerous one. Ported naively, the guards would import, run, pass
their tests, and do nothing, which is worse than not porting them.

## What Brick has instead today

Brick replaced the upstream model-verifier with `completion.py`: postconditions
over real state, where a model verifier may explain but never establish. The
guards are **not** a replacement for that and must not be presented as one. They
sit at a different point in the loop:

| | when it runs | what it decides |
|---|---|---|
| guards | before a tool call executes | should this specific call happen yet |
| `completion.py` | at the done boundary | is the task actually finished |

They compose. A guard questions a call; postconditions still decide completion.

## The five guards

Each one exists because of an observed live failure, and the reason is worth
carrying over with the code.

| guard | fires when | observed failure it prevents |
|---|---|---|
| `wrong_date` | a **write** carries a date the task did not name | a write landing on the wrong day |
| `unplanned_write` | a write the plan never proposed | asked only to "list my emails", an 8B sent an email, added an event and messaged a third party |
| `read_before_write` | the plan put a read before its first write, and nothing has been read | asked for a spreadsheet of July receipts, the model invented 100/200/300 for real values of $230.00, $87.50, $412.30, then saved the invented total to memory |
| `unread_file` | writing a file while a file the run was *told about* sits unopened | a message said the export is in `q3_raw.xlsx`, the agent never opened it and invented rows |
| `done_echo` | a done summary copies a span from an earlier turn | a run ends by quoting its own previous ending, compounding each turn |

Two contract properties matter more than the individual rules:

- **Question once, never forbid.** A guard returns a message; calling the same
  tool again runs it. Guards are not a policy layer and must never become one.
  `ActionPolicy` is where refusal lives.
- **Denial is monotonic.** The first guard to speak wins and no later guard runs,
  so nothing downstream can turn a question back into permission.

## The design

### 1. Spec keys, declared per tool

Three optional keys, following the precedent already set by `simulates` and
`suppress_identical_repeats`:

| key | type | meaning |
|---|---|---|
| `writes_file` | bool | the tool produces a file |
| `opens` | tuple of extensions | the tool can read these, e.g. `(".xlsx",)` |
| `simulates` | string | already exists; the surface a real account would replace |

Note `simulates` **already landed in phase 1** and does the job upstream calls
`simulated_connector`. Keep Brick's name; do not import the second spelling.

`_validate_spec` gains type checks for the two new keys. An unknown value fails
loudly at registry construction, matching how `ALLOWED_EFFECTS` already behaves,
rather than failing silently at guard time.

### 2. Registry methods, not module functions

Upstream's helpers take an optional registry and fall back to a global. Brick has
no global, so they become methods on `ToolRegistry`:

```python
registry.file_writing_tools()      # frozenset of names
registry.opener_for("q3_raw.xlsx") # a tool name, or None
```

This removes coupling point 1 entirely, and means a guard is handed the exact
registry composed for that task, including any MCP tools merged in.

### 3. `GuardState`, carrying a registry rather than reaching for one

Ported close to upstream, with `world`, `registry` and `write_tools` passed in.
It is a plain object precisely so a guard can be unit-tested with a hand-built
state and no run.

`write_tools` derives from `ActionPolicy`, not from a name regex: Brick already
classifies every tool's effect explicitly, and a pack cannot register a tool
without doing so. That is strictly better than what upstream infers, and it means
MCP tools are covered for free, since phase 1 classifies them `external_write`.

### 4. The hook in the loop

One insertion in `run_harness`, after argument validation and before
repeat-suppression, which is where upstream puts it:

```python
g.name, g.args = name, args
questioned = run_guards(g)
if questioned:
    guard_name, message = questioned
    ep.note("guard", guard_name)
    give_feedback(message, reply)
    continue
```

`ep.note("guard", ...)` makes every question visible in the transcript and in
the Agent Lab timeline without further UI work.

### 5. The world contract

> **BLOCKED as of 2026-08-23.** This step was implemented and reverted.
> `domains/office_demo/world.py` is one of sixteen files bound by digest to the
> `v0.13.5` tag, and `bench/focused_recovery_successor.py` requires the live
> implementation delta against that tag to be `harness/experiment.py` and
> nothing else. Any edit to the world voids the v0.13.6 preauthorization, which
> binds the 24 unstarted B1b cells and the 240-cell B2 schedule.
>
> The failing check is
> `test_transitive_model_and_analysis_sources_are_directly_bound`. It was
> reported rather than repaired, and the written patch is kept.
>
> Three ways forward, and the choice is not an engineering one:
>
> 1. **Wait.** Land the world merge after v0.13.6 runs or is formally retired.
>    Guards that need `file_names()` wait with it; the other four do not.
> 2. **Avoid the world.** Source the file listing from `attempt.artifact_dir`
>    rather than `world.file_names()`. No bound file changes, and the guard
>    stops depending on a world member at all, which is arguably better
>    layering. It does mean the loop reads the filesystem directly.
> 3. **Re-authorize.** Treat the world change as a versioned protocol change
>    with its own authorization, which is what the rules say a bound-source
>    change requires.
>
> Option 2 is the only one that needs no decision from anyone and no waiting.

#### Original text

`guard_unread_file` needs `world.file_names()`. Brick's `domains/office_demo/world.py`
does not have it; upstream's does, along with `list_files`, `update_event`,
`cancel_event` and a real fix for `_next_event_id` (Brick still assigns
`c{len(events)+1}`, which repeats an id after any removal).

Fold the world merge into this phase, because the guard cannot work without part
of it. Take upstream's world, keep Brick's `fresh_emails`/`fresh_calendar`
deepcopy isolation, and make the action-log clip a named constant **defaulted to
300**, so 1.5 MB of recorded evidence stays comparable and a new study opts into
1000 explicitly.

A guard whose world lacks the member it needs must **skip, not crash**. A pack
that never declares `opens` simply never triggers `unread_file`.

### 6. What each pack declares

| pack | change |
|---|---|
| `office_demo` | `writes_file` on the document writers, `opens: (".xlsx",)` on the spreadsheet reader. `simulates` already present |
| `counter_demo` | nothing. It has no files, so file guards never fire, which is the portability check |
| `brix_followup_synthetic` | nothing required. Confirm `unplanned_write` behaves against its proposal flow before enabling |

If `counter_demo` needs an edit to keep working, the abstraction is wrong and
that is the signal to stop.

## Risks

**The silent-no-op risk is the main one.** Ported without declarations, guards
run and never fire. Mitigation: a test asserting each guard fires at least once
against a constructed state, plus one asserting `office_demo` declares a
non-empty `file_writing_tools()`.

**Guards change model behaviour, so they change benchmark results.** They must be
off in `bench/` unless a condition explicitly enables them, exactly as upstream
keeps them out of its benchmark. Otherwise every recorded comparison silently
shifts. This is the single most important line in this document.

**`wrong_date` was over-eager upstream.** Checked on every call it hounded a run
whose task merely said "never on Fridays": four corrections for four innocent
`list_events` probes, 14 calls for a task needing four. It is writes-only for
that reason. Keep that restriction.

## Test plan

- one unit test per guard, hand-built `GuardState`, no run
- monotonicity: a second guard never sees a questioned call
- question-once: the same call after a question executes
- `counter_demo` runs unchanged with guards enabled
- guards absent from the benchmark path
- the ported world keeps fixture isolation, and `_next_event_id` survives a removal

## Sequencing

1. Spec keys and registry methods, with validation. No behaviour change.
2. World merge, including `file_names()` and the id fix. No behaviour change.
3. `GuardState` and the five guards, not yet wired. Unit tests only.
4. Wire into `run_harness` behind `RunConfig`, default off.
5. Declare on `office_demo`. Turn on for interactive runs, leave off in `bench/`.

Steps 1 and 2 are safe to land alone. Step 4 is the first that changes what a
model does, and is the right place to stop for review.

## Decisions (settled 2026-08-23)

Answered against DeepSeek Harness `@99f6f02`, which is the reference for this
family of questions. Its `repeat-tool-reminder` sits in
`packages/bundle/base/cordis.patch.yml`, the shared base roster every shipped
surface loads, so it is on by default for everyone.

**1. Guards are ON for interactive runs, OFF in `bench/`.**

dsh can default its guard on because of a contract that is nearly ours word for
word: it "never appears in the tool list, never vetoes or rewrites a call", and
"the decision stays entirely with the model". They considered escalating to a
block and rejected it, because "a blocked call punishes legitimate identical
repeats and an advisory reminder keeps the model in control".

The failures ours prevent are observed, not theoretical, and the asymmetry is
stark: a false positive costs one sentence and one retry, while a false negative
is a confident wrong answer that looks like success and gets saved to memory as
fact. A guard defaulted off is also a guard nobody turns on.

**2. Every guard mounts for every pack, including `brix_followup_synthetic`.**

dsh's include/exclude patterns are predicates over whatever tools exist at call
time, and a pattern matching no current tool "is NOT an error". So a guard mounts
everywhere and simply never fires where it does not apply. No per-pack decision,
and one less thing for a new customer pack to get wrong.

**3. Guards stay out of the retained study.**

dsh calls its guard "a heuristic nudge, not a logged invariant" and keeps it in
memory only. A heuristic nudge does not belong in a frozen protocol as a default.
If guards are ever studied they are an explicit versioned condition.

## One improvement over a straight port

dsh does not fire on first occurrence. It escalates at `[3, 5, 8]`: a short
generic nudge at the first threshold, the detailed form naming tool, count and
canonical arguments at later ones. Zero tokens before the threshold.

`wrong_date` has a recorded over-eagerness problem, four corrections for four
innocent `list_events` probes and 14 calls spent on a task needing four.
Escalation rather than immediate firing is worth adopting for the noisier
guards. It is not in steps 1 and 2 and can be decided when the guards land.

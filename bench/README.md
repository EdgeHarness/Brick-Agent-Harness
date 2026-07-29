# Benchmark

This directory contains a small **exploratory synthetic benchmark**. It is an
instrument under development, not a validated evaluation and not evidence that
the harness improves any model.

No results are committed. `results/` is ignored, so any score mentioned outside
an explicitly versioned result bundle must be treated as unverified.

## Research question

A defensible question for a future version is:

> Under recorded resource constraints, which explicit orchestration mechanisms,
> if any, improve strict task completion or reduce harmful-side-effect rates for
> local models; and where does model capability remain limiting?

“Scaffolding beats scale” is a hypothesis, not the benchmark's established
conclusion.

## Current implementation

`run_bench.py` iterates over model tags, condition names and selected tasks.
Each task receives a new `World` object seeded with ten emails, seven calendar
events and a fixed clock of Monday 2026-07-20. A model/condition pair shares one
JSONL memory file across its tasks.

There are two intended conditions:

- **`raw`** calls `run_raw()`: tool descriptions without examples, a prompt
  requesting JSON, strict parsing, direct execution and error feedback.
- **`harness`** calls `run_harness()`: examples, constrained JSON output,
  lenient parsing, argument repair, shape feedback, date/time normalization,
  planning, duplicate suppression, model verification and memory injection.

Only the exact string `harness` selects the harness runner. Any other condition
string currently falls through to `raw`; condition values are not validated.
An unknown task ID also produces an empty task selection rather than an error.

The raw loop is a deliberately weak prompt-only JSON baseline. It is not a
reasonable native function-calling baseline and must not be presented as “the
normal production implementation.”

## What is and is not held constant

The current conditions share:

- the same default 14-tool registry and executors;
- the same synthetic fixtures and fixed clock;
- the same 14-total-LLM-call ceiling;
- the same client temperature and seed defaults;
- the same 2,000-character observation truncation.

They do **not** consume an equal inference budget. The harness has a longer
prompt, adds planning/verifier requests, uses call-specific output limits and
can grow a different history. A common call ceiling is not equality of tokens,
FLOPs, latency, energy or cost.

Temperature zero and seed 42 improve repeatability but do not guarantee exact
reproduction across model digests, quantizations, runtime versions, hardware or
drivers. The current result record does not capture those dependencies.

## Current task suite

The suite has 12 fixed prompts in a fixed order. The check counts below are the
maximum checks produced when conditional artifact/action branches exist.

| # | Task | Nominal checks | Intended behavior |
|---|---|---:|---|
| 1 | `pptx_basic` | 11 | create a five-slide deck with requested titles and bullets |
| 2 | `pptx_from_email` | 6 | turn seeded Q3 figures into a regional deck |
| 3 | `xlsx_basic` | 7 | create a budget table and total |
| 4 | `xlsx_from_email` | 6 | extract three seeded receipts into a sheet |
| 5 | `email_reply` | 4 | find a recent Northwind email and send a simulated reply |
| 6 | `cal_add` | 6 | create a simulated event with normalized date/time |
| 7 | `cal_freeslot` | 5 | choose a free hour and create a simulated event |
| 8 | `cal_brief` | 5 | send a simulated chronological calendar summary |
| 9 | `remind_msg` | 6 | create a simulated reminder and message |
| 10 | `learn_store` | 3 | write two preferences to JSONL memory |
| 11 | `learn_use` | 4 | apply those preferences in a later episode |
| 12 | `multi_offsite` | 8 | create a simulated event/reply and a real deck |

The nominal maximum is 71 boolean checks. These tasks are not independent:
`learn_store` and `learn_use` deliberately share memory, while all other tasks
also run against that same file. There are no alternate instances, held-out
templates, adversarial variants or independently sampled workplace cases.

The suite exercises synthetic tool use. It does not test real email, calendar,
room, messaging, identity, access-control or concurrency behavior.

## Current scoring

Each task grader returns a list of `(description, passed)` checks. The task
score is:

```text
passed checks / checks emitted
```

`report.py` takes unweighted means of those task scores. It also counts tasks
whose partial score is at least `0.999` as “perfect.”

All graders are programmatic; no LLM judge is used. Programmatic grading is a
useful design choice, but it does not make the current checks valid.

Strict complete-task success should become the primary outcome. The existing
partial score should be retained only as a diagnostic after its denominator is
fixed.

## Known validity defects

Current output must be labeled **exploratory / invalid for publication** until
the following are fixed.

### Stale artifact contamination

The task directory is reused. Constructing a new `World` does not clear
`<task>/files`, so a failed rerun can be graded using a PPTX or XLSX left by an
earlier attempt.

### Resume and shared-memory contamination

The runner deletes the model/condition memory file before checking which tasks
are already complete. On resume, `learn_store` may be skipped while
`learn_use` runs with empty memory.

Conversely, during an uninterrupted run, `learn_store` grades the whole shared
memory file. A fact saved by any earlier task can satisfy part of its rubric.
The same shared memory and fixed ordering can influence unrelated later tasks.

### Variable denominators

Many dependent checks are appended only if an artifact or target action exists.
The denominator therefore varies by output. A missing artifact receives one
failed existence check, while an incomplete artifact can receive a different
number of checks. This can inflate or distort comparisons relative to a fixed
rubric.

### Loose and gameable checks

Examples include:

- `_find_file()` claims stem matching but accepts the requested text anywhere
  in a filename;
- spreadsheet item names and amounts are searched across the entire sheet, so
  they need not be in the same row;
- slide region names and revenue numbers need not be associated with one
  another;
- slide “exact title” checks actually use substring containment;
- email selection is inferred from the outgoing address rather than proving the
  required source email was read;
- a bare substring such as `yes` can satisfy attendance confirmation;
- `sam` in the chronology check can match `same`;
- most tasks do not fail when the agent also sends unwanted emails/messages,
  creates extra events/files, or writes unrelated memory.

These defects make a high partial score easier than correctly completing the
workflow.

### Instrument failures become model failures

A grader exception is turned into `score = 0.0` and an ordinary failed check.
The report averages it as model performance. For example, the formula evaluator
crashes on multi-letter spreadsheet columns because it passes more than one
character to `ord()`.

Runner exceptions and grader exceptions are not represented with a complete,
separate validity status.

### Non-atomic and unversioned results

`results.json` is truncated and rewritten after every task. An interruption in
that window can corrupt the ledger used for resume. There is no lock for two
writers.

Records do not include:

- benchmark/task/grader/harness versions;
- Git commit and dirty-state digest;
- prompt/tool-schema hashes;
- exact model digest or quantization;
- Ollama/backend version;
- hardware, OS or driver provenance;
- task-instance seed, attempt ID or condition order;
- termination category or grader error.

Scores from different instruments can therefore be mixed without detection.

### No isolation between attempts

Directory identity is only `(model, condition, task)`, not run and attempt.
There is no immutable attempt manifest or explicit list of artifacts produced
by that attempt.

### No causal mechanism attribution

The harness changes many mechanisms together. Lower parse failures, invalid
calls or tool errors cannot be assigned to a single mechanism because prompt
content, parser, decoding, validation, planning and context all differ.
`invalid_calls` is also a harness-only pre-execution concept.

The current failure counters are descriptive traces, not causal explanations.

### Weak statistical unit

There is one fixed prompt per task and one attempt per cell. The twelve-task
mean is not a variance estimate, and the task labels are not independent
samples from a defined office-work population. Repeating an identical prompt
with another sampler seed would still not create independent business cases.

### Confounded size comparisons

The commonly listed tags mix Llama 3.2 at 1B/3B, Llama 3.1 at 8B, and another
family for proposed 14B/32B points. Family, generation, tokenizer, training data
and parameter count change together. That is not a causal model-size curve.

## Fields currently recorded

Each completed runner iteration appends:

| Field | Current meaning and caution |
|---|---|
| `model`, `condition`, `task`, `caps` | requested labels, not immutable versions |
| `score`, `checks` | current grader output, including disguised grader errors |
| `finished` | agent called `done`; not proof that work is correct or verified |
| `llm_calls`, `max_calls` | request counts, not total compute |
| `parse_failures` | failures under that condition's parser and prompt |
| `invalid_calls` | pre-execution harness shape rejections only |
| `tool_errors` | executor-returned failures |
| `prompt_tokens`, `output_tokens` | aggregate token counts reported by client |
| `wall_seconds` | outer elapsed time; ordering/system load are uncontrolled |
| `error` | runner exception only; grader error is not separated |

`report.py` emits descriptive means by model, capability and task. If only one
condition exists, the overall table currently omits that model row because it
requires both `raw` and `harness`.

## Files currently produced

```text
results/
  results.json
  summary.json
  SUMMARY.md
  <model-slug>/<condition>/
    memory.jsonl
    <task>/
      transcript.md
      state.json
      files/
```

`summary.json` is not consumed by an HTML report in the current repository.
Generated Office files are genuine local documents; email, calendar, message
and reminder effects remain simulated.

## Running for development only

From the repository root:

```bash
python -m bench.run_bench \
  --models llama3.2:1b \
  --conditions raw harness \
  --tasks pptx_basic cal_add \
  --outdir results-dev

python -m bench.report --outdir results-dev
```

Use a disposable output directory for each invocation. Do not merge records
from different commits. The current runner's resume behavior is unsafe for the
learning pair.

## Required design for the next valid benchmark

The canonical R1 and R2 gates in
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md) are authoritative;
[`../FIXES.md`](../FIXES.md) supplies the code-level defect register. At minimum,
a retained benchmark must implement the following.

### Versioned, isolated attempts

- Unique run and attempt directories, created empty.
- Explicit artifact manifests.
- Isolated state and memory, except for declared multi-episode scenarios.
- Atomic writes and one-writer locking.
- Separate complete, aborted, runner-error, grader-error and invalid states.
- Full code/model/runtime/hardware provenance.

### Outcome-valid graders

- Fixed denominators.
- Strict whole-task pass as primary.
- Exact row/slide/source/recipient associations.
- Required-read evidence where source selection matters.
- Negative checks and harmful-side-effect counts.
- Adversarial grader fixtures and instrument-error exclusion.

### Defensible conditions

Use explicit validated condition IDs:

1. deterministic workflow/rules baseline where applicable;
2. reasonable native function-calling baseline where the selected runtime and
   models expose a comparable interface, otherwise a preregistered substitute
   and limitation;
3. complete harness;
4. preregistered mechanism ablations.

The existing raw loop may remain as a labeled lower bound.

### Resource accounting

Record per-role prompt/output tokens, latency, retries, approvals, peak resource
use and energy where feasible. Compare strict success and side effects against
cost; do not call equal call ceilings equal inference.

### Independent cases and analysis

- Define the target task population and estimand.
- Use varied task instances, entities, dates, policies, wording and distractors.
- Hold out template/policy families.
- Pair conditions on the same instances and counterbalance order.
- Determine sample size before the retained run.
- Report uncertainty appropriate to clustered task data and reliability across
  genuinely varied cases.
- Use a same-family, same-generation model sweep with documented training
  comparability for size analysis, with immutable digests.

### Freeze rule

Freeze tasks, graders, schemas, prompts, analysis and mechanism conditions only
after offline tests and a disposable sentinel matrix pass. Any subsequent
instrument change requires a version bump and a new result stratum.

Until that protocol exists, the benchmark is useful for debugging the harness,
not for supporting scientific or product claims.

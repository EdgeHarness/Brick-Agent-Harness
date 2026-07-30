# Benchmark

This directory contains the released **exploratory synthetic benchmark** and is
being rebuilt into the instrument specified in
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md).

The latest release is `v0.3.1`. F0/Q0 work is **unreleased**, and Lenovo F0 is
pending. No committed result currently establishes that the harness improves a
model.

## Confirmatory question

The future retained primary asks:

> For the 11 fixed synthetic Brick task-family generator distributions, does
> `harness_full` improve strict whole-task success over a competent
> `native_tools` implementation on the pinned Qwen3.5 4B system under the same
> end-to-end opportunity budget?

The answer applies only to the frozen generators, 4B digest, conditions and
budgets. “Scaffolding beats scale” is not a premise or planned universal
conclusion.

## Released exploratory implementation

`run_bench.py` currently loads one `DomainPack`, iterates over model tags,
validated condition names and task IDs, and gives each task a fresh in-memory
world. A model/condition pair still shares one JSONL memory file and reused task
paths.

The only released conditions are:

- `raw`: prompt-requested JSON, strict parsing, direct execution and feedback;
- `harness`: examples, lenient extraction, argument repair, normalization,
  planning, duplicate suppression, model verification and memory injection.

`raw` is a deliberately weak lower bound, not a competent native function-call
baseline. The two released conditions do not share a transport or equal
inference work. They currently share a 14-call ceiling, temperature zero, seed
42 and observation truncation, but differ in prompts, output limits, roles,
history, tokens and latency.

These released settings describe legacy development behavior only. They do not
define the retained protocol and do not establish reproducibility across model
digests, runtimes, drivers or hardware.

## Released office task suite

`office_demo@0.1.0` has 12 fixed prompts:

| # | Task | Intended behavior |
|---|---|---|
| 1 | `pptx_basic` | create a five-slide deck |
| 2 | `pptx_from_email` | turn seeded figures into a deck |
| 3 | `xlsx_basic` | create a budget table and total |
| 4 | `xlsx_from_email` | extract seeded receipts into a sheet |
| 5 | `email_reply` | read and reply to a simulated email |
| 6 | `cal_add` | create a simulated event |
| 7 | `cal_freeslot` | choose and reserve a simulated free hour |
| 8 | `cal_brief` | send a simulated chronological summary |
| 9 | `remind_msg` | create a simulated reminder and message |
| 10 | `learn_store` | write preferences to local model memory |
| 11 | `learn_use` | use the dependent stored preferences |
| 12 | `multi_offsite` | create simulated effects and a real deck |

`counter_demo@0.1.0` has one structural counter task. It is wiring evidence, not
transfer evidence.

The office tasks are not independent. They have no held-out structural
instances, adversarial variants or defined population. Email, calendar,
messaging and reminder effects are simulated. `.pptx` and `.xlsx` artifacts are
real local files.

## Released scoring and validity defects

The released grader emits variable lists of boolean component checks and reports
their mean. That is not a valid strict-success measure.

Known defects include:

- task directories are reused, so stale Office files can influence a rerun;
- resume can erase shared memory before checking completed dependencies;
- unrelated tasks share memory and fixed order;
- missing artifacts can change the denominator;
- filenames use substring matching;
- spreadsheet values need not share the correct row/column association;
- slide titles, regions and values need not be structurally associated;
- broad substrings can satisfy source or confirmation checks;
- extra unwanted actions often go unpenalized;
- a grader exception becomes model score zero;
- `results.json` is rewritten non-atomically without a writer lock;
- records omit complete task, grader, prompt, model, runtime, code, hardware and
  ordering provenance;
- there is one fixed prompt and one attempt per cell;
- the Llama 1B/3B/8B and Qwen2.5 14B/32B launch folders are not a controlled
  size series; and
- bundled mechanisms prevent causal attribution.

All current output is **exploratory / invalid for publication**.

## Running the legacy path for development only

From the repository root:

```bash
python -m bench.run_bench \
  --models llama3.2:1b \
  --conditions raw harness \
  --tasks pptx_basic cal_add \
  --outdir results-dev

python -m bench.report --outdir results-dev
```

Use a new disposable output directory for every invocation. Do not merge
commits, publish scores, or treat resume as safe for the learning pair. These
models and conditions are excluded from the retained matrix.

## Target evidence store

S4 replaces the released layout with:

```text
runs/<run-id>/
  run.json
  run.lock
  attempts/<logical-hash>/<physical-uuid>/
    attempt.json
    initial-state.json
    final-state.json
    result.json
    grade.json
    actions.json
    transcript.md
    memory-delta.jsonl
    artifacts/
    PREPARED.json
    COMMITTED
  results.json
```

A physical UUID directory is created directly at its final location and never
reused. The writer closes and hashes every required file, validates
`PREPARED.json`, then publishes through exclusive creation of the empty
`COMMITTED` marker. No attempt directory is renamed or replaced.

Readers accept only marker-present bundles whose manifest and hashes validate.
A valid prepared bundle without the marker is adopted without another model
call. Incomplete bundles are preserved as abandoned. Duplicate candidates,
logical collisions and invalid committed evidence halt the run. `results.json`
is a rebuildable projection.

## Target tasks and graders

S6G creates 11 fixed scenario-family generator distributions, combining the
dependent learning episodes into one family. Instances vary structure, policy,
state, valid action sequence, wording, entities, dates, conflicts and
distractors. Seed-only or entity-renaming variants are rejected as independent
cases.

Each learning-family case is one logical attempt with ordered store-then-use
subepisodes. They share one isolated memory scope and one
14-call/4096-generated-token ledger; both must strictly succeed. An instrument
failure in either makes the case null. The subepisodes are not counted as two
model attempts, so the stated primary and secondary totals remain unchanged.

Development, validation, sentinel, retained and adversarial manifests replay
exactly and share neither entities nor structural templates.

S5 graders use fixed versioned rubrics over immutable attempt evidence. Strict
whole-task success is primary. Harmful, unauthorized, stale, missing, extra or
incorrect effects fail the task. Store, runner and grader failures yield null
model outcome. Component checks remain fixed-denominator diagnostics.

## Target primary conditions

`native_tools` and `harness_full` use the same:

- pinned `qwen3.5:4b-q4_K_M` digest;
- Ollama native function-call transport and chat template;
- tool schemas, ordering and tool-result transport;
- deterministic validators and state transitions;
- task, initial state and hidden grader; and
- context, sampling, call and output opportunity limits.

The full harness adds only versioned planning, scoped untrusted memory,
known-alias repair, duplicate suppression, observation management and completion
guarding.

Shared candidate settings:

- context 8192 and thinking disabled;
- temperature 1.0, `top_p=1.0`, `top_k=20`, `min_p=0`;
- presence penalty 2.0 and repeat penalty 1.0;
- maximum 700 generated tokens per request;
- maximum 4096 generated tokens and 14 total calls per attempt; and
- a frozen per-instance seed base reused for paired conditions.

All driver, planning and completion calls consume the ledger. This asks whether
the harness pays for its overhead; it does not claim equal tokens, FLOPs,
latency or energy. Record and report the full frontier.

F0 must confirm native transport and accepted options on the Lenovo before S4.
It saves exact payloads, captures template/context state, requires `think=false`,
and requires explicit rejection of the unknown
`brick_f0_unknown_option`. That proves option-name validation, not the numerical
behavioral effect of every black-box sampling option. The exact Ollama binary and
model digests come from F0 rather than a hard-coded version.

## Running the Lenovo F0 gate

Use only the native Windows 11 ARM64 Lenovo, native ARM64 Python and Ollama, a
clean pushed candidate commit, and a short local NTFS output path outside
OneDrive. Connect AC power and keep Defender real-time protection and Windows
Search indexing enabled. Select Windows Best Performance (or an active
High/Ultimate Performance scheme). The probe also requires an unchanged Ollama
listener and observes an Ollama model-runner descendant rather than measuring
only the small listener. From an ARM64 PowerShell in the repository root:

```powershell
git switch --detach <C>
git status --short
python -m pip install -r requirements-test.txt
python -m pytest -q
python -m bench.f0_probe fingerprint
python -m bench.f0_probe run --outdir C:\BrickRuns\f0 --pull
```

The status command must print nothing. The probe must exit zero and print
`F0 PASS run=<RUN_DIR>`. Verify that exact path independently:

```powershell
python -m bench.f0_probe verify "<RUN_DIR>"
```

Preserve the run directory unchanged. Archive it, record the archive and manifest
SHA-256 values, extract the archive to a fresh location, and verify the extracted
copy. The release retains the archive externally and records its identity in
`evidence/f0/v0.4.0.json`; raw F0 evidence is not committed into Git.

```powershell
$runDir = "<RUN_DIR>"
$archive = "$runDir.zip"
$extractRoot = "$runDir-extracted"
Compress-Archive -LiteralPath $runDir -DestinationPath $archive -CompressionLevel Optimal
Get-FileHash -Algorithm SHA256 $archive
Get-FileHash -Algorithm SHA256 (Join-Path $runDir "PREPARED.json")
Get-FileHash -Algorithm SHA256 (Join-Path $runDir "summary.json")
Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot
$extractedRun = Join-Path $extractRoot (Split-Path $runDir -Leaf)
python -m bench.f0_probe verify $extractedRun
```

Both `$archive` and `$extractRoot` must be new paths.

[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md) defines the complete prerequisites,
4B stop rule, allowed 2B/9B omissions, and the tested candidate `C` to
metadata-only release descendant `R` attestation. A nonzero command, non-pass
summary, dirty worktree, unverified archive, or behavioral change after `C`
leaves F0 pending and forbids `v0.4.0`.

## Sample and analysis

D0 runs 44 score-masked development pairs and selects sample size using runtime
only:

- default: 20 cases per family, 220 pairs, 440 attempts;
- predeclared fallback: 12 cases per family, 132 pairs, 264 attempts.

The estimand is the equal-family-weight mean paired strict-success difference.
Its inferential gate is a predeclared 95% within-family percentile bootstrap:
20,000 pair-resampling draws, NumPy `Generator(PCG64)` seed `20260729`,
draw-major/family-major ordering, and Hyndman–Fan type-7 quantiles. Constant
families remain as point masses.

A two-sided exact paired sign-flip/McNemar p-value is an additional diagnostic
under the sharp pairwise-exchangeability null, not an exact test of the weak null
that the equal-family effect is zero. A positive claim requires positive effect,
diagnostic `p < 0.05`, and bootstrap 95% lower bound above zero. Golden tests pin
draw indices, p-values, quantile behavior and endpoints. Claims remain limited to
the frozen generators.

## Descriptive matrix

Run descriptives only after sealing the primary:

| Analysis | Attempts |
|---|---:|
| 2B native/full system replication | 44 |
| 9B native/full system replication | 44 |
| `raw_json` lower bound | 22 |
| Three harness ablations | 66 |
| No-memory learning ablation | 2 |
| Equal-action native/full sensitivity | 44 |

The default maximum is 662 model attempts. `rules_reference` is model-free and
reported separately. Every secondary is descriptive: no confirmatory p-values,
Holm tests, causal mechanism claim or “no effect” conclusion.
The two no-memory cases each remain one ordered two-subepisode logical attempt;
only the scoped memory bridge is disabled.

There is one stochastic draw per retained cell. Report success across
independent structural cases; make no within-instance repeatability or
pass-at-\(k\) claim.

## Scheduler, sentinel and incomplete runs

A standalone Python or PowerShell scheduler owns the queue, lock, heartbeat,
health checks, evidence commits and resume. The primary runs first in `N`
balanced waves, where D0 freezes `N` to 20 or 12. Paired AB/BA order is
counterbalanced.

Reboot resume requires an identical code/protocol/model/runtime/OS/driver/backend
fingerprint after fixed warm-up. Different environment strata are never pooled.
Sustained throughput degradation triggers the frozen cooldown and stop rule
without inspecting outcomes.

S8 must produce zero instrument-invalid cells. Any instrument change requires a
patch release and full sentinel rerun.

A primary with any unresolved required pair is
`INCOMPLETE/DESCRIPTIVE`. Report coverage and reasons, but no confirmatory
inference or selected subset. It does not complete the research milestone. A
sealed complete primary remains reportable if a later descriptive phase stops.

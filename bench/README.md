# Benchmark

This directory contains the released **exploratory synthetic benchmark** and is
being rebuilt into the instrument specified in
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md).

The latest release is `v0.11.1` (pre-D0 integrity repair), preceded by
`v0.11.0` (S6C fair-condition runtime and scheduler), `v0.10.0` (S6G),
`v0.9.0` (S5W), `v0.8.0` (S5), `v0.7.0` (B0),
`v0.6.0` (S1R), `v0.5.0` (S4), and `v0.4.0` (F0/Q0).
The Lenovo F0 gate passed, establishing that this
host can run the designed experiment. S4's production evidence store and
attestor are released: the native gate passed with `overall_status` pass, 461
passed, 0 failed and `s4_skipped` 0. S6C now implements the generated-office
compiler/grader, shared native transport, conditions, accounting, scheduler,
preflight, telemetry, rules reference, and descriptive ablations. Retained
execution remains disabled, and no committed result establishes that the
harness improves a model.

Annotated tags and bound evidence are release-authoritative; see the canonical
`C`/`R`/`D` lifecycle in
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md#native-windows-arm64-attestation).

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

## v0.7 exploratory validity defects and S5 corrections

The `v0.7.0` exploratory path used variable component lists and their mean. The
released S5 implementation replaces that scoring surface with fixed,
versioned, all-or-nothing graders over copied evidence. Exact filenames,
row/column and slide/value association, required source reads, extra effects,
and null grader/runner failures are enforced by the S5 acceptance matrix.

Known defects include:

- task directories are reused, so stale Office files can influence a rerun;
- resume can erase shared memory before checking completed dependencies;
- unrelated tasks share memory and fixed order;
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

S4 implements the production store in `harness/evidence.py` and replaces the
released layout with:

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

`run.json` is an immutable `brick.evidence-run/1` document and its SHA-256 is
bound into every attempt. `run.lock` is a persistent regular file that is never
deleted. A writer acquires an exclusive POSIX `flock` or Windows `LockFileEx`
lock before recovery scanning or model access and holds it through execution,
publication, and projection rebuilding.

The logical directory is the SHA-256 of the exact `brick.attempt-key/1` bytes.
That strict key binds domain name/version/content, task family/version,
generator/grader versions, model tag/digest, condition name/version/mechanism,
instance ID/content, ordered subepisodes, repeat, sampling, opportunity budget,
prompt, and tool schema. Serialization is compact sorted UTF-8 JSON with NFC
strings and no trailing newline. Atomic attempts use an empty subepisode list;
subepisode IDs are unique and ordered. Sampling and opportunity maps contain no
JSON floats. S4 requires a nonempty sampling object and a nonempty
opportunity-budget object of nonnegative integer counts; the later frozen
benchmark protocol owns their exact keys, ranges, and decimal-string grammar.

A physical UUID directory is created directly at its final location and never
reused. The writer uses strict versioned attempt, state, result, grade, and
action envelopes, closes and hashes every required file, validates
`PREPARED.json`, then publishes through exclusive creation of the empty
`COMMITTED` marker. `grade.json` records a candidate decision rather than final
strict success. No attempt directory is renamed, replaced, or mutated after
commit.

Readers accept only marker-present bundles whose manifest and hashes validate.
A valid prepared bundle without the marker is adopted without another model
call. Incomplete bundles are preserved as abandoned. Duplicate valid
candidates, logical collisions and invalid committed evidence halt the run.
`results.json` is a deterministic committed-only projection, not resume
authority. Record and publication status and strict success are derived during
validation. A non-adopting inspection reports aggregate prepared or abandoned
state, invalid committed evidence halts, and uncommitted candidates remain on
disk for forensic inspection.

The complete schema, retry schedule, status derivation, projection shape, and
cooperative-local-writer threat model are normative in
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md#s4--marker-last-evidence-store).

### Native Windows ARM64 S4 gate

Hosted Windows x64 CI is required portability coverage but does not replace the
native Lenovo S4 gate. Run from a clean, pushed candidate commit with native
ARM64 Python, Developer Mode enabled, Defender and Windows Search left active,
and a new short NTFS output directory outside OneDrive:

```powershell
git switch --detach <C>
git status --short
python -m pip install -r requirements-test.txt
$candidate = git rev-parse HEAD
$s4Root = "C:\BrickRuns\s4"
New-Item -ItemType Directory -Path $s4Root -Force | Out-Null
$runToken = [guid]::NewGuid().ToString("N").Substring(0, 8)
$reportDir = Join-Path $s4Root `
  "s4-$($candidate.Substring(0, 12))-$runToken"
if (Test-Path -LiteralPath $reportDir) { throw "S4 report path exists" }
python bench/s4_attest.py run `
  --project-root C:\Brick `
  --report-dir $reportDir `
  --output C:\Brick\evidence\s4\v0.5.0.json
```

The first `git status --short` must print nothing. The attestor independently
requires the pushed worktree to remain clean before and after its exact pytest
command, sanitizes pytest selection/plugin environment variables, sets
`BRICK_S4_NATIVE_REQUIRED=1`, recomputes the candidate's complete collected
inventory, samples all native host/service facts before and after the suite, and
only then exclusively creates the attestation as the intended first worktree
change. It refuses an existing report directory or attestation.
The suite must execute—not skip—the S4
symlink, junction/reparse, real Office held-handle, cross-process lock,
hard-process-exit recovery, corruption, duplicate/collision, stale-artifact, and
projection-rebuild cases. Preserve the JUnit file unchanged and record its
name, size, SHA-256, command, candidate commit, host/runtime/volume identity,
Defender/Search state, exact pass/fail/skip counts, and verification timestamp in
the strict `brick.s4-attestation/1` `evidence/s4/v0.5.0.json` described in the
canonical plan. Attach the hash-matched JUnit file to the `v0.5.0` release. Any
S4 platform skip or behavioral change after `<C>` leaves the gate pending.

After committing only that regular attestation file as direct release descendant
`R`, pushing `R`, and creating the annotated `v0.5.0` tag with the required
`candidate_commit=`, `attestation_blob=`, and `junit_sha256=` lines, verify the
tracked record and unchanged release asset with:

```powershell
python bench/s4_attest.py verify `
  --project-root C:\Brick `
  --attestation C:\Brick\evidence\s4\v0.5.0.json `
  --junit (Join-Path $reportDir "pytest.xml") `
  --native-required
```

After the tag and release asset are verified, create and push docs-only
descendant `D` from `R`. Promote the staged changelog entry with the actual
release date and update candidate-scoped status prose. Review `R..D` and require
that it modifies only already-tracked Markdown. Do not move `v0.5.0` from `R`;
`D` is post-release documentation, not part of the attested release.

## Target tasks and graders

S6G provides 11 fixed scenario-family generator distributions, combining the
dependent learning episodes into one family. Instances vary structure, policy,
state, valid action sequence, wording, entities, dates, conflicts and
distractors. Seed-only or entity-renaming variants are rejected as independent
cases.

Each learning-family case is one logical attempt with ordered store-then-use
subepisodes. They share one isolated memory scope and one
14-call/4096-generated-token ledger; both must strictly succeed. An instrument
failure in either makes the case null. The subepisodes are not counted as two
model attempts, so the stated primary and secondary totals remain unchanged.

The checked-in development, validation, sentinel, retained, and adversarial
manifests contain 88, 11, 11, 220, and 22 cases respectively: 352 total. They
replay exactly and share no instance IDs or semantic structures; no entity key
or entity surface value repeats anywhere in the suite. Verify them without
model or network
access:

```powershell
python -m bench.generate_manifests --verify
```

These are frozen benchmark inputs, not outcomes. S6C compiles them into paired
primary conditions plus separately labeled descriptives. Retained execution for
this retired suite is permanently blocked; its S8/S9 path is unreachable.

Read-only native preflight and disposable engineering runs:

```powershell
python -m bench.s6_preflight
python -m bench.s6_run --split development --max-cases 1 --allow-dirty
python -m bench.s6_rules_reference --split development
```

Omit `--allow-dirty` for a gate candidate. `bench/s6_run.py` rejects the
retained split regardless of CLI arguments in S6C. Its default conditions are
only `native_tools` and `harness_full`; descriptive conditions must be selected
explicitly with `--condition`.

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

F0 must confirm native transport and recognized options on the Lenovo before S4.
It saves exact payloads, captures template/context state, requires `think=false`,
and proves per-key option recognition under protocol v2.

Protocol v1 required the server to *reject* the unknown option
`brick_f0_unknown_option`. Ollama never promised that and 0.32.5 ignores unknown
names, so v1 failed on correct server behavior; its bundle stays immutable and
failed. Protocol v2 instead proves recognition positively: each frozen option
name, given a deliberately invalid value type, must return a 4xx/5xx response
that names the key and states its declared type. This identifies a parsed key
rather than accepting a generic server error, and it holds at the frozen values
— including the neutral `top_p=1.0`, `min_p=0` and `repeat_penalty=1.0` where an
output differential cannot discriminate at all. The same invalid value under an
unknown name is recorded separately; acceptance is a diagnostic typo hazard,
while rejection is also permitted. Unknown-name behavior is not a gate.

This proves recognition and declared type for the exact production option map,
not the numerical behavior of any sampler. Brick additionally owns the request
contract: every request is validated against exact keys, types, finite values and
frozen values before it reaches the network. F0 selected the exact Ollama
runtime and model digests; S6 now binds its passed attestation hash, Ollama
0.32.5, and the exact primary model digest.

## Preparing the Lenovo host

For an operator or coding agent setting up the benchmark host for the first time.
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md) states these same conditions as
acceptance criteria; the steps below are how you satisfy them. The probe
fail-closes on every one, so a missed step appears as a gate failure rather than
a quietly wrong result.

**Do not modify the repository.** The gate requires `git status --short` to print
nothing, so editing any tracked file, documentation included, voids the run.
Install tools and change Windows settings freely; leave the worktree alone.

### 1. Confirm a native ARM64 host and shell

```powershell
$env:PROCESSOR_ARCHITECTURE
[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
```

The first must print `ARM64`. `AMD64` means an emulated x64 shell: open Windows
PowerShell (ARM64) instead. This is the most common setup mistake and it later
surfaces as a confusing probe error rather than an obvious environment problem.

### 2. Install native ARM64 Python and Ollama

Install the **ARM64** builds, not the x64 installers: CPython for Windows ARM64
from python.org, and Ollama for Windows ARM64 from <https://ollama.com/download>.
Then verify:

```powershell
python -c "import platform; print(platform.machine())"
ollama --version
```

`platform.machine()` must print `ARM64`. The probe rejects the host if either
process runs as x64 under emulation. Both installers need UAC approval, so an
agent cannot complete this step unattended.

### 3. Start the Ollama server

```powershell
ollama serve
```

Leave it running in its own window. If it reports that the address is already in
use, the installed Ollama app is already serving and no action is needed; confirm
with `ollama list`. The probe measures an Ollama model-runner descendant process,
not only the listener, so the server must actually be serving.

### 4. Set power and performance

Connect AC power, then select **Settings > System > Power & battery > Power mode
> Best Performance**, or activate a High/Ultimate Performance scheme:

```powershell
powercfg /setactive SCHEME_MIN
```

Disable sleep for the duration. The probe records the active scheme GUID.

### 5. Leave Defender and Windows Search enabled

```powershell
Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled
Get-Service WSearch
```

Both must be enabled and running. This is deliberate: the storage probe tests
publication while a real-time scanner and indexer can hold file handles. Do not
disable them to produce a "clean" benchmark.

### 6. Check free space before pulling

```powershell
[math]::Round((Get-Volume C).SizeRemaining / 1GB, 1)
```

The gate requires 30 GiB free **after** pulling roughly 12 GB of models, so start
with about **42 GiB free**. Free space first; running out mid-pull wastes the
download.

### 7. Choose the output path

A short local NTFS path outside OneDrive, such as `C:\BrickRuns`. Not a network
drive, synced folder, substituted drive, or removable volume.

### 8. Resolve the candidate commit

Use the commit you were given; it must already be pushed.

```powershell
git fetch origin
git switch --detach <C>
git status --short
python -m bench.f0_probe fingerprint
```

`git status --short` must print nothing. If you were given no commit, use
`origin/main` and record `git rev-parse HEAD` so the evidence traces to an exact
tree.

### Expected duration

Roughly 45 to 90 minutes: about 12 GB of model downloads, native tool-calling and
throughput probes across three models, and 200 storage publication cycles
including injected process exits and held file handles. Do not run other heavy
workloads on the machine while it executes.

### If the gate fails

Send the full console output and **do not fix it**. A failure is the result: it
reports that something the design assumed is untrue, and patching around it
produces evidence for a tree nobody reviewed.

| Symptom | Likely cause |
|---|---|
| Host or process rejected | x64 shell, Python, or Ollama under emulation |
| Model pull or metadata failure | a `qwen3.5:*-q4_K_M` tag does not exist as assumed |
| Native tool conformance failure | this model or Ollama build lacks the function-call transport |
| Option recognition failure | a frozen key did not produce a 4xx/5xx, key-specific, type-specific error |
| Runner attestation failure | the real inference runner is not native ARM64, or its identity/process set changed mid-probe |
| Throughput below floor | CPU-only inference too slow for 4B (5 tok/s) or 9B (3 tok/s) |
| Free-space failure after pulls | started with less than about 42 GiB |
| Storage or held-handle failure | marker-last publication does not hold on this Windows configuration |
| Dirty worktree | a tracked file was edited; reset and rerun |

A 4B failure stops the research design. A 2B or 9B failure removes only that
descriptive replication. A storage failure means the S4 evidence store needs
redesign before it is built.

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

## Retired S7 sample and analysis

The now-terminal S7 protocol ran 44 score-masked development pairs and selected
sample size using runtime only:

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

### D0 correction execution boundary

D0-A completed 88 logical cells but was instrument-invalid: three cells retained
an Ollama HTTP 500 after the frozen retry. It was not graded and did not create
a runtime decision. Protocol `1.0.2` consumed reserved D0-B as the sole
correction cohort. D0-B run `s7-d0b-20260804T025010Z` completed all 44 pairs/88
attempts from clean CI-green commit `b756843`. The commands below are retained
as exact provenance; do not rerun D0-B or create another cohort.

```powershell
python -m pip install -r requirements-analysis.txt
python -m bench.s7_preflight
python -m bench.s7_run --run-id s7-d0b-20260804T025010Z
```

The run command schedules exactly 44 D0-B pairs/88 primary attempts and cannot
select one instance, truncate the cohort, grade an attempt, or run inactive
D0-A. Its
console summary excludes success. Do not inspect final state, actions, model
responses, or reconstruct outcomes while the runtime decision is pending.

After all 88 logical cells are instrument-valid, commit the runtime-only sample
decision to a new directory:

```powershell
python -m bench.s7_decision `
  --runs-root C:\BrickRuns\s7 `
  --run-id s7-d0b-20260804T025010Z `
  --output C:\BrickRuns\s7-decisions\s7-d0b-20260804T025010Z
```

Only after that marker-last decision verifies may the direction-blind audit
grade D0 in memory:

```powershell
python -m bench.s7_floor_audit `
  --runs-root C:\BrickRuns\s7 `
  --run-id s7-d0b-20260804T025010Z `
  --decision C:\BrickRuns\s7-decisions\s7-d0b-20260804T025010Z `
  --output C:\BrickRuns\s7-audits\s7-d0b-20260804T025010Z
```

The audit emits only eight-condition-combined successes per family. A floor or
ceiling flag forbids the S7 freeze. D0-B is the only reserved correction cohort,
so any instrument fault or floor/ceiling flag stops the experiment before S8.
An audit with no flags permits protocol freeze but does not unlock retained
execution.

The sealed decision selected 20 cases per family, but the audit raised ceiling
flags for `cal_brief`, `email_reply`, and `pptx_from_email` and a floor flag for
`xlsx_from_email`. It emitted no condition-specific score or directional effect.
The flagged branch is terminal: no D0-C, S7 freeze, S8 handoff, or retained run
is permitted under this protocol.

### Post-S7 successor design boundary

The terminal, condition-blind postmortem is tracked at
`evidence/s7/d0b-direction-blind-postmortem.json`. It consumes only the tracked
runtime decision, direction-blind audit, and public development manifest; it
does not open raw attempts or compute a condition contrast. Rebuild and verify
the complete offline successor scaffold with:

```powershell
python -m bench.s7_postmortem
python -m pytest tests/test_next_study.py -q
```

`bench/next_study_design.json` is deliberately `offline_design_only`. Its fresh
suite, repeated-trial calibration, primary, and larger sentinel are proposed
counts, not an execution protocol. Every execution gate, live model execution,
and retained execution remains false. The research basis and unresolved gates
are documented in `NEXT_STUDY_RESEARCH_BASIS.md`.

## Unexecuted historical descriptive matrix

These descriptives were permitted only after sealing the S7 primary. That
primary is now unreachable, so none of these commands may run:

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

The implementation and current-source rationale for S6C are recorded in
[`S6C_RESEARCH_BASIS.md`](S6C_RESEARCH_BASIS.md). Sources inform design; only
Brick's executable contracts, preflight, and immutable evidence decide whether
the local instrument passes.
The S7 integrity rationale and primary sources are recorded in
[`S7_RESEARCH_BASIS.md`](S7_RESEARCH_BASIS.md).
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

# Brick

Brick is an **experimental, local agent-harness research scaffold**. The
implemented runtime has three domain packs:

- `office_demo@0.1.0`, the legacy synthetic inbox, calendar, messaging,
  reminder, PPTX and XLSX fixture; and
- `counter_demo@0.1.0`, a deliberately small structural portability fixture;
  and
- `brix_followup_synthetic@0.1.0`, a fictional no-network lead-follow-up slice.

The raw and scaffolded loops call a user-supplied local Ollama server. Office
email, calendar, chat and reminder actions mutate simulated state only; Office
document tools do create real files in the attempt workspace.

This is not a production assistant and is not connected to Brix systems. No
benchmark results, training corpora, adapters, or model weights are shipped.
`counter_demo` demonstrates that a second pack can be wired through the
surfaces; it is not evidence of generalization or performance. The proposition
that orchestration improves model tool use remains an untested hypothesis.

The latest release is `v0.11.0` (S6C fair-condition runtime and scheduler),
preceded by `v0.10.0` (S6G), `v0.9.0` (S5W), `v0.8.0` (S5), `v0.7.0` (B0),
`v0.6.0` (S1R), `v0.5.0` (S4), and `v0.4.0` (F0/Q0).
The required native-Windows Lenovo F0 evidence
exists and the gate passed, establishing host and model feasibility only.
Commit `f12dd71` contains the subsequent independent verifier correction and is
pushed with required CI green. Native S4 acceptance, S1R, and B0 are released.
S5 is released with strict versioned graders. S6G freezes 341 replayable,
split-isolated fictional office instances across 11 logical families. S6C
compiles them into shared native-tool primary conditions, descriptive
ablations, a raw-JSON lower bound, a model-free rules reference, and a
restartable disposable scheduler. Retained execution remains mechanically
disabled, D0/S7 is next, and no confirmatory effect estimate exists.
The Mac is a source-development and
offline-test host only.

Annotated tags and bound evidence are release-authoritative. The tagged S4
release commit `R` adds only `evidence/s4/v0.5.0.json` and intentionally retains
this candidate-scoped prose. An immediate docs-only descendant `D` promotes
changelog and current status after the tag; `D` is not part of `v0.5.0`.

## Read first

- [`CLAUDE.md`](CLAUDE.md) is the short orientation for a coding agent or new
  contributor: hard rules, current position, the F0 gate, and remaining stages.
- [`EXECUTION.md`](EXECUTION.md) is the operational handbook: current state,
  schedule, hard checkpoints, cut order, and the per-session protocol.
- [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) defines the canonical evidence,
  research, product, and governance rules.
- [`BRIX_DISCOVERY.md`](BRIX_DISCOVERY.md) records the non-sensitive Brix
  discovery boundary and the relationship between the research and product
  repositories.
- [`PROJECT_SETUP.md`](PROJECT_SETUP.md) is the canonical staged
  implementation and research plan.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) describes what is implemented, what is
  simulated, and the current trust boundaries.
- [`bench/README.md`](bench/README.md) describes the benchmark and why current
  outputs are exploratory.
- [`FIXES.md`](FIXES.md) is the code-level defect and remediation register mapped
  to the canonical gates.
- [`webui/README.md`](webui/README.md) describes the local Agent Lab demo.
- [`training_scripts/README.md`](training_scripts/README.md) describes the
  experimental training package.
- [`CHANGELOG.md`](CHANGELOG.md) records released repository changes; it is not
  a claim that the research or product gates passed.

## Layout

```text
harness/            runtime, grading, agent-loop and tool-registry contracts
domains/            versioned office and counter domain packs
bench/              domain-aware tasks, graders, runner and report
agents/             per-model configs and one shared CLI runner
webui/              loopback development console
finetune/           live-harness data generator
training_scripts/   separate LoRA training package
tests/              offline characterization and architecture tests
```

The public runtime boundary is `RunConfig`, `RunHooks`, `ActionPolicy`,
`AttemptContext`, `ToolRegistry`, and `DomainPack`. `ToolRegistry` exposes
defensive copies of tool specifications, and domain callbacks have a validated
shape. A pack must classify every registered tool's effect explicitly, and an
attempt rejects a policy missing any active tool. These are software
interfaces, not authentication, process isolation,
transactionality, provenance, or safety guarantees. Domain packs are trusted
Python imports, and a domain version is a label rather than a content digest.

## Experimental conditions

The released `raw` condition is a minimal prompt-only JSON loop. The released
`harness` condition adds examples, constrained JSON output, parser/argument
repair, validation feedback, normalization, planning, duplicate suppression, a
model verifier and memory injection.

The benchmark defaults both conditions to the same 14-successful-call ceiling,
measured relative to each attempt's starting LLM-call count. This does **not**
make inference cost equal: prompts, output limits, tokens, latency and the
purposes of calls differ. `raw` is a minimal lower-bound baseline, not a
representative native function-calling implementation.

These are legacy exploratory conditions, not the retained comparison. The
planned primary compares `native_tools` with `harness_full` through the same
Ollama native function-call transport, chat template, model digest, tool schemas,
validators and opportunity limits.

## Install and verify

The supported Python range is 3.9 through 3.13. Direct runtime dependencies are
pinned in `pyproject.toml` and `requirements.txt`; `requirements-lock.txt`
pins transitive versions but has no package hashes. Installation may therefore
require an available package index or populated cache and is not a
cryptographically reproducible supply-chain boundary.

```bash
python -m pip install -r requirements-test.txt
python -m pytest
```

The test suite is designed to run without Ollama. Passing it characterizes the
implemented cases; it does not complete the S4 native gate or validate a
retained result. Three required S4 symlink cases currently remain skipped on
this Lenovo because Windows Developer Mode is disabled, and previously also
because the S4 test root was unbounded against the Windows 248-character
directory limit; the native gate
permits no such skip.

The released F0 gate was a separate live-model operation. Its passing bundle is
retained and bound to `v0.4.0` through the candidate/release attestation defined
in [`PROJECT_SETUP.md`](PROJECT_SETUP.md). First-time host setup remains in
[`bench/README.md`](bench/README.md#preparing-the-lenovo-host), and the exact
F0 commands remain in
[`bench/README.md`](bench/README.md#running-the-lenovo-f0-gate). The current S4
native commands are in
[`bench/README.md`](bench/README.md#native-windows-arm64-s4-gate); running the
offline suite on a Mac is not a substitute.

## Running the legacy benchmark for development

From this directory, with the required Python packages, Ollama and the selected
model tags already available:

```bash
python -m bench.run_bench \
  --domain office_demo \
  --models llama3.2:1b llama3.2:3b llama3.1:8b \
  --conditions raw harness \
  --outdir results-dev-001

python -m bench.report --outdir results-dev-001
```

The runner validates the selected domain, conditions, tasks and duplicate model
labels. Results are namespaced by domain and version. The reporter rejects
missing or malformed core records and duplicate identities, and withholds
raw-versus-harness deltas when task sets or recorded
tool/capability/call-budget surfaces are incompatible. Those checks do not cure
the known stale-artifact, resume, grader, isolation and provenance defects in
[`bench/README.md`](bench/README.md). Do not publish current scores, compare
them across code revisions, or reuse a development output directory.

The listed models also do not form a clean parameter-size experiment: the 8B
model is from a different Llama generation, and proposed larger models use
another family.

They are excluded from the retained matrix. The confirmatory candidate is
`qwen3.5:4b-q4_K_M`, resolved by immutable digest only after Lenovo F0 passes.
The 2B and 9B Qwen3.5 candidates are descriptive system replications, never a
causal size curve.

## Agent Lab

Agent Lab can be launched with:

```bash
python -m webui.server
```

or the platform launcher where supported. It exposes the available domain
packs, starts one agent subprocess and streams its events. The subprocess
provides lifecycle and crash/stop containment only; it is not a security
sandbox. S5W gives the loopback server a fresh 256-bit startup capability,
exact Host/Origin controls, bounded JSON mutations, bounded file/log/event
surfaces, and process-tree teardown. The browser launcher opens the capability
URL; use only that printed URL. These controls do not make Agent Lab a
production or multi-user service.

Some launchers and UI actions can install packages or pull model weights, so
the repository as a whole should not be described as offline.

## Safety

Q0, released in `v0.4.0`, removes the legacy `--root`, `--shell`, `--yolo`,
`--with-domain`, and `--with-office` capabilities from supported CLI, web and
configuration surfaces. Legacy spellings are rejected before output creation,
model access, network access or mutation. Brick retains domain-scoped synthetic
tools and attempt-owned Office artifact writers; it does not expose a supported
general filesystem or shell.

`ActionPolicy` remains a classification/callback seam, not an operating-system
sandbox or authorization system. Absence of a callback denies. S5W's replacement
operator channel is deliberately narrow and binds a one-shot decision to the
current `(run_id, confirmation_id, nonce)`; it is not generic stdin.

Do not place real Brix member, payment, email or document data in this
repository. Authentication, authorization, tenant isolation, privacy controls,
retention, audit policy and real provider integrations have not been built.

For demonstrations, use only synthetic data in a newly created disposable
directory.

## Current boundary and next milestone

F0/Q0 passed on the native Lenovo host and is released as `v0.4.0`; this records
feasibility, not a benchmark effect. The verifier correction in `f12dd71` is
pushed and CI-green without changing the retained bundle. At candidate `C`,
S4's production marker-last store and attestor are implemented, while clean
candidate CI, a native Windows ARM64 run with zero required S4 skips, and the
candidate-bound attestation remain required rather than claimed.

Release descendant `R` may add only that regular attestation file. The annotated
tag and bound evidence—not this candidate-scoped paragraph—authoritatively establish
whether S4 passed and `v0.5.0` was released. Immediately after the tag,
docs-only `D` promotes current status without moving the tag. Stop for review
before S5, which has not started. B0 is released as `v0.7.0`.

No retained matrix begins before the marker-last store, repaired runtime, strict
graders, independent generators, shared native transport, score-masked
development run and zero-invalid sentinel pass. Fine-tuning, external benchmark
integration and real Brix product work are outside this milestone.

The canonical public repository is
[`EdgeHarness/Brick-Agent-Harness`](https://github.com/EdgeHarness/Brick-Agent-Harness).

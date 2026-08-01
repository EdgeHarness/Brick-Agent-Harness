# Brick

Brick is an **experimental, local agent-harness research scaffold**. The
implemented runtime has two domain packs:

- `office_demo@0.1.0`, the legacy synthetic inbox, calendar, messaging,
  reminder, PPTX and XLSX fixture; and
- `counter_demo@0.1.0`, a deliberately small structural portability fixture.

The raw and scaffolded loops call a user-supplied local Ollama server. Office
email, calendar, chat and reminder actions mutate simulated state only; Office
document tools do create real files in the attempt workspace.

This is not a production assistant and is not connected to Brix systems. No
benchmark results, training corpora, adapters, or model weights are shipped.
`counter_demo` demonstrates that a second pack can be wired through the
surfaces; it is not evidence of generalization or performance. The proposition
that orchestration improves model tool use remains an untested hypothesis.

The latest release is `v0.4.0`. The required native-Windows Lenovo F0 evidence
exists and the gate passed, establishing host and model feasibility only. The Mac
is a source-development and offline-test host only.

## Read first

- [`CLAUDE.md`](CLAUDE.md) is the short orientation for a coding agent or new
  contributor: hard rules, current position, the F0 gate, and remaining stages.
- [`EXECUTION.md`](EXECUTION.md) is the operational handbook: current state,
  schedule, hard checkpoints, cut order, and the per-session protocol.
- [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) defines the canonical evidence,
  research, product, and governance rules.
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
harness/            runtime contracts, agent loops and tool registry
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
implemented cases; it does not complete the pending Lenovo F0 gate or validate a
retained result.

The Lenovo gate is a separate, live-model operation. First-time host setup is in
[`bench/README.md`](bench/README.md#preparing-the-lenovo-host), and the exact
clean-commit run and verification commands follow it in
[`bench/README.md`](bench/README.md#running-the-lenovo-f0-gate). A passing bundle
must be retained externally and bound to the eventual `v0.4.0` tag through the
candidate/release attestation in [`PROJECT_SETUP.md`](PROJECT_SETUP.md); running
the offline suite on this Mac is not a substitute.

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
sandbox. The web server is an unauthenticated loopback development interface
without CSRF/origin protection or production access control.

Some launchers and UI actions can install packages or pull model weights, so
the repository as a whole should not be described as offline.

## Safety

Unreleased Q0 removes the legacy `--root`, `--shell`, `--yolo`,
`--with-domain`, and `--with-office` capabilities from supported CLI, web and
configuration surfaces. Legacy spellings are rejected before output creation,
model access, network access or mutation. Brick retains domain-scoped synthetic
tools and attempt-owned Office artifact writers; it does not expose a supported
general filesystem or shell.

`ActionPolicy` remains a classification/callback seam, not an operating-system
sandbox or authorization system. In Q0, absence of a callback denies, and Agent
Lab exposes no browser/stdin confirmation channel.

Do not place real Brix member, payment, email or document data in this
repository. Authentication, authorization, tenant isolation, privacy controls,
retention, audit policy and real provider integrations have not been built.

For demonstrations, use only synthetic data in a newly created disposable
directory.

## Current boundary and next milestone

F0/Q0 is the authorized active stage. Source, tests and probes can be prepared
on development hosts, but `v0.4.0` cannot be released until the native Lenovo
model, runtime, resource and Windows storage gates pass. S4 follows F0/Q0; S1R
follows S4; the entirely synthetic Brix vertical slice follows S1R.

No retained matrix begins before the marker-last store, repaired runtime, strict
graders, independent generators, shared native transport, score-masked
development run and zero-invalid sentinel pass. Fine-tuning, external benchmark
integration and real Brix product work are outside this milestone.

The canonical public repository is
[`EdgeHarness/Brick-Agent-Harness`](https://github.com/EdgeHarness/Brick-Agent-Harness).

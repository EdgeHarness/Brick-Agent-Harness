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

## Read first

- [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) defines the canonical evidence,
  research, product, and governance rules.
- [`PROJECT_SETUP.md`](PROJECT_SETUP.md) is the canonical gated
  implementation plan and gate taxonomy.
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
harness/            runtime contracts, agent loops, registry and file overlay
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

`raw` is a minimal prompt-only JSON loop. `harness` adds examples, constrained
JSON output, parser/argument repair, validation feedback, normalization,
planning, duplicate suppression, a model verifier and memory injection.

The benchmark defaults both conditions to the same 14-successful-call ceiling,
measured relative to each attempt's starting LLM-call count. This does **not**
make inference cost equal: prompts, output limits, tokens, latency and the
purposes of calls differ. `raw` is a minimal lower-bound baseline, not a
representative native function-calling implementation.

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

The test suite is designed to run without Ollama. Passing tests characterize
the implemented cases; they do not pass the G0 or R1 acceptance gates.

## Running the current benchmark

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

Do not use `--root`, `--shell` or `--yolo` on valuable files. The real-file
tools rely on lexical path checks, can follow symlinks outside the chosen root,
accept overly broad roots, and expose arbitrary PowerShell when enabled.
`ActionPolicy` and confirmation are classification/callback seams, not an
operating-system sandbox or authorization system.

Do not place real Brix member, payment, email or document data in this
repository. Authentication, authorization, tenant isolation, privacy controls,
retention, audit policy and real provider integrations have not been built.

For demonstrations, use only synthetic data in a newly created disposable
directory.

## Current boundary and next milestone

The S0–S3 implementation packages in [`PROJECT_SETUP.md`](PROJECT_SETUP.md)
have code and offline tests, but package completion is not gate acceptance:
G0 and R1 are still partial and unpassed. S4 is the next planned implementation
package and requires a separate scope decision. The segmented plan in
`PROJECT_SETUP.md` is canonical; do not start a retained matrix before R1 and
R2 pass. Brix discovery remains a separate P0 track. Fine-tuning remains
blocked at R5 until a validated evaluation identifies a stable,
model-addressable failure.

The canonical public repository is
[`EdgeHarness/Brick-Agent-Harness`](https://github.com/EdgeHarness/Brick-Agent-Harness).
It currently has no owner-selected license, so no reuse license should be
inferred. Branch protection and cleanup of divergent legacy public copies are
also unresolved G0 owner actions.

# Brick

Brick is an **experimental local office-agent research scaffold**. It contains:

- a synthetic inbox, calendar, messaging and reminder world;
- raw and scaffolded agent loops that call a local Ollama server;
- genuine local PPTX/XLSX generation;
- 12 hand-authored benchmark tasks with programmatic graders;
- a local demonstration console;
- experimental LoRA data and training scripts.

It is not a production assistant and is not connected to Brix systems. Sending
email, adding calendar events, sending messages and setting reminders only
modify simulated Python/JSON state.

No benchmark results are committed. The proposition that orchestration may
improve small-model tool use remains a hypothesis.

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

## Layout

```text
harness/            agent loops, tool registry, simulator and file tools
bench/              tasks, graders, runner and descriptive report
agents/             per-model configurations and persistent demo state
webui/              loopback development console
finetune/           live-harness data generator
training_scripts/   separate LoRA training package
```

## Experimental conditions

`raw` is a minimal prompt-only JSON loop. `harness` adds examples, constrained
JSON output, parser/argument repair, validation feedback, normalization,
planning, duplicate suppression, a model verifier and memory injection.

Both conditions stop at the same 14-LLM-call ceiling in the benchmark. This
does **not** make their inference cost equal: prompts, output limits, tokens,
latency and the purposes of calls differ. `raw` is also a lower-bound baseline,
not a representative native function-calling implementation.

## Running the current benchmark

From this directory, with the required Python packages, Ollama and the selected
model tags already available:

```bash
python -m bench.run_bench \
  --models llama3.2:1b llama3.2:3b llama3.1:8b \
  --conditions raw harness \
  --outdir results-dev-001

python -m bench.report --outdir results-dev-001
```

The repository does not yet provide a root dependency lock or automated test
suite. The benchmark has known stale-artifact, resume, grader and provenance
defects documented in [`bench/README.md`](bench/README.md). Do not publish
current scores, compare them across code revisions, or reuse that development
output directory for another invocation.

The listed models also do not form a clean parameter-size experiment: the 8B
model is from a different Llama generation, and proposed larger models use
another family.

## Agent Lab

Agent Lab can be launched with:

```bash
python -m webui.server
```

or the platform launcher where supported. It serves a local browser console,
starts one agent subprocess and streams its events. The current web server is a
development interface with no authentication, CSRF/origin protection or
production access control.

Some launchers and UI actions can install packages or pull model weights, so
the repository as a whole should not be described as offline.

## Safety

Do not use `--root`, `--shell` or `--yolo` on valuable files. The real-file
tools rely on lexical path checks, can follow symlinks outside the chosen root,
accept overly broad roots, and expose arbitrary PowerShell when enabled.
Confirmation is not an operating-system sandbox.

Do not place real Brix member, payment, email or document data in this
repository. Authentication, authorization, tenant isolation, privacy controls,
retention, audit policy and real provider integrations have not been built.

For demonstrations, use only synthetic data in a newly created disposable
directory.

## Intended next milestone

Follow the canonical sequence in [`PROJECT_SETUP.md`](PROJECT_SETUP.md):
complete G0 repository containment, R1 instrument validity, and R2 protocol
freeze before a retained matrix. Brix discovery begins separately at P0 and
advances through product gates P1–P4. Fine-tuning remains blocked at R5 until a
validated evaluation identifies a stable model-addressable failure.

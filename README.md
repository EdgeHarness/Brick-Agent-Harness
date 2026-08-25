# Brick

An **experimental local agent-harness research scaffold**. It tests one
hypothesis: whether an explicit harness makes a small tool-using local model
better at finishing real tasks. That hypothesis is **untested**. No benchmark
result, training corpus, adapter or model weight is shipped here.

This is not a production assistant and is not connected to Brix systems.

Two parts: a domain-independent harness core, and versioned domain packs that
plug into it. This repository is the engine;
[Final-Agent-8B](https://github.com/EdgeHarness/Final-Agent-8B) is its
Snapdragon shipping instance and no longer develops the engine itself.

| pack | what it is |
|---|---|
| `office_demo@0.1.0` | synthetic inbox, calendar, messaging, reminders, PPTX and XLSX |
| `counter_demo@0.1.0` | a deliberately tiny pack, to show a second one wires through |
| `brix_followup_synthetic@0.1.1` | a fictional, no-network lead-follow-up slice |

Both loops call a local Ollama server you supply. Email, calendar, chat and
reminder actions mutate simulated state only. Document tools do write real files
into the attempt workspace.

`counter_demo` proves a second pack fits the surfaces. It is not evidence of
generalization or performance.

## Read first

| | |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | orientation: hard rules, current position, remaining stages |
| [`docs/PROJECT_SETUP.md`](docs/PROJECT_SETUP.md) | canonical staged implementation and research plan |
| [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) | canonical evidence, research and governance rules |
| [`docs/EXECUTION.md`](docs/EXECUTION.md) | operational handbook and per-session protocol |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | what is implemented, what is simulated, trust boundaries |
| [`docs/FIXES.md`](docs/FIXES.md) | defect and remediation register, mapped to the gates |
| [`docs/BRIX_DISCOVERY.md`](docs/BRIX_DISCOVERY.md) | the non-sensitive Brix discovery boundary |
| [`bench/README.md`](bench/README.md) | the benchmark, and why current output is exploratory |
| [`CHANGELOG.md`](CHANGELOG.md) | released changes. Not a claim that any gate passed |

## Layout

```text
harness/            runtime, grading, agent-loop and tool-registry contracts
domains/            versioned domain packs
connectors/         fixed HubSpot MCP and Optix GraphQL adapters, off/unbound by default
mcp/                audited registry for other MCP subprocesses, off by default
bench/              tasks, graders, runner and report
agents/             per-model configs and one shared CLI runner
webui/              loopback development console
finetune/           live-harness data generator
training_scripts/   separate LoRA training package
tests/              offline characterization and architecture tests
```

The public runtime boundary is `RunConfig`, `RunHooks`, `ActionPolicy`,
`AttemptContext`, `ToolRegistry` and `DomainPack`. A pack must classify every
tool's effect explicitly, and an attempt rejects a policy that misses an active
tool. These are software interfaces, not authentication, isolation,
transactionality or safety guarantees. Domain packs are trusted Python imports.

## Install and verify

Python 3.9 through 3.13.

```bash
python -m pip install -r requirements-test.txt
python -m pytest
```

The suite needs no Ollama and no network. Passing it characterizes the
implemented cases. It does not complete the S4 native gate or validate any
result, and running it on a Mac is not a substitute for the native gate. Gate
commands live in [`bench/README.md`](bench/README.md).

Dependencies are pinned in `pyproject.toml` and `requirements.txt`;
`requirements-lock.txt` pins transitive versions but carries no hashes, so
installation is not a reproducible supply-chain boundary.

## Agent Lab

```bash
python -m webui.server        # or python -m webui.app for a desktop window
```

Pick a model and a domain, type a task, and watch the loop: the plan, each token
as it streams, every tool call with the arguments actually sent, and the
domain's own state updating beside it. The workspace panel is driven by whatever
sections a pack declares, so a new pack needs no UI work.

Use only the capability URL it prints. The loopback server takes a fresh 256-bit
capability per launch, with Host and Origin checks and bounded request, file and
event surfaces. The run subprocess gives lifecycle and stop containment, not a
security sandbox, and none of this makes Agent Lab multi-user or production.

Some launchers and UI actions install packages or pull model weights, so the
repository as a whole is not offline.

## Real accounts

Run options include a **real accounts** picker, off unless you tick something.
It supports two separate boundaries:

- normalized HubSpot and Optix tools in [`connectors/`](connectors/README.md):
  HubSpot uses its official remote MCP server; Optix uses fixed reviewed GraphQL
  documents;
- audited Gmail, Google Calendar, Outlook, and Teams subprocess MCP entries in
  [`mcp/`](mcp/ADDING-A-CONNECTOR.md).

Normalized connectors require Python 3.10 or newer and operator-managed
credentials in the OS keyring. Core Brick remains Python 3.9 compatible. The
checked-in HubSpot and Optix bindings are unbound, so neither can reach an
account before authenticated sandbox discovery and installation of a reviewed
operator-local binding. The Brix HubSpot lead profile exposes exactly four CRM
reads and no HubSpot write, even if the run mode is `live`.

Enabling one is a deliberate departure from the synthetic-only boundary below.

- Model inference stays on the local backend.
- The **tool calls** do not stay local. A CRM read sends its query to the
  selected provider and returns the requested business fields. Do not enable one
  during a demonstration whose claim is that nothing leaves the machine.
- `draft` mode drops every tool explicitly declared to notify or invite;
  `read_only` drops all writes; `live` exposes only reviewed writes.
- Every world-changing call is classified `external_write` and is refused unless
  an operator confirms it, because absence of a callback denies.
- Real-account runs use run-only memory and persist only minimal operation
  metadata, not their task, transcript, observations, or answer.
- Dynamic provider catalogs are never given directly to the model. Catalog,
  operation, account, and schema drift fail closed.
- `bench/` never imports the bridge, so the comparison is unaffected.

No benchmark evidence gate covers connectors and no gate result depends on one.
Use only developer/sandbox accounts until Brix explicitly approves production
access. See [`connectors/README.md`](connectors/README.md) for the staged rollout.

## Safety

Q0 removed the `--root`, `--shell`, `--yolo`, `--with-domain` and
`--with-office` capabilities from every supported surface, and legacy spellings
are rejected before any output, model access, network access or mutation. Brick
has domain-scoped synthetic tools and attempt-owned document writers. It exposes
no supported general filesystem or shell.

`ActionPolicy` is a classification and callback seam, not an OS sandbox or an
authorization system. Absence of a callback denies. The operator channel binds
one decision to one `(run_id, confirmation_id, nonce)`; it is not generic stdin.

Do not put real Brix member, payment, email or document data here.
Authentication, tenant isolation, privacy controls, retention and audit policy
have not been built. For demonstrations use synthetic data in a fresh
disposable directory.

## Where the research stands

F0/Q0 passed on the native Lenovo host, which records host and model
feasibility and nothing about effect. S4, S1R, B0, S5, S5W, S6G and S6C are
released. D0-A was instrument-invalid, D0-B completed but its direction-blind
audit raised four flags, and **S7 is terminal with no condition comparison and
no confirmatory estimate**.

The successor is offline-qualified but cannot make a live call yet: it needs an
exact clean commit, Linux and native Windows reproduction, and a separately
authorized score-masked shakeout. See
[`bench/NEXT_STUDY_IMPLEMENTATION.md`](bench/NEXT_STUDY_IMPLEMENTATION.md).

Annotated tags and bound evidence are release-authoritative. Never infer gate
status from this file.

The canonical public repository is
[`EdgeHarness/Brick-Agent-Harness`](https://github.com/EdgeHarness/Brick-Agent-Harness).

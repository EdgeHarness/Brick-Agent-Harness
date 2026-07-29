# Architecture and current limitations

This document describes the code that exists in this repository. It deliberately
separates implemented behavior from proposed work.

## Status

Brick is currently:

- a synthetic office-state simulator;
- two experimental agent loops over a shared Python tool registry;
- a small, hand-authored benchmark with programmatic graders;
- a local demonstration UI;
- experimental LoRA data-generation and training scripts.

Brick is **not** currently:

- a production office assistant;
- connected to Brix email, calendars, messaging, rooms, documents or billing;
- a secure filesystem or shell sandbox;
- a transactional room-booking service;
- an access-controlled document-retrieval system;
- supported by committed benchmark results or a validated statistical study.

The simulator can create genuine `.pptx` and `.xlsx` files. Its inbox,
calendar, sent mail, messages and reminders are Python data structures saved to
JSON; they do not communicate with real services.

The research proposition that orchestration may improve small-model tool use is
a **hypothesis**, not a result. No benchmark results are committed.

## Repository map

```text
harness/
  llm.py              Ollama chat client and usage counters
  model_router.py     optional role-to-model routing; adapter fields are metadata
  world.py            synthetic inbox/calendar/message/reminder state
  office.py           local PPTX/XLSX creation and reading
  memory.py           append-only JSONL memory and keyword-overlap retrieval
  tools.py            the default 14-tool process-global registry
  fs_tools.py         optional real-filesystem and PowerShell tools
  agent.py            raw and harness agent loops

bench/
  tasks.py            12 fixed synthetic tasks and their graders
  grade.py            Office-file and state inspection helpers
  run_bench.py        model × condition × task runner
  report.py           descriptive aggregation

agents/
  _shared/            shared runner source
  1b|3b|8b|14b|32b/  duplicated runners plus model configuration and state dirs

webui/
  server.py           loopback HTTP/SSE server and subprocess controller
  runner.py           event-emitting harness runner
  static/             index.html, style.css and app.js

finetune/             generator tied to the live harness
training_scripts/     separate training package and frozen prompt/data copy
```

`webui/static/app.js` exists in the current tree. Older notes claiming it is
missing, or claiming the dashboard is untracked, are obsolete.

## Execution surfaces

| Surface | Entry point | State | Important boundary |
|---|---|---|---|
| Benchmark | `python -m bench.run_bench` | new in-memory `World` per task; reused artifact directory and shared memory per model/condition | experimental; attempts are not isolated and no real services are called |
| Per-model CLI | `agents/<size>/run.ps1` or `run_agent.py` | persistent synthetic state and memory | optional filesystem/shell mode is unsafe for valuable data |
| Agent Lab | `python -m webui.server` or launcher | same per-agent state through a child process | local demo; no authentication or browser-origin protection |
| Training | `training_scripts/run.sh` and related scripts | local/HPC files | may download models or source unless assets are staged |

Only the benchmark invokes `run_raw()`. The agent CLI and Agent Lab invoke
`run_harness()`.

## Ollama client and routing

`harness.llm.LLM` calls Ollama's `/api/chat` endpoint. The runner asserts that
the configured endpoint contains `127.0.0.1` or `localhost`. Requests use
temperature `0.0`, seed `42`, a configurable context size and a call-specific
output-token limit.

Those settings improve repeatability but do **not** prove bit-for-bit
reproducibility across Ollama versions, model digests, quantizations, hardware,
drivers or execution modes. Model tags and runtime provenance are not currently
recorded by the benchmark.

The client records call count, prompt tokens, output tokens and model-reported
duration. The loop stops at a common 14-call ceiling in benchmark mode.
Equalizing call count does not equalize tokens, FLOPs, latency or energy:
the harness adds planning and verification calls, uses different output limits,
and supplies a longer prompt.

`ModelRouter` can dispatch the `driver`, `router` and `verifier` roles to
configured models. A `deep` role is configured by default but no current agent
path calls it. The optional adapter value is logged only; it is not applied by
the Ollama client.

## Synthetic world

`World` starts with ten fixed emails and seven fixed calendar events. The
benchmark uses a fixed date, Monday 2026-07-20. Each ordinary benchmark task
constructs a new in-memory world. Agent folders use `persistent=True`, which
loads and rewrites `workspace/state.json`.

The following are simulations:

- `send_email` appends to `sent_emails`;
- `add_event` appends to `events`;
- `send_message` appends to `messages`;
- `set_reminder` appends to `reminders`.

`add_event` verifies only date/time syntax and that the end string sorts after
the start string. It does not implement room resources, conflict rejection,
capacity, opening hours, recurrence, cancellation, provider synchronization,
idempotency or concurrent booking. It must not be represented as a Brix room
booking engine.

Date and time checking is weaker than its descriptions imply. The current
regular expressions accept syntactically shaped but impossible values such as
`2026-99-99` and `99:99`. Normalization rejects some impossible time inputs,
but direct raw calls reach the world validator.

Snapshots are ordinary JSON rewrites without locking or atomic replacement.
Two writers to the same persistent agent folder are not supported.

## Office files

`harness.office` uses `python-pptx` and `openpyxl` to create genuine Office
files inside `World.files_dir`. Model-provided filenames are reduced to their
basename and given the expected extension, which prevents a filename from
escaping that directory through ordinary path components.

This is real local file output, but it is not a document-management system.
There is no transactional rollback, antivirus scanning, file ownership model or
concurrent writer coordination.

## Tool registry and validation

`harness.tools.TOOLS` is a process-global dictionary. The default registry has
14 tools covering synthetic email/calendar/comms, Office files, memory,
`think`, and `done`.

`validate_call()` is a **shape check**, not complete schema validation. It
checks:

- whether the tool name exists;
- whether required keys are present and non-empty;
- whether unknown keys are present.

It does not generally enforce the advertised Python/JSON type, nested
structure, email format, date validity, time range or other business
constraints. Executors and `World` add a small amount of validation, but there
is no single typed contract.

`execute()` converts tool exceptions into observations so an episode can
continue. This prevents a tool failure from crashing the loop, but it also means
tool implementation defects can be recorded as ordinary model-facing errors.

## Agent loops

### Raw condition

`run_raw()`:

1. provides tool descriptions without examples;
2. asks for one JSON object;
3. uses strict JSON parsing after optional code-fence stripping;
4. executes the requested tool;
5. returns the observation to the model;
6. accepts `done` or stops when the call ceiling is reached.

This is a deliberately minimal prompt-only JSON baseline. It is **not** a
representative native function-calling baseline and should not be described as
the best ordinary way to wire a model to tools.

### Harness condition

`run_harness()` adds:

- one example in each tool description;
- Ollama JSON-constrained output;
- lenient extraction and trailing-comma removal;
- fuzzy parameter repair and top-level argument lifting;
- pre-execution shape feedback;
- date/time normalization;
- a planning call;
- duplicate-call suppression and context pruning;
- up to two verifier rounds;
- keyword-matched memory injection.

These are bundled in one treatment. The current benchmark cannot attribute a
score change to any individual mechanism without preregistered ablation
conditions.

### Parser limitation

`parse_lenient()` counts `{` and `}` characters without tracking JSON string
state. A brace inside a quoted value can end extraction at the wrong point.
Leniency is useful error recovery, but it is not a standards-compliant streaming
JSON extractor.

### Repair limitation

`repair_args()` uses fuzzy string matching with a low cutoff to rename unknown
keys to missing required keys, then silently drops remaining unknown keys. This
can convert an uncertain write request into a valid but semantically wrong one.
For example, a poorly named field can be reassigned to an unrelated required
field. Fuzzy repair is therefore unsafe for mutation tools unless the result is
validated or explicitly approved.

### Plan limitation

The planner accepts only registered tool names, but its model-authored `what`
text is included in the next prompt. The plan is therefore tool-constrained, not
free of model-generated prose.

### Verifier limitation

The verifier receives the requested task and a summary of tool names,
arguments, success flags, and truncated details. It does not inspect returned
observations, Office file contents, authoritative state or unintended side
effects.

It also fails open: an exception or malformed verdict becomes
`complete = true`; only two incomplete verdicts can delay completion; and a
`done` call at the final call boundary can be accepted without a verifier call.
The verifier is advisory and must not be treated as an authorization or safety
gate.

### Transcript limitation

`Episode.transcript` records system text, task, model replies, feedback,
observations and selected notes. Tool action logs store tool names, arguments,
success flags and truncated results. Planner/verifier raw replies are not
retained as separate complete model-call records by the basic episode
transcript. “Full transcript” should therefore mean the episode notes that are
available, not a complete forensic inference trace.

## Memory and data trust

`MemoryStore` is append-only JSONL. Retrieval tokenizes the query and stored
facts, removes stopwords and ranks by token-set intersection.

Memory facts are written by the model and injected into the next system prompt
without:

- user approval;
- source or timestamp metadata;
- tenant/subject identity;
- trust labels;
- expiration or document version;
- deduplication;
- prompt-injection filtering;
- malformed-row recovery.

This is an experimental learning mechanism, not an authoritative knowledge
base. Runtime memory can contain private or poisoned content and should be
excluded from source control. A malformed JSONL line can also prevent the store
from loading.

## Optional real-filesystem and shell tools

`fs_tools.enable()` mutates the global tool registry for the current process.
Path strings are converted with `abspath` and checked with string-prefix
containment. This does **not** resolve symlinks or junctions, so an in-root link
may expose a path outside the intended root. Additional hazards include:

- a filesystem root such as `/` is accepted;
- the configured root itself can be resolved as `.`, including for deletion;
- the deny-list is hard-coded for one Windows installation and is ineffective
  on other platforms or relocated checkouts;
- missing confirmation callbacks approve actions by default;
- `--yolo` removes confirmations, including for shell commands;
- append operations do not ask before modifying an existing file;
- checks and later writes are vulnerable to filesystem races.

`run_command` launches arbitrary `powershell.exe` with its current directory set
to the configured root. A working directory is not a sandbox: the command may
access other paths, processes, credentials and the network. The command is also
Windows-specific.

Real-file mode must be treated as unsafe. It needs an OS-level sandbox or,
preferably for the Brix product, removal in favor of narrow allowlisted service
adapters and explicit approval for each external mutation.

`--with-office` does not redirect generated PPTX/XLSX files into the selected
real root; those tools still use the agent's synthetic workspace.

## Agent Lab

Agent Lab serves static HTML/CSS/JavaScript, launches one
`python -m webui.runner` child at a time, streams JSONL events over SSE, renders
workspace state, previews generated Office files and relays confirmations over
the child's standard input.

The child-process boundary reduces collisions among process-global registry and
hook settings. It does not create a security boundary.

The server binds locally, but it has no authentication, session-bound
capability token, CSRF defense, or Origin/Host allowlist. State-changing
endpoints accept JSON without enforcing `Content-Type`; model pulling is a
state-changing GET; confirmations are associated only with the current run; and
reset is not coordinated with an active child. A malicious web page or another
local process may be able to drive the server.

Additional current weaknesses include unchecked traversal in `/api/reveal`,
lexical path checks in static/workspace paths, symlink-following previews, and
stop behavior that terminates the wrapper but does not guarantee all descendants
or model work have stopped. Agent Lab is a local development console, not a
multi-user or production UI.

## Benchmark architecture

The benchmark currently defines 12 fixed tasks. It creates one task directory
per `(model, condition, task)`, runs an agent, invokes that task's grader,
appends a record to `results.json`, and later calculates descriptive means.

The current measuring instrument has known validity defects:

- task directories and generated files are reused without cleanup;
- memory is deleted before resume checks;
- graders can match values that are present but incorrectly associated;
- some checks are conditional, changing denominators;
- most graders do not penalize extra actions;
- grader failures are collapsed into model scores of zero;
- results are rewritten non-atomically;
- no benchmark/grader/code/model/hardware provenance is stamped;
- one memory file is shared across all tasks in a condition;
- task order is fixed;
- arbitrary condition names silently use the raw runner;
- no task variants, held-out templates or independent repetitions exist.

See [`bench/README.md`](bench/README.md) for the exact interpretation and
[`FIXES.md`](FIXES.md) for the remediation gates. Current results, if generated,
are exploratory and should not be published as evidence for the research
hypothesis.

## Training track

Two 1,200-row JSONL datasets and two generators are present. They are not
identical, contain substantial duplicate rows, and cover only five of the
fourteen default tools. There is no validation/test split or dataset card.

Repair conversations include an intentionally bad assistant call followed by a
correction. The current trainer places loss on every assistant turn, so it
trains both the error and the repair rather than solely teaching recovery.

The training workflow does not pin every external source revision. It can
download models and llama.cpp, and GGUF conversion failures are caught without
failing the overall script. Adapter serving is not integrated with the Ollama
agent path. This is an exploratory package, not a reproducible end-to-end
training result.

## Process-global configuration

The following are mutable globals:

| Global | Module | Typical mutator |
|---|---|---|
| `TOOLS` | `tools.py` | `fs_tools.enable()` / `restrict_to_files()` |
| `MAX_CALLS` | `agent.py` | CLI and web runner |
| `EXTRA_RULES`, `EXTRA_WRITE_TOOLS` | `agent.py` | real-file mode |
| `SIM_TODAY`, `SIM_TODAY_HUMAN` | `agent.py` | real-file mode |
| `_ROOT`, `_ALLOW_SHELL`, `_CONFIRM` | `fs_tools.py` | `enable()` |
| event/tool/stream hooks | `agent.py`, `tools.py`, `llm.py` | web runner |

This prevents safely running differently configured agents concurrently in one
process. The intended replacement is explicit immutable `RunConfig`,
`ToolRegistry` and domain policy objects passed through the call graph.

## Locality, privacy and production boundaries

Loopback Ollama inference is local. That does not imply that the entire
repository is offline or that data cannot leave the machine:

- model/source download scripts use the network;
- Agent Lab can request an Ollama model pull;
- arbitrary shell commands can use the network;
- a future integration would send data to its configured provider.

The repository has no identity, authorization, encryption, retention, deletion,
tenant isolation, audit-log policy, backup or incident-response layer. Do not
load real Brix member, payment, email or document data until those controls and
narrow provider scopes are implemented and reviewed.

## Safe extension principles

The following are target principles, not current guarantees:

1. Keep business invariants in deterministic services, not prompts or
   model-based verification.
2. Default to read-only scopes; approve every external mutation during pilots.
3. Give each run isolated state and immutable provenance.
4. Treat model output, retrieved documents and model-authored memory as
   untrusted input.
5. Measure strict workflow completion and harmful side effects alongside
   partial diagnostic scores.
6. Compare accuracy and safety against token, latency, compute and human-review
   cost.
7. Add new research conditions explicitly; never mix results from different
   task, grader or harness versions.

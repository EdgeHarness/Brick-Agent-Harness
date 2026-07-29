# Per-model research agents

These folders are thin launch configurations over
[`_shared/run_agent.py`](_shared/run_agent.py). They do not contain separate
agent implementations. They are not production assistants, and the model
labels are not performance claims.
No benchmark results are committed that establish which configuration is faster,
safer, or more reliable.

| folder | configured Ollama tag | model family |
|---|---|---|
| `1b/` | `llama3.2:1b` | Llama |
| `3b/` | `llama3.2:3b` | Llama |
| `8b/` | `llama3.1:8b` | Llama |
| `14b/` | `qwen2.5:14b` | Qwen |
| `32b/` | `qwen2.5:32b` | Qwen |

Only the 1B and 3B configurations are same-generation Llama 3.2 points. The 8B
configuration changes to Llama 3.1, and the 14B/32B configurations change to
Qwen 2.5. The five folders therefore do not form a clean parameter-size sweep.

## What actually runs

Without `--root`, each agent loads its configured domain (currently
`office_demo` in all five checked-in configs). `--domain NAME` overrides it.
The available packs are:

- `office_demo@0.1.0`: simulated office actions and real local Office files;
- `counter_demo@0.1.0`: a namespaced structural fixture, not a useful
  assistant or performance benchmark.

For office mode:

- inbox and calendar records are hardcoded fixtures;
- “sending” email or chat, and setting a reminder, only updates local JSON state;
- reminders are not delivered and nothing is sent to a real person or service;
- PowerPoint and Excel tools create real `.pptx` and `.xlsx` files under that
  agent's `workspace/files/`.

This mode is useful for benchmark and interface experiments. It does not connect
to Brix email, calendars, room-booking systems, SMS, CRM, invoicing, or approved
document repositories.

With `--root`, the runner instead exposes built-in plus local-file tools. By
default it removes the selected domain's tools. `--with-domain` keeps the
selected domain; `--with-office` is a compatibility alias. Domain-generated
artifacts still go to the domain workspace, not the supplied root.

## Requirements and launch

The runtime supports Python 3.9–3.13 and uses the pinned dependencies in the
root `pyproject.toml`/`requirements.txt`. `requirements-lock.txt` pins
transitive versions but has no hashes. Installation may require a package index
or cache. A local Ollama server at `127.0.0.1:11434` and the requested model tag
must already be available to run an agent.

From the project root, a portable direct invocation is:

```bash
python agents/8b/run_agent.py "List my simulated Wednesday meetings"
```

The supplied per-agent `run.ps1` files are Windows-specific and hardcode:

```text
C:\Users\Lab User\SAIL\python\python.exe
```

They need editing or replacement on other machines. The real-file shell tool
also invokes `powershell.exe`, so shell mode is not portable to macOS or Linux.

## Flags

| flag | current behavior |
|---|---|
| `--domain NAME` | selects a convention-loaded `domains.<name>.PACK` |
| `--root PATH` | exposes read, write, append, move, delete, and search inside a lexically checked path |
| `--shell` | adds arbitrary PowerShell execution; `cwd` is set to the root but the command is not sandboxed there |
| `--yolo` | removes file and shell confirmation prompts |
| `--with-domain` | retains selected domain tools alongside real-file tools (`--with-office` is an alias) |
| `--tiers` | selects models by the hardcoded `router`, `driver`, and `verifier` roles |
| `--small TAG` | assigns planning and verification to another tag |
| `--deep TAG` | enables tier/router mode and configures a deep model; no current code dispatches a deep call |
| `--max-calls N` | sets a validated positive successful-LLM-call ceiling |

## Safety limits

Do not point `--root` at business records or any directory you cannot restore.
This is an in-process path check, not an operating-system sandbox.
`ActionPolicy` is only an action-classification and confirmation seam:

- symlinks and Windows junctions are not resolved when containment is checked;
- the configured root itself can be selected for deletion;
- the write deny-list is hardcoded for one Windows installation;
- `--shell` can access paths and networks outside the root;
- `--yolo` removes the only interactive confirmation layer;
- file contents may be copied into agent state and transcript files outside the
  selected root.

Use only a disposable test directory with backups. Do not use real member,
employee, payment, agreement, email, or access-control data.

## Harness and audit limits

The harness adds JSON prompting, examples, argument normalization, a planning
call, duplicate-call suppression, and an LLM verifier. These mechanisms should
be treated as experiment variables, not guarantees:

- validation checks required and unknown keys but does not enforce the documented
  types or semantic date/time validity;
- fuzzy argument repair can silently rename or discard fields;
- planner `what` text is free-form and is inserted back into the conversation;
- the verifier fails open on an error and does not inspect generated files;
- an accepted `done` means the loop stopped, not that the task was correct;
- the 8,192-token context has no general compaction strategy for long runs.

Run logs are useful but not complete model transcripts. Driver replies and
observations are recorded, while the original planner reply and original
verifier reply/error are not retained. Logs, state, tool arguments, and memory
may contain sensitive text and are stored without encryption or access control.

Memory is an append-only JSONL fact store with keyword-overlap retrieval. Facts
may be written by the model and inserted into later system prompts without human
approval or provenance. It is not an authoritative knowledge base.
Runtime files are ignored by Git; no agent memory file is shipped.

## Router and adapter status

The router maps fixed call roles to model tags; it does not classify tasks or
measure actual RAM residency. The `deep` role is declared but unreachable.
Per-role `adapter` values are recorded in telemetry but are not applied by the
Ollama backend. `--deep` and adapter configuration therefore do not currently
add reasoning or fine-tuning capability.

## Persistent files

`office_demo` preserves the legacy per-agent paths:

- `workspace/state.json` and `workspace/files/`;
- `memory/memory.jsonl`;
- `logs/run_NNN.json`;
- `logs/model_calls.jsonl` when tier routing is enabled.

Other domains use:

```text
agents/<size>/runtime/<domain>/<version>/{workspace,memory,logs}/
```

Writes are not uniformly atomic or concurrency-safe. The log does not
programmatically grade CLI tasks. Review actual side effects and artifacts
manually.

Configuration, tools, policies, hooks and clocks are passed through explicit
runtime objects. This removes the prior supported process-global configuration
path; it does not make filesystem writes, logs or persistent domain state safe
for concurrent runs.

The browser console is documented in [`../webui/README.md`](../webui/README.md).
It exposes the same research runtime and does not make these agents production
safe.

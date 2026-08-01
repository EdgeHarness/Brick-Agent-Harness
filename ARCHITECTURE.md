# Architecture and current limitations

This document describes the implemented code and its current boundaries. It
does not treat a planned control, a passing unit test, or a version label as
evidence that the research instrument or product is valid.

## Status

Brick currently provides:

- explicit per-attempt runtime objects and an immutable public tool-registry
  interface;
- `office_demo@0.1.0`, a synthetic office pack with 12 hand-authored tasks;
- `counter_demo@0.1.0`, a one-task structural portability fixture;
- raw and scaffolded loops over attempt-selected domain tools;
- domain-aware CLI, benchmark, report and Agent Lab surfaces; and
- experimental LoRA generators and training scripts, but no shipped corpus,
  adapter or model.

The latest release is `v0.4.0`. The required native Lenovo F0 evidence exists and
the gate passed. That establishes host and model feasibility only; every stage
from S4 onward is unstarted and no measured effect exists.

Brick is not a production assistant, a secure filesystem/shell sandbox, a
transactional room-booking service, an access-controlled retrieval system, or
a validated statistical instrument. It has no Brix provider integrations. No
benchmark results are committed. `counter_demo` shows that a second pack can
traverse supported surfaces; it is not performance or generalization evidence.

Office email, calendar, chat and reminder actions modify local simulated state.
Office document tools create genuine `.pptx` and `.xlsx` files in the attempt
workspace.

## Repository map

```text
harness/
  runtime.py          RunConfig, RunHooks, ActionPolicy and AttemptContext
  domain.py           DomainPack/TaskSpec/PromptProfile contracts and loader
  storage.py          legacy and namespaced runtime-path selection
  builtin_tools.py    think/done tools shared by domain packs
  tools.py            ToolRegistry validation, execution and descriptions
  llm.py              per-instance Ollama client, counters and stream hook
  model_router.py     optional role routing; adapters remain metadata
  agent.py            raw and harness loops

domains/
  office_demo/        legacy office world, tools, prompt, tasks and graders
  counter_demo/       namespaced structural portability fixture

bench/
  run_bench.py        domain × model × condition × task runner
  report.py           domain/version-aware descriptive aggregation
  tasks.py|grade.py   office_demo compatibility re-exports

agents/
  _shared/            one shared runner used by every per-size shim
  1b|3b|8b|14b|32b/   model configuration and compatibility launchers

webui/                loopback HTTP/SSE development console
finetune/             live-harness data generator
training_scripts/     separate training package; local JSONL is ignored
tests/                offline characterization and architecture tests
```

`harness.world` and `harness.office` are compatibility re-exports for
`office_demo`; they are not independent implementations.

## Execution surfaces and storage

| Surface | Entry point | State and boundary |
|---|---|---|
| Benchmark | `python -m bench.run_bench` | New domain world per task, but reused task paths and shared memory per model/condition; exploratory only |
| Per-model CLI | `agents/<size>/run_agent.py` or `run.ps1` | Persistent synthetic domain state; legacy filesystem/shell options are rejected |
| Agent Lab | `python -m webui.server` | One child run over selected domain state; unauthenticated loopback demo |
| Training | scripts under `training_scripts/` | Local/HPC artifacts; may use the network unless assets are staged |

Only the benchmark exposes both `raw` and `harness`; CLI and Agent Lab run the
harness condition.

The office CLI preserves the historic `workspace/`, `memory/` and `logs/`
layout for prompt and path compatibility. Other packs use
`runtime/<domain>/<version>/{workspace,memory,logs}`. Namespacing prevents
ordinary cross-domain path collisions; it does not make writes atomic,
transactional or concurrency-safe. Log numbers are still allocated by counting
existing files and can collide.

## Runtime and domain contracts

Each loop receives an `AttemptContext` containing an attempt ID, `RunConfig`,
`DomainPack`, `ToolRegistry`, `ActionPolicy`, world, memory, workspace/artifact
paths, prompt data and hooks.

`RunConfig` accepts exactly `raw` or `harness` and validates the successful-call
ceiling, simulation date, observation limit, verifier rounds and prompt rules.
The call ceiling is measured relative to the LLM counter at attempt start.

`RunHooks` has best-effort note and tool callbacks. LLM streaming is configured
on the `LLM` or `ModelRouter` instance. Hook exceptions are swallowed so a
display failure does not stop an attempt; a hook is therefore not an
audit-completeness guarantee.

`ActionPolicy` classifies tools as `read`, `state_write`, `external_write` or
`shell`, with an optional confirmation callback. `DomainPack` construction
requires exactly one explicit classification for every registered tool, so a
pack cannot silently omit a mutating tool. `AttemptContext` also requires a
classification for every tool active in that attempt while allowing unused
pack classifications. In the unreleased Q0 working tree, a missing confirmation
callback denies instead of manufacturing consent. The policy is still not
identity, authorization, an OS sandbox, rollback, or a security boundary.

`ToolRegistry` deep-freezes stored public specifications and returns defensive
copies from public accessors. It checks tool names and required/unknown argument
keys. It does not generally enforce advertised value types, nested structure or
domain semantics.

`DomainPack` binds a SemVer-formatted name/version, registry, policy, prompt
profile, rules, lifecycle/normalization/state callbacks, tasks, presets and a
runtime layout. Construction checks callback signatures, reserved
`think`/`done` contracts, task/tool references, unique IDs/presets and the
generic state envelope. Packs load by importing `domains.<name>.PACK`. That is
a trusted Python convention, not isolated plugin discovery, code signing or
provenance. The version is a label, not a code/data digest.

The office pack uses a domain-owned `PromptProfile` to preserve legacy prompt
wording and fixed-date behavior. `counter_demo` uses the generic profile and
namespaced layout. `legacy_agent_v0` is a trusted pack declaration rather than
a globally unique allocation; new packs must use the namespaced layout to avoid
colliding with the office compatibility paths.

## Ollama client and routing

`harness.llm.LLM` calls Ollama `/api/chat`; launch surfaces restrict the
configured endpoint to `localhost` or `127.0.0.1`. The released exploratory
client uses temperature `0.0`, seed `42`, and a configured context. Those
settings neither guarantee identical output across model digests, runtimes and
hardware nor define the retained protocol.

The planned S6C primary uses Ollama native function calls for both
`native_tools` and `harness_full`, the same chat template and schemas, and the
sampling and opportunity ledger frozen in `PROJECT_SETUP.md`. F0 must verify
that the selected Lenovo Ollama build accepts the candidate settings.

The client records call count, prompt/output tokens and model-reported duration.
Equal successful-call ceilings do not equalize tokens, FLOPs, latency, energy
or work: harness adds planning and verification and uses different prompts and
output limits.

`ModelRouter` maps fixed roles to configured tags. The `deep` role is declared
but no current agent path calls it. Adapter values are telemetry only and are
not applied by the Ollama backend.

## Domain behavior

The office world starts with ten emails and seven events and uses Monday
2026-07-20 in benchmark mode. `send_email`, `add_event`, `send_message` and
`set_reminder` append to local state. There are no external sends or provider
calls.

`add_event` checks only basic date/time shape and lexical start/end ordering. It
does not enforce room inventory, conflicts, capacity, hours, recurrence,
cancellation, provider synchronization, idempotency or concurrent booking.
Impossible-looking values can pass some paths. This must not be described as a
Brix room-booking engine.

Office file creation uses `python-pptx` and `openpyxl`. Model filenames are
reduced to a basename and normalized to the expected extension. There is no
rollback, antivirus scanning, ownership model or concurrent-writer
coordination.

`counter_demo` exposes read/increment behavior, built-ins and one task. Its
purpose is to catch office-specific assumptions in wiring, path layout, report
grouping and state presentation. Its simplicity makes it unsuitable as
external validation.

## Agent loops

`run_raw()` gives the selected tool descriptions without examples, requests one
JSON object, parses strict JSON after optional fence removal, executes the call,
returns its observation and accepts `done` or the ceiling. It is a minimal
lower-bound baseline, not a representative native function-calling baseline.

`run_harness()` bundles:

- examples and JSON-constrained output;
- lenient extraction, trailing-comma repair and fuzzy argument repair;
- shape feedback and domain-owned normalization;
- a planning call;
- duplicate-call suppression and context pruning;
- up to two verifier rounds; and
- keyword-overlap memory injection.

Because these mechanisms are bundled, an aggregate delta cannot identify which
mechanism caused it.

The lenient parser counts braces without tracking JSON string state. Fuzzy
repair can rename an unknown field to a semantically unrelated required field
and then discard other unknown fields. Both behaviors are unsafe around
mutations without stronger validation or approval.

The planner restricts tool names, but model-authored plan text returns to the
prompt. The verifier sees a truncated action summary, not complete
observations, authoritative state or file contents. It fails open on exceptions
or malformed verdicts, allows only limited retries, and can miss the last
boundary call. It is advisory, not completion, authorization or safety proof.

Episode and action logs omit some original planner/verifier material and
truncate details. They are useful diagnostics, not complete forensic model
transcripts.

## Memory and data trust

`MemoryStore` is append-only JSONL with keyword-overlap retrieval. Model-authored
facts can re-enter prompts without approval, source, subject/tenant identity,
trust label, expiration, version, deduplication or injection filtering. A
malformed row can stop loading. Runtime memory is ignored by source control and
no agent memory file is shipped, but local files can still contain private or
poisoned text. Memory is not an authoritative knowledge base.

## Filesystem and shell quarantine

Unreleased Q0 removes the general filesystem/PowerShell overlay from supported
runtime composition. CLI, web and configuration surfaces reject legacy
`--root`, `--shell`, `--yolo`, `--with-domain`, and `--with-office` forms before
output creation, model access, network access or mutation.

Domain-owned Office tools may create real `.pptx` and `.xlsx` files inside the
attempt workspace. That narrow artifact contract is distinct from arbitrary host
filesystem access. Product integrations require typed, allowlisted service
adapters and deterministic business invariants.

## Agent Lab

Agent Lab serves static assets, starts one `webui.runner` child, streams JSONL
events over SSE, renders the selected domain's generic state sections, previews
Office files, and records development logs. Q0 removes the old browser endpoint
and child-stdin confirmation channel together with its skip-confirmation mode.
The subprocess supplies lifecycle and crash/stop containment, not a security
sandbox.

Q0 removes real-root, shell and skip-confirmation choices from Agent Lab. The
remaining authentication, origin, request-validation, reset and process-tree
defects stay open until S5W. Action confirmation returns at S5W only as a new
run/nonce-bound protocol; the removed unbound channel is not a supported
capability.

The server has no authentication, session-bound capability, CSRF defense or
Origin/Host allowlist. State-changing endpoints do not consistently enforce
request origin/content type; model pulling is a state-changing GET; reset is not
coordinated with an active child. Static, reveal, log and generated-file
lookups resolve child components beneath trusted canonical roots and reject
direct, same-prefix and child-symlink escapes observed at lookup time. They do
not establish root integrity or race-free containment, protect the
unauthenticated control plane, or harden the separate real-file tool overlay.
Stopping the wrapper does not guarantee descendant processes or in-flight
model work stopped.

Model cards contain neutral tier descriptions and advise measuring on the
actual hardware. They are not speed, reliability, memory-fit or quality
measurements.

## Benchmark and report

The runner validates domain, conditions, duplicate model labels and task IDs.
Artifact paths and records include domain/version:
`<outdir>/<domain>/<version>/<model>/<condition>/<task>`. All records still
share one non-atomic `results.json` ledger.

Records include domain/version, requested model tag, condition, task,
capabilities, selected tools, score/checks, finish status, successful LLM calls,
parser/invalid/tool errors, token counts, wall time, exception text and call
ceiling. This is partial metadata, not immutable provenance: model digest,
quantization, runtime/code/dependency hashes, prompts/registries, hardware and
OS remain unstamped.

The reporter requires core domain/version identity and metric fields, rejects
malformed or duplicate identities, renders single-condition summaries and
suppresses deltas when task sets are unpaired or recorded
call-budget/tool/capability surfaces differ. It validates the current record
shape, not complete experiment provenance. Those guardrails do not cure:

- reused task directories and stale generated files;
- memory deletion before resume checks and shared condition memory;
- loose/conditional graders and limited unintended-action penalties;
- grader exceptions collapsed into zero scores;
- non-atomic result rewrites;
- fixed order, one fixed instance per task and no independent repetitions; or
- cross-run contamination and incomplete provenance.

Generated results are exploratory and must not be published as evidence.

## Training track

Two generators can create 1,200-row JSONL files locally. Those files are ignored
and are not shipped. The default generated examples contain substantial
duplicates, cover only five office tools and have no validation/test split or
dataset card. Repair conversations include a bad call followed by a correction
while the trainer places loss on every assistant turn, so it trains the error
too. Tests now pin both generators' system prompt to the serving builder, but
that parity check does not validate the data or training objective.

External revisions are not fully pinned, scripts may download models and
llama.cpp, GGUF conversion is best effort, and Ollama does not apply the
resulting adapter. This is not a reproducible end-to-end training result.

## Explicit state is not isolation

Supported execution configuration, registry, hooks, budget and simulation clock
are explicit objects passed through the call graph. That removes the former
supported process-global mutation design. A nested two-domain test establishes
single-threaded reentrancy and state separation; it does not establish thread
safety, transaction isolation, concurrent filesystem safety, unique log
allocation, rollback or complete provenance.

## Locality, privacy and release boundary

Loopback inference can be local, but installation, model/source downloads and
Agent Lab pulls can use the network. The repository
has no production identity, authorization, encryption, retention/deletion,
tenant isolation, audit policy, backup or incident-response layer. Do not load
real Brix data.

The released S0–S3-era implementation is present and covered by the offline
suite. The old package taxonomy is historical. F0/Q0 passed on the native Lenovo
host and is released as `v0.4.0`; it establishes feasibility only. The canonical
sequence now proceeds through S4, S1R, synthetic B0, graders, generators, shared
native conditions, protocol freeze, sentinel and retained execution as specified
in [`PROJECT_SETUP.md`](PROJECT_SETUP.md).

## Safe extension principles

1. Keep business invariants in deterministic services, not prompts or model
   verification.
2. Default to read-only scopes; approve every external mutation during pilots.
3. Give each run isolated state and immutable provenance.
4. Treat model output, retrieved documents and memory as untrusted input.
5. Score complete outcomes and harmful side effects, not only partial matches.
6. Compare accuracy and safety against tokens, latency, compute and review cost.
7. Freeze task, grader, prompt, registry and runtime versions before retained
   comparisons.

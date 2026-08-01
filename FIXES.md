# Remediation register

This file maps known implementation defects to the active release sequence in
[`PROJECT_SETUP.md`](PROJECT_SETUP.md). It does not define a second gate
taxonomy.

The latest release is `v0.4.0`. The native Lenovo evidence required for `v0.4.0`
exists and the F0 gate passed. “Targeted” below means planned or in progress; it
does not mean an exit gate passed.

## Status ledger

| Area | Released `v0.3.1` state | Active remediation |
|---|---|---|
| General filesystem/shell | Unsafe lexical overlay exposed by CLI and Agent Lab | Q0 removes all supported activation paths instead of attempting to harden arbitrary host access |
| Attempt isolation/evidence | Reused task directories and non-atomic `results.json` | S4 marker-last immutable physical bundles and rebuildable projections |
| Runtime schemas/parser | Key-only validation, unsafe fuzzy repair, fail-open completion | S1R executable schemas, known-alias-only recovery and authoritative completion |
| Memory | Shared append-only untrusted JSONL | S1R scoped, versioned, expiring untrusted input |
| Synthetic Brix layer | Not implemented | B0 fictional lead follow-up after S1R |
| Graders | Loose associations, variable denominators, exceptions scored as zero | S5 strict versioned evidence graders |
| Agent Lab | Unauthenticated loopback control plane | Q0 removes unsafe capabilities; S5W hardens the remaining control plane |
| Task instances | Twelve fixed prompts and shared order/state | S6G structural generators and isolated splits |
| Conditions/baselines | Prompt-JSON `raw` versus bundled legacy `harness` | S6C shared native transport, competent baseline, explicit harness, rules and descriptives |
| Provenance/scheduler | Partial metadata and interactive long-run assumptions | S4/S6C immutable provenance and standalone restartable execution |
| Protocol/statistics | No frozen valid retained protocol | D0/S7 fixed-family paired protocol and runtime-only sample rule |
| Live evidence | No retained results | Lenovo F0, zero-invalid S8 sentinel, then primary-first S9 |

Do not preserve comparability with known-invalid development output. No released
result is retained evidence.

## F0 protocol v1 — gate asserted a runtime contract that does not exist

### Finding

F0 v1 made 4B eligibility depend on Ollama rejecting the unknown option
`brick_f0_unknown_option` with a 4xx client error naming it. Ollama's chat API
defines `options` only as a runtime-options object and does not promise strict
unknown-key rejection; 0.32.5 logs a warning and continues. The first native
Lenovo run (`f0-20260801T020325Z-5f948e97`, candidate `e4dd167`) therefore failed
on correct server behavior while every other check passed, including native tool
conformance 3/3 and warm throughput of 23.00 tok/s against a 5 tok/s floor.

Two reporting defects compounded it. `option-validation/summary.json` emitted an
unconditional interpretation string asserting that the server rejects unknown
names, which contradicted its own `passed: false`. And `verify_report`
recomputed eligibility only for passing reports, so a failed bundle was echoed
back rather than verified.

### Why the fix is a versioned protocol change, not a repair

`PROJECT_SETUP.md` provides for exactly this: revise and version the candidate
protocol, then rerun all of F0. Lowering the check to make the existing run pass
would be waiving a gate, and a waived gate produces a number nobody should
believe. The failed bundle stays immutable and failed.

### Remediation — protocol v2

- Per-key option recognition replaces unknown-name rejection. Each frozen option
  name given an invalid value type must return a 4xx/5xx response naming the key
  and its declared type. The same value under an unknown name is diagnostic:
  either acceptance or rejection is permitted and recorded. This discriminates
  at the frozen values, including the neutral `top_p=1.0`, `min_p=0` and
  `repeat_penalty=1.0` where an output differential provably cannot.
- Output-differential comparisons are demoted to descriptive diagnostics. They
  cannot serve as acceptance evidence: a no-op value is indistinguishable from an
  ignored key, extreme probe values are not the frozen values, and no sampler
  defines a monotonic output-length invariant.
- Brick owns request validation, fail-closed, before any HTTP request.
- Inference runners are attested by path, SHA-256 and PE architecture and must be
  native ARM64 with a stable identity and stable sampled process set, closing the
  emulated-x64 and mid-probe replacement gaps.
- Failures carry structured domain attribution so a protocol-contract or runner
  fault is never recorded as a model failure.
- Failed reports are verified semantically, including recomputation of structured
  failure codes from component records; early and late failures remain
  independently verifiable. V1 bundles remain verifiable for integrity and
  identity only and can never establish a passing gate.

## Q0 — quarantine unsafe capability paths

### Finding

The released filesystem/PowerShell overlay is not a sandbox:

- lexical checks can follow symlinks or junctions outside the selected root;
- a drive/filesystem root or the selected root itself can be targeted;
- a deny-list is tied to one Windows installation;
- a missing confirmer permits compatibility behavior;
- skip-confirmation removes the only interactive layer;
- command execution is not confined to its working directory and may use the
  network; and
- check-then-write paths are vulnerable to races.

### Required change

Do not attempt to convert this into a production sandbox. Supported CLI, web,
and configuration surfaces must reject:

- `--root`;
- `--shell`;
- `--yolo`;
- `--with-domain`;
- `--with-office`;
- Agent Lab real-root, shell and skip-confirmation inputs; and
- direct configuration/composition of the overlay.

Rejection occurs before output creation, model access, network access or
mutation. Domain-owned tools may still create declared Office artifacts inside
an attempt-owned synthetic workspace.

### Acceptance

Tests enumerate every legacy CLI, API, UI, runner and configuration entry path.
Each must fail before constructing an LLM client, creating an output directory,
opening a network request or executing a tool. Publication tests must show that
no supported module imports the legacy overlay.

## F0 — verify the actual Lenovo environment

### Finding

The released repository contains no evidence that the selected Qwen3.5 tags,
native tool transport, sampling options, backend, memory use, or throughput work
on the target Snapdragon X Elite host. A hard-coded runtime version or claimed
accelerator would be speculation.

### Required change

Add reproducible probes that record:

- Windows, BIOS, driver, power, Python, Ollama and executable hashes;
- complete model metadata and immutable digests;
- native function-call round trips for 2B, 4B and 9B;
- exact accepted sampling payloads, explicit rejection of an unknown sentinel
  option, effective template/context evidence, and disabled thinking;
- backend classification, memory, latency and warm throughput; and
- the exact pass/fail thresholds in `PROJECT_SETUP.md`.

Add a disposable marker-last NTFS probe with real `.pptx`/`.xlsx` fixtures, 200
total cycles, 50 process exits, 10 held-handle cycles, bounded Windows
sharing/access retry, and zero invalid committed bundles. Offline Q0 tests cover
its write boundaries, adoption, abandoned evidence, directory collision,
tampering, unexpected members and simulated retryable errors. Production
concurrency, duplicate candidates, logical collisions and projection rebuilding
remain S4 work; F0 does not claim the production store.

### Acceptance

The native Lenovo evidence bundle passes all F0 gates. A 4B failure stops the
design. A 2B/9B failure removes only that descriptive replication. Hosted
Windows ARM CI remains advisory. The exact run/verify commands, external bundle
retention, and clean candidate `C` to metadata-only release descendant `R`
attestation are mandatory as specified in `PROJECT_SETUP.md`.

## S4 — immutable marker-last evidence

### Findings

- A task directory is reused, so stale Office files can influence a rerun.
- `results.json` is truncated and rewritten in place.
- resume can erase shared memory before determining completed dependencies.
- grader exceptions are recorded as model failures.
- log identity derives from directory contents and can collide.
- no one-writer lock or complete immutable attempt key exists.

### Required store

Use:

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

Execute directly in a never-reused physical UUID directory. Close and hash all
evidence, write and validate `PREPARED.json`, then publish by exclusively
creating the empty regular file `COMMITTED`. Never rename or replace an attempt
directory.

Readers accept only marker-present bundles whose prepared manifest and hashes
validate. A valid prepared bundle without the marker is adopted without another
model call. An incomplete bundle is preserved as abandoned. Duplicate valid
candidates, logical-hash collisions, and corrupted committed evidence halt the
run. `results.json` is rebuilt from evidence.

Retry only idempotent validation and marker operations for the bounded Windows
deadline. Retry exhaustion becomes `publish_blocked`, not a model rerun.

### Acceptance

Tests kill the writer after every boundary and cover stale files, held Office
handles, sharing violations, denied reads, concurrent writers, prepared adoption,
duplicates, collisions, tampering, projection recovery and the ordered learning
scenario. Only fully committed, validated and graded records receive non-null
strict outcomes.

## S1R — typed and fail-closed runtime

### Schema defect

Released tool descriptions are prompt strings. Validation checks missing and
unknown keys but does not enforce complete primitive/nested types, formats,
ranges, calendar dates, time ranges or domain semantics.

Create one executable JSON schema per `ToolSpec`; derive prompt and Ollama native
schemas from it. Return stable structured errors. Keep authorization and
business invariants in deterministic services.

### Parser/repair defect

The released brace scanner ignores quoted-string state. Fuzzy repair may map an
unrelated unknown key into a required mutation field.

Use native tool-call objects for primary conditions. If legacy extraction
remains, use a string-aware decoder. Restrict automatic argument repair to a
small versioned known-alias table. Never fuzzy-repair a mutation.

### Completion defect

The released verifier uses the same model, sees incomplete evidence, can fail
open and can be bypassed at a budget boundary.

Represent completion as `complete | incomplete | unknown`. Inspect
authoritative state and required artifacts. A model verifier may explain missing
work but may not authorize an effect or establish correctness. Malformed,
timed-out, contradictory and budget-starved verification cannot become complete.

### Memory/context defect

Released model-authored memory lacks source, subject/tenant scope, trust,
version, expiry, deduplication and poisoning controls. Observation truncation can
hide required information without an explicit outcome.

Treat memory as scoped untrusted input with provenance, validation, expiry and
an explicit write policy. Quarantine malformed rows. Represent unavailable
observation tails and context exhaustion as explicit outcomes; do not silently
drop evidence needed for completion.

### Acceptance

Parser strings containing braces, invalid types/dates/times, unsafe repairs,
malformed completion output, memory corruption/poisoning, truncation, final-call
boundaries, timeouts and executor exceptions all fail closed with the correct
orthogonal status.

## B0 — replaceable synthetic Brix layer

### Boundary

Build `brix_followup_synthetic` only after S1R. All actors, tenants, leads,
addresses, policies and provider behavior are fictional. The model may read
assigned synthetic records and create typed proposals. It cannot approve,
dispatch, select another tenant, choose an arbitrary recipient, bypass policy or
write authoritative state through memory.

### Required deterministic services

- actor/tenant authorization;
- eligibility and due-date evaluation;
- proposal versions, payload hashes, revisions and expiry;
- approval and dispatch revalidation;
- idempotency and concurrent update handling;
- fake delivery and ambiguous-result reconciliation; and
- immutable audit events.

### Acceptance

Positive, unauthorized, stale, expired, concurrent, duplicate, ambiguous and
recovery tests pass without network access. Generic packages import no Brix
module. This proves replaceable layering, not stakeholder approval, integration
or deployment.

## S5 — strict outcome graders

### Findings

Released graders use substring filenames, loose spreadsheet and slide
associations, broad text substrings, conditional denominators, incomplete
unwanted-action checks and shared memory. A grader exception becomes score zero.

### Required change

- use fixed, versioned check sets and denominators;
- make strict whole-task success primary;
- grade only immutable current-attempt evidence;
- require exact file, row/column, slide/region, recipient and source
  associations;
- require evidence of source reads where selection matters;
- fail on harmful, unauthorized, stale, missing, extra or incorrect effects;
- keep partial checks diagnostic only; and
- convert grader/instrument failure to null, never model failure.

Every check requires a correct fixture and a minimally wrong fixture that would
otherwise be tempting to accept.

## S5W — Agent Lab control plane

Q0 removes the dangerous filesystem/shell capability but does not authenticate
Agent Lab. Remaining defects include no session capability, Host/Origin/CSRF
validation, typed/limited bodies, reset coordination, bounded retention or
guaranteed process-tree termination. Q0 also removes the old browser/stdin
confirmation channel rather than preserving an unbound decision path.

S5W adds a high-entropy startup capability, trusted host/origin policy,
state-changing JSON-only POSTs, request limits, reset/run serialization,
allowlisted previews, process-group termination, bounded logs and redaction. S5W
also adds a new operator-confirmation protocol bound to
`(run_id, confirmation_id, nonce)`; it does not revive the removed generic stdin
channel.

Wrong-token, cross-origin, stale-confirmation, reset-during-run, oversized-body,
path, and orphan-process tests must pass on Windows and POSIX.

## S6G — independent task instances

The released suite has 12 fixed prompts, shared ordering and one memory file.
Changing only an inference seed does not create an independent workplace case.

Create 11 fixed generator distributions, combining the dependent memory episodes
into one family. Vary structure, policy, state, valid action sequence, wording,
entities, dates, conflicts and distractors. Record generator/template/policy
identity and reject seed-only variants.

One learning-family case is one logical attempt with two ordered store-then-use
subepisodes. They share a single isolated memory scope and one
14-call/4096-generated-token ledger without reset. Strict case success requires
both subepisodes; an instrument failure in either makes the case null. They are
not separate model attempts, so the 440/662 totals remain valid.

Development, validation, sentinel, retained and adversarial splits must replay
from manifests and share neither entities nor structural templates.

## S6C — fair conditions and accounting

### Native transport

`native_tools` and `harness_full` must use the same Ollama native function-call
endpoint, chat template, 4B model digest, tool schemas/order, tool-result
transport, deterministic validators, state transitions, task instances, hidden
grader and safety policy.

`harness_full` may add only versioned planning, scoped memory, known-alias
recovery, duplicate suppression, observation management and completion guarding.

### Opportunity accounting

All driver, planning and completion requests count against the primary ledger.
Use the exact context, sampling, call and output limits frozen in
`PROJECT_SETUP.md`. Equal calls are not equal compute. Record calls by role,
tokens, latency, model time, wall time, retries, repairs, approvals, action
opportunities, memory and environment telemetry.

### Baselines

- `native_tools`: competent primary baseline;
- `harness_full`: primary treatment;
- `raw_json`: descriptive lower bound;
- `rules_reference`: separate structured architecture reference;
- three harness ablations, one learning-memory ablation and one
  equal-action-opportunity sensitivity: descriptive only.

If rules dominate a family, recommend deterministic execution for that family.
Do not hide the result as strategically inconvenient.

## D0/S7 through S9 — protocol and retained execution

D0 exposes instrumentation and timing only, not efficacy. It selects 20 or 12
instances per family using the frozen runtime rule. No effect, discordance or
family outcome may affect that choice.

The primary is the equal-family-weight strict-success difference for 4B
`harness_full` versus `native_tools`. Its inferential gate is a 20,000-draw
within-family percentile bootstrap using the pinned PCG64 stream, paired-case
resampling and type-7 quantiles. The exact paired sign-flip/McNemar p-value is an
additional sharp pairwise-exchangeability diagnostic, not an exact test of the
weak null `Delta=0`. Publish every family effect and leave-one-family-out
sensitivity, and pin both procedures with golden fixtures.

The default primary contains 220 pairs/440 attempts. The bounded default maximum
including descriptives is 662 model attempts. Qwen3.5 2B and 9B are descriptive
system replications, never a causal size curve. Every ablation is descriptive;
no Holm testing or “no effect” mechanism claim is permitted.

A standalone Python or PowerShell scheduler owns execution. It runs the primary
first in `N` waves (`N=20` or `12`), balances paired AB/BA order, records
heartbeat and telemetry, resumes from evidence and stops on environment drift.

A partial primary is `INCOMPLETE/DESCRIPTIVE` and receives no confirmatory
inference. A sealed complete primary survives an interrupted descriptive phase.
No outcome-selected subset or mixed environment stratum is allowed. An
incomplete primary is an honestly reportable project state, not completion of the
research milestone.

## Future work outside this milestone

Real Brix workflow discovery, data authorization, provider integration, shadow
evaluation, pilot operation, production deployment, external-benchmark
integration and fine-tuning are not part of the `v0.14.0` completion path.

The training package remains blocked by narrow duplicated data, incorrect repair
masking, absent leakage-resistant splits, incomplete provenance, best-effort
conversion and no served-adapter evaluation. It may be reconsidered only after a
frozen result identifies a stable learnable failure.

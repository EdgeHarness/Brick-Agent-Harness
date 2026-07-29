# Remediation plan

This is the prioritized plan for turning the current synthetic research
scaffold into a trustworthy measuring instrument and, separately, building a
safe Brix workflow.

All items below remain pending except for the explicitly marked partial work in
the status ledger. Describing a target control does not mean its acceptance
criteria passed.

The canonical gate names and dependencies live in
[`PROJECT_SETUP.md`](PROJECT_SETUP.md): G0 for repository truth and
containment, R1–R5 for research, and P0–P4 for the Brix product. This file is the
code-level defect register mapped to those gates; it does not define a second
gate taxonomy.

### Implementation status ledger

This ledger prevents a still-valid defect description from being mistaken for
the current implementation state. `Partial` means useful prerequisites landed;
it does not satisfy the item's acceptance criteria.

| Item | Status at 0.3.1 | Implemented evidence and remaining boundary |
|---|---|---|
| B-01 filesystem/shell | Pending | Per-attempt overlays exist, but real-path/TOCTOU containment, safe-root refusal, fail-closed confirmation, and process sandboxing do not. |
| B-02 stale artifacts | Pending | Domain/version path components exist, but task directories are reused and have no attempt manifest. |
| B-03 result integrity | Pending | Resume identity includes domain/version and report rows are validated, but the ledger is non-atomic and failures are still conflated. |
| B-04 web control plane | Partial | `0.3.1` uses canonical child-component containment for static/reveal/log/generated-file lookups under trusted resolved roots. Root integrity, race-free access, authentication, Origin/CSRF checks, typed bodies, run-bound confirmation, safe process groups, and reset coordination remain absent. |
| B-05 runtime state | Partial | Canonical `main` tracks no runtime memory and ignores agent runtime paths. Persistent state still lives under the source tree, malformed memory handling is incomplete, and a divergent legacy public repository still exposes excluded artifacts. |
| R-01 offline tests | Partial | The offline suite, CI matrix, prompt parity, caller, and architecture tests exist. Adversarial parser/grader/isolation/resume/atomic-write/security coverage remains incomplete. |
| R-02 through R-05 | Pending | Typed semantic schemas, conservative parsing, fail-closed completion, and strict graders are not implemented. |
| R-06 isolation/ablation | Partial | Attempt dependencies and two domain packs are explicit; benchmark task memory, reused directories, fixed ordering, and bundled mechanisms remain. |
| R-07 through R-10 | Pending | Complete provenance, defensible baselines, independent instances, and a controlled model series do not exist. |
| R-11 reporting | Partial | Single-condition rows, domain/version strata, duplicate rejection, core record validation, and incompatible-surface suppression exist; strict success, harmful effects, instrument-error strata, and complete provenance do not. |
| R-12 explicit runtime | Partial | Runtime objects, thin per-model shims, portable launchers, and single-threaded nested domain isolation exist. Thread/concurrent-run safety and duplicated CLI/web construction are not proven or removed. |

Do not preserve comparability with known-invalid historical results. There are
no committed results, and correcting the instrument is more important than
preserving accidental behavior. Version every breaking change and never
aggregate across versions.

## Blocking defects — canonical G0 and R1

### B-01: Quarantine real-file and shell mode

**Finding**

`fs_tools` is not a security sandbox:

- containment uses lexical `abspath`/prefix checks and follows symlinks;
- `/` or a drive root is accepted as the working root;
- `.` resolves to the configured root and can be passed to `delete_path`;
- the deny-list is hard-coded to one Windows installation;
- no confirmation callback means approve by default;
- `--yolo` bypasses all confirmation, including shell;
- append modifies an existing file without confirmation;
- `run_command` can leave the working root and use the network.

**Immediate change**

- Hide or reject `--root`, `--shell`, `--yolo`, delete and move in Agent Lab
  until the boundary below is implemented.
- Keep demonstrations inside a newly created disposable directory containing
  synthetic files only.
- Change a missing confirmation callback to deny mutations.
- Remove shell from every Brix-facing configuration. Confirmation is not a
  shell sandbox.

**Durable change**

- Reject filesystem roots and reject mutation of the configured root itself.
- Resolve and compare canonical paths, including every existing ancestor.
- Reject symlinks/junctions for mutations, or use descriptor-relative,
  no-follow operations that remain rooted after validation.
- Replace the relocation-sensitive deny-list with a narrow allowlist.
- Require approval for overwrite, append, delete, move and every external
  mutation.
- Prefer recoverable trash over permanent deletion.
- If arbitrary commands remain a research feature, run them in an OS/container
  sandbox with a read-only base, explicit mounts, no ambient credentials and
  disabled network.
- Add race-resistant handling; a check followed by a normal path write is
  vulnerable to link swaps.

**Acceptance**

Automated tests must cover `/`, drive roots, `.`, `..`, absolute paths,
environment expansion, nested symlinks, a link swapped after validation,
protected project/runtime paths, missing confirmation, declined confirmation
and a subprocess attempting both filesystem and network escape.

### B-02: Eliminate stale benchmark artifacts

**Finding**

`World(workdir)` resets in-memory state but preserves `workdir/files`. A rerun,
partial crash or manually deleted result record can be graded against a PPTX or
XLSX created by an earlier attempt.

**Change**

- Give every attempt an immutable unique directory:
  `<run-id>/<model>/<condition>/<task-instance>/<attempt-id>/`.
- Never execute into a previously used attempt directory.
- Pass the grader an explicit artifact manifest produced during that episode;
  do not search a shared directory for “a matching file.”
- Publish a completed attempt with an atomic metadata marker only after the
  episode and grader finish.
- Treat unexpected pre-existing files as an instrument error.

**Acceptance**

A failing episode placed after a successful episode must receive no credit from
the earlier artifacts. Killing the runner at every write boundary must not
create a gradeable “completed” attempt.

### B-03: Make the result ledger transactional and auditable

**Finding**

`results.json` is truncated and rewritten non-atomically. A grader exception is
recorded as a score of zero. Resume deletes memory before checking which tasks
were completed. Log numbering uses directory entry count and can overwrite an
existing transcript.

**Change**

- Use one attempt commit protocol covering state, result, artifact manifest and
  completion marker. A set of independently replaced files is not a
  transaction.
- Within that protocol, write files to sibling temporary paths, flush and
  `fsync`, atomically replace, and sync the parent directory on platforms where
  that is required for durable rename.
- Use a lock or one-writer result store. Reject concurrent writers to the same
  run directory.
- Add explicit record states: `complete`, `runner_error`, `grader_error`,
  `aborted` and `invalid`.
- Exclude invalid/instrument-error records from model score aggregates.
- Make resume operate on a run manifest; never erase an existing run's memory.
- Model the learning producer/consumer pair explicitly or isolate it in its own
  scenario.
- Generate log IDs from an immutable run/attempt ID rather than directory
  length.

**Acceptance**

Resume after interruption preserves valid dependencies. Corrupt or partial
files are detected. Grader failures produce no model score. Two simultaneous
writers cannot corrupt or overwrite one another.

### B-04: Protect the local web control plane

**Finding**

Loopback binding is not authentication. The server has no session token,
Origin/Host validation or CSRF defense; accepts state-changing requests without
checking `Content-Type`; exposes model pulling as GET; and does not coordinate
reset/confirm/stop with a specific run capability. Version `0.3.1` resolves
child components under trusted canonical roots and rejects direct, same-prefix,
and child-symlink escapes observed at lookup time. It does not establish root
integrity or race-free access, and is not control-plane authorization.

**Change**

- Generate a high-entropy startup token and require it on every API/SSE request.
- Permit only expected `Host` and `Origin` values.
- Require `application/json`, reject oversized bodies and validate every
  request against a typed schema.
- Make model pull a POST with explicit confirmation and storage limits.
- Bind confirmations to `(run_id, confirmation_id, nonce)` and expire them.
- Reject reset while a run is active, or stop and await full teardown first.
- Allowlist reveal targets; use canonical containment and do not follow
  symlinks for preview/download/tree operations.
- Launch each run in its own process group and make Stop terminate and reap the
  full group. Report “stopped” only after confirmation.
- Add bounded event/log retention and redact sensitive fields.

**Acceptance**

Cross-origin browser requests, wrong tokens, wrong run IDs, traversal, symlink
escape and stale confirmations are rejected. Stop and reset tests leave no
child process and no concurrent writer.

### B-05: Remove runtime state from source control

**Finding**

Model-authored memory is untrusted, potentially private runtime data. A memory
fact was tracked in the legacy history. Canonical EdgeHarness `main` no longer
tracks agent memory and now ignores legacy and namespaced runtime
memory/state/logs. A separate divergent public legacy repository still exposes
excluded runtime/training artifacts, so repository-level containment is not
complete.

**Change**

- Ignore every agent's `memory/`, `workspace/` and `logs/` runtime contents,
  retaining only deliberate empty-directory markers where necessary.
- Remove tracked runtime facts from Git history when privacy requirements
  demand it.
- Store runtime state under a configurable data directory outside the source
  tree.
- Validate JSONL rows and recover/quarantine malformed rows rather than
  preventing startup.

**Acceptance**

A full agent run leaves `git status` clean, and no user/model-authored content
is eligible for commit by default.

### Blocking-defect exit criteria

The relevant G0/R1 work cannot pass until:

- real-file and shell escape tests pass on each supported platform;
- benchmark attempts cannot reuse stale state or artifacts;
- results and state survive forced interruption without silent corruption;
- grader and runner failures are separated from model failures;
- the UI rejects unauthorized and cross-origin control requests;
- runtime data is outside version control.

Until then, use synthetic disposable data only and label every number
“exploratory / instrument not validated.”

## Research instrument and protocol — canonical R1 and R2

### R-01: Build the offline test suite before changing scores

The root dependency inputs, continuous integration, and an Ollama-free offline
suite now exist. The autouse guard blocks `requests` and `urllib` paths but is
not an OS network sandbox. The remaining suites below are still required before
R1 acceptance.

Minimum suites:

- parser and normalization tables, including braces/escapes inside JSON strings,
  invalid dates and invalid times;
- typed tool contract tests for every tool;
- scripted-agent loop tests for budget boundaries, verifier outcomes, duplicate
  calls and mutation approval;
- good, bad and adversarial fixtures for every grader;
- stale artifact, memory isolation, resume and atomic-write tests;
- filesystem and UI security tests from blocking items B-01 and B-04;
- report tests for partial matrices, mixed versions and invalid records;
- frozen-prompt/data provenance tests for the training package.

An intentional regression in any grader must fail the suite.

### R-02: Replace descriptive parameter strings with typed contracts

**Finding**

The registry's type descriptions are prompt text. `validate_call()` checks only
missing and unknown keys.

**Change**

- Define one machine-readable schema per tool and derive prompt documentation
  from it.
- Validate primitive and nested types, required fields, array elements, formats,
  ranges and additional properties.
- Validate dates with a calendar parser and times with explicit range checks.
- Put domain invariants in deterministic services. For example, a scheduling
  service—not the model—must atomically reject collisions.
- Return structured, stable error codes plus safe model-facing explanations.

**Acceptance**

Every documented invalid type/value has a test, and prompt documentation cannot
drift from executable validation.

### R-03: Make parsing and repair conservative

**Finding**

The brace scanner ignores quoted-string state. Fuzzy argument repair can assign
an unrelated unknown field to a missing required write field and silently drops
information.

**Change**

- Prefer the runtime's native structured-output/function-calling interface.
- If extraction remains necessary, use a JSON-aware incremental decoder.
- Restrict automatic repairs to a small, versioned mapping of unambiguous
  aliases.
- Never fuzzy-repair a side-effect parameter. Return a correction request or
  require approval when the intended mapping is uncertain.
- Record original output, proposed repair, confidence/reason and final accepted
  call.

**Acceptance**

Adversarial keys cannot become unrelated required fields; braces in string
values parse correctly; uncertain mutation calls do not execute.

### R-04: Replace the fail-open verifier

**Finding**

The same model verifies a summary of its own actions, not authoritative results.
Malformed/error verdicts become complete, only two rejections are honored, and
completion at the call limit can bypass verification.

**Change**

- Treat completion checking as `complete`, `incomplete` or `unknown`.
- Use this result only to classify episode completion. The current verifier runs
  after tools execute and therefore cannot authorize or prevent side effects
  retroactively.
- Put every external mutation behind a pre-execution typed proposal,
  authentication/authorization, deterministic policy validation, required human
  approval, and transactional commit.
- Check deterministic postconditions against world/service state and generated
  artifacts.
- Use a model verifier only to explain missing work, never as the sole safety
  decision.
- Reserve verification budget explicitly or finish as `budget_exhausted`;
  never bypass the gate because no call remains.
- Record raw verifier input/output and error details.

**Acceptance**

Malformed, timed-out, contradictory and budget-exhausted verifier cases cannot
be reported as verified completion. Deliberate extra actions are detected.

### R-05: Rewrite graders around task outcomes

**Finding**

Current graders are permissive and sometimes internally inconsistent:

- filename matching uses substring rather than exact normalized stem;
- spreadsheet labels and numbers can occur in unrelated rows;
- slide titles, regions and figures need not be associated;
- email “most recent” behavior is not proven by the sent output alone;
- a bare “yes” can satisfy confirmation;
- `"sam"` can match `"same"`;
- conditional checks change denominators;
- most tasks ignore unwanted extra actions;
- `learn_store` can pass from earlier tasks' memory.

**Change**

- Give each task a fixed set of checks and fixed denominator.
- Make strict whole-task pass the primary metric; retain partial checks for
  diagnosis.
- Match exact normalized filenames from the attempt manifest.
- Require values to be associated with the correct row, column, slide, region,
  recipient and source record.
- Grade evidence of required reads when the task requires source selection.
- Add negative assertions for extra email, calendar, message, reminder, memory
  and file mutations.
- Grade memory writes from the current episode only.
- Make grader exceptions invalidate the attempt.

**Acceptance**

For every check, add a minimally wrong adversarial artifact/action set that
would previously pass and now fails.

### R-06: Isolate task instances and causal mechanisms

**Finding**

One memory file spans all 12 tasks in fixed order. That introduces order and
cross-task contamination. The harness treatment bundles ten mechanisms, so
failure counters do not identify causality.

**Change**

- Default every task instance to isolated world, artifact and memory state.
- Define learning as an explicit two-episode scenario with no unrelated tasks in
  between.
- Parameterize each harness mechanism before the benchmark is frozen.
- Preregister a small set of theoretically motivated ablation groups; do not
  infer causality from observational failure counters.
- Counterbalance task and condition order.

**Acceptance**

Changing unrelated task order cannot change another task's starting state.
Every retained result identifies the exact enabled mechanism set.

### R-07: Add complete immutable provenance

Every attempt must record:

- benchmark, task, grader, harness and domain-pack versions;
- Git commit and dirty-tree digest;
- exact model name and immutable model digest;
- quantization, context size, sampling options and output limits;
- Ollama/backend version;
- OS, CPU/GPU/NPU, memory and relevant driver versions;
- task-instance/world seed and condition order;
- prompt hashes and tool-schema hash;
- start/end timestamps, termination reason and approval decisions;
- prompt/output tokens per role, latency and peak resource measurements.

Reports must reject mixed incompatible versions unless explicitly producing
separate strata.

### R-08: Use defensible baselines and resource accounting

Replace the two-way headline with at least:

1. a deterministic workflow/rules implementation where the task permits it;
2. a reasonable native function-calling baseline with ordinary validation and
   retry where the runtime and selected models expose a comparable interface,
   otherwise a preregistered substitute and limitation;
3. the complete harness;
4. preregistered mechanism ablations.

Keep the current raw JSON loop only as a labeled lower-bound baseline.

Report an accuracy/safety/cost frontier. A common call ceiling is one constraint,
not an equal inference budget. Record total prompt/output tokens, latency,
compute/energy where feasible, retries, approvals and human-review time.

### R-09: Replace repeated identical prompts with independent task instances

**Finding**

The current suite has 12 fixed prompts, one run per cell. Temperature zero plus
a fixed seed does not provide a sampling distribution, and changing only an
inference seed does not create independent workplace cases.

**Change**

- Generate or curate independent task instances with varied entities, dates,
  schedules, policies, wording and distractors.
- Hold out template and policy families, not just exact prompt strings.
- Predeclare the estimand and determine sample size using simulation or power
  analysis.
- Use paired comparisons on the same task instances.
- Report uncertainty with a method appropriate to task-level clustered data,
  such as paired/bootstrap intervals, and report pass-at-\(k\) reliability when
  repeated execution is relevant.
- Separate exploratory tuning cases from a locked final evaluation set.

### R-10: Use a valid model comparison

Do not label a Llama 3.2 1B/3B, Llama 3.1 8B and Qwen 14B/32B collection as a
pure size curve. Model family, generation, tokenizer and training data are
confounded with parameter count.

Use:

- a same-family, same-generation size sweep with consistent inference mode; or
- explicitly separate family comparisons and avoid a causal size claim.

Pin immutable model digests and quantizations. Run warmups, counterbalance
condition order and record thermal/system telemetry where latency is analyzed.

### R-11: Make reports descriptive and failure-aware

- Render a row when only one condition exists.
- Show invalid, runner-error and grader-error counts separately.
- Never average instrument failures as zero model capability.
- Show strict task pass and harmful-side-effect rate before partial score.
- Identify missing cells and dependency failures.
- Avoid causal labels such as “constrained decoding caused” unless an ablation
  supports them.
- Mark small exploratory samples and prohibit inferential language.

### R-12: Replace process globals with explicit run objects

`RunConfig`, `ToolRegistry`, `DomainPack`, `ActionPolicy`, hook and attempt
objects now pass through validation and execution. Pack policies must classify
every registered tool. Five per-model Python bodies were replaced by thin
shims, and `0.3.1` removed hard-coded interpreter paths from public launchers.

Remaining work is to deduplicate the overlapping CLI/web runner construction,
define a supported cross-platform shell strategy, and prove actual concurrent
execution rather than only single-threaded nested reentrancy.

**Acceptance**

Two differently configured agents can execute concurrently in one process
without registry, clock, hook, root or call-budget leakage. The calibration pack
runs through the explicit interfaces before the retained protocol is frozen.

### R1/R2 exit criteria

The canonical R1/R2 gates cannot pass until:

- all offline tests pass from a clean checkout;
- tasks, graders, schemas and analysis are versioned and frozen;
- task instances are independent and isolated;
- raw/native/harness/ablation conditions are explicit;
- strict success, side effects and resource costs are preregistered;
- model and environment provenance is complete;
- a sentinel matrix passes before the retained full matrix begins.

Only then run the expensive matrix. Full results generated before this gate
must not be carried into the retained analysis.

## Brix product track — canonical P0 through P4

### P0: Conduct Brix workflow discovery before choosing the pilot

The current repository contains no evidence that room booking and knowledge
search are definitively Brix's top two priorities. Before implementation,
document:

- current email/calendar/SMS/document/CRM/invoicing providers;
- workflow frequency, handling time, errors and cost;
- room inventory, capacity, equipment, hours, buffers, recurrence,
  cancellation and membership policies;
- user/staff roles and access boundaries;
- approved-document owners, versions, effective dates and retention;
- required approvals, reversibility and incident ownership.

Score all requested workflows on value, frequency, data readiness, integration
effort, reversibility and harm. Choose one or two with Brix, and define
acceptance metrics before building.

Before any real record is copied or accessed, obtain owner approval for a
written data plan covering permitted purpose and sources, fields included and
excluded, storage and encryption, roles and access, transcript/log handling,
retention and deletion, network/provider policy, incidents, and accountable
owners. Discovery may use staff descriptions and synthetic examples until that
approval exists.

**P0 acceptance**

- Brix approves the workflow map, value/risk score, selected workflow,
  authoritative system, success threshold and accountable owner.
- The written data plan is approved before real-data access.
- The proposed pilot can stop without disrupting the authoritative workflow.

### P1/P2: Build scheduling as a deterministic service

If scheduling is selected:

- use an authoritative room/resource store;
- enforce overlaps and idempotency transactionally;
- support timezone, capacity, equipment, hours, buffers, recurrence,
  cancellation and changes;
- use least-privilege provider credentials;
- separate conflict checking/drafting from approved commit;
- send notifications through an outbox with retries and deduplication;
- keep an immutable audit trail.

During the pilot, the model may propose a booking; deterministic code validates
it and a human approves the external mutation.

### P1/P2: Build approved-document search with access control

If knowledge search is selected:

- ingest only allowlisted sources;
- parse required file formats and preserve source identity;
- store owner, version, effective/expiry dates and approval state;
- filter by user/tenant ACL before retrieval;
- require citations to exact source passages;
- abstain on insufficient or conflicting evidence;
- test malicious document instructions and cross-user leakage;
- separate authoritative documents from model-authored memory;
- log access without exposing sensitive content unnecessarily.

Read-only does not mean harmless. Confidentiality, stale-policy and incorrect
answer failures require explicit tests.

### P1–P4: Add product security and operations

Before real Brix data:

- authentication, role-based authorization and tenant isolation;
- encrypted transport and storage;
- secret management and credential rotation;
- data minimization, retention and deletion procedures;
- audit review and redaction;
- backups, restore testing and disaster recovery;
- monitoring, rate/resource limits and incident response;
- dependency pinning, vulnerability scanning and release rollback.

No prompt or model verifier can substitute for these controls.

### P1/P2 acceptance

The synthetic vertical slice cannot advance to approved-data shadow evaluation
until:

- authoritative sandbox/fake integrations and deterministic invariants work;
- identity, authorization, privacy and operational controls pass review;
- no model output can bypass proposal validation or required approval;
- duplicate/concurrent requests preserve the declared invariant;
- external effects are attributable, reconcilable and reversible where the
  workflow promises rollback.

### P3/P4 acceptance

Shadow evaluation and any later controlled pilot follow their separate
canonical gates. Real data must use the approved P0 data plan. Every external
mutation remains human-approved unless a later recorded risk decision narrows
that rule. Rollback, deletion, monitoring, recovery, support and incident
ownership must be exercised before production can be considered.

Broader autonomy is a later decision based on pilot evidence, not a default
milestone.

## External validation — canonical R4

After R3 produces a valid internal result, assess a version-pinned external
benchmark whose outcome model resembles office work and harmful side effects.
Treat provider adapters and benchmark-specific tool schemas as declared
integration conditions. Do not assume a short port: first measure task coverage,
runtime dependencies, semantic compatibility, license and cost with a bounded
spike.

External benchmark success does not replace internal instrument validity or
Brix-specific acceptance testing.

## Training experiment — canonical R5

Training remains blocked until R3 demonstrates a recurring,
model-addressable failure that deterministic code, schemas or workflow design do
not solve more safely. Before training:

- generate reviewed corpora, deduplicate them, and establish one source of
  truth; no JSONL corpus is shipped by canonical `main`;
- split by prompt/template/entity/policy family;
- cover the tools and scenarios relevant to the diagnosed failure;
- mask intentionally erroneous assistant turns from loss unless the objective
  explicitly requires them;
- remove invented targets from under-specified prompts;
- add a dataset card, licenses, hashes and generation provenance;
- pin the base model, tokenizer, chat template, dependencies and llama.cpp;
- make conversion or adapter-serving failure fail the job;
- evaluate the adapter through the same versioned serving path.

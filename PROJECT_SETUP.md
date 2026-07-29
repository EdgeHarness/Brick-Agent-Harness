# Gated Implementation Plan

This plan implements the standards in the [Project Guide](PROJECT_GUIDE.md). It uses
acceptance gates rather than calendar promises. A gate advances only when its evidence
exists; elapsed time does not make incomplete work acceptable.

## 1. Rules for executing the plan

1. Treat the current system as a synthetic research scaffold.
2. Do not retain benchmark results until the instrument and protocol gates pass.
3. Do not use real Brix data until the discovery and data-governance gate passes.
4. Do not expose general shell or filesystem mutation to a Brix-facing system.
5. Keep research conclusions separate from product acceptance.
6. Record failures of the runner, model, tool, grader, and analysis separately.
7. Make all comparisons from immutable, versioned artifacts.
8. Freeze hypotheses, primary outcomes, exclusions, and analysis before retained runs.
9. Do not use unsupported time, cost, performance, or compatibility estimates.
10. Fine-tune only after a frozen evaluation identifies a training-addressable failure.

## 2. Session-sized implementation packages

The gate taxonomy below remains authoritative. The `S0`–`S18` identifiers divide that
work into bounded implementation sessions; they do not create a second set of gates.
Only one package is active in a coding session unless the project owner explicitly
changes the scope.

Each package follows the same control loop:

1. State the package identifier, files in scope, acceptance checks, and prohibited work.
2. Verify the prerequisite evidence before editing.
3. Implement only the declared package.
4. Run its offline checks and inspect the complete diff.
5. Update documentation and `CHANGELOG.md` when behavior or a public contract changes.
6. Report changed files, test evidence, limitations, and unresolved risks.
7. Stop. A later package begins only after a separate review decision.

| Package | Canonical gate | Depends on | Bounded deliverable | Exit evidence |
|---|---|---|---|---|
| S0 | G0 | Nothing | Reproducible project metadata, dependency groups, offline test command, publication exclusions, and clean repository baseline | A clean environment can install the declared development dependencies and run the offline smoke suite without Ollama or network access |
| S1 | R1 | S0 | Deterministic characterization tests for parsing, normalization, tools, memory, context limits, agent-loop boundaries, and existing graders | Tests reproduce current behavior and separately mark known defects without silently fixing them |
| S2 | R1 | S1 | Explicit `RunConfig`, `ToolRegistry`, `DomainPack`, `ActionPolicy`, and attempt context passed through the execution path | Two configurations execute in one process without registry, clock, hook, policy, or budget leakage |
| S3 | R1 | S2 | Existing fictional office extracted as `office_demo` plus a minimal second domain used only as a portability fixture | Both domains run through the same core; the second domain requires zero edits to core modules |
| S4 | R1 | S1–S3 | Immutable attempt identity, isolated state/artifacts/memory, transactional result commit, safe resume, and explicit failure statuses | Crash, stale-artifact, resume, and concurrent-writer tests pass |
| S5 | R1 | S1, S4 | Strict outcome graders with positive, minimally wrong, extra-action, stale-artifact, missing-artifact, and corrupt-artifact fixtures | Every adversarial fixture that should fail does fail, and grader errors cannot become model scores |
| S6 | R2 | S3, S5 | Versioned independent task generators and separated development, validation, retained, and adversarial families | Instances replay from manifests and retained families pass semantic-leakage review |
| S7 | R2 | S4–S6 | Frozen research question, conditions, baselines, ablations, models, budgets, metrics, sample-size rationale, ordering, and analysis | Protocol inputs and analysis are reviewed, versioned, and hash-pinned before outcome inspection |
| S8 | R1/R2 | S7 | Scripted-agent checks and a small live-model sentinel | End-to-end instrumentation passes; sentinel outcomes are labeled diagnostic and are not retained evidence |
| S9 | R3 | S8 | Frozen paired retained experiment | Immutable result bundle and preregistered analysis complete without instrument changes |
| S10 | R4 | S9 | Version-pinned external benchmark or independently developed generalization domain | Transfer results are reported separately with compatibility limits and complete provenance |
| S11 | P0 | S0 and owner authorization | Brix workflow map, value/risk score, selected workflow, accountable owners, and approved data plan | Brix approves the workflow boundary and data handling before any real record is accessed |
| S12 | P1 | S3, S11 | Product contract, roles, typed proposals, deterministic invariants, approval rules, provider contracts, and threat model | Brix approves acceptance tests and failure behavior; no invariant depends on a prompt |
| S13 | P2 | S12 | Synthetic Brix organization/domain pack and complete vertical slice | Product, security, concurrency, fault, recovery, and audit tests pass using synthetic data |
| S14 | P2 | S13 and separate owner authorization | Official provider sandbox or isolated test-tenant integration | Create, reconcile, retry/idempotency, correction, and rollback tests pass; absent a safe provider boundary, writes remain blocked |
| S15 | P3 | S11, S14 | Approved-data shadow evaluation without external mutations | Predeclared quality, safety, disclosure, and correction-burden thresholds pass |
| S16 | P4 | S15 | Bounded, human-approved pilot with monitoring and rollback | Brix explicitly accepts measured benefit and residual risk; production remains a separate decision |
| S17 | R5 | S9 and a diagnosed learnable failure | Provenance-complete, deduplicated training experiment evaluated through the frozen serving path | The adapter beats declared alternatives on held-out outcomes and resource tradeoffs |
| S18 | G1 | Applicable completed gates | Reproducibility release and accountable Brix handoff | Published evidence is reproducible and private Brix configuration/data remain separate |

S11 may be scheduled after S0 whenever authorized Brix stakeholders are available; it
does not block S1–S10. Calendar-level parallelism does not permit two packages to make
overlapping repository changes in the same implementation session.

The currently authorized implementation scope is **S0 through S3**. S4 and later
packages remain out of scope until S0–S3 are completed, reviewed, and explicitly
continued.

## 3. Workstreams and dependencies

Track R is the research instrument. Track P is the Brix product. Track G covers shared
governance.

| Gate | Workstream | Depends on | Authorizes |
|---|---|---|---|
| G0 | Repository truth and containment | Nothing | Safe synthetic development |
| R1 | Instrument validity | G0 | Protocol design and diagnostic pilots |
| R2 | Frozen research protocol | R1 | Retained calibration runs |
| R3 | Retained calibration experiment | R2 | Evidence-limited research claims |
| R4 | External validation and generalization | R3 | Broader, still bounded claims |
| P0 | Brix discovery and data governance | G0 | Selection of one product workflow |
| P1 | Product contract and threat model | P0 | Synthetic integration build |
| P2 | Synthetic vertical slice | P1 | Approved-data shadow evaluation |
| P3 | Shadow evaluation | P2 | Controlled live pilot decision |
| P4 | Controlled pilot | P3 | Production-readiness decision |
| R5 | Training experiment | R3 and a diagnosed failure | Adapter evaluation |
| G1 | Research publication and client handoff | Applicable completed gates | Release |

R1/R2 and P0 can proceed in parallel. R3 does not wait for a Brix integration. P2 may
reuse generic typed interfaces from R1, but it must not reuse benchmark state or
model-writable memory as a business database.

## Gate G0 — Establish repository truth and containment

### Work

1. Record the canonical repository, ownership, branch policy, and institutional/client
   publication requirements.
2. Add a root runtime dependency specification and a lock strategy. Keep research,
   web, office-file, and training dependencies separable.
3. Add continuous integration for syntax, unit tests, deterministic integration tests,
   dependency checks, and documentation links.
4. Define an artifact policy:
   - synthetic/redacted fixtures may be committed;
   - private Brix data, secrets, runtime memory, and identifiable transcripts may not;
   - retained research results require an immutable manifest and redaction review.
5. Remove tracked runtime state and host-specific settings from the intended published
   artifact. Add appropriate ignore rules without deleting a user's local records.
6. Create a machine-readable version manifest for the harness, tasks, graders, domain
   pack, analysis, dependencies, model digest, runtime, and Git commit.
7. Mark every unsupported model-performance statement as a hypothesis or remove it.
8. Ensure launchers label the UI and simulated tools as a demonstration, not a Brix
   deployment.
9. Default all real filesystem, shell, external-message, and external-calendar
   capabilities to disabled.

### Acceptance gate

- A clean checkout can install the intended environment from declared inputs.
- CI runs without Ollama, private data, or network-dependent tests.
- No secret, real Brix record, runtime memory, or identifying transcript is tracked.
- Documentation and UI describe the current status accurately.
- Synthetic development cannot invoke a general shell or mutate a real user folder by
  default.

## Gate R1 — Make the research instrument valid

Do not run a retained model matrix during this gate. Use scripted model responses and
small diagnostic runs whose outputs are explicitly disposable.

### R1.1 Offline harness characterization

Build scripted-model tests for:

- valid single-call and multi-call tasks;
- malformed JSON, braces inside strings, prose around JSON, and truncated output;
- long observations, inaccessible truncated tails, paging, and context-window
  exhaustion;
- missing, unknown, mistyped, and semantically invalid parameters;
- impossible dates and times;
- duplicate-call and loop behavior;
- tool exceptions and timeouts;
- premature `done`, empty summaries, completion-check parse failures, and budget
  exhaustion;
- memory load, write, corruption, poisoning, scope, and expiration;
- planner output that contains arbitrary prose or nonexistent tools.

Required changes:

- use typed schemas and semantic validators at the tool boundary;
- distinguish parser recovery from argument repair;
- do not fuzzy-repair write parameters; return structured correction feedback;
- make completion-check failure `unknown` or `incomplete`, never implicitly complete;
- inspect authoritative state and artifact requirements before accepting completion;
- log raw planner/completion-check output and error categories safely;
- treat model-authored memory as untrusted, scoped input with explicit write policy;
- define explicit statuses and recovery behavior for observation truncation, missing
  pagination, and context exhaustion rather than silently losing required evidence.

### R1.2 Attempt isolation and result integrity

Refactor the runner so every attempt has:

- a unique identifier;
- a new world, memory scope, and artifact directory;
- no stale PPTX, XLSX, JSON, or other file from a prior attempt;
- an immutable initial-world snapshot;
- one transactional attempt-commit protocol covering state, result, artifact manifest,
  and completion marker;
- single-writer enforcement or locking, durable atomic writes, and recovery validation
  after interruption;
- resume based on the full attempt key;
- no deletion or reset of state needed by an already completed attempt.

Represent a dependent learning pair as one isolated multi-episode scenario. Its episodes
share only that scenario's memory and execute in fixed internal order.

Reject unknown condition names, unknown task IDs, incompatible versions, and malformed
configuration. Do not silently map an unknown condition to raw.

Record execution failure, model failure, tool failure, grader failure, timeout, and
strict task failure as different statuses. A grader exception must invalidate the
attempt; it must not become a model score of zero.

### R1.3 Rewrite the graders

Create golden positive, negative, boundary, and adversarial artifacts before modifying
the grader. At minimum:

- require exact intended file identity, not filename substring;
- associate spreadsheet values with the correct rows and columns;
- associate slide values with the correct slide, title, region, and structure;
- use fixed denominators;
- inspect the current attempt's action log and state only;
- require task-specific content rather than broad substrings such as `yes`;
- reject extra unrequested emails, messages, events, reminders, or files;
- distinguish a correct final state reached through a harmful action where the task
  requires safe execution;
- make strict complete-task pass the primary result;
- keep component checks as diagnostics.

Version task definitions and graders independently. The report must refuse to combine
incompatible versions unless a deliberate migration analysis is requested.

### R1.4 Correct spreadsheet and artifact handling

Replace the spreadsheet column conversion with a tested multi-letter implementation.
Test formulas, cached values, missing files, corrupted files, extra files, and files
whose names merely contain the requested stem. Test document-generation behavior
against the actual supported library versions.

### R1.5 Explicit configuration and domain packs

Before retained runs, replace mutable module-level research configuration with explicit
objects such as:

- `RunConfig`;
- `ToolRegistry`;
- `DomainPack`;
- `ActionPolicy`;
- `ArtifactStore`.

A domain pack should supply a versioned registry, initial world, task instances,
graders, clock policy, and domain rules. The runner, command-line launcher, and web
console must receive these objects explicitly rather than mutate shared globals.

Move the existing fictional office into a calibration pack. Preserve behavior with
offline golden traces and a small diagnostic sentinel set. Do not demand identical
model output across a refactor: compare recorded configuration, deterministic state
transitions, grader outputs on golden artifacts, and prespecified diagnostic tolerances.

### R1.6 Filesystem and process safety tests

Although no general filesystem or shell belongs in the Brix product, harden the
research tools that remain:

- resolve real paths and verify containment with `commonpath`;
- reject symlink, junction, and time-of-check/time-of-use escapes;
- refuse filesystem roots, repository roots, and deletion of the configured root;
- use narrowly created temporary workspaces;
- default destructive confirmation to deny when no callback exists;
- make deletion recoverable where practical;
- remove or separately sandbox network and process execution;
- verify that stop terminates the entire owned process tree;
- apply limits to file size, count, process duration, and log volume.

Confirmation is not a sandbox and must not be described as one.

### Acceptance gate

- All offline harness, grader, isolation, resume, parser, schema, provenance, and safety
  tests pass on supported platforms.
- Deliberately reintroducing each known defect causes a targeted test to fail.
- A repeated or interrupted attempt cannot inherit artifacts or memory.
- A grader failure cannot be reported as model failure.
- The calibration pack runs through explicit configuration with no mutable global
  registry.
- A disposable sentinel run produces a complete manifest and can be analyzed from a
  clean checkout.

## Gate R2 — Freeze the research protocol

### R2.1 Specify questions and contrasts

Write a preregistration or internal frozen protocol containing:

- the neutral primary research question;
- directional or non-directional hypotheses;
- the primary paired contrasts;
- primary and secondary outcomes;
- harmful-side-effect definitions;
- exclusion and rerun rules;
- missing-data and infrastructure-failure handling;
- multiplicity handling for secondary analyses;
- the exact analysis code and report tables.

At minimum assess these conditions where technically supported:

1. deterministic workflow/rules baseline for suitable tasks;
2. reasonable native-function-calling baseline;
3. full harness;
4. preregistered component or mechanism-group ablations.

Retain prompt-only raw JSON as a minimal baseline if useful, but do not label it the
only “naive” implementation.

### R2.2 Construct independent task instances

Replace dependence on 12 fixed prompts with versioned task families and independently
generated instances. Vary names, dates, wording, policies, state, conflicts, and
irrelevant distractors. Separate generator logic and seeds from the tested agent.

Create:

- development instances visible during implementation;
- frozen validation instances for pre-run checks;
- held-out retained instances unavailable during prompt and grader tuning;
- adversarial instances covering unwanted side effects and ambiguous requests.

Check for semantic as well as verbatim overlap with training data.

### R2.3 Choose sample size and ordering

Use simulation or power analysis for the paired strict-pass outcome and anticipated
failure rates. Specify the independent unit and any repeated trials. Do not justify
uncertainty from three seed changes on an identical task.

Counterbalance or randomize model/condition/scenario-block order according to the
analysis plan. Keep dependent episodes inside a declared multi-episode scenario in their
required order. Record warmup, cooldown, power mode, temperature where available,
concurrent load, and runtime state. Treat thermal drift as a measured nuisance variable,
not something eliminated by assertion.

### R2.4 Select comparable models

Choose a same-family, same-generation size sweep with documented training and
post-training comparability that fits the available hardware. Pin:

- model repository, revision, and served digest;
- quantization;
- chat and tool template;
- thinking mode;
- serving runtime and options;
- context and output limits.

If comparable releases are unavailable or impractical, narrow the size claim. Report
cross-generation or cross-family systems separately as descriptive associations. Do not
combine Llama 3.2, Llama 3.1, and Qwen into one causal size curve.

### R2.5 Define resource accounting

Record per request and per attempt:

- input, cached, reasoning where exposed, and output tokens;
- model and wall time;
- calls, retries, repairs, and approvals;
- peak memory and energy where measurable;
- local hardware assumptions and hosted price snapshot where applicable.

No protocol may call equal call ceilings an equal inference budget. Predefine how
accuracy, safety, latency, and resource use will be shown together.

### Acceptance gate

- Protocol, task-instance set, model manifests, prompts, condition configurations,
  ablations, sample size, ordering, outcomes, and analysis code are frozen and hashed.
- Held-out instances are access-controlled until the run.
- A person not involved in implementation can identify exactly which outcomes support
  each planned claim.
- Any protocol change after unblinding creates a new version and is disclosed.

## Gate R3 — Run the retained calibration experiment

### Work

1. Prepare the reference machine from the locked environment.
2. Verify disk space, power settings, model digests, runtime version, clocks, and
   telemetry with a disposable preflight.
3. Run the frozen matrix without editing prompts, graders, tasks, or conditions.
4. Monitor infrastructure health without inspecting partial outcome patterns to tune
   the system.
5. Preserve raw append-only records, logs allowed by the privacy policy, artifact
   hashes, and the final manifest.
6. Run the frozen analysis from a clean environment.
7. Have another team member reproduce record counts, exclusions, primary metrics, and
   report tables.

### Acceptance gate

- Every planned attempt is accounted for as valid, excluded under a prespecified rule,
  or an explicitly reported infrastructure failure.
- No attempt inherited mutable state or artifacts.
- Results reproduce from immutable records and analysis code.
- Reported uncertainty matches the experimental unit and design.
- Claims are limited to the exact task families, model family, conditions, and
  resource settings tested.
- Null, negative, and adverse findings remain in the report.

Failure to pass this gate means the run is diagnostic. Repair the instrument or protocol,
version the change, and rerun; do not salvage a headline from contaminated records.

## Gate R4 — External validation and generalization

### R4.1 Select an external benchmark

Prepare a fit memo for current versions of
[WorkBench](https://github.com/olly-styles/WorkBench),
[Berkeley Function Calling Leaderboard](https://github.com/ShishirPatil/gorilla),
[τ-bench / τ²-bench](https://github.com/sierra-research/tau2-bench), and
[AutomationBench](https://github.com/zapier/AutomationBench).

For each, verify:

- current version and license;
- task and training-data overlap;
- final-state and harmful-side-effect coverage;
- required provider, customer simulator, browser, database, or container;
- whether Brick's agent loop can be integrated without changing benchmark semantics;
- compute, service, and human-review requirements measured by a small spike.

Select zero or one initially. “No suitable benchmark” is acceptable if documented.
Do not promise an integration duration before the spike.

### R4.2 Generalization packs

Add a second internal domain only if its tasks and ground truth can be independently
specified. External EdgeHarness tasks may be candidates, but first pin its commit,
verify licenses and source evidence, and reconstruct the tasks without importing
uncontrolled state.

Report each pack separately. Compare within-pack condition effects; do not average
absolute scores across packs of different difficulty.

### R4.3 Execute frozen ablations

Run only the ablations specified at Gate R2. Report interactions that were tested and
avoid attributing causality from mechanism counters. If only one model size is used,
state that limitation.

### Acceptance gate

- External or cross-domain semantics were preserved and version-pinned.
- Integration tests show that scoring and state transitions match the benchmark owner’s
  specification.
- Generalization claims name the exact domains and do not imply universal transfer.
- All deviations from the R2 protocol are versioned and disclosed.

## Gate P0 — Discover Brix workflows and approve data handling

This work may begin in parallel with R1. It must not begin by recommending a committed
solution.

### Work

1. Interview the accountable Brix owner and staff who perform the six priority
   workflows in the [Brix discovery summary](BRIX_DISCOVERY.md).
2. For each workflow, map triggers, inputs, systems of record, normal path, exceptions,
   approvals, outputs, volumes, delays, current errors, and failure consequences.
3. Inventory email, calendar, SMS, document, CRM, invoicing, access-control, and room
   systems. Confirm API availability and test environments; do not assume them.
4. Quantify a baseline using Brix-approved records or staff estimates, clearly labeling
   which is which.
5. Score candidates on value, frequency, determinism, reversibility, data readiness,
   integration effort, and harm.
6. Review the scorecard with Brix and select one first workflow plus a fallback.
7. Write and approve a data plan covering purpose, sources, fields, access, storage,
   encryption, retention, deletion, logging, model/runtime network policy, incidents,
   and responsible owners.

Possible candidates include a read-only daily follow-up dashboard, approved-document
assistance, or room conflict checking with a drafted confirmation. These remain
hypotheses until the scorecard is approved.

### Acceptance gate

- Brix approves the current-state workflow map and measured or explicitly estimated
  baseline.
- One workflow is selected by an agreed value/risk score, not by code availability
  alone.
- The authoritative system, integration owner, approvers, exceptions, and success
  threshold are documented.
- The data plan is signed off before any real record is copied or accessed.
- The pilot can be stopped without disrupting the authoritative workflow.

## Gate P1 — Specify the product contract and threat model

### Work

1. Define authenticated actors, roles, permissions, tenants, and service accounts.
2. Define typed read and action-proposal APIs. Do not expose arbitrary shell commands or
   filesystem paths.
3. Express every business invariant in deterministic code and database constraints.
4. Define approval rules, proposal expiry, idempotency, transaction boundaries,
   provider reconciliation, correction, and rollback.
5. Threat-model cross-user disclosure, prompt injection, stale documents, malicious
   attachments, confused deputies, replay, forged local requests, link traversal,
   concurrency, provider failure, and compromised model output.
6. Define audit events, redaction, monitoring, alerts, backup, recovery, and incident
   ownership.
7. Write product acceptance tests before implementation.

If scheduling is selected, tests must cover overlap under concurrency, room identity,
timezones, recurrence, buffers, hours, capacity, equipment, entitlements, cancellation,
and duplicate requests as applicable to Brix policy.

If approved-document assistance is selected, tests must cover access filtering before
retrieval, version/effective date, exact citations, conflicting sources, missing
evidence, abstention, malicious document instructions, and cross-user isolation.

### Acceptance gate

- Brix signs off on the product contract, approval points, and failure behavior.
- Threat-model mitigations map to tests and accountable components.
- No invariant depends on a prompt, model memory, or model-based verifier.
- The design uses least-privilege, allowlisted adapters.

## Gate P2 — Build a synthetic vertical slice

### Work

1. Implement the deterministic domain service and transactional state store.
2. Implement provider interfaces against fakes for development and against an official
   provider sandbox or isolated test tenant for integration testing.
3. Let the model produce typed proposals only; reject invalid or unauthorized proposals
   before approval.
4. Build an authenticated approval queue showing the exact proposed side effect, actor,
   source evidence, expiry, and rollback path.
5. Add immutable audit records and provider reconciliation.
6. Add authentication, authorization, origin/CSRF protection, safe secret handling,
   input and resource limits, and process supervision to the product interface.
7. Exercise the complete workflow with synthetic data, faults, concurrency, retries,
   duplicate delivery, and recovery.

Do not adapt the current demonstration server directly into production without these
boundaries. Loopback binding is not sufficient access control.

### Acceptance gate

- Product acceptance, security, fault-injection, concurrency, and recovery tests pass.
- No model output can bypass authorization or deterministic validation.
- Duplicate and concurrent requests preserve the declared invariants.
- Every external mutation is attributable and reconcilable.
- The complete slice runs with synthetic data and provider sandboxes.
- Create, reconcile, retry/idempotency, correction, and rollback behavior passes against
  the actual provider sandbox or isolated test tenant. If the provider offers no safe
  test boundary, the write workflow is blocked from pilot.

## Gate P3 — Run approved-data shadow evaluation

### Work

1. Complete privacy/security review and provision least-privilege test credentials.
2. Replay or observe an approved, bounded sample without external mutations.
3. Have trained Brix staff label ground truth and review proposed actions.
4. Measure the predeclared workflow outcomes, including missed actions, false or
   unauthorized proposals/attempts, disclosure attempts, correction burden, latency,
   and staff time.
5. Test deletion, access revocation, backup restoration, incident response, and provider
   outage behavior.
6. Compare with the documented current process and the deterministic baseline.

### Acceptance gate

- The predeclared shadow threshold is met without changing it after results are viewed.
- There are zero unauthorized proposals accepted by deterministic policy, zero
  unauthorized mutation attempts reaching the provider adapter, and zero cross-user
  disclosures.
- Brix reviews failures and residual risks and explicitly decides whether to pilot.
- Monitoring, support, stop, rollback, and data-deletion procedures are demonstrated.

If the threshold is missed, return to P1 or P2. Do not compensate by silently expanding
model authority.

## Gate P4 — Conduct a controlled pilot

### Work

1. Limit users, data scope, workflow scope, operating hours, and duration in writing.
2. Keep human approval for every external mutation unless a later risk review authorizes
   a narrower deterministic action.
3. Maintain the existing authoritative workflow and a tested rollback during the pilot.
4. Review incidents, near misses, override burden, adoption, reliability, and time saved
   on an agreed cadence.
5. End, revise, or advance the pilot based on the predeclared decision rule.

### Acceptance gate

- Brix accepts measured benefit and residual risk.
- An accountable product owner and operational support path exist.
- Access reviews, monitoring, backup, recovery, retention, deletion, and incident
  procedures operate in practice.
- Production authorization is a separate recorded decision; a successful pilot does
  not automatically become deployment.

## Gate R5 — Consider a training experiment

Training is blocked until R3 identifies a stable failure that is plausibly learnable.

### Work

1. State the diagnosed failure and why deterministic validation, task design, or
   orchestration is not the better fix.
2. Rebuild the dataset with license and source provenance, exact deduplication, semantic
   overlap checks, and coverage of the relevant tool and state space.
3. Split by task template, entity, policy, and phrasing family so the held-out set tests
   transfer rather than memorization.
4. Mask deliberately bad assistant turns in repair demonstrations unless emitting the
   bad call is explicitly part of the objective.
5. Reject underdetermined examples whose targets invent missing facts.
6. Pin base model, tokenizer, template, training code, dependencies, random seeds,
   hardware, converter, and serving runtime.
7. Make conversion and serving failures fatal and test the produced artifact through
   the real evaluation client.
8. Freeze a comparison among the untrained model, trained model, deterministic or
   orchestration fix, and an appropriate larger model.

### Acceptance gate

- Dataset statistics, licenses, provenance, duplicates, and leakage checks are
  published.
- Validation and held-out test families were not used for prompt or training tuning.
- The served adapter artifact is hash-pinned and evaluated through the frozen R3 path.
- Gains are reported with uncertainty, resource cost, regressions, and safety outcomes.

## Gate G1 — Publication and client handoff

### Research release

Include:

- the frozen question, protocol, and analysis;
- exact scope of models, tasks, conditions, hardware, and versions;
- strict success, harmful effects, uncertainty, and resource tradeoffs;
- all exclusions, grader or infrastructure failures, null results, and regressions;
- a reproducibility package containing synthetic data and non-sensitive artifacts;
- a limitations section that rejects universal, parity, and unmeasured size claims.

Do not write “scaffolding beats scale” unless the specified comparison supports that
statement, and then qualify it to the tested systems. Do not state that a system keeps
data local without a verified deployment and network boundary.

### Brix handoff

Include:

- workflow and system-of-record documentation;
- architecture, threat model, and data-flow diagram;
- access, retention, deletion, audit, backup, recovery, and incident procedures;
- provider contracts and credential-rotation instructions;
- acceptance and pilot evidence;
- known limitations, prohibited uses, rollback, and support ownership.

The research scaffold and private Brix configuration/data remain separate artifacts.

## Immediate next work

The following work is unblocked:

1. Complete G0 repository hygiene and dependency/CI setup without touching private data.
2. Implement R1 offline characterization tests and grader golden cases.
3. Design R1 explicit configuration and attempt-isolation changes.
4. Prepare the P0 workflow/value-risk worksheet; contact or schedule Brix only
   after the project owner authorizes that external coordination.
5. Draft the data-governance questionnaire without requesting or ingesting records.

The following work is blocked:

- a retained model matrix, until R1 and R2 pass;
- a committed recommendation of the first Brix workflow, until P0 passes;
- access to real Brix data, until the data plan is approved;
- mutations against Brix authoritative or production systems, until P2 and P3
  pass; isolated provider-sandbox/test-tenant writes require separate owner
  authorization and are limited to P2 contract tests;
- fine-tuning, until R3 identifies a suitable failure;
- production deployment, until a separate post-pilot authorization.

## Stop conditions

Stop the affected track and reassess if:

- a benchmark attempt can inherit state or artifacts;
- grader behavior changes without a version change;
- private data appears in Git, model memory, logs, or research artifacts;
- a model can bypass deterministic authorization or a business invariant;
- the selected provider cannot supply an authoritative or testable interface;
- task/training leakage invalidates held-out evaluation;
- resource accounting is incomplete for a planned efficiency claim;
- a protocol change is proposed after outcome inspection without a new version;
- Brix cannot assign an accountable owner or accept the residual risk.

Stopping at a failed gate is correct project control, not project failure.

# Project Guide

Last reconciled with the local project tree: 28 July 2026.

Related material:

- [Brix discovery summary](BRIX_DISCOVERY.md)
- [Brick repository documentation](README.md)
- [Brick architecture notes](ARCHITECTURE.md)
- [Implementation plan](PROJECT_SETUP.md)
- [Canonical repository](https://github.com/EdgeHarness/Brick-Agent-Harness)

## 1. Current status

Brick is currently a **synthetic research scaffold** for testing tool-using local language
models. It contains:

- a simulated office world;
- raw and harnessed agent loops;
- simulated email, calendar, messaging, and reminder tools;
- local document-generation tools;
- a small, hand-authored benchmark;
- an Ollama client, a demonstration web interface, and experimental adapter-training code.

It does **not** currently contain:

- a valid retained benchmark result;
- evidence that the harness improves any model;
- a production Brix workflow;
- a Brix email, calendar, messaging, document, CRM, billing, or room-booking integration;
- production authentication, authorization, audit, retention, or recovery controls;
- a safe general-purpose filesystem or shell sandbox;
- a tested fine-tuned model that is served through the application.

No result directory or retained result is present, and result paths are excluded from
version control. The existing benchmark and graders also have validity defects described
in the [implementation plan](PROJECT_SETUP.md).
No performance, reliability, cost, or safety conclusion may be drawn until those defects
are repaired and a protocol is frozen.

The web interface is an experiment console over simulated state. It is not a Brix
application or a deployment candidate.

## 2. Evidence rules

Project language must distinguish the following states:

- **Implemented:** code exists.
- **Tested:** an automated test exercises the stated behavior.
- **Validated:** the behavior passed a frozen evaluation with recorded provenance.
- **Integrated:** the code communicates with the named external system in an approved
  test environment.
- **Piloted:** approved users exercised the integrated workflow under a written pilot
  protocol.
- **Deployed:** the system has an accountable owner, access controls, monitoring,
  recovery procedures, and an approved production boundary.

These terms are not interchangeable. A simulated calendar tool is implemented; it is
not a calendar integration. A model-generated completion checked by the same model is
not independently verified. A loopback HTTP endpoint limits one network path; it does
not prove that no data can leave the machine.

Every experimental performance, reliability, safety, latency, resource, or cost
statement must point to:

1. the immutable result bundle;
2. the task, grader, harness, and domain versions;
3. the exact model identifier and digest;
4. the runtime and dependency versions;
5. the hardware and execution settings;
6. the analysis that produced the reported number.

Static code and dataset claims instead require a pinned commit, source path, and
reproducible inspection or test.

Predictions belong under “hypotheses,” not in model READMEs as observed behavior.

## 3. Two separate tracks

The work has two related but distinct tracks.

### Track R: research instrument and experiments

Track R asks whether explicitly identified orchestration mechanisms improve agent
performance under recorded resource constraints. Its artifacts are synthetic task
instances, frozen graders, run manifests, result bundles, and a reproducible analysis.

Track R must not depend on private Brix data. Brix-inspired task classes may be used,
but retained public experiments must use synthetic or properly redacted records with
documented provenance.

### Track P: Brix product discovery and pilot

Track P identifies one valuable Brix workflow, builds the required deterministic
service and approved integrations, and evaluates it first in shadow mode and then in a
controlled pilot. Its artifacts include process maps, policies, data agreements,
integration contracts, access controls, audit records, and operational acceptance
tests.

Track P is not evidence for Track R unless its task instances and scoring procedure
were frozen in advance and can be evaluated without disclosing protected data.
Likewise, a research benchmark score is not evidence that the product is safe or
valuable in operation.

The tracks may share generic interfaces, telemetry formats, and synthetic domain
models. They must not share uncontrolled state, private data, or unexamined assumptions.

## 4. Research question

The research question is deliberately neutral:

> Under fully recorded resource constraints, which explicit orchestration mechanisms,
> if any, improve strict end-state task success and reduce harmful side effects for
> comparable local language models?

Secondary questions are:

- How do any gains change with model size within one model family?
- What token, latency, memory, energy, and approval costs accompany those gains?
- Which task classes remain beyond a model despite orchestration?
- Do observed effects persist across independently constructed task instances and an
  appropriate external benchmark?

“Scaffolding beats scale” is a possible result, not a premise. The experiment must be
able to find no improvement, a capability floor, or a cost increase that outweighs an
accuracy gain.

No claim of frontier-model parity is planned. Cross-model comparisons remain
descriptive unless family and generation are controlled, training and post-training
comparability are documented, and quantization, serving configuration, prompt format,
and inference mode are held constant. Even then, parameter count is an association
unless the releases were designed as a controlled scale series.

## 5. What the current comparison does and does not establish

Brick presently exposes two agent paths:

- **Raw:** prompt-based JSON tool selection with the shared simulated tools.
- **Harness:** the same basic loop plus planning, examples, parsing and repair,
  normalization, loop handling, memory injection, and a model-based completion check.

This is useful prototype structure, but it is not yet a fair or causal experiment.

### Call count is not inference budget

A shared 14-call ceiling equalizes only the maximum number of calls. The conditions can
use different prompts, output limits, planning and completion-check calls, history
lengths, and total tokens. They therefore do not have an equal inference budget.

Runs must record total input and output tokens, model execution time, wall time, memory,
energy where measurable, retries, approvals, and calls. Results should show an
accuracy/safety/cost frontier rather than declaring one budget “the same.”

### The raw condition is not sufficient by itself

Prompt-only JSON is a useful minimal baseline, but it can be a weak representation of
ordinary tool integration. Where supported, the protocol should include:

1. a deterministic workflow or rules baseline for tasks that do not require a model;
2. a reasonable native-function-calling baseline with ordinary validation and retry;
3. the full harness;
4. preregistered harness ablations.

Comparisons must use the same authoritative tool implementations and world transitions.

### The current harness mechanisms are not all safety mechanisms

The present “schema validation” largely checks parameter names, not complete types and
business semantics. Fuzzy argument repair can convert an uncertain write into a valid
but wrong write. The completion checker uses the same model, can fail open, and does not
independently inspect all artifacts or authoritative state. Model-authored memory is
untrusted input, not durable business knowledge.

These mechanisms may improve formatting or recovery. Their effects and failure modes
must be measured; they must not be presented as enforcement boundaries.

## 6. Valid experiment design

### Experimental unit

Independent task instances—not repeated decoding of an identical prompt—are the main
experimental units. Instances should vary entities, dates, policies, document wording,
initial world state, and valid action sequences while preserving a declared task class.

A fixed seed and temperature-zero decoding can aid replay, but neither guarantees
bit-for-bit reproducibility across runtimes and hardware. Changing a seed does not by
itself create an independent business case. The number of instances and repetitions
must be justified before retained runs, using a power or simulation analysis appropriate
to paired binary outcomes.

### Model comparison

The primary size analysis must use models from the same family and generation, with
documented training/post-training comparability and the following controls:

- immutable model digests;
- consistent instruction and chat templates;
- consistent quantization policy;
- a pinned serving runtime;
- controlled thinking or non-thinking behavior;
- recorded context and generation limits.

Mixing Llama 3.2 at 1B/3B, Llama 3.1 at 8B, and Qwen at larger sizes changes family and
size together and cannot identify a size effect. Cross-family results may be reported
as separate system comparisons, not as one parameter-size curve.

### Outcome measures

Primary measures:

- strict complete-task success;
- unauthorized or harmful side-effect rate;
- success without human correction;
- reliability across independent task instances.

Secondary diagnostics:

- fixed-denominator component checks;
- invalid-call and repair counts;
- retries, loops, and completion-check disagreements;
- tokens, model time, wall time, memory, energy, and approvals;
- cost per strict success under a stated cost model.

A loose average over grader checks is not a substitute for strict success. Additional
unrequested messages, events, reminders, or files must count as failures or harmful
effects where appropriate.

### Isolation and provenance

Every independent attempt requires:

- a fresh artifact directory and memory scope;
- an immutable initial-world snapshot;
- no artifacts inherited from a prior attempt;
- a single-writer or locked transactional attempt commit covering state, result,
  artifacts, and completion, with durable-write and recovery validation;
- a unique attempt identifier;
- explicit task-instance, condition, repeat, ordering, and seed fields;
- task, grader, harness, domain-pack, model, runtime, dependency, Git, and hardware
  versions;
- separate recording of execution failure, grader failure, and task failure.

An explicitly declared multi-episode scenario, such as memory write followed by memory
use, is one experimental unit: its dependent episodes share only that scenario's memory,
run in fixed internal order, and remain isolated from every other scenario.

Reports must refuse incompatible versions by default. Absolute scores from different
domain packs must not be pooled as though their difficulty were equal.

### Causal attribution

All intended ablations must exist as configuration before the protocol is frozen.
Removing one mechanism at a time may still miss interactions, so causal language should
be limited to the tested contrasts. Mechanism counters are descriptive; by themselves
they do not prove why a score changed.

## 7. External validation

An external benchmark is useful only if its task semantics, side effects, model
interface, and scoring answer the research question. Adoption requires a short fit
assessment and a pinned benchmark version or commit.

Candidates to assess include:

- [WorkBench](https://github.com/olly-styles/WorkBench), because it emphasizes workplace
  tasks, final state, and harmful side effects;
- [Berkeley Function Calling Leaderboard](https://github.com/ShishirPatil/gorilla),
  for function-call correctness and format behavior;
- [τ-bench / τ²-bench](https://github.com/sierra-research/tau2-bench), for policy-aware,
  multi-turn agent behavior;
- [AutomationBench](https://github.com/zapier/AutomationBench), for simulated SaaS
  workflows.

These projects change over time. Their current requirements, licenses, task leakage,
provider assumptions, and evaluation semantics must be checked immediately before a
selection. No duration, cost, or compatibility estimate should be stated before a
small integration spike.

External benchmarks supplement rather than validate weak internal graders. The internal
instrument must be sound first.

## 8. Brix discovery comes before use-case commitment

The [Brix discovery summary](BRIX_DISCOVERY.md) identifies several needs but does not provide enough
evidence to rank them conclusively. It names email and task organization, lead and
member follow-up, onboarding, conference-room scheduling, maintenance tracking, and
approved-document search. Brix also prefers one or two reliable functions first.

Before recommending a build, conduct workflow discovery with the accountable Brix
owner and the people who perform the work. For each candidate, record:

- event volume, current time spent, error rate, and cost of failure;
- current systems and authoritative records;
- actors, roles, approvals, and exception paths;
- policy rules, service-level expectations, and escalation;
- data categories, retention, access, and legal or contractual restrictions;
- integration availability and test environments;
- reversibility, observability, and how success will be measured.

Score candidates on business value, frequency, data readiness, integration effort,
determinism, reversibility, and potential harm. Have Brix approve the scorecard and the
selected workflow.

Two plausible starting hypotheses—not commitments—are:

- a read-only daily action/follow-up dashboard or approved-document assistant;
- room conflict checking with a drafted booking and confirmation, approved by a person.

Automatic booking should not be assumed to be the first release. Scheduling is not a
four-step closed problem: production requirements can include room identity, capacity,
equipment, opening hours, time zones, recurrence, buffers, rates, entitlements,
concurrent requests, cancellation, no-shows, reminders, and provider reconciliation.

Approved-document search is also not harmless merely because it is read-only. It can
disclose data, use stale or unauthorized material, follow instructions embedded in a
document, or provide a confident wrong policy answer.

## 9. Product architecture principles

The language model may interpret a request or propose an action. It must not own the
business invariant.

For every write workflow:

1. resolve the authenticated actor and authorization;
2. retrieve current authoritative state;
3. construct a typed action proposal;
4. validate policy and business invariants in deterministic code;
5. show the exact effect to an authorized approver when approval is required;
6. commit transactionally with an idempotency key;
7. write an immutable audit event;
8. reconcile the provider result and expose rollback or correction.

### Scheduling requirements

A scheduling service—not the model—must enforce overlap prevention, resource identity,
hours, timezone handling, capacity and equipment, recurrence, cancellation, and
idempotency. Concurrency tests must demonstrate that two simultaneous valid-looking
requests cannot both reserve the same resource.

### Knowledge requirements

An approved-document service must enforce access before retrieval, record document
owner/version/effective date, cite the evidence used, distinguish quotation from model
text, detect conflicts, and abstain when evidence is missing or unauthorized. Retrieval
quality and answer faithfulness are separate measures.

### Capability boundary

The Brix product should not expose a general shell or general filesystem mutation to the
model. Use narrowly allowlisted adapters and least-privilege service accounts. Human
confirmation is an additional control, not a sandbox.

The current filesystem implementation is unsuitable for private or production data:
lexical path containment can be bypassed by filesystem links, deletion can target the
configured root, and a shell can leave its initial directory or use the network.

### Web and operational boundary

Loopback binding is not authentication. Any product interface requires authenticated
sessions, authorization, request-origin protection, bounded inputs and logs, secure
secret handling, safe process termination, monitoring, backup, recovery, and an
incident owner. Confirmations must be bound to a specific authenticated user, proposal,
and expiry.

## 10. Data governance

No real Brix data may be copied into the repository, benchmark artifacts, model memory,
or logs until a written data plan is approved.

The plan must specify:

- data owner and accountable system owner;
- permitted sources and purposes;
- fields collected and fields excluded;
- storage location, encryption, and backup;
- user and service-account access;
- retention and deletion periods;
- log and transcript redaction;
- whether external inference, telemetry, package downloads, or updates are allowed;
- breach and incident response;
- how a person can inspect and correct records.

Committed tasks and examples must use synthetic or approved redacted data. Runtime
memory must be treated as untrusted, private state with provenance, scope, expiration,
validation, and deletion—not as a text file the model may silently rewrite.

“Local inference” may be a valuable privacy property, but it must be demonstrated by
network and deployment controls. It does not follow from using Ollama, and it does not
cover package downloads, hosted comparisons, shell commands, browser access, logs, or
backups.

## 11. Training policy

Fine-tuning is last, not a prerequisite.

The two current 1,200-row datasets differ, contain substantial exact duplication, cover
only part of the tool surface, and do not provide a defensible held-out evaluation.
Repair conversations are also trained in a way that can reward the deliberately bad
assistant call. Base-model and conversion-tool revisions are not fully pinned, and
conversion failure is not reliably propagated.

Training is justified only after a frozen evaluation identifies a stable failure mode
that:

- is plausibly learned rather than better enforced in code;
- appears on independent held-out task families;
- has enough licensed, provenance-tracked examples;
- has a leakage-resistant train/validation/test split;
- can be served through the same recorded evaluation path.

The relevant comparison is not simply “adapter versus no adapter.” It should compare
the trained system with deterministic fixes, orchestration, and an appropriate larger
base model at recorded quality and resource costs.

## 12. Repository and documentation governance

Brick is the local system under examination. The EdgeHarness repository is not present
in this workspace, so earlier detailed claims about its runtime behavior, saved results,
line counts, and portability are not independently verified here. Before reusing code
or citing evidence from it:

1. pin the exact commit;
2. run its tests or add characterization tests;
3. verify licenses and dependencies;
4. reproduce any result under a documented protocol;
5. port only a bounded capability with an explicit acceptance test.

Repository ownership, authorship, and institutional policy should be agreed before
external publication or client operation. Use protected branches, reviewed changes,
continuous integration, and no secrets or private client artifacts in Git.

Documentation is part of the instrument. When behavior changes, update code, tests,
version stamps, and relevant documentation in the same reviewed change. A “current
state” section must be generated or checked against the repository before release.

## 13. Definition of success

### Research success

Research is complete only when:

- the instrument passes adversarial validity tests;
- the protocol and analysis are frozen before retained runs;
- result bundles carry complete provenance;
- primary outcomes and uncertainty are reported without pooling incompatible tasks;
- negative and null results are retained;
- claims are limited to the tested models, tasks, conditions, and resource settings;
- another person can reproduce the analysis from the published artifacts.

A result that orchestration does not help, or helps only at unacceptable cost, is still
a valid research result.

### Product success

A Brix pilot is ready only when:

- Brix has selected and documented the workflow;
- an authoritative data source and accountable owner exist;
- deterministic business invariants and access checks pass;
- approved integrations work in a test environment;
- private-data handling is documented and enforced;
- shadow evaluation meets a threshold agreed before testing;
- human approvals, audit, monitoring, recovery, and support ownership are operational.

The next actions and all dependencies are specified in the
[gated implementation plan](PROJECT_SETUP.md).

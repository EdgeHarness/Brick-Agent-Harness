# Project Guide

Last reconciled with the local project tree: 1 August 2026.

The canonical execution plan is [`PROJECT_SETUP.md`](PROJECT_SETUP.md). This
guide defines the durable evidence, architecture, and claim rules. Released
history is recorded in [`CHANGELOG.md`](CHANGELOG.md).

## 1. Candidate status and release authority

The latest release is `v0.7.0` (B0 synthetic lead-follow-up slice), preceded by `v0.6.0` (S1R repaired runtime), `v0.5.0` (S4 evidence store) and `v0.4.0` (F0/Q0 feasibility). Brick
is an experimental local agent-harness research scaffold with:

- explicit runtime, registry, policy, hook, and domain-pack contracts;
- `office_demo@0.1.0`, a synthetic office fixture;
- `counter_demo@0.1.0`, a structural portability fixture;
- legacy prompt-JSON raw and harness loops;
- simulated email, calendar, messaging, and reminder effects;
- local PowerPoint and spreadsheet generation;
- a production marker-last evidence store and its native S4 attestor; and
- an exploratory benchmark, local Ollama client, Agent Lab development console,
  and blocked experimental training code.

F0/Q0 is released as `v0.4.0` and S4 as `v0.5.0`. The native Lenovo F0 gate
passed, recording host and model feasibility; the native Windows ARM64 S4 gate
passed from candidate `0b8f77d` with `overall_status` pass, 461 passed, 0 failed
and `s4_skipped` 0. Both record instrument behaviour only. S1R through S9 are
unstarted.

Annotated tags and their bound evidence are authoritative. The tagged S4 release
commit `R` adds only `evidence/s4/v0.5.0.json` to tested candidate `C`; docs-only
descendant `D` promoted this status afterwards and is not part of `v0.5.0`. See
the exact lifecycle in
[`PROJECT_SETUP.md`](PROJECT_SETUP.md#native-windows-arm64-attestation).

Brick currently has no valid retained result, demonstrated harness improvement,
production Brix workflow, real Brix integration, production identity/access
control, or served fine-tuned model. Existing benchmark outputs are exploratory.

The Mac is a source-development and offline-test host only. Live-model evidence
runs on the native Windows 11 ARM64 Lenovo described in the canonical plan.

## 2. Evidence vocabulary

Use these states precisely:

- **Implemented:** code exists.
- **Tested:** an automated test exercises the named behavior.
- **Validated:** the behavior passed a frozen evaluation with complete recorded
  provenance.
- **Integrated:** code communicates with the named external system in an
  approved test boundary.
- **Piloted:** approved users exercised the integration under a written pilot.
- **Deployed:** an accountable owner, access controls, monitoring, recovery, and
  an approved production boundary exist.

These states are not interchangeable. A local simulated calendar is not a
calendar integration. A model verifier is not independent outcome evidence.
Loopback binding is not authentication. A release tag is not proof that a
research gate passed.

Every experimental performance, safety, latency, resource, or cost statement
must identify:

1. the validated immutable result bundle;
2. task generator, instance, grader, harness, and domain versions;
3. exact model tag, digest, quantization, template, and sampling options;
4. runtime, dependency, code, and analysis digests;
5. hardware, operating-system, driver, backend, and power settings; and
6. the exact analysis that produced the number.

Predictions and model-folder labels are hypotheses, not observations.

## 3. Active milestone and product boundary

The active milestone has two related outputs:

- **Research:** a valid fixed-family comparison of a generic harness against a
  competent native-tools baseline.
- **Synthetic layering:** a planned fictional Brix lead-follow-up pack intended
  to test whether a business layer can be replaced without rewriting the
  harness.

The synthetic Brix pack may share generic interfaces, telemetry, and evidence
formats with the research instrument. Generic packages may not import it or
contain Brix branches. It may not use real Brix data, credentials, providers, or
systems.

The synthetic pack is not a selected Brix production workflow. Actual workflow
discovery, data authorization, integration, shadow evaluation, pilot, and
deployment remain future work outside the `v0.14.0` milestone.

### Repository roles and convergence

`EdgeHarness/Brick-Agent-Harness` is the authority for the research instrument,
stage gates, immutable evidence, frozen conditions, and retained analysis.
`SMalshe/Brick` is a separate product-prototype lineage. A moving product branch
is not a research condition, benchmark dependency, source of retained task
instances, or substitute for a frozen domain pack.

The two tracks converge through versioned contracts, not by synchronizing their
working trees:

1. define and test generic tool, state, attempt-evidence, and domain-pack
   interfaces in the research repository;
2. keep B0 fictional and no-network so it tests replaceable layering without
   importing product code or data;
3. identify any future product integration by an immutable repository commit,
   adapter version, schema digest, and conformance result;
4. evaluate that integration separately through approved synthetic or redacted
   shadow data before any pilot; and
5. never change the frozen retained instrument to match observed product or
   benchmark outcomes.

Mechanisms that survive the research gates may later be ported into, packaged
for, or consumed by the product repository. That engineering transfer is not
evidence that the product satisfies the research result, and product behavior is
not evidence that the frozen benchmark instrument is valid.

## 4. Research question and scope

The sole confirmatory question is:

> For the 11 fixed synthetic Brick task-family generator distributions, does
> `harness_full` improve strict whole-task success over a competent
> `native_tools` implementation on the pinned Qwen3.5 4B system under the same
> end-to-end opportunity budget?

The primary result is limited to those frozen generator distributions, model
digest, conditions, and budgets. It does not establish:

- performance across all office work or unseen domains;
- production value or safety for Brix;
- parity with a frontier model;
- a universal benefit from orchestration;
- a causal model-size law; or
- within-instance repeatability.

Qwen3.5 2B and 9B are descriptive system replications. Same family name and
quantization do not prove controlled training or post-training across sizes.
Broader generalization requires a later independently developed domain or
suitable pinned external benchmark.

“The harness helps,” “the harness does not help,” and “deterministic rules are
preferable” are all acceptable outcomes. A positive result is not a completion
requirement.

## 5. Fair condition design

The released `v0.3.1` raw and harness paths are legacy exploratory
implementations. They differ in prompting, parser behavior, repair, planning,
verification, history, and memory. `raw` is a lower bound, not a competent native
tool baseline.

The retained primary instead compares `native_tools` and `harness_full` using the
same:

- Ollama native function-call endpoint and chat template;
- Qwen3.5 4B digest;
- `ToolSpec` names, schemas, order, and tool-result transport;
- deterministic validators, authorization rules, and state transitions;
- task instance, initial state, and hidden grader; and
- context, sampling, call, and output opportunity limits.

The full harness may add only its versioned planning, scoped untrusted memory,
known-alias recovery, duplicate suppression, observation management, and
completion guard. Hidden grader logic is unavailable to both.

All driver, planning, and completion calls count against the same end-to-end
ledger. This deliberately asks whether the harness pays for its own overhead.
It does not make calls, tokens, FLOPs, energy, or latency identical. Reports show
the complete success/safety/resource frontier.

The frozen candidate settings are:

- context 8192;
- thinking disabled;
- temperature 1.0, `top_p=1.0`, `top_k=20`, and `min_p=0`;
- presence penalty 2.0 and repeat penalty 1.0;
- maximum 700 generated tokens per request;
- maximum 4096 generated tokens and 14 total model calls per attempt; and
- a deterministic per-instance seed base reused for the paired conditions.

F0 saves the exact accepted payloads and, under protocol v2, requires the
selected Lenovo Ollama build to *recognize* every frozen option name
individually: each name given a deliberately invalid value type must return a
4xx/5xx response naming the key and its declared type. The same invalid value
under an unknown name is a diagnostic probe; acceptance or rejection is recorded
but does not gate the run. Brick validates every production request against the
frozen contract before it reaches the network, and F0 also captures the effective
template and loaded context and requires thinking to remain disabled.

Protocol v1 instead required rejection of an unknown option name. Ollama does not
promise that, so that gate failed on correct server behavior and was corrected
and versioned rather than waived. What the v2 suite establishes is per-key
recognition and the declared value type for the exact production option map. A
black-box request cannot prove the numerical behavioral effect of any sampling
value, and Brick makes no such claim. Generated-output differentials are
descriptive diagnostics only: at the frozen neutral values (`top_p=1.0`,
`min_p=0`, `repeat_penalty=1.0`) an applied no-op and an ignored key are
indistinguishable in any output.

## 6. Experimental units and outcomes

Independent structural task instances are the units. They vary task structure,
policies, state, valid action sequences, wording, entities, dates, conflicts, and
distractors. Seed changes and renamed entities inside one template do not create
independent business cases.

The learning family remains one case and one logical attempt. Its ordered
store-then-use subepisodes share one isolated memory scope and the same
14-call/4096-generated-token ledger without a reset. Both subepisodes must pass
strictly; an instrument failure in either makes the case null. This definition,
rather than treating the subepisodes as separate attempts, preserves the stated
440-primary and 662-default-maximum counts.

The primary outcome is strict whole-task success. Any harmful, unauthorized,
stale, missing, extra, or incorrect effect makes strict success false. A runner,
store, grader, or analysis failure produces null model outcome, never a score of
zero.

The estimand gives equal weight to the 11 fixed families:

```text
Delta = (1 / 11) * sum(family_mean(harness_success - native_success))
```

The default retained design has 20 cases per family, 220 pairs, and 440 model
attempts. D0 may select the predeclared 12-per-family fallback using runtime
only.

The inferential gate for the equal-family estimand is a predeclared 95%
within-family percentile-bootstrap interval. It uses 20,000 draws, seed
`20260729`, NumPy `Generator(PCG64)`, draw-major/family-major resampling of paired
case differences, and Hyndman–Fan type-7 quantiles. Families and cases are sorted
by frozen IDs. Every family contributes `N` replacement draws and equal weight;
constant families remain as point masses rather than being dropped or jittered.

A two-sided exact paired sign-flip p-value is retained only as a diagnostic under
the sharp pairwise-exchangeability null. It is numerically McNemar with complete
equal allocation, but it is not an exact test of the weaker null `Delta=0` when
family effects differ. A positive claim still requires a positive effect,
diagnostic `p < 0.05`, and a bootstrap lower bound above zero. Publish all family
effects and leave-one-family-out sensitivity. The pinned analysis environment and
golden fixtures must reproduce the draw indices, p-values, estimates, and
interval endpoints exactly.

There is one stochastic draw per retained cell. Report the success distribution
across independent cases; do not report pass-at-\(k\), run-to-run reliability, or
absence of stochastic variance.

All 2B/9B replications, raw results, rules results, harness ablations, memory
ablation, and equal-action sensitivity are descriptive. They receive no
confirmatory p-values and cannot support “mechanism X does not matter.”

## 7. Evidence integrity

Every logical attempt has one full key and one or more auditable physical
candidates. A candidate executes directly in a never-reused
`attempts/<logical-hash>/<physical-uuid>/` directory.

The production store is `harness/evidence.py`. Its strict
`brick.attempt-key/1` identity includes the domain name/version/content digest,
task family/version, generator and grader versions, model tag/digest, condition
name/version/mechanism digest, instance ID/content digest, ordered subepisode
IDs, repeat, sampling map, opportunity-budget map, prompt digest, and tool-schema
digest. Atomic attempts use an empty ordered-subepisode list. S4 requires a
nonempty sampling object without JSON floats and a nonempty opportunity-budget
object of nonnegative integer counts. It preserves both maps without inferred
defaults. The later versioned benchmark protocol freezes their exact keys,
ranges, and decimal-string grammar before retained use.

Attempt-key bytes are compact, key-sorted UTF-8 JSON with every string normalized
to NFC and no trailing newline. Unknown or missing keys, duplicate object keys,
wrong types, noncanonical digests, duplicate subepisode IDs, and normalization
collisions fail closed. The logical hash is SHA-256 of those exact bytes.

Each run has one immutable `brick.evidence-run/1` `run.json`. Its hash is bound
into each strict `brick.evidence-attempt/1` envelope, so moving a candidate
between runs cannot preserve validity. State, result, grade, and action files
also use strict versioned S4 envelopes. Domain state, metrics, diagnostics, and
action payloads remain opaque to S4 and are hashed exactly; later stages own
their semantics.

After every evidence file is closed and hashed, the writer creates and validates
`PREPARED.json`, then publishes by exclusively creating the empty regular file
`COMMITTED`. No attempt directory is renamed or replaced.

`run.lock` is a persistent regular file and is never deleted or replaced. Every
writer holds one exclusive OS lock—from recovery scanning before any model
access through physical execution, publication, and projection rebuilding—using
POSIX `flock` or Windows `LockFileEx`. Process termination releases the lock
without changing the lock-file identity.

A reader accepts only a marker-present bundle whose prepared manifest and hashes
validate. Valid prepared evidence without the marker is adopted without another
model call. Incomplete evidence is preserved as abandoned. Duplicate valid
candidates, logical collisions, or invalid committed evidence halt the run.
Committed bundles are immutable. `results.json` is a rebuildable projection, not
source evidence.

The guarantee is fail-closed process-termination recovery. Sudden-power-loss
durability is not claimed.

Execution, grader, tool, publication, and strict-task statuses remain orthogonal.
Only a fully committed, validated, graded attempt may have a non-null strict
outcome.

Record status, publication status, and strict success are derived reader
properties, never post-preparation mutations. `grade.json` stores a candidate
grader decision rather than `strict_success`. Runner, environment, operator,
store, and grader failures remain instrument-invalid with a null strict outcome;
a model-origin failure remains an instrument-valid model result and, when
graded, has a false candidate decision. Tool errors alone do not determine
validity.

`results.json` is a deterministic committed-only
`brick.evidence-results/1` projection, sorted by logical hash and physical UUID
and containing no rebuild timestamp. A non-adopting inspection reports the
aggregate state of prepared or abandoned evidence; invalid committed evidence
halts, and all uncommitted physical candidates remain on disk. Missing, corrupt,
and stale projections rebuild under the run lock and are never used as resume
authority.

This is a cooperative-local-writer integrity model. Brick never mutates
committed candidates and readers revalidate them, but S4 supplies no digital
signature and does not defend against an administrator, hostile local process,
or hard-link adversary able to rewrite an entire internally consistent bundle.

S4 acceptance also requires the native Lenovo ARM64
`brick.s4-attestation/1` record and its hash-matched JUnit release asset. Hosted
Windows x64 coverage cannot substitute for that platform gate.

F0 uses a separate disposable implementation and external evidence bundle, not
this production S4 store. The exact Lenovo commands and candidate-commit
`C`/metadata-only release-descendant `R` attestation are defined in
[`PROJECT_SETUP.md`](PROJECT_SETUP.md). Any behavioral byte changed after `C`
invalidates that attestation and requires another complete S4 run.

## 8. Runtime and safety principles

Tool schemas are executable contracts. Prompt documentation and native Ollama
schemas derive from the same `ToolSpec`. Domain services enforce types, semantic
values, authorization, and business invariants.

Parser recovery and argument repair are separate. Mutation arguments may only be
repaired through an explicit versioned known-alias map. Fuzzy mutation repair is
not allowed.

Completion is `complete`, `incomplete`, or `unknown`. A model verifier may explain
missing work but cannot authorize an action or establish authoritative outcome
success.

Model-authored memory is untrusted input. It requires subject and tenant scope,
provenance, version, expiry, validation, and explicit write policy. It is not a
business database or an approved-document store.

Supported surfaces reject legacy general filesystem, shell, skip-confirmation,
and overlay-composition options before side effects. Domain-specific Office
artifact writers remain confined to attempt-owned synthetic workspaces.

Agent Lab remains a local development console until its later control-plane
stage passes. Loopback binding and process separation are not authentication,
authorization, or sandboxing. Q0 removes the old browser/stdin confirmation
channel; S5W introduces a newly run-bound confirmation protocol rather than
reviving that unbound channel.

## 9. Planned synthetic Brix principles

The B0 Brix layer will use fictional tenants, actors, leads, addresses, policies,
and a fake provider. The model may read assigned synthetic leads and create typed
follow-up proposals. It may not approve, dispatch, select another tenant, choose
an arbitrary recipient, bypass deterministic policy, or use memory as
authoritative state.

Deterministic code owns:

1. actor and tenant authorization;
2. current-state retrieval;
3. proposal validation, version, payload hash, revision, and expiry;
4. approval and dispatch revalidation;
5. idempotency and concurrency;
6. fake-provider reconciliation; and
7. immutable audit events.

Ambiguous fake delivery will enter `delivery_unknown` and reconcile before retry.
All delivery will be fake. Passing B0 will demonstrate the tested replaceable
layer and safety shape, not Brix acceptance or production readiness.

## 10. Retained execution

A standalone Python or PowerShell scheduler owns the queue, lock, heartbeat,
health checks, commits, logs, and resume. It does not depend on an active Codex
session.

D0 freezes `N` to 20 or 12 cases per family using timing only. The primary then
runs in `N` balanced waves. Paired conditions are contiguous and AB/BA order is
counterbalanced across families and waves.

Reboots are allowed after fixed warm-up only if every code, protocol, model,
runtime, OS, driver, backend, and power fingerprint is identical. Different
environment strata are never pooled. Sustained throughput degradation triggers
the predeclared cooldown and environment stop rule without inspecting task
outcomes.

A partial primary is `INCOMPLETE/DESCRIPTIVE`. It receives no confirmatory
inference and cannot be replaced with a selected subset. A sealed complete
primary remains reportable if a later descriptive phase is interrupted.

## 11. Data, training, and future work

Do not place real Brix member, payment, agreement, email, document, or
access-control data in the repository, benchmark, model memory, or logs.

“Local inference” must be demonstrated through deployment and network controls.
It does not follow merely from using Ollama and does not cover downloads,
browser access, telemetry, logs, or backups.

Fine-tuning is outside the current milestone. It may be considered only after a
frozen evaluation identifies a stable failure that is plausibly learned rather
than better fixed through schemas, deterministic logic, task design, or
orchestration. The existing generators and training scripts are not a valid
training experiment.

External validation and real Brix product work are later tracks. They do not
block an honest fixed-family internal result, and an internal result does not
validate either one.

## 12. Definition of completion

The research milestone is complete when:

- F0 passes on the Lenovo;
- supported unsafe capability paths are quarantined;
- storage, runtime, graders, generators, conditions, and analysis pass their
  versioned gates;
- the sentinel contains zero instrument-invalid cells;
- the primary is complete and sealed;
- null, negative, adverse, and rules-dominant findings remain visible;
- claims stay inside the tested generators, model, conditions, and resources; and
- a clean checkout reproduces the final evidence and report.

An incomplete primary must still be reported honestly as
`INCOMPLETE/DESCRIPTIVE`, but it does not complete the research milestone or
answer the primary question.

The synthetic-layer milestone is complete when the fictional Brix follow-up
slice passes its deterministic authorization, approval, concurrency,
idempotency, reconciliation, audit, and no-network tests without a Brix import in
generic packages.

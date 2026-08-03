# Execution handbook

Operational layer for running the plan. [`PROJECT_SETUP.md`](PROJECT_SETUP.md)
defines *what* to build and *what counts as evidence*; this file covers *how a
work session runs*: current state, schedule, checkpoints, and what to cut when
behind. [`CLAUDE.md`](CLAUDE.md) is the short orientation loaded automatically.

If this file disagrees with `PROJECT_SETUP.md` or `PROJECT_GUIDE.md`, they win.
If the dated state below disagrees with `git log` and the `[Unreleased]` section
of `CHANGELOG.md`, those win.

## 1. Read order for a new session

1. `CLAUDE.md` — hard rules, current position, remaining stages
2. This file — where execution actually stands and what to do next
3. `PROJECT_SETUP.md` — the stage you are about to work on
4. `git log --oneline -5` and `CHANGELOG.md` `[Unreleased]` — ground truth

## 2. State as of 2 August 2026

**Released:** `v0.8.0` (S5), preceded by `v0.7.0` (B0), `v0.6.0` (S1R),
`v0.5.0` (S4), and `v0.4.0` (F0/Q0). Candidate and tag CI are green.

The native Windows ARM64 S4 gate passed from candidate `0b8f77d`:
`overall_status` pass, 461 passed, 0 failed, 3 skipped, `s4_skipped` 0,
collected 464. JUnit report
`df2d8d1f3565f815148139ef1f91954a1b890deef1f02413cc12851952ba54aa` is attached
to the release and bound by the annotated tag.

**Done:** F0/Q0 and the independent F0 verifier correction. Q0 removed the
general filesystem and PowerShell overlay, every legacy escape flag fails before
side effects, and confirmation callbacks fail closed. `bench/f0_probe.py`,
`f0_windows.py`, `f0_storage.py` and `f0_protocol.json` implement the gate, now
at protocol v2.

**F0 PASSED** from candidate `6402bf5`, run `f0-20260801T164210Z-07054bec`,
archive SHA-256
`edf6f06fc06332e1e6cef4322dd583c4656f034c68c7d9f758571292dffc3220`.

| Component | Result |
|---|---|
| Environment (Lenovo, ARM64, AC, Defender, WSearch, NTFS) | pass, zero failures |
| Marker-last storage: 200 cycles, 50 injected exits, 10 held handles | pass, 200/200 committed, 0 invalid, 0 renames |
| All three model pulls | pass |
| Metadata, digest stability, `tools` capability | pass, all three models |
| Native tool conformance | pass, 3/3 cases per model |
| Per-key option recognition | pass, 9/9 frozen option names per model |
| 4B warm throughput | pass, median 22.26 tok/s against a 5 tok/s floor |
| 2B warm throughput | pass, median 45.02 tok/s, no floor |
| 9B warm throughput | pass, median 12.37 tok/s against a 3 tok/s floor |
| Peak process memory | pass, 6.50 / 3.99 / 9.61 GiB against a 28 GiB ceiling |
| Inference runner | native ARM64 `llama-server.exe`, hashed, identity stable |
| Loaded context / backend | 8192, classified `cpu` from measurement |

All three models are `eligible`, so the descriptive matrix is feasible rather than
conditional. At 22.26 tok/s the 4096-token attempt ceiling implies roughly 184 s of
generation per attempt, so 440 attempts with the 1.25 factor land near 28 hours
against the 48-hour threshold. That is generation time only and is **not** the D0
measurement, which must use observed median wall time.

**Four runs exist and only one backs the release.** Keep them distinct:

| Run | Tree / commit | Status |
|---|---|---|
| `f0-...T020325Z-5f948e97` | protocol v1 | **FAIL**, retained unchanged |
| `f0-...T034453Z-94b29703` | `557b5ad8` | pass, superseded by the version-pin fix |
| `f0-...T162806Z-e6ca4f26` | `abf609c0` @ `1beb3da` | pass, superseded by the allowlist fix |
| `f0-...T164210Z-07054bec` | `abf609c0` @ `6402bf5` | **pass — backs `v0.4.0`** |

The v1 failure was a protocol-contract fault: it required Ollama to reject the
unknown option `brick_f0_unknown_option` with a 4xx naming it. Ollama never
promised that; 0.32.5 ignores unknown option names and returned 200. **The
machine, the model and the research design did not fail — the gate asserted a
runtime contract that did not exist.** Protocol v2 replaced it with per-key
recognition, Brick-owned request validation, inference-runner attestation and
domain-attributed failures. Unknown-name acceptance remains true of this build and
is now recorded as a diagnostic typo hazard: not a gate, not a model result.

The two later reruns came from defects in the **release procedure**, not the gate:
a test pinned the project version to a literal while the allowlist permitted
bumping it, and the allowlist enumerated files by name and had rotted. Note the
third and fourth runs share a behavior tree; a shared tree does not make a
different commit's bundle usable, and the attestation asserts both.

A subsequent strict audit found weaker-than-documented verifier predicates, not
a failed measurement: generic non-2xx option errors could count as recognition,
runner replacement across PIDs was not rejected, and some failed-run codes were
shape-checked rather than recomputed. Commit `f12dd71` now derives those results
from raw responses and memory samples. Both the original and extracted release
bundles pass the stronger verifier with their recorded hashes unchanged; the
commit is pushed and required CI is green.

**S4 is released as `v0.5.0`:** `harness/evidence.py` implements the production
marker-last store and `bench/s4_attest.py` implements its native attestor.
Candidate CI, a clean native Windows ARM64 run with all required symlink cases,
and candidate-bound attestation were satisfied. The earlier deep pytest-root
failure remains useful history: the bounded S4 root removed its dependence on
username and pytest counter length before the retained native run.

**S1R is released as `v0.6.0`.** Every item in its exit gate has passing tests:
parser 33, schema 50, semantic-value 6, memory 36, completion 35, truncation 7,
timeout 3, executor 31.

**B0 is released as `v0.7.0`.** Gate coverage: tenant 8, approval 13,
concurrency 2, expiry 3, idempotency 2, ambiguous-delivery 7, audit 4,
no-network 3, plus a generic-package purity scan over 55 files in 7 package
roots.

S5 binds semantic-versioned strict graders to all 14 released
scenarios. Grading inputs are immutable byte copies, rubric denominators are
fixed, and runner/grader failures remain null. Its generated fixture matrix
covers positive, minimally wrong, harmful, stale, missing, extra, corrupt, and
metamorphic cases for every scenario.
`v0.4.0` and the S4 candidate record no benchmark effect.

**Benchmark host, verified eligible:**

| Property | Value |
|---|---|
| Manufacturer / model | LENOVO 83ED |
| Processor | Snapdragon X Elite X1E78100 (Qualcomm Oryon) |
| RAM | 31.6 GB |
| OS | Windows 11 ARM64, build 26200 |
| Free space on C: | ~878 GB |
| Python | 3.13 ARM64, `%LOCALAPPDATA%\Programs\Python\Python313-arm64` |
| Git | 2.55.0.windows.3 |
| Ollama | 0.32.5 installed. The plan deliberately does **not** pre-pin a version: F0 selects and records the exact ARM64 build, digest and metadata. |
| Repository | `C:\Brick` |

Everything F0 requires of the host is satisfied. Nothing else is verified,
because verifying it is F0's job.

## 3. Immediate next action

The S6G boundary is complete: 341 cases across all five manifests replay
exactly, all 341 semantic structures are distinct, no entity key or surface is
reused anywhere, and structural templates do not cross splits. The complete native
suite passes 808 with 3 intentional platform skips, and `v0.10.0` is published.
No model run or effect estimate exists. Stop for review. The next stage is S6C
condition and scheduler integration, and it begins only after a separate
explicit decision.

Do not import or synchronize the moving `SMalshe/Brick` product tree into S4,
S1R, B0, or a retained condition. `PROJECT_GUIDE.md` defines the convergence
rule: future product work is identified by an immutable commit and enters
through a versioned adapter and conformance suite. B0 remains a fictional
no-network domain pack.

## 4. Timeline realism

State this honestly to anyone who asks, including yourself.

| Horizon | Verdict |
|---|---|
| 1 week | Not the full plan. Enough for `v0.4.0` plus possibly S4. |
| 2 weeks | A narrowly defined version of all three milestones is a **stretch goal** with zero rework. Not a reliable commitment. |
| 4–5 weeks | Best case for the plan as written. |
| 6–8 weeks | Realistic for one engineer, one agent, one Lenovo. |

The limiting factor is not effort. It is a serial validation chain: F0 gates S4;
S4 and S1R gate the instrument; graders and generators must freeze before D0; D0
sets the sample size; the sentinel must be clean before the primary; the primary
alone may take up to 48 hours. Agents parallelize *coding within a stage*. They
cannot parallelize dependent gates or substitute for Lenovo execution.

**The dangerous option** is compressing everything into the deadline and
presenting a small post-hoc pilot as proof the harness works. That is a demo, not
evidence, and it destroys the only thing that makes this project worth doing.

## 5. Two-week schedule, zero buffer

Assumes every gate passes first time. Treat slippage as expected, not as failure.

| Day | Required result |
|---:|---|
| 1 | F0 passes; `v0.4.0` released |
| 2–3 | S4 production marker-last evidence store |
| 4 | S1R typed runtime |
| 5 | B0 synthetic lead-follow-up slice *(first to cut)* |
| 6 | S5 strict graders |
| 7 | S5W Agent Lab hardening *(second to cut)* |
| 8 | S6G generators and frozen splits |
| 9 | S6C shared transport, condition registry, ledger, scheduler |
| 10 | D0 timing run; protocol freeze; tag |
| 11 | S8 sentinel, zero invalid cells |
| 12–13 | S9 primary benchmark |
| 14 | Analysis, reproduction check, report, release |

This holds only if the machine runs continuously on AC power, no stage forces an
architectural correction, B0 stays at exactly one fictional workflow, no task
family or feature is added, and the primary runs before any secondary.

## 6. Hard checkpoints

Decide these now, in advance, so a missed date is a decision rather than an
argument.

| Checkpoint | If missed |
|---|---|
| F0 passed by end of Day 1 | A retained benchmark is no longer a credible two-week commitment. Re-plan. |
| S4 and S1R green by end of Day 4 | Target instrument completion and the Brix slice, not a retained result. |
| Protocol frozen by end of Day 9–10 | Do not run a retained benchmark. Ship the instrument. |
| Sentinel clean by end of Day 11 | Fix and rerun. Accept that the final run may miss the deadline. |
| Primary started by Day 11–12 | A complete report by Day 14 is unlikely. Publish the instrument instead. |

**Never waive a failed integrity, grader, sentinel, or environment gate because
of the deadline.** A waived gate produces a number nobody should believe, which
costs more than the deadline it saved.

## 7. Cut order when behind

Cut from the top. Everything below the line invalidates the result.

1. Descriptive matrix — 2B and 9B replications, `raw_json`, the three ablations,
   the no-memory ablation, equal-action-opportunity sensitivity
2. `rules_reference`
3. S5W Agent Lab hardening — not used by the benchmark
4. B0 synthetic slice — separable from the experiment, but it is the only
   stakeholder-visible artifact, so know what you are giving up
5. Validation and adversarial manifests, keeping development / sentinel /
   retained
6. S1R breadth — keep string-safe parsing, removal of fuzzy repair on mutation
   arguments, fail-closed completion, scoped memory, exception classification

**Never cut:** evidence integrity, strict graders, shared native transport,
independent instances, freeze-before-looking, the reproducibility bundle. Those
six are what make the number mean anything.

S4 run locking and its concurrent-writer test are evidence integrity and are not
cuttable. An operator promise that only one process will write is not equivalent
to the canonical gate.

**Never cut by choosing the smaller primary to save time.** D0's preregistered
runtime rule decides between 20 and 12 instances per family. A deadline is not
an input to that rule.

## 8. The estimand decision — DECIDED AND LOCKED

**Recorded 2 August 2026, before any efficacy data exists.** At this date the
only releases are `v0.4.0` (F0 feasibility) and `v0.5.0` (S4 evidence store).
No generator, grader, condition, or attempt outcome exists, so this choice
cannot have been influenced by observed results. That ordering is the entire
reason it is written down now rather than at D0.

**Decision: all 11 families, as written.** The estimand remains the equal-family
mean paired difference over the 11 fixed generator distributions:

```text
Delta = (1 / 11) * sum(family_mean(harness_success - native_success))
```

The families are `pptx_basic`, `pptx_from_email`, `xlsx_basic`,
`xlsx_from_email`, `email_reply`, `cal_add`, `cal_freeslot`, `cal_brief`,
`remind_msg`, `learn_store_use`, and `multi_offsite`.

The rejected alternative was a preregistered structural subset, for example
families requiring three or more dependent tool calls where a later write
depends on an earlier read. It offers better power on a sharper question at the
same run cost. It is rejected because the broader claim is the one worth making:
a harness that helps only on the subset selected for it is a weaker result than
a smaller effect measured across the full frozen distribution. Dilution is
accepted as an honest cost.

### Preregistered floor and ceiling audit

Dilution risk is managed by a rule fixed in advance, not by later judgement.

D0 runs 44 score-masked development pairs: four pairs per family, therefore
**eight outcomes per family** across both conditions. Audit combined
development-set success only, never retained outcomes:

- **0 or 1** of 8 successes triggers the `<15%` floor flag (1/8 = 12.5%);
- **7 or 8** of 8 successes triggers the `>85%` ceiling flag (7/8 = 87.5%).

A flag **blocks the S7 protocol freeze**. It permits exactly one versioned,
direction-blind generator or grader correction — direction-blind meaning the
correction may not be chosen to move the effect in either direction — followed
by a disjoint 44-pair D0 rerun on fresh instances.

A repeated flag after that correction **stops the work before S8**. No family is
silently removed, reweighted, or excluded from the estimand. A family that
cannot be brought inside the band is reported as a floor or ceiling effect in
the final report, with its measurements intact.

Selecting on observed efficacy rather than structure is invalid, and D0's score
masking exists to make that enforceable. Narrowing the estimand later would be a
versioned protocol change requiring a complete rerun, not a scope cut.

## 9. Per-session protocol

Every session, in order:

1. `git log --oneline -5`, `git status --short`, read `CHANGELOG.md`
   `[Unreleased]`
2. Confirm which stage is active. Work on exactly one.
3. `python -m pytest -q` before starting, to establish a clean baseline
4. Implement only that stage's bounded deliverable
5. Run its acceptance checks and read the complete diff
6. Update code, tests, documentation and `CHANGELOG.md` in the same change
7. Commit, tag, push, confirm CI green
8. Report changed files, evidence, limitations, unresolved risks
9. **Stop.** The next stage begins only after a separate review decision.

During any live evidence run: the worktree stays clean, nothing is edited, the
run directory is never renamed or moved, and a failing gate is reported rather
than repaired.

## 10. What "done" means in two weeks

Narrowly defined versions of three milestones, not the full plan:

1. **A research-grade harness** sufficient for the frozen benchmark. Not a
   general-purpose production platform.
2. **One synthetic lead-follow-up vertical slice** with fictional records and
   fake providers. Not a Brix integration.
3. **One sealed primary benchmark**: same pinned Qwen3.5 4B, same paired
   instances, same tools and validators, same opportunity budget,
   `native_tools` versus `harness_full`. Not necessarily any secondary.

Four outcomes are valid and only the first supports an improvement claim:
positive, null, negative, rules-dominant. See `CLAUDE.md`. None of them is a
failure, and none should be engineered away.

## 11. Talking about status without overclaiming

The distinction that matters: **F0/Q0 feasibility has passed; no benchmark
effect has been measured.** Conflating them is the easiest way to lose
credibility.

Accurate framing now:

> At candidate `C`, `v0.4.0` is the preceding release and records a passing Q0
> quarantine and native Windows ARM64 F0
> feasibility gate on the Lenovo Snapdragon X Elite. The retained evidence
> establishes the tested model transport, option recognition, throughput,
> process memory, native runner identity, storage behavior, and host
> prerequisites. Commit `f12dd71` contains the pushed, CI-green independent
> verifier correction. Candidate `C` contains the `v0.5.0` S4 store and
> attestor; native zero-skip acceptance, candidate-bound attestation, and CI are
> requirements, all of which were satisfied. Tagged attestation-only `R` and its
> bound evidence authoritatively record the result: `overall_status` pass, 461
> passed, 0 failed, `s4_skipped` 0. This is not a benchmark result, and S1R has
> not started.

Never say "the research passed" when only feasibility passed. Never say a
benchmark result exists before S9 is sealed. Never round a conditional result
into a general one.

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

## 2. State as of 31 July 2026

**Released:** `v0.3.1`. **Candidate commit:** `61ed911`. **Offline suite:** 188
passed, 2 skipped (Windows-only smoke tests). Linux and Windows x64 CI green.

**Done:** F0/Q0 source is written and audited. Q0 removed the general
filesystem and PowerShell overlay, every legacy escape flag now fails before
side effects, and confirmation callbacks fail closed. `bench/f0_probe.py`,
`f0_windows.py`, `f0_storage.py` and `f0_protocol.json` implement the gate.

**Not done:** F0 has never been executed. `v0.4.0` is unreleased and blocked on
retained native-Lenovo evidence. Every stage from S4 onward is unstarted.

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

Run F0. It is the only thing standing between the current state and ten
buildable stages.

Host preparation and the exact run and verify commands are in
[`bench/README.md`](bench/README.md#preparing-the-lenovo-host). Summary: AC
power, a High/Ultimate Performance scheme or the Best Performance overlay, sleep
disabled, Defender real-time protection and Windows Search left **running**,
Ollama serving, output to a short local NTFS path such as `C:\BrickRuns`.

Expected cost: about 10 to 30 minutes of compute plus however long roughly 12 GB
of model downloads takes. The generation volume is fixed and small — 1,920
tokens per model, from `runtime_warmups=1`, `runtime_samples=5`,
`runtime_num_predict=320`. The download dominates.

F0 measures throughput and backend classification rather than assuming them.
Those measurements are inputs to the sample-size rule later, so this run is not
only a gate but the first real data.

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
6. S4 concurrent-writer locking — assert single writer instead
7. S1R breadth — keep string-safe parsing, removal of fuzzy repair on mutation
   arguments, fail-closed completion, scoped memory, exception classification

**Never cut:** evidence integrity, strict graders, shared native transport,
independent instances, freeze-before-looking, the reproducibility bundle. Those
six are what make the number mean anything.

**Never cut by choosing the smaller primary to save time.** D0's preregistered
runtime rule decides between 20 and 12 instances per family. A deadline is not
an input to that rule.

## 8. One protocol decision to make before D0

`PROJECT_SETUP.md` freezes an equal-family estimand over 11 families. Families
that both conditions solve trivially, or both fail completely, contribute a
family mean near zero and pull the pooled effect toward zero while still
consuming attempts.

Two legitimate options, and the choice must be made and written down **before**
any efficacy data exists:

- **As written.** All 11 families. Broader coverage, more dilution risk.
- **Narrowed.** A preregistered structural subset, for example families
  requiring three or more dependent tool calls where a later write depends on an
  earlier read. Same run cost, better power on a sharper question, narrower
  claim.

Narrowing changes the estimand, so it is a versioned protocol change, not a
scope cut. Selecting on observed outcomes instead of structure is invalid; D0's
score masking exists to make the honest version enforceable.

Regardless of which you pick, run the development-set floor and ceiling check
before freezing: on development and sentinel instances only, flag any family
whose combined success across both conditions falls below roughly 15% or above
85%. Without it, a floor effect is indistinguishable from a null result, and you
can spend the entire retained run learning nothing.

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

The distinction that matters: **the F0 implementation is complete; the F0 gate
has not passed.** Conflating them is the easiest way to lose credibility.

Accurate framing while F0 is pending:

> The audited Q0 quarantine and F0 probe implementation are pushed. Code,
> documentation, offline tests and the required Linux and Windows x64 CI are
> passing. F0 itself is still pending: the next step is running the candidate on
> the Lenovo Snapdragon X Elite under native Windows 11 ARM64. If it passes we
> release `v0.4.0`, build the remaining benchmark infrastructure, and run the
> paired same-model, same-task comparison between native tool use and the full
> harness on that laptop.

Never say "F0 is complete" when it means "F0 is written." Never say a benchmark
result exists before S9 is sealed. Never round a conditional result into a
general one.

# Brick — agent working notes

Experimental research scaffold for testing whether an explicit agent harness
improves tool-using local language models. Two parts: a domain-independent
harness core, and versioned domain packs (`domains/office_demo`,
`domains/counter_demo`) that plug into it.

[`PROJECT_SETUP.md`](PROJECT_SETUP.md) is canonical for the plan, gates, and
status. [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) is canonical for evidence
standards. If this file disagrees with either, they win.

[`EXECUTION.md`](EXECUTION.md) is the operational handbook: current machine and
repository state, the schedule, hard checkpoints, cut order when behind, and the
per-session protocol. Read it before starting work.

## Hard rules

1. **Never modify the worktree while an evidence gate runs.** Gates require
   `git status --short` to print nothing. Editing any tracked file, docs
   included, voids the run and its evidence.
2. **When a gate fails, report it. Do not repair it.** A failure is the result:
   it says something the design assumed is untrue. Patching around it produces
   evidence for a tree nobody reviewed.
3. **Live-model work runs only on the native Windows 11 ARM64 Lenovo.** The Mac
   is for source work and offline tests. Never present a Mac run as gate
   evidence.
4. **Advance only through sealed gates.** A fingerprint-bound authorization may
   auto-advance through its declared phases; a failed or changed gate terminates
   that authorization and cannot be patched in place.
5. **Never convert a runner, store, grader, or analysis failure into a model
   failure.** Keep the status axes separate.
6. **Never tune from retained outcomes.** Development and sentinel instances are
   visible; retained ones are not.
7. Update code, tests, docs, and `CHANGELOG.md` in the same change. A version
   records implemented behavior; it never waives a gate.
8. Keep the harness core free of domain-specific imports. Only the two named
   deprecation shims (`harness/world.py`, `harness/office.py`) may import a
   domain, and a test enforces this.
9. Synthetic and fictional data only. No real client records, no provider
   credentials, no general filesystem or shell capability on a supported surface.

## Current position

Latest release is `v0.11.1` (pre-D0 integrity repair), preceded by `v0.11.0`
(S6C fair-condition runtime and scheduler), `v0.10.0` (S6G), `v0.9.0`
(S5W), `v0.8.0` (S5), `v0.7.0` (B0),
`v0.6.0` (S1R), `v0.5.0` (S4), and `v0.4.0` (F0/Q0). **The native-Lenovo F0 gate passed** from
candidate `6402bf5`, run `f0-20260801T164210Z-07054bec`, with all three models
eligible — 4B at 22.26 tok/s against a 5 tok/s floor, 2B at 45.02, 9B at 12.37
against a 3 tok/s floor — and inference attested to a native ARM64
`llama-server.exe`.

**That is feasibility only.** It establishes that this host can run the designed
experiment. It is not a benchmark result and no measured effect exists.

An earlier attempt failed under protocol v1, which required Ollama to reject an
unknown option name — something Ollama never promised. That bundle
(`f0-20260801T020325Z-5f948e97`) is retained unchanged as failed evidence; the
gate was corrected and versioned rather than repaired. Two further reruns came
from defects in the release procedure itself, not the gate. See
[`EXECUTION.md`](EXECUTION.md) §2.

The independent F0 verifier correction is commit `f12dd71`, pushed to `main`
with required CI green. It strengthens option-recognition and runner-stability
verification without altering the retained evidence; both the original and
extracted `v0.4.0` bundles still pass.

`harness/evidence.py` implements the production marker-last evidence store and
`bench/s4_attest.py` its native attestor. `v0.5.0` is released. The native Windows ARM64 S4 gate passed from candidate
`0b8f77d`: `overall_status` pass, 461 passed, 0 failed, 3 skipped, `s4_skipped`
0, collected 464. That records instrument behaviour only, not a benchmark
result. Developer Mode is
enabled on the benchmark host so the three required S4 symlink cases execute;
Windows long-path support is deliberately off, because the gate must hold on a
default path regime.

S1R is released as `v0.6.0`: executable tool-argument schemas from which the
native schema and prompt docs are derived, conservative parsing with no
inference, fail-closed completion decided by authoritative state, scoped
untrusted memory with quarantine, origin-classified faults, and a typed executor
whose gates admit a call only when all of them agree.

B0 is released as `v0.7.0`: `domains/brix_followup_synthetic`, a fictional
lead-follow-up slice with fake records and a no-network fake provider. The model
may list due follow-ups, inspect an assigned lead, propose a follow-up, inspect
its proposals, think and finish. It cannot approve, dispatch, cross a tenant,
choose a recipient or bypass policy, because those capabilities are not offered
at all. Passing it demonstrates replaceable layering only; it does not make the
workflow Brix-approved or deployed.

S5 is released as `v0.8.0`. Every task binds a named,
semantic-versioned deterministic grader. Graders consume copied canonical state,
actions, memory, and artifact bytes rather than live mutable worlds. Their check
sets are fixed; strict success is all-or-nothing; corrupt evidence or grader
failure yields a null outcome. Candidate and tag CI passed on Linux Python
3.9–3.13 and Windows x64 Python 3.13. The legacy exploratory runner records runner,
grader, candidate-decision, and strict-success axes separately.

S5W is released as `v0.9.0`. S6G is released as `v0.10.0`. S6C is released as
`v0.11.0` with the
shared native transport, exact opportunity ledger, seven mechanism-digested
conditions, standalone disposable scheduler, compiled grader, rules reference,
and strict preflight. The `v0.11.1` repair versions the generator as
`office-generators/1.1.0`: 352 cases and structures, including two fresh,
balanced 44-pair D0 cohorts, with exposed disposable material rejected across
five identity channels. It also versions the corrected Brix domain/grader as
`0.1.1`/`1.0.1`. D0-A ran 88 masked logical cells but is instrument-invalid
because three cells retained Ollama HTTP 500 failures after the frozen retry.
Protocol `1.0.2` binds the original Ollama log and pinned parser source: the six
500s were complete, non-truncated Qwen tool-syntax rejections. D0-B then
completed all 44 pairs/88 attempts as `s7-d0b-20260804T025010Z` from commit
`b756843`. The sealed runtime-only decision selected 20 cases per family
(`d46e074...`), without reading efficacy. The subsequent direction-blind audit
(`3611324...`) raised three ceiling flags and one floor flag and set
`protocol_freeze_allowed=false`. S7 is therefore closed without a freeze:
there is no `v0.12.0`, no S8 handoff, no condition-level result, and retained
execution remains mechanically disabled.

`v0.13.0`/generator 2.1.0 were invalidated before calibration, and the later
2.1.2 candidate terminated with ten deterministic public-prompt/live-grader
contradictions. Both histories remain immutable; `v0.13.1` is permanently
unissued. The user's explicit pre-outcome directive authorizes the independent
`office-generators/2.2.0` successor under protocol `1.5.0` and tag `v0.13.2`.
The final audit found two construct blockers before calibration: every
`cal_add` request was feasible, and every `preference_learning` store prompt
printed its policy-selected answer. The tag remains immutable and is retired.
The user's explicit pre-outcome directive authorizes `office-generators/2.3.0`
under protocol `1.6.0` and target tag `v0.13.3`, retaining only the 2.1.0 seed
namespace and the unchanged 11-family, 220-cluster estimand. All 528 public
outcomes reconstruct independently, all 1,056 typed positive workflows pass,
and grader conformance passes 528 baselines, 4,332 targeted mutations, and
1,872 benign controls. The machine-readable remediation closure passes with
zero live model calls or inspected effectiveness data. Human-review utilities
remain advisory and cannot authorize the study. At that v0.13.3 qualification
point, the candidate was offline-qualified but could not make a model call: it
needed an exact clean
commit, Linux and native Windows reproduction, and a separately authorized
score-masked 22-cell shakeout before `v0.13.3` can be issued. Read
[`bench/NEXT_STUDY_IMPLEMENTATION.md`](bench/NEXT_STUDY_IMPLEMENTATION.md) and
run both offline verify commands before changing it.

## Current focused-recovery status

The v0.13.5 focused-follow-up root is immutable historical evidence. Its
three-family B1a fallback sealed and is the only completed prospective
directional lane. B1b terminated after the exact source-proven Qwen parser
signature `element <parameter> closed by </function>`, leaving 24 cells never
started; B2 never started. Do not resume, modify, or append to that root.

`v0.13.6` is preauthorization only: it is not yet tagged, authorized, or run.
Its one future authorization binds exactly those 24 missing B1b cells and the
byte-identical 240-cell B2 same-context repeatability schedule. B2 is mandatory
after any validated B1b terminal state, and no efficacy result may be exposed
until both lanes are terminal. Its recovered six-family and B2 outputs are
nonclaiming; only the old B1a fallback remains a completed prospective
directional lane. See [`bench/FOCUSED_RECOVERY_SUCCESSOR.md`](bench/FOCUSED_RECOVERY_SUCCESSOR.md).

This remains a fixed synthetic Qwen3.5 4B `harness_full` versus
`native_tools` study. It does not test a bare model, Sharvin's Llama 8B product,
llama.cpp backend, web UI, or production Brix harness.

For S4, release state is authoritative in the annotated tag and bound evidence.
Direct descendant `R` adds only the regular file
`evidence/s4/v0.5.0.json`, so tagged `R`
intentionally retains `C`'s candidate-scoped wording. Immediately afterward,
docs-only descendant `D` promotes changelog/current status and is not part of
`v0.5.0`. Never infer gate status from this frozen prose alone.

Offline suite, from the repository root:

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q
```

The suite requires no Ollama and no network; a test fails rather than reaching
out. Do not record a final count until it is run from the clean pushed S4
candidate. On the native Windows gate, the three required S4 symlink cases may
not be skipped.

## The F0 feasibility gate

F0 answers "can this machine actually run the experiment we designed" before
nine more stages are built on the assumption. It checks four things: that the
`qwen3.5:2b/4b/9b-q4_K_M` models exist and round-trip native tool calls, that the
pinned Ollama build recognizes every frozen sampling option by name and runs
inference in a native ARM64 runner, that the hardware meets measured throughput
and memory floors, and that marker-last publication survives Windows with a
real-time scanner and indexer holding handles.

- First-time host setup:
  [`bench/README.md`](bench/README.md#preparing-the-lenovo-host)
- Run and verify commands:
  [`bench/README.md`](bench/README.md#running-the-lenovo-f0-gate)
- Full requirements and attestation: [`PROJECT_SETUP.md`](PROJECT_SETUP.md)

A 4B *model* failure — no native tool transport, throughput below floor, memory
over ceiling — stops the research design. A 2B or 9B failure removes only that
descriptive replication, with no substitute model. A storage failure means the S4
evidence store needs redesign before it is built.

A **protocol-contract** failure is different and must not be read as a model
result: it says the pinned runtime does not honour a contract Brick declared.
Per `PROJECT_SETUP.md`, revise and version the candidate protocol and rerun all of
F0. Never lower a floor or drop a check to make an existing failed run pass —
that waives a gate and produces a number nobody should believe. Failure codes
carry a `domain` for exactly this reason.

## Remaining stages

| Stage | Release | Deliverable |
|---|---:|---|
| F0/Q0 | `v0.4.0` | Quarantine unsafe capabilities; Lenovo model, runtime, and Windows storage probes |
| S4 | `v0.5.0` | Marker-last immutable attempt evidence, locking, exact resume, failure taxonomy |
| S1R | `v0.6.0` | Typed tool schemas, conservative parsing, fail-closed completion, scoped memory |
| B0 | `v0.7.0` | Replaceable synthetic lead-follow-up vertical slice, fictional records and fake providers |
| S5 | `v0.8.0` | Strict, independently versioned outcome graders |
| S5W | `v0.9.0` | Agent Lab local control-plane hardening |
| S6G | `v0.10.0` | Independent versioned task generators and split manifests |
| S6C | `v0.11.0` | Shared native transport, condition registry, scheduler, telemetry |
| Pre-D0 | `v0.11.1` | Fresh balanced D0 cohorts, exposure ledger, corrected Brix grader |
| D0/S7 | not released | Terminal failed calibration; no protocol freeze or efficacy contrast |
| Successor design | not assigned | Fresh tasks, independent oracle/review, mutation audit, repeated-trial statistics, and sentinel protocol; all live gates currently closed |
| Successor sentinel | not assigned | Disposable sentinel only after every design gate closes |
| Successor retained run | not assigned | New sealed experiment only after a valid sentinel |

## The primary contrast

Same pinned Qwen3.5 4B, same paired task instances, same native tools and
schemas, same initial states and validators, same end-to-end opportunity budget:

```text
native_tools  versus  harness_full
```

Outcome is strict whole-task success over 11 fixed synthetic task families. The
estimand is the equal-family mean difference. The active successor claim rule is
defined by `bench/next_study_claim_contract.json`: a directional claim requires
the two-sided 95% stratified bootstrap interval to exclude zero in that direction
and the inclusive observed-effect threshold `abs(Delta) >= 0.12`. The exact
sign-flip calculation is diagnostic only and cannot alter the claim.

## What completing the plan produces

1. **A reusable harness platform.** Native tool calling, typed tool and state
   contracts, planning and completion control, scoped untrusted memory,
   duplicate suppression, conservative recovery, opportunity accounting,
   immutable attempt evidence, crash-safe resume, a restartable scheduler, and
   auditable actions. Supporting another company should mean writing a domain
   pack, validators, and graders, not editing the harness.
2. **A demonstrable synthetic business slice.** Lead intake and state
   transitions, follow-up drafting, approval-gated delivery, idempotency,
   expiring approvals, ambiguous-delivery reconciliation, tenant separation, and
   full audit history, with fictional records and no real delivery. This proves
   replaceable layering, not a production deployment.
3. **A precise same-model benchmark result** with per-family effects, a bootstrap
   interval, leave-one-family-out sensitivity, resource frontier, and a failure
   taxonomy.

## Four honest conclusions

All four are valid results. Only the first supports an improvement claim, and no
outcome should be presented as a disappointment.

- **Positive** — the harness improves strict success enough to justify its
  overhead on the frozen families.
- **Null** — the difference is too small or uncertain to establish. Suggests
  simplifying the harness or targeting tasks better.
- **Negative** — the harness performs worse, likely because planning and
  verification consume calls, context, or time. Actionable evidence about what
  complexity to remove.
- **Rules-dominant** — deterministic workflows beat both model conditions on
  applicable families. Recommend rules there and reserve the model for ambiguous
  or language-heavy work.

## Never claim

Proven improvement for all models or agent tasks. Performance on real client
operations. A production-ready deployment. External-benchmark generalization.
Validation against real records, email, or company systems. Within-instance
repeatability or pass-at-k. That any single harness mechanism caused the
aggregate effect. Superiority over other agent frameworks.

The honest framing is a reproducible research prototype showing whether a
carefully defined harness helps one pinned local model complete specific
synthetic business tasks.

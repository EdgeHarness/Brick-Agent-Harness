# Brick — agent working notes

Experimental research scaffold for testing whether an explicit agent harness
improves tool-using local language models. Two parts: a domain-independent
harness core, and versioned domain packs (`domains/office_demo`,
`domains/counter_demo`) that plug into it.

[`PROJECT_SETUP.md`](PROJECT_SETUP.md) is canonical for the plan, gates, and
status. [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) is canonical for evidence
standards. If this file disagrees with either, they win.

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
4. **One release stage at a time**, then stop for review. Do not start the next
   stage without an explicit decision.
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

Latest release is `v0.3.1`. F0/Q0 work toward `v0.4.0` is **unreleased and
blocked** on retained native-Lenovo F0 evidence. Do not describe `v0.4.0` as
complete, tagged, or validated.

Offline suite, from the repository root:

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Expect 188 passed, 2 skipped. The two skips are Windows-only smoke tests. The
suite requires no Ollama and no network; a test fails rather than reaching out.

## The F0 feasibility gate

F0 answers "can this machine actually run the experiment we designed" before
nine more stages are built on the assumption. It checks three things: that the
`qwen3.5:2b/4b/9b-q4_K_M` models exist and round-trip native tool calls, that the
hardware meets measured throughput and memory floors, and that marker-last
publication survives Windows with a real-time scanner and indexer holding
handles.

- First-time host setup:
  [`bench/README.md`](bench/README.md#preparing-the-lenovo-host)
- Run and verify commands:
  [`bench/README.md`](bench/README.md#running-the-lenovo-f0-gate)
- Full requirements and attestation: [`PROJECT_SETUP.md`](PROJECT_SETUP.md)

A 4B failure stops the research design. A 2B or 9B failure removes only that
descriptive replication, with no substitute model. A storage failure means the S4
evidence store needs redesign before it is built.

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
| D0/S7 | `v0.12.0` | Score-masked timing run, then frozen protocol and analysis |
| S8 | `v0.13.x` | Disposable sentinel across every retained condition |
| S9 | `v0.14.0` | Sealed retained experiment, evidence bundle, final report |

## The primary contrast

Same pinned Qwen3.5 4B, same paired task instances, same native tools and
schemas, same initial states and validators, same end-to-end opportunity budget:

```text
native_tools  versus  harness_full
```

Outcome is strict whole-task success over 11 fixed synthetic task families. The
estimand is the equal-family mean difference. A positive claim requires all
three: `Delta > 0`, the sharp sign-flip diagnostic below `p = 0.05`, and a
bootstrap 95% lower bound above zero.

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

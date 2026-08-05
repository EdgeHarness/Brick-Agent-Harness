# Brick successor study: implemented state

This document describes the offline-qualified successor instrument. It does
not authorize a model call and it does not report an empirical model result.

## Qualified instrument

- `office-generators/2.1.0` produces 528 unique, split-neutral cases across 11
  fixed synthetic families. `office-generators/2.0.1` is permanently retired.
- The construct contract freezes three genuine decision policies per family.
  All 176 workload/distractor-matched triplets produce three distinct outcomes
  with equal non-policy burden.
- The leakage scanner passes. Executable lower bounds peak at 9 native and 12
  harness requests under the shared 18-call/6,144-token cap. The memory family
  requires 5 native versus 10 harness requests; this asymmetry is a mandatory
  report limitation.
- Public-packet outcomes are independently compiled for all 528 cases without
  importing the generator or grader. The strict grader is built only as
  `build_grader(public_packet, validated_outcome)`.
- The semantic gate executes 1,056 legal typed positive workflows (both primary
  conditions for every case), verifies every relevant dependency and
  record-order/distractor invariance, and reports no critical, high, or medium
  internal-validity finding.
- Grader conformance passes 528 positive baselines, exactly 2,976 targeted
  mutations, and 1,392 benign controls. Placeholder presentations and
  alternate-policy outcomes fail.

Human-review, staffing, pilot, and adjudication utilities remain available as
public advisory fixtures. They cannot satisfy an authorization gate, supply a
validated outcome, or change the fixed synthetic-suite claim.

## Statistics and evidence

Protocol `1.3.0`, design `0.7.0`, construct contract
`office-construct/1.0.0`, and grader `office-strict-grader/3.0.0` are active.
The machine-readable claim contract is authoritative: a directional claim
requires an inclusive `abs(Delta) >= 0.12` and a two-sided 95% stratified
cluster-bootstrap interval excluding zero in that direction. The exact
sign-flip result is diagnostic only.

The primary analysis uses 220 instance clusters, equal family weighting,
50,000 exact-uniform hash bootstrap replicates, nearest-rank endpoints, 11
descriptive-only LOFO records, reliability metrics, and observed paired
variance. Attempt-record, masked-ledger, grade-ledger, primary-analysis,
authorization, and release artifacts use context-bound `/2` schemas. Resource
rows are extracted from marker-last evidence and unknown token counts remain
explicit bounds.

The frozen program is:

```text
352 calibration
→ 88 sentinel
→ 880 retained primary
→ sealed primary analysis
→ at most 222 descriptives
→ v0.14.0 archive
```

The model-free rehearsal uses `synthetic_rehearsal` context and display label
`mock-v0.14.0`. It passes the +57/440, +48/440, -57/440, null,
threshold-but-uncertain, incomplete, 52/440, and 53/440 fixtures; exercises
masked evidence, unmasking, bootstrap, LOFO, descriptives, report construction,
and program transitions; and proves synthetic artifacts cannot pass production
release verification. It creates no tag and writes no production evidence.

## Remaining live gates

The next goal is native qualification followed by a separately authorized,
score-masked 22-cell development shakeout (one case per family and condition,
at most 44 physical attempts). Zero instrument-invalid cells are required.
Only after that pass may a clean commit receive the local annotated `v0.13.0`
instrument tag and a marker-last authorization binding the real host, runtime,
models, schedules, artifacts, and descriptive selection.

Release verification recomputes an exact-key archive from artifact bytes,
cross-binds every phase, requires `authorized_research` context, and checks that
an actual annotated `v0.14.0` tag object peels to the archived commit. Caller
supplied state or arbitrary digest maps cannot satisfy it.

The result is limited to this fixed synthetic benchmark. It cannot establish
generalized real-world performance without a later external-task replication.
Brix/product/plugin development remains isolated until the research archive is
sealed.

## Offline verification

```powershell
python -m bench.generate_next_study --verify
python -m bench.next_study_schedule --verify
python -m bench.next_study_semantic_simulation --verify
python -m bench.next_study_rehearsal --write
python -m bench.next_study_readiness
python -m pytest -q
```

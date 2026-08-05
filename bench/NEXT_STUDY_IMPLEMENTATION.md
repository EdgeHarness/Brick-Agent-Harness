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

Human review remains advisory. Reviewer A now has a blinded, outcome-free,
family-balanced 44-case package under `reviewer-handoff/`. One completed review
can find content defects and support statements about that reviewer's audited
sample, but it is not an inter-rater reliability estimate. A second independent
reviewer is required before any agreement claim, and an independent adjudicator
is required before a consensus claim. No human response may silently supply an
answer key, satisfy authorization, or change the fixed synthetic-suite result.
The separately materialized 66-case valid/invalid challenge set remains internal
and sealed from Reviewer A. See `NEXT_STUDY_HYBRID_VALIDATION.md`.

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

Candidate commit `e7ca30c` passed native Windows qualification and completed a
score-masked 22-cell development shakeout: all 22 cells committed and zero were
instrument-invalid. During the later gate audit, an operator command
inadvertently displayed raw records from that already-invalidated run. It is
therefore retained only as diagnostic history and is not treated as an
operator-masked qualification. It cannot authorize the current source fingerprint: a
review found that Linux CI was documented but not required by the authorization
builder. The premature local tag was deleted and its authorization was retained
under `results-next-study/authorization-invalidated-linux-gate/` for audit.

The repaired authorization now requires all five Ubuntu jobs (Python 3.9
through 3.13) from GitHub Actions for the exact native-preflight commit. The
collector reads the GitHub Actions run and attempt-specific jobs API, retains a
canonical projection, and hashes it. Authorization refetches that run and
rejects absent, stale, hand-authored, wrong-commit, failed, incomplete, or
non-Ubuntu evidence. The exact commit must also pass the native Windows clean
checkout and a fresh score-masked 22-cell shakeout because the authorization
repair changed the fingerprint.

After committing and pushing the candidate so CI can run, the remaining order
is: collect exact-commit Linux evidence; repeat native preflight and clean
checkout qualification; rebuild schedules; rerun the zero-invalid shakeout;
create the local annotated `v0.13.0` tag; then issue marker-last authorization
binding the tag object, host, runtime, model digests, schedules, artifacts,
descriptive selection, and both platform gates. Calibration remains
mechanically blocked until those steps pass. The execution surface is
`python -m bench.next_study_live --help`.

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
python -m bench.next_study_reviewer_handoff verify-reviewer-a
python -m pytest -q
```

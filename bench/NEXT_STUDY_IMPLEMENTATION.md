# Brick successor study: offline-qualified 2.2.0 candidate

This document records the repaired offline instrument and its remaining gates.
It does not authorize a model call or report a model result.

## Candidate and audit result

- `office-generators/2.1.2` remains terminal with ten confirmed prompt/grader
  blockers and `v0.13.1` permanently unissued. An explicit pre-outcome
  authorization creates `office-generators/2.2.0` under protocol 1.5.0 and
  target tag `v0.13.2`. It preserves the 2.1.0 seed namespace, 11 families,
  220 retained clusters, and the claim rule. Full content hashes are rebound.
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
  internal-validity finding. All ten previously reproduced prompt/grader
  contradictions now have explicit public wording and deterministic regression
  coverage.
- Grader conformance passes 528 positive baselines, exactly 4,332 targeted
  mutations, and 1,872 benign controls. Placeholder presentations and
  alternate-policy outcomes fail.

Human and agent packet-review utilities remain advisory and outside
authorization. Four reports and the terminal 2.1.2 failure remain byte-bound.
The 2.2.0 remediation closure maps all ten blocker IDs to public wording and
requires the regenerated manifest, semantic simulation, and grader conformance
to pass. It records zero live model calls and no inspected effectiveness data.

## Statistics and evidence

Protocol `1.5.0`, design `0.9.0`, construct contract
`office-construct/1.3.0`, and grader `office-strict-grader/3.2.0` are active.
The successor authorization is bound before any live study cell or
effectiveness result and permits no automatic 2.2.1 successor.
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

The frozen program would have been:

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

## Remaining gates before calibration

Do not start calibration yet. First commit the exact candidate, pass the
required Linux Python matrix and native Windows clean-checkout reproduction,
then issue and run the separately authorized score-masked 22-cell development
shakeout. It must contain zero instrument-invalid cells. Only that pass permits
the annotated `v0.13.2` tag and host-bound research authorization.

## Historical live gates

The invalidated 2.1.0 candidate passed native Windows qualification and completed a
score-masked 22-cell development shakeout: all 22 cells committed and zero were
instrument-invalid. During the later gate audit, an operator command
inadvertently displayed raw records from that already-invalidated run. It is
therefore retained only as diagnostic history and is not treated as an
operator-masked qualification. It cannot authorize the current source fingerprint: a
review found that Linux CI was documented but not required by the authorization
builder. The premature local tag was deleted and its authorization was retained
under `results-next-study/authorization-invalidated-linux-gate/` for audit.

The repaired authorization now requires all five Ubuntu jobs (Python 3.9
through 3.13) from GitHub Actions for the exact native-preflight commit. Native
qualification clones committed material without hardlinks, detaches at that
same commit, and runs the full suite there so ignored workspace files cannot
affect the result. The
collector reads the GitHub Actions run and attempt-specific jobs API, retains a
canonical projection, and hashes it. Authorization refetches that run and
rejects absent, stale, hand-authored, wrong-commit, failed, incomplete, or
non-Ubuntu evidence. The exact commit must also pass the native Windows clean
checkout and a fresh score-masked 22-cell shakeout because the authorization
repair changed the fingerprint.

That former qualification evidence cannot authorize 2.2.0. The current
execution surface requires the successor remediation closure and a fresh exact-
commit Linux/native/shakeout chain; it never treats the terminal reconciliation
as a pass.

Release verification recomputes an exact-key archive from canonical artifact
bytes, proves every artifact equals its Git blob at the archived commit,
cross-binds every phase and the archived authorization, requires
`authorized_research` context, rechecks the annotated `v0.13.2` instrument tag,
and checks that annotated `v0.14.0` peels to the archived commit. Caller-supplied
state, uncommitted files, or arbitrary digest maps cannot satisfy it.

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

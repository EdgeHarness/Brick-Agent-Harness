# Brick successor study: terminal 2.1.2 construct-gate state

This document records why the frozen replacement cannot advance. It does not
authorize a model call or report a model result.

## Candidate and terminal audit result

- `office-generators/2.1.2` produces 528 unique, split-neutral cases across 11
  fixed synthetic families. It deliberately retains the 2.1.0 seed namespace:
  relative to 2.1.1, 240 public semantic surfaces remain unchanged and 288
  cases across six repaired families change. Full content hashes are rebound.
  Generator 2.1.0 and tag `v0.13.0` are invalidated before calibration.
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
- The earlier semantic gate executes 1,056 legal typed positive workflows (both primary
  conditions for every case), verifies every relevant dependency and
  record-order/distractor invariance, and reports no critical, high, or medium
  internal-validity finding. That model-free result did not test reasonable
  alternate public-prompt interpretations.
- Grader conformance passes 528 positive baselines, exactly 4,332 targeted
  mutations, and 1,872 benign controls. Placeholder presentations and
  alternate-policy outcomes fail.

Human and agent packet-review utilities remain advisory and outside
authorization. The three promised reports are now complete and byte-bound.
Seven reported defect classes reproduce deterministically against the public
prompt and live grader: formula grammar, confirmation language, presentation
bullet exactness, memory separators, `brief_sequence`, preference title
construction, and unannounced mention order. Therefore generator 2.1.2 is
`construct_gate_failed`; this is not an inference from model agreement.

## Statistics and evidence

Protocol `1.4.0`, design `0.8.2`, construct contract
`office-construct/1.2.0`, and grader `office-strict-grader/3.2.0` are active.
The amendment from 2.1.1 is bound before any live study cell or effectiveness
result and permits no automatic 2.1.3 successor.
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

## No remaining live gate under this protocol

Do not run the 22-cell shakeout, create `v0.13.1`, or start the 352-cell
calibration. The bound amendment forbids automatic 2.1.3 and family removal.
Any repair requires explicit authorization of a new protocol and an
independently versioned generator; 2.1.2 must remain immutable evidence.

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
through 3.13) from GitHub Actions for the exact native-preflight commit. The
collector reads the GitHub Actions run and attempt-specific jobs API, retains a
canonical projection, and hashes it. Authorization refetches that run and
rejects absent, stale, hand-authored, wrong-commit, failed, incomplete, or
non-Ubuntu evidence. The exact commit must also pass the native Windows clean
checkout and a fresh score-masked 22-cell shakeout because the authorization
repair changed the fingerprint.

That former qualification sequence is now unreachable. All reports were
reconciled, and deterministic counterexamples failed the construct gate before
the native and live steps. The execution surface remains in the repository for
audit and rehearsal, but its authorization loader rejects the terminal
reconciliation.

Release verification recomputes an exact-key archive from canonical artifact
bytes, proves every artifact equals its Git blob at the archived commit,
cross-binds every phase and the archived authorization, requires
`authorized_research` context, rechecks the annotated `v0.13.1` instrument tag,
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

# Post-S7 next-study research basis

Status date: 2026-08-04; active supersession recorded 2026-08-05. This note
records evidence used to design the successor and retains historical proposals.
It is not a preregistration, execution authorization, benchmark result, or
retained-data release. Where this note requires human review or names generator
2.1.0/design 0.5.0, that text is superseded by protocol 1.4.0 and the
`office-generators/2.1.2` replacement contract and its bound pre-outcome
amendment. Human and agent packet reviews
are advisory only; authorization instead binds deterministic public-outcome,
semantic-runner, mutation, rehearsal, CI, native, and shakeout gates. Live and
retained execution remain disabled in `next_study_design.json`.

## Evidence hierarchy

1. Brick's tracked terminal decision, direction-blind audit, generated-case
   checks, independent review, and executable contracts decide what Brick may
   claim or run.
2. Peer-reviewed work and maintained open-source implementations inform
   evaluation mechanics.
3. Recent preprints identify risks and design candidates. They do not validate
   Brick by analogy, and their numerical findings are not transferred to this
   study.

## What S7 established without reading a condition effect

The score-masked runtime decision selected 20 cases per family. The subsequent
preregistered direction-blind audit raised ceilings for `cal_brief`,
`email_reply`, and `pptx_from_email`, and a floor for `xlsx_from_email`.
Protocol 1.0.2 therefore ended before an S7 freeze. There is no D0-C, S8
handoff, condition comparison, or retained run.

The tracked postmortem consumes only that runtime decision, the
condition-combined audit, and the public D0-B manifest. It does not open raw
attempts. It verifies that every family had the same coarse workload,
distractor, and constraint-profile marginals, but not the same minimum action
burden:

| Family examples | Conservative minimum model-facing tool calls per case |
|---|---:|
| `pptx_basic` | 1, 1, 1, 1 |
| `cal_brief` | 2, 2, 2, 2 |
| `email_reply` | 3, 3, 3, 3 |
| `pptx_from_email` | 3, 3, 3, 3 |
| `multi_offsite` | 5, 5, 5, 5 |
| `xlsx_from_email` | 5, 6, 7, 8 |

That is a design defect, not a directional efficacy result. A successor must
model discovery calls, source reads, mutations, artifact size, constraint
branches, and subepisodes as explicit generation and balance axes.

The rules reference and generated grader also compile the same hidden
`required_effects` object. Their agreement demonstrates implementation
self-consistency, not independent prompt-to-ground-truth validity. A model-free
mutation audit now proves that every applicable named grader check rejects a
targeted valid mutation across all 352 retired-suite cases: 1,984 probes, zero
model calls. This closes mutation sensitivity for the retired grader only; it
does not close independent-oracle or prompt-validity gates for a new suite.

## Research and implementation signals

### Task and reward validity

- The 2025 preprint [Establishing Best Practices for Building Rigorous Agentic
  Benchmarks](https://arxiv.org/abs/2507.02825) introduces the Agentic Benchmark
  Checklist and separates task setup from reward design. Its reported audits
  show that benchmark defects can materially over- or underestimate agent
  performance. Brick consequently requires independent prompt-to-outcome
  derivation, mutation testing of every applicable named check, and human
  adjudication before calibration.
- OpenAI's July 2026
  [SWE-Bench Pro audit](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)
  reports overly strict tests, underspecified prompts, low-coverage tests, and
  misleading prompts, with independent review by experienced engineers. Brick
  adopts the useful process, not its domain-specific numbers: independent cold
  review, recorded disagreements, and adjudication over accepted alternatives.
- NIST's draft
  [AI 800-2](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-2.ipd.pdf)
  treats benchmark validity as evidence for an intended interpretation and use;
  it does not prescribe duplicate annotation of every non-claim cohort. The
  308 calibration/retained claim cases therefore receive human review, while
  the other 220 cases remain explicitly machine-only conformance evidence.
- Partial double annotation is a recognized way to estimate reliability under
  constrained annotation budgets (for example,
  [NAACL Findings 2025](https://aclanthology.org/anthology-files/pdf/naacl/2025.naacl-findings.185.pdf)).
  Brick freezes 88 factor-balanced second reviews and automatically expands to
  all 308 after two reliability events; this is a study-specific control, not a
  claim that partial review is universally sufficient.
- The maintained
  [tau2/tau3 repository](https://github.com/sierra-research/tau2-bench) records
  more than 75 corrections for wrong expected actions, ambiguity, impossible
  constraints, and missing fallbacks. Brick therefore assigns a new generator
  and seed namespace to a corrected suite and forbids model-result reuse from
  office generator 1.1.0.

### Difficulty, action burden, and scaffold effects

- The 2025 preprint
  [SABER: Small Actions, Big Errors](https://arxiv.org/abs/2512.07850) separates
  mutating and non-mutating deviations and reports that mutation errors and
  context drift are strongly associated with task failure. This supports
  recording action burden and mutation count as calibration axes; it does not
  justify changing Brick's harness or excluding a family after seeing results.
- The 2026 preprint
  [A Unified Framework for the Evaluation of LLM Agentic Capabilities](https://arxiv.org/abs/2605.27898)
  reports that scaffold choice and environmental volatility materially change
  outcomes under a standardized instruction/tool/environment layer. Brick
  therefore preserves the same paired instances, model, native tool schemas,
  and environment across the two conditions, while attributing model,
  instrument, and environment failures separately.
- The 2026 preprint
  [Agent psychometrics](https://arxiv.org/abs/2604.00594) argues that aggregate
  pass rates hide task heterogeneity and models task-level features and
  scaffold ability separately. Brick's successor therefore calibrates and
  reports all 11 families explicitly rather than letting an aggregate conceal a
  floor or ceiling.
- The exploratory 2026 preprint
  [Efficient Benchmarking of AI Agents](https://arxiv.org/abs/2603.23749)
  reports useful ranking signal from tasks with historical pass rates between
  30% and 70%, while noting that scaffold shift degrades absolute-score
  prediction. Brick uses a broader provisional 10--22 of 32 direction-blind
  acceptance band. That band is now frozen for direction-blind calibration; it
  is not imported evidence or an execution license.

### Stochastic reliability and final-state grading

- The peer-reviewed ICLR 2025
  [tau-bench paper](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b126cc38b8638e07bef37e7b2bb72bf-Abstract-Conference.html)
  grades authoritative final database state and introduces `pass^k` to expose
  reliability over multiple trials. Brick already grades authoritative state
  and artifacts; the successor proposes two independently seeded trials per
  condition and instance.
- The 2026 preprint
  [On Randomness in Agentic Evals](https://arxiv.org/abs/2602.07150) analyzes
  60,000 trajectories and reports material single-run pass-rate variation even
  at temperature zero. It recommends repeated runs and power analysis. Brick's
  one-trajectory S7 primary is therefore retired; a repeat-aware clustered
  analysis and its power assumptions must be frozen before any successor model
  call.

### Reproducible evaluation architecture

- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) provides a
  maintained dataset/solver/scorer evaluation architecture with sandbox and log
  support. Brick keeps the same separation locally: immutable generated
  instances, condition mechanisms, graders, and marker-last attempt evidence.
- Inspect's 2026
  [SWE-bench scorer correction](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/src/inspect_evals/swe_bench/README.md)
  distinguishes infrastructure failure from an incorrect model outcome rather
  than inferring both from a process exit. Brick retains its separate runner,
  environment, model, grader, and strict-success axes.

## Fail-closed successor architecture

The historical design below proposed version 0.5.0 and generator 2.1.0. The
terminal machine-readable contract is design 0.8.2 with generator 2.1.2 and the
intentionally preserved 2.1.0 seed namespace. The allocation remains
across 11 families:

| Split | Cases per family | Total cases |
|---|---:|---:|
| Development | 8 | 88 |
| Direction-blind calibration | 8 | 88 |
| Validation | 4 | 44 |
| Sentinel | 4 | 44 |
| Retained | 20 | 220 |
| Adversarial | 4 | 44 |
| **Total** | **48** | **528** |

The frozen calibration has eight cases, two conditions, and two independent
trials per cell: 32 condition-combined outcomes per family and 352 total model
attempts. Every family must remain in the inclusive 10--22 band; any miss
retires the complete generator version rather than dropping a family post hoc.
The retained primary is fixed at 20 cases per family, two conditions, and two
trials: 220 instance clusters and 880 attempts. Its normal-approximation power
is `0.828074238908` for a 12 percentage-point paired effect under the declared
conservative variance/correlation envelope. Smaller effects remain estimable
but do not receive a powered confirmatory claim.

The larger sentinel has 88 primary-condition cells. Observing zero invalid
cells would have an exact one-sided 95% binomial upper bound of
`0.03346948891663748` under an explicitly stated independent, identically
distributed Bernoulli model. The protocol labels that bound diagnostic only;
it is not an efficacy or deployment-reliability claim.

Before any model call, the design requires versioned artifacts for the
generator, public-packet outcome compiler, construct and semantic simulation,
grader mutation/conformance matrix, frozen statistics, masking/release
rehearsal, closed research catalog, exact-commit Linux and native reproduction,
and an explicit phase-specific authorization. The three promised advisory
reports are fully mapped to deterministic reproductions or documented
refutations. Seven blocker classes survive that process, so the candidate is
not frozen and packet-review utilities have not supplied outcomes or set the
gate by themselves.

The contract returns `execution_allowed=false`; retained execution is
separately false. Reproduce the offline generator chain with
`python -m bench.generate_next_study --verify`. There is no next live step under
protocol 1.4.0: the 22-cell shakeout, calibration, and `v0.13.1` are blocked.

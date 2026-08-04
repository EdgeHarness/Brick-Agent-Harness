# S7 research and implementation basis

This note records why the S7 controls exist. It is not a claim that clinical
trial regulation governs this software experiment; that guidance is used as a
conservative integrity analogue.

## Generation and scoring separation

The UK AI Security Institute's Inspect documentation supports unscored eval
logs and a later, separate scoring command. S7 adopts the stronger local
boundary that D0 generation writes `not_run` grades and the operator-facing run
summary contains no success field. The runtime sample-size decision must be
committed before the isolated floor/ceiling grader runs.

Source: <https://inspect.aisi.org.uk/scoring-workflow.html>

## Runtime-only sample-size adaptation

ICH E20 says adaptations based on nuisance parameters should use blinded data,
and that the rule should be prespecified to reduce risks to trial integrity.
S7's analogue uses only median valid wall time, a frozen multiplier, and a
frozen threshold. It rejects any evidence that was already graded. It never
reads a condition score or directional effect to choose 12 versus 20 retained
cases per family.

Source: <https://www.fda.gov/media/188961/download> (lines 391-398)

## Executable benchmark integrity

The Agentic Benchmark Checklist reports that task-setup and reward-design bugs
can materially distort agent benchmark results. Accordingly, S7 treats the
protocol prose as insufficient: cohort size, masking, evidence bindings,
floor/ceiling logic, opportunity accounting, and analysis are executable,
fail-closed contracts with regression tests.

Source: <https://arxiv.org/abs/2507.02825>

## Deterministic bootstrap

NumPy documents that `Generator` does not promise version-compatible streams.
S7 therefore pins Python 3.13, NumPy 2.5.1, an explicit `PCG64` bit generator,
seed 20260729, draw-major/family-major/instance-ID ordering, 20,000 draws, and
the linear quantile method (Hyndman-Fan type 7). Tests bind the first 100 index
vectors by a canonical digest so dependency or loop-order drift fails visibly.

Sources:

- <https://numpy.org/doc/stable/reference/random/generator.html>
- <https://numpy.org/doc/stable/reference/generated/numpy.quantile.html>
- <https://robjhyndman.com/publications/quantiles/>

## Opportunity fairness

The primary comparison retains the same frozen end-to-end opportunity ceiling.
The equal-action sensitivity is different and explicitly labeled: both
conditions receive the same non-transferable driver allowance, while only the
full harness receives separately capped planning and completion-review calls.
No role may borrow another role's unused calls or tokens. This distinguishes
useful harness overhead from a hidden increase in action opportunities.

## D0-A instrument correction

D0-A published 88 logical cells, but three cells returned Ollama HTTP 500 on
both the initial attempt and its immediate retry. The score-free audit binds
that fact; no runtime decision or grading followed. Ollama's public issue
tracker documents HTTP 500 as a server/runner failure class on Windows, but the
available local server log did not capture this run, so Brick does not claim a
more specific root cause. Protocol 1.0.1 makes the smallest direction-blind
change supported by the local evidence: retain one full-attempt retry, but
precede it with a fixed 60-second cooldown and require the loopback server to
report the exact frozen Ollama version and model digest. D0-B is consumed as the
only correction cohort; another instrument fault stops the experiment.

Source: <https://github.com/ollama/ollama/issues/12940>

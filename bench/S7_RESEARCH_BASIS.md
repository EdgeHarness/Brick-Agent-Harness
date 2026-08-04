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
both the initial attempt and its same-seed retry. The score-free instrument
audit remains immutable and invalid; no runtime decision or grading followed.
Protocol 1.0.1's cooldown-only explanation was provisional and is preserved as
history, not treated as the final diagnosis.

The original local server log did capture the run. The canonical parser audit
binds its snapshot and all six events. Every HTTP 500 is immediately preceded
by both the Qwen3Coder and Qwen3.5 parser warnings. The paired generations used
259, 275, or 381 tokens and each runner record says `truncated = 0`; there is no
evidence for a 700-token cap, context overflow, or OOM explanation.

The pinned Ollama v0.32.5 source makes the attribution mechanically narrower:
Qwen3Coder does not emit a raw tool-call event until it has observed the full
outer `</tool_call>` delimiter. It then rewrites opening `function` and
`parameter` tags and escapes text without deleting or reordering their closing
tags. The observed `unexpected EOF` and `function closed by parameter`
signatures therefore identify malformed model-emitted inner tool-call grammar.
Protocol 1.0.2 prospectively records these two signatures as
`model_output_tool_syntax_rejected`: model origin, strict failure, no retry.
It does not relabel D0-A.

All other HTTP 5xx, connection, and timeout failures remain environment-origin
and are eligible for the one same-seed retry. A malformed success response or
unrecognized client exception is runner-origin and is not retried. This follows
Inspect's warning that indiscriminate retries can create distribution shift and
its distinction between infrastructure errors and errors that are themselves
scoreable task outcomes. Exact token telemetry is absent from Ollama's error
response, so Brick stores a null exact count plus zero-to-request-limit bounds
rather than inventing a value. Parser-rejection rates by condition are emitted
only after score unmasking.

Protocol 1.0.2 also removes `execution_status` and `failure_origin` from the
operator-facing D0 cell stream. D0-A showed that these fields leak model budget
exhaustion by condition even without a grader score. D0-B exposes only the
instrument-validity bit needed to stop on an infrastructure defect; automated
sealed processing retains the full evidence.

A trace replay was deliberately not performed: a new same-seed generation
cannot recover the original raw bytes and would add post-hoc model calls without
changing the source-level proof. D0-B remains the sole correction cohort; an
unresolved instrument fault still stops the experiment.

Sources:

- <https://github.com/ollama/ollama/blob/v0.32.5/model/parsers/qwen35.go>
- <https://github.com/ollama/ollama/blob/v0.32.5/model/parsers/qwen3coder.go>
- <https://github.com/ollama/ollama/issues/14492>
- <https://inspect.aisi.org.uk/errors-and-limits.html>

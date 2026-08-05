# Brick hybrid content-validity track

This optional track strengthens evidence about the **fixed synthetic suite**.
It does not establish real-world model performance, does not replace the
independent outcome compiler, and is not an execution-authorization gate.

## What human judgment adds

Humans can test whether an office prompt has one reasonable interpretation,
whether its required outcome follows from visible information, and whether the
scoring target reflects the stated business task. That is evidence about face
and content/construct validity. Reviewing synthetic cases cannot show that the
cases occur at real-world frequencies or that benchmark performance predicts
deployment outcomes.

Agent review is useful for exhaustive, repeatable triage. It is not independent
ground truth: agents can share training-data, rubric, and reasoning failures.
Agreement with humans shows reproduction on the audited task and version only;
it does not establish correctness or human-equivalent intelligence.

## Staged economical design

- Reviewer A independently reviews an outcome-blind 44-case audit: four cases
  per family and 44 judgments. This first stage is for defect discovery and is
  not an inter-rater reliability estimate.
- If an agreement claim is wanted, Reviewer B reviews the same packets without
  seeing Reviewer A's answers. A third independent person adjudicates any
  disagreement before seeing the oracle. All reviewers are prohibited from
  using generative AI.
- Two agents from distinct, non-Qwen model lineages review all 308
  claim-bearing packets. Model, prompt, runtime, public inputs, and outputs are
  hash-bound; generator, oracle, and grader access is prohibited.
- The challenge blueprint selects 66 bases: one case per family and split. It
  has been materialized into 33 valid controls and 33 invalid challenges, with
  the truth key stored separately from public challenge packets.
- Humans primary-review all 66 challenges; a fixed 22 are independently
  secondary-reviewed. Agent auditors review all 66.
- The initial human work is 44 judgments. The stronger two-coder agreement
  stage requires 88 original-case judgments. Challenge review is a later,
  separately distributed stage and is not needed to use Reviewer A's defect
  report.

The original sample is coverage-optimized, not a probability sample. It cannot
support a population defect-rate bound. Krippendorff's alpha and exact agreement
are reported with uncertainty when estimable, but no universal alpha threshold
is used. Alpha can be undefined or misleading when nearly every item receives
the same label.

## Acceptance and escalation

- Any confirmed original prompt/outcome defect is converted into a deterministic
  counterexample and routed into the existing construct gate. This indirect
  route can pause execution; the advisory review result itself cannot authorize
  execution.
- With zero original reliability events, human original-case review stops after
  44 cases. One event expands double review to the frozen 88-case sample. Two or
  more events expand primary review to all 308 claim-bearing cases, with
  secondary review of every mismatch.
- An agent may be described only as reproducing the audited human consensus if
  it matches all 44 original consensus records, accepts all 33 valid controls,
  and detects all 33 invalid challenges. Even then, it remains advisory on the
  unaudited cases.
- Passing all 66 challenges has a one-sided 95% exact lower bound of 0.955625
  for that deliberately constructed challenge set. Passing all 33 invalid
  challenges has a corresponding sensitivity lower bound of 0.913219. Neither
  number estimates natural defect prevalence.
- TOST equivalence is not reported unless a separate, prospective power
  analysis, equivalence margin, and coder-group design are frozen. The published
  substitution study used 38 coders in two groups of 19; it does not justify an
  80-item/two-human shortcut for Brick.

## What would establish real-world value

A separate study must define the intended office-user population, draw a
provenance-bound probability sample of real workflows, reproduce realistic
tools/costs, and have qualified target users assess observable outcomes. Sample
size follows that study's estimand, expected variance, clustering, and desired
precision—not a preselected count such as 44.

Relevant guidance and evidence:

- NIST AI 800-2: https://doi.org/10.6028/NIST.AI.800-2.ipd
- NIST AI 800-3: https://doi.org/10.6028/NIST.AI.800-3
- He et al., LLM annotator substitution: https://arxiv.org/abs/2510.06658
- Kasner et al., LLM span annotators: https://arxiv.org/abs/2504.08697
- Krippendorff on reliability thresholds and uncertainty:
  https://repository.upenn.edu/bitstreams/b6ea3a5b-3dee-4f27-a159-e44393eda7d4/download

## Current status

The 66 challenges are materialized and the 44-case Reviewer A package is ready
at `reviewer-handoff/brick-office-v2-reviewer-a.zip`. No human or agent judgment
has yet been recorded, so no human-reviewed validity or agreement claim may be
made. The benchmark authorization remains independent of this advisory track.

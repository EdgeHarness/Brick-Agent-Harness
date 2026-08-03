# S6C research and implementation basis

Status date: 2026-08-03. This note records why the S6C instrument is built the
way it is. It is not benchmark evidence and contains no retained outcome.

## Evidence hierarchy

1. Brick's executable contracts, adversarial tests, native preflight, and
   immutable attempt records decide whether this instrument is valid.
2. Official framework and runtime documentation informs transport, recovery,
   and provenance mechanics.
3. Research papers identify risks and useful audit directions. July 2026 papers
   cited below are preprints; they do not override failed Brick tests or justify
   a result by analogy.

## Operational sources and resulting decisions

- [Ollama tool-calling documentation](https://docs.ollama.com/capabilities/tool-calling)
  shows the native function schema, assistant `tool_calls`, and follow-up
  `role=tool`/`tool_name` envelope. Both primary conditions use that same
  envelope. Brick deliberately permits exactly one call per response; parallel
  calls are a supported Ollama feature but are outside the frozen one-action
  opportunity contract.
- [Inspect agent checkpointing](https://inspect.aisi.org.uk/checkpointing.html)
  restores agent state, sandbox state, events, and store data, while explicitly
  requiring scaffold support and excluding arbitrary in-memory or external
  effects. [Inspect evaluation retries](https://inspect.aisi.org.uk/eval-logs.html#eval-retries)
  preserve completed samples and create a new log. Brick therefore treats
  recovery as an explicit instrument feature: committed attempts are reused,
  prepared evidence is adopted without another model call, and an abandoned
  pre-prepare candidate is preserved before a new physical execution.
- [Harbor regrade](https://github.com/harbor-framework/harbor/blob/main/docs/content/docs/run-jobs/regrade.mdx)
  holds the agent execution fixed, creates a separate result, and anchors resume
  identity to source UUID/task digest rather than a mutable path. Brick likewise
  never mutates a committed attempt or reruns a model to repair a grader result;
  logical identity binds the instance, model digest, condition mechanism,
  prompt, sampling, budget, and tool schema.
- The current [tau-bench repository](https://github.com/sierra-research/tau2-bench)
  reports more than 75 task-quality corrections, including incorrect expected
  actions, ambiguous instructions, impossible constraints, and missing fallback
  behavior. Brick versions every generator correction, regenerates every split,
  changes content hashes, and never silently relabels an already committed run.

## Recent research signals

- The 29 July 2026 preprint
  [Automated Transcript Analysis for Detecting Flaws in Agentic Benchmarks](https://arxiv.org/abs/2607.27518)
  studies ground-truth access, tool failure, guessing vulnerability, and answer
  format ambiguity. Brick's disposable transcript review directly found two
  prompt/oracle mismatches and one tool-schema ceiling; those were corrected
  before D0 and preserved as superseded development records.
- The 31 July 2026 preprint
  [Execution-First Synthetic Tool-Use Trace Generation](https://arxiv.org/abs/2607.29175)
  constructs workflows, maps tools, executes and validates traces, and only then
  synthesizes user tasks. Brick independently follows the same useful ordering:
  a model-free rules executor must satisfy the strict compiled grader for every
  generated case before model efficacy work begins.
- The 31 July 2026 survey
  [Beyond Component Testing: Validating Agentic AI Systems](https://arxiv.org/abs/2607.29405)
  synthesizes 257 papers and emphasizes trajectory context, temporal validity,
  runtime evidence, and audit-ready records. Brick retains full requests,
  responses, actions, state transitions, artifacts, failure origin, and physical
  publication identity rather than relying only on a terminal score.
- The 31 July 2026 preprint
  [AgentHPOBench](https://arxiv.org/abs/2607.29626) uses 30 executable sequential
  tasks under a unified protocol and reports limitations in sustained
  refinement and log diagnosis. Brick therefore reports call, token, model-time,
  wall-time, and action frontiers alongside strict success; a harness that wins
  only by unreported extra opportunity would not answer the primary question.

## S6C decisions fixed before D0

- Primary contrast: identical 4B model digest, paired instances, native tool
  schemas/order, sampling, seed derivation, and end-to-end opportunity ledger.
- `native_tools`: native tool loop, typed closed validation, and structured
  model-error feedback.
- `harness_full`: the native baseline plus plan-first control, attempt-scoped
  untrusted memory, known-alias recovery, identical-mutation suppression,
  bounded model-facing observations, and a public completion-review guard.
- Descriptive conditions: `raw_json`, `harness_no_plan`,
  `harness_no_recovery`, `harness_no_completion_guard`, and
  `harness_no_memory`. They are not confirmatory and cannot support individual
  mechanism-causality claims.
- `rules_reference`: model-free architecture-selection reference, reported
  separately from every model condition.
- Retained execution remains mechanically disabled in S6C.

The equal-action-opportunity sensitivity is intentionally not assigned an
ad-hoc larger total-call budget here. D0/S7 must define and test a role-aware
ledger that distinguishes driver opportunities from planning and completion
overhead. Giving both conditions the same larger undifferentiated budget would
not equalize action opportunity and would answer a different question.

## Development defects found and resolved

- Generator `1.0.1` made every required reminder-message checklist item explicit.
- Generator `1.0.2` made every oracle-critical preference-learning event value
  explicit while preserving the original seed namespace and structure allocation.
- A correct completion review exceeded an unrelated 1,000-character `think`
  schema ceiling. The ceiling is now 4,096 characters, bounded but consistent
  with the configured 700-token response maximum.
- Attempt identity incorrectly recorded the shared-ledger policy as false for
  atomic tasks. It now records the actual protocol policy for every attempt.
- Observation truncation was declared harness-only but applied to native too.
  Mechanism-gated execution now gives native the full observation and retains a
  bounded model view only where the condition declares it; full evidence is
  retained for both.
- The S6 protocol now cryptographically binds the passed F0 release attestation,
  Ollama 0.32.5, and the exact Qwen3.5 4B model digest. Live preflight rejects
  runtime or model drift.

These are instrument corrections from disposable development work. They are not
efficacy results, are not included in the retained estimand, and cannot be used
to choose the D0 sample size.

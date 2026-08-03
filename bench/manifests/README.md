# S6G task manifests

`office-v1/` is the canonical generated-input set for the eleven synthetic
office task families. It is instrument input, not a benchmark result. No model
was called to create or verify these files.

## Frozen split protocol

| Split | Cases/family | Total | Purpose |
|---|---:|---:|---|
| development | 2 | 22 | The preregistered D0 timing set: 22 paired cases × 2 conditions = 44 condition cells. |
| validation | 4 | 44 | Generator, instance-loader, condition, and grader integration checks before sentinel. |
| sentinel | 1 | 11 | One disposable end-to-end instrument cell per family and condition in S8. |
| retained | 20 | 220 | The preregistered primary default; if D0 triggers the runtime-only fallback, the first 12 frozen IDs per family are used. |
| adversarial | 4 | 44 | Non-primary ambiguity, distractor, ordering, and policy-boundary checks. |

The development and retained sizes come from the existing protocol. Validation,
sentinel, and adversarial sizes are S6G design choices frozen here before S6C
or any live efficacy run. Changing a size, generator, prompt, structure, entity,
effect, or instance requires a new generator version and regenerated lock.

## What “independent” means here

The experimental unit is a semantic business-case structure, not an inference
seed. Each instance records a canonical `structure` describing family,
workload, distractor cardinality, constraint profile, and episode shape.
`structure_sha256` is computed from those semantics;
the structural-template ID is derived from that hash. The overlap checker
rejects any repeated semantic structure or template, including a renamed or
reseeded copy.

Fictional entities are generated from case-specific namespaces nested under
split-specific namespaces and use reserved `.example` addresses. The overlap
checker rejects any reused entity key or entity surface value anywhere in the
suite. This is stronger than comparing instance IDs, but it does not prove that
the synthetic distributions represent all real office work. Claims remain
limited to these frozen families.

The learning family is one logical case with two ordered `store` then `use`
subepisodes. Both share one 14-model-call/4096-generated-token opportunity
budget; both required-effect sets must pass. It is never counted as two model
attempts.

## Reproduce and verify

From the repository root:

```bash
python -m bench.generate_manifests --verify
```

Verification regenerates every case from source, compares canonical bytes,
checks every content digest and manifest count, reruns domain semantic checks,
reruns the five-way structure/entity overlap review, and verifies
`manifest-lock.json`. Regeneration is an explicit versioned operation:

```bash
python -m bench.generate_manifests --write
python -m bench.generate_manifests --verify
```

Do not edit generated JSON manually. Do not inspect retained outcomes during
later prompt, condition, or grader tuning. A task correction is a versioned
instrument change; retained inputs must never be silently patched in place.

## Research basis

The contract follows several convergent practices:

- [UK AISI Inspect datasets](https://inspect.aisi.org.uk/datasets.html) use
  stable sample IDs and explicit metadata, and support deterministic seeded
  dataset operations.
- [SWE-bench's evaluation harness](https://www.swebench.com/SWE-bench/api/harness/)
  separates instance preparation, execution, grading, and run/log identity.
- [GSM-Symbolic](https://arxiv.org/abs/2410.05229) demonstrates why symbolic
  variations are useful, while Brick adds a stricter rule that a seed-only or
  entity-only variation is not a new structural unit.
- The [Agentic Benchmark Checklist](https://arxiv.org/abs/2507.02825) documents
  how task setup and reward defects can materially distort agent scores; Brick
  therefore makes setup/effect contracts executable and failures instrument
  errors rather than model failures.
- The original [tau-bench repository](https://github.com/sierra-research/tau-bench)
  now warns that corrected successor tasks should be used. Brick treats that as
  a concrete versioning lesson: fixes create a new generator/instrument version
  and never mutate previously interpreted evidence silently.
- [LiveBench](https://arxiv.org/abs/2406.19314) motivates objective grading,
  contamination awareness, and reporting uncertainty rather than a single
  unqualified score.

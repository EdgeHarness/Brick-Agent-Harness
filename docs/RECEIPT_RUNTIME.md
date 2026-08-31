# Receipt-verified runtime

## Status

`receipt_v1` is an implemented, opt-in runtime protocol for CLI and Agent Lab
runs. It is not enabled in `bench/`, is not the default, and is not approved
for production Brix data or unattended writes.

Its purpose is narrow: a model saying `done` must not be enough to mark a task
successful. A completed run needs all of the following:

1. a durable lifecycle record written before each tool dispatch;
2. a signed receipt issued only after a real executor returns success;
3. a receipt matched to an accepted plan entry; and
4. an authoritative domain postcondition that reads the resulting state.

If no authoritative check exists, completion is `unknown` and the run ends as
`incomplete`. The model verifier may explain a result but cannot establish it.

## Execution sequence

```text
fixed route preflight
        |
        v
model plan -> pending ledger entries
        |
        v
schema and policy checks
        |
        v
fsynced dispatch record -> real tool executor
                              |
                              v
                    successful result record
                              |
                              v
                    signed execution receipt
                              |
                              v
                    matching ledger entry
                              |
                              v
                 authoritative state check
                              |
             completed | incomplete | failed | cancelled
```

The lifecycle file is append-only JSONL with contiguous sequence numbers and a
SHA-256 predecessor chain. It records tool names, result and argument digests,
route decisions, receipt identifiers, completion class, and terminal state. It
does not record prompts, argument values, observations, provider errors, or
credentials. These digests are fingerprints, not anonymization, encryption, or
protection against an attacker who controls the host.

## Code boundaries

| File | Responsibility |
|---|---|
| `harness/runtime_dispatch.py` | selects `legacy` or `receipt_v1` without changing the frozen legacy loop |
| `harness/lifecycle.py` | closed event schemas, durable append, hash-chain and relational validation |
| `harness/receipts.py` | attempt-local receipt issuer and plan-grounded ledger |
| `harness/tool_pipeline.py` | validation, policy, durable dispatch barrier, execution, receipt and grounding order |
| `harness/managed_agent.py` | model loop, replanning, cancellation and fail-closed completion |
| `harness/router_contract.py` | deterministic role and capability manifest with decision digests |
| `harness/runtime_recipe.py` | digest-bound domain, tool, profile and router assembly |

`RunConfig.runtime_protocol` defaults to `legacy`. Frozen benchmark callers do
not set it. `harness/agent.py`, `harness/grading.py`, `bench/`, and the frozen
result roots remain unchanged.

An exact domain task prompt can bind its existing strict grader as an
authoritative checker. An arbitrary interactive request has no such checker and
therefore cannot be reported as complete. A caller may supply a reviewed
`completion_checker`; provider integrations need provider-specific read-back
checks before they can use this route to completion.

Connector runs deliberately do not reuse synthetic task graders. A synthetic
grader cannot prove a HubSpot or Optix effect.

The ledger grounds an accepted sequence at tool-name level. Its `what` text is
hashed for lineage, but it is not a parser for argument-level authorization.
Every receipt separately binds the exact executed argument digest. For
`external_write` and `shell`, the operator must also see the complete canonical
tool name and arguments. If that UTF-8 representation exceeds 4,096 bytes, the
pipeline rejects the proposal before asking for approval or entering the
executor. No authorization display is truncated.

## Routing and cancellation

Each role resolves through an immutable, versioned manifest. Unknown roles,
missing `chat` or `json_object` capabilities, and insufficient declared context
fail before a model call. A plain backend's digest binds its concrete type,
model tag, context window, temperature, timeout, keep-alive value and retry
count when those fields exist. Availability is recorded as declared or
interface-checked; the manifest does not claim that a model is installed,
resident, fast, or accurate.

Cancellation is cooperative at model and tool boundaries. Agent Lab first
writes an attempt-specific cancel marker and allows the child to record a
`cancelled` terminal event, then uses its existing owned process-tree kill as
the hard fallback. A blocking model request or in-process tool cannot be
safely interrupted mid-call by this protocol. If a tool returns after the
marker appears, its real result, receipt and grounding are retained before the
run terminates as cancelled. This records the effect honestly; it does not undo
it.

## Architecture sources and limits

The implementation adopts mechanisms, not project names or unverified claims:

- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) pinned at
  `0a53fb55`: ordered pre-execution stages, durable tool-call evidence before
  dispatch, monotonic checks, normalized results, and explicit finalization.
- [Recuris](https://github.com/Gen-Verse/Recuris) pinned at `7d3745ab`:
  model-proposed pending work cannot become done without a real successful
  receipt; unmatched receipts are recorded rather than used to invent work.
- [HarnessRouter](https://github.com/HarnessRouter/harnessrouter) pinned at
  `1176d9a5`: versioned capabilities and explicit completed, incomplete, failed,
  and cancelled lifecycle states.
- [HELIX](https://github.com/HKUDS/HELIX) pinned at `b5adffa6`: typed,
  source-traceable assembly and conformance gates. Brick uses a smaller fixed
  runtime recipe rather than HELIX's complete architecture.
- [Exo RSI](https://github.com/exoharness/exo/blob/main/docs/RSI.md): immutable
  canonical history and protected control lineage. Here, RSI means Exo's
  recursive self-improvement architecture; it is not a Qualcomm runtime or an
  edge-computing standard.
- [Sakana Fugu](https://github.com/SakanaAI/fugu) pinned at `299a4717`: bounded
  roles and selective context motivated the fixed role surface. Its public
  repository does not expose the trained coordinator needed to reproduce its
  learned routing, so Brick does not claim to implement Fugu routing.
- [Meta-agent](https://github.com/canvas-org/meta-agent) pinned at `28e18519`:
  isolated development and acceptance sets plus an explicit promotion gate.

None of these repositories is copied wholesale. Provider schemas, permissions,
completion checks, error handling, and business policy remain Brick's work.

## Running it

CLI, with a known synthetic task whose grader can prove completion:

```bash
python agents/8b/run_agent.py --domain counter_demo \
  --runtime-protocol receipt_v1 \
  "Increase the counter by one twice."
```

In Agent Lab, enable **Receipt-verified runtime** in Run options. Keep it off
when reproducing a legacy result.

The deterministic engineering acceptance lane is separate from `bench/`:

```bash
python -m evals.runtime_protocol.run_eval
python -m pytest -q tests/test_receipt_runtime.py \
  tests/test_runtime_protocol_eval.py
```

The checked-in report is
`evidence/runtime-protocol/acceptance-v1.json`. In the current fixed acceptance
set, legacy recorded two false completions and one unverified completion;
`receipt_v1` recorded zero of each, preserved the two valid-success cases, and
prevented the fixed policy's unplanned third counter write. This proves the
tested control-flow properties only. It is not an 8B model benchmark, a Brix
deployment result, a security certification, or a latency measurement.
Validation recomputes the case inventory, case digests, outcome invariants,
summary, promotion gates, report digest and every bound source digest. Editing
the JSON and recomputing only its unkeyed report digest is not sufficient to
create a semantically valid report.

## Remaining gates

- Add authoritative read-back checks for each real provider workflow.
- Run an end-to-end local 8B task study with fixed prompts and a baseline.
- Exercise sudden process termination and storage faults on the target Windows
  ARM64 machine.
- Measure cancellation latency and journal retention under a long soak.
- Complete the separate BrickKV Qualcomm and GPU hardware study before making
  any cache-performance claim.

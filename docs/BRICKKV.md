# BrickKV

BrickKV is an opt-in, transaction-safe prompt-cache path for Brick when the
local model is served by a patched GenieX server. Its purpose is to avoid
reprocessing an unchanged conversation prefix without ever treating an edited,
interrupted or cross-session model state as valid.

This document describes implemented software. It does not claim a measured
latency improvement. `off` remains the default until the hardware acceptance
gates pass.

The first attested Snapdragon QAIRT protocol smoke is recorded in
[`BRICKKV_NPU_READINESS.md`](BRICKKV_NPU_READINESS.md). A broader production-
path replay then found that protocol version 1 could reuse a length-truncated
turn. That evidence is retained as a reproducible failure record and is
superseded for readiness. A later protocol-version-2 diagnostic replay found a
separate QAIRT defect: the runtime omitted the sampled assistant EOG boundary
from retained KV, so correct lineage decisions could still produce different
outputs from reset mode. The focused QAIRT fix and Brick's automated paired
equivalence gate must both pass on the NPU before any performance matrix starts.

## Why raw retained state is unsafe

GenieX owns one mutable model handle. Raw `GenieX-KeepCache: true` asks that
handle to retain state, but the header does not prove which transcript produced
the state. Brick can remove a failed exchange, prune context, leave the driver
for a verifier, retry after a disconnect, or start a second attempt. Reusing
the old state after any of those events can silently apply the wrong prefix.

BrickKV adds a lineage transaction around the mutable state:

1. Brick sends a random 128-bit session and the last committed revision.
2. GenieX canonicalizes the text transcript and binds it to the model artifact,
   tokenizer, runtime, plugin, resolved device, model parameters and chat
   template settings.
3. Reuse occurs only when the session and parent match and the request is an
   exact extension of the committed transcript.
4. GenieX commits the logical transcript revision only after generation
   finishes. It marks the resulting physical state reusable only when the
   runtime reports an EOS-complete turn.
5. A length limit, stop sequence or callback stop preserves the logical
   revision but immediately resets the physical model and reports
   `reusable: false`. The next exact extension is cold with
   `reset / previous_not_reusable`.
6. A branch, session switch, stale parent, cancellation, disconnect or error
   resets the model and clears provisional state.

The final normal response or final streaming chunk contains:

```json
{
  "geniex_cache": {
    "mode": "managed",
    "status": "cold",
    "revision": "sha256:...",
    "reason": "first_request",
    "reusable": true
  }
}
```

Managed responses also carry `GenieX-Cache-Protocol: 2`. Brick rejects a
different or missing protocol version. A missing final record means the
generation did not commit; Brick rejects that response and does not advance
its parent. `status` and `reason` describe how the current request started,
while `reusable` describes whether its completed physical state may be used by
the next request. For streaming requests, the NPU shim accepts this metadata
only once and only on the terminal provider chunk; an early, duplicate, or
missing record disables managed mode instead of manufacturing a commit.

## Brick modes

| Mode | Intended use | Available in Agent Lab |
|---|---|---|
| `off` | Current reset-by-default behavior | yes, default |
| `managed` | Transactional protocol with a patched GenieX server | yes, opt-in |
| `legacy-test` | Raw `GenieX-KeepCache` comparison in synthetic experiments | no |

`legacy-test` requires `BRICKKV_ALLOW_LEGACY_TEST=1` in the shim process. It is
not a production fallback. If the GenieX capability probe or any managed final
record is missing, the shim stops advertising managed mode.

Each Brick attempt receives new lineages. Every reasoning role, including the
driver, router, verifier and deep role, receives a different session ID. A
verifier detour can therefore lose a cache hit but cannot consume the driver's
mutable state as if it were its own.

Agent Lab exposes only `off` and `managed`. Cache diagnostics contain role,
session, parent revision and cache decision; the existing call telemetry holds
timing. Neither contains prompts or generated text. Existing run storage
remains byte-compatible in `off` mode.

## Version-one boundary

Managed GenieX caching currently accepts only scalar text messages with
`system`, `user` and `assistant` roles. It rejects VLM content, OpenAI native
tool-call messages, separated reasoning, speculative decoding, unknown roles
and mixed use with `GenieX-KeepCache`. Brick's current tool protocol is
text-based, so its normal agent loop remains inside this boundary.

Protocol version 2 deliberately treats only the runtime stop reason `eos` as
reusable. OpenAI `finish_reason: stop` is not sufficient because it also
represents provider stop sequences and callback stops. Unknown stop reasons
fail closed to a physical reset.

Session IDs separate cache lineage; they are not authentication or tenant
authorization. The server still owns one mutable handle and serializes model
requests. No file-based KV checkpoint is used.

## Run Brick against patched GenieX

Start the patched GenieX server and the shim in separate terminals:

```powershell
geniex --data-dir C:/models/geniex-data serve `
  --host 127.0.0.1:18181 --compute npu
python -m npu.ollama_shim http://127.0.0.1:18181
```

For QAIRT model bundles, the model owns its supported context configuration.
Do not add a guessed `--nctx` override. The server must bind to explicit IPv4
loopback when it is used by the attested runners.

The shim prints `BrickKV : managed` only when its fail-closed capability probe
succeeds. Then opt into one run:

```powershell
python agents/8b/run_agent.py "Use only synthetic data for this task" --cache-mode managed
```

An unpatched server produces an explicit managed-cache error. Brick never
silently falls back to raw retained state.

## Native diagnostic

[`tools/brickkv-replay`](../tools/brickkv-replay/README.md) is a C++20 program
using the GenieX C API. It runs reset, raw-retained and managed traces, applies
the real model chat template, cancels through the token callback, and writes
versioned secret-free JSON. It is an independent diagnostic, not a replacement
for `geniex serve`. Its schema version 4 uses the same EOS-only reusable rule
and `previous_not_reusable` transition as the server protocol, and binds each
result to an embedded committed source bundle, the running executable, and the
exact loaded runtime-module bundle.

The six synthetic trace families are append-only, planning removal, invalid
exchange deletion, context pruning, verifier detour and decode cancellation.
The current C callback can cancel only after token generation begins. The
GenieX API does not expose a primitive that interrupts synchronous prefill.
An HTTP cancellation observed after prefill forces a reset before any later
reuse, but prefill interruption and bounded prefill-cancellation latency are
not measured or claimed.

[`geniex_server_replay.py`](../perf/brickkv/geniex_server_replay.py) runs the
same trace shapes through the reviewed GenieX HTTP streaming path. It is used
when Windows application control blocks the unsigned diagnostic binary. The
runner keeps that policy intact, binds the loopback listener to one process
image and kernel creation time, hashes the loaded runtime modules and model,
and saves no prompt or generated text. A single replay is development evidence,
not the repeated fresh-process performance matrix. Reset mode explicitly calls
the model-reset endpoint before every request because current GenieX can reuse
append-only ordinary chat without a cache header. The paired gate grades fixed
tasks against exact expected-marker digests: managed mode may improve a reset
failure but may not regress a reset success or change results when both modes
have the same task outcome.

## Experiment runners

[`perf/brickkv`](../perf/brickkv/README.md) contains two independent studies:

- Snapdragon compares reset, `legacy-test` and managed GenieX state.
- CHTC compares vLLM automatic prefix caching explicitly off and on, separately
  on L40S and A100-SXM4-80GB GPUs.

Both use five warm-up process runs and ten measured process runs per retained
configuration. Mode order is randomized within hardware blocks. If p95 TTFT
coefficient of variation exceeds 8 percent, all modes in the block receive ten
additional repetitions. The process run is the statistical unit.

Evidence stores timings, token counts, cache decisions, output hashes and
attestation digests. GPU reports additionally retain the complete immutable
container reference and a revision-bound, per-file source manifest. They do not
store prompt or generated content. Each GPU study owns one Linux session and
process group under a child subreaper; escaped or residual workers fail the
run. APC-on evidence must demonstrate
real query activity and an append-only hit, while APC-off evidence must contain
zero hits.

## Acceptance gates

No performance claim is valid until all applicable gates pass:

- zero false hits in at least 1,000 randomized branch mutations;
- zero cross-session canary reuse across 1, 2, 4 and 8-session campaigns;
- every observed decode cancellation or generation failure makes the next
  call cold; prefill interruption is outside the current API and claim;
- reset and managed modes preserve normalized tool-call sequences, task
  outcomes and artifact hashes;
- no deadlock, race, stale provisional state or model use after teardown;
- ten independent measured process runs per retained configuration;
- run-clustered bootstrap confidence intervals and full integrity manifests;
- managed caching lowers Snapdragon append-only p95 TTFT by at least 20 percent
  with the 95 percent confidence interval excluding zero, before it is called a
  latency improvement;
- no task-success or material decode-throughput regression.

Windows ARM64 does not support Go's race detector. Native Windows tests prove
the target build, while `go test -race` remains a required Linux CI gate for the
GenieX contribution.

The frozen `bench/` protocol and completed research evidence are not imported
or modified by BrickKV. This study must not be used to rewrite earlier results.

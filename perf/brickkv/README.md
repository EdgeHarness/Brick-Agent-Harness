# BrickKV performance studies

These runners produce process-level measurements for the BrickKV acceptance
gates. They use synthetic prompts and save no prompt or generated content.

## Managed GenieX NPU smoke

Before an expensive replay matrix, `geniex_managed_smoke.py` verifies the
patched server on a real NPU. It accepts only an explicit IPv4 loopback origin,
checks cold, exact-extension, branch, session-switch, parent-mismatch and
forced-disconnect recovery decisions. Protocol version 2 also deliberately
forces a one-token truncation, requires `reusable: false`, and requires the
next exact extension to report `reset / previous_not_reusable`. It writes only
cache metadata, token counts and output hashes. Every request verifies that the selected Windows PID
still owns the exact listener and runs the exact hashed GenieX executable. The
runner also hashes the model artifact tree and verifies its own source files
byte-for-byte against the claimed HEAD commit. The output always marks
performance claims and final benchmark completion as false. A smoke-model pass
cannot substitute for the Llama 3.1 8B study.

```powershell
$serverPid = (Get-NetTCPConnection `
  -LocalAddress 127.0.0.1 -LocalPort 18182 -State Listen).OwningProcess

python -m perf.brickkv.geniex_managed_smoke `
  --execute `
  --server http://127.0.0.1:18182 `
  --server-pid $serverPid `
  --model qualcomm/qwen3_0_6b `
  --model-role smoke `
  --source-revision BRICK_COMMIT `
  --geniex-revision GENIEX_COMMIT `
  --runtime-version 2.45.0.260326 `
  --hardware-label X1E-78-100 `
  --model-artifact C:/models/geniex-data/models/qualcomm/qwen3_0_6b `
  --geniex-cli C:/geniex/bin/geniex.exe `
  --geniex-data-dir C:/models/geniex-data `
  --runtime-artifact C:/geniex/lib/geniex.dll `
  --runtime-artifact C:/geniex/lib/qairt/geniex_plugin.dll `
  --runtime-artifact C:/geniex/lib/qairt/geniex_core.dll `
  --output C:/evidence/brickkv-managed-smoke.json
```

`--runtime-version` and `--hardware-label` are bounded operator assertions and
are named as such in the evidence. Executable, model artifact, listener and
source attestations are measured by the runner. The runner refuses uncommitted
changes to itself or its source-verification and exclusive-publication helpers.
The selected process must have explicit `--data-dir`, `--host` and
`--compute npu` flags. The model artifact must be the exact
`<data-dir>/models/<catalogue-name>` directory, and its content must remain
unchanged through the run. The three required runtime DLLs must be loaded in
that same process and retain their measured hashes through publication.
The kernel process-creation time is also pinned, so a reused Windows PID cannot
inherit the earlier process identity.

Every managed response must carry `GenieX-Cache-Protocol: 2` and the exact
five-field cache record, including the boolean `reusable` state. Evidence uses
`brickkv.geniex-managed-smoke/2`; version-1 smoke evidence is not accepted as
proof of the corrected truncation behavior.

## Production-path GenieX replay

`geniex_server_replay.py` runs the six BrickKV synthetic traces through the
actual `geniex serve` streaming endpoint. This is the supported fallback when
Windows application-control policy permits the reviewed GenieX server but
rejects the separately built, unsigned C++ diagnostic. It does not weaken or
bypass that policy.

Run exactly one cache mode against one bound server process:

```powershell
python -m perf.brickkv.geniex_server_replay `
  --execute `
  --server http://127.0.0.1:18182 `
  --server-pid $serverPid `
  --model qualcomm/qwen3_0_6b `
  --model-role smoke `
  --mode managed `
  --trace all `
  --source-revision BRICK_COMMIT `
  --geniex-revision GENIEX_COMMIT `
  --runtime-version 2.45.0.260326 `
  --hardware-label X1E-78-100 `
  --model-artifact C:/models/geniex-data/models/qualcomm/qwen3_0_6b `
  --geniex-cli C:/geniex/bin/geniex.exe `
  --geniex-data-dir C:/models/geniex-data `
  --runtime-artifact C:/geniex/lib/geniex.dll `
  --runtime-artifact C:/geniex/lib/qairt/geniex_plugin.dll `
  --runtime-artifact C:/geniex/lib/qairt/geniex_core.dll `
  --output C:/evidence/brickkv-server-managed.json
```

The runner measures request wall time, streaming time to first output, stream
duration, reported token use and process working set. It records only hashes of
generated output. A cancelled stream has no final usage record, so the evidence
records the observed output-chunk count and leaves its generated-token count at
zero instead of inventing a token count.

The replay uses short exact-marker requests so ordinary measured turns can end
at EOS. It records the server's `reusable` decision and rejects a length-limited
turn that is marked reusable. Evidence uses `brickkv.server-replay/2` and
requires protocol header version 2.

One replay file proves trace execution on one bound process. It explicitly does
not attest that the process was freshly launched and never authorizes a
performance or final-benchmark claim. The final matrix controller must launch
and stop a fresh server for each randomized mode block, preserve its launch
receipt, perform the required warm-up and measured repetitions, and compare
reset and managed output hashes before producing statistics.

## Snapdragon GenieX matrix

`run_matrix.py` launches one `brickkv-replay` process for each mode in a
randomized block. The default protocol uses five warm-up blocks and ten
measured blocks. If any retained configuration exceeds 8 percent run-to-run CV
in p95 TTFT, it adds ten complete blocks for every mode.

```powershell
python -m perf.brickkv.run_matrix `
  --execute `
  --replay C:/KVBuild/release/brickkv-replay.exe `
  --model C:/models/Llama-v3.1-8B-Instruct `
  --plugin qairt `
  --plugin-path C:/GX/GenieX/sdk/pkg-geniex/lib `
  --sdk-lib C:/GX/GenieX/sdk/pkg-geniex/lib `
  --runtime-artifact C:/GX/GenieX/sdk/pkg-geniex/lib/geniex.dll `
  --runtime-artifact C:/GX/GenieX/sdk/pkg-geniex/lib/qairt/geniex_plugin.dll `
  --runtime-artifact C:/GX/GenieX/sdk/pkg-geniex/lib/qairt/geniex_core.dll `
  --device npu `
  --hardware-label X1E-78-100 `
  --expected-process-architecture arm64 `
  --source-revision BRICK_COMMIT `
  --output C:/evidence/snapdragon
```

Review the attestation, raw process records, summary and integrity manifest
before interpreting a result.

The controller verifies every native runner byte against the claimed Git HEAD,
passes the revision-bound bundle digest that was embedded at compile time,
hashes the exact replay executable, and requires each declared runtime artifact
to be loaded and unchanged. Matrix schema `brickkv.matrix/2` retains the
per-file source and runtime manifests rather than relying on a revision label.
The report authorizes only a narrow append-only BrickKV latency claim, and only
when at least ten paired process runs show a median p95 TTFT improvement of 20
percent or more, the clustered bootstrap interval excludes zero, prompt-token
work decreases, decode throughput stays within 5 percent, outputs match reset
mode, and every variability cell is stable. It always leaves the broader final
research claim unauthorized.

## CHTC vLLM matrix

`gpu_prefix_study.py` starts vLLM with automatic prefix caching explicitly off
or on and records streaming TTFT plus prefix-cache counter deltas.
`gpu_matrix.py` supplies the process-level randomization, repetitions,
confidence interval and integrity manifest.

Before submission, commit the exact transferred runner files, then calculate a
digest that binds their bytes to the full HEAD revision:

```bash
SOURCE_REVISION=$(git rev-parse HEAD)
SOURCE_BUNDLE_DIGEST=$(python -m perf.brickkv.source_bundle \
  --revision "$SOURCE_REVISION" --verify-git)
```

The verification reads every tracked blob directly from the claimed commit and
compares its bytes with the submitted file. Git index hints such as
`assume-unchanged` cannot hide a modified runner. The Git-free execute sandbox
uses the separate `--transferred` mode only to recompute those already bound
bytes.

The remote wrapper binds the wrapper bytes that HTCondor actually executes to
their canonical manifest path, then recomputes this digest before model
extraction. The final
report also retains a revision-bound per-file manifest with each runner's byte
count and SHA-256. Evidence therefore binds the declared Git revision and the
exact committed study code that was transferred. It also retains the complete,
credential-free OCI image reference and verifies that its immutable digest is
the declared container digest. The model archive is streamed
through a regular-file-only extractor that rejects absolute paths, traversal,
links, special files, duplicate files, and archives without exactly one
`config.json`.

The submit files and exact preparation steps are in
[`chtc/README.md`](chtc/README.md). L40S and A100 results are separate hardware
blocks. They are independent validation of prefix reuse, not evidence that
vLLM implements the GenieX transactional protocol. Quantized Snapdragon and
GPU absolute latency must not be presented as an apples-to-apples hardware
ranking.

Each vLLM process listens only on a Unix-domain socket inside a fresh,
owner-only directory. No TCP port is opened. The client accepts only the
reviewed health, model-catalog, metrics, and chat paths and never resolves a
URL, follows a redirect, or uses a proxy. The `/v1` API also uses a fresh
in-memory key that is neither placed on the command line nor written to
evidence. The runner verifies process liveness, socket ownership, and the exact
served model before and during measurement. This requires a pinned vLLM image
whose `vllm serve` supports `--uds`. Prompts and generated text are not
persisted. Each study and its vLLM worker tree run in one dedicated Linux
session and process group under a child-subreaper supervisor. Timeout and
abnormal-exit handling terminates the group, adopts workers that changed their
session, sweeps every descendant, and refuses the run if any member remains.
Publication also requires observed APC
queries and an append-only cache hit with APC on, plus zero hits with APC off.

## Statistical outputs

The summaries report median, p95, coefficient of variation and a paired,
run-clustered bootstrap 95 percent confidence interval. The process run, not an
individual request, is the unit of analysis. An optional Nsight Systems trace
is diagnostic only and is not required for the statistical result.

# BrickKV performance studies

These runners produce process-level measurements for the BrickKV acceptance
gates. They use synthetic prompts and save no prompt or generated content.

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
  --device npu `
  --hardware-label X1E-78-100 `
  --expected-process-architecture arm64 `
  --source-revision BRICK_COMMIT `
  --output C:/evidence/snapdragon
```

Review the attestation, raw process records, summary and integrity manifest
before interpreting a result.

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

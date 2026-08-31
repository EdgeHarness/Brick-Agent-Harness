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

Before submission, calculate the digest of the exact transferred runner files:

```bash
SOURCE_BUNDLE_DIGEST=$(python -m perf.brickkv.source_bundle)
```

The remote wrapper recomputes this digest before model extraction. Evidence
therefore binds both the Git revision and the exact study code that was
transferred, including deliberate local changes. The model archive is streamed
through a regular-file-only extractor that rejects absolute paths, traversal,
links, special files, duplicate files, and archives without exactly one
`config.json`.

The submit files and exact preparation steps are in
[`chtc/README.md`](chtc/README.md). L40S and A100 results are separate hardware
blocks. They are independent validation of prefix reuse, not evidence that
vLLM implements the GenieX transactional protocol. Quantized Snapdragon and
GPU absolute latency must not be presented as an apples-to-apples hardware
ranking.

Each vLLM process listens on a random loopback port. Its `/v1` API uses a fresh
in-memory key that is neither placed on the command line nor written to
evidence. The runner verifies the authenticated model catalog before recording
measurements. Prompts and generated text are not persisted.

## Statistical outputs

The summaries report median, p95, coefficient of variation and a paired,
run-clustered bootstrap 95 percent confidence interval. The process run, not an
individual request, is the unit of analysis. An optional Nsight Systems trace
is diagnostic only and is not required for the statistical result.

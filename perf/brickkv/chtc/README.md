# CHTC GPU validation for BrickKV

This directory runs a synthetic, single-GPU comparison of vLLM automatic
prefix caching explicitly off and explicitly on. It is independent validation,
not a claim that vLLM implements Brick's managed GenieX protocol.

The submit file follows CHTC's current GPU guidance:

- It requests one GPU and does not set `CUDA_VISIBLE_DEVICES`.
- It selects the experiment's two hardware blocks with the advertised
  `DeviceName` values `NVIDIA L40S` and `NVIDIA A100-SXM4-80GB`.
- It uses long GPU Lab jobs because each block starts a fresh vLLM process for
  every warm-up and measured repetition.
- It transfers the large model archive from `/staging` through OSDF.

Official references checked on 2026-08-30:

- CHTC GPU jobs: https://chtc.cs.wisc.edu/uw-research-computing/gpu-jobs
- CHTC containers: https://chtc.cs.wisc.edu/uw-research-computing/docker-jobs
- CHTC large-file transfer: https://chtc.cs.wisc.edu/uw-research-computing/htc-job-file-transfer
- vLLM serve flags: https://docs.vllm.ai/en/latest/cli/serve/
- vLLM prefix-cache design: https://docs.vllm.ai/en/latest/design/prefix_caching/

## Required preparation

1. Put a Llama 3.1 8B Instruct model directory into one `.tar.zst` archive in
   `/staging`. The archive must contain exactly one `config.json`.
2. Calculate the archive SHA-256 with `sha256sum`.
3. Build or select a vLLM container that contains `vllm`, Python, and `zstd`.
   Resolve its immutable registry digest. A mutable tag is not accepted.
4. Create the local log directory from the repository root:

   ```bash
   mkdir -p logs
   ```

5. From the exact source tree being submitted, compute the transferred runner
   digest:

   ```bash
   SOURCE_BUNDLE_DIGEST=$(python -m perf.brickkv.source_bundle)
   ```

6. Submit from the repository root. Replace every example value:

   ```bash
   condor_submit perf/brickkv/chtc/vllm-apc.sub \
     VLLM_IMAGE='docker://REGISTRY/IMAGE@sha256:IMAGE_DIGEST' \
     CONTAINER_DIGEST='sha256:IMAGE_DIGEST' \
     MODEL_ARCHIVE='osdf:///chtc/staging/u/NETID/brickkv/llama31-8b.tar.zst' \
     MODEL_FILE='llama31-8b.tar.zst' \
     MODEL_ARCHIVE_DIGEST='sha256:MODEL_ARCHIVE_DIGEST' \
     SOURCE_REVISION='BRICK_GIT_COMMIT' \
     SOURCE_BUNDLE_DIGEST="$SOURCE_BUNDLE_DIGEST"
   ```

The wrapper verifies the assigned GPU, archive digest, container-digest
declaration, Git revision shape, and exact transferred source bundle before any
measurement. It extracts only regular files and directories from the model
archive, requires exactly one `config.json`, and never changes
`CUDA_VISIBLE_DEVICES`.

## Measurement behavior

For each GPU type, one job runs five warm-up process blocks followed by ten
measured blocks. Within each block, prefix caching off and on are randomized.
If any run-to-run p95 TTFT coefficient of variation exceeds 8%, the job adds
ten repetitions for both modes. Generated text and prompts are not saved.
Every vLLM process binds a random loopback port and uses a fresh in-memory API
key. Readiness requires an authenticated model-catalog response for the exact
served model name. Results include raw timing records, prefix-cache counter
deltas, output hashes, paired bootstrap intervals, and an integrity manifest.

Do not claim a GPU or cache-performance result until both jobs complete and
their attested `DeviceName`, source bundle, container digest, model archive
digest, and integrity manifest have been checked. Nsight capture is deliberately
not part of the statistical job; add one separate diagnostic job only if CHTC
permits profiling.

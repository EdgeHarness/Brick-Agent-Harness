# brickkv-replay

`brickkv-replay` is a C++20 diagnostic for the GenieX C API. It applies the real
chat template, exercises reset, raw retained-cache and managed lineage traces,
and records versioned JSON without prompt or generated content. Replay schema
`brickkv.replay/4` records whether each completed physical state is reusable
and binds it to the committed source bundle, running executable, and loaded
runtime-module bundle.

It is not the production server and does not prove a speedup on its own.

## Build on Windows ARM64

Open an ARM64 Visual Studio developer shell, then point CMake at an SDK built
from the same pinned GenieX revision used by the experiment:

```powershell
$sourceRevision = git rev-parse HEAD
$sourceBundle = python -m perf.brickkv.source_bundle `
  --revision $sourceRevision --bundle native --verify-git
cmake -S tools/brickkv-replay -B C:/KVBuild/release -G Ninja `
  -DBRICKKV_GENIEX_ROOT=C:/GX/GenieX/sdk/pkg-geniex `
  -DBRICKKV_SOURCE_REVISION=$sourceRevision `
  -DBRICKKV_SOURCE_BUNDLE_DIGEST=$sourceBundle `
  -DCMAKE_BUILD_TYPE=Release
cmake --build C:/KVBuild/release
ctest --test-dir C:/KVBuild/release --output-on-failure
```

The SDK root must contain `include/geniex.h` and the matching GenieX library.
Keep the model bundle and SDK outside Git.

## Linux lineage test with sanitizers

The lineage state machine and SHA-256 implementation do not require the GenieX
runtime:

```bash
cmake -S tools/brickkv-replay -B build/brickkv-sanitize \
  -DBRICKKV_BUILD_REPLAY=OFF \
  -DBRICKKV_SANITIZE=ON \
  -DCMAKE_BUILD_TYPE=Debug
cmake --build build/brickkv-sanitize
ctest --test-dir build/brickkv-sanitize --output-on-failure
```

## Run

```powershell
$replayDigest = "sha256:" + (Get-FileHash `
  C:/KVBuild/release/brickkv-replay.exe -Algorithm SHA256).Hash.ToLowerInvariant()
C:/KVBuild/release/brickkv-replay.exe `
  --model C:/models/Llama-v3.1-8B-Instruct `
  --plugin qairt `
  --device npu `
  --mode all `
  --trace all `
  --hardware-label X1E-78-100 `
  --source-revision $sourceRevision `
  --source-bundle-digest $sourceBundle `
  --replay-digest $replayDigest `
  --runtime-artifact C:/GX/GenieX/sdk/pkg-geniex/lib/geniex.dll `
  --runtime-artifact C:/GX/GenieX/sdk/pkg-geniex/lib/qairt/geniex_plugin.dll `
  --runtime-artifact C:/GX/GenieX/sdk/pkg-geniex/lib/qairt/geniex_core.dll `
  --output C:/evidence/brickkv-replay.json
```

The source revision and source-bundle digest are embedded at compile time and
must match the run arguments. The executable hashes its own running image,
requires every declared runtime module to be loaded from the exact attested
file, rechecks those bytes after the traces, refuses missing attestation fields,
and will not overwrite an existing evidence file.

Supported modes are `reset`, `legacy-test`, `managed` and `all`. Supported
traces are `append_only`, `planning_removed`, `invalid_deleted`,
`context_pruning`, `verifier_detour`, `cancellation_decode` and `all`.

Managed mode retains physical state only after the GenieX runtime reports
`eos`. A length limit, stop sequence, callback stop, unknown stop or error is
not reusable. The logical transcript revision is still recorded after a
completed truncated response, the model is reset immediately, and the next
exact extension reports `reset / previous_not_reusable`. The raw
`legacy-test` mode intentionally keeps its unsafe behavior as the comparison
condition.

For QAIRT, `--context` records the study's expected context but is not sent as
an SDK override. QAIRT bundles own their context configuration and reject a
non-zero `n_ctx`; evidence therefore records `runtime_n_ctx` as `0` (GenieX's
documented "from model" value). For llama.cpp, `runtime_n_ctx` must equal the
requested context.

The output attests the committed native source bundle, running executable,
loaded runtime module bundle, SDK, plugin, model, tokenizer, requested and
resolved device, native process architecture, host processor, system product,
and configuration. The model and tokenizer digest the full artifact tree. The
writer flushes an exclusively created adjacent temporary file, publishes it
through a no-replace hard link, refuses both old evidence and abandoned
temporary evidence, and never silently replaces either. Generated text remains
only in process memory and is represented in evidence by SHA-256.

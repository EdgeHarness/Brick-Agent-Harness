# Experimental tool-calling LoRA package

> **Do not train or treat the output as usable yet.**
>
> The packaging paths are prototypes, but the current generator and evaluation
> design are not sufficient for a valid adapter experiment. Fix the data,
> masking, splits, provenance, and evaluation gates described below before
> spending GPU time.

This folder contains a PEFT/Transformers LoRA trainer, a synthetic JSONL
generator, and Docker, Apptainer/Slurm, and bare-Linux launch paths. It targets a
Llama 3.2 1B-style base by default. None of those launch paths establishes that
the resulting adapter improves the harness.

This legacy training path is outside the `v0.14.0` milestone. It cannot supply a
model, adapter, training result, or condition to the retained Qwen3.5 protocol.
The latest release is `v0.9.0` (S5W Agent Lab hardening), preceded by `v0.8.0`
(S5), `v0.7.0` (B0), `v0.6.0` (S1R), `v0.5.0` (S4), and `v0.4.0` (F0/Q0).
The F0 feasibility gate passed and does not
authorize training. Annotated tags and bound evidence are release-authoritative;
see the `C`/`R`/`D` lifecycle in
[`../PROJECT_SETUP.md`](../PROJECT_SETUP.md).

## Blocking defects

### 1. The default generated data is narrow and duplicated

No JSONL corpus is tracked or shipped. With the checked-in generator's defaults
(`--n 1200 --seed 42 --repair-frac 0.15`), a reproducible local output at
`data/toolcall.jsonl` contains 1,200 rows but only 737 unique rows: 463 rows are
duplicates. There are 661 unique user prompts. The finite slot lists make
additional near-duplicates likely.

Only five of the harness's fourteen default tools appear as targets:

| target tool | rows in the default generated output |
|---|---:|
| `add_event` | 373 |
| `list_events` | 228 |
| `send_message` | 205 |
| `send_email` | 199 |
| `set_reminder` | 195 |

There is no target coverage for `list_emails`, `read_email`,
`create_presentation`, `create_spreadsheet`, `read_spreadsheet`, `think`,
`save_memory`, `recall_memories`, or `done`. The dataset therefore cannot support
claims about general harness tool calling, multi-step work, document creation,
memory use, or completion behavior.

The separate `../finetune/gen_toolcall_data.py` generator is not a harvested or
teacher-distilled expansion. Its default local output is another narrow
synthetic set with the same five target tools and its own duplicates. The
harvested “Source B” and distilled “Source C” scripts referenced elsewhere are
not present.

### 2. Repair examples train on the bad call

The default `training_scripts/make_data.py` output contains 172 multi-turn
repair rows. Each contains:

1. a deliberately malformed assistant call;
2. an error observation;
3. a corrected assistant call.

`train_lora.py:build_example()` assigns loss to **every** assistant turn. As a
result, the deliberately malformed call is a training target as well as the
correction. Calling this “assistant-only loss” is technically true but
misleading for repair rows: it is not final-target-only loss.

Before training, add an explicit per-message target marker or construct labels so
only the desired assistant completion is supervised. Add a unit test proving
that every token from the known-bad assistant turn is `-100`.

### 3. There is no evaluation split or training gate

The trainer loads the entire JSONL as `split="train"` and supplies no
`eval_dataset`. There is:

- no train/validation/test split;
- no deduplication before splitting;
- no stratification by tool, template, or task shape;
- no held-out paraphrase or multi-step set;
- no exact-call, schema-validity, task-success, regression, or safety metric;
- no baseline-versus-adapter evaluation script;
- no contamination audit against the twelve benchmark prompts.

Saying the benchmark is held out because its exact prompts are absent is not
enough. Several generated templates exercise the same narrow calendar and
messaging behaviors, and no semantic-overlap analysis exists.

### 4. Provenance is insufficient

`requirements.txt` pins several Python package versions, but the experiment does
not pin or record all inputs:

- the Hugging Face base model revision and file hashes are not pinned;
- the `unsloth/...` mirror is asserted, not verified here, to match another
  distribution;
- the Docker base image is a mutable tag rather than a digest;
- `llama.cpp` is cloned from the current default branch with no commit pin;
- generated rows carry no schema version, generator commit, template ID, seed,
  or source record;
- `training_meta.json` omits dataset hash, prompt hash, model revision, tokenizer
  revision, dependency lock, git commit, hardware, random seeds, and evaluation
  results.

An adapter is compatible with an exact base model/tokenizer, not merely a similar
display name. Pin and verify revisions and hashes before claiming compatibility
with an Ollama GGUF.

### 5. GGUF conversion is best effort

`--to-gguf` does not guarantee a `.gguf` output. The trainer skips conversion if
`convert_lora_to_gguf.py` is absent and catches a failed converter process while
leaving the PEFT adapter as the only output. The shell wrappers may still print a
successful-looking final message.

The converted adapter is not validated by loading it into a pinned
`llama-server` and comparing logits or held-out task results. `llama-server` is
not launched by this repository's normal agent path, and the current harness
client speaks Ollama's `/api/chat`, not the llama.cpp server API. The router's
`adapter` field is recorded but never applied.

## Required remediation before training

1. Define a versioned data schema and generate balanced coverage for all tools
   that the adapter is expected to call.
2. Remove exact and semantic duplicates before assigning splits.
3. Split by template/task family, not random row, so paraphrases of the same slot
   combination cannot leak across train and evaluation.
4. Fix repair masking so known-bad assistant calls receive no loss.
5. Add unit tests for masking, prompt snapshot drift, schema validity,
   normalization, deduplication, and split isolation.
6. Add a held-out evaluation runner that reports exact tool/argument accuracy,
   invalid-call rate, task-level programmatic score, regressions by tool, and
   repeated trials against the unmodified base.
7. Pin base-model and tokenizer revisions, Docker digest, llama.cpp commit, data
   hash, prompt hash, code commit, and dependency lock; write all of them to the
   output metadata.
8. Make GGUF conversion and a load/smoke test an explicit pass/fail stage.
9. Add a supported llama.cpp provider to the harness before claiming that a
   converted adapter can participate in the router or benchmark.

Only after these gates pass should GPU training begin.

## Package contents

| file | current role |
|---|---|
| `train_lora.py` | LoRA training and optional best-effort GGUF conversion |
| `make_data.py` | standalone five-tool synthetic generator |
| `system_prompt.txt` | frozen harness prompt; the offline suite checks byte parity with the live serving builder |
| `data/toolcall.jsonl` | ignored local generator output; absent from a clean clone |
| `download_assets.py` | downloads an unpinned base snapshot and shallow-clones unpinned llama.cpp |
| `Dockerfile` / `run_local.sh` | NVIDIA Docker packaging prototype |
| `apptainer.def` / `run.slurm` | Apptainer/Slurm packaging prototype |
| `setup.sh` / `run.sh` | bare Linux/CUDA bootstrap prototype |
| `requirements.txt` | partial package pins; not a complete experiment lock |

## What the launch paths actually do

- Docker and Apptainer builds require network access while building. If asset
  download succeeds, the resulting image can run its training step offline.
- `run.sh` uses the current environment if its import probe succeeds; otherwise
  `setup.sh` creates and activates `.venv`. It downloads assets and then trains,
  so it is not an air-gapped path.
- The scripts assume Linux and, for practical training, an NVIDIA CUDA
  environment. Cluster module, driver, filesystem, quota, and container policy
  differences are not automatically handled.
- Resource and duration requirements have not been measured or committed for a
  named GPU and exact configuration. Do not rely on generic time or VRAM claims.

For inspection only, the trainer's intended interface is:

```bash
python train_lora.py \
  --data data/toolcall.jsonl \
  --output out/toolcall-lora
```

Do not train on an unreviewed default generator output. The command is
documented so the code can be reviewed while the blocking data and evaluation
work is fixed.
